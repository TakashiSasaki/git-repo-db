"""P3B initialization authorization, exact frozen receipt and immutable parents."""

import json
import os

import pytest

from scripts.conversion import (
    batch,
    engine,
    identity,
    identity_phase,
    phase,
    source,
    target,
)
from scripts.conversion.common import ConversionError, canonical
from tests.support.conversion_fixture import make_source


@pytest.fixture
def parent(tmp_path):
    database = tmp_path / "source.sqlite3"
    cache = make_source(database)
    workspace = tmp_path / "conversion"
    engine.seal_input(database, workspace, [cache])
    engine.convert(workspace, batch_size=2, map_repositories=True)
    phase.handoff(workspace)
    return database, cache, workspace


def frozen(workspace):
    with source.readonly(workspace / "target.sqlite3") as db:
        return {
            table: batch.encode(
                [tuple(row) for row in db.execute(f"SELECT * FROM {table}")]
            )
            for table in (
                "database_identity",
                "conversion_sources",
                "conversion_runs",
                "conversion_batches",
                "legacy_records",
                "legacy_values",
                "repositories",
                "id_mappings",
                "validation_results",
            )
        }


def test_identity_initialization_preserves_parent_and_exact_repeats(parent):
    database, cache, workspace = parent
    before = frozen(workspace)
    originals = database.read_bytes(), source.cache_inventory([cache])
    result = identity_phase.initialize(workspace, batch_size=2)
    assert result["phase_committed"] and result["new_phase"]
    assert result["lifecycle"] == "building" and not result["activation_permitted"]
    assert identity_phase.initialize(workspace, batch_size=2) == {
        **result,
        "new_phase": False,
    }
    after = frozen(workspace)
    for table in before:
        if table == "conversion_runs":
            assert all(row in after[table] for row in before[table])
            assert len(after[table]) == len(before[table]) + 1
        else:
            assert after[table] == before[table]
    assert originals == (database.read_bytes(), source.cache_inventory([cache]))
    with source.readonly(workspace / "target.sqlite3") as db:
        run = db.execute(
            "SELECT * FROM conversion_runs WHERE parser_version=?",
            (identity_phase.PROTOCOL_VERSION,),
        ).fetchone()
        receipt = json.loads(run["manifest"])
        assert receipt["parent"]["parser_version"] == phase.PROTOCOL_VERSION
        assert receipt["signatures"]["invariant_contract_sha256"]
        assert "legacy_values" in receipt["write_ownership"]["immutable_parent"]
        assert (
            receipt["write_ownership"]["repository_enrichment"]["current_snapshot_id"]
            == "must remain NULL"
        )
        assert run["started_at"] == run["ended_at"] == receipt["committed_at"]


@pytest.mark.parametrize(
    "point", ["before_identity_init_commit", "after_identity_init_commit"]
)
def test_identity_initialization_fault_is_atomic_and_repeatable(parent, point):
    _, _, workspace = parent
    before = frozen(workspace)

    def fault(actual, **context):
        if actual == point:
            raise ConversionError("INJECTED_FAILURE")

    with pytest.raises(ConversionError, match="INJECTED_FAILURE"):
        identity_phase.initialize(workspace, batch_size=2, fault=fault)
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == (
            3 if point.startswith("after") else 2
        )
    result = identity_phase.initialize(workspace, batch_size=2)
    assert result["new_phase"] == point.startswith("before")
    assert (
        identity_phase.initialize(workspace, batch_size=2)["transition_id"]
        == result["transition_id"]
    )
    after = frozen(workspace)
    assert all(
        after[table] == rows
        for table, rows in before.items()
        if table != "conversion_runs"
    )


def test_identity_initialization_requires_p3a_receipt(tmp_path):
    database = tmp_path / "source.sqlite3"
    cache = make_source(database)
    workspace = tmp_path / "conversion"
    engine.seal_input(database, workspace, [cache])
    engine.convert(workspace, batch_size=2, map_repositories=True)
    before = frozen(workspace)
    with pytest.raises(ConversionError, match="PHASE_OWNERSHIP_MISMATCH"):
        identity_phase.initialize(workspace)
    assert frozen(workspace) == before


def test_identity_owner_refuses_old_writers_before_native_open(parent, monkeypatch):
    _, _, workspace = parent
    identity_phase.initialize(workspace, batch_size=2)
    before = (workspace / "target.sqlite3").read_bytes()

    def forbidden(path):
        raise AssertionError("old writer attempted a writable open")

    monkeypatch.setattr(target, "connect", forbidden)
    for old_writer in (
        lambda: engine.convert(workspace, batch_size=2, map_repositories=True),
        lambda: phase.handoff(workspace),
    ):
        with pytest.raises(ConversionError, match="PHASE_OWNERSHIP_MISMATCH"):
            old_writer()
    assert (workspace / "target.sqlite3").read_bytes() == before


def test_identity_options_are_exact_and_writer_lock_is_shared(parent):
    _, _, workspace = parent
    identity_phase.initialize(workspace, batch_size=2)
    with pytest.raises(ConversionError, match="RESUME_OPTIONS_MISMATCH"):
        identity_phase.initialize(workspace, batch_size=3)
    with target.writer_lock(workspace):
        for action in (
            identity_phase.initialize,
            identity_phase.convert,
            identity_phase.verify,
        ):
            with pytest.raises(ConversionError, match="CONVERTER_ALREADY_RUNNING"):
                action(
                    workspace, batch_size=2
                ) if action != identity_phase.verify else action(workspace)


@pytest.mark.parametrize(
    "change", ["receipt", "protocol", "state", "parent", "signature", "extra-phase"]
)
def test_identity_owner_tamper_refused_before_writable_open(
    parent, monkeypatch, change
):
    _, _, workspace = parent
    identity_phase.initialize(workspace, batch_size=2)
    with target.connect(workspace / "target.sqlite3") as db:
        run = db.execute(
            "SELECT * FROM conversion_runs WHERE parser_version=?",
            (identity_phase.PROTOCOL_VERSION,),
        ).fetchone()
        if change in {"receipt", "signature"}:
            value = json.loads(run["manifest"])
            if change == "receipt":
                value["activation_permitted"] = True
            else:
                value["signatures"]["invariant_contract_sha256"] = "0" * 64
            db.execute(
                "UPDATE conversion_runs SET manifest=? WHERE id=?",
                (canonical(value), run["id"]),
            )
        elif change == "protocol":
            db.execute(
                "UPDATE conversion_runs SET parser_version='unknown' WHERE id=?",
                (run["id"],),
            )
        elif change == "state":
            db.execute(
                "UPDATE conversion_runs SET state='validated' WHERE id=?", (run["id"],)
            )
        elif change == "parent":
            db.execute(
                "UPDATE conversion_runs SET started_at='altered' WHERE parser_version=?",
                (phase.PROTOCOL_VERSION,),
            )
        else:
            db.execute(
                "INSERT INTO conversion_runs SELECT 'extra',source_id,started_at,ended_at,parser_version,state,manifest FROM conversion_runs WHERE id=?",
                (run["id"],),
            )
    before = (workspace / "target.sqlite3").read_bytes()

    def forbidden(path):
        raise AssertionError("unrecognized phase opened writable")

    monkeypatch.setattr(target, "connect", forbidden)
    with pytest.raises(ConversionError):
        identity_phase.initialize(workspace, batch_size=2)
    assert (workspace / "target.sqlite3").read_bytes() == before


@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_identity_sidecar_alias_refused_before_native_open(
    parent, tmp_path, monkeypatch, alias
):
    database, _, workspace = parent
    journal = workspace / "target.sqlite3-journal"
    journal_origin = tmp_path / "journal-origin"
    journal_origin.write_bytes(database.read_bytes())
    if alias == "symlink":
        journal.symlink_to(database)
    else:
        os.link(journal_origin, journal)
    before = database.read_bytes(), (workspace / "target.sqlite3").read_bytes()

    def forbidden(path):
        raise AssertionError("sidecar alias opened writable")

    monkeypatch.setattr(target, "connect", forbidden)
    with pytest.raises(ConversionError, match="TARGET_SIDECAR_ALIAS_UNSUPPORTED"):
        identity_phase.initialize(workspace)
    assert before == (
        database.read_bytes(),
        (workspace / "target.sqlite3").read_bytes(),
    )


@pytest.mark.parametrize("change", ["repository", "parent-phase-diagnostic"])
def test_initial_identity_prefix_checks_unconverted_parent_values(
    parent, monkeypatch, change
):
    _, _, workspace = parent
    identity_phase.initialize(workspace, batch_size=2)
    with target.connect(workspace / "target.sqlite3") as db:
        if change == "repository":
            db.execute("UPDATE repositories SET name='changed'")
        else:
            prior_id = db.execute(
                "SELECT id FROM conversion_runs WHERE parser_version=?",
                (phase.PROTOCOL_VERSION,),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO validation_results(run_id,invariant_id,code,severity,observed_at,details) VALUES(?,'I31','EXTRA','blocking','2026-01-01','{}')",
                (prior_id,),
            )
    before = (workspace / "target.sqlite3").read_bytes()

    def forbidden(path):
        raise AssertionError("altered parent opened writable")

    monkeypatch.setattr(target, "connect", forbidden)
    with pytest.raises(ConversionError):
        identity_phase.initialize(workspace, batch_size=2)
    with pytest.raises(ConversionError):
        identity_phase.verify(workspace)
    assert before == (workspace / "target.sqlite3").read_bytes()


def test_identity_completion_keeps_retained_semantic_blockers_visible(parent):
    _, _, workspace = parent
    result = identity_phase.convert(workspace, batch_size=2)
    assert result["complete"] and not result["identity_ready"]
    assert result["parent_diagnostics"]["blocking"] > 0
    assert result["combined_diagnostics"]["blocking"] == result["parent_diagnostics"][
        "blocking"
    ] + result["diagnostics"].get("blocking", 0)
    assert not result["activation_permitted"] and result["lifecycle"] == "building"
    verified = identity_phase.verify(workspace)
    assert verified == {**result, "new_batches": 0, "new_phase": False}


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("action", ["initialize", "convert"])
def test_locked_identity_invocation_reuses_unchanged_entry_proofs(
    parent, monkeypatch, existing, action
):
    _, _, workspace = parent
    if existing:
        identity_phase.initialize(workspace, batch_size=2)
    counts = {"archive": 0, "identity": 0, "seal": 0}

    def count_call(name, function):
        def counted(*args, **kwargs):
            counts[name] += 1
            return function(*args, **kwargs)

        return counted

    monkeypatch.setattr(
        phase, "_exact_archive", count_call("archive", phase._exact_archive)
    )
    monkeypatch.setattr(
        identity, "validate_output", count_call("identity", identity.validate_output)
    )
    monkeypatch.setattr(source, "verify_seal", count_call("seal", source.verify_seal))
    result = getattr(identity_phase, action)(workspace, batch_size=2)
    assert result["phase_committed"]
    assert counts == {
        "archive": 2 if action == "convert" else 1,
        "identity": 2 if action == "convert" else int(existing),
        "seal": 2 if action == "convert" else 1,
    }


def test_changed_native_open_state_requires_fresh_entry_proofs(parent, monkeypatch):
    _, _, workspace = parent
    identity_phase.initialize(workspace, batch_size=2)
    connect, exact_archive = target.connect, phase._exact_archive
    archive_checks = 0

    def changed_open(path):
        db = connect(path)
        # A transaction can preserve logical values while invalidating the
        # verified file state; native-open/recovery reuse must still be refused.
        db.execute("UPDATE conversion_runs SET manifest=manifest||' '")
        db.execute("UPDATE conversion_runs SET manifest=rtrim(manifest)")
        return db

    def counted_archive(*args, **kwargs):
        nonlocal archive_checks
        archive_checks += 1
        return exact_archive(*args, **kwargs)

    monkeypatch.setattr(target, "connect", changed_open)
    monkeypatch.setattr(phase, "_exact_archive", counted_archive)
    assert identity_phase.initialize(workspace, batch_size=2)["phase_committed"]
    assert archive_checks == 2
