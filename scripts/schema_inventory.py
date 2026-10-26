"""Mechanical implemented-store schema inventory, independent of renderers.

Retains the existing normalized IR, including compatibility annotations.
No documentation package is imported and no persistent database is opened.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Ensure src/ is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repo_catalog.adapters.sqlite.cas_integrity import (  # noqa: E402
    register_git_object_sql_function,
)
from repo_catalog.adapters.sqlite.schema import (  # noqa: E402
    DDL_SHA256,
    FORMAT_ID,
    OPERATIONAL_DDL_SHA256,
    OPERATIONAL_FORMAT_ID,
    OPERATIONAL_SCHEMA_VERSION,
    SCHEMA_VERSION,
    SEARCH_DDL_SHA256,
    SEARCH_FORMAT_ID,
    SEARCH_SCHEMA_VERSION,
    operational_schema_sql,
    schema_sql,
    search_schema_sql,
)

# Authoritative functional groups matching ADR 0002 and audit_publication_free.py
CORE_GROUPS: dict[str, list[str]] = {
    "portable_identity_and_registration": [
        "service_instances",
        "sources",
        "repositories",
        "repository_bindings",
        "repository_endpoints",
        "change_requests",
        "documents",
        "review_threads",
        "source_repositories",
        "repository_names",
        "identity_relations",
        "identity_relation_cancellations",
        "identity_relation_staging",
    ],
    "current_api_values": [
        "issue_resources",
        "review_resources",
        "change_request_state",
        "document_state",
        "review_thread_state",
    ],
    "domain_enumeration_and_coverage": [
        "fetch_collections",
        "collection_memberships",
        "current_collection_pages",
        "completion_markers",
        "coverage_scopes",
        "coverage_claims",
        "coverage_claim_markers",
        "code_listings",
        "code_listing_progress",
        "code_assessments",
        "code_acquisitions",
        "code_commits",
        "code_file_changes",
        "source_inventory_assessments",
        "thread_collection_requirements",
        "thread_collection_targets",
        "change_request_events",
        "resume_scopes",
        "thread_collection_continuations",
    ],
    "git_identity_intrinsic_and_capture": [
        "git_acquisitions",
        "snapshots",
        "acquisition_roots",
        "root_origins",
        "git_objects",
        "commits",
        "commit_parents",
        "tree_objects",
        "tree_entries",
        "tag_objects",
        "repository_object_sources",
        "ref_observations",
        "root_manifests",
        "root_manifest_entries",
        "git_commit_facts",
        "git_text_facts",
        "git_name_facts",
        "git_object_payloads",
        "contents",
        "content_digests",
        "blob_content_map",
    ],
    "retained_content_integrity": [
        "text_bodies",
        "stored_bytes",
        "payloads",
        "payload_quarantine",
        "payload_admission_staging",
        "unresolved_payloads",
        "preservation_obligations",
    ],
    "exchange_staging_and_admissions": [
        "exchange_local_identities",
        "exchange_admissions",
        "exchange_staging",
        "exchange_blocked_coverage_claims",
    ],
    "local_physical_catalog": [
        "database_identity",
    ],
}

OPERATIONAL_GROUPS: dict[str, list[str]] = {
    "operational_store": [
        "operational_identity",
        "jobs",
        "job_attempts",
        "cache_locators",
        "active_cache_entries",
        "cache_leases",
        "space_reservations",
        "acquisition_progress",
        "collection_progress",
        "search_rebuild_metrics",
    ]
}

SEARCH_GROUPS: dict[str, list[str]] = {
    "search_store": [
        "search_identity",
        "search_documents",
        "index_generations",
        "index_membership",
    ]
}

# Group metadata labels for human presentation and Mermaid modules
GROUP_METADATA: dict[str, dict[str, str]] = {
    "portable_identity_and_registration": {
        "title": "Portable Identity & Registration",
        "slug": "core-identity",
        "description": "Portable UUIDv4 identities, service instances, sources, repositories, bindings, change requests, and identity relations.",
    },
    "current_api_values": {
        "title": "Current API Values & Projections",
        "slug": "core-current-state",
        "description": "Latest state projections for PRs, issues, documents, and review threads with JSON-contract provenance.",
    },
    "domain_enumeration_and_coverage": {
        "title": "Domain Enumeration & Coverage Evidence",
        "slug": "core-coverage",
        "description": "Collections, memberships, completion markers, typed coverage scopes/claims, and code listing assessments.",
    },
    "git_identity_intrinsic_and_capture": {
        "title": "Git Identity, Intrinsic DAG & Capture",
        "slug": "core-git",
        "description": "Immutable Git acquisitions, snapshots, objects, commits, trees, tags, ref observations, and byte facts.",
    },
    "retained_content_integrity": {
        "title": "Retained Content Integrity & CAS",
        "slug": "core-cas",
        "description": "Shared CAS payload storage, quarantine, unreferenced bodies, and durable preservation obligations.",
    },
    "exchange_staging_and_admissions": {
        "title": "Exchange Staging & Admissions",
        "slug": "core-exchange",
        "description": "Staging area for catalog synchronization, admission receipts, and conflicting candidate resolution.",
    },
    "local_physical_catalog": {
        "title": "Local Physical Catalog Identity",
        "slug": "core-identity",
        "description": "Local SQLite database instance singleton and receiver-local revision counter.",
    },
    "operational_store": {
        "title": "Operational Execution Store",
        "slug": "operational",
        "description": "Disposable jobs, attempts, packfile cache leases, reservations, and progress tracking (ADR 0002).",
    },
    "search_store": {
        "title": "Search Projections & FTS5 Derivatives",
        "slug": "search",
        "description": "Rebuildable document projections, index generations, and trigram FTS5 virtual tables (ADR 0002).",
    },
}

# Verified cross-store logical dependencies under ADR 0002
LOGICAL_DEPENDENCIES: list[dict[str, Any]] = [
    {
        "id": "log_op_identity_catalog",
        "source_store": "operational",
        "source_table": "operational_identity",
        "source_columns": ["catalog_db_instance_id"],
        "target_store": "core",
        "target_table": "database_identity",
        "target_columns": ["db_instance_id"],
        "cardinality": "1 to 1",
        "adr_reference": "ADR 0002 §2 PF-P11, §3.2",
        "description": "Strict 1:1 ownership binding between Operational database and Core Catalog instance. Operational DB is disposable without affecting Core domain facts.",
    },
    {
        "id": "log_op_acq_progress_git_acq",
        "source_store": "operational",
        "source_table": "acquisition_progress",
        "source_columns": ["git_acquisition_id"],
        "target_store": "core",
        "target_table": "git_acquisitions",
        "target_columns": ["git_acquisition_id"],
        "cardinality": "0..N to 1",
        "adr_reference": "ADR 0002 §3.2, PF-P04",
        "description": "Operational Git acquisition worker progress tracking associated Core Git acquisition entity. Interrupted/uncommitted progress is safely discarded.",
    },
    {
        "id": "log_op_col_progress_fetch_col",
        "source_store": "operational",
        "source_table": "collection_progress",
        "source_columns": ["fetch_collection_id"],
        "target_store": "core",
        "target_table": "fetch_collections",
        "target_columns": ["fetch_collection_id"],
        "cardinality": "0..N to 1",
        "adr_reference": "ADR 0002 §3.2, PF-P03, PF-P04",
        "description": "Operational API collection worker progress tracking associated Core fetch collection. Missing progress triggers fallback to fresh full acquisition.",
    },
    {
        "id": "log_op_cache_locators_repo",
        "source_store": "operational",
        "source_table": "cache_locators",
        "source_columns": ["repository_uuidv4"],
        "target_store": "core",
        "target_table": "repositories",
        "target_columns": ["repository_uuidv4"],
        "cardinality": "0..N to 1",
        "adr_reference": "ADR 0002 §3.2, three-store-invariants §1",
        "description": "Transient physical Git packfile cache locator mapped to Core repository UUID. Incomplete Core preservation obligations block cache GC even if locator disappears.",
    },
    {
        "id": "log_search_identity_catalog",
        "source_store": "search",
        "source_table": "search_identity",
        "source_columns": ["catalog_db_instance_id"],
        "target_store": "core",
        "target_table": "database_identity",
        "target_columns": ["db_instance_id"],
        "cardinality": "1 to 1",
        "adr_reference": "ADR 0002 §2 PF-P14, §3.3",
        "description": "Strict 1:1 ownership binding between Search database and Core Catalog instance. Search DB is excluded from backup and rebuildable at any time.",
    },
    {
        "id": "log_search_identity_fence",
        "source_store": "search",
        "source_table": "search_identity",
        "source_columns": ["core_revision_fence"],
        "target_store": "core",
        "target_table": "database_identity",
        "target_columns": ["local_revision"],
        "cardinality": "0..1 to 1",
        "adr_reference": "ADR 0002 §3.3, §4, PF-P15",
        "description": "Search database freshness fence tracking Core local_revision counter. Stale fence triggers direct-scan fallback or rebuild notification.",
    },
    {
        "id": "log_search_gen_fence",
        "source_store": "search",
        "source_table": "index_generations",
        "source_columns": ["core_revision_fence"],
        "target_store": "core",
        "target_table": "database_identity",
        "target_columns": ["local_revision"],
        "cardinality": "0..1 to 1",
        "adr_reference": "ADR 0002 §3.3, §4, three-store-invariants §4",
        "description": "Per-generation index snapshot fence recording Core local_revision at projection time for snapshot pinning.",
    },
    {
        "id": "log_search_docs_git_objects",
        "source_store": "search",
        "source_table": "search_documents",
        "source_columns": ["source_key"],
        "target_store": "core",
        "target_table": "git_objects",
        "target_columns": ["git_object_id"],
        "cardinality": "0..N to 1",
        "adr_reference": "ADR 0002 §3.3, §4",
        "description": "Code and commit search projections (kind IN ('code', 'commits')). The source_key is encoded as 'git:<git_object_id>' derived from Core git_objects.git_object_id via valid git facts. Disposable derivative; application-level polymorphic mapping, not an enforced foreign key.",
        "is_derivation": True,
    },
    {
        "id": "log_search_docs_text_bodies",
        "source_store": "search",
        "source_table": "search_documents",
        "source_columns": ["source_key"],
        "target_store": "core",
        "target_table": "text_bodies",
        "target_columns": ["sha256"],
        "cardinality": "0..N to 1",
        "adr_reference": "ADR 0002 §3.3, §4",
        "description": "PR and Issue search projections (kind IN ('pr', 'issue')). The source_key is derived from lower hex-encoded text_bodies.sha256 for domain text bodies, or SHA-256 hex digest of standalone issue titles. Disposable derivative; application-level polymorphic mapping, not an enforced foreign key.",
        "is_derivation": True,
    },
]


def introspect_store(
    store_slug: str,
    store_title: str,
    db_filename: str,
    format_id: str,
    schema_version: int,
    expected_sha256: bytes,
    ddl: str,
    group_map: dict[str, list[str]],
    *,
    register_udf: bool = False,
) -> dict[str, Any]:
    """Introspect a single SQLite schema entirely in memory."""
    db = sqlite3.connect(":memory:")
    if register_udf:
        register_git_object_sql_function(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(ddl)

    ddl_sha256 = hashlib.sha256(ddl.encode()).digest()
    if ddl_sha256 != expected_sha256:
        raise ValueError(
            f"DDL hash mismatch for {store_slug}: computed {ddl_sha256.hex()}, declared {expected_sha256.hex()}"
        )

    # Invert group map: table_name -> group_slug
    table_to_group: dict[str, str] = {}
    for group_slug, tables in group_map.items():
        for table in tables:
            table_to_group[table] = group_slug

    raw_objects = db.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema "
        "WHERE name NOT LIKE 'sqlite_%' AND name NOT LIKE 'catalog_fts_%' "
        "ORDER BY type, name"
    ).fetchall()

    tables: dict[str, Any] = {}
    views: dict[str, Any] = {}
    triggers: dict[str, Any] = {}
    explicit_indexes: dict[str, Any] = {}

    for obj_type, name, tbl_name, sql in raw_objects:
        if obj_type == "view":
            view_cols = [
                c[1] for c in db.execute(f'PRAGMA table_xinfo("{name}")').fetchall()
            ]
            views[name] = {
                "name": name,
                "sql": sql,
                "columns": view_cols,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            }
        elif obj_type == "trigger":
            triggers[name] = {
                "name": name,
                "table_name": tbl_name,
                "sql": sql,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            }
        elif obj_type == "index":
            explicit_indexes[name] = {
                "name": name,
                "table_name": tbl_name,
                "sql": sql,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest() if sql else None,
            }

    # Introspect each table
    table_names = [
        row[1]
        for row in raw_objects
        if row[0] == "table"
        and not row[1].startswith("sqlite_")
        and not row[1].startswith("catalog_fts_")
    ]

    for t_name in sorted(table_names):
        t_sql = next((r[3] for r in raw_objects if r[1] == t_name), "")
        raw_cols = db.execute(f'PRAGMA table_xinfo("{t_name}")').fetchall()
        # raw_cols: cid, name, type, notnull, dflt_value, pk, hidden
        columns: list[dict[str, Any]] = []
        pk_cols: list[str] = []

        # Sort columns to find PK order
        pk_candidates = [
            (c[1], c[5]) for c in raw_cols if c[5] > 0
        ]  # c[5] is 1-based rank
        pk_cols = [c[0] for c in sorted(pk_candidates, key=lambda x: x[1])]

        for cid, col_name, col_type, notnull, dflt, pk_pos, hidden in raw_cols:
            is_generated = hidden in (2, 3)
            # In SQLite 3.31+ PRAGMA table_xinfo: hidden==2 is VIRTUAL, hidden==3 is STORED
            gen_type = "VIRTUAL" if hidden == 2 else "STORED" if hidden == 3 else None
            columns.append(
                {
                    "cid": cid,
                    "name": col_name,
                    "type": col_type,
                    "notnull": bool(notnull),
                    "default_value": dflt,
                    "is_pk": pk_pos > 0,
                    "pk_position": pk_pos,
                    "is_generated": is_generated,
                    "generation_type": gen_type,
                    "is_hidden": hidden == 1,
                }
            )

        # Foreign keys: PRAGMA foreign_key_list(t_name)
        # rows: id, seq, table, from, to, on_update, on_delete, match
        fk_rows = db.execute(f'PRAGMA foreign_key_list("{t_name}")').fetchall()
        fk_groups: dict[int, list[Any]] = {}
        for row in fk_rows:
            fk_groups.setdefault(row[0], []).append(row)

        foreign_keys: list[dict[str, Any]] = []
        for fk_id in sorted(fk_groups.keys()):
            rows = sorted(fk_groups[fk_id], key=lambda r: r[1])  # sort by seq
            target_table = rows[0][2]
            from_cols = [r[3] for r in rows]
            to_cols = [r[4] for r in rows]
            on_update = rows[0][5]
            on_delete = rows[0][6]
            foreign_keys.append(
                {
                    "id": fk_id,
                    "target_table": target_table,
                    "from_columns": from_cols,
                    "to_columns": to_cols,
                    "is_composite": len(from_cols) > 1,
                    "on_update": on_update,
                    "on_delete": on_delete,
                    "match": rows[0][7],
                }
            )

        # Unique constraints and indexes
        idx_list = db.execute(f'PRAGMA index_list("{t_name}")').fetchall()
        # idx_list: seq, name, unique, origin, partial
        unique_constraints: list[dict[str, Any]] = []
        table_indexes: list[dict[str, Any]] = []

        for _, idx_name, is_unique, origin, is_partial in idx_list:
            xinfo = db.execute(f'PRAGMA index_xinfo("{idx_name}")').fetchall()
            # xinfo: seqno, cid, name, desc, coll, key
            idx_cols = [row[2] for row in xinfo if row[1] >= 0 and row[5] == 1]

            idx_sql_row = db.execute(
                "SELECT sql FROM sqlite_schema WHERE type='index' AND name=?",
                (idx_name,),
            ).fetchone()
            idx_sql = idx_sql_row[0] if idx_sql_row else None
            where_clause = None
            if is_partial and idx_sql:
                m = re.search(r"\bWHERE\s+(.+)$", idx_sql, re.IGNORECASE)
                if m:
                    where_clause = m.group(1).strip()

            # origin 'pk' is the primary key autoindex, handled by primary_key metadata.
            # Only unconditional unique constraints are added to unique_constraints (C3).
            if is_unique and origin != "pk" and not is_partial:
                unique_constraints.append(
                    {
                        "name": idx_name,
                        "columns": idx_cols,
                        "is_composite": len(idx_cols) > 1,
                        "origin": origin,
                        "partial": False,
                        "predicate": None,
                    }
                )

            # Explicit indexes (origin 'c')
            if origin == "c":
                table_indexes.append(
                    {
                        "name": idx_name,
                        "columns": idx_cols,
                        "unique": bool(is_unique),
                        "partial": bool(is_partial),
                        "predicate": where_clause,
                        "sql": idx_sql,
                    }
                )

        # Table triggers
        table_triggers = [
            trig_name
            for trig_name, trig_data in triggers.items()
            if trig_data["table_name"] == t_name
        ]

        group = table_to_group.get(t_name, "unclassified")
        tables[t_name] = {
            "name": t_name,
            "store": store_slug,
            "group": group,
            "group_title": GROUP_METADATA.get(group, {}).get(
                "title", group.replace("_", " ").title()
            ),
            "is_strict": "STRICT" in t_sql.upper(),
            "columns": columns,
            "primary_key": pk_cols,
            "is_composite_pk": len(pk_cols) > 1,
            "foreign_keys": foreign_keys,
            "unique_constraints": unique_constraints,
            "indexes": table_indexes,
            "triggers": table_triggers,
            "sql": t_sql,
            "sql_sha256": hashlib.sha256(t_sql.encode()).hexdigest(),
        }

    # Compute incoming foreign keys for each table
    for t_name, t_meta in tables.items():
        t_meta["incoming_foreign_keys"] = []

    for src_name, src_meta in tables.items():
        for fk in src_meta["foreign_keys"]:
            tgt_name = fk["target_table"]
            if tgt_name in tables:
                tables[tgt_name]["incoming_foreign_keys"].append(
                    {
                        "source_table": src_name,
                        "source_columns": fk["from_columns"],
                        "target_columns": fk["to_columns"],
                        "is_composite": fk["is_composite"],
                        "on_update": fk["on_update"],
                        "on_delete": fk["on_delete"],
                        "constraint_id": fk["id"],
                    }
                )

    db.close()

    total_fks = sum(len(t["foreign_keys"]) for t in tables.values())
    return {
        "slug": store_slug,
        "title": store_title,
        "db_filename": db_filename,
        "format_id": format_id,
        "schema_version": schema_version,
        "ddl_sha256": ddl_sha256.hex(),
        "table_count": len(tables),
        "view_count": len(views),
        "trigger_count": len(triggers),
        "index_count": len(explicit_indexes),
        "foreign_key_count": total_fks,
        "tables": tables,
        "views": views,
        "triggers": triggers,
        "explicit_indexes": explicit_indexes,
    }


def introspect_all() -> dict[str, Any]:
    """Introspect all three stores and assemble normalized schema intermediate representation."""
    core = introspect_store(
        "core",
        "Core Store",
        "catalog.sqlite3",
        FORMAT_ID,
        SCHEMA_VERSION,
        DDL_SHA256,
        schema_sql(),
        CORE_GROUPS,
        register_udf=True,
    )
    operational = introspect_store(
        "operational",
        "Operational Store",
        "operational.sqlite3",
        OPERATIONAL_FORMAT_ID,
        OPERATIONAL_SCHEMA_VERSION,
        OPERATIONAL_DDL_SHA256,
        operational_schema_sql(),
        OPERATIONAL_GROUPS,
    )
    search = introspect_store(
        "search",
        "Search Store",
        "search.sqlite3",
        SEARCH_FORMAT_ID,
        SEARCH_SCHEMA_VERSION,
        SEARCH_DDL_SHA256,
        search_schema_sql(),
        SEARCH_GROUPS,
    )

    # Attach logical cross-store relationships to tables
    for rel in LOGICAL_DEPENDENCIES:
        src_store = rel["source_store"]
        src_table = rel["source_table"]
        store_obj = (
            core
            if src_store == "core"
            else operational
            if src_store == "operational"
            else search
        )
        if src_table in store_obj["tables"]:
            store_obj["tables"][src_table].setdefault("logical_outgoing", []).append(
                rel
            )

        tgt_store = rel["target_store"]
        tgt_table = rel["target_table"]
        tgt_obj = (
            core
            if tgt_store == "core"
            else operational
            if tgt_store == "operational"
            else search
        )
        if tgt_table in tgt_obj["tables"]:
            tgt_obj["tables"][tgt_table].setdefault("logical_incoming", []).append(rel)

    return {
        "stores": {
            "core": core,
            "operational": operational,
            "search": search,
        },
        "logical_dependencies": LOGICAL_DEPENDENCIES,
        "groups": {
            **CORE_GROUPS,
            **OPERATIONAL_GROUPS,
            **SEARCH_GROUPS,
        },
        "group_metadata": GROUP_METADATA,
        "summary": {
            "core_tables": core["table_count"],
            "core_views": core["view_count"],
            "core_triggers": core["trigger_count"],
            "core_fks": core["foreign_key_count"],
            "operational_tables": operational["table_count"],
            "operational_triggers": operational["trigger_count"],
            "operational_fks": operational["foreign_key_count"],
            "search_tables": search["table_count"],
            "search_triggers": search["trigger_count"],
            "search_fks": search["foreign_key_count"],
            "total_product_tables": core["table_count"]
            + operational["table_count"]
            + search["table_count"],
        },
    }


def validate_logical_dependencies(ir: dict[str, Any]) -> list[str]:
    """Validate cross-store logical dependencies against introspected schemas."""
    errors = []
    stores = ir["stores"]
    for dep in ir.get("logical_dependencies", []):
        dep_id = dep["id"]
        src_store_slug = dep["source_store"]
        tgt_store_slug = dep["target_store"]
        if src_store_slug not in stores:
            errors.append(f"{dep_id}: unknown source store '{src_store_slug}'")
            continue
        if tgt_store_slug not in stores:
            errors.append(f"{dep_id}: unknown target store '{tgt_store_slug}'")
            continue

        src_store = stores[src_store_slug]
        tgt_store = stores[tgt_store_slug]
        src_table_name = dep["source_table"]
        tgt_table_name = dep["target_table"]

        if src_table_name not in src_store["tables"]:
            errors.append(
                f"{dep_id}: source table '{src_table_name}' not found in {src_store_slug}"
            )
            continue
        if tgt_table_name not in tgt_store["tables"]:
            errors.append(
                f"{dep_id}: target table '{tgt_table_name}' not found in {tgt_store_slug}"
            )
            continue

        src_table = src_store["tables"][src_table_name]
        tgt_table = tgt_store["tables"][tgt_table_name]
        src_col_names = {c["name"] for c in src_table["columns"]}
        tgt_col_names = {c["name"] for c in tgt_table["columns"]}

        for col in dep.get("source_columns", []):
            if col not in src_col_names:
                errors.append(
                    f"{dep_id}: source column '{col}' not found in {src_table_name}"
                )

        for col in dep.get("target_columns", []):
            if col not in tgt_col_names:
                errors.append(
                    f"{dep_id}: target column '{col}' not found in {tgt_table_name}"
                )

    return errors


def validate_functional_groups_consistency() -> list[str]:
    """Verify that CORE_GROUPS, OPERATIONAL_GROUPS, SEARCH_GROUPS match audit_publication_free.py."""
    errors = []
    try:
        from scripts.audit_publication_free import (
            CORE_GROUPS as AUDIT_CORE,
        )
        from scripts.audit_publication_free import (
            OPERATIONAL_GROUPS as AUDIT_OP,
        )
        from scripts.audit_publication_free import (
            SEARCH_GROUPS as AUDIT_SEARCH,
        )

        if CORE_GROUPS != AUDIT_CORE:
            errors.append(
                "CORE_GROUPS classification differs from audit_publication_free.py"
            )
        if OPERATIONAL_GROUPS != AUDIT_OP:
            errors.append(
                "OPERATIONAL_GROUPS classification differs from audit_publication_free.py"
            )
        if SEARCH_GROUPS != AUDIT_SEARCH:
            errors.append(
                "SEARCH_GROUPS classification differs from audit_publication_free.py"
            )
    except Exception as exc:
        errors.append(f"Could not verify audit_publication_free consistency: {exc}")
    return errors
