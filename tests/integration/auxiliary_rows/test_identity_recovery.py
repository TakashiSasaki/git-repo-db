"""Actual typed identity recovery lifecycle and hostile stored/candidate cases."""

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_schema import (
    initialize,
    register_functions,
)
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.adapters.sqlite.repository_recovery import (
    RecoveryWorkBudget,
    RepositoryRecoveryAdapter,
    stop_catalog,
)
from repo_catalog.application.identity_assertions import IdentityAssertions
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.identity_assertions import identity_record
from repo_catalog.domain.recovery import (
    ActivationError,
    BackupScope,
    CorruptionDetectedError,
    RecoveryBudget,
    RecoveryCapabilityError,
    RestoreValidationError,
)
from repo_catalog.domain.shared_values import Provenance, encode
from tests.integration.auxiliary_rows.test_identity_assertions import (
    assertion,
    cancellation,
    original,
)


def context_authority(endpoints, records):
    return create_local_admission_service(
        operation="salvage_merge",
        grants=DependencySet(
            provider_registrations=endpoints,
            identity_assertions={record["relation_uuidv4"] for record in records},
        ),
        selection=AdmissionSelection(all_selected=True),
    )[:2]


def status(directory, paired):
    with closing(
        GitRepositoryStore(directory / "repository.sqlite3")
    ) as repository_store:
        if paired:
            with Context.snapshot(directory) as context:
                return IdentityAssertions(repository_store, context).status()
        return IdentityAssertions(repository_store).status()


def prepare(tmp_path, paired):
    source = tmp_path / "source"
    source.mkdir()
    repository, instance = str(uuid4()), str(uuid4())
    for role in ("repository", "context") if paired else ("repository",):
        initialize(source / f"{role}.sqlite3", role, repository, instance)
    endpoints = [str(uuid4()) for _ in range(3)]
    with closing(GitRepositoryStore(source / "repository.sqlite3")) as repository_store:
        for endpoint in endpoints:
            repository_store.admit_repository(endpoint)
    records = {}
    for kind in ("repository", "service") if paired else ("repository",):
        a, b, c = endpoints
        first, second, cancelled = (
            assertion(kind, a, b),
            assertion(kind, b, c),
            assertion(kind, a, c),
        )
        unresolved = assertion(kind, a, str(uuid4()))
        records[kind] = (first, second, cancelled, cancellation(cancelled), unresolved)
    service_records = records.get("service", ())
    service_endpoints = set(endpoints)
    if paired:
        service_endpoints.add(service_records[-1]["right_service_instance_uuidv4"])
        authorization, admission = context_authority(service_endpoints, service_records)
        with Context.transaction(
            source, authorization=authorization, admission=admission
        ) as context:
            for endpoint in endpoints:
                context.provider(endpoint, "identity-recovery-test")
    else:
        authorization = admission = None
    adapter = SQLiteRecoveryAdapter() if paired else RepositoryRecoveryAdapter()
    backup = tmp_path / "baseline"
    scope = BackupScope.PAIRED if paired else BackupScope.GIT_ONLY
    adapter.create_consistent_backup(source, backup, scope)
    with closing(GitRepositoryStore(source / "repository.sqlite3")) as repository_store:
        service = IdentityAssertions(repository_store)
        first, second, cancelled, before, unresolved = records["repository"]
        service.admit(
            "cancellation", before, original(before), entity_kind="repository"
        )
        for record in (first, second, cancelled, unresolved):
            service.admit("relation", record, original(record))
    if paired:
        with Context.transaction(
            source, authorization=authorization, admission=admission
        ) as context:
            service = IdentityAssertions(context=context)
            first, second, cancelled, before, unresolved = service_records
            service.admit(
                "cancellation", before, original(before), entity_kind="service"
            )
            for record in (first, second, cancelled, unresolved):
                service.admit("relation", record, original(record))
    expected = status(source, paired)
    stop_catalog(source, "synthetic identity recovery")
    preserved = {
        path.name: path.read_bytes()
        for path in source.glob("*.sqlite3*")
        if path.is_file()
    }
    salvage = tmp_path / "identity.jsonl"
    receipt = adapter.extract_salvage(source, salvage, scope=scope)
    assert not receipt.partial, receipt.unreadable_scope
    assert {
        path.name: path.read_bytes()
        for path in source.glob("*.sqlite3*")
        if path.is_file()
    } == preserved
    return (
        adapter,
        source,
        backup,
        repository,
        salvage,
        expected,
        authorization,
        admission,
        records,
        preserved,
    )


@pytest.mark.parametrize("paired", [False, True], ids=["repository_only", "paired"])
def test_backup_stop_salvage_fresh_restore_merge_activate_preserves_identity(
    tmp_path, paired
):
    (
        adapter,
        source,
        backup,
        repository,
        salvage,
        expected,
        authorization,
        admission,
        records,
        preserved,
    ) = prepare(tmp_path, paired)
    candidates = [json.loads(line) for line in salvage.read_text().splitlines()]
    identity = [
        row
        for row in candidates
        if "identity_assertion" in row["candidate_type"]
        or "identity_cancellation" in row["candidate_type"]
    ]
    assert len(identity) == (10 if paired else 5)
    assert {row["candidate_type"] for row in identity} == {
        "repository_identity_assertion",
        "repository_identity_cancellation",
        *(
            {"service_identity_assertion", "service_identity_cancellation"}
            if paired
            else ()
        ),
    }
    restored = tmp_path / "restored"
    assert adapter.restore_backup(backup, restored, repository).revalidated_clean
    merged = adapter.merge_salvage(
        restored, salvage, authorization=authorization, admission=admission
    )
    assert merged.input_complete and merged.rejected_units == 0
    assert merged.admitted_units >= len(identity)
    assert status(restored, paired) == expected
    # Fixed Exchange projections expose only these complete typed metadata rows.
    work = RecoveryWorkBudget()
    with closing(
        GitRepositoryStore(restored / "repository.sqlite3")
    ) as repository_store:
        for table, count in (
            ("repository_identity_assertions", 4),
            ("repository_identity_cancellations", 1),
        ):
            rows = [
                tuple(row)
                for row in repository_store.exchange_metadata_rows(table, (), work)
            ]
            assert len(rows) == count and rows == sorted(rows)
    if paired:
        with Context.snapshot(restored) as context:
            for table, count in (
                ("service_identity_assertions", 4),
                ("service_identity_cancellations", 1),
            ):
                rows = [
                    tuple(row) for row in context._exchange_metadata_rows(table, work)
                ]
                assert len(rows) == count and rows == sorted(rows)
    assert work.usage["input_bytes"] > 0
    replay = adapter.merge_salvage(
        restored, salvage, authorization=authorization, admission=admission
    )
    assert replay.admitted_units == 0 and replay.replayed_units >= len(identity)
    activated = adapter.activate(restored, tmp_path / "active.json")
    assert activated.source_backup_id
    assert status(restored, paired) == expected
    assert {
        path.name: path.read_bytes()
        for path in source.glob("*.sqlite3*")
        if path.is_file()
    } == preserved
    assert (restored / "context.sqlite3").exists() is paired
    if not paired:
        assert not (restored / "operational.sqlite3").exists()
        assert not (restored / "search.sqlite3").exists()


@pytest.mark.parametrize("paired", [False, True], ids=["repository_only", "paired"])
def test_typed_identity_conflicts_and_forged_candidate_flags_do_not_choose_winners(
    tmp_path, paired
):
    adapter, _, backup, repository, salvage, _, authorization, admission, records, _ = (
        prepare(tmp_path, paired)
    )
    rows = [json.loads(line) for line in salvage.read_text().splitlines()]
    kind = "service" if paired else "repository"
    candidate = next(
        row for row in rows if row["candidate_type"] == f"{kind}_identity_assertion"
    )
    payload = candidate["payload"]
    record = json.loads(payload["record_json"])
    # Same original occurrence, competing asserted payload: preserve both reports.
    other = {**record, "evidence_json": '{"kind":"competing-original-report"}'}
    conflict = {
        **candidate,
        "payload": {**payload, "record_json": identity_record("relation", other)},
    }
    invalid = {
        **candidate,
        "verified": True,
        "sender_authenticated": True,
        "payload": {**payload, "relation_uuidv4": str(uuid4())},
    }
    false_provenance = Provenance(
        "alleged-sender", "original", "identity", "json", "1", "receiver_intrinsic"
    )
    intrinsic = {
        **candidate,
        "payload": {**payload, "provenance": false_provenance.encoded},
    }
    rows.extend((conflict, invalid, intrinsic))
    hostile = tmp_path / "hostile.jsonl"
    hostile.write_text("".join(encode(row) + "\n" for row in rows))
    restored = tmp_path / "restored"
    adapter.restore_backup(backup, restored, repository)
    result = adapter.merge_salvage(
        restored, hostile, authorization=authorization, admission=admission
    )
    assert result.rejected_units == 2
    projected = status(restored, paired)
    assert projected["identity_conflicts"]
    assert not any(
        row["relation_uuidv4"] == record["relation_uuidv4"]
        for row in projected["active_identity_relations"]
        if row["entity_kind"] == kind
    )
    assert not (restored / "p1-recovery-stop.json").exists()
    replay = adapter.merge_salvage(
        restored, hostile, authorization=authorization, admission=admission
    )
    assert replay.admitted_units == 0 and replay.rejected_units == 2
    assert replay.replayed_units > 0


def test_service_identity_recovery_refuses_missing_local_grant_and_repository_only_scope(
    tmp_path,
):
    adapter, _, backup, repository, salvage, _, _, _, _, _ = prepare(tmp_path, True)
    restored = tmp_path / "restored"
    adapter.restore_backup(backup, restored, repository)
    denied = adapter.merge_salvage(restored, salvage)
    assert denied.rejected_units == 5
    assert not status(restored, True)["service_equivalence_closure"]
    repository_only = tmp_path / "repository-only"
    repository_only.mkdir()
    initialize(
        repository_only / "repository.sqlite3", "repository", repository, str(uuid4())
    )
    repository_adapter = RepositoryRecoveryAdapter()
    repository_backup = tmp_path / "repository-backup"
    repository_adapter.create_consistent_backup(
        repository_only, repository_backup, BackupScope.GIT_ONLY
    )
    target = tmp_path / "repository-restored"
    repository_adapter.restore_backup(repository_backup, target, repository)
    with pytest.raises(RecoveryCapabilityError):
        repository_adapter.merge_salvage(target, salvage)
    assert not (target / "context.sqlite3").exists()


def corrupt_identity(path, role, table):
    db = sqlite3.connect(path)
    register_functions(db, role)
    try:
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",
            (table,),
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        db.execute("PRAGMA ignore_check_constraints=ON")
        (record,) = db.execute(f"SELECT record_json FROM {table} LIMIT 1").fetchone()
        invalid = {**json.loads(record), "asserted_at_us": 0}
        db.execute(
            f"UPDATE {table} SET record_json=? WHERE record_json=?",
            (encode(invalid), record),
        )
        db.execute("PRAGMA ignore_check_constraints=OFF")
        for _, sql in triggers:
            db.execute(sql)
        db.commit()
    finally:
        db.close()


def rehash_backup(backup):
    manifest = json.loads((backup / "manifest.json").read_text())
    for role, metadata in manifest["stores"].items():
        data = (backup / "stores" / f"{role}.sqlite3").read_bytes()
        metadata["bytes"], metadata["sha256"] = (
            len(data),
            hashlib.sha256(data).hexdigest(),
        )
    manifest["overall_sha256"] = hashlib.sha256(
        "".join(
            manifest["stores"][role]["sha256"] for role in sorted(manifest["stores"])
        ).encode("ascii")
    ).hexdigest()
    raw = encode(manifest).encode()
    (backup / "manifest.json").write_bytes(raw)
    (backup / "manifest.json.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "  manifest.json\n"
    )


@pytest.mark.parametrize(
    "role,table",
    [
        ("repository", "repository_identity_assertions"),
        ("repository", "repository_identity_cancellations"),
        ("context", "service_identity_assertions"),
        ("context", "service_identity_cancellations"),
    ],
)
def test_backup_and_restore_revalidate_current_identity_payload_not_just_schema(
    tmp_path, role, table
):
    paired = role == "context"
    (
        adapter,
        source,
        baseline,
        repository,
        salvage,
        _,
        authorization,
        admission,
        _,
        _,
    ) = prepare(tmp_path, paired)
    restored = tmp_path / "valid"
    adapter.restore_backup(baseline, restored, repository)
    adapter.merge_salvage(
        restored, salvage, authorization=authorization, admission=admission
    )
    valid_backup = tmp_path / "valid-backup"
    scope = BackupScope.PAIRED if paired else BackupScope.GIT_ONLY
    adapter.create_consistent_backup(restored, valid_backup, scope)
    corrupt_identity(valid_backup / "stores" / f"{role}.sqlite3", role, table)
    rehash_backup(valid_backup)
    with pytest.raises(RestoreValidationError):
        adapter.restore_backup(valid_backup, tmp_path / "refused-restore", repository)
    assert not (tmp_path / "refused-restore").exists()
    corrupt_identity(restored / f"{role}.sqlite3", role, table)
    evidence = (restored / f"{role}.sqlite3").read_bytes()
    with pytest.raises(CorruptionDetectedError):
        adapter.create_consistent_backup(restored, tmp_path / "refused-backup", scope)
    assert (restored / "p1-recovery-stop.json").exists()
    assert (restored / f"{role}.sqlite3").read_bytes() == evidence
    assert not (tmp_path / "refused-backup").exists()


def test_identity_validation_limit_is_indeterminate_and_preserves_sound_authority(
    tmp_path,
):
    adapter, _, backup, repository, salvage, _, _, _, _, _ = prepare(tmp_path, False)
    restored = tmp_path / "restored"
    adapter.restore_backup(backup, restored, repository)
    adapter.merge_salvage(restored, salvage)
    from repo_catalog.adapters.sqlite.repository_recovery_validation import (
        RefValidationBudgetError,
    )

    # Five current identity rows are sound but exceed this deliberate one-row
    # validation allowance. Backup reports its finite limit without diagnosis.
    assert len(status(restored, False)["identity_relations"]) == 4
    bounded = RepositoryRecoveryAdapter(
        validation_budget=replace(RecoveryBudget(), max_input_records=1)
    )
    with pytest.raises(
        RefValidationBudgetError, match="Finite stored identity record limit"
    ):
        bounded.create_consistent_backup(
            restored, tmp_path / "limited", BackupScope.GIT_ONLY
        )
    assert not (restored / "p1-recovery-stop.json").exists()
    assert status(restored, False)["identity_relations"]


@pytest.mark.parametrize(
    "role,table",
    [
        ("repository", "repository_identity_assertions"),
        ("context", "service_identity_cancellations"),
    ],
)
def test_activation_revalidates_stored_identity_and_never_publishes_corrupt_target(
    tmp_path, role, table
):
    paired = role == "context"
    adapter, _, baseline, repository, salvage, _, authorization, admission, _, _ = (
        prepare(tmp_path, paired)
    )
    restored = tmp_path / "activation-target"
    adapter.restore_backup(baseline, restored, repository)
    adapter.merge_salvage(
        restored, salvage, authorization=authorization, admission=admission
    )
    corrupt_identity(restored / f"{role}.sqlite3", role, table)
    locator = tmp_path / "active.json"
    with pytest.raises(ActivationError):
        adapter.activate(restored, locator)
    assert not locator.exists()
    assert (restored / "p1-recovery-stop.json").exists()
