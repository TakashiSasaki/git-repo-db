"""Current exact comparisons consult actual qualified native ref reads."""

import subprocess
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.domain.git_acquisition import GitNativeAcquisitionRequest
from repo_catalog.domain.p1_context import canonical
from repo_catalog.domain.pr_assessment import git_role_check_scope
from repo_catalog.domain.provider_acquisition import make_provenance
from repo_catalog.domain.ref_observation import RefObservationKey, new_uuid7
from tests.integration.p5.test_pr_assessment import Fixture


def read_ref(fixture, *, target=None):
    if target is not None:
        subprocess.run(
            [
                "git",
                "-C",
                str(fixture.path / "input.git"),
                "update-ref",
                "refs/heads/main",
                target.object_oid,
            ],
            check=True,
        )
    request = GitNativeAcquisitionRequest(
        fixture.repository,
        str(uuid4()),
        str(uuid4()),
        "actual-qualified-role-check",
        1_700_000_500_000_000,
        include_refs=True,
        ref_prefixes=("refs/heads/main",),
        retain_bytes=False,
    )
    report = GitAcquisition(fixture.path, operational=fixture.path).acquire_from_native(
        GitNativeSource(fixture.path / "input.git"), request, new_request=True
    )
    link = report.ref_enumerations[0].links[0]
    actual = (
        link.claim.resolved_target_object_oid or link.claim.direct_target_object_oid
    )
    return {
        "role": "head",
        "expected_oid": list(fixture.head.key),
        "ref_name_hex": link.observation.ref_name_bytes.hex(),
        "actual_oid": list(actual.key) if actual else None,
        "ref_observation_key": list(link.observation.ref_observation_key.key),
    }


def observe(fixture, check, *, observed=500, state="complete"):
    scope = git_role_check_scope(
        {"repository_uuidv4": fixture.repository},
        head=fixture.head,
        base=fixture.base,
        anchor_provenance_json=fixture.anchor,
        role_checks=[check],
    )
    original = make_provenance(
        "actual-native-ref-check", {"ref_observation_key": check["ref_observation_key"]}
    )
    fixture.observation(
        fixture.parent, "git_role_checks", original, scope, observed, state, ()
    )


def test_fresh_contrary_native_ref_prevents_complete_even_when_original_commit_bytes_remain_healthy(
    tmp_path,
):
    fixture = Fixture(tmp_path)
    fixture.code()
    assert fixture.query().state == "complete"
    first = read_ref(fixture)
    observe(fixture, first)
    assert fixture.query().state == "complete"
    changed = read_ref(fixture, target=fixture.base)
    observe(fixture, changed, observed=600, state="partial")
    result = fixture.query()
    assert result.state == "partial"
    assert (
        result.git_metadata["state"] == "complete"
        and result.git_metadata["verified_objects"] >= 3
    )
    assert result.git_metadata["ref_checks"]["reason"] == "native_ref_target_changed"
    assert result.git_metadata["ref_checks"]["actual_oid"] == list(fixture.base.key)
    assert not (tmp_path / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "attack", ["unknown-key", "wrong-ref-name", "wrong-reported-target"]
)
def test_context_marker_does_not_substitute_for_actual_native_ref_subject_and_result(
    tmp_path, attack
):
    fixture = Fixture(tmp_path)
    fixture.code()
    check = read_ref(fixture)
    if attack == "unknown-key":
        check["ref_observation_key"] = list(
            RefObservationKey(str(uuid4()), new_uuid7()).key
        )
    elif attack == "wrong-ref-name":
        check["ref_name_hex"] = b"refs/heads/another".hex()
    else:
        check["actual_oid"] = list(fixture.base.key)
    observe(fixture, check)
    result = fixture.query()
    assert result.state != "complete"
    assert result.git_metadata["state"] == "complete"
    assert result.git_metadata["ref_checks"]["state"] == "unknown"


@pytest.mark.parametrize("equivalent", [True, False])
def test_equal_clock_actual_checks_compare_semantics_without_electing_ref_occurrence_ids(
    tmp_path, equivalent
):
    fixture = Fixture(tmp_path)
    fixture.code()
    observe(fixture, read_ref(fixture))
    observe(
        fixture, read_ref(fixture, target=fixture.head if equivalent else fixture.base)
    )
    result = fixture.query()
    assert result.state == ("complete" if equivalent else "conflict")
    assert result.git_metadata["ref_checks"]["state"] == (
        "complete" if equivalent else "conflict"
    )


def test_role_check_grammar_requires_actual_ref_identity_not_old_declared_role_flags(
    tmp_path,
):
    fixture = Fixture(tmp_path)
    check = read_ref(fixture)
    for change in (
        {"ref_observation_key": [str(uuid4()), str(uuid4())]},
        {"ref_name_hex": "726566732f00"},
        {"expected_oid": ["sha1", "a" * 40 + "\x00"]},
        {"required_roles": ["head"]},
    ):
        with pytest.raises(ValueError):
            git_role_check_scope(
                {},
                head=fixture.head,
                base=fixture.base,
                anchor_provenance_json=fixture.anchor,
                role_checks=[{**check, **change}],
            )
    assert canonical(check)


def test_actual_ref_from_another_explicit_repository_cannot_qualify_reported_role_owner(
    tmp_path,
):
    from contextlib import closing
    from dataclasses import replace

    from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
    from repo_catalog.application.provider_acquisition import ProviderAcquisition
    from tests.support.context_admission import fixture_context, fixture_service

    fixture = Fixture(tmp_path)
    fixture.code()
    check = read_ref(fixture)
    other_repository = str(uuid4())
    with closing(
        GitRepositoryStore(tmp_path / "repository.sqlite3")
    ) as repository_store:
        repository_store.admit_repository(other_repository)
    fixture.grants = replace(
        fixture.grants, repositories=fixture.grants.repositories | {other_repository}
    )
    fixture.auth, _ = fixture_service(fixture.grants)
    fixture.admission = fixture_context(fixture.auth)
    fixture.api = ProviderAcquisition(
        tmp_path,
        repository_store=tmp_path,
        authorization=fixture.auth,
        admission=fixture.admission,
    )
    scope = git_role_check_scope(
        {"repository_uuidv4": other_repository},
        head=fixture.head,
        base=fixture.base,
        anchor_provenance_json=fixture.anchor,
        role_checks=[check],
    )
    fixture.observation(
        fixture.parent,
        "git_role_checks",
        make_provenance(
            "actual-native-ref-check", {"read": "wrong-explicit-repository"}
        ),
        scope,
        500,
        "complete",
        (),
    )
    result = fixture.query()
    assert result.git_metadata["state"] == "complete"
    assert result.state != "complete"
    assert result.git_metadata["ref_checks"]["state"] == "unknown"
    assert result.git_metadata["ref_checks"]["reason"] == "native_ref_subject_mismatch"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
