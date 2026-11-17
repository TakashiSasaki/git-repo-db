"""Bounded GitHub HTTP acquisition into the separated Context authority.

Transport settings are invocation inputs, never Provider registrations. Every
HTTP attempt (including internal retries) spends the original durable request.
Complete atomic pages are admitted immediately; later refusal preserves them.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx

from repo_catalog.adapters.github import production_intake as normalization
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.acquisition_errors import AcquisitionError
from repo_catalog.domain.context_admission import AdmissionRefused
from repo_catalog.domain.models import CatalogError, Waiting
from repo_catalog.domain.p1_context import CoverageScope, ResourceKey, canonical
from repo_catalog.domain.p1_coordination import NotesLimits, RequestIdentity
from repo_catalog.domain.p1_core import CoreFailure, uuid4_value
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.production_context import (
    CollectionObservation,
    SourceInventory,
)
from repo_catalog.domain.provider_acquisition import (
    ProviderCommitContextIntake,
    ProviderFileContextIntake,
    ProviderIntakeBatch,
    ProviderIssueCommentIntake,
    ProviderIssueIntake,
    ProviderPullRequestIntake,
    ProviderRegistration,
    ProviderRepositoryIntake,
    ProviderReviewCommentIntake,
    ProviderReviewIntake,
    ProviderReviewThreadIntake,
    ProviderTimelineIntake,
    SourceRegistration,
    make_provenance,
)
from repo_catalog.domain.retry_deadline import validate_retry_deadline_us
from repo_catalog.domain.time import now_us

_NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")
HTTP_INTAKE_VERSION = "1"
_SECTIONS = frozenset(
    {
        "issues",
        "pull_requests",
        "issue_comments",
        "reviews",
        "review_comments",
        "timeline",
        "pr_commits",
        "pr_files",
        "review_threads",
    }
)


def _positive(value, name, maximum=2**63 - 1):
    if type(value) is not int or not 0 < value <= maximum:
        raise CatalogError("INVALID_ARGUMENT", "Invalid finite " + name)
    return value


def _name(value):
    if (
        type(value) is not str
        or len(value) > 255
        or not _NAME.fullmatch(value)
        or value in {".", ".."}
    ):
        raise CatalogError("INVALID_ARGUMENT", "Invalid GitHub owner/repository")
    return value


class _Token:
    def __init__(self, cancelled):
        self.cancelled = cancelled

    def check(self):
        if self.cancelled():
            raise CatalogError("CANCELLED", "Acquisition cancelled", retryable=True)


class _CountedStream(httpx.SyncByteStream):
    def __init__(self, stream, owner):
        self.stream, self.owner, self.count = stream, owner, 0

    def __iter__(self):
        for chunk in self.stream:
            self.owner.token.check()
            self.count += len(chunk)
            self.owner.network_bytes += len(chunk)
            if self.count > self.owner.response_bytes:
                raise CatalogError("API_RESPONSE_LIMIT", "Finite HTTP input limit")
            yield chunk

    def close(self):
        self.stream.close()


class _MeteredClient:
    """Count raw transport bytes before content decoding, on every attempt.

    Reserve a finite page bound before opening the socket. Unmeasurable failed
    transfers retain that reservation; fully measured transfers settle actual
    bytes. A transport can deliver one chunk beyond the limit; it is counted and
    refused before JSON parsing. No failed work is refunded.
    """

    def __init__(
        self,
        client,
        work,
        token,
        response_bytes,
        max_pages,
        progress,
        before_attempt=lambda: None,
    ):
        self.client, self.work, self.token = client, work, token
        self.response_bytes, self.max_pages = response_bytes, max_pages
        self.network_bytes, self.requests = 0, 0
        self.progress, self.next_slot = progress, 0
        self.before_attempt = before_attempt

    def _claim_attempt(self):
        # A slot is durable before opening a connection. Failed/crashed attempts
        # remain spent; retries and separate invocations cannot reset the bound.
        http_attempt = str(uuid4())
        while self.next_slot < self.max_pages:
            self.work.require("metadata_units", 1)
            self.work.charge("metadata_units", 1)
            coordinate = canonical(["github-http-attempt", self.next_slot])
            self.next_slot += 1
            value = {
                "attempt_uuidv4": self.work.attempt_uuidv4,
                "ordinal": self.requests,
                "http_attempt_uuidv4": http_attempt,
            }
            if self.progress.save_once(coordinate, value) == value:
                return {
                    "attempt_uuidv4": self.work.attempt_uuidv4,
                    "http_attempt_slot": self.next_slot - 1,
                    "http_attempt_uuidv4": http_attempt,
                }
        raise CatalogError("PAGE_LIMIT", "Finite cumulative HTTP attempt limit")

    @contextmanager
    def stream(self, *args, **kwargs):
        self.token.check()
        self.before_attempt()
        read_origin = self._claim_attempt()
        self.work.require("metadata_units", 1)
        self.work.charge("metadata_units", 1)
        self.work.require("input_bytes", self.response_bytes)
        self.requests += 1
        stream = None
        try:
            with self.client.stream(*args, **kwargs) as response:
                stream = _CountedStream(response.stream, self)
                if response.is_stream_consumed:
                    stream.count = len(response.content)
                    self.network_bytes += stream.count
                    if stream.count > self.response_bytes:
                        raise CatalogError(
                            "API_RESPONSE_LIMIT", "Finite HTTP input limit"
                        )
                response.stream = stream
                response.extensions["repo_catalog_http_read_origin"] = read_origin
                yield response
        finally:
            if stream is None or stream.count > self.response_bytes:
                self.work.abandon("input_bytes")
            else:
                self.work.charge("input_bytes", stream.count)


@dataclass(frozen=True)
class GitHubFetchReport:
    request_identity: RequestIdentity
    status: str
    batches: tuple[ProviderIntakeBatch, ...]
    admission_reports: tuple
    network_bytes: int
    http_attempts: int
    failure_code: str | None = None
    not_before_us: int | None = None
    git_reports: tuple = ()


class _SourceProgress:
    """Source-qualified continuations over one genuine parent request budget."""

    def __init__(self, progress, source, intent):
        self.progress, self.source, self.intent = progress, source, intent

    def save_once(self, coordinate, value):
        return self.progress.save_once(
            canonical(
                ["github-source", self.source, self.intent, *json.loads(coordinate)]
            ),
            value,
        )


@contextmanager
def _acquisition_ledger(catalog, shared):
    if shared is None:
        with OperationalAcquisitionLedger(catalog) as ledger:
            yield ledger
    else:
        yield shared[0]


class GitHubProviderFetch:
    """Application owner with injected transport, request budget and admission.

    Callers may collect typed batches without persistence using ``admit=None``.
    Production ``acquire_github`` always supplies authorized Context admission.
    """

    def __init__(
        self,
        transport,
        *,
        service_instance_uuidv4,
        source_registration_uuidv4,
        request_identity,
        work,
        admit=None,
        record_wait=lambda error: None,
        git_roles=None,
    ):
        uuid4_value(service_instance_uuidv4)
        uuid4_value(source_registration_uuidv4)
        self.http, self.service, self.source = (
            transport,
            service_instance_uuidv4,
            source_registration_uuidv4,
        )
        self.request, self.work, self.admit = request_identity, work, admit
        self.record_wait = record_wait
        self.git_roles = git_roles
        self.batches, self.reports = [], []
        self._last_read_origin = None
        self.traversal_uuidv4 = str(uuid4())
        self._terminal_report_ordinal = 0
        self._graphql_partial = False
        self.partial_failure = None

    def _emit(self, **sections):
        additional_sources = sections.pop("sources", ())
        batch = ProviderIntakeBatch(
            self.service,
            providers=(ProviderRegistration(self.service, ensure_only=True),),
            sources=(
                SourceRegistration(self.source, self.service, ensure_only=True),
                *additional_sources,
            ),
            **sections,
        )
        if self.admit is not None:
            self.reports.append(self.admit(batch))
        self.batches.append(batch)

    def _provenance(self, path, *, page=None, collection=False):
        # Source coordinates identify original acquisition, not credentials or
        # caller transport options. Page URL is intentionally excluded.
        return make_provenance(
            "github-http",
            {
                "request_identity": list(self.request.values()),
                "service_instance_uuidv4": self.service,
                "source_registration_uuidv4": self.source,
                "resource_path": path,
                "page": page,
                "traversal_attempt_uuidv4": self.traversal_uuidv4,
                "read_origin": None if collection else self._last_read_origin,
                "normalizer": {
                    "module": __name__
                    if collection
                    else normalization.NORMALIZER_MODULE,
                    "version": HTTP_INTAKE_VERSION
                    if collection
                    else normalization.NORMALIZER_VERSION,
                },
            },
        )

    def _response_origin(self, response):
        origin = dict(response.extensions["repo_catalog_http_read_origin"])
        header = response.headers.get("x-oauth-scopes")
        reported = (
            None
            if header is None
            else sorted({value.strip() for value in header.split(",") if value.strip()})
        )
        self.work.require("metadata_units", 1 + (len(reported) if reported else 0))
        self.work.charge("metadata_units", 1 + (len(reported) if reported else 0))
        # This is only a server-reported response attribute. It neither grants
        # admission rights nor authenticates a source, and never changes config.
        origin["reported_oauth_scopes"] = reported
        return origin

    def _request(self, path, **kwargs):
        url = (
            path if path.startswith(("https://", "http://")) else self.http.base + path
        )
        try:
            response = self.http.request("GET", url, **kwargs)
        except Waiting as error:
            self.record_wait(error)
            raise
        self._last_read_origin = self._response_origin(response)
        if response.status_code != 200:
            raise CatalogError("API_REDIRECT", "Explicit endpoint returned no payload")
        self.work.require("verification_bytes", len(response.content))
        self.work.charge("verification_bytes", len(response.content))
        try:
            payload = response.json()
        except (ValueError, UnicodeError, RecursionError):
            raise CatalogError("API_SCHEMA", "Invalid JSON response") from None
        return response, payload

    def _object(self, path):
        response, value = self._request(path)
        if type(value) is not dict:
            raise CatalogError("API_SCHEMA", "Expected resource object")
        return (
            value,
            response.extensions["catalog_observed_at_us"],
            self._provenance(path),
        )

    def _pages(
        self, path, consume, *, parent=None, kind=None, params=None, code_anchor=None
    ):
        url = path + ("?" + urlencode(params) if params else "")
        seen, members, page = set(), [], 0
        observed_page = False
        last_observed = None
        read_origins = []
        provenance = self._provenance(path, collection=True)
        scope_values = {
            "source_registration_uuidv4": self.source,
            "service_instance_uuidv4": self.service,
            "resource_path": path,
            "parameters": params or {},
        }
        page_provenances = []

        def captured_scope():
            if code_anchor is None:
                return canonical(scope_values)
            from repo_catalog.domain.pr_assessment import anchored_code_scope

            head, base, original, count = code_anchor
            return anchored_code_scope(
                scope_values,
                head=head,
                base=base,
                anchor_provenance_json=original,
                member_provenance_jsons=page_provenances,
                expected_count=count,
            )

        try:
            while url:
                if url in seen:
                    raise CatalogError("PAGINATION_CYCLE", "Repeated HTTP page")
                seen.add(url)
                response, values = self._request(url)
                if type(values) is not list:
                    raise CatalogError("API_SCHEMA", "Expected resource list")
                self.work.require("metadata_units", len(values))
                self.work.charge("metadata_units", len(values))
                observed = response.extensions["catalog_observed_at_us"]
                next_url = response.links.get("next", {}).get("url")
                page += 1
                page_provenance = self._provenance(path, page=page)
                new_members = consume(values, observed, page_provenance)
                projected_page = False
                for member in new_members:
                    if not projected_page:
                        page_provenances.append(page_provenance)
                        read_origins.append(self._last_read_origin)
                        projected_page = True
                    observed_page, last_observed = True, observed
                    if member not in members:
                        members.append(member)
                # Successful consumer exhaustion also proves genuine empty or
                # independently filtered-empty projection. Failed normalization
                # before the first admissible unit proves no domain observation.
                if not projected_page:
                    page_provenances.append(page_provenance)
                    read_origins.append(self._last_read_origin)
                observed_page, last_observed = True, observed
                count_mismatch = (
                    not next_url
                    and code_anchor is not None
                    and code_anchor[3] is not None
                    and len(members) != code_anchor[3]
                )
                if count_mismatch:
                    cap = {"pr_commits": 250, "pr_files": 3000}[kind]
                    self.partial_failure = self.partial_failure or (
                        "API_CAP" if code_anchor[3] > cap else "API_COUNT_MISMATCH"
                    )
                if parent is not None:
                    self._collection(
                        parent,
                        kind,
                        provenance,
                        captured_scope(),
                        observed,
                        "partial" if next_url or count_mismatch else "complete",
                        members,
                        read_origins=read_origins,
                    )
                if next_url:
                    self.http.validate_url(next_url)
                url = next_url
        except (CatalogError, CoreFailure, AcquisitionError) as error:
            if error.code == "CANCELLED":
                raise
            if parent is not None and observed_page:
                self._collection(
                    parent,
                    kind,
                    provenance,
                    captured_scope(),
                    last_observed,
                    "partial",
                    members,
                    read_origins=read_origins,
                    report_kind="interrupted",
                )
            raise
        return members

    def _collection(
        self,
        parent,
        kind,
        provenance,
        scope,
        observed,
        state,
        members,
        *,
        read_origins=None,
        report_kind="response",
    ):
        self.work.require("metadata_units", 1 + len(members))
        self.work.charge("metadata_units", 1 + len(members))
        provenance = self._terminal_provenance(
            provenance, members, read_origins, report_kind
        )
        observation = CollectionObservation(
            parent, kind, provenance, scope, observed, state, tuple(members)
        )
        claim = CoverageClaim(
            CoverageScope.collection(parent, kind, provenance, kind),
            observed,
            state,
        )
        self._emit(collection_proofs=((claim, observation, scope),))

    def _terminal_provenance(self, provenance, members, read_origins, report_kind):
        # A traversal can issue several genuine terminal reports, even when the
        # receiving clock ties. Keep each report's exact reads and prefix rather
        # than rebinding partial and complete payloads to one original claim.
        prefix = canonical([list(member.coordinates()) for member in members]).encode()
        self.work.require("verification_bytes", len(prefix))
        self.work.charge("verification_bytes", len(prefix))
        self._terminal_report_ordinal += 1
        evidence = json.loads(provenance)["evidence"]
        evidence["terminal_report"] = {
            "ordinal": self._terminal_report_ordinal,
            "kind": report_kind,
            "read_origins": (
                [self._last_read_origin] if read_origins is None else read_origins
            ),
            "member_prefix_sha256": hashlib.sha256(prefix).hexdigest(),
        }
        return make_provenance("github-http", evidence)

    def _inventory(
        self, scope, observed, state, terminal, members, reads, *, interrupted=False
    ):
        self.work.require("metadata_units", 1 + len(members))
        self.work.charge("metadata_units", 1 + len(members))
        provenance = self._terminal_provenance(
            self._provenance("source-inventory", collection=True),
            members,
            reads,
            "interrupted" if interrupted else "response",
        )
        # Prefix pages and the final traversal assessment are different actual
        # scopes. An intermediate prefix cannot compete with or invalidate its
        # later whole-traversal terminal just because the receipt clock ties.
        # Generic Source proof gates retain their strict original semantics.
        scope = canonical(
            {**scope, "observation_scope": "traversal" if terminal else "page-prefix"}
        )
        observation = SourceInventory(
            self.source,
            scope,
            observed,
            state,
            terminal,
            (),
            provenance,
            tuple(members),
        )
        if terminal:
            claim = CoverageClaim(
                CoverageScope.source_inventory(
                    self.source, scope, "provider_repositories"
                ),
                observed,
                state,
            )
            self._emit(source_inventory_proofs=((claim, observation),))
        else:
            self._emit(source_inventories=(observation,))

    def discover(self, owner, *, include_repositories=None):
        owner = _name(owner)
        if include_repositories is not None:
            if type(include_repositories) is not list or not include_repositories:
                raise CatalogError(
                    "INVALID_ARGUMENT", "Nonempty repository selection required"
                )
            include_repositories = [_name(name) for name in include_repositories]
            if len({name.lower() for name in include_repositories}) != len(
                include_repositories
            ):
                raise CatalogError("INVALID_ARGUMENT", "Duplicate repository selection")
        scope = {
            "source_registration_uuidv4": self.source,
            "service_instance_uuidv4": self.service,
            "coverage_kind": "provider_repositories",
            "owner": owner,
            "visibility": "all",
            "selected_repositories": include_repositories,
            "query_kind": "selected-repositories"
            if include_repositories
            else "owner-repositories",
            "traversal_attempt_uuidv4": self.traversal_uuidv4,
        }
        members, private, reads = [], {}, []
        observed, terminal_recorded = None, False

        def repository(payload, timestamp, original, selected=None):
            member = self._repository(payload, timestamp, original, owner, selected)
            if member in private:
                raise CatalogError("DUPLICATE_MEMBER", "Repeated inventory repository")
            members.append(member)
            private[member] = payload.get("private")

        try:
            response, identity = self._request("/user")
            observed = response.extensions["catalog_observed_at_us"]
            reads.append(self._last_read_origin)
            if (
                type(identity) is not dict
                or type(identity.get("login")) is not str
                or not identity["login"].strip()
            ):
                raise CatalogError("API_SCHEMA", "Authenticated identity missing")
            permissions = response.headers.get("x-oauth-scopes")
            scope["observed_permissions"] = (
                None
                if permissions is None
                else sorted(
                    {item.strip() for item in permissions.split(",") if item.strip()}
                )
            )
            scope["principal_ref"] = str(identity.get("id") or identity["login"])
            if include_repositories:
                for index, name in enumerate(include_repositories):
                    payload, observed, provenance = self._object(
                        f"/repos/{owner}/{name}"
                    )
                    reads.append(self._last_read_origin)
                    repository(payload, observed, provenance, name)
                    if index + 1 < len(include_repositories):
                        self._inventory(
                            scope, observed, "partial", False, members, reads
                        )
                reason = None
            else:
                same_owner = identity["login"].lower() == owner.lower()
                if same_owner:
                    path, params = (
                        "/user/repos",
                        {"affiliation": "owner", "visibility": "all", "per_page": 100},
                    )
                else:
                    user, observed, _ = self._object("/users/" + owner)
                    reads.append(self._last_read_origin)
                    if user.get("type") != "Organization":
                        raise CatalogError(
                            "SCOPE_UNSUPPORTED",
                            "Private owner inventory scope unestablished",
                        )
                    scope["query_kind"] = "organization-repositories"
                    path, params = (
                        f"/orgs/{owner}/repos",
                        {"type": "all", "per_page": 100},
                    )
                url, seen, page = path + "?" + urlencode(params), set(), 0
                while url:
                    if url in seen:
                        raise CatalogError(
                            "PAGINATION_CYCLE", "Repeated inventory page"
                        )
                    seen.add(url)
                    response, values = self._request(url)
                    observed = response.extensions["catalog_observed_at_us"]
                    reads.append(self._last_read_origin)
                    if type(values) is not list:
                        raise CatalogError("API_SCHEMA", "Expected repository list")
                    self.work.require("metadata_units", len(values))
                    self.work.charge("metadata_units", len(values))
                    page += 1
                    provenance = self._provenance(path, page=page)
                    for value in values:
                        if type(value) is not dict:
                            raise CatalogError(
                                "API_SCHEMA", "Expected repository object"
                            )
                        repository(value, observed, provenance)
                    url = response.links.get("next", {}).get("url")
                    if url:
                        self._inventory(
                            scope, observed, "partial", False, members, reads
                        )
                        self.http.validate_url(url)
                counts = (
                    identity.get("public_repos"),
                    identity.get("owned_private_repos"),
                )
                reason = None
                if (
                    not same_owner
                    or any(type(count) is not int or count < 0 for count in counts)
                    or any(type(value) is not bool for value in private.values())
                ):
                    reason = "INVENTORY_SCOPE_UNVERIFIED"
                elif counts != (
                    sum(not value for value in private.values()),
                    sum(private.values()),
                ):
                    reason = "INVENTORY_COUNT_MISMATCH"
            self._inventory(
                scope,
                observed,
                "unknown" if reason else "complete",
                True,
                members,
                reads,
            )
            terminal_recorded = True
            if reason:
                raise CatalogError(
                    reason, "Provider inventory scope is not proven complete"
                )
        except (
            CatalogError,
            CoreFailure,
            AcquisitionError,
            AdmissionRefused,
            KeyError,
            TypeError,
        ) as error:
            if getattr(error, "code", None) == "CANCELLED":
                raise
            if observed is not None and not terminal_recorded:
                self._inventory(
                    scope,
                    self.http.clock_us(),
                    "partial",
                    True,
                    members,
                    reads,
                    interrupted=True,
                )
            raise

    def _repository(self, payload, observed, provenance, owner, repository=None):
        full_name = payload.get("full_name")
        if type(full_name) is not str or len(full_name.split("/")) != 2:
            raise CatalogError("API_SCHEMA", "Repository identity missing")
        actual_owner, actual_repository = full_name.split("/")
        if actual_owner.lower() != owner.lower() or (
            repository is not None and actual_repository.lower() != repository.lower()
        ):
            raise CatalogError("SCOPE_MISMATCH", "Repository outside requested scope")
        unit = normalization.normalize_repository_fields(
            self.service, payload, observed, provenance
        )
        self._emit(
            provider_repositories=(
                ProviderRepositoryIntake(payload, observed, provenance),
            )
        )
        return unit.primary_resource

    def sync(self, owner, repository, *, sections=None):
        owner, repository = _name(owner), _name(repository)
        if sections is not None and (
            type(sections) is not list or any(type(s) is not str for s in sections)
        ):
            raise CatalogError("INVALID_ARGUMENT", "Explicit section list required")
        sections = _SECTIONS if sections is None else frozenset(sections)
        if not sections <= _SECTIONS:
            raise CatalogError("INVALID_ARGUMENT", "Unknown GitHub acquisition section")
        path = f"/repos/{owner}/{repository}"
        payload, observed, provenance = self._object(path)
        repo_key = self._repository(payload, observed, provenance, owner, repository)
        issues, pulls = [], []
        if "issues" in sections or {"issue_comments", "timeline"} & sections:

            def consume_issues(values, timestamp, prov):
                for value in values:
                    if type(value) is not dict:
                        raise CatalogError("API_SCHEMA", "Expected issue object")
                    normalization.github_resource_id(value, graphql=False)
                    value = {**value, "repository": {"id": payload["id"]}}
                    unit = normalization.normalize_issue(
                        self.service, value, timestamp, prov
                    )
                    if unit is not None:
                        self._emit(
                            issues=(ProviderIssueIntake(value, timestamp, prov),)
                        )
                        issues.append(value)
                        yield unit.primary_resource

            self._pages(
                path + "/issues",
                consume_issues,
                parent=repo_key,
                kind="issues",
                params={"state": "all", "per_page": 100},
            )
        if sections - {"issues"}:

            def consume_pulls(values, timestamp, prov):
                for value in values:
                    if type(value) is not dict:
                        raise CatalogError("API_SCHEMA", "Expected pull request object")
                    unit = normalization.normalize_pull_request(
                        self.service, value, timestamp, prov
                    )
                    self._emit(
                        pull_requests=(
                            ProviderPullRequestIntake(value, timestamp, prov),
                        )
                    )
                    pulls.append(value)
                    yield unit.primary_resource

            self._pages(
                path + "/pulls",
                consume_pulls,
                parent=repo_key,
                kind="pull_requests",
                params={"state": "all", "per_page": 100},
            )
        for kind, items in (("issue", issues), ("pull_request", pulls)):
            for item in items:
                number = _positive(item.get("number"), "issue number")
                parent_id = normalization.github_resource_id(item, graphql=False)
                parent = ResourceKey(self.service, kind, parent_id)
                for section in ("issue_comments", "timeline"):
                    if section in sections:
                        self._independent(
                            lambda section=section: self._children(
                                path + f"/issues/{number}", section, parent, item["id"]
                            )
                        )
                if kind == "pull_request":
                    # List projections omit independent scalar/detail fields.
                    detail, ts, prov = self._object(path + f"/pulls/{number}")
                    if (
                        normalization.github_resource_id(detail, graphql=False)
                        != parent_id
                    ):
                        raise CatalogError(
                            "SCOPE_MISMATCH", "Pull request identity changed"
                        )
                    self._emit(
                        pull_requests=(ProviderPullRequestIntake(detail, ts, prov),)
                    )
                    try:
                        self._pull_children(
                            path,
                            owner,
                            repository,
                            number,
                            parent,
                            item["id"],
                            detail,
                            prov,
                            sections,
                            detail.get("node_id", item.get("node_id")),
                        )
                    except (CatalogError, CoreFailure, AcquisitionError) as error:
                        if (
                            self.git_roles is not None
                            and not isinstance(error, Waiting)
                            and error.code != "CANCELLED"
                        ):
                            self.git_roles.acquire(
                                self,
                                parent,
                                number,
                                detail,
                                prov,
                                path + f"/pulls/{number}",
                            )
                        raise
                    if self.git_roles is not None:
                        self.git_roles.acquire(
                            self,
                            parent,
                            number,
                            detail,
                            prov,
                            path + f"/pulls/{number}",
                        )

    def _independent(self, operation):
        try:
            return operation()
        except (CatalogError, AcquisitionError) as error:
            if isinstance(error, Waiting) or error.code in {
                "CANCELLED",
                "CREDENTIALS_MISSING",
                "RECOVERY_REQUIRED",
                "RECOVERY_STOP",
                "AUTHORITATIVE_CORRUPTION",
                "INTEGRITY",
                "CORRUPT",
                "BUDGET",
                "CONTINUATION_UNAVAILABLE",
                "INCOMPATIBLE_REPLAY",
                "REQUEST_SCOPE",
            }:
                raise
            self.partial_failure = self.partial_failure or error.code

    def _pull_children(
        self,
        path,
        owner,
        repository,
        number,
        parent,
        parent_id,
        detail,
        provenance,
        sections,
        known_node_id,
    ):
        for section in ("reviews", "review_comments", "pr_commits", "pr_files"):
            if section in sections:
                self._independent(
                    lambda section=section: self._children(
                        path + f"/pulls/{number}",
                        section,
                        parent,
                        parent_id,
                        code_detail=(detail, provenance),
                    )
                )
        if "review_threads" in sections:
            self._independent(
                lambda: self._threads(
                    owner,
                    repository,
                    number,
                    parent,
                    parent_id,
                    code_detail=(detail, provenance),
                    known_node_id=known_node_id,
                )
            )

    def _children(self, base, section, parent, parent_id, *, code_detail=None):
        suffix = {
            "issue_comments": "comments",
            "timeline": "timeline",
            "reviews": "reviews",
            "review_comments": "comments",
            "pr_commits": "commits",
            "pr_files": "files",
        }[section]

        def consume(values, observed, provenance):
            for value in values:
                if type(value) is not dict:
                    raise CatalogError("API_SCHEMA", "Expected child resource object")
                if section == "issue_comments":
                    intake = ProviderIssueCommentIntake(
                        parent.resource_kind, parent_id, value, observed, provenance
                    )
                    unit = normalization.normalize_issue_comment(
                        self.service,
                        parent.resource_kind,
                        parent_id,
                        value,
                        observed,
                        provenance,
                    )
                elif section == "timeline":
                    event_id = value.get("id")
                    intake = ProviderTimelineIntake(
                        parent.resource_kind,
                        parent_id,
                        event_id,
                        value,
                        observed,
                        provenance,
                    )
                    unit = normalization.normalize_timeline_event(
                        self.service,
                        parent.resource_kind,
                        parent_id,
                        event_id,
                        value,
                        observed,
                        provenance,
                    )
                else:
                    constructors = {
                        "reviews": (
                            ProviderReviewIntake,
                            normalization.normalize_review,
                        ),
                        "review_comments": (
                            ProviderReviewCommentIntake,
                            normalization.normalize_review_comment,
                        ),
                        "pr_commits": (
                            ProviderCommitContextIntake,
                            normalization.normalize_pr_commit,
                        ),
                        "pr_files": (
                            ProviderFileContextIntake,
                            normalization.normalize_pr_file,
                        ),
                    }
                    cls, normalizer = constructors[section]
                    # PR patches are Provider context, never native file bodies.
                    intake = cls(parent_id, value, observed, provenance)
                    unit = normalizer(
                        self.service, parent_id, value, observed, provenance
                    )
                # Each typed resource is an atomic unit. A later unsupported
                # occurrence cannot erase already admissible current-page facts.
                self._emit(
                    **{
                        section if section != "timeline" else "timeline_events": (
                            intake,
                        )
                    }
                )
                if self.git_roles is not None and section in {
                    "reviews",
                    "review_comments",
                }:
                    self.git_roles.record(parent, unit.core_references)
                yield unit.primary_resource

        anchor = None
        if section in {"pr_commits", "pr_files"} and code_detail is not None:
            detail, original = code_detail
            head, base_value = detail.get("head"), detail.get("base")
            head = (
                normalization.parse_git_oid(head.get("sha"))
                if isinstance(head, dict)
                else None
            )
            base_value = (
                normalization.parse_git_oid(base_value.get("sha"))
                if isinstance(base_value, dict)
                else None
            )
            count = detail.get(
                "commits" if section == "pr_commits" else "changed_files"
            )
            if type(count) is not int or count < 0:
                count = None
            if (
                head is not None
                and base_value is not None
                and head.object_format == base_value.object_format
            ):
                anchor = (head, base_value, original, count)
        self._pages(
            base + "/" + suffix,
            consume,
            parent=parent,
            kind=section,
            params={"per_page": 100},
            code_anchor=anchor,
        )

    def _threads(
        self,
        owner,
        repository,
        number,
        parent,
        parent_id,
        *,
        code_detail=None,
        known_node_id=None,
    ):
        # Both connection levels are paginated independently. A thread list is
        # never called complete while a nested comment continuation is missing.
        cursor, seen, members = None, set(), []
        traversal_reads = []
        path = f"/repos/{owner}/{repository}/pulls/{number}/review_threads"
        provenance = self._provenance(path, collection=True)
        scope_values = {
            "source_registration_uuidv4": self.source,
            "resource_path": path,
            "nested_comments": True,
        }
        root_originals = []
        root_owner_id = None
        anchor = None
        if code_detail is not None:
            detail, original = code_detail
            head, base = detail.get("head"), detail.get("base")
            head = (
                normalization.parse_git_oid(head.get("sha"))
                if isinstance(head, dict)
                else None
            )
            base = (
                normalization.parse_git_oid(base.get("sha"))
                if isinstance(base, dict)
                else None
            )
            if (
                head is not None
                and base is not None
                and head.object_format == base.object_format
            ):
                anchor = head, base, original

        def captured_scope(values, originals):
            if anchor is None:
                return canonical(values)
            from repo_catalog.domain.pr_assessment import anchored_code_scope

            head, base, original = anchor
            return anchored_code_scope(
                values,
                head=head,
                base=base,
                anchor_provenance_json=original,
                member_provenance_jsons=originals,
            )

        try:
            while True:
                data, observed = self._graphql(
                    _THREAD_QUERY,
                    {
                        "owner": owner,
                        "name": repository,
                        "number": number,
                        "cursor": cursor,
                    },
                )
                root_partial = self._graphql_partial
                root_observed, root_origin = observed, self._last_read_origin
                repository_value = data.get("repository")
                root = (
                    repository_value.get("pullRequest")
                    if type(repository_value) is dict
                    else None
                )
                if type(root) is not dict:
                    raise CatalogError(
                        "SCOPE_MISMATCH", "GraphQL PR owner is unavailable"
                    )
                node_id = root.get("id")
                if type(node_id) is not str or not node_id or "\0" in node_id:
                    raise CatalogError(
                        "SCOPE_MISMATCH", "GraphQL PR owner identity missing"
                    )
                if known_node_id is not None and node_id != known_node_id:
                    raise CatalogError(
                        "SCOPE_MISMATCH", "GraphQL PR opaque owner differs"
                    )
                if "number" in root:
                    if type(root["number"]) is not int or root["number"] != number:
                        raise CatalogError(
                            "SCOPE_MISMATCH", "GraphQL PR canonical owner differs"
                        )
                elif known_node_id is None:
                    raise CatalogError(
                        "SCOPE_MISMATCH",
                        "Unknown GraphQL owner requires returned canonical number",
                    )
                for key in ("fullDatabaseId", "databaseId"):
                    if (
                        key in root
                        and root[key] is not None
                        and normalization.canonical_database_id(root[key])
                        != normalization.canonical_database_id(parent_id)
                    ):
                        raise CatalogError(
                            "SCOPE_MISMATCH", "GraphQL PR native owner differs"
                        )
                if root_owner_id is not None and node_id != root_owner_id:
                    raise CatalogError(
                        "SCOPE_MISMATCH", "GraphQL PR owner changed across pages"
                    )
                root_owner_id = node_id
                scope_values["graphql_parent"] = {
                    "id": node_id,
                    "number": root.get("number"),
                }
                # Comparison fields belong to this identified actual HTTP read,
                # even when GraphQL returned only a partial document connection.
                # Do not fabricate a REST/database ID to invoke the normalizer.
                if any(
                    key in root for key in ("headRefOid", "baseRefOid", "mergeCommit")
                ):
                    header_original = self._provenance(path + "/comparison")

                    def admit_header():
                        unit = normalization.normalize_pr_comparison_header(
                            parent, root, root_observed, header_original
                        )
                        self._emit(
                            observations=unit.observations,
                            core_references=unit.core_references,
                        )
                        if self.git_roles is not None:
                            self.git_roles.record(parent, unit.core_references)
                        return unit

                    header_unit = self._independent(admit_header)
                    head = (
                        normalization.parse_git_oid(root.get("headRefOid"))
                        if header_unit is not None
                        else None
                    )
                    base = (
                        normalization.parse_git_oid(root.get("baseRefOid"))
                        if header_unit is not None
                        else None
                    )
                    if head is not None and base is not None:
                        if cursor is None:
                            anchor = head, base, header_original
                        elif anchor is None or (head, base) != anchor[:2]:
                            # Independently usable thread facts survive; a
                            # changing comparison cannot qualify one whole pass.
                            root_partial = True
                            self.partial_failure = (
                                self.partial_failure or "PR_CODE_RACE"
                            )
                traversal_reads.append(root_origin)
                completion_observed = root_observed
                connection = root["reviewThreads"]
                for thread in _nodes(connection):
                    observed, self._last_read_origin = root_observed, root_origin
                    thread_prov = self._provenance(path + "/" + thread["id"])
                    root_originals.append(thread_prov)
                    collection_prov = self._provenance(
                        path + "/" + thread["id"] + "/comments", collection=True
                    )
                    unit = normalization.normalize_review_thread(
                        self.service, parent_id, thread, observed, thread_prov
                    )
                    self._emit(
                        review_threads=(
                            ProviderReviewThreadIntake(
                                parent_id, thread, observed, thread_prov
                            ),
                        )
                    )
                    members.append(unit.primary_resource)
                    comments = thread["comments"]
                    comment_members, child_seen = [], set()
                    comment_reads = [root_origin]
                    comment_originals = []
                    child_partial = root_partial
                    while True:
                        comment_prov = self._provenance(
                            path + "/" + thread["id"] + "/comments"
                        )
                        comment_originals.append(comment_prov)
                        try:
                            for comment in _nodes(comments):
                                intake = ProviderReviewCommentIntake(
                                    parent_id,
                                    comment,
                                    observed,
                                    comment_prov,
                                    graphql=True,
                                    thread_id=thread["id"],
                                )
                                normalized = normalization.normalize_review_comment(
                                    self.service,
                                    parent_id,
                                    comment,
                                    observed,
                                    comment_prov,
                                    graphql=True,
                                    thread_id=thread["id"],
                                )
                                # A resource is the atomic admission unit, including
                                # when its siblings arrived in this same response.
                                self._emit(review_comments=(intake,))
                                if self.git_roles is not None:
                                    self.git_roles.record(
                                        parent, normalized.core_references
                                    )
                                comment_members.append(normalized.primary_resource)
                        except (
                            CatalogError,
                            CoreFailure,
                            AcquisitionError,
                            KeyError,
                            TypeError,
                        ) as error:
                            if getattr(error, "code", None) == "CANCELLED":
                                raise
                            self._collection(
                                unit.primary_resource,
                                "review_thread_comments",
                                collection_prov,
                                captured_scope(
                                    {
                                        "source_registration_uuidv4": self.source,
                                        "thread_id": thread["id"],
                                        "resource_path": path,
                                    },
                                    comment_originals,
                                ),
                                observed,
                                "partial",
                                comment_members,
                                read_origins=comment_reads,
                                report_kind="interrupted",
                            )
                            raise
                        child_cursor = _cursor(comments, child_seen)
                        child_scope = captured_scope(
                            {
                                "source_registration_uuidv4": self.source,
                                "thread_id": thread["id"],
                                "resource_path": path,
                            },
                            comment_originals,
                        )
                        self._collection(
                            unit.primary_resource,
                            "review_thread_comments",
                            collection_prov,
                            child_scope,
                            observed,
                            "partial" if child_cursor or child_partial else "complete",
                            comment_members,
                            read_origins=comment_reads,
                        )
                        if child_partial:
                            raise CatalogError(
                                "GRAPHQL_PARTIAL",
                                "GraphQL supplied only a partial comment projection",
                            )
                        if child_cursor is None:
                            break
                        child, observed = self._graphql(
                            _COMMENTS_QUERY,
                            {"id": thread["id"], "cursor": child_cursor},
                        )
                        comment_reads.append(self._last_read_origin)
                        traversal_reads.append(self._last_read_origin)
                        comments = child["node"]["comments"]
                        child_partial = self._graphql_partial
                    completion_observed = max(completion_observed, observed)
                cursor = _cursor(connection, seen)
                self._collection(
                    parent,
                    "review_threads",
                    provenance,
                    captured_scope(scope_values, root_originals),
                    completion_observed,
                    "partial" if cursor or root_partial else "complete",
                    members,
                    read_origins=traversal_reads,
                )
                if root_partial:
                    raise CatalogError(
                        "GRAPHQL_PARTIAL",
                        "GraphQL supplied only a partial thread projection",
                    )
                if cursor is None:
                    break
        except (
            CatalogError,
            CoreFailure,
            AcquisitionError,
            KeyError,
            TypeError,
        ) as error:
            if getattr(error, "code", None) == "CANCELLED":
                raise
            if not traversal_reads:
                raise
            self._collection(
                parent,
                "review_threads",
                provenance,
                captured_scope(scope_values, root_originals),
                self.http.clock_us(),
                "partial",
                members,
                read_origins=traversal_reads,
                report_kind="interrupted",
            )
            raise

    def _graphql(self, query, variables):
        try:
            response = self.http.request(
                "POST", self.http.graphql, json={"query": query, "variables": variables}
            )
        except Waiting as error:
            self.record_wait(error)
            raise
        self._last_read_origin = self._response_origin(response)
        self.work.require("verification_bytes", len(response.content))
        self.work.charge("verification_bytes", len(response.content))
        self._graphql_partial = False
        try:
            value = response.json()
        except (ValueError, UnicodeError, RecursionError):
            raise CatalogError("API_SCHEMA", "Invalid GraphQL JSON response") from None
        if type(value) is not dict:
            raise CatalogError("API_SCHEMA", "Invalid GraphQL response")
        errors = value.get("errors")
        if isinstance(errors, list) and any(
            isinstance(error, dict) and error.get("type") == "RATE_LIMITED"
            for error in errors
        ):
            deadline = validate_retry_deadline_us(self.http.clock_us() + 60_000_000)
            error = Waiting(
                "RATE_LIMIT", "GraphQL rate limited", {"not_before_us": deadline}, True
            )
            self.record_wait(error)
            raise error
        data = value.get("data")
        if type(data) is not dict:
            raise CatalogError(
                "GRAPHQL_PARTIAL" if errors else "API_SCHEMA",
                "Incomplete GraphQL response",
            )
        if errors:
            self._graphql_partial = True
            resource = data.get("node") if "id" in variables else data.get("repository")
            if "id" not in variables and isinstance(resource, dict):
                resource = resource.get("pullRequest")
            if type(resource) is not dict:
                raise CatalogError("GRAPHQL_PARTIAL", "GraphQL error-only response")
        if "id" in variables:
            node = data.get("node")
            if type(node) is not dict or node.get("id") != variables["id"]:
                raise CatalogError(
                    "SCOPE_MISMATCH",
                    "GraphQL child response has a different thread parent",
                )
        return data, response.extensions["catalog_observed_at_us"]


def _nodes(connection):
    if type(connection) is not dict or type(connection.get("nodes")) is not list:
        raise CatalogError("API_SCHEMA", "Missing GraphQL connection")
    for node in connection["nodes"]:
        if type(node) is not dict:
            raise CatalogError("API_SCHEMA", "Invalid GraphQL node")
        yield node


def _cursor(connection, seen):
    info = connection.get("pageInfo")
    if type(info) is not dict or type(info.get("hasNextPage")) is not bool:
        raise CatalogError("API_SCHEMA", "Missing GraphQL pagination evidence")
    if not info["hasNextPage"]:
        return None
    cursor = info.get("endCursor")
    if type(cursor) is not str or not cursor or cursor in seen:
        raise CatalogError("PAGINATION_CYCLE", "Invalid GraphQL continuation")
    seen.add(cursor)
    return cursor


_COMMENT_FIELDS = """id databaseId body createdAt updatedAt url author { login }
 path position originalPosition diffHunk state replyTo { id databaseId }
 commit { oid } originalCommit { oid } pullRequestReview { id databaseId }"""
_THREAD_QUERY = (
    """query($owner:String!,$name:String!,$number:Int!,$cursor:String) {
 repository(owner:$owner,name:$name) { pullRequest(number:$number) { id number headRefOid baseRefOid
 mergeCommit { oid } updatedAt
 reviewThreads(first:100,after:$cursor) { nodes { id isResolved isOutdated path line
 comments(first:100) { nodes { """
    + _COMMENT_FIELDS
    + """ }
 pageInfo { hasNextPage endCursor } } } pageInfo { hasNextPage endCursor } } } } }"""
)
_COMMENTS_QUERY = (
    """query($id:ID!,$cursor:String) { node(id:$id) { id
 ... on PullRequestReviewThread { comments(first:100,after:$cursor) { nodes {
 """
    + _COMMENT_FIELDS
    + """ } pageInfo { hasNextPage endCursor } } } } }"""
)


def acquire_github(
    catalog,
    document,
    *,
    authorization,
    admission,
    client=None,
    credentials=None,
    cancelled=lambda: False,
    clock_us=None,
    _shared=None,
):
    """Execute one explicit local HTTP request using durable Operational limits."""
    clock_us = now_us if clock_us is None else clock_us
    if type(document) is not dict:
        raise CatalogError("INVALID_ARGUMENT", "GitHub request object required")
    allowed = {
        "operation",
        "service_instance_uuidv4",
        "source_registration_uuidv4",
        "request_identity",
        "new_request",
        "owner",
        "repository",
        "rest_base_url",
        "graphql_url",
        "token_env_var",
        "max_pages",
        "response_bytes",
        "work_limits",
        "sections",
        "include_repositories",
        "git_source",
    }
    if set(document) - allowed:
        raise CatalogError("INVALID_ARGUMENT", "Unknown GitHub request field")
    uuid4_value(document["service_instance_uuidv4"])
    uuid4_value(document["source_registration_uuidv4"])
    authorization.validate_context(admission)
    operation = document.get("operation")
    if operation not in {"discover", "sync"}:
        raise CatalogError("INVALID_ARGUMENT", "Expected discover or sync operation")
    if "git_source" in document:
        from repo_catalog.application.github_git_roles import validate_git_source

        validate_git_source(document["git_source"])
        if operation != "sync":
            raise CatalogError(
                "INVALID_ARGUMENT", "Git roles require an explicit sync operation"
            )
        if not (Path(catalog) / "core.sqlite3").is_file():
            raise CatalogError(
                "STORE_UNAVAILABLE", "Explicit Git role work requires initialized Core"
            )
    owner = _name(document.get("owner"))
    request = RequestIdentity(*document["request_identity"])
    if _shared is not None:
        from repo_catalog.adapters.sqlite.notes import NotesProgress
        from repo_catalog.adapters.sqlite.operational_coordination import (
            NotesWorkBudget,
        )

        ledger, work, progress = _shared
        if (
            type(ledger) is not OperationalAcquisitionLedger
            or type(work) is not NotesWorkBudget
            or type(progress) is not NotesProgress
            or progress.work is not work
            or work.ledger is not ledger.work_ledger
            or work.request != request
            or ledger.work_ledger._path.resolve()
            != (Path(catalog) / "operational.sqlite3").resolve()
            or document.get("new_request", False)
            or document.get("work_limits")
        ):
            raise CatalogError(
                "INCOMPATIBLE_REPLAY", "Genuine original parent budget required"
            )
        ledger.work_ledger.validate_continuation(request, work.attempt_uuidv4)
    if type(document.get("new_request", False)) is not bool:
        raise CatalogError("INVALID_ARGUMENT", "Explicit new-request boolean required")
    cfg = {
        "rest_base_url": document.get("rest_base_url", "https://api.github.com"),
        "graphql_url": document.get("graphql_url", "https://api.github.com/graphql"),
        "token_env_var": document.get("token_env_var", "GITHUB_TOKEN"),
        "rest_api_version": "2022-11-28",
        "read_timeout_seconds": 30,
        "connect_timeout_seconds": 10,
        "max_attempts": 3,
    }
    for name in ("rest_base_url", "graphql_url"):
        if type(cfg[name]) is not str:
            raise CatalogError("UNSAFE_API_URL", "API base must be a string")
        parsed = urlsplit(cfg[name])
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise CatalogError("UNSAFE_API_URL", "Credential-free API base required")
    response_bytes = _positive(
        document.get("response_bytes", 32 * 1024 * 1024),
        "response byte limit",
        32 * 1024 * 1024,
    )
    max_pages = _positive(
        document.get("max_pages", 1000), "HTTP attempt limit", 1_000_000
    )
    token = _Token(cancelled)
    catalog = Path(catalog)
    if not (catalog / "operational.sqlite3").is_file():
        raise CatalogError(
            "CONTINUATION_UNAVAILABLE", "Durable Operational store required"
        )
    # Hash transport location and credential *reference*, never the credential.
    # Scope binds retries to exact local intent without moving options to Context.
    intent = {
        k: v
        for k, v in document.items()
        if k not in {"new_request", "work_limits", "max_pages", "response_bytes"}
    }
    scope = ["github-http", hashlib.sha256(canonical(intent).encode()).hexdigest()]
    limits = NotesLimits.work_limits()
    requested_limits = document.get("work_limits", {})
    if (
        type(requested_limits) is not dict
        or set(requested_limits) - set(limits)
        or any(
            type(value) is not int or not 0 <= value <= 2**63 - 1
            for value in requested_limits.values()
        )
    ):
        raise CatalogError("INVALID_ARGUMENT", "Finite known work limits required")
    limits.update(requested_limits)
    with _acquisition_ledger(catalog, _shared) as ledger:
        if _shared is None:
            ledger.ensure_request(
                request,
                scope=scope,
                new_request=document.get("new_request", False),
                limits=limits,
            )
        else:
            original = progress.save_once(
                canonical(
                    ["github-source-intent", document["source_registration_uuidv4"]]
                ),
                scope[1],
            )
            if original != scope[1]:
                raise CatalogError(
                    "INCOMPATIBLE_REPLAY", "Frozen Source HTTP intent changed"
                )
        retry_scope = ["github-http-retry", scope[1]]

        def retry_guard():
            retry = ledger.get_retry_state(retry_scope, request=request)
            current = validate_retry_deadline_us(clock_us())
            if current is None:
                raise CatalogError("INVALID_ARGUMENT", "Required retry clock missing")
            if retry is not None and current < retry["not_before_us"]:
                raise Waiting(
                    "NOT_BEFORE",
                    "Original request retry deadline has not arrived",
                    {"not_before_us": retry["not_before_us"]},
                    True,
                )

        try:
            retry_guard()
        except Waiting as error:
            return GitHubFetchReport(
                request,
                "partial",
                (),
                (),
                0,
                0,
                error.code,
                error.details["not_before_us"],
            )
        if _shared is None:
            _, _, work, progress = ledger.create_budget(
                scope=scope,
                request=request,
                new_request=document.get("new_request", False),
                work_limits=document.get("work_limits"),
            )
            parent_progress = progress
        else:
            parent_progress = progress
            progress = _SourceProgress(
                progress, document["source_registration_uuidv4"], scope[1]
            )
        # Attempts are counted durably as metadata work; checkpoint also freezes
        # per-request finite HTTP invocation bounds across continuation calls.
        bound = {"max_pages": max_pages, "response_bytes": response_bytes}
        original_bound = progress.save_once(canonical(["github-http-bounds", 1]), bound)
        if any(bound[name] < original_bound[name] for name in bound):
            raise CatalogError(
                "INCOMPATIBLE_REPLAY",
                "HTTP continuation requires original or deliberately increased finite bounds",
            )
        acquisition = ProviderAcquisition(
            catalog,
            core=catalog,
            operational=catalog,
            authorization=authorization,
            admission=admission,
        )
        transport = GitHubTransport(
            cfg, token, client=client, credentials=credentials, clock_us=clock_us
        )
        original_client = transport.client
        metered = _MeteredClient(
            original_client,
            work,
            token,
            response_bytes,
            max_pages,
            progress,
            before_attempt=retry_guard,
        )
        transport.client = metered
        scheduled_deadline = None
        scheduled_reason = None

        def record_wait(error):
            nonlocal scheduled_deadline, scheduled_reason
            deadline = validate_retry_deadline_us(error.details["not_before_us"])
            if deadline is None:
                raise CatalogError(
                    "INVALID_ARGUMENT", "Required retry deadline missing"
                )
            if scheduled_deadline != deadline or scheduled_reason != error.code:
                ledger.record_retry_state(
                    retry_scope,
                    not_before_us=deadline,
                    reason=error.code,
                    request=request,
                )
            scheduled_deadline, scheduled_reason = deadline, error.code

        fetch = GitHubProviderFetch(
            transport,
            service_instance_uuidv4=document["service_instance_uuidv4"],
            source_registration_uuidv4=document["source_registration_uuidv4"],
            request_identity=request,
            work=work,
            admit=acquisition.admit_batch,
            record_wait=record_wait,
        )
        if "git_source" in document:
            from repo_catalog.application.github_git_roles import GitHubGitRoles

            fetch.git_roles = GitHubGitRoles(
                catalog,
                document["git_source"],
                ledger=ledger,
                work=work,
                progress=parent_progress,
                request=request,
                clock_us=clock_us,
                cancelled=cancelled,
            )
        failure = None
        not_before_us = None
        try:
            if operation == "discover":
                fetch.discover(
                    owner, include_repositories=document.get("include_repositories")
                )
            else:
                fetch.sync(
                    owner, document.get("repository"), sections=document.get("sections")
                )
            failure = fetch.partial_failure
        except (CatalogError, CoreFailure, AcquisitionError) as error:
            if error.code in {"RECOVERY_REQUIRED", "CORRUPT", "INTEGRITY"}:
                raise
            failure = error.code
            deadline = getattr(error, "details", {}).get("not_before_us")
            if deadline is not None:
                not_before_us = validate_retry_deadline_us(deadline)
                record_wait(error)
            elif scheduled_deadline is not None:
                # Failure to append an optional partial proof cannot erase the
                # already observed, durably recorded retry boundary.
                not_before_us, failure = scheduled_deadline, scheduled_reason
        finally:
            transport.client = original_client
            transport.close()
        if failure is None:
            ledger.clear_retry_state(retry_scope, request=request)
        return GitHubFetchReport(
            request,
            "partial" if failure else "complete",
            tuple(fetch.batches),
            tuple(fetch.reports),
            metered.network_bytes,
            metered.requests,
            failure,
            not_before_us,
            () if fetch.git_roles is None else tuple(fetch.git_roles.reports),
        )


def acquire_github_with_budget(
    catalog,
    document,
    *,
    authorization,
    admission,
    work,
    progress,
    ledger,
    client=None,
    credentials=None,
    cancelled=lambda: False,
    clock_us=None,
):
    """Trusted batch composition: one parent ledger, budget and original attempt.

    No child requests or finite work counters are created/reset. Each Source's
    exact frozen intent, HTTP slots and finite response bounds remain durable.
    """
    return acquire_github(
        catalog,
        document,
        authorization=authorization,
        admission=admission,
        client=client,
        credentials=credentials,
        cancelled=cancelled,
        clock_us=clock_us,
        _shared=(ledger, work, progress),
    )
