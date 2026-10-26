"""Neutral inventory boundary controls; product checks never import rendering."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import schema_inventory

ROOT = Path(__file__).resolve().parents[2]


def test_product_audit_without_renderer_or_documentation_imports():
    script = r"""
import importlib.abc
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path[:0] = [str(root), str(root / "scripts"), str(root / "src")]
class RefuseDocumentation(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"schema_viz", "scripts.schema_viz"} or fullname.split(".")[0] in {"mkdocs", "material", "yaml"}:
            raise ImportError("documentation import forbidden: " + fullname)
sys.meta_path.insert(0, RefuseDocumentation())
from scripts.audit_implementation_boundary import build
inventory, report = build()
assert inventory and report
assert not any(name in sys.modules for name in ("schema_viz", "scripts.schema_viz", "mkdocs", "material", "yaml"))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_neutral_inventory_rejects_changed_ddl_fingerprint():
    with pytest.raises(ValueError, match="DDL hash mismatch"):
        schema_inventory.introspect_store(
            "fixture",
            "Fixture",
            "unused.sqlite3",
            "fixture",
            1,
            hashlib.sha256(b"different DDL").digest(),
            "CREATE TABLE item(id INTEGER PRIMARY KEY) STRICT;",
            {},
        )


def test_neutral_inventory_preserves_composite_generated_and_partial_metadata():
    ddl = """
    CREATE TABLE parent(a INTEGER, b INTEGER, PRIMARY KEY(a,b)) STRICT;
    CREATE TABLE child(
        a INTEGER, b INTEGER,
        virtual_value INTEGER GENERATED ALWAYS AS (a + b) VIRTUAL,
        stored_value INTEGER GENERATED ALWAYS AS (a * b) STORED,
        FOREIGN KEY(a,b) REFERENCES parent(a,b)
    ) STRICT;
    CREATE UNIQUE INDEX child_partial ON child(a) WHERE b > 0;
    """
    result = schema_inventory.introspect_store(
        "fixture",
        "Fixture",
        "unused.sqlite3",
        "fixture",
        1,
        hashlib.sha256(ddl.encode()).digest(),
        ddl,
        {},
    )
    child = result["tables"]["child"]
    assert len(child["foreign_keys"]) == 1
    assert child["foreign_keys"][0]["from_columns"] == ["a", "b"]
    assert child["foreign_keys"][0]["to_columns"] == ["a", "b"]
    assert child["foreign_keys"][0]["is_composite"]
    columns = {column["name"]: column for column in child["columns"]}
    assert columns["virtual_value"]["generation_type"] == "VIRTUAL"
    assert columns["stored_value"]["generation_type"] == "STORED"
    assert child["unique_constraints"] == []
    assert child["indexes"][0]["partial"]
    assert child["indexes"][0]["predicate"] == "b > 0"
    assert result["ddl_sha256"] == hashlib.sha256(ddl.encode()).hexdigest()


def test_inventory_export_refuses_unsafe_output_before_writing(tmp_path):
    target = tmp_path / "authoritative"
    target.mkdir()
    marker = target / "inventory.json"
    marker.write_text("unchanged sentinel")
    with pytest.raises(ValueError, match="output must remain"):
        schema_inventory.export_inventory(target, "0" * 40)
    assert marker.read_text() == "unchanged sentinel"
