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

import hashlib
import re
import tempfile
from pathlib import Path

from scripts.schema_inventory import (
    CORE_GROUPS,
    LOGICAL_DEPENDENCIES,
    OPERATIONAL_GROUPS,
    SEARCH_GROUPS,
    introspect_all,
    introspect_store,
    validate_functional_groups_consistency,
    validate_logical_dependencies,
)

from tools.schema_viz import (
    check_artifacts,
    generate_all_artifacts,
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


def test_15_generated_column_classifications():
    """C1: Generated column types are correctly classified as VIRTUAL or STORED."""
    ir = introspect_all()
    core_tables = ir["stores"]["core"]["tables"]

    # 1. Production column verification
    # issue_resources.parent_kind
    ir_cols = {c["name"]: c for c in core_tables["issue_resources"]["columns"]}
    assert ir_cols["parent_kind"]["is_generated"] is True
    assert ir_cols["parent_kind"]["generation_type"] == "VIRTUAL"

    # review_resources.parent_review_kind and reply_kind
    rr_cols = {c["name"]: c for c in core_tables["review_resources"]["columns"]}
    assert rr_cols["parent_review_kind"]["is_generated"] is True
    assert rr_cols["parent_review_kind"]["generation_type"] == "VIRTUAL"
    assert rr_cols["reply_kind"]["is_generated"] is True
    assert rr_cols["reply_kind"]["generation_type"] == "VIRTUAL"

    # 2. Artifact verification (DBML and HTML)
    artifacts = generate_all_artifacts(ir, "all")
    core_dbml = artifacts["dbml/core.dbml"]
    assert "parent_kind text [note: 'GENERATED VIRTUAL']" in core_dbml
    assert "parent_review_kind text [note: 'GENERATED VIRTUAL']" in core_dbml
    assert "reply_kind text [note: 'GENERATED VIRTUAL']" in core_dbml
    assert "GENERATED STORED" not in core_dbml

    html_content = artifacts["index.html"]
    assert '"generation_type":"VIRTUAL"' in html_content
    assert '"generation_type":"STORED"' not in html_content
    start_token = "const SCHEMA_DATA = "
    start_pos = html_content.find(start_token) + len(start_token)
    end_pos = html_content.find(";\n", start_pos)
    import json

    html_data = json.loads(html_content[start_pos:end_pos])
    html_col_map = {
        c["name"]: c
        for c in html_data["stores"]["core"]["tables"]["issue_resources"]["columns"]
    }
    assert html_col_map["parent_kind"]["generation_type"] == "VIRTUAL"

    # 3. Synthetic schema verification with both VIRTUAL and STORED columns
    syn_ddl = """
    CREATE TABLE syn_gen_test (
        id INTEGER PRIMARY KEY,
        raw_val TEXT NOT NULL,
        virt_val TEXT GENERATED ALWAYS AS (lower(raw_val)) VIRTUAL,
        stor_val TEXT GENERATED ALWAYS AS (upper(raw_val)) STORED
    ) STRICT;
    """
    syn_hash = hashlib.sha256(syn_ddl.encode()).digest()
    syn_store = introspect_store(
        "synthetic",
        "Synthetic Store",
        "synthetic.db",
        "syn-format",
        1,
        syn_hash,
        syn_ddl,
        {"synthetic_group": ["syn_gen_test"]},
    )
    syn_cols = {c["name"]: c for c in syn_store["tables"]["syn_gen_test"]["columns"]}
    assert syn_cols["virt_val"]["is_generated"] is True
    assert syn_cols["virt_val"]["generation_type"] == "VIRTUAL"
    assert syn_cols["stor_val"]["is_generated"] is True
    assert syn_cols["stor_val"]["generation_type"] == "STORED"


def test_16_single_column_unique_and_dbml_fidelity():
    """C2: Single-column UNIQUE constraints and unique indexes are exported faithfully in DBML."""
    ir = introspect_all()
    core_tables = ir["stores"]["core"]["tables"]

    # 1. Regression test on production text_bodies.sha256
    tb = core_tables["text_bodies"]
    assert any(
        u["columns"] == ["sha256"] and not u.get("partial", False)
        for u in tb["unique_constraints"]
    )

    artifacts = generate_all_artifacts(ir, "dbml")
    core_dbml = artifacts["dbml/core.dbml"]

    # text_bodies definition must preserve sha256 uniqueness
    assert "Table text_bodies {" in core_dbml
    tb_block = core_dbml.split("Table text_bodies {")[1].split("}")[0]
    assert "sha256 blob [not null, unique]" in tb_block
    # Ensure text_body_id is marked pk and not unique
    assert "text_body_id integer [pk]" in tb_block
    assert "text_body_id integer [pk, unique]" not in tb_block
    # Ensure sha256 is not duplicated inside indexes block
    assert "sha256 [unique]" not in tb_block

    # 2. Synthetic verification of composite PK, composite UNIQUE, and single-column UNIQUE
    syn_ddl = """
    CREATE TABLE syn_constraints (
        org_id INTEGER NOT NULL,
        repo_id INTEGER NOT NULL,
        identifier TEXT NOT NULL UNIQUE,
        code TEXT NOT NULL,
        tag TEXT NOT NULL,
        PRIMARY KEY (org_id, repo_id),
        UNIQUE (code, tag)
    ) STRICT;
    """
    syn_hash = hashlib.sha256(syn_ddl.encode()).digest()
    syn_store = introspect_store(
        "synthetic",
        "Synthetic Store",
        "synthetic.db",
        "syn-format",
        1,
        syn_hash,
        syn_ddl,
        {"synthetic_group": ["syn_constraints"]},
    )
    from tools.schema_viz import _render_dbml_table

    rendered_dbml = _render_dbml_table(syn_store["tables"]["syn_constraints"])
    assert "identifier text [not null, unique]" in rendered_dbml
    assert "(org_id, repo_id) [pk]" in rendered_dbml
    assert "(code, tag) [unique]" in rendered_dbml
    # Verify identifier is not repeated in the indexes block
    assert (
        "indexes {\n    (org_id, repo_id) [pk]\n    (code, tag) [unique]\n  }"
        in rendered_dbml
    )


def test_17_partial_unique_indexes_not_unconditional():
    """C3: Partial unique indexes are not misrepresented as unconditional constraints in DBML."""
    ir = introspect_all()
    core_tables = ir["stores"]["core"]["tables"]

    # 1. Production coverage_scopes verification
    cs = core_tables["coverage_scopes"]
    # Unconditional unique constraints must NOT include the partial index
    assert not any(
        u["name"] == "coverage_scope_repository_kind" for u in cs["unique_constraints"]
    )

    # Indexes list must capture the partial unique index with its predicate
    cs_idx = {i["name"]: i for i in cs["indexes"]}
    assert "coverage_scope_repository_kind" in cs_idx
    assert cs_idx["coverage_scope_repository_kind"]["unique"] is True
    assert cs_idx["coverage_scope_repository_kind"]["partial"] is True
    assert "WHERE" in cs_idx["coverage_scope_repository_kind"]["sql"]
    assert (
        "change_request_id IS NULL"
        in cs_idx["coverage_scope_repository_kind"]["predicate"]
    )

    # DBML must not emit unconditional unique constraint for coverage_scopes
    artifacts = generate_all_artifacts(ir, "dbml")
    core_dbml = artifacts["dbml/core.dbml"]
    cs_block = core_dbml.split("Table coverage_scopes {")[1].split("}")[0]
    assert "(repository_uuidv4, kind) [unique]" not in cs_block
    assert (
        "(repository_uuidv4, kind) [name: 'coverage_scope_repository_kind', note: 'UNIQUE WHERE change_request_id IS NULL']"
        in cs_block
    )

    # 2. Synthetic verification of single/composite ordinary vs partial unique indexes
    syn_ddl = """
    CREATE TABLE syn_idx_variety (
        id INTEGER PRIMARY KEY,
        regular_u TEXT NOT NULL UNIQUE,
        comp_a TEXT NOT NULL,
        comp_b TEXT NOT NULL,
        part_s TEXT,
        part_c1 TEXT,
        part_c2 TEXT,
        non_u TEXT,
        UNIQUE (comp_a, comp_b)
    ) STRICT;
    CREATE UNIQUE INDEX idx_part_single ON syn_idx_variety(part_s) WHERE part_s IS NOT NULL;
    CREATE UNIQUE INDEX idx_part_comp ON syn_idx_variety(part_c1, part_c2) WHERE non_u = 'active';
    CREATE INDEX idx_non_unique_part ON syn_idx_variety(non_u) WHERE non_u IS NOT NULL;
    """
    syn_hash = hashlib.sha256(syn_ddl.encode()).digest()
    syn_store = introspect_store(
        "synthetic",
        "Synthetic Store",
        "synthetic.db",
        "syn-format",
        1,
        syn_hash,
        syn_ddl,
        {"synthetic_group": ["syn_idx_variety"]},
    )
    from tools.schema_viz import _render_dbml_table

    syn_table = syn_store["tables"]["syn_idx_variety"]
    syn_dbml = _render_dbml_table(syn_table)
    # Ordinary single unique on column
    assert "regular_u text [not null, unique]" in syn_dbml
    # Ordinary composite unique in indexes
    assert "(comp_a, comp_b) [unique]" in syn_dbml
    # Partial unique must have note and not unconditional unique
    assert (
        "(part_s) [name: 'idx_part_single', note: 'UNIQUE WHERE part_s IS NOT NULL']"
        in syn_dbml
    )
    assert (
        "(part_c1, part_c2) [name: 'idx_part_comp', note: 'UNIQUE WHERE non_u = \\'active\\'']"
        in syn_dbml
    )
    assert "(part_s) [unique" not in syn_dbml
    assert "(part_c1, part_c2) [unique" not in syn_dbml
    # Non-unique partial index
    assert (
        "(non_u) [name: 'idx_non_unique_part', note: 'partial index: WHERE non_u IS NOT NULL']"
        in syn_dbml
    )


def test_18_mermaid_relationship_cardinality_and_pk_formatting():
    """C4: Mermaid ER diagrams obey orientation-sensitive cardinality markers and clean PK rendering."""
    ir = introspect_all()
    artifacts = generate_all_artifacts(ir, "mermaid")

    rel_pattern = re.compile(
        r"^\s*([A-Za-z0-9_]+)\s+([|{}o]{2})--([|{}o]{2})\s+([A-Za-z0-9_]+)\s*:\s*\"([^\"]+)\"",
        re.MULTILINE,
    )
    valid_left = {"||", "|o", "}o", "}|"}
    valid_right = {"||", "o|", "o{", "|{"}

    for path, content in artifacts.items():
        assert path.startswith("mermaid/")
        for match in rel_pattern.finditer(content):
            parent_table, left_marker, right_marker, child_table, label = match.groups()
            assert left_marker in valid_left, (
                f"Invalid left cardinality marker '{left_marker}' in {path}: {match.group(0)}"
            )
            assert right_marker in valid_right, (
                f"Invalid right cardinality marker '{right_marker}' in {path}: {match.group(0)}"
            )
            # Critical C4 invariant: '|o' must never appear on the right side
            assert right_marker != "|o", (
                f"Right-hand cardinality marker '|o' is illegal in Mermaid ER ({path}): {match.group(0)}"
            )

        # Invariant: No PK column line contains "nullable"
        lines = content.splitlines()
        for i, line in enumerate(lines):
            line_str = line.strip()
            if "PK" in line_str and "nullable" in line_str:
                raise AssertionError(
                    f"PK column line contains 'nullable' in {path}:{i + 1}: {line}"
                )

        # Invariant: Composite PK in stubs must not concatenate columns onto a single line
        if "erDiagram" in content:
            assert "PK" in content
            for line in lines:
                if line.strip().startswith("TEXT ") and "PK" in line:
                    # Stub format: 'TEXT <col> PK "External reference..."'
                    col_part = line.strip().split()[1]
                    assert "," not in col_part, (
                        f"Comma found in stub PK column definition in {path}: {line}"
                    )


def test_19_cross_store_logical_dependencies_and_derivation_semantics():
    """C5: Cross-store logical relationships have verified semantics, valid columns, and polymorphic notes."""
    ir = introspect_all()

    # 1. Production logical dependencies validation passes cleanly
    errors = validate_logical_dependencies(ir)
    assert errors == [], f"Validation errors found in LOGICAL_DEPENDENCIES: {errors}"

    # 2. Invariants on LOGICAL_DEPENDENCIES
    for dep in LOGICAL_DEPENDENCIES:
        # Must not reference non-existent oid_hex column
        assert "oid_hex" not in dep.get("source_columns", [])
        assert "oid_hex" not in dep.get("target_columns", [])

    # Verify search_documents derivations
    git_dep = next(
        d for d in LOGICAL_DEPENDENCIES if d["id"] == "log_search_docs_git_objects"
    )
    assert git_dep["target_table"] == "git_objects"
    assert git_dep["target_columns"] == ["git_object_id"]
    assert git_dep.get("is_derivation") is True
    assert "git:<git_object_id>" in git_dep["description"]

    text_dep = next(
        d for d in LOGICAL_DEPENDENCIES if d["id"] == "log_search_docs_text_bodies"
    )
    assert text_dep["target_table"] == "text_bodies"
    assert text_dep["target_columns"] == ["sha256"]
    assert text_dep.get("is_derivation") is True
    assert "text_bodies.sha256" in text_dep["description"]

    # 3. Validation catches non-existent table or column
    fake_ir = {
        "stores": {
            "core": {"tables": {"t1": {"columns": [{"name": "c1"}]}}},
            "operational": {"tables": {"t2": {"columns": [{"name": "c2"}]}}},
        },
        "logical_dependencies": [
            {
                "id": "test_invalid_col",
                "source_store": "operational",
                "source_table": "t2",
                "source_columns": ["missing_col"],
                "target_store": "core",
                "target_table": "t1",
                "target_columns": ["c1"],
            },
            {
                "id": "test_invalid_table",
                "source_store": "operational",
                "source_table": "missing_table",
                "source_columns": ["c2"],
                "target_store": "core",
                "target_table": "t1",
                "target_columns": ["c1"],
            },
        ],
    }
    fake_errors = validate_logical_dependencies(fake_ir)
    assert any("source column 'missing_col' not found" in e for e in fake_errors)
    assert any("source table 'missing_table' not found" in e for e in fake_errors)


def test_20_functional_groups_and_tablegroups_consistency():
    """Section 4: Functional groups match audit_publication_free and TableGroups are emitted in combined DBML."""
    # 1. Classification matches audit_publication_free
    errors = validate_functional_groups_consistency()
    assert errors == [], f"Functional groups mismatch: {errors}"

    # 2. Group counts and table inventory
    assert len(CORE_GROUPS) == 7
    total_core_tables = sum(len(tables) for tables in CORE_GROUPS.values())
    assert total_core_tables == 70

    total_op_tables = sum(len(tables) for tables in OPERATIONAL_GROUPS.values())
    assert total_op_tables == 10

    total_search_tables = sum(len(tables) for tables in SEARCH_GROUPS.values())
    assert total_search_tables == 4

    total_tables = total_core_tables + total_op_tables + total_search_tables
    assert total_tables == 84

    # 3. combined.dbml TableGroup emission
    ir = introspect_all()
    artifacts = generate_all_artifacts(ir, "dbml")
    combined_dbml = artifacts["dbml/combined.dbml"]

    assert "TableGroup core_store {" in combined_dbml
    assert "TableGroup operational_store {" in combined_dbml
    assert "TableGroup search_store {" in combined_dbml

    core_group_block = combined_dbml.split("TableGroup core_store {")[1].split("}")[0]
    for t_name in ir["stores"]["core"]["tables"]:
        assert f"  {t_name}" in core_group_block

    op_group_block = combined_dbml.split("TableGroup operational_store {")[1].split(
        "}"
    )[0]
    for t_name in ir["stores"]["operational"]["tables"]:
        assert f"  {t_name}" in op_group_block

    search_group_block = combined_dbml.split("TableGroup search_store {")[1].split("}")[
        0
    ]
    for t_name in ir["stores"]["search"]["tables"]:
        assert f"  {t_name}" in search_group_block
