# Independent non-Author re-review of PR #153

**Verdict: scoped PASS for I6-B and the M01/M02 corrections. Critical 0 / High 0 /
Medium 0 / Low 0 new findings. M01 and M02 may close.** The reviewed I6-B gate
permits a separately authorized I6-C implementation task to start; this review
starts no I6-C/I7/I8 work. Normal Transfer, integration and Release acceptance
remain unqualified. Known unsuccessful tests and packaging limits are preserved.

## Frozen target and independence

| Coordinate | Observed value |
| --- | --- |
| Reviewed #153 HEAD | `61e44291e293f773904a0127606e20c8cb83c95e` |
| Reviewed tree | `4aa8ddf49fb52d0b903db0b0bfce00ccea2fae0c` |
| #153 direct #152 base / merge-base | `8521158f2996f125d2fcaac36ea79ac1296a7cf7` |
| #152 tree | `455ef25606ee555e4154dd2d14929b41aa4ef50f` |
| Actual #153 GitHub test merge | `99477234735b9f45cbb4d0634bb8372eaf120710` |
| Merge ordered parents | #152 `8521158` / #153 `61e4429` |
| Merge effective tree | Exactly the reviewed feature tree |
| New evidence branch | `review/adr0031-i6b-rereview-20261023` |
| New Draft review PR direct base | `fix/adr0031-i6b-m01-m02-20261023` (#153 itself) |

Start metadata, remote heads, CI, recent PRs and review/comment inventories were
reacquired. No newer target or competing same-scope review was substituted.
`TARGET.json`, `broad/initial/` and `ci/` retain these reads. The reviewing agents
are separate from the implementation Author; the authorized shared GitHub owner
account publishes the independent result. Neither the publishing account nor
reuse of attributed tests is presented as independent test design.

AGENTS.md, the applicable investigation/CI/three-store/lessons skills, Accepted
ADR0001/0031/0032, I6 wire/admission/exchange, vectors/tests, change-map/handoff,
#152 REPORT/findings/probes, #153 Author REPORT and actual implementation/test
diffs were inspected. [MATRIX.md](MATRIX.md) maps every R02–R09, V01–V09 and
T01–T27, including deferred C/I7/I8 portions. Seven named Resource row columns
are distinguished from the three-coordinate embedded ResourceKey. Namespace
coordinates supply no Parent report. Original Parent and endpoint evidence,
ordered Relation/Collection alternatives, genuine terminals, positive Source
membership and five-column Coverage/proof meanings remain distinct.

`INPUTS.json` binds all 487 runtime/test/script/workflow/action/configuration
inputs to actual #153 Git blobs. The ordinary driver binds 486, with exactly the
additional composite action covered by the root manifest. All 7,121 unchanged
existing paths are blob-equal to #152 (`broad/protected-scope.json`); changed
existing paths are only the two reviewed product files and two Author skill
updates. The two new Author test files remain unchanged. This review adds only
this new evidence directory: no product, existing test/assertion, Accepted ADR,
safety guard, old evidence or existing skill is modified.

#144/#147/#150 remain open/unmerged, diverge from this target and are not its
ancestors. Their current heads and API ancestry responses are retained in
`ci/sibling-nonintegration.json`. #150 is a documentary simulated-candidate audit,
not proof of actual integration. Nothing was cherry-picked, rebased, force-pushed,
merged, released, deployed or enabled. Only disposable synthetic catalogs were used.

## Finding closure and independent adversaries

**M01 closes in this scope.** The scanner now receives cumulative `spend` before
queue growth, escaping, typed identity parsing and embedded lexical/JSON parsing.
Root type/cardinality precedes set allocation. The fixed envelope's row-count
lower bound preserves necessarily oversized row-array `INPUT_LIMIT` before work
scanning. Failed reservation charges one fixed refusal unit without running the
refused operation; prior work is not refunded. Funded hard caps/cycle refusal and
completed whole semantic units remain intact.

The independently repeated valid 1,001-row fixture changes **1,501 parses /
314,392 characters to zero / zero**. Budgets 0/1/17 and exhausted prior17 charge
1/2/18/18 rather than 26,041/26,041/26,041/26,058. For a preconstructed
20,000-key malformed root, set allocations change **2 to 0**, process-local
tracemalloc peak **1,052,148 to 1,818 bytes**, retaining `MALFORMED_SECTION`.
The new 40,000-key control similarly changes 2,100,580 to 1,514 bytes. These are
individual allocation observations, not stable exact thresholds or elapsed-time
benchmarks. New 38 cases cover Unicode/escaping, huge embedded and malformed JSON,
zero/small/exact/over/prior budgets, byte/depth/cycle boundaries, exact huge-row
refusal ordering, completed partial plans and whole terminal alternatives.
Another 81 scanner observations are controls, not 81 pytest nodes.
See [planner/REPORT.md](planner/REPORT.md) and original measurement/probe receipts.

**M02 closes in this scope.** `decode_package` hashes the bounded received
dictionary before normalizing selection conversion. The shared outer encoder
excludes only top-level `digest_sha256`. Existing selection `to_dict()` remains
the canonical authority; correctly rehashed duplicate/permuted selections refuse
`INVALID_SELECTION`. The unchanged saved30 stale-digest cases now all refuse
`DIGEST_MISMATCH`. New 61 independent cases use a separate raw-dictionary hash
oracle, compound selection changes, nested digest keys, object insertion order,
UTF-8/escape equivalence, NFC/NFD distinction, strict primitive/duplicate-key/
UTF-8 negatives and constructor-entry guards. Canonical positives retain their
digest. Identity, report and outer encoders keep their distinct normative
profiles. Digest integrity supplies no origin, authorization or replay grant.
See [wire/REPORT.md](wire/REPORT.md).

Retained I6-A received new 13 cases (12 behavioral plus one evidence writer).
Foreign service-issued handles fail even with the same principal/policy objects.
Revocation inside the real second endpoint INSERT, actual SAVEPOINT RELEASE
denial and actual deferred outer COMMIT failure retain leases through the reached
boundary and roll back Event plus both endpoints. Finite exact replay exhausts
the shared budget; the next replay refuses without refund. Separate retained
second-INSERT/deferred-COMMIT and normal fence/unconnected-route lanes pass.
Both exact Transfer fences, service-bound current authorization and normal
Provider/Exchange fail-closed behavior remain. Positive isolated fixtures remove
only the verified two stage fences on their private test connection; ordinary
product behavior is never activated. See [admission/REPORT.md](admission/REPORT.md).

## Actual execution and regression comparison

Every row below is a separate invocation or explicitly identified subset.
Overlaps are never added into a full-suite result.

| Scope | Actual result | Exit |
| --- | --- | ---: |
| One complete final #153 ordinary source invocation | **6,344 unique: 6,045 PASS / 279 FAIL / 20 ERROR**, zero skip/xfail/xpass | 1 |
| Separate matched assertion-entry diagnostic | 745: 446 PASS / 279 FAIL / 20 ERROR | 1 |
| Source saved33, byte-identical #152 probes | 33 PASS | 0 |
| Source prior independent normal208 | 208 PASS | 0 |
| Source attributed Author external34 | 34 PASS | 0 |
| New source M01 / M02 / retained-A lanes, individually | 38 / 61 / 13 PASS | 0 each |
| Safety626 / wire212 / correction56 inside the single full invocation | All PASS; I4 217 and I5 29 are included p3-module subsets of safety626 | Full exit1 above |
| Each independent installed form: safety / wire / normal / Author / saved / correction | 626 / 212 / (204+4) / 34 / 33 / 56 PASS | 0 each |
| Each installed form: newly designed M01 / M02 / retained-A | 38 / 61 / 13 PASS | 0 each |
| Each minimal installed form: original Access smoke | 1 FAIL, child and pytest exit1, `PERMISSION_DENIED` | 1 each |
| Independent policy/callsite/schema/boundary/lint/format/report checks | Seven commands succeed | 0 each |

The complete source invocation lasted 509.20 seconds by pytest, has 19,012 normal
phase reports and 57 genuinely passing SubtestReports, and completed normally.
Its all-node collection contains 6,346 nodes; the live and benchmark opt-ins are
the two explicitly unexecuted nodes. Collection, selected IDs, JUnit, append-only
journal, controller report types, actual worker ExceptionInfo frames, process
exit and before/after input bindings reconcile. Generic duplicate-phase predicates
in the reused driver remain false because they conflate subtests with normal
calls; the independent comparator checks the actual report classes and exact
ordinary phases instead. No missing phase, interruption or test is called passed.

The baseline #152 historical full invocation is attributed to its actual
execution HEAD `ef787a5` / tree `a3ed262`; its 484 recorded executable inputs were
independently checked against #152 Git blobs before comparison. It remains
5,989/279/20, not a new baseline execution by this review. The independent parser
in `broad/tools/independent_compare.py.txt` compares the raw old and fresh records:
no removed node, 56 new passing nodes, zero common outcome/phase changes, and the
same 299 unsuccessful node/phase, exception types, refusal codes and actual
project frame-function sequences. One physical coordinate shifts in
`test_empty_oid_and_context_payload_cannot_override_selection`.
Raw JUnit messages differ at 19 temporary-path presentations and rendered
tracebacks at all 299; those raw differences remain saved, not called byte-equal.
`broad/full-comparison/` preserves the full raw-pair inventories.

The separate diagnostic likewise retains 299 unsuccessful signatures, and
**all 745 nodes' all-phase and call-phase assertion AST entry sets match** the
historical 745 reference. This is statement entry on the traced main worker
thread, not subexpression, other-thread or subprocess assertion coverage.
The older #149→#151 three-column malformed fixture's early `MALFORMED_ROW`
instead of `PERMISSION_DENIED`, and the two `[initial]`/`[cached-receipt]` fixture
migrations with unchanged assertions, are historical #152 observations. They are
not new #152→#153 changes, nor proof that their downstream assertions now ran.

The observer captures the original `json.dumps` reference. A preflight actively
replaced the module attribute with a raising function and proved emission still
works. An initial system-Python preflight lacked pytest; it executed no test and
was corrected to the selected venv before testing. No full or diagnostic pytest
invocation was interrupted. Preliminary independently designed fixture mistakes
are separately retained: M01 9/29, 18/20 and 37/1 passing/failing attempts; retained-A
10/1. They are never combined with or relabeled as final passes.

## Distribution, hosted evidence and limits

Fresh direct wheel and sdist-derived wheel builds use the same complete frozen
`61e4429` archive, separate build roots/venvs and external execution directories.
All 164 wheel members, ZIP metadata, metadata/entry points, archive and installed
RECORD rows, and product 160 files / 6,025,551 bytes match. Actual imports resolve
to each external site-packages and child CLI; checkout imports are rejected.
Both wheel SHA256 values are
`2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8`.
Fresh sdist SHA256 is
`88e2496b9335f475bbcaa6857832ce0d9dabc128b10bbf5aa0b08336039d52dc`;
the artifact inventory is authoritative for its exact bytes and size.
The sdist retains 8,159 of 8,279 original files exactly, plus matching PKG-INFO;
120 historical `artifacts/` evidence files remain omitted under existing rules.
Their exact paths/parent blobs are saved. All product/test/build inputs survive.
This is a retained source-evidence limitation, not a claimed all-source archive
or integration of the sibling sdist improvement. Independent artifact hashes
are not silently substituted for the distinct Author or hosted sdist artifacts.

The unchanged original smoke stops at unconnected export. Each installed trace
records 26 assertion statements entered and 28 following assertions unreached.
Its historical v4 assertion is among that unreached tail. This failure is not
hidden by a rewritten fixture, excessive permission, skip or xfail.
See [distribution/REPORT.md](distribution/REPORT.md).

The exact Author feature's hosted runs were independently verified from actual
metadata/logs and receipts: [Development 39975300074](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39975300074)
SUCCESS, [Access 39975300189](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39975300189)
FAILURE. All 21 / 121 indexed receipt payloads match bytes/hash and exact
feature/base/actual merge/tree. Development has zero hosted product pytest and
`full_acceptance=false`. Access main is 2,487/279/20; its overlapping I5 lane is
2,849/279/20, each exit1. All new56 nodes are absent from hosted JUnit.
Actual CI publication-tree builds/installations and both smoke failures were
checked. Access log views each lose 90 bytes; only complementary observed chunks
were aligned to recover the exact 1,953,448-byte original receipt SHA256, with no
inferred bytes. Unsuccessful download/log attempts remain recorded.
Both receipt ZIPs retain every indexed payload; expanded duplicates are omitted
from this delivery as described in `ci/DELIVERY.json`.

Fresh source versus each hosted Access lane also retains the same 299 identities,
phases/outcomes, primary message first lines and refusal-token sets. Full messages
match 280/299 and rendered project-frame projections 135/299; raw traceback text
matches 0/299. Hosted actual ExceptionInfo/assertion tracing was not captured.
`ci/source-hosted-comparison.json` and raw pairs preserve those limits rather
than treating them as identical complete hosted tracebacks or assertion coverage.

Source uses Python 3.12.14 / its actually loaded SQLite 3.53.1; hosted uses
Python 3.12.15 / SQLite 3.53.1. Source IDs/options/import origins are measured.
No alternative SQLite was obtained, built, installed, swapped or required.
Final evidence-PR HEAD/tree and CI are externally bound in its PR body and final
handoff, avoiding a circular committed self-hash. Development success verifies
only its selected checks. No Release workflow or full hosted acceptance is claimed.

Remaining conditions are the unchanged 299 unsuccessful source cases, original
smoke, historical sdist evidence omission, two opt-ins, and future authorized
C/I7/I8, integrated-runtime and Release gates. These known deferred boundaries
do not reopen the two corrected I6-B contracts. Both fences remain mandatory.

## Evidence and reproducibility

`ARTIFACTS.json` indexes every delivered payload. `TRANSPORT.json` and each scoped
transport preserve original and compressed bytes/hashes; `.py.txt` files keep
probe code outside ordinary collection. [REPRODUCTION.md](REPRODUCTION.md)
describes invocation and restoration. The final verdict does not depend on
count equality alone. No new skill was created: existing procedures already
cover typed preconditions, harness mistakes and raw-frame comparison. The
verified encoder-capture preflight is recorded as a recommendation in
[LESSONS.md](LESSONS.md), without mutating the frozen reviewed tree.
