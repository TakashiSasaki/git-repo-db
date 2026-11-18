"""Actual GraphQL projections distinguish absent nested selections from NULL."""

import json
from uuid import uuid4

import pytest

from repo_catalog.adapters.github.production_intake import normalize_review_comment
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.acquisition import AcquisitionError
from repo_catalog.domain.provider_acquisition import (
    ProviderIntakeBatch,
    ProviderRegistration,
    make_provenance,
)
from tests.integration.p5.conftest import init_catalog_stores
from tests.support.context_admission import (
    AuthorizedProviderAcquisition as ProviderAcquisition,
)

FIELDS = [
    ("pullRequestReview", "fullDatabaseId", "review_id", "11"),
    ("replyTo", "fullDatabaseId", "in_reply_to_id", "62"),
    ("commit", "oid", "target_commit_object_oid", "a" * 40),
    ("originalCommit", "oid", "original_commit_object_oid", "b" * 40),
]
SERVICE = "91d0b077-f084-47c0-872c-4d7aa329f2e4"


def normalized(source, nested, stamp):
    return normalize_review_comment(
        SERVICE,
        "20",
        {
            "fullDatabaseId": "61",
            "body": "first\x00body" if stamp == 1 else "new body",
            "updatedAt": f"2026-10-10T00:00:0{stamp}Z",
            source: nested,
        },
        stamp,
        make_provenance("actual-graphql-normalizer", {"read": str(uuid4())}),
        graphql=True,
    )


def field(unit, name):
    return tuple(
        candidate
        for observation in unit.observations
        for candidate in observation.fields
        if candidate.resource == unit.primary_resource and candidate.field_name == name
    )


@pytest.mark.parametrize("source,key,target,known", FIELDS)
@pytest.mark.parametrize("sparse", [{}, {"unselected": "attribute"}])
def test_actual_nested_sparse_reference_retains_original_until_explicit_parent_null(
    tmp_path, source, key, target, known, sparse
):
    directory = tmp_path / "context"
    init_catalog_stores(directory, stores=("context", "operational"))
    acquisition = ProviderAcquisition(directory)
    acquisition.admit_batch(
        ProviderIntakeBatch(SERVICE, providers=(ProviderRegistration(SERVICE),))
    )
    first = normalized(source, {key: known}, 1)
    acquisition.admit_units((first,))
    with Context.snapshot(directory) as context:
        original = context.candidates(first.primary_resource, target)
        assert len(original) == 1
        assert json.loads(original[0].value_json) == known
        assert original[0].provenance_json == first.provenance_json
    partial = normalized(source, sparse, 2)
    assert field(partial, target) == ()
    acquisition.admit_units((partial,))
    with Context.snapshot(directory) as context:
        assert context.candidates(first.primary_resource, target) == original
        bodies = context.candidates(first.primary_resource, "text_body_sha256")
        assert len(bodies) == 1 and bodies[0].provenance_json == partial.provenance_json
        assert context.read_text(json.loads(bodies[0].value_json)) == "new body"
    cleared = normalized(source, None, 3)
    assert field(cleared, target)[0].value_json == "null"
    acquisition.admit_units((cleared,))
    with Context.snapshot(directory) as context:
        values = context.candidates(first.primary_resource, target)
        assert len(values) == 1 and values[0].value_json == "null"
        assert values[0].provenance_json == cleared.provenance_json
        assert values[0].observed_at_us == 3
        assert context.db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not (directory / "repository.sqlite3").exists()
    assert not (directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("source,key,target,known", FIELDS)
@pytest.mark.parametrize("bad", [False, 0, "", [], "not an object"])
def test_actual_nested_malformed_object_never_emits_an_observed_null(
    source, key, target, known, bad
):
    with pytest.raises(AcquisitionError):
        normalized(source, bad, 1)


@pytest.mark.parametrize("source,key,target,known", FIELDS[:2])
@pytest.mark.parametrize("bad", [None, False, 0, "0", ""])
def test_actual_present_parent_identity_requires_a_positive_native_id(
    source, key, target, known, bad
):
    with pytest.raises(AcquisitionError):
        normalized(source, {key: bad}, 1)


@pytest.mark.parametrize("source,key,target,known", FIELDS[2:])
@pytest.mark.parametrize("bad", ["a" * 39, "a" * 40 + "\x00hidden", {}, 1])
def test_actual_present_nested_oid_requires_an_exact_git_identity(
    source, key, target, known, bad
):
    with pytest.raises(AcquisitionError):
        normalized(source, {key: bad}, 1)


@pytest.mark.parametrize("source,key,target,known", FIELDS[2:])
def test_actual_selected_null_oid_is_an_observation_without_a_repository_reference(
    tmp_path, source, key, target, known
):
    directory = tmp_path / "context"
    init_catalog_stores(directory, stores=("context", "operational"))
    acquisition = ProviderAcquisition(directory)
    acquisition.admit_batch(
        ProviderIntakeBatch(SERVICE, providers=(ProviderRegistration(SERVICE),))
    )
    first, cleared = (
        normalized(source, {key: known}, 1),
        normalized(source, {key: None}, 2),
    )
    assert field(cleared, target)[0].value_json == "null"
    assert not cleared.repository_references
    acquisition.admit_units((first, cleared))
    with Context.snapshot(directory) as context:
        values = context.candidates(first.primary_resource, target)
        assert len(values) == 1 and values[0].value_json == "null"
        assert values[0].provenance_json == cleared.provenance_json
        assert values[0].observed_at_us == 2
    assert not (directory / "repository.sqlite3").exists()
