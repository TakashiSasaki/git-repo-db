# PR #153 independent M01 re-review

Scoped result: **M01 may close; no new Critical/High/Medium finding in this
planner/scanner scope.** This reviewer did not author the correction and changed
no product, existing test, ADR, old evidence, or skill. This result is not Release
acceptance or a claim that I6-C executes; the parent review controls the overall
verdict after its other lanes.

Target: `61e44291e293f773904a0127606e20c8cb83c95e`, tree
`4aa8ddf49fb52d0b903db0b0bfce00ccea2fae0c`. Baseline #152:
`8521158f2996f125d2fcaac36ea79ac1296a7cf7`, tree
`455ef25606ee555e4154dd2d14929b41aa4ef50f`. The measured origins and hashes are
retained in `baseline-measurements.json` and `corrected-measurements.json`.
Both measurements load the actual respective source through an explicit
PYTHONPATH; baseline source was a trusted `git archive 8521158 src` extraction.
The environment Python is 3.12.14 and its loaded SQLite is 3.53.1; no SQLite
acquisition/build/replacement or alternative binding was used. The SQLite source
ID and actual interpreter path are in the receipts.

Read scope: repository AGENTS, ADR index, Accepted ADR0001/0031/0032, I6
wire/admission/exchange, vectors/tests, change-map/handoff and I6-B notes; #152
REPORT/planner REPORT/saved work-budget probe and independent graph probes;
#153 Author REPORT and implementation/test diff. Relevant skills:
efficient-repository-investigation, three-store-invariants and its scoped
work-reservation guidance. ADR0032 supersedes old exact-SQLite skill examples.

## Independent observations

The unchanged saved valid-context fixture is first accepted through
`decode_context_v5`, then only the planner call is measured. At 500 Resources and
500 relation reports (1,001 rows), the actual baseline versus corrected counts
are:

| Budget / prior | Baseline parses / chars / work | Corrected parses / chars / work |
| --- | --- | --- |
| 0 / 0 | 1,501 / 314,392 / 26,041 | 0 / 0 / 1 |
| 1 / 0 | 1,501 / 314,392 / 26,041 | 0 / 0 / 2 |
| 17 / 0 | 1,501 / 314,392 / 26,041 | 0 / 0 / 18 |
| 17 / 17 | 1,501 / 314,392 / 26,058 | 0 / 0 / 18 |
| 17 / 27 | 1,501 / 314,392 / 26,068 | 0 / 0 / 28 |

The independent measurement additionally uses 0, 1 and 13 Resource/report pairs
and both current and already-excessive prior balances: 20 observations per
source, not pytest counts and not added to other lanes. Input creation and codec
validation occur before measured instrumentation. The observer delegates to the
original parser and never substitutes `json.dumps`.

Malformed root dictionaries are constructed before `tracemalloc` starts and
before entering the measured call. Patch setup is also excluded. The wrapper
records actual `set` argument lengths while returning ordinary sets.

| Root keys | Baseline sets / peak bytes | Corrected sets / peak bytes | Both refusals |
| --- | --- | --- | --- |
| 20,000 | [20,000,16] / 1,052,148 | [] / 1,818 | MALFORMED_SECTION |
| 40,000 | [40,000,16] / 2,100,580 | [] / 1,514 | MALFORMED_SECTION |

These individual allocation observations independently corroborate the claimed
approximately 1.05 MB to 2 KB change, without treating the exact byte number as a
stable threshold, statistical comparison or elapsed-time benchmark. Inputs are
preallocated, so those numbers describe work newly allocated during refusal.

## New adversarial probes

`test_m01_new.py.txt` contains **38 new probes, source PASS38 / exit0**. The final
source invocation's 38 unique collection IDs equal the JUnit cases and journal
starts exactly, with 114 ordinary passed phase records, one setup/call/teardown
per ID and a normal exit0 journal finish. No skip, xfail or substituted node is
used. `source.execution.json`, `source.reconciliation.json`, raw collection,
JUnit, journal and log retain that invocation. The byte-fixed probe SHA256 is
`52865c1c59314a523adbb36099da0109b80034874e54637404d92c615f96a302`.

The probes independently build Resources with recursive Unicode/meaningful-empty
identity coordinates and lawful cycles. Provider configuration is canonical `{}`.
Large valid payloads use the actual typed unknown-relation scope, which must pass
the codec before measured planning. The probe set covers:

- Zero/small/exhausted/excessive-prior budgets, ASCII, Unicode and escape-heavy
  validated inputs. Scanner parse/identity/escaping operations record their
  previously accepted reservation; no giant operation executes after a refused
  reservation. Accepted reservations stay within remaining work.
- Malformed 180,000-character embedded suffixes and a caller-owned 20,000-key
  embedded object. These hostile caller inputs are explicitly separate from the
  validated-input precondition; the latter is correctly refused `INPUT_LIMIT` by
  the codec, while the planner's smaller work budget avoids its giant parse.
  A funded unrelated small parse is allowed and remains charged.
- The exact fixed-envelope lower bound `MAX_ELEMENTS - 1 - 2*section_count`:
  one below and exact return work_limit at work0; one above gives `INPUT_LIMIT`
  before parser or row inspection. Thus the final root repair retains the
  Author's additional oversized-row-array refusal-order correction.
- Root cardinalities 0/15/17/20,000/40,000 refuse without set construction;
  wrong names at the lawful fixed cardinality perform only the two bounded sets
  and preserve `MALFORMED_SECTION`.
- More than 37 sampled work stop positions, full-work exact/+1/-1, cumulative
  prior-work exact/short/exhausted retry, exact/short output-byte and unit caps.
  Actual positive partial plans retain completed independent units, while both
  real Collection terminal alternatives are either unchanged together or absent.
  Every emitted plan decodes through the real v5 codec and all emitted rows are
  unchanged originals; input is unmodified. No partial member list is emitted.
- Seven-node lawful cycles succeed; caller container cycles and over-depth
  containers retain `MALFORMED_JSON`/`INPUT_LIMIT` when funded. A known-zero
  budget withholds before the malformed suffix is visited. Explicitly unselected
  Context performs no scanner traversal and charges zero request work.

`supplemental_scanner.py.txt` records **81 successful observation checks**, not
81 pytest cases. It uses new mixed embedded/literal Unicode, control characters
and astral characters: inclusive escaped-byte bound, one below/above, scanner
depth 0/1/30/31/32/33, and work limits spanning actual accepted reservation
prefixes. The structured data is in `supplemental_scanner.json`; exit is 0.

## Code assessment and limits

At `context_dependencies.py:102`, exact root type/cardinality precedes root set
construction. The 16-section list/type/length checks do not visit row contents.
At line 153 the existing shared scanner receives `spend` before traversal. Its
dictionary/list queue growth, per-key escaping, typed identity parsing, embedded
JSON lexical/decode pass and string escaping each reserve before the operation.
Failed reservations stop immediately and charge one fixed refusal unit; they
neither charge the entire unperformed operation nor refund previously accepted
work. The wire element counter remains separate from character-inclusive request
work. With enough work the original byte/depth/element/cycle caps still apply.

The existing downstream planner similarly charges row walks, identity/JSON
reconstruction, dependency visits and copy/output work. A completed closure is
published only after all its prepared row copies exist, and an exception returns
only `completed_rows`; new probes observe independently retained partial plans
without a split terminal group. This review found no unbounded pre-refusal parse
or copied unfinished unit in the new adversarial cases. Logical work units
remain an engineering accounting scheme, not a wall-clock-instruction limit;
no exact complexity or denial-of-service latency benchmark is claimed.

Saved33/new56 and the wider normal/safety/wire scopes are executed and attributed
by the parent/distribution reviewers; this report does not add those counts to
38 or claim their independent artifact results before receiving them. The
38-byte-fixed probes were executed by the distribution reviewer in both actual
installed wheels: each has PASS38 / exit0, exact collection/JUnit/journal and
ordinary phase reconciliation, and recorded site-packages imports. The actual
receipts are in the parent distribution scope as `*fresh-test_m01_new*`; no
source/wheel count is added to another lane. Parent full-suite and hosted failure reconciliation are
separate obligations. No I6-C/I7/I8 route, live Provider, Transfer fence removal,
release, deployment or integration is performed here.

## Preserved probe-development mistakes

Three preliminary receipts remain distinct, compressed and unchanged:

| Receipt | Actual result | Cause and correction |
| --- | --- | --- |
| initial | 9 PASS / 29 FAIL / exit1 | Arbitrary/oversize Provider configuration was correctly rejected before the intended planner call; giant auto parameter IDs also inflated logs. Use real schema and bounded explicit IDs. |
| second | 18 PASS / 20 FAIL / exit1 | Oversize scope exceeded the independent Admission provenance parser's 65,536-byte cap. Valid scenarios now use lawful bounded payloads; hostile oversized caller input is explicitly separate. |
| third | 37 PASS / 1 FAIL / exit1 | The observer incorrectly forbade all small unrelated JSON parses at budget8192. The required property is that the giant/unfunded operation does not run. |

These were reviewer fixture/expectation corrections. They do not establish a
product defect, and none is aggregated into or relabeled as the final PASS38.
All corresponding probe versions are retained as `.py.txt` files. This verified
lesson is already covered by the repository guidance to establish actual typed
preconditions and preserve harness failures; no new skill or reviewed-tree
mutation is needed.
