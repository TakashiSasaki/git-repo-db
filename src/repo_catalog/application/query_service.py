from __future__ import annotations

import base64
import heapq
import json
import math
import sqlite3
import time
from pathlib import Path

from repo_catalog.adapters.sqlite.coverage import current_coverages
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import repository_identity as identity
from repo_catalog.application.collection_service import select_repositories
from repo_catalog.application.git_query_context import object_context
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
            self.collection_proof_graph = None
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
        found = set()
        for root in roots:
            ident = self.s.git_object_id(root["object_format"], root["oid"])
            if ident is None:
                continue
            scope = self.git_scope(root)
            sql = f"""WITH RECURSIVE edges(a,b) AS (
                SELECT git_object_id,tree_git_object_id FROM {self.git_relation("commits", root)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=?
                UNION ALL SELECT commit_git_object_id,parent_git_object_id FROM {self.git_relation("commit_parents", root)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=?
                UNION ALL SELECT tree_git_object_id,child_git_object_id FROM {self.git_relation("tree_entries", root)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=? AND child_git_object_id IS NOT NULL
                UNION ALL SELECT git_object_id,target_git_object_id FROM {self.git_relation("tag_objects", root)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=?),
                reach(git_object_id) AS (VALUES (?) UNION SELECT e.b FROM edges e JOIN reach r ON e.a=r.git_object_id)
                SELECT git_object_id FROM reach"""
            found.update(r[0] for r in self.s.execute(sql, (*(scope * 4), ident)))
        return found

    @staticmethod
    def git_relation(table, context):
        return (
            "eligible_git_" if context.get("historical") else "current_git_"
        ) + table

    @staticmethod
    def git_scope(context):
        return context["repository_uuidv4"], context["parsed_result_uuidv4"]

    def git_context(self, repo, options):
        if options.get("snapshot"):
            snapshot = self.snapshot(repo, options)
            return {
                "repository_uuidv4": repo["repository_uuidv4"],
                "parsed_result_uuidv4": snapshot["parsed_result_uuidv4"],
                "historical": True,
            }
        selected = self.s.one(
            "SELECT parsed_result_uuidv4 FROM active_fact_selections WHERE repository_uuidv4=? AND fact_kind='git' AND change_request_id IS NULL AND git_acquisition_id IS NULL",
            (repo["repository_uuidv4"],),
        )
        return {
            "repository_uuidv4": repo["repository_uuidv4"],
            "parsed_result_uuidv4": selected[0] if selected else None,
            "historical": False,
        }

    def git_content(self, context, object_id):
        return self.s.one(
            f"SELECT t.*,c.byte_length FROM {self.git_relation('text_facts', context)} t JOIN contents c USING(content_id) WHERE t.repository_uuidv4=? AND t.parsed_result_uuidv4=? AND t.git_object_id=?",
            (*self.git_scope(context), object_id),
        )

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
                "search issue",
                "issue list",
            )
            and not o.get("repo")
            and not o.get("repos")
        ):
            for source in self.s.all("SELECT * FROM sources"):
                if o.get("source") and o["source"] != source["source_id"]:
                    continue
                latest = self.s.one(
                    "SELECT asserted_state FROM current_inventory_observations WHERE source_id=?",
                    (source["source_id"],),
                )
                if not latest or latest[0] != "complete":
                    self.coverage.add(
                        "inventory",
                        "inventory_incomplete",
                        source_id=source["source_id"],
                    )
        if command in ("repos list", "repos show"):
            for repo in self.repos(o):
                for source in self.s.execute(
                    "SELECT DISTINCT history.source_registration_uuidv4 "
                    "FROM repository_inventory_observations history "
                    "WHERE history.repository_uuidv4=? AND NOT EXISTS(SELECT 1 "
                    "FROM current_inventory_observations selected "
                    "WHERE selected.source_registration_uuidv4=history.source_registration_uuidv4)",
                    (repo["repository_uuidv4"],),
                ):
                    self.coverage.add(
                        "inventory",
                        "inventory_selection_unresolved",
                        repository_uuidv4=repo["repository_uuidv4"],
                        source_registration_uuidv4=source[0],
                    )
        if command.startswith("pr ") or command == "search pr":
            from repo_catalog.application.pr_queries import prepare_pr_coverage

            prepare_pr_coverage(self, command, o)
        if command.startswith("issue ") or command == "search issue":
            from repo_catalog.application.issue_queries import prepare_issue_coverage

            prepare_issue_coverage(self, command, o)
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
                    fact = entry.get("git_text_fact_uuidv4")
                    if fact in seen:
                        continue
                    seen.add(fact)
                    c = self.s.one(
                        "SELECT text_state,raw_text FROM eligible_git_text_facts WHERE git_fact_uuidv4=?",
                        (fact,),
                    )
                    if c is None or c["raw_text"] is None:
                        if c is None or c["text_state"] == "eligible":
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
        ident = o.get("snapshot")
        row = (
            self.s.one(
                "SELECT s.* FROM snapshots s JOIN usable_parsed_results r USING(parsed_result_uuidv4) "
                "JOIN effective_repository_parser_profiles e ON e.repository_uuidv4=s.repository_uuidv4 AND e.fact_kind='git' AND e.parser_profile_uuidv4=r.parser_profile_uuidv4 "
                "WHERE s.snapshot_id=? AND s.repository_uuidv4=? AND s.published=1",
                (ident, repo["repository_uuidv4"]),
            )
            if ident
            else self.s.one(
                "SELECT * FROM current_snapshots WHERE repository_uuidv4=? AND published=1",
                (repo["repository_uuidv4"],),
            )
        )
        if not row:
            if ident:
                raise CatalogError("NOT_FOUND", "Published usable snapshot not found")
            self.coverage.add(
                "git",
                "current_selection_unresolved"
                if self.s.one(
                    "SELECT 1 FROM snapshots WHERE repository_uuidv4=? LIMIT 1",
                    (repo["repository_uuidv4"],),
                )
                else "not_collected",
                repository_uuidv4=repo["repository_uuidv4"],
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
            code_view = (
                "eligible_code_observations"
                if scope == "recorded"
                else "current_code_observations"
            )
            rows = self.s.all(
                "SELECT DISTINCT a.*,p.provider_change_request_number pr_number,"
                "o.change_request_observation_id,ca.role origin_role FROM acquisition_roots a "
                "JOIN root_origins o ON o.acquisition_root_id=a.acquisition_root_id AND o.origin_kind='pr_role' "
                "JOIN change_requests p ON p.change_request_id=o.change_request_id "
                f"JOIN {code_view} co ON co.change_request_id=p.change_request_id "
                "AND co.change_request_observation_id=o.change_request_observation_id "
                "JOIN code_acquisitions ca ON ca.code_observation_id=co.code_observation_id "
                "AND ca.acquisition_root_id=a.acquisition_root_id "
                "WHERE a.repository_uuidv4=? AND a.published=1 "
                "AND (? IS NULL OR p.provider_change_request_number=?) "
                "AND (?='recorded' OR EXISTS(SELECT 1 FROM current_change_request_observations selected "
                "WHERE selected.change_request_observation_id=o.change_request_observation_id)) "
                "ORDER BY a.acquisition_root_id,ca.role",
                (repo["repository_uuidv4"], pr, pr, scope),
            )
            selected = [
                {
                    "id": r["acquisition_root_id"],
                    "oid": r["oid"],
                    "object_format": r["object_format"],
                    "name": f"pr/{r['pr_number']}/{r['origin_role']}",
                    "snapshot": None,
                    "role": r["origin_role"],
                    "git_acquisition_id": r["git_acquisition_id"],
                }
                for r in rows
                if not kinds
                or ("pr-head" if r["origin_role"] == "head" else "pr-related") in kinds
            ]
            selected = self.acquired_root_contexts(repo, selected, scope)
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
                "SELECT DISTINCT a.*,o.root_origin_id origin_id,o.snapshot_id,o.raw_ref_name,p.provider_change_request_number pr_number,f.kind ref_kind,ca.role origin_role FROM acquisition_roots a LEFT JOIN root_origins o ON o.acquisition_root_id=a.acquisition_root_id LEFT JOIN change_requests p ON p.change_request_id=o.change_request_id LEFT JOIN ref_observations f ON f.snapshot_id=o.snapshot_id AND f.raw_ref_name=o.raw_ref_name LEFT JOIN eligible_code_observations co ON co.change_request_id=o.change_request_id AND co.change_request_observation_id=o.change_request_observation_id LEFT JOIN code_acquisitions ca ON ca.code_observation_id=co.code_observation_id AND ca.acquisition_root_id=a.acquisition_root_id WHERE a.repository_uuidv4=? AND a.published=1 AND (o.origin_kind IS NOT 'pr_role' OR co.code_observation_id IS NOT NULL) ORDER BY a.acquisition_root_id,o.root_origin_id,ca.role",
                (repo["repository_uuidv4"],),
            )
            selected = [
                {
                    "id": r["origin_id"] or r["acquisition_root_id"],
                    "oid": r["oid"],
                    "object_format": r["object_format"],
                    "name": r["raw_ref_name"].decode("utf8", "backslashreplace")
                    if r["raw_ref_name"]
                    else f"pr/{r['pr_number']}/{r['origin_role'] or r['role']}",
                    "snapshot": r["snapshot_id"],
                    "role": r["origin_role"] or r["ref_kind"] or r["role"],
                    "git_acquisition_id": r["git_acquisition_id"],
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
            return self.acquired_root_contexts(repo, selected, scope)
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
                "repository_uuidv4": repo["repository_uuidv4"],
                "parsed_result_uuidv4": snapshot["parsed_result_uuidv4"],
                "historical": bool(o.get("snapshot")),
            }
            for r in selected
        ]

    def acquired_root_contexts(self, repo, roots, scope):
        selected = []
        for root in roots:
            result = self.s.one(
                "SELECT repository_uuidv4,parsed_result_uuidv4 FROM selected_git_acquisition_results WHERE repository_uuidv4=? AND git_acquisition_id=?",
                (repo["repository_uuidv4"], root["git_acquisition_id"]),
            )
            if result:
                selected.append({**root, **dict(result), "historical": True})
            else:
                self.coverage.add(
                    "git",
                    "acquisition_selection_unresolved",
                    repository_uuidv4=repo["repository_uuidv4"],
                    git_acquisition_id=root["git_acquisition_id"],
                )
        return selected

    def peel(self, fmt, oid, context):
        row = self.s.one(
            "SELECT * FROM git_objects WHERE object_format=? AND oid=?", (fmt, oid)
        )
        seen = set()
        while row and row["type"] == "tag":
            if row["git_object_id"] in seen:
                raise CatalogError("INTEGRITY_ERROR", "Tag cycle")
            seen.add(row["git_object_id"])
            row = self.s.one(
                f"SELECT g.* FROM {self.git_relation('tag_objects', context)} t JOIN git_objects g ON g.git_object_id=t.target_git_object_id WHERE t.repository_uuidv4=? AND t.parsed_result_uuidv4=? AND t.git_object_id=?",
                (*self.git_scope(context), row["git_object_id"]),
            )
        if row is None:
            self.coverage.add(
                "git", "root_object_missing", object_format=fmt, oid=oid.hex()
            )
        return row

    def commit_set(self, roots, first_parent=False):
        found = set()
        for root in roots:
            obj = self.peel(root["object_format"], root["oid"], root)
            if not obj or obj["type"] != "commit":
                continue
            if not self.s.one(
                f"SELECT 1 FROM {self.git_relation('commits', root)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=? AND git_object_id=?",
                (*self.git_scope(root), obj["git_object_id"]),
            ):
                self.coverage.add(
                    "git",
                    "commit_structure_missing",
                    git_object_id=obj["git_object_id"],
                )
                continue
            where = " AND p.parent_ordinal=0" if first_parent else ""
            found.update(
                (*self.git_scope(root), row[0])
                for row in self.s.all(
                    f"WITH RECURSIVE reach(git_object_id) AS (VALUES (?) UNION SELECT p.parent_git_object_id FROM {self.git_relation('commit_parents', root)} p JOIN reach r ON p.commit_git_object_id=r.git_object_id WHERE p.repository_uuidv4=? AND p.parsed_result_uuidv4=?{where}) SELECT git_object_id FROM reach",
                    (obj["git_object_id"], *self.git_scope(root)),
                )
            )
        return found

    def git_commits(self, roots):
        contexts = {}
        for root in roots:
            contexts[self.git_scope(root)] = root
        streams = []
        for context in contexts.values():
            streams.append(
                self.s.execute(
                    f"SELECT g.*,c.* FROM {self.git_relation('commits', context)} c JOIN git_objects g ON g.git_object_id=c.git_object_id WHERE c.repository_uuidv4=? AND c.parsed_result_uuidv4=? ORDER BY g.oid,c.parsed_result_uuidv4",
                    self.git_scope(context),
                )
            )
        return heapq.merge(
            *streams, key=lambda row: (row["oid"], row["parsed_result_uuidv4"])
        )

    def tree_entries(self, tree, context, prefix=b""):
        # Raw byte frames avoid text coercion and terminate incomplete/cyclic
        # imported trees while preserving the usable recorded entries.
        frames = [(tree, prefix, "", frozenset())]
        while frames:
            self.token.check()
            if time.monotonic() > self.deadline:
                raise TimeoutError()
            ident, raw_prefix, display_prefix, ancestors = frames.pop()
            if ident in ancestors:
                self.coverage.add("git", "tree_cycle", git_object_id=ident)
                continue
            rows = self.s.all(
                f"SELECT * FROM {self.git_relation('tree_entries', context)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=? AND tree_git_object_id=? ORDER BY raw_name",
                (*self.git_scope(context), ident),
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
                display_path = display_prefix + row["decoded_name"]
                if row["mode"] == 16384:
                    subtrees.append(
                        (
                            row["child_git_object_id"],
                            raw_path + b"/",
                            display_path + "/",
                            ancestors | {ident},
                        )
                    )
                    continue
                content = self.git_content(context, row["child_git_object_id"])
                yield {
                    "raw_path": raw_path,
                    "path_display": "".join(
                        character
                        if character.isprintable()
                        else f"\\x{ord(character):02x}"
                        for character in display_path
                    ),
                    "parsed_result_uuidv4": context["parsed_result_uuidv4"],
                    "git_text_fact_uuidv4": content["git_fact_uuidv4"]
                    if content
                    else None,
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
                obj = self.peel(root["object_format"], root["oid"], root)
                if not obj or obj["type"] != "commit":
                    continue
                tree = self.s.one(
                    f"SELECT tree_git_object_id FROM {self.git_relation('commits', root)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=? AND git_object_id=?",
                    (*self.git_scope(root), obj["git_object_id"]),
                )
                if tree is None:
                    self.coverage.add(
                        "git",
                        "commit_structure_missing",
                        git_object_id=obj["git_object_id"],
                    )
                    continue
                for entry in self.tree_entries(tree[0], root):
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
            contexts = {self.git_scope(root): root for root in roots}
            for obj in self.git_commits(roots):
                scope_key = (obj["repository_uuidv4"], obj["parsed_result_uuidv4"])
                if (*scope_key, obj["git_object_id"]) not in commits:
                    continue
                for entry in self.tree_entries(
                    obj["tree_git_object_id"], contexts[scope_key]
                ):
                    yield (
                        (
                            obj["oid"].hex(),
                            obj["parsed_result_uuidv4"],
                            entry["raw_path"].hex(),
                        ),
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
                selected = s.one(
                    "SELECT snapshot_id FROM current_snapshots WHERE repository_uuidv4=?",
                    (r["repository_uuidv4"],),
                )
                item = {
                    **dict(r),
                    "metadata": json.loads(r["metadata"]),
                    "current_snapshot_id": selected[0] if selected else None,
                    "inventory_observations": [
                        {
                            **dict(observation),
                            "metadata": json.loads(observation["metadata_json"]),
                        }
                        for observation in s.execute(
                            "SELECT * FROM current_repository_inventory_observations "
                            "WHERE repository_uuidv4=? ORDER BY source_registration_uuidv4,repository_inventory_observation_uuidv4",
                            (r["repository_uuidv4"],),
                        )
                    ],
                }
                for observation in item["inventory_observations"]:
                    observation.pop("metadata_json")
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
                    "SELECT s.* FROM snapshots s JOIN usable_parsed_results r USING(parsed_result_uuidv4) WHERE s.snapshot_id=? AND s.published=1",
                    (o.get("snapshot"),),
                )
                if not row:
                    raise CatalogError("NOT_FOUND", "Snapshot not found")
                rows = [row]
            else:
                repo = self.single_repo(o)
                rows = s.all(
                    "SELECT s.* FROM snapshots s JOIN usable_parsed_results r USING(parsed_result_uuidv4) WHERE s.repository_uuidv4=? AND s.published=1 ORDER BY s.generation",
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
                left_roots = self.roots(repo, {**o, "refs": [o["left"]]})
                right_roots = self.roots(repo, {**o, "refs": [o["right"]]})
                roots = left_roots + right_roots
                left = self.commit_set(left_roots)
                right = self.commit_set(right_roots)
                ids = {
                    "left-only": left - right,
                    "right-only": right - left,
                    "common": left & right,
                    "symmetric": left ^ right,
                }[o["set"]]
            else:
                if o.get("commit"):
                    oid = GitOid.parse(o["commit"])
                    context = self.git_context(repo, o)
                    root_object = s.one(
                        "SELECT git_object_id,type FROM git_objects WHERE object_format=? AND oid=?",
                        (oid.algorithm, oid.value),
                    )
                    if root_object:
                        context = object_context(
                            s,
                            context,
                            root_object["git_object_id"],
                            root_object["type"],
                        )
                    if context.get("selection_unresolved"):
                        self.coverage.add(
                            "git",
                            "git_interpretation_selection_unresolved",
                            repository_uuidv4=repo["repository_uuidv4"],
                            git_object_id=root_object["git_object_id"],
                        )
                        return
                    obj = self.peel(oid.algorithm, oid.value, context)
                    if not obj or not self.public_object(repo, obj["git_object_id"]):
                        raise CatalogError(
                            "NOT_FOUND", "Commit not publicly acquired for this repo"
                        )
                    roots = [
                        {"object_format": oid.algorithm, "oid": oid.value, **context}
                    ]
                else:
                    if not o.get("ref"):
                        raise CatalogError(
                            "INVALID_ARGUMENT", "--ref or --commit required"
                        )
                    roots = self.roots(repo, {**o, "refs": [o["ref"]]})
                ids = self.commit_set(roots, o.get("first_parent", False))
                if not roots:
                    return
                if command == "commits show":
                    obj = self.peel(
                        roots[0]["object_format"], roots[0]["oid"], roots[0]
                    )
                    if not obj or obj["type"] != "commit":
                        raise CatalogError(
                            "NOT_FOUND", "Stored commit structure missing"
                        )
                    ids = {(*self.git_scope(roots[0]), obj["git_object_id"])}
                if command in ("tree list", "file show"):
                    obj = self.peel(
                        roots[0]["object_format"], roots[0]["oid"], roots[0]
                    )
                    if not obj or obj["type"] not in ("tree", "commit"):
                        raise CatalogError(
                            "INVALID_ARGUMENT",
                            "Tree query requires a commit or tree root",
                        )
                    tree = obj["git_object_id"]
                    if obj["type"] == "commit":
                        structure = s.one(
                            f"SELECT tree_git_object_id FROM {self.git_relation('commits', roots[0])} WHERE repository_uuidv4=? AND parsed_result_uuidv4=? AND git_object_id=?",
                            (*self.git_scope(roots[0]), obj["git_object_id"]),
                        )
                        if structure is None:
                            return
                        tree = structure[0]
                    wanted = None
                    if command == "file show":
                        from repo_catalog.application.target_queries import (
                            TargetQueryService,
                        )

                        wanted = TargetQueryService._path(o)
                    found = False
                    for entry in self.tree_entries(tree, roots[0]):
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
                                    "SELECT t.*,c.byte_length FROM eligible_git_text_facts t JOIN contents c USING(content_id) WHERE git_fact_uuidv4=?",
                                    (entry["git_text_fact_uuidv4"],),
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
                        yield [raw.hex()], {**path_fields(raw), **entry}
                    if wanted is not None and not found:
                        raise CatalogError(
                            "NOT_FOUND", "Raw path not present in stored tree"
                        )
                    return
            contexts = {self.git_scope(root): root for root in roots}
            for r in self.git_commits(roots):
                scope_key = (r["repository_uuidv4"], r["parsed_result_uuidv4"])
                if (*scope_key, r["git_object_id"]) not in ids:
                    continue
                context = contexts[scope_key]
                parents = s.all(
                    f"SELECT g.object_format,g.oid FROM {self.git_relation('commit_parents', context)} p JOIN git_objects g ON g.git_object_id=p.parent_git_object_id WHERE p.repository_uuidv4=? AND p.parsed_result_uuidv4=? AND p.commit_git_object_id=? ORDER BY parent_ordinal",
                    (*scope_key, r["git_object_id"]),
                )
                tree = s.one(
                    "SELECT * FROM git_objects WHERE git_object_id=?",
                    (r["tree_git_object_id"],),
                )
                yield (
                    [r["oid"].hex(), r["parsed_result_uuidv4"]],
                    {
                        **oid_fields(r),
                        "repository_uuidv4": repo["repository_uuidv4"],
                        "parents": [
                            f"{p['object_format']}:{p['oid'].hex()}" for p in parents
                        ],
                        "tree": f"{tree['object_format']}:{tree['oid'].hex()}",
                        "message": r["message_text"],
                        "parsed_result_uuidv4": r["parsed_result_uuidv4"],
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
                    roots = self.roots(repo, o)
                    ids = self.commit_set(roots)
                    needle = literal.encode("utf8")
                    for r in self.git_commits(roots):
                        message = r["message_text"]
                        if (
                            (
                                r["repository_uuidv4"],
                                r["parsed_result_uuidv4"],
                                r["git_object_id"],
                            )
                            in ids
                            and literal in message
                            and self.literal_match(
                                "commits", r["git_fact_uuidv4"], message, literal
                            )
                        ):
                            offset = r["raw_message"].find(needle)
                            match_bytes = len(needle)
                            if offset < 0:
                                encoding = s.one(
                                    "SELECT coalesce(json_extract(p.definition_json,'$.settings.git_metadata_encoding'),'utf-8') FROM parsed_results r JOIN parser_profiles p USING(parser_profile_uuidv4) WHERE r.parsed_result_uuidv4=?",
                                    (r["parsed_result_uuidv4"],),
                                )[0]
                                offset = len(
                                    message[: message.index(literal)].encode(encoding)
                                )
                                match_bytes = len(literal.encode(encoding))
                            yield (
                                [
                                    repo["repository_uuidv4"],
                                    r["oid"].hex(),
                                    r["parsed_result_uuidv4"],
                                ],
                                {
                                    **oid_fields(r),
                                    "repository_uuidv4": repo["repository_uuidv4"],
                                    "message": message,
                                    "parsed_result_uuidv4": r["parsed_result_uuidv4"],
                                    "message_b64": base64.b64encode(
                                        r["raw_message"]
                                    ).decode(),
                                    "byte_start": offset,
                                    "byte_end": offset + match_bytes,
                                    "line": message[: message.index(literal)].count(
                                        "\n"
                                    )
                                    + 1,
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
                            "SELECT * FROM eligible_git_text_facts WHERE git_fact_uuidv4=?",
                            (entry["git_text_fact_uuidv4"],),
                        )
                        if c is None or c["raw_text"] is None:
                            continue
                        if not self.literal_match(
                            "code", c["git_fact_uuidv4"], c["raw_text"], literal
                        ):
                            continue
                        offset = c["raw_text"].index(literal)
                        encoding = s.one(
                            "SELECT coalesce(json_extract(p.definition_json,'$.settings.git_text_encoding'),'utf-8') FROM parsed_results r JOIN parser_profiles p USING(parser_profile_uuidv4) WHERE r.parsed_result_uuidv4=?",
                            (c["parsed_result_uuidv4"],),
                        )[0]
                        entry.update(
                            byte_start=len(c["raw_text"][:offset].encode(encoding)),
                            byte_end=len(
                                c["raw_text"][: offset + len(literal)].encode(encoding)
                            ),
                            line=c["raw_text"][:offset].count("\n") + 1,
                            snippet=c["raw_text"][
                                max(0, offset - 40) : offset + len(literal) + 80
                            ],
                        )
                    yield (
                        [repo["repository_uuidv4"], *sortkey],
                        {**path_fields(raw), **entry},
                    )
        elif command == "content show":
            content = s.one(
                "SELECT * FROM contents WHERE content_id=?", (o["content_id"],)
            )
            if not content:
                raise CatalogError("NOT_FOUND", "Content not found")
            facts = s.all(
                "SELECT * FROM current_git_text_facts WHERE content_id=?",
                (o["content_id"],),
            )
            if not any(fact["raw_text"] is not None for fact in facts):
                states = {fact["text_state"] for fact in facts}
                raise CatalogError(
                    "RAW_CONTENT_UNAVAILABLE",
                    "Raw bytes are not durably saved",
                    {
                        "content_id": content["content_id"],
                        "reason": next(iter(states))
                        if len(states) == 1
                        else "current_selection_unresolved",
                    },
                )
            offset = o.get("offset", 0)
            length = o.get("length", 65536)
            if offset < 0 or not 0 <= length <= 1048576:
                raise CatalogError(
                    "INVALID_ARGUMENT",
                    "Raw range must be nonnegative and at most 1 MiB",
                )
            payload = s.one(
                "SELECT DISTINCT bytes.body FROM current_git_text_facts fact JOIN git_object_payloads payload USING(git_object_id) JOIN stored_bytes bytes ON bytes.sha256=payload.payload_sha256 WHERE fact.content_id=? AND fact.raw_text IS NOT NULL AND NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=payload.payload_sha256)",
                (content["content_id"],),
            )
            if payload is None:
                raise CatalogError(
                    "RAW_CONTENT_UNAVAILABLE", "Raw bytes are not durably saved"
                )
            raw = payload[0]
            part = raw[offset : offset + length]
            yield (
                [content["content_id"]],
                {
                    "content_id": content["content_id"],
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
                            (content["content_id"],),
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
        elif command.startswith("issue ") or command == "search issue":
            from repo_catalog.application.issue_queries import issue_query

            yield from issue_query(self, command, o)
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
