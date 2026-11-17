"""The architectural audit must expose uncertainty and never mutate its input."""

import json
import sqlite3
from pathlib import Path

from scripts.audit_phase2_dependencies import (
    cli_inventory,
    prepare,
    schema_inventory,
    source_inventory,
)

ROOT = Path(__file__).resolve().parents[2]


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


def test_sql_helpers_compile_without_executing_or_treating_file_writes_as_sql(
    tmp_path,
):
    source = tmp_path / "src"
    source.mkdir()
    (source / "service.py").write_text("""
class SqlPort:
    def read(self, sql, args=()):
        return self.driver.execute(sql, args).fetchone()
    def read_again(self, sql):
        return self.read(sql)
    def run(self, store, table):
        store.one("SELECT value FROM observations WHERE id=?", (1,))
        store.all("SELECT value FROM admitted")
        self.read("UPDATE observations SET value='changed' WHERE id=1")
        self.read_again(f"SELECT * FROM {table}")
class FilePort:
    def write(self, data):
        return self.stream.write(data)
    def run(self):
        self.write("DELETE FROM observations")
def unrelated():
    all("SELECT value FROM observations")
""")
    with catalog() as db:
        before = list(db.iterdump())
        report = source_inventory(tmp_path, db, {"observations", "admitted"})
        assert list(db.iterdump()) == before
    sites = [site for site in report["sql_sites"] if site["caller"].endswith(".run")]
    assert {site["target"] for site in sites} == {
        "store.one",
        "store.all",
        "self.read",
        "self.read_again",
    }
    statements = {
        site["target"]: report["sql_statements"][site["statement"]] for site in sites
    }
    for target in ("store.one", "store.all", "self.read"):
        assert statements[target]["preparation"]["status"] == "compiled"
    assert (
        statements["self.read_again"]["preparation"]["status"] == "dynamic_or_non_dml"
    )
    assert not any(
        site["caller"].endswith(":unrelated") for site in report["sql_sites"]
    )


def test_current_role_audit_has_separate_authority_definitions_without_legacy_driver():
    from scripts.audit_phase2_dependencies import build_report

    report = build_report()
    assert set(report["stores"]) == {
        "p1.core",
        "p1.context",
        "p1.operational",
        "p1.search",
        "access",
        "filesystem",
        "worktrees",
    }
    core, context = report["stores"]["p1.core"], report["stores"]["p1.context"]
    assert "resources" in context["tables"] and "resources" not in core["tables"]
    assert "text_bodies" in context["tables"] and "text_bodies" not in core["tables"]
    assert "git_objects" in core["tables"] and "git_objects" not in context["tables"]
    modules = report["source"]["modules"]
    assert any("production_context.py" in module["path"] for module in modules)
    assert any("p1_core.py" in module["path"] for module in modules)
    assert "not operation reachability" in report["limits"][0]


def test_native_preparation_keeps_current_field_conflict_and_exact_source_scope_dependencies():
    from repo_catalog.adapters.sqlite import p1_schema

    with sqlite3.connect(":memory:", isolation_level=None) as db:
        p1_schema.register_functions(db, "context")
        p1_schema.configure(db, "context")
        ddl = p1_schema.compose("context")
        db.executescript(ddl)
        before = db.total_changes
        report = schema_inventory(db, ddl)
        assert db.total_changes == before
        tables = report["tables"]
        assert "field_candidates" in tables and "text_bodies" in tables
        assert "source_coverage_proofs" in tables
        assert "source_inventory_evidence" in tables
        assert "local_revision" not in {
            column["name"] for table in tables.values() for column in table["columns"]
        }
        assert all(
            item["status"] in {"compiled", "not_compiled"}
            for item in report["prepared_mutations"].values()
        )


def test_actual_context_readers_compile_body_conflict_and_source_scope_dependencies(
    tmp_path,
):
    from repo_catalog.adapters.sqlite import p1_schema

    source = tmp_path / "src"
    source.mkdir()
    for name in ("p1_context.py", "production_context.py"):
        origin = ROOT / "packages/context/src/repo_catalog/adapters/sqlite" / name
        (source / name).write_bytes(origin.read_bytes())
    db = sqlite3.connect(":memory:", isolation_level=None)
    try:
        p1_schema.register_functions(db, "context")
        p1_schema.configure(db, "context")
        db.executescript(p1_schema.compose("context"))
        report = source_inventory(
            tmp_path, db, set(schema_inventory(db, "context")["objects"])
        )
        reads = {
            (access["object"], access["column"])
            for statement in report["sql_statements"].values()
            if statement["preparation"]["status"] == "compiled"
            for access in statement["preparation"].get("accesses", ())
            if access["operation"] == "read"
        }
        assert ("text_bodies", "text_value") in reads
        assert {
            ("field_candidates", column)
            for column in ("value_json", "clock_json", "provenance_json")
        } <= reads
        assert {
            ("source_inventory_evidence", column)
            for column in ("source_registration_uuidv4", "scope_json", "observed_at_us")
        } <= reads
        assert db.total_changes == 0
    finally:
        db.close()
