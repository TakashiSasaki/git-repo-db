"""P5 integration tests for coordinated paired Core-first Context-second admission,
dependency reconciliation, operational retry resilience, and stop propagation.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import GitAcquisition
from repo_catalog.domain.acquisition import (
    GitNativeAcquisitionRequest,
    ProviderIntakeBatch,
    ProviderPullRequestIntake,
    ProviderRegistration,
    RepositoryRegistration,
    make_provenance,
)
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_coordination import (
    AdmissionFailure,
    CoordinationError,
    PairAdmission,
    RequestIdentity,
)
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores
from tests.support.context_admission import (
    AuthorizedPairedAcquisitionCoordinator as PairedAcquisitionCoordinator,
)
from tests.support.context_admission import (
    AuthorizedProviderAcquisition as ProviderAcquisition,
)


def test_core_first_context_second_and_failure_retry_convergence(
    tmp_path: Path,
) -> None:
    """Verify that Core commits first, and if Context fails, Core facts persist,
    and a subsequent retry converges cleanly to PairAdmission(True, True).
    """
    repo_dir = tmp_path / "repo"
    oids = build_sample_git_repo(repo_dir, "sha1")
    cat_dir = tmp_path / "paired_cat"
    repo_uuid, _ = init_catalog_stores(
        cat_dir, stores=("core", "context", "operational")
    )
    service_uuid = str(uuid4())
    prov_json = make_provenance("paired-test", "step-1")

    git_source = GitNativeSource(repo_dir)
    git_req = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="paired-test-git",
        observed_at_us=1_700_000_100_000_000,
        select_object_oids=(oids["commit1"], oids["commit2"], oids["tree"]),
        retain_bytes=True,
    )

    pr_payload = {
        "id": 101,
        "number": 1,
        "title": "PR linking commit2",
        "state": "open",
        "body": "PR description",
        "head": {"sha": oids["commit2"].object_oid, "ref": "feat/1"},
        "base": {"sha": oids["commit1"].object_oid, "ref": "main"},
    }
    provider_batch = ProviderIntakeBatch(
        service_instance_uuidv4=service_uuid,
        providers=(ProviderRegistration(service_uuid, "github"),),
        repositories=(RepositoryRegistration(repo_uuid),),
        pull_requests=(
            ProviderPullRequestIntake(
                pr_payload,
                1_700_000_150_000_000,
                prov_json,
            ),
        ),
    )

    coord = PairedAcquisitionCoordinator(cat_dir)

    # 1. First run with cut="during_context" to simulate mid-admission failure after Core commit
    def cut_hook(point: str) -> None:
        if point == "during_context":
            raise RuntimeError("simulated_context_failure")

    with pytest.raises(AdmissionFailure) as exc_info:
        coord.admit_paired(
            new_request=True,
            git_source=git_source,
            git_request=git_req,
            provider_batch=provider_batch,
            cut=cut_hook,
        )
    assert exc_info.value.outcome == PairAdmission(True, False)
    assert isinstance(exc_info.value.cause, RuntimeError)

    # Verify Core committed its facts despite Context failure!
    core = GitCore(cat_dir / "core.sqlite3")
    try:
        assert (
            len(
                core.sql(
                    "SELECT 1 FROM git_objects WHERE object_oid=?",
                    (oids["commit1"].object_oid,),
                )
            )
            == 1
        )
        assert (
            len(
                core.sql(
                    "SELECT 1 FROM git_objects WHERE object_oid=?",
                    (oids["commit2"].object_oid,),
                )
            )
            == 1
        )
    finally:
        core.close()

    # Verify Context did not commit the PR
    with Context.snapshot(cat_dir) as ctx:
        pr_key = ResourceKey.from_native(service_uuid, "pull_request", "101")
        assert len(ctx.candidates(pr_key, "title")) == 0

    # 2. Retry the admission without cut -> converges cleanly!
    res = coord.admit_paired(
        new_request=True,
        git_source=git_source,
        git_request=git_req,
        provider_batch=provider_batch,
    )
    assert res.admission == PairAdmission(True, True)
    assert res.git_report is not None
    assert res.provider_report is not None

    # Verify both Core and Context now have facts, and CoreReference is linked
    with (
        Context.snapshot(cat_dir) as ctx,
        closing(GitCore(cat_dir / "core.sqlite3")) as core,
    ):
        assert len(ctx.candidates(pr_key, "title")) == 1
        core_deps = ctx.core_dependencies(
            pr_key,
            validate=lambda fmt, oid: bool(
                core.sql(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                    (fmt, oid),
                )
            ),
        )
        assert len([dep for dep in core_deps if dep.required]) == 2
        assert len([dep for dep in core_deps if not dep.required]) == 2
        # Both commit1 and commit2 are now present in Core, so required=True
        assert all(dep.available for dep in core_deps)


def test_late_core_dependency_reconciliation(tmp_path: Path) -> None:
    """Verify Context-first intake with unavailable Git Core OID produces required=False,
    and subsequent Core acquisition + reconcile_core_dependencies promotes to required=True.
    """
    repo_dir = tmp_path / "repo"
    oids = build_sample_git_repo(repo_dir, "sha1")
    cat_dir = tmp_path / "paired_cat"
    repo_uuid, _ = init_catalog_stores(
        cat_dir, stores=("core", "context", "operational")
    )
    service_uuid = str(uuid4())
    prov_json = make_provenance("late-core-test", "step-1")

    # 1. Admit Context PR pointing to commit2, when commit2 is NOT yet in Core
    pr_payload = {
        "id": 202,
        "number": 2,
        "title": "PR with pending core commit",
        "state": "open",
        "head": {"sha": oids["commit2"].object_oid, "ref": "feat/2"},
        "base": {"sha": oids["commit1"].object_oid, "ref": "main"},
    }
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=service_uuid,
        providers=(ProviderRegistration(service_uuid, "github"),),
        repositories=(RepositoryRegistration(repo_uuid),),
        pull_requests=(
            ProviderPullRequestIntake(
                pr_payload,
                1_700_000_100_000_000,
                prov_json,
            ),
        ),
    )

    prov_acq = ProviderAcquisition(
        cat_dir, core=cat_dir / "core.sqlite3", operational=cat_dir
    )
    report = prov_acq.admit_batch(batch)
    assert len(report.pending_core_references) == 2
    assert len(report.linked_core_references) == 0

    with Context.snapshot(cat_dir) as ctx:
        pr_key = ResourceKey.from_native(service_uuid, "pull_request", "202")
        core_deps = ctx.core_dependencies(pr_key)
        assert len(core_deps) == 2
        assert all(not dep.required for dep in core_deps)

    # 2. Acquire Git objects into Core
    git_source = GitNativeSource(repo_dir)
    git_acq = GitAcquisition(cat_dir / "core.sqlite3", operational=cat_dir)
    git_req = GitNativeAcquisitionRequest(
        repository_uuidv4=repo_uuid,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        source_attribution="late-core-test-git",
        observed_at_us=1_700_000_200_000_000,
        select_object_oids=(oids["commit1"], oids["commit2"], oids["tree"]),
        retain_bytes=True,
    )
    git_acq.acquire_from_native(git_source, git_req, new_request=True)

    # 3. Run PairedAcquisitionCoordinator.reconcile_core_dependencies
    coord = PairedAcquisitionCoordinator(cat_dir)
    reconciled = coord.reconcile_core_dependencies()
    assert len(reconciled.promoted_references) >= 2

    # Verify that Context core_dependencies were promoted to required=True!
    with Context.snapshot(cat_dir) as ctx:
        promoted_deps = ctx.core_dependencies(pr_key)
        required_deps = [d for d in promoted_deps if d.required]
        assert len(required_deps) == 2
        assert {d.reference.role for d in required_deps} == {"head", "base"}


def test_operational_retry_ledger_and_recreation_resilience(tmp_path: Path) -> None:
    """Verify operational retry state tracking, backoff recording, and that deletion
    of operational.sqlite3 allows graceful recreation without affecting Core or Context.
    """
    cat_dir = tmp_path / "paired_cat"
    repo_uuid, _ = init_catalog_stores(
        cat_dir, stores=("core", "context", "operational")
    )

    ledger = OperationalAcquisitionLedger(cat_dir / "operational.sqlite3")
    scope_key = {"task": "fetch_commits", "repo": repo_uuid}

    # Record retry state
    ledger.record_retry_state(
        scope_key,
        attempt_count=1,
        next_retry_at_us=1_700_000_900_000_000,
        reason="rate_limit",
        state={"note": "exponential backoff"},
    )
    retry_info = ledger.get_retry_state(scope_key)
    assert retry_info is not None
    assert retry_info["attempt_count"] == 1
    assert retry_info["reason"] == "rate_limit"

    # Save a continuation under an ensured request
    req = RequestIdentity(str(uuid4()), str(uuid4()))
    ledger.ensure_request(req, scope=scope_key, new_request=True)
    ledger.save_continuation(req, scope_key, {"last_oid": "deadbeef", "page": 5})
    loaded_cont = ledger.load_continuation(req, scope_key)
    assert loaded_cont is not None
    assert loaded_cont["page"] == 5

    # Simulate operational.sqlite3 loss/deletion
    op_path = cat_dir / "operational.sqlite3"
    op_path.unlink()
    assert not op_path.exists()

    # Re-initialize operational.sqlite3
    from repo_catalog.adapters.sqlite.p1_schema import initialize

    initialize(op_path, "operational", repo_uuid, str(uuid4()))

    # New ledger connects cleanly
    new_ledger = OperationalAcquisitionLedger(op_path)
    # Old continuation triggers CONTINUATION_UNAVAILABLE
    with pytest.raises(CoordinationError) as exc_info:
        new_ledger.load_continuation(req, scope_key)
    assert exc_info.value.code == "CONTINUATION_UNAVAILABLE"

    # The old identity cannot silently become new work after loss.
    with pytest.raises(CoordinationError):
        new_ledger.ensure_request(req, scope=scope_key)
    fresh = RequestIdentity(str(uuid4()), str(uuid4()))
    new_ledger.ensure_request(fresh, scope=scope_key, new_request=True)
    new_ledger.save_continuation(fresh, scope_key, {"page": 1})
    assert new_ledger.load_continuation(fresh, scope_key)["page"] == 1


def test_immediate_stop_propagation(tmp_path: Path) -> None:
    """Verify that p1-recovery-stop.json halts paired acquisition immediately."""
    cat_dir = tmp_path / "stopped_cat"
    init_catalog_stores(cat_dir, stores=("core", "context", "operational"))

    # Write catalog stop
    persist_catalog_stop(cat_dir, "Recovery required by test harness")

    coord = PairedAcquisitionCoordinator(cat_dir)
    with pytest.raises(CoordinationError) as exc_info:
        coord.admit_paired()
    assert exc_info.value.code == "RECOVERY_REQUIRED"


def test_paired_preparation_carries_claim_specific_notes_to_core(tmp_path):
    from repo_catalog.domain.acquisition import NotesAcquisitionSpec

    repo_dir = tmp_path / "repo-ref-i2"
    oids = build_sample_git_repo(repo_dir, "sha1")
    catalog = tmp_path / "paired-ref-i2"
    repository, _ = init_catalog_stores(
        catalog, stores=("core", "context", "operational")
    )
    request = GitNativeAcquisitionRequest(
        repository,
        str(uuid4()),
        str(uuid4()),
        "paired-ref-i2",
        1_700_000_100_000_000,
        notes=NotesAcquisitionSpec(
            discover_notes=True,
            acquire_inventories=True,
            target_object_oids=(oids["commit2"],),
            retain_note_bodies=True,
        ),
    )
    outcome = PairedAcquisitionCoordinator(catalog).admit_paired(
        new_request=True, git_source=GitNativeSource(repo_dir), git_request=request
    )
    assert outcome.git_report.ref_note_acquisitions
    assert all(
        result.body_retained for result in outcome.git_report.ref_note_acquisitions
    )
    core = GitCore(catalog / "core.sqlite3")
    try:
        assert core.sql("SELECT 1 FROM ref_retained_notes")
        assert core.sql("SELECT 1 FROM notes_mapping_groups")
    finally:
        core.close()
