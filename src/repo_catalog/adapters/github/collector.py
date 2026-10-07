from __future__ import annotations

import json
from importlib.resources import files
from urllib.parse import urlencode, urljoin, urlsplit

from repo_catalog.adapters.github.identity import database_resource_id
from repo_catalog.adapters.github.persistence import (
    PARSER,
    ApiFacts,
    canonical,
    oid_context,
)
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.domain.models import CatalogError, Waiting
from repo_catalog.domain.time import format_iso8601_us, now_us


class GitHubCollector:
    """Explicit acquisition into ordinary catalog3 facts; no legacy write model."""

    def __init__(
        self, store, token, transport=None, *, config=None, repository_endpoint_id=None
    ):
        self.s, self.token = store, token
        self.cfg = config or store.config["github"]
        self.repository_endpoint_id = repository_endpoint_id
        self.http = transport or GitHubTransport(self.cfg, token)
        self.owned = transport is None
        self.inventory_uncertainty = None
        self.inventory_evidence = []
        self.facts = ApiFacts(store, self.cfg)
        self.authorized_prs = {}
        self.observed_partial_scopes = set()

    def coverage_claim(
        self,
        repo,
        change_request_id,
        kind,
        state,
        observed_at_us,
        details_json=None,
    ):
        if observed_at_us is None:
            return
        repository_id = repo["repository_id"]
        self.s.coverage(
            repository_id,
            kind,
            state,
            details_json,
            observed_at_us=observed_at_us,
            change_request_id=change_request_id,
        )
        if state == "partial":
            current = self.s.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage WHERE repository_id=? AND change_request_id IS ? AND kind=?",
                (repository_id, change_request_id, kind),
            )
            if (
                current
                and current["observed_at_us"] == observed_at_us
                and current["coverage_state"] in ("partial", "conflict")
            ):
                self.observed_partial_scopes.add(
                    (repository_id, change_request_id, kind)
                )

    def collection_coverage(self, repo, pr, kind, collection, state, *, reason=None):
        self.coverage_claim(
            repo,
            pr,
            kind,
            state,
            self.facts.observed_at_us(collection),
            {"reason": reason} if reason else None,
        )

    def summary_observed_at_us(self, repo, job, *, documents_only=False):
        return self.s.one(
            "SELECT MAX(o.observed_at_us) FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id WHERE f.repository_id=? AND f.source_id=? AND p.job_id=?"
            + (
                " AND f.kind NOT IN ('pr-commits','pr-files','timeline')"
                if documents_only
                else ""
            ),
            (repo["repository_id"], repo["source_id"], job),
        )[0]

    def request_get(self, url, repo=None, **kwargs):
        seen = set()
        while True:
            if url in seen:
                raise CatalogError("PAGINATION_CYCLE", "API redirect cycle")
            seen.add(url)
            response = self.http.request("GET", url, **kwargs)
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
            with self.s.transaction():
                self.s.execute(
                    "UPDATE repositories SET name=? WHERE repository_id=?",
                    (name, repo["repository_id"]),
                )
                if not self.s.one(
                    "SELECT 1 FROM repository_name_assertions WHERE repository_id=? AND name=?",
                    (repo["repository_id"], name),
                ):
                    self.s.execute(
                        "INSERT INTO repository_name_assertions(repository_id,name,observed_at_us) VALUES(?,?,?)",
                        (repo["repository_id"], name, now_us()),
                    )
                self.s.publish()
            url = target

    def inventory_request(self, method, url, **kwargs):
        response = self.http.request(method, url, **kwargs)
        with self.s.transaction():
            payload_id = self.facts.payload(response.content)
            self.inventory_evidence.append(
                {
                    "payload_id": payload_id,
                    "url": url,
                    "method": method,
                    "observed_at_us": now_us(),
                    "etag": response.headers.get("etag"),
                    "next_url": self.http.next_url(response),
                }
            )
        return response

    def inventory(self, source, job):
        cfg = json.loads(source["settings"])
        owner = cfg["owner"]
        base = self.http.base
        try:
            identity = self.inventory_request("GET", base + "/user").json()
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
                    payload = self.inventory_request(
                        "GET", base + "/repos/" + owner + "/" + name
                    ).json()
                    if (
                        payload.get("full_name", "").lower()
                        != f"{owner}/{name}".lower()
                    ):
                        raise CatalogError(
                            "SCOPE_MISMATCH", "Selected repository identity changed"
                        )
                    provider = str(payload["id"])
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
                user = self.inventory_request("GET", base + "/users/" + owner).json()
                if user.get("type") == "Organization":
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
                response = self.inventory_request("GET", url)
                values = response.json()
                if not isinstance(values, list):
                    raise CatalogError("API_SCHEMA", "Expected repository list")
                for r in values:
                    if not r.get("id") or not r.get("full_name"):
                        raise CatalogError("API_SCHEMA", "Repository identity missing")
                    if r["full_name"].split("/")[0].lower() != owner.lower():
                        raise CatalogError(
                            "SCOPE_MISMATCH",
                            "Inventory returned repository outside owner scope",
                        )
                    provider = str(r["id"])
                    clone = cfg.get("clone_url_overrides", {}).get(
                        provider, r.get("clone_url")
                    )
                    if not clone:
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
            if listing_kind and reuse:
                imported = self.imported_listing(
                    repo, pr, listing_kind, job, url, context, reported, cap
                )
                if imported:
                    return imported
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
                try:
                    values = response.json()
                except (ValueError, UnicodeError):
                    raise CatalogError(
                        "API_SCHEMA", "Malformed JSON collection page"
                    ) from None
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
                        normalizer(
                            value,
                            collection,
                            occurrence,
                            ordinal * 10000 + position,
                            timestamp,
                            listing[0] if listing else None,
                        )
                    if listing:
                        s.execute(
                            "UPDATE code_listing_progress SET page_count=page_count+1,terminal=? WHERE code_listing_id=?",
                            (int(next_url is None), listing[0]),
                        )
                    s.publish()
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
                s.publish()
            return collection["fetch_collection_id"], listing[0] if listing else None
        except CatalogError as error:
            with s.transaction():
                if response is not None and uncommitted:
                    self.facts.fence(job)
                    occurrence, _, _ = self.facts.page(
                        collection,
                        response,
                        {
                            "url": url,
                            "method": "GET",
                            "normalization_error": error.code,
                        },
                        url,
                        advance=False,
                    )
                    payload_id = s.one(
                        "SELECT payload_id FROM fetch_occurrences WHERE fetch_occurrence_id=?",
                        (occurrence,),
                    )[0]
                    s.execute(
                        "INSERT INTO unresolved_payloads(payload_id,reason) VALUES(?,?)",
                        (
                            payload_id,
                            canonical(
                                {
                                    "code": error.code,
                                    "fetch_collection_id": collection[
                                        "fetch_collection_id"
                                    ],
                                    "fetch_occurrence_id": occurrence,
                                }
                            ),
                        ),
                    )
                self.facts.partial(collection, error.code)
                if error.code not in ("CANCELLED", "STALE_ATTEMPT") and (
                    self.facts.pending_response(collection) or error.code == "API_CAP"
                ):
                    # A saved prefix or rejected response needs another acquisition.
                    # A committed terminal page interrupted before finish does not.
                    self.collection_coverage(
                        repo, pr, kind, collection, "partial", reason=error.code
                    )
                s.publish()
            raise

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
        if type(value.get("number")) is not int or value["number"] <= 0:
            raise CatalogError("API_SCHEMA", "PR number missing")
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
            else f"{repo['repository_id']}:{value['number']}"
        )
        if not row:
            s.execute(
                "INSERT INTO change_requests(change_request_id,repository_id,repository_binding_id,change_request_kind,provider_change_request_number,current_change_request_observation_id) VALUES(?,?,?,'pull_request',?,NULL)",
                (
                    ident,
                    repo["repository_id"],
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
        observation = (
            existing[0]
            if existing
            else s.execute(
                "INSERT INTO change_request_observations(change_request_id,observed_at_us,published,payload,origin_key,parsed_at_us,origin_fetch_occurrence_id) VALUES(?,?,?,?,?,?,?)",
                (
                    ident,
                    timestamp,
                    int(publish or not row),
                    canonical(value),
                    origin,
                    now_us(),
                    occurrence,
                ),
            ).lastrowid
        )
        if publish or not row:
            s.execute(
                "UPDATE change_requests SET current_change_request_observation_id=? WHERE change_request_id=?",
                (observation, ident),
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
            imported_validator = False
            if not validator:
                validator = self.imported_validator(
                    repo, url, collection["resume_scope_id"]
                )
                imported_validator = validator is not None
        if collection["state"] == "complete":
            row = self.s.one(
                "SELECT o.* FROM change_request_observations o JOIN fetch_occurrences f ON f.fetch_occurrence_id=o.origin_fetch_occurrence_id WHERE f.fetch_collection_id=? ORDER BY f.ordinal DESC,o.change_request_observation_id DESC LIMIT 1",
                (collection["fetch_collection_id"],),
            )
            if row:
                value = json.loads(row["payload"])
                self.authorized_prs[(pr["change_request_id"], *oid_context(value))] = (
                    row["observed_at_us"]
                )
                return value, row["change_request_observation_id"]
            current = self.s.one(
                "SELECT p.current_change_request_observation_id,o.payload,o.observed_at_us FROM change_requests p JOIN change_request_observations o ON o.change_request_observation_id=p.current_change_request_observation_id WHERE p.change_request_id=?",
                (pr["change_request_id"],),
            )
            value = json.loads(current["payload"])
            self.authorized_prs[(pr["change_request_id"], *oid_context(value))] = (
                current["observed_at_us"]
            )
            return value, current["current_change_request_observation_id"]
        headers = {"If-None-Match": validator["etag"]} if validator else {}
        response = self.request_get(url, repo, headers=headers)
        if response.status_code == 304:
            payload = (
                self.s.one(
                    "SELECT body FROM payloads WHERE payload_id=?",
                    (validator["payload_id"],),
                )
                if validator
                else None
            )
            if payload:
                value = json.loads(payload[0])
                admitted = self.s.one(
                    "SELECT p.current_change_request_observation_id,o.payload FROM change_requests p JOIN change_request_observations o ON o.change_request_observation_id=p.current_change_request_observation_id WHERE p.change_request_id=?",
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
                        evidence={"status": 304, "payload_id": validator["payload_id"]},
                        observed_at_us=validated_at_us,
                    )
                    if imported_validator:
                        self.s.execute(
                            "INSERT INTO validators(resume_scope_id,validator_key,etag,payload_id,validated_at_us) VALUES(?,'representation',?,?,?)",
                            (
                                collection["resume_scope_id"],
                                validator["etag"],
                                validator["payload_id"],
                                validated_at_us,
                            ),
                        )
                    else:
                        self.s.execute(
                            "UPDATE validators SET validated_at_us=? WHERE resume_scope_id=? AND validator_key='representation'",
                            (validated_at_us, collection["resume_scope_id"]),
                        )
                    self.s.publish()
                self.authorized_prs[(pr["change_request_id"], *oid_context(value))] = (
                    validated_at_us
                )
                return value, current
            response = self.request_get(url, repo)
            if response.status_code == 304:
                raise CatalogError("API_SCHEMA", "304 without saved representation")
        value = response.json()
        with self.s.transaction():
            self.facts.fence(job)
            occurrence, _, timestamp = self.facts.page(
                collection, response, {"url": url, "method": "GET"}, None
            )
            self.ensure_pr(repo, value, collection, occurrence, 0, timestamp)
            if response.headers.get("etag"):
                payload_id = self.facts.payload(response.content)
                if validator and not imported_validator:
                    self.s.execute(
                        "UPDATE validators SET etag=?,payload_id=?,validated_at_us=? WHERE resume_scope_id=? AND validator_key='representation'",
                        (
                            response.headers["etag"],
                            payload_id,
                            timestamp,
                            collection["resume_scope_id"],
                        ),
                    )
                else:
                    self.s.execute(
                        "INSERT INTO validators(resume_scope_id,validator_key,etag,payload_id,validated_at_us) VALUES(?,'representation',?,?,?)",
                        (
                            collection["resume_scope_id"],
                            response.headers["etag"],
                            payload_id,
                            timestamp,
                        ),
                    )
            self.facts.finish(collection)
            self.s.publish()
        current = self.s.one(
            "SELECT current_change_request_observation_id FROM change_requests WHERE change_request_id=?",
            (pr["change_request_id"],),
        )[0]
        self.authorized_prs[(pr["change_request_id"], *oid_context(value))] = timestamp
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
            "SELECT f.fetch_collection_id,f.observed_at_us,s.endpoint FROM fetch_collections f JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id JOIN resume_scopes s ON s.resume_scope_id=f.resume_scope_id WHERE f.repository_id=? AND f.kind=? AND p.job_id=? AND s.source_id=? AND s.principal_ref=? AND s.api_version=? AND s.parser_version=? AND s.profile_version=? AND s.confidence='proven' ORDER BY f.observed_at_us DESC LIMIT 1",
            (
                repo["repository_id"],
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
            pr = self.s.one(
                "SELECT change_request_id FROM change_requests WHERE repository_id=? AND provider_change_request_number=?",
                (repo["repository_id"], number),
            )
            if not pr:
                payload_id = self.s.one(
                    "SELECT payload_id FROM fetch_occurrences WHERE fetch_occurrence_id=?",
                    (occurrence,),
                )[0]
                self.s.execute(
                    "INSERT INTO unresolved_payloads(payload_id,reason) VALUES(?,?)",
                    (
                        payload_id,
                        canonical(
                            {
                                "code": "COMMENT_PARENT_UNKNOWN",
                                "number": number,
                                "kind": kind,
                                "position": position,
                            }
                        ),
                    ),
                )
                return
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
            self.s.publish()

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

    def failed_graphql_page(
        self, collection, response, variables, query, cursor, error
    ):
        """Retain raw rejected evidence in the caller's writer transaction."""
        occurrence, _, _ = self.facts.page(
            collection,
            response,
            {
                "url": self.http.graphql,
                "method": "POST",
                "query": query,
                "variables": variables,
                "normalization_error": error.code,
            },
            cursor,
            advance=False,
        )
        payload_id = self.s.one(
            "SELECT payload_id FROM fetch_occurrences WHERE fetch_occurrence_id=?",
            (occurrence,),
        )[0]
        self.s.execute(
            "INSERT INTO unresolved_payloads(payload_id,reason) VALUES(?,?)",
            (
                payload_id,
                canonical({"code": error.code, "fetch_occurrence_id": occurrence}),
            ),
        )

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
        merge = {}
        if collection["state"] == "complete":
            last = self.s.one(
                "SELECT p.body FROM fetch_occurrences o JOIN payloads p ON p.payload_id=o.payload_id WHERE o.fetch_collection_id=? ORDER BY o.ordinal DESC LIMIT 1",
                (collection["fetch_collection_id"],),
            )
            if last:
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

        def observed_at_us():
            return self.facts.thread_observed_at_us(collection)

        seen = set()
        response, uncommitted = None, False
        try:
            while True:
                response, uncommitted = None, False
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
                        "SELECT o.*,p.body FROM fetch_occurrences o JOIN payloads p ON p.payload_id=o.payload_id WHERE o.fetch_occurrence_id=? AND o.fetch_collection_id=?",
                        (pending["occurrence"], collection["fetch_collection_id"]),
                    )
                    payload = json.loads(page["body"])
                    occurrence, timestamp = (
                        page["fetch_occurrence_id"],
                        page["observed_at_us"],
                    )
                else:
                    response = self.http.request(
                        "POST",
                        self.http.graphql,
                        json={"query": root_query, "variables": variables},
                    )
                    uncommitted = True
                    payload = response.json()
                    p = ((payload.get("data") or {}).get("repository") or {}).get(
                        "pullRequest"
                    ) or {}
                    connection = p.get("reviewThreads") or {}
                    info, next_cursor, valid_info = self._page_info(connection)
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
                        for index, thread in enumerate(connection.get("nodes") or []):
                            review_thread_provider_resource_id = self._thread(
                                repo, pr, thread, timestamp
                            )
                            self._thread_documents(
                                pr,
                                review_thread_provider_resource_id,
                                thread.get("comments") or {},
                                collection,
                                occurrence,
                                index * 10000,
                                timestamp,
                            )
                        # Root page and pending child boundary commit together. Resume
                        # reads this exact page and never records it as a new response.
                        if not payload.get("errors") and valid_info:
                            self.s.execute(
                                "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                                (
                                    canonical(
                                        {"cursor": cursor, "occurrence": occurrence}
                                    ),
                                    collection["fetch_collection_id"],
                                ),
                            )
                        self.s.publish()
                    uncommitted = False
                p = ((payload.get("data") or {}).get("repository") or {}).get(
                    "pullRequest"
                ) or {}
                connection = p.get("reviewThreads") or {}
                merge = self._merge_roles(p)
                if any(
                    e.get("type") == "RATE_LIMITED" for e in payload.get("errors") or []
                ):
                    raise Waiting(
                        "RATE_LIMIT",
                        "GraphQL rate limited",
                        {"not_before_us": self.http.clock_us() + 60_000_000},
                        True,
                    )
                if payload.get("errors"):
                    raise CatalogError(
                        "GRAPHQL_PARTIAL", "GraphQL partial page; cursor retained"
                    )
                info, next_cursor, valid_info = self._page_info(connection)
                if not valid_info:
                    raise CatalogError(
                        "API_SCHEMA", "Missing or invalid thread pageInfo"
                    )
                for thread in connection.get("nodes") or []:
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
                        self.facts.finish(collection, observed_at_us=observed_at_us())
                        self.coverage_claim(
                            repo,
                            pr["change_request_id"],
                            "threads",
                            "complete",
                            observed_at_us(),
                        )
                    self.s.publish()
                if not info.get("hasNextPage"):
                    return merge
        except CatalogError as error:
            with self.s.transaction():
                self.facts.fence(job)
                if response is not None and uncommitted:
                    self.failed_graphql_page(
                        collection, response, variables, root_query, cursor, error
                    )
                if error.details.get("refresh_root"):
                    self.s.execute(
                        "UPDATE collection_progress SET cursor=? WHERE fetch_collection_id=?",
                        (
                            canonical({"cursor": pending.get("cursor")}),
                            collection["fetch_collection_id"],
                        ),
                    )
                self.facts.partial(collection, error.code)
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
                        repo,
                        pr["change_request_id"],
                        "threads",
                        "partial",
                        observed_at_us(),
                        {"reason": error.code},
                    )
                self.s.publish()
            raise

    @staticmethod
    def _page_info(connection):
        info = connection.get("pageInfo")
        if not isinstance(info, dict) or type(info.get("hasNextPage")) is not bool:
            return {}, None, False
        next_cursor = info.get("endCursor") if info["hasNextPage"] else None
        return info, next_cursor, not info["hasNextPage"] or bool(next_cursor)

    @staticmethod
    def _merge_roles(value):
        return {
            role: (value.get(field) or {}).get("oid")
            for role, field in (
                ("merge", "mergeCommit"),
                ("test-merge", "potentialMergeCommit"),
            )
        }

    def _thread(self, repo, pr, thread, timestamp):
        if not isinstance(thread.get("id"), str) or not thread["id"]:
            raise CatalogError("API_SCHEMA", "Thread identity missing")
        provider_resource_id = thread["id"]
        value = canonical(
            {key: item for key, item in thread.items() if key != "comments"}
        )
        if self.s.one(
            "SELECT 1 FROM review_threads WHERE change_request_id=? AND provider_resource_id=?",
            (pr["change_request_id"], provider_resource_id),
        ):
            self.s.execute(
                "UPDATE review_threads SET payload=?,observed_at_us=? WHERE change_request_id=? AND provider_resource_id=?",
                (value, timestamp, pr["change_request_id"], provider_resource_id),
            )
        else:
            self.s.execute(
                "INSERT INTO review_threads(change_request_id,provider_resource_id,payload,observed_at_us) VALUES(?,?,?,?)",
                (pr["change_request_id"], provider_resource_id, value, timestamp),
            )
        return provider_resource_id

    def _thread_documents(
        self,
        pr,
        review_thread_provider_resource_id,
        connection,
        collection,
        occurrence,
        offset,
        timestamp,
    ):
        for position, value in enumerate(connection.get("nodes") or []):
            provider = self.document_provider_id(value, "fullDatabaseId")
            self.facts.document(
                pr["change_request_id"],
                "review-comment",
                str(provider),
                "" if value.get("body") is None else value["body"],
                value,
                collection,
                occurrence,
                offset + position,
                timestamp,
                thread=review_thread_provider_resource_id,
            )

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
        initial = thread.get("comments") or {}
        info, initial_cursor, valid_info = self._page_info(initial)
        if not valid_info:
            raise CatalogError(
                "API_SCHEMA",
                "Missing or invalid nested pageInfo",
                {"refresh_root": True},
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
            "SELECT next_cursor FROM fetch_occurrences WHERE fetch_collection_id=? ORDER BY ordinal DESC LIMIT 1",
            (collection["fetch_collection_id"],),
        )
        cursor = page[0] if page else initial_cursor
        seen = set()
        response, uncommitted = None, False
        try:
            while cursor:
                response, uncommitted = None, False
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
                response = self.http.request(
                    "POST",
                    self.http.graphql,
                    json={"query": query, "variables": variables},
                )
                uncommitted = True
                payload = response.json()
                comments = ((payload.get("data") or {}).get("node") or {}).get(
                    "comments"
                ) or {}
                info, next_cursor, valid_info = self._page_info(comments)
                with self.s.transaction():
                    self.facts.fence(job)
                    occurrence, ordinal, timestamp = self.facts.page(
                        collection,
                        response,
                        {
                            "url": self.http.graphql,
                            "method": "POST",
                            "query": query,
                            "variables": variables,
                        },
                        cursor
                        if payload.get("errors") or not valid_info
                        else next_cursor,
                    )
                    self._thread_documents(
                        pr,
                        review_thread_provider_resource_id,
                        comments,
                        collection,
                        occurrence,
                        ordinal * 10000,
                        timestamp,
                    )
                    self.s.publish()
                uncommitted = False
                if payload.get("errors"):
                    raise CatalogError(
                        "GRAPHQL_PARTIAL", "Thread comments page has errors"
                    )
                if not valid_info:
                    raise CatalogError(
                        "API_SCHEMA", "Missing or invalid nested pageInfo"
                    )
                cursor = next_cursor
            with self.s.transaction():
                self.facts.fence(job)
                self.facts.finish(collection)
                self.s.publish()
        except CatalogError as error:
            with self.s.transaction():
                self.facts.fence(job)
                if response is not None and uncommitted:
                    self.failed_graphql_page(
                        collection, response, variables, query, cursor, error
                    )
                self.facts.partial(collection, error.code)
                self.s.publish()
            raise

    def completed_pr(self, repo, job, pr_id):
        row = self.s.one(
            "SELECT c.code_observation_id,c.head_oid,c.base_oid,c.details,sc.request_context scope_context FROM code_observations c JOIN change_request_observations o ON o.change_request_observation_id=c.change_request_observation_id JOIN fetch_occurrences a ON a.fetch_occurrence_id=o.origin_fetch_occurrence_id JOIN collection_progress p ON p.fetch_collection_id=a.fetch_collection_id JOIN fetch_collections f ON f.fetch_collection_id=p.fetch_collection_id JOIN resume_scopes sc ON sc.resume_scope_id=f.resume_scope_id WHERE p.job_id=? AND c.change_request_id=? AND c.state='complete' AND sc.source_id=? AND sc.principal_ref=? AND sc.api_version=? AND sc.parser_version=? AND sc.profile_version=? AND sc.confidence='proven' ORDER BY c.code_observation_id DESC LIMIT 1",
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

    def sync(self, repo, job):
        s = self.s
        root = f"{self.http.base}/repos/{repo['name']}"
        failures, waiting = [], None
        self.observed_partial_scopes.clear()

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
                ("review-comment", root + "/pulls/comments", "pull_request_url"),
            ):
                attempt(
                    kind + "-incremental",
                    lambda kind=kind, endpoint=endpoint, parent=parent: (
                        self.incremental_comments(repo, job, kind, endpoint, parent)
                    ),
                )
            prs = s.all(
                "SELECT p.*,o.payload FROM change_requests p LEFT JOIN change_request_observations o ON o.change_request_observation_id=p.current_change_request_observation_id WHERE p.repository_id=? ORDER BY p.provider_change_request_number",
                (repo["repository_id"],),
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
                        lambda kind=kind, endpoint=endpoint: self.collection(
                            repo,
                            pr["change_request_id"],
                            kind,
                            job,
                            endpoint + f"?per_page={size}",
                            self._document_normalizer(pr["change_request_id"], kind),
                        ),
                    )

                def event(value, collection, occurrence, position, timestamp, listing):
                    s.execute(
                        "INSERT INTO change_request_events(change_request_id,origin_key,ordinal,provider_event_id,payload,observed_at_us) VALUES(?,?,?,?,?,?)",
                        (
                            pr["change_request_id"],
                            self.facts.origin(collection, occurrence, position),
                            position,
                            str(value["id"]) if value.get("id") is not None else None,
                            canonical(value),
                            timestamp,
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
                merge = attempt("threads", lambda: self.threads(repo, pr, job)) or {}
                if not current:
                    continue
                algorithm, head, base = oid_context(before)

                def commit(value, collection, occurrence, position, timestamp, listing):
                    from repo_catalog.domain.models import GitOid

                    if not value.get("sha") or not algorithm:
                        raise CatalogError("API_SCHEMA", "PR commit OID missing")
                    oid = GitOid.parse(algorithm + ":" + value["sha"]).value
                    s.execute(
                        "INSERT INTO code_commits(code_listing_id,fetch_occurrence_id,position,object_format,oid,payload) VALUES(?,?,?,?,?,?)",
                        (
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
                        "INSERT INTO code_file_changes(code_listing_id,fetch_occurrence_id,position,raw_path,payload) VALUES(?,?,?,?,?)",
                        (
                            listing,
                            occurrence,
                            position,
                            value["filename"].encode("utf-8"),
                            canonical(value),
                        ),
                    )

                code_context_failures = [
                    failure
                    for failure in failures[initial_failures:]
                    if failure["kind"] in {"pr-detail", "review", "threads"}
                ]
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
                state = (
                    "complete"
                    if (
                        same
                        and not code_context_failures
                        and len(failures) == oldfail
                        and commits
                        and files_result
                    )
                    else "partial"
                )
                if not same:
                    failures.append({"kind": "pr-code", "reason": "PR_CODE_RACE"})

                # Failed listings still retain their IDs and early pages.
                def code_listing_id(kind):
                    row = s.one(
                        "SELECT l.code_listing_id FROM code_listings l JOIN collection_progress p ON p.fetch_collection_id=l.fetch_collection_id WHERE l.change_request_id=? AND l.kind=? AND l.head_oid IS ? AND l.base_oid IS ? ORDER BY (p.job_id=?) DESC,l.code_listing_id DESC LIMIT 1",
                        (pr["change_request_id"], kind, head, base, job),
                    )
                    return row[0] if row else None

                role_oids = {
                    "head": (before.get("head") or {}).get("sha"),
                    "base": (before.get("base") or {}).get("sha"),
                    **merge,
                }
                for review in s.all(
                    "SELECT payload FROM reviews WHERE change_request_id=?",
                    (pr["change_request_id"],),
                ):
                    value = json.loads(review[0]).get("commit_id")
                    if value:
                        role_oids["review-target:" + value] = value
                with s.transaction():
                    self.facts.fence(job)
                    code = s.execute(
                        "INSERT INTO code_observations(change_request_id,change_request_observation_id,commit_code_listing_id,file_code_listing_id,state,object_format,head_oid,base_oid,details) VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            pr["change_request_id"],
                            current,
                            commits[1] if commits else code_listing_id("commits"),
                            files_result[1]
                            if files_result
                            else code_listing_id("files"),
                            state,
                            algorithm,
                            head,
                            base,
                            canonical(
                                {
                                    "api_head_base_stable": same,
                                    "merge": merge,
                                    "expected_roles": {
                                        role: value
                                        for role, value in role_oids.items()
                                        if value
                                    },
                                    "provider_limits": {"commits": 250, "files": 3000},
                                }
                            ),
                        ),
                    ).lastrowid
                    s.publish()
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
                    if fetched:
                        with s.transaction():
                            for rootrow in s.all(
                                "SELECT * FROM acquisition_roots WHERE git_acquisition_id=? AND oid=?",
                                (
                                    fetched["git_acquisition_id"],
                                    bytes.fromhex(expected),
                                ),
                            ):
                                if not s.one(
                                    "SELECT 1 FROM code_acquisitions WHERE code_observation_id=? AND role=?",
                                    (code, role),
                                ):
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
                                        "INSERT INTO root_origins(acquisition_root_id,origin_kind,source_ordinal,change_request_id,change_request_observation_id,repository_id) VALUES(?,'pr_role',?,?,?,?)",
                                        (
                                            rootrow["acquisition_root_id"],
                                            s.one(
                                                "SELECT coalesce(max(source_ordinal),-1)+1 FROM root_origins WHERE acquisition_root_id=? AND origin_kind='pr_role'",
                                                (rootrow["acquisition_root_id"],),
                                            )[0],
                                            pr["change_request_id"],
                                            current,
                                            repo["repository_id"],
                                        ),
                                    )
                            s.publish()
                linked_roles = {
                    row["role"]
                    for row in s.all(
                        "SELECT role FROM code_acquisitions WHERE code_observation_id=?",
                        (code,),
                    )
                }
                missing_roles = sorted(
                    role
                    for role, expected in role_oids.items()
                    if expected and role not in linked_roles
                )
                runtime_code_failures = failures[oldfail:]
                code_failures = [*code_context_failures, *runtime_code_failures]
                if missing_roles and not code_failures:
                    missing_failure = {
                        "kind": "pr-git",
                        "reason": "PR_CODE_ROLE_MISSING",
                        "roles": missing_roles,
                    }
                    failures.append(missing_failure)
                    code_failures.append(missing_failure)
                observed_incomplete_code = (
                    bool(code_context_failures)
                    or not same
                    or bool(missing_roles)
                    or any(
                        (
                            repo["repository_id"],
                            pr["change_request_id"],
                            kind,
                        )
                        in self.observed_partial_scopes
                        for kind in ("pr-commits", "pr-files")
                    )
                )
                if after_response is not None and (
                    not code_failures or observed_incomplete_code
                ):
                    partial_code = bool(code_failures or missing_roles)
                    details = (
                        {
                            "missing": code_failures,
                            "missing_roles": missing_roles,
                        }
                        if partial_code
                        else None
                    )
                    with s.transaction():
                        self.coverage_claim(
                            repo,
                            pr["change_request_id"],
                            "pr-code",
                            "partial" if partial_code else "complete",
                            after_response.extensions["catalog_observed_at_us"],
                            details,
                        )
                        s.publish()
                if len(failures) != initial_failures:
                    continue
            document_failures = [
                failure
                for failure in failures
                if failure["kind"]
                not in {"pr-git", "pr-code", "pr-commits", "pr-files", "timeline"}
            ]
            with s.transaction():
                for component, missing in (
                    ("pr-documents", document_failures),
                    ("pr", failures),
                ):
                    documents_only = component == "pr-documents"
                    observed_incomplete = any(
                        not documents_only
                        or kind
                        not in (
                            "pr-git",
                            "pr-code",
                            "pr-commits",
                            "pr-files",
                            "timeline",
                        )
                        for _, _, kind in self.observed_partial_scopes
                    )
                    if missing and not observed_incomplete:
                        # Failed work with no observed incomplete response is progress,
                        # not a newer assessment of the saved repository coverage.
                        continue
                    self.coverage_claim(
                        repo,
                        None,
                        component,
                        "partial" if missing else "complete",
                        self.summary_observed_at_us(
                            repo, job, documents_only=documents_only
                        ),
                        {"missing": missing} if missing else None,
                    )
                s.publish()
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
                "repository_id": repo["repository_id"],
                "state": "complete",
                "pull_requests": len(prs),
            }
        finally:
            if self.owned:
                self.http.close()

    def imported_validator(self, repo, url, runtime_scope):
        """A legacy validator can issue a conditional request, never skip one."""
        binding = self.s.one(
            "SELECT repository_binding_id FROM resume_scopes WHERE resume_scope_id=?",
            (runtime_scope,),
        )[0]
        candidates = self.s.all(
            "SELECT v.*,sc.request_context,sc.principal_ref FROM validators v JOIN resume_scopes sc ON sc.resume_scope_id=v.resume_scope_id WHERE sc.repository_id=? AND sc.repository_binding_id=? AND sc.source_id=? AND sc.endpoint=? AND sc.api_version=? AND sc.confidence='legacy_unknown' AND sc.parser_version='v1' ORDER BY v.validated_at_us DESC",
            (
                repo["repository_id"],
                binding,
                repo["source_id"],
                url,
                self.cfg["rest_api_version"],
            ),
        )
        for validator in candidates:
            context = json.loads(validator["request_context"])
            if (
                validator["principal_ref"] is not None
                and validator["principal_ref"] != self.facts.principal
                or str(context.get("repo")) != repo["provider_repository_id"]
                or context.get("source") != repo["source_id"]
                or context.get("accept") != "application/vnd.github+json"
            ):
                continue
            if (
                context.get("permissions") is not None
                and context["permissions"] != self.facts.permissions
            ):
                continue
            return validator
        return None

    def imported_listing(self, repo, pr, kind, job, url, context, reported, cap):
        """Reuse deterministic saved head/base listings after current authorization.

        This does not make a historical cursor or watermark reusable. The
        importer's completed marker proves terminal, contiguous, matching saved
        pages and head/base fencing. We additionally check the current API,
        binding, endpoint, principal where known, exact OIDs and reported count.
        """
        algorithm, head, base = oid_context(context or {})
        authorization_key = (pr, algorithm, head, base)
        if (
            not algorithm
            or not head
            or not base
            or type(reported) is not int
            or authorization_key not in self.authorized_prs
            or self.authorized_prs[authorization_key] is None
        ):
            return None
        authorization_observed_at_us = self.authorized_prs[authorization_key]
        binding = self.s.one(
            "SELECT repository_binding_id FROM change_requests WHERE change_request_id=?",
            (pr,),
        )[0]
        rows = self.s.all(
            "SELECT l.*,sc.endpoint,sc.principal_ref,sc.request_context,sc.profile_version,p.page_count FROM code_listings l JOIN code_listing_progress p ON p.code_listing_id=l.code_listing_id JOIN resume_scopes sc ON sc.resume_scope_id=l.resume_scope_id WHERE l.change_request_id=? AND l.kind=? AND l.object_format=? AND l.head_oid=? AND l.base_oid=? AND p.state='complete' AND p.terminal=1 AND p.context_proven=1 AND sc.repository_id=? AND sc.repository_binding_id=? AND sc.source_id=? AND sc.api_version=? AND sc.parser_version='v1' AND sc.confidence='legacy_unknown'",
            (
                pr,
                kind,
                algorithm,
                head,
                base,
                repo["repository_id"],
                binding,
                repo["source_id"],
                self.cfg["rest_api_version"],
            ),
        )
        for listing in rows:
            if (
                listing["principal_ref"] is not None
                and listing["principal_ref"] != self.facts.principal
            ):
                continue
            if not listing["endpoint"]:
                continue
            old, current = urlsplit(listing["endpoint"]), urlsplit(url)
            if (old.scheme, old.netloc, old.path) != (
                current.scheme,
                current.netloc,
                current.path,
            ):
                continue
            prior_context = json.loads(listing["request_context"])
            # Supported v1 REST lists contain exact raw JSON membership/OIDs/paths;
            # Git text preservation profiles do not change those deterministic
            # lists. Unknown cursor/profile assertions are never promoted. A
            # known conflicting profile/parser/API/context still forces refresh.
            if (
                listing["profile_version"]
                not in ("legacy_unknown", self.s.config["preservation"]["profile"])
                or prior_context.get("repository_id") != repo["repository_id"]
                or prior_context.get("accept", "application/vnd.github+json")
                != "application/vnd.github+json"
                or prior_context.get("api_version", self.cfg["rest_api_version"])
                != self.cfg["rest_api_version"]
            ):
                continue
            if (
                prior_context.get("permissions") is not None
                and prior_context["permissions"] != self.facts.permissions
            ):
                continue
            table = "code_commits" if kind == "commits" else "code_file_changes"
            count = self.s.one(
                f"SELECT count(*) FROM {table} WHERE code_listing_id=?",
                (listing["code_listing_id"],),
            )[0]
            if count != reported or cap and count >= cap:
                continue
            marker = self.s.one(
                "SELECT 1 FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='complete' AND observed_at_us=? AND json_extract(evidence,'$.boundary')='authenticated-current-head-base'",
                (listing["fetch_collection_id"], authorization_observed_at_us),
            )
            if marker is None:
                self.s.execute(
                    "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,?)",
                    (
                        listing["resume_scope_id"],
                        listing["fetch_collection_id"],
                        canonical(
                            {
                                "boundary": "authenticated-current-head-base",
                                "principal": self.facts.principal,
                                "job_id": job,
                                "parser": PARSER,
                                "profile": self.s.config["preservation"]["profile"],
                                "legacy_profile": listing["profile_version"],
                                "profile_admission": "REST membership and raw paths independent of Git text retention",
                                "saved_parser": "v1",
                                "parser_admission": "imported terminal contiguous raw pages and matching normalized items",
                                "reported": reported,
                                "head": head.hex(),
                                "base": base.hex(),
                                "legacy_cursor_reused": False,
                            }
                        ),
                        authorization_observed_at_us,
                    ),
                )
                self.s.publish()
            return listing["fetch_collection_id"], listing["code_listing_id"]
        return None

    def code_check(self, repo, pr, job, url, observation):
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
            occurrence, _, timestamp = self.facts.page(
                collection, response, {"url": url, "method": "GET"}, None
            )
            self.ensure_pr(repo, response.json(), collection, occurrence, 0, timestamp)
            self.facts.finish(collection)
            self.s.publish()
        response.extensions["catalog_observation_id"] = self.s.one(
            "SELECT current_change_request_observation_id FROM change_requests WHERE change_request_id=?",
            (pr["change_request_id"],),
        )[0]
        response.extensions["catalog_observed_at_us"] = timestamp
        return response
