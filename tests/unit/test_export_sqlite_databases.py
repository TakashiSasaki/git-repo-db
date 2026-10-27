"""Test authoritative SQLite database exporter for SchemaSpy and external tools."""

import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import scripts.export_sqlite_databases as exporter
from scripts.export_sqlite_databases import export_databases


def test_export_databases():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "specimens"
        dbs = export_databases(out_dir)

        assert "catalog.sqlite3" in dbs
        assert "operational.sqlite3" in dbs
        assert "search.sqlite3" in dbs
        assert "catalog.sql" in dbs
        assert "operational.sql" in dbs
        assert "search.sql" in dbs
        assert dbs["catalog.sql"].is_file()
        assert dbs["operational.sql"].is_file()
        assert dbs["search.sql"].is_file()

        # Core Store
        core_conn = sqlite3.connect(dbs["catalog.sqlite3"])
        try:
            core_tables = core_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            assert len(core_tables) == 70
        finally:
            core_conn.close()

        # Operational Store
        op_conn = sqlite3.connect(dbs["operational.sqlite3"])
        try:
            op_tables = op_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            assert len(op_tables) == 10
        finally:
            op_conn.close()

        # Search Store
        search_conn = sqlite3.connect(dbs["search.sqlite3"])
        try:
            search_tables = search_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            assert len(search_tables) == 4
        finally:
            search_conn.close()


def test_existing_destination_and_links_preserve_sentinels(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "catalog.sqlite3"
    sentinel.write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        export_databases(target)
    assert sentinel.read_bytes() == b"preserve"
    link = tmp_path / "linked"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        export_databases(link / "new")
    assert sentinel.read_bytes() == b"preserve"


def test_sidecar_and_failure_leave_no_output(tmp_path, monkeypatch):
    sidecar = tmp_path / "important.sqlite3-wal"
    sidecar.write_bytes(b"preserve")
    with pytest.raises(ValueError):
        export_databases(tmp_path / "new")
    assert sidecar.read_bytes() == b"preserve"
    sidecar.unlink()

    def fail(*args):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(exporter, "_publish_exclusive", fail)
    with pytest.raises(RuntimeError, match="injected"):
        export_databases(tmp_path / "new")
    assert list(tmp_path.iterdir()) == []


def test_concurrent_publish_has_one_winner(tmp_path):
    target = tmp_path / "new"

    def run():
        try:
            return export_databases(target)
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(list(target.iterdir())) == 6
    assert not list(tmp_path.glob(".schema-export-*"))


@pytest.mark.parametrize("kind", ["empty", "symlink", "hardlink", "sidecar"])
def test_existing_aliases_never_overwritten(tmp_path, kind):
    outside = tmp_path / "outside"
    outside.write_bytes(b"private")
    target = tmp_path / "output"
    target.mkdir()
    if kind == "symlink":
        (target / "catalog.sql").symlink_to(outside)
    elif kind == "hardlink":
        (target / "catalog.sqlite3").hardlink_to(outside)
    elif kind == "sidecar":
        (target / "catalog.sqlite3-wal").write_bytes(b"wal")
    before = {p.name for p in target.iterdir()}
    with pytest.raises(FileExistsError):
        export_databases(target)
    assert outside.read_bytes() == b"private"
    assert {p.name for p in target.iterdir()} == before


@pytest.mark.parametrize(
    "name", ["src/new", "docs/evidence/new", ".git/new", ".venv/new"]
)
def test_protected_checkout_paths(tmp_path, monkeypatch, name):
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        export_databases(tmp_path / name)
    assert list(tmp_path.iterdir()) == []


def test_missing_parents_and_source_fidelity(tmp_path):
    result = export_databases(tmp_path / "new" / "parents" / "output")
    for stem, factory in [
        ("catalog", exporter.schema_sql),
        ("operational", exporter.operational_schema_sql),
        ("search", exporter.search_schema_sql),
    ]:
        assert result[stem + ".sql"].read_text() == factory()
        with (
            sqlite3.connect(":memory:") as reference,
            sqlite3.connect(result[stem + ".sqlite3"]) as actual,
        ):
            reference.executescript(factory())
            query = (
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
            )
            assert (
                actual.execute(query).fetchall() == reference.execute(query).fetchall()
            )
            assert actual.execute("PRAGMA foreign_key_check").fetchall() == []


def test_construction_failure_cleans_only_own_stage(tmp_path, monkeypatch):
    connect = exporter.sqlite3.connect
    calls = 0
    sentinel = tmp_path / "unrelated"
    sentinel.mkdir()
    (sentinel / "keep").write_bytes(b"keep")

    def failing_connect(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second database failed")
        return connect(*args, **kwargs)

    monkeypatch.setattr(exporter.sqlite3, "connect", failing_connect)
    with pytest.raises(RuntimeError, match="second database"):
        export_databases(tmp_path / "output")
    assert [p.name for p in tmp_path.iterdir()] == ["unrelated"]
    assert (sentinel / "keep").read_bytes() == b"keep"


def test_racing_destination_is_preserved(tmp_path, monkeypatch):
    publish = exporter._publish_exclusive
    target = tmp_path / "output"

    def raced(fd, source, destination):
        target.mkdir()
        (target / "sentinel").write_bytes(b"winner")
        publish(fd, source, destination)

    monkeypatch.setattr(exporter, "_publish_exclusive", raced)
    with pytest.raises(FileExistsError):
        export_databases(target)
    assert (target / "sentinel").read_bytes() == b"winner"
    assert not list(tmp_path.glob(".schema-export-*"))


def test_external_checkout_ancestor_refused_before_mkdir(tmp_path):
    checkout = tmp_path / "other"
    checkout.mkdir()
    (checkout / ".git").write_bytes(b"gitdir: sentinel")
    with pytest.raises(ValueError, match="ancestor"):
        export_databases(checkout / "new" / "output")
    assert not (checkout / "new").exists()
    assert (checkout / ".git").read_bytes() == b"gitdir: sentinel"
