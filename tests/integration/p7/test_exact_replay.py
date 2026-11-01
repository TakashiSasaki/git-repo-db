"""Salvage replay must preserve complete immutable evidence, not only hashes."""

import base64
import json
import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.application.recovery import RecoveryService


def _row(catalog, table):
    with sqlite3.connect(catalog / "core.sqlite3") as conn:
        conn.row_factory = sqlite3.Row
        return dict(conn.execute(f"SELECT * FROM {table} LIMIT 1").fetchone())


def _candidate(catalog, table):
    payload = _row(catalog, table)
    if "body" in payload:
        payload["body_base64"] = base64.b64encode(payload.pop("body")).decode()
    return {
        "candidate_type": {
            "retained_metadata": "retained_body",
        }.get(table, "git_metadata"),
        "extraction_status": "clean",
        "extraction_provenance": {"table": table},
        "payload": payload,
    }


def _merge(catalog, tmp_path, candidate):
    source = tmp_path / "candidate.jsonl"
    source.write_text(json.dumps(candidate) + "\n")
    return RecoveryService().merge_salvage(catalog, source, request_id=str(uuid4()))


def _authority(catalog):
    with sqlite3.connect(catalog / "core.sqlite3") as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        ).fetchall()
        return {
            name: conn.execute(f'SELECT * FROM "{name}" ').fetchall()
            for (name,) in tables
        }


@pytest.mark.parametrize(
    "table",
    ["retained_metadata", "git_objects", "repositories"],
)
def test_exact_evidence_replays(restored_catalog, tmp_path, table):
    before = _authority(restored_catalog)
    receipt = _merge(restored_catalog, tmp_path, _candidate(restored_catalog, table))
    assert receipt.replayed_units == 1
    assert receipt.admitted_units == receipt.rejected_units == 0
    assert _authority(restored_catalog) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("native_type", "blob"),
        ("size", 999),
        ("body_base64", base64.b64encode(b"changed retained bytes").decode()),
        ("physical_copy_uuidv4", "invalid-copy"),
    ],
)
def test_metadata_digest_match_does_not_bypass_native_identity(
    restored_catalog, tmp_path, field, value
):
    candidate = _candidate(restored_catalog, "retained_metadata")
    candidate["payload"][field] = value
    before = _authority(restored_catalog)
    receipt = _merge(restored_catalog, tmp_path, candidate)
    assert receipt.rejected_units == 1
    assert receipt.replayed_units == receipt.admitted_units == 0
    assert _authority(restored_catalog) == before


@pytest.mark.parametrize("table", ["retained_metadata"])
def test_new_physical_copy_is_admission_not_replay(restored_catalog, tmp_path, table):
    candidate = _candidate(restored_catalog, table)
    candidate["payload"]["physical_copy_uuidv4"] = str(uuid4())
    receipt = _merge(restored_catalog, tmp_path, candidate)
    assert receipt.admitted_units == 1
    assert receipt.replayed_units == receipt.rejected_units == 0


@pytest.mark.parametrize("table", ["retained_metadata"])
def test_missing_physical_identity_is_only_observation(
    restored_catalog, tmp_path, table
):
    candidate = _candidate(restored_catalog, table)
    del candidate["payload"]["physical_copy_uuidv4"]
    before = _authority(restored_catalog)
    receipt = _merge(restored_catalog, tmp_path, candidate)
    assert receipt.observation_units == 1
    assert (
        receipt.replayed_units == receipt.admitted_units == receipt.rejected_units == 0
    )
    assert _authority(restored_catalog) == before


def test_empty_metadata_body_is_admissible(restored_catalog, tmp_path):
    import hashlib

    from repo_catalog.domain.p1_core import native_object_oid

    candidate = _candidate(restored_catalog, "retained_metadata")
    candidate["payload"].update(
        native_type="tree",
        object_oid=native_object_oid("sha1", "tree", b""),
        body_base64="",
        size=0,
        digest_sha256=hashlib.sha256(b"").hexdigest(),
        physical_copy_uuidv4=str(uuid4()),
    )
    receipt = _merge(restored_catalog, tmp_path, candidate)
    assert receipt.admitted_units == 1
    assert receipt.rejected_units == 0


def test_empty_context_text_admission_and_replay(restored_catalog, tmp_path):
    import hashlib

    candidate = {
        "candidate_type": "context_document",
        "extraction_status": "clean",
        "payload": {"text_value": "", "sha256": hashlib.sha256(b"").hexdigest()},
    }
    first = _merge(restored_catalog, tmp_path, candidate)
    retry = _merge(restored_catalog, tmp_path, candidate)
    assert first.admitted_units == 1
    assert retry.replayed_units == 1
    assert first.rejected_units == retry.rejected_units == 0


def test_context_resources_are_explicit_observations_not_false_replays(
    restored_catalog, tmp_path
):
    candidate = {
        "candidate_type": "context_resource",
        "extraction_status": "clean",
        "extraction_provenance": {"store": "context", "table": "core_references"},
        "payload": {
            "repository_uuidv4": str(uuid4()),
            "object_format": "sha1",
            "object_oid": "f" * 40,
        },
    }
    before = _authority(restored_catalog)
    receipt = _merge(restored_catalog, tmp_path, candidate)
    assert receipt.observation_units == 1
    assert (
        receipt.admitted_units == receipt.replayed_units == receipt.rejected_units == 0
    )
    assert _authority(restored_catalog) == before
