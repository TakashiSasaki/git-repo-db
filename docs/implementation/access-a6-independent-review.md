# A6 independent Access review and correction

This is a correction child of PR #102, based on exactly
`f4d0d448fca5925bfbe4f8cb8345c3bd0df7de60`, tree
`a7b4521fb7fa6562c8e0bf67e2766743e0b82c5b`. The main branch remained
`b2a87cfc6562413d9ecde7f4329e90c434ae9aad` at preflight. All eight stack PRs
#95–#102 were Draft/Open/unmerged; each actual base was an ancestor of its head.
PR #102 had no submitted reviews and no existing correction child. The checkout
had full reachable history; a main-only fetch refspec was explicitly supplemented
for #102. No existing worktree or uncommitted work was replaced.

## Independent baseline review

R1–R4 were separate read-only agents, not authors of the reviewed stack or of the
following product correction. Root integrated evidence, owned corrections and ran
the controlled focused workload. All baseline agents fixed the same commit/tree,
kept the target clean and wrote evidence outside it. Synthetic data only was used.

| Reviewer | Actual JST start / finish | Scope and result |
| --- | --- | --- |
| R1 | 12:35:33 / 12:39:57 | Identity/SQL/time/history; 9 independent real-API/SQL matrix groups passed; no defect reproduced |
| R2 | 12:35:44 / 12:42:14 | Approval/execution/Git; independent A5-vs-A6 handoff experiment and three new findings |
| R3 | 12:35:56 / 12:43:15 | Context/Exchange/backup; two implementation defects and the existing cross-seed Exchange gap |
| R4 | 12:36:09 / 12:45:01 | 26 assertion meanings, 43 ADR clause rows, current/historical links, actual hosted receipts and CI/distribution scope |

All times are 2026-10-18. Detailed reports, executable probes and minimal observed
results are retained in the [baseline evidence index](evidence/access-a6-independent-20261018/baseline-index.json).
The [R1 report](evidence/access-a6-independent-20261018/r1/review.md),
[R2 report](evidence/access-a6-independent-20261018/r2/review-baseline.md),
[R3 report](evidence/access-a6-independent-20261018/r3/baseline-review.md) and
[R4 report](evidence/access-a6-independent-20261018/r4/review.md) distinguish their
actual executions from static inspection, failed fixture construction and work
performed by another reviewer. Root's correction is not called independent review.

## Reproduced findings and corrections

Source coordinates in this table refer to the fixed **baseline**, before edits.
The independent reports contain complete commands, original/expected outcomes and
retained minimal scripts. High identifies a selected-request scope violation; it
does not claim that an incorrectly attributed UUID or remote exploit was observed.

| Finding | Severity / baseline source | Minimal reproduction and correction |
| --- | --- | --- |
| R2-H01 | Medium; `adapters/git/access_native.py:209` | Prefix the first `[include]` or matching `[includeIf]` with UTF-8 BOM. Valid external config is read; malformed external config produces `GIT_INPUT` after a command starts. Inspect Git's BOM-free lexical prefix and reject indirect config before any command; safe BOM config remains supported. |
| R2-H02 | Medium; `adapters/git/access_native.py:105`, `:235` | Cancel during `_process_options`' final `http-alternates` stat. A subprocess starts before the loop notices cancellation. Recheck the guard after final filesystem preparation. |
| R2-H03 | Medium; `application/access_workflow.py:295` | Cancel while the actual final `current_grant` transaction is active. Both public dispatch APIs start the callback. Recheck the guard after that read, then session/deadline, before callback admission. |
| R3-01 | Medium; `application/acquisition.py:818` | Seed R0 plus registered R1: external `GitMetadataInput(R1, ...)` rejects without admission. Allow an explicitly selected nonseed target while keeping actual Core/Operational seed+instance pairing. |
| R3-02 | High; `application/acquisition.py:849`, `:853` | A unit selecting R0 accepts a nested RepositoryClaim for registered R1 and reports R0. Validate every repository-owned nested claim/observation/Notes capture and repository/Capture Coverage before any Core admission. Global OIDs retain their independent meaning. |
| Root-M01 | Medium; `application/acquisition.py:826` | Deliver a valid unit, then change source/time/nominal objects under the same request. The baseline accepts it. Freeze complete bounded semantic input in request progress without raw native bodies; preserve actual repeat-work charging and explicit new-request compatible additions under the same Capture. |
| R3-P01 | High, post-fix counterexample at `f81a399`; metadata/paired scope preparation | Live Notes with durable progress fails `REQUEST_SCOPE`; shared explicit memory progress accepts source A→B and returns A's saved observation. Bind actual Notes source scope/format in saved intent and its exact target/instance/source request scope in both paths. Preserve externally reported Capture source independently. |
| R3-P02 | High, post-fix counterexample at `f81a399`; metadata Capture preflight | An existing foreign Capture pair supplied with a falsified selected owner, without Capture Coverage, is refused only after standalone claim writes. Preflight every incoming Notes Capture against its complete stored original key (owner/source/ref/root), with metered indexed lookups, before any Core admission. |
| R3-C01 | High, post-fix counterexample at `8dcb515`; stored Capture read boundary | Generic SQL treated damaged stored source/ref/OID as incoming mismatch or raw UTF-8 error without stopping. Missing repository/root parents were silently recreated. Move touched Capture reconstruction, canonical ref/domain checks and parent existence into a typed Core snapshot reader with decoded-read and persistent completion/stop fences. Preserve the suspect file; valid incoming conflict remains noncorruption. |
| R4-01/02 | P3; acceptance ledger items 7/16/24 | Scope URI tests do not prove positive Repository grammar, MAX ties do not prove all-history continuity, and ADR approval is not an implementation-check gap. Add existing positive/full-history references and separate the gates. |
| R3-03 | Medium; `application/exchange.py:306`, `:327`, `:367`, `:1319` | Actual R1 acquisition in seed-R0 catalog exports an R0 envelope containing R1 evidence. Seed-R2 import rejects without mutation; same-seed onward export preserves R1 exactly. Cross-seed Exchange remains an explicit incomplete contract, below. |

The newly written regression file initially produced 26 failures and 7 passes on
unchanged production source. Its first cancellation fixture injected during the
earlier grant read; moving injection to the actual final read then reproduced
both dispatch failures. Later fixture failures (foreign Capture setup missing its
Repository parent, wrong expected pairing error and matching an error's detail
instead of its typed code) were corrected without changing product guards. Raw
failed outputs are retained outside the checkout. These failures are not relabeled
as successful executions. The extended 46-case regression checkpoint passed.

Separate post-fix review then reproduced the live Notes and existing-Capture cases
above. Nine new source-scope regressions failed on the first correction. Its broad
run was intentionally interrupted **before further edits**, after 1,401 passes,
exit 2, and is not complete acceptance. Partial JUnit/journal and the interruption
reason are retained. The subsequent correction binds actual Notes source/format
for explicit progress too and preflights complete stored Capture identity. Its
extended **63-case regression checkpoint passed**; final broad execution is bound
separately to the new source commit.

The next independent review found R3-C01. A second broad checkpoint was stopped
before edits; its SIGINT was absorbed during the P4 actual-Git test and the journal
recorded that call as failed, before SIGTERM ended the process (exit -15). This is
retained as an interruption-associated failed call, not a passing full run or a
hidden skip. The new typed-reader correction has a **75-case regression checkpoint**
with damaged UTF-8/domain/FK controls that assert persistent stop and exact
unchanged suspect Core bytes. The final broad run must execute the interrupted
P4 node again along with the complete collection.

The original A6-H01 fix was independently checked using an OS/environment
checkpoint and a second SQLite handle, without importing the existing test
fixture. All eight A5 parent cases improperly started callbacks; all eight A6
cases rejected changes, consumed tokens and released both descriptors. Later
revocation of admitted work remains a different, documented in-flight case.

## Remaining item 11 contract

External metadata acquisition is corrected in standalone and prepared paired
paths. Imported RepositoryClaims keep direct JSON values, original observations
and genuine Capture UUID pairs. No Access FK is introduced into Core. Core stays
INSERT-only and ordinary file bodies stay excluded.

Exchange v3 has one top-level Repository field but no Repository-set selector or
receiver-target argument. Export reads all repository rows; OIDs may be shared
without membership proof. Removing `REPOSITORY_MISMATCH` cannot establish which
repositories the caller selected or how missing/foreign registrations, captures,
Coverage and detached Context alternatives should be handled. The precise
[R3 contract analysis](evidence/access-a6-independent-20261018/r3/baseline-review.md)
lists those missing rules. ADR 0003's DS-R05 remains explicitly deferred. The
correction preserves pairing, selection and mismatch guards and exercises both
same-seed R1 roundtrip and mutation-free R2 rejection. No header is relabeled to
force import. Item 11 remains partial; this contract decision does not stop the
other corrections or reopen settled Scope policy.

## Acceptance and ADR replacement gates

The [baseline 26-row semantic map](evidence/access-a6-independent-20261018/r4/semantic-acceptance.md)
records the assertion meanings and limitations of all 48 baseline-linked functions.
The [final independently verified map](evidence/access-a6-independent-20261018/r4/final/typed-source/semantic-acceptance-verified.md)
checks all 64 final linked functions and actual execution, rather than names alone.
The updated
[implementation ledger](access-a6-acceptance.json) has 24 scoped covered items,
one partial (11) and one deferred (15). Item 16 covers its stated implementation
checks; independent review, whole-ADR approval, merge and release remain separate.
The auditor's fixed gate vocabulary intentionally cannot certify reviewer
independence or grant owner approval; use this report and the final execution
receipt for the actual review outcome.

Item 15 has three distinct dispositions: the key-classification ledger is
implemented; a legacy extractor is absent and outside this task; real-data
reads/extraction/migration are not authorized or performed. This unreleased project
has no backward-compatibility obligation. Legacy extraction is not an automatic
prerequisite for this synthetic Access validation.

R4 read all of ADR 0003 and mapped 43 clauses, including its six acceptance
criteria, to operative successors in proposed ADR 0029. The
[clause map](evidence/access-a6-independent-20261018/r4/adr-clause-map.md) found no
material loss after the already accepted 0004/0014/0026/0028 refinements. The
[incoming-reference classification](evidence/access-a6-independent-20261018/r4/adr0003-inbound-classified.json)
contains 25 baseline files/26 occurrences, including three immutable distribution
receipts. They must not be globally rewritten. New review evidence is historical
in the same sense; future retirement must rescan current links.

Still required from the human owner: explicit acceptance of the **whole** ADR 0003
replacement, with its real acceptance date. Only a later authorized coherent
change should accept 0029, update the index/current authority links, retire 0003
and close its particular policy debt. Accepted Scope choices do not supply this
approval. This task leaves 0003 present, 0029 proposed/date-null, default Schema 21
and P8 unchanged. Merge, auto-merge, release, tag and deployment are not authorized.

## Execution binding and scope

Baseline: this session independently collected and ran the current workflow's
exact target arguments: **1,802 passed** on embedded SQLite 3.53.1/Python 3.12.14,
then **1,802 passed** on actual SQLite 3.51.3/Python 3.13.5. The latter took
205.29 seconds; it is not the historical CI rerun claim in the supplied ZIP.
Both exact collection/JUnit reconciliations and all six required audits passed.
Ruff lint/format and cumulative diff whitespace passed. The official SQLite
amalgamation's published SHA3-256 and actual source ID are recorded in
[runtime evidence](evidence/access-a6-independent-20261018/runtime/runtime-minimum.json).
The default interpreter embedded SQLite; its initial exact-minimum assertion
failed despite `LD_LIBRARY_PATH`. A separately locked dynamic-binding environment
then established the actual minimum. Neither version spoofing nor a disabled
network guard was used.

Baseline direct wheel and sdist-derived wheel smoke both ran installed with `-I`,
outside checkout, from a clean Git archive. Their passing smoke is not the full
pytest cohort run against installed distributions.

Final executable source: **`536ad33941283a439825ad606b8718c88c967ffa`**, tree
**`169b5d7ad5dea4fa271f71bea96863bc318fb332`**. On actual SQLite 3.51.3,
the final focused collection/execution was **1,877 passed in 228.72 seconds**,
zero failures/errors/skips. All original nodes remain; 75 new regression nodes
were added. Collected IDs, normalized JUnit, journal starts and each of
setup/call/teardown match exactly once. The interruption-associated P4 node passed.
The separate P2/P3 and P5/P6 compatibility cohort passed **49 cases** in 23.58
seconds with its own exact-node reconciliation. These are separate overlapping
behavioral checks, not counts added to claim a complete release suite.

All six required audits, Ruff lint/format and cumulative whitespace passed on
that source. Both direct wheel and sdist-wheel installed smoke passed from a
clean archive, with actual site-packages module origins, interpreter, source ID,
wheel hashes and sdist hash retained. The two wheels had identical SHA-256.
Allowlisted MkDocs passed with zero broken links/sensitive outputs. It used
placeholders: the legacy builder's summary label says "Rendered", but no fresh
Mermaid rendering is claimed. Public Schema 21 diagrams remain distinct from
the explicitly started Access implementation.

See [execution receipts](evidence/access-a6-independent-20261018/execution/acceptance.json),
[exact-node reconciliation](evidence/access-a6-independent-20261018/execution/node-reconciliation.json),
[distribution proof](evidence/access-a6-independent-20261018/execution/distribution.json),
[stack pins](evidence/access-a6-independent-20261018/execution/stack-pins.json) and
[raw-artifact hashes](evidence/access-a6-independent-20261018/execution/raw-artifact-index.json).
The 450-file input list is a selected validation-input set; the additional
2,662-file map covers every file tracked at the tested source, including the
acceptance ledger, design and audit contracts. A later evidence-only commit may
change this narrative/add frozen receipts; it must prove all other original files
unchanged and identify its different Git tree. Final hosted checkout/tree and
actual test execution are recorded in the child PR and exported packet, without
transferring a baseline PASS to changed executable inputs.

R2 independently closed its three execution findings with 23 corrected-source
scenarios plus eight A5 negative controls, then checked unchanged-scope binding
at `8dcb515`. The later Core reader is separately reviewed by R3. R3's
[final independent review](evidence/access-a6-independent-20261018/r3/typed/review.md)
at the final executable source passed **91 independent groups**: 58 metadata,
12 live Notes, 14 stored-corruption/conflict and seven typed-reader controls.
R4 completed its [final independent review](evidence/access-a6-independent-20261018/r4/final/review.md)
at 13:15:03 JST. It checked assertion meanings, all 2,662 tracked source hashes,
current/historical ADR preservation, raw collection/JUnit/journal phases, installed
package origins and separate gates. It did not claim root/other-agent tests as its own.

The ordinary hosted offline job at the baseline had `development_checks_passed`,
`full_acceptance=false` and zero runtime tests; R4 independently decoded and
hash/index-verified its bounded receipt. The dedicated Access job really executed
1,802 tests, installed smoke and allowlisted placeholder MkDocs. Those historical
hosted results have their own source binding. The workflow does not directly select
the compatibility directories; risk-relevant compatibility checks are separate.
The documentation build uses the existing allowlist and `--no-mermaid`: it checks
staging, links/templates and output safety, not fresh Mermaid rendering or internal
Access-document publication. No deployment is performed.

Complete ordinary/release pytest, full installed pytest cohorts, hardware power
loss, hostile privileged-writer guarantees, remote SSH/HTTPS/container execution
and real-data operations are outside this bounded review. Stored remote settings
do not constitute execution support. None is reported as executed.

## Reusable lessons

Updated existing skills: final executor handoff (guard after final DB/OS work),
Access native acquisition (Git BOM semantics and selected nested metadata), and
CI final-tree verification (actual embedded/dynamic SQLite binding and assertion
meaning). These procedures grant no new permissions and retain their tested
counterexamples and limits. The correction author and post-fix reviewers are
identified separately in the final receipt.
