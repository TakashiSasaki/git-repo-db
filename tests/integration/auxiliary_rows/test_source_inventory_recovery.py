"""Source-owned typed salvage retains membership and historical proof originals."""

import json
import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite.core_recovery import RecoveryWorkBudget, stop_catalog
from repo_catalog.adapters.sqlite.p1_schema import initialize, register_functions
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.recovery import (
    BackupScope,
    CorruptionDetectedError,
    RestoreValidationError,
)
from repo_catalog.domain.shared_values import encode
from tests.integration.auxiliary_rows.test_identity_recovery import rehash_backup
from tests.integration.auxiliary_rows.test_source_inventory_history import prepare


def snapshot(directory):
    with Context.snapshot(directory) as context:
        return {
            table: [
                tuple(row)
                for row in context.db.execute(f"SELECT * FROM {table} ORDER BY 1,2,3")
            ]
            for table in (
                "source_inventory_evidence",
                "source_coverage_proofs",
                "coverage_claims",
                "source_repositories",
            )
        }


def setup_recovery(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    old, claim, authorization, admission, policy = prepare(source)
    # sqlite3.Connection's own context manager commits but does not close.
    # Close the fixture identity reader before capturing suspect DB/WAL bytes;
    # otherwise its later GC close checkpoints the fixture's own pending WAL.
    with closing(sqlite3.connect(source / "context.sqlite3")) as db:
        repository, instance = db.execute(
            "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity"
        ).fetchone()
    initialize(source / "core.sqlite3", "core", repository, instance)
    # Baseline has no Context registrations. Typed units must reconcile their
    # exact Source/Provider/member dependencies under destination authority.
    empty = tmp_path / "empty"
    empty.mkdir()
    for role in ("core", "context"):
        initialize(empty / f"{role}.sqlite3", role, repository, instance)
    adapter = SQLiteRecoveryAdapter()
    backup = tmp_path / "baseline"
    adapter.create_consistent_backup(empty, backup, BackupScope.PAIRED)
    latest = replace(old, observed_at_us=200, state="partial", terminal=False)
    with Context.transaction(
        source, authorization=authorization, admission=admission
    ) as context:
        context.associate_source(
            old.source_registration_uuidv4,
            old.repositories[0],
            encode(
                {
                    "label": "authored membership",
                    "source": "synthetic",
                    "evidence": "original association",
                }
            ),
        )
        context.inventory(old)
        context.prove_inventory(claim, old)
        context.inventory(latest)
    expected = snapshot(source)
    stop_catalog(source, "synthetic Source recovery")
    preserved = {
        path.name: path.read_bytes()
        for path in source.glob("*.sqlite3*")
        if path.is_file()
    }
    salvage = tmp_path / "source.jsonl"
    receipt = adapter.extract_salvage(source, salvage, scope=BackupScope.PAIRED)
    assert not receipt.partial, receipt.unreadable_scope
    assert {
        path.name: path.read_bytes()
        for path in source.glob("*.sqlite3*")
        if path.is_file()
    } == preserved
    candidates = [json.loads(line) for line in salvage.read_text().splitlines()]
    typed = [
        row
        for row in candidates
        if row["candidate_type"] in {"source_inventory", "source_inventory_proof"}
    ]
    assert len(typed) == 3
    # Force historical replay after newer evidence, irrespective of physical PK
    # traversal order; generic Context rows cannot authorize typed success.
    typed.sort(
        key=lambda row: (
            row["payload"]["inventory"]["observed_at_us"],
            row["candidate_type"] == "source_inventory_proof",
        ),
        reverse=True,
    )
    salvage.write_text("".join(encode(row) + "\n" for row in typed))
    return (
        adapter,
        source,
        backup,
        repository,
        salvage,
        expected,
        old,
        claim,
        authorization,
        admission,
        policy,
        preserved,
    )


def test_source_backup_stop_salvage_fresh_restore_merge_activate(tmp_path):
    (
        adapter,
        source,
        backup,
        repository,
        salvage,
        expected,
        old,
        claim,
        authorization,
        admission,
        _,
        preserved,
    ) = setup_recovery(tmp_path)
    restored = tmp_path / "restored"
    adapter.restore_backup(backup, restored, repository)
    receipt = adapter.merge_salvage(
        restored, salvage, authorization=authorization, admission=admission
    )
    assert receipt.input_complete and receipt.rejected_units == 0
    # The proof unit includes its old inventory. Its subsequent standalone
    # inventory candidate is an exact replay, not a third insertion unit.
    assert receipt.admitted_units == 2 and receipt.replayed_units == 1
    assert snapshot(restored) == expected
    with Context.snapshot(restored) as context:
        assert context.coverage(claim.scope).state != "complete"
        assert tuple(context.resources(kind="repository")) == old.provider_repositories
        assert (
            context.source_repositories(old.source_registration_uuidv4)
            == old.repositories
        )
        assert (
            context.db.execute(
                "SELECT count(*) FROM resource_repository_relations"
            ).fetchone()[0]
            == 0
        )
    replay = adapter.merge_salvage(
        restored, salvage, authorization=authorization, admission=admission
    )
    assert replay.admitted_units == 0 and replay.replayed_units == 3
    # Stored validation accepts the original historical proof, independent of
    # the newer partial observation; backup and activation both run that route.
    adapter.create_consistent_backup(
        restored, tmp_path / "roundtrip", BackupScope.PAIRED
    )
    assert adapter.activate(restored, tmp_path / "active.json").source_backup_id
    assert {
        path.name: path.read_bytes()
        for path in source.glob("*.sqlite3*")
        if path.is_file()
    } == preserved


@pytest.mark.parametrize(
    "forgery", ["local-denial", "foreign-service", "changed-proof"]
)
def test_source_recovery_rechecks_originals_and_current_authority(tmp_path, forgery):
    (
        adapter,
        _,
        backup,
        repository,
        salvage,
        _,
        old,
        _,
        authorization,
        admission,
        policy,
        _,
    ) = setup_recovery(tmp_path)
    rows = [json.loads(line) for line in salvage.read_text().splitlines()]
    proof = next(
        row for row in rows if row["candidate_type"] == "source_inventory_proof"
    )
    if forgery == "local-denial":
        policy.denied = DependencySet(sources={old.source_registration_uuidv4})
    elif forgery == "foreign-service":
        proof["payload"]["source_registration"]["service_instance_uuidv4"] = repository
    else:
        proof["payload"]["proof"]["provider_repositories_json"] = "[]"
    proof["extraction_status"] = "complete"
    proof["extraction_provenance"] = {
        "store": "context",
        "table": "source_coverage_proofs",
    }
    salvage.write_text(encode(proof) + "\n")
    restored = tmp_path / "refused"
    adapter.restore_backup(backup, restored, repository)
    receipt = adapter.merge_salvage(
        restored, salvage, authorization=authorization, admission=admission
    )
    assert receipt.input_complete and receipt.rejected_units == 1
    assert receipt.admitted_units == 0
    assert not any(snapshot(restored).values())
    with Context.snapshot(restored) as context:
        assert context.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        assert context.db.execute("SELECT count(*) FROM providers").fetchone()[0] == 0


def corrupt_source_scope(path):
    with sqlite3.connect(path) as db:
        register_functions(db, "context")
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name='source_inventory_evidence'"
        ).fetchall()
        for name, _ in triggers:
            db.execute(f'DROP TRIGGER "{name}"')
        # Exact DDL/CHECKs stay valid; trusted Source service semantics fail.
        scope = encode(
            {
                "coverage_kind": "repositories",
                "service_instance_uuidv4": "00000000-0000-4000-8000-000000000001",
            }
        )
        changed = db.execute(
            "UPDATE source_inventory_evidence SET scope_json=? WHERE observed_at_us=200",
            (scope,),
        )
        assert changed.rowcount == 1, (
            "fault injection must reach an admitted Source row"
        )
        for _, sql in triggers:
            db.execute(sql)


def test_source_backup_and_restore_revalidate_stored_domain_not_only_fingerprint(
    tmp_path,
):
    (
        adapter,
        _,
        backup,
        repository,
        salvage,
        expected,
        _,
        _,
        authorization,
        admission,
        _,
        _,
    ) = setup_recovery(tmp_path)
    restored = tmp_path / "valid"
    adapter.restore_backup(backup, restored, repository)
    merged = adapter.merge_salvage(
        restored, salvage, authorization=authorization, admission=admission
    )
    assert merged.rejected_units == 0
    assert merged.admitted_units == 2 and merged.replayed_units == 1
    assert snapshot(restored) == expected
    valid = tmp_path / "valid-backup"
    adapter.create_consistent_backup(restored, valid, BackupScope.PAIRED)
    corrupt_source_scope(valid / "stores" / "context.sqlite3")
    rehash_backup(valid)
    with pytest.raises(RestoreValidationError):
        adapter.restore_backup(valid, tmp_path / "rejected", repository)
    assert not (tmp_path / "rejected").exists()
    corrupt_source_scope(restored / "context.sqlite3")
    retained = (restored / "context.sqlite3").read_bytes()
    with pytest.raises(CorruptionDetectedError):
        adapter.create_consistent_backup(
            restored, tmp_path / "rejected-backup", BackupScope.PAIRED
        )
    assert (restored / "p1-recovery-stop.json").exists()
    assert (restored / "context.sqlite3").read_bytes() == retained


def test_source_dependency_projection_uses_existing_forensic_primitives_and_denies_writes(
    tmp_path,
):
    from repo_catalog.adapters.sqlite.source_inventory_salvage import _read

    old, _, _, _, _ = prepare(tmp_path)
    service = old.provider_repositories[0].service_instance_uuidv4
    with sqlite3.connect(tmp_path / "context.sqlite3") as db:
        register_functions(db, "context")
        db.execute("PRAGMA query_only=ON")
        called = []
        db.create_function("forbidden_original_body", 0, lambda: called.append(True))

        def authorizer(action, _arg1, arg2, _database, origin):
            if origin is not None:
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION and arg2 not in (
                "typeof",
                "octet_length",
                "like",
            ):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorizer)
        row = _read(
            db,
            "providers",
            {"service_instance_uuidv4": service},
            RecoveryWorkBudget(),
            8192,
        )
        assert row["service_instance_uuidv4"] == service
        assert row["provider_kind"] == "synthetic"
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("SELECT forbidden_original_body()")
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("SELECT substr('untrusted',1,1)")
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("DELETE FROM providers")
        assert not called
