"""Reported Groups never lend Core authority to caller work callbacks."""

import json
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_core import CoreFailure
from tests.integration.p4 import conftest as fixtures
from tests.integration.p4.test_ref_observation_i2 import discover

acquisition = fixtures.acquisition


@contextmanager
def group_core(app, core_path, external):
    if not external:
        yield app.core
        return
    with closing(connect(core_path, "core")) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            with GitCore.for_transaction(db) as core:
                yield core
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
    app, _, _, repository, _, core_path, _ = acquisition
    original = reported_group(acquisition)
    assert app.verify_ref_inventory(original).verified
    group = replace(
        original,
        provenance=replace(original.provenance, coordinate="callback-group"),
    )
    injected = str(uuid4())
    phases = set()

    with group_core(app, core_path, external) as core:

        class Reentrant(UnlimitedWorkBudget):
            def probe(self):
                phases.add(core._db.in_transaction)
                for action in (
                    lambda: core._db.execute(
                        "INSERT INTO repositories(repository_uuidv4) VALUES (?)",
                        (injected,),
                    ),
                    lambda: core.admit_repository(injected),
                    lambda: core.sql("SELECT 1"),
                    lambda: core._db.execute(
                        "SELECT structures_json FROM ref_coverage_proofs"
                    ).fetchall(),
                    lambda: core._db.execute("COMMIT"),
                    lambda: core._db.execute("ROLLBACK"),
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

        core.admit_notes_mapping_group(group, Reentrant())
        assert (
            core.sql(
                "SELECT count(*) FROM notes_mapping_groups WHERE provenance=?",
                (group.key[-1],),
            )[0][0]
            == 1
        )
        assert not core.sql(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?", (injected,)
        )
        core.ensure_available()

    assert phases == ({True} if external else {False, True})
    assert not (core_path.parent / "p1-recovery-stop.json").exists()
    assert app.core.sql("SELECT count(*) FROM ref_coverage_proofs")[0][0] == 1
    assert repository != injected


class CallerCancelled(BaseException):
    pass


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("mode", ["require", "charge"])
@pytest.mark.parametrize("kind", ["sqlite", "core", "json", "cancel"])
def test_group_callback_failure_rolls_back_without_false_corruption(
    acquisition, external, mode, kind
):
    app, _, _, _, _, core_path, _ = acquisition
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
        "core": CoreFailure("AUTHORITATIVE_CORRUPTION", "caller", "caller error"),
        "json": json.JSONDecodeError("caller JSON error", "x", 0),
        "cancel": CallerCancelled("caller cancellation"),
    }[kind]
    if kind == "sqlite":
        failure.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
    triggered = []

    with group_core(app, core_path, external) as core:

        class Failing(UnlimitedWorkBudget):
            def probe(self):
                # Raise only after the unit has inserted its first object.
                # Reading nominal metadata does not require byte authority.
                if (
                    core._db.in_transaction
                    and core._db.execute(
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
            core.admit_notes_mapping_group(group, Failing())
        assert caught.value is failure and triggered == [True]
        core.ensure_available()
        assert not core.sql("SELECT 1 FROM git_objects WHERE object_oid=?", (target,))
        assert core.sql("SELECT count(*) FROM notes_mapping_groups")[0][0] == 1
        assert core._db.in_transaction is external
        core.admit_notes_mapping_group(group, app.work)
        core.admit_notes_mapping_group(group)
        assert core.sql("SELECT count(*) FROM notes_mapping_groups")[0][0] == 2

    assert not (core_path.parent / "p1-recovery-stop.json").exists()
    app.core.ensure_available()


def test_group_admission_budget_failure_keeps_existing_facts(acquisition):
    app, _, _, _, _, core_path, _ = acquisition
    original = reported_group(acquisition)
    group = replace(
        original,
        provenance=replace(original.provenance, coordinate="budget-limited-group"),
    )
    with pytest.raises(CoreFailure) as caught:
        app.core.admit_notes_mapping_group(
            group, UnlimitedWorkBudget(work_limits={"input_bytes": 1})
        )
    assert caught.value.code == "BUDGET"
    assert app.core.sql("SELECT count(*) FROM notes_mapping_groups")[0][0] == 1
    app.core.admit_notes_mapping_group(group, app.work)
    assert app.core.sql("SELECT count(*) FROM notes_mapping_groups")[0][0] == 2
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_group_admission_still_stops_on_damaged_stored_subject(acquisition):
    app, _, _, _, _, core_path, _ = acquisition
    group = reported_group(acquisition)
    with closing(connect(core_path, "core")) as db:
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
    with pytest.raises(CoreFailure) as caught:
        app.core.admit_notes_mapping_group(group, app.work)
    assert caught.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (core_path.parent / "p1-recovery-stop.json").exists()
