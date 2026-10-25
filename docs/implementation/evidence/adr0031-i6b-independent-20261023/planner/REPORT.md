# Independent finite-planner review

Frozen product: PR #151 HEAD `ef787a5ff8b13f118d6bf5107c7338f43fde56dc`, tree
`a3ed2628a98db134bdc65d13da905f5ddf25e972`. Reviewer `/root/planner_review`
is separate from the implementation Author. Product and existing tests are unchanged.

Scoped result: **FAIL — one Medium R04 configured-work-budget defect**. The
planner remains globally finite and no incomplete output was observed. The
configured work ceiling does not constrain its complete preliminary validation
scan, so it is unsuitable as I6-C's promised request-work boundary until corrected.
This review does not implement I6-C or retire either Transfer fence.

## Executions and evidence

The environment's existing Python 3.12.14 loads SQLite 3.53.1. The complete
executable, source ID, compile options and input hashes are in `runtime-inputs.json`.
No SQLite was obtained, replaced, built or selected by version. These probes are
pure Python planning checks, with the repository's offline fixture/journal loaded
once through `-p tests.conftest`; no database or Provider traffic is used.

| Independent invocation | Actual result | Exit | Evidence |
| --- | --- | --- | --- |
| Original independent graph/atomic-unit probes | 28 PASS | 0 | `pytest.log`, `junit.xml`, `journal.jsonl`, `execution.json` |
| R04 known-work-limit counterexample | 3 FAIL | 1 | `work-budget-contract.pytest.log`, `.junit.xml`, `.journal.jsonl`, `.execution.json` |
| Scaling/instrumentation script, six graph sizes and four budget/prior-work settings | 24 observations; no test PASS claim | 0 | `work-floor-measurements.json`, `.log`, `measure_work_floor.py.txt` |

The first lane has exactly 28 unique collection IDs, the same 28 journal starts
and JUnit identities, and exactly one passed setup/call/teardown phase per ID;
see `reconciliation.json`. External probe files use the actual `::test_name`
node prefix emitted by this pytest configuration, recorded without inventing a
repository test path. The second lane has three actual call-phase assertion
failures after successful setup, teardown and measurement. It is not xfailed,
skipped or counted among the 28 successes. `work-budget-contract.reconciliation.json`
records its exact identities and phases.

All probe code is retained as `.py.txt` to avoid changing ordinary repository
collection. To reproduce source probes, copy the two `test_*.py.txt` files to a
fresh external directory as `.py` and run from the frozen checkout with its
Python, `-m pytest -p tests.conftest -c pyproject.toml -o addopts=`, adding each
probe file and fresh `--junitxml`, `--journal`, `-o junit_family=xunit1` paths.
The exact invocations are retained in each execution receipt. The measurement
script expects the adjacent contract probe filename and writes its structured
observations to this evidence directory; adapt only the output destination in a
fresh reproduction. Preserve its observed result and script hash separately.

## I6B-IR-M01 — configured work limit checked after the entire embedded scan

Severity: **Medium**, requirement R04 / T11 (shared R13 closure prerequisite).

`context_dependencies.py:106` executes `_bounded_json(data, root="context")`
completely, then sets `work = prior_work + scanned` at line 107. Only line 127
checks `scope.max_work`. That scanner traverses every row and reparses all
embedded `*_json` strings (`exchange.py:97–101`), ultimately calling
`json.loads` (`exchange.py:325`). It is therefore substantive traversal and
allocation, rather than a fixed amount of envelope/type inspection.

The counterexample first calls `decode_context_v5` to establish the planner's
stated precondition: decoded and already validated v5 input. It then supplies
**explicitly empty Resource, Source and Repository selections**, 500 Resources
and 500 self-relation reports, with `max_work` equal to 0, 1 or 17. All inputs are
synthetic, typed and within outer grammar/size caps. An observer delegates every
parse to the unchanged original `_parse_json`, recording calls without replacing
validation behavior. In each case the planner still reparses **1,501 embedded
JSON values / 314,392 characters**, reports **26,041 work units**, and only then
returns `work_limit` with no output. Each of the three regression assertions
requiring at most the selected budget plus one refusal operation fails.

This is not only irreducible envelope inspection. With the known zero limit,
measured additional work scales with irrelevant input size:

| Resources + relation reports | Total input rows | Input bytes | Embedded parses | Embedded characters parsed | Charged additional work |
| --- | --- | --- | --- | --- | --- |
| 0 + 0 | 1 | 469 | 1 | 2 | 41 |
| 1 + 1 | 3 | 1,613 | 4 | 629 | 93 |
| 5 + 5 | 11 | 6,197 | 16 | 3,137 | 301 |
| 50 + 50 | 101 | 57,887 | 151 | 31,392 | 2,641 |
| 500 + 500 | 1,001 | 576,137 | 1,501 | 314,392 | 26,041 |
| 1,000 + 1,000 | 2,001 | 1,152,137 | 3,001 | 628,892 | 52,041 |

Changing the supplied maximum from 0 to 1 or 17 does not alter this work.
Likewise, an already exhausted cumulative request (`max_work=17`,
`prior_work=17`) performs the same additional work. The outer 32 MiB /
200,000-element caps still ensure finite stopping; this finding does **not**
claim infinite execution, a schema bypass, partial report emission, fabricated
completeness or an authorization grant. Those outer hard caps do not implement
the separately configurable actual-work ceiling. R04 expressly says zero permits
no corresponding work and that embedded parsing counts, with scan bounds before
allocation/recursive decoding. The Author's test asserting nonzero scan work at
`max_work=0` is an implementation claim, not authority to relax R04.

Correction acceptance conditions:

1. Constrain the preliminary scanner and its embedded parser/queue allocation by
   the **already known** remaining request work, including exhausted `prior_work`.
   Perform only a documented constant bounded refusal/envelope overhead after the
   available work is exhausted; do not finish a full irrelevant input scan first.
2. Keep actual work already performed charged and preserve only fully completed
   independent units. Continue to reject cyclic or hard-cap input finitely.
3. Make all three retained independent contract probes pass without weakening
   their assertions. Add exact scanner-budget and +1 cases, larger irrelevant
   input, exhausted cumulative retry and parser/allocation instrumentation; rerun
   both installed forms. Preserve the current failures as historical evidence.

I6-C readiness: **blocked by this Medium contract defect** for adoption of this
planner as its request-work boundary. This review starts no I6-C work.

## Independently satisfied planner scopes

These are separately observed successes, not a closure claim for R04:

| Requirement / test-plan scope | Independent probe and actual observation |
| --- | --- |
| R04 / T11 depth | A 34-Resource chain has an independently computed reachability oracle; exact depth 0, 1, 2, 7, 8, 31, 32 selects precisely the permitted nodes, retaining only complete reports. |
| R04 / T11 nodes | A three-child fanout with deliberately reversed membership order; node caps 0/1/2/3/4 preserve only whole reports and exact selected count. |
| R04 / T11 edges | All Resources are explicit seeds, so edge caps cannot be masked by reachability; 0/1/2 omit the entire three-edge report, exact 3 and +1 preserve it. |
| R04 / T11 units and bytes | For a cyclic graph and conflicting real Collection terminals: zero, one below full required units/UTF-8 payload bytes, exact and +1 preserve indivisible units and obey emitted counters. |
| R04 / T11 work after the unbudgeted initial floor | Exact full-work and +1 preserve the whole plan; one under withholds unfinished units. More than 40 independent work-stop positions preserve only completed terminal groups. The zero-work preliminary-scan defect above remains separate. |
| R04 / T11 cumulative work | Replaying the same graph with prior work doubles charged work; exhausted retry emits no units and does not refund work. The extra unbounded-by-config scanner work is the finding above. |
| R04/R06/R13 / T11 cycles | A 24-node strongly connected graph with two explicit outgoing edges per node terminates; reversing Resource/report input arrays preserves semantic selection and work count while retaining actual row order. A self-cycle at depth zero remains lawful. |
| R04 / T01/T11 hostile caller input | Cyclic Python container gives typed `MALFORMED_JSON`; over-hard-cap element array gives typed `INPUT_LIMIT` before planner row indexing. |
| R05/R06 / T11 Document/nonleaf and unknown names | A genuine global Document with recursive Unicode/empty identity owns generic children. The unknown relation name adds only the exact declared member edges; no name-based business semantics is used. |
| R06/R07 / V09/T12 | Complete/partial/unknown real terminals under the same Collection header survive as the exact original multiset or are all withheld. Every sampled limited plan decodes through the unchanged v5 codec and keeps original member order/bytes. |
| R06/R13 / T11 missing dependency | An absent referenced Resource withholds the complete two-member report; independent Resource registrations survive and the original member list remains intact. No pending payload is exposed. |
| R13 / T09/T11 | Explicit empty dimensions emit no unrelated Resource/Provider rows; output copies do not alias input; omission diagnostics contain offsets/reasons rather than full original provenance/member payloads. |

R02/R03 envelope/version/digest/schema, full seven-column native-profile cases,
Source/Coverage semantics beyond generic terminal atomicity, original Parent and
complete endpoint declarations (R08/R09), AdmissionContext/SQL/route and artifact
checks belong to the other independent lanes; this planner report does not claim
those were exercised here. Installed wheel observations belong to the separate
artifact lane, not this source invocation. No full Release acceptance, Provider
operation, performance benchmark or live check is claimed.

Repository-local skills read: `efficient-repository-investigation`,
`three-store-invariants` and its Context registration/Exchange reference,
`lessons-to-skills`. A targeted lesson recommendation is to extend the existing
zero-work probe guidance to explicitly supplied planner limits: instrument full
embedded-parser calls on already validated, explicitly unselected rows and an
exhausted prior-work balance. No product fix or skill mutation was made in this
read-only review; a verified implementation fix remains required.
