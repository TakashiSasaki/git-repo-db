"""The architectural audit must expose uncertainty and never mutate its input."""

import json
import sqlite3
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.schema import schema_sql
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


@pytest.fixture(scope="module")
def production_readers(tmp_path_factory):
    root = tmp_path_factory.mktemp("production-reader-audit")
    for relative in (
        "application/issue_queries.py",
        "application/query_service.py",
        "adapters/sqlite/current_resources.py",
        "application/git_query_context.py",
        "adapters/git/parsing.py",
    ):
        target = root / "src/repo_catalog" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / "src/repo_catalog" / relative).read_text())
    with sqlite3.connect(":memory:", isolation_level=None, cached_statements=0) as db:
        register_git_object_sql_function(db)
        db.executescript(schema_sql())
        changes = db.total_changes
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_schema")}
        report = source_inventory(root, db, names)
        assert db.total_changes == changes
        assert db.execute("SELECT count(*) FROM issue_resources").fetchone() == (0,)
    return report


def accesses_for(report, symbol, sql_fragment):
    for site in report["sql_sites"]:
        if site["caller"].endswith(":" + symbol):
            statement = report["sql_statements"][site["statement"]]
            if statement["literal"] and sql_fragment in statement["literal"]:
                assert statement["preparation"]["status"] == "compiled"
                return {
                    (item["operation"], item["object"], item["column"])
                    for item in statement["preparation"]["accesses"]
                }
    pytest.fail(f"Missing SQL dependency for {symbol}: {sql_fragment}")


def test_actual_issue_eligibility_reader_includes_body_and_conflict_dependencies(
    production_readers,
):
    accesses = accesses_for(production_readers, "_eligible", "eligible_issue_resources")
    assert ("read", "issue_resources", "provider_resource_id") in accesses
    assert ("read", "text_bodies", "body") in accesses
    assert ("read", "exchange_staging", "record_json") in accesses


def test_actual_source_coverage_reader_includes_source_and_inventory_dependencies(
    production_readers,
):
    sources = accesses_for(
        production_readers, "QueryService.prepare_coverage", "sources"
    )
    inventory = accesses_for(
        production_readers,
        "QueryService.prepare_coverage",
        "source_inventory_assessments",
    )
    assert ("read", "sources", "source_id") in sources
    assert ("read", "source_inventory_assessments", "state") in inventory


def test_actual_git_name_reader_includes_explicit_decoder_evidence(production_readers):
    accesses = accesses_for(production_readers, "decoded_name", "git_name_facts")
    assert ("read", "git_name_facts", "decoder_key") in accesses
    assert ("read", "git_name_facts", "metadata_encoding") in accesses
    assert ("read", "git_name_facts", "parser_module") in accesses
    assert ("read", "git_name_facts", "parser_version") in accesses


def test_actual_decoder_candidate_queries_report_dynamic_sql_honestly(
    production_readers,
):
    sites = [
        site
        for site in production_readers["sql_sites"]
        if site["caller"].endswith(":decoded_fact")
        or site["caller"].endswith(":decoder_settings")
    ]
    assert sites
    for site in sites:
        assert (
            production_readers["sql_statements"][site["statement"]]["preparation"][
                "status"
            ]
            == "dynamic_or_non_dml"
        )
    refs = production_readers["static_object_references"]
    assert not any(
        ref.get("object") in {"parser_profiles", "parsed_results"} for ref in refs
    )


def test_actual_local_forwarders_preserve_revision_and_git_content_boundaries(
    production_readers,
):
    current = accesses_for(
        production_readers, "CurrentResources.capture_context", "local_revision"
    )
    git = accesses_for(production_readers, "GitParsing.object", "git_object_payloads")
    assert ("read", "database_identity", "local_revision") in current
    assert ("read", "git_objects", "verified") in git
    assert ("read", "git_object_payloads", "") in git
