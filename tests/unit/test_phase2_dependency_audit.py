"""The architectural audit must expose uncertainty and never mutate its input."""

import json
import sqlite3

from scripts.audit_phase2_dependencies import (
    cli_inventory,
    prepare,
    schema_inventory,
    source_inventory,
)


def catalog():
    db = sqlite3.connect(":memory:", isolation_level=None, cached_statements=0)
    db.executescript("""
        PRAGMA foreign_keys=ON;
        PRAGMA recursive_triggers=ON;
        CREATE TABLE owners(a TEXT,b TEXT,PRIMARY KEY(a,b));
        CREATE TABLE observations(id INTEGER PRIMARY KEY,a TEXT,b TEXT,
          value TEXT, size INTEGER GENERATED ALWAYS AS (length(value)) STORED,
          FOREIGN KEY(a,b) REFERENCES owners(a,b));
        CREATE TABLE evidence(id INTEGER PRIMARY KEY);
        CREATE VIEW admitted AS SELECT id,value FROM observations;
        CREATE TRIGGER record_observation AFTER INSERT ON observations BEGIN
          INSERT INTO evidence VALUES(NEW.id);
        END;
        INSERT INTO owners VALUES('r','s');
        INSERT INTO observations(id,a,b,value) VALUES(1,'r','s','exact');
    """)
    return db


def test_compilation_records_native_view_trigger_edges_without_mutation():
    with catalog() as db:
        before = list(db.iterdump())
        report = schema_inventory(db, "synthetic")
        assert list(db.iterdump()) == before
        observations = report["tables"]["observations"]
        assert observations["foreign_keys"][0]["columns"] == ["a", "b"]
        assert observations["foreign_keys"][0]["targets"] == ["a", "b"]
        assert observations["columns"][4]["hidden"] == 3
        assert report["tables"]["owners"]["primary_key"] == ["a", "b"]
        assert any(
            access["object"] == "observations"
            for access in report["prepared_views"]["admitted"]["accesses"]
        )
        trigger = report["prepared_mutations"]["observations:insert"]
        assert any(
            access["object"] == "evidence" and access["context"] == "record_observation"
            for access in trigger["accesses"]
        )


def test_parameters_and_unknown_sql_are_reported_honestly():
    with catalog() as db:
        assert (
            prepare(db, "SELECT value FROM observations WHERE id=?")["status"]
            == "compiled"
        )
        assert (
            prepare(db, "SELECT value FROM observations WHERE id=:id")["status"]
            == "compiled"
        )
        report = prepare(db, "SELECT absent FROM observations")
        assert report["status"] == "not_compiled"
        assert "absent" in report["error"]


def test_source_inventory_separates_dynamic_sql_and_static_literals(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "service.py").write_text("""
class Service:
    def run(self, db, table):
        self.read(db)
        db.execute(f"SELECT * FROM {table}")
        untouched = "observations"
    def read(self, db):
        return db.execute("SELECT value FROM observations WHERE id=?", (1,))
""")
    with catalog() as db:
        report = source_inventory(tmp_path, db, {"observations"})
    assert len(report["local_call_edges"]) == 1
    assert report["local_call_edges"][0]["callee"] == "src/service.py:Service.read"
    dynamic, literal = report["sql_sites"]
    dynamic = report["sql_statements"][dynamic["statement"]]
    literal = report["sql_statements"][literal["statement"]]
    assert dynamic["preparation"]["status"] == "dynamic_or_non_dml"
    assert literal["preparation"]["status"] == "compiled"
    assert all(
        "not runtime reachability" in item["evidence"]
        for item in report["static_object_references"]
    )
    json.dumps(report)


def test_cli_inventory_expands_actual_parser_loops():
    import argparse

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers()
    for name in ("read", "check"):
        commands.add_parser(name).add_argument("--scope")
    assert cli_inventory(parser) == [
        {"command": "read", "options": ["--help", "--scope", "-h"]},
        {"command": "check", "options": ["--help", "--scope", "-h"]},
    ]
