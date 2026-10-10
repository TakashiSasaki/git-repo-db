from __future__ import annotations

import json
import uuid
from importlib.resources import files
from urllib.parse import urlencode, urljoin, urlsplit

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.identity import database_resource_id
from repo_catalog.adapters.github.persistence import (
    PARSER,
    ApiFacts,
    canonical,
    oid_context,
)
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.sqlite.cas_integrity import diagnose_admission_failure
from repo_catalog.domain.models import CatalogError, Waiting
from repo_catalog.domain.payload import PayloadRef
from repo_catalog.domain.pr_scope import NON_DOCUMENT_KINDS, document_scope_includes
from repo_catalog.domain.time import format_iso8601_us, now_us


class GitHubCollector:
    """Explicit acquisition into ordinary catalog3 facts; no legacy write model."""

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

    def current_incremental_url(self, repo, job, kind, endpoint, context):
        """Freeze a bounded overlapping update scan and resume its original URL."""
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        matches = self.s.all(
            "SELECT f.fetch_collection_id,f.observed_at_us,r.endpoint,r.request_context,p.job_id,p.state,c.completion_marker_uuidv4,c.asserted_state,c.evidence,c.observed_at_us marker_observed_at_us "
            "FROM fetch_collections f JOIN resume_scopes r USING(resume_scope_id) JOIN collection_progress p USING(fetch_collection_id) "
            "LEFT JOIN completion_markers c USING(fetch_collection_id) "
            "WHERE f.repository_uuidv4=? AND f.kind=? AND r.source_id=? AND r.principal_ref IS ? AND r.api_version=? AND r.parser_version=? AND r.profile_version=? "
            "AND json_extract(r.request_context,'$.incremental_endpoint')=? ORDER BY f.observed_at_us DESC",
            (
                repo["repository_uuidv4"],
                kind,
                repo["source_id"],
                self.facts.principal,
                self.cfg["rest_api_version"],
                PARSER,
                self.s.config["preservation"]["profile"],
                endpoint,
            ),
        )
        for row in matches:
            saved_context = json.loads(row["request_context"])
            if saved_context.get("permissions") != self.facts.permissions:
                continue
            if row["job_id"] == job:
                return row["endpoint"], saved_context
        proof = CurrentCollectionProof(self.s.connection)
        for row in matches:
            if (
                json.loads(row["request_context"]).get("permissions")
                != self.facts.permissions
            ):
                continue
            if row["state"] != "complete" or row["asserted_state"] != "complete":
                continue
            if any(
                (page["parser_module"], page["parser_version"])
                != (current_parser.PARSER_MODULE, current_parser.PARSER_VERSION)
                for page in proof.pages(row["fetch_collection_id"])
            ):
                continue
            marker = {**dict(row), "observed_at_us": row["marker_observed_at_us"]}
            if proof.is_complete_marker(marker):
                return endpoint + "&" + urlencode(
                    {"since": format_iso8601_us(row["observed_at_us"] - 300_000_000)}
                ), {
                    **context,
                    "completion_marker_uuidv4": row["completion_marker_uuidv4"],
                }
        return endpoint, context

    def current_collection(self, repo, pr, kind, job, url, parser, *, context=None):
        """Admit mutable pages with durable bounds/members and no HTTP CAS input."""
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )
        from repo_catalog.domain.current_state import fingerprint_candidate

        s = self.s
        proof = CurrentCollectionProof(s.connection)
        with s.transaction():
            self.facts.fence(job)
            collection = self.facts.begin(repo, pr, kind, job, url, context)
            candidate_context = self.facts.current_context(
                repo, pr, url, kind.replace("-incremental", "")
            )
        if collection["state"] == "complete":
            return collection["fetch_collection_id"], None
        previous = s.one(
            "SELECT ordinal,next_cursor FROM current_collection_pages WHERE fetch_collection_id=? ORDER BY ordinal DESC LIMIT 1",
            (collection["fetch_collection_id"],),
        )
        ordinal = previous["ordinal"] + 1 if previous else 0
        page_url = previous["next_cursor"] if previous else url
        seen = set()
        try:
            while page_url:
                self.token.check()
                if page_url in seen:
                    raise CatalogError(
                        "PAGINATION_CYCLE", "Repeated current resource page"
                    )
                seen.add(page_url)
                base_revision = s.revision()
                response = self.request_get(
                    page_url,
                    repo,
                    record_context={
                        "provider_request_kind": kind,
                        "repository": repo["name"],
                        "collection_scope": canonical(
                            candidate_context["acquisition_scope"]
                        ),
                        "service_instance_uuidv4": candidate_context[
                            "service_instance_uuidv4"
                        ],
                    },
                )
                timestamp = response.extensions.get("catalog_observed_at_us", now_us())
                values = self.rest_json(response)
                if not isinstance(values, list):
                    raise CatalogError(
                        "API_SCHEMA", "Current collection response must be a list"
                    )
                next_url = self.http.next_url(response)
                from repo_catalog.adapters.git.runner import hook

                hook("before_api_page_commit")
                with s.transaction():
                    self.facts.fence(job)
                    members = []
                    for value in values:
                        self.rest_item(value, kind)
                        candidate = parser(value, candidate_context, timestamp)
                        if candidate is None:
                            continue
                        self.facts.admit_current(candidate, base_revision)
                        issue_family = candidate["kind"] in ("issue", "issue-comment")
                        key_fields = (
                            ("service_instance_uuidv4", "provider_resource_id")
                            if issue_family
                            else (
                                "change_request_id",
                                "provider_change_request_document_id",
                            )
                        )
                        members.append(
                            {
                                "family": "issue" if issue_family else "review",
                                "kind": candidate["kind"],
                                **{field: candidate[field] for field in key_fields},
                                "state_digest": fingerprint_candidate(candidate),
                            }
                        )
                    proof.page(
                        collection["fetch_collection_id"],
                        ordinal,
                        timestamp,
                        next_url,
                        members,
                        status=response.status_code,
                        parser_module=current_parser.PARSER_MODULE,
                        parser_version=current_parser.PARSER_VERSION,
                    )
                    s.execute(
                        "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                        (next_url, collection["fetch_collection_id"]),
                    )
                    self.facts.publish()
                hook("after_api_page_commit")
                ordinal += 1
                page_url = next_url
            with s.transaction():
                self.facts.fence(job)
                # A resumed terminal receipt must still account for unresolved
                # members saved by the earlier attempt; local control flow is
                # never completeness evidence.
                if self.current_members_unresolved(collection["fetch_collection_id"]):
                    raise CatalogError(
                        "CURRENT_STATE_UNRESOLVED",
                        "Current collection contains unordered or unresolved resources",
                    )
                evidence = proof.evidence(collection["fetch_collection_id"])
                self.facts.finish(collection, evidence=evidence)
                self.collection_coverage(repo, pr, kind, collection, "complete")
                self.facts.publish()
            return collection["fetch_collection_id"], None
        except CatalogError as error:
            with s.transaction():
                self.facts.fence(job)
                self.facts.partial(collection, error.code)
                self.collection_coverage(
                    repo, pr, kind, collection, "partial", reason=error.code
                )
                self.facts.publish()
            raise

    def current_members_unresolved(self, collection_id):
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        for member in CurrentCollectionProof(self.s.connection).members(collection_id):
            if member["family"] == "issue":
                table, keys = (
                    "issue_resources",
                    ("service_instance_uuidv4", "kind", "provider_resource_id"),
                )
            else:
                table, keys = (
                    "review_resources",
                    (
                        "change_request_id",
                        "kind",
                        "provider_change_request_document_id",
                    ),
                )
            predicate = " AND ".join(f"{field}=?" for field in keys)
            if (
                self.s.one(
                    f"SELECT 1 FROM {table} WHERE {predicate}",
                    tuple(member[field] for field in keys),
                )
                is None
            ):
                return True
            diagnostics = " AND ".join(
                f"json_extract(record_json,'$.{field}')=?" for field in keys
            )
            if self.s.one(
                "SELECT 1 FROM current_resource_diagnostics WHERE table_name=? AND "
                + diagnostics,
                (table, *(member[field] for field in keys)),
            ):
                return True
        return False

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
                **({"reason": reason} if reason else {}),
            },
            change_request_id=pr,
        )

    def summary_collection_ids(self, repo, job, *, documents_only=False):
        """The exact collections assessed by this job's repository summary."""
        collections = {
            row[0]
            for row in self.s.all(
                "SELECT DISTINCT f.fetch_collection_id FROM fetch_collections f "
                "JOIN collection_progress p USING(fetch_collection_id) "
                "WHERE f.repository_uuidv4=? AND f.source_id=? AND p.job_id=?"
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
        }
        if not documents_only:
            # Reused sealed code listings retain their original acquisition
            # identity and collection. The assessment names those exact roots,
            # rather than treating the later job's pages as their replacement.
            collections.update(
                row[0]
                for row in self.s.all(
                    "SELECT DISTINCT l.fetch_collection_id FROM current_code_observations o JOIN code_listings l ON l.code_listing_id IN (o.commit_code_listing_id,o.file_code_listing_id) WHERE o.repository_uuidv4=? AND o.state='complete'",
                    (repo["repository_uuidv4"],),
                )
            )
        return sorted(collections)

    def thread_collection_ids(self, collection):
        """Include the root and its exact children across interrupted resumes."""
        return [
            row[0]
            for row in self.s.all(
                """SELECT member.fetch_collection_id
                   FROM fetch_collections root JOIN fetch_collections member
                     ON member.repository_uuidv4=root.repository_uuidv4
                    AND member.change_request_id IS root.change_request_id
                    AND member.source_id IS root.source_id
                   JOIN resume_scopes scope ON scope.resume_scope_id=member.resume_scope_id
                   WHERE root.fetch_collection_id=? AND (
                       member.fetch_collection_id=root.fetch_collection_id OR
                       (member.kind='thread-comments' AND
                        json_extract(scope.request_context,'$.parent_fetch_collection_id')
                            =root.fetch_collection_id))
                   ORDER BY member.fetch_collection_id""",
                (collection["fetch_collection_id"],),
            )
        ]

    def summary_observed_at_us(
        self, repo, job, *, documents_only=False, include_partial=True
    ):
        return self.s.one(
            "SELECT MAX(o.observed_at_us) FROM (SELECT fetch_collection_id,observed_at_us FROM fetch_occurrences UNION ALL SELECT fetch_collection_id,observed_at_us FROM current_collection_pages UNION ALL SELECT fetch_collection_id,observed_at_us FROM completion_markers WHERE asserted_state='partial' AND ?) o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id WHERE f.repository_uuidv4=? AND f.source_id=? AND p.job_id=?"
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
            identity = self.http.request(
                "GET", self.http.base + "/repos/" + name
            ).json()
            if str(identity.get("id")) != repo["provider_repository_id"]:
                raise CatalogError(
                    "SCOPE_MISMATCH", "Redirect changed repository identity"
                )
            from repo_catalog.application.repository_identity import observe_name

            with self.s.transaction():
                observe_name(
                    self.s,
                    repo["repository_uuidv4"],
                    name,
                    now_us(),
                    provenance={"kind": "verified-api-redirect", "url": target},
                )
                self.facts.publish()
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

    def inventory_input(self, response, url):
        """Retain accepted live inventory proof, after endpoint validation."""
        next_url = self.http.next_url(response)
        try:
            with self.s.transaction():
                input_uuid, observed, payload_ref = self.facts.source_input(
                    self.inventory_source_registration_uuidv4,
                    response,
                    {
                        "url": url,
                        "method": "GET",
                        "etag": response.headers.get("etag"),
                        "source_settings": self.inventory_source_settings,
                    },
                )
        except CatalogError as error:
            diagnose_admission_failure(self.s.connection, error)
            raise
        self.inventory_evidence.append(
            {
                "source_input_uuidv4": input_uuid,
                "payload": payload_ref.as_json(),
                "url": url,
                "method": "GET",
                "observed_at_us": observed,
                "etag": response.headers.get("etag"),
                "next_url": next_url,
            }
        )

    def inventory(self, source, job):
        cfg = json.loads(source["settings"])
        self.inventory_source_registration_uuidv4 = source["source_registration_uuidv4"]
        self.inventory_source_settings = cfg
        owner = cfg["owner"]
        base = self.http.base
        try:
            response, identity = self.inventory_request("GET", base + "/user")
            if (
                not isinstance(identity, dict)
                or not isinstance(identity.get("login"), str)
                or not identity["login"].strip()
            ):
                raise CatalogError("API_SCHEMA", "Authenticated user identity missing")
            self.inventory_input(response, base + "/user")
            if cfg.get("include_repositories"):
                import re

                selected = []
                for repository in cfg["include_repositories"]:
                    name = repository.removeprefix(owner + "/")
                    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                        raise CatalogError(
                            "INVALID_ARGUMENT",
                            "Included repository must be a name within declared owner",
                        )
                    url = base + "/repos/" + owner + "/" + name
                    response, payload = self.inventory_request("GET", url)
                    if not isinstance(payload, dict) or not isinstance(
                        payload.get("full_name"), str
                    ):
                        raise CatalogError("API_SCHEMA", "Repository identity missing")
                    if (
                        payload.get("full_name", "").lower()
                        != f"{owner}/{name}".lower()
                    ):
                        raise CatalogError(
                            "SCOPE_MISMATCH", "Selected repository identity changed"
                        )
                    if not isinstance(payload.get("clone_url"), str):
                        raise CatalogError(
                            "API_SCHEMA", "Repository identity or clone URL missing"
                        )
                    provider = self.inventory_repository_id(payload.get("id"))
                    self.inventory_input(response, url)
                    selected.append(
                        {
                            "host": "github.com",
                            "provider_repository_id": provider,
                            "name": payload["full_name"],
                            "url": cfg.get("clone_url_overrides", {}).get(
                                provider, payload["clone_url"]
                            ),
                            "metadata": payload,
                        }
                    )
                return selected
            if identity.get("login", "").lower() == owner.lower():
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
                url = base + "/users/" + owner
                response, user = self.inventory_request("GET", url)
                if not isinstance(user, dict) or not isinstance(user.get("type"), str):
                    raise CatalogError("API_SCHEMA", "Owner identity missing")
                if user.get("type") == "Organization":
                    self.inventory_input(response, url)
                    url = (
                        base
                        + "/orgs/"
                        + owner
                        + "/repos?"
                        + urlencode(
                            {
                                "per_page": self.cfg["rest_page_size"],
                                "type": "all",
                            }
                        )
                    )
                else:
                    raise CatalogError(
                        "SCOPE_UNSUPPORTED",
                        "Owner is not the authenticated user; private owner inventory is not established",
                    )
            result = []
            seen = set()
            while url:
                if url in seen:
                    raise CatalogError("PAGINATION_CYCLE", "Repeated inventory page")
                seen.add(url)
                response, values = self.inventory_request("GET", url)
                if not isinstance(values, list):
                    raise CatalogError("API_SCHEMA", "Expected repository list")
                for r in values:
                    if not isinstance(r, dict) or not isinstance(
                        r.get("full_name"), str
                    ):
                        raise CatalogError("API_SCHEMA", "Repository identity missing")
                    provider = self.inventory_repository_id(r.get("id"))
                    if r["full_name"].split("/")[0].lower() != owner.lower():
                        raise CatalogError(
                            "SCOPE_MISMATCH",
                            "Inventory returned repository outside owner scope",
                        )
                    clone = cfg.get("clone_url_overrides", {}).get(
                        provider, r.get("clone_url")
                    )
                    if not isinstance(clone, str) or not clone:
                        raise CatalogError("API_SCHEMA", "Clone URL missing")
                    result.append(
                        {
                            "host": "github.com",
                            "provider_repository_id": provider,
                            "name": r["full_name"],
                            "url": clone,
                            "metadata": r,
                        }
                    )
                self.inventory_input(response, url)
                url = self.http.next_url(response)
            by_id = {repo["provider_repository_id"]: repo for repo in result}
            result = list(by_id.values())
            counts = (identity.get("public_repos"), identity.get("owned_private_repos"))
            if (
                identity.get("login", "").lower() != owner.lower()
                or not all(type(value) is int and value >= 0 for value in counts)
                or any(
                    type(repo["metadata"].get("private")) is not bool for repo in result
                )
            ):
                self.inventory_uncertainty = "INVENTORY_SCOPE_UNVERIFIED"
            elif counts != (
                sum(not repo["metadata"]["private"] for repo in result),
                sum(repo["metadata"]["private"] for repo in result),
            ):
                self.inventory_uncertainty = "INVENTORY_COUNT_MISMATCH"
            return result
        finally:
            if self.owned:
                self.http.close()

    def inventory_result(self, source):
        """Create the source-owned parse execution; caller adds inventory facts."""
        return self.facts.model.create_result(
            self.facts.profile(),
            source_registration_uuidv4=source["source_registration_uuidv4"],
            inputs=[
                {"source_input_uuidv4": item["source_input_uuidv4"]}
                for item in self.inventory_evidence
            ],
            derivation={"parser": PARSER, "kind": "inventory"},
        )

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
        s = self.s
        if listing_kind:
            # A changed provider count invalidates a completed cached listing
            # even if its head/base fields are unchanged.
            context = {**(context or {}), "reported_count": reported}
        with s.transaction():
            self.facts.fence(job)
            collection = self.facts.begin(
                repo, pr, kind, job, url, context, reuse=reuse
            )
            listing = None
            if listing_kind:
                listing = s.one(
                    "SELECT code_listing_id FROM code_listings WHERE fetch_collection_id=? AND kind=?",
                    (collection["fetch_collection_id"], listing_kind),
                )
                if not listing:
                    algorithm, head, base = oid_context(context or {})
                    ident = collection["fetch_collection_id"] + ":" + listing_kind
                    s.execute(
                        "INSERT INTO code_listings(code_listing_id,change_request_id,fetch_collection_id,kind,resume_scope_id,object_format,head_oid,base_oid) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            ident,
                            pr,
                            collection["fetch_collection_id"],
                            listing_kind,
                            collection["resume_scope_id"],
                            algorithm,
                            head,
                            base,
                        ),
                    )
                    s.execute(
                        "INSERT INTO code_listing_progress(code_listing_id,state,terminal,page_count,context_proven) VALUES(?,'partial',0,0,0)",
                        (ident,),
                    )
                    listing = (ident,)
            if collection["state"] == "complete":
                return collection["fetch_collection_id"], listing[
                    0
                ] if listing else None
        previous = s.one(
            "SELECT ordinal,next_cursor FROM fetch_occurrences WHERE fetch_collection_id=? ORDER BY ordinal DESC,fetch_occurrence_id DESC LIMIT 1",
            (collection["fetch_collection_id"],),
        )
        # A committed terminal page still needs its completion boundary, never a
        # repeated request. Empty initial cursor without a page means start fresh.
        url = previous["next_cursor"] if previous else url
        seen = set()
        response, uncommitted = None, False
        try:
            while url:
                self.token.check()
                if url in seen:
                    raise CatalogError("PAGINATION_CYCLE", "Repeated collection page")
                seen.add(url)
                response, uncommitted = None, False
                response = self.request_get(url, repo)
                uncommitted = True
                values = self.rest_json(response)
                if not isinstance(values, list):
                    raise CatalogError(
                        "API_SCHEMA", "Collection response must be a list"
                    )
                next_url = self.http.next_url(response)
                from repo_catalog.adapters.git.runner import hook

                hook("before_api_page_commit")
                with s.transaction():
                    self.facts.fence(job)
                    occurrence, ordinal, timestamp = self.facts.page(
                        collection, response, {"url": url, "method": "GET"}, next_url
                    )
                    for position, value in enumerate(values):
                        self.rest_item(value, kind)
                        normalizer(
                            value,
                            collection,
                            occurrence,
                            ordinal * 10000 + position,
                            timestamp,
                            listing[0] if listing else None,
                        )
                    self.facts.choose_page(collection, occurrence)
                    if listing:
                        s.execute(
                            "UPDATE code_listing_progress SET page_count=page_count+1,terminal=? WHERE code_listing_id=?",
                            (int(next_url is None), listing[0]),
                        )
                    self.facts.publish()
                uncommitted = False
                hook("after_api_page_commit")
                url = next_url
            if listing:
                table = (
                    "code_commits" if listing_kind == "commits" else "code_file_changes"
                )
                count = s.one(
                    f"SELECT count(*) FROM {table} WHERE code_listing_id=?",
                    (listing[0],),
                )[0]
                if cap and (count >= cap or reported is not None and count < reported):
                    raise CatalogError(
                        "API_CAP",
                        "Provider list may be truncated",
                        {"cap": cap, "collected": count, "reported": reported},
                    )
            with s.transaction():
                self.facts.fence(job)
                self.facts.finish(collection)
                if listing:
                    s.execute(
                        "UPDATE code_listing_progress SET state='complete',terminal=1,context_proven=1 WHERE code_listing_id=?",
                        (listing[0],),
                    )
                self.collection_coverage(repo, pr, kind, collection, "complete")
                self.facts.publish()
            return collection["fetch_collection_id"], listing[0] if listing else None
        except CatalogError as error:
            self.partial_rest_collection(
                repo,
                pr,
                kind,
                job,
                collection,
                error,
                response if uncommitted else None,
                url,
            )
            raise

    def partial_rest_collection(
        self, repo, pr, kind, job, collection, error, response, url
    ):
        """Keep the safe live retry boundary, never the rejected response bytes."""
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
                and error.code not in ("CANCELLED", "STALE_ATTEMPT")
                else None,
            )
            if error.code not in ("CANCELLED", "STALE_ATTEMPT") and (
                self.facts.pending_response(collection) or error.code == "API_CAP"
            ):
                # A committed terminal page interrupted before finish needs no
                # new acquisition; a rejected response or saved prefix does.
                self.collection_coverage(
                    repo, pr, kind, collection, "partial", reason=error.code
                )
            self.facts.publish()

    @staticmethod
    def rest_json(response):
        try:
            value = response.json()
            # SQLite projections retain whole provider objects as JSON. Check
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

    def ensure_pr(
        self, repo, value, collection, occurrence, position, timestamp, *, publish=True
    ):
        s = self.s
        self.rest_item(value, "pr-detail")
        provider_document_id = self.document_provider_id(value)
        binding = s.one(
            "SELECT repository_binding_id FROM resume_scopes WHERE resume_scope_id=?",
            (collection["resume_scope_id"],),
        )[0]
        row = s.one(
            "SELECT * FROM change_requests WHERE repository_binding_id=? AND change_request_kind='pull_request' AND provider_change_request_number=?",
            (binding, value["number"]),
        )
        ident = (
            row["change_request_id"]
            if row
            else f"{repo['repository_uuidv4']}:{value['number']}"
        )
        if row is None and s.one(
            "SELECT 1 FROM change_requests WHERE change_request_id=?", (ident,)
        ):
            ident = f"{binding}:{value['number']}"
        if collection.get("change_request_id") not in (None, ident):
            raise CatalogError(
                "API_SCHEMA", "PR response does not match the requested PR"
            )
        if not row:
            s.execute(
                "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES(?,?,?,'pull_request',?)",
                (
                    ident,
                    repo["repository_uuidv4"],
                    binding,
                    value["number"],
                ),
            )
        origin = self.facts.origin(collection, occurrence, position)
        existing = s.one(
            "SELECT change_request_observation_id FROM change_request_observations WHERE change_request_id=? AND origin_key=?",
            (ident, origin),
        )
        if existing:
            return ident
        s.execute(
            "INSERT INTO change_request_observations(change_request_observation_uuidv4,repository_uuidv4,parsed_result_uuidv4,change_request_id,observed_at_us,published,payload,origin_key,parsed_at_us,origin_fetch_occurrence_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                repo["repository_uuidv4"],
                self.facts.result(occurrence),
                ident,
                timestamp,
                int(publish or not row),
                canonical(value),
                origin,
                now_us(),
                occurrence,
            ),
        )
        if publish or not row:
            self.facts.choose(
                self.facts.result(occurrence),
                fact_kind="change-request",
                change_request_id=ident,
            )
            for offset, (kind, body) in enumerate(
                (
                    ("pr-title", value.get("title")),
                    ("pr-body", "" if value.get("body") is None else value["body"]),
                )
            ):
                self.facts.document(
                    ident,
                    kind,
                    provider_document_id,
                    body,
                    value,
                    collection,
                    occurrence,
                    position + offset,
                    timestamp,
                )
        return ident

    def detail(self, repo, pr, job, url):
        with self.s.transaction():
            self.facts.fence(job)
            collection = self.facts.begin(
                repo, pr["change_request_id"], "pr-detail", job, url
            )
            validator = self.s.one(
                "SELECT * FROM validators WHERE resume_scope_id=? AND validator_key='representation'",
                (collection["resume_scope_id"],),
            )
        if collection["state"] == "complete":
            candidates = self.s.all(
                "SELECT DISTINCT o.* FROM completion_markers c JOIN eligible_change_request_observations o ON o.change_request_observation_uuidv4=json_extract(c.evidence,'$.change_request_observation_uuidv4') WHERE c.fetch_collection_id=? AND o.change_request_id=?",
                (collection["fetch_collection_id"], pr["change_request_id"]),
            )
            row = candidates[0] if len(candidates) == 1 else None
            if row is None:
                raise CatalogError(
                    "API_SCHEMA", "Completed detail has no saved authorization"
                )
            value = json.loads(row["payload"])
            return value, row["change_request_observation_id"]
        headers = {"If-None-Match": validator["etag"]} if validator else {}
        response = self.request_get(url, repo, headers=headers)
        if response.status_code == 304:
            payload = (
                self.s.one(
                    "SELECT b.body FROM payloads p JOIN stored_bytes b ON b.sha256=p.sha256 WHERE p.representation=? AND p.sha256=? AND NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=p.sha256)",
                    (validator["payload_representation"], validator["payload_sha256"]),
                )
                if validator
                else None
            )
            if payload:
                value = json.loads(payload[0])
                admitted = self.s.one(
                    "SELECT o.change_request_observation_id AS current_change_request_observation_id,o.change_request_observation_uuidv4,o.payload FROM current_change_request_observations o WHERE o.change_request_id=?",
                    (pr["change_request_id"],),
                )
                if not admitted or json.loads(admitted["payload"]) != value:
                    # A newer race observation can differ from this validator.
                    # Acquire an actual representation rather than attaching old
                    # cached A bytes to the newer B observation.
                    payload = None
                else:
                    current = admitted["current_change_request_observation_id"]
            if payload:
                # A validation is a successful boundary, not a new observation of
                # cached bytes. It records no page/document/PR occurrence.
                validated_at_us = now_us()
                with self.s.transaction():
                    self.facts.fence(job)
                    self.facts.finish(
                        collection,
                        evidence={
                            "status": 304,
                            "response": self.facts.response_metadata(response),
                            "payload": PayloadRef(
                                validator["payload_representation"],
                                validator["payload_sha256"],
                            ).as_json(),
                            "change_request_observation_uuidv4": admitted[
                                "change_request_observation_uuidv4"
                            ],
                        },
                        observed_at_us=validated_at_us,
                    )
                    self.s.execute(
                        "UPDATE validators SET validated_at_us=? WHERE resume_scope_id=? AND validator_key='representation'",
                        (validated_at_us, collection["resume_scope_id"]),
                    )
                    self.facts.publish()
                return value, current
            response = self.request_get(url, repo)
            if response.status_code == 304:
                raise CatalogError("API_SCHEMA", "304 without saved representation")
        try:
            value = self.rest_json(response)
            with self.s.transaction():
                self.facts.fence(job)
                occurrence, _, timestamp = self.facts.page(
                    collection, response, {"url": url, "method": "GET"}, None
                )
                self.ensure_pr(repo, value, collection, occurrence, 0, timestamp)
                if response.headers.get("etag"):
                    payload_key = self.s.one(
                        "SELECT payload_representation,payload_sha256 FROM fetch_occurrences WHERE fetch_occurrence_id=?",
                        (occurrence,),
                    )
                    if validator:
                        self.s.execute(
                            "UPDATE validators SET etag=?,payload_representation=?,payload_sha256=?,validated_at_us=? WHERE resume_scope_id=? AND validator_key='representation'",
                            (
                                response.headers["etag"],
                                *payload_key,
                                timestamp,
                                collection["resume_scope_id"],
                            ),
                        )
                    else:
                        self.s.execute(
                            "INSERT INTO validators(resume_scope_id,validator_key,etag,payload_representation,payload_sha256,validated_at_us) VALUES(?,'representation',?,?,?,?)",
                            (
                                collection["resume_scope_id"],
                                response.headers["etag"],
                                *payload_key,
                                timestamp,
                            ),
                        )
                self.facts.finish(collection)
                self.facts.publish()
        except CatalogError as error:
            self.partial_rest_collection(
                repo,
                pr["change_request_id"],
                "pr-detail",
                job,
                collection,
                error,
                response,
                url,
            )
            raise
        selected = self.s.one(
            "SELECT change_request_observation_id FROM current_change_request_observations WHERE change_request_id=?",
            (pr["change_request_id"],),
        )
        if selected is None:
            raise CatalogError(
                "PARSER_SELECTION_UNRESOLVED",
                "Acquisition saved; an explicit parser/fact selection is required",
            )
        current = selected[0]
        return value, current

    def incremental_comments(self, repo, job, kind, endpoint, parent_field):
        with self.s.transaction():
            scope = self.facts.scope(
                repo, endpoint, {"kind": kind, "sort": "updated", "direction": "asc"}
            )
        previous = self.s.one(
            "SELECT i.* FROM incremental_scans i JOIN collection_progress p ON p.fetch_collection_id=i.fetch_collection_id WHERE json_extract(i.evidence,'$.stable_scope')=? AND i.safe_watermark_us IS NOT NULL AND p.state='complete' ORDER BY i.scan_started_at_us DESC LIMIT 1",
            (scope,),
        )
        started = now_us()
        parameters = {
            "per_page": self.cfg["rest_page_size"],
            "sort": "updated",
            "direction": "asc",
        }
        if previous:
            parameters["since"] = format_iso8601_us(
                previous["safe_watermark_us"] - 300_000_000
            )
        endpoint_url = endpoint + "?" + urlencode(parameters)
        # Resume keeps its originally bounded request and original scan start;
        # resumption itself must never move a child watermark.
        existing = self.s.one(
            "SELECT f.fetch_collection_id,f.observed_at_us,s.endpoint FROM fetch_collections f JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id JOIN resume_scopes s ON s.resume_scope_id=f.resume_scope_id WHERE f.repository_uuidv4=? AND f.kind=? AND p.job_id=? AND s.source_id=? AND s.principal_ref=? AND s.api_version=? AND s.parser_version=? AND s.profile_version=? AND s.confidence='proven' ORDER BY f.observed_at_us DESC LIMIT 1",
            (
                repo["repository_uuidv4"],
                kind + "-incremental",
                job,
                repo["source_id"],
                self.facts.principal,
                self.cfg["rest_api_version"],
                PARSER,
                self.s.config["preservation"]["profile"],
            ),
        )
        if existing:
            endpoint_url, started = existing["endpoint"], existing["observed_at_us"]

        def normalize(value, collection, occurrence, position, timestamp, listing):
            parent = value.get(parent_field)
            if not isinstance(parent, str) or value.get("id") is None:
                raise CatalogError("API_SCHEMA", "Comment parent/identity missing")
            self.http.validate_url(parent)
            expected_path = urlsplit(endpoint).path.rsplit("/", 2)[0]
            parts = urlsplit(parent).path.rsplit("/", 2)
            if (
                len(parts) != 3
                or parts[0] != expected_path
                or parts[1] not in ("issues", "pulls")
            ):
                raise CatalogError(
                    "SCOPE_MISMATCH", "Comment parent outside repository"
                )
            try:
                number = int(parts[-1])
            except ValueError:
                raise CatalogError("API_SCHEMA", "Invalid comment parent") from None
            self.rest_integer(number, "comment parent number", minimum=1)
            pr = self.s.one(
                "SELECT change_request_id FROM change_requests WHERE repository_binding_id=(SELECT repository_binding_id FROM resume_scopes WHERE resume_scope_id=?) AND change_request_kind='pull_request' AND provider_change_request_number=?",
                (scope, number),
            )
            if not pr:
                raise CatalogError(
                    "COMMENT_PARENT_UNKNOWN", "Comment parent has not been acquired"
                )
            self.facts.document(
                pr[0],
                kind,
                self.document_provider_id(value),
                "" if value.get("body") is None else value["body"],
                value,
                collection,
                occurrence,
                position,
                timestamp,
            )

        cid, _ = self.collection(
            repo,
            None,
            kind + "-incremental",
            job,
            endpoint_url,
            normalize,
            context={"kind": kind, "sort": "updated", "direction": "asc"},
        )
        # Separate stable watermark scope from the actual since-specific request.
        with self.s.transaction():
            self.facts.fence(job)
            if not self.s.one(
                "SELECT 1 FROM incremental_scans WHERE fetch_collection_id=?", (cid,)
            ):
                actual_scope = self.s.one(
                    "SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?",
                    (cid,),
                )[0]
                # Each request scope records its own scan, and a stable scope also
                # points to that same endpoint context via safe scan lookup below.
                self.s.execute(
                    "INSERT INTO incremental_scans(incremental_scan_id,resume_scope_id,fetch_collection_id,scan_started_at_us,safe_watermark_us,evidence) VALUES(?,?,?,?,?,?)",
                    (
                        cid,
                        actual_scope,
                        cid,
                        started,
                        started,
                        canonical(
                            {
                                "stable_scope": scope,
                                "boundary": "successful-terminal-page",
                            }
                        ),
                    ),
                )
            self.facts.publish()

    def current_incremental_reviews(self, repo, job, endpoint):
        parameters = {
            "per_page": self.cfg["rest_page_size"],
            "sort": "updated",
            "direction": "asc",
        }
        fixed_endpoint = endpoint + "?" + urlencode(parameters)
        context = {
            "kind": "review-comment",
            "sort": "updated",
            "direction": "asc",
            "incremental_endpoint": fixed_endpoint,
        }
        url, context = self.current_incremental_url(
            repo, job, "review-comment-incremental", fixed_endpoint, context
        )

        def parse(value, candidate_context, timestamp):
            parent = value.get("pull_request_url") if isinstance(value, dict) else None
            if not isinstance(parent, str):
                raise CatalogError("API_SCHEMA", "Review comment parent missing")
            self.http.validate_url(parent)
            prefix = urlsplit(endpoint).path.rsplit("/", 2)[0] + "/pulls/"
            path = urlsplit(parent).path
            suffix = path.removeprefix(prefix)
            if (
                not path.startswith(prefix)
                or not suffix.isascii()
                or not suffix.isdecimal()
                or str(int(suffix)) != suffix
                or int(suffix) <= 0
            ):
                raise CatalogError(
                    "SCOPE_MISMATCH",
                    "Review comment parent outside selected repository",
                )
            self.rest_integer(int(suffix), "review comment parent number", minimum=1)
            owner = self.s.one(
                "SELECT change_request_id FROM change_requests WHERE repository_binding_id=? AND change_request_kind='pull_request' AND provider_change_request_number=?",
                (candidate_context["repository_binding_id"], int(suffix)),
            )
            if owner is None:
                raise CatalogError(
                    "COMMENT_PARENT_UNKNOWN",
                    "Review comment parent has not been acquired",
                )
            candidate_context = {
                **candidate_context,
                "change_request_id": owner["change_request_id"],
                "acquisition_scope": {
                    **candidate_context["acquisition_scope"],
                    "change_request_id": owner["change_request_id"],
                },
            }
            return current_parser.review_comment(value, candidate_context, timestamp)

        cid, _ = self.current_collection(
            repo, None, "review-comment-incremental", job, url, parse, context=context
        )
        with self.s.transaction():
            self.facts.fence(job)
            row = self.s.one(
                "SELECT resume_scope_id,observed_at_us FROM fetch_collections WHERE fetch_collection_id=?",
                (cid,),
            )
            if (
                self.s.one(
                    "SELECT 1 FROM incremental_scans WHERE fetch_collection_id=?",
                    (cid,),
                )
                is None
            ):
                self.s.execute(
                    "INSERT INTO incremental_scans(incremental_scan_id,resume_scope_id,fetch_collection_id,scan_started_at_us,safe_watermark_us,evidence) VALUES(?,?,?,?,?,?)",
                    (
                        cid,
                        row["resume_scope_id"],
                        cid,
                        row["observed_at_us"],
                        row["observed_at_us"],
                        canonical(
                            {
                                "boundary": "successful-terminal-page",
                                "current_resource_pages": True,
                            }
                        ),
                    ),
                )
            self.facts.publish()
        return cid

    def _document_normalizer(self, pr, kind):
        def normalize(value, collection, occurrence, position, timestamp, listing):
            if value.get("id") is None:
                raise CatalogError("API_SCHEMA", "Document ID missing")
            self.facts.document(
                pr,
                kind,
                self.document_provider_id(value),
                "" if value.get("body") is None else value["body"],
                value,
                collection,
                occurrence,
                position,
                timestamp,
            )

        return normalize

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

    def saved_thread_code_input(self, pr):
        """Recover observed merge targets even when thread collection failed."""
        collection = self.thread_collections.get(pr)
        if collection is None:
            return {}, False, None
        page = self.s.one(
            "SELECT b.body,o.observed_at_us,o.payload_sha256 FROM fetch_occurrences o JOIN payloads p ON p.representation=o.payload_representation AND p.sha256=o.payload_sha256 JOIN stored_bytes b ON b.sha256=p.sha256 WHERE o.fetch_collection_id=? ORDER BY o.ordinal DESC,o.fetch_occurrence_id DESC LIMIT 1",
            (collection["fetch_collection_id"],),
        )
        if page is None:
            return {}, False, None
        from repo_catalog.adapters.sqlite.cas_integrity import is_quarantined

        if is_quarantined(self.s.connection, page["payload_sha256"]):
            return {}, False, None
        try:
            payload = json.loads(page["body"])
            value = self.graphql_object(payload, "data", "repository", "pullRequest")
        except (ValueError, CatalogError):
            return {}, False, page["observed_at_us"]
        roles = {}
        complete = not bool(payload.get("errors"))
        from repo_catalog.domain.models import GitOid

        for role, field in (
            ("merge", "mergeCommit"),
            ("test-merge", "potentialMergeCommit"),
        ):
            if field not in value:
                complete = False
                continue
            target = value[field]
            if target is None:
                roles[role] = None
                continue
            oid = target.get("oid") if isinstance(target, dict) else None
            if not isinstance(oid, str):
                complete = False
                continue
            try:
                GitOid.parse(("sha256:" if len(oid) == 64 else "sha1:") + oid)
            except CatalogError:
                complete = False
                continue
            roles[role] = oid
        return roles, complete, page["observed_at_us"]

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
        with self.s.transaction():
            self.facts.current_context(
                repo, pr["change_request_id"], self.http.graphql, "review-comment"
            )
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
                },
            )
        self.thread_collections[pr["change_request_id"]] = collection
        merge = {}
        if collection["state"] == "complete":
            last = self.s.one(
                "SELECT b.body,o.payload_sha256 FROM fetch_occurrences o JOIN payloads p ON p.representation=o.payload_representation AND p.sha256=o.payload_sha256 JOIN stored_bytes b ON b.sha256=p.sha256 WHERE o.fetch_collection_id=? ORDER BY o.ordinal DESC LIMIT 1",
                (collection["fetch_collection_id"],),
            )
            if last:
                self.facts.require_payload(last["payload_sha256"])
                p = (
                    (json.loads(last[0]).get("data") or {}).get("repository") or {}
                ).get("pullRequest") or {}
                return self._merge_roles(p)
            return merge
        pending = (
            json.loads(collection["cursor"])
            if collection["cursor"]
            else {"cursor": None}
        )
        child_collections = []

        def observed_at_us(*, include_partial=True):
            return self.facts.thread_observed_at_us(
                collection, include_partial=include_partial
            )

        seen = set()
        response, uncommitted, resource_observed = None, False, False
        try:
            while True:
                response, uncommitted, resource_observed = None, False, False
                cursor = pending.get("cursor")
                if cursor in seen:
                    raise CatalogError("PAGINATION_CYCLE", "Thread cursor cycle")
                seen.add(cursor)
                variables = {
                    "owner": owner,
                    "name": name,
                    "number": pr["provider_change_request_number"],
                    "cursor": cursor,
                    "pageSize": self.cfg["graphql_page_size"],
                }
                if pending.get("occurrence"):
                    page = self.s.one(
                        "SELECT o.*,b.body FROM fetch_occurrences o JOIN payloads p ON p.representation=o.payload_representation AND p.sha256=o.payload_sha256 JOIN stored_bytes b ON b.sha256=p.sha256 WHERE o.fetch_occurrence_id=? AND o.fetch_collection_id=?",
                        (pending["occurrence"], collection["fetch_collection_id"]),
                    )
                    self.facts.require_payload(page["payload_sha256"])
                    payload = json.loads(page["body"])
                    self.graphql_errors(payload, "data", "repository", "pullRequest")
                    occurrence, timestamp = (
                        page["fetch_occurrence_id"],
                        page["observed_at_us"],
                    )
                else:
                    base_revision = self.s.revision()
                    response = self.http.request(
                        "POST",
                        self.http.graphql,
                        json={"query": root_query, "variables": variables},
                    )
                    self._retain_recording_diagnostics(response)
                    uncommitted = True
                    payload = self.rest_json(response)
                    self.graphql_errors(payload, "data", "repository", "pullRequest")
                    p = self.graphql_object(
                        payload, "data", "repository", "pullRequest"
                    )
                    resource_observed = True
                    connection = p.get("reviewThreads")
                    nodes, info, next_cursor = self.graphql_connection(connection)
                    with self.s.transaction():
                        self.facts.fence(job)
                        occurrence, _, timestamp = self.facts.page(
                            collection,
                            response,
                            {
                                "url": self.http.graphql,
                                "method": "POST",
                                "query": root_query,
                                "variables": variables,
                            },
                            next_cursor,
                            advance=False,
                        )
                        current_members = []
                        for index, thread in enumerate(nodes):
                            review_thread_provider_resource_id = thread.get("id")
                            if (
                                not isinstance(review_thread_provider_resource_id, str)
                                or not review_thread_provider_resource_id
                            ):
                                raise CatalogError(
                                    "API_SCHEMA", "Thread identity missing"
                                )
                            if not self.s.one(
                                "SELECT 1 FROM review_threads WHERE change_request_id=? AND provider_resource_id=?",
                                (
                                    pr["change_request_id"],
                                    review_thread_provider_resource_id,
                                ),
                            ):
                                self.s.execute(
                                    "INSERT INTO review_threads(change_request_id,provider_resource_id) VALUES(?,?)",
                                    (
                                        pr["change_request_id"],
                                        review_thread_provider_resource_id,
                                    ),
                                )
                            current_members.extend(
                                self._thread_documents(
                                    repo,
                                    pr,
                                    review_thread_provider_resource_id,
                                    thread.get("comments"),
                                    collection,
                                    occurrence,
                                    index * 10000,
                                    timestamp,
                                    base_revision=base_revision,
                                    refresh_root=True,
                                )
                            )
                        for thread in nodes:
                            self._thread(
                                repo,
                                pr,
                                thread,
                                timestamp,
                                occurrence,
                                observation_complete=not bool(payload.get("errors")),
                            )
                        from repo_catalog.adapters.sqlite.current_collections import (
                            CurrentCollectionProof,
                        )

                        CurrentCollectionProof(self.s.connection).page(
                            collection["fetch_collection_id"],
                            self.s.one(
                                "SELECT count(*) FROM current_collection_pages WHERE fetch_collection_id=?",
                                (collection["fetch_collection_id"],),
                            )[0],
                            timestamp,
                            canonical({"cursor": cursor})
                            if payload.get("errors")
                            else next_cursor,
                            current_members,
                            status=response.status_code,
                            parser_module=current_parser.PARSER_MODULE,
                            parser_version=current_parser.PARSER_VERSION,
                        )
                        # Root page and pending child boundary commit together. Resume
                        # reads this exact page and never records it as a new response.
                        if not payload.get("errors"):
                            self.s.execute(
                                "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                                (
                                    canonical(
                                        {"cursor": cursor, "occurrence": occurrence}
                                    ),
                                    collection["fetch_collection_id"],
                                ),
                            )
                        self.facts.publish()
                    uncommitted = False
                p = self.graphql_object(payload, "data", "repository", "pullRequest")
                connection = p.get("reviewThreads")
                nodes, info, next_cursor = self.graphql_connection(connection)
                merge = self._merge_roles(p)
                if payload.get("errors"):
                    raise CatalogError(
                        "GRAPHQL_PARTIAL", "GraphQL partial page; cursor retained"
                    )
                for thread in nodes:
                    review_thread_provider_resource_id = str(thread["id"])
                    self._thread_children(
                        repo,
                        pr,
                        thread,
                        review_thread_provider_resource_id,
                        job,
                        child_query,
                        collection,
                        occurrence,
                        timestamp,
                        child_collections,
                    )
                with self.s.transaction():
                    self.facts.fence(job)
                    if info.get("hasNextPage"):
                        pending = {"cursor": next_cursor}
                        self.s.execute(
                            "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                            (canonical(pending), collection["fetch_collection_id"]),
                        )
                    else:
                        if any(
                            self.current_members_unresolved(ident)
                            for ident in self.thread_collection_ids(collection)
                        ):
                            raise CatalogError(
                                "CURRENT_STATE_UNRESOLVED",
                                "Thread has unresolved current comment members",
                            )
                        self.facts.finish(
                            collection,
                            evidence={
                                "terminal": True,
                                "fetch_collection_ids": self.thread_collection_ids(
                                    collection
                                ),
                            },
                            observed_at_us=observed_at_us(include_partial=False),
                        )
                        self.coverage_claim(
                            repo["repository_uuidv4"],
                            "threads",
                            "complete",
                            observed_at_us(include_partial=False),
                            {
                                "fetch_collection_ids": self.thread_collection_ids(
                                    collection
                                )
                            },
                            change_request_id=pr["change_request_id"],
                        )
                    self.facts.publish()
                if not info.get("hasNextPage"):
                    return merge
        except CatalogError as error:
            with self.s.transaction():
                self.facts.fence(job)
                diagnose_admission_failure(self.s.connection, error)
                if error.details.get("refresh_root"):
                    self.s.execute(
                        "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                        (
                            canonical({"cursor": pending.get("cursor")}),
                            collection["fetch_collection_id"],
                        ),
                    )
                self.facts.partial(
                    collection,
                    error.code,
                    observed_at_us=self.facts.response_time(response)
                    if response is not None
                    and uncommitted
                    and resource_observed
                    and error.code not in ("CANCELLED", "STALE_ATTEMPT")
                    else None,
                )
                if error.code not in ("CANCELLED", "STALE_ATTEMPT") and (
                    any(
                        self.facts.pending_response(item)
                        for item in (collection, *child_collections)
                    )
                    or error.code
                    in (
                        "GRAPHQL_PARTIAL",
                        "API_SCHEMA",
                        "CANONICAL_DOCUMENT_ID_MISSING",
                    )
                ):
                    self.coverage_claim(
                        repo["repository_uuidv4"],
                        "threads",
                        "partial",
                        observed_at_us(),
                        {
                            "reason": error.code,
                            "fetch_collection_ids": self.thread_collection_ids(
                                collection
                            ),
                        },
                        change_request_id=pr["change_request_id"],
                    )
                self.facts.publish()
            raise

    @staticmethod
    def _merge_roles(value):
        return {
            role: value[field].get("oid")
            if isinstance(value.get(field), dict)
            else None
            for role, field in (
                ("merge", "mergeCommit"),
                ("test-merge", "potentialMergeCommit"),
            )
        }

    def _thread(
        self, repo, pr, thread, timestamp, occurrence, *, observation_complete=True
    ):
        if not isinstance(thread.get("id"), str) or not thread["id"]:
            raise CatalogError("API_SCHEMA", "Thread identity missing")
        provider_resource_id = thread["id"]
        nodes, info, _ = self.graphql_connection(
            thread.get("comments"), refresh_root=True
        )
        value = canonical(
            {
                **{key: item for key, item in thread.items() if key != "comments"},
                "comments": {
                    "nodes": [
                        {
                            "fullDatabaseId": current_parser.resource_id(
                                item, "fullDatabaseId"
                            )
                        }
                        for item in nodes
                    ],
                    "pageInfo": info,
                    "observation_complete": observation_complete,
                },
            }
        )
        if not self.s.one(
            "SELECT 1 FROM review_threads WHERE change_request_id=? AND provider_resource_id=?",
            (pr["change_request_id"], provider_resource_id),
        ):
            self.s.execute(
                "INSERT INTO review_threads(change_request_id,provider_resource_id) VALUES(?,?)",
                (pr["change_request_id"], provider_resource_id),
            )
        result = self.facts.result(occurrence)
        self.s.execute(
            "INSERT INTO review_thread_observations(thread_observation_uuidv4,repository_uuidv4,change_request_id,provider_resource_id,parsed_result_uuidv4,observed_at_us,payload) VALUES(?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                repo["repository_uuidv4"],
                pr["change_request_id"],
                provider_resource_id,
                result,
                timestamp,
                value,
            ),
        )
        self.facts.choose(
            result,
            fact_kind="review-thread",
            change_request_id=pr["change_request_id"],
            provider_resource_id=provider_resource_id,
        )
        return provider_resource_id

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

    def _thread_children(
        self,
        repo,
        pr,
        thread,
        review_thread_provider_resource_id,
        job,
        query,
        parent,
        parent_occurrence,
        timestamp,
        child_collections,
    ):
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        proof = CurrentCollectionProof(self.s.connection)
        _, info, initial_cursor = self.graphql_connection(
            thread.get("comments"), refresh_root=True
        )
        if not info["hasNextPage"]:
            return
        with self.s.transaction():
            collection = self.facts.begin(
                repo,
                pr["change_request_id"],
                "thread-comments",
                job,
                self.http.graphql,
                {
                    "thread": thread["id"],
                    "query": query,
                    "parent_fetch_collection_id": parent["fetch_collection_id"],
                },
            )
        child_collections.append(collection)
        if collection["state"] == "complete":
            return
        page = self.s.one(
            "SELECT ordinal,next_cursor FROM current_collection_pages WHERE fetch_collection_id=? ORDER BY ordinal DESC LIMIT 1",
            (collection["fetch_collection_id"],),
        )
        cursor = page["next_cursor"] if page else initial_cursor
        ordinal = page["ordinal"] + 1 if page else 0
        seen = set()
        response, uncommitted, resource_observed = None, False, False
        try:
            while cursor:
                response, uncommitted, resource_observed = None, False, False
                if cursor in seen:
                    raise CatalogError(
                        "PAGINATION_CYCLE", "Thread comments cursor cycle"
                    )
                seen.add(cursor)
                variables = {
                    "thread": thread["id"],
                    "commentCursor": cursor,
                    "pageSize": self.cfg["graphql_page_size"],
                }
                base_revision = self.s.revision()
                response = self.http.request(
                    "POST",
                    self.http.graphql,
                    json={"query": query, "variables": variables},
                    record_context={
                        "provider_request_kind": "thread-comments",
                        "repository": repo["name"],
                        "pr_number": pr["provider_change_request_number"],
                    },
                )
                self._retain_recording_diagnostics(response)
                uncommitted = True
                payload = self.rest_json(response)
                self.graphql_errors(payload, "data", "node")
                comments = self.graphql_object(payload, "data", "node").get("comments")
                resource_observed = True
                _, info, next_cursor = self.graphql_connection(comments)
                with self.s.transaction():
                    self.facts.fence(job)
                    timestamp = response.extensions.get(
                        "catalog_observed_at_us", now_us()
                    )
                    members = self._thread_documents(
                        repo,
                        pr,
                        review_thread_provider_resource_id,
                        comments,
                        collection,
                        None,
                        ordinal * 10000,
                        timestamp,
                        base_revision=base_revision,
                    )
                    proof.page(
                        collection["fetch_collection_id"],
                        ordinal,
                        timestamp,
                        cursor if payload.get("errors") else next_cursor,
                        members,
                        status=response.status_code,
                        parser_module=current_parser.PARSER_MODULE,
                        parser_version=current_parser.PARSER_VERSION,
                    )
                    self.s.execute(
                        "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                        (
                            cursor if payload.get("errors") else next_cursor,
                            collection["fetch_collection_id"],
                        ),
                    )
                    self.facts.publish()
                uncommitted = False
                if payload.get("errors"):
                    raise CatalogError(
                        "GRAPHQL_PARTIAL", "Thread comments page has errors"
                    )
                cursor = next_cursor
                ordinal += 1
            with self.s.transaction():
                self.facts.fence(job)
                if self.current_members_unresolved(collection["fetch_collection_id"]):
                    raise CatalogError(
                        "CURRENT_STATE_UNRESOLVED",
                        "Thread comments have unresolved current members",
                    )
                self.facts.finish(
                    collection,
                    evidence=proof.evidence(collection["fetch_collection_id"]),
                )
                self.facts.publish()
        except CatalogError as error:
            with self.s.transaction():
                self.facts.fence(job)
                diagnose_admission_failure(self.s.connection, error)
                if response is not None and uncommitted:
                    self.s.execute(
                        "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                        (cursor, collection["fetch_collection_id"]),
                    )
                self.facts.partial(
                    collection,
                    error.code,
                    observed_at_us=self.facts.response_time(response)
                    if response is not None
                    and uncommitted
                    and resource_observed
                    and error.code not in ("CANCELLED", "STALE_ATTEMPT")
                    else None,
                )
                self.facts.publish()
            raise

    def completed_pr(self, repo, job, pr_id):
        row = self.s.one(
            "SELECT c.code_observation_id,c.head_oid,c.base_oid,c.details,sc.request_context scope_context FROM eligible_code_observations c JOIN eligible_change_request_observations o ON o.change_request_observation_id=c.change_request_observation_id JOIN fetch_occurrences a ON a.fetch_occurrence_id=o.origin_fetch_occurrence_id JOIN collection_progress p ON p.fetch_collection_id=a.fetch_collection_id JOIN fetch_collections f ON f.fetch_collection_id=p.fetch_collection_id JOIN resume_scopes sc ON sc.resume_scope_id=f.resume_scope_id WHERE p.job_id=? AND c.change_request_id=? AND c.state='complete' AND sc.source_id=? AND sc.principal_ref=? AND sc.api_version=? AND sc.parser_version=? AND sc.profile_version=? AND sc.confidence='proven' ORDER BY c.code_observation_id DESC LIMIT 1",
            (
                job,
                pr_id,
                repo["source_id"],
                self.facts.principal,
                self.cfg["rest_api_version"],
                PARSER,
                self.s.config["preservation"]["profile"],
            ),
        )
        if (
            not row
            or json.loads(row["scope_context"]).get("permissions")
            != self.facts.permissions
        ):
            return False
        kinds = {
            r[0]
            for r in self.s.all(
                "SELECT f.kind FROM fetch_collections f JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id WHERE p.job_id=? AND f.change_request_id=? AND p.state='complete'",
                (job, pr_id),
            )
        }
        if (
            not {"issue-comment", "review", "review-comment", "timeline", "threads"}
            <= kinds
        ):
            return False
        links = {
            r[0]
            for r in self.s.all(
                "SELECT a.role FROM code_acquisitions a JOIN acquisition_roots r ON r.acquisition_root_id=a.acquisition_root_id WHERE a.code_observation_id=? AND r.published=1",
                (row["code_observation_id"],),
            )
        }
        roles = set(json.loads(row["details"]).get("expected_roles", {}))
        if not roles:
            return False
        return roles <= links

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
                    "SELECT MAX(p.observed_at_us) FROM current_collection_pages p JOIN collection_progress c USING(fetch_collection_id) JOIN fetch_collections f USING(fetch_collection_id) WHERE c.job_id=? AND f.repository_uuidv4=? AND f.kind IN ('issue','ordinary-issue-comment')",
                    (job, repo["repository_uuidv4"]),
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
                self.facts.publish()
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

    def sync(self, repo, job):
        s = self.s
        root = f"{self.http.base}/repos/{repo['name']}"
        failures, waiting = [], None
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
            identity_response = self.http.request("GET", self.http.base + "/user")
            self._retain_recording_diagnostics(identity_response)
            identity = identity_response.json()
            permissions = identity_response.headers.get("x-oauth-scopes")
            self.facts.permissions = (
                sorted(item.strip() for item in permissions.split(",") if item.strip())
                if permissions is not None
                else None
            )
            principal = identity.get("id") or identity.get("login")
            if not principal:
                raise CatalogError("API_SCHEMA", "Principal identity missing")
            self.facts.principal = str(principal)
            size = self.cfg["rest_page_size"]

            def pr_item(value, collection, occurrence, position, timestamp, listing):
                self.ensure_pr(
                    repo,
                    value,
                    collection,
                    occurrence,
                    position,
                    timestamp,
                    publish=False,
                )

            attempt(
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
            for kind, endpoint, parent in (
                ("issue-comment", root + "/issues/comments", "issue_url"),
            ):
                attempt(
                    kind + "-incremental",
                    lambda kind=kind, endpoint=endpoint, parent=parent: (
                        self.incremental_comments(repo, job, kind, endpoint, parent)
                    ),
                )
            attempt(
                "review-comment-incremental",
                lambda: self.current_incremental_reviews(
                    repo, job, root + "/pulls/comments"
                ),
            )
            selected_binding = self.facts.current_context(repo, None, root)[
                "repository_binding_id"
            ]
            prs = s.all(
                "SELECT p.*,o.change_request_observation_id AS current_change_request_observation_id,o.payload FROM change_requests p LEFT JOIN current_change_request_observations o ON o.change_request_id=p.change_request_id WHERE p.repository_binding_id=? AND p.change_request_kind='pull_request' ORDER BY p.provider_change_request_number",
                (selected_binding,),
            )
            for pr in prs:
                self.token.check()
                if self.completed_pr(repo, job, pr["change_request_id"]):
                    continue
                initial_failures = len(failures)
                url = root + f"/pulls/{pr['provider_change_request_number']}"
                detail = attempt("pr-detail", lambda: self.detail(repo, pr, job, url))
                if detail:
                    before, current = detail
                else:
                    before = json.loads(pr["payload"]) if pr["payload"] else {}
                    current = pr["current_change_request_observation_id"]
                for kind, endpoint in (
                    (
                        "issue-comment",
                        root
                        + f"/issues/{pr['provider_change_request_number']}/comments",
                    ),
                    ("review", url + "/reviews"),
                    ("review-comment", url + "/comments"),
                ):
                    attempt(
                        kind,
                        lambda kind=kind, endpoint=endpoint: (
                            self.collection(
                                repo,
                                pr["change_request_id"],
                                kind,
                                job,
                                endpoint + f"?per_page={size}",
                                self._document_normalizer(
                                    pr["change_request_id"], kind
                                ),
                            )
                            if kind == "issue-comment"
                            else self.current_collection(
                                repo,
                                pr["change_request_id"],
                                kind,
                                job,
                                endpoint + f"?per_page={size}",
                                current_parser.review
                                if kind == "review"
                                else current_parser.review_comment,
                            )
                        ),
                    )

                def event(value, collection, occurrence, position, timestamp, listing):
                    s.execute(
                        "INSERT INTO change_request_events(change_request_event_uuidv4,repository_uuidv4,parsed_result_uuidv4,change_request_id,origin_key,ordinal,provider_event_id,payload,observed_at_us,origin_fetch_occurrence_uuidv4) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            str(uuid.uuid4()),
                            repo["repository_uuidv4"],
                            self.facts.result(occurrence),
                            pr["change_request_id"],
                            self.facts.origin(collection, occurrence, position),
                            position,
                            str(value["id"]) if value.get("id") is not None else None,
                            canonical(value),
                            timestamp,
                            s.one(
                                "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences WHERE fetch_occurrence_id=?",
                                (occurrence,),
                            )[0],
                        ),
                    )

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
                merge, merge_complete, merge_observed_at_us = (
                    self.saved_thread_code_input(pr["change_request_id"])
                )
                code_input_failures = [
                    failure
                    for failure in failures[initial_failures:]
                    if failure["kind"] in ("review", "threads")
                ]
                if (
                    merge_observed_at_us is not None
                    and not merge_complete
                    and not any(f["kind"] == "threads" for f in code_input_failures)
                ):
                    failure = {
                        "kind": "pr-code",
                        "reason": "PR_CODE_TARGETS_INCOMPLETE",
                    }
                    failures.append(failure)
                    code_input_failures.append(failure)
                if not current:
                    continue
                algorithm, head, base = oid_context(before)

                def commit(value, collection, occurrence, position, timestamp, listing):
                    from repo_catalog.domain.models import GitOid

                    if not value.get("sha") or not algorithm:
                        raise CatalogError("API_SCHEMA", "PR commit OID missing")
                    oid = GitOid.parse(algorithm + ":" + value["sha"]).value
                    s.execute(
                        "INSERT INTO code_commits(repository_uuidv4,parsed_result_uuidv4,code_listing_id,fetch_occurrence_id,position,object_format,oid,payload) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            repo["repository_uuidv4"],
                            self.facts.result(occurrence),
                            listing,
                            occurrence,
                            position,
                            algorithm,
                            oid,
                            canonical(value),
                        ),
                    )

                def file_item(
                    value, collection, occurrence, position, timestamp, listing
                ):
                    if not isinstance(value.get("filename"), str):
                        raise CatalogError("API_SCHEMA", "PR file path missing")
                    s.execute(
                        "INSERT INTO code_file_changes(repository_uuidv4,parsed_result_uuidv4,code_listing_id,fetch_occurrence_id,position,raw_path,payload) VALUES(?,?,?,?,?,?,?)",
                        (
                            repo["repository_uuidv4"],
                            self.facts.result(occurrence),
                            listing,
                            occurrence,
                            position,
                            value["filename"].encode("utf-8"),
                            canonical(value),
                        ),
                    )

                oldfail = len(failures)
                commits = attempt(
                    "pr-commits",
                    lambda: self.collection(
                        repo,
                        pr["change_request_id"],
                        "pr-commits",
                        job,
                        url + f"/commits?per_page={size}",
                        commit,
                        context={
                            "head": before.get("head"),
                            "base": before.get("base"),
                        },
                        listing_kind="commits",
                        cap=250,
                        reported=before.get("commits"),
                        reuse=True,
                    ),
                )
                files_result = attempt(
                    "pr-files",
                    lambda: self.collection(
                        repo,
                        pr["change_request_id"],
                        "pr-files",
                        job,
                        url + f"/files?per_page={size}",
                        file_item,
                        context={
                            "head": before.get("head"),
                            "base": before.get("base"),
                        },
                        listing_kind="files",
                        cap=3000,
                        reported=before.get("changed_files"),
                        reuse=True,
                    ),
                )
                after_response = attempt(
                    "pr-code", lambda: self.code_check(repo, pr, job, url, current)
                )
                same = bool(after_response) and all(
                    (before.get(role) or {}).get("sha")
                    == (after_response.json().get(role) or {}).get("sha")
                    for role in ("head", "base")
                )
                if same:
                    current = after_response.extensions["catalog_observation_id"]
                if after_response is not None and not same:
                    failures.append({"kind": "pr-code", "reason": "PR_CODE_RACE"})

                # Failed listings still retain their IDs and early pages.
                def code_listing_id(kind):
                    scope = self.facts.scope(
                        repo,
                        url + f"/{kind}?per_page={size}",
                        {
                            "head": before.get("head"),
                            "base": before.get("base"),
                            "reported_count": before.get(
                                "commits" if kind == "commits" else "changed_files"
                            ),
                        },
                    )
                    row = s.one(
                        "SELECT l.code_listing_id FROM code_listings l JOIN collection_progress p ON p.fetch_collection_id=l.fetch_collection_id JOIN code_listing_progress lp ON lp.code_listing_id=l.code_listing_id WHERE l.change_request_id=? AND l.kind=? AND l.resume_scope_id=? ORDER BY (lp.state='complete') DESC,(p.job_id=?) DESC,l.code_listing_id DESC LIMIT 1",
                        (pr["change_request_id"], kind, scope, job),
                    )
                    return row[0] if row else None

                role_oids = {
                    "head": (before.get("head") or {}).get("sha"),
                    "base": (before.get("base") or {}).get("sha"),
                    **merge,
                }
                for review in s.all(
                    "SELECT target_commit_oid FROM eligible_review_resources WHERE kind='review' AND change_request_id=?",
                    (pr["change_request_id"],),
                ):
                    value = review[0]
                    if value:
                        role_oids["review-target:" + value] = value
                role_links = {}
                for role, expected in role_oids.items():
                    if not expected:
                        continue
                    from repo_catalog.adapters.git.importer import GitImporter

                    fetched = attempt(
                        "pr-git",
                        lambda role=role, expected=expected: GitImporter(
                            s, self.token
                        ).sync(
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
                            change_request_observation_id=current,
                            repository_endpoint_id=self.repository_endpoint_id,
                        ),
                    )
                    # A failed refresh cannot erase an already preserved matching
                    # role. Reuse only published same-repository, exact-OID roots
                    # whose recorded role permits the same link as a fresh fetch.
                    rootrow = s.one(
                        """SELECT r.* FROM acquisition_roots r
                           JOIN git_acquisitions g ON g.git_acquisition_id=r.git_acquisition_id
                           JOIN preservation_obligations p ON p.git_acquisition_id=g.git_acquisition_id
                           JOIN acquisition_progress a ON a.git_acquisition_id=g.git_acquisition_id
                           JOIN git_objects o ON o.object_format=r.object_format AND o.oid=r.oid
                           WHERE r.repository_uuidv4=? AND r.object_format=? AND r.oid=?
                             AND r.published=1 AND p.published=1 AND a.state='published'
                             AND o.type='commit' AND o.verified=1
                             AND (r.expected_oid IS NULL OR r.expected_oid=r.oid)
                             AND (r.role=? OR (r.role='traversal' AND EXISTS(
                                 SELECT 1 FROM json_each(g.roots_manifest) j
                                 WHERE json_extract(j.value,'$.role')=?
                                   AND lower(json_extract(j.value,'$.expected'))=lower(hex(r.oid)))))
                           ORDER BY (r.git_acquisition_id IS ?) DESC,r.acquisition_root_id DESC LIMIT 1""",
                        (
                            repo["repository_uuidv4"],
                            algorithm,
                            bytes.fromhex(expected),
                            role,
                            role,
                            fetched["git_acquisition_id"] if fetched else None,
                        ),
                    )
                    if rootrow:
                        role_links[role] = rootrow
                missing_roles = sorted(
                    role
                    for role, expected in role_oids.items()
                    if expected and role not in role_links
                )
                if missing_roles:
                    failures.append(
                        {
                            "kind": "pr-code",
                            "reason": "MISSING_CODE_ACQUISITION",
                            "roles": missing_roles,
                        }
                    )
                inputs_complete = bool(
                    algorithm
                    and head
                    and base
                    and merge_complete
                    and thread_result is not None
                    and not code_input_failures
                )
                if not inputs_complete and not code_input_failures:
                    failures.append(
                        {"kind": "pr-code", "reason": "PR_CODE_TARGETS_INCOMPLETE"}
                    )
                code_race = any(
                    failure["reason"] == "PR_CODE_RACE"
                    for failure in failures[oldfail:]
                )
                with s.transaction():
                    self.facts.fence(job)
                    commit_listing = (
                        commits[1] if commits else code_listing_id("commits")
                    )
                    file_listing = (
                        files_result[1] if files_result else code_listing_id("files")
                    )
                    listings_complete = all(
                        s.one(
                            "SELECT 1 FROM code_listing_progress WHERE code_listing_id=? AND state='complete' AND terminal=1 AND context_proven=1",
                            (listing,),
                        )
                        for listing in (commit_listing, file_listing)
                    )
                    state = (
                        "complete"
                        if same
                        and not code_race
                        and inputs_complete
                        and listings_complete
                        and not missing_roles
                        else "partial"
                    )
                    code_failures = code_input_failures + failures[oldfail:]
                    prior_code_coverage = s.one(
                        "SELECT observed_at_us FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=? AND kind='pr-code'",
                        (repo["repository_uuidv4"], pr["change_request_id"]),
                    )
                    observed_incomplete_merge = (
                        merge_observed_at_us is not None
                        and not merge_complete
                        and (
                            prior_code_coverage is None
                            or prior_code_coverage["observed_at_us"] is None
                            or merge_observed_at_us
                            >= prior_code_coverage["observed_at_us"]
                        )
                    )
                    observed_incomplete_code = (
                        code_race
                        or bool(missing_roles)
                        or observed_incomplete_merge
                        or any(
                            (repo["repository_uuidv4"], pr["change_request_id"], kind)
                            in self.observed_partial_scopes
                            for kind in ("pr-commits", "pr-files", "review", "threads")
                        )
                    )
                    prior_code = s.one(
                        "SELECT * FROM current_code_observations WHERE change_request_id=? AND change_request_observation_id=?",
                        (pr["change_request_id"], current),
                    )
                    prior_roles = (
                        json.loads(prior_code["details"]).get("expected_roles")
                        if prior_code
                        else None
                    )
                    if isinstance(prior_roles, dict) and merge_observed_at_us is None:
                        # No merge input was observed on this attempt. Absence
                        # from its inputs cannot revoke a prior saved role.
                        prior_roles = {
                            role: oid
                            for role, oid in prior_roles.items()
                            if role not in ("merge", "test-merge")
                        }
                    if (
                        state == "partial"
                        and not observed_incomplete_code
                        and prior_code
                        and prior_code["state"] == "complete"
                        and prior_code["head_oid"] == head
                        and prior_code["base_oid"] == base
                        and prior_code["commit_code_listing_id"] == commit_listing
                        and prior_code["file_code_listing_id"] == file_listing
                        and prior_roles
                        == {role: oid for role, oid in role_oids.items() if oid}
                    ):
                        # An unsuccessful check of an already represented
                        # observation is job progress, not a partial code fact.
                        continue
                    input_rows = s.all(
                        "SELECT DISTINCT o.fetch_occurrence_uuidv4 FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id WHERE f.repository_uuidv4=? AND f.change_request_id=? AND p.job_id=?",
                        (repo["repository_uuidv4"], pr["change_request_id"], job),
                    )
                    inputs = [
                        {"fetch_occurrence_uuidv4": item[0]} for item in input_rows
                    ]
                    for listing_id in (commit_listing, file_listing):
                        for item in s.all(
                            "SELECT o.fetch_occurrence_uuidv4 FROM fetch_occurrences o JOIN code_listings l ON l.fetch_collection_id=o.fetch_collection_id WHERE l.code_listing_id=?",
                            (listing_id,),
                        ):
                            entry = {"fetch_occurrence_uuidv4": item[0]}
                            if entry not in inputs:
                                inputs.append(entry)
                    original = s.one(
                        "SELECT f.fetch_occurrence_uuidv4 FROM change_request_observations o JOIN fetch_occurrences f ON f.fetch_occurrence_id=o.origin_fetch_occurrence_id WHERE o.change_request_observation_id=?",
                        (current,),
                    )
                    if (
                        original
                        and {"fetch_occurrence_uuidv4": original[0]} not in inputs
                    ):
                        inputs.append({"fetch_occurrence_uuidv4": original[0]})
                    for rootrow in role_links.values():
                        entry = {"git_acquisition_id": rootrow["git_acquisition_id"]}
                        if entry not in inputs:
                            inputs.append(entry)
                    result = self.facts.model.create_result(
                        self.facts.profile(),
                        repository_uuidv4=repo["repository_uuidv4"],
                        inputs=inputs,
                        derivation={"parser": PARSER, "kind": "code"},
                    )
                    self.facts.choose(
                        result,
                        fact_kind="code",
                        change_request_id=pr["change_request_id"],
                    )
                    code = s.execute(
                        "INSERT INTO code_observations(code_observation_uuidv4,repository_uuidv4,parsed_result_uuidv4,change_request_id,change_request_observation_id,commit_code_listing_id,file_code_listing_id,state,object_format,head_oid,base_oid,details) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            str(uuid.uuid4()),
                            repo["repository_uuidv4"],
                            result,
                            pr["change_request_id"],
                            current,
                            commit_listing,
                            file_listing,
                            state,
                            algorithm,
                            head,
                            base,
                            canonical(
                                {
                                    "api_head_base_stable": same,
                                    "code_inputs_complete": inputs_complete,
                                    "merge": merge,
                                    "expected_roles": {
                                        role: value
                                        for role, value in role_oids.items()
                                        if value
                                    },
                                    "missing_roles": missing_roles,
                                    "provider_limits": {"commits": 250, "files": 3000},
                                }
                            ),
                        ),
                    ).lastrowid
                    for role, rootrow in role_links.items():
                        s.execute(
                            "INSERT INTO code_acquisitions(code_observation_id,role,object_format,oid,acquisition_root_id) VALUES(?,?,?,?,?)",
                            (
                                code,
                                role,
                                rootrow["object_format"],
                                rootrow["oid"],
                                rootrow["acquisition_root_id"],
                            ),
                        )
                        if not s.one(
                            "SELECT 1 FROM root_origins WHERE acquisition_root_id=? AND change_request_observation_id=?",
                            (rootrow["acquisition_root_id"], current),
                        ):
                            s.execute(
                                "INSERT INTO root_origins(acquisition_root_id,origin_kind,source_ordinal,change_request_id,change_request_observation_id,repository_uuidv4) VALUES(?,'pr_role',?,?,?,?)",
                                (
                                    rootrow["acquisition_root_id"],
                                    s.one(
                                        "SELECT coalesce(max(source_ordinal),-1)+1 FROM root_origins WHERE acquisition_root_id=? AND origin_kind='pr_role'",
                                        (rootrow["acquisition_root_id"],),
                                    )[0],
                                    pr["change_request_id"],
                                    current,
                                    repo["repository_uuidv4"],
                                ),
                            )
                    code_observed_at_us = s.one(
                        "SELECT MAX(o.observed_at_us) FROM (SELECT fetch_collection_id,observed_at_us FROM fetch_occurrences UNION ALL SELECT fetch_collection_id,observed_at_us FROM current_collection_pages UNION ALL SELECT fetch_collection_id,observed_at_us FROM completion_markers WHERE asserted_state='partial' AND ?) o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id WHERE f.repository_uuidv4=? AND f.change_request_id=? AND f.source_id=? AND p.job_id=? AND f.kind IN ('pr-detail','pr-code-check','pr-commits','pr-files','review','threads','thread-comments')",
                        (
                            state != "complete",
                            repo["repository_uuidv4"],
                            pr["change_request_id"],
                            repo["source_id"],
                            job,
                        ),
                    )[0]
                    if (
                        state == "complete"
                        and not code_failures
                        or observed_incomplete_code
                    ):
                        self.coverage_claim(
                            repo["repository_uuidv4"],
                            "pr-code",
                            state,
                            code_observed_at_us,
                            {
                                "parsed_result_uuidv4": result,
                                "fetch_collection_ids": [
                                    row[0]
                                    for row in s.all(
                                        "SELECT DISTINCT f.fetch_collection_id FROM parsed_result_inputs i "
                                        "JOIN fetch_occurrences o USING(fetch_occurrence_uuidv4) "
                                        "JOIN fetch_collections f USING(fetch_collection_id) "
                                        "WHERE i.parsed_result_uuidv4=? AND f.kind IN "
                                        "('pr-detail','pr-code-check','pr-commits','pr-files','review','threads','thread-comments') "
                                        "ORDER BY f.fetch_collection_id",
                                        (result,),
                                    )
                                ],
                                "git_acquisition_ids": sorted(
                                    {
                                        item["git_acquisition_id"]
                                        for item in inputs
                                        if "git_acquisition_id" in item
                                    }
                                ),
                                **({"missing": code_failures} if code_failures else {}),
                            },
                            change_request_id=pr["change_request_id"],
                        )
                    self.facts.publish()
                if len(failures) != initial_failures:
                    continue
            document_failures = [
                failure
                for failure in failures
                if document_scope_includes(failure["kind"])
            ]
            with s.transaction():
                for component, missing in (
                    ("pr-documents", document_failures),
                    ("pr", failures),
                ):
                    documents_only = component == "pr-documents"
                    observed_incomplete = any(
                        not documents_only or document_scope_includes(kind)
                        for _, _, kind in self.observed_partial_scopes
                    )
                    if missing and not observed_incomplete:
                        # Failed work with no observed incomplete response is progress,
                        # not a newer assessment of the saved repository coverage.
                        continue
                    self.coverage_claim(
                        repo["repository_uuidv4"],
                        component,
                        "partial" if missing else "complete",
                        self.summary_observed_at_us(
                            repo,
                            job,
                            documents_only=documents_only,
                            include_partial=bool(missing),
                        ),
                        {
                            "fetch_collection_ids": self.summary_collection_ids(
                                repo, job, documents_only=documents_only
                            ),
                            "change_request_ids": sorted(
                                pr["change_request_id"] for pr in prs
                            ),
                            **(
                                {
                                    "parsed_result_uuidv4s": [
                                        row[0]
                                        for row in s.all(
                                            "SELECT DISTINCT parsed_result_uuidv4 FROM current_code_observations "
                                            "WHERE repository_uuidv4=? AND state='complete' "
                                            "ORDER BY parsed_result_uuidv4",
                                            (repo["repository_uuidv4"],),
                                        )
                                    ]
                                }
                                if not documents_only
                                else {}
                            ),
                            **({"missing": missing} if missing else {}),
                        },
                    )
                self.facts.publish()
            if self.facts.unselected_results:
                failures.append(
                    {
                        "kind": "parser-selection",
                        "reason": "PARSER_SELECTION_UNRESOLVED",
                        "parsed_results": sorted(self.facts.unselected_results),
                    }
                )
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
                "pull_requests": len(prs),
                **(
                    {"recording_diagnostics": self.recording_diagnostics}
                    if self.recording_diagnostics
                    else {}
                ),
            }
        finally:
            if self.owned:
                self.http.close()

    def code_check(self, repo, pr, job, url, observation):
        # A transport failure adds no new evidence or incomplete saved listing.
        response = self.request_get(url, repo)
        with self.s.transaction():
            self.facts.fence(job)
            collection = self.facts.begin(
                repo,
                pr["change_request_id"],
                "pr-code-check",
                job,
                url,
                {"observation": observation, "attempt": self.s.expected_attempt},
            )
        try:
            value = self.rest_json(response)
            with self.s.transaction():
                self.facts.fence(job)
                occurrence, _, timestamp = self.facts.page(
                    collection, response, {"url": url, "method": "GET"}, None
                )
                self.ensure_pr(repo, value, collection, occurrence, 0, timestamp)
                self.facts.finish(collection)
                self.facts.publish()
        except CatalogError as error:
            self.partial_rest_collection(
                repo,
                pr["change_request_id"],
                "pr-code-check",
                job,
                collection,
                error,
                response,
                url,
            )
            raise
        selected = self.s.one(
            "SELECT change_request_observation_id FROM current_change_request_observations WHERE change_request_id=?",
            (pr["change_request_id"],),
        )
        if selected is None:
            raise CatalogError(
                "PARSER_SELECTION_UNRESOLVED",
                "Acquisition saved; an explicit parser/fact selection is required",
            )
        response.extensions["catalog_observation_id"] = selected[0]
        response.extensions["catalog_observed_at_us"] = timestamp
        return response
