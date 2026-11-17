"""Real transaction owners preserve initiating errors after Core discards SQL."""

import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.core_recovery import RecoveryWorkBudget
from repo_catalog.adapters.sqlite.p1_core import Core
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.paired_admission import PairCoordinator
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.p1_coordination import AdmissionFailure
from repo_catalog.domain.p1_core import RelationGroup, RelationMember
from tests.integration.p1.test_core import core, oid, provenance

__all__ = ["core"]


def group():
    return RelationGroup(
        oid("c"),
        "commit_parents",
        "owner-cleanup-original",
        "complete",
        (RelationMember(0, oid("d")),),
        provenance(),
    )


def refuse_rollback(transaction):
    execute = transaction.execute

    def refusing(statement, *args, **kwargs):
        if statement == "ROLLBACK TO p1_core_unit":
            raise sqlite3.OperationalError("injected Core unit rollback refusal")
        return execute(statement, *args, **kwargs)

    transaction.execute = refusing


def assert_discarded(raw, path):
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        raw.execute("COMMIT")
    with closing(Core(path)) as reopened:
        assert reopened.sql("SELECT * FROM git_objects") == []
        assert reopened.sql("SELECT * FROM relation_groups") == []
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "cancelled", [False, True], ids=["admission-failure", "cancellation"]
)
def test_real_pair_owner_preserves_failure_outcome_and_original_cause_after_discard(
    core, cancelled
):
    owner, path, repository = core
    instance = owner.sql("SELECT catalog_instance_uuidv4 FROM store_identity")[0][0]
    initialize(path.parent / "context.sqlite3", "context", repository, instance)
    initiating = (
        KeyboardInterrupt("original cancellation")
        if cancelled
        else ValueError("original evidence failure")
    )
    raw_connections = []

    def fail():
        raise initiating

    def core_unit(transaction):
        raw_connections.append(transaction._db)
        with Core.for_transaction(transaction) as capability:
            capability.admit_object(oid("a"))
            refuse_rollback(transaction)
            capability.admit_group(group(), before_commit=fail)

    expected = KeyboardInterrupt if cancelled else AdmissionFailure
    with pytest.raises(expected) as failure:
        PairCoordinator(path.parent).admit(core_unit, lambda _transaction: None)
    if cancelled:
        assert failure.value is initiating
    else:
        assert failure.value.cause is initiating
        assert not failure.value.outcome.core_committed
        assert not failure.value.outcome.context_committed
    assert any("OperationalError" in note for note in initiating.__notes__)
    assert_discarded(raw_connections[0], path)


def test_real_core_only_exchange_owner_preserves_original_after_discard(
    core, tmp_path, monkeypatch
):
    source, path, repository = core
    source.admit_group(group())
    package = ExchangeService(path.parent).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_context=False)
    )
    receiver = tmp_path / "receiver"
    receiver.mkdir()
    instance = str(uuid4())
    for role in ("core", "operational"):
        initialize(receiver / (role + ".sqlite3"), role, repository, instance)
    original = ValueError("original checked group failure")
    raw_connections = []
    admit = Core.admit_group

    def fail():
        raise original

    def refusing(capability, value, *args, **kwargs):
        transaction = capability._db
        raw_connections.append(transaction._db)
        refuse_rollback(transaction)
        return admit(capability, value, *args, before_commit=fail, **kwargs)

    monkeypatch.setattr(Core, "admit_group", refusing)
    with pytest.raises(ValueError) as failure:
        ExchangeService(receiver).import_package(
            package, new_request=True, permitted_repository_uuidv4s=(repository,)
        )
    assert failure.value is original
    assert any("OperationalError" in note for note in original.__notes__)
    assert_discarded(raw_connections[0], receiver / "core.sqlite3")


@pytest.mark.parametrize(
    "work_boundary", [False, True], ids=["domain-error", "work-callback-error"]
)
def test_real_ref_salvage_owner_preserves_original_after_discard(
    core, monkeypatch, work_boundary
):
    import repo_catalog.adapters.sqlite.ref_salvage as salvage

    _owner, path, _repository = core
    original = ValueError("original salvage evidence failure")
    raw_connections = []

    def fail():
        if work_boundary:
            raise salvage._WorkCallbackFailure(original)
        raise original

    def refusing(capability, _kind, _payload, _work):
        raw = capability._db
        raw_connections.append(raw)
        execute = raw.execute

        class RefusingRollback:
            def __getattr__(self, name):
                return getattr(raw, name)

            def execute(self, statement, *args, **kwargs):
                if statement == "ROLLBACK TO p1_core_unit":
                    raise sqlite3.OperationalError("injected salvage rollback refusal")
                return execute(statement, *args, **kwargs)

        capability.admit_object(oid("a"))
        capability._db = RefusingRollback()
        capability.admit_group(group(), before_commit=fail)

    monkeypatch.setattr(salvage, "admit_ref_unit", refusing)
    with pytest.raises(ValueError) as failure:
        salvage.admit_ref_unit_atomic(
            path.parent, "ref_subject", {}, RecoveryWorkBudget()
        )
    assert failure.value is original
    assert any("OperationalError" in note for note in original.__notes__)
    assert_discarded(raw_connections[0], path)
