# Task C: independent re-review of PR #148

**Verdict: scoped PASS for I6-A.** ORIGINALS-M1 (Medium) and I6A-IR-L01 (Low)
are independently verified closed. Open/new findings: Critical 0, High 0,
Medium 0, Low 0. The I6-A independent-review prerequisite for starting I6-B is
satisfied. I6-B may proceed within the approved staged plan; this review does
not implement or accept I6-B/C, I7, I8, ordinary Transfer or Release acceptance.
Both Transfer fences remain mandatory.

## Exact target and independence

| Role | HEAD | Tree |
| --- | --- | --- |
| Reviewed #148 public HEAD / sole review parent | `268025f67841285d105737b5a0d7bd15b1a6f59c` | `e5fa0437f19f31fa414d488ec10f483ef68f03fa` |
| Author's execution/build source | `f777d195bd219398a51d2a90553377f61fb39370` | `7ccc8685e06253e2102d46369110c7150d34a587` |
| Prior independent FAIL #146 | `274645e7dd451e24f324feb81b1591a64ba2a7ab` | `773c7de12d2ea564aeabe4c87a980e4fe438ce1f` |
| Prior remediation #145 | `08fbb956c2e470e245146b0dbae747ed0690ea40` | `7072f952975a8537f74ced1bbc2a4a31d7aa3690` |

A new delegated non-Author review thread used a clean dedicated checkout and
branch `review/adr0031-i6a-task-c-20261023`, directly based on
`fix/adr0031-i6a-originals-binding-20261023`. Live GitHub metadata confirmed
#143 → #145 → #146 → #148, the assigned public HEAD, two commits and 22 changed
files. Initial search found no duplicate review and #148 had no submitted
reviews. The repository owner's connected account publishes this authorized
review; independence means separate agent work, not a different human account.

AGENTS.md, the ADR index and applicable Accepted ADR0031/0032 and I6 contracts
were read. Local efficient-repository-investigation, ci-final-tree-verification
and lessons-to-skills procedures were used. The read-only source, Accepted ADRs,
existing tests/assertions, workflows and historical evidence are unchanged.
#147, #142 and #144 heads were fetched and independently confirmed absent from
reviewed ancestry. They were not merged, cherry-picked or rebased.

New code includes an independent stdlib receipt parser (no Author classifier
import), 132 new intake/precedence/positive vectors, four explicit foreign
allow-all-handle vectors, 13 actual-evidence binding controls and independent
wheel/installed audits. Existing #146 finite policy, report/SQL setup and saved
counterexamples are attributed reuse. Execution and diagnostic drivers adapt
indexed #146/Task A helpers; reuse alone is not presented as independence. New
executions, the separate parser and new counterexamples establish the results.

## Independent measured execution

These lanes overlap and must not be added into a unique-coverage total.

| Actual invocation / scope | PASS | FAIL | ERROR | Exit |
| --- | ---: | ---: | ---: | ---: |
| **One complete ordinary execution** | **5,777** | **279** | **20** | **1** |
| Separate original743 assertion/exception diagnostic | 444 | 279 | 20 | 1 |
| Reused independent #146 authorization/SQL, source | 27 | 0 | 0 | 0 |
| New Task C intake/precedence/positive vectors, source | 132 | 0 | 0 | 0 |
| Explicit foreign allow-all handle vectors, source | 4 | 0 | 0 | 0 |
| Direct installed safety, including I4 217 / I5 29 | 626 | 0 | 0 | 0 |
| Sdist-derived installed safety, same exact cohort | 626 | 0 | 0 | 0 |
| Authorization/SQL, each installed form separately | 27 | 0 | 0 | 0 |
| New intake/precedence/positive vectors, each form | 132 | 0 | 0 | 0 |
| Foreign allow-all handle vectors, each form | 4 | 0 | 0 | 0 |

All completed lanes have zero skips/xfails. The full run selected/executed 6,076
unique ordinary nodes exactly once; all 5,974 prior IDs remain and all 102 added
product-regression nodes pass. The full run independently matches every Author
node's outcome and phase. Collection, JUnit, journal starts, typed report phases
and actual process exit reconcile. Its 57 passing unittest subtest reports are
additional measured phases: 18,208 ordinary reports plus 57 subtest reports.
Legacy duplicate-phase predicates remain false; they were not rewritten into
success. Independent typed reconciliation preserves every report.

The saved originals probe separately passes 19 standalone assertion cases per
source/direct/derived form. The saved invalid-carrier probe separately gives four
`INCOMPLETE_ORIGINAL_REPORT` refusals and two ordinary-fence controls per form.
These are not additional pytest nodes. The 13 new binding controls are separate
stdlib checks. Runtime values describe separate invocations, not benchmarks.

## ORIGINALS-M1 closure and safety

A fresh source-bound reproduction on unchanged #146 still produces two initial
`insert` and two replay `duplicate` outcomes, zero required refusals and two
working normal-fence controls (expected exit1). Its actual imported modules are
bound to the separately archived #146 source. The same saved probe on #148 and
both freshly built installed forms instead refuses all four cases before writes.
The original constructor/replace/validator controls still reject malformed input.

The new vectors traverse real ContextStore transactions and the owned facade.
They cover invalid from/to endpoint values, an absent/wrong declaration object,
absent Parent originals and keys, missing Parent Resource and missing/wrongly
typed original member/provenance/scope coordinates. Both initial and replay paths
are exercised. For each malformed carrier, current permission denial precedes
selection omission, which precedes `INCOMPLETE_ORIGINAL_REPORT`. No malformed
carrier becomes insert or duplicate. Complete persistent rowsets remain equal,
no dependency-content SELECT or mutation SQL occurs in the input observation
window, transactions close and leases release. Grants remain finite and unchanged.

Independent one-sided, two-sided and explicit-NULL positives insert and replay
as duplicate through both APIs, preserving exact readback and rows. The saved
19-case probes additionally preserve independent Parent clocks/provenance/time,
Provider-only unresolved state, changed-original conflict and no reconstruction
from surviving/local rows. Ordinary normal-fence controls retain the exact two
packaged trigger definitions and return `I2_TRANSFER_UNSUPPORTED`.

The reused 27-case independent policy/SQL tests and actual 626-node safety
cohorts verify service-bound contexts, forged/mutated principals, foreign issuer
handles, finite selection, each dependency grant, replay revocation, lease
retention through successful and duplicate COMMIT, and actual second-endpoint
INSERT/deferred-COMMIT failures. Observations reach Event plus first endpoint or
COMMIT before rollback; they are not preflight-only simulations. Whole-unit
changes roll back, preexisting originals remain and actual work is charged.
Four further new allow-all-port counterexamples use a foreign service issuing
an otherwise matching principal: Store/facade initial/replay all refuse before
either policy callback or content access, with equal full rowsets.

I4's 217 actual SQL cases verify native-I7 constraints, full Parent/Event FKs,
immutable originals, exact endpoint references and SQL atomic boundaries. I5's
29 actual cases verify their semantic admission and strict pre-affinity inputs.
The executed fence cohort covers both exact triggers, either missing, altered,
uninspectable and both absent; absence is accepted only by the explicit expiring
fresh-memory fixture. Normal opening, disabled PRAGMAs and invalid UDF profiles
remain refused. The executed ordinary Provider/import/export controls fail closed
before resource lookup, progress/cached-success reuse or implicit authority.

Code review confirms the canonical complete-original validator runs after
bounded accounting and current authority/selection, before dependency lookups,
serialization, writes and duplicate success. Parent dependency traversal no
longer dereferences malformed convenience properties. It never invents a missing
original or borrows an Event coordinate or SQL row. No production fence or guard
was weakened.

## I6A-IR-L01 closure

Both actual published gzip-only #146 run directories reproduce the old helper's
false `consistent=true` with null bindings and an omitted binding check. The
fixed helper reloads both complete bindings. Independent Git-blob hashing verifies
all **480** runtime/test/script/workflow/configuration input bytes against the
Author freeze and public #148; all match. Source/test/workflow input sets and
before/after tracked status are also bound to the actual new executions.

Thirteen new actual-evidence controls cover matching compressed bindings,
missing before/after/both, changed head/tree/input hash/status, empty input maps
and equally missing required fields. Only the matching control is accepted;
all others explicitly fail the source-binding predicate. Neither frozen gzip
artifact is rewritten. All 227 Author ZIP member lengths and SHA-256 values were
also independently checked, in addition to its 14-payload checker.

## Full regression and actual first boundaries

#146's **one raw full invocation** is 5,656 PASS / 276 FAIL / 42 ERROR.
Its 5,675 / 279 / 20 latest map combines four invocations. This review parses and
compares both separately; neither replaces the current single full execution.
There are 23 raw outcome/phase differences: 22 old read-only uv-cache setup
errors now reach 18 PASS and four genuine I6-C failures, and the old timed-out
query now passes. No outcome/phase differs from the separate prior latest map.
Raw messages and traces remain available, including wrapped/truncated I7 receipts.

The fresh743 diagnostic and source-resolved exception stacks independently
classify the remaining 299 as **242 I6-C / 14 I7 composition / 43 Transfer-stage**,
with no unresolved/new category. All 743 outcome/phase and actual local literal
assertion-entry sets match #146. Of743 nodes, 411 enter local assertions; 375 are
among 444 passing nodes and 36 among 299 unsuccessful nodes. These are statement-line
entries, not subexpression, thread or spawned-process coverage. Setup errors do
not establish body assertions. All 14 I7 cases have current caught admission stacks;
a rejected salvage receipt does not establish Recovery composition acceptance.

Exactly 16 first boundaries move from Store/facade method bodies to the shared
wrapper (ten raw Store, six facade). `boundary16-proof.json` binds every ID to an
actual `UnsupportedResourceStage`, code `I2_TRANSFER_UNSUPPORTED`, failed call
phase, original/new source statement and identical reached assertion lines.
Input validation/current authority remain before the wrapper's stage refusal;
dependency lookup and mutation remain after it. Separate full-rowset, privacy,
normal-fence, lease and actual SQL rollback controls above verify this safety.
Later assertions in those failed tests stay unproved.

## Fresh public-HEAD distributions and environment

The selected Python is 3.12.14 with its environment's built-in SQLite 3.53.1,
source ID `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Actual executable/base executable, SQLite origin/options, schema/UDF/PRAGMA and
integrity receipts are retained before/after and inside pytest. No SQLite was
obtained, built, installed, replaced or matrix-tested.

Both distributions are newly built from a clean Git archive of public #148,
then installed into separate external venvs with locked hash-verified offline
dependencies. All 158 source/product/wheel/installed files, every wheel member and
RECORD digest match. Actual collection/execution/probe imports resolve inside the
corresponding site-packages. Direct and derived lane node multisets match.
Schema fingerprints, full expected schema, both exact fences, native UDFs,
foreign_keys/recursive_triggers, FK check and integrity_check pass in both forms.

Both wheels are 778,384 bytes, SHA-256
`b92078f0153c187dd5d06773b75d98e134970694a79a58534b59c4f8503da878`.
The **new public-HEAD sdist** is 122,823,537 bytes, SHA-256
`b54c8896685e1982a1f2405acfdbc4cd54d7084eea9ad59775a2613fbc063b5f`.
Its 5,234 members and the 5,233 build-source entries are completely inventoried;
every source entry is independently checked against frozen Git. The Author's
execution source had 5,218 entries and its sdist 5,219: publication adds 15 evidence
files and changes one skill. Full archive/sdist bytes differ; runtime-input and
wheel equality do not imply full-distribution equality. This task actually rebuilt
and exercised public #148's forms, without claiming #142/#144 minimization or
qualifying the later review-evidence tree's whole sdist.

## Hosted checks, attempts and limits

#148 Actions run 39931207892 has successful offline and sqlite-policy jobs.
Actual logs and the decoded checksum/index-verified receipt bind feature
`268025f...`, temporary merge `72c31e3bd992158ce7cd7c84b419d6dc2d31bd3a`
and effective tree `e5fa043...`. It reports `development_checks_passed`,
`full_acceptance=false`, pytest executed 0. Lint/format, runtime/doctor,
composed-schema and policy checks succeeded. This is not hosted complete testing.
The review PR's final HEAD/tree and its selected CI are recorded in its PR body.

Preserved unsuccessful attempts are explicitly excluded from passing lanes:

- Initial generic fetch refreshed only main; explicit feature fetch then succeeded.
  This was a refspec issue, not an access denial.
- The first external source collection exited3 because the sidecar output variable
  was unset. No tests ran. A fresh directory with distinct collection/execution
  sidecars fixed it.
- The next source run had 129 PASS/3 FAIL: normal-fence facade controls incorrectly
  retained an isolated-fixture wrapper after restoring the fenced schema. The
  normal factory correctly refused its inconsistent wrapper/schema profile.
  The corrected test validates the complete restored schema on the raw synthetic
  connection before the normal factory; all 132 then pass. No product assertion
  or guard was relaxed.
- The first installed driver passed 626 and 27 per form, then its collection helper
  filtered the new 132 fileless IDs because they were outside `tests/`. Those132
  were collected but not executed, and later lanes were unexecuted in that attempt.
  A fresh conventional test-package harness completed every lane. All three
  artifact hashes are identical across builds/retries.
- An initial postprocessing check assumed one too many source/sdist entries and
  failed. The corrected independent audit verifies the measured entire manifest
  against Git rather than imposing guessed counts. Raw failure/script are kept.
- Known-bad baseline probes intentionally exit1; they are not current-product
  failures or passing ordinary-suite replacements.

One live node and one benchmark node remain unexecuted:
`tests/live/test_smoke.py::test_selected_repository` and
`tests/e2e/test_github_sync.py::test_nested_pagination_stress_workload`.
Hosted release dispatch, complete hosted suite, I6-B/C/I7/I8 acceptance and ordinary
Transfer activation are unexecuted. The 299 unsuccessful ordinary nodes remain
unsuccessful. No merge, release, deployment, real-data recovery, force-push or
implementation-author branch modification occurred.

No action is denied, pending approval or of uncertain outcome at local completion.
Publication status is verified separately in the PR. See findings.json,
REPRODUCTION.md, full/diagnostic/installed summaries, criteria.json and the indexed
raw evidence. LESSONS.md records scoped recommendations without mutating the
reviewed skill/source tree.
