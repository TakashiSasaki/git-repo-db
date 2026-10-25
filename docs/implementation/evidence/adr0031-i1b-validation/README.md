# ADR 0031 I1b validation receipts

Local development validation, not product/distribution/release acceptance.
Executable freeze: `d77acad2c2d97538479d7fa5489ecebfd5ad8f67`, tree
`9e6a0d9db602446d4ce7e93d98f12533202e4b5e`, based on exact I1b
`32e5d4de67c0d436f7583d04e1cfd349b64b2bbd`.

- [Report and reviewer handoff](../../adr0031-i1b-validation-closure.md).
- [Summary](summary.json), [per-node dispositions](failure-disposition.csv),
  [active boundary inventory](active-boundary-audit.json).
- [Raw receipts](receipts.tar.gz): SHA-256 `f8551728c0ab7bddfc317d552d9af5f4726b6aa1aabcf2f8327e4d2bb59d8398`.
- [Archive member index](receipts-index.json): 123 files, exact byte lengths and hashes.

The archive contains exact commands, interpreter/source IDs/options, all 429
input hashes, selected IDs, full JUnit/logs/journals, original failed/interrupted
attempts, runtime setup/source hashes, stack snapshots and frozen-head hosted CI
observations. It contains synthetic test evidence, not catalogs or credentials.
Verify every member against the index before relying on it. Local receipts are
agent-asserted evidence; hashes establish consistency, not independent attestation.

`final-r2-*` records bind the final executable freeze. Each runtime executed
2,740 cases: 2,736 passed, four failed; no errors/skips/xfails. Both isolated Access
distribution variants failed at the I2 composite-local Event gate. No PASS is
inferred from earlier/focused receipts or from green Development CI.

The raw runner's `selected_equals_junit=false` is preserved. Four parameter IDs
contain literal `::`; `junit-reconciliation-3513.json`,
`junit-reconciliation-3531.json` and `summarize.py` correctly use the existing
repository normalization rule and reconcile exact duplicate-aware node counters.
The intentionally interrupted diagnostic also retains its original runner's
`skipped=1` default for a missing call; the summary explicitly records that case
as incomplete. Neither parser issue is a product failure or a passing run.

Commands and environment overrides are retained in each `receipt.json`.
`final_runs.py`, `run.py`, `receipt_plugin.py`, `summarize.py`, `cohort.json` and
`final-executable-freeze.json` make selection, journaling and reconciliation
reviewable. Historical attempts retain their original limitations; final receipts
capture the exact harness hashes. Later publication adds reporting and skill
prose only; distributions were built at the executable freeze above.
