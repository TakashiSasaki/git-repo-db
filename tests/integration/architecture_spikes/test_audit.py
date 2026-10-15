"""Exercise audit omission/drift detection against disposable authored artifacts."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "boundary_audit", ROOT / "scripts/audit_implementation_boundary.py"
)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


@pytest.fixture(scope="module")
def inventory():
    return AUDIT.introspect_all()


def test_all_production_tables_columns_and_guards_are_accounted_for():
    inventory, markdown = AUDIT.build()
    assert inventory["audit_contract"]["table_counts"] == {
        "core": 70,
        "operational": 10,
        "search": 4,
    }
    assert inventory["audit_contract"]["unclassified"] == []
    for store in inventory["stores"].values():
        assert len(store["ddl_sha256"]) == 64
        for name, table in store["tables"].items():
            assert name in markdown
            policy = table["implementation_recommendation"]
            assert set(policy["column_disposition"]) == {
                c["name"] for c in table["columns"]
            }
            assert set(table["update_guard_triggers"]) <= set(table["triggers"])
            assert set(table["triggers"]) <= set(store["triggers"])


def test_new_production_table_fails_instead_of_silently_omitting(
    monkeypatch, inventory
):
    changed = copy.deepcopy(inventory)
    changed["stores"]["core"]["tables"]["new_unreviewed_authority"] = {
        "name": "new_unreviewed_authority"
    }
    monkeypatch.setattr(AUDIT, "introspect_all", lambda: changed)
    with pytest.raises(ValueError, match="missing=.*new_unreviewed_authority"):
        AUDIT.build()


def test_new_column_requires_explicit_routing(monkeypatch, inventory):
    changed = copy.deepcopy(inventory)
    changed["stores"]["core"]["tables"]["git_objects"]["columns"].append(
        {"name": "new_unreviewed_fact"}
    )
    monkeypatch.setattr(AUDIT, "introspect_all", lambda: changed)
    with pytest.raises(ValueError, match="column disposition drift: git_objects"):
        AUDIT.build()


def test_check_reports_stale_ddl_fingerprint_without_overwriting(
    monkeypatch, tmp_path, inventory
):
    original = copy.deepcopy(inventory)
    monkeypatch.setattr(AUDIT, "introspect_all", lambda: original)
    monkeypatch.setattr(AUDIT, "OUTPUT", tmp_path)
    (tmp_path / "table-disposition.json").write_text(
        (ROOT / "docs/implementation/table-disposition.json").read_text()
    )
    monkeypatch.setattr(AUDIT.sys, "argv", ["boundary-audit"])
    assert AUDIT.main() == 0
    before = (tmp_path / "schema-inventory.json").read_bytes()
    changed = copy.deepcopy(inventory)
    changed["stores"]["core"]["ddl_sha256"] = "0" * 64
    monkeypatch.setattr(AUDIT, "introspect_all", lambda: changed)
    monkeypatch.setattr(AUDIT.sys, "argv", ["boundary-audit", "--check"])
    assert AUDIT.main() == 1
    assert (tmp_path / "schema-inventory.json").read_bytes() == before
    assert json.loads(before)["stores"]["core"]["ddl_sha256"] != "0" * 64
