# Independent broad regression and first-boundary review

No new product finding was identified in this scope. One fresh complete ordinary
execution of the final public #151 source has **6,288 unique selected/executed
nodes: 5,989 PASS / 279 FAIL / 20 ERROR, exit 1**, with zero skips, xfails or
xpasses. These are actual results of `full-final-v3`, not a combination of Author,
focused, installed, partial or diagnostic runs. Full Release acceptance remains
outside this result.

## Source and evidence binding

Both the complete run and the separate matched diagnostic executed
`ef787a5ff8b13f118d6bf5107c7338f43fde56dc`, tree
`a3ed2628a98db134bdc65d13da905f5ddf25e972`. All **484** product/test/script/workflow/
configuration input hashes and the empty tracked status remain equal before and
after each invocation. Per-worker configure/finish records retain actual imports
and their SHA-256, interpreter/configuration identity and the loaded runtime.
The selected CPython is 3.12.14 using its own built-in SQLite 3.53.1; no SQLite
installation, replacement or version matrix was used. Product capability checks,
offline/network guards, existing test code and assertions remain intact.

The #149 reference is the preserved real #148 independent execution
`268025f67841285d105737b5a0d7bd15b1a6f59c` / `e5fa0437f19f31fa414d488ec10f483ef68f03fa`.
Its 480 before/after input hashes were independently compared with every actual
Git blob at #149 `ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00`; all match. This maps
that historical execution to #149 inputs without relabeling its execution SHA.
See `reference149-attribution.json` and `reference149-input-binding-audit.json`.

## Actual execution and reconciliation

| Invocation or actual subset | PASS | FAIL | ERROR | Exit |
| --- | ---: | ---: | ---: | ---: |
| One complete ordinary final source invocation | 5,989 | 279 | 20 | 1 |
| Separate matched 745-node assertion/refusal diagnostic | 446 | 279 | 20 | 1 |
| Independent old-three-column / valid-seven-column boundary controls | 2 | 0 | 0 | 0 |
| Whole identity module, observer isolation control | 195 | 0 | 0 | 0 |
| Identity + SQLite policy observer/subtest control | 226 | 0 | 0 | 0 |

The 226-node observer control additionally emits 57 passing subtest reports.
It does not add 57 nodes. The complete source invocation has **18,844 normal
phase reports and 57 passing subtest reports**. The matched diagnostic has 2,215
normal reports and no subtest reports. Independent stdlib parsing verifies
selected IDs, unique JUnit identities, journal starts, controller report types,
worker reports, exact phase/outcome/duration multisets, required setup/call/
teardown reach, actual process finish and unchanged input bindings. The old
helper's duplicate-phase predicates remain false for the complete invocation;
actual typed reconciliation accounts for subtests rather than modifying those
raw predicates into success.

The following are subsets of that same full invocation, not separate runs:
**626 safety nodes PASS**, including original I4 SQL **217** and I5 admission
**29**; **212 new wire/planner nodes PASS** (wire 150 / planner 62). The complete
626-node multiset also exactly matches the Author safety roster. `SUMMARY.json`
retains all actual subset node IDs and the cross-run summaries.

All collection has 6,290 IDs. The two unexecuted opt-in IDs are
`tests/e2e/test_github_sync.py::test_nested_pagination_stress_workload` and
`tests/live/test_smoke.py::test_selected_repository`. No later stage or omitted
assertion is represented as passing.

## Historical and Author comparison

Relative to the real #149 6,076-node execution (5,777 / 279 / 20), all common
node outcomes/phases are unchanged, all 212 additions pass and the unsuccessful
299-node set is exactly equal. **298** retain primary exception type, primary
refusal code and traceback frame functions. Exactly one retains `failed/call`
but changes its first boundary:

`tests/integration/i3/test_selective_exchange.py::test_empty_oid_and_context_payload_cannot_override_selection`

The old three-column carrier now gets `ExchangeError/MALFORMED_ROW` during v5
package construction instead of `AdmissionRefused/PERMISSION_DENIED` at the
unconnected receiver. The original two downstream selection assertions were
unentered in the baseline and remain unentered. Independent matched controls
show the malformed form is refused at construction while the canonical seven-
column form still reaches `PERMISSION_DENIED`, preserving complete Core/resource
rowsets in both cases. This strict caller-input refusal leaks no catalog
existence or authority and does not establish I6-C selection behavior. Do not
weaken v5 or restore a compatibility shim to recover this stale fixture. Preserve
both assertions when a genuinely connected I6-C migration is separately
implemented. See `legacy-early-refusal-assessment.json` and `selection-boundary/`.

No current failures are assigned to future owners merely from test names or the
old historical I6-C/I7/Transfer counts. Raw primary JUnit messages, phases, codes,
tracebacks and the per-node comparison remain available.

Relative to the Author's *pre-migration* complete `2f874ce` run (5,987 / 281 / 20),
only the two migrated unconnected-import guard parameterizations change from
FAIL to PASS. Independent AST comparison against #149, `2f874ce` and final #151
proves the entire test file is equal except one Resource fixture assignment;
every assertion AST and parameterization remains equal. The target function
has four unchanged assertion statements. Actual diagnostic reach is three for
`[initial]` and four for `[cached-receipt]`.

The fresh 745-node diagnostic exactly matches the Author's final 745-node
outcome, phase, primary exception/code and frame-function map. All historical
299 unsuccessful nodes retain their assertion AST entry sets, including the one
earlier refusal. All common call-phase assertion entries match. The only common
statement-entry differences are setup-only ownership of the unchanged module-
fixture return-code assertion at `tests/packaging/test_p1_distribution.py:26`
among passing P6 packaging cases on different xdist workers. The original743
reference lacks observations for the two additional guard IDs; those absences
are not treated as old assertion coverage. Tracing covers actual main-thread
statement entry, not subexpression, spawned-thread or child-process coverage.

The recovered exact Author Access CI main 2,786-node receipt (2,487 / 279 / 20)
and I5 regressions 3,148-node receipt (2,849 / 279 / 20) each have the same 299
unsuccessful IDs as the fresh complete source run and zero primary exception/
code differences. This is read-only comparison of real hosted receipts, not a
new hosted execution. See `hosted-author-failure-comparison*`.

## Preserved infrastructure controls

- `full-final/`: observer bootstrap exits 3 before test execution because the
  actual built-in `_sqlite3` lacks `__file__`; corrected identity uses
  `__spec__.origin`. Collection is not test execution.
- `full-final-v2/`: partial invocation exits 3 when an intentional test monkeypatch
  of shared `json.dumps` reaches the worker-side observer before teardown. Its
  incomplete JUnit/journal and failed reconciliation remain preserved; its raw
  counts are not product or complete-suite results.
- `observer-regression/`: an initial no-xdist control exits 1 because the same
  legitimate shared-module monkeypatch reaches the existing journal writer.
  The independent observer fix alone does not repair that standard infrastructure
  interaction. No product failure or skipped test is inferred from it.
- Serializer binding before tests plus standard xdist controller journaling is
  verified on the complete identity module and identity/policy combined control.
  Controller typed subtest context is retained. Worker makereport observes
  pre-conversion plain TestReport rows for subtests, so all worker rows reconcile
  to all controller rows; main/subtest classification uses the actual controller
  types/context. The initially rejected parser predicate and corrected exact
  mapping are retained in `observer-complete-control/typed-reconciliation.json`.

Each valid invocation has its own fresh output/basetemp. No source, test,
assertion, permission fixture, safety floor, skip/xfail or production fence was
changed. All recorded timing describes the invocation only and is not a
sequential benchmark comparison.

## Reproduction and deliverables

`tools/*.py.txt` preserves the actual independent drivers, AST audit, reference
extraction/binding checks, receipt parser and boundary controls, together with
separately retained earlier failing versions. The per-invocation execution JSON
records exact command, working directory and exit. Driver paths are the measured
cloud paths under `/workspace/i6b-broad-tools`; materialize the archived helper
bytes there and use the same checked-out source/venv or deliberately adapt paths
in a new copy. Choose fresh output and basetemp names before rerunning drivers;
their refusal to overwrite earlier evidence is intentional. Restore compressed
transport logs/JUnit/journals to their original logical paths when running the
saved analysis drivers. `prepare_reference.py.txt` reconstructs the historical
reference from its indexed repository ZIP; no historical evidence is edited.

Primary deliverables are `SUMMARY.json`, `fixture-AST-audit.json`, the
`full-vs-*.summary.json` and `.nodes.json.gz` pairs, the diagnostic and
`assertion-reach-*` pairs, `hosted-author-failure-comparison*`, actual full and
diagnostic JUnit/journals/reports, runtime/import/input bindings, all process
exits, the two independent early-refusal controls and preserved infrastructure
failures. There is no remaining execution blocker in this delegated scope.
