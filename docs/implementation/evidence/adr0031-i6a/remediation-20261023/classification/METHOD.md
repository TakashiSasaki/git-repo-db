# I6-A failure and assertion reachability audit

The classification tool reports first reached failures. It does not turn an
expected stage refusal into a passing test, or infer downstream acceptance from
a test's name. The historical #141 evidence and #143 Author evidence remain
unchanged. New executions use the selected environment's Python 3.12.14 and
built-in SQLite 3.53.1, without obtaining or substituting a SQLite component.

## Separate ordinary invocations and repeated diagnostics

The fresh clean #143 checkout at
`f5dc409429cdb69955b55e3c27a7ef3c163762fb`, tree
`3ef434120202c6fa4cfaa1152802784a1671d3ed`, executed all 5,941 ordinary nodes:
5,198 PASS, 324 FAIL, 419 ERROR, exit 1. Its 57 passing unittest subtests are
separate typed reports, not additional selected test nodes. Two live/benchmark
nodes were collected but not selected for ordinary execution. Selected IDs,
JUnit, journal starts and typed ordinary setup/call/teardown reports reconcile;
the input bindings remain unchanged before and after the invocation.

These fresh local counts agree with the historical local Author aggregate, but
remain a separate invocation. The historical hosted broad receipt is 2,399 PASS,
324 FAIL, 419 ERROR: 3,142 executed, with 2,799 of 5,941 ordinary nodes unrun.
Its historical focused receipt of 2,059 PASS, 302 FAIL, 419 ERROR overlaps the
broad receipt. Neither hosted receipt is added to local or focused totals.

The fresh 743-node assertion diagnostic deliberately repeats exactly the ordinary
unsuccessful nodes. It also ends with 324 FAIL, 419 ERROR, exit 1. All 743 node
identities, failure phases, top exceptions and normalized product/test traceback
paths/functions match the ordinary invocation. Raw messages match in 731 cases;
the other 12 packaging messages retain their actual changed temporary and worker
paths. No raw message is rewritten to make these repetitions equal. These
repeated diagnostics are excluded from ordinary aggregate counts and their
elapsed times are not benchmark comparisons.

Two further diagnostic nodes retain their failures while recording actual
`AdmissionRefused` exception events. They establish that assertions masking the
underlying traceback in `p5/test_corrections.py` and
`p5/test_paired_admission.py` reach `ProviderAcquisition._open_context` at the
explicit closed I6-C guard. Before and after diagnostics have distinct inputs
and output namespaces; the before trace is not reused as after evidence.

## Historical signatures and fresh categories

The fresh before invocation retains all 79 historical unsuccessful identities
and all 664 additional identities, with no additional unsuccessful identity.
All 664 are freshly classified using actual tracebacks and the two actual
exception traces: 490 direct missing-authority fixture/caller failures, 47
Coordinator missing-authority failures, and 127 explicit unconnected I6-C
Provider/Exchange guards. The latter tests still fail and their intended
behavior beyond the guard remains unverified.

Among the original 79, 58 retain their phase, 24 their top exception, 20 their raw
message and stage refusal, and only 20 their full signature. The 59 changed full
signatures comprise 21 call-to-setup changes and 38 earlier call failures:

| Test module | Changed full signatures |
| --- | ---: |
| `integration/p1/test_context_relations` | 21 |
| `integration/i2/test_provider_intake` | 16 |
| `integration/i23/test_provider_exchange` | 6 |
| `integration/i3/test_selective_exchange` | 6 |
| `integration/i4/test_query_search_backup` | 1 |
| `integration/p3/test_production_context` | 1 |
| `integration/p5/test_exchange` | 4 |
| `packaging/test_p5_distribution` | 4 |

The historical source-only frame projection reports 24 equal path/function
sequences; re-reading fresh JUnit with that unchanged projection reproduces 24.
The new ledger additionally records embedded installed-child frames. Under this
expanded projection the count is 20: four P5 packaging cases no longer compare
two empty source-only frame lists. The full-signature count remains 20 in both
projections. This reporting distinction is not a new product failure.

## Actual assertion statement line observations

The evidence-only `i6a_assertion_lines.py.txt` plugin runs externally, never in
the product wheel. It traces source assertion statement line entry during each
test's setup, call and teardown and writes exclusive per-worker streams. A
completed protocol requires one start and finish per selected diagnostic node.
Serial and xdist counterexamples demonstrate that a reached assertion is
recorded, an unchosen conditional assertion is absent, a failure prevents a
later assertion, and a setup failure prevents entry into the test body.

Before remediation, none of the 59 changed-signature cases entered an assertion
statement in its own test function. Four P5 packaging cases entered a failing
subprocess helper assertion; that observation does not prove that assertions
inside their child process executed. All 21 setup failures leave their bodies
unentered. The ledger retains actual observations for every one of the 743
diagnostic nodes, together with static assertion source lines and traceback
bounds. It distinguishes an imported/unidentified function from an identified
function containing no assertions.

The measurement identifies Python `assert` statements through the source AST;
it does not enumerate `pytest.raises`/`pytest.warns` context managers or unittest
assertion methods as assertion statements. Their actual exceptions and outcomes
remain in the raw traceback/JUnit evidence. It establishes entry to the listed
statement source lines, rather than every rewritten assertion subexpression,
every conditional branch, newly spawned Python threads, or separately launched
child-process assertions.
Passing a test means its body completed; unchanged assertion ASTs and actual
line-entry observations provide the additional available evidence. Future-stage
assertions behind a retained refusal remain explicitly unverified.

## Reproduction and reporting limits

`scripts/classify_i6a_regressions.py` consumes the ordinary run directories,
their JUnit/journal/typed sidecars and optional assertion/exception diagnostic
directories. Pass separate `--supplemental` and `--after-supplemental` paths and
separate `--before-assertions` and `--after-assertions` directories. Preserve the
external trace plugin under the same module name, set `I6A_ASSERTIONS_SOURCE` to
the frozen source root, set `I6A_ASSERTIONS_OUTPUT` to a fresh directory, and add
`-p i6a_assertion_lines` to source pytest. The exception and assertion tracers
use separate invocations because each owns `sys.settrace`.

Run the tool against clean, frozen source roots matching each run's bindings.
If transporting compressed worker streams, restore their `.jsonl` names in an
external temporary directory before supplying an assertion directory. Other
ledger inputs transparently support their `.gz` transport forms. The parser's
counterexamples reject duplicate selected/JUnit identities, mismatched raw
phase/typed reports, and a failed subtest hidden behind a passing parent. Its
JUnit identity parser preserves literal `::` inside parameter IDs.

The first unbound recovery production call is separately identified from a
fixture or explicit I6-C guard. A failure through actual
`SQLiteRecoveryAdapter._merge_salvage_request` remains an I7 composition handoff;
the classifier does not call every permission error an I6-A fixture issue or
pretend that this is an intentional explicit Provider/Exchange stage guard.
