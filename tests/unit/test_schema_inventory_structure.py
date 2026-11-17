"""Complete neutral IR for current separated schemas and SQL counterexamples."""

import hashlib

import pytest

from scripts.schema_inventory import (
    introspect_all,
    introspect_store,
    validate_inventory,
    validate_logical_dependencies,
)


@pytest.fixture(scope="module")
def ir():
    return introspect_all()


def test_1_introspection_success(ir):
    assert validate_inventory(ir) == []
    assert set(ir["stores"]) == {
        "p1.core",
        "p1.context",
        "access",
        "p1.operational",
        "p1.search",
        "filesystem",
        "worktrees",
    }
    assert all(len(s["authority_domains"]) == 1 for s in ir["stores"].values())
    assert not ir["scope"]["configurations_are_required_startup_sets"]


def test_2_table_inventories_match(ir):
    # Includes four identity-evidence tables in their owning domain, with no
    # former mixed Catalog3 schema hidden alongside the separated factories.
    assert {k: v["table_count"] for k, v in ir["stores"].items()} == {
        "p1.core": 25,
        "p1.context": 21,
        "access": 10,
        "p1.operational": 8,
        "p1.search": 3,
        "filesystem": 4,
        "worktrees": 5,
    }
    assert ir["summary"]["table_definitions"] == 76
    for store in ir["stores"].values():
        assert {t["group"] for t in store["tables"].values()} == set(
            store["authority_domains"]
        )


def test_3_product_tables_distinguished(ir):
    for store in ir["stores"].values():
        assert all(
            not name.startswith(("sqlite_", "catalog_fts_")) for name in store["tables"]
        )
        assert store["table_count"] == len(store["tables"])


def test_4_no_physical_fk_omitted_or_duplicated(ir):
    assert {k: v["foreign_key_count"] for k, v in ir["stores"].items()} == {
        "p1.core": 34,
        "p1.context": 31,
        "access": 12,
        "p1.operational": 6,
        "p1.search": 1,
        "filesystem": 2,
        "worktrees": 2,
    }
    for store in ir["stores"].values():
        for table in store["tables"].values():
            ids = [fk["id"] for fk in table["foreign_keys"]]
            assert len(ids) == len(set(ids))


def test_5_composite_foreign_keys_grouped(ir):
    fks = ir["stores"]["p1.core"]["tables"]["core_coverage_proofs"]["foreign_keys"]
    claim = next(fk for fk in fks if fk["target_table"] == "coverage_claims")
    assert claim["is_composite"]
    assert (
        claim["from_columns"]
        == claim["to_columns"]
        == [
            "owner_kind",
            "owner_coordinates_json",
            "observed_at_us",
            "coverage_state",
        ]
    )
    fks = ir["stores"]["filesystem"]["tables"]["entries"]["foreign_keys"]
    assert (
        fks[0]["from_columns"]
        == fks[0]["to_columns"]
        == ["namespace_uuid", "scan_uuid"]
    )


def test_6_physical_fk_endpoints_exist_in_own_store(ir):
    for store in ir["stores"].values():
        for table in store["tables"].values():
            assert all(
                fk["target_table"] in store["tables"] for fk in table["foreign_keys"]
            )


def test_7_no_cross_store_logical_declared_as_physical_fk(ir):
    scan = next(
        r for r in ir["optional_references"] if r["id"] == "worktrees.filesystem-scan"
    )
    assert not scan["physical_foreign_key"] and scan["missing_target"] == "unresolved"
    physical = ir["stores"]["worktrees"]["tables"]["scan_references"]["foreign_keys"]
    assert all(fk["target_table"] != "scans" for fk in physical)
    assert scan["source_columns"] == [
        "filesystem_namespace_uuid",
        "filesystem_scan_uuid",
    ]
    assert scan["target_columns"] == ["namespace_uuid", "scan_uuid"]


def test_11_no_persistent_sqlite_files_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    introspect_all()
    assert list(tmp_path.iterdir()) == []


def _fixture(ddl):
    return introspect_store(
        "fixture",
        "Fixture",
        "unused.db",
        "test",
        1,
        hashlib.sha256(ddl.encode()).digest(),
        ddl,
        {},
    )


def test_15_generated_column_classifications():
    ddl = """
    CREATE TABLE sample (id INTEGER PRIMARY KEY, raw_val TEXT NOT NULL,
      virt_val TEXT GENERATED ALWAYS AS (lower(raw_val)) VIRTUAL,
      stor_val TEXT GENERATED ALWAYS AS (upper(raw_val)) STORED) STRICT;
    """
    columns = {c["name"]: c for c in _fixture(ddl)["tables"]["sample"]["columns"]}
    assert (
        columns["virt_val"]["is_generated"]
        and columns["virt_val"]["generation_type"] == "VIRTUAL"
    )
    assert (
        columns["stor_val"]["is_generated"]
        and columns["stor_val"]["generation_type"] == "STORED"
    )
    assert not columns["raw_val"]["is_generated"]


def test_16_single_column_unique_and_dbml_fidelity():
    ddl = """
    CREATE TABLE sample (org_id INTEGER NOT NULL, repo_id INTEGER NOT NULL,
      identifier TEXT NOT NULL UNIQUE, code TEXT NOT NULL, tag TEXT NOT NULL,
      PRIMARY KEY(org_id,repo_id), UNIQUE(code,tag)) STRICT;
    """
    table = _fixture(ddl)["tables"]["sample"]
    assert table["primary_key"] == ["org_id", "repo_id"]
    assert any(u["columns"] == ["identifier"] for u in table["unique_constraints"])
    assert any(u["columns"] == ["code", "tag"] for u in table["unique_constraints"])
    assert all(not u["partial"] for u in table["unique_constraints"])


def test_17_partial_unique_indexes_not_unconditional():
    ddl = """
    CREATE TABLE sample (id INTEGER PRIMARY KEY, code TEXT UNIQUE, a TEXT, b TEXT, state TEXT) STRICT;
    CREATE UNIQUE INDEX partial_single ON sample(a) WHERE a IS NOT NULL;
    CREATE UNIQUE INDEX partial_composite ON sample(a,b) WHERE state = 'active';
    CREATE INDEX partial_nonunique ON sample(b) WHERE b IS NOT NULL;
    """
    table = _fixture(ddl)["tables"]["sample"]
    assert [u["columns"] for u in table["unique_constraints"]] == [["code"]]
    indices = {i["name"]: i for i in table["indexes"]}
    assert indices["partial_single"]["unique"] and indices["partial_single"]["partial"]
    assert indices["partial_composite"]["predicate"] == "state = 'active'"
    assert (
        not indices["partial_nonunique"]["unique"]
        and indices["partial_nonunique"]["partial"]
    )


def test_19_cross_store_logical_dependencies_and_derivation_semantics():
    fake_ir = {
        "stores": {
            "a": {"tables": {"one": {"columns": [{"name": "key"}]}}},
            "b": {"tables": {"two": {"columns": [{"name": "key"}]}}},
        },
        "logical_dependencies": [
            {
                "id": "bad_column",
                "source_store": "a",
                "source_table": "one",
                "source_columns": ["absent"],
                "target_store": "b",
                "target_table": "two",
                "target_columns": ["key"],
            },
            {
                "id": "bad_table",
                "source_store": "a",
                "source_table": "absent",
                "source_columns": ["key"],
                "target_store": "b",
                "target_table": "two",
                "target_columns": ["key"],
            },
        ],
    }
    errors = validate_logical_dependencies(fake_ir)
    assert any("source column 'absent' not found" in e for e in errors)
    assert any("source table 'absent' not found" in e for e in errors)


def test_20_functional_groups_and_tablegroups_consistency(ir):
    for store in ir["stores"].values():
        assert store["authority_domains"][0] in ir["authority_domains"]
    with pytest.raises(ValueError, match="Unknown inventory profile"):
        introspect_all("normal")
