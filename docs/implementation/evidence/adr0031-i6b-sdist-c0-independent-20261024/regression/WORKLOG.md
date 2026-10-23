# Independent ordinary-source regression review

Frozen source: PR155 `fee364c6d61a5feebf08dbdd830a5a57ee2d872b`, tree `ace7e44cd89194d189a30a0aa6cf513a45b3b87c`. This review reads only published Git; no I6-C unpublished work, product corrections, assertions, workflows or ADRs were accessed or changed.

The runner uses the locked dev+docs environment and native Python3.12.14 / loaded SQLite3.53.1. The 48 compatible `uv.lock` dependency wheels were downloaded during separate online preparation and then manifest/hash verified; test executions retain the original offline guards. No SQLite engine acquisition, change or matrix occurred.

## Completed raw historical reconciliation

The new independent comparator directly checks exact collection IDs, xunit1 identities, journal starts/phases/completion and controller/worker reports. It does not import an Author failure classifier. It checks all source inventory SHA256 values against both recorded execution Git commits and named review targets with `git cat-file --batch`. It additionally binds all reported product-module origin hashes. Existing observers are attributed byte-for-byte copies of the published read-only hooks and were inspected for assumptions.

- Historical154 execution at published153 `61e4429…`:6344 unique,6045pass/279callfail/20setuperror,exit1. All486 source/test/script/workflow/config inventory entries match154 `9182736…`.
- Historical155 execution at `fb5d7b5…`:6497 unique,6198pass/279callfail/20setuperror,exit1. All490 inventory entries match final155.
- Common6343 nodes:zero outcome/phase changes.154added all pass. One passing README parameter removed and replaced with reviewed144's minimal-sdist case; actual replacement AST matches144.
- Same299 unsuccessful node/phase keys, exception classes, typed refusal codes and project path/function sequences. Four physical frame-coordinate changes remain explicit.19 raw JUnit message and299 raw traceback bodies differ; no byte identity claim.
- Each historical full invocation additionally has57 passing pytest subtest reports. These are separate from ordinary node totals. The published generic helper's duplicate-phase warnings arise from its subtest-unaware reconciliation; the own parser distinguishes actual report types/context and verifies all report/journal counters.
- Historical diagnostic745 has zero call-phase assertion-entry changes and zero unsuccessful all-phase changes. Two passing setup node associations differ; the global assertion-entry set is equal. Statement-entry evidence is limited to the main worker Python thread, not subexpressions, other threads or child processes.

## Fresh execution status

Full6497 ordinary invocation is running separately. Final verdict/counts/source binding will be recorded after process completion. The exact two unexecuted opt-ins are retained in its `unexecuted.json`. No full-source success or inherited failure equality is inferred from progress.

## Preserved implementation failures

The first independent comparator attempt used `Counter(mapping)` instead of `Counter(mapping.keys())`, falsely failing its node-key check. Its log and initial comparator source are retained. Correcting that review-parser bug produced the documented comparison without changing or rerunning product tests. No service denial or approval override occurred.

A later completion-check hardening attempt incorrectly required every xdist worker's session exit to equal the controller's global exit. The raw154 `gw2` session correctly had exit0 and no failed reports while other workers/controller exited1. That failed comparator log and its source snapshot are retained. The corrected independent comparator verifies the controller exit against the process and each worker exit against its own failed-report set. This is a review-instrumentation mistake, not a product regression.

## Fresh execution completed

- One final frozen-source ordinary invocation completed: **6497 unique =6198PASS /279FAIL /20ERROR, exit1**, skip/xfail/xpass0;57 additional passing subtest reports are separate. All selected/JUnit/journal/controller/worker counters reconcile exactly. Before/after HEAD/tree,490-file executable inventory and clean tracked status match. .github/actions/product-python/action.yml,`.gitignore`,README match the same tracked Git source; supplemental build binding records the combined493-file scope. Review evidence is untracked in the shared checkout, so this is no fully-clean Release receipt.
- Separate diagnostic745 completed:446PASS/279FAIL/20ERROR,exit1,zeroskip/xfail/xpass. It is overlapping evidence, never added to ordinary totals.
- Freshfull vs published155:all6497 common outcomes/phases and all299 exception/refusal/project-frame-function/physical-frame coordinates match.19 raw message and299 raw traceback bodies differ.
- Freshfull vs154:6343common zero outcome/phase changes,154newPASS and1passingREADMEreplaced;all299 unsuccessful keys/exception/refusal/framefunctions match,4physicalcoordinate differences retained.
- Freshdiagnostic vs155:all745 call and all-phase assertion-entry sets match. Freshdiagnostic vs154:all745call sets match,2passing setup associations differ,all299unsuccessfulall-phase sets match,global assertion-entry set equal.

The active runner and both observer modules were unchanged before/after both invocations. Additional external analysis tools were created while ordinary tests ran; they are explicitly outside tested source and did not replace production operations.
