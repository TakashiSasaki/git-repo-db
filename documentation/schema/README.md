# git-repo-db Database Schema Visualization Workbench

This workbench provides non-destructive, authoritative visualization and inspection tooling for the production database schema of `git-repo-db`.

The database architecture implements the **Three-Store Boundary** under **ADR 0002** and binding owner decisions **PF-P01–PF-P17**.

---

## 1. Architecture and Three-Store Boundary

The production database is physically partitioned into three distinct SQLite databases:

| Store | Database File | Schema Version | Product Tables | DDL SHA-256 Fingerprint | Operational Responsibility |
|---|---|---|---|---|---|
| **Core** | `catalog.sqlite3` | 21 | 70 | `8ee2631fe083e26cd0346bc71a8a5d1f4d7dab4bf661958d6406c885bc553ff0` | Authoritative domain facts, entities, immutable observations, coverage claims, code listings, Git DAG, and Exchange staging. |
| **Operational** | `operational.sqlite3` | 1 | 10 | `dafdc014ebf3e54e1695ffb0bb3fd953f1a1c893d5b0b13d812740ee2f288def` | Transient execution state, jobs, job attempts, packfile cache leases, reservations, and progress tracking. |
| **Search** | `search.sqlite3` | 1 | 4 | `1fff79854824aae850184fd4af16a29ee8574769e42a139283b01825520a84b7` | Rebuildable FTS5 trigram virtual tables, search document projections, and index generations. |

### Physical vs Logical Relationships

A key architectural invariant of ADR 0002 is that **SQLite foreign keys do not cross physical store boundaries**:
- **Physical Foreign Keys (Solid Edges):** Enforced by SQLite foreign key constraints (`PRAGMA foreign_keys=ON`). They operate strictly within `catalog.sqlite3` (121 FKs), `operational.sqlite3` (9 FKs), and `search.sqlite3` (2 FKs).
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
- **Location:** `documentation/schema/mermaid/`
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
- **Location:** `documentation/schema/dbml/`
- **Formats:** `.dbml` files compatible with [dbdiagram.io](https://dbdiagram.io/) and [dbdocs.io](https://dbdocs.io/).
- **Files:**
  - `core.dbml` — Complete DBML schema for all 70 Core tables.
  - `operational.dbml` — Operational store schema (10 tables).
  - `search.dbml` — Search store schema (4 tables).
  - `combined.dbml` — Conceptual combined export representing all three stores with documented logical dependencies.

### Approach C: Standalone Interactive HTML Viewer
- **Location:** `documentation/schema/index.html`
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

The CLI tool `documentation/tools/schema_viz.py` provides deterministic generation and validation:

```bash
# Select a full product commit SHA; producer checkout must match it:
FULL_PRODUCT_SHA="FULL_PRODUCT_COMMIT_SHA"
scripts/local-run.sh python scripts/schema_inventory.py --source "$FULL_PRODUCT_SHA" --output documentation/.build/inputs

# Generate all formats (or use mermaid, dbml, or html):
uv run --project documentation --no-sync python documentation/tools/schema_viz.py --ir documentation/.build/inputs/inventory.json --format all

# Check committed visualization files without writing:
uv run --project documentation --no-sync python documentation/tools/schema_viz.py --ir documentation/.build/inputs/inventory.json --check
```

The product producer inspects the selected committed checkout and writes a pinned neutral IR and producer evidence. The renderer reads that IR; `--check` generates expected outputs in memory and compares them byte-for-byte with `documentation/schema/`. It exits nonzero on a mismatch. The renderer does not independently verify producer provenance.

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
   - **Recommended:** **Mermaid ER Diagrams** (`documentation/schema/mermaid/overview.md` and module diagrams).
   - *Rationale:* Renders directly within GitHub web interface, PR reviews, and mobile GitHub app without opening external tools.
2. **For Local Interactive Exploration and Query Development:**
   - **Recommended:** **Standalone Interactive HTML Viewer** (`documentation/schema/index.html`).
   - *Rationale:* Provides instantaneous table search, column filtering, clickable incoming/outgoing relationship navigation, trigger review, and neighborhood graphing with zero configuration.
3. **For Third-Party Visual Design, Team Presentations, or External Tools:**
   - **Recommended:** **DBML Exports** (`documentation/schema/dbml/core.dbml` / `combined.dbml`).
   - *Rationale:* Easily imported into dbdiagram.io or dbdocs.io for collaborative layout adjustments, team sharing, or PDF exports.
4. **For Automated CI and Continuous Documentation:**
   - **Recommended:** `uv run --project documentation --no-sync python documentation/tools/schema_viz.py --ir documentation/.build/inputs/inventory.json --check` in repository checks.
   - *Rationale:* Guarantees that any future DDL change immediately updates or invalidates stale documentation.
