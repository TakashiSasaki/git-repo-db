# PR #142 independent non-Author re-review — PASS WITH CONDITIONS

The reviewed **archive-hardening requirements pass** independent execution.
AR-001, AR-002 and AR-003 are addressed, and A-CI-01's two input identities are
documented and independently reproduced. There are **0 new or residual Critical,
High, Medium or Low archive findings**. This is a new agent review, including
separate archive and CI audit agents; none authored #142. The GitHub account is
the repository owner's account, not a claim of independent human approval.

The overall disposition is **PASS WITH CONDITIONS** for accepting the scoped
repair: preserve the inherited failing product-stage tests and Access refusal,
keep this work Draft, and qualify any eventual combined integration tree
separately. These conditions do not require another archive repair. This is
neither full product/release acceptance nor authority to merge. No Critical/High
counterexample or new regression was found. No outcome is hidden as SKIP/XFAIL.

## Frozen target and unchanged scope

| Role | Commit | Tree |
| --- | --- | --- |
| Accepted ADR 0033, #135 | `18ba867d1c2f33c7d17939b2722d22a67139363a` | `57475b6fe473bc0cb691d9b7165414eb498b3893` |
| Original implementation, #138 | `8cd89a3d25c811ee32d117ec32fe76a6022e6d94` | `0f42e9d0e498e249bc2cc02f6b96df9ef87106a0` |
| Original independent review, #140 | `ef3ca118d4ab5e52dc2d1c7de384c3557509add2` | `ded7bd39fd86dd0d738404abf667beaf44fb06d0` |
| **Reviewed #142 HEAD** | **`59307c40ea65554736e131cedd00f04c9906551b`** | **`5ea93707d62b542c84632515392ac6a35c36cd65`** |
| Actual hosted test merge | `e0c60765bd0d99b8276a8d0528dabfa7f4d6971a` | `5ea93707d62b542c84632515392ac6a35c36cd65` |

Live startup reads confirmed #142 OPEN/DRAFT/unmerged, base
`review/adr0033-sdist-independent-20261023` at the #140 SHA, head branch
`fix/adr0033-sdist-archive-hardening`, and no reviews/comments. Latest 100 PRs
and all 78 remote branches contained no competing re-review. These responses
are in `startup/`. The frozen target was checked out into a new independent
worktree. Builds additionally used pristine `git archive` sources, with their
archive hashes retained. The hosted merge has exactly #140 and #142 as parents.

This new review branch starts directly at the frozen #142 HEAD; its PR base is
`fix/adr0033-sdist-archive-hardening`. Its published HEAD/tree are recorded in the
Draft PR and final handoff, avoiding a self-referential commit identifier here.
Every changed path is new evidence under this directory. Product code, tests,
scripts, workflows, accepted ADRs, skills and all old evidence remain unchanged.
All **459 execution/configuration input hashes** match the frozen pre-execution
inventory, SHA-256
`c0742237299a23851496ed83d87f0f64ba75e41e1b64fa7f0e507861003d73f7`.
The product `src` tree remains `ec0e0b9ebc8c9117453c0cace607626803e90c8e`.
The conservative CI acceptance hash can change when this new evidence is added;
the frozen #142 hash is `8413e49bbfd35224c6c864680809a8956a2eda4f1324b04c3247e792b32ebdaf`.
Unchanged executable-input binding is not represented as transferring a complete
release receipt to the later review commit.

Neither #139 nor the opposite #143/I6-A feature series was integrated or repaired.
Task B is outside this assigned task. No existing PR, automation (including the
separately mentioned 13:49 audit), real catalog, merge, release or deployment was
modified. GitHub publication of this new evidence branch/PR is the authorized
external write.

Read AGENTS, ADR index/0001/0032/0033, the design, original review report/findings/
reproducers, #142 report/summary/measurements/index, checker, packaging tests,
distribution builders/cache and CI/Pages/planner contracts. Both old evidence
archives and their internal/external indexes verify: **171 old-review and 196
Author payloads**. Their historical results are not substituted for these new
runs. Repository investigation, final-tree verification and lessons-to-skills
procedures were used. No new skill was created: existing bounded-archive guidance
covers the verified mechanism, and the review found no new generalizable repair.

## Finding disposition and independent counterexamples

| ID / original severity | Verdict | Independent evidence |
| --- | --- | --- |
| AR-001 / Medium | PASS, addressed | Old hidden 10 MiB PAX specimen and local/global/GNU/unknown extensions reject. Separate 16/64 MiB streamed PAX bombs stop at exactly **8,922,625 produced bytes**, maximum decoder output **65,536 bytes**, with **0 TarInfo parser calls**. Raw fixed headers reject extensions before logical tar materialization. Fresh locked Hatchling output has 159 plain headers and no PAX keys. |
| AR-002 / Medium | PASS, addressed | CRC32/ISIZE/FHCRC corruption, missing/truncated trailers, invalid/truncated DEFLATE, extra gzip members, hidden second tar, bad/giant/negative physical sizes/checksums, nonzero member/end padding and incomplete end markers reject. Valid optional gzip headers and two-block tar endings pass. Entire bounded gzip EOF/trailer and physical stream are checked before logical iteration. |
| AR-003 / Low | PASS, addressed | Case-insensitive duplicate singleton headers, invalid/folded identity values, malformed Metadata-Version and invalid matching project identities reject. Correct identities/CRLF pass. Fresh PKG-INFO bytes match complete wheel METADATA. No claim of standalone semantic checking of every unrelated metadata field. |
| A-CI-01 / Low advisory | PASS, addressed | README-only counterexample changes shipped-source inventory/tree while runtime acceptance hash stays unchanged, selects the lightweight sdist gate and selects no runtime pytest files. Active docs distinguish the identities; no ADR 0001 runtime-selection expansion or stale-receipt bypass was found. |

The supporting [archive audit](independent-audit/REPORT.md) has **66 independent
standalone cases and 18 CLI outcomes**, diagnostic exit 0. All seven original
attack specimens reject, and their CLI invocations exit 1 with failed receipts.
These cases are not added to pytest coverage counts. The measured bomb children
used approximately 23 MiB maximum RSS; this is supporting observation, not a
portable exact memory guarantee. Deterministic byte limits/parser-call counts
establish the finite boundary. The integrated negative test proves rejection
before extract/rebuild/install, and the checker itself performs no extraction.

The initial standalone audit exited 1 on an incorrect expectation about a bare
CR separating an unrelated metadata header. Correct identity fields remained
valid; the corrected expectation and three additional missing-resource cases
are explicit. The original 63-case result remains intact. This was a reviewer
expectation correction, not a product fix or removal of a failing test.

## Fresh artifact measurements and installed behavior

| Measurement | Fresh accepted-design build | Fresh reviewed build |
| --- | ---: | ---: |
| Compressed sdist bytes | 83,949,291 | **677,902** |
| Regular-file bytes | 137,661,254 | **5,921,698** |
| Members | 3,875 | **159** |
| Direct / sdist-derived wheel bytes | 762,725 | **762,725** |

Measured reduction is **99.19248633082559%**. These are this review's actual builds;
they reproduce the historical deterministic values. Reviewed whole-tar bytes are
**6,051,840** with **159 raw headers**. Budgets remain **2,097,152 compressed**,
**8,388,608 regular-file bytes**, **512 members**, **8,922,624 whole-tar bytes**.
The complete inventories are [after-members.json](after-members.json),
[before-members.json](before-members.json) and [sdist-contract.json](sdist-contract.json).

- Sdist SHA-256: `c72f86709f360b306daa1d39e2854e910f773e6acfce9f4bec7dae3396012e21`.
- Direct and derived wheels: `22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842`.
- Complete sdist source-inventory hash: `7d93a7c4b2d3d6a7411f0fc98a42901a83b508a63d2e15e44c2f6f2674f21934`.

All **159 wheel members**, complete metadata and every RECORD row/hash/size are
equivalent. All **155 product files** remain: **132 Python, 19 SQL, 2 JSON,
2 GraphQL**. No developer docs/tests/scripts/evidence ZIPs enter the sdist.
Rebuilding the sdist works outside Git and the original checkout. A separate
backend-only environment has no product installed or Git on PATH and rebuilds
the same complete wheel using only preverified locked dependencies.

Separate fresh runtime venvs outside checkout verify installed site-packages
origins, all 155 installed hashes, console/module CLI, SQL/JSON/GraphQL resources,
generated JSON guards, every store's DDL fingerprint, integrity and foreign-key
checks. Additional direct/sdist installed I4+I5 runs collect and **execute 246
nodes each**, with exact JUnit/journal starts/phases/finish and process exits.
Product imports never resolve to checkout; only a copied network guard is on
PYTHONPATH. No tests are bundled in the product artifacts. I2/I3 installed probes
also pass. Original Access smoke fails with `I2_TRANSFER_UNSUPPORTED` on both
artifacts; consequently the original installed orchestrator exits 1.

## Actual local test execution and limits

Counts overlap and are not summed as independent coverage. The preserved helper
scripts retain their historical `author_verification: true` field; this review's
outer invocation/source bindings identify their independent execution.

| Execution | Actual outcome | Exit |
| --- | --- | ---: |
| Broad source cohort | **3,058 PASS / 59 FAIL / 20 ERROR** | 1 |
| Complete packaging, including 37+94 archive tests | **151 PASS / 4 FAIL** | 1 |
| CI planner/journal/profile/efficiency/execution | **266 PASS** | 0 |
| Docs unit tests / allowlisted checkout build | **8 PASS** / successful `--no-mermaid` placeholder build | 0 / 0 |
| Overlapping source I4 / I5 | **217 / 29 PASS** | 0 / 0 |
| Original installed I4 / I5, each artifact | **217 / 29 PASS** | 0 / 0 |
| Additional installed collection/JUnit/journal, each artifact | **246 PASS** | 0 / 0 |
| Independent artifact/resource probe, backend-only rebuild | PASS / PASS | 0 / 0 |
| Ruff lint / format / SQLite policy detector | PASS / PASS / zero violations | 0 / 0 / 0 |

Every source cohort reconciles exact selected nodes, JUnit, journal starts,
phase multiplicity and final process status, including failures. There are no
skips/xfails. **3,544 unique ordinary nodes of 5,888** were executed; **2,344
ordinary**, one live and one benchmark node were not run. The exact ordinary
remainder is `ordinary-unexecuted.txt` in the raw bundle. Full ordinary and full
dual-environment release qualification were not requested or claimed.

Fresh comparison against the preserved #133 baseline finds **79/79 same nodes,
phases, raw exception messages, stage refusals and trace path/function sequences**,
with **0 added / 0 resolved**. Against #142 Author XML, all 79 node/phase/stage/
path/function signatures match and 75 messages match; four packaging messages
differ in temporary paths/pytest rendering. Whole raw traceback bodies are
**0/79 byte-identical**: all differences were separately inspected and retained.
They are fixture UUIDs, memory-address/set/environment/temp-path rendering and
four packaging helper frame coordinates (24 to 26). See
[trace-difference-audit.json](trace-difference-audit.json) and complete per-node
diffs/comparisons in the raw bundle. No broad assertion of byte-identical failure
signatures is made. The tests still stop at their inherited Transfer or
Identification Wire refusals, so downstream assertions remain unproved.

Python is **3.12.14**, Hatchling **1.32.4**, and the actually loaded SQLite is
**3.53.1**, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Measured compile options/PRAGMAs/UDFs and interpreter origins are retained.
Dependency preparation precedes offline checks. No SQLite download/build/
replacement/rebinding, extra engine, matrix or product-guard relaxation occurred.

Two preparation mistakes are retained: uv's default cache was read-only (exit 2,
corrected with a workspace cache), and the first evidence-index verifier omitted
the deliberate internal `payload-index.json` self-index from its expected names
(exit 1, corrected after all payload bytes had already matched). Neither is a
test PASS or a product failure. CI-audit bootstrap attempts are likewise retained
in its command records.

## Final #142 hosted CI and publication conditions

The [independent CI report](ci/REPORT.md) verifies live jobs, logs, full decoded
receipt indexes and the exact feature/test-merge/tree. The log receipt ZIPs are
below 2 MiB; the independent #139 receipt-limit series remains unintegrated.

- [Final tests 39892052621](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39892052621): **completed SUCCESS**, 21 indexed payloads verified;
  `acceptance_status=development_checks_passed`, `full_acceptance=false`, runtime
  pytest **0**. Its evidence-only synchronization leaves the sdist gate not
  applicable; the final Access run actually executes that gate.
- [Final Access 39892052634](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39892052634): **completed FAILURE**, 102 indexed payloads verified.
  Broad **3,058 PASS / 59 FAIL / 20 ERROR** across 3,137 nodes. Focused
  **2,696 PASS / 59 FAIL / 20 ERROR** across 2,775 nodes is wholly overlapping;
  do not add it to broad. Hosted unique ordinary execution is **3,137 / 5,888**,
  leaving **2,751 ordinary** unrun. Installed I4/I5 pass on each wheel, both
  original Access probes fail, and sdist/wheel checks pass. Fresh per-node
  comparison supports the inherited 79 failures without relabeling them.

Pages/build inputs and publication allowlist remain unchanged; the local
allowlisted build succeeds with Mermaid placeholders and is not a full rendered
Mermaid acceptance claim. No Pages deployment or release-mode dispatch occurred.
The final published review branch's own Development CI is reported separately in
the Draft PR/handoff; it does not replace the frozen #142 runs above.

The scoped archive repair is ready for acceptance/integration planning. Final
integration execution still requires the intended combined effective-tree
verification, a separately authorized integration action and honest disposition
of inherited failures/unrun product assertions. This review supplies no full
product PASS and performs no integration. No action is denied, awaiting approval
or uncertain at the review checkpoint.

Raw local evidence: [173-payload index](raw-evidence-index.json),
[raw ZIP](raw-evidence.zip), [verification summary](verification-summary.json),
[unchanged-input binding](verified-input-binding.json). Commands, exits, JUnit,
journals, full traces, artifact inventories and the exact executed drivers are
retained. New evidence file hashes and final publication identities are recorded
by the review evidence index and Draft PR.
