"""Real Git and Operational replay coverage for ADR 0036 acquisition."""

from uuid import uuid4

import pytest

from repo_catalog.domain.p1_core import CoreFailure
from tests.integration.p4.conftest import fixture_note, git


def discover(app, repository, origin, request, nominated=()):
    return app.discover(repository, "local-test", origin, request, 1234567, nominated)


def test_two_real_scans_have_distinct_keys_and_replay_exactly(acquisition):
    app, path, fmt, repository, origin, *_ = acquisition
    capture, target, _ = fixture_note(acquisition)
    request = str(uuid4())
    first = discover(app, repository, origin, request)
    assert len(first.enumerations) == 2
    event1, event2 = first.enumerations
    assert app.core.ref_enumeration(*event1.event.identity, app.work) == event1
    assert app.core.ref_enumeration(*event2.event.identity, app.work) == event2
    assert event1.event.identity != event2.event.identity
    assert len(event1.links) == len(event2.links) == 1
    first_link, second_link = event1.links[0], event2.links[0]
    assert (
        first_link.observation.ref_observation_key
        != second_link.observation.ref_observation_key
    )
    assert first_link.claim.root_oid == second_link.claim.root_oid == capture.root
    assert first_link.claim.ref_form is None  # this adapter did not read symref form
    repeated = discover(app, repository, origin, request)
    assert repeated.enumerations == first.enumerations
    fresh = discover(app, repository, origin, str(uuid4()))
    assert fresh.enumerations[0].event.identity != event1.event.identity
    assert (
        fresh.enumerations[0].links[0].observation.ref_observation_key
        != first_link.observation.ref_observation_key
    )


def test_named_absence_is_qualified_and_failed_enumeration_never_infers_absence(
    acquisition, monkeypatch
):
    app, path, fmt, repository, origin, *_ = acquisition
    fixture_note(acquisition)
    missing = "refs/notes/missing"
    result = discover(app, repository, origin, str(uuid4()), (missing,))
    lookup = [
        x
        for x in result.enumerations
        if x.event.nominated == (missing.encode(),) and not x.event.prefixes
    ]
    assert len(lookup) == 1
    link = lookup[0].links[0]
    assert link.derivation == "absence" and link.claim.presence_state == "absent"
    assert link.claim.absence_evidence.method == "lookup"
    assert (
        link.claim.absence_evidence.visibility_scope == lookup[0].event.visibility_scope
    )

    def fail(*args):
        raise CoreFailure("GIT_INPUT", "scan", "failed")

    monkeypatch.setattr(app.source, "_scan", fail)
    failed = discover(app, repository, origin, str(uuid4()), (missing,))
    assert failed.failure_code == "GIT_INPUT"
    assert not any(
        link.claim.presence_state == "absent"
        for e in failed.enumerations
        for link in e.links
    )


def test_dangling_symbolic_ref_is_not_absence(acquisition):
    app, path, fmt, repository, origin, *_ = acquisition
    name = "refs/notes/dangling"
    git(path, "symbolic-ref", name, "refs/notes/does-not-exist")
    result = discover(app, repository, origin, str(uuid4()), (name,))
    lookup = [
        e
        for e in result.enumerations
        if e.event.nominated == (name.encode(),) and not e.event.prefixes
    ]
    assert len(lookup) == 1
    assert lookup[0].links[0].claim.presence_state == "present"
    assert lookup[0].links[0].claim.root_oid is None


def test_ref_note_evidence_is_bound_to_exact_scan_claim(acquisition):
    app, path, fmt, repository, origin, *_ = acquisition
    _, target, note = fixture_note(acquisition, fanout=1)
    result = discover(app, repository, origin, str(uuid4()))
    c1, c2 = [event.links[0].claim for event in result.enumerations]
    acquired = app.acquire_ref_note(c1, target)
    assert acquired.role_verified and acquired.body_retained and acquired.note == note
    mapping = (
        app.core.notes_mapping_projection(
            c1, target, "git-notes", "1", "native-notes-tree", app.work
        )
        .evidence[0]
        .mapping
    )
    assert app.core.read_ref_note(c1, mapping, app.work) == b"\0\xffbinary\r\n"
    with pytest.raises(CoreFailure) as error:
        app.core.read_ref_note(c2, mapping, app.work)
    assert error.value.code == "NOTES_ROLE_UNAVAILABLE"
    second = app.acquire_ref_note(c2, target, retain_body=False)
    assert second.role_verified and not second.body_retained
    assert app.core.read_ref_note(c1, mapping, app.work) == b"\0\xffbinary\r\n"


def test_pinned_scan_survives_failed_admission_without_a_reread(
    acquisition, monkeypatch
):
    app, path, fmt, repository, origin, *_ = acquisition
    fixture_note(acquisition)
    request = str(uuid4())
    original_discover = app.source.discover
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original_discover(*args, **kwargs)

    monkeypatch.setattr(app.source, "discover", counted)
    original_admit = app.core.admit_ref_enumeration

    def fail_once(*args, **kwargs):
        monkeypatch.setattr(app.core, "admit_ref_enumeration", original_admit)
        raise CoreFailure("INJECTED", "core", "before event admission")

    monkeypatch.setattr(app.core, "admit_ref_enumeration", fail_once)
    with pytest.raises(CoreFailure, match="before event admission"):
        discover(app, repository, origin, request)
    resumed = discover(app, repository, origin, request)
    assert len(calls) == 1 and len(resumed.enumerations) == 2
    assert (
        discover(app, repository, origin, request).enumerations == resumed.enumerations
    )


def test_event_rebind_rolls_back_and_small_progress_limit_does_not_stop_catalog(
    acquisition,
):
    from dataclasses import replace

    from repo_catalog.domain.ref_observation import new_uuid7

    app, path, fmt, repository, origin, *_ = acquisition
    fixture_note(acquisition)
    result = discover(app, repository, origin, str(uuid4()))
    original = result.enumerations[0]
    link = original.links[0]
    event = replace(original.event, enumeration_uuidv7=new_uuid7())
    subject = replace(
        link.observation, observed_at_us=link.observation.observed_at_us + 1
    )
    changed = replace(link, event=event, observation=subject)
    with pytest.raises(CoreFailure) as error:
        app.core.admit_ref_enumeration(event, (changed,), app.work)
    assert error.value.code == "INCOMPATIBLE_REPLAY"
    assert not app.core.sql(
        "SELECT 1 FROM ref_enumeration_observations WHERE enumeration_uuidv7=?",
        (event.enumeration_uuidv7,),
    )
    scope = next(
        scope
        for scope in app.progress.work.ledger.db.execute(
            "SELECT continuation_scope_json FROM request_continuations"
        )
        if "p4-enumeration" in scope[0]
    )[0]
    with pytest.raises(CoreFailure) as error:
        app.progress.load_bounded(scope, 1)
    assert error.value.code == "BUDGET"
    with pytest.raises(CoreFailure) as error:
        app.core.ref_enumeration(*original.event.identity, app.work, max_bytes=8)
    assert error.value.code == "QUERY_BUDGET"
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert app.core.ref_enumeration(*original.event.identity, app.work) == original


def test_two_changed_scans_are_separate_events_not_atomic_snapshot(
    acquisition, monkeypatch
):
    app, path, fmt, repository, origin, *_ = acquisition
    capture, _, _ = fixture_note(acquisition)
    other = fixture_note(acquisition, body=b"another note")[0].root
    git(path, "update-ref", capture.ref, capture.root.full_oid)
    original_scan = app.source._scan
    calls = []

    def changing(names, work, observed):
        if calls:
            git(path, "update-ref", capture.ref, other.full_oid)
        calls.append(1)
        return original_scan(names, work, observed)

    monkeypatch.setattr(app.source, "_scan", changing)
    result = discover(app, repository, origin, str(uuid4()))
    assert result.failure_code == "REF_CHANGED"
    assert len(result.enumerations) == 2
    assert [item.links[0].claim.root_oid for item in result.enumerations] == [
        capture.root,
        other,
    ]
    assert all(
        item.event.enumeration_state == "complete" for item in result.enumerations
    )
    assert (
        result.enumerations[0].event.identity != result.enumerations[1].event.identity
    )


def test_stored_enumeration_corruption_stops_catalog(acquisition):
    from repo_catalog.adapters.sqlite.p1_schema import connect

    app, path, fmt, repository, origin, core_path, _ = acquisition
    fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0].event
    db = connect(core_path, "core")
    db.execute("DROP TRIGGER p1_immutable_ref_enumeration_observations_update")
    db.execute(
        "UPDATE ref_enumeration_observations SET enumeration_scope_json='[[],[]]' WHERE enumeration_uuidv7=?",
        (event.enumeration_uuidv7,),
    )
    db.commit()
    db.close()
    with pytest.raises(CoreFailure) as error:
        app.core.ref_enumeration(*event.identity, app.work)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (core_path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        app.core.ensure_available()
    assert stopped.value.code == "RECOVERY_STOP"


def test_note_body_requires_claim_specific_proof_for_commit_root(acquisition):
    app, _, _, repository, origin, *_ = acquisition
    _, target, note = fixture_note(acquisition, commit=True)
    first = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    result = app.acquire_ref_note(first, target)
    assert result.role_verified and result.body_retained and result.note == note


def test_ack_loss_replays_pinned_event_after_commit(acquisition, monkeypatch):
    app, _, _, repository, origin, *_ = acquisition
    fixture_note(acquisition)
    request = str(uuid4())
    original = app.core.admit_ref_enumeration
    admitted = []

    def lose_ack(event, links, work):
        original(event, links, work)
        admitted.append(event.identity)
        monkeypatch.setattr(app.core, "admit_ref_enumeration", original)
        raise CoreFailure("INJECTED", event.identity, "ack lost")

    monkeypatch.setattr(app.core, "admit_ref_enumeration", lose_ack)
    with pytest.raises(CoreFailure, match="ack lost"):
        discover(app, repository, origin, request)
    result = discover(app, repository, origin, request)
    assert result.enumerations[0].event.identity == admitted[0]
    assert (
        len(
            app.core.sql(
                "SELECT 1 FROM ref_enumeration_observations WHERE enumeration_uuidv7=?",
                (admitted[0][1],),
            )
        )
        == 1
    )


def test_concurrent_redeliveries_do_not_discard_actual_distinct_scans(acquisition):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.adapters.sqlite.notes import NotesProgress
    from repo_catalog.adapters.sqlite.p1_coordination import NotesWorkBudget, WorkLedger
    from repo_catalog.adapters.sqlite.p1_schema import connect
    from repo_catalog.application.ref_observations import (
        EnumeratedRef,
        RefScan,
        pin_scan,
    )
    from repo_catalog.domain.p1_coordination import NotesLimits
    from repo_catalog.domain.p1_core import encode

    app, path, fmt, repository, origin, core_path, op_path = acquisition
    initial, _, _ = fixture_note(acquisition)
    updated, _, _ = fixture_note(acquisition, body=b"changed root")
    git(path, "update-ref", initial.ref, initial.root.full_oid)
    attempts = [str(uuid4()) for _ in range(3)]
    for attempt in attempts:
        app.work.ledger.attempt(app.work.request, attempt)
    seen, resume, reads = Event(), Event(), []
    slot = encode(["i2-concurrent-test", str(uuid4())])
    next_slot = encode(["i2-fresh-test", str(uuid4())])

    def run(attempt, selected_slot, hold=False):
        db = connect(op_path, "operational")
        core = GitCore(core_path)
        try:
            ledger = WorkLedger(db)
            work = NotesWorkBudget(ledger, app.work.request, attempt, NotesLimits())
            progress = NotesProgress(work)

            def scan():
                records = app.source.source.ref_records(work)
                values = tuple(
                    EnumeratedRef(r.name, r.target, r.symbolic_target, r.peeled)
                    for r in records
                    if r.name.startswith(b"refs/notes/")
                )
                reads.append(values[0].target)
                if hold:
                    seen.set()
                    assert resume.wait(15)
                return RefScan(values, "complete", "git-for-each-ref:exit-0")

            return pin_scan(
                core,
                progress,
                work,
                slot=selected_slot,
                binding=["same-real-request"],
                origin=origin,
                repository=repository,
                source="local-test",
                visibility="concurrent-local",
                prefixes=(b"refs/notes/",),
                nominated=(),
                observed_at_us=1234567,
                byte_limit=1_000_000,
                ref_limit=100,
                scan=scan,
            )
        finally:
            core.close()
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run, attempts[0], slot, True)
        assert seen.wait(15)
        git(path, "update-ref", initial.ref, updated.root.full_oid)
        second = executor.submit(run, attempts[1], slot)
        try:
            with pytest.raises(CoreFailure) as busy:
                second.result(timeout=15)
            assert busy.value.code == "ACQUISITION_BUSY"
        finally:
            resume.set()
        pinned = first.result(timeout=15)
    assert reads == [initial.root]
    assert run(attempts[1], slot) == pinned
    assert reads == [initial.root]  # redelivery did not read the changed ref
    fresh = run(attempts[2], next_slot)
    assert reads == [initial.root, updated.root]
    assert fresh.event.identity != pinned.event.identity
    assert (
        fresh.links[0].observation.ref_observation_key
        != pinned.links[0].observation.ref_observation_key
    )
    assert fresh.links[0].claim.root_oid == updated.root


def test_empty_enumerations_survive_git_only_backup_and_restore(acquisition):
    from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
    from repo_catalog.domain.recovery import BackupScope

    app, path, fmt, repository, origin, core_path, _ = acquisition
    result = discover(app, repository, origin, str(uuid4()))
    assert len(result.enumerations) == 2
    assert all(not event.links for event in result.enumerations)
    assert not app.core.sql("SELECT 1 FROM ref_observations")
    destination = path.parent / "backup-ref-i2"
    adapter = SQLiteRecoveryAdapter()
    assert adapter.create_consistent_backup(
        core_path.parent, destination, BackupScope.GIT_ONLY
    ).verified_clean
    restored = path.parent / "restored-ref-i2"
    assert adapter.restore_backup(destination, restored, repository).revalidated_clean
    copy = GitCore(restored / "core.sqlite3")
    try:
        for original in result.enumerations:
            assert (
                copy.ref_enumeration(*original.event.identity, UnlimitedWorkBudget())
                == original
            )
    finally:
        copy.close()
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_inventory_is_pinned_as_distinct_claim_specific_whole_groups(
    acquisition, monkeypatch
):
    app, _, _, repository, origin, *_ = acquisition
    _, target, note = fixture_note(acquisition)
    events = discover(app, repository, origin, str(uuid4())).enumerations
    c1, c2 = [event.links[0].claim for event in events]
    first = app.inventory_ref(c1)
    assert first.group.status == "complete"
    assert first.group.members == ((target.full_oid, note.full_oid, target.full_oid),)
    monkeypatch.setattr(
        app.source, "metadata", lambda *_: pytest.fail("pinned group reread source")
    )
    assert app.inventory_ref(c1) == first
    projection = app.core.notes_mapping_projection(
        c1, target, "git-notes", "1", "native-notes-tree", app.work
    )
    assert projection.groups == (first.group,)
    assert (
        app.core.notes_mapping_projection(
            c2, target, "git-notes", "1", "native-notes-tree", app.work
        ).groups
        == ()
    )


def test_missing_stored_enumeration_link_is_corruption(acquisition):
    from repo_catalog.adapters.sqlite.p1_schema import connect

    app, path, fmt, repository, origin, core_path, _ = acquisition
    fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0].event
    db = connect(core_path, "core")
    db.execute("DROP TRIGGER p1_immutable_ref_enumeration_links_delete")
    db.execute(
        "DELETE FROM ref_enumeration_links WHERE enumeration_uuidv7=?",
        (event.enumeration_uuidv7,),
    )
    db.commit()
    db.close()
    with pytest.raises(CoreFailure) as error:
        app.core.ref_enumeration(*event.identity, app.work)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (core_path.parent / "p1-recovery-stop.json").exists()


def test_partial_scan_cannot_pin_or_admit_absence(acquisition):
    from repo_catalog.application.ref_observations import (
        EnumeratedRef,
        RefScan,
        pin_scan,
    )
    from repo_catalog.domain.p1_core import encode

    app, path, _, repository, origin, core_path, _ = acquisition
    name = b"refs/notes/missing"
    slot = encode(["partial-negative-test", str(uuid4())])
    with pytest.raises(CoreFailure) as error:
        pin_scan(
            app.core,
            app.progress,
            app.work,
            slot=slot,
            binding=["partial"],
            origin=origin,
            repository=repository,
            source="local-test",
            visibility="local",
            prefixes=(),
            nominated=(name,),
            observed_at_us=1234567,
            byte_limit=1_000_000,
            ref_limit=100,
            scan=lambda: RefScan(
                (EnumeratedRef(name, None, absent=True),), "partial", None
            ),
        )
    assert error.value.code == "ENUMERATION"
    assert app.progress.load_bounded(slot, 1_000_000) is None
    assert not app.core.sql("SELECT 1 FROM ref_observation_claims")
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_replay_validates_corrupt_stored_event_before_comparing_input(acquisition):
    from repo_catalog.adapters.sqlite.p1_schema import connect

    app, _, _, repository, origin, core_path, _ = acquisition
    fixture_note(acquisition)
    original = discover(app, repository, origin, str(uuid4())).enumerations[0]
    db = connect(core_path, "core")
    db.execute("DROP TRIGGER p1_immutable_ref_enumeration_observations_update")
    db.execute(
        "UPDATE ref_enumeration_observations SET enumeration_scope_json='[[],[]]' WHERE enumeration_uuidv7=?",
        (original.event.enumeration_uuidv7,),
    )
    db.commit()
    db.close()
    with pytest.raises(CoreFailure) as error:
        app.core.admit_ref_enumeration(original.event, original.links, app.work)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (core_path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        app.core.ensure_available()
    assert stopped.value.code == "RECOVERY_STOP"


def _prepared_thousand_links(acquisition):
    from dataclasses import replace

    from repo_catalog.application.acquisition import _PreparedCore
    from repo_catalog.domain.p1_core import encode
    from repo_catalog.domain.ref_observation import (
        RefEnumerationLink,
        RefObservationKey,
        new_uuid7,
    )

    app, _, _, repository, origin, *_ = acquisition
    fixture_note(acquisition)
    sample = discover(app, repository, origin, str(uuid4())).enumerations[0]
    event = replace(
        sample.event, enumeration_uuidv7=new_uuid7(), link_count=1000, ref_limit=1000
    )
    base = sample.links[0]

    class CountedTuple(tuple):
        visits = 0

        def __iter__(self):
            for value in super().__iter__():
                self.visits += 1
                yield value

    items = []
    for position in range(1000):
        key = RefObservationKey(origin, new_uuid7())
        subject = replace(
            base.observation,
            ref_observation_key=key,
            ref_name_bytes=f"refs/notes/review-{position}".encode(),
        )
        claim = replace(
            base.claim,
            ref_observation_key=key,
            provenance=replace(
                base.claim.provenance,
                observation=encode(event.identity),
                coordinate=str(position),
            ),
        )
        items.append(RefEnumerationLink(event, subject, claim, "item", position))
    links = CountedTuple(items)
    prepared = _PreparedCore(app.core)
    prepared.admit_ref_enumeration(event, links, app.work)
    return prepared, links


def test_prepared_lookup_charges_every_inspected_link(acquisition):
    from tests.integration.p1.test_core import Budget

    prepared, links = _prepared_thousand_links(acquisition)
    work = Budget()
    result = prepared.ref_observation(links[-1].observation.ref_observation_key, work)
    assert result.claims == (links[-1].claim,)
    assert links.visits == 1000
    assert work.counts.get("metadata_units", 0) >= 1000


def test_valid_event_rebinding_and_budget_exhaustion_are_not_corruption(acquisition):
    from dataclasses import replace

    app, _, _, repository, origin, core_path, _ = acquisition
    fixture_note(acquisition)
    original = discover(app, repository, origin, str(uuid4())).enumerations[0]
    changed_event = replace(original.event, byte_limit=original.event.byte_limit + 1)
    changed_links = tuple(replace(link, event=changed_event) for link in original.links)
    with pytest.raises(CoreFailure) as rebound:
        app.core.admit_ref_enumeration(changed_event, changed_links, app.work)
    assert rebound.value.code == "INCOMPATIBLE_REPLAY"
    with pytest.raises(CoreFailure) as limited:
        app.core.admit_ref_enumeration(
            original.event, original.links, app.work, max_replay_bytes=8
        )
    assert limited.value.code in ("BUDGET", "QUERY_BUDGET")
    assert not (core_path.parent / "p1-recovery-stop.json").exists()
    app.core.admit_ref_enumeration(original.event, original.links, app.work)
    assert app.core.ref_enumeration(*original.event.identity, app.work) == original


def test_prepared_lookup_stops_at_request_metadata_budget(acquisition):
    from tests.integration.p1.test_core import Budget

    prepared, links = _prepared_thousand_links(acquisition)

    class Limited(Budget):
        def require(self, unit, amount=1):
            if unit == "metadata_units" and self.counts.get(unit, 0) + amount > 20:
                raise CoreFailure("BUDGET", unit, "finite work limit")
            super().require(unit, amount)

    work = Limited()
    with pytest.raises(CoreFailure) as error:
        prepared.ref_observation(links[-1].observation.ref_observation_key, work)
    assert error.value.code == "BUDGET"
    assert work.counts["metadata_units"] == 20
    assert links.visits == 20


def test_concurrent_notes_discovery_scans_once_before_pin(acquisition, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.adapters.sqlite.notes import NotesProgress
    from repo_catalog.adapters.sqlite.p1_coordination import NotesWorkBudget, WorkLedger
    from repo_catalog.adapters.sqlite.p1_schema import connect
    from repo_catalog.application.notes import NotesAcquisition
    from repo_catalog.domain.p1_coordination import NotesLimits

    app, path, _, repository, origin, core_path, op_path = acquisition
    first_root, _, _ = fixture_note(acquisition)
    next_root, _, _ = fixture_note(acquisition, body=b"second notes discovery")
    git(path, "update-ref", first_root.ref, first_root.root.full_oid)
    attempts = [str(uuid4()) for _ in range(3)]
    for attempt in attempts:
        app.work.ledger.attempt(app.work.request, attempt)
    observed, resume, calls = Event(), Event(), []
    original_discover = app.source.discover

    def delayed(*args, **kwargs):
        result = original_discover(*args, **kwargs)
        calls.append(result.refs[0][1])
        if len(calls) == 1:
            observed.set()
            assert resume.wait(15)
        return result

    monkeypatch.setattr(app.source, "discover", delayed)
    request = str(uuid4())

    def run(attempt, request_id):
        db = connect(op_path, "operational")
        core = GitCore(core_path)
        try:
            work = NotesWorkBudget(
                WorkLedger(db), app.work.request, attempt, NotesLimits()
            )
            owner = NotesAcquisition(
                core,
                app.source,
                work,
                NotesProgress(work),
                source_attribution="local-test",
            )
            return discover(owner, repository, origin, request_id)
        finally:
            core.close()
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run, attempts[0], request)
        assert observed.wait(15)
        git(path, "update-ref", first_root.ref, next_root.root.full_oid)
        second = executor.submit(run, attempts[1], request)
        try:
            with pytest.raises(CoreFailure) as busy:
                second.result(timeout=15)
            assert busy.value.code == "ACQUISITION_BUSY"
        finally:
            resume.set()
        pinned = first.result(timeout=15)
    assert calls == [first_root.root]
    assert run(attempts[1], request).enumerations == pinned.enumerations
    assert calls == [first_root.root]
    fresh = run(attempts[2], str(uuid4()))
    assert calls == [first_root.root, next_root.root]
    assert fresh.enumerations[0].event.identity != pinned.enumerations[0].event.identity


def test_discovery_redelivery_stops_for_corrupt_pinned_event(acquisition):
    from repo_catalog.adapters.sqlite.p1_schema import connect

    app, _, _, repository, origin, core_path, _ = acquisition
    fixture_note(acquisition)
    request = str(uuid4())
    event = discover(app, repository, origin, request).enumerations[0].event
    db = connect(core_path, "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_enumeration_observations_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_enumeration_observations_update")
        db.execute(
            "UPDATE ref_enumeration_observations SET enumeration_scope_json='[[],[]]' WHERE enumeration_uuidv7=?",
            (event.enumeration_uuidv7,),
        )
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    with pytest.raises(CoreFailure) as error:
        discover(app, repository, origin, request)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (core_path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        app.core.ensure_available()
    assert stopped.value.code == "RECOVERY_STOP"


def test_failed_unpinned_read_releases_guard_and_retry_is_new_read(acquisition):
    from repo_catalog.application.ref_observations import (
        EnumeratedRef,
        RefScan,
        pin_scan,
    )
    from repo_catalog.domain.p1_core import encode

    app, path, _, repository, origin, *_ = acquisition
    first, _, _ = fixture_note(acquisition)
    second, _, _ = fixture_note(acquisition, body=b"after interrupted read")
    git(path, "update-ref", first.ref, first.root.full_oid)
    slot = encode(["unpublished-scan-test", str(uuid4())])
    calls = []

    def scan():
        records = app.source.source.ref_records(app.work)
        result = tuple(
            EnumeratedRef(r.name, r.target, r.symbolic_target, r.peeled)
            for r in records
            if r.name.startswith(b"refs/notes/")
        )
        calls.append(result[0].target)
        if len(calls) == 1:
            raise CoreFailure("INJECTED", "scan", "crash before pin")
        return RefScan(result, "complete", "git-for-each-ref:exit-0")

    args = dict(
        slot=slot,
        binding=["new-after-loss"],
        origin=origin,
        repository=repository,
        source="local-test",
        visibility="local",
        prefixes=(b"refs/notes/",),
        nominated=(),
        observed_at_us=1234567,
        byte_limit=1_000_000,
        ref_limit=100,
        scan=scan,
    )
    with pytest.raises(CoreFailure, match="crash before pin"):
        pin_scan(app.core, app.progress, app.work, **args)
    assert app.progress.load_bounded(slot, 1_000_000) is None
    git(path, "update-ref", first.ref, second.root.full_oid)
    result = pin_scan(app.core, app.progress, app.work, **args)
    assert calls == [first.root, second.root]
    assert result.links[0].claim.root_oid == second.root
    assert len(app.core.sql("SELECT 1 FROM ref_enumeration_observations")) == 1


def test_scan_guard_released_after_process_termination(acquisition):
    import selectors
    import subprocess
    import sys

    from repo_catalog.domain.p1_core import encode

    app, _, _, _, _, _, op_path = acquisition
    attempt = str(uuid4())
    app.work.ledger.attempt(app.work.request, attempt)
    scope = encode(["i2-guard-crash", str(uuid4())])
    code = r"""
import sys,time
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.p1_coordination import WorkLedger,NotesWorkBudget
from repo_catalog.adapters.sqlite.notes import NotesProgress
from repo_catalog.domain.p1_coordination import RequestIdentity,NotesLimits
path, origin, request, attempt, scope = sys.argv[1:]
db=connect(path,"operational")
work=NotesWorkBudget(WorkLedger(db),RequestIdentity(origin,request),attempt,NotesLimits())
with NotesProgress(work).scan_guard(scope):
    print("READY",flush=True)
    time.sleep(60)
"""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            code,
            str(op_path),
            *app.work.request.values(),
            attempt,
            scope,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            assert selector.select(10), "child did not acquire scan guard"
            assert proc.stdout.readline().strip() == "READY"
        with pytest.raises(CoreFailure) as busy:
            with app.progress.scan_guard(scope):
                pytest.fail("another process still owns the guard")
        assert busy.value.code == "ACQUISITION_BUSY"
    finally:
        proc.terminate()
        proc.communicate(timeout=10)
    with app.progress.scan_guard(scope):
        pass
    assert app.progress.load_bounded(scope, 1024) is None


def test_guard_scopes_are_canonical_and_independent(acquisition):
    import hashlib

    from repo_catalog.domain.p1_core import encode

    app, *_ = acquisition
    left = encode(["slot-a", 1])
    same = '[ "slot-a", 1 ]'
    req = "".join(app.work.request.values()).encode("ascii")

    def stripe(scope):
        return hashlib.sha256(req + b"\0" + scope.encode("ascii")).hexdigest()[:4]

    right = next(
        encode(["slot-b", n])
        for n in range(100)
        if stripe(encode(["slot-b", n])) != stripe(left)
    )
    with app.progress.scan_guard(left):
        with pytest.raises(CoreFailure) as error:
            with app.progress.scan_guard(same):
                pytest.fail("equivalent slot was concurrently acquired")
        assert error.value.code == "ACQUISITION_BUSY"
        with app.progress.scan_guard(right):
            pass
