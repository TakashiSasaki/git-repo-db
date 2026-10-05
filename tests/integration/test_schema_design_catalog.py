import csv
import json
from pathlib import Path

import pytest

from scripts.schema_design_catalog import rows


def test_every_v2_column_has_reviewable_conversion_correspondence():
    root = Path(__file__).resolve().parents[2] / "docs/schema-hardening"
    inventory = json.loads((root / "current-schema.json").read_text())
    expected = {
        (table["name"], column["name"])
        for table in inventory["tables"]
        for column in table["columns"]
    }
    with (root / "column-conversion.csv").open() as stream:
        recorded = list(csv.DictReader(stream))
    assert len(recorded) == len(expected) == 287
    assert {(r["source_table"], r["source_column"]) for r in recorded} == expected
    assert recorded == rows(inventory)
    assert all(
        r["target"] and r["relation"] and r["transform_rules"] and r["failure_policy"]
        for r in recorded
    )


def test_new_source_table_requires_mapping_review():
    root = Path(__file__).resolve().parents[2] / "docs/schema-hardening"
    inventory = json.loads((root / "current-schema.json").read_text())
    inventory["tables"].append({"name": "unrecognized_table", "columns": []})
    with pytest.raises(ValueError, match="Review required"):
        rows(inventory)
