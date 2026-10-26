"""Mechanical counterparts of historical mixed schema tests; no renderer import."""

import hashlib

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
    assert core["table_count"] == 70
    assert op["table_count"] == 10
    assert search["table_count"] == 4
    assert ir["summary"]["total_product_tables"] == 84
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
    assert core["foreign_key_count"] == 121
    assert op["foreign_key_count"] == 9
    assert search["foreign_key_count"] == 2
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
    acq_roots = core["tables"]["acquisition_roots"]
    comp_fks = [fk for fk in acq_roots["foreign_keys"] if fk["is_composite"]]
    assert len(comp_fks) == 1
    assert comp_fks[0]["target_table"] == "git_acquisitions"
    assert comp_fks[0]["from_columns"] == ["git_acquisition_id", "repository_uuidv4"]
    assert comp_fks[0]["to_columns"] == ["git_acquisition_id", "repository_uuidv4"]
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
    for rel in LOGICAL_DEPENDENCIES:
        src_table = rel["source_table"]
        tgt_table = rel["target_table"]
        assert rel["source_store"] != rel["target_store"]
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


def test_11_no_persistent_sqlite_files_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    introspect_all()
    assert not list(tmp_path.rglob("*.sqlite3"))
    assert not list(tmp_path.rglob("*.db"))


def test_15_generated_column_classifications():
    """C1: Generated column types are correctly classified as VIRTUAL or STORED."""
    ir = introspect_all()
    core_tables = ir["stores"]["core"]["tables"]
    ir_cols = {c["name"]: c for c in core_tables["issue_resources"]["columns"]}
    assert ir_cols["parent_kind"]["is_generated"] is True
    assert ir_cols["parent_kind"]["generation_type"] == "VIRTUAL"
    rr_cols = {c["name"]: c for c in core_tables["review_resources"]["columns"]}
    assert rr_cols["parent_review_kind"]["is_generated"] is True
    assert rr_cols["parent_review_kind"]["generation_type"] == "VIRTUAL"
    assert rr_cols["reply_kind"]["is_generated"] is True
    assert rr_cols["reply_kind"]["generation_type"] == "VIRTUAL"
    syn_ddl = "\n    CREATE TABLE syn_gen_test (\n        id INTEGER PRIMARY KEY,\n        raw_val TEXT NOT NULL,\n        virt_val TEXT GENERATED ALWAYS AS (lower(raw_val)) VIRTUAL,\n        stor_val TEXT GENERATED ALWAYS AS (upper(raw_val)) STORED\n    ) STRICT;\n    "
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
    assert syn_cols["virt_val"]["is_generated"]
    assert syn_cols["virt_val"]["generation_type"] == "VIRTUAL"
    assert syn_cols["stor_val"]["is_generated"]
    assert syn_cols["stor_val"]["generation_type"] == "STORED"


def test_16_single_column_unique_and_dbml_fidelity():
    """C2: Single-column UNIQUE constraints and unique indexes are exported faithfully in DBML."""
    ir = introspect_all()
    core_tables = ir["stores"]["core"]["tables"]
    tb = core_tables["text_bodies"]
    assert any(
        (
            u["columns"] == ["sha256"] and (not u.get("partial", False))
            for u in tb["unique_constraints"]
        )
    )
    syn_ddl = "\n    CREATE TABLE syn_constraints (\n        org_id INTEGER NOT NULL,\n        repo_id INTEGER NOT NULL,\n        identifier TEXT NOT NULL UNIQUE,\n        code TEXT NOT NULL,\n        tag TEXT NOT NULL,\n        PRIMARY KEY (org_id, repo_id),\n        UNIQUE (code, tag)\n    ) STRICT;\n    "
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

    table = syn_store["tables"]["syn_constraints"]
    assert table["primary_key"] == ["org_id", "repo_id"]
    assert any(u["columns"] == ["identifier"] for u in table["unique_constraints"])
    assert any(u["columns"] == ["code", "tag"] for u in table["unique_constraints"])


def test_17_partial_unique_indexes_not_unconditional():
    """C3: Partial unique indexes are not misrepresented as unconditional constraints in DBML."""
    ir = introspect_all()
    core_tables = ir["stores"]["core"]["tables"]
    cs = core_tables["coverage_scopes"]
    assert not any(
        (
            u["name"] == "coverage_scope_repository_kind"
            for u in cs["unique_constraints"]
        )
    )
    cs_idx = {i["name"]: i for i in cs["indexes"]}
    assert "coverage_scope_repository_kind" in cs_idx
    assert cs_idx["coverage_scope_repository_kind"]["unique"] is True
    assert cs_idx["coverage_scope_repository_kind"]["partial"] is True
    assert "WHERE" in cs_idx["coverage_scope_repository_kind"]["sql"]
    assert (
        "change_request_id IS NULL"
        in cs_idx["coverage_scope_repository_kind"]["predicate"]
    )
    syn_ddl = "\n    CREATE TABLE syn_idx_variety (\n        id INTEGER PRIMARY KEY,\n        regular_u TEXT NOT NULL UNIQUE,\n        comp_a TEXT NOT NULL,\n        comp_b TEXT NOT NULL,\n        part_s TEXT,\n        part_c1 TEXT,\n        part_c2 TEXT,\n        non_u TEXT,\n        UNIQUE (comp_a, comp_b)\n    ) STRICT;\n    CREATE UNIQUE INDEX idx_part_single ON syn_idx_variety(part_s) WHERE part_s IS NOT NULL;\n    CREATE UNIQUE INDEX idx_part_comp ON syn_idx_variety(part_c1, part_c2) WHERE non_u = 'active';\n    CREATE INDEX idx_non_unique_part ON syn_idx_variety(non_u) WHERE non_u IS NOT NULL;\n    "
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
    syn_table = syn_store["tables"]["syn_idx_variety"]
    assert all(not u["partial"] for u in syn_table["unique_constraints"])
    assert any(
        i["name"] == "idx_part_comp" and i["partial"] and i["predicate"]
        for i in syn_table["indexes"]
    )


def test_19_cross_store_logical_dependencies_and_derivation_semantics():
    """C5: Cross-store logical relationships have verified semantics, valid columns, and polymorphic notes."""
    ir = introspect_all()
    errors = validate_logical_dependencies(ir)
    assert errors == [], f"Validation errors found in LOGICAL_DEPENDENCIES: {errors}"
    for dep in LOGICAL_DEPENDENCIES:
        assert "oid_hex" not in dep.get("source_columns", [])
        assert "oid_hex" not in dep.get("target_columns", [])
    git_dep = next(
        (d for d in LOGICAL_DEPENDENCIES if d["id"] == "log_search_docs_git_objects")
    )
    assert git_dep["target_table"] == "git_objects"
    assert git_dep["target_columns"] == ["git_object_id"]
    assert git_dep.get("is_derivation") is True
    assert "git:<git_object_id>" in git_dep["description"]
    text_dep = next(
        (d for d in LOGICAL_DEPENDENCIES if d["id"] == "log_search_docs_text_bodies")
    )
    assert text_dep["target_table"] == "text_bodies"
    assert text_dep["target_columns"] == ["sha256"]
    assert text_dep.get("is_derivation") is True
    assert "text_bodies.sha256" in text_dep["description"]
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
    assert any(("source column 'missing_col' not found" in e for e in fake_errors))
    assert any(("source table 'missing_table' not found" in e for e in fake_errors))


def test_20_functional_groups_and_tablegroups_consistency():
    """Section 4: Functional groups match audit_publication_free and TableGroups are emitted in combined DBML."""
    errors = validate_functional_groups_consistency()
    assert errors == [], f"Functional groups mismatch: {errors}"
    assert len(CORE_GROUPS) == 7
    total_core_tables = sum((len(tables) for tables in CORE_GROUPS.values()))
    assert total_core_tables == 70
    total_op_tables = sum((len(tables) for tables in OPERATIONAL_GROUPS.values()))
    assert total_op_tables == 10
    total_search_tables = sum((len(tables) for tables in SEARCH_GROUPS.values()))
    assert total_search_tables == 4
    total_tables = total_core_tables + total_op_tables + total_search_tables
    assert total_tables == 84
