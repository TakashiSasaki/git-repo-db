# Independent published-source scanner investigation

**FAIL — I155-M01, Medium.** The admission input scanner performs variable
queue allocation without reserving the remaining cumulative work. This is an
inherited published-source defect, reproduced on154 and155 and both independently
built155 installed forms. It is not a claim about unpublished Task A/I6-C work.

## Exact counterexample

`store_case.py` creates a fresh synthetic in-memory Context with the actual
packaged schema/UDFs, validates it, and keeps both original Transfer fences.
It calls the real `Context.owned_transaction` and `Context.relation` with a
valid `x-links` ResourceRelation containing1,000 distinct typed Issue members.
Their canonical member JSON is58,891 UTF-8 bytes. The service-issued context has
an explicit finite selected Resource set and a policy that raises if contacted.
Prior work is charged using the production `AdmissionBudget.charge`, never by
altering its usage list.

At work_limit10,000/prior_work9,992, the wrapper/report/string traversal consumes
the8 remaining units. At domain/context_admission.py:381, actual `list.extend`
then grows the scanner queue **2→1,002 at used_work10,000**. No child-queue
reservation occurs: line379 compares `len(item)` with the **total** work_limit.
The next child charge raises INPUT_LIMIT at used_work10,001. An independent
C-call-only observation in the I6 section confirms the same production event.

The observed queue after extension occupies8,888 shallow list bytes plus56,112
shallow entry-tuple bytes on this interpreter; existing queued entries account
for112 of the tuple bytes. These are measured object sizes, not a total heap,
peak RSS, timing or portable memory guarantee. The observer's own allocations
are excluded from those object sizes and no performance comparison is claimed.

| Real relation case | Max pending entries | Result |
| --- | ---: | --- |
|16 members, budget10,000/prior9,992 |18 | INPUT_LIMIT, used10,001 |
|1,000 members, budget10,000/prior9,992 |1,002 | INPUT_LIMIT, used10,001 |
|1,000 members, budget10,000/prior10,000 |1 | INPUT_LIMIT, used10,001 |
|1,000 members, budget10,000/prior0, selection.max_work7 |1,002 | INPUT_LIMIT, used8 |

The already-exhausted control allocates only the fixed root queue before its
first failed charge. That bounded bookkeeping is **not** the finding. The
variable expansion occurs **before** refusal, after remaining work reaches zero;
it is not post-refusal processing. Selection's work bound is checked at the
bottom of the loop, after the expansion, which supplies the independent small
selection counterexample. Dictionary controls similarly allocate two entries
per member. Dataclass fields are fixed-size in these vectors and are not
misreported as1,000 children themselves.

All four real-store cases on each source/installed form call the policy zero
times, leave relation rows0→0, end outside a transaction and issue ROLLBACK.
The saved17 SQL statements include facade schema/stage validation reads before
the scanner; they are retained, not described as an absence of all SQL reads.
No mutation INSERT/UPDATE/DELETE/REPLACE or successful admission is observed.
This does not establish an authorization bypass, corruption, unlimited input
growth or partial durable report. Severity is Medium because configurable
cumulative/selection work stops fail to bound actual queue work before
allocation, within otherwise finite input limits.

R04 requires cumulative actual work, zero expansion at zero corresponding
budget, and bounds before allocation. R13 requires actual closure checks/work
and whole-unit withholding. The refusal/rollback preserves whole units but does
not refund or justify preceding unreserved allocation. The task makes a real
mandatory finite-work violation a FAIL. No product repair is included; a later
separately assigned Author correction and independent review are required.

## Tested scope and controls

`study.py` observes17 admission cases,22 codec cases and6 planner cases per form;
`store_case.py` adds4 normal-store cases. `run.py` executes all49 per form against
published154, published155 and each separate installed direct/derived wheel.
`summary.json` binds actual imported module SHA256s to both published Git blobs;
all three scanner/planner module bytes match in all four forms. The two wheel
module origins are external site-packages. Actual native runtime is
Python3.12.14/SQLite3.53.1; no other SQLite was acquired or selected.

There is **no reproduced variable queue violation in `_bounded_json` or
`plan_context_dependencies` within these controls**. Dictionary/list1,000-child
and nested embedded-JSON/canonical-identity inputs with work0/1/17, and exhausted
prior_work1,000, refuse before bulk expansion/parser calls. Accepted larger
budget controls actually invoke the parsers. A cycle and34-container depth case
stop finitely. A valid two-Resource planner fixture at work3,610 preserves the
completed Provider and first Resource while withholding the next Resource;
work3,611 completes all3 rows. Earlier passing scanner probes are not declared
invalid, and these bounded controls do not prove absence for unlimited inputs.

The optional codec `spend` callback implements the published planner's reservation
semantics as an independent control; it is an API argument, not a replacement
production scanner. Real planner cases execute its own nested `spend`. Real
admission/store cases execute actual `AdmissionBudget.charge` unchanged.
`sys.settrace` reads real pending lists/work counters; `sys.setprofile` observes
actual C `list.extend` entry/return and parser calls. No product callee, list
writer, parser, return value or budget is monkeypatched. Tuple-size summation
adds observation overhead, which is not attributed as product work.

## Reproduction and remaining obligations

From an external working directory:

```sh
PYTHONPATH=CHECKOUT/src REVIEW_PYTHON scanner/study.py --output source.json
PYTHONPATH=CHECKOUT/src REVIEW_PYTHON scanner/store_case.py --output store.json
env -u PYTHONPATH INSTALLED_PYTHON scanner/study.py --output installed.json
env -u PYTHONPATH INSTALLED_PYTHON scanner/store_case.py --output installed-store.json
```

Use a separate clean154 checkout for the first pair. `run.py` preserves the
actual task-local paths, subprocess commands, script/observer/output hashes,
stdout/stderr and exits. `verify.py` independently checks the saved observations,
real list-extension event, refusal/persistence, proper pre-reserved controls,
completed-unit control, all execution hashes and source/installed bindings.
`store155.json`/`store154.json` are retained initial exploratory runs; authoritative
final repeated runs are `store-source155.json`/`store-source154.json` and
`store-direct.json`/`store-derived.json`, indexed by `executions.json`.

No Task A workspace was opened, unpublished reproduction was requested, service
denial bypassed, or implementation substituted. The next checkpoint is a
separately authorized published correction covering cumulative remaining work,
selection-bound ordering, list/dict/dataclass/string accounting and these saved
vectors, followed by independent source and both-installed re-review. Existing
299 ordinary non-successes and deferred I6-C/I7/I8 do not excuse this finding and
are not themselves its basis. No merge/release/Transfer activation follows.
