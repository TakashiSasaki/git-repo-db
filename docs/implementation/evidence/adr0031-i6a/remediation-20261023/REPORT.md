# I6-A regression and installed-harness remediation

Author remediation for [Draft PR #145](https://github.com/TakashiSasaki/git-repo-db/pull/145),
stacked directly on #143. This is development evidence, not non-Author acceptance,
release qualification, or permission to retire Transfer fences.

## Source identity and scope

| Input | Commit | Tree |
| --- | --- | --- |
| Unmodified #143 baseline | `f5dc409429cdb69955b55e3c27a7ef3c163762fb` | `3ef434120202c6fa4cfaa1152802784a1671d3ed` |
| Initial remediation source | `423e34504b2a9686c94f971f37c164449a28fe31` | `cd93e1e226042e45b145b9c5eab605f9aa4d2d9d` |
| Final remediation source | `93d9927ae801d5402aab0aa0c7c270eeab2809e6` | `0c8a50e7cc23b98c6e7e2d1e6066077cbe8d203a` |

Before writing, live all-state PRs and all 78 remote branches showed no competing
I6-A remediation. #143 stayed pinned. The later #144 is the independent #142
re-review, a separate task and ancestry. No #139/#142 implementation was merged
or cherry-picked. Existing PRs, accepted ADRs, DDL/fingerprints, both packaged
Transfer fences and frozen Author/reviewer evidence remain unchanged. No real
Provider/catalog, automation, merge, release or deployment was operated.

The final evidence publication adds documentation/receipts after the tested
source freeze. Its exact head/tree are bound externally in the PR body; a report
cannot embed the Git tree hash containing itself.

## Changes and retained boundaries

The complete 41-file executable/source change inventory and assertion AST audit
are in [scope-audit.json](scope-audit.json).

- `context_admission.py` and `production_context.py` now check only a facade's
  local `_active` and `_writable` state before admission validation. This restores
  `CAPABILITY_EXPIRED` and `READ_ONLY`. The new hook performs no database, Stop-file,
  policy or dependency lookup. Active writable callers still require the exact
  service-issued context before selection, existence lookup or replay.
- Synthetic Store/Facade and Coordinator fixtures declare finite Resource,
  Provider, Repository, Source/pair, OID and claim authority at composition.
  Helpers run real product transactions and commit-held leases, never expand
  grants from attempted input, retry a denial, accept `None`, or install an
  autouse unrestricted issuer. Caller-owned raw transactions remain refused.
- Installed I4/I5 harnesses now stage the explicit `tests` package/support files
  outside the checkout. Tests stay out of product wheels. An explicit external
  pytest configuration prevents ancestor `pythonpath = ["src"]` contamination.
  Session-start and session-finish checks verify actual loaded product module
  origins and every installed product file against the wheel. Only the offline
  network guard uses `PYTHONPATH`; no product checkout path is added.
- I2/I3/Access and P3/P6 installed smoke fixtures receive explicit finite local
  authority. Original downstream assertions remain; Context-bearing Access
  smoke still stops at the actual I6-C guard. Nine genuinely Core-only claim
  round-trip cases now explicitly request `include_context=False` in both
  directions, retaining their original Core assertions and supported route.
- CI path triggers cover the repaired harness/support files. The classifier and
  evidence preserve node identities, failure phases, embedded child-process
  traces, current/future responsibility and actual assertion-line observations.

The complete initial run exposed eleven further P6 fixture authority omissions:
ten literal-search cases and one concurrent snapshot writer. Their finite
transaction/Coordinator wiring is corrected in the final source; all 50 P6
nodes pass in the diagnostic rerun with original assertion ASTs unchanged.
Three historical Transfer tests also needed fixture correction to reach their
real boundary. Two had omitted finite Repository/mapping/withdrawal grants.
The I3 test lacked mandatory originals, so it now explicitly authors a new
disposable upstream fixture report before selection: fixed Provider identities,
independent Parent clock/provenance/time, Mapping claims, full declaration and
endpoint tuples. It infers nothing from Core UUIDs or filtered/local rows.
All three still FAIL at the actual ordinary `I2_TRANSFER_UNSUPPORTED` fence;
their downstream assertions remain unexecuted. Initial failures/diagnostics
remain preserved rather than relabeled as final executions.

No authorization is moved after a dependency/replay check. Parent original
clock/provenance/time, total Provider endpoint declarations, whole-unit rollback,
native-I7 eligibility, both SQL fences and ordinary Transfer refusal remain.
No I6-B/C codec/Provider/Exchange connection, I7 implementation, I8 implementation,
new Parent authority, pending queue, or distribution minimization is introduced.
Requirement mapping: finite issuance, service/principal isolation and lease
lifetime preserve R10/R11/T07–T09/I5-A1/I6-L1; refusal precedence preserves R12;
actual INSERT/COMMIT/revocation rollback exercises R15/T17–T18; unchanged fence
definitions and installed checks preserve R16/R19/T19/T27. Mandatory independent
Parent originals and total endpoint declarations retain R08/R09/I5-B1/I5-C1.
No later-stage T/R acceptance is inferred from a first-stage refusal.

## Ordinary execution and classification

The selected runtime is Python 3.12.14 and its actual built-in SQLite 3.53.1,
source ID `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
No SQLite component was downloaded, built, replaced or overridden. Each frozen
checkout has its own locked dev+docs environment. Raw command, exit, runtime,
collection, JUnit, journal, typed-report and before/after input bindings are retained.

| Execution | Ordinary nodes | PASS | FAIL | ERROR | Qualification |
| --- | --- | --- | --- | --- | --- |
| Fresh clean #143 before | 5,941 | 5,198 | 324 | 419 | Completed failed execution, exit 1 |
| Initial clean remediation `423e345` | 5,974 | 5,664 | 290 | 20 | Completed failed execution, exit 1 |
| Final clean remediation `93d9927` | 5,974 | 5,675 | 279 | 20 | Completed failed execution, exit 1 |

Fresh baseline classification independently reproduces **490 direct callers,
47 Coordinator callers and 127 actual I6-C guard failures** among the additional
664. Two caught assertions required separate failing trace-only repeats to
observe `_open_context`; their counts are never added to ordinary execution.
The initial before/after ledger retains all 743 rows and separates newly reached
failures from fixed PASS outcomes. All 5,941 original ordinary nodes remain;
all 33 added nodes pass. No ordinary node is skipped/xfail. Four warnings are
Python multiprocessing fork-from-thread deprecation warnings in two passing P7
filesystem tests; the baseline had two such warnings. Source inputs and clean
head/tree bindings remain unchanged before and after both full invocations.
Its initial additional-failure remainder is 206 actual I6-C refusals, 14 actual
Recovery composition gaps, and eleven I6-A fixture omissions; the final run
measures the corrections separately. No zero-I6-A-gap claim is made for the
initial source. The final source resolves all eleven omissions and retains all
original nodes: **444 of the additional 664 now PASS**; **206 remain at actual
I6-C guards and 14 at actual I7 Recovery composition gaps**. All 79 historical
nodes still fail. There are no newly unsuccessful identities and no remaining
missing-authority fixture failure in the final measured I6-A classification.
The fourteen Recovery cases are real unconnected composition, not an intentional
explicit stage-refusal API and not a successful salvage. Their product frames
were measured in separate failing exception traces; no authorization is minted
inside recovery and no recovery implementation is bundled here.

The [final JSON ledger](classification/final/failure-ledger-reviewed.json.gz)
and [CSV ledger](classification/final/failure-ledger-reviewed.csv.gz) retain every
node's phases, old/new exceptions, first semantic frame/call chain, responsibility,
fixture/production/unsupported carrier, refusal status, repair files, rerun result,
actual assertion-line observations and handoff condition. The initial 423 ledger
is retained separately, including its eleven real I6-A misses.

| Fresh additional category | Before | Final PASS | Final I6-C failure | Final I7 failure |
| --- | ---: | ---: | ---: | ---: |
| Direct missing-authority callers | 490 | 388 | 88 | 14 |
| Coordinator missing-authority callers | 47 | 47 | 0 | 0 |
| Explicit I6-C guards | 127 | 9 | 118 | 0 |
| Total | 664 | 444 | 206 | 14 |

The nine previously guarded cases are genuinely Core-only fixtures now making
their Core-only selection explicit; no Context-bearing I6-C route is enabled.

All 79 historical node identities remain in the fresh before failure set. Only
20 retain the complete signature; 58 retain phase, 20 raw message/stage refusal,
and 24 the exception. The legacy source-only path/function projection matches
24; the expanded projection including installed child-process frames matches
20, with the four extra packaging traces explicitly retained. Of the 59 changed
full signatures, 21 stop in setup and 38 in call. A separate 743-node diagnostic
preserved all outcomes and measured **zero own-test Python `assert` statement entries
for those 59**, rather than assuming downstream equivalence. Four packaging
cases reach a failing helper assertion; child assertion execution is not inferred.
See [classification/METHOD.md](classification/METHOD.md).

In the final run, the original 79 have 59 call failures and 20 setup errors:
all 79 phases again match historical #141, but only 42 raw messages and 27
complete signatures match.
Their actual final boundaries are 36 explicit I6-C guards and 43 ordinary
Transfer-stage refusals. Of the 59 previously changed signatures, 13 now enter
an own-function literal Python `assert` line (zero before); across all 743 the
count changes from 17 to 411, with 444 test bodies completing. An entered line
does not imply successful evaluation or downstream acceptance beyond its refusal.
These measured phase/statement improvements are not a claim that the 79 failures
are equivalent or that their future behavior has passed.

The raw journal includes 57 additional passing pytest subtest call reports.
The generic old once-per-phase predicate remains false and is preserved. Typed
sidecars reconcile every raw report, then separately verify ordinary phases and
subtest outcomes; reports are never silently deduplicated into a passing receipt.
Actual assertion tracing measures literal Python `assert` source-line entry,
not `pytest.raises`/`warns`, unittest assert-method calls, subexpression coverage,
or spawned thread/process execution. Those other outcomes remain in raw traces.

## Focused, installed and adversarial verification

- Existing frozen 583-node focused cohort: **583 PASS**, exact original node set,
  zero skips/xfails and strict collection/JUnit/journal phase reconciliation.
- Serial SQL repeats: **3 PASS**. Actual second endpoint INSERT observes 1 Event /
  1 endpoint then rollback to 0/0 (`SQLITE_CONSTRAINT_TRIGGER`, 1811). Deferred
  outer COMMIT observes 1 Event / 2 endpoints with live leases, then rollback to
  0/0 (`SQLITE_CONSTRAINT_FOREIGNKEY`, 787). Post-INSERT revocation yields
  `PERMISSION_DENIED`, work charged 168, no active leases/open transaction and
  no new rows. Parent observation time remains 51.
- New controls add 33 ordinary nodes: 21 local capability preflight tripwires,
  six finite low-level fixture/rollback controls, two facade fixture binding
  controls, and four installed-harness import/configuration controls.
- A separate read-only [supporting adversarial review](adversarial-review/SUPPORTING-REVIEW.md)
  exercises all 23 mutation entrypoints in three local states (69 refusals),
  three actual finite-fixture denials, malicious ancestor pytest configuration,
  late foreign product-module injection and wrong wheel hashes. Its successful
  installed control and failing negative controls are retained independently;
  this is not a whole-branch non-Author acceptance claim.
- Dedicated I4/I5 installed direct-wheel and sdist-wheel lanes: **217 PASS +
  29 PASS each**, with exact selected/JUnit/journal identities and complete phases.
  I2/I3 smoke also passes. Overall harness exit remains 1 for both original
  Access smokes at explicit I6-C refusal, with downstream assertions unexecuted.
- Full existing installed safety cohort: **551 PASS per artifact**, exact
  historical node identities, zero skips/xfails, source/wheel/installed file maps
  equal, and in-pytest product import/configuration binding. Both normal schemas,
  original fence definitions, empty FK checks and `integrity_check=ok` pass.
  These cohorts overlap I4/I5 and are not added to their counts. Both wheels have
  SHA-256 `53f628499da0f47f72d8236e433bd0f02093202a638dbb1f657e3301891ec359`.
  The final inherited sdist remains 92,582,574 bytes, SHA-256
  `1ab614a13cf92b583050af614c9600740ae6a42c7edd5211595dee906cb774e3`;
  the separate #142 minimization/hardening is not integrated. See the
  [installed report](installed-harness/REPORT.md).
  Standalone `verify_i4_distribution.py` is not independently rerun;
  the shared I5 orchestrator executes all required I4/I5 tests in both lanes.

The initial CI-equivalent installed repro failed I4/I5 collection with
`ModuleNotFoundError: No module named 'tests'` in both artifact lanes while product
imports already resolved to installed site-packages. Frozen corrected executions
are distinct from intermediate diagnostic probes; see the installed-harness report.

Two pre-existing assert ASTs are intentionally replaced: the exact Context-only
directory assertion permits its mandatory `p1-writer.lock` alongside the sole
Context database, and a compatibility admission assertion invokes the finite
composition helper while still asserting the same `PairAdmission` value.
No assertion is removed without replacement. One authorized cross-service Source
collection now checks the exact earlier `UNQUALIFIED_MAPPING` refusal and adds
zero-row/no-Stop checks; the expired-facade Coordinator unit checks
`CAPABILITY_EXPIRED`, retaining raw-Store denial and policy-call checks. Original
read-only facade expectations remain, with an additional actual SQL read-only check.
No skip/xfail or exception-suppression mechanism is added.

Completed disposable `before/basetemp` and initial `after/basetemp` databases
were removed only after verifying their completed executions and archived raw
receipt hashes, recovering workspace capacity before the final run could exhaust
it. No active fixture, raw log, JUnit, journal, assertion stream, source checkout
or frozen evidence was removed. [Cleanup receipt](completed-fixture-cleanup.json)
records exact paths and measurements; this is not a hidden environment-failure rerun.

## Hosted CI and handoff

#143 final Access CI [39895402410](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39895402410)
has independently verified log-embedded receipts: 96 indexed members match their
byte lengths and SHA-256. Its broad cohort is **2,399 PASS / 324 FAIL / 419 ERROR**
(3,142 executed, 2,799/5,941 ordinary nodes unrun). The focused **2,059 PASS /
302 FAIL / 419 ERROR** overlaps that broad cohort and is not added to it or to
the local full 5,198/324/419. All four installed I4/I5 collection errors are
preserved in the receipt. The completed log's receipt digest is
`a7b63590d5239830257b79ddda14d24b64cd7d8f310c7bf6a314a75b6406f092`.

Final source [development CI 39902230386](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39902230386)
passes with `development_checks_passed`, `full_acceptance=false` and zero hosted
runtime test nodes. Its 21 indexed receipt members bind feature `93d9927`, test
merge `8988a5c3f5bdbab4a54dc1ec35ed8365540c6fe9`, and the exact final source tree
`0c8a50e7cc23b98c6e7e2d1e6066077cbe8d203a`; both merge parents and tree were fetched
and checked. This static/development success is not whole-runtime acceptance.

Final source [Access CI 39902230351](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39902230351)
completes with failure: its broad cohort executes 3,148 nodes, **2,849 PASS /
279 FAIL / 20 ERROR**, leaving 2,826/5,974 ordinary nodes unrun, including 27 of
the 33 newly added ordinary controls (all 33 executed locally). Its focused
**2,487 PASS / 279 FAIL / 20 ERROR** overlaps broad and is not added to it.
Both hosted artifact lanes independently execute I4 **217 PASS** and I5
**29 PASS** with all four `required_tests_executed=true` and strict node/phase
reconciliation; collection, journal, JUnit and in-pytest imports are retained.
I2/I3 smoke passes; the Access smoke remains closed at I6-C. The 121-member
receipt index is independently verified against ZIP bytes/SHA-256, digest
`2a7b364b120f88bc7ae7258ec7171d33fa02f408be30009a6b7e6e2dc9adab75`.
Hosted Python is 3.12.15 with its actual SQLite 3.53.1; no exact-version agreement
was required. The earlier `423e345` hosted receipts remain separately archived,
not rebound to the final source. Later evidence-only publication checks are
reported externally in the PR body, with unchanged executable-input verification.

The final local run executes all 5,974 ordinary nodes exactly once, with all 57
typed subtests passing, zero skips/xfails, and unchanged clean source bindings.
The only collected unselected nodes are the opt-in pagination benchmark and live
repository smoke recorded in `after-final/unexecuted.json`.
Independent non-Author acceptance remains NOT RUN. The handoff must review the
exact final source/evidence binding, finite authority boundaries, both artifact
lanes, all newly reached failures, unsupported-route refusals and the two SQL
rollback traces. Any later I6-B/C/I7/I8 work needs its own scoped implementation
and review; ordinary Transfer remains closed until the integrated R19 gate.

The repository investigation, final-tree-verification and lessons-to-skills
procedures were used. The existing final-tree skill records the verified external
test-support/import binding, finite fixture transaction and signature/line-trace
lessons; no overlapping skill or policy development was added.
