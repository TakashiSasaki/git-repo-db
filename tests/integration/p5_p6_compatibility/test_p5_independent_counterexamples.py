import json
import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.github.production_intake import normalize_repository_fields
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.acquisition import (
    GitAcquisition,
    PairedAcquisitionCoordinator,
)
from repo_catalog.domain.acquisition import (
    GitNativeAcquisitionRequest,
)
from repo_catalog.domain.exchange import ExchangePackage, decode_package, encode_package
from repo_catalog.domain.p1_coordination import RequestIdentity
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


def test_declared_digest_required():
    p = ExchangePackage(str(uuid4()), 1, str(uuid4()), str(uuid4()))
    d = json.loads(encode_package(p))
    assert "digest_sha256" in d
    d["package_id"] = str(uuid4())
    with pytest.raises(ValueError):
        decode_package(d)


def test_missing_repository_provider_id_rejected():
    with pytest.raises(ValueError):
        normalize_repository_fields(
            str(uuid4()),
            str(uuid4()),
            {"name": "partial"},
            1,
            '{"evidence":"minimal","source":"synthetic"}',
        )


def test_native_external_io_outside_write_transaction(tmp_path, monkeypatch):
    cat = tmp_path / "cat"
    repo, _ = init_catalog_stores(cat)
    oids = build_sample_git_repo(tmp_path / "git")
    source = GitNativeSource(tmp_path / "git")
    original = source.metadata
    seen = []

    def checked(oid, *args, **kwargs):
        db = sqlite3.connect(cat / "core.sqlite3", timeout=0)
        try:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
            seen.append("free")
        except sqlite3.OperationalError:
            seen.append("locked")
        finally:
            db.close()
        return original(oid, *args, **kwargs)

    monkeypatch.setattr(source, "metadata", checked)
    req = GitNativeAcquisitionRequest(
        repo,
        str(uuid4()),
        str(uuid4()),
        "synthetic",
        1,
        select_oids=(oids["commit1"],),
        include_refs=False,
    )
    PairedAcquisitionCoordinator(cat).admit_paired(
        git_source=source, git_request=req, new_request=True
    )
    assert seen and set(seen) == {"free"}, seen


def test_selected_object_never_repository_complete(tmp_path):
    cat = tmp_path / "cat"
    repo, _ = init_catalog_stores(cat)
    oids = build_sample_git_repo(tmp_path / "git")
    req = GitNativeAcquisitionRequest(
        repo,
        str(uuid4()),
        str(uuid4()),
        "synthetic",
        1,
        select_oids=(oids["commit1"],),
        include_refs=False,
    )
    r = GitAcquisition(cat / "core.sqlite3", operational=cat).acquire_from_native(
        GitNativeSource(tmp_path / "git"), req, new_request=True
    )
    assert all(
        c.state != "complete"
        for c in r.coverage_claims
        if c.scope.owner_kind == "repository"
        and c.scope.coordinates == (repo, "git_metadata")
    )


def test_retry_preserves_physical_copy(tmp_path):
    cat = tmp_path / "cat"
    repo, _ = init_catalog_stores(cat)
    oids = build_sample_git_repo(tmp_path / "git")
    req = GitNativeAcquisitionRequest(
        repo,
        str(uuid4()),
        str(uuid4()),
        "synthetic",
        1,
        select_oids=(oids["commit1"],),
        include_refs=False,
        retain_bytes=True,
    )
    acq = GitAcquisition(cat / "core.sqlite3", operational=cat)
    acq.acquire_from_native(GitNativeSource(tmp_path / "git"), req, new_request=True)
    with sqlite3.connect(cat / "core.sqlite3") as db:
        before = db.execute("SELECT count(*) FROM retained_metadata").fetchone()[0]
    acq.acquire_from_native(GitNativeSource(tmp_path / "git"), req)
    with sqlite3.connect(cat / "core.sqlite3") as db:
        after = db.execute("SELECT count(*) FROM retained_metadata").fetchone()[0]
    assert before == after


@pytest.mark.parametrize("declare_new", [False, True])
def test_missing_request_after_operational_loss_refuses_resume(tmp_path, declare_new):
    from repo_catalog.domain.p1_coordination import CoordinationError

    cat = tmp_path / "cat"
    repo, inst = init_catalog_stores(cat)
    req = RequestIdentity(str(uuid4()), str(uuid4()))
    with OperationalAcquisitionLedger(cat) as ledger:
        _, _, budget, _ = ledger.create_budget(
            scope=["synthetic"], request=req, new_request=True
        )
        budget.require("input_bytes", 5)
        budget.charge("input_bytes", 5)
    for p in cat.glob("operational.sqlite3*"):
        p.unlink()
    initialize(cat / "operational.sqlite3", "operational", repo, inst)
    with OperationalAcquisitionLedger(cat) as ledger:
        with pytest.raises(CoordinationError):
            ledger.create_budget(
                scope=["synthetic"], request=req, new_request=declare_new
            )


def test_exchange_retains_partial_admission_outcome(tmp_path, monkeypatch):
    from repo_catalog.application.exchange import ExchangeService
    from repo_catalog.domain.exchange import empty_context_section, empty_core_section
    from repo_catalog.domain.p1_coordination import AdmissionFailure, PairAdmission

    cat = tmp_path / "cat"
    repo, inst = init_catalog_stores(cat)
    core = empty_core_section()
    core["git_objects"].append({"object_format": "sha1", "full_oid": "a" * 40})
    p = ExchangePackage(
        str(uuid4()), 1, str(uuid4()), repo, core=core, context=empty_context_section()
    )
    service = ExchangeService(cat)

    def bad(*args, **kwargs):
        raise ValueError("synthetic context failure")

    monkeypatch.setattr(service, "_import_context_into", bad)
    with pytest.raises(AdmissionFailure) as err:
        service.import_package(p, new_request=True)
    assert err.value.outcome == PairAdmission(True, False)


def test_exchange_export_uses_one_paired_snapshot(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from repo_catalog.application.exchange import ExchangeService
    from repo_catalog.domain.p1_context import ResourceKey
    from repo_catalog.domain.p1_core import OID

    cat = tmp_path / "cat"
    repo, inst = init_catalog_stores(cat)
    service = ExchangeService(cat)
    original = service._export_core
    oid = OID("sha1", "b" * 40)
    svc = str(uuid4())
    rk = ResourceKey(svc, "issue", "1")
    attempted = threading.Event()
    completed = threading.Event()
    observed = []
    executor = ThreadPoolExecutor(max_workers=1)
    future = []

    def writer():
        attempted.set()

        def core(cap):
            cap.admit_object(oid)

        def ctx(cap):
            cap.provider(svc, "github", "{}")
            cap.resource(rk)
            cap.link_core(
                rk,
                "head",
                *oid.key,
                '{"evidence":"synthetic","source":"synthetic"}',
                lambda *_: True,
            )

        PairedAcquisitionCoordinator(cat).admit_paired(core_fn=core, context_fn=ctx)
        completed.set()

    def racing(*args, **kwargs):
        result = original(*args, **kwargs)
        future.append(executor.submit(writer))
        assert attempted.wait(3)
        observed.append(completed.wait(0.2))
        return result

    monkeypatch.setattr(service, "_export_core", racing)
    try:
        p = service.export_package(exported_at_us=1)
        future[0].result(timeout=10)
    finally:
        executor.shutdown(wait=True)
    assert observed == [False], "paired writer escaped shared export fence"
    assert p.core["git_objects"] == [] and p.context["core_references"] == []
    assert completed.is_set()


def test_exchange_export_refuses_stop_before_return(tmp_path, monkeypatch):
    from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
    from repo_catalog.application.exchange import ExchangeService
    from repo_catalog.domain.p1_coordination import CoordinationError

    cat = tmp_path / "cat"
    init_catalog_stores(cat)
    service = ExchangeService(cat)
    original = service._export_context

    def stop_after_read(*args, **kwargs):
        result = original(*args, **kwargs)
        persist_catalog_stop(cat, "synthetic independent stop before export completion")
        return result

    monkeypatch.setattr(service, "_export_context", stop_after_read)
    with pytest.raises((CoordinationError, ValueError)):
        service.export_package(exported_at_us=1)
