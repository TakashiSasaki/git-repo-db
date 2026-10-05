import ast
import json

from scripts.schema_contract import ROOT, validate


def test_all_invariants_have_real_ddl_test_and_remaining_gate():
    _, target = validate()
    rows = json.loads((ROOT / "invariant-contract.json").read_text())["invariants"]
    assert [r["id"] for r in rows] == [f"I{i:02d}" for i in range(1, 32)]
    for row in rows:
        assert row["ddl_tables"] and set(row["ddl_tables"]) <= set(target)
        assert row["implemented"] and row["remaining"]
        for node in row["tests"]:
            path, function = node.split("::")
            tree = ast.parse((ROOT.parents[1] / path).read_text())
            assert function in {
                n.name for n in tree.body if isinstance(n, ast.FunctionDef)
            }


def test_generated_views_match_machine_contract():
    import csv

    from scripts.schema_contract import render_rows

    contract, _ = validate()
    with (ROOT / "column-conversion.csv").open() as stream:
        recorded = list(csv.DictReader(stream))
    assert recorded == render_rows(contract)
    recorded_target = json.loads((ROOT / "target-inventory.json").read_text())
    assert recorded_target["ddl_sha256"] == contract["ddl_sha256"]


def test_generated_markdown_view_matches_generator(tmp_path, monkeypatch):
    from scripts import schema_contract

    for name in (
        "target-schema.sql",
        "current-schema.json",
        "conversion-contract.json",
    ):
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    monkeypatch.setattr(schema_contract, "ROOT", tmp_path)
    schema_contract.generate()
    assert (tmp_path / "table-conversion.md").read_bytes() == (
        ROOT / "table-conversion.md"
    ).read_bytes()
