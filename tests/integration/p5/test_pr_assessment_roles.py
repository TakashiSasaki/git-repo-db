"""Actual captured role targets and independent exact code scopes."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.github.production_intake import make_document_key
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.acquisition_errors import AcquisitionError
from repo_catalog.domain.p1_context import FieldCandidate, FieldClock, canonical
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.pr_assessment import anchored_code_scope
from repo_catalog.domain.provider_acquisition import (
    ProviderCommitContextIntake,
    ProviderPullRequestIntake,
    ProviderReviewIntake,
    make_provenance,
)
from tests.integration.p5.test_pr_assessment import Fixture
from tests.support.context_admission import (
    fixture_context,
    fixture_service,
    fixture_transaction,
)


@pytest.mark.parametrize(
    "role",
    [
        "head-absent",
        "base-null",
        "merge-unavailable",
        "head-tree",
        "base-unavailable",
        "complete",
    ],
)
def test_exact_actual_current_role_targets_control_assessment_even_after_complete_labels(
    tmp_path, role
):
    fixture = Fixture(tmp_path)
    fixture.code()
    assert fixture.query().state == "complete"
    payload = {**fixture.payload, "updated_at": "2026-02-01T00:00:00Z"}
    if role == "head-absent":
        payload["head"] = None
    elif role == "base-null":
        payload["base"] = None
    elif role == "merge-unavailable":
        payload["merge_commit_sha"] = "a" * 40
    elif role == "head-tree":
        fixture.head = fixture.objects["tree"]
        fixture.commit = make_document_key(
            fixture.parent, "pr_commit", "pr_commit", fixture.head.object_oid
        )
        payload["head"] = {"sha": fixture.head.object_oid}
    elif role == "base-unavailable":
        fixture.base = OID("sha1", "a" * 40)
        payload["base"] = {"sha": fixture.base.object_oid}
    fixture.grants = replace(
        fixture.grants,
        resources=fixture.grants.resources | {fixture.commit},
        object_oids=fixture.grants.object_oids | {fixture.head, fixture.base},
    )
    fixture.auth, _ = fixture_service(fixture.grants)
    fixture.admission = fixture_context(fixture.auth)
    fixture.api = ProviderAcquisition(
        tmp_path, core=tmp_path, authorization=fixture.auth, admission=fixture.admission
    )
    fixture.anchor = make_provenance("actual-role-fixture", {"read": role})
    fixture.admit(
        pull_requests=(ProviderPullRequestIntake(payload, 400, fixture.anchor),)
    )
    fixture.code(observed=500)
    result = fixture.query()
    assert (result.state == "complete") == (role == "complete")
    if role == "head-tree":
        assert result.git_metadata["reason"] == "role_target_type_conflict"
    if role == "merge-unavailable":
        assert result.anchors["merge"] == ["sha1", "a" * 40]
        assert result.git_metadata["reason"] == "role_metadata_unavailable"


def test_partial_commit_prefix_cannot_inherit_complete_independent_file_scope(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.code()
    before = fixture.query()
    commit_listing = next(
        row for row in before.collections if row["kind"] == "pr_commits"
    )
    alternative = commit_listing["alternatives"][0]
    fixture.observation(
        fixture.parent,
        "pr_commits",
        make_provenance("actual-role-fixture", {"read": "partial-commits"}),
        alternative["scope_json"],
        400,
        "partial",
        (),
    )
    after = fixture.query()
    states = {row["kind"]: row["state"] for row in after.collections}
    assert states == {"pr_commits": "partial", "pr_files": "complete"}
    assert after.state == "partial"
    assert any(gap["kind"] == "pr_commits" for gap in after.coverage["missing"])


def test_equivalent_capture_without_embedded_count_uses_only_actual_coobserved_current_count(
    tmp_path,
):
    fixture = Fixture(tmp_path)
    fixture.code()
    original = fixture.query()
    for listing in original.collections:
        scope = json.loads(listing["alternatives"][0]["scope_json"])
        del scope["expected_count"]
        fixture.observation(
            fixture.parent,
            listing["kind"],
            make_provenance(
                "actual-role-fixture",
                {"read": "equivalent-no-count-" + listing["kind"]},
            ),
            canonical(scope),
            300,
            "complete",
            (fixture.commit,) if listing["kind"] == "pr_commits" else fixture.files[:2],
        )
    equivalent = fixture.query()
    assert equivalent.state == "complete"
    assert len(equivalent.collections[0]["alternatives"]) == 2
    assert len(equivalent.collections[1]["alternatives"]) == 2
    assert any(
        "expected_count" not in json.loads(row["scope_json"])
        for row in equivalent.collections[0]["alternatives"]
    )


def test_actual_same_clock_reported_count_conflict_requires_genuine_newer_detail_and_listing(
    tmp_path,
):
    fixture = Fixture(tmp_path)
    fixture.code()
    assert fixture.query().state == "complete"

    fixture.admit(
        pull_requests=(
            ProviderPullRequestIntake(
                {**fixture.payload, "changed_files": 3},
                300,
                make_provenance("actual-role-fixture", {"read": "count-conflict"}),
            ),
        )
    )
    conflict = fixture.query()
    assert conflict.state == "conflict" and conflict.page.items == ()
    assert any(
        gap["reason"] == "current_reported_count_conflict"
        for gap in conflict.coverage["missing"]
    )
    fixture.anchor = make_provenance(
        "actual-role-fixture", {"read": "genuinely-new-count"}
    )
    fixture.admit(
        pull_requests=(
            ProviderPullRequestIntake(
                {**fixture.payload, "updated_at": "2026-02-01T00:00:00Z"},
                400,
                fixture.anchor,
            ),
        )
    )
    assert fixture.query().state != "complete"
    fixture.code(observed=500)
    assert fixture.query().state == "complete"


@pytest.mark.parametrize("count", [True, 2.0])
def test_malformed_current_count_cannot_equal_a_typed_embedded_count(tmp_path, count):
    fixture = Fixture(tmp_path)
    # Live Provider normalization rejects these types before admission. Exercise
    # the independent reader guard with an explicit generic Context report.
    with Context.snapshot(tmp_path) as context:
        original = context.candidates(fixture.parent, "changed_files")[0]
    with fixture_transaction(tmp_path, fixture.grants) as context:
        context.admit_field(
            FieldCandidate(
                fixture.parent,
                "changed_files",
                canonical(count),
                FieldClock(original.clock.domain, original.clock.at_us + 1),
                make_provenance(
                    "deliberate-query-count-shape-fixture", {"read": "malformed-count"}
                ),
                400,
            )
        )
    fixture.code(observed=500)
    result = fixture.query()
    assert result.state != "complete"
    assert any(
        gap["reason"] == "current_reported_count_invalid"
        for gap in result.coverage["missing"]
    )


def test_different_current_head_cannot_borrow_historical_exact_listing_even_when_both_commits_are_verified(
    tmp_path,
):
    fixture = Fixture(tmp_path)
    fixture.code()
    assert fixture.query().state == "complete"
    with Context.snapshot(tmp_path) as context:
        old_scopes = context.db.execute(
            "SELECT collection_kind,provenance_json,scope_json FROM collections ORDER BY collection_kind,provenance_json"
        ).fetchall()
    fixture.admit(
        pull_requests=(
            ProviderPullRequestIntake(
                {
                    **fixture.payload,
                    "head": {"sha": fixture.base.object_oid},
                    "updated_at": "2026-02-01T00:00:00Z",
                },
                400,
                make_provenance("actual-role-fixture", {"read": "different-head"}),
            ),
        )
    )
    current = fixture.query()
    assert current.state != "complete" and current.git_metadata["state"] == "complete"
    assert current.anchors["head"] == list(fixture.base.key)
    assert current.page.items == ()
    assert all(
        row["reason"] == "matching_listing_unavailable" for row in current.collections
    )
    with Context.snapshot(tmp_path) as context:
        assert (
            context.db.execute(
                "SELECT collection_kind,provenance_json,scope_json FROM collections ORDER BY collection_kind,provenance_json"
            ).fetchall()
            == old_scopes
        )
        assert (
            context.db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name IN ('code_assessments','change_request_state','change_request_observations')"
            ).fetchall()
            == []
        )


def test_actual_commit_listing_with_other_object_format_never_proves_sha1_comparison(
    tmp_path,
):
    fixture = Fixture(tmp_path)
    fixture.code()
    other = OID("sha256", "b" * 64)
    member = make_document_key(
        fixture.parent, "pr_commit", "pr_commit", other.object_oid
    )
    fixture.grants = replace(
        fixture.grants,
        resources=fixture.grants.resources | {member},
        object_oids=fixture.grants.object_oids | {other},
    )
    fixture.auth, _ = fixture_service(fixture.grants)
    fixture.admission = fixture_context(fixture.auth)
    fixture.api = ProviderAcquisition(
        tmp_path, core=tmp_path, authorization=fixture.auth, admission=fixture.admission
    )
    original = make_provenance("actual-role-fixture", {"read": str(uuid4())})
    fixture.admit(
        pr_commits=(
            ProviderCommitContextIntake(100, {"sha": other.object_oid}, 400, original),
        )
    )
    scope = anchored_code_scope(
        {},
        head=fixture.head,
        base=fixture.base,
        anchor_provenance_json=fixture.anchor,
        member_provenance_jsons=[original],
        expected_count=1,
    )
    fixture.observation(
        fixture.parent, "pr_commits", original, scope, 400, "complete", (member,)
    )
    result = fixture.query()
    assert result.state != "complete"
    assert any(
        gap["reason"] == "captured_member_facts_unavailable"
        for gap in result.coverage["missing"]
    )
    with pytest.raises(ValueError):
        anchored_code_scope(
            {},
            head=fixture.head,
            base=other,
            anchor_provenance_json=fixture.anchor,
            member_provenance_jsons=[original],
        )


@pytest.mark.parametrize(
    "change", [{"head": {"sha": ["head"]}}, {"merge_commit_sha": {"oid": "unparsed"}}]
)
def test_malformed_actual_role_targets_are_refused_before_context_admission(
    tmp_path, change
):
    fixture = Fixture(tmp_path)
    fixture.code()
    before = fixture.query()
    with pytest.raises(AcquisitionError):
        fixture.admit(
            pull_requests=(
                ProviderPullRequestIntake(
                    {**fixture.payload, **change, "updated_at": "2026-02-01T00:00:00Z"},
                    400,
                    make_provenance("actual-role-fixture", {"read": "malformed"}),
                ),
            )
        )
    after = fixture.query()
    assert after.state == before.state == "complete"
    assert after.anchors == before.anchors


@pytest.mark.parametrize(
    "target", ["verified", "unavailable", "tree", "null", "conflict"]
)
def test_captured_review_target_roles_require_actual_commit_metadata_without_inventing_a_review_universe(
    tmp_path, target
):
    fixture = Fixture(tmp_path)
    fixture.code()
    assert fixture.query().state == "complete"
    tree = fixture.objects["tree"]
    fixture.grants = replace(
        fixture.grants, object_oids=fixture.grants.object_oids | {tree}
    )
    fixture.auth, _ = fixture_service(fixture.grants)
    fixture.admission = fixture_context(fixture.auth)
    fixture.api = ProviderAcquisition(
        tmp_path, core=tmp_path, authorization=fixture.auth, admission=fixture.admission
    )
    oid = {
        "verified": fixture.head.object_oid,
        "unavailable": "a" * 40,
        "tree": tree.object_oid,
        "null": None,
        "conflict": fixture.head.object_oid,
    }[target]
    fixture.admit(
        reviews=(
            ProviderReviewIntake(
                100,
                {"id": 200, "commit_id": oid},
                400,
                make_provenance("actual-role-fixture", {"read": "review-target"}),
            ),
        )
    )
    if target == "conflict":
        fixture.admit(
            reviews=(
                ProviderReviewIntake(
                    100,
                    {"id": 200, "commit_id": fixture.base.object_oid},
                    400,
                    make_provenance(
                        "actual-role-fixture", {"read": "independent-review-target"}
                    ),
                ),
            )
        )
    result = fixture.query()
    assert (result.state == "complete") == (target in {"verified", "null"})
    if target != "null":
        assert (
            any(key.startswith("review_target:") for key in result.anchors)
            or target == "conflict"
        )
    if target == "tree":
        assert result.git_metadata["reason"] == "role_target_type_conflict"
    if target == "unavailable":
        assert result.git_metadata["reason"] == "role_metadata_unavailable"
    if target == "conflict":
        assert result.git_metadata["reason"] == "current_review_target_conflict"
