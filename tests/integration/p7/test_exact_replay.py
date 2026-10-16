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
    if table == "retained_notes":
        capture = _row(catalog, "captures")
        payload.update(
            {key: capture[key] for key in ("repository_uuidv4", "source", "ref")}
        )
        payload["native_type"] = "blob"
    return {
        "candidate_type": {
            "retained_metadata": "retained_body",
            "retained_notes": "notes_mapping",
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
    ["retained_metadata", "retained_notes", "captures", "git_objects", "repositories"],
)
def test_exact_evidence_replays(synthetic_catalog, tmp_path, table):
    before = _authority(synthetic_catalog)
    receipt = _merge(synthetic_catalog, tmp_path, _candidate(synthetic_catalog, table))
    assert receipt.replayed_units == 1
    assert receipt.admitted_units == receipt.rejected_units == 0
    assert _authority(synthetic_catalog) == before


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
    synthetic_catalog, tmp_path, field, value
):
    candidate = _candidate(synthetic_catalog, "retained_metadata")
    candidate["payload"][field] = value
    before = _authority(synthetic_catalog)
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.rejected_units == 1
    assert receipt.replayed_units == receipt.admitted_units == 0
    assert _authority(synthetic_catalog) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("repository_uuidv4", "99999999-9999-4999-8999-999999999999"),
        ("capture_origin_uuidv4", "99999999-9999-4999-8999-999999999999"),
        ("capture_uuidv4", "99999999-9999-4999-8999-999999999999"),
        ("source", "another-original-source"),
        ("ref", "refs/notes/another"),
        ("root", "a" * 40),
        ("target", "b" * 40),
        ("path", "b" * 40),
        ("proof_bundle", "[]"),
        ("native_type", "tree"),
        ("size", 999),
        ("body_base64", base64.b64encode(b"changed retained bytes").decode()),
        ("digest_sha256", "0" * 64),
    ],
)
def test_note_replay_requires_all_capture_role_and_byte_evidence(
    synthetic_catalog, tmp_path, field, value
):
    candidate = _candidate(synthetic_catalog, "retained_notes")
    candidate["payload"][field] = value
    before = _authority(synthetic_catalog)
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.rejected_units == 1
    assert receipt.replayed_units == receipt.admitted_units == 0
    assert _authority(synthetic_catalog) == before


def test_capture_replay_cannot_rebind_repository(synthetic_catalog, tmp_path):
    candidate = _candidate(synthetic_catalog, "captures")
    candidate["payload"]["repository_uuidv4"] = str(uuid4())
    before = _authority(synthetic_catalog)
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.rejected_units == 1
    assert receipt.replayed_units == receipt.admitted_units == 0
    assert _authority(synthetic_catalog) == before


@pytest.mark.parametrize("table", ["retained_metadata", "retained_notes"])
def test_new_physical_copy_is_admission_not_replay(synthetic_catalog, tmp_path, table):
    candidate = _candidate(synthetic_catalog, table)
    candidate["payload"]["physical_copy_uuidv4"] = str(uuid4())
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.admitted_units == 1
    assert receipt.replayed_units == receipt.rejected_units == 0


@pytest.mark.parametrize("table", ["retained_metadata", "retained_notes"])
def test_missing_physical_identity_is_only_observation(
    synthetic_catalog, tmp_path, table
):
    candidate = _candidate(synthetic_catalog, table)
    del candidate["payload"]["physical_copy_uuidv4"]
    before = _authority(synthetic_catalog)
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.observation_units == 1
    assert (
        receipt.replayed_units == receipt.admitted_units == receipt.rejected_units == 0
    )
    assert _authority(synthetic_catalog) == before


def test_invalid_new_note_does_not_leave_capture_or_objects(
    synthetic_catalog, tmp_path
):
    candidate = _candidate(synthetic_catalog, "retained_notes")
    candidate["payload"].update(
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        physical_copy_uuidv4=str(uuid4()),
        target="b" * 40,
    )
    before = _authority(synthetic_catalog)
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.rejected_units == 1
    assert _authority(synthetic_catalog) == before


def test_disagreeing_capture_coordinates_rejected(synthetic_catalog, tmp_path):
    candidate = _candidate(synthetic_catalog, "retained_notes")
    candidate["capture_origin_uuidv4"] = str(uuid4())
    before = _authority(synthetic_catalog)
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.rejected_units == 1
    assert _authority(synthetic_catalog) == before


def test_original_repository_is_not_replaced_by_destination_identity(
    synthetic_catalog, tmp_path
):
    from repo_catalog.adapters.sqlite.git_core import GitCore

    candidate = _candidate(synthetic_catalog, "retained_notes")
    original_repository = str(uuid4())
    GitCore(synthetic_catalog / "core.sqlite3").admit_repository(original_repository)
    candidate["payload"].update(
        repository_uuidv4=original_repository,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        physical_copy_uuidv4=str(uuid4()),
    )
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.admitted_units == 1
    assert receipt.rejected_units == receipt.replayed_units == 0
    with sqlite3.connect(synthetic_catalog / "core.sqlite3") as conn:
        actual = conn.execute(
            "SELECT repository_uuidv4 FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
            (
                candidate["payload"]["capture_origin_uuidv4"],
                candidate["payload"]["capture_uuidv4"],
            ),
        ).fetchone()
    assert actual == (original_repository,)


def test_empty_metadata_body_is_admissible(synthetic_catalog, tmp_path):
    import hashlib

    from repo_catalog.domain.p1_core import native_oid

    candidate = _candidate(synthetic_catalog, "retained_metadata")
    candidate["payload"].update(
        native_type="tree",
        full_oid=native_oid("sha1", "tree", b""),
        body_base64="",
        size=0,
        digest_sha256=hashlib.sha256(b"").hexdigest(),
        physical_copy_uuidv4=str(uuid4()),
    )
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.admitted_units == 1
    assert receipt.rejected_units == 0


def test_empty_context_text_admission_and_replay(synthetic_catalog, tmp_path):
    import hashlib

    candidate = {
        "candidate_type": "context_document",
        "extraction_status": "clean",
        "payload": {"text_value": "", "sha256": hashlib.sha256(b"").hexdigest()},
    }
    first = _merge(synthetic_catalog, tmp_path, candidate)
    retry = _merge(synthetic_catalog, tmp_path, candidate)
    assert first.admitted_units == 1
    assert retry.replayed_units == 1
    assert first.rejected_units == retry.rejected_units == 0


def test_context_resources_are_explicit_observations_not_false_replays(
    synthetic_catalog, tmp_path
):
    candidate = {
        "candidate_type": "context_resource",
        "extraction_status": "clean",
        "extraction_provenance": {"store": "context", "table": "core_references"},
        "payload": {
            "repository_uuidv4": str(uuid4()),
            "object_format": "sha1",
            "full_oid": "f" * 40,
        },
    }
    before = _authority(synthetic_catalog)
    receipt = _merge(synthetic_catalog, tmp_path, candidate)
    assert receipt.observation_units == 1
    assert (
        receipt.admitted_units == receipt.replayed_units == receipt.rejected_units == 0
    )
    assert _authority(synthetic_catalog) == before


def test_notes_extraction_preserves_original_repository_binding(
    synthetic_catalog, tmp_path
):
    service = RecoveryService()
    service.stop_suspect_catalog(synthetic_catalog, "synthetic extraction")
    output = tmp_path / "salvage.jsonl"
    service.extract_salvage(synthetic_catalog, output)
    notes = [
        json.loads(line)
        for line in output.read_text().splitlines()
        if json.loads(line)["candidate_type"] == "notes_mapping"
    ]
    assert notes
    assert (
        notes[0]["payload"]["repository_uuidv4"]
        == _row(synthetic_catalog, "captures")["repository_uuidv4"]
    )
