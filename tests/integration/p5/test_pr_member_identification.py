"""Specialized PR proofs cannot borrow another native document namespace."""

import json
from dataclasses import replace

import pytest

from repo_catalog.adapters.github.production_intake import make_document_key
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.provider_acquisition import (
    ProviderCommitContextIntake,
    ProviderFileContextIntake,
    ProviderPullRequestIntake,
    make_provenance,
)
from tests.integration.p5.test_pr_assessment import Fixture
from tests.support.context_admission import fixture_context, fixture_service


@pytest.mark.parametrize("kind", ["pr_commits", "pr_files"])
def test_exact_pr_listing_cannot_borrow_valid_other_pr_document_with_identical_native_fields(
    tmp_path, kind
):
    fixture = Fixture(tmp_path)
    fixture.code()
    assert fixture.query().state == "complete"
    other = ResourceKey.from_native(fixture.service, "pull_request", "101")
    local = fixture.head.object_oid if kind == "pr_commits" else "a.txt"
    subtype = "pr_commit" if kind == "pr_commits" else "pr_file"
    member = make_document_key(other, subtype, subtype, local)
    fixture.grants = replace(
        fixture.grants, resources=fixture.grants.resources | {other, member}
    )
    fixture.auth, _ = fixture_service(fixture.grants)
    fixture.admission = fixture_context(fixture.auth)
    fixture.api = ProviderAcquisition(
        tmp_path,
        repository_store=tmp_path,
        authorization=fixture.auth,
        admission=fixture.admission,
    )
    original = make_provenance("actual-other-pr", {"read": kind})
    fixture.admit(
        pull_requests=(ProviderPullRequestIntake({"id": 101}, 400, original),),
        **{
            kind: (
                (ProviderCommitContextIntake(101, {"sha": local}, 400, original),)
                if kind == "pr_commits"
                else (
                    ProviderFileContextIntake(
                        101, {"filename": local, "patch": "original"}, 400, original
                    ),
                )
            )
        },
    )
    before = fixture.query()
    listing = next(row for row in before.collections if row["kind"] == kind)
    scope = json.loads(listing["alternatives"][0]["scope_json"])
    scope["member_provenance_jsons"].append(original)
    members = (member,) if kind == "pr_commits" else (member, fixture.files[1])
    fixture.observation(
        fixture.parent, kind, original, canonical(scope), 500, "complete", members
    )
    result = fixture.query()
    assert result.state != "complete"
    assert any(
        gap["kind"] == kind and gap["reason"] == "captured_member_facts_unavailable"
        for gap in result.coverage["missing"]
    )
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_file_document_cannot_discharge_commit_listing_even_with_matching_count_and_native_metadata(
    tmp_path,
):
    from repo_catalog.domain.provider_acquisition import make_provenance
    from tests.integration.p5.test_pr_assessment import Fixture

    fixture = Fixture(tmp_path)
    fixture.code()
    before = fixture.query()
    commits = next(row for row in before.collections if row["kind"] == "pr_commits")
    fixture.observation(
        fixture.parent,
        "pr_commits",
        make_provenance("actual-member-kind", {"read": "swapped-file"}),
        commits["alternatives"][0]["scope_json"],
        400,
        "complete",
        (fixture.files[0],),
    )
    after = fixture.query()
    assert after.git_metadata["state"] == "complete"
    assert after.state != "complete"
    listing = next(row for row in after.collections if row["kind"] == "pr_commits")
    assert listing["state"] == "unknown"
    assert listing["reason"] == "captured_member_facts_unavailable"
