# Independent non-Author review of published PR155

**Verdict: FAIL.** One **Medium** mandatory finite-work finding blocks scoped
acceptance. There are0 Critical/High findings and one Low nonblocking evidence
precision observation. The inherited299 ordinary non-successes and intentionally
unconnected I6-C boundary are visible limitations, not the basis of this FAIL.

Reviewed publication: `fee364c6d61a5feebf08dbdd830a5a57ee2d872b`, tree
`ace7e44cd89194d189a30a0aa6cf513a45b3b87c`, on
`integration/adr0031-i6b-sdist-c0-20261024`. Actual direct base154 is
`91827360c185cbf813277bf32a6627d894b1b20a`, tree
`4db21ecf4267f1f31023fd63ac6de7ebd8d93d3c`. This new review branch is directly
stacked on155 and changes only this new evidence directory.

This is a fresh cloud non-Author review in a separate clean clone. Work is
limited to already-published source, disposable synthetic catalogs and review
evidence. Task A/I6-C was not resumed, its unpublished work was not requested or
reproduced, and its workspace was not accessed. No product repair, assertion,
workflow, Accepted ADR, historical review/evidence, existing branch or main was
changed. No merge, force-push, rebase, Release dispatch, deploy or real-data work
is part of this review. Shared evidence additions during testing are untracked
documentation; frozen tracked execution inputs remain bound. This is not a
clean-tree Release receipt or product-wide acceptance.

## Blocking finding

**I155-M01 — Medium: admission input scanner queues children after remaining
cumulative work is exhausted, without reservation.** A normal both-fenced
Context relation with1,000 actual typed members (58,891-byte canonical member
JSON), work_limit10,000 and prior_work9,992 consumes the8 remaining units, then
the actual production `list.extend` grows pending2→1,002 at used_work10,000.
The next charge refuses at10,001. The guard compares child count with the total
work limit, not remaining work. Selection.max_work7 also allows the same queue
growth before refusal at used_work8.

The exact case reproduces on published154, published155 and both independent
wheel installs. A separate C-call-only observer confirms actual member
references, not an inferred allocation or replaced scanner. The observed queue
is8,888 shallow list bytes plus56,112 shallow tuple bytes on this interpreter.
Policy calls0, relation rows0→0, actual rollback and both exact Transfer fences
remain intact. This is a bounded resource-accounting violation, not an
authorization bypass, unbounded-allocation or partial-persistence claim.
R04/R13 actual-work/bounds-before-allocation requirements make the scoped verdict
FAIL. [Full scanner study](scanner/REPORT.md), [independent second observation](i6/queue-confirmation.json),
[machine-checked source/installed binding](scanner/summary.json).

The fixed root bookkeeping in an already-exhausted request is excluded from the
finding. The variable work happens before refusal, not afterward. Properly
pre-reserved codec/planner controls pass within tested list/dict/embedded-JSON/
canonical-identity/cycle/depth bounds. A late planner stop preserves a completed
Provider+Resource and withholds the next whole Resource. These controls and
earlier scoped passing probes do not establish unlimited absence; the finding
is inherited and does not claim an integration-induced product-blob change.
No correction is implemented here.

## Integration, contracts and distribution

Independent Git-object checks verify154 base,147 and144 ordered merge ancestry,
their common merge-base,150 as reference rather than ancestor, all six shared
paths and both textual conflict unions. All160 product blobs equal154; both
Transfer fences,31 preexisting Accepted ADRs, Accepted0033 from144 and historical
evidence are preserved. GitHub test merge `90e222635a01e89f095e9a256ac69ecfc759ec4e`
has ordered154/155 parents and exactly155's tree. All493 tested execution/build
inputs remain identical to the Author tested source. Low **HCI-L01** records24
Author shared-path SHA256s computed after `.strip()`; correct Git OIDs and this
review's complete-byte hashes verify actual provenance without altering history.
[History and CI evidence](history-ci/REPORT.md).

The I6 study independently checks strict v5/native identification, raw dictionary
digest before selection conversion, canonical selection/embedded JSON, local
service-bound authority/finite selection, foreign handles, originals, real
terminals/Source/Coverage, first/replay/revocation and leases through actual
COMMIT. Actual second INSERT and deferred COMMIT rollback observations are
retained separately from SAVEPOINT release. Reused tests/fixtures are inspected
and attributed, not treated as independent semantic oracles. The normal
Provider/Exchange/Transfer routes stay intentionally unconnected. Detailed
executed cohorts and exact source/installed coverage are in [I6 REPORT](i6/REPORT.md)
and [I6 MATRIX](i6/MATRIX.md).

Independent distribution measurements:160 product files/6,025,551 bytes;
sdist164 members,702,494 compressed/6,041,897 regular/6,174,720 tar bytes.
Backend-only rebuild outside Git yields the same791,300-byte wheel as the
direct build, all164 members/full bytes/ZIP metadata/RECORD equal. Both external
installs verify160 source hashes, installed RECORDs, actual imports and doctor.
Sdist SHA256 `9d228f889f9507cdc5a166b9658e80873fcbd48255c6c958eb90e33954014b54`;
both wheel SHA256 `2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8`.
23 independent hostile archive specimens and8 exact finite-budget controls
behave as expected before extraction/build/install.
[Distribution REPORT](distribution/REPORT.md).

C0 runs actual closed DEFLATED ZIPs:2,097,151/2,097,152 accept;
2,097,153/2,323,560 refuse with zero stdout and the artifact diagnostic.
Expanded6,120,406/compressed6,660 accepts. Successful strict framing/base64,
CRC/index/member SHA256 and synthetic run/Git-tree bindings verify. These are
complete real emitter measurements, not mocked payload/final sizes. Workflow
`always()` upload behavior is inspected; hosted overflow was not run.

## Regression and hosted evidence

The fresh full ordinary source run completed **6,497 unique =6,198 PASS /
279 FAIL /20 ERROR, exit1**, zero skip/xfail/xpass, with57 passing subtest
reports kept separate. Its original HEAD/tree and all490 regression inputs
match before/after execution. Each installed wheel executes692 mapped ordinary
source nodes (446 I6 plus246 I4/I5, overlap0);5,805 exact unrun source IDs per
form are saved. Independent pure58 checks and49 scanner cases per form are
separate adversarial observations, not invented ordinary-suite node coverage.
The unchanged minimal Access smoke separately fails on both with
PERMISSION_DENIED,26 assertion entries reached/28 unreached.

The [regression report](regression/README.md) contains the fresh ordinary and
diagnostic executions, exact collection/JUnit/journal/observer reconciliation,
unexecuted opt-ins, actual exceptions/refusals/frame functions, assertion-entry
comparisons and all failed review-helper attempts. Independent raw historical
comparison verifies1546344=6045PASS/279FAIL/20ERROR versus1556497=6198PASS/279FAIL/
20ERROR:6,343 common nodes retain outcomes/phases,154 added nodes pass, and one
passing README parameter has an explicit reviewed144 replacement. All299
unsuccessful phase/exception/refusal/frame-function keys match. Four physical
frame-coordinate shifts,19 raw message changes and299 raw traceback-body changes
remain visible; no byte-identity claim is made. Historical79 is not the current
299 baseline. Overlapping lane counts are never added.

Final155 hosted Development40006927076 is SUCCESS with0 product pytest and
`full_acceptance=false`; Access40006927148 is FAILURE, main2487PASS/279FAIL/
20ERROR inside broad2849PASS/279FAIL/20ERROR; Pages40006927071 is SUCCESS with
deployment skipped. Independent Development receipt verification checks all21
payloads. Current supported Access log views contain1,993,868 decoded bytes,
90 fewer than declared1,993,958; the strict verifier refuses rather than guessing
bytes. Author historical full-receipt claims are separately attributed, not
conflated with current independent verification.

Full Access artifact12524818073 bytes were not downloaded after the inherited
Azure Forbidden/zero-byte limitation. API/log metadata reports856,700,515 bytes
and digest `ca97a1db8fff294fad2d5d4be893e3f4338a9737381a17a9010ac1efc9a33872`;
this is not independent downloaded-byte hashing. No new artifact denial or
successful download is claimed. Current receipt incompleteness is a retrieval
limitation, not a new product defect. [Exact limitation](history-ci/findings.json).
The lightweight Development routing follows Accepted0001/0033 and does not
require a duplicate full hosted product run. Own review-PR terminal CI and final
published head/tree are recorded in the durable Draft PR description to avoid
an evidence-commit/CI cycle.

All local execution uses the environment's actual Python3.12.14/SQLite3.53.1,
with measured source ID/options/origins. No extra SQLite engine, library
download/build/swap/matrix, version spoof, guard bypass or floor relaxation.

## Audit and next checkpoint

[MATRIX](MATRIX.md), [findings](findings.json), [complete payload index](ARTIFACTS.json)
and `verify_review.py` provide the entry points. Each subreview retains executable
reproductions and raw indexed evidence in Git, including actual C0 ZIPs and
source/distribution artifacts. Run `python verify_review.py` to check every
indexed payload and ZIP; `scanner/verify.py` separately checks the saved real
operations and published-source/installed binding. Helpers contain actual task
paths where required and their replay limits are documented. The final review
commit content, index and raw ZIPs are verified through published Git objects.

The next checkpoint requires a separately assigned Author correction for
I155-M01, then independent review against the saved source/both-installed
vectors and current frozen source. Preserve existing299 failures, original
Access refusal/unreached assertions and I6-C/I7/I8 obligations. Complete Access
receipt/download and any required hosted overflow evidence need ordinary
authorized access/execution later. Independent PASS would still not authorize
merge, Release, incorporating I6-C or fence retirement.

Skills applied: `efficient-repository-investigation`,
`ci-final-tree-verification`, and the `lessons-to-skills` handoff assessment.
Recommend a later skill lesson to observe real queue expansion and reservations
separately from the first refusal/whole-unit rollback; no skill, product or
historical file is changed by this evidence-only review.
