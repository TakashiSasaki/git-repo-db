# Independent retained I6-A admission review of PR #153

Scoped PASS for the retained I6-A boundaries examined here. No new contract-blocking Critical, High, Medium, or Low finding was established. This does not qualify I6-C, I7, I8, ordinary Transfer, integration, or Release acceptance.

The fixed target is `61e44291e293f773904a0127606e20c8cb83c95e`, tree `4aa8ddf49fb52d0b903db0b0bfce00ccea2fae0c`, directly based on #152 `8521158f2996f125d2fcaac36ea79ac1296a7cf7`. `source-binding.json` checks the actual bytes against both Git commits for 15 production/fixture/test files. Every compared file is unchanged. Both fix-touched product modules are outside the admission, coordinator, SQL schema/fence, and application-routing modules; the parent independently evaluates their behavior.

The repository AGENTS, relevant local invariant/investigation/CI skills, Accepted ADR0001/0031/0032, I6 wire/admission/exchange design, vectors/tests, change map, #152 report/findings/admission probes, and #153 Author report and implementation diff were inspected. The reviewed tree, existing tests/assertions, Accepted ADRs, and historical evidence were not changed. All SQL uses synthetic in-memory fixture catalogs. The isolated fixture checks packaged schema and both fences before removing exactly those two fences on its private ephemeral connection; this does not activate normal Transfer.

## Executed evidence

These are separate overlapping invocations; none is added to the parent's complete-suite result.

| Invocation | Result | Exit | Evidence |
| --- | --- | ---: | --- |
| Final newly designed guard cases | 13 PASS = 12 behavior + 1 evidence writer | 0 | `raw/final13/` |
| Existing exact/invalid/uninspectable fences and unwired Provider/Exchange route selection | 13 PASS, 70 deselected | 0 | `raw/retained-route-fence/` |
| Existing actual second-endpoint INSERT failure and deferred outer-COMMIT failure | 2 PASS | 0 | `raw/retained-sql/` |
| Earlier 11-node version before adding the two deferred-COMMIT cases | 11 PASS | 0 | `raw/junit.xml`, `raw/journal.jsonl`, `raw/test.log` |
| Initial harness attempt | 10 PASS / 1 FAIL | 1 | `raw/initial-*` |

Every final completed source lane has normal exit, JUnit and journal identity equality and exactly one successful setup/call/teardown per node. The new final13 lane also reconciles independently collected IDs. `bind_and_reconcile.py.txt` is the executed pure binding/reconciliation tool. Commands and actual exits are in `commands.json` and each lane's `exit.txt`. The final probe SHA256 is `87abba86d707e00556014781aa2720e30068d642a6191529fb001ff4e2b4156d`.

The distribution reviewer separately reports executing the exact final13 probe bytes in each independently installed direct and sdist-derived wheel form, each 13 PASS/exit0 with collection/JUnit/journal identity reconciliation and actual external site-packages imports. Those independent receipts are owned by the distribution evidence and are not new source runs claimed here.

## New adversaries and what actually ran

- Four Store/facade, initial/replay cases issue a context from a different `ContextAdmissionService` while reusing the **exact same principal and policy objects**. Each receives `PERMISSION_DENIED`, invokes no policy callback, issues no SQL, and leaves every persistent table unchanged. Equal principal fields, or even identical principal/policy objects, do not substitute for the receiver service's issued handle registry.
- Two Store/facade cases revoke the finite policy epoch from an actual second endpoint `AFTER INSERT` trigger. At revocation the real database contains Event=1, endpoints=2 and active leases. Current-lease validation rejects the unit and performs SAVEPOINT and outer rollback. Every preexisting row is byte/value-identical afterward; no COMMIT is reached and actual work remains charged.
- Two Store/facade cases use SQLite's real authorizer to deny `RELEASE p1_transfer_event`. The first release attempt sees Event=1, endpoints=2 and active leases. The actual exception is `SQLITE_AUTH` (23), followed by whole transaction rollback; no partial Event/endpoint escapes and no COMMIT is reached. This exercises a release failure after SQL, not a preflight refusal.
- Two Store/facade cases independently calibrate the work of one exact duplicate and issue a fresh finite budget at that exact measured amount. The duplicate succeeds once, exhausting the budget; the same context's next replay receives `INPUT_LIMIT` before INSERT, increments consumed work further, leaves every row unchanged, and releases all leases. Replay and rollback do not refund request work.
- Two Store/facade cases inject a real deferred FK violation in the already active transaction after a guarded Transfer has written Event=1/endpoints=2. Actual outer COMMIT sees those pending rows, active policy leases and nonempty `foreign_key_check`. `SQLITE_CONSTRAINT_FOREIGNKEY` (787) rolls back everything; afterward the original complete rowsets and clean FK check return. No schema/trigger guard is weakened.

`raw/final13/observations.json` retains reached counts, actual SQL traces, charged work, exception codes and COMMIT observations. The ordinary fixture has its required FK/recursive-trigger settings. The retained SQL tests independently execute the genuine aborting second endpoint INSERT: its trigger sees Event=1/first endpoint=1 before raising, and the saved trace proves whole-unit rollback. Their separate deferred-FK case reaches actual COMMIT with Event=1/endpoints=2 and active leases.

## Refusal ordering, fences, and deferred routes

The selected existing fence cases exercise exact both-trigger definitions, each unilateral missing fence, both missing, each altered definition, and unreadable schema. Invalid/uninspectable states remain `UNSUPPORTED_SCHEMA`, never permission to enable Transfer. Normal source binding measures both exact packaged definitions, `has_transfer_fence=True`, clean integrity/FK checks and required PRAGMAs. Normal reopen, remaining fence profiles, and additional coordinator behavior are within the parent's full source and distribution cohorts; this report does not label their mere existence as a separate execution.

The selected unconnected route cases retain Provider unit/units/batch fail-closed behavior before Resource lookup, export refusal before stored identity/dependency lookup, and both initial/cached-success import refusal before progress/receipt/Context handling. These are executions of boundary refusal, not successful Provider/Exchange integration or authorization of any deferred stage.

R10–R12/T07–T09/T26 map to service binding, policy denial, replay and selection/privacy controls; R15/T08/T17–T18 map to actual second INSERT, release failure, lease retention and actual deferred COMMIT; R16/T19–T20/T26 map to both exact fences and unconnected routes. Full original Parent/endpoint revalidation tests and remaining admission/coordinator nodes are preserved and run by the complete source/safety cohorts; no borrowed provenance, sender authenticity, or cached replay authority is asserted here.

## Environment, initial error and limits

The actual interpreter is `/workspace/rr-env/bin/python`, CPython3.12.14 using its actual embedded SQLite3.53.1. `source-binding.json` records SQLite source ID, compile options, imported module paths, required PRAGMAs, integrity/FK checks and exact both-fence comparison. No SQLite library was acquired, built, installed, replaced or selected by version. The original offline/network fixture remains loaded exactly once through `tests.conftest`.

The initial 11-node harness installed the revocation fault trigger **before** constructing the facade. Its exact-schema check correctly refused `UNSUPPORTED_SCHEMA`, so the intended second-INSERT assertion was not reached for that single case. The failed source probe bytes, JUnit, journal, observations, log and exit1 are retained as `raw/initial-*`. The correction changed only the independent test's injection timing: construct the schema-verified facade, then install the disposable trigger inside the owned transaction. This proved the intended actual write/revocation/rollback behavior, and its trigger is rolled back. No product/schema check was modified. The earlier failed run is not relabeled PASS.

No runtime timing comparison, live acquisition, real catalog operation, production fix, I6-C/I7/I8 implementation, fence retirement, normal Transfer activation, merge, release or deployment was performed. Remaining full-suite known failures and historical legacy refusal differences are owned by the parent broad comparison. This subreview establishes no full Release acceptance.

No skill file was edited in the frozen reviewed tree. The initial injection-order symptom is a harness setup boundary, not a product defect: future tests should retain exact facade schema validation, then inject transaction-local faults after capability creation and preserve the rejected initial receipt. Existing skills already require actual reached SQL/COMMIT evidence and preservation of harness errors; no separate speculative policy or skill was created.
