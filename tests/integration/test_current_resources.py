"""Synthetic SQLite behavior at the mutable-resource admission boundary."""

import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.schema import (
    DDL_SHA256,
    FORMAT_ID,
    SCHEMA_VERSION,
    schema_sql,
)
from repo_catalog.domain.models import CatalogError


@pytest.fixture
def resources(tmp_path):
    path = tmp_path / "current-resources.db"
    db = sqlite3.connect(path, autocommit=True)
    db.row_factory = sqlite3.Row
    db.executescript(schema_sql())
    db.execute(
        "INSERT INTO database_identity VALUES(1,?,?,?,?,?,'validated')",
        (FORMAT_ID, SCHEMA_VERSION, str(uuid.uuid4()), 0, DDL_SHA256),
    )
    service, repo, binding, change = (str(uuid.uuid4()) for _ in range(4))
    db.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','synthetic','{}')",
        (service,),
    )
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic','{}')",
        (repo,),
    )
    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata) VALUES(?,?,?,'11','{}')",
        (binding, repo, service),
    )
    db.execute(
        "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)",
        (change, repo, binding),
    )
    capabilities = [
        {"owner_kind": "repository", "fact_kind": kind}
        for kind in ("issue", "ordinary-issue-comment", "review", "review-comment")
    ]
    definition = {
        "implementation": {"fixture": "current-resources"},
        "settings": {},
        "output_schema": {},
        "capabilities": capabilities,
    }
    model = ParserModel(db)
    profile = model.register_profile(definition)
    verification = model.verify_profile(
        profile,
        criteria={"synthetic": True},
        evidence={
            "definition": definition,
            "capabilities": [
                {
                    **capability,
                    "outcome": "passed",
                    "checks": ["synthetic admission fixture"],
                }
                for capability in capabilities
            ],
        },
    )
    model.trust_verification(verification, rationale={"synthetic": True})
    for capability in capabilities:
        model.ensure_scope_profile(
            profile, repository_uuidv4=repo, fact_kind=capability["fact_kind"]
        )
    context = {
        "service_instance_uuidv4": service,
        "repository_uuidv4": repo,
        "repository_binding_id": binding,
    }
    adapter = CurrentResources(db)
    yield adapter, context, profile, change, path
    db.close()


def issue(resources, **changes):
    _, context, profile, _, _ = resources
    return {
        **context,
        "kind": "issue",
        "provider_resource_id": "12",
        "provider_issue_number": 2,
        "body": "original\nbody\x00suffix",
        "title": "issue title",
        "state": "open",
        "provider_updated_at_us": 10,
        "provider_clock_scope": "github-issue-updated-at",
        "observed_at_us": 0,
        "parsed_at_us": 1,
        "parser_profile_uuidv4": profile,
        "metadata": {"labels": ["synthetic"], "nested": {"known": True}},
        "acquisition_scope": {**context, "endpoint": "issues"},
        **changes,
    }


def current(adapter, table="issue_resources"):
    row = adapter.c.execute(f"SELECT * FROM {table}").fetchone()
    return adapter.candidate_from_row(table, row) if row is not None else None


def test_shared_physical_storage_replaces_marker_and_review_history(resources):
    adapter, context, profile, change, _ = resources
    assert adapter.admit(issue(resources), source="import").status == "accepted"
    comment = issue(
        resources,
        kind="issue-comment",
        provider_resource_id="12",
        parent_provider_resource_id="12",
        title=None,
        state=None,
        body="distinct comment",
        provider_clock_scope="github-issue-comment-updated-at",
    )
    assert adapter.admit(comment, source="import").status == "accepted"
    review = {
        **context,
        "kind": "review",
        "change_request_id": change,
        "provider_change_request_document_id": "12",
        "body": "review",
        "state": "DISMISSED",
        "submitted_at_us": 0,
        "observed_at_us": -1,
        "parsed_at_us": 1,
        "parser_profile_uuidv4": profile,
        "acquisition_scope": {
            **context,
            "change_request_id": change,
            "endpoint": "reviews",
        },
    }
    assert adapter.admit(review, source="import").status == "accepted"
    review_comment = {
        **review,
        "kind": "review-comment",
        "state": None,
        "submitted_at_us": None,
        "body": "review comment",
        "review_provider_resource_id": "12",
    }
    assert adapter.admit(review_comment, source="import").status == "accepted"
    assert adapter.c.execute("SELECT count(*) FROM issue_resources").fetchone()[0] == 2
    assert adapter.c.execute("SELECT count(*) FROM review_resources").fetchone()[0] == 2
    assert (
        adapter.c.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name IN ('reviews','review_comments')"
        ).fetchall()
        == []
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM document_observations").fetchone()[0]
        == 0
    )
    assert adapter.c.execute("PRAGMA foreign_key_check").fetchall() == []


def test_edit_and_identical_refresh_have_no_normalized_versions(resources):
    adapter, *_ = resources
    first = issue(resources)
    assert adapter.admit(first, source="import").status == "accepted"
    assert (
        adapter.admit(issue(resources, observed_at_us=500), source="import").status
        == "identical"
    )
    assert current(adapter)["observed_at_us"] == 0
    assert (
        adapter.admit(
            issue(resources, body="edited", provider_updated_at_us=20), source="import"
        ).status
        == "accepted"
    )
    assert adapter.admit(first, source="replay").status == "stale"
    assert current(adapter)["body"] == "edited"
    assert adapter.c.execute("SELECT count(*) FROM issue_resources").fetchone()[0] == 1
    assert adapter.c.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 2
    assert adapter.c.execute("SELECT count(*) FROM parsed_results").fetchone()[0] == 0


@pytest.mark.parametrize("updated", [None, 10])
def test_unordered_values_hide_incumbent_even_if_received_later(resources, updated):
    adapter, *_ = resources
    adapter.admit(issue(resources, provider_updated_at_us=updated), source="import")
    assert (
        adapter.admit(
            issue(
                resources,
                body="conflicting",
                provider_updated_at_us=updated,
                observed_at_us=999,
            ),
            source="import",
        ).status
        == "conflict"
    )
    assert current(adapter)["body"].startswith("original")
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
        == 0
    )
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM current_resource_diagnostics"
        ).fetchone()[0]
        == 1
    )


def test_newer_than_incumbent_must_also_dominate_staged_clock(resources):
    adapter, *_ = resources
    adapter.admit(issue(resources), source="import")
    adapter.admit(
        issue(resources, body="unclocked", provider_updated_at_us=None), source="import"
    )
    assert (
        adapter.admit(
            issue(resources, body="later clock", provider_updated_at_us=20),
            source="import",
        ).status
        == "conflict"
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
        == 0
    )


def test_fresh_serialized_live_scope_resolves_unknown_conflict(resources):
    adapter, *_ = resources
    adapter.admit(issue(resources, provider_updated_at_us=None), source="import")
    adapter.admit(
        issue(resources, body="unknown fork", provider_updated_at_us=None),
        source="import",
    )
    candidate = issue(resources, provider_updated_at_us=None, observed_at_us=12)
    revision, scope = adapter.capture_context(candidate["acquisition_scope"])
    assert (
        adapter.admit(
            candidate, source="live", base_revision=revision, scope_context=scope
        ).status
        == "identical"
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
        == 1
    )
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM current_resource_diagnostics"
        ).fetchone()[0]
        == 0
    )


def test_stale_revision_and_wrong_scope_do_not_certify_live_order(resources):
    adapter, *_ = resources
    first = issue(resources, provider_updated_at_us=None)
    revision, scope = adapter.capture_context(first["acquisition_scope"])
    adapter.admit(first, source="import")
    changed = issue(resources, body="later arrival", provider_updated_at_us=None)
    assert (
        adapter.admit(
            changed, source="live", base_revision=revision, scope_context=scope
        ).status
        == "conflict"
    )
    revision, _ = adapter.capture_context(scope)
    assert (
        adapter.admit(
            changed,
            source="live",
            base_revision=revision,
            scope_context={**scope, "endpoint": "wrong endpoint"},
        ).status
        == "conflict"
    )
    assert current(adapter)["body"] == first["body"]


def test_partial_and_provider_null_are_distinct_from_empty_and_missing(resources):
    adapter, *_ = resources
    adapter.admit(issue(resources), source="import")
    partial = issue(
        resources, provider_updated_at_us=20, metadata={"nested": {"new": True}}
    )
    for field in ("body", "title"):
        partial.pop(field)
    assert adapter.admit(partial, source="import").status == "accepted"
    assert current(adapter)["body"].endswith("\x00suffix")
    assert current(adapter)["metadata"]["nested"] == {"known": True, "new": True}
    null = {**partial, "body_status": "provider-null", "provider_updated_at_us": 30}
    assert adapter.admit(null, source="import").status == "accepted"
    assert current(adapter)["body"] is None
    assert current(adapter)["body_status"] == "provider-null"
    empty = {**partial, "body": "", "provider_updated_at_us": 40}
    assert adapter.admit(empty, source="import").status == "accepted"
    assert current(adapter)["body"] == ""
    assert current(adapter)["body_status"] == "present"
    assert adapter.c.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 2


def test_missing_parent_survives_restart_then_promotes(resources):
    adapter, _, _, _, path = resources
    comment = issue(
        resources,
        kind="issue-comment",
        provider_resource_id="23",
        parent_provider_resource_id="12",
        title=None,
        state=None,
        body="waiting comment",
        provider_clock_scope="github-issue-comment-updated-at",
    )
    assert adapter.admit(comment, source="import").status == "missing_dependency"
    adapter.c.close()
    db = sqlite3.connect(path, autocommit=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    adapter.c = db
    adapter.admit(issue(resources), source="import")
    assert adapter.promote_staging() == 1
    assert (
        db.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0] == 2
    )
    assert (
        db.execute("SELECT count(*) FROM current_resource_diagnostics").fetchone()[0]
        == 0
    )
    db.close()


def test_issue_membership_transfer_preserves_natural_identity_and_children(resources):
    adapter, context, profile, _, _ = resources
    adapter.admit(issue(resources), source="import")
    comment = issue(
        resources,
        kind="issue-comment",
        provider_resource_id="23",
        parent_provider_resource_id="12",
        title=None,
        state=None,
        body="comment",
        provider_clock_scope="github-issue-comment-updated-at",
    )
    adapter.admit(comment, source="import")
    repo, binding = str(uuid.uuid4()), str(uuid.uuid4())
    adapter.c.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'destination','{}')",
        (repo,),
    )
    adapter.c.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata) VALUES(?,?,?,'22','{}')",
        (binding, repo, context["service_instance_uuidv4"]),
    )
    ParserModel(adapter.c).ensure_scope_profile(
        profile, repository_uuidv4=repo, fact_kind="issue"
    )
    ParserModel(adapter.c).ensure_scope_profile(
        profile, repository_uuidv4=repo, fact_kind="ordinary-issue-comment"
    )
    moved = issue(
        resources,
        repository_uuidv4=repo,
        repository_binding_id=binding,
        provider_issue_number=7,
        provider_updated_at_us=20,
        acquisition_scope={
            **context,
            "repository_uuidv4": repo,
            "repository_binding_id": binding,
            "endpoint": "issues",
        },
    )
    assert adapter.admit(moved, source="import").status == "accepted"
    rows = adapter.c.execute(
        "SELECT repository_uuidv4,provider_issue_number FROM issue_resources"
    ).fetchall()
    assert [tuple(row) for row in rows] == [(repo, 7), (repo, 7)]
    assert adapter.c.execute("PRAGMA foreign_key_check").fetchall() == []


def test_staging_repeated_conflict_dedupes_semantic_values(resources):
    adapter, *_ = resources
    adapter.admit(issue(resources), source="import")
    for observed in range(12):
        assert (
            adapter.admit(
                issue(resources, body="fork", observed_at_us=observed), source="import"
            ).status
            == "conflict"
        )
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM current_resource_diagnostics"
        ).fetchone()[0]
        == 1
    )
    exported = adapter.export_candidates(issue(resources)["repository_uuidv4"])
    assert len(exported) == 2
    assert all(conflicted for _, _, conflicted in exported)
    assert (
        json.loads(
            adapter.c.execute(
                "SELECT record_json FROM current_resource_diagnostics"
            ).fetchone()[0]
        )["body"]
        == "fork"
    )


def test_identical_later_provider_clock_fences_intermediate_delayed_edit(resources):
    adapter, *_ = resources
    adapter.admit(issue(resources), source="import")
    assert (
        adapter.admit(
            issue(resources, provider_updated_at_us=30), source="import"
        ).status
        == "identical"
    )
    assert current(adapter)["provider_updated_at_us"] == 30
    assert (
        adapter.admit(
            issue(resources, body="intermediate stale", provider_updated_at_us=20),
            source="import",
        ).status
        == "stale"
    )
    assert current(adapter)["body"].startswith("original")


def test_identical_newer_clock_resolves_all_comparable_tied_alternatives(resources):
    adapter, *_ = resources
    adapter.admit(issue(resources), source="import")
    adapter.admit(issue(resources, body="tied alternative"), source="import")
    assert (
        adapter.admit(
            issue(resources, provider_updated_at_us=30), source="import"
        ).status
        == "identical"
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_issue_resources").fetchone()[0]
        == 1
    )
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM current_resource_diagnostics"
        ).fetchone()[0]
        == 0
    )


def test_tied_live_response_requires_matching_prerequest_fence(resources):
    adapter, *_ = resources
    adapter.admit(issue(resources), source="import")
    changed = issue(resources, body="same-second provider edit", observed_at_us=999)
    assert adapter.admit(changed, source="live").status == "conflict"
    revision, scope = adapter.capture_context(changed["acquisition_scope"])
    assert (
        adapter.admit(
            changed, source="live", base_revision=revision, scope_context=scope
        ).status
        == "accepted"
    )
    assert current(adapter)["body"] == changed["body"]
    assert current(adapter)["provider_updated_at_us"] == 10


def test_provider_clock_scope_cannot_be_invented_for_reviews(resources):
    adapter, context, profile, change, _ = resources
    candidate = {
        **context,
        "kind": "review",
        "change_request_id": change,
        "provider_change_request_document_id": "14",
        "body": "pending review",
        "observed_at_us": 0,
        "parsed_at_us": 1,
        "parser_profile_uuidv4": profile,
        "provider_updated_at_us": 100,
        "provider_clock_scope": "invented-submission-clock",
        "acquisition_scope": {
            **context,
            "change_request_id": change,
            "endpoint": "reviews",
        },
    }
    with pytest.raises(CatalogError, match="clock"):
        adapter.admit(candidate, source="import")


def test_late_owner_mismatch_does_not_block_independent_parent_promotion(resources):
    adapter, context, _, _, _ = resources
    invalid_late = issue(
        resources,
        kind="issue-comment",
        provider_resource_id="23",
        parent_provider_resource_id="12",
        title=None,
        state=None,
        body="old repository association",
        provider_clock_scope="github-issue-comment-updated-at",
    )
    valid_late = {
        **invalid_late,
        "provider_resource_id": "24",
        "parent_provider_resource_id": "13",
        "provider_issue_number": 3,
    }
    assert adapter.admit(invalid_late, source="import").status == "missing_dependency"
    assert adapter.admit(valid_late, source="import").status == "missing_dependency"
    other_repo, other_binding = str(uuid.uuid4()), str(uuid.uuid4())
    adapter.c.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'other','{}')",
        (other_repo,),
    )
    adapter.c.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata) VALUES(?,?,?,'33','{}')",
        (other_binding, other_repo, context["service_instance_uuidv4"]),
    )
    owner = {
        **context,
        "repository_uuidv4": other_repo,
        "repository_binding_id": other_binding,
    }
    adapter.admit(
        issue(resources, **owner, acquisition_scope={**owner, "endpoint": "issues"}),
        source="import",
    )
    adapter.admit(
        issue(resources, provider_resource_id="13", provider_issue_number=3),
        source="import",
    )
    assert adapter.promote_staging() == 1
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM issue_resources WHERE kind='issue-comment'"
        ).fetchone()[0]
        == 1
    )
    assert (
        adapter.c.execute("SELECT reason FROM current_resource_diagnostics").fetchone()[
            0
        ]
        == "current_state:invalid"
    )
