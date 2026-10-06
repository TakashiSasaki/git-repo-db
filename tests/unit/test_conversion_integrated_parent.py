"""Integrated admission keeps complete P3B evidence independently verifiable."""

import subprocess
import sys
import tarfile
from contextlib import contextmanager

import pytest

from scripts.conversion import (
    batch,
    engine,
    identity_phase,
    integrated_parent,
    source,
    target,
)
from scripts.conversion.common import ROOT, ConversionError, canonical, digest, now
from scripts.schema_contract import tagged_key
from tests.unit.test_conversion_identity import workspace

TABLES = ("git_objects",)


@pytest.fixture
def parent(tmp_path):
    _, destination = workspace(tmp_path)
    identity_phase.convert(destination, batch_size=1)
    _, spec, signatures = identity_phase.resources()
    sealed = source.verify_seal(destination, allow_legacy=True)
    return destination, sealed, spec, signatures


def check(parent):
    destination, sealed, spec, signatures = parent
    with (
        source.readonly(destination / "source.sqlite3") as src,
        source.readonly(destination / "target.sqlite3") as db,
    ):
        return integrated_parent.check_parent(db, src, sealed, spec, signatures, TABLES)


def initialize(parent):
    destination, _, _, signatures = parent
    run, _, _, proof = check(parent)
    stamp = now()
    receipt = {
        "protocol": integrated_parent.PROTOCOL_VERSION,
        "committed_at": stamp,
        "source_id": run["source_id"],
        "parent": proof,
        "signatures": signatures,
        "batch_size": 2,
        "encoding": "UTF-8",
        "recipes": ["git_objects"],
        "write_ownership": {
            "tables": list(TABLES),
            "operations": ["insert", "reuse", "update_listing_progress"],
        },
        "activation_permitted": False,
    }
    receipt["transition_id"] = "p3:" + digest(canonical(receipt).encode())
    db = target.connect(destination / "target.sqlite3")
    try:
        db.execute(
            "INSERT INTO conversion_runs VALUES(?,?,?,?,?,'paused',?)",
            (
                receipt["transition_id"],
                run["source_id"],
                stamp,
                stamp,
                integrated_parent.PROTOCOL_VERSION,
                canonical(receipt),
            ),
        )
    finally:
        db.close()
    return receipt


def owned_batch(db, receipt, mapping_ids):
    stamp = now()
    output = {"mapping_ids": mapping_ids, "observed_at": stamp}
    manifest = {
        "protocol": integrated_parent.PROTOCOL_VERSION,
        "recipe": "git_objects",
        "index": 0,
        "output": output,
        "output_sha256": batch.proof_digest(output),
    }
    db.execute(
        "INSERT INTO conversion_batches VALUES(?,?,?,?,?,?)",
        (
            batch.next_id(db, "conversion_batches"),
            receipt["transition_id"],
            "git_objects",
            b"\0" * 32,
            stamp,
            canonical(manifest),
        ),
    )


def test_complete_parent_proof_stays_identical_after_own_receipt(parent):
    before = check(parent)
    initialize(parent)
    after = check(parent)
    assert before[2]["complete"] and after[2]["complete"]
    assert before[3] == after[3]
    destination, sealed, spec, signatures = parent
    with source.readonly(destination / "target.sqlite3") as db:
        pending = integrated_parent.pending(db, sealed, spec, signatures, TABLES)
    assert pending["parent_run_id"] == before[0]["id"]


def test_tentative_identity_cursor_selects_resume_without_payload_reads(
    parent, monkeypatch
):
    run, _, _, _ = check(parent)
    statements = []
    readonly = target.readonly_destination

    @contextmanager
    def observed_destination(path):
        with readonly(path) as db:
            db.set_trace_callback(statements.append)
            yield db

    monkeypatch.setattr(target, "readonly_destination", observed_destination)
    assert engine._tentative_identity_complete(parent[0], run["id"], 1)
    assert not engine._tentative_identity_complete(parent[0], "absent-run", 1)
    assert not engine._tentative_identity_complete(parent[0], run["id"], 2)
    assert statements and all("manifest" not in sql for sql in statements)


def test_incomplete_identity_is_not_an_integrated_predecessor(tmp_path):
    _, destination = workspace(tmp_path)
    _, spec, signatures = identity_phase.resources()
    incomplete = (
        destination,
        source.verify_seal(destination, allow_legacy=True),
        spec,
        signatures,
    )
    with pytest.raises(ConversionError, match="IDENTITY_CONVERSION_INCOMPLETE"):
        check(incomplete)


@pytest.mark.parametrize("owned", [False, True])
def test_only_explicit_owned_map_ids_are_filtered(parent, owned):
    receipt = initialize(parent)
    destination = parent[0]
    db = target.connect(destination / "target.sqlite3")
    try:
        record = db.execute("SELECT id FROM legacy_records LIMIT 1").fetchone()[0]
        mapping_id = batch.next_id(db, "id_mappings")
        db.execute(
            "INSERT INTO id_mappings VALUES(?,?,?,?,'identity','synthetic integrated')",
            (
                mapping_id,
                record,
                "git_objects",
                tagged_key([("text", b"synthetic")]),
            ),
        )
        if owned:
            owned_batch(db, receipt, [mapping_id])
    finally:
        db.close()
    if owned:
        assert check(parent)[3] == receipt["parent"]
    else:
        with pytest.raises(ConversionError, match="IDENTITY_UNLEDGERED_MAPPING"):
            check(parent)


def test_owned_batch_cannot_hide_a_parent_mapping(parent):
    receipt = initialize(parent)
    db = target.connect(parent[0] / "target.sqlite3")
    try:
        parent_id = db.execute("SELECT id FROM id_mappings LIMIT 1").fetchone()[0]
        owned_batch(db, receipt, [parent_id])
    finally:
        db.close()
    with pytest.raises(ConversionError, match="INTEGRATED_MAPPING_OWNERSHIP_MISMATCH"):
        check(parent)


def test_tampered_authenticated_parent_still_fails(parent):
    initialize(parent)
    db = target.connect(parent[0] / "target.sqlite3")
    try:
        db.execute("UPDATE repositories SET name='altered' WHERE id='repo-a'")
    finally:
        db.close()
    with pytest.raises(ConversionError, match="IDENTITY_SOURCE_MISMATCH"):
        check(parent)


def test_unrecognized_owner_fails_before_recovery(parent):
    db = target.connect(parent[0] / "target.sqlite3")
    try:
        parent_run = db.execute("SELECT * FROM conversion_runs LIMIT 1").fetchone()
        db.execute(
            "INSERT INTO conversion_runs VALUES('unknown',?,?,NULL,'unknown/1','paused','{}')",
            (parent_run["source_id"], now()),
        )
    finally:
        db.close()
    destination, sealed, spec, signatures = parent
    with source.readonly(destination / "target.sqlite3") as db:
        with pytest.raises(ConversionError, match="PHASE_OWNERSHIP_MISMATCH"):
            integrated_parent.pending(db, sealed, spec, signatures, TABLES)


def test_pending_does_not_read_spilled_domain_or_archive_pages(parent):
    receipt = initialize(parent)
    db = target.connect(parent[0] / "target.sqlite3")
    try:
        # Recovery admission must ignore possibly inconsistent spilled batch
        # pages; the post-recovery full checker must reject this bad envelope.
        db.execute(
            "INSERT INTO conversion_batches VALUES(?,?,?,?,?,'{}')",
            (
                batch.next_id(db, "conversion_batches"),
                receipt["transition_id"],
                "git_objects",
                b"\0" * 32,
                now(),
            ),
        )
    finally:
        db.close()
    destination, sealed, spec, signatures = parent
    statements = []
    with source.readonly(destination / "target.sqlite3") as db:
        db.set_trace_callback(statements.append)
        integrated_parent.pending(db, sealed, spec, signatures, TABLES)
    for table in (
        "conversion_batches",
        "id_mappings",
        "validation_results",
        "legacy_records",
        "legacy_values",
        *TABLES,
    ):
        assert all(table not in sql for sql in statements)
    with pytest.raises(ConversionError, match="INTEGRATED_BATCH_PROOF_MISMATCH"):
        check(parent)


def test_streaming_proof_covers_archive_bytes_even_without_deep_audit(parent):
    receipt = initialize(parent)
    db = target.connect(parent[0] / "target.sqlite3")
    try:
        # Simulate a damaged destination independently of its enforcement;
        # restore the exact schema so the proof comparison tests stored bytes.
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='legacy_values_immutable'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER legacy_values_immutable")
        db.execute(
            "UPDATE legacy_values SET value_bytes=X'616C7465726564' "
            "WHERE record_id=(SELECT id FROM legacy_records "
            "WHERE source_table='repositories' LIMIT 1) AND column_name='metadata'"
        )
        db.execute(trigger)
        run = db.execute(
            "SELECT * FROM conversion_runs WHERE id=?", (receipt["transition_id"],)
        ).fetchone()
        view = integrated_parent.ParentView(db, run, frozenset(TABLES))
        assert integrated_parent._proof(view) != receipt["parent"]["proof_sha256"]
    finally:
        db.close()


@pytest.mark.parametrize("mutate", [None, "converter_sha256", "contract_sha256"])
def test_only_exact_reviewed_p3b_pair_is_accepted(parent, mutate):
    signatures = parent[3]
    reviewed = {key: signatures[key] for key in integrated_parent.SIGNATURE_KEYS}
    reviewed.update(
        ddl_sha256=integrated_parent.REVIEWED_P3B_DDL,
        contract_sha256=integrated_parent.REVIEWED_P3B_CONTRACT,
        converter_sha256=integrated_parent.REVIEWED_P3B_CONVERTER,
        invariant_contract_sha256=integrated_parent.REVIEWED_P3B_INVARIANTS,
    )
    if mutate:
        reviewed[mutate] = "0" * 64
    run = {"manifest": canonical({"signatures": reviewed})}
    if mutate:
        with pytest.raises(ConversionError, match="UNSUPPORTED_P3B_PREDECESSOR"):
            integrated_parent._parent_signatures(run, signatures)
    else:
        assert integrated_parent._parent_signatures(run, signatures) == reviewed


def test_full_reviewed_parent_verifies_without_rewriting_receipts(tmp_path):
    exported = tmp_path / "reviewed-code"
    exported.mkdir()
    archive = tmp_path / "reviewed-code.tar"
    with archive.open("wb") as output:
        subprocess.run(
            ["git", "archive", "--format=tar", integrated_parent.REVIEWED_P3B_REVISION],
            cwd=ROOT,
            stdout=output,
            check=True,
        )
    with tarfile.open(archive) as snapshot:
        snapshot.extractall(exported, filter="data")
    inputs = tmp_path / "reviewed-inputs"
    inputs.mkdir()
    # Execute the unmodified reviewed converter in its exported tree. No
    # converter, contract, run, receipt or output signature is relabeled.
    script = """
from pathlib import Path
import sys
from scripts.conversion import identity_phase
from tests.unit.test_conversion_identity import workspace
_, _, signatures = identity_phase.resources()
assert signatures['converter_sha256'] == sys.argv[2]
assert signatures['contract_sha256'] == sys.argv[3]
_, destination = workspace(Path(sys.argv[1]))
assert identity_phase.convert(destination, batch_size=1)['complete']
"""
    subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(inputs),
            integrated_parent.REVIEWED_P3B_CONVERTER,
            integrated_parent.REVIEWED_P3B_CONTRACT,
        ],
        cwd=exported,
        check=True,
        capture_output=True,
        text=True,
    )
    destination = inputs / "conversion"
    _, spec, signatures = identity_phase.resources()
    reviewed_parent = (
        destination,
        source.verify_seal(destination, allow_legacy=True),
        spec,
        signatures,
    )
    assert check(reviewed_parent)[3]["reviewed_predecessor_revision"] == (
        integrated_parent.REVIEWED_P3B_REVISION
    )
