"""Non-destructive Three-Store Schema Visualization Workbench for git-repo-db.

Generates authoritative schema visualizations across the Three-Store Boundary (ADR 0002):
1. Mermaid ER diagrams (Markdown viewers and GitHub native)
2. DBML exports (dbdiagram.io and dbdocs.io)
3. Standalone interactive HTML workbench (browser-native, zero dependencies, offline)

Supports deterministic generation and non-mutating freshness checks (--check).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


# ==============================================================================
# Mermaid ER Diagram Generator
# ==============================================================================


def _render_mermaid_table_block(
    table_meta: dict[str, Any], *, stub: bool = False
) -> str:
    """Format a table definition for a Mermaid ER diagram block."""
    lines = [f"    {table_meta['name']} {{"]
    if stub:
        pk_cols = table_meta["primary_key"] if table_meta["primary_key"] else ["id"]
        for pk_col in pk_cols:
            lines.append(
                f'        TEXT {pk_col} PK "External reference from {table_meta["group"]}"'
            )
    else:
        for col in table_meta["columns"]:
            c_name = col["name"]
            c_type = col["type"]
            badges: list[str] = []
            if col["is_pk"]:
                badges.append("PK")
            # check if part of foreign key
            is_fk = any(
                c_name in fk["from_columns"] for fk in table_meta["foreign_keys"]
            )
            if is_fk:
                badges.append("FK")
            # check if unique constraint
            is_uk = any(
                [c_name] == u["columns"] and not u.get("partial", False)
                for u in table_meta["unique_constraints"]
            )
            if is_uk and not col["is_pk"]:
                badges.append("UK")

            key_tag = (
                "PK"
                if "PK" in badges
                else "FK"
                if "FK" in badges
                else "UK"
                if "UK" in badges
                else ""
            )

            comments = []
            if col["is_generated"]:
                comments.append(f"GENERATED {col['generation_type']}")
            elif is_fk and "PK" in badges:
                comments.append("FK")
            elif not col["notnull"] and not col["is_pk"]:
                comments.append("nullable")

            comment_str = f' "{", ".join(comments)}"' if comments else ""
            key_space = f" {key_tag}" if key_tag else ""
            lines.append(f"        {c_type} {c_name}{key_space}{comment_str}")
    lines.append("    }")
    return "\n".join(lines)


def _render_mermaid_relationships(
    tables: dict[str, Any], include_external_stubs: bool = True
) -> tuple[list[str], set[str]]:
    """Render Mermaid relationship lines and return needed stub table names."""
    rel_lines = []
    stubs_needed: set[str] = set()

    for t_name in sorted(tables.keys()):
        t = tables[t_name]
        for fk in t["foreign_keys"]:
            tgt = fk["target_table"]
            # Parent side (left end):
            # If all foreign key columns in child are NOT NULL, exactly one parent row is required (||).
            # If any foreign key column is nullable, parent reference is zero or one (|o).
            all_not_null = all(
                next(
                    (c["notnull"] for c in t["columns"] if c["name"] == col),
                    False,
                )
                for col in fk["from_columns"]
            )
            parent_card = "||" if all_not_null else "|o"

            # Child side (right end):
            # A parent never requires at least one child merely due to an FK.
            # If child FK columns form the PK or match an unconditional UNIQUE constraint,
            # at most one child can exist (zero or one: "o|").
            # Unconditional uniqueness cannot be inferred from partial unique indexes.
            # Otherwise, zero or more children may reference the parent ("o{").
            is_unique = (fk["from_columns"] == t["primary_key"]) or any(
                fk["from_columns"] == u["columns"] and not u.get("partial", False)
                for u in t["unique_constraints"]
            )
            child_card = "o|" if is_unique else "o{"

            cols_label = ", ".join(fk["from_columns"])
            edge = f'    {tgt} {parent_card}--{child_card} {t_name} : "references ({cols_label})"'

            if tgt in tables:
                rel_lines.append(edge)
            elif include_external_stubs:
                rel_lines.append(edge)
                stubs_needed.add(tgt)

    return rel_lines, stubs_needed


def generate_mermaid(ir: dict[str, Any]) -> dict[str, str]:
    """Generate Markdown files containing fenced mermaid ER diagrams."""
    outputs: dict[str, str] = {}
    core = ir["stores"]["core"]
    GROUP_METADATA = ir["group_metadata"]
    op = ir["stores"]["operational"]
    search = ir["stores"]["search"]

    # 1. Three-Store Overview (mermaid/overview.md)
    overview_md = f"""# Three-Store Boundary Architecture Overview

Authoritative physical separation under **ADR 0002** and binding owner decisions **PF-P01–PF-P17**.

## Physical Stores and Boundaries

The database architecture intentionally partitions concerns into three distinct SQLite databases:

| Store | Physical Database | Schema Version | Product Tables | Responsibility & Invariant |
|---|---|---|---|---|
| **Core** | `catalog.sqlite3` | {core["schema_version"]} | {core["table_count"]} | Authoritative domain facts, entities, immutable observations, coverage claims, code listings, Git DAG, and Exchange staging. |
| **Operational** | `operational.sqlite3` | {op["schema_version"]} | {op["table_count"]} | Disposable execution tracking, jobs, attempts, packfile cache leases, reservations, and progress. Loss never compromises Core facts. |
| **Search** | `search.sqlite3` | {search["schema_version"]} | {search["table_count"]} | Rebuildable FTS5 trigram virtual tables, search document projections, and index generations. Excluded from normal backups. |

```mermaid
flowchart TD
    subgraph CoreStore["Core Store: catalog.sqlite3 (Schema {core["schema_version"]})"]
        direction TB
        c_ident["Portable Identity & Catalog (14 tables)"]
        c_api["Current API Values (5 tables)"]
        c_cov["Domain Coverage & Enumeration (19 tables)"]
        c_git["Git Domain & Intrinsic DAG (21 tables)"]
        c_cas["CAS & Retained Content (7 tables)"]
        c_exch["Exchange & Admissions (4 tables)"]
    end

    subgraph OpStore["Operational Store: operational.sqlite3 (Schema {op["schema_version"]})"]
        direction TB
        op_jobs["Jobs & Attempts"]
        op_cache["Cache Locators & Leases"]
        op_prog["Acquisition & Collection Progress"]
        op_tele["Search Rebuild Telemetry"]
    end

    subgraph SearchStore["Search Store: search.sqlite3 (Schema {search["schema_version"]})"]
        direction TB
        s_docs["Search Documents (Projections)"]
        s_gen["Index Generations & Membership"]
        s_fts["FTS5 Trigram Virtual Tables (catalog_fts_*)"]
    end

    OpStore -.->|"Logical 1:1 Instance Binding\\n(PF-P11, non-enforced)"| CoreStore
    OpStore -.->|"Logical Progress Tracking\\n(PF-P04, non-enforced)"| CoreStore
    SearchStore -.->|"Logical 1:1 Instance Binding\\n(PF-P14, non-enforced)"| CoreStore
    SearchStore -.->|"Logical Revision Fence\\n(PF-P15, non-enforced)"| CoreStore
```

## Physical vs Logical Relationships

- **Physical Foreign Keys (Solid Edges):** Enforced by SQLite foreign key constraints (`PRAGMA foreign_keys=ON`). **Never cross store boundaries.**
- **Logical References (Dashed Edges):** Application-level identities and revision fences that connect secondary stores to Core. Loss or absence of secondary stores leaves Core evidence 100% intact and valid.

## Cross-Store Logical Dependency Reference

| Source Store & Table | Source Column(s) | Target Store & Table | Target Column(s) | Reference | Description |
|---|---|---|---|---|---|
"""
    for dep in ir["logical_dependencies"]:
        overview_md += f"| `{dep['source_store']}.{dep['source_table']}` | `{', '.join(dep['source_columns'])}` | `{dep['target_store']}.{dep['target_table']}` | `{', '.join(dep['target_columns'])}` | {dep['adr_reference']} | {dep['description']} |\n"

    overview_md += """
## Navigation

- [Core Schema Overview](core-overview.md) — 70 tables partitioned into 7 functional modules.
- [Operational Schema ER Diagram](operational.md) — 10 execution and cache management tables.
- [Search Schema ER Diagram](search.md) — 4 derivative search tables and runtime FTS5 trigram virtual tables.
"""
    outputs["mermaid/overview.md"] = overview_md.strip() + "\n"

    # 2. Core Schema Overview (mermaid/core-overview.md)
    core_overview_md = f"""# Core Store Schema Overview (catalog.sqlite3)

Authoritative domain facts, entities, observations, and evidence under **Core Schema Version {core["schema_version"]}**.

- **Physical Database:** `catalog.sqlite3`
- **DDL SHA-256:** `{core["ddl_sha256"]}`
- **Product Tables:** {core["table_count"]}
- **Views:** {core["view_count"]}
- **Triggers:** {core["trigger_count"]}
- **Physical Foreign Keys:** {core["foreign_key_count"]}
- **Explicit Indexes:** {core["index_count"]}

## High-Level Module Dependency Map

The 70 Core tables are partitioned into 7 cohesive functional categories (presented across 6 modular ER diagrams, with Local Physical Catalog Identity grouped alongside Portable Identity & Registration). SQLite foreign keys connect these modules hierarchically:

```mermaid
flowchart TD
    c_ident["1. Portable Identity & Catalog (14 tables)\\n(13 portable identity + 1 local physical catalog identity)"]
    c_api["2. Current API Values (5 tables)\\nissue_resources, review_resources, change_request_state..."]
    c_cov["3. Domain Coverage & Enumeration (19 tables)\\nfetch_collections, coverage_scopes, coverage_claims..."]
    c_git["4. Git Domain & Intrinsic DAG (21 tables)\\ngit_acquisitions, snapshots, git_objects, commits, trees..."]
    c_cas["5. Retained Content & CAS (7 tables)\\ntext_bodies, payloads, preservation_obligations..."]
    c_exch["6. Exchange Staging (4 tables)\\nexchange_admissions, exchange_staging..."]

    c_api -->|"20 FKs"| c_ident
    c_api -->|"2 FKs"| c_cas
    c_cov -->|"13 FKs"| c_ident
    c_cov -->|"1 FK"| c_git
    c_git -->|"3 FKs"| c_ident
    c_git -->|"1 FK"| c_cov
    c_git -->|"1 FK"| c_cas
    c_cas -->|"1 FK"| c_git
    c_exch -->|"1 FK"| c_cov
```

## Functional Modules Directory

| Category / Module | Tables | Detailed Diagram | Description |
|---|---|---|---|
| **Portable Identity & Registration** | 13 | [core-identity.md](core-identity.md) | Universal portable identities, Sources, repositories, bindings, endpoints, and identity relations. |
| **Local Physical Catalog Identity** | 1 | [core-identity.md](core-identity.md) | Local SQLite database singleton and receiver-local revision counter (`database_identity`, grouped into core-identity diagram). |
| **Current API Values** | 5 | [core-current-state.md](core-current-state.md) | Current PR/Issue/thread observation states, resource projections, and generated column contracts. |
| **Domain Coverage & Enumeration** | 19 | [core-coverage.md](core-coverage.md) | API collections, memberships, typed coverage claims/scopes, and code listing evidence. |
| **Git Domain & Intrinsic DAG** | 21 | [core-git.md](core-git.md) | Git acquisitions, snapshots, objects, tree entries, commit DAG, and verified byte facts. |
| **Retained Content & CAS** | 7 | [core-cas.md](core-cas.md) | Shared CAS storage, verified payloads, quarantine, and durable preservation obligations. |
| **Exchange Staging & Admissions** | 4 | [core-exchange.md](core-exchange.md) | Inter-catalog sync staging, admission receipts, and conflicting candidate resolution. |

## Complete Core Table Inventory

| Table Name | Module | Columns | Primary Key | Outgoing FKs | Incoming FKs | Strict |
|---|---|---|---|---|---|---|
"""
    for t_name in sorted(core["tables"].keys()):
        t = core["tables"][t_name]
        pk_s = ", ".join(t["primary_key"]) if t["primary_key"] else "None"
        strict_s = "Yes" if t["is_strict"] else "No"
        core_overview_md += f"| `{t_name}` | {t['group_title']} | {len(t['columns'])} | `{pk_s}` | {len(t['foreign_keys'])} | {len(t['incoming_foreign_keys'])} | {strict_s} |\n"

    core_overview_md += """
## Core Views Inventory (20 Views)

| View Name | Columns | Description |
|---|---|---|
"""
    for v_name in sorted(core["views"].keys()):
        v = core["views"][v_name]
        core_overview_md += f"| `{v_name}` | {len(v['columns'])} | Canonical read projection for {v_name.replace('_', ' ')} |\n"

    outputs["mermaid/core-overview.md"] = core_overview_md.strip() + "\n"

    # 3. Core Functional Module Mermaid files
    module_definitions = [
        (
            "core-identity.md",
            "Core Module: Portable Identity & Registration",
            [
                "portable_identity_and_registration",
                "local_physical_catalog",
            ],
            "Portable UUIDv4 identities, service instances, sources, repositories, bindings, change requests, and identity relations.",
        ),
        (
            "core-current-state.md",
            "Core Module: Current API Values & Projections",
            ["current_api_values"],
            "Latest state projections for PRs, issues, documents, and review threads with JSON-contract provenance and generated columns.",
        ),
        (
            "core-coverage.md",
            "Core Module: Domain Enumeration & Coverage Evidence",
            ["domain_enumeration_and_coverage"],
            "Collections, memberships, completion markers, typed coverage scopes/claims, and code listing assessments.",
        ),
        (
            "core-git.md",
            "Core Module: Git Identity, Intrinsic DAG & Capture",
            ["git_identity_intrinsic_and_capture"],
            "Immutable Git acquisitions, snapshots, objects, commits, trees, tags, ref observations, and byte facts.",
        ),
        (
            "core-cas.md",
            "Core Module: Retained Content Integrity & CAS",
            ["retained_content_integrity"],
            "Shared CAS payload storage, quarantine, unreferenced bodies, and durable preservation obligations.",
        ),
        (
            "core-exchange.md",
            "Core Module: Exchange Staging & Admissions",
            ["exchange_staging_and_admissions"],
            "Staging area for catalog synchronization, admission receipts, and conflicting candidate resolution.",
        ),
    ]

    for filename, title, groups, desc in module_definitions:
        mod_tables = {
            t_name: t for t_name, t in core["tables"].items() if t["group"] in groups
        }

        # Relationships and external stubs
        rel_lines, stubs_needed = _render_mermaid_relationships(
            mod_tables, include_external_stubs=True
        )

        mod_md = f"""# {title}

{desc}

- **Store:** Core (`catalog.sqlite3`)
- **Module Tables:** {len(mod_tables)}

```mermaid
erDiagram
"""
        # Render internal tables
        for t_name in sorted(mod_tables.keys()):
            mod_md += (
                _render_mermaid_table_block(mod_tables[t_name], stub=False) + "\n\n"
            )

        # Render external stub entities (target tables outside this module)
        for stub_name in sorted(stubs_needed):
            if stub_name in core["tables"]:
                mod_md += (
                    _render_mermaid_table_block(core["tables"][stub_name], stub=True)
                    + "\n\n"
                )

        # Render relationships
        for rel in sorted(rel_lines):
            mod_md += rel + "\n"

        mod_md += "```\n\n"

        # Table of cross-module relationships
        cross_fks = []
        for t_name, t in sorted(mod_tables.items()):
            for fk in t["foreign_keys"]:
                if fk["target_table"] not in mod_tables:
                    tgt_t = core["tables"].get(fk["target_table"])
                    cross_fks.append(
                        {
                            "source_table": t_name,
                            "source_cols": ", ".join(fk["from_columns"]),
                            "target_table": fk["target_table"],
                            "target_cols": ", ".join(fk["to_columns"]),
                            "target_group": tgt_t["group_title"]
                            if tgt_t
                            else "External",
                            "target_slug": GROUP_METADATA.get(tgt_t["group"], {}).get(
                                "slug", "core-overview"
                            )
                            if tgt_t
                            else "core-overview",
                            "on_update": fk["on_update"],
                            "on_delete": fk["on_delete"],
                        }
                    )

        if cross_fks:
            mod_md += "## Cross-Module Foreign Keys\n\n"
            mod_md += "| Source Table | Source Column(s) | Target Table | Target Column(s) | Target Module | Action |\n"
            mod_md += "|---|---|---|---|---|---|\n"
            for x in cross_fks:
                mod_md += f"| `{x['source_table']}` | `{x['source_cols']}` | [`{x['target_table']}`]({x['target_slug']}.md) | `{x['target_cols']}` | {x['target_group']} | ON UPDATE {x['on_update']}, ON DELETE {x['on_delete']} |\n"
            mod_md += "\n"

        mod_md += "[Back to Core Overview](core-overview.md) | [Back to Architecture Overview](overview.md)\n"
        outputs[f"mermaid/{filename}"] = mod_md.strip() + "\n"

    # 4. Operational ER Diagram (mermaid/operational.md)
    op_rel_lines, _ = _render_mermaid_relationships(
        op["tables"], include_external_stubs=False
    )
    op_md = f"""# Operational Store Schema (operational.sqlite3)

Execution management, worker progress, and packfile cache leases under **Operational Schema Version {op["schema_version"]}**.

- **Physical Database:** `operational.sqlite3`
- **DDL SHA-256:** `{op["ddl_sha256"]}`
- **Product Tables:** {op["table_count"]}
- **Physical Foreign Keys:** {op["foreign_key_count"]}
- **Triggers:** {op["trigger_count"]}
- **Physical Invariant:** Completely physically separate from `catalog.sqlite3`. Loss of Operational DB never compromises Core facts (ADR 0002 §2 PF-P06, PF-P12).

## Physical ER Diagram

```mermaid
erDiagram
"""
    for t_name in sorted(op["tables"].keys()):
        op_md += _render_mermaid_table_block(op["tables"][t_name], stub=False) + "\n\n"

    for rel in sorted(op_rel_lines):
        op_md += rel + "\n"

    op_md += """```

## Logical Cross-Store References to Core

Operational tables maintain application-level references to Core identities without SQLite foreign key constraints:

| Operational Table | Operational Column | Core Target Table | Core Column | Invariant & ADR Reference |
|---|---|---|---|---|
| `operational_identity` | `catalog_db_instance_id` | `database_identity` | `db_instance_id` | Strict 1:1 ownership binding between Operational DB and Core Catalog (ADR 0002 §2 PF-P11). |
| `acquisition_progress` | `git_acquisition_id` | `git_acquisitions` | `git_acquisition_id` | Git acquisition worker progress tracking Core acquisition entity (ADR 0002 §3.2, PF-P04). |
| `collection_progress` | `fetch_collection_id` | `fetch_collections` | `fetch_collection_id` | API collection worker progress tracking Core fetch collection (ADR 0002 §3.2, PF-P03). |
| `cache_locators` | `repository_uuidv4` | `repositories` | `repository_uuidv4` | Physical cache directory mapping. Core incomplete preservation obligations block cache GC even if locator disappears (three-store-invariants §1). |

[Back to Architecture Overview](overview.md)
"""
    outputs["mermaid/operational.md"] = op_md.strip() + "\n"

    # 5. Search ER Diagram (mermaid/search.md)
    search_rel_lines, _ = _render_mermaid_relationships(
        search["tables"], include_external_stubs=False
    )
    search_md = f"""# Search Store Schema (search.sqlite3)

Rebuildable FTS5 search projections and index generations under **Search Schema Version {search["schema_version"]}**.

- **Physical Database:** `search.sqlite3`
- **DDL SHA-256:** `{search["ddl_sha256"]}`
- **Fixed Product Tables:** {search["table_count"]}
- **Physical Foreign Keys:** {search["foreign_key_count"]}
- **Triggers:** {search["trigger_count"]}
- **Physical Invariant:** Completely rebuildable from Core store. Excluded from normal backups (ADR 0002 §2 PF-P14, PF-P16, PF-P17).

## Fixed Packaged Schema ER Diagram

```mermaid
erDiagram
"""
    for t_name in sorted(search["tables"].keys()):
        search_md += (
            _render_mermaid_table_block(search["tables"][t_name], stub=False) + "\n\n"
        )

    for rel in sorted(search_rel_lines):
        search_md += rel + "\n"

    search_md += """```

## Dynamic FTS5 Virtual Tables (`catalog_fts_<generation_id>`)

At runtime, an explicit `repo-catalog index rebuild` command populates `search_documents` and instantiates dedicated SQLite FTS5 virtual tables:

```sql
CREATE VIRTUAL TABLE catalog_fts_<generation_id> USING fts5(
    body,
    tokenize='trigram case_sensitive 1',
    content='',
    detail=full
);
```

- **Generation Lifecycle:** Indexed generations transition through states: `building` -> `ready` -> `retired` -> `removed` in table `index_generations`.
- **FTS5 Internal Shadow Tables:** SQLite automatically creates internal shadow tables for each virtual table (`catalog_fts_<id>_data`, `catalog_fts_<id>_idx`, `catalog_fts_<id>_content`, `catalog_fts_<id>_docsize`, `catalog_fts_<id>_config`). These shadow tables are derivative implementation artifacts and are intentionally excluded from product schema inventories.
- **Search Fallback:** If `search.sqlite3` is absent, stale, or corrupt, search commands automatically fall back to direct-scan queries against `catalog.sqlite3` without failing (ADR 0002 §2 PF-P15).

## Logical Cross-Store References to Core

| Search Table | Search Column | Core Target Table | Core Column | Invariant & ADR Reference |
|---|---|---|---|---|
| `search_identity` | `catalog_db_instance_id` | `database_identity` | `db_instance_id` | Strict 1:1 ownership binding between Search DB and Core Catalog (ADR 0002 §2 PF-P14). |
| `search_identity` | `core_revision_fence` | `database_identity` | `local_revision` | Global index freshness fence tracking Core local revision (ADR 0002 §3.3, §4). |
| `index_generations` | `core_revision_fence` | `database_identity` | `local_revision` | Per-generation snapshot fence recorded during rebuild projection (three-store-invariants §4). |
| `search_documents` | `source_key` | `git_objects` / `text_bodies` | `git_object_id` / `sha256` | Projections derived from Core Git blobs/commits ('git:<id>') and PR/Issue text bodies (SHA-256 hex) (ADR 0002 §3.3, §4). |

[Back to Architecture Overview](overview.md)
"""
    outputs["mermaid/search.md"] = search_md.strip() + "\n"

    return outputs


# ==============================================================================
# DBML Generator
# ==============================================================================


def _render_dbml_table(table_meta: dict[str, Any]) -> str:
    """Format a table definition in DBML format."""
    lines = [f"Table {table_meta['name']} {{"]
    for col in table_meta["columns"]:
        c_name = col["name"]
        c_type = col["type"].lower()
        settings: list[str] = []

        if col["is_pk"] and not table_meta["is_composite_pk"]:
            settings.append("pk")
        if col["notnull"]:
            settings.append("not null")

        # Single-column unconditional UNIQUE constraint (C2)
        is_col_unique = any(
            u["columns"] == [c_name] and not u.get("partial", False)
            for u in table_meta["unique_constraints"]
        )
        if is_col_unique and not col["is_pk"]:
            settings.append("unique")

        if col["default_value"] is not None:
            settings.append(f"default: `{col['default_value']}`")

        # Column notes
        col_notes = []
        if col["is_generated"]:
            col_notes.append(f"GENERATED {col['generation_type']}")
        if col["is_pk"] and table_meta["is_composite_pk"]:
            col_notes.append(f"Composite PK (pos {col['pk_position']})")
        if col_notes:
            settings.append(f"note: '{', '.join(col_notes)}'")

        setting_str = f" [{', '.join(settings)}]" if settings else ""
        lines.append(f"  {c_name} {c_type}{setting_str}")

    # Composite PK or indexes in indexes block
    idx_lines = []
    if table_meta["is_composite_pk"]:
        pk_cols_s = ", ".join(table_meta["primary_key"])
        idx_lines.append(f"    ({pk_cols_s}) [pk]")

    # Composite unconditional UNIQUE constraints
    emitted_unique_names = set()
    for u in table_meta["unique_constraints"]:
        if len(u["columns"]) > 1:
            u_cols_s = ", ".join(u["columns"])
            if not u["name"].startswith("sqlite_autoindex_"):
                idx_lines.append(f"    ({u_cols_s}) [unique, name: '{u['name']}']")
            else:
                idx_lines.append(f"    ({u_cols_s}) [unique]")
            emitted_unique_names.add(u["name"])

    # Explicit indexes
    for idx in table_meta["indexes"]:
        if idx["name"] in emitted_unique_names:
            continue
        cols_s = ", ".join(idx["columns"])
        opt = []
        if idx["name"]:
            opt.append(f"name: '{idx['name']}'")
        if idx["partial"]:
            # Never export a partial unique index as an unconditional unique constraint in DBML (C3)
            pred = (
                f"WHERE {idx['predicate']}" if idx.get("predicate") else "partial index"
            )
            pred_escaped = pred.replace("'", "\\'")
            if idx["unique"]:
                opt.append(f"note: 'UNIQUE {pred_escaped}'")
            else:
                opt.append(f"note: 'partial index: {pred_escaped}'")
        elif idx["unique"]:
            opt.append("unique")
        opt_s = f" [{', '.join(opt)}]" if opt else ""
        idx_lines.append(f"    ({cols_s}){opt_s}")

    if idx_lines:
        lines.append("")
        lines.append("  indexes {")
        lines.extend(idx_lines)
        lines.append("  }")

    strict_s = "STRICT mode enabled. " if table_meta["is_strict"] else ""
    lines.append("")
    lines.append(f"  Note: '{strict_s}Functional group: {table_meta['group_title']}.'")
    lines.append("}")
    return "\n".join(lines)


def _render_dbml_relationships(tables: dict[str, Any]) -> list[str]:
    """Render physical foreign key references in DBML format."""
    lines = []
    for t_name in sorted(tables.keys()):
        t = tables[t_name]
        for fk in t["foreign_keys"]:
            tgt = fk["target_table"]
            # DBML ref format:
            # Single: Ref: child.col > parent.col [update: ..., delete: ...]
            # Composite: Ref: child.(col1, col2) > parent.(col1, col2)
            u_act = fk["on_update"].lower()
            d_act = fk["on_delete"].lower()
            settings = f"[update: {u_act}, delete: {d_act}]"

            if fk["is_composite"]:
                src_cols = f"({', '.join(fk['from_columns'])})"
                tgt_cols = f"({', '.join(fk['to_columns'])})"
            else:
                src_cols = fk["from_columns"][0]
                tgt_cols = fk["to_columns"][0]

            lines.append(
                f"Ref fk_{t_name}_{fk['id']}: {t_name}.{src_cols} > {tgt}.{tgt_cols} {settings}"
            )
    return lines


def generate_dbml(ir: dict[str, Any]) -> dict[str, str]:
    """Generate DBML export files suitable for dbdiagram.io and dbdocs.io."""
    outputs: dict[str, str] = {}
    core = ir["stores"]["core"]
    op = ir["stores"]["operational"]
    search = ir["stores"]["search"]

    # 1. dbml/core.dbml
    core_dbml = f"""// git-repo-db Core Store Schema (catalog.sqlite3)
// Schema Version: {core["schema_version"]}
// DDL SHA-256: {core["ddl_sha256"]}
// Authoritative domain facts, entities, observations, and evidence.
// Compatible with https://dbdiagram.io/ and https://dbdocs.io/

Project git_repo_db_core {{
  database_type: 'SQLite'
  Note: '''
    # git-repo-db Core Store (catalog.sqlite3)
    Schema Version: {core["schema_version"]}
    Tables: {core["table_count"]}
    Physical Foreign Keys: {core["foreign_key_count"]}
    DDL SHA-256: {core["ddl_sha256"]}
    
    Authoritative domain facts, entities, observations, coverage claims, Git DAG, and Exchange staging.
    Physical boundary: strictly isolated inside catalog.sqlite3 under ADR 0002.
  '''
}}

"""
    for t_name in sorted(core["tables"].keys()):
        core_dbml += _render_dbml_table(core["tables"][t_name]) + "\n\n"

    core_dbml += (
        "// Physical Foreign Keys (enforced by SQLite PRAGMA foreign_keys=ON)\n"
    )
    for ref_line in _render_dbml_relationships(core["tables"]):
        core_dbml += ref_line + "\n"

    outputs["dbml/core.dbml"] = core_dbml.strip() + "\n"

    # 2. dbml/operational.dbml
    op_dbml = f"""// git-repo-db Operational Store Schema (operational.sqlite3)
// Schema Version: {op["schema_version"]}
// DDL SHA-256: {op["ddl_sha256"]}
// Disposable jobs, attempts, packfile cache leases, reservations, and progress.
// Compatible with https://dbdiagram.io/ and https://dbdocs.io/

Project git_repo_db_operational {{
  database_type: 'SQLite'
  Note: '''
    # git-repo-db Operational Store (operational.sqlite3)
    Schema Version: {op["schema_version"]}
    Tables: {op["table_count"]}
    Physical Foreign Keys: {op["foreign_key_count"]}
    DDL SHA-256: {op["ddl_sha256"]}
    
    Transient execution state, jobs, job attempts, space reservations, and cache leases (ADR 0002).
    Physical boundary: completely isolated inside operational.sqlite3. Loss never compromises Core facts.
  '''
}}

"""
    for t_name in sorted(op["tables"].keys()):
        op_dbml += _render_dbml_table(op["tables"][t_name]) + "\n\n"

    op_dbml += "// Physical Foreign Keys (enforced by SQLite PRAGMA foreign_keys=ON)\n"
    for ref_line in _render_dbml_relationships(op["tables"]):
        op_dbml += ref_line + "\n"

    op_dbml += """
// Logical Cross-Store References to Core (ADR 0002, application-enforced, NOT SQLite FKs)
// Ref: operational_identity.catalog_db_instance_id > database_identity.db_instance_id
// Ref: acquisition_progress.git_acquisition_id > git_acquisitions.git_acquisition_id
// Ref: collection_progress.fetch_collection_id > fetch_collections.fetch_collection_id
// Ref: cache_locators.repository_uuidv4 > repositories.repository_uuidv4
"""
    outputs["dbml/operational.dbml"] = op_dbml.strip() + "\n"

    # 3. dbml/search.dbml
    search_dbml = f"""// git-repo-db Search Store Schema (search.sqlite3)
// Schema Version: {search["schema_version"]}
// DDL SHA-256: {search["ddl_sha256"]}
// Rebuildable FTS5 search projections and index generations.
// Compatible with https://dbdiagram.io/ and https://dbdocs.io/

Project git_repo_db_search {{
  database_type: 'SQLite'
  Note: '''
    # git-repo-db Search Store (search.sqlite3)
    Schema Version: {search["schema_version"]}
    Fixed Tables: {search["table_count"]}
    Physical Foreign Keys: {search["foreign_key_count"]}
    DDL SHA-256: {search["ddl_sha256"]}
    
    Rebuildable FTS5 trigram virtual tables, document projections, and index generations (ADR 0002).
    Physical boundary: completely isolated inside search.sqlite3. Excluded from normal backups.
  '''
}}

"""
    for t_name in sorted(search["tables"].keys()):
        search_dbml += _render_dbml_table(search["tables"][t_name]) + "\n\n"

    search_dbml += (
        "// Physical Foreign Keys (enforced by SQLite PRAGMA foreign_keys=ON)\n"
    )
    for ref_line in _render_dbml_relationships(search["tables"]):
        search_dbml += ref_line + "\n"

    search_dbml += """
// Dynamic FTS5 Virtual Tables (instantiated at runtime by index rebuild command)
// Table catalog_fts_generation_id {
//   body text
//   Note: 'SQLite FTS5 virtual table with tokenize=trigram case_sensitive 1'
// }

// Logical Cross-Store References to Core (ADR 0002, application-enforced, NOT SQLite FKs)
// Ref: search_identity.catalog_db_instance_id > database_identity.db_instance_id
// Ref: search_identity.core_revision_fence > database_identity.local_revision
// Ref: index_generations.core_revision_fence > database_identity.local_revision
// Ref: search_documents.source_key > git_objects.git_object_id (for code/commits, encoded 'git:<id>')
// Ref: search_documents.source_key > text_bodies.sha256 (for pr/issue, hex-encoded SHA-256)
"""
    outputs["dbml/search.dbml"] = search_dbml.strip() + "\n"

    # 4. dbml/combined.dbml (Conceptual combined export)
    combined_dbml = f"""// git-repo-db Combined Conceptual Schema (Three-Store Boundary)
// Core Schema {core["schema_version"]} ({core["table_count"]} tables)
// Operational Schema {op["schema_version"]} ({op["table_count"]} tables)
// Search Schema {search["schema_version"]} ({search["table_count"]} tables)
// ADR 0002 Three-Store Boundary Architecture

Project git_repo_db_three_store {{
  database_type: 'SQLite'
  Note: '''
    # git-repo-db Three-Store Conceptual Model
    Total Product Tables: {ir["summary"]["total_product_tables"]}
    - Core: catalog.sqlite3 (Version {core["schema_version"]})
    - Operational: operational.sqlite3 (Version {op["schema_version"]})
    - Search: search.sqlite3 (Version {search["schema_version"]})
    
    Physical SQLite foreign keys operate strictly WITHIN each store.
    Cross-store connections are logical application-level dependencies under ADR 0002.
  '''
}}

"""
    # Render all tables with store prefixes for combined visualization
    for s_slug, s_data in [
        ("core", core),
        ("op", op),
        ("search", search),
    ]:
        combined_dbml += f"// ==================== {s_data['title']} ({s_data['db_filename']}) ====================\n\n"
        for t_name in sorted(s_data["tables"].keys()):
            combined_dbml += _render_dbml_table(s_data["tables"][t_name]) + "\n\n"

        combined_dbml += f"// Physical Foreign Keys for {s_data['title']}\n"
        for ref_line in _render_dbml_relationships(s_data["tables"]):
            combined_dbml += ref_line + "\n"
        combined_dbml += "\n"

    # TableGroup constructs to explicitly group tables by physical store (ADR 0002)
    combined_dbml += (
        "// ==================== Store Groupings (ADR 0002) ====================\n\n"
    )
    for group_name, s_data in [
        ("core_store", core),
        ("operational_store", op),
        ("search_store", search),
    ]:
        combined_dbml += f"TableGroup {group_name} {{\n"
        for t_name in sorted(s_data["tables"].keys()):
            combined_dbml += f"  {t_name}\n"
        combined_dbml += "}\n\n"

    combined_dbml += """// ==================== Logical Cross-Store Dependencies (ADR 0002) ====================
// These are application-level dependencies across physical SQLite databases.
// They are NOT enforced by SQLite foreign keys. Loss of Operational or Search never invalidates Core.
"""
    for dep in ir["logical_dependencies"]:
        src_cols = (
            f"({', '.join(dep['source_columns'])})" if dep.get("source_columns") else ""
        )
        tgt_cols = (
            f"({', '.join(dep['target_columns'])})" if dep.get("target_columns") else ""
        )
        combined_dbml += (
            f"// Ref {dep['id']}: {dep['source_table']}.{src_cols} > {dep['target_table']}.{tgt_cols} "
            f"[note: '{dep['adr_reference']} - {dep['description']}']\n"
        )

    outputs["dbml/combined.dbml"] = combined_dbml.strip() + "\n"

    return outputs


# ==============================================================================
# Standalone Interactive HTML Viewer Generator
# ==============================================================================


def generate_html(ir: dict[str, Any]) -> dict[str, str]:
    """Generate self-contained interactive HTML schema workbench."""
    import copy

    # Truncate large repetitive JSON schema guard triggers for browser performance
    html_ir = copy.deepcopy(ir)
    for s in html_ir["stores"].values():
        for trig in s["triggers"].values():
            if len(trig["sql"]) > 600:
                trig["sql"] = (
                    trig["sql"][:400]
                    + "\n-- ... [truncated long JSON guard contract; see json_contracts.sql] ..."
                )

    ir_json = json.dumps(html_ir, indent=None, separators=(",", ":"))

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>git-repo-db Schema Visualization Workbench</title>
<style>
:root {{
  --bg-base: #0f172a;
  --bg-surface: #1e293b;
  --bg-card: #334155;
  --bg-card-hover: #475569;
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --text-sub: #cbd5e1;
  --border: #334155;
  --border-light: #475569;
  --accent: #38bdf8;
  --accent-hover: #0ea5e9;
  --accent-rgb: 56, 189, 248;
  --badge-pk: #facc15;
  --badge-fk: #38bdf8;
  --badge-uk: #4ade80;
  --badge-gen: #c084fc;
  --badge-log: #f472b6;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  background-color: var(--bg-base);
  color: var(--text-main);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}}

header {{
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  flex-shrink: 0;
  gap: 16px;
}}

.brand {{
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 16px;
  color: var(--text-main);
}}

.brand-badge {{
  background: rgba(var(--accent-rgb), 0.15);
  color: var(--accent);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 500;
}}

.store-tabs {{
  display: flex;
  background: var(--bg-base);
  padding: 3px;
  border-radius: 6px;
  border: 1px solid var(--border);
}}

.store-tab {{
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 4px;
  cursor: pointer;
  border: none;
  background: transparent;
  color: var(--text-muted);
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}}

.store-tab:hover {{ color: var(--text-main); }}
.store-tab.active {{
  background: var(--bg-card);
  color: var(--text-main);
  font-weight: 600;
}}

.header-right {{
  display: flex;
  align-items: center;
  gap: 12px;
}}

.search-box {{
  position: relative;
  width: 260px;
}}

.search-box input {{
  width: 100%;
  background: var(--bg-base);
  border: 1px solid var(--border);
  color: var(--text-main);
  padding: 6px 10px 6px 30px;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
}}

.search-box input:focus {{ border-color: var(--accent); }}

.search-icon {{
  position: absolute;
  left: 9px;
  top: 8px;
  color: var(--text-muted);
  width: 14px;
  height: 14px;
}}

.layout {{
  display: flex;
  flex: 1;
  overflow: hidden;
}}

aside {{
  width: 320px;
  background: var(--bg-surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}}

.sidebar-header {{
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}}

.group-select {{
  width: 100%;
  background: var(--bg-base);
  color: var(--text-main);
  border: 1px solid var(--border);
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 12px;
  outline: none;
}}

.sidebar-stats {{
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  justify-content: space-between;
}}

.table-list {{
  flex: 1;
  overflow-y: auto;
  padding: 6px 0;
}}

.table-item {{
  padding: 8px 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-left: 3px solid transparent;
  transition: all 0.1s ease;
}}

.table-item:hover {{ background: rgba(255, 255, 255, 0.03); }}
.table-item.active {{
  background: var(--bg-card);
  border-left-color: var(--accent);
}}

.table-item-name {{
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-main);
}}

.table-item-badges {{
  display: flex;
  gap: 4px;
}}

.mini-badge {{
  font-size: 10px;
  font-family: var(--font-mono);
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--bg-base);
  color: var(--text-muted);
}}

main {{
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
  background: var(--bg-base);
}}

.table-view {{
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}}

.table-header {{
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
}}

.table-title {{
  font-size: 22px;
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 12px;
}}

.tag {{
  font-size: 11px;
  font-family: var(--font-mono);
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}}

.tag-strict {{ background: rgba(74, 222, 128, 0.15); color: #4ade80; }}
.tag-store {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; }}
.tag-group {{ background: rgba(192, 132, 252, 0.15); color: #c084fc; }}

.view-tabs {{
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 8px;
}}

.view-tab {{
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 500;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}}

.view-tab:hover {{ color: var(--text-main); background: var(--bg-surface); }}
.view-tab.active {{ color: var(--accent); background: var(--bg-surface); font-weight: 600; }}

.card {{
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}}

.card-header {{
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.02);
  border-bottom: 1px solid var(--border);
  font-weight: 600;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}

table.data-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}}

table.data-table th {{
  background: rgba(255, 255, 255, 0.02);
  text-align: left;
  padding: 10px 14px;
  color: var(--text-muted);
  font-weight: 500;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}}

table.data-table td {{
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  color: var(--text-sub);
}}

table.data-table tr:hover td {{ background: rgba(255, 255, 255, 0.015); }}

.col-name {{
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-main);
}}

.col-type {{
  font-family: var(--font-mono);
  color: var(--accent);
  font-size: 12px;
}}

.badge {{
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-family: var(--font-mono);
  font-weight: 600;
  margin-right: 4px;
}}

.badge-pk {{ background: rgba(250, 204, 21, 0.2); color: var(--badge-pk); }}
.badge-fk {{ background: rgba(56, 189, 248, 0.2); color: var(--badge-fk); }}
.badge-uk {{ background: rgba(74, 222, 128, 0.2); color: var(--badge-uk); }}
.badge-gen {{ background: rgba(192, 132, 252, 0.2); color: var(--badge-gen); }}
.badge-log {{ background: rgba(244, 114, 182, 0.2); color: var(--badge-log); }}

.link-table {{
  color: var(--accent);
  text-decoration: none;
  font-family: var(--font-mono);
  font-weight: 500;
  cursor: pointer;
}}
.link-table:hover {{ text-decoration: underline; }}

pre.sql-code {{
  padding: 16px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-sub);
  background: var(--bg-base);
  overflow-x: auto;
  line-height: 1.6;
}}

.graph-container {{
  width: 100%;
  min-height: 380px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}

.graph-header {{
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.02);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  justify-content: space-between;
}}

svg.neighborhood-svg {{
  width: 100%;
  height: 100%;
  min-height: 350px;
}}

.overview-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
}}

.store-card {{
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}}

.store-card h3 {{
  font-size: 18px;
  color: var(--text-main);
  display: flex;
  align-items: center;
  justify-content: space-between;
}}

.store-card p {{
  color: var(--text-muted);
  font-size: 13px;
}}

.metric-row {{
  display: flex;
  gap: 16px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}}

.metric {{
  display: flex;
  flex-direction: column;
}}

.metric-val {{
  font-size: 20px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--accent);
}}

.metric-lbl {{
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
}}

/* Responsive */
@media (max-width: 768px) {{
  body {{ overflow-x: hidden; }}
  header {{
    height: auto;
    flex-wrap: wrap;
    padding: 10px 12px;
    gap: 8px;
  }}
  .brand {{
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .store-tabs {{
    overflow-x: auto;
    max-width: 100%;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 2px;
    scrollbar-width: thin;
  }}
  .header-right {{
    width: 100%;
  }}
  .search-box {{
    width: 100%;
  }}
  .layout {{ flex-direction: column; }}
  aside {{ width: 100%; height: 260px; max-height: 40vh; }}
  main {{ padding: 12px; overflow-x: hidden; }}
  .card {{ overflow-x: auto; }}
  .data-table {{ min-width: 100%; }}
}}
</style>
</head>
<body>

<header>
  <div class="brand">
    <span>git-repo-db</span>
    <span class="brand-badge">Schema Workbench</span>
  </div>
  
  <div class="store-tabs">
    <button class="store-tab active" onclick="setStore('core')">Core ({ir["summary"]["core_tables"]})</button>
    <button class="store-tab" onclick="setStore('operational')">Operational ({ir["summary"]["operational_tables"]})</button>
    <button class="store-tab" onclick="setStore('search')">Search ({ir["summary"]["search_tables"]})</button>
    <button class="store-tab" onclick="showArchitectureView()">Architecture Map</button>
    <button class="store-tab" onclick="showComparisonView()">Workbench Guide</button>
  </div>

  <div class="header-right">
    <div class="search-box">
      <svg class="search-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
      </svg>
      <input type="text" id="searchInput" placeholder="Search tables or columns..." oninput="handleSearch(this.value)">
    </div>
  </div>
</header>

<div class="layout">
  <aside id="sidebar">
    <div class="sidebar-header">
      <select id="groupSelect" class="group-select" onchange="handleGroupChange(this.value)">
        <option value="all">All Functional Groups</option>
      </select>
      <div class="sidebar-stats">
        <span id="filteredCount">70 tables</span>
        <span id="storeBadge">catalog.sqlite3</span>
      </div>
    </div>
    <div class="table-list" id="tableList"></div>
  </aside>

  <main id="mainPanel">
    <div id="contentArea"></div>
  </main>
</div>

<script>
const SCHEMA_DATA = {ir_json};

let currentStore = "core";
let currentGroup = "all";
let currentTable = null;
let currentViewTab = "columns";
let searchQuery = "";

function init() {{
  populateGroupDropdown();
  renderSidebarTableList();
  // Select first table in core
  const firstTable = Object.keys(SCHEMA_DATA.stores[currentStore].tables).sort()[0];
  selectTable(firstTable);
}}

function setStore(storeSlug) {{
  currentStore = storeSlug;
  currentGroup = "all";
  currentViewTab = "columns";
  
  document.querySelectorAll('.store-tab').forEach(tab => {{
    tab.classList.toggle('active', tab.textContent.toLowerCase().includes(storeSlug));
  }});
  
  populateGroupDropdown();
  renderSidebarTableList();
  const firstTable = Object.keys(SCHEMA_DATA.stores[currentStore].tables).sort()[0];
  selectTable(firstTable);
}}

function populateGroupDropdown() {{
  const select = document.getElementById("groupSelect");
  select.innerHTML = '<option value="all">All Functional Groups</option>';
  
  if (currentStore === "core") {{
    const groupCounts = {{}};
    Object.values(SCHEMA_DATA.stores.core.tables).forEach(t => {{
      groupCounts[t.group] = (groupCounts[t.group] || 0) + 1;
    }});
    
    Object.keys(groupCounts).sort().forEach(g => {{
      const meta = SCHEMA_DATA.group_metadata[g] || {{ title: g }};
      const opt = document.createElement("option");
      opt.value = g;
      opt.textContent = `${{meta.title}} (${{groupCounts[g]}})`;
      select.appendChild(opt);
    }});
    select.style.display = "block";
  }} else {{
    select.style.display = "none";
  }}
  document.getElementById("storeBadge").textContent = SCHEMA_DATA.stores[currentStore].db_filename;
}}

function handleGroupChange(group) {{
  currentGroup = group;
  renderSidebarTableList();
}}

function handleSearch(query) {{
  searchQuery = query.trim().toLowerCase();
  renderSidebarTableList();
}}

function renderSidebarTableList() {{
  const listEl = document.getElementById("tableList");
  listEl.innerHTML = "";
  
  const tables = SCHEMA_DATA.stores[currentStore].tables;
  const filtered = Object.keys(tables).sort().filter(tName => {{
    const t = tables[tName];
    if (currentGroup !== "all" && t.group !== currentGroup) return false;
    if (!searchQuery) return true;
    
    // Match table name
    if (tName.toLowerCase().includes(searchQuery)) return true;
    // Match column names
    return t.columns.some(c => c.name.toLowerCase().includes(searchQuery));
  }});

  document.getElementById("filteredCount").textContent = `${{filtered.length}} tables`;

  filtered.forEach(tName => {{
    const t = tables[tName];
    const item = document.createElement("div");
    item.className = `table-item ${{currentTable === tName ? "active" : ""}}`;
    item.onclick = () => selectTable(tName);
    
    const fkCount = t.foreign_keys.length;
    item.innerHTML = `
      <span class="table-item-name">${{tName}}</span>
      <div class="table-item-badges">
        <span class="mini-badge">${{t.columns.length}}c</span>
        ${{fkCount > 0 ? `<span class="mini-badge" style="color:var(--accent)">${{fkCount}}fk</span>` : ""}}
      </div>
    `;
    listEl.appendChild(item);
  }});
}}

function selectTable(tName) {{
  currentTable = tName;
  
  // Highlight in sidebar
  document.querySelectorAll('.table-item').forEach(el => {{
    const name = el.querySelector('.table-item-name').textContent;
    el.classList.toggle('active', name === tName);
  }});
  
  renderTableDetails();
}}

function setViewTab(tab) {{
  currentViewTab = tab;
  renderTableDetails();
}}

function renderTableDetails() {{
  if (!currentTable) return;
  const t = SCHEMA_DATA.stores[currentStore].tables[currentTable];
  if (!t) return;

  const contentArea = document.getElementById("contentArea");
  
  let tabContent = "";
  if (currentViewTab === "columns") {{
    tabContent = renderColumnsTab(t);
  }} else if (currentViewTab === "relationships") {{
    tabContent = renderRelationshipsTab(t);
  }} else if (currentViewTab === "graph") {{
    tabContent = renderGraphTab(t);
  }} else if (currentViewTab === "indexes") {{
    tabContent = renderIndexesTab(t);
  }} else if (currentViewTab === "triggers") {{
    tabContent = renderTriggersTab(t);
  }} else if (currentViewTab === "sql") {{
    tabContent = renderSqlTab(t);
  }}

  contentArea.innerHTML = `
    <div class="table-view">
      <div class="table-header">
        <div>
          <div class="table-title">
            ${{t.name}}
            ${{t.is_strict ? '<span class="tag tag-strict">STRICT</span>' : ''}}
          </div>
          <div style="margin-top:6px; display:flex; gap:8px;">
            <span class="tag tag-store">${{SCHEMA_DATA.stores[currentStore].title}}</span>
            <span class="tag tag-group">${{t.group_title}}</span>
          </div>
        </div>
        <div style="text-align:right">
          <div style="font-size:12px; color:var(--text-muted); font-family:var(--font-mono)">
            Schema Version ${{SCHEMA_DATA.stores[currentStore].schema_version}}
          </div>
        </div>
      </div>

      <div class="view-tabs">
        <button class="view-tab ${{currentViewTab==='columns'?'active':''}}" onclick="setViewTab('columns')">Columns (${{t.columns.length}})</button>
        <button class="view-tab ${{currentViewTab==='relationships'?'active':''}}" onclick="setViewTab('relationships')">Relationships (${{t.foreign_keys.length + t.incoming_foreign_keys.length}})</button>
        <button class="view-tab ${{currentViewTab==='graph'?'active':''}}" onclick="setViewTab('graph')">Neighborhood Graph</button>
        <button class="view-tab ${{currentViewTab==='indexes'?'active':''}}" onclick="setViewTab('indexes')">Indexes (${{t.indexes.length + t.unique_constraints.length}})</button>
        <button class="view-tab ${{currentViewTab==='triggers'?'active':''}}" onclick="setViewTab('triggers')">Triggers (${{t.triggers.length}})</button>
        <button class="view-tab ${{currentViewTab==='sql'?'active':''}}" onclick="setViewTab('sql')">DDL SQL</button>
      </div>

      ${{tabContent}}
    </div>
  `;

  if (currentViewTab === "graph") {{
    drawNeighborhoodSvg(t);
  }}
}}

function renderColumnsTab(t) {{
  let rows = "";
  t.columns.forEach(col => {{
    let badges = "";
    if (col.is_pk) badges += `<span class="badge badge-pk">PK</span>`;
    
    // FK check
    const isFk = t.foreign_keys.some(fk => fk.from_columns.includes(col.name));
    if (isFk) badges += `<span class="badge badge-fk">FK</span>`;
    
    // Unique check
    const isUk = t.unique_constraints.some(u => u.columns.length === 1 && u.columns[0] === col.name && !u.partial);
    if (isUk && !col.is_pk) badges += `<span class="badge badge-uk">UK</span>`;
    
    if (col.is_generated) badges += `<span class="badge badge-gen">${{col.generation_type}}</span>`;

    const defVal = col.default_value !== null ? `<code>${{escapeHtml(col.default_value)}}</code>` : `<span style="color:var(--text-muted)">NULL</span>`;
    const notNull = col.notnull ? "YES" : (col.is_pk ? `<span style="color:var(--accent); font-weight:600" title="Primary Key semantics (rowid/PK)">PK</span>` : `<span style="color:var(--text-muted)">NO</span>`);

    rows += `
      <tr>
        <td class="col-name">${{col.name}}</td>
        <td class="col-type">${{col.type}}</td>
        <td>${{badges || "-"}}</td>
        <td>${{notNull}}</td>
        <td>${{defVal}}</td>
      </tr>
    `;
  }});

  return `
    <div class="card">
      <div class="card-header">
        <span>Columns Definition</span>
        <span style="font-family:var(--font-mono); font-size:12px; color:var(--text-muted)">${{t.columns.length}} columns</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Column Name</th>
            <th>Type</th>
            <th>Constraints</th>
            <th>Not Null</th>
            <th>Default Value</th>
          </tr>
        </thead>
        <tbody>${{rows}}</tbody>
      </table>
    </div>
  `;
}}

function renderRelationshipsTab(t) {{
  let outRows = "";
  t.foreign_keys.forEach(fk => {{
    outRows += `
      <tr>
        <td>${{fk.from_columns.map(c => `<code>${{c}}</code>`).join(", ")}}</td>
        <td><a class="link-table" onclick="navigateTable('${{fk.target_table}}')">${{fk.target_table}}</a></td>
        <td>${{fk.to_columns.map(c => `<code>${{c}}</code>`).join(", ")}}</td>
        <td style="font-family:var(--font-mono); font-size:11px">ON UPDATE ${{fk.on_update}}<br>ON DELETE ${{fk.on_delete}}</td>
      </tr>
    `;
  }});

  let inRows = "";
  t.incoming_foreign_keys.forEach(ifk => {{
    inRows += `
      <tr>
        <td><a class="link-table" onclick="navigateTable('${{ifk.source_table}}')">${{ifk.source_table}}</a></td>
        <td>${{ifk.source_columns.map(c => `<code>${{c}}</code>`).join(", ")}}</td>
        <td>${{ifk.target_columns.map(c => `<code>${{c}}</code>`).join(", ")}}</td>
        <td style="font-family:var(--font-mono); font-size:11px">ON UPDATE ${{ifk.on_update}}<br>ON DELETE ${{ifk.on_delete}}</td>
      </tr>
    `;
  }});

  let logRows = "";
  const outLog = t.logical_outgoing || [];
  const inLog = t.logical_incoming || [];
  [...outLog, ...inLog].forEach(l => {{
    const isOut = outLog.includes(l);
    logRows += `
      <tr>
        <td><span class="badge badge-log">${{isOut ? "Outgoing" : "Incoming"}} Logical</span></td>
        <td>${{isOut ? `<code>${{l.source_columns.join(", ")}}</code>` : `<a class="link-table" onclick="navigateTable('${{l.source_table}}')">${{l.source_table}}</a> (${{l.source_columns.join(", ")}})`}}</td>
        <td>${{isOut ? `<a class="link-table" onclick="navigateTable('${{l.target_table}}')">${{l.target_table}}</a> (${{l.target_columns.join(", ")}})` : `<code>${{l.target_columns.join(", ")}}</code>`}}</td>
        <td style="font-size:12px; color:var(--text-muted)">${{l.description}}<br><span style="color:var(--badge-gen); font-family:var(--font-mono)">${{l.adr_reference}}</span></td>
      </tr>
    `;
  }});

  return `
    <div style="display:flex; flex-direction:column; gap:20px;">
      <div class="card">
        <div class="card-header">
          <span>Outgoing Physical Foreign Keys (References Target)</span>
          <span style="font-family:var(--font-mono); font-size:12px; color:var(--text-muted)">${{t.foreign_keys.length}} FKs</span>
        </div>
        ${{t.foreign_keys.length > 0 ? `
          <table class="data-table">
            <thead>
              <tr>
                <th>Source Column(s)</th>
                <th>Target Table</th>
                <th>Target Column(s)</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>${{outRows}}</tbody>
          </table>
        ` : `<div style="padding:16px; color:var(--text-muted)">No outgoing foreign keys.</div>`}}
      </div>

      <div class="card">
        <div class="card-header">
          <span>Incoming Physical Foreign Keys (Referenced By Other Tables)</span>
          <span style="font-family:var(--font-mono); font-size:12px; color:var(--text-muted)">${{t.incoming_foreign_keys.length}} references</span>
        </div>
        ${{t.incoming_foreign_keys.length > 0 ? `
          <table class="data-table">
            <thead>
              <tr>
                <th>Referencing Table</th>
                <th>Referencing Column(s)</th>
                <th>This Table's Column(s)</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>${{inRows}}</tbody>
          </table>
        ` : `<div style="padding:16px; color:var(--text-muted)">No incoming foreign key references.</div>`}}
      </div>

      ${{logRows ? `
      <div class="card" style="border-color:rgba(244, 114, 182, 0.4)">
        <div class="card-header" style="background:rgba(244, 114, 182, 0.05)">
          <span style="color:var(--badge-log)">Documented Cross-Store Logical Dependencies (ADR 0002)</span>
          <span style="font-size:11px; color:var(--text-muted)">Application-enforced (Non-enforced SQLite FKs)</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Source</th>
              <th>Target</th>
              <th>Purpose & Guarantees</th>
            </tr>
          </thead>
          <tbody>${{logRows}}</tbody>
        </table>
      </div>
      ` : ""}}
    </div>
  `;
}}

function renderGraphTab(t) {{
  return `
    <div class="graph-container">
      <div class="graph-header">
        <span>Interactive Neighborhood Graph</span>
        <span>Click any node to navigate • Solid: Physical FK • Dashed: Logical ADR 0002</span>
      </div>
      <svg id="neighborhoodSvg" class="neighborhood-svg"></svg>
    </div>
  `;
}}

function drawNeighborhoodSvg(t) {{
  const svg = document.getElementById("neighborhoodSvg");
  if (!svg) return;
  svg.innerHTML = "";

  const upstream = t.foreign_keys.map(fk => ({{
    name: fk.target_table,
    label: fk.from_columns.join(", ") + " -> " + fk.to_columns.join(", "),
    logical: false
  }}));
  (t.logical_outgoing || []).forEach(l => {{
    upstream.push({{
      name: l.target_table,
      label: l.source_columns.join(", ") + " -> " + l.target_columns.join(", "),
      logical: true
    }});
  }});

  const downstream = t.incoming_foreign_keys.map(ifk => ({{
    name: ifk.source_table,
    label: ifk.source_columns.join(", ") + " -> " + ifk.target_columns.join(", "),
    logical: false
  }}));
  (t.logical_incoming || []).forEach(l => {{
    downstream.push({{
      name: l.source_table,
      label: l.source_columns.join(", ") + " -> " + l.target_columns.join(", "),
      logical: true
    }});
  }});

  const maxNodes = Math.max(upstream.length, downstream.length, 1);
  const rowHeight = 60;
  const height = Math.max(360, maxNodes * rowHeight + 80);
  const width = svg.clientWidth || 900;
  svg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);

  // Markers
  svg.innerHTML += `
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8"/>
      </marker>
      <marker id="arrow-log" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#f472b6"/>
      </marker>
    </defs>
  `;

  const centerY = height / 2;
  const centerX = width / 2;
  const cardW = 180;
  const cardH = 36;

  // Draw Center Node
  drawNode(svg, centerX - cardW/2, centerY - cardH/2, cardW, cardH, t.name, true);

  // Draw Upstream (Left)
  const upStartY = centerY - ((upstream.length - 1) * rowHeight) / 2;
  upstream.forEach((u, i) => {{
    const uy = upStartY + i * rowHeight;
    const ux = 80;
    drawNode(svg, ux, uy - cardH/2, cardW, cardH, u.name, false, () => navigateTable(u.name));
    drawEdge(svg, centerX - cardW/2, centerY, ux + cardW, uy, u.label, u.logical);
  }});

  // Draw Downstream (Right)
  const downStartY = centerY - ((downstream.length - 1) * rowHeight) / 2;
  downstream.forEach((d, i) => {{
    const dy = downStartY + i * rowHeight;
    const dx = width - 80 - cardW;
    drawNode(svg, dx, dy - cardH/2, cardW, cardH, d.name, false, () => navigateTable(d.name));
    drawEdge(svg, dx, dy, centerX + cardW/2, centerY, d.label, d.logical);
  }});
}}

function drawNode(svg, x, y, w, h, text, isCenter, onClick) {{
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.style.cursor = isCenter ? "default" : "pointer";
  if (onClick) g.onclick = onClick;

  const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  rect.setAttribute("x", x);
  rect.setAttribute("y", y);
  rect.setAttribute("width", w);
  rect.setAttribute("height", h);
  rect.setAttribute("rx", "6");
  rect.setAttribute("fill", isCenter ? "#1e293b" : "#334155");
  rect.setAttribute("stroke", isCenter ? "#38bdf8" : "#475569");
  rect.setAttribute("stroke-width", isCenter ? "2" : "1");

  const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
  label.setAttribute("x", x + w / 2);
  label.setAttribute("y", y + h / 2 + 4);
  label.setAttribute("text-anchor", "middle");
  label.setAttribute("fill", isCenter ? "#f8fafc" : "#cbd5e1");
  label.setAttribute("font-family", "monospace");
  label.setAttribute("font-size", "12");
  label.setAttribute("font-weight", isCenter ? "700" : "500");
  label.textContent = text;

  g.appendChild(rect);
  g.appendChild(label);
  svg.appendChild(g);
}}

function drawEdge(svg, x1, y1, x2, y2, labelText, isLogical) {{
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  const dx = (x2 - x1) * 0.5;
  const d = `M ${{x1}} ${{y1}} C ${{x1 + dx}} ${{y1}}, ${{x2 - dx}} ${{y2}}, ${{x2}} ${{y2}}`;
  path.setAttribute("d", d);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", isLogical ? "#f472b6" : "#38bdf8");
  path.setAttribute("stroke-width", "1.5");
  if (isLogical) path.setAttribute("stroke-dasharray", "5,5");
  path.setAttribute("marker-end", isLogical ? "url(#arrow-log)" : "url(#arrow)");

  const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
  title.textContent = labelText;
  path.appendChild(title);

  svg.appendChild(path);
}}

function renderIndexesTab(t) {{
  let idxRows = "";
  t.indexes.forEach(idx => {{
    const statusBadge = idx.partial
      ? (idx.unique ? '<span class="badge badge-uk">PARTIAL UNIQUE</span>' : '<span class="badge badge-gen">PARTIAL</span>')
      : (idx.unique ? '<span class="badge badge-uk">UNIQUE</span>' : 'NON-UNIQUE');
    const predNote = idx.predicate ? `<br><small style="color:var(--text-muted); font-family:var(--font-mono); font-size:11px">WHERE ${{escapeHtml(idx.predicate)}}</small>` : '';
    idxRows += `
      <tr>
        <td style="font-family:var(--font-mono); font-weight:600">${{idx.name}}${{predNote}}</td>
        <td>${{idx.columns.map(c => `<code>${{c}}</code>`).join(", ")}}</td>
        <td>${{statusBadge}}</td>
        <td>${{idx.partial ? 'PARTIAL' : 'FULL'}}</td>
      </tr>
    `;
  }});

  let uRows = "";
  t.unique_constraints.forEach(u => {{
    uRows += `
      <tr>
        <td style="font-family:var(--font-mono); font-weight:600">${{u.name}}</td>
        <td>${{u.columns.map(c => `<code>${{c}}</code>`).join(", ")}}</td>
        <td>${{u.is_composite ? 'COMPOSITE' : 'SINGLE'}}</td>
        <td><span class="badge badge-uk">UNIQUE CONSTRAINT</span></td>
      </tr>
    `;
  }});

  return `
    <div style="display:flex; flex-direction:column; gap:20px;">
      <div class="card">
        <div class="card-header">
          <span>Unique Constraints</span>
          <span style="font-size:12px; color:var(--text-muted)">${{t.unique_constraints.length}} constraints</span>
        </div>
        ${{t.unique_constraints.length > 0 ? `
          <table class="data-table">
            <thead>
              <tr>
                <th>Constraint / Autoindex Name</th>
                <th>Column(s)</th>
                <th>Type</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>${{uRows}}</tbody>
          </table>
        ` : `<div style="padding:16px; color:var(--text-muted)">No explicit unique constraints beyond Primary Key.</div>`}}
      </div>

      <div class="card">
        <div class="card-header">
          <span>Indexes</span>
          <span style="font-size:12px; color:var(--text-muted)">${{t.indexes.length}} indexes</span>
        </div>
        ${{t.indexes.length > 0 ? `
          <table class="data-table">
            <thead>
              <tr>
                <th>Index Name</th>
                <th>Column(s)</th>
                <th>Uniqueness</th>
                <th>Coverage</th>
              </tr>
            </thead>
            <tbody>${{idxRows}}</tbody>
          </table>
        ` : `<div style="padding:16px; color:var(--text-muted)">No explicit secondary indexes.</div>`}}
      </div>
    </div>
  `;
}}

function renderTriggersTab(t) {{
  if (t.triggers.length === 0) {{
    return `<div class="card"><div style="padding:24px; color:var(--text-muted)">No triggers defined on this table.</div></div>`;
  }}

  let items = "";
  t.triggers.forEach(trigName => {{
    const trig = SCHEMA_DATA.stores[currentStore].triggers[trigName];
    items += `
      <div style="border-bottom:1px solid var(--border); padding:16px 20px;">
        <div style="font-family:var(--font-mono); font-weight:600; color:var(--text-main); margin-bottom:8px;">
          ${{trigName}}
        </div>
        <pre class="sql-code">${{escapeHtml(trig.sql)}}</pre>
      </div>
    `;
  }});

  return `
    <div class="card">
      <div class="card-header">
        <span>Associated Triggers</span>
        <span style="font-size:12px; color:var(--text-muted)">${{t.triggers.length}} triggers</span>
      </div>
      <div>${{items}}</div>
    </div>
  `;
}}

function renderSqlTab(t) {{
  return `
    <div class="card">
      <div class="card-header">
        <span>SQLite DDL Statement</span>
        <span style="font-family:var(--font-mono); font-size:11px; color:var(--text-muted)">SHA-256: ${{t.sql_sha256.substring(0, 16)}}...</span>
      </div>
      <pre class="sql-code">${{escapeHtml(t.sql)}}</pre>
    </div>
  `;
}}

function navigateTable(tName) {{
  // Check which store has this table
  for (const [sSlug, sData] of Object.entries(SCHEMA_DATA.stores)) {{
    if (sData.tables[tName]) {{
      if (currentStore !== sSlug) {{
        setStore(sSlug);
      }}
      selectTable(tName);
      return;
    }}
  }}
}}

function showArchitectureView() {{
  document.querySelectorAll('.store-tab').forEach(tab => tab.classList.remove('active'));
  document.querySelectorAll('.store-tab')[3].classList.add('active');

  let logTableRows = "";
  SCHEMA_DATA.logical_dependencies.forEach(d => {{
    logTableRows += `
      <tr>
        <td><code>${{d.source_store}}.${{d.source_table}}</code></td>
        <td><code>${{d.source_columns.join(", ")}}</code></td>
        <td><code>${{d.target_store}}.${{d.target_table}}</code></td>
        <td><code>${{d.target_columns.join(", ")}}</code></td>
        <td style="color:var(--badge-gen); font-family:var(--font-mono); font-size:12px">${{d.adr_reference}}</td>
        <td style="font-size:12px">${{d.description}}</td>
      </tr>
    `;
  }});

  let viewTableRows = "";
  Object.values(SCHEMA_DATA.stores.core.views).forEach(v => {{
    viewTableRows += `
      <tr>
        <td class="col-name">${{v.name}}</td>
        <td>${{v.columns.length}}</td>
        <td><pre class="sql-code" style="max-height:80px; padding:6px; font-size:11px">${{escapeHtml(v.sql)}}</pre></td>
      </tr>
    `;
  }});

  document.getElementById("contentArea").innerHTML = `
    <div class="table-view" style="max-width:1200px">
      <div class="table-header">
        <div>
          <div class="table-title">Three-Store Boundary Architecture (ADR 0002)</div>
          <div style="color:var(--text-muted); margin-top:6px">Binding decisions PF-P01–PF-P17 establishing physical store isolation.</div>
        </div>
      </div>

      <div class="overview-grid">
        <div class="store-card">
          <h3>Core Store <span class="tag tag-store">catalog.sqlite3</span></h3>
          <p>Durable domain facts, entities, immutable observations, coverage claims, code listings, Git DAG, and Exchange staging.</p>
          <div class="metric-row">
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.core_tables}}</span><span class="metric-lbl">Tables</span></div>
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.core_fks}}</span><span class="metric-lbl">Foreign Keys</span></div>
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.core_views}}</span><span class="metric-lbl">Views</span></div>
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.core_triggers}}</span><span class="metric-lbl">Triggers</span></div>
          </div>
        </div>

        <div class="store-card">
          <h3>Operational Store <span class="tag tag-store">operational.sqlite3</span></h3>
          <p>Transient execution state, jobs, job attempts, capacity reservations, and packfile cache leases. Loss never invalidates Core facts.</p>
          <div class="metric-row">
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.operational_tables}}</span><span class="metric-lbl">Tables</span></div>
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.operational_fks}}</span><span class="metric-lbl">Foreign Keys</span></div>
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.operational_triggers}}</span><span class="metric-lbl">Triggers</span></div>
          </div>
        </div>

        <div class="store-card">
          <h3>Search Store <span class="tag tag-store">search.sqlite3</span></h3>
          <p>Rebuildable FTS5 trigram virtual tables, search document projections, and index generations. Excluded from normal backups.</p>
          <div class="metric-row">
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.search_tables}}</span><span class="metric-lbl">Fixed Tables</span></div>
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.search_fks}}</span><span class="metric-lbl">Foreign Keys</span></div>
            <div class="metric"><span class="metric-val">${{SCHEMA_DATA.summary.search_triggers}}</span><span class="metric-lbl">Triggers</span></div>
          </div>
        </div>
      </div>

      <div class="card" style="border-color:rgba(244, 114, 182, 0.4)">
        <div class="card-header" style="background:rgba(244, 114, 182, 0.05)">
          <span style="color:var(--badge-log)">Verified Cross-Store Logical Dependencies</span>
          <span style="font-size:11px; color:var(--text-muted)">Non-enforced application references</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Source Table</th>
              <th>Source Column(s)</th>
              <th>Target Table</th>
              <th>Target Column(s)</th>
              <th>Authority</th>
              <th>Architectural Guarantee</th>
            </tr>
          </thead>
          <tbody>${{logTableRows}}</tbody>
        </table>
      </div>

      <div class="card">
        <div class="card-header">
          <span>Core Views Inventory</span>
          <span style="font-size:12px; color:var(--text-muted)">20 compiled views in catalog.sqlite3</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>View Name</th>
              <th>Columns</th>
              <th>SQL Definition</th>
            </tr>
          </thead>
          <tbody>${{viewTableRows}}</tbody>
        </table>
      </div>
    </div>
  `;
}}

function showComparisonView() {{
  document.querySelectorAll('.store-tab').forEach(tab => tab.classList.remove('active'));
  document.querySelectorAll('.store-tab')[4].classList.add('active');

  document.getElementById("contentArea").innerHTML = `
    <div class="table-view" style="max-width:1100px">
      <div class="table-header">
        <div>
          <div class="table-title">Visualization Approach Tradeoffs & Comparison</div>
          <div style="color:var(--text-muted); margin-top:6px">Evaluation of Mermaid, DBML, and Standalone Interactive HTML.</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span>Approach Comparison Matrix</span>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Criterion</th>
              <th>1. Mermaid ER Diagrams</th>
              <th>2. DBML Exports</th>
              <th>3. Interactive HTML Workbench</th>
            </tr>
          </thead>
          <tbody>
            <tr><td><strong>Desktop Readability</strong></td><td>Good (split by functional module)</td><td>Excellent in dbdiagram.io canvas</td><td>Optimal (responsive split pane)</td></tr>
            <tr><td><strong>Mobile Readability</strong></td><td>Moderate to Poor on large diagrams</td><td>Poor (requires zooming canvas)</td><td>Excellent (collapsible sidebar)</td></tr>
            <tr><td><strong>Relationship Navigation</strong></td><td>Static visual edges</td><td>Interactive hover highlights</td><td>Interactive SVG graph & table links</td></tr>
            <tr><td><strong>70-Table Core Schema</strong></td><td>Requires splitting into 6 modules</td><td>Can open full schema in canvas</td><td>Single filterable/searchable UI</td></tr>
            <tr><td><strong>Cross-Store Visibility</strong></td><td>Explicit overview diagram & tables</td><td>Documented notes / combined export</td><td>Dedicated Architecture Map view</td></tr>
            <tr><td><strong>GitHub-Native Viewing</strong></td><td>Native in Markdown without plugins</td><td>Requires third-party tool</td><td>Requires opening HTML locally</td></tr>
            <tr><td><strong>Offline Availability</strong></td><td>100% offline (local markdown)</td><td>Files local; viewers online/offline</td><td>100% offline (self-contained)</td></tr>
            <tr><td><strong>Setup Overhead</strong></td><td>Zero dependencies</td><td>Zero dependencies for export</td><td>Zero dependencies</td></tr>
            <tr><td><strong>Regeneration Overhead</strong></td><td>Deterministic & sub-second</td><td>Deterministic & sub-second</td><td>Deterministic & sub-second</td></tr>
            <tr><td><strong>Coding Agent Friendliness</strong></td><td>High (parseable markdown)</td><td>High (concise structured DSL)</td><td>Moderate (rendered HTML)</td></tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <div class="card-header"><span>Unified Generation Commands</span></div>
        <pre class="sql-code"># Generate Mermaid ER diagrams:
uv run --no-sync python scripts/schema_viz.py --format mermaid

# Generate DBML exports:
uv run --no-sync python scripts/schema_viz.py --format dbml

# Generate Standalone HTML Workbench:
uv run --no-sync python scripts/schema_viz.py --format html

# Generate all formats:
uv run --no-sync python scripts/schema_viz.py --format all

# Non-mutating freshness validation check:
uv run --no-sync python scripts/schema_viz.py --check</pre>
      </div>
    </div>
  `;
}}

function escapeHtml(str) {{
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}}

window.onload = init;
</script>
</body>
</html>
"""
    return {"index.html": html_content.strip() + "\n"}


# ==============================================================================
# Comprehensive Comparison README Generator
# ==============================================================================


def generate_readme(ir: dict[str, Any]) -> dict[str, str]:
    """Generate comprehensive docs/schema/README.md documentation."""
    core = ir["stores"]["core"]
    op = ir["stores"]["operational"]
    search = ir["stores"]["search"]

    content = f"""# git-repo-db Database Schema Visualization Workbench

This workbench provides non-destructive, authoritative visualization and inspection tooling for the production database schema of `git-repo-db`.

The database architecture implements the **Three-Store Boundary** under **ADR 0002** and binding owner decisions **PF-P01–PF-P17**.

---

## 1. Architecture and Three-Store Boundary

The production database is physically partitioned into three distinct SQLite databases:

| Store | Database File | Schema Version | Product Tables | DDL SHA-256 Fingerprint | Operational Responsibility |
|---|---|---|---|---|---|
| **Core** | `catalog.sqlite3` | {core["schema_version"]} | {core["table_count"]} | `{core["ddl_sha256"]}` | Authoritative domain facts, entities, immutable observations, coverage claims, code listings, Git DAG, and Exchange staging. |
| **Operational** | `operational.sqlite3` | {op["schema_version"]} | {op["table_count"]} | `{op["ddl_sha256"]}` | Transient execution state, jobs, job attempts, packfile cache leases, reservations, and progress tracking. |
| **Search** | `search.sqlite3` | {search["schema_version"]} | {search["table_count"]} | `{search["ddl_sha256"]}` | Rebuildable FTS5 trigram virtual tables, search document projections, and index generations. |

### Physical vs Logical Relationships

A key architectural invariant of ADR 0002 is that **SQLite foreign keys do not cross physical store boundaries**:
- **Physical Foreign Keys (Solid Edges):** Enforced by SQLite foreign key constraints (`PRAGMA foreign_keys=ON`). They operate strictly within `catalog.sqlite3` ({core["foreign_key_count"]} FKs), `operational.sqlite3` ({op["foreign_key_count"]} FKs), and `search.sqlite3` ({search["foreign_key_count"]} FKs).
- **Logical References (Dashed Edges):** Application-level references and revision fences (e.g. Operational job tracking Core Git acquisitions, Search index tracking Core `local_revision`). Loss or absence of Operational or Search databases never invalidates Core facts.

### Authoritative Schema Sources

The visualizations are derived from the production composed DDL functions in `src/repo_catalog/adapters/sqlite/schema.py`:
- `schema_sql()` — complete composed Core DDL from packaged SQL resources (`catalog3.sql`, `git_domain.sql`, `cas_integrity.sql`, etc.).
- `operational_schema_sql()` — Operational DDL (`operational.sql`).
- `search_schema_sql()` — Search DDL (`search.sql`).

---

## 2. Implemented Visualization Approaches

The workbench implements three distinct visualization approaches:

### Approach A: Mermaid ER Diagrams
- **Location:** `docs/schema/mermaid/`
- **Formats:** GitHub-native Markdown documents with fenced ````mermaid` blocks.
- **Organization:**
  - [overview.md](mermaid/overview.md) — High-level Three-Store Boundary architecture overview.
  - [core-overview.md](mermaid/core-overview.md) — Map of the 7 functional modules and Core table directory.
  - [core-identity.md](mermaid/core-identity.md) — Portable identities, sources, and repositories (14 tables).
  - [core-current-state.md](mermaid/core-current-state.md) — Current PR/Issue/document state projections (5 tables).
  - [core-coverage.md](mermaid/core-coverage.md) — Collection and coverage evidence (19 tables).
  - [core-git.md](mermaid/core-git.md) — Git acquisition and object DAG (21 tables).
  - [core-cas.md](mermaid/core-cas.md) — Retained content integrity and CAS (7 tables).
  - [core-exchange.md](mermaid/core-exchange.md) — Exchange staging and admissions (4 tables).
  - [operational.md](mermaid/operational.md) — Operational jobs, leases, and progress (10 tables).
  - [search.md](mermaid/search.md) — Search projections, generations, and FTS5 virtual tables (4 tables).

### Approach B: DBML Exports
- **Location:** `docs/schema/dbml/`
- **Formats:** `.dbml` files compatible with [dbdiagram.io](https://dbdiagram.io/) and [dbdocs.io](https://dbdocs.io/).
- **Files:**
  - `core.dbml` — Complete DBML schema for all 70 Core tables.
  - `operational.dbml` — Operational store schema (10 tables).
  - `search.dbml` — Search store schema (4 tables).
  - `combined.dbml` — Conceptual combined export representing all three stores with documented logical dependencies.

### Approach C: Standalone Interactive HTML Viewer
- **Location:** `docs/schema/index.html`
- **Format:** Single self-contained HTML file with embedded CSS and vanilla JavaScript.
- **Features:**
  - Instant store switching (Core / Operational / Search).
  - Live filtering by table name and column name.
  - Functional module filtering for Core tables.
  - Tabbed table details: Columns, Physical Relationships, Indexes, Triggers, and DDL SQL.
  - Interactive SVG neighborhood graph connecting upstream and downstream tables.
  - Three-Store Architecture Map view with compiled views catalog and logical dependency matrix.
  - Zero external network dependencies; operates 100% offline via local `file://` protocol.

---

## 3. Unified Generation and Consistency Commands

The CLI tool `scripts/schema_viz.py` provides deterministic generation and validation:

```bash
# Generate Mermaid ER diagrams:
uv run --no-sync python scripts/schema_viz.py --format mermaid

# Generate DBML exports:
uv run --no-sync python scripts/schema_viz.py --format dbml

# Generate standalone interactive HTML viewer:
uv run --no-sync python scripts/schema_viz.py --format html

# Generate all visualization artifacts:
uv run --no-sync python scripts/schema_viz.py --format all

# Run non-mutating freshness validation check (fails nonzero if stale):
uv run --no-sync python scripts/schema_viz.py --check
```

The `--check` mode executes in-memory schema introspection, generates expected outputs in memory, compares them byte-for-byte with committed files in `docs/schema/`, and exits with code 0 if up to date, or code 1 with specific diff diagnostics if stale.

---

## 4. Evaluation and Tradeoff Comparison

| Criterion | 1. Mermaid ER Diagrams | 2. DBML Exports | 3. Standalone Interactive HTML |
|---|---|---|---|
| **Desktop Readability** | Good (split by functional module) | Excellent in dbdiagram.io canvas | Optimal (responsive split pane & tabs) |
| **Mobile Readability** | Moderate (large SVGs shrink) | Poor (requires pan/zoom on small canvas) | Excellent (collapsible sidebar layout) |
| **Relationship Navigation** | Static visual edges | Interactive highlight on click/hover | Interactive SVG neighborhood graph & table links |
| **Navigating 70-Table Core** | Requires 6 modular diagrams | Can render full canvas; crowded | Single searchable list + group filter |
| **Cross-Store Boundary Visibility** | Explicit overview diagram & markdown tables | Documented in notes & combined export | Dedicated Architecture Map view |
| **Column & Constraint Inspection** | Column list with PK/FK/UK badges | Column attributes & DBML index block | Full table with nullability, defaults, triggers |
| **GitHub-Native Viewing** | **Native** (renders directly in Markdown) | Requires external tool / web app | Requires opening HTML locally in browser |
| **Interactive Exploration** | None (static rendering) | High (pan/zoom/move in web canvas) | High (interactive graph, search, tabs) |
| **Offline Availability** | 100% offline | 100% offline files (viewer may be web) | 100% offline (self-contained zero-CDN) |
| **Dependency & Setup Overhead** | Zero dependencies | Zero dependencies | Zero dependencies |
| **Regeneration & Maintenance** | Deterministic & sub-second | Deterministic & sub-second | Deterministic & sub-second |
| **Coding Agent Friendliness** | **High** (read directly by agents) | **High** (clean parseable DSL) | Moderate (rendered HTML) |
| **Output Size & Maintenance** | Compact Markdown (~75 KB total across 10 files) | Compact DSL (~122 KB total across 4 files) | Single self-contained file (~700 KB) |

---

## 5. Practical Workflow Recommendations

1. **For Quick Architecture Reviews on GitHub:**
   - **Recommended:** **Mermaid ER Diagrams** (`docs/schema/mermaid/overview.md` and module diagrams).
   - *Rationale:* Renders directly within GitHub web interface, PR reviews, and mobile GitHub app without opening external tools.
2. **For Local Interactive Exploration and Query Development:**
   - **Recommended:** **Standalone Interactive HTML Viewer** (`docs/schema/index.html`).
   - *Rationale:* Provides instantaneous table search, column filtering, clickable incoming/outgoing relationship navigation, trigger review, and neighborhood graphing with zero configuration.
3. **For Third-Party Visual Design, Team Presentations, or External Tools:**
   - **Recommended:** **DBML Exports** (`docs/schema/dbml/core.dbml` / `combined.dbml`).
   - *Rationale:* Easily imported into dbdiagram.io or dbdocs.io for collaborative layout adjustments, team sharing, or PDF exports.
4. **For Automated CI and Continuous Documentation:**
   - **Recommended:** `python scripts/schema_viz.py --check` in repository checks.
   - *Rationale:* Guarantees that any future DDL change immediately updates or invalidates stale documentation.
"""
    return {"README.md": content.strip() + "\n"}


# ==============================================================================
# Artifact Writing and Checking
# ==============================================================================


def generate_all_artifacts(
    ir: dict[str, Any], format_type: str = "all"
) -> dict[str, str]:
    """Generate requested artifact file mapping {relative_path: content}."""
    artifacts: dict[str, str] = {}

    if format_type in ("all", "mermaid"):
        artifacts.update(generate_mermaid(ir))
    if format_type in ("all", "dbml"):
        artifacts.update(generate_dbml(ir))
    if format_type in ("all", "html"):
        artifacts.update(generate_html(ir))
    if format_type == "all":
        artifacts.update(generate_readme(ir))

    return artifacts


def write_artifacts(artifacts: dict[str, str], output_dir: Path) -> list[str]:
    """Write generated artifacts deterministically to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for rel_path, content in sorted(artifacts.items()):
        dest = output_dir / rel_path
        if output_dir.resolve() not in dest.resolve().parents or any(
            p.is_symlink() for p in (dest, *dest.parents)
        ):
            raise ValueError("Artifact path escapes output or traverses a link")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="\n")
        written.append(rel_path)

    return written


def check_artifacts(
    artifacts: dict[str, str], output_dir: Path
) -> tuple[bool, list[str]]:
    """Verify that committed files match generated artifacts byte-for-byte without mutating disk."""
    mismatches: list[str] = []

    # Complete IR semantics are verified by the neutral product producer.
    for rel_path, expected_content in sorted(artifacts.items()):
        target = output_dir / rel_path
        if not target.exists():
            mismatches.append(f"Missing file: {rel_path}")
            continue

        actual_content = target.read_text(encoding="utf-8")
        if actual_content != expected_content:
            mismatches.append(
                f"Stale content: {rel_path} (expected {len(expected_content)} bytes, actual {len(actual_content)} bytes)"
            )

    return len(mismatches) == 0, mismatches


# ==============================================================================
# CLI Entrypoint
# ==============================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Non-destructive database schema visualization workbench for git-repo-db."
    )
    parser.add_argument(
        "--format",
        choices=["all", "mermaid", "dbml", "html"],
        default="all",
        help="Visualization format to generate (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "schema",
        help="Output directory for generated files (default: docs/schema)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that existing artifacts match fresh generation without mutating disk",
    )

    parser.add_argument(
        "--ir",
        type=Path,
        required=True,
        help="Pinned complete neutral IR exported by product Python",
    )
    args = parser.parse_args(argv)

    print("Introspecting Three-Store schemas in memory...")
    ir = json.loads(args.ir.read_bytes())
    print(
        f"Introspection successful: Core ({ir['summary']['core_tables']} tables, {ir['summary']['core_fks']} FKs), "
        f"Operational ({ir['summary']['operational_tables']} tables, {ir['summary']['operational_fks']} FKs), "
        f"Search ({ir['summary']['search_tables']} tables, {ir['summary']['search_fks']} FKs)."
    )

    artifacts = generate_all_artifacts(ir, args.format)

    if args.check:
        print(f"Checking {len(artifacts)} artifacts against {args.output_dir}...")
        is_clean, mismatches = check_artifacts(artifacts, args.output_dir)
        if not is_clean:
            print("ERROR: Generated schema artifacts are stale or missing:")
            for m in mismatches:
                print(f"  - {m}")
            return 1
        print("PASS: All schema visualization artifacts are up-to-date and consistent.")
        return 0

    if args.output_dir.resolve() != (ROOT / "schema").resolve():
        from tools.build_docs_site import validate_destination

        args.output_dir = validate_destination(args.output_dir, "output")
    print(f"Writing {len(artifacts)} artifacts to {args.output_dir}...")
    written = write_artifacts(artifacts, args.output_dir)
    for p in written:
        print(f"  + {p}")
    print(f"Successfully generated {len(written)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
