"""Generate design views from the machine-readable P1 conversion contract.

The empty v2 fixture inventory remains the source baseline. No real DB is opened.
"""

import argparse
import json
import re

if __package__:
    from .schema_contract import ROOT, generate, render_rows, validate
else:
    from schema_contract import ROOT, generate, render_rows, validate


def rows(inventory):
    contract, _ = validate()
    actual = {(t["name"], c["name"]) for t in inventory["tables"] for c in t["columns"]}
    expected = {(r["table"], r["column"]) for r in contract["source_columns"]}
    tables = {r["table"] for r in contract["source_columns"]}
    if actual != expected or {t["name"] for t in inventory["tables"]} != tables:
        raise ValueError("Review required: source inventory mismatch")
    return render_rows(contract)


def source_access(root, tables):
    result = {t: {"read": set(), "write": set(), "other": set()} for t in tables}
    pattern = re.compile(
        r"\b(INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM|FROM|JOIN)\s+([a-z_]+)\b",
        re.I,
    )
    for path in (root / "src").rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for match in pattern.finditer(line):
                table = match[2].lower()
                if table in result:
                    mode = "read" if match[1].upper() in ("FROM", "JOIN") else "write"
                    result[table][mode].add(f"{path.relative_to(root)}:{number}")
    return {t: {k: sorted(v) for k, v in modes.items()} for t, modes in result.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    generate()
    contract, _ = validate()
    tables = {r["table"] for r in contract["source_columns"]}
    (ROOT / "source-access.json").write_text(
        json.dumps(
            {
                "limitations": "Lexical SQL table references, not a call graph; dynamic SQL, filesystem and tests require manual review in README.md",
                "tables": source_access(ROOT.parents[1], tables),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
