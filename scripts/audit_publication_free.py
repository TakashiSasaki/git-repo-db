"""Inventory the composed fresh schema and compare the preserved schema19 baseline.

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
from repo_catalog.adapters.sqlite.schema import SCHEMA_VERSION, schema_sql  # noqa: E402

BASELINE = "0bd5704caca2f6e3723bef22531b065cd4d7bad0"
GROUPS = {
    "portable_identity_and_registration": "service_instances sources repositories repository_bindings repository_endpoints change_requests documents review_threads source_repositories repository_names identity_relations identity_relation_cancellations identity_relation_staging",
    "current_api_values": "issue_resources review_resources change_request_state document_state review_thread_state",
    "domain_enumeration_and_coverage": "fetch_collections collection_memberships current_collection_pages completion_markers coverage_scopes coverage_claims coverage_claim_markers code_listings code_listing_progress code_assessments code_acquisitions code_commits code_file_changes source_inventory_assessments thread_collection_requirements thread_collection_targets change_request_events",
    "git_identity_intrinsic_and_capture": "git_acquisitions snapshots acquisition_roots root_origins git_objects commits commit_parents tree_objects tree_entries tag_objects repository_object_sources ref_observations root_manifests root_manifest_entries git_commit_facts git_text_facts git_name_facts git_object_payloads contents content_digests blob_content_map",
    "retained_content_integrity": "text_bodies stored_bytes payloads payload_quarantine payload_admission_staging unresolved_payloads preservation_obligations",
    "discardable_operations_and_derived_index": "jobs job_attempts acquisition_progress collection_progress resume_scopes incremental_scans resume_cursors thread_collection_continuations cache_locators content_locations active_cache_entries cache_leases space_reservations search_documents index_generations index_membership exchange_local_identities exchange_admissions exchange_staging exchange_blocked_coverage_claims",
    "local_physical_catalog": "database_identity",
}
GROUPS = {key: value.split() for key, value in GROUPS.items()}


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


def inventory(sql, *, validate_views=False):
    db = sqlite3.connect(":memory:")
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
        columns = db.execute(f'PRAGMA table_info("{name}")').fetchall()
        tables[name] = {
            "columns": [item[1] for item in columns],
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


def report():
    old, current = (
        inventory(baseline_sql()),
        inventory(schema_sql(), validate_views=True),
    )
    assigned = [name for group in GROUPS.values() for name in group]
    if len(set(assigned)) != len(assigned) or set(assigned) != set(current["tables"]):
        raise ValueError(
            {
                "unclassified": sorted(set(current["tables"]) - set(assigned)),
                "stale": sorted(set(assigned) - set(current["tables"])),
            }
        )
    packaged = ROOT / "src/repo_catalog/resources/json_contracts.sql"
    if packaged.read_text() != guard_sql():
        raise ValueError("Generated JSON guards differ from packaged SQL")
    delta = {}
    for kind in ("tables", "views", "triggers", "indexes"):
        delta[kind] = {
            "removed": sorted(set(old[kind]) - set(current[kind])),
            "added": sorted(set(current[kind]) - set(old[kind])),
            "changed": sorted(
                name
                for name in set(old[kind]) & set(current[kind])
                if old[kind][name] != current[kind][name]
            ),
        }
    return {
        "purpose": "Exact composed-DDL structural map; semantic responsibilities in publication-free-implementation.md; not independent review or acceptance",
        "schema_version": SCHEMA_VERSION,
        "baseline_commit": BASELINE,
        "baseline_tree": subprocess.check_output(
            ["git", "rev-parse", BASELINE + "^{tree}"], cwd=ROOT, text=True
        ).strip(),
        "baseline_ddl_sha256": old["ddl_sha256"],
        "current": current,
        "changed_table_contracts": {
            name: {
                "removed_columns": sorted(
                    set(old["tables"][name]["columns"])
                    - set(current["tables"][name]["columns"])
                ),
                "added_columns": sorted(
                    set(current["tables"][name]["columns"])
                    - set(old["tables"][name]["columns"])
                ),
                "old_primary_key": old["tables"][name]["primary_key"],
                "new_primary_key": current["tables"][name]["primary_key"],
                "old_foreign_keys": old["tables"][name]["foreign_keys"],
                "new_foreign_keys": current["tables"][name]["foreign_keys"],
            }
            for name in delta["tables"]["changed"]
        },
        "responsibility_groups": GROUPS,
        "delta": delta,
        "fresh_empty_ddl_checks": [
            "all views compile",
            "foreign_key_check empty",
            "integrity_check ok",
            "generated JSON SQL equal",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, ensure_ascii=False))
