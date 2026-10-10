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
                        or token.get("seq") != revision["local_revision"]
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
                        "seq": revision["local_revision"],
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

    def check(self):
        self.token.check()
        if time.monotonic() > self.deadline:
            raise TimeoutError()

    def repos(self, options):
        selectors = tuple(options.get("repos") or ())
        if options.get("repo"):
            selectors = (options["repo"],)
        return select_repositories(self.s, selectors, options.get("source"))

    def single_repo(self, options):
        if not options.get("repo") and len(options.get("repos") or ()) != 1:
            raise CatalogError("INVALID_ARGUMENT", "A single repository is required")
        rows = self.repos(options)
        if len(rows) != 1:
            raise CatalogError("INVALID_ARGUMENT", "Select one repository")
        return rows[0]

    def prepare_coverage(self, command, options):
        if command.startswith("pr ") or command == "search pr":
            from repo_catalog.application.pr_queries import prepare_pr_coverage

            prepare_pr_coverage(self, command, options)
        elif command.startswith("issue ") or command == "search issue":
            from repo_catalog.application.issue_queries import prepare_issue_coverage

            prepare_issue_coverage(self, command, options)
        if (
            not options.get("repo")
            and not options.get("repos")
            and command
            in {
                "repos list",
                "search pr",
                "search issue",
                "issue list",
                "search code",
                "search path",
                "search commits",
                "search hash",
            }
        ):
            for source in self.s.execute("SELECT source_id FROM sources"):
                if options.get("source") and source[0] != options["source"]:
                    continue
                rows = self.s.all(
                    "SELECT a.* FROM source_inventory_assessments a WHERE source_id=? AND observed_at_us=(SELECT max(b.observed_at_us) FROM source_inventory_assessments b WHERE b.source_id=a.source_id AND b.scope_key=a.scope_key)",
                    (source[0],),
                )
                if not rows or any(r["state"] != "complete" for r in rows):
                    self.coverage.add(
                        "inventory", "inventory_incomplete", source_id=source[0]
                    )

    def snapshot(self, repo, options):
        if options.get("snapshot"):
            row = self.s.one(
                "SELECT * FROM snapshots WHERE repository_uuidv4=? AND snapshot_id=?",
                (repo["repository_uuidv4"], options["snapshot"]),
            )
            if not row:
                raise CatalogError("NOT_FOUND", "Snapshot not found")
        else:
            rows = self.s.all(
                "SELECT * FROM current_snapshots WHERE repository_uuidv4=?",
                (repo["repository_uuidv4"],),
            )
            row = rows[0] if len(rows) == 1 else None
            if row is None:
                self.coverage.add(
                    "git",
                    "current_snapshot_unresolved" if rows else "not_collected",
                    repository_uuidv4=repo["repository_uuidv4"],
                )
        if row and not row["complete"]:
            self.coverage.add(
                "git", "snapshot_incomplete", snapshot_id=row["snapshot_id"]
            )
        return row

    def git_context(self, repo, options):
        context = {
            "repository_uuidv4": repo["repository_uuidv4"],
            "decoder_key": options.get("decoder_key"),
        }
        if options.get("snapshot"):
            snapshot = self.snapshot(repo, options)
            context.update(
                snapshot_id=snapshot["snapshot_id"],
                git_acquisition_id=snapshot["git_acquisition_id"],
            )
        if options.get("git_acquisition_id"):
            acquisition = self.s.one(
                "SELECT * FROM git_acquisitions WHERE repository_uuidv4=? AND git_acquisition_id=?",
                (repo["repository_uuidv4"], options["git_acquisition_id"]),
            )
            if not acquisition:
                raise CatalogError("NOT_FOUND", "Git acquisition not found")
            context["git_acquisition_id"] = acquisition["git_acquisition_id"]
        return context

    def public_object(self, repo, object_id, context=None):
        context = context or {}
        return bool(
            self.s.one(
                "SELECT 1 FROM repository_object_sources s JOIN available_git_objects g USING(git_object_id) WHERE s.repository_uuidv4=? AND s.git_object_id=? AND (? IS NULL OR s.git_acquisition_id=?)",
                (
                    repo["repository_uuidv4"],
                    object_id,
                    context.get("git_acquisition_id"),
                    context.get("git_acquisition_id"),
                ),
            )
        )

    def roots(self, repo, options):
        scope = options.get("scope") or "current"
        if scope not in {"current", "history", "recorded"}:
            raise CatalogError("INVALID_ARGUMENT", "Invalid Git scope")
        refs, kinds, pr = (
            options.get("refs") or [],
            options.get("ref_kinds") or [],
            options.get("pr"),
        )
        if sum(bool(v) for v in (refs, kinds, pr)) > 1:
            raise CatalogError(
                "INVALID_ARGUMENT", "Root selectors are mutually exclusive"
            )
        if any(not ref.startswith("refs/") for ref in refs):
            raise CatalogError("INVALID_ARGUMENT", "Full ref names are required")
        if scope == "current" and (
            pr
            or any(k != "head" for k in kinds)
            or any(not r.startswith("refs/heads/") for r in refs)
        ):
            raise CatalogError("INVALID_ARGUMENT", "Current scope permits branch heads")
        context = self.git_context(repo, options)
        if scope == "recorded" or pr or any(k.startswith("pr-") for k in kinds):
            rows = self.s.all(
                "SELECT a.*,o.snapshot_id,o.raw_ref_name,o.change_request_id,o.code_assessment_id,p.provider_change_request_number FROM acquisition_roots a LEFT JOIN root_origins o USING(acquisition_root_id) LEFT JOIN change_requests p ON p.change_request_id=o.change_request_id WHERE a.repository_uuidv4=? AND (? IS NULL OR a.git_acquisition_id=?) ORDER BY a.acquisition_root_id,o.root_origin_id",
                (
                    repo["repository_uuidv4"],
                    context.get("git_acquisition_id"),
                    context.get("git_acquisition_id"),
                ),
            )
            result = []
            for row in rows:
                if pr and row["provider_change_request_number"] != pr:
                    continue
                raw = row["raw_ref_name"]
                if refs and raw not in [ref.encode() for ref in refs]:
                    continue
                role = row["role"]
                kind = (
                    "pr-head"
                    if row["change_request_id"] and role == "head"
                    else "pr-related"
                    if row["change_request_id"]
                    else "head"
                    if raw and raw.startswith(b"refs/heads/")
                    else "tag"
                    if raw and raw.startswith(b"refs/tags/")
                    else "other"
                )
                if kinds and kind not in kinds:
                    continue
                if scope != "recorded" and row["code_assessment_id"]:
                    current = self.s.one(
                        "SELECT a.code_assessment_id FROM code_assessments a JOIN eligible_change_request_state s USING(change_request_id) WHERE a.code_assessment_id=? AND a.object_format IS s.object_format AND a.head_oid IS s.head_oid AND a.base_oid IS s.base_oid",
                        (row["code_assessment_id"],),
                    )
                    if current is None:
                        continue
                if not row["complete"]:
                    self.coverage.add(
                        "git",
                        "root_incomplete",
                        acquisition_root_id=row["acquisition_root_id"],
                    )
                result.append(
                    {
                        **context,
                        "git_acquisition_id": row["git_acquisition_id"],
                        "snapshot_id": row["snapshot_id"],
                        "id": row["acquisition_root_id"],
                        "object_format": row["object_format"],
                        "oid": row["oid"],
                        "role": role,
                        "name": raw.decode("utf8", "backslashreplace")
                        if raw
                        else f"pr/{row['provider_change_request_number']}/{role}",
                    }
                )
            return result
        snapshots = (
            [self.snapshot(repo, options)]
            if scope == "current" or options.get("snapshot")
            else self.s.all(
                "SELECT * FROM snapshots WHERE repository_uuidv4=? ORDER BY generation,snapshot_id",
                (repo["repository_uuidv4"],),
            )
        )
        result = []
        for snapshot in snapshots:
            if not snapshot:
                continue
            for row in self.s.execute(
                "SELECT * FROM ref_observations WHERE snapshot_id=? ORDER BY raw_ref_name",
                (snapshot["snapshot_id"],),
            ):
                if (
                    scope == "current"
                    and row["kind"] != "head"
                    or refs
                    and row["raw_ref_name"] not in [ref.encode() for ref in refs]
                    or kinds
                    and row["kind"] not in kinds
                ):
                    continue
                result.append(
                    {
                        **context,
                        "git_acquisition_id": snapshot["git_acquisition_id"],
                        "snapshot_id": snapshot["snapshot_id"],
                        "id": row["raw_ref_name"].hex(),
                        "object_format": row["object_format"],
                        "oid": row["target_oid"],
                        "role": row["kind"],
                        "name": row["raw_ref_name"].decode("utf8", "backslashreplace"),
                    }
                )
        return result

    def peel(self, fmt, oid, context):
        seen = set()
        while (fmt, oid) not in seen:
            seen.add((fmt, oid))
            obj = self.s.one(
                "SELECT * FROM available_git_objects WHERE object_format=? AND oid=?",
                (fmt, oid),
            )
            if obj is None or not self.public_object(
                {"repository_uuidv4": context["repository_uuidv4"]},
                obj["git_object_id"],
                context,
            ):
                self.coverage.add(
                    "git", "object_unavailable", oid=fmt + ":" + oid.hex()
                )
                return None
            if obj["type"] != "tag":
                return obj
            target = self.s.one(
                "SELECT * FROM tag_objects WHERE git_object_id=?",
                (obj["git_object_id"],),
            )
            if target is None:
                return None
            fmt, oid = target["target_format"], target["target_oid"]
        self.coverage.add("git", "tag_cycle")
        return None

    def closure(self, roots):
        result, pending = set(), []
        for root in roots:
            obj = self.peel(root["object_format"], root["oid"], root)
            if obj:
                pending.append((obj["git_object_id"], root))
        while pending:
            object_id, context = pending.pop()
            if object_id in result:
                continue
            result.add(object_id)
            obj = self.s.one(
                "SELECT * FROM available_git_objects WHERE git_object_id=?",
                (object_id,),
            )
            if obj is None:
                continue
            refs = []
            if obj["type"] == "commit":
                commit = self.s.one(
                    "SELECT * FROM commits WHERE git_object_id=?", (object_id,)
                )
                refs.append((commit["tree_format"], commit["tree_oid"]))
                refs.extend(
                    (p["parent_format"], p["parent_oid"])
                    for p in self.s.execute(
                        "SELECT * FROM commit_parents WHERE commit_git_object_id=?",
                        (object_id,),
                    )
                )
            elif obj["type"] == "tree":
                refs.extend(
                    (e["child_format"], e["child_oid"])
                    for e in self.s.execute(
                        "SELECT * FROM tree_entries WHERE tree_git_object_id=? AND mode<>57344",
                        (object_id,),
                    )
                )
            elif obj["type"] == "tag":
                tag = self.s.one(
                    "SELECT * FROM tag_objects WHERE git_object_id=?", (object_id,)
                )
                refs.append((tag["target_format"], tag["target_oid"]))
            for fmt, oid in refs:
                target = self.s.one(
                    "SELECT * FROM available_git_objects WHERE object_format=? AND oid=?",
                    (fmt, oid),
                )
                if target and self.public_object(
                    {"repository_uuidv4": context["repository_uuidv4"]},
                    target["git_object_id"],
                    context,
                ):
                    pending.append((target["git_object_id"], context))
                else:
                    self.coverage.add(
                        "git", "descendant_unavailable", oid=fmt + ":" + oid.hex()
                    )
        return result

    def commit_set(self, roots, first_parent=False):
        ids, pending = set(), []
        for root in roots:
            obj = self.peel(root["object_format"], root["oid"], root)
            if obj and obj["type"] == "commit":
                pending.append((obj["git_object_id"], root))
        while pending:
            object_id, context = pending.pop()
            if object_id in ids:
                continue
            ids.add(object_id)
            for parent in self.s.execute(
                "SELECT * FROM commit_parents WHERE commit_git_object_id=?"
                + (" AND parent_ordinal=0" if first_parent else "")
                + " ORDER BY parent_ordinal",
                (object_id,),
            ):
                obj = self.s.one(
                    "SELECT * FROM available_git_objects WHERE object_format=? AND oid=?",
                    (parent["parent_format"], parent["parent_oid"]),
                )
                if obj and self.public_object(
                    {"repository_uuidv4": context["repository_uuidv4"]},
                    obj["git_object_id"],
                    context,
                ):
                    pending.append((obj["git_object_id"], context))
                else:
                    self.coverage.add(
                        "git",
                        "parent_unavailable",
                        oid=parent["parent_format"] + ":" + parent["parent_oid"].hex(),
                    )
        return ids

    def decoded(self, object_id, kind, context):
        from repo_catalog.application.git_query_context import decoded_fact

        result = decoded_fact(
            self.s, object_id, kind, decoder_key=context.get("decoder_key")
        )
        if (
            result.get("decoder_missing")
            or context.get("decoder_key") is not None
            and result["fact"] is None
            and not result["decoder_conflict"]
        ):
            self.coverage.add(
                "git",
                "decoder_unavailable",
                git_object_id=object_id,
                decoder_key=context.get("decoder_key"),
            )
        if result["decoder_conflict"]:
            self.coverage.add(
                "git",
                "decoder_conflict",
                git_object_id=object_id,
                candidates=result["candidates"],
            )
        return result

    def tree_entries(
        self, tree, context, prefix=b"", _seen=None, _display="", _names=()
    ):
        seen = set() if _seen is None else _seen
        if tree in seen:
            self.coverage.add("git", "tree_cycle", git_object_id=tree)
            return
        seen = seen | {tree}
        if not self.s.one(
            "SELECT 1 FROM available_git_objects WHERE git_object_id=? AND type='tree'",
            (tree,),
        ):
            self.coverage.add("git", "tree_structure_unavailable", git_object_id=tree)
            return
        from repo_catalog.application.git_query_context import decoded_names

        tree_names = decoded_names(self.s, tree, decoder_key=context.get("decoder_key"))
        for row in self.s.execute(
            "SELECT * FROM tree_entries WHERE tree_git_object_id=? ORDER BY raw_name",
            (tree,),
        ):
            self.check()
            raw = prefix + row["raw_name"]
            name = tree_names.get(
                row["raw_name"],
                {"decoded_name": None, "decoder_conflict": False, "candidates": []},
            )
            name_evidence = [
                {
                    **candidate,
                    "raw_name": base64.b64encode(candidate["raw_name"]).decode(),
                }
                for candidate in name["candidates"]
            ]
            names = (*_names, *name_evidence)
            display = (
                (_display + name["decoded_name"])
                if _display is not None and name["decoded_name"] is not None
                else None
            )
            if name["decoder_conflict"]:
                self.coverage.add(
                    "git",
                    "decoder_conflict",
                    tree_git_object_id=tree,
                    raw_name_b64=base64.b64encode(row["raw_name"]).decode(),
                    candidates=name_evidence,
                )
            elif name["decoded_name"] is None:
                self.coverage.add(
                    "git",
                    "decoder_unavailable",
                    tree_git_object_id=tree,
                    decoder_key=context.get("decoder_key"),
                )
            child = (
                self.s.one(
                    "SELECT * FROM available_git_objects WHERE object_format=? AND oid=?",
                    (row["child_format"], row["child_oid"]),
                )
                if row["mode"] != 57344
                else None
            )
            if row["mode"] == 16384:
                if child:
                    yield from self.tree_entries(
                        child["git_object_id"],
                        context,
                        raw + b"/",
                        seen,
                        None if display is None else display + "/",
                        names,
                    )
                else:
                    self.coverage.add(
                        "git", "tree_child_unavailable", **path_fields(raw)
                    )
                continue
            body = (
                self.decoded(child["git_object_id"], "blob", context)
                if child
                else {"fact": None, "decoder_conflict": False, "candidates": []}
            )
            fact = body["fact"]
            if child and not self.public_object(
                {"repository_uuidv4": context["repository_uuidv4"]},
                child["git_object_id"],
                context,
            ):
                fact = None
            yield {
                "raw_path": raw,
                "path_display": None
                if display is None
                else "".join(
                    c if c.isprintable() else f"\\x{ord(c):02x}" for c in display
                ),
                "name_decoder_candidates": list(names),
                "mode": format(row["mode"], "o"),
                "object_format": row["child_format"],
                "oid": row["child_format"] + ":" + row["child_oid"].hex(),
                "git_object_id": child["git_object_id"] if child else None,
                "content_id": fact["content_id"] if fact else None,
                "git_text_fact_uuidv4": fact.get("git_fact_uuidv4") if fact else None,
                "text": fact["raw_text"] if fact else None,
                "text_state": fact["text_state"] if fact else "unknown",
                "decoder_candidates": body["candidates"],
            }

    def occurrences(self, repo, options):
        for root in self.roots(repo, options):
            obj = self.peel(root["object_format"], root["oid"], root)
            if not obj:
                continue
            tree = obj["git_object_id"]
            if obj["type"] == "commit":
                row = self.s.one("SELECT * FROM commits WHERE git_object_id=?", (tree,))
                target = self.s.one(
                    "SELECT git_object_id FROM available_git_objects WHERE object_format=? AND oid=?",
                    (row["tree_format"], row["tree_oid"]),
                )
                if not target:
                    self.coverage.add("git", "commit_tree_unavailable")
                    continue
                tree = target[0]
            elif obj["type"] != "tree":
                continue
            for entry in self.tree_entries(tree, root):
                yield (
                    [str(root["id"]), entry["raw_path"].hex()],
                    {
                        **entry,
                        "root": root["name"],
                        "snapshot_id": root.get("snapshot_id"),
                        "git_acquisition_id": root.get("git_acquisition_id"),
                        "repository_uuidv4": repo["repository_uuidv4"],
                    },
                )

    def literal(self, options):
        value = options.get("literal")
        if not isinstance(value, str) or not value or "\0" in value:
            raise CatalogError("INVALID_ARGUMENT", "A nonempty literal is required")
        return value

    def literal_match(self, kind, key, body, literal):
        # Search scope always comes from current/domain rows. An index may only
        # accelerate this predicate; obsolete shared text is never a scope.
        return literal in body

    def commit_fields(self, obj, context):
        commit = self.s.one(
            "SELECT * FROM commits WHERE git_object_id=?", (obj["git_object_id"],)
        )
        decoded = self.decoded(obj["git_object_id"], "commit", context)
        fact = decoded["fact"]
        return {
            **oid_fields(obj),
            "repository_uuidv4": context["repository_uuidv4"],
            "parents": [
                p["parent_format"] + ":" + p["parent_oid"].hex()
                for p in self.s.execute(
                    "SELECT * FROM commit_parents WHERE commit_git_object_id=? ORDER BY parent_ordinal",
                    (obj["git_object_id"],),
                )
            ],
            "tree": commit["tree_format"] + ":" + commit["tree_oid"].hex(),
            "message": fact["message_text"] if fact else None,
            "metadata": json.loads(fact["metadata"]) if fact else None,
            "decoder_candidates": decoded["candidates"],
            "decoder_conflict": decoded["decoder_conflict"],
            "message_b64": base64.b64encode(commit["raw_message"]).decode(),
            "raw_headers_b64": base64.b64encode(commit["raw_headers"]).decode(),
        }

    def iter_query(self, command, options):
        s = self.s
        if command.startswith("pr ") or command == "search pr":
            from repo_catalog.application.pr_queries import pr_query

            yield from pr_query(self, command, options)
        elif command.startswith("issue ") or command == "search issue":
            from repo_catalog.application.issue_queries import issue_query

            yield from issue_query(self, command, options)
        elif command in {"instances list", "instances show"}:
            rows = (
                [identity.instance(s, options["instance"])]
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
            repo = self.single_repo(options)
            for row in s.execute(
                "SELECT * FROM repository_endpoints WHERE repository_uuidv4=? ORDER BY repository_endpoint_id",
                (repo["repository_uuidv4"],),
            ):
                yield (
                    [row["repository_endpoint_id"]],
                    {**dict(row), "metadata": json.loads(row["metadata"])},
                )
        elif command in {"repos list", "repos show"}:
            for repo in self.repos(options):
                snapshot = self.snapshot(repo, options)
                fields = {
                    **dict(repo),
                    "metadata": json.loads(repo["metadata"]),
                    "current_snapshot_id": snapshot["snapshot_id"]
                    if snapshot
                    else None,
                }
                if command == "repos show":
                    fields["nested_collections"] = {}
                    for name, table in (
                        ("endpoints", "repository_endpoints"),
                        ("bindings", "repository_bindings"),
                        ("sources", "source_repositories"),
                    ):
                        rows = s.all(
                            f"SELECT * FROM {table} WHERE repository_uuidv4=? ORDER BY 1 LIMIT 100",
                            (repo["repository_uuidv4"],),
                        )
                        total = s.one(
                            f"SELECT count(*) FROM {table} WHERE repository_uuidv4=?",
                            (repo["repository_uuidv4"],),
                        )[0]
                        fields[name] = [dict(row) for row in rows]
                        fields["nested_collections"][name] = {
                            "returned": len(rows),
                            "total": total,
                            "has_more": total > len(rows),
                        }
                yield [repo["repository_uuidv4"]], fields
        elif command in {"snapshots list", "snapshots show"}:
            if command.endswith("show"):
                row = s.one(
                    "SELECT * FROM snapshots WHERE snapshot_id=?",
                    (options.get("snapshot"),),
                )
                if row is None:
                    raise CatalogError("NOT_FOUND", "Snapshot not found")
                rows = [row]
            else:
                repo = self.single_repo(options)
                rows = s.execute(
                    "SELECT * FROM snapshots WHERE repository_uuidv4=? ORDER BY generation,snapshot_id",
                    (repo["repository_uuidv4"],),
                )
            for row in rows:
                yield (
                    [row["repository_uuidv4"], row["generation"], row["snapshot_id"]],
                    {
                        **dict(row),
                        "run": dict(
                            s.one(
                                "SELECT * FROM git_acquisitions WHERE git_acquisition_id=?",
                                (row["git_acquisition_id"],),
                            )
                        ),
                        "coverage": current_coverages(
                            s.connection, row["repository_uuidv4"]
                        ),
                    },
                )
        elif command == "refs list":
            repo = self.single_repo(options)
            snapshot = self.snapshot(repo, options)
            if snapshot is None:
                return
            for row in s.execute(
                "SELECT * FROM ref_observations WHERE snapshot_id=? ORDER BY raw_ref_name",
                (snapshot["snapshot_id"],),
            ):
                if options.get("ref_kinds") and row["kind"] not in options["ref_kinds"]:
                    continue
                yield (
                    [row["raw_ref_name"].hex()],
                    {
                        "ref": row["raw_ref_name"].decode("utf8", "backslashreplace"),
                        "ref_b64": base64.b64encode(row["raw_ref_name"]).decode(),
                        "kind": row["kind"],
                        "oid": row["object_format"] + ":" + row["target_oid"].hex(),
                        "peeled_oid": row["object_format"]
                        + ":"
                        + row["peeled_oid"].hex()
                        if row["peeled_oid"]
                        else None,
                        "snapshot_id": snapshot["snapshot_id"],
                    },
                )
        elif command in {
            "tree list",
            "file show",
            "commits list",
            "commits show",
            "commits compare",
        }:
            repo = self.single_repo(options)
            if command == "commits compare":
                left_roots = self.roots(repo, {**options, "refs": [options["left"]]})
                right_roots = self.roots(repo, {**options, "refs": [options["right"]]})
                left, right = self.commit_set(left_roots), self.commit_set(right_roots)
                ids = {
                    "left-only": left - right,
                    "right-only": right - left,
                    "common": left & right,
                    "symmetric": left ^ right,
                }[options["set"]]
                roots = left_roots + right_roots
            else:
                if options.get("commit"):
                    oid = GitOid.parse(options["commit"])
                    context = self.git_context(repo, options)
                    roots = [
                        {
                            **context,
                            "object_format": oid.algorithm,
                            "oid": oid.value,
                            "name": options["commit"],
                            "id": options["commit"],
                        }
                    ]
                elif options.get("ref"):
                    roots = self.roots(repo, {**options, "refs": [options["ref"]]})
                else:
                    raise CatalogError(
                        "INVALID_ARGUMENT", "A ref or commit is required"
                    )
                ids = self.commit_set(roots, options.get("first_parent", False))
            if command in {"tree list", "file show"}:
                if not roots:
                    return
                obj = self.peel(roots[0]["object_format"], roots[0]["oid"], roots[0])
                if obj is None:
                    raise CatalogError("NOT_FOUND", "Git root unavailable")
                tree = obj["git_object_id"]
                if obj["type"] == "commit":
                    commit = s.one(
                        "SELECT * FROM commits WHERE git_object_id=?", (tree,)
                    )
                    target = s.one(
                        "SELECT git_object_id FROM available_git_objects WHERE object_format=? AND oid=?",
                        (commit["tree_format"], commit["tree_oid"]),
                    )
                    if target is None:
                        self.coverage.add("git", "commit_tree_unavailable")
                        return
                    tree = target[0]
                elif obj["type"] != "tree":
                    raise CatalogError(
                        "INVALID_ARGUMENT", "Tree queries require a commit or tree"
                    )
                from repo_catalog.application.target_queries import TargetQueryService

                wanted = (
                    TargetQueryService._path(options)
                    if command == "file show"
                    else None
                )
                found = False
                for entry in self.tree_entries(tree, roots[0]):
                    raw = entry.pop("raw_path")
                    if (
                        wanted is not None
                        and raw != wanted
                        or options.get("path_prefix")
                        and not raw.startswith(options["path_prefix"].encode())
                    ):
                        continue
                    found = True
                    if command == "tree list":
                        entry.pop("text")
                    elif entry["text"] is None and entry["mode"] != "160000":
                        self.coverage.add("code", "body_not_saved", **path_fields(raw))
                    yield [raw.hex()], {**path_fields(raw), **entry}
                if wanted is not None and not found:
                    raise CatalogError("NOT_FOUND", "Raw path absent from stored tree")
                return
            if command == "commits show":
                if not roots:
                    return
                obj = self.peel(roots[0]["object_format"], roots[0]["oid"], roots[0])
                if obj is None or obj["type"] != "commit":
                    raise CatalogError("NOT_FOUND", "Commit unavailable")
                ids = {obj["git_object_id"]}
            context = roots[0] if roots else self.git_context(repo, options)
            for obj in s.execute(
                "SELECT * FROM available_git_objects WHERE type='commit' ORDER BY oid"
            ):
                if obj["git_object_id"] in ids:
                    yield [obj["oid"].hex()], self.commit_fields(obj, context)
        elif command in {"search code", "search path", "search commits", "search hash"}:
            literal = (
                self.literal(options)
                if command in {"search code", "search commits"}
                else None
            )
            path = None
            if command == "search path":
                from repo_catalog.application.target_queries import TargetQueryService

                path = (
                    TargetQueryService._path(options)
                    if options.get("path") is not None
                    or options.get("path_b64") is not None
                    else None
                )
                if path is None and options.get("content_id") is None:
                    raise CatalogError(
                        "INVALID_ARGUMENT", "Path or content ID required"
                    )
            for repo in self.repos(options):
                roots = self.roots(repo, options)
                if command == "search commits":
                    ids = self.commit_set(roots)
                    context = roots[0] if roots else self.git_context(repo, options)
                    for obj in s.execute(
                        "SELECT * FROM available_git_objects WHERE type='commit' ORDER BY oid"
                    ):
                        if obj["git_object_id"] not in ids:
                            continue
                        fields = self.commit_fields(obj, context)
                        if (
                            fields["message"] is not None
                            and literal in fields["message"]
                        ):
                            fields.update(
                                self.decoder_offsets(
                                    obj["git_object_id"],
                                    "commit",
                                    context,
                                    fields["message"],
                                    literal,
                                )
                            )
                            yield [repo["repository_uuidv4"], obj["oid"].hex()], fields
                    continue
                if command == "search hash":
                    algorithm = options["algorithm"].removeprefix("raw-")
                    try:
                        digest = bytes.fromhex(options["digest"])
                        if (
                            len(digest)
                            != {"md5": 16, "sha1": 20, "sha256": 32}[algorithm]
                        ):
                            raise ValueError()
                    except (ValueError, KeyError):
                        raise CatalogError(
                            "INVALID_ARGUMENT", "Invalid full-length digest"
                        )
                    closure = self.closure(roots)
                    for row in s.execute(
                        "SELECT DISTINCT c.* FROM contents c JOIN content_digests d USING(content_id) WHERE d.algorithm=? AND d.digest=? ORDER BY content_id",
                        (algorithm, digest),
                    ):
                        if (
                            options.get("byte_length") is not None
                            and row["byte_length"] != options["byte_length"]
                        ):
                            continue
                        maps = s.all(
                            "SELECT g.* FROM blob_content_map b JOIN available_git_objects g USING(git_object_id) WHERE b.content_id=?",
                            (row["content_id"],),
                        )
                        if any(g["git_object_id"] in closure for g in maps):
                            yield (
                                [repo["repository_uuidv4"], row["content_id"]],
                                {
                                    **dict(row),
                                    "repository_uuidv4": repo["repository_uuidv4"],
                                    "representation": "raw-content-v1",
                                    "digests": self._digests(row["content_id"]),
                                    "verification": "verified",
                                },
                            )
                    continue
                for key, entry in self.occurrences(repo, options):
                    raw = entry.pop("raw_path")
                    if command == "search path":
                        if (
                            options.get("content_id") is not None
                            and entry["content_id"] != options["content_id"]
                        ):
                            continue
                        mode = options.get("path_mode", "exact")
                        if path is not None and not (
                            raw == path
                            if mode == "exact"
                            else raw.startswith(path)
                            if mode == "prefix"
                            else path in raw
                        ):
                            continue
                        entry.pop("text")
                    else:
                        text = entry.pop("text")
                        if text is None:
                            if entry["text_state"] in {"nul", "non_utf8", "oversize"}:
                                self.coverage.excluded_by_policy.append(
                                    {
                                        "content_id": entry["content_id"],
                                        "reason": entry["text_state"],
                                        **path_fields(raw),
                                    }
                                )
                            elif entry["mode"] != "160000":
                                self.coverage.add(
                                    "code", "body_not_saved", **path_fields(raw)
                                )
                            continue
                        if literal not in text:
                            continue
                        entry.update(
                            self.decoder_offsets(
                                entry["git_object_id"],
                                "blob",
                                {"decoder_key": options.get("decoder_key")},
                                text,
                                literal,
                            )
                        )
                    yield (
                        [repo["repository_uuidv4"], *key],
                        {**path_fields(raw), **entry},
                    )
        elif command == "content show":
            content = s.one(
                "SELECT * FROM contents WHERE content_id=?", (options["content_id"],)
            )
            if not content:
                raise CatalogError("NOT_FOUND", "Content not found")
            raw = s.one(
                "SELECT b.body FROM blob_content_map c JOIN available_git_objects g USING(git_object_id) JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 WHERE c.content_id=?",
                (content["content_id"],),
            )
            if raw is None:
                raise CatalogError(
                    "RAW_CONTENT_UNAVAILABLE", "Verified raw domain bytes unavailable"
                )
            offset, length = options.get("offset", 0), options.get("length", 65536)
            if offset < 0 or not 0 <= length <= 1048576:
                raise CatalogError("INVALID_ARGUMENT", "Invalid byte range")
            part = raw[0][offset : offset + length]
            yield (
                [content["content_id"]],
                {
                    "content_id": content["content_id"],
                    "offset": offset,
                    "requested_length": length,
                    "returned_length": len(part),
                    "byte_length": len(raw[0]),
                    "data_b64": base64.b64encode(part).decode(),
                    "has_more": offset + len(part) < len(raw[0]),
                    "digests": self._digests(content["content_id"]),
                },
            )
        elif command in {"coverage", "status"}:
            for repo in self.repos(options):
                snapshot = self.snapshot(repo, options)
                yield (
                    [repo["repository_uuidv4"]],
                    {
                        "repository_uuidv4": repo["repository_uuidv4"],
                        "snapshot_id": snapshot["snapshot_id"] if snapshot else None,
                        "components": current_coverages(
                            s.connection, repo["repository_uuidv4"], options.get("kind")
                        ),
                    },
                )
        elif command in {"jobs list", "jobs show"}:
            rows = s.all(
                "SELECT j.*,a.state,a.attempt,a.not_before_us,a.checkpoint,a.reason,a.updated_at_us FROM jobs j LEFT JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt"
                + (" WHERE j.job_id=?" if options.get("job_id") else "")
                + " ORDER BY j.job_id",
                (options["job_id"],) if options.get("job_id") else (),
            )
            if options.get("job_id") and not rows:
                raise CatalogError("NOT_FOUND", "Job not found")
            for row in rows:
                yield (
                    [row["job_id"]],
                    {
                        **dict(row),
                        "request": json.loads(row["request"]),
                        "checkpoint": json.loads(row["checkpoint"]),
                    },
                )
        elif command == "cache status":
            from repo_catalog.adapters.filesystem.cache import CacheManager
            from repo_catalog.adapters.filesystem.capacity import (
                Capacity,
                allocated_bytes,
            )

            for row in s.execute(
                "SELECT a.*,l.repository_uuidv4,l.path,l.access FROM active_cache_entries a JOIN cache_locators l USING(cache_locator_id) WHERE l.access='target_active' ORDER BY active_cache_entry_id"
            ):
                path, quarantine = CacheManager(s).paths(row)
                yield (
                    [row["active_cache_entry_id"]],
                    {
                        **dict(row),
                        "bytes": allocated_bytes(path) + allocated_bytes(quarantine),
                        "budget": s.config["cache"],
                        "managed_usage_bytes": Capacity(s).used(),
                        "reservations": [
                            dict(r) for r in s.all("SELECT * FROM space_reservations")
                        ],
                        "blocked_by": CacheManager(s).gate(row),
                    },
                )
        else:
            raise CatalogError("INVALID_ARGUMENT", "Unknown query")

    def _digests(self, content_id):
        return {
            r["algorithm"]: r["digest"].hex()
            for r in self.s.execute(
                "SELECT * FROM content_digests WHERE content_id=?", (content_id,)
            )
        }

    def decoder_offsets(self, object_id, kind, context, text, literal):
        decoded = self.decoded(object_id, kind, context)
        selected = [
            row
            for row in decoded["candidates"]
            if context.get("decoder_key") in (None, row["decoder_key"])
        ]
        field = "text_encoding" if kind == "blob" else "metadata_encoding"
        offsets = [self._literal_offsets(text, literal, row[field]) for row in selected]
        signatures = {json.dumps(value, sort_keys=True) for value in offsets}
        if len(signatures) == 1:
            return offsets[0]
        if len(signatures) > 1:
            self.coverage.add(
                "git",
                "decoder_offset_conflict",
                git_object_id=object_id,
                candidates=decoded["candidates"],
            )
        start = text.index(literal)
        return {
            "byte_start": None,
            "byte_end": None,
            "line": text[:start].count("\n") + 1,
            "snippet": text[max(0, start - 40) : start + len(literal) + 80],
        }

    @staticmethod
    def _literal_offsets(text, literal, encoding):
        start = text.index(literal)
        return {
            "byte_start": len(text[:start].encode(encoding)),
            "byte_end": len(text[: start + len(literal)].encode(encoding)),
            "line": text[:start].count("\n") + 1,
            "snippet": text[max(0, start - 40) : start + len(literal) + 80],
        }

    def pr_query(self, command, options):
        from repo_catalog.application.pr_queries import pr_query

        yield from pr_query(self, command, options)
