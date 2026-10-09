# Complete schema 14 to 15 inventory

The comparison starts from PR #13 HEAD
`db3a5ecfbf95b4c1318198aa308ca6dc749876a1` and uses disposable fresh SQLite
databases. Baseline resource files are read with `git show` into a temporary
directory; the working checkout is never replaced. The current side comes from
the production `adapters/sqlite/schema.py::schema_sql()` composer. Historical
schema-hardening SQL is not used.

The [machine-readable inventory](current-state-schema-inventory.json) contains
every named production object and its SQL hash, every physical table's complete
`table_xinfo` column inventory (including generated columns), and both current
resource tables' native foreign keys. The [column liveness review](current-state-schema-liveness.md)
records writers, meaningful readers, constraints, transport use and retention
decisions. Executed checks and their limitations are in the
[schema-check receipt](validation/synthetic/2026-10-09-current-state-schema-checks.md).

| Named production objects | Schema 14 baseline | Schema 15 current |
|---|---:|---:|
| Tables | 103 | 103 |
| Views | 48 | 48 |
| Triggers | 496 | 500 |
| Indexes with explicit SQL | 108 | 108 |

Counts include FTS shadow tables and exclude SQLite internal objects and
automatically created indexes whose SQL is NULL. No table, view or named index
is added or removed. No normalized history table is introduced. Native
foreign-key declarations of `issue_resources` and `review_resources` are
unchanged.

| Table | Added columns | Removed columns |
|---|---|---|
| `issue_resources` | `field_evidence_json` | None |
| `review_resources` | `field_evidence_json` | `title` |

These are the only physical column changes across all 103 tables. The new JSON
maps retain attribution for current values and nested metadata paths: observed
and parsed times, provider clock, exact parser profile and original acquisition
scope. A map entry contains no previous value. Sparse updates can preserve a
value with its actual evidence instead of assigning the enclosing response's
clock to an inherited value. The review title had no provider producer or
meaningful query/search consumer.

The six generated current-resource columns are preserved with the same column
attributes and foreign-key use:

| Table | Generated constraint discriminators |
|---|---|
| `issue_resources` | `parent_kind`, `owner_kind`, `fact_kind` |
| `review_resources` | `parent_review_kind`, `reply_kind`, `owner_kind` |

Four new triggers guard INSERT and UPDATE of the two evidence maps. Timestamp
members require both JSON integer tokens and SQLite integer extraction, rejecting
out-of-int64 tokens that SQLite would otherwise extract as REAL; nullable
provider update time still admits NULL.
The existing Issue acquisition guards and child-transfer trigger are updated to
preserve valid original capture context while changing current membership.
`database_identity` also advances its version constraint from 14 to 15.
The exact changed object list and hashes are in the JSON inventory.

`exchange.LOCAL_COLUMNS` now contains only
`repositories.preferred_repository_endpoint_id`, a real local endpoint-selection
column. The three former policy entries for nonexistent current snapshot,
change-request observation and document observation pointers are removed. The
inventory asserts that every remaining policy entry exists in complete
production DDL.

The production resource composition is unchanged: `catalog3.sql`,
`git_facts.sql`, `cas_integrity.sql`, `exchange.sql`, `identity_relations.sql`,
`current_resources.sql`, `current_collections.sql`, then `json_contracts.sql`.
The last resource is generated from the JSON registry; it classifies 57 fields,
including the two new `current-field-evidence` fields.

To reproduce the exact inventory logic from the repository root, execute the
script stored in the JSON receipt. This writes a new disposable measurement of
the checked-out current tree and the fixed baseline:

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
receipt = json.loads(Path('docs/current-state-schema-inventory.json').read_text())
exec(compile(receipt['reproduction_script'], '<schema-inventory>', 'exec'))
PY
```

The JSON records the observed working HEAD separately from its uncommitted
implementation. It is schema evidence for this tree, not a hosted-CI or released
commit certificate. DDL installation and DML compilation do not claim execution
of every trigger branch.
