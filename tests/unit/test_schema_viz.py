"""Focused tests for the Three-Store Schema Visualization Workbench.

Validates the 11 structural requirements specified for schema introspection and generation:
1. All three schema definitions introspected successfully.
2. Generated table inventories match the production composed schemas.
3. Product tables are distinguished from SQLite internal and FTS shadow tables.
4. No physical FK is omitted or duplicated.
5. Composite foreign keys are grouped correctly.
6. All physical relationship endpoints exist in their appropriate store.
7. No cross-store logical relationship is falsely declared as an enforced SQLite FK.
8. All expected output formats are generated.
9. Output generation is deterministic.
10. "--check" succeeds after generation and fails when a generated output is modified.
11. Generation does not create or mutate persistent SQLite files.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scripts.schema_viz import (
    LOGICAL_DEPENDENCIES,
    check_artifacts,
    generate_all_artifacts,
    introspect_all,
    write_artifacts,
)


def test_1_introspection_success():
    """All three schema definitions can be introspected successfully."""
    ir = introspect_all()
    assert "core" in ir["stores"]
    assert "operational" in ir["stores"]
    assert "search" in ir["stores"]

    assert ir["stores"]["core"]["schema_version"] == 21
    assert ir["stores"]["operational"]["schema_version"] == 1
    assert ir["stores"]["search"]["schema_version"] == 1


def test_2_table_inventories_match():
    """Generated table inventories match the production composed schemas."""
    ir = introspect_all()
    core = ir["stores"]["core"]
    op = ir["stores"]["operational"]
    search = ir["stores"]["search"]

    # Baseline sanity check (derived from checked-out schema)
    assert core["table_count"] == 70
    assert op["table_count"] == 10
    assert search["table_count"] == 4
    assert ir["summary"]["total_product_tables"] == 84

    # Every table is classified in a known functional group
    for t_name, t_meta in core["tables"].items():
        assert t_meta["group"] != "unclassified", f"Core table {t_name} is unclassified"
    for t_name, t_meta in op["tables"].items():
        assert t_meta["group"] == "operational_store"
    for t_name, t_meta in search["tables"].items():
        assert t_meta["group"] == "search_store"


def test_3_product_tables_distinguished():
    """Product tables are distinguished from SQLite internal and FTS shadow tables."""
    ir = introspect_all()
    all_table_names = [
        t_name for s in ir["stores"].values() for t_name in s["tables"].keys()
    ]

    for name in all_table_names:
        assert not name.startswith("sqlite_"), (
            f"SQLite internal table {name} misclassified as product table"
        )
        assert not name.startswith("catalog_fts_"), (
            f"FTS shadow table {name} misclassified as product table"
        )


def test_4_no_physical_fk_omitted_or_duplicated():
    """No physical FK is omitted or duplicated."""
    ir = introspect_all()
    core = ir["stores"]["core"]
    op = ir["stores"]["operational"]
    search = ir["stores"]["search"]

    # Core has 121 FK constraints across 70 tables
    assert core["foreign_key_count"] == 121
    assert op["foreign_key_count"] == 9
    assert search["foreign_key_count"] == 2

    # Check that constraint IDs are unique per table
    for s in (core, op, search):
        for t_name, t_meta in s["tables"].items():
            fk_ids = [fk["id"] for fk in t_meta["foreign_keys"]]
            assert len(fk_ids) == len(set(fk_ids)), (
                f"Duplicate FK id in {t_name}: {fk_ids}"
            )


def test_5_composite_foreign_keys_grouped():
    """Composite foreign keys are grouped correctly into single constraints with multiple columns."""
    ir = introspect_all()
    core = ir["stores"]["core"]
    op = ir["stores"]["operational"]

    # Verify Core composite FK: acquisition_roots -> git_acquisitions
    acq_roots = core["tables"]["acquisition_roots"]
    comp_fks = [fk for fk in acq_roots["foreign_keys"] if fk["is_composite"]]
    assert len(comp_fks) == 1
    assert comp_fks[0]["target_table"] == "git_acquisitions"
    assert comp_fks[0]["from_columns"] == [
        "git_acquisition_id",
        "repository_uuidv4",
    ]
    assert comp_fks[0]["to_columns"] == [
        "git_acquisition_id",
        "repository_uuidv4",
    ]

    # Verify Operational composite FK: acquisition_progress -> job_attempts
    acq_prog = op["tables"]["acquisition_progress"]
    op_comp = [fk for fk in acq_prog["foreign_keys"] if fk["is_composite"]]
    assert len(op_comp) == 1
    assert op_comp[0]["target_table"] == "job_attempts"
    assert op_comp[0]["from_columns"] == ["job_id", "attempt"]
    assert op_comp[0]["to_columns"] == ["job_id", "attempt"]


def test_6_physical_fk_endpoints_exist_in_own_store():
    """All physical relationship endpoints exist in their appropriate store (Three-Store boundary)."""
    ir = introspect_all()
    for s_slug, s_data in ir["stores"].items():
        own_tables = set(s_data["tables"].keys())
        for t_name, t_meta in s_data["tables"].items():
            for fk in t_meta["foreign_keys"]:
                target_table = fk["target_table"]
                assert target_table in own_tables, (
                    f"Physical FK crosses store boundary: {s_slug}.{t_name} references {target_table}"
                )


def test_7_no_cross_store_logical_declared_as_physical_fk():
    """No cross-store logical relationship is falsely declared as an enforced SQLite FK."""
    ir = introspect_all()
    core_tables = set(ir["stores"]["core"]["tables"].keys())
    op_tables = set(ir["stores"]["operational"]["tables"].keys())
    search_tables = set(ir["stores"]["search"]["tables"].keys())

    # Verify logical dependencies
    for rel in LOGICAL_DEPENDENCIES:
        src_table = rel["source_table"]
        tgt_table = rel["target_table"]

        # Ensure source and target are in distinct stores
        assert rel["source_store"] != rel["target_store"]

        # Ensure no physical FK exists between them in SQLite schema
        src_store_tables = (
            core_tables
            if rel["source_store"] == "core"
            else op_tables
            if rel["source_store"] == "operational"
            else search_tables
        )
        assert src_table in src_store_tables

        t_meta = ir["stores"][rel["source_store"]]["tables"][src_table]
        physical_targets = [fk["target_table"] for fk in t_meta["foreign_keys"]]
        assert tgt_table not in physical_targets, (
            f"Logical relationship falsely declared as physical SQLite FK: {src_table} -> {tgt_table}"
        )


def test_8_all_output_formats_generated():
    """All expected output formats are generated."""
    ir = introspect_all()
    artifacts = generate_all_artifacts(ir, "all")

    # Check README
    assert "README.md" in artifacts

    # Check Mermaid files
    assert "mermaid/overview.md" in artifacts
    assert "mermaid/core-overview.md" in artifacts
    assert "mermaid/core-identity.md" in artifacts
    assert "mermaid/core-current-state.md" in artifacts
    assert "mermaid/core-coverage.md" in artifacts
    assert "mermaid/core-git.md" in artifacts
    assert "mermaid/core-cas.md" in artifacts
    assert "mermaid/core-exchange.md" in artifacts
    assert "mermaid/operational.md" in artifacts
    assert "mermaid/search.md" in artifacts

    # Check DBML files
    assert "dbml/core.dbml" in artifacts
    assert "dbml/operational.dbml" in artifacts
    assert "dbml/search.dbml" in artifacts
    assert "dbml/combined.dbml" in artifacts

    # Check Standalone HTML
    assert "index.html" in artifacts

    assert len(artifacts) == 16


def test_9_deterministic_generation():
    """Output generation is deterministic (byte-for-byte identical across runs)."""
    ir1 = introspect_all()
    artifacts1 = generate_all_artifacts(ir1, "all")

    ir2 = introspect_all()
    artifacts2 = generate_all_artifacts(ir2, "all")

    assert set(artifacts1.keys()) == set(artifacts2.keys())
    for path, content1 in artifacts1.items():
        content2 = artifacts2[path]
        assert content1 == content2, f"Nondeterministic output for {path}"


def test_10_check_mode_success_and_failure_on_mutation():
    """Check mode succeeds when clean and detects stale or modified outputs."""
    ir = introspect_all()
    artifacts = generate_all_artifacts(ir, "all")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        write_artifacts(artifacts, tmp_path)

        # 1. Clean check succeeds
        is_clean, mismatches = check_artifacts(artifacts, tmp_path)
        assert is_clean
        assert len(mismatches) == 0

        # 2. Tampered file is detected
        target = tmp_path / "mermaid" / "overview.md"
        target.write_text("modified content", encoding="utf-8")
        is_clean, mismatches = check_artifacts(artifacts, tmp_path)
        assert not is_clean
        assert any("mermaid/overview.md" in m for m in mismatches)

        # 3. Missing file is detected
        target.unlink()
        is_clean, mismatches = check_artifacts(artifacts, tmp_path)
        assert not is_clean
        assert any("Missing file: mermaid/overview.md" in m for m in mismatches)


def test_11_no_persistent_sqlite_files_created():
    """Introspection and generation does not create persistent SQLite files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        ir = introspect_all()
        artifacts = generate_all_artifacts(ir, "all")
        write_artifacts(artifacts, tmp_path)

        # Ensure no .sqlite3 or .db files exist in output
        db_files = list(tmp_path.glob("**/*.sqlite3")) + list(tmp_path.glob("**/*.db"))
        assert len(db_files) == 0, f"Persistent SQLite files created: {db_files}"


def test_12_html_viewer_smoke():
    """HTML viewer is 100% self-contained with no external network dependencies and valid embedded metadata."""
    import json

    ir = introspect_all()
    artifacts = generate_all_artifacts(ir, "html")
    html_text = artifacts["index.html"]

    assert "<!DOCTYPE html>" in html_text
    assert "const SCHEMA_DATA = " in html_text
    # No external stylesheet or script references
    assert 'href="http' not in html_text
    assert 'src="http' not in html_text

    # Extract JSON and parse
    start_token = "const SCHEMA_DATA = "
    start_pos = html_text.find(start_token) + len(start_token)
    end_pos = html_text.find(";\n", start_pos)
    embedded_json = html_text[start_pos:end_pos]

    data = json.loads(embedded_json)
    assert set(data["stores"].keys()) == {"core", "operational", "search"}
    assert data["summary"]["total_product_tables"] == 84


def test_13_mermaid_syntax_smoke():
    """Mermaid markdown files contain valid fenced blocks with balanced table blocks."""
    ir = introspect_all()
    artifacts = generate_all_artifacts(ir, "mermaid")

    for path, content in artifacts.items():
        assert path.startswith("mermaid/")
        assert "```mermaid" in content
        blocks = [b.split("```")[0] for b in content.split("```mermaid\n")[1:]]
        assert len(blocks) >= 1, f"No mermaid block in {path}"
        for block in blocks:
            assert "erDiagram" in block or "flowchart" in block
            if "erDiagram" in block:
                # In Mermaid erDiagram, table blocks use "table_name {" and "}"
                # while relationship lines use "o{" or "|{" as cardinality markers.
                table_open = [
                    line
                    for line in block.splitlines()
                    if line.strip().endswith("{")
                    and not line.strip().endswith("o{")
                    and not line.strip().endswith("|{")
                ]
                table_close = [
                    line for line in block.splitlines() if line.strip() == "}"
                ]
                assert len(table_open) == len(table_close), (
                    f"Mismatched table definition braces in {path}: {len(table_open)} open vs {len(table_close)} close"
                )


def test_14_dbml_syntax_smoke():
    """DBML files contain valid Project blocks, Table definitions, and balanced braces."""
    ir = introspect_all()
    artifacts = generate_all_artifacts(ir, "dbml")

    for path, content in artifacts.items():
        assert path.startswith("dbml/")
        assert content.count("{") == content.count("}"), f"Unbalanced braces in {path}"
        assert "Project " in content
        assert "Table " in content
