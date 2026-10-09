"""Current readers and derived search never require transport message bodies."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.index import rebuild
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.pr_queries import _collection_state, _latest_collections
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.application.target_queries import TargetQueryService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime


@dataclass
class CurrentCatalog:
    state: object
    store: Store
    model: ParserModel
    repository: str
    service: str
    binding: str
    request: str
    profile: str
    verification: str

    def candidate(self, kind, provider, body, **fields):
        scope = {
            "repository_uuidv4": self.repository,
            "service_instance_uuidv4": self.service,
            "repository_binding_id": self.binding,
            "endpoint": "synthetic-current-test",
        }
        candidate = {
            **scope,
            "kind": kind,
            "body": body,
            "author": "reviewer",
            "provider_updated_at_us": None if kind == "review" else 1,
            "provider_clock_scope": {
                "issue": "github-issue-updated-at",
                "issue-comment": "github-issue-comment-updated-at",
                "review-comment": "github-review-comment-updated-at",
            }.get(kind),
            "observed_at_us": 1,
            "parsed_at_us": 2,
            "parser_profile_uuidv4": self.profile,
            "metadata": {},
        }
        candidate.pop("endpoint")
        if kind in ("issue", "issue-comment"):
            candidate.update(provider_resource_id=provider, provider_issue_number=1)
        else:
            candidate.update(
                change_request_id=self.request,
                provider_change_request_document_id=provider,
            )
            scope["change_request_id"] = self.request
        candidate["acquisition_scope"] = scope
        candidate.update(fields)
        return candidate

    def admit(self, candidate):
        with self.store.transaction():
            admitted = CurrentResources(self.store).admit(candidate, source="import")
            self.store.publish()
        return admitted

    def query(self, command, **options):
        return QueryService(self.state).query(
            command, {"repo": self.repository, **options}
        )


@pytest.fixture
def current_catalog(tmp_path):
    state = tmp_path / "current-query-catalog"
    MaintenanceService(state).init("catalog-text-v1", 67_108_864, 0)
    with Store(state) as store:
        model = ParserModel(store.connection)
        repository, request = str(uuid.uuid4()), str(uuid.uuid4())
        with store.transaction():
            service = add_instance(store, "github", "current-query-test")
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'current/test','{}')",
                (repository,),
            )
            bind(store, repository, service, "1")
            binding = store.one(
                "SELECT repository_binding_id FROM repository_bindings WHERE repository_uuidv4=?",
                (repository,),
            )[0]
            store.execute(
                "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)",
                (request, repository, binding),
            )
            definition = {
                "implementation": {"synthetic_current_reader_test": 1},
                "settings": {},
                "output_schema": {"current_resource_test": 1},
                "capabilities": [
                    {"owner_kind": "repository", "fact_kind": kind}
                    for kind in (
                        "issue",
                        "ordinary-issue-comment",
                        "review",
                        "review-comment",
                    )
                ],
            }
            profile = model.register_profile(definition)
            verification = model.verify_profile(
                profile,
                criteria={"test": "current-reader-fixture"},
                evidence={
                    "definition": definition,
                    "capabilities": [
                        {**capability, "outcome": "passed", "checks": ["fixture"]}
                        for capability in definition["capabilities"]
                    ],
                },
            )
            model.trust_verification(verification)
            for capability in definition["capabilities"]:
                model.select_profile(
                    profile,
                    verification,
                    repository_uuidv4=repository,
                    fact_kind=capability["fact_kind"],
                )
            store.coverage(repository, "issue", "complete", observed_at_us=1)
            store.publish()
        yield CurrentCatalog(
            state,
            store,
            model,
            repository,
            service,
            binding,
            request,
            profile,
            verification,
        )
        assert not store.all("PRAGMA foreign_key_check")
        assert store.one("PRAGMA integrity_check")[0] == "ok"


def test_issue_family_keeps_each_comment_and_search_replaces_superseded_text(
    current_catalog,
):
    catalog = current_catalog
    issue = catalog.candidate(
        "issue", "1", "issue body", title="title needle", state="open"
    )
    assert catalog.admit(issue).status == "accepted"
    comment = catalog.candidate(
        "issue-comment", "1", "obsolete needle", parent_provider_resource_id="1"
    )
    assert catalog.admit(comment).status == "accepted"
    assert (
        catalog.admit(
            catalog.candidate(
                "issue-comment", "2", "second comment", parent_provider_resource_id="1"
            )
        ).status
        == "accepted"
    )
    assert len(catalog.query("issue list").data["items"]) == 1
    assert {
        r["provider_resource_id"]
        for r in catalog.query("issue comments", provider_issue_number=1).data["items"]
    } == {"1", "2"}
    assert (
        catalog.query("search issue", literal="title needle").data["items"][0]["field"]
        == "title"
    )
    rebuild(catalog.store, "issue")
    edited = {
        **comment,
        "body": "replacement needle",
        "provider_updated_at_us": 3,
        "observed_at_us": 4,
    }
    assert catalog.admit(edited).status == "accepted"
    assert catalog.admit(edited).status == "identical"
    assert catalog.store.one("SELECT count(*) FROM issue_resources")[0] == 3
    assert catalog.store.one("SELECT count(*) FROM document_observations")[0] == 0
    assert catalog.store.one("SELECT count(*) FROM fetch_occurrences")[0] == 0
    assert catalog.query("search issue", literal="obsolete needle").data["items"] == []
    assert (
        catalog.query("search issue", literal="replacement needle").data["items"][0][
            "body"
        ]
        == edited["body"]
    )
    rebuild(catalog.store, "issue")
    generation = catalog.store.one(
        "SELECT index_generation_id FROM index_generations WHERE kind='issue' AND state='ready'"
    )[0]
    assert not catalog.store.one(
        "SELECT 1 FROM index_membership m JOIN search_documents d USING(search_document_id) WHERE m.index_generation_id=? AND d.source_key=?",
        (generation, hashlib.sha256(comment["body"].encode()).hexdigest()),
    )
    assert not catalog.store.one(
        "SELECT 1 FROM search_documents WHERE kind='issue' AND source_key=?",
        (hashlib.sha256(comment["body"].encode()).hexdigest(),),
    )


def test_current_review_reads_keep_dismissed_reviews_and_no_edit_history(
    current_catalog,
):
    catalog = current_catalog
    review = catalog.candidate(
        "review", "1", "old summary", state="APPROVED", submitted_at_us=0
    )
    assert catalog.admit(review).status == "accepted"
    assert (
        catalog.admit(
            catalog.candidate("review", "2", "dismissed summary", state="DISMISSED")
        ).status
        == "accepted"
    )
    comment = catalog.candidate(
        "review-comment",
        "1",
        "old unique review text",
        review_provider_resource_id="1",
        raw_path="file.py",
        original_position=1,
        current_position=2,
    )
    assert catalog.admit(comment).status == "accepted"
    rebuild(catalog.store, "pr")
    edited = {
        **comment,
        "body": "new unique review text",
        "provider_updated_at_us": 3,
        "observed_at_us": 4,
    }
    assert catalog.admit(edited).status == "accepted"
    documents = catalog.query("pr documents", provider_change_request_number=1).data[
        "items"
    ]
    assert len(documents) == 3
    assert {r["review_state"] for r in documents if r["document_kind"] == "review"} == {
        "APPROVED",
        "DISMISSED",
    }
    assert all(
        r["resource_lifecycle"] == "current" and r["parsed_result_uuidv4"] is None
        for r in documents
    )
    assert catalog.query("search pr", literal=comment["body"]).data["items"] == []
    assert (
        catalog.query("search pr", literal=edited["body"]).data["items"][0][
            "current_position"
        ]
        == 2
    )
    assert catalog.query("pr list", reviewer="reviewer").data["items"]
    assert (
        len(catalog.query("pr documents", document_observations="all").data["items"])
        == 3
    )
    diagnostic = TargetQueryService(catalog.store.db_path).query(
        "pr", {"repo": catalog.repository, "provider_change_request_number": 1}
    )
    assert (
        len(
            [
                r
                for r in diagnostic.data["items"]
                if r["record_kind"] in ("review", "review_comment")
            ]
        )
        == 3
    )
    assert catalog.store.one("SELECT count(*) FROM document_observations")[0] == 0
    assert catalog.store.one("SELECT count(*) FROM parsed_results")[0] == 0


def test_unordered_conflict_and_local_trust_block_current_search(current_catalog):
    catalog = current_catalog
    issue = catalog.candidate(
        "issue", "1", "first value", title="first title", state="open"
    )
    assert catalog.admit(issue).status == "accepted"
    rebuild(catalog.store, "issue")
    conflict = {**issue, "body": "unordered second value", "observed_at_us": 99}
    assert catalog.admit(conflict).status == "conflict"
    result = catalog.query("issue show", provider_issue_number=1)
    assert result.data["items"] == []
    assert any(
        gap["reason"] == "current_resource_unresolved"
        for gap in result.coverage.missing
    )
    assert catalog.query("search issue", literal="first value").data["items"] == []
    resolved = {**issue, "body": "resolved value", "provider_updated_at_us": 2}
    assert catalog.admit(resolved).status == "accepted"
    assert (
        catalog.query("issue show", provider_issue_number=1).data["items"][0]["body"]
        == resolved["body"]
    )
    with catalog.store.transaction():
        catalog.model.trust_verification(catalog.verification, False)
        catalog.store.publish()
    assert catalog.query("search issue", literal="resolved value").data["items"] == []


def test_issue_search_cursor_orders_parent_and_all_child_matches(current_catalog):
    catalog = current_catalog
    catalog.admit(
        catalog.candidate(
            "issue", "10", "needle parent", title="needle title", state="open"
        )
    )
    catalog.admit(
        catalog.candidate(
            "issue-comment", "1", "needle child", parent_provider_resource_id="10"
        )
    )
    catalog.admit(
        catalog.candidate(
            "issue",
            "20",
            "needle other parent",
            state="closed",
            provider_issue_number=2,
        )
    )
    query = QueryService(catalog.state)
    options = {"repo": catalog.repository, "literal": "needle"}
    expected = query.query("search issue", options).data["items"]
    collected, cursor = [], None
    while True:
        result = query.query("search issue", options, limit=1, cursor=cursor)
        collected.extend(result.data["items"])
        cursor = result.data["page"]["next_cursor"]
        if cursor is None:
            break
    assert collected == expected


@pytest.mark.parametrize("family", ["issue", "review-comment"])
def test_corrupt_current_domain_body_rejects_reads_and_index_rebuild(
    current_catalog, family
):
    catalog = current_catalog
    candidate = catalog.candidate(
        family, "1", "saved text", **({"state": "open"} if family == "issue" else {})
    )
    assert catalog.admit(candidate).status == "accepted"
    digest = hashlib.sha256(candidate["body"].encode()).digest()
    # Emulate physical text damage while preserving the production trigger.
    with catalog.store.transaction():
        trigger = catalog.store.one(
            "SELECT sql FROM sqlite_schema WHERE name='text_bodies_immutable'"
        )[0]
        catalog.store.execute("DROP TRIGGER text_bodies_immutable")
        catalog.store.execute(
            "UPDATE text_bodies SET body='wrong text' WHERE sha256=?", (digest,)
        )
        catalog.store.execute(trigger)
        catalog.store.publish()
    command = "issue show" if family == "issue" else "pr documents"
    selector = (
        {"provider_issue_number": 1}
        if family == "issue"
        else {"provider_change_request_number": 1}
    )
    with pytest.raises(CatalogError) as shown:
        catalog.query(command, **selector)
    assert shown.value.code == "TEXT_BODY_IDENTITY_CONFLICT"
    search = "search issue" if family == "issue" else "search pr"
    with pytest.raises(CatalogError) as searched:
        catalog.query(search, literal="saved text")
    assert searched.value.code == "TEXT_BODY_IDENTITY_CONFLICT"
    with pytest.raises(CatalogError) as indexed:
        rebuild(catalog.store, "issue" if family == "issue" else "pr")
    assert indexed.value.code == "TEXT_BODY_IDENTITY_CONFLICT"


def test_null_missing_and_empty_current_bodies_remain_distinct(current_catalog):
    catalog = current_catalog
    issue = catalog.candidate(
        "issue",
        "1",
        None,
        body_status="provider-null",
        title="searchable title",
        state="open",
    )
    assert catalog.admit(issue).status == "accepted"
    shown = catalog.query("issue show", provider_issue_number=1)
    assert shown.status == "complete"
    assert shown.data["items"][0]["body"] is None
    assert shown.data["items"][0]["text_body_sha256"] is None
    assert shown.data["items"][0]["body_status"] == "provider-null"
    catalog.admit(
        catalog.candidate("issue-comment", "2", "", parent_provider_resource_id="1")
    )
    catalog.admit(
        catalog.candidate(
            "issue-comment",
            "3",
            None,
            body_status="inaccessible",
            parent_provider_resource_id="1",
        )
    )
    comments = catalog.query("issue comments", provider_issue_number=1)
    assert comments.status == "partial"
    assert [(row["body"], row["body_status"]) for row in comments.data["items"]] == [
        ("", "present"),
        (None, "inaccessible"),
    ]
    rebuild(catalog.store, "issue")
    assert (
        catalog.query("search issue", literal="searchable title").data["items"][0][
            "field"
        ]
        == "title"
    )


def test_partial_current_page_is_a_new_boundary_without_archive_or_marker(
    current_catalog,
):
    catalog = current_catalog
    proof = CurrentCollectionProof(catalog.store.connection)
    with catalog.store.transaction():
        for identifier in ("old-complete", "new-partial"):
            catalog.store.execute(
                "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,request_context,parser_version,profile_version,confidence) VALUES(?,?,'{}','synthetic','synthetic','proven')",
                (identifier, catalog.repository),
            )
            catalog.store.execute(
                "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,resume_scope_id) VALUES(?,?,?,'review',?)",
                (identifier, catalog.repository, catalog.request, identifier),
            )
        proof.page(
            "old-complete", 0, 1, None, [], parser_profile_uuidv4=catalog.profile
        )
        catalog.store.execute(
            "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES('old-complete','old-complete','complete',?,1)",
            (json.dumps(proof.evidence("old-complete")),),
        )
        proof.page(
            "new-partial",
            0,
            2,
            "continuation",
            [],
            parser_profile_uuidv4=catalog.profile,
        )
    query = SimpleNamespace(s=catalog.store, check=lambda: None)
    old = {"fetch_collection_id": "old-complete", "state": "complete"}
    new = {"fetch_collection_id": "new-partial", "state": "partial"}
    assert _collection_state(query, old) == "complete"
    assert _latest_collections(query, [old, new]) == [new]
    assert _collection_state(query, new) == "partial"
    assert catalog.store.one("SELECT count(*) FROM fetch_occurrences")[0] == 0


def test_real_issue_collection_reports_complete_normal_queries(github_runtime):
    store, repository, _, _ = github_runtime
    job = JobService(store).create("sync", {"kind": "issue"})
    store.expected_attempt = 1
    collector = GitHubCollector(store, CancellationToken())
    try:
        assert collector.sync_issues(repository, job)["issues"] == 2
    finally:
        collector.http.close()
    JobService(store).update(job, "complete")
    assert (
        store.one(
            "SELECT coverage_state FROM current_coverage WHERE repository_uuidv4=? "
            "AND change_request_id IS NULL AND kind='issue'",
            (repository["repository_uuidv4"],),
        )[0]
        == "complete"
    )
    assert store.one("SELECT count(*) FROM fetch_occurrences")[0] == 0
    query = QueryService(store.path)
    for command, options, expected in (
        ("issue list", {}, 2),
        ("issue show", {"provider_issue_number": 1}, 1),
        ("issue comments", {"provider_issue_number": 1}, 1),
        ("search issue", {"literal": "ordinary-issue-comment"}, 2),
    ):
        result = query.query(
            command, {"repo": repository["repository_uuidv4"], **options}
        )
        assert result.status == "complete", (command, result.coverage)
        assert result.coverage.complete_for_requested_scope
        assert result.coverage.missing == []
        assert len(result.data["items"]) == expected
