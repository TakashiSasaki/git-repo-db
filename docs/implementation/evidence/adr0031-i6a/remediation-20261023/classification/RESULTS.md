# Final per-node classification outcome

Final tested source is `93d9927ae801d5402aab0aa0c7c270eeab2809e6`, tree
`0c8a50e7cc23b98c6e7e2d1e6066077cbe8d203a`. The clean #143 before source is
`f5dc409429cdb69955b55e3c27a7ef3c163762fb`, tree
`3ef434120202c6fa4cfaa1152802784a1671d3ed`. These are source executions, not
non-Author acceptance or release receipts.

| Complete local ordinary invocation | Selected | PASS | FAIL | ERROR |
| --- | ---: | ---: | ---: | ---: |
| Before | 5,941 | 5,198 | 324 | 419 |
| Final | 5,974 | 5,675 | 279 | 20 |

Every original ordinary identity remains. All 33 added identities pass. There
are no new unsuccessful identities. Both invocations exit 1; their typed
selected/JUnit/journal/phase reconciliation passes, with 57 passing subtests
reported separately and no skips or xfails. The final source bindings remain
unchanged. Two live/benchmark identities remain unexecuted.

The original 743 unsuccessful nodes now comprise 444 passing nodes and 299
remaining unsuccessful nodes. Among the additional 664, the measured transition
is:

| Before category | Before | Final PASS | Final I6-C dependency | Final I7 dependency |
| --- | ---: | ---: | ---: | ---: |
| Direct missing authority | 490 | 388 | 88 | 14 |
| Coordinator missing authority | 47 | 47 | 0 | 0 |
| Actual unconnected I6-C guard | 127 | 9 | 118 | 0 |
| **Additional total** | **664** | **444** | **206** | **14** |

No additional failure remains assigned to I6-A, and no remaining category is
unresolved. The nine initially guarded cases now passing are the parameterized
Core-only repository-claim round trips in Access boundary tests: their catalogs
already omit Context, and their export scopes now explicitly set
`include_context=False`. Their original idempotent/reverse Core assertions
remain. This does not enable Context Exchange or Provider intake.

The 14 I7 cases are actual recovery production calls. Fresh exception-event
diagnostics reach `SQLiteRecoveryAdapter._merge_salvage_request`, which creates
an unbound ContextStore and catches permission rejection into its receipt. Valid
later Context candidates remain rejected. They are a recovery composition
handoff, not an explicit I6-C Provider/Exchange guard or accepted recovery
behavior. No authority is manufactured from salvage input.

Three additional assertions hide explicit Exchange guard frames behind expected
corruption/RecoveryStop checks. Fresh diagnostics identify the actual
`ExchangeService.export_package` refusal at line 397. The ledger preserves the
failed assertion outcomes and the automatic classifications, and attaches the
actual supplemental exception stacks used to establish I6-C ownership.

## The original 79 and reached statements

All original 79 identities remain unsuccessful. Before remediation they comprise
38 call failures and 41 setup errors; finally they comprise 59 call failures and
20 setup errors. Those final phases match the #141 phases, but only 42 raw
messages and 27 full phase/message/path-function signatures match #141. The
final first boundaries are 43 retained Transfer stage refusals and 36 explicit
unconnected I6-C guards. No constructor-TypeError or incomplete fixture-grant
failure remains among these nodes. Deferred wire and Transfer behavior beyond
the first boundary remains unverified.

The 59 full signatures changed by #143 are individually retained in the
historical audit. Before this remediation none entered a literal Python
`assert` statement in its own test function; finally 13 do. Across all original
743 unsuccessful nodes, that count increases from 17 to 411, and 444 test bodies
complete successfully. These are source-statement line-entry observations, not
claims that every assertion branch/subexpression or child-process assertion
executed. [METHOD.md](METHOD.md) states the instrumentation limits and the
serial/xdist counterexamples. The original test assertion changes flagged by the
AST comparison are explicitly reviewed in
[assertion-semantic-review.json](assertion-semantic-review.json).

The first corrected freeze `423e345` remains separately archived under
`after-initial/`. Its full run found 11 further P6 fixture-authority omissions;
they were corrected before the new final freeze and full execution. Its
433-resolved/11-I6-A result is not relabeled as the final 444-resolved result.

## Deliverables

The complete 743-row JSON and CSV ledger, original-79 audit, compact summary and
664 transition table are under [final/](final/), losslessly gzip-compressed with
original/transport lengths and SHA-256 values in `compression-index.json`.
Resolved rows have no remaining handoff; their before handoffs remain retained.
Unsuccessful rows name their measured first boundary and remaining I6-C or I7
condition. Ordinary/focused/installed/hosted results and intentional diagnostic
repetitions remain separate counts throughout.
