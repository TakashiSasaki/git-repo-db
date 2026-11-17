"""A failed Context undo cannot leave a partial resource committable by its owner."""

import sqlite3
from contextlib import nullcontext
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.paired_admission import PairCoordinator
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_coordination import AdmissionFailure
from repo_catalog.domain.production_context import ResourceObservation
from repo_catalog.domain.resource_identification import ResourceIdentification


@pytest.fixture
def catalog(tmp_path):
    repository, instance, service = (str(uuid4()) for _ in range(3))
    for role in ("core", "context"):
        initialize(tmp_path / (role + ".sqlite3"), role, repository, instance)
    keys = tuple(
        ResourceKey.from_native(service, "issue", str(value))
        for value in range(100, 104)
    )
    authorization, admission, policy = create_local_admission_service(
        "salvage_merge",
        grants=DependencySet(resources=set(keys), provider_registrations={service}),
        selection=AdmissionSelection(all_selected=True),
    )
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        context.provider(service, "synthetic")
    pair = PairCoordinator(tmp_path, authorization=authorization)

    def healthy(transaction):
        with Context.for_transaction(
            transaction, tmp_path, authorization=authorization, admission=admission
        ) as context:
            context.observe(observation(keys[0], "previously committed"))

    outcome = pair.admit(
        lambda _: None, healthy, authorization=authorization, admission=admission
    )
    assert outcome.core_committed and outcome.context_committed
    assert len(facts(tmp_path, keys[0])[1]) == 2
    return tmp_path, keys, authorization, admission, policy


def observation(key, label):
    return ResourceObservation(
        key,
        tuple(
            FieldCandidate(
                key,
                name,
                canonical(label + " " + name),
                FieldClock("provider.updated_at", 10),
                canonical(
                    {"source": "cleanup-regression", "evidence": label + " " + name}
                ),
                100,
            )
            for name in ("title", "author")
        ),
        ResourceIdentification.unscoped(key),
    )


def facts(directory, key):
    with Context.snapshot(directory) as context:
        nominal = context.db.execute(
            "SELECT count(*) FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
            key.coordinates(),
        ).fetchone()[0]
        values = context.db.execute(
            "SELECT field_name,value_json,clock_json,provenance_json,observed_at_us FROM field_candidates "
            "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? ORDER BY field_name",
            key.coordinates(),
        ).fetchall()
        return nominal, tuple(tuple(row) for row in values)


def assert_discarded(raw, directory, healthy, before, failed, sibling):
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        raw.execute("COMMIT")
    assert facts(directory, healthy) == before
    assert facts(directory, failed) == facts(directory, sibling) == (0, ())
    assert not (directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "cleanup,managed,cancelled",
    [
        ("rollback-to", True, False),
        ("rollback-to", False, False),
        ("release", True, False),
        ("release", False, False),
        ("rollback-to", True, True),
    ],
    ids=[
        "rollback-managed",
        "rollback-direct",
        "release-managed",
        "release-direct",
        "cancelled",
    ],
)
def test_actual_pair_caught_context_failure_discards_sql_and_all_owned_leases(
    catalog, cleanup, managed, cancelled
):
    directory, keys, authorization, admission, policy = catalog
    healthy, failed, sibling, reopened = keys
    before, held = facts(directory, healthy), {}
    attempted = observation(failed, "failed resource")
    original_input = repr(attempted)
    original = (
        KeyboardInterrupt("original Context cancellation")
        if cancelled
        else ValueError("original second-field refusal")
    )
    state = {"inserts": 0, "refusals": 0, "rollback": False, "failed": False}

    def callback(transaction):
        held["raw"], held["guard"] = transaction._db, transaction
        execute = transaction.execute

        def refusing(sql, *args, **kwargs):
            statement = sql.strip().upper()
            if state["failed"] and statement.startswith("ROLLBACK TO"):
                state["rollback"] = True
                if cleanup == "rollback-to":
                    state["refusals"] += 1
                    raise sqlite3.OperationalError("injected Context rollback refusal")
            if (
                state["failed"]
                and state["rollback"]
                and cleanup == "release"
                and statement.startswith("RELEASE")
            ):
                state["refusals"] += 1
                raise sqlite3.OperationalError("injected Context release refusal")
            if statement.startswith("INSERT INTO FIELD_CANDIDATES"):
                state["inserts"] += 1
                if state["inserts"] == 2:
                    assert (
                        transaction._db.execute(
                            "SELECT count(*) FROM field_candidates WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                            failed.coordinates(),
                        ).fetchone()[0]
                        == 1
                    )
                    state["failed"] = True
                    raise original
            return execute(sql, *args, **kwargs)

        transaction.execute = refusing
        boundary = (
            Context.for_transaction(
                transaction, directory, authorization=authorization, admission=admission
            )
            if managed
            else nullcontext(
                Context(
                    transaction, directory, writable=True, authorization=authorization
                )
            )
        )
        with boundary as context:
            held["context"] = context
            with pytest.raises(type(original)) as caught:
                context.observe(attempted)
            assert caught.value is original
            assert state["refusals"] == 1
            assert any(
                "Context transaction cleanup failed" in note
                and "OperationalError" in note
                for note in original.__notes__
            )
            assert not context._active and not transaction._active
            assert policy.active == 0
            with pytest.raises(Exception) as expired:
                context.observe(observation(sibling, "must not commit"))
            assert getattr(expired.value, "code", None) == "CAPABILITY_EXPIRED"
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                transaction._db.execute("COMMIT")
            # Deliberately return after handling the unit error. The actual
            # owning Pair must refuse rather than commit its pending prefix.

    expected = KeyboardInterrupt if cancelled else AdmissionFailure
    with pytest.raises(expected) as failure:
        PairCoordinator(directory, authorization=authorization).admit(
            lambda _: None, callback, authorization=authorization, admission=admission
        )
    if cancelled:
        assert failure.value is original
    else:
        assert failure.value.cause is original
        assert failure.value.outcome.core_committed
        assert not failure.value.outcome.context_committed
    assert repr(attempted) == original_input and policy.active == 0
    assert_discarded(held["raw"], directory, healthy, before, failed, sibling)
    with Context.transaction(
        directory, authorization=authorization, admission=admission
    ) as context:
        context.observe(observation(reopened, "healthy new connection"))
    assert len(facts(directory, reopened)[1]) == 2


def refuse_second_insert(raw, cleanup):
    state = {"inserts": 0, "failed": False, "refusals": 0, "rolled_back": False}

    def authorize(action, first, *_):
        if action == sqlite3.SQLITE_INSERT and first == "field_candidates":
            state["inserts"] += 1
            if state["inserts"] == 2:
                state["failed"] = True
                return sqlite3.SQLITE_DENY
        if state["failed"] and action == sqlite3.SQLITE_SAVEPOINT:
            if first == "ROLLBACK":
                state["rolled_back"] = True
                if cleanup == "rollback-to":
                    state["refusals"] += 1
                    return sqlite3.SQLITE_DENY
            if first == "RELEASE" and state["rolled_back"] and cleanup == "release":
                state["refusals"] += 1
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    raw.set_authorizer(authorize)
    return state


@pytest.mark.parametrize("owner", ["transaction", "owned-transaction", "raw-store"])
@pytest.mark.parametrize("cleanup", ["rollback-to", "release"])
def test_context_finalizers_keep_original_sql_error_after_failed_cleanup(
    catalog, owner, cleanup
):
    directory, keys, authorization, admission, policy = catalog
    healthy, failed, sibling, reopened = keys
    before, caught = facts(directory, healthy), []
    raw = None
    if owner == "transaction":
        boundary = Context.transaction(
            directory, authorization=authorization, admission=admission
        )
    else:
        raw = connect(directory / "context.sqlite3", "context")
        boundary = (
            Context.owned_transaction(
                raw, directory, authorization=authorization, admission=admission
            )
            if owner == "owned-transaction"
            else ContextStore(raw, authorization=authorization).admission_transaction(
                admission=admission
            )
        )
    try:
        with pytest.raises(sqlite3.DatabaseError) as failed_outer:
            with boundary as context:
                if raw is None:
                    raw = context.db._connection
                state = refuse_second_insert(raw, cleanup)
                if owner == "raw-store":
                    context.resource(failed)
                    context.admit_field(
                        observation(failed, "failed raw unit").fields[0]
                    )
                with pytest.raises(sqlite3.DatabaseError) as initiating:
                    if owner == "raw-store":
                        context.admit_field(
                            observation(failed, "failed raw unit").fields[1]
                        )
                    else:
                        context.observe(observation(failed, "failed facade unit"))
                caught.append(initiating.value)
                assert state["inserts"] == 2 and state["refusals"] == 1
                assert any(
                    "Context transaction cleanup failed" in note
                    for note in initiating.value.__notes__
                )
                assert not context._active and policy.active == 0
                with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                    raw.execute("COMMIT")
                # Swallow the unit exception: owner finalization must retain it.
        assert failed_outer.value is caught[0]
        assert_discarded(raw, directory, healthy, before, failed, sibling)
    finally:
        if raw is not None:
            raw.close()
    with Context.transaction(
        directory, authorization=authorization, admission=admission
    ) as context:
        context.observe(observation(reopened, "fresh connection"))
    assert len(facts(directory, reopened)[1]) == 2


def test_successful_context_rollback_still_allows_an_independent_sibling_unit(catalog):
    directory, keys, authorization, admission, policy = catalog
    healthy, failed, sibling, _ = keys
    before = facts(directory, healthy)

    def callback(transaction):
        with Context.for_transaction(
            transaction, directory, authorization=authorization, admission=admission
        ) as context:
            state = refuse_second_insert(transaction._db, "none")
            with pytest.raises(sqlite3.DatabaseError):
                context.observe(observation(failed, "ordinary refused unit"))
            assert context._active and transaction._active and not state["refusals"]
            context.observe(observation(sibling, "independent sibling"))

    outcome = PairCoordinator(directory, authorization=authorization).admit(
        lambda _: None, callback, authorization=authorization, admission=admission
    )
    assert outcome.core_committed and outcome.context_committed
    assert facts(directory, failed) == (0, ())
    assert len(facts(directory, sibling)[1]) == 2
    assert facts(directory, healthy) == before and policy.active == 0
    assert not (directory / "p1-recovery-stop.json").exists()
