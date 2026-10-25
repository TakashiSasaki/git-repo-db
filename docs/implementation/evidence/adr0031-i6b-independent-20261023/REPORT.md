# Independent review of PR #151: I6-B generalized wire v5

**Verdict: FAIL. Critical 0 / High 0 / Medium 2 / Low 0.**
I6B-IR-M01 violates the configured/cumulative work boundary; I6B-IR-M02 violates
the checksum's binding to the received dictionary. Both reproduce in source and
both newly built installed forms. **I6-C must wait for Author corrections and
independent re-review.** This review starts no I6-C/I7/I8 work and retires no
Transfer fence. Other successful scopes below do not close these findings.

## Exact target, independence and protected scope

| Coordinate | Frozen value |
| --- | --- |
| #151 public feature HEAD | `ef787a5ff8b13f118d6bf5107c7338f43fde56dc` |
| Feature tree | `a3ed2628a98db134bdc65d13da905f5ddf25e972` |
| #151 actual branch / new review PR base | `impl/adr0031-i6b-generalized-wire` |
| #151 parent #149 HEAD | `ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00` |
| #151 parent branch | `review/adr0031-i6a-task-c-20261023` |
| Merge base | `ea43a21fca1dbf8fa6dd1c254b28a96d5dd28d00` |
| Actual GitHub test merge | `54464ad882ee644ff37f0af0a3a8d5af52f9f7ec` |
| Actual merge parents, in order | #149 `ea43a21` / #151 `ef787a5` |
| Actual merge tree | Feature tree exactly |
| New review branch | `review/adr0031-i6b-independent-20261023` |

Live public metadata, branch roster, CI and duplicate-review search were reacquired
before verification. The assigned HEAD/tree/base match; no newer Author target
was substituted. No submitted review or competing I6-B review was found at start.
`TARGET.json`, `raw/pr151-start.json`, `raw/pr149-start.json` and the remote-head
snapshot retain the observations. A broad substring initially matched the older
I6 design boundary PR #134; it is explicitly excluded, not silently called an
I6-B implementation review.

The delegated reviewer and five scoped review agents are separate from the
implementation Author. The connected repository-owner account publishes the
authorized result; a shared publishing account does not make the Author perform
this review. New wire/planner fixtures, independent reachability and raw-digest
oracles, new authority/COMMIT probes and new receipt parsers supplement attributed
existing tests. Author reports are claims to compare, not acceptance authority.

AGENTS.md, the ADR index, applicable local skills, Accepted ADR0001/0031/0032,
the I6 wire/admission/exchange design, vectors-and-tests, change-map-and-handoff,
#149 independent review, #151 Author report and actual changed code were read.
The local efficient-repository-investigation, ci-final-tree-verification,
three-store-invariants and lessons-to-skills procedures were used where relevant;
ADR0032 supersedes older skill examples requiring another SQLite engine.

The reviewed product, all existing tests/assertions, Accepted ADRs, historical
evidence and existing skills remain unchanged. Only this new evidence directory
is added. #144, #147 and #150 were fetched and proven **not ancestors**; no sibling
implementation/audit was integrated. No existing PR modification, rebase,
force-push, merge, live acquisition, release, deployment, catalog mutation or
Transfer activation was performed. All databases are disposable synthetic state.

`INPUTS.json` independently binds all 485 selected runtime/test/script/workflow/
action/configuration files to the actual Git blobs. The inventory SHA256 is
`32bc049e2ba765c04b81f6a15ccebd7837aa2d1349bfaea7f24d749e64161389`.
Execution-specific inventories and origins additionally bind each invocation.
The broad driver binds 484 inputs; the root inventory adds exactly
`.github/actions/product-python/action.yml` (see `raw/input-selector-difference.json`).
No count equality is substituted for byte equality.
The evidence-only final review HEAD/tree and its Development CI are externally
bound in the new PR body/final handoff; a committed file cannot contain its own
final Git tree hash.

## Contract-blocking findings

**I6B-IR-M01 — Medium: work limit checked after full embedded-input reparsing.**
`context_dependencies.py:106` finishes `_bounded_json` before checking max_work
at line 127. An already codec-validated Context with 500 Resources and 500 reports,
all selection dimensions empty, still performs 1,501 embedded JSON parses over
314,392 characters and reports 26,041 work units for each configured limit 0, 1
or 17. An exhausted prior_work balance behaves the same. The 24 independent
scaling observations distinguish substantive input-proportional work from fixed
envelope/refusal overhead. Three unchanged required-bound assertions fail in
source and each installed form. Global hard caps still ensure finite stopping
and no partial output is emitted; they do not implement R04's configurable work
ceiling. Constrain scanner/parser/queue allocation by remaining work before doing
it, retain actual charges and whole units, and pass the saved exact/boundary/
exhausted-retry controls without weakening them. See [planner report](planner/REPORT.md).

**I6B-IR-M02 — Medium: checksum binds normalized selection, not received dictionary.**
`decode_package` converts the received selection before verifying the checksum;
`ExchangeSelectionScope.to_dict` sorts/deduplicates its five set arrays, and
`_canonical_content` hashes the reconstructed dictionary. Appending a duplicate
or permuting entries changes the actual canonical received-dictionary hash but
the old digest is accepted. All 30 five-dimension/two-mutation/three-carrier
required-refusal probes fail in source and both installed forms. Conversely,
standalone probes supplying the actual changed-dictionary digest are refused.
The same mechanism is independently reproduced in #149 v4: it is inherited,
but remains incompatible with the newly frozen v5 R03 contract. No Provider
authentication or authorization bypass is claimed. Verify the actual bounded
received dictionary before normalization, or reject noncanonical set arrays
without silent repair; retain valid canonical positives and both fences. The saved
regressions require `DIGEST_MISMATCH`; raw-dictionary verification should pass
them unchanged. If an alternative early canonicality refusal uses a different
contract-valid typed code, submit an explicit reviewed outcome/node mapping and
retain these original failed receipts; do not call their unchanged assertions
passed. See
[wire report](wire/REPORT.md), raw vectors and `raw/root-digest-confirmation.json`.

`findings.json` records source anchors, reproduction artifacts and correction
acceptance conditions. [MATRIX.md](MATRIX.md) allocates every R02–R09, V01–V09
and T01–T27 obligation, including shared/deferred stages and unexecuted assertions.

## Actual independent execution

The lanes below are separate, overlapping invocations. They must not be summed
or combined with Author snapshots into a unique full-suite result.

| Invocation | Actual result | Exit |
| --- | --- | ---: |
| Complete ordinary final-publication source | 6,288 unique: 5,989 PASS / 279 FAIL / 20 ERROR | 1 |
| Matched original assertion/exception diagnostic | 745: 446 PASS / 279 FAIL / 20 ERROR | 1 |
| Independent wire/Source/Coverage | 157 PASS, zero failure/error/skip/xfail | 0 |
| Separate independent resolved V07 alternatives | 4 PASS | 0 |
| Independent planner oracle | 28 PASS | 0 |
| Independent work-budget contract probes | 3 FAIL at required-bound assertions | 1 |
| Independent received-digest contract probes | 30 FAIL at required-refusal assertions | 1 |
| Retained admission/fence/coordinator/originals | 237 PASS | 0 |
| New authority/COMMIT + attributed prior independent authorization | 46 PASS = 19 new + 27 reused | 0 |
| Legacy malformed-v5 versus canonical-v5 first-boundary controls | 2 PASS | 0 |
| Source Author external probes, attributed reuse | 34 PASS | 0 |
| Independent lint/format/policy/schema/callsite/boundary commands | Six successful commands | 0 each |
| Each direct/derived wheel, separately: safety | 626 PASS (I4 217 / I5 29 included) | 0 each |
| Each direct/derived wheel: Author wire/planner | 212 PASS | 0 each |
| Each direct/derived wheel: initial independent probes | 204 PASS = wire157 / planner28 / admission19 | 0 each |
| Each direct/derived wheel: separate resolved V07 probes | 4 PASS | 0 each |
| Each direct/derived wheel: unchanged Author external probes | 34 PASS | 0 each |
| Each direct/derived wheel: new work/digest contract probes | 33 FAIL = work3 / digest30 | 1 each |
| Each minimal installed form: unchanged original Access smoke | 1 FAIL, child exit 1, at unconnected export | 1 each |

The final exact collection, JUnit, append-only journal starts/phase reports,
commands, process exits and input bindings are retained by each subreport.
Independent probe files use `.py.txt` transport to avoid altering ordinary
collection. Runtime paths in the receipts identify actual source or site-packages
imports. Zero skipped/xfail results are asserted only for completed lanes whose
raw evidence establishes them.

One complete final-source invocation (`broad/full-final-v3`) selected and executed
6,288 unique ordinary IDs exactly once: 5,989 PASS / 279 FAIL / 20 ERROR, exit1.
The all-node inventory is 6,290; two live/benchmark opt-ins remain unexecuted.
All 626 safety nodes, I4 217/I5 29 and the 212 new wire/planner nodes pass as
**subsets of this one invocation**, not additional source runs. The independent
controller-type reconciliation matches JUnit/journal starts and 18,844 normal
phase reports plus 57 genuinely passing SubtestReports. Legacy generic
`no_duplicate_phases` / `call_once_after_successful_setup` predicates remain
false because they conflate subtests with ordinary calls; their recorded failure
is preserved rather than rewritten. Actual controller types and contexts establish
which phases are extra.

The #149 historical execution is explicitly attributed to execution HEAD
`268025f` / tree `e5fa043`, whose 480 runtime/test/script/workflow/configuration
inputs independently equal actual #149 Git blobs. Its one complete invocation
is 6,076: 5,777 PASS / 279 FAIL / 20 ERROR. All 6,076 common nodes retain outcome
and phase; all 212 added nodes pass; no node disappears or duplicates. The
unsuccessful 299-node set is identical. **298 primary exception/refusal/frame-function
signatures are unchanged; one is different.** This is a measured comparison,
not a forced reassignment into historical I6-C/I7/Transfer buckets. Per-node raw
trace/phase inventories and normalized comparisons are in `broad/`.

That one node is
`tests/integration/i3/test_selective_exchange.py::test_empty_oid_and_context_payload_cannot_override_selection`.
Its old three-column fixture now fails `ExchangePackage` construction with
`MALFORMED_ROW` before `receive_package`, rather than reaching unconnected
`PERMISSION_DENIED`. Syntax-first refusal of caller-owned malformed v5 rows is
consistent with R02/R03/R12 and reveals no catalog existence. A new matched pair
separately proves old-three-column constructor refusal and canonical-seven-column
unconnected receive denial, both with unchanged complete persistent rowsets.
Neither the historical nor current legacy node reaches its two downstream
selection assertions; valid-v5 selective routing remains an I6-C obligation.
No compatibility relaxation or acceptance of unreached behavior follows.

The two migrated guards are the `[initial]` and `[cached-receipt]` parameters of
one unchanged test function. Independent whole-file AST comparison removes only
its one Resource fixture assignment: every other statement/decorator and all four
assertion ASTs are equal across #149, pre-migration and final source. The fresh
745 diagnostic separately yields 446 PASS / 279 FAIL / 20 ERROR, exit1. Initial
now enters three original assertions; cached-receipt enters four. Relative #149's
743 diagnostic, common outcome/phases and all 299 unsuccessful nodes' assertion
AST entry sets are unchanged; common call-phase assertion entries match. The two
additional guards have no observations in the original743 reference. The legacy
malformed-input node alone changes its primary failure signature. Passing P6
fixture-setup association differences are retained in both reference comparisons.
Relative Author final745, every node outcome/phase/primary exception/refusal/frame
signature and call-phase assertion entry matches. Two passing P6 nodes exchange
association with the unchanged module-fixture setup assertion at
`test_p1_distribution.py:26` between workers; this scheduling difference is retained.
Statement entry is not subexpression, spawned-process or full branch coverage.

Before the completed v3, an observer bootstrap assumed `_sqlite3.__file__` and
exited3 before testing; a separate v2 was interrupted by legitimate shared
`json.dumps` monkeypatching reaching reviewer instrumentation. Both raw attempt
records, partial JUnit/journals, exits and nonreconciliation remain preserved.
A no-xdist narrow control also exposes the shared-journal instrumentation collision
and remains failed. Only observer serializer/origin handling was corrected;
product/tests were unchanged. Separate affected-module 195 PASS and final
226 PASS plus 57 subtests preflight controls precede the new complete v3. No
partial attempt is combined into its final result or substituted for a product run.


The Author's pre-migration complete run is separately 5,987 PASS / 281 FAIL /
20 ERROR at `2f874ce`. Its final focused safety626, wire212 and external34 and
745-node diagnostic (446/279/20) do not form a final full run. This independent
review never relabels that aggregate as a single invocation. The Author initial
jsonschema-missing collection exit4 is a separate historical bootstrap attempt,
not the later smoke's exit1 or successful execution of its unreached assertions.
`raw/author-artifact-independent-integrity.json` independently checks all 1,094
Author indexed files and 1,057 raw-index entries, including lossless gzip hashes;
internal file consistency alone does not attest product execution.

## Retained safety and distribution verification

New equal-principal foreign/reconstructed/mutated contexts refuse before policy
callbacks or content SQL. Leases remain active through actual denied SQLite
COMMIT after Event plus two endpoints are pending; rollback preserves all prior
rows. A second unit denied after revocation rolls back the first pending unit.
Attributed independent controls still reach the second endpoint INSERT failure,
deferred FK COMMIT failure, successful and duplicate COMMIT, policy revocation
and cancellation. Both exact fences, each missing/changed, both absent, unreadable
schema, normal reopen, required PRAGMAs/UDF/fingerprint and unconnected Provider/
Exchange fail-closed controls pass. [Admission report](admission/REPORT.md) records
actual reached SQL and complete lease/rowset observations. Eight relevant product
guard modules are byte-equal to #149.

The selected Python 3.12.14 loads its actual SQLite 3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Each installed environment measures itself; no alternative engine, dynamic
override, safety-floor relaxation, skip/xfail or permission widening is used.
Concurrent execution durations are not sequential benchmark evidence.

Fresh direct wheel and publication-sdist-derived wheel are independently built
from `ef787a5`, not the Author's earlier `a354348` snapshot. Each wheel is 790,488
bytes, SHA256 `6b3a865b90673b9626ad120ecf106064d2211657d2d78a68fb6568a52a8aba71`.
The publication sdist is 137,096,882 bytes, SHA256
`1f83f0ad52deedadde5a43b0ad066e61147df371ee31177564916409108c0422`.
All 6,349 publication files remain exact in the sdist, plus PKG-INFO. All 164
wheel members/metadata and 160 product files (6,022,477 bytes) match; every archive
and installed RECORD row is independently checked. Separate venvs outside the
checkout import actual site-packages; installed code, DDL/UDF/fingerprint and
product-input hashes remain unchanged before/after execution. Full artifacts
remain under `/workspace/i6b-distribution-work`; complete member manifests/hashes
are committed, while the >100 MB sdist is not a Git blob. See the
[distribution report](distribution/REPORT.md).

Original minimal Access smoke retains its original bytes/assertions. Both forms
stop at original line187 `ExchangeService.export_package` with
`AdmissionRefused: PERMISSION_DENIED`, child/pytest exit1; subsequent statements
and assertions remain unexecuted. The initial direct tracing attempt interrupted
by an expensive reviewer observer is preserved separately; only instrumentation
was corrected for new v2 executions. No failure is turned into PASS.

## Hosted CI: exact feature and effective tree

Author Development run [39955068751](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39955068751)
is completed **SUCCESS** at the assigned feature. Independent receipt parsing
verifies its 92,059-byte receipt SHA256
`7622c0d22dac39585c968ebfd04cc8a7667c64500dcbe3b964d1d005d5255c4e`,
21 indexed payloads, run/attempt and actual two-parent checkout/tree. Manifest
status is `development_checks_passed`, `full_acceptance=false`, zero hosted
product-pytest cases, and `local_evidence_unavailable`. The 31 policy and four
runtime-binding stdlib tests are distinct from product-suite execution.

Author Access run [39955068823](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39955068823)
is finally completed **FAILURE**. Its actual checkout/tree and Python3.12.15 /
loaded SQLite3.53.1 are independently bound. Main runtime JUnit has 2,487 PASS /
279 FAIL / 20 ERROR (2,786 cases); separate broad I5 regression has 2,849 PASS /
279 FAIL / 20 ERROR (3,148 cases). I4 217/I5 29 pass separately in source and
both installed forms. Original installed Access export fails as above. The
workflow's old 79-node comparison is not a current 299-node disposition oracle.
These lanes overlap and are neither a hosted complete suite nor Release acceptance.

The 796,218,981-byte artifact download is unavailable: connector maximum-size
failure, then supported CLI redirect **HTTP403 (denied)**. No signed URL is
retained or retried. Both actual downloaded log views each lack a different DATA
chunk. Neither damaged stream is accepted. Their unambiguous observed union
matches original receipt length 1,948,089 and SHA256
`0847e6e5445d0d3726bda2020b2438a1b7ee2ac85da4931aced08055fc6199ea`;
all 121 indexed payloads verify. No byte is guessed and full-artifact download
is not claimed. Missing-both/conflicting-view/false-hash negative controls refuse.
`ci/author-access-verification.json`, original log ZIPs and the recovery helper
preserve this read-only fallback and exact remaining archive limitation.

Final review HEAD CI is checked after publication and recorded in the new Draft
PR body/final response. No automatic Release workflow is triggered by this review.

## Remaining conditions and handoff

Author fixes for M01/M02 and non-Author re-review are required before I6-C may
use these contracts. Preserve current denial precedence, actual-work accounting,
whole reports, complete originals, native-I7/full-report SQL guarantees, both
Transfer fences and all existing assertions during correction.

Normal Provider/selective Exchange composition, two/three-catalog late/reverse/
onward behavior, I7 recovery/pairing and I8 query/Search, live/benchmark opt-ins,
actual PR-stack integration, full hosted independent Release acceptance and
fence retirement remain unexecuted or unauthorized. Failed tests' downstream
assertions are not accepted merely because the first refusal is expected.

The only unavailable external read is the large Access artifact blob (denied403);
its compact indexed evidence and exact CI scope were recovered from supported
readable logs. No commit/push/PR operation is left pending or uncertain at handoff
unless explicitly reported in the final publication record. No additional user
approval was requested. [LESSONS.md](LESSONS.md) documents verified reusable
procedures and recommends a targeted existing-skill update without mutating the
frozen reviewed skill tree.
