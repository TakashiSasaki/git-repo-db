"""Reported Groups never lend Repository authority to caller work callbacks."""

import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_repository import RepositoryFailure
from tests.integration.p4 import conftest as fixtures
from tests.integration.p4.test_ref_observation_i2 import discover

acquisition = fixtures.acquisition


@contextmanager
def group_repository(app, repository_path, external):
    if not external:
        yield app.repository_store
        return
    with closing(connect(repository_path, "repository")) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            with GitRepositoryStore.for_transaction(db) as repository_store:
                yield repository_store
        finally:
            db.rollback()


def reported_group(acquisition):
    app, _, _, repository, origin, *_ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    return app.inventory_ref(claim).group


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("mode", ["require", "charge"])
def test_group_callbacks_cannot_write_reenter_or_read_proofs(
    acquisition, external, mode
):
    app, _, _, repository, _, repository_path, _ = acquisition
    original = reported_group(acquisition)
    assert app.verify_ref_inventory(original).verified
    group = replace(
        original,
        provenance=replace(original.provenance, coordinate="callback-group"),
    )
    injected = str(uuid4())
    phases = set()

    with group_repository(app, repository_path, external) as repository_store:

        class Reentrant(UnlimitedWorkBudget):
            def probe(self):
                phases.add(repository_store._db.in_transaction)
                for action in (
                    lambda: repository_store._db.execute(
                        "INSERT INTO repositories(repository_uuidv4) VALUES (?)",
                        (injected,),
                    ),
                    lambda: repository_store.admit_repository(injected),
                    lambda: repository_store.sql("SELECT 1"),
                    lambda: repository_store._db.execute(
                        "SELECT structures_json FROM ref_coverage_proofs"
                    ).fetchall(),
                    lambda: repository_store._db.execute("COMMIT"),
                    lambda: repository_store._db.execute("ROLLBACK"),
                ):
                    with pytest.raises(sqlite3.DatabaseError):
                        action()

            def require(self, unit, amount=1):
                if mode == "require":
                    self.probe()
                return super().require(unit, amount)

            def charge(self, unit, amount):
                if mode == "charge":
                    self.probe()
                return super().charge(unit, amount)

        repository_store.admit_notes_mapping_group(group, Reentrant())
        assert (
            repository_store.sql(
                "SELECT count(*) FROM notes_mapping_groups WHERE provenance=?",
                (group.key[-1],),
            )[0][0]
            == 1
        )
        assert not repository_store.sql(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?", (injected,)
        )
        repository_store.ensure_available()

    assert phases == ({True} if external else {False, True})
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()
    assert (
        app.repository_store.sql("SELECT count(*) FROM ref_coverage_proofs")[0][0] == 1
    )
    assert repository != injected


class CallerCancelled(BaseException):
    pass


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("mode", ["require", "charge"])
@pytest.mark.parametrize("kind", ["sqlite", "repository", "json", "cancel"])
def test_group_callback_failure_rolls_back_without_false_corruption(
    acquisition, external, mode, kind
):
    app, _, _, _, _, repository_path, _ = acquisition
    original = reported_group(acquisition)
    target, note, path = original.members[0]
    target = "b" * len(target)
    group = replace(
        original,
        members=((target, note, path),),
        provenance=replace(original.provenance, coordinate="failed-callback-group"),
    )
    failure = {
        "sqlite": sqlite3.DatabaseError("caller CORRUPT-shaped error"),
        "repository": RepositoryFailure(
            "AUTHORITATIVE_CORRUPTION", "caller", "caller error"
        ),
        "json": json.JSONDecodeError("caller JSON error", "x", 0),
        "cancel": CallerCancelled("caller cancellation"),
    }[kind]
    if kind == "sqlite":
        failure.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
    triggered = []

    with group_repository(app, repository_path, external) as repository_store:

        class Failing(UnlimitedWorkBudget):
            def probe(self):
                # Raise only after the unit has inserted its first object.
                # Reading nominal metadata does not require byte authority.
                if (
                    repository_store._db.in_transaction
                    and repository_store._db.execute(
                        "SELECT 1 FROM git_objects WHERE object_oid=?", (target,)
                    ).fetchone()
                ):
                    triggered.append(True)
                    raise failure

            def require(self, unit, amount=1):
                if mode == "require":
                    self.probe()
                return super().require(unit, amount)

            def charge(self, unit, amount):
                if mode == "charge":
                    self.probe()
                return super().charge(unit, amount)

        with pytest.raises(type(failure)) as caught:
            repository_store.admit_notes_mapping_group(group, Failing())
        assert caught.value is failure and triggered == [True]
        repository_store.ensure_available()
        assert not repository_store.sql(
            "SELECT 1 FROM git_objects WHERE object_oid=?", (target,)
        )
        assert (
            repository_store.sql("SELECT count(*) FROM notes_mapping_groups")[0][0] == 1
        )
        assert repository_store._db.in_transaction is external
        repository_store.admit_notes_mapping_group(group, app.work)
        repository_store.admit_notes_mapping_group(group)
        assert (
            repository_store.sql("SELECT count(*) FROM notes_mapping_groups")[0][0] == 2
        )

    assert not (repository_path.parent / "p1-recovery-stop.json").exists()
    app.repository_store.ensure_available()


def test_group_admission_budget_failure_keeps_existing_facts(acquisition):
    app, _, _, _, _, repository_path, _ = acquisition
    original = reported_group(acquisition)
    group = replace(
        original,
        provenance=replace(original.provenance, coordinate="budget-limited-group"),
    )
    with pytest.raises(RepositoryFailure) as caught:
        app.repository_store.admit_notes_mapping_group(
            group, UnlimitedWorkBudget(work_limits={"input_bytes": 1})
        )
    assert caught.value.code == "BUDGET"
    assert (
        app.repository_store.sql("SELECT count(*) FROM notes_mapping_groups")[0][0] == 1
    )
    app.repository_store.admit_notes_mapping_group(group, app.work)
    assert (
        app.repository_store.sql("SELECT count(*) FROM notes_mapping_groups")[0][0] == 2
    )
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


def test_group_admission_still_stops_on_damaged_stored_subject(acquisition):
    app, _, _, _, _, repository_path, _ = acquisition
    group = reported_group(acquisition)
    with closing(connect(repository_path, "repository")) as db:
        name = "p1_immutable_ref_observations_update"
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name=?", (name,)
        ).fetchone()[0]
        db.execute("DROP TRIGGER " + name)
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE ref_observations SET ref_name_bytes=X''")
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.execute(trigger)
        db.commit()
    with pytest.raises(RepositoryFailure) as caught:
        app.repository_store.admit_notes_mapping_group(group, app.work)
    assert caught.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (repository_path.parent / "p1-recovery-stop.json").exists()
