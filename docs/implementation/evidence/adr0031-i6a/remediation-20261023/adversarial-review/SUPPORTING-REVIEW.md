# Supporting adversarial review of the I6-A remediation

No material finding was reproduced in this bounded review. This reviewer did not
write the inspected product, fixture or installed-harness changes. This is a
supporting check within the Author remediation task, not non-Author acceptance of
the whole branch, I6-A, later integration stages or release qualification.

Frozen source: `423e34504b2a9686c94f971f37c164449a28fe31`, tree
`cd93e1e226042e45b145b9c5eab605f9aa4d2d9d` in a clean detached checkout.
Read scope: the two product capability-hook changes, both finite fixture wrappers,
installed harness and I4/I5 distribution-driver composition, associated negative
controls, and unchanged authorization-before-dependency/replay guards.

## Actually executed

- `probe-v3.py`: all 23 mutation entry points in each of expired, read-only and
  active-unbound states: 69 expected refusals with storage/Recovery-Stop tripwires.
  Three real finite-fixture refusals cover a foreign-issued invocation, an
  unlisted Resource and repeated unlisted admission. Grants and admitted row set
  remain fixed, all leases close, and foreign policy is not called. Exit 0.
- `installed_probe_v2.py`: uses the parent's already installed direct-wheel venv,
  without a build, installation or SQLite change. An ancestor pytest configuration
  requests the checkout's `src`, while explicit external configuration correctly
  imports the installed artifact and passes (exit 0).
- In that same installed venv, importing a foreign product module during the test
  is rejected by the session-finish origin check (exit 1). An incorrect expected
  wheel file digest is rejected at session start (exit 3). Those nonzero results
  are intentional negative controls, not product suite failures. Actual pytest
  commands, configuration, origins and hash snapshots are retained.

## Preserved unsuccessful probe construction

The initial probe mistakenly called `provider()` on low-level `ContextStore`,
which has no such method. The second compared `sqlite3.Row` directly to a tuple.
The corrected probe registers synthetic prerequisites through trusted SQL and
normalizes returned rows. The first installed injection probe had a Python local
import-binding error (`UnboundLocalError`), corrected with `importlib.import_module`.
All original scripts/logs remain; none of those attempts establishes a product
finding or replaces the successful corrected controls.

## Not run and limits

No full ordinary suite, complete focused cohort, sdist-wheel lane, hosted CI,
benchmark, live Provider, real catalog, release or deployment was run by this
reviewer. Parent-run acceptance evidence remains separate. Origin checks here
verify the actual pytest session-start/session-finish module snapshots and wheel
file bytes; this report does not claim arbitrary hostile test-code containment.
The pure local refusal hook does not authorize any mutation. Active writable
callers continue into the existing service/context, policy and dependency checks.
Both SQL fences and I6-B/C refusals were read as preserved; no fence retirement or
later-stage runtime acceptance is asserted.

`compression-index.json` binds each original and stored byte stream. Only scripts,
logs, JSON receipts and this report are copied; disposable catalogs, installed
venvs, source copies and distribution artifacts are excluded.
