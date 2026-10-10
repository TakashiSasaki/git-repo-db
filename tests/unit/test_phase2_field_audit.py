"""Field audit supplements must preserve historical evidence and expose gaps."""

import ast
import json

import pytest

from scripts import audit_phase2_fields as audit


def test_field_audit_records_forwarded_sql_but_does_not_invent_file_dependencies():
    tree = ast.parse("""
class Resources:
    def _read(self, sql):
        return self.connection.execute(sql)
    async def query(self, store, table):
        store.one("SELECT metadata FROM issue_resources")
        store.all("SELECT settings FROM sources")
        self._read("SELECT body FROM text_bodies")
        self._read(f"SELECT * FROM {table}")
class Files:
    def write(self, data):
        return self.stream.write(data)
    def run(self):
        self.write("DELETE FROM issue_resources")
""")
    source = audit.SourceAudit("synthetic.py")
    source.visit(tree)
    assert len(source.sql_calls) == 4
    assert {tuple(call["tables"]) for call in source.sql_calls} == {
        ("issue_resources",),
        ("sources",),
        ("text_bodies",),
        (),
    }
    assert all(call["symbol"] == "Resources.query" for call in source.sql_calls)
    assert sum(call["dynamic_sql"] for call in source.sql_calls) == 1
    assert all(
        "not runtime reachability" in call["evidence"] for call in source.sql_calls
    )


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    path = tmp_path / "historical-fields.json"
    path.write_text(
        json.dumps(
            {
                "status": "Proposed / Pending Owner Decision",
                "field_groups": [{"id": "F20", "status": "Pending Q09"}],
                "generated_inventory": {
                    "schema_version": 18,
                    "ddl_sha256": "old-ddl",
                    "json_column_count": 57,
                },
            },
            indent=2,
        )
        + "\n"
    )
    monkeypatch.setattr(audit, "CONTRACT", path)
    monkeypatch.setattr(
        audit,
        "generated_inventory",
        lambda: {
            "schema_version": 19,
            "ddl_sha256": "current-ddl",
            "json_column_count": 57,
        },
    )
    return path


def test_default_check_identifies_both_revisions_and_preserves_snapshot(
    snapshot, monkeypatch
):
    before = snapshot.read_bytes()
    monkeypatch.setattr(audit.sys, "argv", ["audit_phase2_fields.py", "--check"])
    with pytest.raises(SystemExit) as failure:
        audit.main()
    message = str(failure.value)
    assert "Schema 18, DDL SHA-256 old-ddl" in message
    assert "Schema 19, DDL SHA-256 current-ddl" in message
    assert "Preserve the historical proposal snapshot" in message
    assert "--output artifacts/schema19-fields.json" in message
    assert "--check --output artifacts/schema19-fields.json" in message
    assert snapshot.read_bytes() == before


def test_separate_current_generation_and_check_keep_pending_policy_unchanged(
    snapshot, tmp_path, monkeypatch
):
    before = snapshot.read_bytes()
    output = tmp_path / "current-fields.json"
    monkeypatch.setattr(
        audit.sys, "argv", ["audit_phase2_fields.py", "--output", str(output)]
    )
    audit.main()
    generated = json.loads(output.read_text())
    assert generated["generated_inventory"]["schema_version"] == 19
    assert generated["field_groups"] == [{"id": "F20", "status": "Pending Q09"}]
    monkeypatch.setattr(
        audit.sys,
        "argv",
        ["audit_phase2_fields.py", "--check", "--output", str(output)],
    )
    audit.main()
    assert snapshot.read_bytes() == before
