# Non-Author independent review: ADR 0031 I6-A remediation / PR #145

**Verdict: FAIL.** One open Medium I6-A original-input validation defect (R09/R14) blocks
scoped acceptance. One Low evidence-tool defect remains. Critical 0 / High 0 /
Medium 1 / Low 1. The Medium defect is inherited from #143; this review does not
attribute its introduction to #145's twelve-line product correction. Correct it
and independently reverify before accepting I6-A or relying on that acceptance
for the I6-B implementation sequence. Ordinary Transfer remains fenced.

This verdict is based on a concrete counterexample outside the existing 299
unsuccessful-node ledger. Correctly assigning those 299 to later stages does not
prove all I6-A requirements. It is separate from overall Release acceptance,
merging, release or deployment; none is completed or authorized here.

## Exact scope and independence

| Binding | Commit | Tree |
| --- | --- | --- |
| Reviewed #145 public HEAD / sole review parent | `08fbb956c2e470e245146b0dbae747ed0690ea40` | `7072f952975a8537f74ced1bbc2a4a31d7aa3690` |
| Author executable-source freeze | `93d9927ae801d5402aab0aa0c7c270eeab2809e6` | `0c8a50e7cc23b98c6e7e2d1e6066077cbe8d203a` |
| Before #143 | `f5dc409429cdb69955b55e3c27a7ef3c163762fb` | `3ef434120202c6fa4cfaa1152802784a1671d3ed` |

The independent checkout and all new builds/tests target the public HEAD above.
All 478 tracked executable/test/script/workflow/configuration SHA-256 values are
identical to the Author executable freeze. Publication changed 703 evidence/skill
paths; full Git archives/sdist inputs differ. Equality is scoped to execution
inputs, not claimed equality of full source archives or Author build hashes.
`preflight/input-binding.json` contains the independent comparison.

A fresh Codex review thread and independent subsidiary audits performed this
work. They did not author the implementation. The repository owner's connected
GitHub identity is used for authorized evidence publication; this is thread/work
independence, not an assertion that a different human GitHub account authored it.
Existing schema/test constructors, an isolated fresh-memory fixture and execution
wrappers are attributed where reused. New finite authorization policy, SQL faults,
original-evidence vectors, receipt parsers and exception/assertion tracer provide
independent checks. Author outcomes remain labeled as Author provenance.

Initial API reads confirmed #145 was latest, at the exact assigned HEAD, with no
same-base independent review. #144 is the separate ADR0033 review. The dedicated
review branch starts at the frozen public HEAD; its PR base is
`fix/adr0031-i6a-regressions-20261023`. The final publication HEAD/tree, Draft
status, file list and live CI results are externally bound in the new PR body.
A report cannot embed the Git tree hash containing itself.

Read scope includes AGENTS.md, Accepted ADR0001/0031/0032, all three I6 design
contracts, the prior independent design report, #143 Author report, #145 REPORT,
classification METHOD/RESULTS, raw selected/JUnit/journal/typed/assertion evidence,
installed-harness code, the product authority/original/SQL paths and hosted logs.
Local efficient-investigation, ci-final-tree-verification and lessons-to-skills
procedures were used; proposed reusable lessons are in LESSONS.md.

## Blocking Medium: ORIGINALS-M1

The actual public Store accepts a malformed nested original Provider endpoint
declaration and converts it into valid explicit NULL. Construct a valid whole
TransferEventReport, then mutate `endpoint_declaration.from_endpoint` to None or
an invalid string with `object.__setattr__`. Initial intake returns `insert`;
exact replay returns `duplicate`. Stored/readback original state is
`explicit_null`. The supplied original was missing/invalid.

The constructor, `dataclasses.replace(report)` and pure `validate_originals`
all reject that same carrier with `INCOMPLETE_ORIGINAL_REPORT`. The real intake
never invokes the complete validator. Frozen dataclasses prevent ordinary
assignment, but do not replace promised revalidation at the public typed-input
boundary. This claim is limited to input validation, matching established nested
carrier mutation tests. It makes no arbitrary-Python sandbox, remote exploitation,
Provider authentication or permission-escalation claim.

The subreviewer reproduced four failed safety predicates in source. The root
reviewer independently reran those probes on both frozen-public-HEAD installed
wheel forms: **four failed safety predicates per form**, zero required refusals,
with actual installed product origins asserted. Each form's two ordinary-fence
controls correctly reject with `I2_TRANSFER_UNSUPPORTED` and unchanged rows.
No stage fence was removed on a normal product catalog. All positive Transfer
work occurs only in the explicit fresh-memory isolated test fixture.

Targets at reviewed HEAD: `domain/p1_context.py:1855` constructor validation;
`adapters/sqlite/context_admission.py:126` actual intake;
`adapters/sqlite/p1_context.py:340` partial manual checks;
`domain/context_admission.py:658` unused complete validator. SQL receives an
already-laundered valid explicit-NULL representation, so FK/schema integrity does
not detect the original input mismatch.

Correction: connect bounded complete-original validation to every real initial
and replay intake before serialization, lookup/write or duplicate success,
while preserving authority/selection ordering, zero denied-input disclosures,
finite grants and both Transfer fences. Add missing/invalid nested originals on
initial/replay; require exact refusal and unchanged rows. Re-run source and both
installed forms, the 19 original-evidence probes and independent SQL/revocation
controls. The review contains no product fix. Reproduction/code/SQL traces are
in [originals](originals/REPORT.md) and findings.json.

## Low: I6A-IR-L01

`classify_i6a_regressions.py:109-115` checks uncompressed binding paths before
calling its gzip-aware loader. The actual published directories contain only
`.json.gz`; the unmodified helper returns null bindings, omits its binding
predicate and still reports `consistent=true`. Both original published run
paths independently reproduce this. This review's separate parser explicitly
resolves gzip paths and validates both bindings; no source drift was found.
Fix compressed path resolution, require both bindings, and add complete/missing/
mismatching compressed controls. Frozen evidence must remain unchanged.
See [failure audit](failure-audit/REPORT.md) and its actual counterexample.

## Completed independent safety and artifact executions

| Lane | Actual result / scope |
| --- | --- |
| New finite-principal authority/SQL tests, source | 27 PASS /0 FAIL/ERROR/SKIP |
| Same new tests, direct and sdist-derived installed wheels | 27 PASS per form; exact node/JUnit/journal/81-phase reconciliation |
| Existing complete I6-A installed safety cohort | 551 PASS per form, including actual I4 217 and I5 29; exact historical node equality |
| New original-evidence vectors | 19 PASS; first reviewer setup18 PASS / 1 FAIL retained separately |
| Malformed-original counterexamples | 4 safety failures source; 4 per installed form;2 ordinary-fence controls pass per form |
| Installed harness adversaries | 2 positive controls PASS;4 expected negative subprocess failures verified, covering false wheel hashes and late foreign module injection under an adversarial ancestor config |
| CLI / complete package contents | doctor and module launch pass both forms; all 158 product files and all RECORD/member bytes match source/direct/derived/installed |
| Original I2/I3 smoke | PASS on both wheel forms |
| Original Access smoke | FAIL on both minimal installed forms at actual installed `exchange.py:397` PERMISSION_DENIED; downstream assertions unexecuted |

The independent SQL controls reach an Event and first endpoint before the second
endpoint's real SQLITE_CONSTRAINT_TRIGGER; a separate real deferred-FK COMMIT
fails with live leases and pending1 Event / 2 endpoints. Both roll back all new rows.
Precommit policy revocation and KeyboardInterrupt also leave no partial rows,
open transaction or leases. Successful and duplicate commits retain active
policy leases through COMMIT. Forged/copied/foreign contexts, principal/selection/
budget mutation, absent grants, replay after revocation, missing transaction and
read-only/expired facade controls refuse. No implicit fixture grants or product
imports from tests were found. The complete #143-to-#145 product delta is twelve
lines of pure local capability checks in two files; fixture authority is finite
and declared at composition.

Python3.12.14 uses its actual built-in SQLite3.53.1. No SQLite component was
obtained, built, installed, replaced or matrix-tested. Both wheel forms have 158
product files:135 Python, 19 SQL, 2 JSON, 2 GraphQL. The Author harness independently
binds 156 Python/SQL/JSON files inside pytest; this reviewer additionally binds
both GraphQL files and verifies every wheel RECORD row. Context schema and exact
both fence definitions match; FK checks are empty and integrity_check is ok.
The public-HEAD direct/derived wheels are 777,887 bytes with equal member contents
and SHA-256 `53f628499da0f47f72d8236e433bd0f02093202a638dbb1f657e3301891ec359`.
The fresh full public-HEAD sdist is 106,546,884 bytes, SHA-256
`8f0a794511f8cdbd8f4e1e50f1dc4c516830084169d7f81578dad27b7e51aab4`.
ADR0033/#142 minimization is absent from this ancestry and is not integrated.

The first additional Access probe used the full-dependency safety venv and
stopped at its explicit no-httpx premise. That failed setup is preserved.
Separate minimal venvs installed only each product wheel with no dependencies;
the unchanged smoke then reaches its real I6-C guard. Expected negative outcomes
and diagnostic repetitions are never added to ordinary passing-node totals.
Concurrent executions supply no comparable benchmark timings.

## Per-node transition and deferred responsibilities

Archived Author before/final execution reanalysis is independent; it remains
Author execution provenance: 5,941 = 5,198 PASS / 324 FAIL / 419 ERROR before and
5,974 = 5,675 PASS / 279 FAIL / 20 ERROR final. No identity was removed, no new
unsuccessful identity was added, and all 33 new nodes pass. The reviewer parses selected/JUnit/journal and
all actual typed reports, retaining 57 passing unittest subtests separately.
The generic legacy duplicate-phase predicate stays false; it is not relabeled.

All 743 old unsuccessful nodes have per-node comparison records. Additional 664
transition to 444 PASS, 206 I6-C guards and 14 actual I7 composition failures.
The old 79 remain 36 I6-C and 43 Transfer-stage refusals. Thus all 299 are
242 I6-C, 14 I7 and 43 Transfer. The 14 I7 failures are real missing trusted Recovery composition, not an intentional
stage-refusal API or accepted salvage. `_merge_salvage_request` creates an
unbound ContextStore and records valid later Context candidates as rejected.

The independent archived transition further resolves the additional categories:

| Before boundary | Before | Final PASS | I6-C | I7 |
| --- | ---: | ---: | ---: | ---: |
| Direct missing authority | 490 | 388 | 88 | 14 |
| Coordinator missing authority | 47 | 47 | 0 | 0 |
| Explicit I6-C guard | 127 | 9 | 118 | 0 |
| Total additional | 664 | 444 | 206 | 14 |

The old 79 are not signature-equivalent. Before remediation, 38 call / 41 setup become
59 call / 20 setup: 21 reach call after fixture repair. Compared with original I5/#141,
all 79 final phases match, but only 42 raw messages and 27 path/function sequences
match. The archive's actual assertion-line streams independently recompute
17 to 411 literal-assert entries across 743, and 0 to 13 across 79. These are archived
measurements, with statement/branch/subexpression/thread/process limits stated.
Five changed test-function assertion/raises ASTs were inspected; no unexplained
assertion removal, deleted rejection or skip/xfail addition was found. Nine
already Core-only roundtrips now explicitly exclude Context and keep their Core
assertions. Passing these is not evidence of an I6-C application route.

A separate pristine detached checkout and its own locked venv now rerun all
original 743 identities in one actual invocation: **444 PASS / 279 FAIL /
20 ERROR**, exit 1, no skips/xfails. Before and after, HEAD/tree are the exact
public freeze and full tracked/untracked status is empty. All 478 input hashes
match public Git blobs. Every pytest worker verifies product origins and loaded
module hashes at configure/finish against the pristine `src` tree; child CLI
launchers use that separate editable venv. No reviewer files enter that checkout.

Every one of the 743 outcomes and phases matches the Author's final execution.
The reviewer's own tracer also reproduces actual literal assertion-entry sets
for all 743, not merely their totals: 411 nodes enter local assertion statements,
including 375 of the 444 resolved nodes. Independent source-resolved exception
stacks reproduce 242 I6-C / 14 I7 / 43 Transfer. Thus the 444 PASS transitions,
assertion reachability and 299 taxonomy have fresh independent execution support.
The earlier archive reanalysis and environment-affected diagnostic below remain
separate provenance. See `failure-audit/clean743-summary.json`,
`clean743.json.gz`, `clean478-inputs.json` and the hash-bound raw archive.

New reviewer tracing repeats all 299. Its initial 275 FAIL / 24 ERROR includes four
read-only uv-cache setup failures. The four corrected repetitions are 4 FAIL and
reach the real installed I6-C boundary. Explicit latest-per-node combination is
279 FAIL / 20 ERROR across 299, with actual 242 I6-C / 14 I7 / 43 Transfer stacks. This is not
represented as one 279/20 invocation. All raw invocations and per-node provenance
are retained in failure-audit. The fresh full ordinary result and any necessary
cache-corrected supplementation are reported in executions.json and the final
execution addendum below.

## Hosted CI and progress decision

Fresh authoritative API/job/log/receipt verification:

- Development [39903868636](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39903868636): Success,21 verified payloads; product pytest 0,223 required files unexecuted, full_acceptance=false.
- Public-head Access [39903868666](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39903868666): Failure,121 verified payloads. Broad3,148=2,849 PASS/279 FAIL / 20 ERROR,0 SKIP;2,826of5,974 ordinary nodes unexecuted. Focused2,786=2,487 PASS/279 FAIL / 20 ERROR completely overlaps broad.
- Source Access [39902230351](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39902230351): Failure,121 verified payloads. All 299 source/public phases/types/refusals/extracted full frame projections match. Actual merge parents/tree and all 478 inputs verify.

Both Access runs actually execute installed I4 217 / I5 29 on direct/derived wheels
and retain the failing original Access smokes. The same six job steps fail;
inherited-79 comparison correctly reports220 additional nonpasses and never
becomes green. No additional public-head runtime blocker is introduced relative
to the executed source freeze. Classification of later-stage failures does not
make the workflow successful. See ci/REPORT.md for exact logs, hashes and scope.

Next coding agent: fix ORIGINALS-M1 in a separate authorized implementation PR,
add initial/replay/installed regressions and obtain non-Author re-review. Repair
the Low classifier provenance check with compression adversaries. I6-B must carry
exact v5 identification and original Parent/endpoint data; I6-C must connect real
finite caller authority, qualified dependencies, Provider intake and selective
Exchange without early cached-receipt bypass. I7 must compose trusted
salvage_merge admission, retain Stop and genuinely validate original candidates,
then re-run the 14 Recovery cases and G-R1/paired recovery obligations. I8/final
combined-tree/distribution acceptance and separate fence-retirement authorization
remain. Do not proceed on an asserted I6-A PASS while ORIGINALS-M1 is open.

Only new review evidence is added. Existing PRs, Author evidence, Accepted ADRs,
product/test/scripts/workflows, #139/#142 ancestry, merge history, releases,
deployments, automation and real Provider/catalog data are untouched. All
publication changes and payload hashes are indexed. No unresolved action is
pending approval or uncertain. CLI log redirects were Forbidden; that route was
not retried, and supported GitHub connector retrieval succeeded. No access
restriction was bypassed; no auto-review rejection required user approval.

The review recursively scans plain, gzip and ZIP payloads before publication.
New CI API snapshots are privacy-redacted projections: personal commit
author/committer email and real-name fields are omitted or replaced; Git SHAs,
trees, parents, public account identifiers and execution statuses are retained.
These projected JSON snapshots are not claimed to be byte-identical API replies.
No token, private key, signed download URL or personal mailbox is published.

## Final full-execution addendum

The actual full ordinary invocation selected and executed all **5,974** nodes:
**5,656 PASS / 276 FAIL / 42 ERROR**, pytest exit 1, 0 SKIP/XFAIL, plus 57 separately
retained passing subtest reports and four warnings. Collection/JUnit/journal/typed
reports reconcile. Before/after HEAD/tree, all 478 input hashes and tracked status
are identical. This checkout contained untracked reviewer evidence; the separate
pristine743 execution above supplies the clean source review requested.

Compared with the archived final outcome/phase, exactly 23 nodes differ. All 22
additional setup stops have an actual read-only default uv-cache traceback:
18 formerly passing packaging nodes and four formerly failing P5 nodes. The
initial full launcher omitted the writable cache environment; this is reviewer
setup, not a newly identified I6-A product defect. A new pristine-source invocation
with the corrected cache executes all 22: **18 PASS / 4 FAIL / 0 ERROR**, exit 1.
The four remaining P5 failures reach their real I6-C boundaries.

The sole additional call failure is `tests/e2e/test_queries.py::test_pr_root_scopes`:
its actual search-path CLI returns exit 3, partial/timed_out at the unchanged
30-second request budget during overlapping review workloads. A separate exact
serial repetition, after other product workloads finish, is **1 PASS**, exit 0,
with the same test, source and 30-second setting. This records observed timing
sensitivity; it is neither a product fix nor a claim of equivalent timing.

Using actual per-node finish timestamps from the full invocation, pristine743,
corrected22 and serial1 yields **5,974 unique latest outcomes: 5,675 PASS /
279 FAIL / 20 ERROR**. This is explicitly a multi-invocation node-wise comparison,
not a single corrected full run, exactly-once release receipt or green acceptance.
The initial full 5,656/276/42 result is immutable. All 5,941 original identities
remain, all 33 new identities pass, and no new unsuccessful identity remains in
that latest comparison. The original743 transitions and all assertion-entry sets
are independently established by the single pristine743 invocation.

All ordinary identities were observed; their setup-error bodies remain unentered
where indicated. One live and one benchmark node were collected and unexecuted.
Source, installed, focused and diagnostic repetitions overlap and are not summed.
`failure-audit/full-final-summary.json`, `full-latest-node-map.json.gz` and raw
archives retain every node's actual invocation, phase, exception and observations.
No skip, xfail, timeout increase, assertion weakening, source fix or failure
suppression was used. Full release acceptance remains unperformed and unmet.
