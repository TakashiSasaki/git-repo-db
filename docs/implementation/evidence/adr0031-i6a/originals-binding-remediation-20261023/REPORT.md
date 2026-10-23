# Task A: complete-original and source-binding remediation

ORIGINALS-M1 and I6A-IR-L01 are corrected by this implementation. The saved
malformed-carrier counterexample now refuses all four initial/replay cases in
source, direct wheel and sdist-derived wheel. Non-Author re-review remains
required; this report does not declare independent I6-A acceptance or Release
acceptance. Ordinary Transfer remains fenced.

## Frozen lineage and execution identity

| Role | Commit | Tree |
| --- | --- | --- |
| PR #145, historical reference | `08fbb956c2e470e245146b0dbae747ed0690ea40` | `7072f952975a8537f74ced1bbc2a4a31d7aa3690` |
| PR #146, fixed Task A base | `274645e7dd451e24f324feb81b1591a64ba2a7ab` | `773c7de12d2ea564aeabe4c87a980e4fe438ce1f` |
| Actual Task A source/test/build freeze | `f777d195bd219398a51d2a90553377f61fb39370` | `7ccc8685e06253e2102d46369110c7150d34a587` |

Base branch is `review/adr0031-i6a-remediation-independent-20261023`; new branch
is `fix/adr0031-i6a-originals-binding-20261023`. The tested commit has #146 as
its sole parent. The final publication adds evidence and a procedural skill
update; its exact HEAD/tree and selected GitHub Actions are recorded externally
in the PR body. A report cannot embed the Git tree containing itself.

Start-of-task GitHub search found #146 latest and no duplicate remediation.
The final pre-submission check is retained separately. #143/#145/#146, Accepted
ADRs and frozen evidence are unchanged. Task B / #139 and Task C independent
re-review were not started here. #142/#144 sdist changes are intentionally absent
from this ancestry; no unrelated series was merged or cherry-picked.

Python 3.12.14 loads its environment's actual built-in SQLite 3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Runtime receipts record executable, compile options, PRAGMAs, UDFs, schema,
fingerprints and integrity checks. No SQLite library was downloaded, built,
installed, replaced or matrix-tested. The full and diagnostic runs bind all
480 execution-input hashes to frozen Git and the executing checkout, with empty
tracked status before/after. Later publication preserves these input bytes.

This is implementation-author verification. Existing #146 probe/policy/tracer
and execution helpers are attributed reuse; their new executions are not
independent acceptance. No merge, release, deployment or fence retirement occurred.

## Changes and refusal ordering

The shared `admission_checked` wrapper covers real raw Store and facade Transfer
intake, including initial and replay calls. It first accounts bounded input and
enumerates supplied dependencies without SQL, then validates current service
authority, lease and selection. It calls the canonical `validate_originals()`
before Source/resource/Parent/mapping lookup, serialization, writes or duplicate
success. Previously successful construction is no longer treated as a seal on
caller-owned nested state. The existing validator reconstructs the report and
its original Parent and endpoint declarations; no replacement validation system
or fallback authority was added.

The canonical constructor now gives `INCOMPLETE_ORIGINAL_REPORT` for missing or
wrongly typed nested Parent keys and required original coordinate fields.
Dependency enumeration traverses the actual ParentReportKey dataclass once,
rather than dereferencing a malformed Transfer convenience property first.
Non-text missing Parent coordinates yield no invented dependency and are refused
after current authority. They are never stringified, repaired or borrowed from SQL.
Valid Parent membership/provenance dependencies still pass the existing denial,
selection, source-scope and native-Issue tests.

Current authorization and selection still precede permanent native semantics,
which precede missing-dependency diagnostics. Normal Transfer stage refusal is
preserved, including the saved malformed-endpoint ordinary-fence controls.
Legitimate one-sided, two-sided, explicit-NULL and Provider-only reports preserve
their original semantics, immutable key, clocks, provenance and independent
Parent observation time. No I6-B/C/I7/I8 implementation is added.

The classifier now resolves plain/gzip transport before presence checks and
requires both complete source bindings on every audited run. Missing either or
both, incomplete head/tree/input SHA-256 inventory/status, or any mismatch makes
`consistent=false` and raises an explicit inconsistent-run error. Both missing is
a provenance failure under the run audit contract, not permission to omit it.
Frozen compressed evidence and separate negative copies are actually re-read.

## Actual measurements

These overlapping lanes are never added into a unique-coverage total.

| Invocation / lane | PASS | FAIL | ERROR | Exit / scope |
| --- | ---: | ---: | ---: | --- |
| Task A ordinary, **one complete invocation** | 5,777 | 279 | 20 | 1; all 6,076 ordinary nodes |
| Original743 diagnostic, one separate invocation | 444 | 279 | 20 | 1; assertion/admission tracing |
| Source safety + classifier | 653 | 0 | 0 | 0; exact selected/JUnit/journal |
| Direct installed safety | 626 | 0 | 0 | 0; historical551 + new75 |
| Sdist-derived installed safety | 626 | 0 | 0 | 0; same exact selected set |
| Reused #146 authorization/SQL, source | 27 | 0 | 0 | 0; staged outside frozen evidence |
| Same authorization/SQL, each installed form | 27 | 0 | 0 | 0 per form |
| Classifier focused unit controls | 27 | 0 | 0 | 0; synthetic controls plus actual frozen evidence |
| New original-intake focused tests | 75 | 0 | 0 | 0; included in larger lanes |

All completed passing lanes have zero skips/xfails/errors. The full run has zero
skips/xfails and retains four warnings and **57 passing unittest subtest reports
separately**. The old generic reconciliation flags for duplicate phases/call
counts remain false because they cannot distinguish subtests. The typed sidecar
audit reconciles every ordinary node and main phase plus all subtest records;
those legacy flags were not rewritten as true.

The unchanged saved originals probe executes 19 passing standalone assertion
cases in source and each installed form; these are not 19 additional pytest
nodes. The unchanged saved invalid-carrier probe has four required refusals and
two successful ordinary-fence controls per form. Before editing #146 source, its
actual replay reproduced zero required refusals, initial `insert` and replay
`duplicate` (exit1). That fresh failure and all SQL rowsets are retained.

The new 75 tests cover from/to None and invalid strings; missing/wrong Parent
originals, nested keys and required Parent coordinates; initial and replay at
Store and facade; current denial and revoked replay; lawful declaration states;
and coherent same-key changed-original conflict. Refusals compare every
persistent table, forbid dependency reads and INSERTs, and check transaction and
lease release. Source and both installed lanes export full synthetic SQL traces
and rowsets, including preexisting immutable rows.

I4's exact 217 SQL nodes and I5's exact 29 admission nodes run in the source
safety and each installed safety lane. Existing finite grants, read-only/expired
capabilities, current revocation, transaction leases, real second-endpoint INSERT
failure and real deferred COMMIT failure all pass. In-flight faults actually reach
the Event/first endpoint or COMMIT and roll back the entire intended unit. These
are distinct from pre-SQL malformed-original refusals.

## One-run comparison and remaining299

#146's actual raw full invocation is **5,656 PASS /276 FAIL /42 ERROR**, not
5,675/279/20. The latter #146 node-wise map combines four ordinary invocations
and has separate provenance. Both are compared independently with this new
single invocation; they are not relabeled or summed. The historical #145 full
result is only a reference, never a target count imposed on execution.

All original 5,974 identities remain; the 102 additions are the 75 original
intake and 27 classifier tests. No preexisting test or assertion was edited,
skipped or xfailed, and no fixture grant was broadened. The comparison preserves
raw messages, exception/refusal codes, phase, trace hashes and source-resolved
boundary changes. The old raw cache errors and timeout remain failed evidence
in the unchanged #146 archive.

Exactly23 outcome/phase differences from that raw invocation are explained by
actual traces:22 old read-only UV-cache setup errors now reach18 PASS and four
genuine I6-C failures; the old30-second query timeout now passes. All existing
outcomes/phases agree with the separately combined #146 latest map. Thirteen
full-run I7 messages truncate the caught MergeReceipt representation differently;
the initial unresolved-parser output is retained, and current diagnostic stacks
resolve their actual boundary without replacing any full-run outcome. Literal
message equality is not asserted where only the supported causal projection agrees.

The separate743 diagnostic reproduces every prior outcome/phase and actual
assertion-entry set: 411 nodes enter local literal assertions, including375 of
the444 passing nodes; 36 of the299 unsuccessful nodes enter local assertions.
This is statement-entry evidence, not branch/subexpression or child/thread
coverage. Setup errors do not establish test-body assertions. All14 I7 failures
have actual current caught admission stacks; rejected salvage receipts do not
establish functioning Recovery composition.

Exactly16 Transfer first boundaries move earlier from raw/facade method bodies
to the shared checked boundary, retaining the same typed stage refusal, phase
and assertion-entry set. Ten were raw Store and six facade calls. Complete old/new
source coordinates and IDs are in `first-boundary-changes.json`; line movement
alone is not treated as semantic equivalence or a new defect.

The unresolved299 remain **242 I6-C /14 I7 composition /43 Transfer-stage**.
No later-stage functionality is accepted by assigning ownership. One live node
and one benchmark node remain deliberately unexecuted; their exact IDs are in
the ordinary inventory. No new product regression is hidden by a selection change.

## Installed artifacts and input scope

Both builds use a fresh Git archive of the frozen tested commit. Separate external
venvs install direct and independently sdist-derived wheels with hash-verified
locked dependencies. Product origin and every loaded module path are checked
inside collection, pytest execution and each standalone probe; none imports the
checkout product. Every158 product file, including GraphQL, agrees across frozen
source, wheel members and installed bytes before/after. Every wheel RECORD entry
and direct/derived member byte agrees. Exact packaged schema, both Transfer
fences, FK checks and integrity_check are verified.

Direct and derived wheels each have778,384bytes and SHA-256
`b92078f0153c187dd5d06773b75d98e134970694a79a58534b59c4f8503da878`.
The tested sdist has118,388,592bytes, SHA-256
`293852d70522df5529d98d275d218ab489f38a86deb774fb10de4a59ac2edce0`.
Complete build-source5218-entry and sdist5219-member inventories are saved,
separately from the480 execution inputs. The large full sdist retains the
intentional pre-#142 ancestry; it is not claimed minimized/hardened by this task.
Final evidence/skill publication changes full source archive/sdist bytes and
was not rebuilt or release-qualified. Runtime-input equality alone does not
qualify that later full archive.

## Preserved unsuccessful setup and iterative work

* The initial source regression-test creation run had44 PASS/1 FAIL because its
  conflict vector changed Event time without coherently changing endpoints. It
  failed during construction, before Store admission. The corrected vector changes
  the independent Parent time, retaining the conflict assertion. Raw first-run
  JUnit/journal/log remain; they are not final-tree acceptance evidence.
* A classifier unit launch used the base Python before pytest was installed in
  it and exited1 at bootstrap. The selected locked venv then executed the tests.
* The initial installed driver built both artifacts successfully but both offline
  installs exited2 on a read-only default uv cache, before installed tests. A new
  output directory with parent-level writable UV_CACHE_DIR succeeded. All source,
  sdist/member and artifact bytes agree across retries; old logs are unchanged.
* Relocating an external diagnostic wrapper exposed an eager default Path.parents
  IndexError before collection. The corrected external wrapper is retained; the
  first exception and exact observed correction remain. An initial-driver hash
  was not captured and is not invented.

Full, diagnostic and installed workloads overlap in time. Elapsed values describe
their actual invocations and are not sequential benchmark measurements. Failed
executions remain failed; supplementary successes never overwrite them.

## Evidence and next review

`raw-evidence.zip` and `raw-index.json` preserve actual commands, exits, selected
IDs, JUnit, journals, typed sidecars, assertion/admission streams, SQL rowsets,
import/module bindings, complete build inventories and analysis scripts. Frozen
baseline files are referenced from #146 and are not overwritten. The artifact
checker verifies all indexed bytes without executing or blindly extracting ZIP
contents. Detailed reproduction is in `REPRODUCTION.md`.

The local efficient-investigation, ci-final-tree-verification and
lessons-to-skills procedures were used. The existing CI verification skill gains
the verified real-intake/gzip-binding and inherited-uv-cache lessons, with stable
regression commands and no additional policy or approval requirement.

Next: a separate non-Author thread must review the final PR/effective tree,
reproduce malformed first/replay cases and missing/mismatched compressed bindings,
inspect refusal precedence/zero writes/SQL rollback and both installed forms,
and retain all299 unresolved downstream cases. The parent initiates Task C.
No requested action remains denied or awaiting user approval at publication;
final GitHub publication/CI status is stated in the PR body and task handoff.
