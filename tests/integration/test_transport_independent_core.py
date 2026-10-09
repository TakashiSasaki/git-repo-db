"""Independent current-domain acceptance without saved API inputs or profiles."""

from __future__ import annotations

import copy
import json
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.recording import LocalFileRecorder
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.index import rebuild
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.exchange_service import ExchangeService
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.domain.models import CancellationToken, CatalogError

API = "https://synthetic.github.test"
OPAQUE = "unmodeled-transport-original-must-not-be-retained"


@dataclass
class CoreCatalog:
    state: object
    store: Store
    repository: str
    service: str
    binding: str
    request: str

    @property
    def repo(self):
        return {
            "repository_uuidv4": self.repository,
            "source_id": "source",
            "provider_repository_id": "101",
            "name": "synthetic/core",
        }

    def job(self):
        job = JobService(self.store).create("sync", {"kind": "issue"})
        self.store.expected_attempt = 1
        return job

    @contextmanager
    def collector(self, responder, recorder=None):
        config = copy.deepcopy(self.store.config["github"])
        config.update(rest_base_url=API, graphql_url=API + "/graphql", max_attempts=1)
        with httpx.Client(transport=httpx.MockTransport(responder)) as client:
            transport = GitHubTransport(
                config,
                CancellationToken(),
                client=client,
                recorder=recorder,
                clock_us=lambda: 100,
            )
            yield GitHubCollector(
                self.store, CancellationToken(), transport=transport, config=config
            )

    def candidate(self, *, version="1", clock=10, **fields):
        """An explicit synthetic producer; versions are attribution only."""
        scope = {
            "repository_uuidv4": self.repository,
            "repository_binding_id": self.binding,
            "service_instance_uuidv4": self.service,
            "endpoint": "synthetic-provider-issue",
        }
        return {
            **{key: value for key, value in scope.items() if key != "endpoint"},
            "kind": "issue",
            "provider_resource_id": "1",
            "provider_issue_number": 1,
            "observed_at_us": clock,
            "parsed_at_us": clock + 1,
            "provider_updated_at_us": clock,
            "provider_clock_scope": "github-issue-updated-at",
            "parser_module": __name__,
            "parser_version": version,
            "acquisition_scope": scope,
            **fields,
        }

    def admit(self, candidate):
        with self.store.transaction():
            result = CurrentResources(self.store).admit(candidate, source="import")
            self.store.publish()
        return result

    def query(self, command, **options):
        return QueryService(self.state).query(
            command, {"repo": self.repository, **options}
        )


@pytest.fixture
def core_catalog(tmp_path):
    state = tmp_path / "transport-independent-synthetic-catalog"
    MaintenanceService(state).init("catalog-text-v1", 67_108_864, 0)
    with Store(state) as store:
        repository, request, source = (str(uuid.uuid4()) for _ in range(3))
        with store.transaction():
            service = add_instance(store, "github", "synthetic", API, API)
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) "
                "VALUES(?,'synthetic/core','{}')",
                (repository,),
            )
            bind(store, repository, service, "101")
            binding = store.one(
                "SELECT repository_binding_id FROM repository_bindings "
                "WHERE repository_uuidv4=?",
                (repository,),
            )[0]
            store.execute(
                "INSERT INTO sources(source_id,source_registration_uuidv4,"
                "service_instance_uuidv4,discovery_kind,name,settings) "
                "VALUES('source',?,?,'github_inventory','synthetic','{\"owner\":\"synthetic\"}')",
                (source, service),
            )
            store.execute(
                "INSERT INTO source_repositories(source_id,repository_uuidv4) "
                "VALUES('source',?)",
                (repository,),
            )
            # Review ownership is a typed identity, never a fabricated PR fact.
            store.execute(
                "INSERT INTO change_requests VALUES(?,?,?,'pull_request',7)",
                (request, repository, binding),
            )
            store.publish()
        yield CoreCatalog(state, store, repository, service, binding, request)
        assert store.all("PRAGMA foreign_key_check") == []
        assert store.one("PRAGMA integrity_check")[0] == "ok"


def assert_no_originals_or_selection(store):
    for table in (
        "fetch_occurrences",
        "source_input_observations",
        "stored_bytes",
        "payloads",
        "parsed_results",
        "change_request_observations",
        "document_observations",
    ):
        assert store.one(f"SELECT count(*) FROM {table}")[0] == 0, table
    tables = [
        row[0]
        for row in store.all("SELECT name FROM sqlite_schema WHERE type='table'")
        if row[0].startswith(("parser_profile", "fact_selection"))
        or row[0] == "local_parser_profile_verification_trust"
    ]
    for table in tables:
        assert store.one(f"SELECT count(*) FROM {table}")[0] == 0, table
    assert OPAQUE not in "\n".join(store.connection.iterdump())


def current_api_response(request):
    values = {
        "/user": {"id": 10},
        "/repos/synthetic/core/issues": [
            {
                "id": 1,
                "number": 1,
                "title": "needle Issue",
                "body": "retained Issue body",
                "state": "open",
                "updated_at": "2026-01-01T00:00:00Z",
                "opaque_api_extension": OPAQUE,
            }
        ],
        "/repos/synthetic/core/issues/1/comments": [
            {
                "id": 2,
                "body": "needle ordinary comment",
                "updated_at": "2026-01-01T00:00:00Z",
                "opaque_api_extension": OPAQUE,
            }
        ],
        "/repos/synthetic/core/pulls/7/reviews": [
            {"id": 3, "body": "needle review", "state": "APPROVED"}
        ],
        "/repos/synthetic/core/pulls/7/comments": [
            {
                "id": 4,
                "body": "needle review comment",
                "pull_request_review_id": 3,
                "updated_at": "2026-01-01T00:00:00Z",
                "opaque_api_extension": OPAQUE,
            }
        ],
    }
    assert request.method == "GET"
    return httpx.Response(200, json=values[request.url.path])


def acquire(catalog, recorder=None):
    job = catalog.job()
    with catalog.collector(current_api_response, recorder) as collector:
        assert collector.sync_issues(catalog.repo, job)["state"] == "complete"
        for kind, suffix, parser in (
            ("review", "reviews", current_parser.review),
            ("review-comment", "comments", current_parser.review_comment),
        ):
            collector.current_collection(
                catalog.repo,
                catalog.request,
                kind,
                job,
                API + "/repos/synthetic/core/pulls/7/" + suffix,
                parser,
            )
    JobService(catalog.store).update(job, "complete")


def test_live_acquisition_and_ordinary_reads_need_no_saved_inputs(core_catalog):
    catalog = core_catalog
    acquire(catalog)
    assert_no_originals_or_selection(catalog.store)
    assert catalog.store.one("SELECT count(*) FROM issue_resources")[0] == 2
    assert catalog.store.one("SELECT count(*) FROM review_resources")[0] == 2
    for table in ("issue_resources", "review_resources", "current_collection_pages"):
        producers = catalog.store.all(
            f"SELECT DISTINCT parser_module,parser_version FROM {table}"
        )
        assert [tuple(row) for row in producers] == [
            (current_parser.PARSER_MODULE, current_parser.PARSER_VERSION)
        ]
    assert len(catalog.query("issue list").data["items"]) == 1
    assert (
        len(catalog.query("issue comments", provider_issue_number=1).data["items"]) == 1
    )
    assert {
        item["document_kind"]
        for item in catalog.query(
            "pr documents", provider_change_request_number=7
        ).data["items"]
    } == {"review", "review-comment"}
    rebuild(catalog.store, "issue")
    rebuild(catalog.store, "pr")
    assert len(catalog.query("search issue", literal="needle").data["items"]) == 2
    assert len(catalog.query("search pr", literal="needle").data["items"]) == 2


@pytest.mark.parametrize("selective", [False, True])
def test_deleted_optional_archives_do_not_affect_exchange_or_restore(
    core_catalog, tmp_path, selective
):
    catalog = core_catalog
    archive = catalog.state / "transport-archive"
    acquire(catalog, LocalFileRecorder(archive))
    assert list(archive.glob("*.body"))
    shutil.rmtree(archive)
    assert_no_originals_or_selection(catalog.store)
    options = {}
    if selective:
        options["fetch_collection_id"] = catalog.store.one(
            "SELECT fetch_collection_id FROM fetch_collections WHERE kind='review-comment'"
        )[0]
    exchange = tmp_path / "domain-exchange.json"
    ExchangeService(catalog.state).export_repository(
        catalog.repository, exchange, **options
    )
    records = json.loads(exchange.read_text())["records"]
    assert not {
        "fetch_occurrences",
        "parsed_results",
        "parser_profiles",
        "stored_bytes",
        "payloads",
    } & {record["table"] for record in records}
    receiver = tmp_path / "receiver"
    MaintenanceService(receiver).init("catalog-text-v1", 67_108_864, 0)
    result = ExchangeService(receiver).import_file(exchange)
    assert result.data["staged_records"] == 0
    assert result.data["rejected_records"] == 0
    with Store(receiver) as received:
        assert_no_originals_or_selection(received)
        assert received.one("SELECT count(*) FROM eligible_review_resources")[0] == 2
        assert (
            received.one(
                "SELECT body FROM text_bodies WHERE body LIKE ?",
                ("%needle review comment%",),
            )[0]
            == "needle review comment"
        )
        assert received.all("PRAGMA foreign_key_check") == []
    backup = tmp_path / "domain-backup.sqlite3"
    MaintenanceService(catalog.state).backup(catalog.store, backup)
    restored = tmp_path / "restored"
    MaintenanceService(restored).restore(backup)
    with Store(restored) as store:
        assert_no_originals_or_selection(store)
        assert store.one("SELECT count(*) FROM eligible_issue_resources")[0] == 2
        assert store.one("SELECT count(*) FROM eligible_review_resources")[0] == 2
        assert store.all("PRAGMA foreign_key_check") == []
    assert not (restored / "transport-archive").exists()
    assert (
        len(
            QueryService(restored)
            .query("search pr", {"repo": catalog.repository, "literal": "needle"})
            .data["items"]
        )
        == 2
    )


def test_optional_recorder_failure_does_not_gate_domain_persistence(core_catalog):
    class BrokenRecorder:
        def record_exchange(self, context, body):
            raise OSError("synthetic unavailable diagnostic archive")

    with pytest.warns(RuntimeWarning, match="recording failed"):
        acquire(core_catalog, BrokenRecorder())
    assert_no_originals_or_selection(core_catalog.store)
    assert (
        core_catalog.store.one("SELECT count(*) FROM eligible_issue_resources")[0] == 2
    )
    assert (
        core_catalog.store.one("SELECT count(*) FROM eligible_review_resources")[0] == 2
    )


def test_actual_parser_overrides_context_claims_and_distinguishes_null_from_missing():
    context = {
        "acquisition_scope": {},
        "parser_module": "invented.module",
        "parser_version": "invented-version",
    }
    missing = current_parser.review({"id": 1}, context, 0)
    null = current_parser.review({"id": 1, "body": None}, context, 0)
    assert "body" not in missing and "body_status" not in missing
    assert "body" not in null and null["body_status"] == "provider-null"
    for result in (missing, null):
        assert result["parser_module"] == current_parser.__name__
        assert result["parser_version"] == current_parser.PARSER_VERSION


def test_partial_merges_keep_actual_per_field_producers(core_catalog):
    catalog = core_catalog
    full = catalog.candidate(
        version="1", title="original title", body="first body", author="first author"
    )
    assert catalog.admit(full).status == "accepted"
    assert (
        catalog.admit(
            catalog.candidate(version="2", clock=20, body="second body")
        ).status
        == "accepted"
    )
    # An old complete parse can add unknown facts, with its own original evidence.
    assert (
        catalog.admit(
            catalog.candidate(
                version="99",
                clock=5,
                title="older title",
                body="older body",
                author=None,
                url="https://synthetic.example/old-observation",
            )
        ).status
        == "accepted"
    )
    row = catalog.store.one("SELECT * FROM issue_resources")
    proof = json.loads(row["field_evidence_json"])
    assert row["title"] == "original title"
    assert row["author"] == "first author"
    assert proof['["title"]']["parser_version"] == "1"
    assert proof['["author"]']["parser_version"] == "1"
    assert proof['["body"]']["parser_version"] == "2"
    assert proof['["url"]']["parser_version"] == "99"
    assert proof['["url"]']["provider_updated_at_us"] == 5
    assert {entry["parser_module"] for entry in proof.values()} == {__name__}
    assert_no_originals_or_selection(catalog.store)


def test_explicit_null_is_retained_when_a_later_parse_omits_the_field(core_catalog):
    catalog = core_catalog
    assert (
        catalog.admit(
            catalog.candidate(
                title="initial title", body="initial body", author="initial"
            )
        ).status
        == "accepted"
    )
    assert (
        catalog.admit(
            catalog.candidate(
                version="2", clock=20, body_status="provider-null", author=None
            )
        ).status
        == "accepted"
    )
    assert (
        catalog.admit(
            catalog.candidate(version="3", clock=30, title="new title")
        ).status
        == "accepted"
    )
    row = catalog.store.one("SELECT * FROM issue_resources")
    proof = json.loads(row["field_evidence_json"])
    assert row["body_status"] == "provider-null"
    assert row["text_body_sha256"] is None
    assert row["author"] is None
    assert proof['["body"]']["parser_version"] == "2"
    assert proof['["author"]']["parser_version"] == "2"
    assert proof['["title"]']["parser_version"] == "3"
    assert_no_originals_or_selection(catalog.store)


def test_identical_values_from_another_parser_version_do_not_create_conflicts(
    core_catalog,
):
    catalog = core_catalog
    initial = catalog.candidate(body="same domain value")
    assert catalog.admit(initial).status == "accepted"
    assert catalog.admit({**initial, "parser_version": "99"}).status == "identical"
    assert (
        catalog.store.one("SELECT count(*) FROM current_resource_diagnostics")[0] == 0
    )
    assert catalog.store.one("SELECT count(*) FROM eligible_issue_resources")[0] == 1
    assert_no_originals_or_selection(catalog.store)


@pytest.mark.parametrize("version", ["0.1", "100000.0", "zzz"])
def test_parser_version_never_resolves_equal_clock_domain_conflict(
    core_catalog, version
):
    catalog = core_catalog
    assert catalog.admit(catalog.candidate(body="first body")).status == "accepted"
    assert (
        catalog.admit(
            catalog.candidate(version=version, body="contradictory body")
        ).status
        == "conflict"
    )
    assert catalog.store.one("SELECT count(*) FROM eligible_issue_resources")[0] == 0
    assert catalog.query("issue list").data["items"] == []
    assert (
        catalog.admit(
            catalog.candidate(version="0", clock=11, body="provider-resolved body")
        ).status
        == "accepted"
    )
    assert (
        catalog.store.one("SELECT count(*) FROM current_resource_diagnostics")[0] == 0
    )
    assert len(catalog.query("issue list").data["items"]) == 1
    assert_no_originals_or_selection(catalog.store)


def test_incomplete_pagination_cannot_publish_complete_coverage(core_catalog):
    catalog = core_catalog

    def respond(request):
        if request.url.params.get("page") == "2":
            return httpx.Response(503, json={"message": "synthetic failed page"})
        return httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "number": 1,
                    "title": "retained first page",
                    "state": "open",
                    "body": "first page domain text",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ],
            headers={"Link": f'<{API}/repos/synthetic/core/issues?page=2>; rel="next"'},
        )

    job = catalog.job()
    with catalog.collector(respond) as collector:
        with pytest.raises(CatalogError):
            collector.current_collection(
                catalog.repo,
                None,
                "issue",
                job,
                API + "/repos/synthetic/core/issues",
                current_parser.issue,
            )
    assert catalog.store.one("SELECT count(*) FROM issue_resources")[0] == 1
    assert catalog.store.one("SELECT count(*) FROM completion_markers")[0] == 0
    assert (
        catalog.store.one("SELECT coverage_state FROM current_coverage")[0] == "partial"
    )
    collection = catalog.store.one("SELECT fetch_collection_id FROM fetch_collections")[
        0
    ]
    assert CurrentCollectionProof(catalog.store.connection).evidence(collection) is None
    assert_no_originals_or_selection(catalog.store)
