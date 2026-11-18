"""P5 orchestration of independently checked RefObservation inventories."""

import json
import os
import sqlite3
import subprocess
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.adapters.sqlite.acquisition import (
    InMemoryNotesProgress,
    UnlimitedWorkBudget,
)
from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.application.acquisition import (
    GitAcquisition,
    PairedAcquisitionCoordinator,
)
from repo_catalog.application.notes import NotesAcquisition
from repo_catalog.domain.acquisition import (
    GitMetadataInput,
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
)
from repo_catalog.domain.p1_coordination import AdmissionFailure, PairAdmission
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.p1_repository import RepositoryFailure, encode
from repo_catalog.domain.ref_observation import new_uuid7
from tests.integration.p4 import conftest as fixtures
from tests.integration.p4.test_ref_observation_i2 import discover

acquisition = fixtures.acquisition


def request_for(case, *, metadata=False):
    _, path, fmt, repository, origin, *_ = case
    spec = NotesAcquisitionSpec(
        discover_notes=True,
        acquire_inventories=True,
        nominated_refs=("refs/notes/not-present",),
    )
    shared = dict(
        repository_uuidv4=repository,
        capture_origin_uuidv4=origin,
        capture_uuidv4=str(uuid4()),
        source_attribution="local-test",
        observed_at_us=1_700_000_000_000_000,
        notes=spec,
    )
    if metadata:
        return GitMetadataInput(object_format=fmt, **shared)
    return GitNativeAcquisitionRequest(include_refs=False, **shared)


def enable_context(case):
    app, _, _, _, _, repository_path, _ = case
    repository, instance = app.repository_store.catalog_identity()
    initialize(
        repository_path.parent / "context.sqlite3", "context", repository, instance
    )


def run_request(case, request, *, paired=False, metadata=False, new_request=True, **kw):
    _, path, _, _, _, repository_path, _ = case
    source = GitNativeSource(path)
    if paired:
        coord = PairedAcquisitionCoordinator(repository_path.parent)
        args = (
            {"git_input": request, "notes_source": GitNotesSource(source)}
            if metadata
            else {"git_source": source, "git_request": request}
        )
        result = coord.admit_paired(new_request=new_request, **args, **kw)
        assert result.admission == PairAdmission(True, True)
        return result.git_report
    app = GitAcquisition(repository_path, operational=repository_path.parent)
    if metadata:
        return app.acquire_metadata_only(
            request, notes_source=GitNotesSource(source), new_request=new_request, **kw
        )
    return app.acquire_from_native(source, request, new_request=new_request, **kw)


def budget_spent(case, request):
    op_path = case[-1]
    with closing(connect(op_path, "operational")) as db:
        return dict(
            db.execute(
                "SELECT work_kind, spent_or_reserved FROM request_budgets "
                "WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                (request.capture_origin_uuidv4, request.capture_uuidv4),
            ).fetchall()
        )


@pytest.mark.parametrize("metadata", [False, True], ids=["native", "metadata"])
@pytest.mark.parametrize("paired", [False, True], ids=["repository", "paired"])
def test_inventory_wiring_keeps_original_claims_and_receiver_checks(
    acquisition, metadata, paired
):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition, fanout=1, commit=metadata)
    if paired:
        enable_context(acquisition)
    request = request_for(acquisition, metadata=metadata)
    first = run_request(acquisition, request, paired=paired, metadata=metadata)
    assert first.status == "complete"
    assert first.ref_notes_inventories
    assert not app.repository_store.sql("SELECT 1 FROM ref_retained_notes")
    assert len(first.ref_inventory_verifications) == len(first.ref_notes_inventories)
    assert len(first.ref_inventory_projections) == len(first.ref_notes_inventories)
    assert all(v.verified for v in first.ref_inventory_verifications)
    assert all(
        v.group == reported.group
        for v, reported in zip(
            first.ref_inventory_verifications, first.ref_notes_inventories, strict=True
        )
    )
    assert any(
        link.claim.presence_state == "absent" and link.claim.root_object_oid is None
        for discovery in first.notes_discoveries
        for enumeration in discovery.enumerations
        for link in enumeration.links
    )
    for checked in first.ref_inventory_verifications:
        projection = app.repository_store.ref_notes_inventory_projection(
            checked.group.ref_claim, app.work
        )
        assert any(
            view.current_verified and view.group == checked.group
            for view in projection.groups
        )
    before = budget_spent(acquisition, request)
    again = run_request(
        acquisition, request, paired=paired, metadata=metadata, new_request=False
    )
    after = budget_spent(acquisition, request)
    assert again.ref_inventory_verifications == first.ref_inventory_verifications
    assert again.ref_notes_inventories == first.ref_notes_inventories
    assert after["metadata_units"] > before["metadata_units"]
    assert after["verification_bytes"] > before["verification_bytes"]
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("paired", [False, True], ids=["repository", "paired"])
@pytest.mark.parametrize("kind", ["later-partial", "conflicting-claim"])
def test_replay_reports_current_coverage_without_losing_historical_proof(
    acquisition, paired, kind
):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    if paired:
        enable_context(acquisition)
    request = request_for(acquisition)
    first = run_request(acquisition, request, paired=paired)
    original = first.ref_inventory_verifications[0]
    if kind == "later-partial":
        app.repository_store.admit_coverage(
            CoverageClaim(
                original.coverage_claim.scope,
                original.coverage_claim.observed_at_us + 1,
                "partial",
            )
        )
    else:
        other_root = fixtures.fixture_note(acquisition, body=b"other root")[0].root
        claim = original.group.ref_claim
        competing = replace(
            claim,
            provenance=replace(claim.provenance, coordinate="independent-conflict"),
            root_object_oid=other_root,
        )
        app.repository_store.admit_ref_observation_claim(competing)
    replay = run_request(acquisition, request, paired=paired, new_request=False)
    assert replay.status == "partial"
    assert replay.ref_inventory_verifications[0] == original
    assert replay.ref_inventory_projections[0].coverage.state == (
        "partial" if kind == "later-partial" else "conflict"
    )
    assert replay.failure_code == (
        "REF_INVENTORY_NOT_CURRENT"
        if kind == "later-partial"
        else "REF_INVENTORY_CONFLICT"
    )
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


def test_aggregate_coverage_uses_one_repository_snapshot(acquisition, monkeypatch):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    request = request_for(acquisition)
    first = run_request(acquisition, request)
    assert len(first.ref_inventory_verifications) >= 2
    second_claim = first.ref_inventory_verifications[1].coverage_claim
    later = CoverageClaim(
        second_claim.scope, second_claim.observed_at_us + 1, "partial"
    )
    original = GitRepositoryStore.ref_notes_inventory_projection
    changed = []

    def interleave(repository_store, *args, **kwargs):
        in_outer_snapshot = repository_store._db.in_transaction
        projection = original(repository_store, *args, **kwargs)
        if in_outer_snapshot and not changed:
            with closing(GitRepositoryStore(repository_path)) as writer:
                writer.admit_coverage(later)
            changed.append(True)
        return projection

    monkeypatch.setattr(
        GitRepositoryStore, "ref_notes_inventory_projection", interleave
    )
    replay = run_request(acquisition, request, new_request=False)
    assert changed
    assert replay.status == "complete"
    assert all(p.coverage.state == "complete" for p in replay.ref_inventory_projections)
    assert app.repository_store.coverage(later.scope, app.work).state == "partial"


@pytest.mark.parametrize("mode", ["reentry", "corrupt-shaped"])
def test_aggregate_snapshot_guards_work_callback(acquisition, monkeypatch, mode):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    request = request_for(acquisition)
    original = GitRepositoryStore.ref_notes_inventory_projections
    sentinel = sqlite3.DatabaseError("synthetic callback failure")
    sentinel.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
    attempted = []

    def intercept(repository_store, groups, work, **kwargs):
        class CallbackWork:
            def __getattr__(self, name):
                return getattr(work, name)

            def require(self, unit, amount=1):
                if not attempted:
                    attempted.append(True)
                    if mode == "corrupt-shaped":
                        raise sentinel
                    with pytest.raises(sqlite3.DatabaseError):
                        repository_store.sql("SELECT 1")
                    with pytest.raises(sqlite3.DatabaseError):
                        repository_store._db.execute(
                            "SELECT body FROM ref_retained_notes"
                        ).fetchall()
                return work.require(unit, amount)

            def charge(self, unit, amount):
                return work.charge(unit, amount)

        return original(repository_store, groups, CallbackWork(), **kwargs)

    monkeypatch.setattr(
        GitRepositoryStore, "ref_notes_inventory_projections", intercept
    )
    if mode == "corrupt-shaped":
        with pytest.raises(sqlite3.DatabaseError) as error:
            run_request(acquisition, request)
        assert error.value is sentinel
    else:
        report = run_request(acquisition, request)
        assert report.status == "complete"
    assert attempted
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()
    app.repository_store.ensure_available()


def test_aggregate_snapshot_honors_finite_limits(acquisition):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    report = run_request(acquisition, request_for(acquisition))
    groups = tuple(item.group for item in report.ref_inventory_verifications)
    assert len(groups) >= 2
    checked = app.repository_store.ref_notes_inventory_projections(groups, app.work)
    assert len(checked) == len(groups) and all(current for _, current in checked)
    with pytest.raises(RepositoryFailure) as limit:
        app.repository_store.ref_notes_inventory_projections(
            groups, app.work, max_items=1
        )
    assert limit.value.code == "QUERY_BUDGET"
    with pytest.raises(RepositoryFailure) as budget:
        app.repository_store.ref_notes_inventory_projections(
            groups, UnlimitedWorkBudget(work_limits={"input_bytes": 1})
        )
    assert budget.value.code in ("BUDGET", "QUERY_BUDGET")
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()
    app.repository_store.ensure_available()


@pytest.mark.parametrize("paired", [False, True], ids=["repository", "paired"])
def test_completion_refuses_stop_after_aggregate_snapshot(
    acquisition, monkeypatch, paired
):
    _, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    if paired:
        enable_context(acquisition)
    original = GitRepositoryStore.ref_notes_inventory_projections

    def stop_after(repository_store, groups, work, **kwargs):
        views = original(repository_store, groups, work, **kwargs)
        persist_catalog_stop(repository_path.parent, "synthetic concurrent stop")
        return views

    monkeypatch.setattr(
        GitRepositoryStore, "ref_notes_inventory_projections", stop_after
    )
    with pytest.raises(RepositoryFailure) as error:
        run_request(acquisition, request_for(acquisition), paired=paired)
    assert error.value.code == "RECOVERY_STOP"
    assert (repository_path.parent / "p1-recovery-stop.json").exists()


def test_completion_without_inventory_also_observes_stop(acquisition, monkeypatch):
    _, _, _, _, _, repository_path, _ = acquisition
    original = GitRepositoryStore.admit_coverage

    def stop_after(repository_store, *args, **kwargs):
        result = original(repository_store, *args, **kwargs)
        persist_catalog_stop(repository_path.parent, "synthetic concurrent stop")
        return result

    monkeypatch.setattr(GitRepositoryStore, "admit_coverage", stop_after)
    request = replace(request_for(acquisition), notes=None)
    with pytest.raises(RepositoryFailure) as error:
        run_request(acquisition, request)
    assert error.value.code == "RECOVERY_STOP"
    assert (repository_path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("shape", ["empty", "malformed", "non-utf8"])
def test_inventory_wiring_preserves_exact_source_scope(acquisition, shape):
    app, path, fmt, _, _, repository_path, _ = acquisition
    capture, _, note = fixtures.fixture_note(acquisition)
    if shape == "empty":
        root = fixtures.write(path, fmt, "tree", b"")
        fixtures.git(path, "update-ref", capture.ref, root.object_oid)
    elif shape == "malformed":
        root = fixtures.write(
            path, fmt, "tree", fixtures.entry(b"100644", b"not-notes", note)
        )
        fixtures.git(path, "update-ref", capture.ref, root.object_oid)
    else:
        raw = b"refs/notes/invalid-\xff"
        subprocess.run(
            [
                b"git",
                b"-C",
                os.fsencode(path),
                b"update-ref",
                raw,
                capture.root.object_oid.encode(),
            ],
            check=True,
            capture_output=True,
        )
    report = run_request(acquisition, request_for(acquisition))
    if shape == "empty":
        assert report.ref_inventory_verifications
        assert all(
            v.verified and v.group.status == "known_empty"
            for v in report.ref_inventory_verifications
        )
    elif shape == "malformed":
        assert report.status == "partial"
        assert report.ref_inventory_verifications
        assert all(
            not v.verified and v.failure_code == "NOTES_INVENTORY"
            for v in report.ref_inventory_verifications
        )
        assert not app.repository_store.sql("SELECT 1 FROM ref_coverage_proofs")
    else:
        claims = [
            link
            for discovery in report.notes_discoveries
            for event in discovery.enumerations
            for link in event.links
            if link.observation.ref_name_bytes == raw
        ]
        assert claims
        verified_keys = {
            v.group.ref_claim.ref_observation_key
            for v in report.ref_inventory_verifications
            if v.verified
        }
        assert all(link.claim.ref_observation_key in verified_keys for link in claims)
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("point", ["before_repository_commit", "during_context"])
def test_paired_commit_failure_cannot_pin_a_future_proof(acquisition, point):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    enable_context(acquisition)
    request = request_for(acquisition)

    def cut(actual):
        if actual == point:
            raise RuntimeError("synthetic paired cut")

    with pytest.raises(AdmissionFailure) as error:
        run_request(acquisition, request, paired=True, cut=cut)
    assert error.value.outcome == PairAdmission(point == "during_context", False)
    assert not app.repository_store.sql("SELECT 1 FROM ref_coverage_proofs")
    with closing(connect(acquisition[-1], "operational")) as db:
        pins = db.execute(
            "SELECT continuation_scope_json FROM request_continuations "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            (request.capture_origin_uuidv4, request.capture_uuidv4),
        ).fetchall()
    assert not any("p4-ref-inventory-check" in row[0] for row in pins)
    retried = run_request(acquisition, request, paired=True, new_request=False)
    assert retried.ref_inventory_verifications
    assert all(item.verified for item in retried.ref_inventory_verifications)
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("paired", [False, True], ids=["repository", "paired"])
def test_failed_receiver_rewalk_remains_reported_without_proof(
    acquisition, monkeypatch, paired
):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    if paired:
        enable_context(acquisition)
    request = request_for(acquisition)
    original = NotesAcquisition.verify_ref_inventory

    def unavailable(self, group):
        def fail(oid, work):
            raise RepositoryFailure("OBJECT_UNAVAILABLE", oid, "synthetic source loss")

        monkeypatch.setattr(self.source, "metadata", fail)
        return original(self, group)

    monkeypatch.setattr(NotesAcquisition, "verify_ref_inventory", unavailable)
    report = run_request(acquisition, request, paired=paired)
    assert report.status == "partial"
    assert report.failure_code == "OBJECT_UNAVAILABLE"
    assert report.ref_notes_inventories
    assert all(not result.verified for result in report.ref_inventory_verifications)
    assert not app.repository_store.sql("SELECT 1 FROM ref_coverage_proofs")
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("kind", ["budget", "corrupt-shaped", "json", "hostile-notes"])
@pytest.mark.parametrize("paired", [False, True], ids=["repository", "paired"])
def test_verification_work_callback_exception_keeps_identity(
    acquisition, monkeypatch, paired, kind
):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    if paired:
        enable_context(acquisition)
    request = request_for(acquisition)
    original = NotesAcquisition.verify_ref_inventory
    sentinel = {
        "budget": RepositoryFailure("BUDGET", "callback", "synthetic caller refusal"),
        "corrupt-shaped": RepositoryFailure(
            "AUTHORITATIVE_CORRUPTION", "callback", "synthetic caller exception"
        ),
        "json": json.JSONDecodeError("synthetic callback", "x", 0),
        "hostile-notes": ValueError("synthetic callback with invalid notes"),
    }[kind]
    if kind == "hostile-notes":
        sentinel.__notes__ = "not-a-list"

    def inject(self, group):
        previous = self.work.require

        def require(unit, amount=1):
            if unit == "proof_steps":
                raise sentinel
            return previous(unit, amount)

        monkeypatch.setattr(self.work, "require", require)
        return original(self, group)

    monkeypatch.setattr(NotesAcquisition, "verify_ref_inventory", inject)
    with pytest.raises(type(sentinel)) as error:
        run_request(acquisition, request, paired=paired)
    assert error.value is sentinel
    assert not app.repository_store.sql("SELECT 1 FROM ref_coverage_proofs")
    if paired:
        if kind == "hostile-notes":
            assert sentinel.__notes__ == "not-a-list"
        else:
            assert any(
                "Repository and Context committed" in note
                for note in sentinel.__notes__
            )
        assert app.repository_store.sql("SELECT 1 FROM notes_mapping_groups")
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()
    before = budget_spent(acquisition, request)
    monkeypatch.setattr(NotesAcquisition, "verify_ref_inventory", original)
    retried = run_request(acquisition, request, paired=paired, new_request=False)
    assert all(v.verified for v in retried.ref_inventory_verifications)
    assert (
        budget_spent(acquisition, request)["metadata_units"] > before["metadata_units"]
    )


def test_wiring_stops_on_corrupted_stored_verification(acquisition):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    request = request_for(acquisition)
    first = run_request(acquisition, request)
    assert all(v.verified for v in first.ref_inventory_verifications)
    with connect(repository_path, "repository") as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE name='p1_immutable_ref_coverage_proofs_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_coverage_proofs_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE ref_coverage_proofs SET structures_json='[]'")
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.execute(trigger)
        db.commit()
    with pytest.raises(RepositoryFailure) as error:
        run_request(acquisition, request, new_request=False)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (repository_path.parent / "p1-recovery-stop.json").exists()


def test_paired_post_commit_failure_preserves_verified_prefix(acquisition, monkeypatch):
    app, _, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    enable_context(acquisition)
    request = request_for(acquisition)
    original = NotesAcquisition.verify_ref_inventory
    calls = []
    sentinel = RuntimeError("second verification interrupted")

    def interrupt(self, group):
        if calls:
            raise sentinel
        calls.append(group)
        return original(self, group)

    monkeypatch.setattr(NotesAcquisition, "verify_ref_inventory", interrupt)
    with pytest.raises(RuntimeError) as error:
        run_request(acquisition, request, paired=True)
    assert error.value is sentinel
    assert any(
        "Repository and Context committed" in note for note in sentinel.__notes__
    )
    before = app.repository_store.sql(
        "SELECT verification_provenance FROM ref_coverage_proofs"
    )
    assert len(before) == 1
    spent = budget_spent(acquisition, request)
    monkeypatch.setattr(NotesAcquisition, "verify_ref_inventory", original)
    replay = run_request(acquisition, request, paired=True, new_request=False)
    assert all(v.verified for v in replay.ref_inventory_verifications)
    after = app.repository_store.sql(
        "SELECT verification_provenance FROM ref_coverage_proofs"
    )
    assert len(after) == 2 and before[0] in after
    assert (
        budget_spent(acquisition, request)["metadata_units"] > spent["metadata_units"]
    )
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


def test_caller_owned_transaction_defers_until_durable_commit(acquisition):
    app, path, _, _, _, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    enable_context(acquisition)
    request = request_for(acquisition, metadata=True)

    def repository_unit(repository_store):
        return GitAcquisition(repository_store).acquire_metadata_only(
            request,
            notes_source=GitNotesSource(GitNativeSource(path)),
            work=app.work,
            progress=app.progress,
        )

    result = PairedAcquisitionCoordinator(repository_path.parent).admit_paired(
        repository_fn=repository_unit, reconcile_dependencies=False
    )
    assert result.admission == PairAdmission(True, True)
    report = result.git_report
    assert report.status == "partial"
    assert report.failure_code == "REF_INVENTORY_DEFERRED"
    assert all(not v.verified for v in report.ref_inventory_verifications)
    assert not app.repository_store.sql("SELECT 1 FROM ref_coverage_proofs")
    assert all(
        app.verify_ref_inventory(v.group).verified
        for v in report.ref_inventory_verifications
    )
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


def test_caller_transaction_rollback_cannot_leave_verification_pin(acquisition):
    app, path, _, _, _, repository_path, op_path = acquisition
    fixtures.fixture_note(acquisition)
    enable_context(acquisition)
    request = request_for(acquisition, metadata=True)
    source = GitNotesSource(GitNativeSource(path))
    attempted = []

    def repository_unit(repository_store):
        attempted.append(
            GitAcquisition(repository_store).acquire_metadata_only(
                request, notes_source=source, work=app.work, progress=app.progress
            )
        )
        raise RuntimeError("abort caller transaction")

    with pytest.raises(AdmissionFailure) as error:
        PairedAcquisitionCoordinator(repository_path.parent).admit_paired(
            repository_fn=repository_unit, reconcile_dependencies=False
        )
    assert error.value.outcome == PairAdmission(False, False)
    assert attempted[0].failure_code == "REF_INVENTORY_DEFERRED"
    assert not app.repository_store.sql("SELECT 1 FROM notes_mapping_groups")
    with closing(connect(op_path, "operational")) as db:
        pins = db.execute(
            "SELECT continuation_scope_json FROM request_continuations "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            app.work.request.values(),
        ).fetchall()
    assert not any("p4-ref-inventory-check" in row[0] for row in pins)
    replay = GitAcquisition(repository_path).acquire_metadata_only(
        request, notes_source=source, work=app.work, progress=app.progress
    )
    assert all(v.verified for v in replay.ref_inventory_verifications)
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


def test_direct_verification_rejects_caller_owned_transaction(acquisition):
    app, _, _, repository, origin, repository_path, op_path = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    enable_context(acquisition)

    def repository_unit(repository_store):
        NotesAcquisition(
            repository_store,
            app.source,
            app.work,
            app.progress,
            source_attribution="local-test",
            repository_uuidv4=repository,
        ).verify_ref_inventory(group)
        raise RuntimeError("synthetic rollback after verification")

    with pytest.raises(AdmissionFailure) as error:
        PairedAcquisitionCoordinator(repository_path.parent).admit_paired(
            repository_fn=repository_unit, reconcile_dependencies=False
        )
    assert error.value.outcome == PairAdmission(False, False)
    assert not app.repository_store.sql("SELECT 1 FROM ref_coverage_proofs")
    with closing(connect(op_path, "operational")) as db:
        pins = db.execute(
            "SELECT continuation_scope_json FROM request_continuations "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            app.work.request.values(),
        ).fetchall()
    assert not any("p4-ref-inventory-check" in row[0] for row in pins)
    assert error.value.cause.code == "REF_INVENTORY_DEFERRED"
    assert app.verify_ref_inventory(group).verified
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


def test_existing_orphaned_pin_refuses_without_fabricating_a_proof(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    group = app.inventory_ref(claim).group
    identity = (
        *app.progress.request_identity(),
        *claim.ref_observation_key.key,
        encode(claim.provenance.key),
        *claim.root_object_oid.key,
        group.interpretation_kind,
        group.interpretation_version,
        group.interpretation_scope,
        group.group_scope,
        *group.provenance.key,
    )
    slot = encode(["p4-ref-inventory-check", *identity])
    orphan = {
        "verification_uuidv7": new_uuid7(),
        "observed_at_us": 1_700_000_000_000_000,
    }
    app.progress.save_once_bounded(slot, orphan, 4096, encoded=encode(orphan))
    with pytest.raises(RepositoryFailure) as error:
        app.verify_ref_inventory(group)
    assert error.value.code == "CONTINUATION_UNAVAILABLE"
    assert not app.repository_store.sql("SELECT 1 FROM ref_coverage_proofs")
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()
    fresh = NotesAcquisition(
        app.repository_store,
        app.source,
        UnlimitedWorkBudget(),
        InMemoryNotesProgress(),
        source_attribution="local-test",
        repository_uuidv4=repository,
    )
    assert fresh.verify_ref_inventory(group).verified
    with pytest.raises(RepositoryFailure) as old_request:
        app.verify_ref_inventory(group)
    assert old_request.value.code == "CONTINUATION_UNAVAILABLE"
