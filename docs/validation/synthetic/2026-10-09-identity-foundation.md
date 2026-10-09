# Identity foundation validation

Base: PR #7, `d6ee309a6845cf915f821aa1f1910b46b536a614`.
Branch: `refactor/identity-foundation`. Catalog schema advances from 9 to 10;
the import workspace remains schema 2. This report covers the identity stride,
not the subsequent CAS/parser/selection/exchange implementation.

## Scope

- Repository key naming across production DDL, callers, queries and salvage.
- Independent portable Source registration UUIDs, immutability and replay.
- Non-unique service names, explicit UUID selection and ambiguity handling.
- Source ID/registration prefixes and no display-name selection.
- NULL Source settings, pre-Job rejection, mixed discovery without fabricated
  observations and atomic result/attempt persistence.
- Backup/restore identity preservation and ordinary schema integrity.

All tests use disposable synthetic catalogs, local Git and local HTTP. Raw user
design attachments are absent from this publication branch and its new commits.
No live acquisition, retained-data changes, main merge or release is performed.

## Validation procedure

Prepare locked dependencies and wheels; record lint/format, prose and SQLite
capabilities. Use `scripts/ci_plan.py --full`, `scripts/ci_execute.py collect`,
the ordinary and packaging lanes, then `scripts/ci_execute.py gate` to reconcile
every selected test exactly once. New contract fixtures check
`PRAGMA foreign_key_check` and `PRAGMA integrity_check`.

Final results are recorded below against the tested application revision.
