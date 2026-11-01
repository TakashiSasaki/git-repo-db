"""Every salvage family requires the same restored-target preflight."""

import base64
import json
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import initialize, register_functions
from repo_catalog.application.core_recovery import CoreRecoveryService
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import BackupScope, RecoveryBudget, RecoveryError
from repo_catalog.domain.ref_observation import (
    RefObservation,
    RefObservationKey,
    new_uuid7,
)
from tests.integration.p7.conftest import (
    make_commit,
    make_tag,
    make_tree,
    merge_preflight_input_bytes,
)


def _authority(directory):
    result = {}
    for role in ("core", "context"):
        database = directory / (role + ".sqlite3")
        if database.exists():
            with closing(sqlite3.connect(database)) as db:
                register_functions(db, role)
                tables = db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
                ).fetchall()
                result[role] = {
                    name: db.execute(f'SELECT * FROM "{name}"').fetchall()
                    for (name,) in tables
                }
    return result


@pytest.fixture(params=[BackupScope.GIT_ONLY, BackupScope.PAIRED])
def restored_target(tmp_path, request):
    scope = request.param
    service = (
        CoreRecoveryService() if scope == BackupScope.GIT_ONLY else RecoveryService()
    )
    source = tmp_path / "source"
    source.mkdir()
    repository, instance = str(uuid4()), str(uuid4())
    for role in ("core", "context") if scope == BackupScope.PAIRED else ("core",):
        initialize(source / (role + ".sqlite3"), role, repository, instance)
    backup, target = tmp_path / "backup", tmp_path / "target"
    service.create_consistent_backup(source, backup, scope)
    service.restore_backup(backup, target, repository)
    # Source evidence and its persistent stop must survive failed target merges.
    service.stop_suspect_catalog(source, "synthetic preflight source")
    preserved = {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}
    yield service, target, repository
    assert {
        p.name: p.read_bytes() for p in source.iterdir() if p.is_file()
    } == preserved
    assert service.is_stopped(source)


def _stream(tmp_path, family, repository):
    def candidate(kind, payload, table=None):
        return {
            "candidate_type": kind,
            "extraction_status": "clean",
            "extraction_provenance": {"scope": "git_only", "table": table},
            "payload": payload,
        }

    if family == "repository" or family == "mixed":
        rows = [
            candidate(
                "git_metadata", {"repository_uuidv4": str(uuid4())}, "repositories"
            )
        ]
    elif family == "object":
        rows = [
            candidate(
                "git_metadata",
                {"object_format": "sha1", "object_oid": "a" * 40},
                "git_objects",
            )
        ]
    else:
        tree = make_tree("sha1", [])
        commit = make_commit("sha1", tree.object_oid.object_oid, [])
        native = {
            "tree": tree,
            "commit": commit,
            "tag": make_tag("sha1", commit.object_oid.object_oid),
        }[family]
        rows = [
            candidate(
                "retained_body",
                {
                    "object_format": "sha1",
                    "object_oid": native.object_oid.object_oid,
                    "native_type": native.native_type,
                    "size": len(native.body),
                    "digest_sha256": native.digest_sha256,
                    "physical_copy_uuidv4": str(uuid4()),
                    "body_base64": base64.b64encode(native.body).decode(),
                },
            )
        ]
    if family == "mixed":
        # A real extracted Ref unit follows a generic candidate that used to commit first.
        source = tmp_path / "ref-source"
        source.mkdir()
        initialize(source / "core.sqlite3", "core", repository, str(uuid4()))
        with closing(GitCore(source / "core.sqlite3")) as core:
            core.admit_repository(repository)
            core.admit_ref_observation(
                RefObservation(
                    RefObservationKey(str(uuid4()), new_uuid7()),
                    repository,
                    b"refs/heads/main",
                    "fixture",
                    "visible",
                )
            )
        extracted = tmp_path / "refs.jsonl"
        CoreRecoveryService().extract_salvage(
            source, extracted, scope=BackupScope.GIT_ONLY
        )
        rows.append(
            next(
                json.loads(line)
                for line in extracted.read_text().splitlines()
                if json.loads(line)["candidate_type"] == "ref_subject"
            )
        )
    path = tmp_path / "candidates.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path, len(rows)


@pytest.mark.parametrize(
    "family", ["repository", "object", "commit", "tree", "tag", "mixed"]
)
@pytest.mark.parametrize(
    "fault", ["missing", "repository_uuidv4", "catalog_instance_uuidv4", "scope"]
)
def test_invalid_baseline_rejects_before_any_authority_write(
    restored_target, tmp_path, family, fault
):
    service, target, repository = restored_target
    stream, _ = _stream(tmp_path, family, repository)
    marker = target / "p1-restored-baseline.json"
    if fault == "missing":
        marker.unlink()
    else:
        value = json.loads(marker.read_text())
        value[fault] = (
            ("paired" if value["scope"] == "git_only" else "git_only")
            if fault == "scope"
            else str(uuid4())
        )
        marker.write_text(json.dumps(value))
    before = _authority(target)
    with pytest.raises(RecoveryError):
        service.merge_salvage(target, stream)
    assert _authority(target) == before
    assert not service.is_stopped(target)


@pytest.mark.parametrize(
    "family", ["repository", "object", "commit", "tree", "tag", "mixed"]
)
def test_valid_baseline_admits_and_replays_each_family(
    restored_target, tmp_path, family
):
    service, target, repository = restored_target
    stream, count = _stream(tmp_path, family, repository)
    first = service.merge_salvage(target, stream)
    assert first.admitted_units == count and first.rejected_units == 0
    before = _authority(target)
    second = service.merge_salvage(target, stream)
    assert second.replayed_units == count and second.rejected_units == 0
    assert _authority(target) == before
    assert not service.is_stopped(target)


@pytest.mark.parametrize("raw", ["{", "{}", '{"version":true}'])
def test_malformed_baseline_is_input_refusal(restored_target, tmp_path, raw):
    service, target, repository = restored_target
    stream, _ = _stream(tmp_path, "repository", repository)
    (target / "p1-restored-baseline.json").write_text(raw)
    before = _authority(target)
    with pytest.raises(RecoveryError, match="validated fresh backup"):
        service.merge_salvage(target, stream)
    assert _authority(target) == before
    assert not service.is_stopped(target)


@pytest.mark.parametrize("unit,limit", [("input_bytes", 1), ("metadata_units", 1)])
def test_preflight_budget_stop_is_durable_and_precedes_input(
    restored_target, tmp_path, unit, limit
):
    service, target, repository = restored_target
    stream, _ = _stream(tmp_path, "repository", repository)
    before = _authority(target)
    budget = RecoveryBudget(max_work_units={unit: limit})
    first = service.merge_salvage(target, stream, budget, "preflight-limit")
    path = target / "p1-recovery-request-preflight-limit.json"
    state = json.loads(path.read_text())
    assert state["budget_exhausted"]
    assert state["cumulative_usage"]["input_scan_bytes"] == 0
    assert state["cumulative_usage"]["input_records"] == 0
    if unit == "metadata_units":
        assert state["cumulative_usage"]["input_bytes"] == (
            merge_preflight_input_bytes(target) - 72
        )
    second = service.merge_salvage(target, stream, budget, "preflight-limit")
    assert json.loads(path.read_text())["cumulative_usage"] == state["cumulative_usage"]
    for receipt in (first, second):
        assert receipt.candidates_processed == receipt.admitted_units == 0
        assert receipt.unprocessed_units == 1 and not receipt.input_complete
        assert not receipt.unprocessed_count_exact
    assert _authority(target) == before
    assert not service.is_stopped(target)
