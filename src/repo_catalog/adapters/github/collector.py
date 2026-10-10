from __future__ import annotations

import hashlib
import json
import uuid
from importlib.resources import files
from urllib.parse import urlencode, urljoin, urlsplit

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.identity import database_resource_id
from repo_catalog.adapters.github.persistence import (
    ApiFacts,
    canonical,
    oid_context,
)
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.sqlite.cas_integrity import diagnose_admission_failure
from repo_catalog.domain.models import CatalogError, Waiting
from repo_catalog.domain.pr_scope import NON_DOCUMENT_KINDS
from repo_catalog.domain.time import format_iso8601_us


class GitHubCollector:
    """Live collection of direct resources and independent scoped evidence."""

    def __init__(
        self, store, token, transport=None, *, config=None, repository_endpoint_id=None
    ):
        self.s, self.token = store, token
        self.cfg = config or store.config["github"]
        self.repository_endpoint_id = repository_endpoint_id
        if transport is None:
            from repo_catalog.adapters.recording import recorder_from_config

            transport = GitHubTransport(
                self.cfg, token, recorder=recorder_from_config(self.cfg, store.path)
            )
            self.owned = True
        else:
            self.owned = False
        self.http = transport
        self.inventory_uncertainty = None
        self.inventory_evidence = []
        self.facts = ApiFacts(store, self.cfg)
        self.thread_collections = {}
        self.observed_partial_scopes = set()
        self.recording_diagnostics = []

    def coverage_claim(
        self,
        repository_uuidv4,
        kind,
        state,
        observed_at_us,
        details_json=None,
        *,
        change_request_id=None,
    ):
        if observed_at_us is None:
            return
        self.s.coverage(
            repository_uuidv4,
            kind,
            state,
            details_json,
            change_request_id=change_request_id,
            observed_at_us=observed_at_us,
        )
        if state == "partial":
            current = self.s.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id IS ? AND kind=?",
                (repository_uuidv4, change_request_id, kind),
            )
            if (
                current
                and current["observed_at_us"] == observed_at_us
                and current["coverage_state"] in ("partial", "conflict")
            ):
                self.observed_partial_scopes.add(
                    (repository_uuidv4, change_request_id, kind)
                )

    def collection_coverage(self, repo, pr, kind, collection, state, *, reason=None):
        self.coverage_claim(
            repo["repository_uuidv4"],
            kind,
            state,
            self.facts.observed_at_us(collection, include_partial=state != "complete"),
            {
                "fetch_collection_ids": [collection["fetch_collection_id"]],
                "completion_marker_uuidv4s": [
                    row[0]
                    for row in self.s.all(
                        "SELECT completion_marker_uuidv4 FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='complete'",
                        (collection["fetch_collection_id"],),
                    )
                ]
                if state == "complete"
                else [],
                **({"reason": reason} if reason else {}),
            },
            change_request_id=pr,
        )

    def _retain_recording_diagnostics(self, response):
        self.recording_diagnostics.extend(
            response.extensions.get("repo_catalog_recording_diagnostics", [])
        )
        del self.recording_diagnostics[:-100]

    def request_get(self, url, repo=None, **kwargs):
        seen = set()
        while True:
            if url in seen:
                raise CatalogError("PAGINATION_CYCLE", "API redirect cycle")
            seen.add(url)
            response = self.http.request("GET", url, **kwargs)
            self._retain_recording_diagnostics(response)
            if response.status_code not in (301, 302):
                return response
            target = urljoin(url, response.headers.get("location", ""))
            self.http.validate_url(target)
            if not repo:
                raise CatalogError("SCOPE_MISMATCH", "Unverified inventory redirect")
            target_path = urlsplit(target).path
            rest_prefix = urlsplit(self.http.base).path.rstrip("/") + "/repos/"
            if GitHubTransport.origin(target) != GitHubTransport.origin(
                self.http.base
            ) or not target_path.startswith(rest_prefix):
                raise CatalogError(
                    "SCOPE_MISMATCH",
                    "Redirect target is outside configured REST endpoint",
                )
            parts = target_path[len(rest_prefix) :].split("/")
            source = getattr(self.s, "frozen_source_settings", {}).get(
                repo["source_id"]
            )
            if source is None:
                source = json.loads(
                    self.s.one(
                        "SELECT settings FROM sources WHERE source_id=?",
                        (repo["source_id"],),
                    )[0]
                )
            if len(parts) < 2 or parts[0].lower() != source["owner"].lower():
                raise CatalogError(
                    "SCOPE_MISMATCH", "Transfer target is outside declared owner"
                )
            name = "/".join(parts[:2])
            base_revision = self.s.revision()
            identity_response = self.http.request(
                "GET", self.http.base + "/repos/" + name
            )
            self._retain_recording_diagnostics(identity_response)
            identity = self.rest_json(identity_response)
            if str(identity.get("id")) != repo["provider_repository_id"]:
                raise CatalogError(
                    "SCOPE_MISMATCH", "Redirect changed repository identity"
                )
            from repo_catalog.adapters.sqlite.current_api import CurrentApiState

            registration = self.s.one(
                "SELECT source_registration_uuidv4,service_instance_uuidv4 FROM sources WHERE source_id=?",
                (repo["source_id"],),
            )
            scope = {
                "source_registration_uuidv4": registration[
                    "source_registration_uuidv4"
                ],
                "service_instance_uuidv4": registration["service_instance_uuidv4"],
                "owner": source["owner"],
                "principal_ref": self.facts.principal,
                "api_version": self.cfg["rest_api_version"],
                "endpoint": self.http.base + "/repos/" + name,
                "query_kind": "verified-repository-redirect",
            }
            with self.s.transaction():
                CurrentApiState(self.s).confirm_source_repository(
                    repo["source_id"],
                    repo["repository_uuidv4"],
                    observed_at_us=self.facts.response_time(identity_response),
                    scope=scope,
                    parser_module=current_parser.PARSER_MODULE,
                    parser_version=current_parser.PARSER_VERSION,
                    name=name,
                    metadata=current_parser.repository_metadata(identity),
                    source="live",
                    base_revision=base_revision,
                    scope_context=scope,
                )
                self.facts.advance_revision()
            url = target

    def inventory_request(self, method, url, **kwargs):
        response = self.http.request(method, url, **kwargs)
        return response, self.rest_json(response)

    @staticmethod
    def inventory_repository_id(value):
        try:
            return database_resource_id(value)
        except ValueError:
            raise CatalogError(
                "API_SCHEMA", "Repository database ID must be a positive decimal ID"
            ) from None

    @staticmethod
    def rest_json(response):
        try:
            value = response.json()
            # Validate JSON strings before projecting modeled fields. Check
            # every string, including unknown metadata and keys, before any
            # projection can fail with UnicodeEncodeError. Rejected responses
            # remain transient and are acquired afresh on a live retry.
            json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            return value
        except (ValueError, UnicodeError):
            raise CatalogError("API_SCHEMA", "Malformed API JSON") from None

    @staticmethod
    def rest_item(value, kind):
        """Validate consumed REST shapes, leaving unknown provider fields raw."""
        if not isinstance(value, dict):
            raise CatalogError("API_SCHEMA", "REST item must be an object")
        if kind in (
            "pr-list",
            "pr-detail",
            "pr-code-check",
            "issue-comment",
            "review",
            "review-comment",
            "issue-comment-incremental",
            "review-comment-incremental",
        ):
            for field in ("body", "html_url", "url"):
                if value.get(field) is not None and not isinstance(value[field], str):
                    raise CatalogError("API_SCHEMA", f"Malformed document {field}")
            for field in ("user", "author"):
                author = value.get(field)
                if author is not None and (
                    not isinstance(author, dict)
                    or author.get("login") is not None
                    and not isinstance(author["login"], str)
                ):
                    raise CatalogError("API_SCHEMA", f"Malformed document {field}")
            if value.get("commit_id") is not None:
                GitHubCollector.rest_oid(value["commit_id"], "commit_id")
        if kind in ("pr-list", "pr-detail", "pr-code-check"):
            GitHubCollector.rest_integer(value.get("number"), "number", minimum=1)
            if not isinstance(value.get("title"), str):
                raise CatalogError("API_SCHEMA", "PR title missing or malformed")
            for field in ("head", "base"):
                ref = value.get(field)
                if ref is not None:
                    if not isinstance(ref, dict):
                        raise CatalogError("API_SCHEMA", f"Malformed PR {field}")
                    if ref.get("sha") is not None:
                        GitHubCollector.rest_oid(ref["sha"], field + ".sha")
            try:
                oid_context(value)
            except CatalogError:
                raise CatalogError(
                    "API_SCHEMA", "PR head/base must use the same object format"
                ) from None
            for field in ("commits", "changed_files"):
                if value.get(field) is not None:
                    GitHubCollector.rest_integer(value[field], field)
        if kind == "pr-commits":
            GitHubCollector.rest_oid(value.get("sha"), "sha")

    @staticmethod
    def rest_oid(value, field):
        if (
            not isinstance(value, str)
            or len(value) not in (40, 64)
            or any(char not in "0123456789abcdefABCDEF" for char in value)
        ):
            raise CatalogError("API_SCHEMA", f"Malformed REST {field}")

    @staticmethod
    def rest_integer(value, field, *, minimum=0):
        if type(value) is not int or not minimum <= value < 1 << 63:
            raise CatalogError("API_SCHEMA", f"Malformed REST {field}")

    @staticmethod
    def document_provider_id(value, field="id"):
        try:
            return database_resource_id(
                value.get(field) if isinstance(value, dict) else None
            )
        except ValueError:
            raise CatalogError(
                "CANONICAL_DOCUMENT_ID_MISSING",
                f"GitHub document {field} is missing or invalid; Node IDs are not aliases",
            ) from None

    def graphql_errors(self, payload, *resource):
        """Classify error-only responses before requiring ordinary data fields."""
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if isinstance(errors, list) and any(
            isinstance(error, dict) and error.get("type") == "RATE_LIMITED"
            for error in errors
        ):
            raise Waiting(
                "RATE_LIMIT",
                "GraphQL rate limited",
                {"not_before_us": self.http.clock_us() + 60_000_000},
                True,
            )
        if errors:
            try:
                self.graphql_object(payload, *resource)
            except CatalogError:
                raise CatalogError(
                    "GRAPHQL_PARTIAL", "GraphQL error-only response"
                ) from None

    @staticmethod
    def graphql_object(value, *path):
        for key in path:
            if not isinstance(value, dict):
                raise CatalogError("API_SCHEMA", "Malformed GraphQL object")
            value = value.get(key)
        if not isinstance(value, dict):
            raise CatalogError("API_SCHEMA", "Missing GraphQL object")
        return value

    @staticmethod
    def graphql_connection(value, *, refresh_root=False):
        """Only an explicit, well-formed terminal page proves completeness."""
        details = {"refresh_root": True} if refresh_root else None
        if not isinstance(value, dict) or not isinstance(value.get("nodes"), list):
            raise CatalogError("API_SCHEMA", "Missing GraphQL nodes array", details)
        if any(not isinstance(node, dict) for node in value["nodes"]):
            raise CatalogError("API_SCHEMA", "Malformed GraphQL node", details)
        info = value.get("pageInfo")
        if not isinstance(info, dict) or type(info.get("hasNextPage")) is not bool:
            raise CatalogError("API_SCHEMA", "Missing GraphQL page boundary", details)
        cursor = info.get("endCursor")
        if cursor is not None and not isinstance(cursor, str):
            raise CatalogError("API_SCHEMA", "Malformed GraphQL cursor", details)
        if info["hasNextPage"] and not cursor:
            raise CatalogError("API_SCHEMA", "Missing GraphQL next cursor", details)
        return value["nodes"], info, cursor if info["hasNextPage"] else None

    def _thread_documents(
        self,
        repo,
        pr,
        review_thread_provider_resource_id,
        connection,
        collection,
        occurrence,
        offset,
        timestamp,
        *,
        base_revision,
        refresh_root=False,
    ):
        from repo_catalog.domain.current_state import fingerprint_candidate

        nodes, _, _ = self.graphql_connection(connection, refresh_root=refresh_root)
        context = self.facts.current_context(
            repo, pr["change_request_id"], self.http.graphql, "review-comment"
        )
        members = []
        for position, value in enumerate(nodes):
            candidate = current_parser.review_comment(
                value,
                context,
                timestamp,
                graphql=True,
                thread=review_thread_provider_resource_id,
            )
            self.facts.admit_current(candidate, base_revision)
            members.append(
                {
                    "family": "review",
                    "change_request_id": pr["change_request_id"],
                    "kind": "review-comment",
                    "provider_change_request_document_id": candidate[
                        "provider_change_request_document_id"
                    ],
                    "state_digest": fingerprint_candidate(candidate),
                }
            )
        return members

    def sync_issues(self, repo, job):
        """Collect all accessible ordinary Issues and independently refresh children."""
        s = self.s
        root = f"{self.http.base}/repos/{repo['name']}"
        failures, waiting = [], None

        def attempt(kind, operation):
            nonlocal waiting
            if waiting is not None and waiting > self.http.clock_us():
                failures.append({"kind": kind, "reason": "RATE_LIMIT_WAIT"})
                return None
            try:
                return operation()
            except CatalogError as error:
                if error.code in ("CANCELLED", "STALE_ATTEMPT"):
                    raise
                failures.append({"kind": kind, "reason": error.code})
                waiting = error.details.get("not_before_us", waiting)
                return None

        try:
            response = self.http.request("GET", self.http.base + "/user")
            self._retain_recording_diagnostics(response)
            identity = response.json()
            principal = identity.get("id") or identity.get("login")
            if not principal:
                raise CatalogError("API_SCHEMA", "Principal identity missing")
            self.facts.principal = str(principal)
            permissions = response.headers.get("x-oauth-scopes")
            self.facts.permissions = (
                sorted(item.strip() for item in permissions.split(",") if item.strip())
                if permissions is not None
                else None
            )
            size = self.cfg["rest_page_size"]
            list_endpoint = (
                root + f"/issues?state=all&sort=updated&direction=asc&per_page={size}"
            )
            list_context = {
                "state": "all",
                "sort": "updated",
                "direction": "asc",
                "incremental_endpoint": list_endpoint,
            }
            list_url, list_context = self.current_incremental_url(
                repo, job, "issue", list_endpoint, list_context
            )
            listing = attempt(
                "issue",
                lambda: self.current_collection(
                    repo,
                    None,
                    "issue",
                    job,
                    list_url,
                    current_parser.issue,
                    context=list_context,
                ),
            )
            # Parent updated_at does not order comment edits. Refresh every
            # stored accessible parent's complete comment list independently,
            # including closed Issues and parents absent from a failed page.
            selected_binding = self.facts.current_context(repo, None, root)[
                "repository_binding_id"
            ]
            issues = s.all(
                "SELECT * FROM issue_resources WHERE repository_binding_id=? AND kind='issue' ORDER BY provider_issue_number",
                (selected_binding,),
            )
            collections = [listing[0]] if listing else []
            for parent in issues:
                comment_endpoint = (
                    root
                    + f"/issues/{parent['provider_issue_number']}/comments?per_page={size}"
                )
                comment_context = {
                    "provider_issue_id": parent["provider_resource_id"],
                    "provider_issue_number": parent["provider_issue_number"],
                    "incremental_endpoint": comment_endpoint,
                }
                comment_url, comment_context = self.current_incremental_url(
                    repo,
                    job,
                    "ordinary-issue-comment",
                    comment_endpoint,
                    comment_context,
                )

                def parse_comment(value, context, timestamp, parent=parent):
                    context = {
                        **context,
                        "provider_issue_number": parent["provider_issue_number"],
                    }
                    return current_parser.issue_comment(
                        value, context, timestamp, parent["provider_resource_id"]
                    )

                collected = attempt(
                    "ordinary-issue-comment",
                    lambda parent=parent, parse_comment=parse_comment, comment_url=comment_url, comment_context=comment_context: (
                        self.current_collection(
                            repo,
                            None,
                            "ordinary-issue-comment",
                            job,
                            comment_url,
                            parse_comment,
                            context=comment_context,
                        )
                    ),
                )
                if collected:
                    collections.append(collected[0])
            with s.transaction():
                self.facts.fence(job)
                observed = s.one(
                    "WITH scoped AS (SELECT f.fetch_collection_id FROM fetch_collections f "
                    "JOIN collection_progress c USING(fetch_collection_id) "
                    "WHERE c.job_id=? AND f.repository_uuidv4=? AND f.source_id=? "
                    "AND f.kind IN ('issue','ordinary-issue-comment')) "
                    "SELECT MAX(observed_at_us) FROM ("
                    "SELECT p.observed_at_us FROM scoped JOIN current_collection_pages p "
                    "USING(fetch_collection_id) UNION ALL "
                    "SELECT m.observed_at_us FROM scoped JOIN completion_markers m "
                    "USING(fetch_collection_id) WHERE m.asserted_state='partial' AND ?)",
                    (job, repo["repository_uuidv4"], repo["source_id"], bool(failures)),
                )[0]
                self.coverage_claim(
                    repo["repository_uuidv4"],
                    "issue",
                    "partial" if failures else "complete",
                    observed,
                    {
                        "fetch_collection_ids": sorted(collections),
                        **({"missing": failures} if failures else {}),
                    },
                )
                self.facts.advance_revision()
            if failures:
                raise Waiting(
                    "ISSUE_PARTIAL",
                    "Some ordinary Issue collections are incomplete",
                    {
                        "missing": failures,
                        **({"not_before_us": waiting} if waiting is not None else {}),
                    },
                    True,
                )
            return {
                "repository_uuidv4": repo["repository_uuidv4"],
                "state": "complete",
                "issues": len(issues),
                **(
                    {"recording_diagnostics": self.recording_diagnostics}
                    if self.recording_diagnostics
                    else {}
                ),
            }
        finally:
            if self.owned:
                self.http.close()

    @staticmethod
    def member(candidate):
        from repo_catalog.domain.current_state import fingerprint_candidate

        kind = candidate["kind"]
        if kind == "change-request":
            family, keys = "change-request", ("change_request_id",)
        elif kind == "review-thread":
            family, keys = "thread", ("change_request_id", "provider_resource_id")
        elif (
            kind in ("pr-title", "pr-body")
            or kind == "issue-comment"
            and "change_request_id" in candidate
        ):
            family, keys = (
                "document",
                ("change_request_id", "kind", "provider_change_request_document_id"),
            )
        elif kind in ("issue", "issue-comment"):
            family, keys = (
                "issue",
                ("service_instance_uuidv4", "kind", "provider_resource_id"),
            )
        else:
            family, keys = (
                "review",
                ("change_request_id", "kind", "provider_change_request_document_id"),
            )
        return {
            "family": family,
            **{key: candidate[key] for key in keys},
            "state_digest": fingerprint_candidate(candidate),
        }

    def current_incremental_url(self, repo, job, kind, endpoint, context):
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        candidates = self.s.all(
            "SELECT f.*,p.job_id,p.state,c.completion_marker_uuidv4,c.asserted_state,c.evidence,c.observed_at_us marker_observed_at_us FROM fetch_collections f JOIN collection_progress p USING(fetch_collection_id) LEFT JOIN completion_markers c USING(fetch_collection_id) WHERE f.repository_uuidv4=? AND f.kind=? AND f.source_id=? AND json_extract(f.scope_json,'$.principal_ref') IS ? AND json_extract(f.scope_json,'$.api_version')=? AND json_extract(f.scope_json,'$.request_context.incremental_endpoint')=? ORDER BY f.observed_at_us DESC",
            (
                repo["repository_uuidv4"],
                kind,
                repo["source_id"],
                self.facts.principal,
                self.cfg["rest_api_version"],
                endpoint,
            ),
        )
        proof = CurrentCollectionProof(self.s.connection)
        for row in candidates:
            scope = json.loads(row["scope_json"])
            saved_context = scope.get("request_context", {})
            if saved_context.get("permissions") != self.facts.permissions:
                continue
            if row["job_id"] == job:
                return scope["endpoint"], saved_context
            if (
                scope.get("parser_module") != current_parser.PARSER_MODULE
                or scope.get("parser_version") != current_parser.PARSER_VERSION
            ):
                continue
            if row["state"] == "complete" and proof.is_complete_marker(
                {**dict(row), "observed_at_us": row["marker_observed_at_us"]}
            ):
                return endpoint + "&" + urlencode(
                    {"since": format_iso8601_us(row["observed_at_us"] - 300_000_000)}
                ), {
                    **context,
                    "completion_marker_uuidv4": row["completion_marker_uuidv4"],
                }
        return endpoint, context

    def current_collection(self, repo, pr, kind, job, url, parser, *, context=None):
        def normalize(value, collection, base_revision, position, timestamp, listing):
            candidate_context = self.facts.current_context(repo, pr, url)
            candidate = parser(value, candidate_context, timestamp)
            if candidate is None:
                return []
            self.facts.admit_current(candidate, base_revision)
            return [self.member(candidate)]

        return self.collection(repo, pr, kind, job, url, normalize, context=context)

    @staticmethod
    def current_resource_identified(value, kind):
        if not isinstance(value, dict) or kind == "issue" and "pull_request" in value:
            return False
        try:
            current_parser.resource_id(value)
        except CatalogError:
            return False
        if kind == "issue":
            number = value.get("number")
            return type(number) is int and 0 < number < 1 << 63
        return True

    def current_members_unresolved(self, collection_id):
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        tables = {
            "issue": (
                "issue_resources",
                ("service_instance_uuidv4", "kind", "provider_resource_id"),
            ),
            "review": (
                "review_resources",
                ("change_request_id", "kind", "provider_change_request_document_id"),
            ),
            "change-request": ("change_request_state", ("change_request_id",)),
            "document": (
                "document_state",
                ("change_request_id", "kind", "provider_change_request_document_id"),
            ),
            "thread": (
                "review_thread_state",
                ("change_request_id", "provider_resource_id"),
            ),
        }
        for member in CurrentCollectionProof(self.s.connection).members(collection_id):
            if member["family"] == "event":
                if (
                    self.s.one(
                        "SELECT 1 FROM change_request_events WHERE change_request_event_uuidv4=? AND provider_event_id IS NOT NULL",
                        (member["change_request_event_uuidv4"],),
                    )
                    is None
                ):
                    return True
                continue
            if member["family"] not in tables:
                continue
            table, keys = tables[member["family"]]
            predicate = " AND ".join(f"{key}=?" for key in keys)
            if (
                self.s.one(
                    f"SELECT 1 FROM {table} WHERE {predicate}",
                    tuple(member[key] for key in keys),
                )
                is None
            ):
                return True
            if table in ("issue_resources", "review_resources"):
                diagnostics = " AND ".join(
                    f"json_extract(record_json,'$.{key}')=?" for key in keys
                )
                if self.s.one(
                    "SELECT 1 FROM current_resource_diagnostics WHERE table_name=? AND "
                    + diagnostics,
                    (table, *(member[key] for key in keys)),
                ):
                    return True
            else:
                diagnostics = " AND ".join(
                    f"json_extract(record_json,'$.{key}')=?" for key in keys
                )
                if self.s.one(
                    "SELECT 1 FROM exchange_staging WHERE reason LIKE 'current_state:%' AND table_name=? AND "
                    + diagnostics,
                    (table, *(member[key] for key in keys)),
                ):
                    return True
        return False

    def collection(
        self,
        repo,
        pr,
        kind,
        job,
        url,
        normalizer,
        *,
        context=None,
        listing_kind=None,
        cap=None,
        reported=None,
        reuse=False,
    ):
        from repo_catalog.adapters.git.runner import hook

        s = self.s
        if listing_kind:
            context = {**(context or {}), "reported_count": reported}
        with s.transaction():
            self.facts.fence(job)
            collection = self.facts.begin(
                repo, pr, kind, job, url, context, reuse=reuse
            )
            listing = None
            if listing_kind:
                row = s.one(
                    "SELECT code_listing_id FROM code_listings WHERE fetch_collection_id=? AND kind=?",
                    (collection["fetch_collection_id"], listing_kind),
                )
                listing = row[0] if row else str(uuid.uuid4())
                if row is None:
                    algorithm, head, base = oid_context(context or {})
                    s.execute(
                        "INSERT INTO code_listings(code_listing_id,change_request_id,fetch_collection_id,kind,resume_scope_id,object_format,head_oid,base_oid) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            listing,
                            pr,
                            collection["fetch_collection_id"],
                            listing_kind,
                            collection.get("resume_scope_id"),
                            algorithm,
                            head,
                            base,
                        ),
                    )
                    s.execute(
                        "INSERT INTO code_listing_progress(code_listing_id,state,terminal,page_count,context_proven) VALUES(?,'partial',0,0,0)",
                        (listing,),
                    )
            if collection["state"] == "complete":
                return collection["fetch_collection_id"], listing
        previous = s.one(
            "SELECT ordinal,has_next FROM current_collection_pages WHERE fetch_collection_id=? ORDER BY ordinal DESC LIMIT 1",
            (collection["fetch_collection_id"],),
        )
        page_url = (
            collection.get("cursor")
            if previous and previous["has_next"]
            else None
            if previous
            else url
        )
        if previous and previous["has_next"] and not page_url:
            raise CatalogError(
                "RESUME_UNAVAILABLE",
                "Committed prefix has no operational cursor; a fresh scan is required",
            )
        seen = set()
        response, uncommitted, identified = None, False, False
        try:
            while page_url:
                response, uncommitted, identified = None, False, False
                self.token.check()
                if page_url in seen:
                    raise CatalogError("PAGINATION_CYCLE", "Repeated collection page")
                seen.add(page_url)
                base_revision = s.revision()
                response = self.request_get(page_url, repo)
                if response.status_code == 304:
                    # No response cache is a core input. Conditional reuse requires
                    # corresponding normalized state, so acquire a fresh body.
                    response = self.request_get(
                        page_url, repo, headers={"Cache-Control": "no-cache"}
                    )
                    if response.status_code == 304:
                        raise CatalogError(
                            "REUSE_UNAVAILABLE",
                            "304 has no corresponding normalized representation",
                        )
                uncommitted = True
                values = self.rest_json(response)
                if not isinstance(values, list):
                    raise CatalogError(
                        "API_SCHEMA", "Collection response must be a list"
                    )
                identified = not values or any(
                    self.current_resource_identified(value, kind)
                    if kind not in ("pr-commits", "pr-files", "timeline")
                    else isinstance(value, dict)
                    and (
                        isinstance(value.get("sha"), str)
                        or isinstance(value.get("filename"), str)
                        or isinstance(value.get("event"), str)
                    )
                    for value in values
                )
                timestamp, next_url = (
                    self.facts.response_time(response),
                    self.http.next_url(response),
                )
                hook("before_api_page_commit")
                with s.transaction():
                    self.facts.fence(job)
                    ordinal = s.one(
                        "SELECT count(*) FROM current_collection_pages WHERE fetch_collection_id=?",
                        (collection["fetch_collection_id"],),
                    )[0]
                    members = []
                    for index, value in enumerate(values):
                        self.rest_item(value, kind)
                        admitted = normalizer(
                            value,
                            collection,
                            base_revision,
                            ordinal * self.cfg["rest_page_size"] + index,
                            timestamp,
                            listing,
                        )
                        members.extend(admitted or [])
                    self.facts.page(
                        collection,
                        timestamp,
                        next_url,
                        members,
                        status=response.status_code,
                    )
                    if listing:
                        s.execute(
                            "UPDATE code_listing_progress SET page_count=page_count+1,terminal=? WHERE code_listing_id=?",
                            (int(next_url is None), listing),
                        )
                    self.facts.advance_revision()
                uncommitted = False
                hook("after_api_page_commit")
                page_url = next_url
            if listing:
                table = (
                    "code_commits" if listing_kind == "commits" else "code_file_changes"
                )
                count = s.one(
                    f"SELECT count(*) FROM {table} WHERE code_listing_id=?", (listing,)
                )[0]
                if cap and (count >= cap or reported is not None and count < reported):
                    raise CatalogError(
                        "API_CAP",
                        "Provider list may be truncated",
                        {"cap": cap, "collected": count, "reported": reported},
                    )
            with s.transaction():
                self.facts.fence(job)
                if self.current_members_unresolved(collection["fetch_collection_id"]):
                    raise CatalogError(
                        "CURRENT_STATE_UNRESOLVED",
                        "Collection contains unresolved resources",
                    )
                self.facts.finish(collection)
                if listing:
                    s.execute(
                        "UPDATE code_listing_progress SET state='complete',terminal=1,context_proven=1 WHERE code_listing_id=?",
                        (listing,),
                    )
                self.collection_coverage(repo, pr, kind, collection, "complete")
                self.facts.advance_revision()
            return collection["fetch_collection_id"], listing
        except CatalogError as error:
            self.partial_rest_collection(
                repo,
                pr,
                kind,
                job,
                collection,
                error,
                response if uncommitted and identified else None,
                page_url,
            )
            raise

    def partial_rest_collection(
        self, repo, pr, kind, job, collection, error, response, url
    ):
        with self.s.transaction():
            self.facts.fence(job)
            diagnose_admission_failure(self.s.connection, error)
            if response is not None:
                self.s.execute(
                    "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                    (url, collection["fetch_collection_id"]),
                )
            self.facts.partial(
                collection,
                error.code,
                observed_at_us=self.facts.response_time(response)
                if response is not None
                and error.code not in ("CANCELLED", "STALE_ATTEMPT", "SCOPE_MISMATCH")
                else None,
            )
            if error.code not in (
                "CANCELLED",
                "STALE_ATTEMPT",
            ) or self.facts.pending_response(collection):
                self.collection_coverage(
                    repo, pr, kind, collection, "partial", reason=error.code
                )
            self.facts.advance_revision()

    def ensure_pr(
        self, repo, value, collection, base_revision, position, timestamp, **unused
    ):
        self.rest_item(value, "pr-detail")
        self.document_provider_id(value)
        endpoint = json.loads(collection["scope_json"])["endpoint"]
        context = self.facts.current_context(repo, None, endpoint)
        binding = context["repository_binding_id"]
        row = self.s.one(
            "SELECT change_request_id FROM change_requests WHERE repository_binding_id=? AND change_request_kind='pull_request' AND provider_change_request_number=?",
            (binding, value["number"]),
        )
        ident = row[0] if row else f"{repo['repository_uuidv4']}:{value['number']}"
        if row is None and self.s.one(
            "SELECT 1 FROM change_requests WHERE change_request_id=?", (ident,)
        ):
            ident = f"{binding}:{value['number']}"
        if collection.get("change_request_id") not in (None, ident):
            raise CatalogError(
                "SCOPE_MISMATCH", "PR response differs from requested parent"
            )
        if row is None:
            self.s.execute(
                "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES(?,?,?,'pull_request',?)",
                (ident, repo["repository_uuidv4"], binding, value["number"]),
            )
        context = {
            **context,
            "change_request_id": ident,
            "acquisition_scope": {
                **context["acquisition_scope"],
                "change_request_id": ident,
            },
        }
        candidate = current_parser.pull_request(value, context, timestamp)
        self.facts.admit_current(candidate, base_revision)
        members = [self.member(candidate)]
        for kind in ("pr-title", "pr-body"):
            candidate = current_parser.document(value, context, timestamp, kind)
            # A missing title/body is unknown, never synthesized empty text.
            self.facts.admit_current(candidate, base_revision)
            members.append(self.member(candidate))
        return ident, members

    def detail(self, repo, pr, job, url):
        with self.s.transaction():
            self.facts.fence(job)
            collection = self.facts.begin(
                repo, pr["change_request_id"], "pr-detail", job, url
            )
        if collection["state"] == "complete":
            return self._current_pr_value(pr["change_request_id"]), pr[
                "change_request_id"
            ]
        base_revision = self.s.revision()
        response = self.request_get(url, repo)
        if response.status_code == 304:
            response = self.request_get(
                url, repo, headers={"Cache-Control": "no-cache"}
            )
            if response.status_code == 304:
                raise CatalogError(
                    "REUSE_UNAVAILABLE", "304 without normalized representation"
                )
        value = None
        try:
            value = self.rest_json(response)
            timestamp = self.facts.response_time(response)
            with self.s.transaction():
                self.facts.fence(job)
                _, members = self.ensure_pr(
                    repo, value, collection, base_revision, 0, timestamp
                )
                self.facts.page(
                    collection, timestamp, None, members, status=response.status_code
                )
                if self.current_members_unresolved(collection["fetch_collection_id"]):
                    raise CatalogError(
                        "CURRENT_STATE_UNRESOLVED",
                        "Detail contains unresolved current state",
                    )
                self.facts.finish(collection)
                self.facts.advance_revision()
            return value, pr["change_request_id"]
        except CatalogError as error:
            self.partial_rest_collection(
                repo,
                pr["change_request_id"],
                "pr-detail",
                job,
                collection,
                error,
                response
                if isinstance(value, dict) and value.get("id") is not None
                else None,
                url,
            )
            raise

    def _document_normalizer(self, repo, pr, kind, endpoint):
        def normalize(value, collection, base_revision, position, timestamp, listing):
            context = self.facts.current_context(repo, pr, endpoint)
            candidate = current_parser.document(value, context, timestamp, kind)
            self.facts.admit_current(candidate, base_revision)
            return [self.member(candidate)]

        return normalize

    def summary_collection_ids(self, repo, job, *, documents_only=False):
        return [
            row[0]
            for row in self.s.all(
                "SELECT f.fetch_collection_id FROM fetch_collections f JOIN collection_progress p USING(fetch_collection_id) WHERE f.repository_uuidv4=? AND f.source_id=? AND p.job_id=?"
                + (
                    " AND f.kind NOT IN ("
                    + ",".join("?" for _ in NON_DOCUMENT_KINDS)
                    + ")"
                    if documents_only
                    else ""
                )
                + " ORDER BY f.fetch_collection_id",
                (
                    repo["repository_uuidv4"],
                    repo["source_id"],
                    job,
                    *(sorted(NON_DOCUMENT_KINDS) if documents_only else ()),
                ),
            )
        ]

    def summary_marker_ids(self, repo, job, *, documents_only=False):
        identifiers = self.summary_collection_ids(
            repo, job, documents_only=documents_only
        )
        return (
            [
                row[0]
                for row in self.s.all(
                    "SELECT completion_marker_uuidv4 FROM completion_markers WHERE asserted_state='complete' AND fetch_collection_id IN ("
                    + ",".join("?" for _ in identifiers)
                    + ") ORDER BY completion_marker_uuidv4",
                    identifiers,
                )
            ]
            if identifiers
            else []
        )

    def summary_observed_at_us(
        self, repo, job, *, documents_only=False, include_partial=True
    ):
        return self.s.one(
            "SELECT MAX(o.observed_at_us) FROM (SELECT fetch_collection_id,observed_at_us FROM current_collection_pages UNION ALL SELECT fetch_collection_id,observed_at_us FROM completion_markers WHERE asserted_state='partial' AND ?) o JOIN fetch_collections f USING(fetch_collection_id) JOIN collection_progress p USING(fetch_collection_id) WHERE f.repository_uuidv4=? AND f.source_id=? AND p.job_id=?"
            + (
                " AND f.kind NOT IN (" + ",".join("?" for _ in NON_DOCUMENT_KINDS) + ")"
                if documents_only
                else ""
            ),
            (
                include_partial,
                repo["repository_uuidv4"],
                repo["source_id"],
                job,
                *(sorted(NON_DOCUMENT_KINDS) if documents_only else ()),
            ),
        )[0]

    def thread_collection_ids(self, collection):
        return [
            collection["fetch_collection_id"],
            *[
                row[0]
                for row in self.s.all(
                    "SELECT child_fetch_collection_id FROM thread_collection_requirements WHERE fetch_collection_id=? AND child_fetch_collection_id IS NOT NULL ORDER BY provider_resource_id",
                    (collection["fetch_collection_id"],),
                )
            ],
        ]

    def inventory(self, source, job, *, admit_repository=None):
        cfg = json.loads(source["settings"])
        owner = cfg["owner"]
        self.inventory_items = []
        self.inventory_evidence = []
        self.inventory_uncertainty = None
        base = self.http.base
        scope = {
            "source_registration_uuidv4": source["source_registration_uuidv4"],
            "service_instance_uuidv4": source["service_instance_uuidv4"],
            "owner": owner,
            "api_version": self.cfg["rest_api_version"],
            "principal_ref": None,
            "visibility": "all",
            "selected_repositories": cfg.get("include_repositories"),
            "query_kind": "owner-repositories",
        }
        self.inventory_scope = scope
        self.inventory_job = (job, self.facts.fence(job))

        def request(url):
            base_revision = self.s.revision()
            response, value = self.inventory_request("GET", url)
            self._retain_recording_diagnostics(response)
            return response, value, base_revision

        def item(value, timestamp, base_revision):
            if not isinstance(value, dict) or not isinstance(
                value.get("full_name"), str
            ):
                raise CatalogError("API_SCHEMA", "Repository identity missing")
            provider = self.inventory_repository_id(value.get("id"))
            parts = value["full_name"].split("/")
            if len(parts) != 2 or not all(parts) or parts[0].lower() != owner.lower():
                raise CatalogError(
                    "SCOPE_MISMATCH", "Inventory repository outside owner scope"
                )
            clone = cfg.get("clone_url_overrides", {}).get(
                provider, value.get("clone_url")
            )
            if not isinstance(clone, str) or not clone:
                raise CatalogError("API_SCHEMA", "Repository clone URL missing")
            return {
                "host": "github.com",
                "provider_repository_id": provider,
                "name": value["full_name"],
                "url": clone,
                "metadata": current_parser.repository_metadata(value),
                "observed_at_us": timestamp,
                "parser_module": current_parser.PARSER_MODULE,
                "parser_version": current_parser.PARSER_VERSION,
                "scope": dict(scope),
                "scope_context": dict(scope),
                "base_revision": base_revision,
            }

        def admit_page(response, values, base_revision, terminal):
            timestamp = self.facts.response_time(response)
            normalized = [item(value, timestamp, base_revision) for value in values]
            members = []
            with self.s.transaction():
                self.facts.fence(job)
                for candidate in normalized:
                    repository = (
                        admit_repository(candidate) if admit_repository else None
                    )
                    members.append(repository or candidate["provider_repository_id"])
                self.facts.advance_revision()
            self.inventory_items.extend(normalized)
            self.inventory_evidence.append(
                {
                    "scope": dict(scope),
                    "observed_at_us": timestamp,
                    "members": members,
                    "terminal": terminal,
                    "parser_module": current_parser.PARSER_MODULE,
                    "parser_version": current_parser.PARSER_VERSION,
                }
            )

        try:
            _, identity, _ = request(base + "/user")
            if (
                not isinstance(identity, dict)
                or not isinstance(identity.get("login"), str)
                or not identity["login"].strip()
            ):
                raise CatalogError("API_SCHEMA", "Authenticated identity missing")
            scope["principal_ref"] = str(identity.get("id") or identity["login"])
            self.facts.principal = scope["principal_ref"]
            if cfg.get("include_repositories"):
                import re

                scope["query_kind"] = "selected-repositories"
                selected = cfg["include_repositories"]
                for index, name in enumerate(selected):
                    name = name.removeprefix(owner + "/")
                    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                        raise CatalogError(
                            "INVALID_ARGUMENT",
                            "Included repository must belong to declared owner",
                        )
                    response, value, revision = request(
                        base + "/repos/" + owner + "/" + name
                    )
                    if (
                        not isinstance(value, dict)
                        or value.get("full_name", "").lower()
                        != f"{owner}/{name}".lower()
                    ):
                        raise CatalogError(
                            "SCOPE_MISMATCH", "Selected repository identity changed"
                        )
                    admit_page(response, [value], revision, index == len(selected) - 1)
                return self.inventory_items
            if identity["login"].lower() == owner.lower():
                url = (
                    base
                    + "/user/repos?"
                    + urlencode(
                        {
                            "affiliation": "owner",
                            "visibility": "all",
                            "per_page": self.cfg["rest_page_size"],
                        }
                    )
                )
            else:
                _, user, _ = request(base + "/users/" + owner)
                if not isinstance(user, dict) or user.get("type") != "Organization":
                    raise CatalogError(
                        "SCOPE_UNSUPPORTED",
                        "Private owner inventory scope is unestablished",
                    )
                scope["query_kind"] = "organization-repositories"
                url = (
                    base
                    + "/orgs/"
                    + owner
                    + "/repos?"
                    + urlencode({"type": "all", "per_page": self.cfg["rest_page_size"]})
                )
            seen = set()
            while url:
                if url in seen:
                    raise CatalogError("PAGINATION_CYCLE", "Repeated inventory page")
                seen.add(url)
                response, values, revision = request(url)
                if not isinstance(values, list):
                    raise CatalogError("API_SCHEMA", "Expected repository list")
                next_url = self.http.next_url(response)
                admit_page(response, values, revision, next_url is None)
                url = next_url
            counts = (identity.get("public_repos"), identity.get("owned_private_repos"))
            if (
                identity["login"].lower() != owner.lower()
                or not all(type(value) is int and value >= 0 for value in counts)
                or any(
                    type(candidate["metadata"].get("private")) is not bool
                    for candidate in self.inventory_items
                )
            ):
                self.inventory_uncertainty = "INVENTORY_SCOPE_UNVERIFIED"
            elif counts != (
                sum(
                    not candidate["metadata"]["private"]
                    for candidate in self.inventory_items
                ),
                sum(
                    candidate["metadata"]["private"]
                    for candidate in self.inventory_items
                ),
            ):
                self.inventory_uncertainty = "INVENTORY_COUNT_MISMATCH"
            return list(
                {
                    candidate["provider_repository_id"]: candidate
                    for candidate in self.inventory_items
                }.values()
            )
        except CatalogError as error:
            self.inventory_uncertainty = error.code
            raise
        finally:
            if self.owned:
                self.http.close()

    def saved_thread_code_input(self, pr):
        collection = self.thread_collections.get(pr)
        if collection is None:
            return {}, False, None
        rows = self.s.all(
            "SELECT role,oid,observed_at_us FROM thread_collection_targets WHERE fetch_collection_id=?",
            (collection["fetch_collection_id"],),
        )
        return (
            {
                row["role"]: row["oid"].hex() if row["oid"] is not None else None
                for row in rows
            },
            {row["role"] for row in rows} == {"merge", "test-merge"},
            max((row["observed_at_us"] for row in rows), default=None),
        )

    def _thread_child(self, repo, pr, requirement, job, query):
        collection = dict(
            self.s.one(
                "SELECT f.*,p.state,p.cursor FROM fetch_collections f LEFT JOIN collection_progress p USING(fetch_collection_id) WHERE f.fetch_collection_id=?",
                (requirement["child_fetch_collection_id"],),
            )
        )
        if collection.get("state") == "complete":
            return
        child_cursor = self.s.one(
            "SELECT child_cursor FROM thread_collection_continuations WHERE fetch_collection_id=? AND provider_resource_id=?",
            (requirement["fetch_collection_id"], requirement["provider_resource_id"]),
        )
        if self.facts.pending_response(collection) and (
            child_cursor is None or child_cursor[0] is None
        ):
            raise CatalogError(
                "RESUME_UNAVAILABLE",
                "Thread child continuation is unavailable; a fresh root is required",
            )
        try:
            cursor = child_cursor[0] if child_cursor else None
            seen = set()
            response, node, uncommitted = None, None, False
            while cursor:
                self.token.check()
                if cursor in seen:
                    raise CatalogError(
                        "PAGINATION_CYCLE", "Repeated thread child cursor"
                    )
                seen.add(cursor)
                node, uncommitted = None, True
                base_revision = self.s.revision()
                response = self.http.request(
                    "POST",
                    self.http.graphql,
                    json={
                        "query": query,
                        "variables": {
                            "thread": requirement["provider_resource_id"],
                            "commentCursor": cursor,
                            "pageSize": self.cfg["graphql_page_size"],
                        },
                    },
                )
                self._retain_recording_diagnostics(response)
                payload = self.rest_json(response)
                self.graphql_errors(payload, "data", "node")
                node = self.graphql_object(payload, "data", "node")
                if node.get("id") != requirement["provider_resource_id"]:
                    raise CatalogError(
                        "SCOPE_MISMATCH", "Child response has foreign thread parent"
                    )
                _, _, next_cursor = self.graphql_connection(node.get("comments"))
                timestamp = self.facts.response_time(response)
                with self.s.transaction():
                    self.facts.fence(job)
                    members = self._thread_documents(
                        repo,
                        pr,
                        requirement["provider_resource_id"],
                        node["comments"],
                        collection,
                        None,
                        0,
                        timestamp,
                        base_revision=base_revision,
                    )
                    self.facts.page(
                        collection,
                        timestamp,
                        cursor if payload.get("errors") else next_cursor,
                        members,
                        status=response.status_code,
                    )
                    self.s.execute(
                        "UPDATE thread_collection_continuations SET child_cursor=?,observed_at_us=? WHERE fetch_collection_id=? AND provider_resource_id=?",
                        (
                            cursor if payload.get("errors") else next_cursor,
                            timestamp,
                            requirement["fetch_collection_id"],
                            requirement["provider_resource_id"],
                        ),
                    )
                    self.facts.advance_revision()
                uncommitted = False
                if payload.get("errors"):
                    raise CatalogError(
                        "GRAPHQL_PARTIAL", "Thread child page is partial"
                    )
                cursor = next_cursor
            with self.s.transaction():
                self.facts.fence(job)
                if self.current_members_unresolved(collection["fetch_collection_id"]):
                    raise CatalogError(
                        "CURRENT_STATE_UNRESOLVED",
                        "Thread child has unresolved members",
                    )
                self.facts.finish(collection)
                self.facts.advance_revision()
        except CatalogError as error:
            with self.s.transaction():
                self.facts.fence(job)
                self.facts.partial(
                    collection,
                    error.code,
                    observed_at_us=self.facts.response_time(response)
                    if response is not None
                    and uncommitted
                    and isinstance(node, dict)
                    and node.get("id") == requirement["provider_resource_id"]
                    and error.code
                    not in ("CANCELLED", "STALE_ATTEMPT", "SCOPE_MISMATCH")
                    else None,
                )
                self.facts.advance_revision()
            raise

    def threads(self, repo, pr, job):
        owner, name = repo["name"].split("/", 1)
        root_query = (
            files("repo_catalog").joinpath("resources/pr_threads.graphql").read_text()
        )
        child_query = (
            files("repo_catalog")
            .joinpath("resources/thread_comments.graphql")
            .read_text()
        )
        current = self.s.one(
            "SELECT object_format,head_oid,base_oid FROM change_request_state WHERE change_request_id=?",
            (pr["change_request_id"],),
        )
        target = (
            {
                "object_format": current["object_format"],
                "head_oid": current["head_oid"].hex() if current["head_oid"] else None,
                "base_oid": current["base_oid"].hex() if current["base_oid"] else None,
            }
            if current
            else {}
        )
        with self.s.transaction():
            self.facts.fence(job)
            collection = self.facts.begin(
                repo,
                pr["change_request_id"],
                "threads",
                job,
                self.http.graphql,
                {
                    "owner": owner,
                    "name": name,
                    "number": pr["provider_change_request_number"],
                    "query": root_query,
                    **target,
                },
            )
        self.thread_collections[pr["change_request_id"]] = collection
        if collection["state"] == "complete":
            return self.saved_thread_code_input(pr["change_request_id"])[0]
        response, uncommitted, identified = None, False, False
        payload = None
        try:
            # Commit the root's accepted values and normalized child requirements
            # first. Resume requires no saved response envelope.
            for requirement in self.s.all(
                "SELECT * FROM thread_collection_requirements WHERE fetch_collection_id=? ORDER BY provider_resource_id",
                (collection["fetch_collection_id"],),
            ):
                self._thread_child(repo, pr, requirement, job, child_query)
            previous = self.s.one(
                "SELECT has_next FROM current_collection_pages WHERE fetch_collection_id=? ORDER BY ordinal DESC LIMIT 1",
                (collection["fetch_collection_id"],),
            )
            progress = self.s.one(
                "SELECT cursor FROM collection_progress WHERE fetch_collection_id=?",
                (collection["fetch_collection_id"],),
            )
            cursor = (
                json.loads(progress[0])["cursor"] if progress and progress[0] else None
            )
            need_root = previous is None or bool(previous["has_next"])
            seen = set()
            while need_root:
                self.token.check()
                if cursor in seen:
                    raise CatalogError(
                        "PAGINATION_CYCLE", "Repeated root thread cursor"
                    )
                seen.add(cursor)
                response, uncommitted, identified = None, False, False
                base_revision = self.s.revision()
                response = self.http.request(
                    "POST",
                    self.http.graphql,
                    json={
                        "query": root_query,
                        "variables": {
                            "owner": owner,
                            "name": name,
                            "number": pr["provider_change_request_number"],
                            "cursor": cursor,
                            "pageSize": self.cfg["graphql_page_size"],
                        },
                    },
                )
                self._retain_recording_diagnostics(response)
                uncommitted = True
                payload = self.rest_json(response)
                self.graphql_errors(payload, "data", "repository", "pullRequest")
                value = self.graphql_object(
                    payload, "data", "repository", "pullRequest"
                )
                # The response reached the exact PR requested by owner/name/number.
                # A malformed connection is still a real scoped observation;
                # error-only/null resource responses above supply no capture.
                if (
                    "number" in value
                    and value["number"] != pr["provider_change_request_number"]
                ):
                    raise CatalogError(
                        "SCOPE_MISMATCH", "Thread root has a foreign PR parent"
                    )
                identified = True
                nodes, _, next_cursor = self.graphql_connection(
                    value.get("reviewThreads")
                )
                timestamp = self.facts.response_time(response)
                with self.s.transaction():
                    self.facts.fence(job)
                    context = self.facts.current_context(
                        repo, pr["change_request_id"], self.http.graphql
                    )
                    members = []
                    for node in nodes:
                        candidate = current_parser.thread(node, context, timestamp)
                        self.facts.admit_current(candidate, base_revision)
                        members.append(self.member(candidate))
                        thread_id = candidate["provider_resource_id"]
                        _, _, child_cursor = self.graphql_connection(
                            node.get("comments"), refresh_root=True
                        )
                        # A root refresh under the same request needs a new exact
                        # child capture, never an old child's completion.
                        child = self.facts.begin(
                            repo,
                            pr["change_request_id"],
                            "thread-comments",
                            job,
                            self.http.graphql,
                            {
                                "provider_resource_id": thread_id,
                                "parent_fetch_collection_id": collection[
                                    "fetch_collection_id"
                                ],
                                "parent_observed_at_us": timestamp,
                                **target,
                            },
                        )
                        child_members = self._thread_documents(
                            repo,
                            pr,
                            thread_id,
                            node["comments"],
                            child,
                            None,
                            0,
                            timestamp,
                            base_revision=base_revision,
                            refresh_root=True,
                        )
                        self.facts.page(
                            child,
                            timestamp,
                            child_cursor
                            if not payload.get("errors")
                            else child_cursor or "partial-root",
                            child_members,
                            status=response.status_code,
                        )
                        self.s.execute(
                            "INSERT INTO thread_collection_requirements(fetch_collection_id,provider_resource_id,child_fetch_collection_id,required_observed_at_us,object_format,head_oid,base_oid) VALUES(?,?,?,?,?,?,?) ON CONFLICT(fetch_collection_id,provider_resource_id) DO UPDATE SET child_fetch_collection_id=excluded.child_fetch_collection_id,required_observed_at_us=excluded.required_observed_at_us,object_format=excluded.object_format,head_oid=excluded.head_oid,base_oid=excluded.base_oid",
                            (
                                collection["fetch_collection_id"],
                                thread_id,
                                child["fetch_collection_id"],
                                timestamp,
                                target.get("object_format"),
                                bytes.fromhex(target["head_oid"])
                                if target.get("head_oid")
                                else None,
                                bytes.fromhex(target["base_oid"])
                                if target.get("base_oid")
                                else None,
                            ),
                        )
                        self.s.execute(
                            "INSERT INTO thread_collection_continuations(fetch_collection_id,provider_resource_id,child_cursor,observed_at_us) VALUES(?,?,?,?) ON CONFLICT(fetch_collection_id,provider_resource_id) DO UPDATE SET child_cursor=excluded.child_cursor,observed_at_us=excluded.observed_at_us",
                            (
                                collection["fetch_collection_id"],
                                thread_id,
                                child_cursor,
                                timestamp,
                            ),
                        )
                        if (
                            not child_cursor
                            and not payload.get("errors")
                            and not self.current_members_unresolved(
                                child["fetch_collection_id"]
                            )
                        ):
                            self.facts.finish(child)
                    for role, field in (
                        ("merge", "mergeCommit"),
                        ("test-merge", "potentialMergeCommit"),
                    ):
                        if field in value:
                            raw = value[field]
                            oid = (
                                current_parser._oid(raw.get("oid"))
                                if isinstance(raw, dict)
                                else None
                                if raw is None
                                else current_parser._oid(raw)
                            )
                            algorithm = (
                                "sha256"
                                if oid and len(oid) == 64
                                else "sha1"
                                if oid
                                else None
                            )
                            self.s.execute(
                                "INSERT INTO thread_collection_targets(fetch_collection_id,role,object_format,oid,observed_at_us) VALUES(?,?,?,?,?) ON CONFLICT(fetch_collection_id,role) DO UPDATE SET object_format=excluded.object_format,oid=excluded.oid,observed_at_us=excluded.observed_at_us",
                                (
                                    collection["fetch_collection_id"],
                                    role,
                                    algorithm,
                                    bytes.fromhex(oid) if oid else None,
                                    timestamp,
                                ),
                            )
                    saved_cursor = (
                        canonical(
                            {"cursor": cursor if payload.get("errors") else next_cursor}
                        )
                        if payload.get("errors") or next_cursor
                        else None
                    )
                    self.facts.page(
                        collection,
                        timestamp,
                        saved_cursor,
                        members,
                        status=response.status_code,
                    )
                    self.facts.advance_revision()
                uncommitted = False
                if payload.get("errors"):
                    raise CatalogError(
                        "GRAPHQL_PARTIAL",
                        "Accepted root facts are partial; fresh acquisition is required",
                    )
                for requirement in self.s.all(
                    "SELECT * FROM thread_collection_requirements WHERE fetch_collection_id=? ORDER BY provider_resource_id",
                    (collection["fetch_collection_id"],),
                ):
                    self._thread_child(repo, pr, requirement, job, child_query)
                cursor, need_root = next_cursor, next_cursor is not None
            with self.s.transaction():
                self.facts.fence(job)
                if any(
                    self.current_members_unresolved(ident)
                    for ident in self.thread_collection_ids(collection)
                ):
                    raise CatalogError(
                        "CURRENT_STATE_UNRESOLVED",
                        "Thread tree has unresolved current members",
                    )
                self.facts.finish(collection)
                self.coverage_claim(
                    repo["repository_uuidv4"],
                    "threads",
                    "complete",
                    self.facts.thread_observed_at_us(collection, include_partial=False),
                    {
                        "fetch_collection_ids": self.thread_collection_ids(collection),
                        "completion_marker_uuidv4s": [
                            row[0]
                            for row in self.s.all(
                                "SELECT completion_marker_uuidv4 FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='complete'",
                                (collection["fetch_collection_id"],),
                            )
                        ],
                    },
                    change_request_id=pr["change_request_id"],
                )
                self.facts.advance_revision()
            return self.saved_thread_code_input(pr["change_request_id"])[0]
        except CatalogError as error:
            with self.s.transaction():
                self.facts.fence(job)
                self.facts.partial(
                    collection,
                    "GRAPHQL_ROOT_PARTIAL"
                    if error.code == "GRAPHQL_PARTIAL"
                    and isinstance(payload, dict)
                    and payload.get("errors")
                    else error.code,
                    observed_at_us=self.facts.response_time(response)
                    if response is not None
                    and uncommitted
                    and identified
                    and error.code
                    not in ("CANCELLED", "STALE_ATTEMPT", "SCOPE_MISMATCH")
                    else None,
                )
                self.coverage_claim(
                    repo["repository_uuidv4"],
                    "threads",
                    "partial",
                    self.facts.thread_observed_at_us(collection),
                    {
                        "fetch_collection_ids": self.thread_collection_ids(collection),
                        "reason": error.code,
                    },
                    change_request_id=pr["change_request_id"],
                )
                self.facts.advance_revision()
            raise

    def incremental_comments(self, repo, job, kind, endpoint, parent_field):
        parameters = {
            "per_page": self.cfg["rest_page_size"],
            "sort": "updated",
            "direction": "asc",
        }
        fixed_endpoint = endpoint + "?" + urlencode(parameters)
        context = {
            "kind": kind,
            "sort": "updated",
            "direction": "asc",
            "incremental_endpoint": fixed_endpoint,
        }
        url, context = self.current_incremental_url(
            repo, job, kind + "-incremental", fixed_endpoint, context
        )

        def normalize(value, collection, base_revision, position, timestamp, listing):
            parent = value.get(parent_field)
            if not isinstance(parent, str):
                raise CatalogError("API_SCHEMA", "Comment parent missing")
            self.http.validate_url(parent)
            prefix = urlsplit(endpoint).path.rsplit("/", 2)[0]
            parts = urlsplit(parent).path.rsplit("/", 2)
            if (
                len(parts) != 3
                or parts[0] != prefix
                or parts[1] not in ("issues", "pulls")
                or not parts[2].isascii()
                or not parts[2].isdecimal()
            ):
                raise CatalogError(
                    "SCOPE_MISMATCH", "Comment parent outside repository"
                )
            self.rest_integer(int(parts[2]), "comment parent", minimum=1)
            capture = self.facts.current_context(repo, None, endpoint)
            owner = self.s.one(
                "SELECT change_request_id FROM change_requests WHERE repository_binding_id=? AND provider_change_request_number=? AND change_request_kind='pull_request'",
                (capture["repository_binding_id"], int(parts[2])),
            )
            if owner is None:
                raise CatalogError(
                    "COMMENT_PARENT_UNKNOWN", "Comment parent is unavailable"
                )
            capture = self.facts.current_context(repo, owner[0], endpoint)
            candidate = (
                current_parser.review_comment(value, capture, timestamp)
                if kind == "review-comment"
                else current_parser.document(value, capture, timestamp, kind)
            )
            self.facts.admit_current(candidate, base_revision)
            return [self.member(candidate)]

        return self.collection(
            repo, None, kind + "-incremental", job, url, normalize, context=context
        )

    def current_incremental_reviews(self, repo, job, endpoint):
        return self.incremental_comments(
            repo, job, "review-comment", endpoint, "pull_request_url"
        )

    def _current_pr_value(self, ident):
        row = self.s.one(
            "SELECT * FROM eligible_change_request_state WHERE change_request_id=?",
            (ident,),
        )
        if row is None:
            return {}
        metadata = json.loads(row["metadata"])
        return {
            "head": {"sha": row["head_oid"].hex() if row["head_oid"] else None},
            "base": {"sha": row["base_oid"].hex() if row["base_oid"] else None},
            **{
                key: metadata[key]
                for key in ("commits", "changed_files")
                if key in metadata
            },
        }

    def _event(self, repo, pr, value, timestamp):
        from repo_catalog.domain.time import parse_iso8601_us

        modeled = current_parser.timeline_event(value)
        kind = modeled.get("event") or "unknown"
        # Timeline occurrences retain transition meaning. Resource projections
        # such as comment bodies are maintained in their own current stores.
        for field in ("body", "title"):
            modeled.pop(field, None)
        event_id = str(value["id"]) if value.get("id") is not None else None
        prior = (
            self.s.one(
                "SELECT change_request_event_uuidv4,metadata FROM change_request_events WHERE change_request_id=? AND provider_event_id=?",
                (pr, event_id),
            )
            if event_id is not None
            else None
        )
        ident = prior[0] if prior else str(uuid.uuid4())
        if prior and json.loads(prior["metadata"]) != modeled:
            raise CatalogError(
                "EVENT_CONFLICT",
                "Provider event identity has conflicting transition evidence",
            )
        oid = current_parser._oid(modeled.get("commit_id"))
        algorithm = "sha256" if oid and len(oid) == 64 else "sha1" if oid else None
        created = modeled.get("created_at") or modeled.get("submitted_at")
        try:
            created = parse_iso8601_us(created) if created else None
        except (ValueError, TypeError):
            raise CatalogError("API_SCHEMA", "Malformed timeline instant") from None
        actor = (modeled.get("actor") or modeled.get("user") or {}).get("login")
        self.s.execute(
            "INSERT INTO change_request_events(change_request_event_uuidv4,change_request_id,repository_uuidv4,provider_event_id,event_kind,actor,created_at_us,object_format,commit_oid,metadata,observed_at_us,parser_module,parser_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(change_request_event_uuidv4) DO UPDATE SET metadata=excluded.metadata,observed_at_us=excluded.observed_at_us,parser_module=excluded.parser_module,parser_version=excluded.parser_version",
            (
                ident,
                pr,
                repo["repository_uuidv4"],
                event_id,
                kind,
                actor,
                created,
                algorithm,
                bytes.fromhex(oid) if oid else None,
                canonical(modeled),
                timestamp,
                current_parser.PARSER_MODULE,
                current_parser.PARSER_VERSION,
            ),
        )
        return {
            "family": "event",
            "change_request_id": pr,
            "change_request_event_uuidv4": ident,
            "state_digest": hashlib.sha256(canonical(modeled).encode()).hexdigest(),
        }

    def _code_collect(self, repo, pr, job, url, before):
        algorithm, head, base = oid_context(before)
        if algorithm is None or head is None or base is None:
            raise CatalogError(
                "PR_CODE_TARGETS_INCOMPLETE", "PR comparison target is unknown"
            )
        context = {"head": {"sha": head.hex()}, "base": {"sha": base.hex()}}

        def commit(value, collection, base_revision, position, timestamp, listing):
            from repo_catalog.domain.models import GitOid

            oid = GitOid.parse(algorithm + ":" + value["sha"]).value
            metadata = current_parser.code_commit_metadata(value)
            self.s.execute(
                "INSERT INTO code_commits(code_listing_id,position,repository_uuidv4,object_format,oid,metadata) VALUES(?,?,?,?,?,?)",
                (
                    listing,
                    position,
                    repo["repository_uuidv4"],
                    algorithm,
                    oid,
                    canonical(metadata),
                ),
            )
            return [
                {
                    "family": "code-commit",
                    "code_listing_id": listing,
                    "position": position,
                    "state_digest": hashlib.sha256(
                        canonical({"oid": oid.hex(), "metadata": metadata}).encode()
                    ).hexdigest(),
                }
            ]

        def file_item(value, collection, base_revision, position, timestamp, listing):
            path = value.get("filename")
            if not isinstance(path, str):
                raise CatalogError("API_SCHEMA", "PR file path missing")
            previous = value.get("previous_filename")
            if previous is not None and not isinstance(previous, str):
                raise CatalogError("API_SCHEMA", "PR previous path malformed")
            oid = current_parser._oid(value.get("sha"))
            file_format = (
                "sha256" if oid and len(oid) == 64 else "sha1" if oid else None
            )
            metadata = {
                field: value[field]
                for field in ("blob_url", "raw_url", "contents_url")
                if field in value
            }
            self.s.execute(
                "INSERT INTO code_file_changes(code_listing_id,position,repository_uuidv4,raw_path,previous_path,status,object_format,oid,additions,deletions,changes,patch,patch_status,metadata) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    listing,
                    position,
                    repo["repository_uuidv4"],
                    path.encode("utf-8"),
                    previous.encode("utf-8") if previous else None,
                    value.get("status"),
                    file_format,
                    bytes.fromhex(oid) if oid else None,
                    value.get("additions"),
                    value.get("deletions"),
                    value.get("changes"),
                    value.get("patch"),
                    "present"
                    if "patch" in value and value["patch"] is not None
                    else "provider-null"
                    if "patch" in value
                    else "missing",
                    canonical(metadata),
                ),
            )
            projected = current_parser.code_file_metadata(value)
            return [
                {
                    "family": "code-file",
                    "code_listing_id": listing,
                    "position": position,
                    "state_digest": hashlib.sha256(
                        canonical({"path": path, "metadata": projected}).encode()
                    ).hexdigest(),
                }
            ]

        commits = self.collection(
            repo,
            pr["change_request_id"],
            "pr-commits",
            job,
            url + f"/commits?per_page={self.cfg['rest_page_size']}",
            commit,
            context=context,
            listing_kind="commits",
            cap=250,
            reported=before.get("commits"),
            reuse=True,
        )
        files_result = self.collection(
            repo,
            pr["change_request_id"],
            "pr-files",
            job,
            url + f"/files?per_page={self.cfg['rest_page_size']}",
            file_item,
            context=context,
            listing_kind="files",
            cap=3000,
            reported=before.get("changed_files"),
            reuse=True,
        )
        return commits, files_result

    def _assess_code(
        self, repo, pr, job, before, after, listings, inputs_complete, missing
    ):
        from repo_catalog.adapters.git.importer import GitImporter

        algorithm, head, base = oid_context(before)
        if algorithm is None or head is None or base is None:
            return None
        scope = self.facts.current_context(
            repo, pr["change_request_id"], self.http.base
        )["acquisition_scope"]
        assessment = (
            "code:"
            + hashlib.sha256(
                canonical(
                    {
                        "pr": pr["change_request_id"],
                        "format": algorithm,
                        "head": head.hex(),
                        "base": base.hex(),
                        "scope": scope,
                    }
                ).encode()
            ).hexdigest()
        )
        commit_listing = listings[0][1] if listings else None
        file_listing = listings[1][1] if listings else None
        actual = self.s.one(
            "SELECT head_oid,base_oid FROM eligible_change_request_state WHERE change_request_id=?",
            (pr["change_request_id"],),
        )
        same = (
            bool(after)
            and all(
                (before.get(role) or {}).get("sha")
                == (after.get(role) or {}).get("sha")
                for role in ("head", "base")
            )
            and actual is not None
            and actual["head_oid"] == head
            and actual["base_oid"] == base
        )
        previous = self.s.one(
            "SELECT * FROM code_assessments WHERE code_assessment_id=?", (assessment,)
        )
        relevant_kinds = {
            "pr-detail",
            "pr-code-check",
            "review",
            "review-comment",
            "threads",
            "thread-comments",
            "pr-commits",
            "pr-files",
        }
        newly_partial = any(
            repository == repo["repository_uuidv4"]
            and owner == pr["change_request_id"]
            and kind in relevant_kinds
            for repository, owner, kind in self.observed_partial_scopes
        )
        if (
            previous
            and after is None
            and actual is not None
            and actual["head_oid"] == head
            and actual["base_oid"] == base
            and not newly_partial
        ):
            return assessment
        # A completed older prefix cannot discharge a newer observed gap.
        # Required scoped input coverage uses its latest candidate set.
        inputs_complete = inputs_complete and all(
            (
                row := self.s.one(
                    "SELECT coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind=?",
                    (repo["repository_uuidv4"], pr["change_request_id"], kind),
                )
            )
            is not None
            and row["coverage_state"] == "complete"
            for kind in (
                "review",
                "review-comment",
                "threads",
                "pr-commits",
                "pr-files",
            )
        )
        for kind in ("pr-detail", "pr-code-check"):
            captures = self.s.one(
                "SELECT MAX(m.observed_at_us) observed, MAX(CASE WHEN m.asserted_state='complete' THEN m.observed_at_us END) completed FROM completion_markers m JOIN fetch_collections f USING(fetch_collection_id) JOIN collection_progress p USING(fetch_collection_id) WHERE f.repository_uuidv4=? AND f.change_request_id=? AND p.job_id=? AND f.kind=?",
                (repo["repository_uuidv4"], pr["change_request_id"], job, kind),
            )
            inputs_complete = (
                inputs_complete
                and captures["completed"] is not None
                and captures["completed"] == captures["observed"]
            )
        roles, roles_complete, _ = self.saved_thread_code_input(pr["change_request_id"])
        role_oids = {"head": head.hex(), "base": base.hex(), **roles}
        for row in self.s.all(
            "SELECT target_commit_oid FROM eligible_review_resources WHERE change_request_id=?",
            (pr["change_request_id"],),
        ):
            if row[0]:
                oid = row[0] if isinstance(row[0], str) else row[0].hex()
                role_oids["review-target:" + oid] = oid
        observed = self.s.one(
            "SELECT MAX(o.observed_at_us) FROM (SELECT fetch_collection_id,observed_at_us FROM current_collection_pages UNION ALL SELECT fetch_collection_id,observed_at_us FROM completion_markers WHERE asserted_state='partial') o JOIN fetch_collections f USING(fetch_collection_id) JOIN collection_progress p USING(fetch_collection_id) WHERE f.repository_uuidv4=? AND f.change_request_id=? AND f.source_id=? AND p.job_id=? AND f.kind IN ("
            + ",".join("?" for _ in relevant_kinds)
            + ")",
            (
                repo["repository_uuidv4"],
                pr["change_request_id"],
                repo["source_id"],
                job,
                *sorted(relevant_kinds),
            ),
        )[0]
        with self.s.transaction():
            self.facts.fence(job)
            self.s.execute(
                "INSERT INTO code_assessments(code_assessment_id,change_request_id,repository_uuidv4,commit_code_listing_id,file_code_listing_id,state,object_format,head_oid,base_oid,observed_at_us,parser_module,parser_version,details_json) VALUES(?,?,?,?,?,'partial',?,?,?,?,?,?,?) ON CONFLICT(code_assessment_id) DO UPDATE SET commit_code_listing_id=excluded.commit_code_listing_id,file_code_listing_id=excluded.file_code_listing_id,state='partial',observed_at_us=excluded.observed_at_us,details_json=excluded.details_json",
                (
                    assessment,
                    pr["change_request_id"],
                    repo["repository_uuidv4"],
                    commit_listing,
                    file_listing,
                    algorithm,
                    head,
                    base,
                    observed,
                    current_parser.PARSER_MODULE,
                    current_parser.PARSER_VERSION,
                    canonical(
                        {
                            "race": not same,
                            "code_inputs_complete": bool(
                                inputs_complete and roles_complete
                            ),
                        }
                    ),
                ),
            )
            self.facts.advance_revision()
        links = {}
        for role, expected in role_oids.items():
            if expected is None:
                continue
            try:
                GitImporter(self.s, self.token).sync(
                    repo,
                    job,
                    pr_roots=[
                        {
                            "ref": f"refs/pull/{pr['provider_change_request_number']}/head"
                            if role == "head"
                            else expected,
                            "expected": expected,
                            "role": role,
                            "number": pr["provider_change_request_number"],
                        }
                    ],
                    code_assessment_id=assessment,
                    repository_endpoint_id=self.repository_endpoint_id,
                )
            except CatalogError as error:
                if error.code in ("CANCELLED", "STALE_ATTEMPT"):
                    raise
                missing.append({"kind": "pr-git", "reason": error.code, "role": role})
            requested_format = "sha256" if len(expected) == 64 else "sha1"
            row = self.s.one(
                "SELECT r.acquisition_root_id FROM acquisition_roots r JOIN git_objects o ON o.object_format=r.object_format AND o.oid=r.oid WHERE r.repository_uuidv4=? AND r.object_format=? AND r.oid=? AND r.complete=1 AND o.type='commit' AND o.verified=1 AND r.role=? ORDER BY r.acquisition_root_id DESC LIMIT 1",
                (
                    repo["repository_uuidv4"],
                    requested_format,
                    bytes.fromhex(expected),
                    role,
                ),
            )
            if row:
                links[role] = row[0]
        required = {role for role, oid in role_oids.items() if oid is not None}
        state = (
            "complete"
            if same
            and inputs_complete
            and roles_complete
            and listings
            and required <= links.keys()
            and not any(failure["reason"] == "PR_CODE_RACE" for failure in missing)
            else "partial"
        )
        if not same:
            missing.append({"kind": "pr-code", "reason": "PR_CODE_RACE"})
        if required - links.keys():
            missing.append(
                {
                    "kind": "pr-code",
                    "reason": "MISSING_CODE_ACQUISITION",
                    "roles": sorted(required - links.keys()),
                }
            )
        with self.s.transaction():
            self.facts.fence(job)
            self.s.execute(
                "UPDATE code_assessments SET state=?,details_json=? WHERE code_assessment_id=?",
                (
                    state,
                    canonical(
                        {
                            "race": not same,
                            "code_inputs_complete": bool(
                                inputs_complete and roles_complete
                            ),
                            "missing": missing,
                        }
                    ),
                    assessment,
                ),
            )
            for role, oid in role_oids.items():
                if oid is not None:
                    self.s.execute(
                        "INSERT INTO code_acquisitions(code_assessment_id,role,object_format,oid,acquisition_root_id) VALUES(?,?,?,?,?) ON CONFLICT(code_assessment_id,role) DO UPDATE SET acquisition_root_id=excluded.acquisition_root_id",
                        (
                            assessment,
                            role,
                            "sha256" if len(oid) == 64 else "sha1",
                            bytes.fromhex(oid),
                            links.get(role),
                        ),
                    )
            code_collections = [
                row[0]
                for row in self.s.all(
                    "SELECT f.fetch_collection_id FROM fetch_collections f JOIN collection_progress p USING(fetch_collection_id) WHERE f.repository_uuidv4=? AND f.change_request_id=? AND p.job_id=? AND f.kind IN ("
                    + ",".join("?" for _ in relevant_kinds)
                    + ")",
                    (
                        repo["repository_uuidv4"],
                        pr["change_request_id"],
                        job,
                        *sorted(relevant_kinds),
                    ),
                )
            ]
            if listings:
                code_collections.extend(
                    item[0] for item in listings if item is not None
                )
            code_collections = sorted(set(code_collections))
            marker_ids = (
                [
                    row[0]
                    for row in self.s.all(
                        "SELECT completion_marker_uuidv4 FROM completion_markers WHERE asserted_state='complete' AND fetch_collection_id IN ("
                        + ",".join("?" for _ in code_collections)
                        + ") ORDER BY completion_marker_uuidv4",
                        code_collections,
                    )
                ]
                if code_collections
                else []
            )
            self.coverage_claim(
                repo["repository_uuidv4"],
                "pr-code",
                state,
                observed,
                {
                    "code_assessment_ids": [assessment],
                    "fetch_collection_ids": code_collections,
                    "completion_marker_uuidv4s": marker_ids,
                    "missing": missing,
                },
                change_request_id=pr["change_request_id"],
            )
            self.facts.advance_revision()
        return assessment

    def sync(self, repo, job):
        root = f"{self.http.base}/repos/{repo['name']}"
        failures, waiting = [], None
        assessments = []
        self.observed_partial_scopes.clear()
        self.thread_collections.clear()

        def attempt(kind, operation):
            nonlocal waiting
            if (
                waiting is not None
                and waiting > self.http.clock_us()
                and kind != "pr-git"
            ):
                failures.append({"kind": kind, "reason": "RATE_LIMIT_WAIT"})
                return None
            try:
                return operation()
            except CatalogError as error:
                if error.code in ("CANCELLED", "STALE_ATTEMPT"):
                    raise
                failures.append({"kind": kind, "reason": error.code})
                waiting = error.details.get("not_before_us", waiting)
                return None

        try:
            response = self.http.request("GET", self.http.base + "/user")
            self._retain_recording_diagnostics(response)
            identity = self.rest_json(response)
            principal = identity.get("id") or identity.get("login")
            if not principal:
                raise CatalogError("API_SCHEMA", "Principal identity missing")
            self.facts.principal = str(principal)
            permissions = response.headers.get("x-oauth-scopes")
            self.facts.permissions = (
                sorted(item.strip() for item in permissions.split(",") if item.strip())
                if permissions is not None
                else None
            )
            size = self.cfg["rest_page_size"]

            def pr_item(value, collection, base_revision, position, timestamp, listing):
                return self.ensure_pr(
                    repo, value, collection, base_revision, position, timestamp
                )[1]

            pr_listing = attempt(
                "pr-list",
                lambda: self.collection(
                    repo,
                    None,
                    "pr-list",
                    job,
                    root
                    + f"/pulls?state=all&sort=created&direction=asc&per_page={size}",
                    pr_item,
                ),
            )
            attempt(
                "issue-comment-incremental",
                lambda: self.incremental_comments(
                    repo, job, "issue-comment", root + "/issues/comments", "issue_url"
                ),
            )
            attempt(
                "review-comment-incremental",
                lambda: self.current_incremental_reviews(
                    repo, job, root + "/pulls/comments"
                ),
            )
            binding = self.facts.current_context(repo, None, root)[
                "repository_binding_id"
            ]
            prs = self.s.all(
                "SELECT * FROM change_requests WHERE repository_binding_id=? AND change_request_kind='pull_request' ORDER BY provider_change_request_number",
                (binding,),
            )
            for pr in prs:
                self.token.check()
                start = len(failures)
                url = root + f"/pulls/{pr['provider_change_request_number']}"
                detailed = attempt("pr-detail", lambda: self.detail(repo, pr, job, url))
                before = (
                    detailed[0]
                    if detailed
                    else self._current_pr_value(pr["change_request_id"])
                )
                for kind, endpoint in (
                    (
                        "issue-comment",
                        root
                        + f"/issues/{pr['provider_change_request_number']}/comments",
                    ),
                    ("review", url + "/reviews"),
                    ("review-comment", url + "/comments"),
                ):
                    endpoint += f"?per_page={size}"
                    attempt(
                        kind,
                        lambda kind=kind, endpoint=endpoint: (
                            self.collection(
                                repo,
                                pr["change_request_id"],
                                kind,
                                job,
                                endpoint,
                                self._document_normalizer(
                                    repo, pr["change_request_id"], kind, endpoint
                                ),
                            )
                            if kind == "issue-comment"
                            else self.current_collection(
                                repo,
                                pr["change_request_id"],
                                kind,
                                job,
                                endpoint,
                                current_parser.review
                                if kind == "review"
                                else current_parser.review_comment,
                            )
                        ),
                    )

                def event(
                    value, collection, base_revision, position, timestamp, listing
                ):
                    return [
                        self._event(repo, pr["change_request_id"], value, timestamp)
                    ]

                attempt(
                    "timeline",
                    lambda: self.collection(
                        repo,
                        pr["change_request_id"],
                        "timeline",
                        job,
                        root
                        + f"/issues/{pr['provider_change_request_number']}/timeline?per_page={size}",
                        event,
                    ),
                )
                thread_result = attempt("threads", lambda: self.threads(repo, pr, job))
                listings = attempt(
                    "pr-code-listings",
                    lambda: self._code_collect(repo, pr, job, url, before),
                )
                checked = attempt(
                    "pr-code-check", lambda: self.code_check(repo, pr, job, url)
                )
                current_failures = failures[start:]
                assessment = self._assess_code(
                    repo,
                    pr,
                    job,
                    before,
                    checked,
                    listings,
                    detailed is not None
                    and thread_result is not None
                    and not any(
                        failure["kind"] in ("review", "review-comment", "threads")
                        for failure in current_failures
                    ),
                    current_failures,
                )
                assessments.append(assessment)
                failures[start:] = current_failures
            code_complete = (
                pr_listing is not None
                and len(assessments) == len(prs)
                and all(
                    assessment is not None
                    and self.s.one(
                        "SELECT state FROM code_assessments WHERE code_assessment_id=?",
                        (assessment,),
                    )[0]
                    == "complete"
                    for assessment in assessments
                )
            )
            with self.s.transaction():
                self.facts.fence(job)
                document_failures = [
                    failure
                    for failure in failures
                    if failure["kind"]
                    not in ("pr-git", "pr-code-listings", "pr-code-check", "pr-code")
                ]
                for kind, documents_only in (
                    ("pr-documents", True),
                    ("pr", True),
                    ("pr-code", False),
                ):
                    summary_failures = (
                        document_failures if kind == "pr-documents" else failures
                    )
                    self.coverage_claim(
                        repo["repository_uuidv4"],
                        kind,
                        ("complete" if code_complete else "partial")
                        if kind == "pr-code"
                        else "partial"
                        if summary_failures
                        else "complete",
                        self.summary_observed_at_us(
                            repo,
                            job,
                            documents_only=documents_only,
                            include_partial=bool(summary_failures),
                        ),
                        {
                            "fetch_collection_ids": self.summary_collection_ids(
                                repo, job, documents_only=documents_only
                            ),
                            "completion_marker_uuidv4s": self.summary_marker_ids(
                                repo, job, documents_only=documents_only
                            ),
                            "missing": summary_failures,
                        },
                    )
                self.facts.advance_revision()
            if failures:
                raise Waiting(
                    "PR_PARTIAL",
                    "Some PR collections are incomplete",
                    {
                        "missing": failures,
                        **({"not_before_us": waiting} if waiting is not None else {}),
                    },
                    True,
                )
            return {
                "repository_uuidv4": repo["repository_uuidv4"],
                "state": "complete",
                "change_requests": len(prs),
                **(
                    {"recording_diagnostics": self.recording_diagnostics}
                    if self.recording_diagnostics
                    else {}
                ),
            }
        finally:
            if self.owned:
                self.http.close()

    def code_check(self, repo, pr, job, url, observation=None):
        target = self._current_pr_value(pr["change_request_id"])
        with self.s.transaction():
            self.facts.fence(job)
            collection = self.facts.begin(
                repo,
                pr["change_request_id"],
                "pr-code-check",
                job,
                url,
                {"head": target.get("head"), "base": target.get("base")},
            )
        if collection["state"] == "complete":
            return target
        base_revision = self.s.revision()
        response = self.request_get(url, repo)
        value = None
        try:
            value = self.rest_json(response)
            timestamp = self.facts.response_time(response)
            with self.s.transaction():
                self.facts.fence(job)
                _, members = self.ensure_pr(
                    repo, value, collection, base_revision, 0, timestamp
                )
                self.facts.page(
                    collection, timestamp, None, members, status=response.status_code
                )
                if self.current_members_unresolved(collection["fetch_collection_id"]):
                    raise CatalogError(
                        "CURRENT_STATE_UNRESOLVED",
                        "Code target check has unresolved current fields",
                    )
                self.facts.finish(collection)
                self.facts.advance_revision()
            return value
        except CatalogError as error:
            self.partial_rest_collection(
                repo,
                pr["change_request_id"],
                "pr-code-check",
                job,
                collection,
                error,
                response
                if isinstance(value, dict) and value.get("id") is not None
                else None,
                url,
            )
            raise
