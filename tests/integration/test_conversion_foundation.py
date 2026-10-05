import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.conversion import archive, engine, mapping, source, target
from scripts.conversion.common import DESIGN, ConversionError, stat_identity
from scripts.schema_contract import tagged_key
from tests.support.conversion_fixture import REPO_ID, make_source


@pytest.fixture
def sealed(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    cache = make_source(database)
    workspace = tmp_path / "conversion"
    engine.seal_input(database, workspace, [cache])
    return database, cache, workspace


def worker(workspace, *args, expected=0):
    child_env = dict(os.environ)
    minimum = bool(
        os.environ.get("TEST_SQLITE_MINIMUM")
    ) or sqlite3.sqlite_version_info < (3, 46, 1)
    if minimum:
        child_env["TEST_SQLITE_MINIMUM"] = "3.46.1"
    child = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.support.conversion_worker",
            str(workspace),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=child_env,
    )
    assert child.returncode == expected, (child.returncode, child.stdout, child.stderr)
    if child.stdout:
        value = json.loads(child.stdout)
        assert value.pop("_sqlite_version") == (
            "3.46.1" if minimum else sqlite3.sqlite_version
        )
        return value
    return child.stderr


def contents(path):
    return hashlib.sha256(path.read_bytes()).digest()


@pytest.mark.parametrize(
    "probe",
    [
        "source-open",
        "source-sqlite",
        "source-ro",
        "cache-open",
        "cache-unlink",
        "cache-ref",
        "cache-chmod",
        "git-fetch",
        "git-gc",
        "git-prune",
        "git-ref",
        "git-lazy",
        "rest",
        "graphql",
        "http",
        "raw-socket",
        "raw-exec",
        "cache-dirfd",
        "attach",
    ],
)
def test_guarded_worker_denies_acquisition_and_source_mutation(sealed, probe):
    database, cache, workspace = sealed
    before = contents(database), source.cache_inventory([cache])
    assert worker(workspace, "--probe", probe) == {"denied": probe}
    assert before == (contents(database), source.cache_inventory([cache]))


@pytest.mark.parametrize("kind", ["source", "cache"])
def test_existing_hardlink_alias_cannot_bypass_input_write_guard(sealed, kind):
    database, cache, workspace = sealed
    original = database if kind == "source" else cache / "objects/evidence"
    os.link(original, workspace / "input-alias")
    before = contents(original), stat_identity(original)
    probe = f"{kind}-hardlink-open"
    assert worker(workspace, "--probe", probe) == {"denied": probe}
    assert before == (contents(original), stat_identity(original))


def test_source_hardlinked_as_destination_is_never_opened_writable(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    cache = make_source(database)
    with sqlite3.connect(database) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        db.execute("UPDATE catalog_meta SET publication_seq=42")
    db.close()
    workspace = tmp_path / "conversion"
    workspace.mkdir()
    os.link(database, workspace / "target.sqlite3")
    engine.seal_input(database, workspace, [cache])
    before = contents(database), stat_identity(database)
    worker(workspace, expected=2)
    # journal_mode=DELETE on an accidentally writable connection would rewrite
    # the stopped WAL-format source header before target identity validation.
    assert before == (contents(database), stat_identity(database))


def test_complete_exact_archive_and_replay(sealed):
    database, cache, workspace = sealed
    before = contents(database), source.cache_inventory([cache])
    result = worker(workspace)
    assert result["archive_complete"] and result["lifecycle"] == "building"
    assert result["diagnostics"]["blocking"] > 0
    assert result["diagnostics"]["partial"] > 0
    with (
        source.readonly(database) as old,
        source.readonly(workspace / "target.sqlite3") as new,
    ):
        tables = [
            r[0]
            for r in old.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        covered = set()
        for table in tables:
            for record in archive.rows(old, table):
                saved = new.execute(
                    "SELECT id,row_sha256 FROM legacy_records WHERE source_table=? AND source_key=?",
                    (table, record.key),
                ).fetchone()
                assert saved[1] == record.row_sha256
                values = [
                    tuple(r)
                    for r in new.execute(
                        "SELECT column_name,storage_type,value_bytes FROM legacy_values WHERE record_id=?",
                        (saved[0],),
                    )
                ]
                assert sorted(values) == sorted(record.values)
                covered.update((table, value[0]) for value in values)
        spec = json.loads((DESIGN / "conversion-contract.json").read_text())
        assert covered == {(r["table"], r["column"]) for r in spec["source_columns"]}
        assert (
            new.execute(
                "SELECT count(*) FROM legacy_records WHERE source_table='resource_observations'"
            ).fetchone()[0]
            == 3
        )
        assert (
            new.execute(
                "SELECT count(*) FROM legacy_records WHERE source_table='document_versions'"
            ).fetchone()[0]
            == 3
        )
        assert (
            new.execute(
                "SELECT count(*) FROM legacy_records WHERE source_table='ref_observations'"
            ).fetchone()[0]
            == 2
        )
        assert tuple(new.execute("SELECT id,name FROM repositories").fetchone()) == (
            REPO_ID,
            "synthetic/repo",
        )
        assert (
            new.execute("SELECT db_instance_id FROM database_identity").fetchone()[0]
            != new.execute(
                "SELECT source_db_instance_id FROM conversion_sources"
            ).fetchone()[0]
        )
        assert (
            new.execute(
                "SELECT count(DISTINCT storage_type) FROM legacy_values"
            ).fetchone()[0]
            == 5
        )
        assert (
            new.execute(
                "SELECT count(*) FROM legacy_values WHERE storage_type='text' AND value_bytes=x'fffe00'"
            ).fetchone()[0]
            == 1
        )
        codes = {r[0] for r in new.execute("SELECT code FROM validation_results")}
        assert {
            "MALFORMED_TEXT",
            "INVALID_LEGACY_BOOLEAN",
            "INVALID_LEGACY_STATE",
            "INVALID_LEGACY_JSON",
            "SOURCE_FOREIGN_KEY_VIOLATION",
            "PARTIAL_ACQUISITION_PRESERVED",
            "PAYLOAD_REPLAY_PENDING",
        } <= codes
        counts = tuple(
            new.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "legacy_records",
                "legacy_values",
                "id_mappings",
                "conversion_batches",
                "validation_results",
            )
        )
    again = worker(workspace)
    assert again["new_batches"] == 0
    with source.readonly(workspace / "target.sqlite3") as db:
        assert counts == tuple(
            db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "legacy_records",
                "legacy_values",
                "id_mappings",
                "conversion_batches",
                "validation_results",
            )
        )
    assert before == (contents(database), source.cache_inventory([cache]))
    assert engine.verify(workspace)["archive_complete"]


@pytest.mark.parametrize(
    "point", ["before_insert", "after_data", "after_mapping", "before_commit"]
)
@pytest.mark.parametrize("hard_exit", [False, True])
def test_precommit_fault_has_no_partial_output_and_restarts(sealed, point, hard_exit):
    database, _, workspace = sealed
    before = contents(database)
    worker(
        workspace,
        "--fault",
        point,
        *(["--hard-exit"] if hard_exit else []),
        expected=77 if hard_exit else 2,
    )
    # A killed writer leaves a hot target journal, never a source sidecar.
    with target.connect(workspace / "target.sqlite3") as db:
        for table in (
            "legacy_records",
            "legacy_values",
            "id_mappings",
            "conversion_batches",
        ):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert worker(workspace)["archive_complete"]
    assert contents(database) == before


@pytest.mark.parametrize("hard_exit", [False, True])
def test_postcommit_crash_recognized_without_duplication(sealed, hard_exit):
    _, _, workspace = sealed
    worker(
        workspace,
        "--fault",
        "after_commit",
        *(["--hard-exit"] if hard_exit else []),
        expected=77 if hard_exit else 2,
    )
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_batches").fetchone()[0] == 1
    assert worker(workspace)["archive_complete"]
    assert worker(workspace)["new_batches"] == 0


def test_fault_during_resume_does_not_replay_committed_work(sealed):
    _, _, workspace = sealed
    assert not worker(workspace, "--max-batches", "3")["archive_complete"]
    worker(workspace, "--fault", "during_resume", "--hard-exit", expected=77)
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_batches").fetchone()[0] == 3
    assert worker(workspace)["archive_complete"]


@pytest.mark.parametrize("change", ["sealed", "original", "replacement", "cache"])
def test_source_change_blocks_resume(sealed, change):
    database, cache, workspace = sealed
    worker(workspace, "--max-batches", "1")
    if change == "replacement":
        copy = database.with_suffix(".replacement")
        shutil.copyfile(database, copy)
        os.replace(copy, database)
    elif change == "cache":
        (cache / "objects/evidence").write_bytes(b"changed")
    else:
        path = workspace / "source.sqlite3" if change == "sealed" else database
        path.chmod(0o644)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE catalog_meta SET publication_seq=999")
    with pytest.raises(ConversionError):
        engine.convert(workspace, batch_size=2, map_repositories=True)
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_batches").fetchone()[0] == 1


@pytest.mark.parametrize(
    "mismatch", ["ddl", "contract", "parser", "converter", "target-schema", "output"]
)
def test_resume_rejects_version_or_output_mismatch(sealed, tmp_path, mismatch):
    _, _, workspace = sealed
    worker(workspace, "--max-batches", "1")
    options = {}
    if mismatch in {"ddl", "contract"}:
        name = "target-schema.sql" if mismatch == "ddl" else "conversion-contract.json"
        altered = tmp_path / name
        altered.write_bytes((DESIGN / name).read_bytes() + b"\n")
        options[mismatch] = altered
    else:
        with target.connect(workspace / "target.sqlite3") as db:
            if mismatch == "parser":
                db.execute("UPDATE conversion_runs SET parser_version='wrong'")
            elif mismatch == "converter":
                manifest = json.loads(
                    db.execute("SELECT manifest FROM conversion_runs").fetchone()[0]
                )
                manifest["converter_sha256"] = "0" * 64
                db.execute(
                    "UPDATE conversion_runs SET manifest=?", (json.dumps(manifest),)
                )
            elif mismatch == "target-schema":
                db.execute("CREATE TABLE unexpected(x INTEGER)")
            else:
                db.execute("DROP TRIGGER legacy_values_immutable")
                db.execute("UPDATE legacy_values SET value_bytes=x'ff'")
                # Restoring the trigger keeps the schema fingerprint intact;
                # output proof must still catch the corrupted saved bytes.
                sql = (DESIGN / "target-schema.sql").read_text()
                statement = next(
                    s
                    for s in sql.splitlines()
                    if s.startswith("CREATE TRIGGER legacy_values_immutable ")
                )
                db.execute(statement)
    with pytest.raises(ConversionError):
        engine.convert(workspace, batch_size=2, map_repositories=True, **options)


def test_source_open_rejects_sidecars_schema_and_checksum(tmp_path):
    path = tmp_path / "v2.sqlite3"
    make_source(path)
    sidecar = Path(str(path) + "-wal")
    sidecar.write_bytes(b"synthetic")
    with pytest.raises(ConversionError, match="SOURCE_NOT_SEALED"):
        with source.readonly(path):
            pass
    sidecar.unlink()  # Only this synthetic dummy sidecar, not real WAL recovery.
    with sqlite3.connect(path) as db:
        db.execute("UPDATE schema_migrations SET checksum='wrong'")
    with (
        source.readonly(path) as db,
        pytest.raises(ConversionError, match="MIGRATIONS"),
    ):
        source.identify(db)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unsupported(x TEXT)")
    with source.readonly(path) as db, pytest.raises(ConversionError, match="SCHEMA"):
        source.identify(db)


def test_insufficient_space_and_write_failure_leave_source(sealed):
    database, _, workspace = sealed
    before = contents(database)
    with pytest.raises(ConversionError, match="INSUFFICIENT_SPACE"):
        engine.convert(workspace, free_bytes=0)
    assert not (workspace / "target.sqlite3").exists()
    worker(workspace, "--fault", "after_data", expected=2)
    assert contents(database) == before
    assert worker(workspace)["archive_complete"]


def test_mapping_allocation_stable_and_conflicts_rejected(sealed):
    _, _, workspace = sealed
    worker(workspace)
    with target.connect(workspace / "target.sqlite3") as db:
        record_id = db.execute(
            "SELECT id FROM legacy_records WHERE source_table='repositories'"
        ).fetchone()[0]
        original = mapping.lookup(db, record_id, "repositories")
        assert mapping.allocate(db, record_id, "repositories", REPO_ID) == original
        with pytest.raises(ConversionError, match="CONFLICT"):
            mapping.allocate(db, record_id, "repositories", "different")
        db.execute("BEGIN")
        with pytest.raises(ConversionError, match="CONFLICT"):
            mapping.persist(
                db, record_id, "repositories", tagged_key([("text", b"different")])
            )
        db.rollback()
    with target.connect(workspace / "target.sqlite3") as db:
        assert mapping.lookup(db, record_id, "repositories") == original


def test_source_serialization_repeated_is_identical(sealed):
    database, _, workspace = sealed
    with (
        source.readonly(database) as a,
        source.readonly(workspace / "source.sqlite3") as b,
    ):
        for table in (
            "sources",
            "ref_observations",
            "jobs",
            "contents",
            "schema_migrations",
        ):
            assert list(archive.rows(a, table)) == list(archive.rows(b, table))
    assert tagged_key([("null", None)]) != tagged_key([("text", b"")])
    assert (
        len(
            {
                tagged_key([(kind, value)])
                for kind, value in (
                    ("integer", 1),
                    ("real", 1.0),
                    ("text", b"1"),
                    ("blob", b"1"),
                )
            }
        )
        == 4
    )
    assert tagged_key([("text", b"a"), ("text", b"bc")]) != tagged_key(
        [("text", b"ab"), ("text", b"c")]
    )


@pytest.mark.parametrize(
    "point", ["after_data", "after_mapping", "before_commit", "after_commit"]
)
def test_fault_in_actual_repository_mapping_batch(sealed, point):
    _, _, workspace = sealed
    worker(
        workspace,
        "--fault",
        point,
        "--fault-table",
        "repositories",
        "--hard-exit",
        expected=77,
    )
    with target.connect(workspace / "target.sqlite3") as db:
        committed = point == "after_commit"
        assert db.execute("SELECT count(*) FROM repositories").fetchone()[0] == int(
            committed
        )
        assert db.execute("SELECT count(*) FROM id_mappings").fetchone()[0] == int(
            committed
        )
        previous = tuple(tuple(r) for r in db.execute("SELECT * FROM id_mappings"))
    assert worker(workspace)["archive_complete"]
    if previous:
        with source.readonly(workspace / "target.sqlite3") as db:
            assert previous == tuple(
                tuple(r) for r in db.execute("SELECT * FROM id_mappings")
            )


def test_uuid_allocation_and_target_writes_commit_together(sealed):
    _, _, workspace = sealed
    worker(workspace)
    with target.connect(workspace / "target.sqlite3") as db:
        record_id = db.execute(
            "SELECT id FROM legacy_records WHERE source_table='jobs'"
        ).fetchone()[0]
        key = mapping.allocate(db, record_id, "repositories")
        identity = key[9:].decode()  # P1 TEXT TLV, one UUID element.
        db.execute("BEGIN")
        db.execute(
            "INSERT INTO repositories VALUES(?,'synthetic-allocated',NULL,NULL,'{}')",
            (identity,),
        )
        mapping.persist(db, record_id, "repositories", key)
        db.execute("COMMIT")
    with target.connect(workspace / "target.sqlite3") as db:
        assert mapping.allocate(db, record_id, "repositories") == key
        other = db.execute(
            "SELECT id FROM legacy_records WHERE source_table='contents'"
        ).fetchone()[0]
        db.execute("BEGIN")
        with pytest.raises(ConversionError, match="COLLISION"):
            mapping.persist(db, other, "repositories", key)
        db.rollback()


def test_sqlite_full_rolls_back_failed_batch_and_source_is_unchanged(
    tmp_path, monkeypatch
):
    database = tmp_path / "legacy.sqlite3"
    cache = make_source(database)
    with sqlite3.connect(database) as db:
        body = b"synthetic" * (256 * 1024)
        db.execute(
            "UPDATE api_responses SET body=?,payload_sha256=?",
            (body, hashlib.sha256(body).digest()),
        )
    workspace = tmp_path / "conversion"
    engine.seal_input(database, workspace, [cache])
    before = contents(database)
    engine.convert(workspace, batch_size=2, max_batches=0)
    connect = target.connect

    def limited(path):
        db = connect(path)
        pages = db.execute("PRAGMA page_count").fetchone()[0]
        db.execute(f"PRAGMA max_page_count={pages}")
        return db

    with monkeypatch.context() as patch:
        patch.setattr(target, "connect", limited)
        with pytest.raises(sqlite3.OperationalError, match="full"):
            engine.convert(workspace, batch_size=2)
    with source.readonly(workspace / "target.sqlite3") as db:
        assert (
            db.execute(
                "SELECT count(*) FROM legacy_records WHERE source_table='api_responses'"
            ).fetchone()[0]
            == 0
        )
    assert contents(database) == before
    assert engine.convert(workspace, batch_size=2)["archive_complete"]


def test_live_wal_is_rejected_without_checkpoint(tmp_path):
    database = tmp_path / "live.sqlite3"
    db = sqlite3.connect(database)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE live_data(x)")
    db.commit()
    wal = Path(str(database) + "-wal")
    before = database.read_bytes(), wal.read_bytes()
    try:
        with pytest.raises(ConversionError, match="SOURCE_NOT_SEALED"):
            engine.seal_input(database, tmp_path / "conversion")
        assert before == (database.read_bytes(), wal.read_bytes())
    finally:
        db.close()


def test_standalone_entrypoint_seal_archive_verify(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    cache = make_source(database)
    workspace = tmp_path / "conversion"
    for action, options in (
        ("seal", ["--source", str(database), "--source-cache", str(cache)]),
        ("archive", []),
        ("verify", []),
    ):
        entry = [sys.executable, "scripts/offline_convert.py"]
        if os.environ.get("TEST_SQLITE_MINIMUM") or sqlite3.sqlite_version_info < (
            3,
            46,
            1,
        ):
            entry = [
                sys.executable,
                "-c",
                "from scripts.sqlite_minimum import activate;activate();import runpy;runpy.run_path('scripts/offline_convert.py',run_name='__main__')",
            ]
        child = subprocess.run(
            [
                *entry,
                action,
                "--work-dir",
                str(workspace),
                *options,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert child.returncode == 0, child.stderr
        assert json.loads(child.stdout)
