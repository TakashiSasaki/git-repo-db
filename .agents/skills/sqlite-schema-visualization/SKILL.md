---
name: sqlite-schema-visualization
description: Introspect, validate, and generate non-destructive database visualizations (Mermaid ER diagrams, DBML exports, and standalone HTML workbenches) for the implemented multi-store SQLite schema, while distinguishing accepted four-store target contracts. Use when extracting composite foreign keys, filtering FTS shadow tables, handling generated columns, or validating schema documentation freshness.
---

# SQLite Schema Introspection and Visualization Invariants

Read the [ADR index](../../../docs/adr/README.md) before interpreting ownership.
The production visualization commands below introspect the implemented Schema 21
Core / Operational 1 / Search 1 baseline. ADR 0003's independent Context and the
later metadata/notes/key/recovery decisions are accepted targets, not already
implemented merely because a diagram can be generated. Legacy table names and
IDs below are introspection examples, not approved target DDL. In particular,
ADR 0017 requires semantic PKs/FKs; a visualization must expose storage-only
surrogates and cross-domain tables rather than silently validating them. Target
Core is INSERT-only; no diagram implies mutable verified/revision/quarantine
states or ordinary file-body archival is permitted.

When inspecting and generating schema documentation for multi-store SQLite databases (such as `git-repo-db`'s Core, Operational, and Search stores under ADR 0002), follow these verified procedures to avoid silent misclassification, broken diagrams, or nondeterministic diffs.

---

## 1. Composite Foreign Key Extraction

### Symptom
Naive introspection treats every row in `PRAGMA foreign_key_list(table)` as an independent foreign key constraint. For composite keys like `acquisition_roots(git_acquisition_id, repository_uuidv4) REFERENCES git_acquisitions(...)`, this produces two separate single-column foreign key edges in diagrams, misrepresenting the database constraint and generating invalid DBML/Mermaid syntax.

### Rule & Invariant
- Rows returned by `PRAGMA foreign_key_list(table)` share a constraint ID in column 0 (`id`).
- All rows sharing the same `id` constitute a single composite foreign key.
- Sort column pairs within each constraint by sequence rank column 1 (`seq`).

### Remediation Pattern
```python
fk_rows = db.execute(f'PRAGMA foreign_key_list("{table_name}")').fetchall()
fk_groups = {}
for row in fk_rows:
    # row: (id, seq, table, from, to, on_update, on_delete, match)
    fk_groups.setdefault(row[0], []).append(row)

for fk_id, rows in sorted(fk_groups.items()):
    ordered = sorted(rows, key=lambda r: r[1])
    target_table = ordered[0][2]
    from_cols = [r[3] for r in ordered]
    to_cols = [r[4] for r in ordered]
```

---

## 2. Product Table vs. Virtual / Shadow Table Distinction

### Symptom
SQLite FTS5 virtual tables (e.g. `catalog_fts_<generation_id>`) create internal shadow tables: `_data`, `_idx`, `_content`, `_docsize`, `_config`. Introspecting `sqlite_schema WHERE type='table'` without filtering includes these implementation details in product table counts, corrupting baseline inventories.

### Rule & Invariant
- Product tables are static tables declared in authoritative packaged DDL.
- Filter out SQLite internal tables (`sqlite_%`) AND virtual table shadow tables (`catalog_fts_%`).
- Virtual tables created dynamically at runtime must be classified as runtime derivatives, not static product tables.

---

## 3. Generated Columns and SQLite STRICT Mode

### Symptom
Columns declared as `GENERATED ALWAYS AS (...) VIRTUAL` or `STORED` (e.g. `issue_resources.parent_kind`) fail to render or break third-party tools if treated as regular mutable columns.
In SQLite 3.31+, `PRAGMA table_xinfo` reports column hidden rank in column 6 (`hidden`):
- `0`: Normal column
- `1`: Hidden column in virtual tables
- `2`: Virtual generated column (`GENERATED ALWAYS AS (...) VIRTUAL`)
- `3`: Stored generated column (`GENERATED ALWAYS AS (...) STORED`)

### Rule & Invariant
- Check `hidden in (2, 3)` to identify generated columns.
- Correctly map `hidden == 2` to `VIRTUAL` and `hidden == 3` to `STORED`.
- Retain generated columns in column inventories, but flag them as `GENERATED` in Mermaid/DBML/HTML and document the contract.

---

## 4. Mermaid ER Syntax, Cardinality Orientation & Stub Rendering

### Symptom
- Syntax errors in Mermaid ER renderers due to special characters, spaces, or parentheses in column types (e.g. `VARCHAR(255)`).
- Cardinality orientation errors: Mermaid ER cardinality markers are direction-sensitive. Using `|o` on the right side (e.g. `stored_bytes ||--|o payload_quarantine`) causes syntax errors in `@mermaid-js/mermaid-cli`.
- Composite primary keys in external stub tables rendered on a single line (e.g. `TEXT col1, col2 PK`) cause syntax errors.
- Test assertions checking brace balance (`block.count("{") == block.count("}")`) fail because Mermaid ER diagrams use `o{` and `|{` as relationship cardinality markers ("zero or more", "one or more"), which do not have matching closing braces.

### Rule & Invariant
- Cardinality markers are orientation-sensitive:
  - Left end (parent): `||` (exactly one, NOT NULL) or `|o` (zero or one, nullable).
  - Right end (child): `o|` (zero or one, unique FK) or `o{` (zero or more, non-unique FK). Never use `|o` on the right end.
- External stub tables with composite PKs must declare each column on a distinct line with `PK`.
- Declared types in Mermaid `erDiagram` must be clean alphanumeric tokens (e.g. `INTEGER`, `TEXT`, `BLOB`).
- Avoid unescaped double quotes inside comments.
- In structural tests, verify table definition block braces (`table_name { ... }`) separately from relationship cardinality edges (`||--o{`).

---

## 5. Partial UNIQUE Indexes vs. Unconditional Constraints

### Symptom
Partial UNIQUE indexes with a `WHERE` predicate (e.g. `coverage_scopes(repository_uuidv4, kind) WHERE change_request_id IS NULL`) are exported to DBML as unconditional unique constraints or duplicate indexes, creating false guarantees not enforced by SQLite.

### Rule & Invariant
- Recover index defining SQL from `sqlite_schema` and extract `WHERE <predicate>`.
- Exclude partial indexes from unconditional `unique_constraints`.
- In DBML, annotate partial unique indexes with `[name: '...', note: 'UNIQUE WHERE ...']` and escape inner quotes. Never assert unconditional `unique` on partial indexes.

---

## 6. Physical vs. Logical Cross-Store Boundaries

### Symptom
Diagrams represent cross-store references (e.g. `operational_identity.catalog_db_instance_id` -> Core `database_identity.db_instance_id`) as enforced foreign keys, falsely implying that secondary database loss corrupts Core data.

### Rule & Invariant
- Physical foreign keys operate strictly within each SQLite database file.
- SQLite foreign keys never cross physical store boundaries.
- Cross-store relationships must be depicted as non-enforced logical dependencies (dashed lines, distinct badges, and the applicable baseline/target ADR references). Context is independently durable in the accepted target; it is not a disposable secondary. A missing cross-store FK does not waive application validation or paired full-backup requirements.

---

## 7. Deterministic Generation & Freshness Verification

### Verification Commands
```bash
# Verify that generated outputs match authoritative DDL without writing to disk:
uv run --no-sync python scripts/schema_viz.py --check

# Regenerate all visual representations:
uv run --no-sync python scripts/schema_viz.py --format all

# Run focused structural tests:
uv run --no-sync pytest tests/unit/test_schema_viz.py
```
Outputs must be byte-for-byte reproducible with deterministic sorting, UTF-8 encoding, and no runtime timestamps.
