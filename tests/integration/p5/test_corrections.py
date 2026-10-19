"""Owner-decision regressions on synthetic catalogs; no public runtime activation."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.github.production_intake import (
    normalize_issue,
    normalize_repository_fields,
)
from repo_catalog.adapters.sqlite.acquisition import (
    OperationalAcquisitionLedger,
    UnlimitedWorkBudget,
)
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import (
    GitAcquisition,
    PairedAcquisitionCoordinator,
    ProviderAcquisition,
)
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.acquisition import (
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
    ProviderIntakeBatch,
    ProviderRegistration,
    RepositoryRegistration,
)
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangePackage,
    decode_package,
    empty_core_section,
    encode_package,
)
from repo_catalog.domain.p1_coordination import (
    AdmissionFailure,
    CoordinationError,
    PairAdmission,
    RequestIdentity,
)
from repo_catalog.domain.p1_core import CoreCoverageScope, CoreFailure
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


def package(repo=None):
    return ExchangePackage(
        str(uuid4()),
        None,
        str(uuid4()),
        repo or str(uuid4()),
        core=empty_core_section(),
    )


def resign(data):
    content = {k: v for k, v in data.items() if k != "digest_sha256"}
    data["digest_sha256"] = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return data


def request(repo, oid, *, notes=None):
    return GitNativeAcquisitionRequest(
        repo,
        str(uuid4()),
        str(uuid4()),
        "synthetic",
        10,
        select_oids=(oid,),
        include_refs=False,
        notes=notes,
    )


def test_declared_digest_detects_tamper_and_is_not_authentication():
    original = package()
    data = json.loads(encode_package(original))
    assert len(data["digest_sha256"]) == 64
    data["exported_at_us"] = 12
    with pytest.raises(ExchangeError, match="DIGEST_MISMATCH"):
        decode_package(data)
    # An attacker can rewrite data and checksum: independent domain checks remain.
    assert decode_package(resign(data)).exported_at_us == 12
    del data["digest_sha256"]
    with pytest.raises(ExchangeError, match="MALFORMED_ENVELOPE"):
        decode_package(data)


@pytest.mark.parametrize("value", [-1, 0, 2**63, True, 1.0, "1"])
def test_exchange_export_timestamp_strict_even_with_recomputed_digest(value):
    data = package().to_dict()
    data["exported_at_us"] = value
    with pytest.raises(ExchangeError, match="ENVELOPE_IDENTITY"):
        decode_package(resign(data))


@pytest.mark.parametrize("value", [None, 1, 2**63 - 1])
def test_exchange_nullable_timestamp_boundaries(value):
    data = package().to_dict()
    data["exported_at_us"] = value
    assert decode_package(resign(data)).exported_at_us == value


def test_json_depth_duplicate_and_float_controls():
    with pytest.raises(ExchangeError, match="INPUT_LIMIT"):
        decode_package("[" * 33 + "0" + "]" * 33)
    with pytest.raises(ExchangeError, match="duplicate key"):
        decode_package('{"format": 1, "format": 2}')
    data = package().to_dict()
    data["core"]["repository_claims"] = [{"value_json": "1.5"}]
    assert (
        decode_package(resign(data)).core["repository_claims"][0]["value_json"] == "1.5"
    )
    data["core"]["repository_claims"][0]["value_json"] = "[" * 33 + "0" + "]" * 33
    with pytest.raises(ExchangeError, match="INPUT_LIMIT"):
        decode_package(resign(data))


@pytest.mark.parametrize("value", [-1, 0, 2**63, True, 1.0, "1"])
def test_provider_timestamp_rejects_invalid_values(value):
    with pytest.raises((ValueError, TypeError)):
        normalize_issue(
            str(uuid4()),
            {"id": 1, "updated_at": value},
            None,
            '{"evidence":"synthetic","source":"synthetic"}',
        )


def test_repository_unknown_observation_retained_without_fabricated_coordinates(
    tmp_path,
):
    cat = tmp_path / "cat"
    repo, _ = init_catalog_stores(cat, stores=("context", "operational"))
    svc = str(uuid4())
    batch = ProviderIntakeBatch(
        svc,
        providers=(ProviderRegistration(svc),),
        repositories=(
            RepositoryRegistration(
                repo,
                raw_metadata={"id": 1, "name": "repo"},
                provenance_json='{"evidence":"synthetic","source":"synthetic"}',
            ),
        ),
    )
    ProviderAcquisition(cat).admit_batch(batch)
    with Context.snapshot(cat) as ctx:
        rows = ctx.db.execute("SELECT observed_at_us FROM field_candidates").fetchall()
        assert rows and all(row[0] is None for row in rows)
        assert not ctx.db.execute(
            "SELECT 1 FROM resource_repository_relations"
        ).fetchall()
    with pytest.raises(ValueError):
        normalize_repository_fields(
            svc,
            {"name": "missing id"},
            None,
            '{"evidence":"synthetic","source":"synthetic"}',
        )
    with pytest.raises(ValueError, match="provenance"):
        ProviderAcquisition(cat).admit_batch(
            ProviderIntakeBatch(
                svc,
                repositories=(RepositoryRegistration(repo, raw_metadata={"id": 1}),),
            )
        )


def test_provider_registration_is_explicit(tmp_path):
    cat = tmp_path / "cat"
    init_catalog_stores(cat, stores=("context",))
    with pytest.raises(ValueError, match="registration"):
        ProviderAcquisition(cat).admit_batch(ProviderIntakeBatch(str(uuid4())))


@pytest.mark.parametrize("loss", ["all", "budget"])
def test_operational_loss_never_reissues_same_request_even_new_flag(tmp_path, loss):
    cat = tmp_path / "cat"
    repo, inst = init_catalog_stores(cat, stores=("core", "operational"))
    req = RequestIdentity(str(uuid4()), str(uuid4()))
    path = cat / "operational.sqlite3"
    with OperationalAcquisitionLedger(path) as ledger:
        _, _, budget, _ = ledger.create_budget(
            scope=["test"], request=req, new_request=True
        )
        budget.require("input_bytes", 10)
        budget.charge("input_bytes", 10)
        if loss == "budget":
            ledger.db.execute(
                'DELETE FROM request_budgets WHERE work_kind="verification_bytes"'
            )
    if loss == "all":
        path.unlink()
        initialize(path, "operational", repo, inst)
    with OperationalAcquisitionLedger(path) as ledger:
        with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
            ledger.create_budget(scope=["test"], request=req, new_request=True)
        fresh, _, budget, _ = ledger.create_budget(scope=["test"], new_request=True)
        assert fresh != req
        assert budget.ledger.usage(fresh)["input_bytes"] == 0
    core = GitCore(cat / "core.sqlite3")
    try:
        assert core.catalog_identity() == (repo, inst)
    finally:
        core.close()


def test_retry_preserves_notes_capture_and_all_copy_ids(tmp_path, git_format):
    src = tmp_path / "git"
    oids = build_sample_git_repo(src, git_format)
    cat = tmp_path / "cat"
    repo, _ = init_catalog_stores(cat)
    req = request(
        repo,
        oids["commit2"],
        notes=NotesAcquisitionSpec(
            discover_notes=True,
            acquire_inventories=True,
            target_oids=(oids["commit2"],),
        ),
    )
    acq = GitAcquisition(cat, operational=cat)
    first = acq.acquire_from_native(GitNativeSource(src), req, new_request=True)
    second = acq.acquire_from_native(GitNativeSource(src), req)
    assert first.notes_discoveries[0].captures == second.notes_discoveries[0].captures
    assert (
        first.note_acquisitions[0].physical_copy_uuidv4
        == second.note_acquisitions[0].physical_copy_uuidv4
    )
    core = GitCore(cat / "core.sqlite3")
    try:
        assert core.sql("SELECT count(*) FROM retained_metadata")[0][0] == 1
        assert core.sql("SELECT count(*) FROM retained_notes")[0][0] == 1
        assert (
            core.coverage(CoreCoverageScope("repository", (repo, "git_metadata"))).state
            == "partial"
        )
    finally:
        core.close()
    with OperationalAcquisitionLedger(cat) as ledger:
        usage = ledger.work_ledger.usage(
            RequestIdentity(req.capture_origin_uuidv4, req.capture_uuidv4)
        )
        assert usage["input_bytes"] > 0 and usage["verification_bytes"] > 0


def test_paired_git_processes_run_before_core_transaction(tmp_path, monkeypatch):
    src = tmp_path / "git"
    oids = build_sample_git_repo(src)
    cat = tmp_path / "cat"
    repo, _ = init_catalog_stores(cat)
    source = GitNativeSource(src)
    original = source.metadata
    checked = []

    def bounded_read(oid, work):
        from repo_catalog.adapters.sqlite.p1_schema import connect

        db = connect(cat / "core.sqlite3", "core")
        try:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
            checked.append(oid)
        finally:
            db.close()
        return original(oid, work)

    monkeypatch.setattr(source, "metadata", bounded_read)
    result = PairedAcquisitionCoordinator(cat).admit_paired(
        git_source=source, git_request=request(repo, oids["commit2"]), new_request=True
    )
    assert checked and result.admission == PairAdmission(True, True)


def test_git_input_read_is_prepaid(tmp_path, monkeypatch):
    src = tmp_path / "git"
    oids = build_sample_git_repo(src)
    source = GitNativeSource(src)
    work = UnlimitedWorkBudget(work_limits={"input_bytes": 0})
    from types import SimpleNamespace

    import repo_catalog.adapters.git.notes as notes

    monkeypatch.setattr(
        notes,
        "os",
        SimpleNamespace(read=lambda *args: pytest.fail("unreserved input read")),
    )
    with pytest.raises(CoreFailure, match="budget"):
        source.metadata(oids["commit2"], work)
    with pytest.raises(CoreFailure, match="budget"):
        source.refs(work)


def test_exchange_partial_commit_outcome_survives(tmp_path, monkeypatch):
    cat = tmp_path / "cat"
    repo, _ = init_catalog_stores(cat)
    service = ExchangeService(cat)
    data = package(repo).to_dict()
    from repo_catalog.domain.exchange import empty_context_section

    data["context"] = empty_context_section()

    def broken(*args):
        raise ValueError("context failure")

    monkeypatch.setattr(service, "_import_context_into", broken)
    with pytest.raises(AdmissionFailure) as failure:
        service.import_package(resign(data), new_request=True)
    assert failure.value.outcome == PairAdmission(True, False)
    assert isinstance(failure.value.cause, ValueError)


def test_exchange_wire_budget_and_repeat_are_cumulative(tmp_path):
    cat = tmp_path / "cat"
    repo, _ = init_catalog_stores(cat)
    pkg = package(repo)
    service = ExchangeService(cat)
    identity = RequestIdentity(pkg.sender_catalog_instance_uuidv4, pkg.package_id)
    raw = encode_package(pkg)
    service.import_package(raw, request=identity, new_request=True)
    with OperationalAcquisitionLedger(cat) as ledger:
        before = ledger.work_ledger.usage(identity)
    service.import_package(raw, request=identity)
    with OperationalAcquisitionLedger(cat) as ledger:
        after = ledger.work_ledger.usage(identity)
    assert after["input_bytes"] == 2 * before["input_bytes"]
    assert after["verification_bytes"] == 2 * before["verification_bytes"]
    assert 0 < before["input_bytes"] < 10000
    assert 0 < before["metadata_units"] < 1000
