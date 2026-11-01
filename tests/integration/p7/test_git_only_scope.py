"""Recovery scope is durable intent, independent of optional feature discovery."""

import json
from uuid import uuid4

import pytest

from repo_catalog.application.core_recovery import CoreRecoveryService
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import (
    BackupScope,
    RecoveryBudget,
    RecoveryCapabilityError,
    RecoveryError,
    SalvageError,
)


def _extract_state(catalog):
    paths = [
        path
        for path in catalog.glob("p1-recovery-request-extract-*.json")
        if not path.name.endswith((".reserved.json", ".source.json"))
    ]
    assert len(paths) == 1
    return json.loads(paths[0].read_text())


def test_same_source_request_cannot_change_interpreted_scope(
    synthetic_catalog, tmp_path
):
    service = RecoveryService()
    service.stop_suspect_catalog(synthetic_catalog, "synthetic scope binding")
    first = tmp_path / "git-only.jsonl"
    service.extract_salvage(
        synthetic_catalog, first, request_id="scope", scope=BackupScope.GIT_ONLY
    )
    original = _extract_state(synthetic_catalog)
    second = tmp_path / "paired.jsonl"
    with pytest.raises(SalvageError, match="source binding changed"):
        service.extract_salvage(
            synthetic_catalog, second, request_id="scope", scope=BackupScope.PAIRED
        )
    assert not second.exists()
    assert _extract_state(synthetic_catalog) == original
    assert service.is_stopped(synthetic_catalog)


def test_default_request_keeps_cumulative_work_when_output_changes(
    synthetic_catalog, tmp_path
):
    service = RecoveryService()
    budget = RecoveryBudget(max_input_records=1)
    service.stop_suspect_catalog(synthetic_catalog, "synthetic continuation")
    service.extract_salvage(
        synthetic_catalog,
        tmp_path / "first.jsonl",
        budget=budget,
        scope=BackupScope.GIT_ONLY,
    )
    before = _extract_state(synthetic_catalog)["cumulative_usage"]
    other = tmp_path / "another-output-directory"
    other.mkdir()
    service.extract_salvage(
        synthetic_catalog,
        other / "second.jsonl",
        budget=budget,
        scope=BackupScope.GIT_ONLY,
    )
    after = _extract_state(synthetic_catalog)["cumulative_usage"]
    assert all(after[unit] >= amount for unit, amount in before.items())
    assert after["input_scan_bytes"] > before["input_scan_bytes"]


def test_merge_request_cannot_switch_verified_baseline(
    synthetic_catalog, tmp_path, repo_uuid
):
    service = RecoveryService()
    backup, destination = tmp_path / "backup", tmp_path / "fresh"
    service.create_consistent_backup(synthetic_catalog, backup)
    service.restore_backup(backup, destination, repo_uuid)
    salvage = tmp_path / "empty.jsonl"
    salvage.write_text("")
    service.merge_salvage(destination, salvage, request_id="baseline")
    receipt_path = destination / "p1-restored-baseline.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["backup_id"] = str(uuid4())
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(RecoveryError, match="target scope or baseline changed"):
        service.merge_salvage(destination, salvage, request_id="baseline")
    assert not service.is_stopped(destination)


def test_core_refuses_implicit_paired_scope_without_marking_corruption(
    synthetic_catalog, tmp_path
):
    service = CoreRecoveryService()
    output = tmp_path / "unavailable.jsonl"
    with pytest.raises(RecoveryCapabilityError):
        service.extract_salvage(synthetic_catalog, output)
    assert not output.exists()
    assert not service.is_stopped(synthetic_catalog)


def test_git_only_candidates_can_merge_into_validated_paired_target(
    synthetic_catalog, tmp_path, repo_uuid
):
    service = RecoveryService()
    backup, destination = tmp_path / "backup", tmp_path / "paired-fresh"
    service.create_consistent_backup(synthetic_catalog, backup)
    service.restore_backup(backup, destination, repo_uuid)
    repository = str(uuid4())
    candidate = {
        "candidate_id": "git-only-repository",
        "candidate_type": "git_metadata",
        "extraction_provenance": {"table": "repositories", "scope": "git_only"},
        "payload": {"repository_uuidv4": repository},
        "extraction_status": "clean",
    }
    salvage = tmp_path / "git-only.jsonl"
    salvage.write_text(json.dumps(candidate) + "\n")
    merged = service.merge_salvage(destination, salvage)
    assert merged.admitted_units == 1 and merged.rejected_units == 0
    assert (destination / "context.sqlite3").exists()
    activated = service.activate_catalog(destination, tmp_path / "paired-active")
    assert activated.reconstructed_stores == ["operational", "search"]
    assert activated.clean_operational is True


@pytest.mark.parametrize("scope", ["invalid", 1, {"scope": "git_only"}])
def test_malformed_declared_scope_does_not_diagnose_corruption(
    restored_catalog, tmp_path, scope
):
    service = RecoveryService()
    candidate = {
        "candidate_type": "git_metadata",
        "extraction_provenance": {"scope": scope},
        "payload": {},
        "extraction_status": "clean",
    }
    salvage = tmp_path / "invalid-scope.jsonl"
    salvage.write_text(json.dumps(candidate) + "\n")
    with pytest.raises(RecoveryError, match="Unsupported declared salvage scope"):
        service.merge_salvage(restored_catalog, salvage)
    assert not service.is_stopped(restored_catalog)


@pytest.mark.parametrize("binding", ["source", "target"])
def test_request_binding_rejects_boolean_version_alias(
    restored_catalog, tmp_path, binding
):
    service = RecoveryService()
    if binding == "source":
        service.stop_suspect_catalog(restored_catalog, "synthetic typed binding")
        service.extract_salvage(
            restored_catalog, tmp_path / "first.jsonl", scope=BackupScope.GIT_ONLY
        )
        path = next(restored_catalog.glob("p1-recovery-request-extract-*.source.json"))
    else:
        salvage = tmp_path / "empty.jsonl"
        salvage.write_text("")
        service.merge_salvage(restored_catalog, salvage)
        path = restored_catalog / "p1-recovery-request-default.target.json"
    value = json.loads(path.read_text())
    value["version"] = True
    path.write_text(json.dumps(value))
    with pytest.raises(
        RecoveryError, match="binding changed|scope or baseline changed"
    ):
        if binding == "source":
            service.extract_salvage(
                restored_catalog, tmp_path / "second.jsonl", scope=BackupScope.GIT_ONLY
            )
        else:
            service.merge_salvage(restored_catalog, salvage)
    assert not (tmp_path / "second.jsonl").exists()
    if binding == "target":
        assert not service.is_stopped(restored_catalog)
