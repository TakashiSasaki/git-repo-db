---
name: sqlite-schema-visualization
description: Introspect implemented SQLite formats and generate non-destructive schema visualizations. Distinguish responsibility domains, composition, source ownership and operation requirements. Use for composite keys, all-format inventory, FTS/generated-column classification, provenance or diagram freshness.
---

# SQLite Schema Introspection and Visualization Invariants

Read the [ADR index](../../../docs/adr/README.md) before interpreting ownership.
The visualization commands below consume the normal Schema 21 / Operational 1 /
Search 1 baseline. The explicit all-format diagnostic profile also inventories
P1, Access, Filesystem and Worktrees; see section 8. These schema definitions are
not a count of required databases or logical authorities.
[ADR 0029](../../../docs/adr/0029-independent-access-store.md)
owns the five existing responsibility domains, including independent Context and Access;
[ADR 0030](../../../docs/adr/0030-context-repository-relations-and-selective-exchange.md)
selects two additional Context relations (19 composed tables as a target, not an
implemented count), without mapping Witness storage. These and the
metadata/notes/key/recovery decisions do not become implemented merely because a
diagram can be generated. [ADR 0039](../../../docs/adr/0039-independent-filesystem-and-worktree-catalogs.md)
adds independent Filesystem and Worktrees, with DB-free Local composition.
Legacy table names and
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
uv run --project documentation --no-sync python documentation/tools/schema_viz.py --ir documentation/.build/inputs/inventory.json --check

# Regenerate all visual representations:
uv run --project documentation --no-sync python documentation/tools/schema_viz.py --ir documentation/.build/inputs/inventory.json --format all

# Run focused structural tests:
uv run --project documentation --no-sync pytest documentation/tests/test_schema_viz.py
```
Outputs must be byte-for-byte reproducible with deterministic sorting, UTF-8 encoding, and no runtime timestamps.

## 8. Separate format coverage, ownership and semantic guarantees

**Observed traps:** a normal-CLI inventory omits opt-in formats; same-named tables
from different factories appear to be one entity; a composed schema has Runtime,
domain and Contracts contributors even though each installed source file has one
owner. Inferring one package per schema gives false ownership violations. Some
formats expose only an opaque format ID, others only an integer schema version.

1. Use `scripts/local-run.sh python scripts/schema_inventory.py --check --profile all`
   for the registered complete format inventory. Keep the default normal renderer
   input separate; do not feed an all-format graph into a three-store renderer.
2. Qualify entity IDs by revision/profile/format before combining graphs. Separate
   responsibility domains, composition entry points, contributing files, package
   dependencies and operation prerequisites. Verify installed namespace path
   ownership across all workspace distributions, not only Git conflict paths.
3. Register the real UDFs before applying DDL in memory. Retain SQL and observed
   connection/function metadata, but label them structural evidence. Do not claim
   trigger behavior, CHECK/NULL equivalence, persistent-DB configuration or recovery
   correctness from successful schema creation. Preserve absent version fields.
4. Require expected format/object/column targets and test removed-target examples.
   A missing schema in a declared complete profile is an extraction failure; an
   unavailable instance behind an optional domain reference is unresolved. These
   are different scopes and need different outcomes.
5. Export only from committed, byte-matched producer inputs. The input digest closure
   is broader than the human-readable contributing-file annotation. Stage/commit
   new scripts before producing evidence; never bind dirty new code to old HEAD.
6. Check `test_schema_catalog.py` counterexamples and the existing normal inventory
   tests together. Run product extraction with verified product Python and rendering
   with the separate documentation environment. Avoid adding reasoner packages to
   product dependencies for an optional analysis workflow.

See [the inventory guide](../../../documentation/schema-model-inventory.md).
These checks are useful preparation for RDF/SHACL; they do not constitute ontology
satisfiability, instance-data validation or a proof of implementation conformance.

## 9. Verify the semantic checker and evidence source independently

For an optional SHACL pilot, use one pinned IR and request-private graph. Exercise
the same shape with a valid witness, a deliberate violation and no matching target.
Inspect target counts, skipped constraints and definitive versus undetermined
results; `violation_count == 0` alone is not success. Open Ontologies was observed
to distinguish these three cases, while its verified-evaluator call returned no
verdict when the executable was absent. Capability status is a point-in-time
inventory; check the actual requested mode instead of inferring it from a healthy
server or ordinary-SHACL success. Preserve engine/version and translation limits.

When a repository test builds a temporary Git index with `git read-tree HEAD`,
staging new files is insufficient. Commit a coherent inventory/file set before
running that exact-tree check. Otherwise a new classification can fail as stale
before the intended frozen-evidence counterexample is reached. Preserve the first
failure, rerun after committing, and distinguish that setup issue from a product
or validator defect. Do not weaken the frozen-evidence guard to make the test pass.
