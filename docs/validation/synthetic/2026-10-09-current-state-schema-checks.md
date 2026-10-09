# Independent complete current-state schema checks

This receipt compares PR #13 HEAD `db3a5ecfbf95b4c1318198aa308ca6dc749876a1` (schema 14)
with the uncommitted schema 15 implementation. The complete production composer
is the only DDL source. All catalogs and GitHub responses are disposable
synthetic data; no live Source or retained user database is involved.

The [JSON receipt](2026-10-09-current-state-schema-checks.json) records commands,
runtime, complete object names, queried views, accessed named indexes, compiled
trigger targets, JSON categories and the actual JUnit hashes. The
[before/after inventory](../../current-state-schema-inventory.md) separately
contains every table's physical columns and all native current-resource FKs.

| Executed scope | Result |
|---|---|
| Full fresh packaged DDL | Schema 15: 103 tables, 48 views, 500 triggers, 108 named indexes. |
| Views and indexes | Every view queried; every named index inspected and accessed through `INDEXED BY`, including its partial predicate. |
| Trigger programs | INSERT/UPDATE/DELETE compiled for all 97 trigger-target tables (291 statements). |
| Native identity insertion | Current format, schema 15 and validated lifecycle admitted. |
| FK/integrity | `foreign_key_check` empty; `integrity_check` returns `ok`. |
| JSON registry | 57 fields classified; packaged generated SQL exactly equals `guard_sql()`; authored-record audit passed. |
| Baseline invariants | Current natural keys, typed FKs, generated discriminators, exact UTF-8 body hashes, signed int64/NULL timestamps and five-column coverage contract preserved. |
| Preceding behavioral checkpoint | 128 passed; failures/errors/skips 0; 59.263s JUnit duration. Test-only synthetic parser bootstrap enabled. Exact checkpoint source/test hashes preserved; this precedes the final Graph error-containment correction. |

DDL installation and DML compilation establish SQLite compilation and ownership
structure. They do not establish execution of every trigger branch. Real
writer/SQL paths in the focused tests exercise field provenance, sparse/full
arrival order, older observations filling unknown fields, explicit NULL and
empty values, truthful transfer captures, detached capture import/reopen/export,
malformed paths and Source/binding rejection, exact review PR/repository captures,
declared profile capabilities, live check time and REST/GraphQL collector projections.
JSON tests also cover canonical and nested references,
duplicate properties, missing target staging and opaque provider data.

The preliminary focused run passed 63 JSON cases and encountered 48 setup errors
because `SCHEMA_VERSION` had advanced to 15 while the native DDL identity CHECK
still required 14. The mismatch was reported to the primary owner and corrected;
the synchronized rerun passed 111 cases. Following the final guard performance
optimization and ownership tightening, 119 cases passed on DDL `df95ed8987106e881d6a5ff45d73f7cc3fe1eef21e120026178676da42e08cab`.
Final review then found that SQLite reports out-of-int64 JSON integer tokens as
`json_type='integer'` while extracting a REAL. The three field-proof timestamp
guards now also require integer extraction; nullable provider time still admits
NULL. That expanded checkpoint passed 128 cases, including six
overflow rejections and three positive cases checking signed minimum, maximum,
zero and negative values. Superseded complete-DDL/source/JUnit evidence for the
119-case tree and the earlier setup failure remain in the JSON receipt.
Complete DDL checks themselves use no bootstrap.

One subsequent source correction normalizes field-proof timestamp
`TypeError`/`ValueError` to `JsonContractError`, ensuring malformed exchanged
proofs cannot roll back independent valid siblings. It changes Python admission
behavior and its source hash; complete DDL remains unchanged. The 128-case
checkpoint is retained with its original genuine input/JUnit hashes and is not
claimed as successor-source behavioral acceptance. Cheap complete-DDL/JSON and
native identity checks were recaptured after the correction, with current
generator/source hashes. The central final-source ordinary suite and independent
combined-case review cover the successor and its additional Graph regressions.

The current complete DDL SHA-256 is
`20ec2e5c3b2fe7a064aa4e9a122d6b452d0f6b1a5be00113ce1dbd948f8f3826`. Runtime: Python 3.12.14,
SQLite 3.53.1, git version 2.52.0,
uv 0.12.19 (x86_64-unknown-linux-gnu) on Linux x86_64.

The following command reproduces the 128-case selection on whichever source is
checked out. A rerun on successor code is new evidence and must not overwrite the
saved preceding-checkpoint hashes. Before such a rerun, record input hashes with
the same snapshot logic stored in this receipt:

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
receipt = json.loads(Path('docs/validation/synthetic/2026-10-09-current-state-schema-checks.json').read_text())
exec(compile(receipt['focused_input_snapshot_source'], '<input-snapshot>', 'exec'))
PY
```

The preceding checkpoint used this focused command:

```bash
REPO_CATALOG_TEST_BOOTSTRAP=1 uv run --no-sync pytest \
  tests/integration/test_catalog3_json_contracts.py \
  tests/integration/test_current_resources.py \
  tests/integration/test_current_projection_followup.py \
  tests/integration/test_issue_transfer_followup.py \
  tests/integration/test_current_collector_projection_followup.py \
  tests/integration/test_current_followup_adversarial.py::test_review_field_proof_cannot_claim_another_change_request \
  tests/integration/test_current_followup_adversarial.py::test_field_proof_profile_requires_resources_declared_capability \
  tests/integration/test_current_followup_adversarial.py::test_sql_field_evidence_rejects_times_outside_signed_int64 \
  tests/integration/test_current_followup_adversarial.py::test_sql_field_evidence_preserves_signed_int64_limits_zero_and_negative \
  -q --junitxml=artifacts/current-schema-focused-int64-final.xml
```

The schema inspection itself uses no bootstrap. Its exact reproduction script
is stored in the JSON receipt; from the repository root, after updating the
before/after inventory, regenerate current schema checks while preserving saved
historical behavioral receipts. Missing superseded JUnit files retain their
saved historical receipts:

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
receipt = json.loads(Path('docs/validation/synthetic/2026-10-09-current-state-schema-checks.json').read_text())
exec(compile(receipt['reproduction_script'], '<schema-checks>', 'exec'))
PY
```

Complete ordinary and installed-package acceptance, genuine parser certificate
regeneration and hosted CI belong to the primary acceptance receipt. They were
not executed by this independent schema receipt. Live authenticated acquisition,
hardware power loss and non-Linux restore also remain unexecuted scopes.
