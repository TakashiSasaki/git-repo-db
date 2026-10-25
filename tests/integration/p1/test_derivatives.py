"""Derivative loss and finite cumulative actual-work contracts."""

import contextlib
import json
import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_coordination import (
    NotesWorkBudget,
    PairCoordinator,
    SearchProjection,
    WorkLedger,
)
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.domain.p1_coordination import (
    CoordinationError,
    NotesLimits,
    RequestIdentity,
)
from tests.integration.p1.test_coordination import (
    INSTANCE,
    REPOSITORY,
    admit_fixture,
    build,
    child_code,
    context_unit,
    core_unit,
    fixture_authority,
)


def limits(amount):
    return {
        unit: amount
        for unit in (
            "input_bytes",
            "verification_bytes",
            "metadata_units",
            "proof_steps",
        )
    }


def request():
    return RequestIdentity(str(uuid4()), str(uuid4()))


def test_request_cumulative_across_real_attempts_and_safe_settlement(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    with contextlib.closing(
        connect(directory / "operational.sqlite3", "operational")
    ) as db:
        ledger, identity = WorkLedger(db), request()
        ledger.new_request(identity, '{"ref":"refs/notes/review"}', limits(10))
        first, retry = str(uuid4()), str(uuid4())
        ledger.attempt(identity, first)
        permit = ledger.reserve(identity, first, "input_bytes", "read-note:0", 8)
        ledger.finish(permit, 7)
        with pytest.raises(CoordinationError, match="PERMIT_ALREADY_SETTLED"):
            ledger.finish(permit, 0)
        ledger.attempt(identity, retry)
        with pytest.raises(sqlite3.IntegrityError, match="finite cumulative"):
            ledger.reserve(identity, retry, "input_bytes", "reread-note:0", 4)
        permit = ledger.reserve(identity, retry, "input_bytes", "lookup-note:0", 3)
        ledger.finish(permit, 3)
        assert db.execute("SELECT sum(actual) FROM work_accounting").fetchone()[0] == 10
        ledger.increase_limit(identity, "input_bytes", 12)
        with pytest.raises(CoordinationError, match="FINITE_INCREASE_REQUIRED"):
            ledger.increase_limit(identity, "input_bytes", 11)
        permit = ledger.reserve(identity, retry, "input_bytes", "deliberate-extra:0", 2)
        ledger.finish(permit, 2)
        assert db.execute("SELECT sum(actual) FROM work_accounting").fetchone()[0] == 12


def test_unsettled_work_and_core_rollback_never_refund_actual_work(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    identity = request()
    with (
        contextlib.closing(
            connect(directory / "operational.sqlite3", "operational")
        ) as db,
        contextlib.closing(connect(directory / "core.sqlite3", "core")) as core,
    ):
        ledger = WorkLedger(db)
        ledger.new_request(identity, "{}", limits(10))
        attempt = str(uuid4())
        ledger.attempt(identity, attempt)
        core.execute("BEGIN IMMEDIATE")
        core_unit(core)
        ledger.reserve(identity, attempt, "proof_steps", "traversal:0", 9)
        core.rollback()  # Work already performed or uncertain remains reserved.
    with contextlib.closing(
        connect(directory / "operational.sqlite3", "operational")
    ) as db:
        ledger = WorkLedger(db)
        retry = str(uuid4())
        ledger.attempt(identity, retry)
        with pytest.raises(sqlite3.IntegrityError, match="finite cumulative"):
            ledger.reserve(identity, retry, "proof_steps", "traversal:0", 2)
        assert (
            db.execute("SELECT reserved,actual FROM work_accounting").fetchone()[0] == 9
        )


def test_operational_loss_disables_old_continuation_without_invalidating_authority(
    tmp_path,
):
    directory = tmp_path / "live"
    build(directory)
    admit_fixture(PairCoordinator(directory), core_unit, context_unit)
    old = request()
    with contextlib.closing(
        connect(directory / "operational.sqlite3", "operational")
    ) as db:
        WorkLedger(db).new_request(old, "{}", limits(10))
    (directory / "operational.sqlite3").unlink()
    initialize(directory / "operational.sqlite3", "operational", REPOSITORY, INSTANCE)
    with contextlib.closing(
        connect(directory / "operational.sqlite3", "operational")
    ) as db:
        ledger = WorkLedger(db)
        with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
            ledger.attempt(old, str(uuid4()))
        # A genuinely new explicit request is distinct, never an automatic reset.
        new = request()
        ledger.new_request(new, "{}", limits(10))
        ledger.attempt(new, str(uuid4()))
    with PairCoordinator(directory).snapshots() as pair:
        assert pair.context.execute("SELECT count(*) FROM resources").fetchone()[0] == 1


def test_process_death_keeps_uncertain_work_reservation(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    identity, attempt = request(), str(uuid4())
    with contextlib.closing(
        connect(directory / "operational.sqlite3", "operational")
    ) as db:
        ledger = WorkLedger(db)
        ledger.new_request(identity, "{}", limits(10))
        ledger.attempt(identity, attempt)
    code = """
import os,sys
from pathlib import Path
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.p1_coordination import WorkLedger
from repo_catalog.domain.p1_coordination import RequestIdentity
db=connect(Path(sys.argv[1])/'operational.sqlite3','operational')
WorkLedger(db).reserve(RequestIdentity(sys.argv[2],sys.argv[3]),sys.argv[4],'proof_steps','traverse-root:0',9)
os._exit(86)
"""
    process = child_code(code, directory, *identity.values(), attempt)
    _, error = process.communicate(timeout=15)
    assert process.returncode == 86, error
    with contextlib.closing(
        connect(directory / "operational.sqlite3", "operational")
    ) as db:
        with pytest.raises(sqlite3.IntegrityError, match="finite cumulative"):
            WorkLedger(db).reserve(
                identity, attempt, "proof_steps", "traverse-root:1", 2
            )


@pytest.mark.parametrize("amount", [-1, 2**63, float("inf"), True])
def test_nonfinite_or_invalid_work_limits_rejected(tmp_path, amount):
    directory = tmp_path / "live"
    build(directory)
    with contextlib.closing(
        connect(directory / "operational.sqlite3", "operational")
    ) as db:
        with pytest.raises(ValueError, match="finite"):
            WorkLedger(db).new_request(request(), "{}", limits(amount))
    with pytest.raises(ValueError, match="finite"):
        NotesLimits(amount)


def test_notes_budget_precharge_exact_replay_and_invalid_unit(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    with contextlib.closing(
        connect(directory / "operational.sqlite3", "operational")
    ) as db:
        ledger, identity, attempt = WorkLedger(db), request(), str(uuid4())
        ledger.new_request(identity, "{}", limits(10))
        ledger.attempt(identity, attempt)
        budget = NotesWorkBudget(ledger, identity, attempt, NotesLimits(10))
        with pytest.raises(CoordinationError, match="UNRESERVED_WORK"):
            budget.charge("input_bytes", 1)
        budget.require("input_bytes", 4)
        with pytest.raises(CoordinationError, match="UNSETTLED_WORK"):
            budget.require("input_bytes", 4)
        budget.charge("input_bytes", 4)
        budget.require("input_bytes", 4)  # replay reprocessing is charged again
        budget.charge("input_bytes", 4)
        assert db.execute("SELECT sum(actual) FROM work_accounting").fetchone()[0] == 8
        with pytest.raises(sqlite3.IntegrityError):
            budget.require("unrecognized", 1)
        db.execute("BEGIN")
        with pytest.raises(CoordinationError, match="ACCOUNTING_TRANSACTION"):
            budget.require("proof_steps", 1)
        db.rollback()


def test_search_snapshot_fence_loss_corruption_and_reconstruction(tmp_path):
    from repo_catalog.adapters.sqlite.p1_context import ContextStore
    from repo_catalog.domain.p1_context import FieldCandidate, FieldClock, ResourceKey
    from tests.integration.p1.test_coordination import PROVIDER

    directory = tmp_path / "live"
    build(directory)
    coordinator = PairCoordinator(directory)
    admit_fixture(coordinator, core_unit, context_unit)
    with contextlib.closing(
        connect(directory / "context.sqlite3", "context")
    ) as authority:
        authorization, admission = fixture_authority()
        with ContextStore(authority, authorization=authorization).admission_transaction(
            admission=admission
        ) as store:
            store.admit_field(
                FieldCandidate(
                    ResourceKey.from_native(PROVIDER, "issue", "7"),
                    "body",
                    '"body needle"',
                    FieldClock("provider.edit", 17),
                    '{"evidence":"issue-7-edit-17","source":"provider.example"}',
                    20,
                )
            )
    with (
        contextlib.closing(connect(directory / "search.sqlite3", "search")) as db,
        coordinator.snapshots() as pair,
    ):
        rows = SearchProjection.context_documents(pair)
        assert len(rows) == 1
        search = SearchProjection(db)
        assert search.read("context_text", pair.token, "needle", lambda: rows) == (
            "authority_scan",
            rows,
        )
        search.rebuild_context(pair)
        assert search.read("context_text", pair.token, "needle", lambda: rows) == (
            "projection",
            rows,
        )
        db.execute("DELETE FROM search_documents")
        assert search.read("context_text", pair.token, "needle", lambda: rows) == (
            "authority_scan",
            rows,
        )
        search.rebuild_context(pair)

        def new_fact(core):
            core.execute("INSERT INTO git_objects VALUES('sha1',?)", ("b" * 40,))

        coordinator.admit(new_fact, lambda db: None)
        assert search.candidates("context_text", pair.token, "needle") == set(rows)
        with coordinator.snapshots() as newer:
            assert search.candidates("context_text", newer.token, "needle") is None
        db.execute("DROP TABLE search_documents")
        assert (
            search.read("context_text", pair.token, "needle", lambda: rows)[0]
            == "authority_scan"
        )
    (directory / "search.sqlite3").unlink()
    assert (
        SearchProjection(None).read("context_text", pair.token, "needle", lambda: rows)[
            0
        ]
        == "authority_scan"
    )
    initialize(directory / "search.sqlite3", "search", REPOSITORY, INSTANCE)
    with (
        contextlib.closing(connect(directory / "search.sqlite3", "search")) as db,
        coordinator.snapshots() as rebuilt,
    ):
        SearchProjection(db).rebuild_context(rebuilt)
        assert SearchProjection(db).candidates(
            "context_text", rebuilt.token, "needle"
        ) == set(rows)


def test_search_rejects_ordinary_file_content_projection(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    with (
        contextlib.closing(connect(directory / "search.sqlite3", "search")) as db,
        PairCoordinator(directory).snapshots() as pair,
    ):
        # Public builders derive actual authority rather than accepting raw text.
        assert not hasattr(SearchProjection(db), "rebuild")
        SearchProjection(db).rebuild_git_metadata(pair)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute(
                "INSERT INTO search_projections VALUES('ordinary_file',?)",
                (pair.token.encode(),),
            )
        assert db.execute("SELECT count(*) FROM search_documents").fetchone()[0] == 0


def test_context_search_resolves_actual_text_fk_in_projection_and_fallback(tmp_path):
    from repo_catalog.adapters.sqlite.p1_context import ContextStore
    from repo_catalog.domain.p1_context import FieldCandidate, FieldClock, ResourceKey
    from tests.integration.p1.test_coordination import PROVIDER

    directory = tmp_path / "live"
    build(directory)
    coordinator = PairCoordinator(directory)
    admit_fixture(coordinator, core_unit, context_unit)
    actual = ResourceKey.from_native(PROVIDER, "issue", "7")
    reported = ResourceKey.from_native(PROVIDER, "issue", "reported")
    null = ResourceKey.from_native(PROVIDER, "issue", "null")
    provenance = '{"evidence":"provider-body-event","source":"provider.example"}'

    def candidate(resource, field, value, clock):
        return FieldCandidate(
            resource,
            field,
            json.dumps(value),
            FieldClock("provider.edit", clock),
            provenance,
            clock,
        )

    with contextlib.closing(
        connect(directory / "context.sqlite3", "context")
    ) as authority:
        authorization, admission = fixture_authority(extra_resources=(reported, null))
        with ContextStore(authority, authorization=authorization).admission_transaction(
            admission=admission
        ) as store:
            body = "provider-only needle 😀"
            digest = store.text(body)
            store.admit_field(candidate(actual, "text_body_sha256", digest, 1))
            store.resource(reported, REPOSITORY)
            store.admit_field(candidate(reported, "reported_text_sha256", digest, 1))
            store.resource(null, REPOSITORY)
            store.admit_field(candidate(null, "text_body_sha256", None, 1))
    with (
        contextlib.closing(connect(directory / "search.sqlite3", "search")) as db,
        coordinator.snapshots() as old,
    ):
        rows = SearchProjection.context_documents(old)
        body_rows = {key: text for key, text in rows.items() if "needle" in text}
        assert list(body_rows.values()) == [body]
        assert json.loads(next(iter(body_rows)))[2:4] == [
            actual.provider_resource_id,
            "text_body_sha256",
        ]
        reported_rows = {
            key: text
            for key, text in rows.items()
            if json.loads(key)[2] == reported.provider_resource_id
        }
        assert list(reported_rows.values()) == [digest]
        assert not any(json.loads(key)[2] == null.provider_resource_id for key in rows)

        def fallback():
            return SearchProjection.context_documents(old)

        assert SearchProjection(None).read(
            "context_text", old.token, "needle", fallback
        ) == ("authority_scan", body_rows)
        search = SearchProjection(db)
        search.rebuild_context(old)
        assert search.read("context_text", old.token, "needle", fallback) == (
            "projection",
            body_rows,
        )

        def update(context):
            store = ContextStore(context)
            newer_digest = store.text("replacement new-token")
            store.admit_field(candidate(actual, "text_body_sha256", newer_digest, 2))

        admit_fixture(coordinator, lambda core: None, update)
        # Both projection and direct fallback retain the actual pinned body.
        assert search.read("context_text", old.token, "needle", fallback) == (
            "projection",
            body_rows,
        )
        with coordinator.snapshots() as newer:

            def direct():
                return SearchProjection.context_documents(newer)

            assert search.read("context_text", newer.token, "needle", direct) == (
                "authority_scan",
                {},
            )
            backend, matches = search.read(
                "context_text", newer.token, "new-token", direct
            )
            assert backend == "authority_scan" and list(matches.values()) == [
                "replacement new-token"
            ]
            search.rebuild_context(newer)
            assert search.read("context_text", newer.token, "new-token", direct) == (
                "projection",
                matches,
            )
