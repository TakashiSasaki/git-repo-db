"""Synthetic ADR 0036 recovery units on disposable catalogs."""

import base64
import copy
import io
import json
import multiprocessing
import os
import signal
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.recovery import (
    RecoveryWorkBudget,
    SQLiteRecoveryAdapter,
    stop_catalog,
)
from repo_catalog.adapters.sqlite.ref_salvage import (
    admit_ref_unit,
    admit_ref_unit_atomic,
    scan_ref_units,
)
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_core import (
    OID,
    CoreCoverageScope,
    CoreFailure,
    Provenance,
    account_verification,
    encode,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.recovery import (
    ActivationError,
    BackupScope,
    RecoveryBudget,
    RecoveryError,
)
from repo_catalog.domain.ref_coverage import RefNotesInventoryCoverageProof
from repo_catalog.domain.ref_exchange import observation_from_wire
from repo_catalog.domain.ref_observation import (
    NotesMapping,
    NotesMappingGroup,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
    new_uuid7,
)
from tests.integration.p1 import test_core as p1_fixtures
from tests.integration.p1.test_core import Budget
from tests.integration.p1.test_notes import tree
from tests.integration.p1.test_ref_coverage_i3 import proof_fixture
from tests.integration.p4 import conftest as p4_fixtures
from tests.integration.p4.test_ref_observation_i2 import discover

acquisition = p4_fixtures.acquisition
p1_core_fixture = p1_fixtures.core


def _extract_process(source, output, start, result, crash):
    if crash == "vm":
        original = RecoveryWorkBudget.require

        def reserve_and_kill(self, unit, amount):
            original(self, unit, amount)
            if unit == "ref_source_vm_steps":
                os.kill(os.getpid(), signal.SIGKILL)

        RecoveryWorkBudget.require = reserve_and_kill
    elif crash:
        original = RecoveryWorkBudget.charge

        def charge_and_kill(self, unit, amount):
            original(self, unit, amount)
            if unit == "input_scan_bytes" and amount:
                os.kill(os.getpid(), signal.SIGKILL)

        RecoveryWorkBudget.charge = charge_and_kill
    if start is not None:
        start.wait(15)
    receipt = SQLiteRecoveryAdapter().extract_salvage(
        source, output, request_id="shared-extraction"
    )
    if result is not None:
        result.put((receipt.partial, receipt.candidate_count))


def _extract_state(directory):
    paths = [
        path
        for path in directory.glob("p1-recovery-request-extract-*.json")
        if not path.name.endswith((".reserved.json", ".source.json"))
    ]
    assert len(paths) == 1
    return json.loads(paths[0].read_text())["cumulative_usage"]


def _damage_historical_coverage(path):
    db = connect(path, "core")
    try:
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' "
            "AND tbl_name='coverage_claims' AND sql LIKE '%UPDATE%'"
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(
            "UPDATE coverage_claims SET details_json=CAST(x'80' AS TEXT) "
            "WHERE observed_at_us=20"
        )
        db.execute("PRAGMA ignore_check_constraints=OFF")
        for _, sql in triggers:
            db.execute(sql)
        db.commit()
    finally:
        db.close()


def test_full_fresh_restore_salvage_and_activation(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    adapter = SQLiteRecoveryAdapter()
    outside = tmp_path.parent / (tmp_path.name + "-recovery")
    outside.mkdir()
    backup = outside / "baseline-backup"
    adapter.create_consistent_backup(core_path.parent, backup, BackupScope.GIT_ONLY)
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.inventory_ref(claim)
    app.acquire_ref_note(claim, target)
    stop_catalog(core_path.parent, "synthetic recovery")
    evidence = {
        p.name: p.read_bytes()
        for p in core_path.parent.glob("core.sqlite3*")
        if p.is_file()
    }
    salvage = outside / "ref-salvage.jsonl"
    receipt = adapter.extract_salvage(core_path.parent, salvage)
    assert not receipt.partial, receipt.unreadable_scope
    assert {
        p.name: p.read_bytes()
        for p in core_path.parent.glob("core.sqlite3*")
        if p.is_file()
    } == evidence
    restored = outside / "restored"
    assert adapter.restore_backup(backup, restored, repository).revalidated_clean
    merged = adapter.merge_salvage(restored, salvage)
    assert merged.admitted_units > 0
    recovered = GitCore(restored / "core.sqlite3")
    try:
        work = RecoveryWorkBudget()
        assert recovered.ref_observation(claim.ref_observation_key, work).claims == (
            claim,
        )
        projection = recovered.notes_mapping_projection(
            claim, target, "git-notes", "1", "native-notes-tree", work
        )
        assert (
            recovered.read_ref_note(claim, projection.evidence[0].mapping, work)
            == b"\0\xffbinary\r\n"
        )
    finally:
        recovered.close()
    for mode in ("auto", "core_only"):
        query = ProductionQueryService(restored, mode=mode)
        query_work = RecoveryWorkBudget()
        assert query.detect_mode() == "core_only"
        assert query.get_ref_observation(
            claim.ref_observation_key, query_work
        ).claims == (claim,)
        mapping = (
            query.get_notes_mapping(
                claim, target, "git-notes", "1", "native-notes-tree", query_work
            )
            .evidence[0]
            .mapping
        )
        body = query.read_ref_note_bytes(claim, mapping, query_work)
        assert (
            body.available and body.verified and body.body_bytes == b"\0\xffbinary\r\n"
        )
    assert adapter.activate(restored, outside / "active.json").clean_operational


def test_missing_verified_baseline_cannot_merge_or_activate(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    discover(app, repository, origin, str(uuid4()))
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    subject = next(c for c in scan.candidates if c["candidate_type"] == "ref_subject")
    destination = tmp_path / "unbacked"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    input_file = tmp_path / "candidate.jsonl"
    input_file.write_text(json.dumps(subject) + "\n")
    adapter = SQLiteRecoveryAdapter()
    with pytest.raises(RecoveryError, match="validated fresh backup"):
        adapter.merge_salvage(destination, input_file)
    locator = tmp_path / "unbacked-active"
    with pytest.raises(ActivationError, match="validated fresh backup"):
        adapter.activate(destination, locator)
    assert not locator.exists()
    assert not (destination / "p1-recovery-stop.json").exists()


def test_candidate_decode_limit_stops_before_admission_and_survives_retry(
    acquisition, tmp_path
):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    discover(app, repository, origin, str(uuid4()))
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    candidate = next(c for c in scan.candidates if c["candidate_type"] == "ref_subject")
    outside = tmp_path.parent / (tmp_path.name + "-decode-limit")
    outside.mkdir()
    adapter = SQLiteRecoveryAdapter()
    backup = outside / "backup"
    adapter.create_consistent_backup(core_path.parent, backup, BackupScope.GIT_ONLY)
    destination = outside / "fresh"
    adapter.restore_backup(backup, destination, repository)
    candidate_file = outside / "candidate.jsonl"
    candidate_file.write_text(json.dumps(candidate) + "\n")
    budget = RecoveryBudget(max_work_units={"json_decode_bytes": 1})
    first = adapter.merge_salvage(destination, candidate_file, budget, "decode-limit")
    assert first.admitted_units == first.rejected_units == 0
    assert first.unprocessed_units == 1 and not first.input_complete
    state = destination / "p1-recovery-request-decode-limit.json"
    before = json.loads(state.read_text())["cumulative_usage"]
    assert "ref_source_vm_steps" not in before
    assert "legacy_source_vm_steps" not in before
    retry = adapter.merge_salvage(destination, candidate_file, budget, "decode-limit")
    after = json.loads(state.read_text())["cumulative_usage"]
    assert retry.admitted_units == 0 and not retry.input_complete
    assert after == before
    assert not (destination / "p1-recovery-stop.json").exists()


def test_corrupt_fresh_target_is_stopped_and_not_activated(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    outside = tmp_path.parent / (tmp_path.name + "-failed-activation")
    outside.mkdir()
    backup = outside / "backup"
    adapter = SQLiteRecoveryAdapter()
    adapter.create_consistent_backup(core_path.parent, backup, BackupScope.GIT_ONLY)
    destination = outside / "fresh"
    adapter.restore_backup(backup, destination, repository)
    db = connect(destination / "core.sqlite3", "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_retained_notes_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE ref_retained_notes SET body=zeroblob(size)")
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    locator = outside / "active"
    with pytest.raises(ActivationError, match="validation failed"):
        adapter.activate(destination, locator)
    assert not locator.exists()
    assert (destination / "p1-recovery-stop.json").exists()


def test_real_sqlite_open_corruption_stops_target(p1_core_fixture, tmp_path):
    _, _, repository = p1_core_fixture
    destination = tmp_path / "invalid-sqlite-target"
    destination.mkdir()
    database = destination / "core.sqlite3"
    initialize(database, "core", repository, str(uuid4()))
    database.write_bytes(b"not a sqlite database" * 500)
    with pytest.raises(CoreFailure) as stopped:
        admit_ref_unit_atomic(destination, "ref_subject", {}, RecoveryWorkBudget())
    assert stopped.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (destination / "p1-recovery-stop.json").exists()


def test_unrelated_sqlite_open_failure_does_not_stop_target(
    p1_core_fixture, tmp_path, monkeypatch
):
    from repo_catalog.adapters.sqlite import ref_salvage

    _, _, repository = p1_core_fixture
    destination = tmp_path / "busy-sqlite-target"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    failure = sqlite3.OperationalError("transient busy")
    failure.sqlite_errorcode = sqlite3.SQLITE_BUSY

    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(ref_salvage, "connect", fail)
    with pytest.raises(sqlite3.OperationalError) as caught:
        admit_ref_unit_atomic(destination, "ref_subject", {}, RecoveryWorkBudget())
    assert caught.value is failure
    assert not (destination / "p1-recovery-stop.json").exists()


def test_scanner_keeps_original_observations_and_whole_events(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    events = discover(app, repository, origin, str(uuid4()), ("refs/notes/missing",))
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        work = RecoveryWorkBudget()
        scan = scan_ref_units(
            connection, work, max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    assert not scan.omissions
    subjects = [c for c in scan.candidates if c["candidate_type"] == "ref_subject"]
    claims = [c for c in scan.candidates if c["candidate_type"] == "ref_claim"]
    enumerations = [
        c for c in scan.candidates if c["candidate_type"] == "ref_enumeration"
    ]
    assert len(enumerations) == len(events.enumerations)
    assert (
        len(subjects) == len(claims) == sum(len(e.links) for e in events.enumerations)
    )
    assert any(c["payload"]["claim"]["presence_state"] == "absent" for c in claims)
    assert work.usage["input_bytes"] > 0
    assert work.usage["metadata_units"] > 0


def test_generated_source_columns_are_never_evaluated_and_other_rows_survive(tmp_path):
    suspect = tmp_path / "suspect"
    suspect.mkdir()
    path = suspect / "core.sqlite3"
    repository, origin, observation_id = str(uuid4()), str(uuid4()), new_uuid7()
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE repositories(seed INTEGER, repository_uuidv4 TEXT "
            "GENERATED ALWAYS AS (hex(zeroblob(8388608))) VIRTUAL)"
        )
        db.execute("INSERT INTO repositories(seed) VALUES(1)")
        db.execute(
            "CREATE TABLE ref_observations(observation_origin_uuidv4 TEXT, "
            "ref_observation_uuidv7 TEXT, repository_uuidv4 TEXT, ref_name_bytes BLOB, "
            "source_attribution TEXT, visibility_scope TEXT, observed_at_us INTEGER)"
        )
        db.execute(
            "INSERT INTO ref_observations VALUES(?,?,?,?,?,?,?)",
            (
                origin,
                observation_id,
                repository,
                b"refs/notes/safe",
                "source",
                "scope",
                1,
            ),
        )
    before = path.read_bytes()

    class ObservedConnection(sqlite3.Connection):
        limits_at_scan = []

        def execute(self, statement, *args, **kwargs):
            if statement.startswith("PRAGMA table_list"):
                self.limits_at_scan.append(
                    (
                        self.getlimit(sqlite3.SQLITE_LIMIT_LENGTH),
                        self.getlimit(sqlite3.SQLITE_LIMIT_COLUMN),
                    )
                )
            return super().execute(statement, *args, **kwargs)

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, factory=ObservedConnection)
    calls = []

    def authorizer(action, arg1, arg2, _db, _trigger):
        if action == sqlite3.SQLITE_FUNCTION and arg2 in ("zeroblob", "hex"):
            calls.append(arg2)
        return sqlite3.SQLITE_OK

    conn.set_authorizer(authorizer)
    try:
        work = RecoveryWorkBudget(work_limits={"input_bytes": 100_000})
        previous_length = conn.getlimit(sqlite3.SQLITE_LIMIT_LENGTH)
        scan = scan_ref_units(conn, work, max_records=200, max_row_bytes=1024)
        assert conn.limits_at_scan and all(
            length == 65536 and columns == 512
            for length, columns in conn.limits_at_scan
        )
        assert conn.getlimit(sqlite3.SQLITE_LIMIT_LENGTH) == previous_length
        assert work.usage["ref_source_vm_steps"] > 0
    finally:
        conn.close()
    assert not calls
    assert any(
        "repositories" in item and "generated" in item for item in scan.omissions
    )
    assert any(c["candidate_type"] == "ref_subject" for c in scan.candidates)
    stop_catalog(suspect, "synthetic generated-column corruption")
    output = tmp_path / "safe.jsonl"
    receipt = SQLiteRecoveryAdapter().extract_salvage(
        suspect,
        output,
        budget=RecoveryBudget(
            max_payload_bytes=1024,
            max_input_bytes=65536,
            max_input_records=200,
            max_work_units={"input_bytes": 100_000},
        ),
    )
    assert receipt.partial
    assert any(
        "repositories" in item and "generated" in item
        for item in receipt.unreadable_scope
    )
    assert any(
        json.loads(line)["candidate_type"] == "ref_subject"
        for line in output.read_text().splitlines()
    )
    assert path.read_bytes() == before


@pytest.mark.parametrize("kind", ["VIRTUAL", "STORED"])
def test_unselected_generated_column_is_rejected_before_projection(tmp_path, kind):
    path = tmp_path / "generated.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE repositories(repository_uuidv4 TEXT, "
            f"derived TEXT GENERATED ALWAYS AS (upper('x')) {kind})"
        )
        db.execute(
            "INSERT INTO repositories(repository_uuidv4) VALUES(?)", (str(uuid4()),)
        )
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    calls = []

    def authorizer(action, _arg1, arg2, _db, _trigger):
        if action == sqlite3.SQLITE_FUNCTION and arg2 == "upper":
            calls.append(arg2)
        return sqlite3.SQLITE_OK

    conn.set_authorizer(authorizer)
    try:
        scan = scan_ref_units(
            conn, RecoveryWorkBudget(), max_records=100, max_row_bytes=1024
        )
    finally:
        conn.close()
    assert not calls
    assert any(
        "repositories" in item and "generated" in item for item in scan.omissions
    )


def test_source_vm_budget_is_finite_and_not_reset_on_continuation(tmp_path):
    path = tmp_path / "source.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE repositories(repository_uuidv4 TEXT)")
        db.execute("INSERT INTO repositories VALUES(?)", (str(uuid4()),))
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        work = RecoveryWorkBudget(work_limits={"ref_source_vm_steps": 100})
        first = scan_ref_units(conn, work, max_records=100, max_row_bytes=1024)
        charged = work.usage["ref_source_vm_steps"]
        assert first.exhausted and charged == 100
        second = scan_ref_units(conn, work, max_records=100, max_row_bytes=1024)
        assert second.exhausted and not second.candidates
        assert work.usage["ref_source_vm_steps"] == charged
    finally:
        conn.close()


def test_oversized_stored_value_is_omitted_without_executing_schema(tmp_path):
    path = tmp_path / "large-stored.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE repositories(repository_uuidv4 TEXT)")
        db.execute("INSERT INTO repositories VALUES(?)", ("x" * 8192,))
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            conn, RecoveryWorkBudget(), max_records=100, max_row_bytes=1024
        )
    finally:
        conn.close()
    assert any(
        "repositories" in item and "row exceeds" in item for item in scan.omissions
    )
    assert not any(
        "repositories" in item and "generated" in item for item in scan.omissions
    )


def test_context_generated_columns_are_not_selected_or_executed(tmp_path):
    path = tmp_path / "context.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE text_bodies(sha256 TEXT, text_value TEXT, "
            "derived TEXT GENERATED ALWAYS AS (hex(zeroblob(8388608))) VIRTUAL)"
        )
        db.execute(
            "INSERT INTO text_bodies(sha256,text_value) VALUES(?,?)", ("a" * 64, "safe")
        )
    output = io.StringIO()
    counts = SQLiteRecoveryAdapter()._salvage_store_stream(
        path,
        "context",
        output,
        100,
        100_000,
        1024,
        0,
        0,
        RecoveryWorkBudget(work_limits={"input_records": 100}),
    )
    assert counts[0] == counts[3] == 1 and not counts[2] and not counts[-1]
    row = json.loads(output.getvalue())
    assert row["payload"]["text_value"] == "safe"


def test_extract_vm_expenditure_survives_a_continuing_request(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    discover(app, repository, origin, str(uuid4()))
    stop_catalog(core_path.parent, "synthetic bounded source scan")
    budget = RecoveryBudget(max_work_units={"ref_source_vm_steps": 100})
    adapter = SQLiteRecoveryAdapter()
    outside = tmp_path.parent / (tmp_path.name + "-vm-output")
    outside.mkdir()
    first = adapter.extract_salvage(
        core_path.parent,
        outside / "vm-first.jsonl",
        budget=budget,
        request_id="vm-continuation",
    )
    before = _extract_state(core_path.parent)
    assert first.partial and before["ref_source_vm_steps"] == 100
    second = adapter.extract_salvage(
        core_path.parent,
        outside / "vm-second.jsonl",
        budget=budget,
        request_id="vm-continuation",
    )
    after = _extract_state(core_path.parent)
    assert second.partial and after["ref_source_vm_steps"] == 100
    assert all(after[key] >= value for key, value in before.items())


def test_crashed_vm_reservation_is_not_refunded_on_resume(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    discover(app, repository, origin, str(uuid4()))
    stop_catalog(core_path.parent, "synthetic interrupted source scan")
    before = {
        path.name: path.read_bytes()
        for path in core_path.parent.glob("core.sqlite3*")
        if path.is_file()
    }
    outside = tmp_path.parent / (tmp_path.name + "-vm-crash")
    outside.mkdir()
    ctx = multiprocessing.get_context("spawn")
    child = ctx.Process(
        target=_extract_process,
        args=(core_path.parent, outside / "crashed.jsonl", None, None, "vm"),
    )
    child.start()
    child.join(40)
    if child.is_alive():
        child.terminate()
        child.join(5)
        pytest.fail("VM reservation crash probe did not finish")
    assert child.exitcode == -signal.SIGKILL
    reserved = _extract_state(core_path.parent)["ref_source_vm_steps"]
    assert reserved == RecoveryWorkBudget()._max["ref_source_vm_steps"]
    resumed = SQLiteRecoveryAdapter().extract_salvage(
        core_path.parent, outside / "resumed.jsonl", request_id="shared-extraction"
    )
    assert resumed.partial
    assert _extract_state(core_path.parent)["ref_source_vm_steps"] == reserved
    assert {
        path.name: path.read_bytes()
        for path in core_path.parent.glob("core.sqlite3*")
        if path.is_file()
    } == before


def test_empty_event_and_rootless_claims_survive_without_context(acquisition, tmp_path):
    app, path, _, repository, origin, core_path, _ = acquisition
    empty_events = discover(app, repository, origin, str(uuid4())).enumerations
    assert empty_events and all(not event.links for event in empty_events)
    p4_fixtures.git(path, "symbolic-ref", "refs/notes/dangling", "refs/notes/missing")
    result = discover(
        app,
        repository,
        origin,
        str(uuid4()),
        ("refs/notes/dangling", "refs/notes/absent"),
    )
    rootless = [
        link.claim
        for event in result.enumerations
        for link in event.links
        if link.claim.root_object_oid is None
    ]
    assert {claim.presence_state for claim in rootless} == {"present", "absent"}
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    destination = tmp_path / "rootless"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    work = RecoveryWorkBudget()
    for candidate in reversed(scan.candidates):
        admit_ref_unit_atomic(
            destination, candidate["candidate_type"], candidate["payload"], work
        )
    receiver = GitCore(destination / "core.sqlite3")
    try:
        for event in empty_events:
            assert receiver.ref_enumeration(*event.event.identity, work) == event
        for claim in rootless:
            stored = receiver.ref_observation(claim.ref_observation_key, work)
            assert claim in stored.claims
            assert claim.root_object_oid is None
        assert not (destination / "context.sqlite3").exists()
    finally:
        receiver.close()
    empty = next(
        candidate
        for candidate in scan.candidates
        if candidate["candidate_type"] == "ref_enumeration"
        and candidate["payload"]["section"]["ref_enumeration_observations"][0][
            "link_count"
        ]
        == 0
    )
    forged = copy.deepcopy(empty["payload"])
    forged["section"]["ref_enumeration_observations"][0]["link_count"] = 1
    with pytest.raises((CoreFailure, ValueError)):
        admit_ref_unit_atomic(destination, "ref_enumeration", forged, work)
    assert not (destination / "p1-recovery-stop.json").exists()


def test_missing_event_link_does_not_discard_independent_claim(acquisition):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    db = connect(core_path, "core")
    try:
        db.execute("PRAGMA foreign_keys=OFF")
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_enumeration_links_delete'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_enumeration_links_delete")
        db.execute(
            "DELETE FROM ref_enumeration_links WHERE enumeration_origin_uuidv4=? AND enumeration_uuidv7=?",
            event.event.identity,
        )
        db.execute(trigger)
        db.commit()
        db.execute("PRAGMA foreign_keys=ON")
    finally:
        db.close()
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    assert any("ref_enumeration_observations" in item for item in scan.omissions)
    assert any(
        c["candidate_type"] == "ref_claim"
        and c["payload"]["claim"]["ref_observation_uuidv7"]
        == event.links[0].observation.ref_observation_key.ref_observation_uuidv7
        for c in scan.candidates
    )
    assert not any(
        c["candidate_type"] == "ref_enumeration"
        and c["payload"]["section"]["ref_enumeration_observations"][0][
            "enumeration_uuidv7"
        ]
        == event.event.enumeration_uuidv7
        for c in scan.candidates
    )


def test_existing_whole_event_rejects_reordered_membership(acquisition, tmp_path):
    app, path, _, repository, origin, core_path, _ = acquisition
    capture, _, _ = p4_fixtures.fixture_note(acquisition)
    p4_fixtures.git(
        path, "update-ref", "refs/notes/nested/second", capture.root.object_oid
    )
    events = discover(app, repository, origin, str(uuid4())).enumerations
    event = next(value for value in events if len(value.links) == 2)
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    candidate = next(
        value
        for value in scan.candidates
        if value["candidate_type"] == "ref_enumeration"
        and value["payload"]["section"]["ref_enumeration_observations"][0][
            "enumeration_uuidv7"
        ]
        == event.event.enumeration_uuidv7
    )
    destination = tmp_path / "ordered-event"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    work = RecoveryWorkBudget()
    assert not admit_ref_unit_atomic(
        destination, "ref_enumeration", candidate["payload"], work
    )
    assert admit_ref_unit_atomic(
        destination, "ref_enumeration", candidate["payload"], work
    )
    forged = copy.deepcopy(candidate["payload"])
    links = forged["section"]["ref_enumeration_links"]
    links[0]["position"], links[1]["position"] = (
        links[1]["position"],
        links[0]["position"],
    )
    with pytest.raises((CoreFailure, ValueError, sqlite3.IntegrityError)):
        admit_ref_unit_atomic(destination, "ref_enumeration", forged, work)
    receiver = GitCore(destination / "core.sqlite3")
    try:
        assert receiver.ref_enumeration(*event.event.identity, work) == event
    finally:
        receiver.close()
    assert not (destination / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("missing", ["claim", "subject"])
def test_missing_event_dependency_resolves_from_baseline_or_later_input(
    acquisition, tmp_path, missing
):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    link = event.links[0]
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        before = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    original_claim = next(
        item
        for item in before.candidates
        if item["candidate_type"] == "ref_claim"
        and item["payload"]["observation"]["ref_observation_uuidv7"]
        == link.observation.ref_observation_key.ref_observation_uuidv7
    )
    outside = tmp_path.parent / (tmp_path.name + "-dependencies")
    outside.mkdir()
    adapter = SQLiteRecoveryAdapter()
    backups = {}
    for seeded in (False, True):
        baseline = outside / f"baseline-{seeded}"
        baseline.mkdir()
        initialize(baseline / "core.sqlite3", "core", repository, str(uuid4()))
        core = GitCore(baseline / "core.sqlite3")
        try:
            core.admit_repository(repository)
            if seeded:
                core.admit_ref_observation(link.observation)
                if missing == "claim":
                    core.admit_ref_observation_claim(link.claim)
        finally:
            core.close()
        backups[seeded] = outside / f"backup-{seeded}"
        adapter.create_consistent_backup(
            baseline, backups[seeded], BackupScope.GIT_ONLY
        )
    db = connect(core_path, "core")
    try:
        db.execute("PRAGMA foreign_keys=OFF")
        table = "ref_observation_claims" if missing == "claim" else "ref_observations"
        trigger_name = f"p1_immutable_{table}_delete"
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name=?", (trigger_name,)
        ).fetchone()[0]
        db.execute(f"DROP TRIGGER {trigger_name}")
        if missing == "claim":
            db.execute(
                "DELETE FROM ref_observation_claims WHERE observation_origin_uuidv4=? "
                "AND ref_observation_uuidv7=? AND provenance=?",
                link.claim.identity,
            )
        else:
            db.execute(
                "DELETE FROM ref_observations WHERE observation_origin_uuidv4=? "
                "AND ref_observation_uuidv7=?",
                link.observation.ref_observation_key.key,
            )
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        damaged = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    assert any("dependency requires receiver" in value for value in damaged.omissions)
    event_candidate = next(
        item
        for item in damaged.candidates
        if item["candidate_type"] == "ref_enumeration"
        and item["payload"]["section"]["ref_enumeration_observations"][0][
            "enumeration_uuidv7"
        ]
        == event.event.enumeration_uuidv7
    )
    missing_key = "ref_observation_claims" if missing == "claim" else "ref_observations"
    assert not event_candidate["payload"]["section"][missing_key]
    bad = copy.deepcopy(original_claim)
    bad["payload"]["observation"]["visibility_scope"] = "rebound-subject"
    for label, seeded, inputs in (
        ("baseline", True, [event_candidate]),
        ("missing", False, [event_candidate]),
        ("later", False, [event_candidate, original_claim, bad]),
    ):
        destination = outside / f"restored-{label}"
        adapter.restore_backup(backups[seeded], destination, repository)
        input_file = outside / f"{label}.jsonl"
        input_file.write_text("".join(json.dumps(item) + "\n" for item in inputs))
        result = adapter.merge_salvage(destination, input_file)
        if label == "missing":
            assert result.deferred_units == 1 and result.admitted_units == 0
        else:
            assert result.deferred_units == 0 and result.admitted_units == (
                2 if label == "later" else 1
            )
            assert result.rejected_units == (1 if label == "later" else 0)
            receiver = GitCore(destination / "core.sqlite3")
            try:
                assert (
                    receiver.ref_enumeration(
                        *event.event.identity, RecoveryWorkBudget()
                    )
                    == event
                )
            finally:
                receiver.close()
        assert not (destination / "p1-recovery-stop.json").exists()
    limited = outside / "restored-pending-limit"
    adapter.restore_backup(backups[False], limited, repository)
    input_file = outside / "pending-limit.jsonl"
    input_file.write_text(
        "".join(json.dumps(item) + "\n" for item in (event_candidate, original_claim))
    )
    limited_result = adapter.merge_salvage(
        limited,
        input_file,
        RecoveryBudget(max_work_units={"pending_candidate_bytes": 1}),
        "pending-limit",
    )
    assert limited_result.admitted_units == 0
    assert limited_result.unprocessed_units >= 1 and not limited_result.input_complete
    assert not (limited / "p1-recovery-stop.json").exists()
    if missing == "subject":
        pending_claim = next(
            item
            for item in damaged.candidates
            if item["candidate_type"] == "ref_claim"
            and item["payload"]["observation"] is None
            and item["payload"]["claim"]["ref_observation_uuidv7"]
            == link.claim.ref_observation_key.ref_observation_uuidv7
        )
        original_subject = next(
            item
            for item in before.candidates
            if item["candidate_type"] == "ref_subject"
            and item["payload"]["observation"]["ref_observation_uuidv7"]
            == link.observation.ref_observation_key.ref_observation_uuidv7
        )
        destination = outside / "restored-later-subject"
        adapter.restore_backup(backups[False], destination, repository)
        input_file = outside / "later-subject.jsonl"
        input_file.write_text(
            "".join(
                json.dumps(item) + "\n" for item in (pending_claim, original_subject)
            )
        )
        result = adapter.merge_salvage(destination, input_file)
        assert result.admitted_units == 2 and result.deferred_units == 0
        receiver = GitCore(destination / "core.sqlite3")
        try:
            assert receiver.ref_observation(
                link.claim.ref_observation_key, RecoveryWorkBudget()
            ).claims == (link.claim,)
        finally:
            receiver.close()


@pytest.mark.parametrize("reverse", [False, True])
def test_transitive_pending_dependencies_are_order_independent(
    acquisition, tmp_path, reverse
):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    key = event.links[0].claim.ref_observation_key
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    pending_event = copy.deepcopy(
        next(
            c
            for c in scan.candidates
            if c["candidate_type"] == "ref_enumeration"
            and c["payload"]["section"]["ref_enumeration_observations"][0][
                "enumeration_uuidv7"
            ]
            == event.event.enumeration_uuidv7
        )
    )
    pending_event["payload"]["section"]["ref_observations"] = []
    pending_event["payload"]["section"]["ref_observation_claims"] = []
    pending_claim = copy.deepcopy(
        next(
            c
            for c in scan.candidates
            if c["candidate_type"] == "ref_claim"
            and c["payload"]["claim"]["ref_observation_uuidv7"]
            == key.ref_observation_uuidv7
        )
    )
    pending_claim["payload"]["observation"] = None
    subject = next(
        c
        for c in scan.candidates
        if c["candidate_type"] == "ref_subject"
        and c["payload"]["observation"]["ref_observation_uuidv7"]
        == key.ref_observation_uuidv7
    )
    outside = tmp_path.parent / (tmp_path.name + "-transitive")
    outside.mkdir()
    baseline = outside / "baseline"
    baseline.mkdir()
    initialize(baseline / "core.sqlite3", "core", repository, str(uuid4()))
    baseline_core = GitCore(baseline / "core.sqlite3")
    try:
        baseline_core.admit_repository(repository)
    finally:
        baseline_core.close()
    adapter = SQLiteRecoveryAdapter()
    backup = outside / "backup"
    adapter.create_consistent_backup(baseline, backup, BackupScope.GIT_ONLY)
    destination = outside / "fresh"
    adapter.restore_backup(backup, destination, repository)
    items = [pending_event, pending_claim, subject]
    if reverse:
        items.reverse()
    lines = [json.dumps(item) + "\n" for item in items]
    source_file = outside / "candidates.jsonl"
    source_file.write_text("".join(lines))
    receipt = adapter.merge_salvage(destination, source_file, request_id="chain")
    assert receipt.admitted_units == 3 and receipt.deferred_units == 0, (
        receipt.rejections
    )
    receiver = GitCore(destination / "core.sqlite3")
    try:
        assert (
            receiver.ref_enumeration(*event.event.identity, RecoveryWorkBudget())
            == event
        )
    finally:
        receiver.close()
    assert not (destination / "p1-recovery-stop.json").exists()
    if not reverse:
        # The first dependency retry consumes the remainder; a continuing
        # request may not forget that work or manufacture an event.
        bounded_destination = outside / "fresh-bounded"
        adapter.restore_backup(backup, bounded_destination, repository)
        decode_limit = 3 * (
            sum(len(line.encode()) for line in lines) + len(lines[0].encode())
        )
        budget = RecoveryBudget(max_work_units={"json_decode_bytes": decode_limit})
        limited = adapter.merge_salvage(
            bounded_destination, source_file, budget=budget, request_id="bounded-chain"
        )
        assert not limited.input_complete and limited.unprocessed_units > 0
        state_path = bounded_destination / "p1-recovery-request-bounded-chain.json"
        before_retry = json.loads(state_path.read_text())["cumulative_usage"]
        assert before_retry["json_decode_bytes"] == decode_limit
        adapter.merge_salvage(
            bounded_destination, source_file, budget=budget, request_id="bounded-chain"
        )
        assert json.loads(state_path.read_text())["cumulative_usage"] == before_retry
        bounded_core = GitCore(bounded_destination / "core.sqlite3")
        try:
            assert not bounded_core.sql("SELECT 1 FROM ref_enumeration_observations")
        finally:
            bounded_core.close()
        assert not (bounded_destination / "p1-recovery-stop.json").exists()

        missing_destination = outside / "fresh-missing"
        adapter.restore_backup(backup, missing_destination, repository)
        missing_file = outside / "missing-subject.jsonl"
        missing_file.write_text("".join(lines[:2]))
        missing = adapter.merge_salvage(missing_destination, missing_file)
        assert missing.deferred_units == 2 and missing.input_complete
        assert missing.admitted_units == missing.unprocessed_units == 0
        assert not (missing_destination / "p1-recovery-stop.json").exists()


def test_lossless_ref_and_competing_claims_survive_shuffled_replay(
    acquisition, tmp_path
):
    app, _, fmt, repository, origin, core_path, _ = acquisition
    observation = RefObservation(
        RefObservationKey(origin, new_uuid7()),
        repository,
        b"refs/notes/\xff",
        "local-test",
        "local",
        1234567,
    )
    app.core.admit_ref_observation(observation)
    provenance = p1_fixtures.provenance("first")
    a = RefObservationClaim(
        observation.ref_observation_key,
        provenance,
        "present",
        root_object_oid=OID(fmt, "a" * (40 if fmt == "sha1" else 64)),
    )
    b = replace(
        a,
        provenance=replace(provenance, coordinate="other"),
        root_object_oid=OID(fmt, "b" * (40 if fmt == "sha1" else 64)),
    )
    app.core.admit_ref_observation_claim(a)
    app.core.admit_ref_observation_claim(b)
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    dest = tmp_path / "conflicts"
    dest.mkdir()
    initialize(dest / "core.sqlite3", "core", repository, str(uuid4()))
    receiver = GitCore(dest / "core.sqlite3")
    try:
        work = RecoveryWorkBudget()
        for candidate in reversed(scan.candidates):
            with account_verification(work):
                admit_ref_unit(
                    receiver, candidate["candidate_type"], candidate["payload"], work
                )
        result = receiver.ref_observation(observation.ref_observation_key, work)
        assert result.ref_observation.ref_name_bytes == b"refs/notes/\xff"
        assert result.conflict and set(result.claims) == {a, b}
        candidate = next(
            c for c in scan.candidates if c["candidate_type"] == "ref_subject"
        )
        forged = dict(
            candidate["payload"],
            observation=dict(
                candidate["payload"]["observation"], source_attribution="changed"
            ),
        )
        with pytest.raises((CoreFailure, sqlite3.IntegrityError)):
            with account_verification(work):
                admit_ref_unit(receiver, "ref_subject", forged, work)
        assert not (dest / "p1-recovery-stop.json").exists()
    finally:
        receiver.close()


def test_receiver_replays_shuffled_original_units(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    events = discover(app, repository, origin, str(uuid4()), ("refs/notes/missing",))
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    destination = tmp_path / "receiver"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    core = GitCore(destination / "core.sqlite3")
    try:
        work = RecoveryWorkBudget()
        for candidate in reversed(scan.candidates):
            with account_verification(work):
                admit_ref_unit(
                    core, candidate["candidate_type"], candidate["payload"], work
                )
        for event in events.enumerations:
            assert core.ref_enumeration(*event.event.identity, work) == event
        for candidate in reversed(scan.candidates):
            with account_verification(work):
                assert admit_ref_unit(
                    core, candidate["candidate_type"], candidate["payload"], work
                )
    finally:
        core.close()


def test_notes_copy_requires_rechecked_original_claim_and_proof(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    events = discover(app, repository, origin, str(uuid4())).enumerations
    claim, other_claim = (event.links[0].claim for event in events)
    app.inventory_ref(claim)
    app.acquire_ref_note(claim, target)
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    assert not scan.omissions
    assert {"ref_group", "ref_evidence", "ref_note"} <= {
        c["candidate_type"] for c in scan.candidates
    }
    destination = tmp_path / "notes-receiver"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    core = GitCore(destination / "core.sqlite3")
    try:
        work = RecoveryWorkBudget()
        for candidate in reversed(scan.candidates):
            with account_verification(work):
                admit_ref_unit(
                    core, candidate["candidate_type"], candidate["payload"], work
                )
        projection = core.notes_mapping_projection(
            claim, target, "git-notes", "1", "native-notes-tree", work
        )
        assert len(projection.evidence) >= 1
        assert (
            core.read_ref_note(claim, projection.evidence[0].mapping, work)
            == b"\0\xffbinary\r\n"
        )
        with pytest.raises(CoreFailure) as unrelated:
            core.read_ref_note(other_claim, projection.evidence[0].mapping, work)
        assert unrelated.value.code == "NOTES_ROLE_UNAVAILABLE"
        for candidate in scan.candidates:
            with account_verification(work):
                assert admit_ref_unit(
                    core, candidate["candidate_type"], candidate["payload"], work
                )
    finally:
        core.close()


@pytest.mark.parametrize("missing", ["claim", "mapping", "evidence"])
def test_notes_dependencies_resolve_without_rebinding_original_evidence(
    acquisition, tmp_path, missing
):
    app, _, _, repository, origin, core_path, _ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    claim = event.links[0].claim
    app.inventory_ref(claim)
    app.acquire_ref_note(claim, target)
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        original = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    claim_candidate = next(
        item
        for item in original.candidates
        if item["candidate_type"] == "ref_claim"
        and item["payload"]["claim"]["ref_observation_uuidv7"]
        == claim.ref_observation_key.ref_observation_uuidv7
    )
    outside = tmp_path.parent / (tmp_path.name + "-notes-dependencies")
    outside.mkdir()
    adapter = SQLiteRecoveryAdapter()
    backups = {}
    for seeded in (False, True):
        baseline = outside / f"baseline-{seeded}"
        baseline.mkdir()
        initialize(baseline / "core.sqlite3", "core", repository, str(uuid4()))
        core = GitCore(baseline / "core.sqlite3")
        try:
            core.admit_repository(repository)
            if seeded:
                core.admit_ref_observation(event.links[0].observation)
                core.admit_ref_observation_claim(claim)
        finally:
            core.close()
        backups[seeded] = outside / f"backup-{seeded}"
        adapter.create_consistent_backup(
            baseline, backups[seeded], BackupScope.GIT_ONLY
        )
    table = {
        "claim": "ref_observation_claims",
        "mapping": "notes_mappings",
        "evidence": "notes_mapping_evidence",
    }[missing]
    db = connect(core_path, "core")
    try:
        db.execute("PRAGMA foreign_keys=OFF")
        name = f"p1_immutable_{table}_delete"
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name=?", (name,)
        ).fetchone()[0]
        db.execute(f"DROP TRIGGER {name}")
        db.execute(f"DELETE FROM {table}")
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        damaged = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    note = next(
        item
        for item in damaged.candidates
        if item["candidate_type"] == "ref_note"
        and item["payload"]["unit"]["ref_observation_uuidv7"]
        == claim.ref_observation_key.ref_observation_uuidv7
    )
    assert damaged.omissions
    if missing == "claim":
        assert note["payload"]["claim"] is None
    cases = [("baseline", True, [note])]
    if missing == "claim":
        cases += [
            ("later", False, [note, claim_candidate]),
            ("unavailable", False, [note]),
        ]
    for label, seeded, inputs in cases:
        destination = outside / f"restored-{label}"
        adapter.restore_backup(backups[seeded], destination, repository)
        input_file = outside / f"{label}.jsonl"
        input_file.write_text("".join(json.dumps(item) + "\n" for item in inputs))
        result = adapter.merge_salvage(destination, input_file)
        receiver = GitCore(destination / "core.sqlite3")
        try:
            work = RecoveryWorkBudget()
            if label == "unavailable":
                assert result.deferred_units == 1 and not receiver.sql(
                    "SELECT 1 FROM ref_retained_notes"
                )
            else:
                assert result.deferred_units == result.rejected_units == 0
                projection = receiver.notes_mapping_projection(
                    claim, target, "git-notes", "1", "native-notes-tree", work
                )
                assert (
                    receiver.read_ref_note(claim, projection.evidence[0].mapping, work)
                    == b"\0\xffbinary\r\n"
                )
        finally:
            receiver.close()
        assert not (destination / "p1-recovery-stop.json").exists()


def test_pending_note_cannot_rebind_existing_claim_to_another_root(
    acquisition, tmp_path
):
    app, _, fmt, repository, origin, core_path, _ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    claim = event.links[0].claim
    app.acquire_ref_note(claim, target)
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    note = copy.deepcopy(
        next(c for c in scan.candidates if c["candidate_type"] == "ref_note")
    )
    note["payload"]["claim"] = None
    destination = tmp_path / "other-root"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    other = replace(
        claim, root_object_oid=OID(fmt, "f" * (40 if fmt == "sha1" else 64))
    )
    core = GitCore(destination / "core.sqlite3")
    try:
        core.admit_repository(repository)
        core.admit_ref_observation(event.links[0].observation)
        core.admit_ref_observation_claim(other)
    finally:
        core.close()
    with pytest.raises((CoreFailure, ValueError)):
        admit_ref_unit_atomic(
            destination, "ref_note", note["payload"], RecoveryWorkBudget()
        )
    core = GitCore(destination / "core.sqlite3")
    try:
        assert core.ref_observation(
            claim.ref_observation_key, RecoveryWorkBudget()
        ).claims == (other,)
        assert not core.sql("SELECT 1 FROM ref_retained_notes")
    finally:
        core.close()
    assert not (destination / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("damage", ["body", "proof", "root"])
def test_missing_claim_never_stages_an_unproven_note(acquisition, damage):
    app, _, fmt, repository, origin, core_path, _ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    db = connect(core_path, "core")
    try:
        db.execute("PRAGMA foreign_keys=OFF")
        names = (
            "p1_immutable_ref_observation_claims_delete",
            "p1_immutable_ref_retained_notes_update",
        )
        triggers = [
            db.execute(
                "SELECT sql FROM sqlite_schema WHERE name=?", (name,)
            ).fetchone()[0]
            for name in names
        ]
        for name in names:
            db.execute(f"DROP TRIGGER {name}")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("DELETE FROM ref_observation_claims")
        if damage == "body":
            db.execute("UPDATE ref_retained_notes SET body=zeroblob(size)")
        elif damage == "proof":
            db.execute("UPDATE ref_retained_notes SET proof_bundle='[]'")
        else:
            db.execute(
                "UPDATE ref_retained_notes SET root_object_oid=?",
                ("f" * (40 if fmt == "sha1" else 64),),
            )
        db.execute("PRAGMA ignore_check_constraints=OFF")
        for trigger in triggers:
            db.execute(trigger)
        db.commit()
    finally:
        db.close()
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    assert not any(item["candidate_type"] == "ref_note" for item in scan.candidates)
    assert any("ref_retained_notes" in item for item in scan.omissions)


@pytest.mark.parametrize("damage", ["body", "proof"])
def test_damaged_note_copy_is_omitted_without_losing_valid_sibling(acquisition, damage):
    app, _, _, repository, origin, core_path, _ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    events = discover(app, repository, origin, str(uuid4())).enumerations
    for event in events:
        app.acquire_ref_note(event.links[0].claim, target)
    copies = [
        r[0]
        for r in app.core.sql(
            "SELECT physical_copy_uuidv4 FROM ref_retained_notes ORDER BY physical_copy_uuidv4"
        )
    ]
    db = connect(core_path, "core")
    try:
        db.execute("PRAGMA foreign_keys=OFF")
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_retained_notes_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        if damage == "body":
            db.execute(
                "UPDATE ref_retained_notes SET body=zeroblob(size) WHERE physical_copy_uuidv4=?",
                (copies[1],),
            )
        else:
            db.execute(
                "UPDATE ref_retained_notes SET proof_bundle='[]' WHERE physical_copy_uuidv4=?",
                (copies[1],),
            )
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.execute(trigger)
        db.commit()
        db.execute("PRAGMA foreign_keys=ON")
    finally:
        db.close()
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    bodies = [c for c in scan.candidates if c["candidate_type"] == "ref_note"]
    assert len(bodies) == 1
    assert bodies[0]["payload"]["unit"]["physical_copy_uuidv4"] == copies[0]
    assert any("ref_retained_notes" in item for item in scan.omissions)


@pytest.mark.parametrize("forgery", ["body", "proof", "root"])
def test_invalid_candidate_rolls_back_and_actual_target_damage_stops(
    acquisition, tmp_path, forgery
):
    app, _, _, repository, origin, core_path, _ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    note = next(c for c in scan.candidates if c["candidate_type"] == "ref_note")
    forged = copy.deepcopy(note["payload"])
    if forgery == "body":
        forged["unit"]["body_hex"] = "ff" + forged["unit"]["body_hex"][2:]
        assert forged["unit"]["body_hex"] != note["payload"]["unit"]["body_hex"]
    elif forgery == "proof":
        forged["unit"]["proof_bundle_json"] = "[]"
    else:
        fmt, value = forged["claim"]["root_object_oid"]
        forged["claim"]["root_object_oid"] = [fmt, "f" * len(value)]
    destination = tmp_path / "atomic-receiver"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    with pytest.raises((CoreFailure, ValueError)):
        admit_ref_unit_atomic(destination, "ref_note", forged, RecoveryWorkBudget())
    receiver = GitCore(destination / "core.sqlite3")
    try:
        assert receiver.sql("SELECT 1 FROM ref_observations") == []
        assert receiver.sql("SELECT 1 FROM ref_observation_claims") == []
        assert receiver.sql("SELECT 1 FROM ref_retained_notes") == []
    finally:
        receiver.close()
    assert not (destination / "p1-recovery-stop.json").exists()
    assert not admit_ref_unit_atomic(
        destination, "ref_note", note["payload"], RecoveryWorkBudget()
    )
    db = connect(destination / "core.sqlite3", "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_retained_notes_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE ref_retained_notes SET body=zeroblob(size)")
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    with pytest.raises(CoreFailure) as stopped:
        admit_ref_unit_atomic(
            destination, "ref_note", note["payload"], RecoveryWorkBudget()
        )
    assert stopped.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (destination / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("error_kind", ["value", "sqlite_corrupt", "core_corrupt"])
def test_receiver_work_callback_errors_keep_identity_and_do_not_stop(
    acquisition, tmp_path, error_kind
):
    app, _, _, repository, origin, core_path, _ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    note = next(c for c in scan.candidates if c["candidate_type"] == "ref_note")
    destination = tmp_path / "callback-receiver"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    if error_kind == "value":
        failure = ValueError("callback only")
    elif error_kind == "sqlite_corrupt":
        failure = sqlite3.DatabaseError("callback only")
        failure.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
    else:
        failure = CoreFailure("AUTHORITATIVE_CORRUPTION", "callback", "callback only")

    class Failing(RecoveryWorkBudget):
        def require(self, unit, amount=1):
            if unit == "verification_bytes":
                raise failure
            return super().require(unit, amount)

    with pytest.raises(type(failure)) as caught:
        admit_ref_unit_atomic(destination, "ref_note", note["payload"], Failing())
    assert caught.value is failure
    assert not (destination / "p1-recovery-stop.json").exists()
    receiver = GitCore(destination / "core.sqlite3")
    try:
        assert receiver.sql("SELECT 1 FROM ref_observations") == []
    finally:
        receiver.close()


def test_receiver_work_callback_cannot_borrow_body_access(
    acquisition, tmp_path, monkeypatch
):
    app, _, _, repository, origin, core_path, _ = acquisition
    _, target, _ = p4_fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    connection = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    note = next(c for c in scan.candidates if c["candidate_type"] == "ref_note")
    destination = tmp_path / "callback-capability"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    admit_ref_unit_atomic(
        destination, "ref_note", note["payload"], RecoveryWorkBudget()
    )
    original = GitCore.for_transaction

    class Probe(RecoveryWorkBudget):
        core = None
        denied = 0

        def require(self, unit, amount=1):
            if unit == "verification_bytes" and self.core is not None:
                try:
                    self.core._db.execute(
                        "SELECT body FROM ref_retained_notes LIMIT 1"
                    ).fetchall()
                except sqlite3.DatabaseError:
                    self.denied += 1
                else:
                    pytest.fail("callback borrowed protected body access")
            return super().require(unit, amount)

    probe = Probe()

    @contextmanager
    def record_capability(db):
        with original(db) as capability:
            probe.core = capability
            yield capability

    monkeypatch.setattr(GitCore, "for_transaction", record_capability)
    assert admit_ref_unit_atomic(destination, "ref_note", note["payload"], probe)
    assert probe.denied > 0
    assert not (destination / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("empty", [False, True])
def test_inventory_coverage_rechecks_original_whole_group(
    p1_core_fixture, tmp_path, fmt, empty
):
    core, path, repository = p1_core_fixture
    proof = proof_fixture(p1_core_fixture, fmt=fmt, empty=empty)
    core.admit_ref_coverage_proof(proof, Budget())
    unsupported = CoreCoverageScope(
        "ref_observation",
        (*proof.group.ref_claim.ref_observation_key.key, "ref-enumeration"),
    )
    core.admit_coverage_scope(unsupported)
    core.admit_coverage(CoverageClaim(unsupported, 20, "complete"))
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    assert not scan.omissions
    assert "ref_coverage_proof" in {c["candidate_type"] for c in scan.candidates}
    destination = tmp_path / "coverage-receiver"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    receiver = GitCore(destination / "core.sqlite3")
    try:
        work = RecoveryWorkBudget()
        for candidate in reversed(scan.candidates):
            with account_verification(work):
                admit_ref_unit(
                    receiver, candidate["candidate_type"], candidate["payload"], work
                )
        assert receiver.coverage(proof.coverage_claim.scope, work).state == "complete"
        assert receiver.coverage(proof.coverage_claim.scope, work).known_empty is empty
        assert receiver.coverage(unsupported, work).state == "unknown"
        assert len(receiver.ref_coverage_proofs(proof.coverage_claim, work)) == 2
        for candidate in scan.candidates:
            with account_verification(work):
                assert (
                    admit_ref_unit(
                        receiver,
                        candidate["candidate_type"],
                        candidate["payload"],
                        work,
                    )
                    is True
                )
    finally:
        receiver.close()


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("damage", ["missing", "reordered", "extra", "malformed"])
def test_whole_inventory_rejects_changed_group_membership(
    p1_core_fixture, tmp_path, fmt, damage
):
    core, path, repository = p1_core_fixture
    width = 40 if fmt == "sha1" else 64
    targets = ("a" * width, "b" * width)
    notes = (OID(fmt, "c" * width), OID(fmt, "d" * width))
    root = tree(
        [("100644", target, note) for target, note in zip(targets, notes, strict=True)],
        fmt,
    )
    observation = RefObservation(
        RefObservationKey(str(uuid4()), new_uuid7()),
        repository,
        b"refs/notes/inventory",
        "issuer",
        "scope",
        1,
    )
    claim = RefObservationClaim(
        observation.ref_observation_key,
        p1_fixtures.provenance("claim"),
        "present",
        root_object_oid=root.object_oid,
    )
    group = NotesMappingGroup(
        claim,
        "git-notes",
        "1",
        "native-notes-tree",
        "all-notes-mappings",
        "complete",
        tuple(
            (target, note.object_oid, target)
            for target, note in zip(targets, notes, strict=True)
        ),
        p1_fixtures.provenance("whole"),
    )
    scope = CoreCoverageScope(
        "ref_observation",
        (*observation.ref_observation_key.key, "notes-mapping-inventory"),
    )
    coverage = CoverageClaim(scope, 20, "complete")
    proof = RefNotesInventoryCoverageProof(
        coverage,
        group,
        Provenance(
            "receiver",
            "source",
            "whole",
            "git-native-notes-inventory",
            "1",
            "receiver_intrinsic",
        ),
        (root,),
    )
    core.admit_ref_observation(observation)
    core.admit_ref_observation_claim(claim)
    core.admit_notes_mapping_group(group, Budget())
    core.admit_coverage_scope(scope)
    core.admit_coverage(coverage)
    core.admit_ref_coverage_proof(proof, Budget())
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    candidate = next(
        c for c in scan.candidates if c["candidate_type"] == "ref_coverage_proof"
    )
    forged = copy.deepcopy(candidate["payload"])
    original_members = json.loads(forged["group"]["membership_json"])
    if damage == "missing":
        altered = original_members[:1]
    elif damage == "reordered":
        altered = list(reversed(original_members))
    elif damage == "extra":
        altered = original_members + [["e" * width, "f" * width, "e" * width]]
    else:
        altered = None
    forged["group"]["membership_json"] = "{" if altered is None else encode(altered)
    destination = tmp_path / "whole-inventory"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    work = RecoveryWorkBudget()
    with pytest.raises((CoreFailure, ValueError)):
        admit_ref_unit_atomic(destination, "ref_coverage_proof", forged, work)
    receiver = GitCore(destination / "core.sqlite3")
    try:
        assert receiver.sql("SELECT 1 FROM ref_observations") == []
        assert receiver.sql("SELECT 1 FROM notes_mapping_groups") == []
    finally:
        receiver.close()
    assert not (destination / "p1-recovery-stop.json").exists()
    assert not admit_ref_unit_atomic(
        destination, "ref_coverage_proof", candidate["payload"], work
    )
    receiver = GitCore(destination / "core.sqlite3")
    try:
        assert receiver.coverage(scope, work).state == "complete"
    finally:
        receiver.close()


def test_partial_groups_are_not_unioned_into_complete_coverage(
    p1_core_fixture, tmp_path
):
    core, path, repository = p1_core_fixture
    proof = proof_fixture(p1_core_fixture)
    for coordinate in ("partial-one", "partial-two"):
        partial = replace(
            proof.group, status="partial", provenance=p1_fixtures.provenance(coordinate)
        )
        core.admit_notes_mapping_group(partial, Budget())
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    assert not any(c["candidate_type"] == "ref_coverage_proof" for c in scan.candidates)
    destination = tmp_path / "partial-groups"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    work = RecoveryWorkBudget()
    for candidate in reversed(scan.candidates):
        admit_ref_unit_atomic(
            destination, candidate["candidate_type"], candidate["payload"], work
        )
    receiver = GitCore(destination / "core.sqlite3")
    try:
        assert len(receiver.sql("SELECT 1 FROM notes_mapping_groups")) == 3
        assert receiver.coverage(proof.coverage_claim.scope, work).state == "unknown"
    finally:
        receiver.close()


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("missing", ["subject", "claim", "group", "coverage_claim"])
def test_inventory_dependencies_resolve_from_baseline_or_later_input(
    p1_core_fixture, tmp_path, fmt, missing
):
    core, path, repository = p1_core_fixture
    proof = proof_fixture(p1_core_fixture, fmt=fmt)
    core.admit_ref_coverage_proof(proof, Budget())
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        before = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    original_claim = next(
        c for c in before.candidates if c["candidate_type"] == "ref_claim"
    )
    original_coverage = next(
        c for c in before.candidates if c["candidate_type"] == "ref_coverage"
    )
    outside = tmp_path.parent / (tmp_path.name + "-inventory-dependencies")
    outside.mkdir()
    adapter = SQLiteRecoveryAdapter()
    backups = {}
    for seeded in (False, True):
        baseline = outside / f"baseline-{seeded}"
        baseline.mkdir()
        initialize(baseline / "core.sqlite3", "core", repository, str(uuid4()))
        destination_core = GitCore(baseline / "core.sqlite3")
        try:
            destination_core.admit_repository(repository)
            if seeded:
                subject = proof.group.ref_claim.ref_observation_key
                source_subject = core.ref_observation(subject, Budget()).ref_observation
                destination_core.admit_ref_observation(source_subject)
                destination_core.admit_ref_observation_claim(proof.group.ref_claim)
                destination_core.admit_coverage_scope(proof.coverage_claim.scope)
                destination_core.admit_coverage(proof.coverage_claim)
        finally:
            destination_core.close()
        backups[seeded] = outside / f"backup-{seeded}"
        adapter.create_consistent_backup(
            baseline, backups[seeded], BackupScope.GIT_ONLY
        )
    table = {
        "subject": "ref_observations",
        "claim": "ref_observation_claims",
        "group": "notes_mapping_groups",
        "coverage_claim": "coverage_claims",
    }[missing]
    db = connect(path, "core")
    try:
        db.execute("PRAGMA foreign_keys=OFF")
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=? "
            "AND sql LIKE '%DELETE%'",
            (table,),
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        db.execute(f"DELETE FROM {table}")
        for _, sql in triggers:
            db.execute(sql)
        db.commit()
    finally:
        db.close()
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        damaged = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    assert damaged.omissions
    candidate = next(
        c for c in damaged.candidates if c["candidate_type"] == "ref_coverage_proof"
    )
    for label, seeded, inputs in (
        ("baseline", True, [candidate]),
        ("later", False, [candidate, original_claim, original_coverage]),
    ):
        destination = outside / f"restored-{label}"
        adapter.restore_backup(backups[seeded], destination, repository)
        input_file = outside / f"{label}.jsonl"
        input_file.write_text("".join(json.dumps(item) + "\n" for item in inputs))
        result = adapter.merge_salvage(destination, input_file)
        assert result.deferred_units == result.rejected_units == 0, result.rejections
        receiver = GitCore(destination / "core.sqlite3")
        try:
            projection = receiver.coverage(
                proof.coverage_claim.scope, RecoveryWorkBudget()
            )
            assert projection.state == "complete" and not projection.known_empty
        finally:
            receiver.close()
        assert not (destination / "p1-recovery-stop.json").exists()
    if missing == "coverage_claim":
        destination = outside / "restored-missing-coverage"
        adapter.restore_backup(backups[False], destination, repository)
        input_file = outside / "missing-coverage.jsonl"
        input_file.write_text(json.dumps(candidate) + "\n")
        result = adapter.merge_salvage(destination, input_file)
        assert result.deferred_units == 1 and result.admitted_units == 0
        receiver = GitCore(destination / "core.sqlite3")
        try:
            assert not receiver.sql("SELECT 1 FROM ref_observations")
            assert not receiver.sql("SELECT 1 FROM ref_observation_claims")
            assert not receiver.sql("SELECT 1 FROM notes_mapping_groups")
        finally:
            receiver.close()


def test_older_salvaged_complete_cannot_replace_newer_partial(
    p1_core_fixture, tmp_path
):
    core, path, repository = p1_core_fixture
    proof = proof_fixture(p1_core_fixture)
    core.admit_ref_coverage_proof(proof, Budget())
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    subject = next(c for c in scan.candidates if c["candidate_type"] == "ref_subject")
    coverage = next(c for c in scan.candidates if c["candidate_type"] == "ref_coverage")
    coverage_proof = next(
        c for c in scan.candidates if c["candidate_type"] == "ref_coverage_proof"
    )
    destination = tmp_path / "newer"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    receiver = GitCore(destination / "core.sqlite3")
    try:
        work = RecoveryWorkBudget()
        with account_verification(work):
            admit_ref_unit(
                receiver, subject["candidate_type"], subject["payload"], work
            )
        receiver.admit_coverage_scope(proof.coverage_claim.scope)
        receiver.admit_coverage(
            CoverageClaim(proof.coverage_claim.scope, 30, "partial")
        )
        for candidate in (coverage, coverage_proof):
            with account_verification(work):
                assert (
                    admit_ref_unit(
                        receiver,
                        candidate["candidate_type"],
                        candidate["payload"],
                        work,
                    )
                    is None
                )
        assert receiver.coverage(proof.coverage_claim.scope, work).state == "partial"
    finally:
        receiver.close()

    atomic_destination = tmp_path / "newer-atomic"
    atomic_destination.mkdir()
    initialize(atomic_destination / "core.sqlite3", "core", repository, str(uuid4()))
    receiver = GitCore(atomic_destination / "core.sqlite3")
    try:
        receiver.admit_repository(repository)
        receiver.admit_ref_observation(
            observation_from_wire(subject["payload"]["observation"])
        )
        receiver.admit_coverage_scope(proof.coverage_claim.scope)
        receiver.admit_coverage(
            CoverageClaim(proof.coverage_claim.scope, 30, "partial")
        )
    finally:
        receiver.close()
    assert (
        admit_ref_unit_atomic(
            atomic_destination,
            "ref_coverage_proof",
            coverage_proof["payload"],
            RecoveryWorkBudget(),
        )
        is None
    )
    receiver = GitCore(atomic_destination / "core.sqlite3")
    try:
        assert not receiver.sql("SELECT 1 FROM notes_mapping_groups")
        assert not receiver.sql("SELECT 1 FROM ref_observation_claims")
        assert (
            receiver.coverage(proof.coverage_claim.scope, RecoveryWorkBudget()).state
            == "partial"
        )
    finally:
        receiver.close()


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_corrupt_historical_source_coverage_cannot_prove_completeness(
    p1_core_fixture, tmp_path, fmt
):
    core, path, repository = p1_core_fixture
    proof = proof_fixture(p1_core_fixture, fmt=fmt)
    core.admit_ref_coverage_proof(proof, Budget())
    core.admit_coverage(CoverageClaim(proof.coverage_claim.scope, 30, "partial"))
    _damage_historical_coverage(path)
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    assert any(
        "coverage_claims" in value and "invalid stored text" in value
        for value in scan.omissions
    )
    assert not any(c["candidate_type"] == "ref_coverage_proof" for c in scan.candidates)
    destination = tmp_path / "source-coverage"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    work = RecoveryWorkBudget()
    for candidate in reversed(scan.candidates):
        admit_ref_unit_atomic(
            destination, candidate["candidate_type"], candidate["payload"], work
        )
    receiver = GitCore(destination / "core.sqlite3")
    try:
        assert receiver.coverage(proof.coverage_claim.scope, work).state == "partial"
    finally:
        receiver.close()
    assert not (destination / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_corrupt_historical_target_coverage_stops_during_salvage_replay(
    p1_core_fixture, tmp_path, fmt
):
    core, path, repository = p1_core_fixture
    proof = proof_fixture(p1_core_fixture, fmt=fmt)
    core.admit_coverage(CoverageClaim(proof.coverage_claim.scope, 30, "partial"))
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    candidate = next(
        c
        for c in scan.candidates
        if c["candidate_type"] == "ref_coverage"
        and c["payload"]["history"]
        and c["payload"]["history"][-1]["observed_at_us"] == 30
    )
    destination = tmp_path / "target-coverage"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    work = RecoveryWorkBudget()
    assert not admit_ref_unit_atomic(
        destination, "ref_coverage", candidate["payload"], work
    )
    _damage_historical_coverage(destination / "core.sqlite3")
    with pytest.raises(CoreFailure) as stopped:
        admit_ref_unit_atomic(destination, "ref_coverage", candidate["payload"], work)
    assert stopped.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (destination / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("empty", [False, True])
def test_inventory_coverage_survives_full_recovery(
    p1_core_fixture, tmp_path, fmt, empty
):
    core, path, repository = p1_core_fixture
    adapter = SQLiteRecoveryAdapter()
    outside = tmp_path.parent / (tmp_path.name + "-coverage-recovery")
    outside.mkdir()
    backup = outside / "baseline"
    adapter.create_consistent_backup(path.parent, backup, BackupScope.GIT_ONLY)
    proof = proof_fixture(p1_core_fixture, fmt=fmt, empty=empty)
    core.admit_ref_coverage_proof(proof, Budget())
    stop_catalog(path.parent, "synthetic coverage recovery")
    salvage = outside / "coverage.jsonl"
    extracted = adapter.extract_salvage(path.parent, salvage)
    assert not extracted.partial, extracted.unreadable_scope
    destination = outside / "restored"
    adapter.restore_backup(backup, destination, repository)
    merged = adapter.merge_salvage(destination, salvage)
    assert merged.rejected_units == merged.deferred_units == 0, merged.rejections
    receiver = GitCore(destination / "core.sqlite3")
    try:
        projection = receiver.coverage(proof.coverage_claim.scope, RecoveryWorkBudget())
        assert projection.state == "complete" and projection.known_empty is empty
    finally:
        receiver.close()
    assert adapter.activate(destination, outside / "active").clean_operational


def test_standalone_mapping_never_creates_evidence_or_body(p1_core_fixture, tmp_path):
    core, path, repository = p1_core_fixture
    root = OID("sha1", "a" * 40)
    mapping = NotesMapping(
        root,
        "git-notes",
        "1",
        "native-notes-tree",
        OID("sha1", "b" * 40),
        OID("sha1", "c" * 40),
        "b" * 40,
    )
    core.admit_notes_mapping(mapping, Budget())
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            connection, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        connection.close()
    candidate = next(
        c for c in scan.candidates if c["candidate_type"] == "ref_mapping_content"
    )
    destination = tmp_path / "mapping-only"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", repository, str(uuid4()))
    assert not admit_ref_unit_atomic(
        destination,
        candidate["candidate_type"],
        candidate["payload"],
        RecoveryWorkBudget(),
    )
    receiver = GitCore(destination / "core.sqlite3")
    try:
        assert len(receiver.sql("SELECT 1 FROM notes_mappings")) == 1
        assert not receiver.sql("SELECT 1 FROM notes_mapping_claims")
        assert not receiver.sql("SELECT 1 FROM notes_mapping_evidence")
        assert not receiver.sql("SELECT 1 FROM ref_retained_notes")
    finally:
        receiver.close()


def test_extract_request_budget_survives_retry_and_operational_loss(
    acquisition, tmp_path
):
    app, _, _, repository, origin, core_path, op_path = acquisition
    p4_fixtures.fixture_note(acquisition)
    discover(app, repository, origin, str(uuid4()))
    stop_catalog(core_path.parent, "synthetic extraction budget")
    outside = tmp_path.parent / (tmp_path.name + "-accounting")
    outside.mkdir()
    adapter = SQLiteRecoveryAdapter()
    b = RecoveryBudget(max_input_records=1)
    first = adapter.extract_salvage(
        core_path.parent, outside / "first.jsonl", budget=b, request_id="same"
    )
    assert first.partial
    states = [
        p
        for p in core_path.parent.glob("p1-recovery-request-extract-*.json")
        if not p.name.endswith((".reserved.json", ".source.json"))
    ]
    assert len(states) == 1
    before = json.loads(states[0].read_text())["cumulative_usage"]
    assert before["input_scan_bytes"] > 0
    op_path.unlink()
    other_output = tmp_path.parent / (tmp_path.name + "-different-output")
    other_output.mkdir()
    second = adapter.extract_salvage(
        core_path.parent, other_output / "second.jsonl", budget=b, request_id="same"
    )
    assert second.partial
    after = json.loads(states[0].read_text())["cumulative_usage"]
    assert after["input_records"] >= before["input_records"]
    assert after["input_scan_bytes"] > before["input_scan_bytes"]
    with pytest.raises(RecoveryError, match="budget contract cannot change"):
        adapter.extract_salvage(
            core_path.parent,
            other_output / "third.jsonl",
            budget=RecoveryBudget(max_input_records=2),
            request_id="same",
        )


def test_extract_crash_retains_reservation_and_preserves_source(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    discover(app, repository, origin, str(uuid4()))
    stop_catalog(core_path.parent, "synthetic crash during extraction")
    original = {
        path.name: path.read_bytes()
        for path in core_path.parent.glob("core.sqlite3*")
        if path.is_file()
    }
    outside = tmp_path.parent / (tmp_path.name + "-crash-accounting")
    outside.mkdir()
    ctx = multiprocessing.get_context("spawn")
    child = ctx.Process(
        target=_extract_process,
        args=(core_path.parent, outside / "crashed.jsonl", None, None, True),
    )
    child.start()
    child.join(30)
    if child.is_alive():
        child.terminate()
        child.join(5)
        pytest.fail("extraction crash probe did not finish")
    assert child.exitcode == -signal.SIGKILL
    before = _extract_state(core_path.parent)
    assert before["input_scan_bytes"] > 0
    assert not (outside / "crashed.jsonl").exists()
    adapter = SQLiteRecoveryAdapter()
    result = adapter.extract_salvage(
        core_path.parent,
        outside / "retry.jsonl",
        request_id="shared-extraction",
    )
    after = _extract_state(core_path.parent)
    assert result.candidate_count > 0
    assert after["input_scan_bytes"] > before["input_scan_bytes"]
    assert all(after[key] >= value for key, value in before.items())
    assert {
        path.name: path.read_bytes()
        for path in core_path.parent.glob("core.sqlite3*")
        if path.is_file()
    } == original


def test_parallel_extractions_share_one_cumulative_budget(acquisition, tmp_path):
    app, _, _, repository, origin, core_path, _ = acquisition
    p4_fixtures.fixture_note(acquisition)
    discover(app, repository, origin, str(uuid4()))
    stop_catalog(core_path.parent, "synthetic concurrent extraction")
    outside = tmp_path.parent / (tmp_path.name + "-parallel-accounting")
    outside.mkdir()
    ctx = multiprocessing.get_context("spawn")
    start, result = ctx.Event(), ctx.Queue()
    children = [
        ctx.Process(
            target=_extract_process,
            args=(core_path.parent, outside / f"{index}.jsonl", start, result, False),
        )
        for index in range(2)
    ]
    for child in children:
        child.start()
    start.set()
    for child in children:
        child.join(40)
        if child.is_alive():
            child.terminate()
            child.join(5)
            pytest.fail("concurrent extraction probe did not finish")
        assert child.exitcode == 0
    assert all(result.get(timeout=5)[1] > 0 for _ in children)
    usage = _extract_state(core_path.parent)
    assert usage["input_scan_bytes"] >= 2 * core_path.stat().st_size
    assert usage["input_scan_bytes"] <= RecoveryBudget().max_input_bytes
    assert usage["input_records"] <= RecoveryBudget().max_input_records


def test_unknown_binary_is_not_staged_by_generic_extraction(acquisition, tmp_path):
    app, _, _, _, _, core_path, _ = acquisition
    marker = b"ordinary-unproven-file-body-\x00\xff"
    db = sqlite3.connect(core_path)
    try:
        db.execute("CREATE TABLE unexpected_binary (name TEXT, body BLOB, text TEXT)")
        db.execute(
            "INSERT INTO unexpected_binary VALUES (?, ?, ?)",
            ("unknown", marker, "ordinary-unproven-text-body"),
        )
        db.commit()
    finally:
        db.close()
    stop_catalog(core_path.parent, "synthetic untyped bytes")
    output = tmp_path.parent / (tmp_path.name + "-untyped.jsonl")
    result = SQLiteRecoveryAdapter().extract_salvage(core_path.parent, output)
    raw = output.read_bytes()
    assert marker not in raw
    assert base64.b64encode(marker) not in raw
    assert b"ordinary-unproven-text-body" not in raw
    assert any("unexpected_binary" in item for item in result.unreadable_scope)
    assert result.partial


def test_ordinary_blob_cannot_be_staged_as_structural_metadata(
    synthetic_catalog, tmp_path
):
    db = connect(synthetic_catalog / "core.sqlite3", "core")
    try:
        body = db.execute(
            "SELECT body FROM retained_metadata WHERE native_type='commit'"
        ).fetchone()[0]
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' "
            "AND tbl_name='retained_metadata' AND sql LIKE '%UPDATE%'"
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(
            "UPDATE retained_metadata SET native_type='blob' WHERE native_type='commit'"
        )
        db.execute("PRAGMA ignore_check_constraints=OFF")
        for _, sql in triggers:
            db.execute(sql)
        db.commit()
    finally:
        db.close()
    stop_catalog(synthetic_catalog, "synthetic forbidden body type")
    output = tmp_path / "ordinary-blob.jsonl"
    receipt = SQLiteRecoveryAdapter().extract_salvage(synthetic_catalog, output)
    records = [json.loads(line) for line in output.read_text().splitlines()]
    candidate = next(
        item
        for item in records
        if item["extraction_provenance"].get("table") == "retained_metadata"
        and item["payload"].get("native_type") == "blob"
    )
    assert receipt.partial and candidate["extraction_status"] == "partial"
    assert "body_base64" not in candidate["payload"]
    assert base64.b64encode(body).decode("ascii") not in output.read_text()


@pytest.mark.parametrize("mismatch", [False, True])
def test_ref_merge_checks_paired_context_identity(acquisition, tmp_path, mismatch):
    app, _, _, repository, origin, core_path, _ = acquisition
    _, instance = app.core.catalog_identity()
    initialize(core_path.parent / "context.sqlite3", "context", repository, instance)
    outside = tmp_path.parent / (tmp_path.name + "-paired")
    outside.mkdir()
    adapter = SQLiteRecoveryAdapter()
    backup = outside / "backup"
    adapter.create_consistent_backup(core_path.parent, backup, BackupScope.PAIRED)
    p4_fixtures.fixture_note(acquisition)
    discover(app, repository, origin, str(uuid4()))
    source = sqlite3.connect(f"file:{core_path}?mode=ro", uri=True)
    try:
        scan = scan_ref_units(
            source, RecoveryWorkBudget(), max_records=500, max_row_bytes=1024 * 1024
        )
    finally:
        source.close()
    candidate = next(c for c in scan.candidates if c["candidate_type"] == "ref_subject")
    input_file = outside / "candidate.jsonl"
    input_file.write_text(json.dumps(candidate) + "\n")
    destination = outside / "fresh"
    adapter.restore_backup(backup, destination, repository)
    if mismatch:
        db = connect(destination / "context.sqlite3", "context")
        try:
            triggers = db.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='trigger' "
                "AND tbl_name='store_identity' AND sql LIKE '%UPDATE%'"
            ).fetchall()
            for name, _ in triggers:
                db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
            db.execute(
                "UPDATE store_identity SET catalog_instance_uuidv4=?", (str(uuid4()),)
            )
            for _, sql in triggers:
                db.execute(sql)
            db.commit()
        finally:
            db.close()
        with pytest.raises(CoreFailure) as error:
            adapter.merge_salvage(destination, input_file)
        assert error.value.code == "AUTHORITATIVE_CORRUPTION"
        assert (destination / "p1-recovery-stop.json").exists()
        assert not (outside / "active").exists()
    else:
        merged = adapter.merge_salvage(destination, input_file)
        assert merged.admitted_units == 1
        for mode, expected in (("auto", "paired"), ("core_only", "core_only")):
            query = ProductionQueryService(destination, mode=mode)
            assert query.detect_mode() == expected
        assert adapter.activate(destination, outside / "active").clean_operational
