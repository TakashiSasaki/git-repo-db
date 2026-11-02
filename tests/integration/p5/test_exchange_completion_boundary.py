"""Completion is fenced after identity, accounting and paired owned cleanup."""

from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.catalog_runtime import persist_catalog_stop
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.operational_coordination import NotesWorkBudget
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.paired_admission import PairCoordinator
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.exchange import (
    ExchangePackage,
    ExchangeSelectionScope,
    empty_core_section,
)
from repo_catalog.domain.p1_coordination import (
    CoordinationError,
    NotesLimits,
    RequestIdentity,
)


def fixture(directory, *, context=False):
    directory.mkdir()
    repository, instance = str(uuid4()), str(uuid4())
    for role in ("core", "operational", *(("context",) if context else ())):
        initialize(directory / (role + ".sqlite3"), role, repository, instance)
    section = empty_core_section()
    section["git_objects"] = [{"object_format": "sha1", "object_oid": "1" * 40}]
    package = ExchangePackage(
        str(uuid4()),
        1700000500000000,
        str(uuid4()),
        repository,
        selection_scope=ExchangeSelectionScope(
            all_selected=True, include_context=False
        ),
        core=section,
    )
    return repository, package


@pytest.mark.parametrize("boundary", ["identity", "operational"])
def test_owned_cleanup_stop_cannot_return_complete(tmp_path, monkeypatch, boundary):
    directory = tmp_path / "catalog"
    repository, package = fixture(directory)
    owner = GitCore if boundary == "identity" else OperationalAcquisitionLedger
    original = owner.close
    calls = []

    def stopped(capability):
        original(capability)
        calls.append(True)
        persist_catalog_stop(directory, "synthetic post-owned-cleanup stop")

    monkeypatch.setattr(owner, "close", stopped)
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        ExchangeService(directory).import_package(
            package, new_request=True, permitted_repository_uuidv4s=(repository,)
        )
    assert calls
    with closing(connect(directory / "operational.sqlite3", "operational")) as db:
        requests = db.execute("SELECT count(*) FROM acquisition_requests").fetchone()[0]
    assert requests == (0 if boundary == "identity" else 1)
    if boundary == "identity":
        assert not list((directory / "p5-request-witnesses").glob("*/*"))


def test_pair_owned_connection_cleanup_stop_cannot_return_complete(tmp_path):
    directory = tmp_path / "catalog"
    fixture(directory, context=True)
    coordinator = PairCoordinator(directory)
    original = coordinator._open
    closes = []

    class CloseStop:
        def __init__(self, db, role):
            self.db, self.role = db, role

        def __getattr__(self, name):
            return getattr(self.db, name)

        def close(self):
            self.db.close()
            closes.append(self.role)
            if self.role == "context":
                persist_catalog_stop(directory, "synthetic paired cleanup stop")

    coordinator._open = lambda role: CloseStop(original(role), role)
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        coordinator.admit(lambda tx: None, lambda tx: None)
    assert closes == ["context", "core"]


@pytest.mark.parametrize("counterfeit", ["subclass", "ledger"])
def test_counterfeit_accounting_refused_before_input_work(tmp_path, counterfeit):
    directory = tmp_path / "catalog"
    repository, package = fixture(directory)
    request = RequestIdentity(str(uuid4()), str(uuid4()))

    class FreeBudget(NotesWorkBudget):
        def require(self, *args):
            pass

        def charge(self, *args):
            pass

        def abandon(self, *args):
            pass

    with OperationalAcquisitionLedger(directory) as ledger:
        _, attempt, canonical, _ = ledger.create_budget(
            scope=["supported-custom-scope"],
            request=request,
            new_request=True,
            work_limits={unit: 0 for unit in NotesLimits.work_limits()},
        )
        if counterfeit == "subclass":
            work = FreeBudget(ledger.work_ledger, request, attempt, NotesLimits())
        else:
            work = canonical
            work.ledger = object()
        with pytest.raises(Exception, match="DURABLE_BUDGET_REQUIRED"):
            ExchangeService(directory, operational=ledger).import_package(
                package,
                work=work,
                request=request,
                permitted_repository_uuidv4s=(repository,),
            )
        assert not any(ledger.work_ledger.usage(request).values())
    with closing(GitCore(directory / "core.sqlite3")) as core:
        assert not core.sql("SELECT * FROM git_objects")
    assert not (directory / "p1-recovery-stop.json").exists()


def test_lost_final_checkpoint_refuses_without_rolling_back_core(tmp_path):
    directory = tmp_path / "catalog"
    repository, package = fixture(directory)
    request = RequestIdentity(str(uuid4()), str(uuid4()))
    with OperationalAcquisitionLedger(directory) as ledger:
        deleted = []

        def cut(point):
            if point == "after_summary":
                deleted.append(
                    ledger.db.execute(
                        "DELETE FROM request_continuations WHERE request_origin_uuidv4=? "
                        "AND request_uuidv4=? AND continuation_scope_json=?",
                        (*request.values(), ledger.work_ledger._CHECKPOINT_SCOPE),
                    ).rowcount
                )

        with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
            ExchangeService(directory, operational=ledger).import_package(
                package,
                request=request,
                new_request=True,
                permitted_repository_uuidv4s=(repository,),
                cut=cut,
            )
        assert deleted == [1]
    with closing(GitCore(directory / "core.sqlite3")) as core:
        assert len(core.sql("SELECT * FROM git_objects")) == 1
    assert not (directory / "p1-recovery-stop.json").exists()
