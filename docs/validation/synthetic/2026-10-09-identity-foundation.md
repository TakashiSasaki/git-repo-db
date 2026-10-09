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

## Results

Tested commit: `e3e6f34ab0397db7d7b86ffa446fe3b5da693ba5`.
Tested tree: `6f0b0c87952f126a56a6814ee829ae8ea04aa1d8`.

- Ordinary acceptance: 837 passed in 93.68 s.
- Installed wheel and sdist acceptance: 2 passed in 3.45 s.
- Final CI reconciliation: 839 executed across 49 selected files; zero
  unexecuted or excluded files.
- Lint, formatting, prose, locked dependency/wheel preparation, SQLite doctor
  and FTS probes passed.
- New identity contracts: 18 tests covering namespace ambiguity, registration
  immutability, selector collisions, preflight, replay/backup identity and atomic
  terminal results.

Environment: Python 3.12.14, SQLite 3.53.1, Git 2.51.1, uv 0.12.19,
pytest 9.1.1, Ruff 0.16.10.

These are synthetic local checks. Hosted CI and real-source acquisition are
not included. The report commit changes evidence only; its runtime, tests and
CI files match the tested revision.
