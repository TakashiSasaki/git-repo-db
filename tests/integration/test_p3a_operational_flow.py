"""Guarded synthetic operational-source -> P2 -> P3A boundary evidence."""

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from scripts.conversion import archive, source, target
from scripts.conversion.common import DESIGN
from scripts.schema_contract import tagged_key
from tests.integration.test_conversion_foundation import worker
from tests.support.conversion_fixture import REPO_ID, make_source
from tests.support.operational_source import add_operational_indexes


def cli(action, workspace, *arguments, expected=0):
    child_env = dict(os.environ)
    minimum = bool(os.environ.get("TEST_SQLITE_MINIMUM")) or (
        sqlite3.sqlite_version_info < (3, 46, 1)
    )
    command = [sys.executable]
    if minimum:
        child_env["TEST_SQLITE_MINIMUM"] = "3.46.1"
        command += [
            "-c",
            "from scripts.sqlite_minimum import activate;activate();"
            "import runpy;runpy.run_path('scripts/offline_convert.py',run_name='__main__')",
        ]
    else:
        command.append("scripts/offline_convert.py")
    result = subprocess.run(
        [*command, action, "--work-dir", str(workspace), *map(str, arguments)],
        capture_output=True,
        text=True,
        timeout=30,
        env=child_env,
    )
    assert result.returncode == expected, (result.stdout, result.stderr)
    return json.loads(result.stdout if expected == 0 else result.stderr)


@pytest.fixture
def operational(tmp_path):
    database = tmp_path / "catalog.sqlite3"
    cache = make_source(database)
    add_operational_indexes(database, kinds=("code", "pr", "commits"), analyze=True)
    workspace = tmp_path / "conversion"
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    assert cli("seal", workspace, "--source", database, "--source-cache", cache) == {
        "sealed": True
    }
    assert before == (
        source.file_fingerprint(database),
        source.cache_inventory([cache]),
    )
    return database, cache, workspace, before


def assert_exact_core_archive(database, destination):
    spec = json.loads((DESIGN / "conversion-contract.json").read_bytes())
    tables = {row["table"] for row in spec["source_columns"]}
    with source.readonly(database) as src, source.readonly(destination) as db:
        expected_records = expected_values = 0
        for table in tables:
            for record in archive.rows(src, table):
                expected_records += 1
                expected_values += len(record.values)
                saved = db.execute(
                    "SELECT id,row_sha256 FROM legacy_records "
                    "WHERE source_table=? AND source_key=?",
                    (table, record.key),
                ).fetchone()
                assert saved is not None and saved[1] == record.row_sha256
                values = [
                    tuple(row)
                    for row in db.execute(
                        "SELECT column_name,storage_type,value_bytes FROM legacy_values "
                        "WHERE record_id=?",
                        (saved[0],),
                    )
                ]
                assert sorted(values) == sorted(record.values)
        assert (
            db.execute("SELECT count(*) FROM legacy_records").fetchone()[0]
            == expected_records
        )
        assert (
            db.execute("SELECT count(*) FROM legacy_values").fetchone()[0]
            == expected_values
        )
        assert {
            row[0]
            for row in db.execute("SELECT DISTINCT source_table FROM legacy_records")
        } <= tables
        repository = db.execute("SELECT id,name FROM repositories").fetchone()
        assert tuple(repository) == (REPO_ID, "synthetic/repo")
        mapping = db.execute(
            "SELECT target_table,target_key,relation FROM id_mappings"
        ).fetchone()
        assert tuple(mapping) == (
            "repositories",
            tagged_key([("text", REPO_ID.encode())]),
            "identity",
        )
        for table, expected in (
            ("resource_observations", 3),
            ("document_versions", 3),
            ("ref_observations", 2),
        ):
            assert (
                db.execute(
                    "SELECT count(*) FROM legacy_records WHERE source_table=?", (table,)
                ).fetchone()[0]
                == expected
            )


def test_guarded_operational_archive_handoff_and_restart(operational):
    database, cache, workspace, before = operational
    archived = worker(workspace)
    assert archived["archive_complete"] and archived["diagnostics"]["blocking"] > 0
    assert archived["diagnostics"]["partial"] > 0
    assert_exact_core_archive(database, workspace / "target.sqlite3")
    with source.readonly(workspace / "target.sqlite3") as db:
        p2_run = tuple(db.execute("SELECT * FROM conversion_runs").fetchone())
        diagnostics = [
            tuple(row) for row in db.execute("SELECT * FROM validation_results")
        ]
        batches = [tuple(row) for row in db.execute("SELECT * FROM conversion_batches")]
    receipt = worker(workspace, "--action", "handoff")
    assert receipt["lifecycle"] == "building"
    assert receipt["new_phase"]
    resumed = {**receipt, "new_phase": False}
    assert worker(workspace, "--action", "handoff") == resumed
    assert worker(workspace, "--action", "verify-phase") == resumed
    assert cli("verify-phase", workspace) == resumed
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == 2
        assert (
            tuple(
                db.execute(
                    "SELECT * FROM conversion_runs WHERE id=?", (p2_run[0],)
                ).fetchone()
            )
            == p2_run
        )
        assert [
            tuple(row) for row in db.execute("SELECT * FROM validation_results")
        ] == diagnostics
        assert [
            tuple(row) for row in db.execute("SELECT * FROM conversion_batches")
        ] == batches
        manifest = json.loads(p2_run[-1])
        dispositions = manifest["seal"]["preservation_dispositions"]
        assert {item["classification"] for item in dispositions} >= {
            "strict_v2_core",
            "application_fts",
            "sqlite_statistics",
        }
        assert all(
            item["preservation"] == "sealed_bytes_rebuild_excluded"
            and item["rebuild_from"]
            for item in dispositions
            if item["classification"] in {"application_fts", "sqlite_statistics"}
        )
    destination_before = source.file_fingerprint(workspace / "target.sqlite3")
    assert "PHASE_OWNERSHIP_MISMATCH" in worker(workspace, expected=2)
    assert destination_before == source.file_fingerprint(workspace / "target.sqlite3")
    assert_exact_core_archive(database, workspace / "target.sqlite3")
    assert before == (
        source.file_fingerprint(database),
        source.cache_inventory([cache]),
    )


def test_guarded_competing_handoff_writer_keeps_parent(operational):
    database, cache, workspace, before = operational
    worker(workspace)
    destination_before = source.file_fingerprint(workspace / "target.sqlite3")
    with target.writer_lock(workspace):
        assert "CONVERTER_ALREADY_RUNNING" in worker(
            workspace, "--action", "handoff", expected=2
        )
    assert destination_before == source.file_fingerprint(workspace / "target.sqlite3")
    receipt = worker(workspace, "--action", "handoff")
    assert worker(workspace, "--action", "verify-phase") == {
        **receipt,
        "new_phase": False,
    }
    assert before == (
        source.file_fingerprint(database),
        source.cache_inventory([cache]),
    )


@pytest.mark.parametrize("point", ["before_handoff_commit", "after_handoff_commit"])
@pytest.mark.parametrize("hard_exit", [False, True])
def test_guarded_handoff_commit_fault_and_restart(operational, point, hard_exit):
    database, cache, workspace, before = operational
    worker(workspace)
    args = ["--action", "handoff", "--fault", point]
    if hard_exit:
        args.append("--hard-exit")
    worker(workspace, *args, expected=77 if hard_exit else 2)
    if point == "before_handoff_commit":
        # The P2 writer recovers a target hot journal after abrupt termination.
        # Read-only verification deliberately never performs that recovery.
        assert worker(workspace)["new_batches"] == 0
    # Observe only the prior target after its writer has verified P2. A cold
    # target journal can remain after a no-op retry; this read never recovers it.
    with closing(
        sqlite3.connect(
            (workspace / "target.sqlite3").as_uri() + "?mode=ro&immutable=1", uri=True
        )
    ) as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == (
            1 if point == "before_handoff_commit" else 2
        )
    receipt = worker(workspace, "--action", "handoff")
    resumed = {**receipt, "new_phase": False}
    assert worker(workspace, "--action", "verify-phase") == resumed
    assert worker(workspace, "--action", "handoff") == resumed
    assert_exact_core_archive(database, workspace / "target.sqlite3")
    assert before == (
        source.file_fingerprint(database),
        source.cache_inventory([cache]),
    )


@pytest.mark.parametrize("suffix", [None, "-wal", "-shm", "-journal"])
def test_guarded_rejected_source_keeps_original_cache_and_sidecars(tmp_path, suffix):
    database = tmp_path / "catalog.sqlite3"
    cache = make_source(database)
    sidecar = None
    if suffix:
        sidecar = Path(str(database) + suffix)
        sidecar.write_bytes(b"synthetic stopped input with unsupported sidecar")
    else:
        with sqlite3.connect(database) as db:
            db.execute("CREATE TABLE catalog_fts_suspicious(body TEXT)")
    before = source.file_fingerprint(database), source.cache_inventory([cache])
    sidecar_before = source.file_fingerprint(sidecar) if sidecar else None
    result = cli(
        "seal",
        tmp_path / "conversion",
        "--source",
        database,
        "--source-cache",
        cache,
        expected=2,
    )
    assert result["code"] == (
        "SOURCE_NOT_SEALED" if suffix else "SOURCE_SCHEMA_MISMATCH"
    )
    if suffix is None:
        report = json.loads(
            (tmp_path / "conversion/source-admission.json").read_bytes()
        )
        assert report["state"] == "rejected" and not report["sealed"]
        assert report["source_fingerprint"] == before[0]
        unsupported = [
            item
            for item in report["admission"]["preservation_dispositions"]
            if item["classification"] == "unsupported"
        ]
        assert any(item["object"] == "catalog_fts_suspicious" for item in unsupported)
        assert result["admission"]["unsupported"] == len(unsupported)
        assert not (tmp_path / "conversion/sealed.json").exists()
        assert not (tmp_path / "conversion/target.sqlite3").exists()
    assert before == (
        source.file_fingerprint(database),
        source.cache_inventory([cache]),
    )
    if sidecar:
        assert source.file_fingerprint(sidecar) == sidecar_before


@pytest.mark.parametrize("recovery_action", ["archive", "handoff"])
def test_guarded_spilled_handoff_rolls_back_to_exact_p2(operational, recovery_action):
    database, cache, workspace, before = operational
    worker(workspace)
    with source.readonly(workspace / "target.sqlite3") as db:
        parent = tuple(db.execute("SELECT * FROM conversion_runs").fetchone())
        evidence = {
            name: [tuple(row) for row in db.execute(f"SELECT * FROM {name}")]
            for name in (
                "conversion_sources",
                "conversion_batches",
                "legacy_records",
                "legacy_values",
                "id_mappings",
                "validation_results",
                "repositories",
            )
        }
    worker(
        workspace,
        "--action",
        "handoff",
        "--spill",
        "--fault",
        "before_handoff_commit",
        "--hard-exit",
        expected=77,
    )
    journal = workspace / "target.sqlite3-journal"
    assert journal.stat().st_size > 512
    assert journal.read_bytes()[:8] == bytes.fromhex("d9d505f920a163d7")
    # This intentionally observes the uncommitted spill, without recovering it.
    with target.readonly_destination(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == 2
    recovered = worker(workspace, "--action", recovery_action)
    if recovery_action == "archive":
        assert recovered["new_batches"] == 0
    else:
        assert recovered["new_phase"]
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == (
            1 if recovery_action == "archive" else 2
        )
        assert (
            tuple(
                db.execute(
                    "SELECT * FROM conversion_runs WHERE id=?", (parent[0],)
                ).fetchone()
            )
            == parent
        )
        for name, rows in evidence.items():
            assert [tuple(row) for row in db.execute(f"SELECT * FROM {name}")] == rows
    receipt = (
        worker(workspace, "--action", "handoff")
        if recovery_action == "archive"
        else recovered
    )
    resumed = {**receipt, "new_phase": False}
    assert worker(workspace, "--action", "handoff") == resumed
    assert worker(workspace, "--action", "verify-phase") == resumed
    assert_exact_core_archive(database, workspace / "target.sqlite3")
    assert before == (
        source.file_fingerprint(database),
        source.cache_inventory([cache]),
    )
