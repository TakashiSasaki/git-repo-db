from __future__ import annotations

import base64
import json
import math
import sqlite3
import time
from pathlib import Path

from repo_catalog.adapters.sqlite.coverage import current_coverages
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import repository_identity as identity
from repo_catalog.application.collection_service import select_repositories
from repo_catalog.domain.models import (
    CancellationToken,
    CatalogError,
    CoverageReport,
    GitOid,
    Result,
    fingerprint,
    path_fields,
)


def oid_fields(row):
    return {
        "git_object_id": row["git_object_id"],
        "oid": f"{row['object_format']}:{row['oid'].hex()}",
        "type": row["type"],
        "byte_length": row["size"],
    }


class QueryService:
    def __init__(self, state_dir, token=None):
        self.path = Path(state_dir)
        self.token = token or CancellationToken()

    def execute(self, request):
        from repo_catalog.application.contracts import SearchQuery

        if isinstance(request, SearchQuery):
            options = {
                **request.options,
                "literal": request.literal,
                "scope": request.scope,
                "repos": list(request.repositories),
            }
            command = "search " + request.kind
        else:
            command = request.command
            options = request.options
        return self.query(
            command,
            options,
            limit=request.page.limit,
            cursor=request.page.cursor,
            timeout=request.timeout_seconds,
        )

    def query(self, command, options=None, *, limit=100, cursor=None, timeout=30):
        opts = dict(options or {})
        if not 1 <= limit <= 1000 or not math.isfinite(timeout) or timeout <= 0:
            raise CatalogError(
                "INVALID_ARGUMENT", "Limit must be 1..1000 and timeout positive"
            )
        self.token.check()
        with Store(self.path, readonly=True) as s:
            self.s = s
            self.coverage = CoverageReport()
            self.deadline = time.monotonic() + timeout
            self.backend = "scan"
            self.literal_cache = {}
            s.connection.set_progress_handler(
                lambda: self.token.cancelled or time.monotonic() > self.deadline, 1000
            )
            with s.transaction(read=True):
                if opts.get("source") is not None:
                    opts["source"] = identity.source(s, opts["source"])["source_id"]
                revision = s.revision()
                key = fingerprint({"command": command, "options": opts})
                last = None
                if cursor:
                    try:
                        if len(cursor) > 16384:
                            raise ValueError()
                        token = json.loads(
                            base64.urlsafe_b64decode(
                                cursor + "=" * ((-len(cursor)) % 4)
                            )
                        )
                        if (
                            not isinstance(token, dict)
                            or not isinstance(token.get("last"), list)
                            or not all(type(k) in (str, int) for k in token["last"])
                        ):
                            raise ValueError()
                    except (ValueError, TypeError, json.JSONDecodeError):
                        raise CatalogError("INVALID_ARGUMENT", "Malformed cursor")
                    if (
                        token.get("db") != revision["db_instance_id"]
                        or token.get("seq") != revision["publication_seq"]
                    ):
                        raise CatalogError(
                            "STALE_CURSOR",
                            "Catalog changed; restart the query",
                            {"action": "restart_query"},
                            True,
                        )
                    if token.get("version") != 1 or token.get("query") != key:
                        raise CatalogError(
                            "INVALID_ARGUMENT", "Cursor belongs to another query"
                        )
                    last = token.get("last")
                items = []
                more = False
                page_bytes = 0
                from repo_catalog.adapters.git.runner import hook

                hook("query_started")
                try:
                    self.token.check()
                    self.prepare_coverage(command, opts)
                    for sortkey, item in self.iter_query(command, opts):
                        self.check()
                        if last is not None and sortkey <= last:
                            continue
                        size = len(
                            json.dumps(
                                item, default=lambda b: b.hex(), ensure_ascii=True
                            )
                        )
                        if len(items) == limit or items and page_bytes + size > 8388608:
                            more = True
                            break
                        items.append((sortkey, item))
                        page_bytes += size
                    self.check()
                except (TimeoutError, sqlite3.OperationalError) as e:
                    self.token.check()
                    if (
                        not isinstance(e, TimeoutError)
                        and "interrupt" not in str(e).lower()
                    ):
                        raise
                    self.coverage.add("execution", "timeout")
                    return Result(
                        {
                            "items": [],
                            "page": {
                                "limit": limit,
                                "returned": 0,
                                "has_more": None,
                                "next_cursor": None,
                                "total": None,
                            },
                        },
                        self.coverage,
                        "partial",
                        revision,
                        {
                            "completed": False,
                            "timed_out": True,
                            "backend": self.backend,
                        },
                    )
                next_cursor = None
                if more:
                    token = {
                        "version": 1,
                        "db": revision["db_instance_id"],
                        "seq": revision["publication_seq"],
                        "query": key,
                        "last": items[-1][0],
                    }
                    next_cursor = (
                        base64.urlsafe_b64encode(
                            json.dumps(token, separators=(",", ":")).encode()
                        )
                        .decode()
                        .rstrip("=")
                    )
                return Result(
                    {
                        "items": [item for _, item in items],
                        "page": {
                            "limit": limit,
                            "returned": len(items),
                            "has_more": more,
                            "next_cursor": next_cursor,
                            "total": None,
                        },
                    },
                    self.coverage,
                    "complete"
                    if self.coverage.complete_for_requested_scope
                    else "partial",
                    revision,
                    {"completed": True, "timed_out": False, "backend": self.backend},
                )

    def closure(self, roots):
        ids = [self.s.git_object_id(r["object_format"], r["oid"]) for r in roots]
        ids = [x for x in ids if x is not None]
        if not ids:
            return set()
        values = ",".join("(?)" for _ in ids)
        sql = f"""WITH RECURSIVE edges(a,b) AS (
            SELECT git_object_id,tree_git_object_id FROM commits UNION ALL SELECT commit_git_object_id,parent_git_object_id FROM commit_parents
            UNION ALL SELECT tree_git_object_id,child_git_object_id FROM tree_entries WHERE child_git_object_id IS NOT NULL
            UNION ALL SELECT git_object_id,target_git_object_id FROM tag_objects),
            reach(git_object_id) AS (VALUES {values} UNION SELECT e.b FROM edges e JOIN reach r ON e.a=r.git_object_id)
            SELECT git_object_id FROM reach"""
        return {r[0] for r in self.s.execute(sql, ids)}

    def check(self):
        self.token.check()
        if time.monotonic() > self.deadline:
            raise TimeoutError()

    def prepare_coverage(self, command, o):
        if (
            command
            in (
                "repos list",
                "search code",
                "search path",
                "search hash",
                "search commits",
                "search pr",
            )
            and not o.get("repo")
            and not o.get("repos")
        ):
            for source in self.s.all("SELECT * FROM sources"):
                if o.get("source") and o["source"] != source["source_id"]:
                    continue
                latest = self.s.one(
                    "SELECT asserted_state FROM inventory_observations WHERE source_id=? ORDER BY observed_at_us DESC LIMIT 1",
                    (source["source_id"],),
                )
                if not latest or latest[0] != "complete":
                    self.coverage.add(
                        "inventory",
                        "inventory_incomplete",
                        source_id=source["source_id"],
                    )
        if command.startswith("pr ") or command == "search pr":
            from repo_catalog.application.pr_queries import prepare_pr_coverage

            prepare_pr_coverage(self, command, o)
        if command == "search code":
            seen = set()
            for repo in self.repos(o):
                for _, entry in self.occurrences(repo, o):
                    self.token.check()
                    if time.monotonic() > self.deadline:
                        raise TimeoutError()
                    cid = entry["content_id"]
                    if cid is None:
                        if entry["mode"] != "160000":
                            self.coverage.add(
                                "code",
                                "body_not_saved",
                                git_object_id=entry["git_object_id"],
                                **path_fields(entry["raw_path"]),
                            )
                        continue
                    if cid in seen:
                        continue
                    seen.add(cid)
                    c = self.s.one(
                        "SELECT text_state,raw_text FROM contents WHERE content_id=?",
                        (cid,),
                    )
                    if c["raw_text"] is None:
                        if c["text_state"] == "eligible":
                            self.coverage.add("code", "body_not_saved", content_id=cid)
                        else:
                            self.coverage.excluded_by_policy.append(
                                {"content_id": cid, "reason": c["text_state"]}
                            )

    def repos(self, o):
        selectors = tuple(o.get("repos") or ())
        if o.get("repo"):
            selectors = (o["repo"],)
        return select_repositories(self.s, selectors, o.get("source"))

    def single_repo(self, o):
        selectors = o.get("repos") or []
        if not o.get("repo") and (len(selectors) != 1 or selectors == ["all"]):
            raise CatalogError("INVALID_ARGUMENT", "A single --repo is required")
        rows = self.repos(o)
        if len(rows) != 1:
            raise CatalogError("INVALID_ARGUMENT", "Select one repository")
        return rows[0]

    def snapshot(self, repo, o):
        ident = o.get("snapshot") or repo["current_snapshot_id"]
        row = (
            self.s.one(
                "SELECT * FROM snapshots WHERE snapshot_id=? AND repository_uuidv4=? AND published=1",
                (ident, repo["repository_uuidv4"]),
            )
            if ident
            else None
        )
        if not row:
            if o.get("snapshot"):
                raise CatalogError("NOT_FOUND", "Published snapshot not found")
            self.coverage.add(
                "git", "not_collected", repository_uuidv4=repo["repository_uuidv4"]
            )
        return row

    def roots(self, repo, o):
        scope = o.get("scope") or "current"
        refs = o.get("refs") or []
        kinds = o.get("ref_kinds") or []
        pr = o.get("pr")
        if scope not in ("current", "history", "recorded"):
            raise CatalogError("INVALID_ARGUMENT", "Invalid scope")
        if sum(bool(x) for x in (refs, kinds, pr)) > 1:
            raise CatalogError(
                "INVALID_ARGUMENT", "Root selectors are mutually exclusive"
            )
        if any(not r.startswith("refs/") for r in refs):
            raise CatalogError("INVALID_ARGUMENT", "Ref selectors require full names")
        if o.get("snapshot") and (
            scope == "recorded" or pr or any(k.startswith("pr-") for k in kinds)
        ):
            raise CatalogError(
                "INVALID_ARGUMENT",
                "Snapshot cannot be combined with recorded or PR roots",
            )
        if o.get("snapshot") or pr:
            self.single_repo(o)
        if scope == "current" and (
            pr
            or any(k != "head" for k in kinds)
            or any(not r.startswith("refs/heads/") for r in refs)
        ):
            raise CatalogError("INVALID_ARGUMENT", "Current scope permits only heads")
        if pr or any(k.startswith("pr-") for k in kinds):
            rows = self.s.all(
                "SELECT DISTINCT a.*,p.provider_change_request_number pr_number,o.change_request_observation_id,ca.role origin_role FROM acquisition_roots a JOIN root_origins o ON o.acquisition_root_id=a.acquisition_root_id AND o.origin_kind='pr_role' JOIN change_requests p ON p.change_request_id=o.change_request_id JOIN code_observations co ON co.change_request_id=p.change_request_id AND co.change_request_observation_id=o.change_request_observation_id JOIN code_acquisitions ca ON ca.code_observation_id=co.code_observation_id AND ca.acquisition_root_id=a.acquisition_root_id WHERE a.repository_uuidv4=? AND a.published=1 AND (? IS NULL OR p.provider_change_request_number=?) AND ((?='recorded' AND ? IS NULL) OR o.change_request_observation_id=p.current_change_request_observation_id) AND co.code_observation_id=(SELECT max(latest.code_observation_id) FROM code_observations latest WHERE latest.change_request_id=p.change_request_id AND latest.change_request_observation_id=o.change_request_observation_id) ORDER BY a.acquisition_root_id,ca.role",
                (repo["repository_uuidv4"], pr, pr, scope, pr),
            )
            selected = [
                {
                    "id": r["acquisition_root_id"],
                    "oid": r["oid"],
                    "object_format": r["object_format"],
                    "name": f"pr/{r['pr_number']}/{r['origin_role']}",
                    "snapshot": None,
                    "role": r["origin_role"],
                }
                for r in rows
                if not kinds
                or ("pr-head" if r["origin_role"] == "head" else "pr-related") in kinds
            ]
            if pr and not selected:
                self.coverage.add(
                    "pr",
                    "pr_root_unavailable",
                    repository_uuidv4=repo["repository_uuidv4"],
                    number=pr,
                )
            normal = [k for k in kinds if not k.startswith("pr-")]
            if normal:
                selected += self.roots(repo, {**o, "ref_kinds": normal})
            return selected
        if scope == "recorded":
            rows = self.s.all(
                "SELECT DISTINCT a.*,o.root_origin_id origin_id,o.snapshot_id,o.raw_ref_name,p.provider_change_request_number pr_number,f.kind ref_kind,ca.role origin_role FROM acquisition_roots a LEFT JOIN root_origins o ON o.acquisition_root_id=a.acquisition_root_id LEFT JOIN change_requests p ON p.change_request_id=o.change_request_id LEFT JOIN ref_observations f ON f.snapshot_id=o.snapshot_id AND f.raw_ref_name=o.raw_ref_name LEFT JOIN code_observations co ON co.change_request_id=o.change_request_id AND co.change_request_observation_id=o.change_request_observation_id LEFT JOIN code_acquisitions ca ON ca.code_observation_id=co.code_observation_id AND ca.acquisition_root_id=a.acquisition_root_id WHERE a.repository_uuidv4=? AND a.published=1 ORDER BY a.acquisition_root_id,o.root_origin_id,ca.role",
                (repo["repository_uuidv4"],),
            )
            return [
                {
                    "id": r["origin_id"] or r["acquisition_root_id"],
                    "oid": r["oid"],
                    "object_format": r["object_format"],
                    "name": r["raw_ref_name"].decode("utf8", "backslashreplace")
                    if r["raw_ref_name"]
                    else f"pr/{r['pr_number']}/{r['origin_role'] or r['role']}",
                    "snapshot": r["snapshot_id"],
                    "role": r["origin_role"] or r["ref_kind"] or r["role"],
                }
                for r in rows
                if (not refs or r["raw_ref_name"] in [x.encode() for x in refs])
                and (
                    not kinds
                    or (
                        r["ref_kind"]
                        if r["raw_ref_name"]
                        else "pr-head"
                        if r["origin_role"] == "head"
                        else "pr-related"
                        if r["pr_number"]
                        else r["role"]
                    )
                    in kinds
                )
            ]
        snapshot = self.snapshot(repo, o)
        if not snapshot:
            return []
        rows = self.s.all(
            "SELECT * FROM ref_observations WHERE snapshot_id=? ORDER BY raw_ref_name",
            (snapshot["snapshot_id"],),
        )
        selected = [
            r
            for r in rows
            if (
                r["raw_ref_name"] in [x.encode() for x in refs]
                if refs
                else r["kind"] in kinds
                if kinds
                else r["kind"] == "head" or scope == "history"
            )
        ]
        if refs and len(selected) != len(set(refs)):
            raise CatalogError("NOT_FOUND", "Ref not present in selected snapshot")
        return [
            {
                "id": r["raw_ref_name"].hex(),
                "oid": r["target_oid"],
                "object_format": r["object_format"],
                "name": r["raw_ref_name"].decode("utf8", "backslashreplace"),
                "snapshot": snapshot["snapshot_id"],
                "role": r["kind"],
            }
            for r in selected
        ]

    def peel(self, fmt, oid):
        row = self.s.one(
            "SELECT * FROM git_objects WHERE object_format=? AND oid=?", (fmt, oid)
        )
        seen = set()
        while row and row["type"] == "tag":
            if row["git_object_id"] in seen:
                raise CatalogError("INTEGRITY_ERROR", "Tag cycle")
            seen.add(row["git_object_id"])
            row = self.s.one(
                "SELECT g.* FROM tag_objects t JOIN git_objects g ON g.git_object_id=t.target_git_object_id WHERE t.git_object_id=?",
                (row["git_object_id"],),
            )
        if row is None:
            self.coverage.add(
                "git", "root_object_missing", object_format=fmt, oid=oid.hex()
            )
        return row

    def commit_set(self, roots, first_parent=False):
        ids = []
        for root in roots:
            obj = self.peel(root["object_format"], root["oid"])
            if obj and obj["type"] == "commit":
                if not self.s.one(
                    "SELECT 1 FROM commits WHERE git_object_id=?",
                    (obj["git_object_id"],),
                ):
                    self.coverage.add(
                        "git",
                        "commit_structure_missing",
                        git_object_id=obj["git_object_id"],
                    )
                ids.append(obj["git_object_id"])
        if not ids:
            return set()
        values = ",".join("(?)" for _ in ids)
        where = " WHERE p.parent_ordinal=0" if first_parent else ""
        return {
            r[0]
            for r in self.s.all(
                f"WITH RECURSIVE reach(git_object_id) AS (VALUES {values} UNION SELECT p.parent_git_object_id FROM commit_parents p JOIN reach r ON p.commit_git_object_id=r.git_object_id{where}) SELECT git_object_id FROM reach",
                ids,
            )
        }

    def tree_entries(self, tree, prefix=b""):
        # Raw byte frames avoid text coercion and terminate incomplete/cyclic
        # imported trees while preserving the usable recorded entries.
        frames = [(tree, prefix, frozenset())]
        while frames:
            self.token.check()
            if time.monotonic() > self.deadline:
                raise TimeoutError()
            ident, raw_prefix, ancestors = frames.pop()
            if ident in ancestors:
                self.coverage.add("git", "tree_cycle", git_object_id=ident)
                continue
            rows = self.s.all(
                "SELECT * FROM tree_entries WHERE tree_git_object_id=? ORDER BY raw_name",
                (ident,),
            )
            if not rows:
                obj = self.s.one(
                    "SELECT size FROM git_objects WHERE git_object_id=?", (ident,)
                )
                if not obj or obj["size"]:
                    self.coverage.add(
                        "git", "tree_structure_missing", git_object_id=ident
                    )
            subtrees = []
            for row in rows:
                raw_path = raw_prefix + row["raw_name"]
                if row["mode"] == 16384:
                    subtrees.append(
                        (
                            row["child_git_object_id"],
                            raw_path + b"/",
                            ancestors | {ident},
                        )
                    )
                    continue
                content = self.s.one(
                    "SELECT c.* FROM blob_content_map b JOIN contents c ON c.content_id=b.content_id WHERE b.git_object_id=?",
                    (row["child_git_object_id"],),
                )
                yield {
                    "raw_path": raw_path,
                    "mode": format(row["mode"], "06o"),
                    "oid": f"{row['child_format']}:{row['child_oid'].hex()}",
                    "git_object_id": row["child_git_object_id"],
                    "content_id": content["content_id"] if content else None,
                    "text_state": content["text_state"] if content else "unknown",
                    "raw_available": bool(content and content["raw_text"] is not None),
                }
            frames.extend(reversed(subtrees))

    def occurrences(self, repo, o):
        roots = self.roots(repo, o)
        scope = o.get("scope") or "current"
        if scope == "current":
            for root in sorted(roots, key=lambda r: r["name"]):
                obj = self.peel(root["object_format"], root["oid"])
                if not obj or obj["type"] != "commit":
                    continue
                tree = self.s.one(
                    "SELECT tree_git_object_id FROM commits WHERE git_object_id=?",
                    (obj["git_object_id"],),
                )
                if tree is None:
                    self.coverage.add(
                        "git",
                        "commit_structure_missing",
                        git_object_id=obj["git_object_id"],
                    )
                    continue
                for entry in self.tree_entries(tree[0]):
                    yield (
                        (root["name"], entry["raw_path"].hex()),
                        {
                            "repository_uuidv4": repo["repository_uuidv4"],
                            "snapshot_id": root["snapshot"],
                            "ref": root["name"],
                            "commit": f"{obj['object_format']}:{obj['oid'].hex()}",
                            **entry,
                        },
                    )
        else:
            commits = self.commit_set(roots)
            for obj in self.s.execute(
                "SELECT g.*,c.tree_git_object_id FROM commits c JOIN git_objects g ON g.git_object_id=c.git_object_id ORDER BY g.oid"
            ):
                if obj["git_object_id"] not in commits:
                    continue
                for entry in self.tree_entries(obj["tree_git_object_id"]):
                    yield (
                        (obj["oid"].hex(), entry["raw_path"].hex()),
                        {
                            "repository_uuidv4": repo["repository_uuidv4"],
                            "commit": f"{obj['object_format']}:{obj['oid'].hex()}",
                            **entry,
                        },
                    )

    def public_object(self, repo, obj):
        sources = self.s.all(
            "SELECT p.git_acquisition_id,r.state FROM repository_object_sources p LEFT JOIN acquisition_progress r ON r.git_acquisition_id=p.git_acquisition_id WHERE p.repository_uuidv4=? AND p.git_object_id=? ORDER BY p.git_acquisition_id",
            (repo["repository_uuidv4"], obj),
        )
        if sources and not any(row["state"] == "published" for row in sources):
            self.coverage.add(
                "git",
                "acquisition_not_published",
                repository_uuidv4=repo["repository_uuidv4"],
                git_object_id=obj,
            )
        return bool(sources)

    def literal(self, o):
        text = o.get("literal")
        if not text:
            raise CatalogError("INVALID_ARGUMENT", "A nonempty literal is required")
        return text

    def literal_match(self, kind, key, body, literal):
        cachekey = (kind, key, literal)
        if cachekey in self.literal_cache:
            return self.literal_cache[cachekey]
        matched = literal in body
        if len(literal) >= 3 and self.s.config["search"]["backend"] != "scan":
            generation = self.s.one(
                "SELECT * FROM index_generations WHERE kind=? AND state='ready' ORDER BY index_generation_id DESC LIMIT 1",
                (kind,),
            )
            doc = self.s.one(
                "SELECT search_document_id FROM search_documents WHERE kind=? AND source_key=?",
                (kind, str(key)),
            )
            if (
                generation
                and doc
                and self.s.one(
                    "SELECT 1 FROM index_membership WHERE index_generation_id=? AND search_document_id=?",
                    (generation["index_generation_id"], doc["search_document_id"]),
                )
            ):
                try:
                    quoted = '"' + literal.replace('"', '""') + '"'
                    hit = self.s.one(
                        f"SELECT rowid FROM {generation['table_name']} WHERE rowid=? AND {generation['table_name']} MATCH ?",
                        (doc["search_document_id"], quoted),
                    )
                    self.backend = "fts+scan"
                    matched = bool(hit) and matched
                except sqlite3.Error:
                    self.backend = "scan"
        # Bound this per-page memoization; never retain every matching document in a large catalog.
        if len(self.literal_cache) < 2000:
            self.literal_cache[cachekey] = matched
        return matched

    def iter_query(self, command, o):
        s = self.s
        if command in ("instances list", "instances show"):
            from repo_catalog.application.repository_identity import instance

            rows = (
                [instance(s, o["instance"])]
                if command.endswith("show")
                else s.all(
                    "SELECT * FROM service_instances ORDER BY service_instance_uuidv4"
                )
            )
            for row in rows:
                yield (
                    [row["service_instance_uuidv4"]],
                    {**dict(row), "metadata": json.loads(row["metadata"])},
                )
        elif command == "endpoints list":
            repo = self.single_repo(o)
            for row in s.all(
                "SELECT * FROM repository_endpoints WHERE repository_uuidv4=? ORDER BY repository_endpoint_id",
                (repo["repository_uuidv4"],),
            ):
                yield (
                    [row["repository_endpoint_id"]],
                    {**dict(row), "metadata": json.loads(row["metadata"])},
                )
        elif command in ("repos list", "repos show"):
            for r in self.repos(o):
                item = {**dict(r), "metadata": json.loads(r["metadata"])}
                if command == "repos show":
                    item["nested_collections"] = {}
                    for name, table in [
                        ("endpoints", "repository_endpoints"),
                        ("bindings", "repository_bindings"),
                        ("sources", "source_repositories"),
                    ]:
                        total = s.one(
                            f"SELECT count(*) FROM {table} WHERE repository_uuidv4=?",
                            (r["repository_uuidv4"],),
                        )[0]
                        rows = s.all(
                            f"SELECT * FROM {table} WHERE repository_uuidv4=? ORDER BY 1 LIMIT 100",
                            (r["repository_uuidv4"],),
                        )
                        item[name] = [dict(row) for row in rows]
                        item["nested_collections"][name] = {
                            "returned": len(rows),
                            "total": total,
                            "has_more": total > len(rows),
                        }
                yield [r["repository_uuidv4"]], item
        elif command in ("snapshots list", "snapshots show"):
            if command.endswith("show"):
                row = s.one(
                    "SELECT * FROM snapshots WHERE snapshot_id=? AND published=1",
                    (o.get("snapshot"),),
                )
                if not row:
                    raise CatalogError("NOT_FOUND", "Snapshot not found")
                rows = [row]
            else:
                repo = self.single_repo(o)
                rows = s.all(
                    "SELECT * FROM snapshots WHERE repository_uuidv4=? AND published=1 ORDER BY generation",
                    (repo["repository_uuidv4"],),
                )
            for r in rows:
                yield (
                    [r["repository_uuidv4"], r["generation"]],
                    {
                        **dict(r),
                        "run": dict(
                            s.one(
                                "SELECT * FROM git_acquisitions WHERE git_acquisition_id=?",
                                (r["git_acquisition_id"],),
                            )
                        ),
                        "coverage": current_coverages(
                            s.connection, r["repository_uuidv4"]
                        ),
                    },
                )
        elif command == "refs list":
            repo = self.single_repo(o)
            snapshot = self.snapshot(repo, o)
            if not snapshot:
                return
            for r in s.all(
                "SELECT * FROM ref_observations WHERE snapshot_id=? ORDER BY raw_ref_name",
                (snapshot["snapshot_id"],),
            ):
                if o.get("ref_kinds") and r["kind"] not in o["ref_kinds"]:
                    continue
                yield (
                    [r["raw_ref_name"].hex()],
                    {
                        "ref": r["raw_ref_name"].decode("utf8", "backslashreplace"),
                        "ref_b64": base64.b64encode(r["raw_ref_name"]).decode(),
                        "kind": r["kind"],
                        "oid": f"{r['object_format']}:{r['target_oid'].hex()}",
                        "peeled_oid": f"{r['object_format']}:{r['peeled_oid'].hex()}"
                        if r["peeled_oid"]
                        else None,
                        "snapshot_id": snapshot["snapshot_id"],
                    },
                )
        elif command in (
            "tree list",
            "file show",
            "commits list",
            "commits show",
            "commits compare",
        ):
            repo = self.single_repo(o)
            if command == "commits compare":
                left = self.commit_set(self.roots(repo, {**o, "refs": [o["left"]]}))
                right = self.commit_set(self.roots(repo, {**o, "refs": [o["right"]]}))
                ids = {
                    "left-only": left - right,
                    "right-only": right - left,
                    "common": left & right,
                    "symmetric": left ^ right,
                }[o["set"]]
            else:
                if o.get("commit"):
                    oid = GitOid.parse(o["commit"])
                    obj = self.peel(oid.algorithm, oid.value)
                    if not obj or not self.public_object(repo, obj["git_object_id"]):
                        raise CatalogError(
                            "NOT_FOUND", "Commit not publicly acquired for this repo"
                        )
                    roots = [{"object_format": oid.algorithm, "oid": oid.value}]
                else:
                    if not o.get("ref"):
                        raise CatalogError(
                            "INVALID_ARGUMENT", "--ref or --commit required"
                        )
                    roots = self.roots(repo, {**o, "refs": [o["ref"]]})
                ids = self.commit_set(roots, o.get("first_parent", False))
                if command == "commits show":
                    obj = self.peel(roots[0]["object_format"], roots[0]["oid"])
                    if not obj or obj["type"] != "commit":
                        raise CatalogError(
                            "NOT_FOUND", "Stored commit structure missing"
                        )
                    ids = {obj["git_object_id"]}
                if command in ("tree list", "file show"):
                    obj = self.peel(roots[0]["object_format"], roots[0]["oid"])
                    if not obj or obj["type"] not in ("tree", "commit"):
                        raise CatalogError(
                            "INVALID_ARGUMENT",
                            "Tree query requires a commit or tree root",
                        )
                    tree = (
                        obj["git_object_id"]
                        if obj["type"] == "tree"
                        else s.one(
                            "SELECT tree_git_object_id FROM commits WHERE git_object_id=?",
                            (obj["git_object_id"],),
                        )[0]
                    )
                    wanted = None
                    if command == "file show":
                        from repo_catalog.application.target_queries import (
                            TargetQueryService,
                        )

                        wanted = TargetQueryService._path(o)
                    found = False
                    for entry in self.tree_entries(tree):
                        if wanted is not None and entry["raw_path"] != wanted:
                            continue
                        found = True
                        if o.get("path_prefix") and not entry["raw_path"].startswith(
                            o["path_prefix"].encode()
                        ):
                            continue
                        raw = entry.pop("raw_path")
                        if command == "file show":
                            content = (
                                s.one(
                                    "SELECT * FROM contents WHERE content_id=?",
                                    (entry["content_id"],),
                                )
                                if entry["content_id"]
                                else None
                            )
                            entry["text"] = content["raw_text"] if content else None
                            entry["byte_length"] = (
                                content["byte_length"] if content else None
                            )
                            if entry["text"] is None and entry["mode"] != "160000":
                                self.coverage.add(
                                    "code",
                                    "body_not_saved",
                                    content_id=entry["content_id"],
                                    **path_fields(raw),
                                )
                        yield [raw.hex()], {**entry, **path_fields(raw)}
                    if wanted is not None and not found:
                        raise CatalogError(
                            "NOT_FOUND", "Raw path not present in stored tree"
                        )
                    return
            for r in s.execute(
                "SELECT g.*,c.* FROM commits c JOIN git_objects g ON g.git_object_id=c.git_object_id ORDER BY g.oid"
            ):
                if r["git_object_id"] not in ids:
                    continue
                parents = s.all(
                    "SELECT g.object_format,g.oid FROM commit_parents p JOIN git_objects g ON g.git_object_id=p.parent_git_object_id WHERE p.commit_git_object_id=? ORDER BY parent_ordinal",
                    (r["git_object_id"],),
                )
                tree = s.one(
                    "SELECT * FROM git_objects WHERE git_object_id=?",
                    (r["tree_git_object_id"],),
                )
                yield (
                    [r["oid"].hex()],
                    {
                        **oid_fields(r),
                        "repository_uuidv4": repo["repository_uuidv4"],
                        "parents": [
                            f"{p['object_format']}:{p['oid'].hex()}" for p in parents
                        ],
                        "tree": f"{tree['object_format']}:{tree['oid'].hex()}",
                        "message": r["raw_message"].decode("utf8", "replace"),
                        "message_b64": base64.b64encode(r["raw_message"]).decode(),
                        "raw_headers_b64": base64.b64encode(r["raw_headers"]).decode(),
                        "metadata": json.loads(r["metadata"]),
                    },
                )
        elif command in ("search path", "search code", "search commits", "search hash"):
            repos = self.repos(o)
            if command == "search hash":
                scoped = {
                    repo["repository_uuidv4"]: self.closure(self.roots(repo, o))
                    for repo in repos
                }
                algo = o["algorithm"].removeprefix("raw-")
                try:
                    digest = bytes.fromhex(o["digest"])
                    if len(digest) != {"md5": 16, "sha1": 20, "sha256": 32}[algo]:
                        raise ValueError()
                except (ValueError, KeyError):
                    raise CatalogError("INVALID_ARGUMENT", "Invalid full-length digest")
                rows = s.all(
                    "SELECT c.* FROM contents c JOIN content_digests d ON d.content_id=c.content_id WHERE d.algorithm=? AND d.digest=? ORDER BY c.content_id",
                    (algo, digest),
                )
                allowed = {r["repository_uuidv4"] for r in repos}
                for c in rows:
                    if (
                        o.get("byte_length") is not None
                        and c["byte_length"] != o["byte_length"]
                    ):
                        continue
                    sources = s.all(
                        "SELECT DISTINCT p.repository_uuidv4,p.git_acquisition_id,r.state acquisition_state,g.object_format,g.oid FROM repository_object_sources p LEFT JOIN acquisition_progress r ON r.git_acquisition_id=p.git_acquisition_id JOIN git_objects g ON g.git_object_id=p.git_object_id JOIN blob_content_map b ON b.git_object_id=g.git_object_id WHERE b.content_id=? ORDER BY p.repository_uuidv4,p.git_acquisition_id",
                        (c["content_id"],),
                    )
                    sources = [
                        {**dict(r), "oid": f"{r['object_format']}:{r['oid'].hex()}"}
                        for r in sources
                        if r["repository_uuidv4"] in allowed
                        and self.s.git_object_id(r["object_format"], r["oid"])
                        in scoped[r["repository_uuidv4"]]
                    ]
                    if sources:
                        if not any(
                            row["acquisition_state"] == "published" for row in sources
                        ):
                            self.coverage.add(
                                "git",
                                "acquisition_not_published",
                                content_id=c["content_id"],
                            )
                        yield (
                            [c["content_id"]],
                            {
                                "content_id": c["content_id"],
                                "byte_length": c["byte_length"],
                                "representation": "raw-content-v1",
                                "digests": {
                                    r["algorithm"]: r["digest"].hex()
                                    for r in s.all(
                                        "SELECT * FROM content_digests WHERE content_id=?",
                                        (c["content_id"],),
                                    )
                                },
                                "verification": "verified",
                                "sources": sources,
                            },
                        )
                return
            if command == "search path":
                if o.get("path") is not None and o.get("path_b64") is not None:
                    raise CatalogError(
                        "INVALID_ARGUMENT", "Path forms are mutually exclusive"
                    )
                try:
                    path = (
                        base64.b64decode(o["path_b64"], validate=True)
                        if o.get("path_b64") is not None
                        else o["path"].encode()
                        if o.get("path") is not None
                        else None
                    )
                except ValueError:
                    raise CatalogError("INVALID_ARGUMENT", "Invalid path base64")
                if path is None and o.get("content_id") is None:
                    raise CatalogError(
                        "INVALID_ARGUMENT", "Path or content ID required"
                    )
            else:
                literal = self.literal(o)
            for repo in repos:
                if command == "search commits":
                    ids = self.commit_set(self.roots(repo, o))
                    needle = literal.encode("utf8")
                    for r in s.execute(
                        "SELECT g.*,c.raw_message FROM commits c JOIN git_objects g ON g.git_object_id=c.git_object_id ORDER BY g.oid"
                    ):
                        message = r["raw_message"].decode("utf8", "replace")
                        if (
                            r["git_object_id"] in ids
                            and needle in r["raw_message"]
                            and self.literal_match(
                                "commits", r["git_object_id"], message, literal
                            )
                        ):
                            offset = r["raw_message"].index(needle)
                            yield (
                                [repo["repository_uuidv4"], r["oid"].hex()],
                                {
                                    **oid_fields(r),
                                    "repository_uuidv4": repo["repository_uuidv4"],
                                    "message": message,
                                    "message_b64": base64.b64encode(
                                        r["raw_message"]
                                    ).decode(),
                                    "byte_start": offset,
                                    "byte_end": offset + len(needle),
                                    "line": r["raw_message"][:offset].count(b"\n") + 1,
                                },
                            )
                    continue
                for sortkey, entry in self.occurrences(repo, o):
                    raw = entry.pop("raw_path")
                    if command == "search path":
                        if (
                            o.get("content_id") is not None
                            and entry["content_id"] != o["content_id"]
                        ):
                            continue
                        if path is not None:
                            mode = o.get("path_mode") or "exact"
                            if not (
                                raw == path
                                if mode == "exact"
                                else raw.startswith(path)
                                if mode == "prefix"
                                else path in raw
                            ):
                                continue
                    else:
                        if not entry["content_id"]:
                            continue
                        c = s.one(
                            "SELECT * FROM contents WHERE content_id=?",
                            (entry["content_id"],),
                        )
                        if c["raw_text"] is None:
                            continue
                        if not self.literal_match(
                            "code", c["content_id"], c["raw_text"], literal
                        ):
                            continue
                        offset = c["raw_text"].index(literal)
                        entry.update(
                            byte_start=len(c["raw_text"][:offset].encode()),
                            byte_end=len(
                                c["raw_text"][: offset + len(literal)].encode()
                            ),
                            line=c["raw_text"][:offset].count("\n") + 1,
                            snippet=c["raw_text"][
                                max(0, offset - 40) : offset + len(literal) + 80
                            ],
                        )
                    yield (
                        [repo["repository_uuidv4"], *sortkey],
                        {**entry, **path_fields(raw)},
                    )
        elif command == "content show":
            c = s.one("SELECT * FROM contents WHERE content_id=?", (o["content_id"],))
            if not c:
                raise CatalogError("NOT_FOUND", "Content not found")
            if c["raw_text"] is None:
                raise CatalogError(
                    "RAW_CONTENT_UNAVAILABLE",
                    "Raw bytes are not durably saved",
                    {"content_id": c["content_id"], "reason": c["text_state"]},
                )
            offset = o.get("offset", 0)
            length = o.get("length", 65536)
            if offset < 0 or not 0 <= length <= 1048576:
                raise CatalogError(
                    "INVALID_ARGUMENT",
                    "Raw range must be nonnegative and at most 1 MiB",
                )
            raw = c["raw_text"].encode()
            part = raw[offset : offset + length]
            yield (
                [c["content_id"]],
                {
                    "content_id": c["content_id"],
                    "offset": offset,
                    "requested_length": length,
                    "returned_length": len(part),
                    "byte_length": len(raw),
                    "data_b64": base64.b64encode(part).decode(),
                    "has_more": offset + len(part) < len(raw),
                    "digests": {
                        r["algorithm"]: r["digest"].hex()
                        for r in s.all(
                            "SELECT * FROM content_digests WHERE content_id=?",
                            (c["content_id"],),
                        )
                    },
                },
            )
        elif command in ("jobs list", "jobs show"):
            rows = s.all(
                "SELECT j.*,a.state,a.attempt,a.not_before_us,a.checkpoint,a.reason,a.updated_at_us FROM jobs j LEFT JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt"
                + (" WHERE j.job_id=?" if o.get("job_id") else "")
                + " ORDER BY j.job_id",
                (o["job_id"],) if o.get("job_id") else (),
            )
            if o.get("job_id") and not rows:
                raise CatalogError("NOT_FOUND", "Job not found")
            for r in rows:
                yield (
                    [r["job_id"]],
                    {
                        **dict(r),
                        "request": json.loads(r["request"]),
                        "checkpoint": json.loads(r["checkpoint"]),
                    },
                )
        elif command in ("coverage", "status"):
            for repo in self.repos(o):
                snapshot = self.snapshot(repo, o)
                components = current_coverages(
                    s.connection, repo["repository_uuidv4"], o.get("kind")
                )
                yield (
                    [repo["repository_uuidv4"]],
                    {
                        "repository_uuidv4": repo["repository_uuidv4"],
                        "snapshot_id": snapshot["snapshot_id"] if snapshot else None,
                        "components": components,
                    },
                )
        elif command.startswith("pr ") or command == "search pr":
            yield from self.pr_query(command, o)
        elif command == "cache status":
            for r in s.all(
                "SELECT a.*,l.repository_uuidv4,l.path,l.access FROM active_cache_entries a JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE l.access='target_active' ORDER BY a.active_cache_entry_id"
            ):
                from repo_catalog.adapters.filesystem.cache import CacheManager
                from repo_catalog.adapters.filesystem.capacity import (
                    Capacity,
                    allocated_bytes,
                )

                path, quarantine = CacheManager(s).paths(r)
                yield (
                    [r["active_cache_entry_id"]],
                    {
                        **dict(r),
                        "bytes": allocated_bytes(path) + allocated_bytes(quarantine),
                        "budget": s.config["cache"],
                        "managed_usage_bytes": Capacity(s).used(),
                        "reservations": [
                            dict(x) for x in s.all("SELECT * FROM space_reservations")
                        ],
                        "blocked_by": CacheManager(s).gate(r),
                    },
                )
        else:
            raise CatalogError("INVALID_ARGUMENT", "Unknown query")

    def pr_query(self, command, o):
        # Implemented alongside the API collector, using only persisted state.
        from repo_catalog.application.pr_queries import pr_query

        yield from pr_query(self, command, o)
