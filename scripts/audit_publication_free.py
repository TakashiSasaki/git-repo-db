"""Inventory the composed fresh schemas and compare the preserved baseline.

This is a structural review aid, not a policy decision or a correctness certificate.
Run from the repository with `uv run python scripts/audit_publication_free.py`.
"""

import ast
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from repo_catalog.adapters.sqlite.cas_integrity import (  # noqa: E402
    register_git_object_sql_function,
)
from repo_catalog.adapters.sqlite.json_contracts import guard_sql  # noqa: E402
from repo_catalog.adapters.sqlite.schema import (  # noqa: E402
    DDL_SHA256,
    OPERATIONAL_DDL_SHA256,
    OPERATIONAL_SCHEMA_VERSION,
    SCHEMA_VERSION,
    SEARCH_DDL_SHA256,
    SEARCH_SCHEMA_VERSION,
    operational_schema_sql,
    schema_sql,
    search_schema_sql,
)

BASELINE = "0bd5704caca2f6e3723bef22531b065cd4d7bad0"

# Production tables partitioned strictly by actual store (PF-P06, PF-P11, PF-P14).
# Exchange conflict candidates (exchange_staging), Coverage blocking evidence
# (exchange_blocked_coverage_claims), and durable preservation obligations (preservation_obligations)
# remain strictly classified under Core semantics.
CORE_GROUPS = {
    "portable_identity_and_registration": "service_instances sources repositories repository_bindings repository_endpoints change_requests documents review_threads source_repositories repository_names identity_relations identity_relation_cancellations identity_relation_staging",
    "current_api_values": "issue_resources review_resources change_request_state document_state review_thread_state",
    "domain_enumeration_and_coverage": "fetch_collections collection_memberships current_collection_pages completion_markers coverage_scopes coverage_claims coverage_claim_markers code_listings code_listing_progress code_assessments code_acquisitions code_commits code_file_changes source_inventory_assessments thread_collection_requirements thread_collection_targets change_request_events resume_scopes thread_collection_continuations",
    "git_identity_intrinsic_and_capture": "git_acquisitions snapshots acquisition_roots root_origins git_objects commits commit_parents tree_objects tree_entries tag_objects repository_object_sources ref_observations root_manifests root_manifest_entries git_commit_facts git_text_facts git_name_facts git_object_payloads contents content_digests blob_content_map",
    "retained_content_integrity": "text_bodies stored_bytes payloads payload_quarantine payload_admission_staging unresolved_payloads preservation_obligations",
    "exchange_staging_and_admissions": "exchange_local_identities exchange_admissions exchange_staging exchange_blocked_coverage_claims",
    "local_physical_catalog": "database_identity",
}
CORE_GROUPS = {key: value.split() for key, value in CORE_GROUPS.items()}

OPERATIONAL_GROUPS = {
    "operational_store": "operational_identity jobs job_attempts cache_locators active_cache_entries cache_leases space_reservations acquisition_progress collection_progress search_rebuild_metrics",
}
OPERATIONAL_GROUPS = {key: value.split() for key, value in OPERATIONAL_GROUPS.items()}

SEARCH_GROUPS = {
    "search_store": "search_identity search_documents index_generations index_membership",
}
SEARCH_GROUPS = {key: value.split() for key, value in SEARCH_GROUPS.items()}

# Intentionally retired tables from monolithic Schema 20 (PF-P03, PF-P04, PF-P06, ADR 0002 §3.4)
RETIRED_TABLES = sorted(["content_locations", "incremental_scans", "resume_cursors"])


def git_text(path):
    return subprocess.check_output(
        ["git", "show", f"{BASELINE}:{path}"], cwd=ROOT, text=True
    )


def baseline_sql():
    tree = ast.parse(git_text("src/repo_catalog/adapters/sqlite/schema.py"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and all(
            isinstance(item, ast.Constant)
            and isinstance(item.value, str)
            and item.value.endswith(".sql")
            for item in node.elts
        ):
            names = [item.value for item in node.elts]
    if not names:
        raise ValueError("Cannot identify baseline composed DDL")
    return "\n".join(git_text("src/repo_catalog/resources/" + name) for name in names)


def inventory(sql, *, validate_views=False, register_udf=False):
    db = sqlite3.connect(":memory:")
    if register_udf:
        register_git_object_sql_function(db)
    db.executescript(sql)
    objects = db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_schema "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()
    tables = {}
    for kind, name, _, statement in objects:
        if kind != "table":
            continue
        # Distinguish product tables from SQLite internal and FTS shadow tables
        if name.startswith("sqlite_") or name.startswith("catalog_fts_"):
            continue
        columns = db.execute(f'PRAGMA table_xinfo("{name}")').fetchall()
        tables[name] = {
            "columns": [item[1] for item in columns],
            "generated_columns": [item[1] for item in columns if item[6] in (2, 3)],
            "primary_key": [
                item[1] for item in sorted(columns, key=lambda r: r[5]) if item[5]
            ],
            "foreign_keys": [
                list(row) for row in db.execute(f'PRAGMA foreign_key_list("{name}")')
            ],
            "sql_sha256": hashlib.sha256(statement.encode()).hexdigest(),
        }
    if validate_views:
        for kind, name, _, _ in objects:
            if kind == "view":
                db.execute(f'SELECT * FROM "{name}" LIMIT 0').fetchall()
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Fresh DDL FK failure")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Fresh DDL integrity failure")
    db.close()
    return {
        "ddl_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        "tables": tables,
        "views": {
            row[1]: hashlib.sha256(row[3].encode()).hexdigest()
            for row in objects
            if row[0] == "view"
        },
        "triggers": {
            row[1]: {
                "owner": row[2],
                "sql_sha256": hashlib.sha256(row[3].encode()).hexdigest(),
            }
            for row in objects
            if row[0] == "trigger"
        },
        "indexes": {
            row[1]: {
                "owner": row[2],
                "sql_sha256": hashlib.sha256(row[3].encode()).hexdigest(),
            }
            for row in objects
            if row[0] == "index"
        },
    }


def verify_cross_store_isolation(core_inv, op_inv, search_inv):
    stores = [
        ("core", core_inv),
        ("operational", op_inv),
        ("search", search_inv),
    ]
    all_table_names = {name: sname for sname, inv in stores for name in inv["tables"]}
    for sname, inv in stores:
        own_tables = set(inv["tables"].keys())
        for tname, tinfo in inv["tables"].items():
            for fk in tinfo["foreign_keys"]:
                target_table = fk[2]
                if target_table not in own_tables:
                    target_store = all_table_names.get(target_table, "unknown")
                    raise ValueError(
                        f"Prohibited cross-store FK: {sname}.{tname} references {target_store}.{target_table}"
                    )


def report():
    old = inventory(baseline_sql(), register_udf=True)
    current_core = inventory(schema_sql(), validate_views=True, register_udf=True)
    current_op = inventory(operational_schema_sql(), validate_views=True)
    current_search = inventory(search_schema_sql(), validate_views=True)

    # Verify DDL fingerprints match package declarations
    if bytes.fromhex(current_core["ddl_sha256"]) != DDL_SHA256:
        raise ValueError("Core DDL fingerprint mismatch")
    if bytes.fromhex(current_op["ddl_sha256"]) != OPERATIONAL_DDL_SHA256:
        raise ValueError("Operational DDL fingerprint mismatch")
    if bytes.fromhex(current_search["ddl_sha256"]) != SEARCH_DDL_SHA256:
        raise ValueError("Search DDL fingerprint mismatch")

    # Verify cross-store isolation (no foreign keys crossing store boundaries)
    verify_cross_store_isolation(current_core, current_op, current_search)

    # Verify each production table is classified exactly once within its actual store
    for store_name, inv, groups in [
        ("core", current_core, CORE_GROUPS),
        ("operational", current_op, OPERATIONAL_GROUPS),
        ("search", current_search, SEARCH_GROUPS),
    ]:
        assigned = [name for group in groups.values() for name in group]
        if len(set(assigned)) != len(assigned) or set(assigned) != set(inv["tables"]):
            raise ValueError(
                {
                    f"{store_name}_unclassified": sorted(
                        set(inv["tables"]) - set(assigned)
                    ),
                    f"{store_name}_stale": sorted(set(assigned) - set(inv["tables"])),
                }
            )

    # Verify retired tables are completely absent from all active stores
    all_current_tables = (
        set(current_core["tables"])
        | set(current_op["tables"])
        | set(current_search["tables"])
    )
    unretired_in_active = set(RETIRED_TABLES) & all_current_tables
    if unretired_in_active:
        raise ValueError(
            f"Retired tables still present in active stores: {sorted(unretired_in_active)}"
        )

    packaged = ROOT / "src/repo_catalog/resources/json_contracts.sql"
    if packaged.read_text() != guard_sql():
        raise ValueError("Generated JSON guards differ from packaged SQL")

    # Compute delta relative to preserved baseline
    combined_current = {
        "tables": {
            **current_core["tables"],
            **current_op["tables"],
            **current_search["tables"],
        },
        "views": {
            **current_core["views"],
            **current_op["views"],
            **current_search["views"],
        },
        "triggers": {
            **current_core["triggers"],
            **current_op["triggers"],
            **current_search["triggers"],
        },
        "indexes": {
            **current_core["indexes"],
            **current_op["indexes"],
            **current_search["indexes"],
        },
    }
    delta = {}
    for kind in ("tables", "views", "triggers", "indexes"):
        delta[kind] = {
            "removed": sorted(set(old[kind]) - set(combined_current[kind])),
            "added": sorted(set(combined_current[kind]) - set(old[kind])),
            "changed": sorted(
                name
                for name in set(old[kind]) & set(combined_current[kind])
                if old[kind][name] != combined_current[kind][name]
            ),
        }

    responsibility_groups = {
        **CORE_GROUPS,
        **OPERATIONAL_GROUPS,
        **SEARCH_GROUPS,
    }

    return {
        "purpose": "Exact composed-DDL structural map for Three-Store Boundary (Core Schema 21, Operational Schema 1, Search Schema 1); semantic responsibilities in ADR 0002; not independent review or acceptance",
        "schema_version": SCHEMA_VERSION,
        "operational_schema_version": OPERATIONAL_SCHEMA_VERSION,
        "search_schema_version": SEARCH_SCHEMA_VERSION,
        "baseline_commit": BASELINE,
        "baseline_tree": subprocess.check_output(
            ["git", "rev-parse", BASELINE + "^{tree}"], cwd=ROOT, text=True
        ).strip(),
        "baseline_ddl_sha256": old["ddl_sha256"],
        "current": current_core,
        "operational": current_op,
        "search": current_search,
        "retired_tables": RETIRED_TABLES,
        "store_disposition": {
            "core": sorted(current_core["tables"]),
            "operational": sorted(current_op["tables"]),
            "search": sorted(current_search["tables"]),
            "retired": RETIRED_TABLES,
        },
        "changed_table_contracts": {
            name: {
                "removed_columns": sorted(
                    set(old["tables"][name]["columns"])
                    - set(combined_current["tables"][name]["columns"])
                ),
                "added_columns": sorted(
                    set(combined_current["tables"][name]["columns"])
                    - set(old["tables"][name]["columns"])
                ),
                "old_primary_key": old["tables"][name]["primary_key"],
                "new_primary_key": combined_current["tables"][name]["primary_key"],
                "old_foreign_keys": old["tables"][name]["foreign_keys"],
                "new_foreign_keys": combined_current["tables"][name]["foreign_keys"],
            }
            for name in delta["tables"]["changed"]
        },
        "responsibility_groups": responsibility_groups,
        "delta": delta,
        "fresh_empty_ddl_checks": [
            "all views compile",
            "foreign_key_check empty on core, operational, and search stores",
            "integrity_check ok on core, operational, and search stores",
            "no cross-store foreign key dependencies",
            "generated JSON SQL equal",
            "registered git_object sql functions verified",
            "fts shadow tables distinguished from product tables",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, ensure_ascii=False))
