"""Typed CLI input cannot select implementation code or lose composite keys."""

import json

import pytest

from repo_catalog.cli.separated_io import decode, invocation, read_document
from repo_catalog.domain.p1_core import OID


def test_composite_dto_map_keys_roundtrip_without_stringification():
    value = decode(
        {
            "$map": [
                [
                    {
                        "$type": "OID",
                        "fields": {"object_format": "sha1", "object_oid": "a" * 40},
                    },
                    "copy",
                ]
            ]
        }
    )
    assert value == {OID("sha1", "a" * 40): "copy"}
    with pytest.raises(ValueError, match="duplicate typed map key"):
        decode({"$map": [["key", 1], ["key", 2]]})


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"args": {}},
        {"kwargs": []},
        {"method": "__getattribute__"},
        {"$type": "GitCore", "fields": {}},
    ],
)
def test_malformed_invocation_and_non_dto_constructor_are_rejected(tmp_path, value):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        invocation(path)


def test_duplicate_json_keys_and_deep_documents_fail_before_opening_catalog(tmp_path):
    path = tmp_path / "input.json"
    path.write_text('{"args":[],"args":[]}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        read_document(path)
    path.write_text("[" * 60 + "0" + "]" * 60)
    with pytest.raises(ValueError, match="INPUT_LIMIT"):
        read_document(path)


def test_forward_referenced_exchange_selection_uses_public_dto_namespace():
    from repo_catalog.domain.exchange import ExchangeSelectionScope

    value = decode(
        {
            "$type": "ExchangeSelectionScope",
            "fields": {"all_selected": True, "include_context": False},
        }
    )
    assert type(value) is ExchangeSelectionScope
    assert value.all_selected and not value.include_context


def test_admission_budget_serializes_only_public_limits_and_measured_usage():
    from repo_catalog.cli.separated_io import encode
    from repo_catalog.domain.context_admission import (
        AdmissionBudget,
        AdmissionContext,
        AdmissionSelection,
    )

    budget = AdmissionBudget(work_limit=100, bytes_limit=100, dependency_limit=100)
    budget.charge(work=2, bytes_=3, dependencies=1)
    output = encode(budget)
    assert output == {
        "work_limit": 100,
        "bytes_limit": 100,
        "dependency_limit": 100,
        "depth_limit": 12,
        "used_work": 2,
        "used_bytes": 3,
        "used_dependencies": 1,
    }
    assert "_lock" not in json.dumps(output)
    with pytest.raises(ValueError, match="runtime admission authority"):
        encode(
            AdmissionContext(
                "local-principal",
                "provider_intake",
                AdmissionSelection(all_selected=True),
                budget,
            )
        )
    with pytest.raises(ValueError, match="public DTO constructor"):
        decode({"$type": "AdmissionBudget", "fields": {"_usage": [0, 0, 0]}})


def test_omitted_optional_context_annotations_do_not_block_core_selection(monkeypatch):
    import repo_catalog.cli.separated_io as codec

    registry = dict(codec._dto_registry())
    registry.pop("ResourceKey", None)
    monkeypatch.setattr(codec, "_dto_registry", lambda: registry)
    codec._hints.cache_clear()
    try:
        value = decode(
            {
                "$type": "ExchangeSelectionScope",
                "fields": {
                    "all_selected": True,
                    "include_context": False,
                    "object_oids": [
                        {
                            "$type": "OID",
                            "fields": {"object_format": "sha1", "object_oid": "a" * 40},
                        }
                    ],
                },
            }
        )
        assert value.object_oids == (OID("sha1", "a" * 40),)
    finally:
        codec._hints.cache_clear()
