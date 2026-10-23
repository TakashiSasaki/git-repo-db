# Supporting runtime verification

**Author validation is not complete.** Final frozen source
`770e42d4828238cc0001c96663d078605ac44841`, tree
`9769a431eed95b841c9ac2d5a54a83ea248fc5be`, has 743 ordinary nonsuccesses.
This is development evidence, not independent acceptance, release qualification,
or merge authorization.

| Frozen source | Ordinary nodes | Passed | Call failed | Setup/error | Qualification |
| --- | --- | --- | --- | --- | --- |
| #141 `dc6e663` | 5,742 | 5,663 | 59 | 20 | Complete baseline inventory; original remainder journal has untyped subtests |
| First I6-A `30888b6` | 5,919 | 5,154 | 341 | 424 | Complete first-source inventory; environment failures preserved |
| Intermediate `cc6e611` | Partial | — | — | — | Historical 3,137 completed; remainder deliberately interrupted for refusal-order correction |
| Final `770e42d` | 5,941 | 5,198 | 324 | 419 | Complete ordinary inventory and measured typed phase accounting; acceptance fails |

Each complete ordinary inventory uses two disjoint source pytest cohorts: the
exact inherited 3,137-node cohort and the remaining ordinary nodes. Final source
ran 2,394 pass / 324 fail / 419 error in the inherited cohort (130.274 seconds),
and all 2,804 remaining ordinary nodes passed (470.607 seconds). Process wall
times sum to 600.881 seconds across two separate invocations; this is not a
benchmark comparison or one-shot pytest run. Dedicated, installed and diagnostic
repeats overlap ordinary nodes and are excluded from this aggregate.

All 5,941 selected ordinary nodes match JUnit cases and journal starts exactly.
The clean detached final worktree kept the same HEAD/tree and all 471 measured
code/test/script/workflow/configuration input digests before and after execution.
No node was skipped/xfail. Two live/benchmark nodes were collected and remain
unexecuted. The 419 setup errors prevent those test bodies from executing.

## Failure reconciliation

All 79 historical nonsuccess nodes remain failing. The final mapping preserves
every original/current phase, top and causal exception, raw assertion/message,
and traceback frame. Only 58 have the same phase, 24 the same top exception,
and 20 the same raw message. Baseline categories were 45 Transfer call failures,
20 Transfer setup errors and 14 Wire call failures; final categories are
24 Transfer call failures, 41 Transfer setup errors and 14 Wire call failures.
No equivalence of the 79 failures beyond the preserved node set is asserted.

The 664 additional final nonsuccesses are individually classified using actual
tracebacks, including installed child-process frames:

| Category | Setup | Call | Total |
| --- | --- | --- | --- |
| Direct Context/caller fixtures lack a bound local admission service | 378 | 112 | 490 |
| Coordinator fixtures/callers lack explicit constructor service/admission wiring after the lease bridge correction | 0 | 47 | 47 |
| Actual explicit not-yet-connected I6-C Provider/Exchange guards | 0 | 127 | 127 |

These categories do not turn failures into passes. Genuine local authority,
selection and grant wiring must be supplied while preserving original assertions;
there is no default allow-all fallback. The coordinator API/lease bridge exists
and its authorized paths pass the focused and installed checks. I6-C routes remain
outside this implementation scope, and assertions beyond their guard are unverified.
Every row retains the concrete node, phase, message, source/installed frames and
closest test callsite. Two caught assertions initially suppressed underlying
frames; trace-only repeats measured both actual
`ProviderAcquisition._open_context` raises at `acquisition.py:1111`. Their failing
results remain preserved separately and are excluded from the ordinary aggregate.

Against the first source, final source resolves 22 failed nodes and adds none:
18 coordinator nodes, two ownership-audit nodes and two P4 packaging nodes that
previously failed from temporary-space exhaustion. Five original ENOSPC-affected
nodes were rerun as part of the entire final inherited cohort under workspace
storage; the P4 pair passes, while the P5 pair and P6 node reach real permission
failures. No final environment-only or ownership-audit failure remains. Original
ENOSPC outputs, missing-docs bootstrap failure, interrupted attempts and corrected
receipts all remain distinguished by their actual source and process status.

## Installed artifacts and SQL probes

Both independent installed lanes pass **551/551**: direct wheel in 35.131 seconds,
sdist-derived wheel in 35.268 seconds, zero skips/xfail, exact JUnit/journal node
and phase reconciliation. The 551 include inherited I4 217 / I5 29 obligations,
Parent 65, new admission/original/fence/OID/bounds tests, integration I6-A,
coordinator 46, lease-bridge 11 and refusal-priority six. Static ownership audits
apply to source and are separately covered there.

Both venvs import only their own installed product. Source-to-wheel and
wheel-to-installed product file SHA-256 maps match; post-execution product file
maps remain unchanged. Normal schema/fences, fingerprint and integrity checks
pass. Complete committed build-source and complete sdist-member inventories are
preserved. Build trees, full artifacts and venvs stay outside the repository.
The inherited packaging design is unchanged; Task A / ADR 0033 is not integrated.
Frozen build inputs are separate from later evidence publication inputs.

Three intentional serial SQL repeats also pass on the final source. The refreshed
JSON records actual second-endpoint INSERT failure and rollback
(`SQLITE_CONSTRAINT_TRIGGER`, 1811), deferred outer COMMIT failure and rollback
(`SQLITE_CONSTRAINT_FOREIGNKEY`, 787), and revision revocation after INSERT with
`PERMISSION_DENIED`, work charged 168, zero active leases and closed transaction.
Original Parent observation time 51 remains preserved. These repeats have their
own runtime, source hashes, JUnit/journal and raw SQL JSON; they are not added to
the exactly-once ordinary union.

The root-supplied 583-pass focused receipt and valid pre-fix refusal-priority
counterexample (two fail / four pass) are retained with supplied/end-bind
provenance. The earlier six-failure fixture-construction attempt is preserved
separately and is not treated as a valid product counterexample. The clean final
ordinary and installed runs provide definitive measured source binding.

## Runtime and phase accounting

Execution uses the environment's Python 3.12.14 and its actual built-in SQLite
3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
No SQLite component was obtained, installed, replaced or overridden. Native
capability/safety checks pass. Per-invocation identities, compile options and
supporting post-run base-executable hash/spec/loader mappings are retained.
Separate installed environments share the measured selected base executable;
post-run identities supplement, rather than replace, original invocation receipts.

The inherited journal lacks pytest report types. Locked pytest 9 records the
57 passing unittest subtests as additional `call` reports. Original baseline and
first-source journals retain that ambiguity and their strict duplicate-call
checks remain false; they were not silently deduplicated.

Final source records actual `TestReport` versus `SubtestReport` and subtest context
in a master-only sidecar. Every raw phase record matches its sidecar record
multiset, including node/phase/outcome/duration. Each selected node has exactly
one ordinary setup/teardown and one call after successful setup, with no duplicate
ordinary phases. All 57 measured subtests pass. A separate serial/xdist helper
probe retained an intentional failing subtest, demonstrating that the accounting
does not suppress subtest failures.

Large logs, JUnit, journals, node lists and source manifests are losslessly gzip
compressed. Each directory's `compression-index.json` binds original and gzip
sizes/SHA-256 values; original process argv stays unchanged. Scripts are archived
under `raw/` as `.py.txt`. The final source summary, complete failure classification
and 79-node mapping live under `final-v3/`; artifact receipts under
`distribution-v3/`; measured SQL/guard diagnostics in its source-specific
subdirectories. Existing efficient-investigation, final-tree-verification and
lessons-to-skills procedures were used. The verified report-type procedure is a
reusable correction candidate for the existing final-tree skill.
