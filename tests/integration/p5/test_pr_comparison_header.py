"""A verified owner permits sparse comparison headers without synthetic identity."""

import pytest

from repo_catalog.adapters.github.production_intake import (
    normalize_pr_comparison_header,
)
from repo_catalog.domain.acquisition import AcquisitionError
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.provider_acquisition import make_provenance

PARENT = ResourceKey.from_native(
    "91d0b077-f084-47c0-872c-4d7aa329f2e4", "pull_request", "20"
)


@pytest.mark.parametrize(
    "payload", [{}, {"mergeCommit": {}}, {"mergeCommit": {"unselected": True}}]
)
def test_sparse_comparison_header_keeps_unknown_clock_and_emits_no_candidate(payload):
    unit = normalize_pr_comparison_header(
        PARENT, payload, 100, make_provenance("comparison-header", "actual-response")
    )
    assert unit.primary_resource == PARENT and unit.clock.at_us is None
    assert not unit.observations[0].fields and not unit.core_references
    assert not unit.relations and not unit.text_admissions


def test_actual_comparison_header_preserves_null_and_exact_references():
    unit = normalize_pr_comparison_header(
        PARENT,
        {"headRefOid": "a" * 40, "baseRefOid": None, "mergeCommit": {"oid": "b" * 40}},
        100,
        make_provenance("comparison-header", "actual-response"),
    )
    assert {
        field.field_name: field.value_json for field in unit.observations[0].fields
    } == {
        "head_object_oid": '"' + "a" * 40 + '"',
        "base_object_oid": "null",
        "merge_object_oid": '"' + "b" * 40 + '"',
    }
    assert [
        (ref.role, ref.object_oid.object_oid) for ref, _, _ in unit.core_references
    ] == [("head", "a" * 40), ("merge", "b" * 40)]
    assert all(
        clock.at_us is None and observed == 100
        for _, clock, observed in unit.core_references
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"mergeCommit": False},
        {"mergeCommit": {"oid": False}},
        {"headRefOid": "bad"},
        {"baseRefOid": False},
    ],
)
def test_malformed_comparison_header_refuses_without_candidate(payload):
    with pytest.raises(AcquisitionError):
        normalize_pr_comparison_header(
            PARENT,
            payload,
            100,
            make_provenance("comparison-header", "actual-response"),
        )
