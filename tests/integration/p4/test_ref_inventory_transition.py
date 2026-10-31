"""Claim-specific inventory reports and independently verified Coverage."""

import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.notes import NotesProgress
from repo_catalog.adapters.sqlite.p1_coordination import NotesWorkBudget
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.notes import NotesAcquisition
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.p1_coordination import NotesLimits, RequestIdentity
from repo_catalog.domain.p1_core import CoreCoverageScope, CoreFailure, Provenance
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ports.notes import request_scope
from repo_catalog.domain.recovery import BackupScope
from repo_catalog.domain.ref_coverage import REF_NOTES_INVENTORY
from repo_catalog.domain.ref_observation import (
    RefAbsenceEvidence,
    account_notes_group_comparison,
    account_provenance_comparison,
)
from tests.integration.p4 import conftest as fixtures
from tests.integration.p4.test_ref_observation_i2 import discover
from tests.integration.p5.conftest import init_catalog_stores

acquisition = fixtures.acquisition


@pytest.mark.parametrize("empty", [False, True])
def test_inventory_report_and_receiver_proof_remain_claim_specific(
    acquisition, monkeypatch, empty
):
    app, path, fmt, repository, origin, core_path, _ = acquisition
    capture, target, _ = fixtures.fixture_note(acquisition, fanout=1, commit=not empty)
    if empty:
        root = fixtures.write(path, fmt, "tree", b"")
        fixtures.git(path, "update-ref", capture.ref, root.object_oid)
    events = discover(app, repository, origin, str(uuid4())).enumerations
    first_claim, second_claim = (event.links[0].claim for event in events)
    reported = app.inventory_ref(first_claim).group
    assert reported.status == ("known_empty" if empty else "complete")

    query = ProductionQueryService(core_path.parent, mode="core_only")
    initial = query.list_ref_notes_inventories(first_claim, app.work)
    assert initial.coverage.state == "unknown"
    assert [item.group for item in initial.groups] == [reported]
    assert not initial.groups[0].current_verified
    assert not query.list_ref_notes_inventories(second_claim, app.work).groups

    checked = app.verify_ref_inventory(reported)
    assert checked.verified and checked.coverage_claim is not None
    assert checked.verification_provenance.qualification == "receiver_intrinsic"
    assert checked.coverage_claim.observed_at_us != events[0].event.observed_at_us
    result = query.list_ref_notes_inventories(first_claim, app.work)
    assert result.coverage.state == "complete"
    assert result.coverage.known_empty is empty
    assert result.groups[0].current_verifications == (checked.verification_provenance,)
    assert not query.list_ref_notes_inventories(second_claim, app.work).groups
    monkeypatch.setattr(
        app.source, "metadata", lambda *_: pytest.fail("replay reread Git")
    )
    assert app.verify_ref_inventory(reported) == checked
    if not empty:
        assert not app.core.sql("SELECT 1 FROM ref_retained_notes")
        assert target.object_oid in repr(reported.members)


def test_later_partial_does_not_fall_back_to_verified_complete(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    verified = app.verify_ref_inventory(group)
    assert verified.verified
    later = CoverageClaim(
        verified.coverage_claim.scope,
        verified.coverage_claim.observed_at_us + 1,
        "partial",
    )
    app.core.admit_coverage(later)
    projection = ProductionQueryService(
        core_path.parent, mode="core_only"
    ).list_ref_notes_inventories(claim, app.work)
    assert projection.coverage.state == "partial"
    assert projection.groups[0].group == group
    assert not projection.groups[0].current_verified
    assert app.verify_ref_inventory(group) == verified
    assert projection.coverage.observed_at_us == later.observed_at_us


def test_competing_claims_keep_separate_groups_and_no_winner(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition, body=b"first")
    first = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group1 = app.inventory_ref(first).group
    proof1 = app.verify_ref_inventory(group1)
    second_capture, _, _ = fixtures.fixture_note(acquisition, body=b"second")
    second = replace(
        first,
        provenance=replace(first.provenance, coordinate="independent-result"),
        root_object_oid=second_capture.root,
    )
    app.core.admit_ref_observation_claim(second)
    group2 = app.inventory_ref(second).group
    query = ProductionQueryService(core_path.parent, mode="core_only")
    before = query.list_ref_notes_inventories(first, app.work)
    assert before.coverage.state == "conflict"
    assert before.groups[0].current_verified
    other_before = query.list_ref_notes_inventories(second, app.work)
    assert other_before.coverage.state == "conflict"
    assert not other_before.groups[0].current_verified
    proof2 = app.verify_ref_inventory(group2)
    assert (
        proof2.verified
        and proof1.verification_provenance != proof2.verification_provenance
    )
    first_after = query.list_ref_notes_inventories(first, app.work)
    second_after = query.list_ref_notes_inventories(second, app.work)
    assert first_after.coverage.state == second_after.coverage.state == "conflict"
    assert first_after.groups[0].group == group1
    assert not first_after.groups[0].current_verified
    assert second_after.groups[0].group == group2
    assert second_after.groups[0].current_verified


def test_shared_root_does_not_share_claim_verification(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    first = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    second = replace(
        first,
        provenance=replace(first.provenance, coordinate="same-root-result"),
    )
    app.core.admit_ref_observation_claim(second)
    group1 = app.inventory_ref(first).group
    group2 = app.inventory_ref(second).group
    assert (
        group1.members == group2.members
        and first.root_object_oid == second.root_object_oid
    )
    assert app.verify_ref_inventory(group1).verified
    query = ProductionQueryService(core_path.parent, mode="core_only")
    assert query.list_ref_notes_inventories(first, app.work).groups[0].current_verified
    assert (
        not query.list_ref_notes_inventories(second, app.work)
        .groups[0]
        .current_verified
    )
    assert app.verify_ref_inventory(group2).verified
    assert query.list_ref_notes_inventories(second, app.work).groups[0].current_verified


def test_absent_ref_has_no_invented_inventory(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    result = discover(
        app, repository, origin, str(uuid4()), ("refs/notes/no-such-ref",)
    )
    absence = next(
        link.claim
        for event in result.enumerations
        for link in event.links
        if link.claim.presence_state == "absent"
    )
    view = ProductionQueryService(
        core_path.parent, mode="auto"
    ).list_ref_notes_inventories(absence, app.work)
    assert absence.root_object_oid is None and not view.groups
    assert view.coverage.state == "unknown"


def test_paired_and_core_only_queries_preserve_scope(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    assert app.verify_ref_inventory(group).verified
    _, instance = app.core.catalog_identity()
    initialize(core_path.parent / "context.sqlite3", "context", repository, instance)
    paired = ProductionQueryService(core_path.parent, mode="auto")
    core_only = ProductionQueryService(core_path.parent, mode="core_only")
    assert paired.detect_mode() == "paired"
    assert core_only.detect_mode() == "core_only"
    assert paired.list_ref_notes_inventories(
        claim, app.work
    ) == core_only.list_ref_notes_inventories(claim, app.work)


def test_proof_writer_callback_cannot_reenter_or_fake_corruption(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    verified = app.verify_ref_inventory(group)
    proof = app.core.ref_coverage_proofs(verified.coverage_claim, app.work)[0]
    failure = sqlite3.DatabaseError("caller budget callback")
    failure.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
    attempts = []

    class Reentrant(UnlimitedWorkBudget):
        def require(self, unit, amount=1):
            if app.core._db.in_transaction and app.core._work_callback_depth:
                for action in (
                    lambda: app.core.sql(
                        "SELECT structures_json FROM ref_coverage_proofs"
                    ),
                    lambda: app.core.admit_repository(repository),
                    lambda: app.core._db.execute(
                        "SELECT structures_json FROM ref_coverage_proofs"
                    ).fetchall(),
                ):
                    with pytest.raises(sqlite3.DatabaseError):
                        action()
                    attempts.append(1)
                raise failure
            super().require(unit, amount)

    with pytest.raises(sqlite3.DatabaseError) as caught:
        app.core.admit_ref_coverage_proof(proof, Reentrant())
    assert caught.value is failure and len(attempts) == 3
    assert not (core_path.parent / "p1-recovery-stop.json").exists()
    app.core.ensure_available()
    app.core.admit_ref_coverage_proof(proof, app.work)

    class Probe(UnlimitedWorkBudget):
        blocked = 0

        def require(self, unit, amount=1):
            with pytest.raises(sqlite3.DatabaseError):
                app.core.sql("SELECT structures_json FROM ref_coverage_proofs")
            self.blocked += 1
            super().require(unit, amount)

    probe = Probe()
    assert (
        app.core.ref_notes_inventory_projection(claim, probe).groups[0].current_verified
    )
    assert probe.blocked > 0


def test_group_limits_refuse_without_stopping_healthy_catalog(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    _, target, note = fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    first = app.inventory_ref(claim).group
    extra_target = replace(target, object_oid="b" * len(target.object_oid))
    app.core.admit_object(extra_target)
    second = replace(
        first,
        members=(
            first.members[0],
            (extra_target.object_oid, note.object_oid, extra_target.object_oid),
        ),
        provenance=Provenance("other", "other-observation", "whole", "test", "1"),
    )
    app.core.admit_notes_mapping_group(second, app.work)
    with pytest.raises(CoreFailure) as too_many:
        app.core.ref_notes_inventory_projection(claim, app.work, max_groups=1)
    assert too_many.value.code == "QUERY_BUDGET"
    with pytest.raises(CoreFailure) as too_many_members:
        app.core.ref_notes_inventory_projection(claim, app.work, max_members=1)
    assert too_many_members.value.code == "QUERY_BUDGET"
    assert len(app.core.ref_notes_inventory_projection(claim, app.work).groups) == 2
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_partial_group_never_becomes_receiver_verified(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    complete_report = app.inventory_ref(claim).group
    partial = replace(
        complete_report,
        status="partial",
        provenance=Provenance("external", "partial", "inventory", "test", "1"),
    )
    app.core.admit_notes_mapping_group(partial, app.work)
    result = app.verify_ref_inventory(partial)
    assert not result.verified and result.failure_code == "NOTES_INVENTORY"
    view = app.core.ref_notes_inventory_projection(claim, app.work)
    assert view.coverage.state == "unknown"
    assert all(not item.current_verified for item in view.groups)
    assert not app.core.sql("SELECT 1 FROM ref_coverage_proofs")
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_group_comparison_accounts_for_non_ascii_bytes(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    long_origin = replace(
        group, provenance=replace(group.provenance, source="日本" * 4000)
    )
    budget = UnlimitedWorkBudget(work_limits={"input_bytes": 40_000})
    with pytest.raises(CoreFailure) as error:
        account_notes_group_comparison(long_origin, long_origin, budget)
    assert error.value.code == "BUDGET"
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_provenance_comparison_accounts_for_non_ascii_bytes(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    provenance = replace(group.provenance, source="日本" * 4000)
    budget = UnlimitedWorkBudget(work_limits={"input_bytes": 40_000})
    with pytest.raises(CoreFailure) as error:
        account_provenance_comparison(provenance, provenance, budget)
    assert error.value.code == "BUDGET"
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_long_provenance_is_not_scanned_before_budget_reservation(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )

    class CountedText(str):
        visits = 0

        def __iter__(self):
            for char in super().__iter__():
                self.visits += 1
                yield char

    source = CountedText("x" * 65_536)
    incoming = replace(claim, provenance=replace(claim.provenance, source=source))
    work = UnlimitedWorkBudget(work_limits={"input_bytes": len(source) + 4096})
    with pytest.raises(CoreFailure) as error:
        app.core.ref_notes_inventory_projection(incoming, work)
    assert error.value.code in ("BUDGET", "QUERY_BUDGET")
    assert source.visits == 0
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("kind", ["mapping-path", "absence"])
def test_variable_json_fields_reserve_character_walk_before_scanning(acquisition, kind):
    app, _, _, _, _, core_path, _ = acquisition

    class CountedText(str):
        visits = 0

        def __iter__(self):
            for char in super().__iter__():
                self.visits += 1
                yield char

    value = CountedText("x" * 65_536)
    work = UnlimitedWorkBudget(work_limits={"input_bytes": 1024})
    with pytest.raises(CoreFailure) as error:
        if kind == "mapping-path":
            app.core._meter_mapping_path_encoding(work, value, 100_000)
        else:
            evidence = RefAbsenceEvidence(
                "source", "scope", b"refs/notes/a", "lookup", value
            )
            app.core._meter_absence_encoding(work, evidence, 100_000)
    assert error.value.code in ("BUDGET", "QUERY_BUDGET")
    assert value.visits == 0
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_lost_verification_pin_causes_new_check_without_rebinding(
    acquisition, monkeypatch
):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    original_save = app.progress.save_once_bounded
    calls = []

    def fail_after_proof(scope, value, maximum, *, encoded):
        if "p4-ref-inventory-check" in scope and not calls:
            calls.append(1)
            raise OSError("synthetic lost acknowledgement")
        return original_save(scope, value, maximum, encoded=encoded)

    monkeypatch.setattr(app.progress, "save_once_bounded", fail_after_proof)
    with pytest.raises(OSError, match="lost acknowledgement"):
        app.verify_ref_inventory(group)
    assert len(app.core.sql("SELECT 1 FROM ref_coverage_proofs")) == 1
    retried = app.verify_ref_inventory(group)
    assert retried.verified
    assert len(app.core.sql("SELECT 1 FROM ref_coverage_proofs")) == 2
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_progress_cannot_rebind_another_requests_verification(acquisition, monkeypatch):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    first = app.verify_ref_inventory(group)
    ledger = app.work.ledger
    request = RequestIdentity(origin, str(uuid4()))
    _, instance = app.core.catalog_identity()
    ledger.new_request(
        request,
        request_scope(repository, instance, "local-test", app.source.scope),
        NotesLimits().work_limits(),
    )
    attempt = str(uuid4())
    ledger.attempt(request, attempt)
    second_work = NotesWorkBudget(ledger, request, attempt, NotesLimits())
    progress = NotesProgress(second_work)
    second = NotesAcquisition(
        app.core, app.source, second_work, progress, source_attribution="local-test"
    )
    original = progress.load_bounded

    def rebound(scope, maximum):
        if "p4-ref-inventory-check" in scope:
            return {
                "verification_uuidv7": first.verification_provenance.observation,
                "observed_at_us": first.coverage_claim.observed_at_us,
            }
        return original(scope, maximum)

    monkeypatch.setattr(progress, "load_bounded", rebound)
    with pytest.raises(CoreFailure) as error:
        second.verify_ref_inventory(group)
    assert error.value.code == "CONTINUATION_UNAVAILABLE"
    assert not (core_path.parent / "p1-recovery-stop.json").exists()
    monkeypatch.setattr(progress, "load_bounded", original)
    later = second.verify_ref_inventory(group)
    assert later.verified
    assert later.verification_provenance != first.verification_provenance
    assert (
        later.verification_provenance.coordinate
        != first.verification_provenance.coordinate
    )
    assert (
        app.core.ref_coverage_proofs(first.coverage_claim, app.work)[0].group == group
    )


def test_proof_writer_budget_failure_rolls_back_without_false_completion(
    acquisition, monkeypatch
):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    original = app.core.admit_ref_coverage_proof

    class LimitedAtWrite:
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def require(self, unit, amount=1):
            if app.core._db.in_transaction:
                raise CoreFailure("BUDGET", unit, "synthetic proof writer limit")
            self.inner.require(unit, amount)

        def charge(self, unit, amount):
            self.inner.charge(unit, amount)

    monkeypatch.setattr(
        app.core,
        "admit_ref_coverage_proof",
        lambda proof, work: original(proof, LimitedAtWrite(work)),
    )
    with pytest.raises(CoreFailure) as error:
        app.verify_ref_inventory(group)
    assert error.value.code == "BUDGET"
    view = app.core.ref_notes_inventory_projection(claim, app.work)
    assert view.coverage.state == "unknown" and not view.groups[0].current_verified
    assert not app.core.sql("SELECT 1 FROM ref_coverage_proofs")
    assert not (core_path.parent / "p1-recovery-stop.json").exists()
    monkeypatch.setattr(app.core, "admit_ref_coverage_proof", original)
    assert app.verify_ref_inventory(group).verified


def test_receiver_inventory_proof_survives_exchange_and_backup(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition, fanout=1, commit=True)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    verified = app.verify_ref_inventory(group)
    selection = ExchangeSelectionScope(
        all_selected=True,
        include_context=False,
        include_retained_bytes=False,
        object_oids=(),
        ref_observation_keys=(claim.ref_observation_key,),
    )
    package = ExchangeService(
        core_path.parent, operational=core_path.parent
    ).export_package(selection=selection)
    assert len(package.core["ref_coverage_proofs"]) == 1
    assert not package.core["ref_retained_notes"]
    outside = tmp_path.parent / (tmp_path.name + "-inventory-exchange")
    outside.mkdir()
    receiver = outside / "receiver"
    init_catalog_stores(
        receiver, repository_uuidv4=repository, stores=("core", "operational")
    )
    ExchangeService(receiver, operational=receiver).import_package(
        package, new_request=True, permitted_repository_uuidv4s=(repository,)
    )
    query = ProductionQueryService(receiver, mode="core_only")
    view = query.list_ref_notes_inventories(claim, app.work)
    assert view.coverage.state == "complete"
    assert view.groups[0].group == group and view.groups[0].current_verified
    assert verified.verification_provenance in view.groups[0].current_verifications
    assert len(view.groups[0].current_verifications) == 2

    backup = outside / "backup"
    adapter = SQLiteRecoveryAdapter()
    adapter.create_consistent_backup(receiver, backup, BackupScope.GIT_ONLY)
    restored = outside / "restored"
    adapter.restore_backup(backup, restored, repository)
    after = ProductionQueryService(restored, mode="auto").list_ref_notes_inventories(
        claim, app.work
    )
    assert after == view


def test_forged_group_and_source_failure_never_prove_completeness(
    acquisition, monkeypatch
):
    app, _, fmt, repository, origin, core_path, _ = acquisition
    _, target, _ = fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    original = app.inventory_ref(claim).group
    fake_note = replace(target, object_oid="b" * len(target.object_oid))
    app.core.admit_object(fake_note)
    forged = replace(
        original,
        members=((target.object_oid, fake_note.object_oid, target.object_oid),),
        provenance=Provenance("external", "different", "report", "test", "1"),
    )
    app.core.admit_notes_mapping_group(forged, app.work)
    mismatch = app.verify_ref_inventory(forged)
    assert not mismatch.verified and mismatch.failure_code == "NOTES_INVENTORY_MISMATCH"
    monkeypatch.setattr(
        app.source,
        "metadata",
        lambda oid, _work: (_ for _ in ()).throw(
            CoreFailure("OBJECT_UNAVAILABLE", oid, "missing")
        ),
    )
    failed = app.verify_ref_inventory(original)
    assert not failed.verified and failed.failure_code == "OBJECT_UNAVAILABLE"
    view = ProductionQueryService(
        core_path.parent, mode="core_only"
    ).list_ref_notes_inventories(claim, app.work)
    assert view.coverage.state == "unknown"
    assert all(not item.current_verified for item in view.groups)
    assert not (core_path.parent / "p1-recovery-stop.json").exists()

    unadmitted = replace(original, status="partial")
    with pytest.raises(CoreFailure) as missing:
        app.verify_ref_inventory(unadmitted)
    assert missing.value.code == "MISSING_DEPENDENCY"
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_inventory_limit_and_callback_error_do_not_stop_catalog(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    query = ProductionQueryService(core_path.parent, mode="core_only")
    with pytest.raises(CoreFailure) as limited:
        query.list_ref_notes_inventories(
            claim, UnlimitedWorkBudget(work_limits={"input_bytes": 32})
        )
    assert limited.value.code in ("BUDGET", "QUERY_BUDGET")
    callback_error = json.JSONDecodeError("callback only", "x", 0)

    class Failing(UnlimitedWorkBudget):
        def require(self, unit, amount=1):
            raise callback_error

    with pytest.raises(json.JSONDecodeError) as error:
        query.list_ref_notes_inventories(claim, Failing())
    assert error.value is callback_error
    scope = CoreCoverageScope(
        "ref_observation", (*claim.ref_observation_key.key, REF_NOTES_INVENTORY)
    )
    with pytest.raises(json.JSONDecodeError) as direct:
        app.core.coverage(scope, Failing())
    assert direct.value is callback_error
    with pytest.raises(json.JSONDecodeError) as query_error:
        query.get_core_coverage(scope, work=Failing())
    assert query_error.value is callback_error
    assert (
        app.core.ref_notes_inventory_projection(claim, app.work).groups[0].group
        == group
    )
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_damaged_inventory_metadata_stops_catalog(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.inventory_ref(claim)
    with connect(core_path, "core") as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_notes_mapping_groups_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_notes_mapping_groups_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE notes_mapping_groups SET group_scope=CAST(x'80' AS TEXT)")
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.execute(trigger)
        db.commit()
    with pytest.raises(CoreFailure) as error:
        ProductionQueryService(
            core_path.parent, mode="core_only"
        ).list_ref_notes_inventories(claim, app.work)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (core_path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        app.core.ensure_available()
    assert stopped.value.code == "RECOVERY_STOP"


def test_noncanonical_unicode_group_is_bounded_before_reencoding(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    target, note, _ = group.members[0]
    bad = json.dumps(
        [[target, note, "😀" * 50_000]], ensure_ascii=False, separators=(",", ":")
    )
    with connect(core_path, "core") as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_notes_mapping_groups_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_notes_mapping_groups_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE notes_mapping_groups SET membership=?", (bad,))
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.execute(trigger)
        db.commit()
    small = UnlimitedWorkBudget(work_limits={"input_bytes": 1_000_000})
    with pytest.raises(CoreFailure) as limited:
        app.core.ref_notes_inventory_projection(claim, small, max_bytes=1_000_000)
    assert limited.value.code in ("BUDGET", "QUERY_BUDGET")
    assert not (core_path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as corrupt:
        app.core.ref_notes_inventory_projection(claim, UnlimitedWorkBudget())
    assert corrupt.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (core_path.parent / "p1-recovery-stop.json").exists()


def test_inventory_query_detects_damaged_stored_receiver_proof(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    assert app.verify_ref_inventory(group).verified
    with connect(core_path, "core") as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_coverage_proofs_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_coverage_proofs_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE ref_coverage_proofs SET structures_json='[]'")
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.execute(trigger)
        db.commit()
    with pytest.raises(CoreFailure) as error:
        ProductionQueryService(
            core_path.parent, mode="core_only"
        ).list_ref_notes_inventories(claim, app.work)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (core_path.parent / "p1-recovery-stop.json").exists()
