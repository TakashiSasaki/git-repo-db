# Independent final audit of PR #133

Reviewer: a separate non-implementer agent, `/root/independent_audit`.
Result: **PASS; no unresolved material source-code finding**. This is a read-only audit of the reviewed repositories, not merge or release authorization.

## Fixed inputs

- Repository: `TakashiSasaki/git-repo-db`, PR #133.
- Source HEAD: `f16e5b1713bde9a2f18263a25397c4b450fd5773`.
- Source Git tree: `6bfa580baafa9f6a117b7a0b610c4e65cd031b86`.
- Stack base (#132): `a022dd3efb9c8116cf9dc0abc13ab1d5bbc88e37`.
- Existing evidence publication: `14b7901c95b01b1ad2fc162f76e0210abc049a96`, at `docs/implementation/evidence/adr0032-host-runtime-20261022/`.
- Hosted execution merge: `b5f5026b07826b551cbd35ec39ac0ef3ca214a99`; receipt tree equals the fixed source tree.

I read the applicable AGENTS.md, ADR 0032, `ci-final-tree-verification` and `lessons-to-skills` guidance, implementation diff, workflows, runtime manifest/probe, distribution drivers and raw execution receipts. No source or frozen evidence was edited. No new skill is needed: the existing CI skill already describes the verified receipt and runtime-identity procedures.

## Independently verified evidence

The fresh GitHub connector logs in this audit directory decode to byte-identical published receipt ZIPs. Strict base64, BEGIN length/digest and matching END were checked:

- Access 39799299209: 1,632,586 bytes; SHA-256 `511732209c4fda5c84a61b470ea4f56f271a6bbcb3c5e1842680dd0c6c1ff4b6`.
- Tests 39799299296 offline job: 70,747 bytes; SHA-256 `36eddda2b07aa7a70e1022849e3b02526ec8ffb5b1ddc8faf0c5d4437ba38add`.

The outer payload SHA-256 is `e38171c16b5e58cfa222f281ea87406645ae85876cc05aa9f34f055749a76176`; all 150 indexed members match their lengths and hashes. All three nested receipt indices match their members. Execution bindings identify the specified runs/attempt and final source tree. Each of 456 frozen input hashes matches the pinned source, independently checked in the I5 execution binding and both offline inventory before/after sets.

I independently reconstructed duplicate-aware selected/JUnit/journal-start equality and exactly-once setup/call/teardown rules for the hosted source cohorts: I5 29, I4 217, and broad regression 3,137 nodes. I4/I5 pass. Broad results are 3,058 passed, 59 failures, 20 setup errors, zero skipped. The original Access cohort has the same 79 non-success nodes.

All 79 broad non-successes match the PR #132 frozen `run-3594f47/i5/regressions.xml` by node, phase, refusal and complete recorded frame sequence including line numbers: zero added, zero resolved. The four differing messages are subprocess assertion wrappers with environment-specific temporary installation paths and the observed pytest CompletedProcess-repr truncation boundary; the underlying exception/refusal remains `UnsupportedIdentificationStage` / `I2_IDENTIFICATION_WIRE_UNSUPPORTED`. The other 75 exception messages match. Original-versus-broad subprocess wrappers also contain temporary-path differences and must not be compared as unnormalized whole-message equality.

The 79 comprise 37 direct UnsupportedResourceStage call failures, 20 UnsupportedResourceStage setup errors, 10 direct UnsupportedIdentificationStage failures, seven sqlite3.IntegrityError stage-fence failures and five assertion wrappers. Their original failures remain visible; this audit does not treat them as success.

## Runtime, policy and actual installations

Eight hosted runtime receipts agree on resolved selected Python, executable digest, built-in SQLite, source ID, compile options and mappings, with null loader overrides. Python is 3.12.15; SQLite is 3.53.1; source ID is:

`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.

Real Access and P1 factories plus STRICT, JSON, FTS5 and WAL probes pass, including inside each actual direct-wheel and sdist-derived-wheel venv. Their product-module paths are in their own site-packages. Recorded installation commands are offline, no-index, no-deps and hash-required; artifact hashes, installed file measurement, source binding and original outside-checkout checks are retained. Both installed I2/I3 probes and I4 217/I5 29 pass. Both original Access smokes still return exit 1 at the inherited Transfer refusal.

Product source is byte-unchanged from #132. No original test target/assertion or safety predicate was removed. The selected archive is the complete checksum-bound CPython distribution; no SQLite component is separately obtained, compiled, installed or swapped. No multiple-SQLite validation requirement or fixed SQLite release equality gate was added. Same-invocation identity comparison is receipt binding, not cross-environment version policy. I independently reran the four stdlib runtime-selection tests (pass) and policy detector (zero violations) using the environment Python 3.12.14 / its actual built-in SQLite 3.53.1. That run is tool-only and is not new product acceptance.

## Scope and remaining limits

The bounded I4/I5 fixtures intentionally remove the two named I2 Transfer stage fences in disposable test databases. Their passing outcomes establish the reviewed bounded lower-level behavior and installed-code execution; they do not establish end-to-end production Transfer support. Unmodified production/Access smoke rejection remains an unresolved functional outcome. Identification wire and downstream I6/I7 work are unfinished.

I independently recomputed inventory coverage: 5,742 ordinary nodes; hosted unique 3,172, leaving 2,570 unexecuted on the host. With the disjoint final local 289-node tool cohort, unique coverage is 3,426 and 2,316 ordinary nodes remain unexecuted. One live and one benchmark node also remain unrun. Installed duplicates do not add ordinary source coverage. Additional offline cohorts were inventory-only. The mutable-input local broad trial remains excluded. No complete release acceptance is established.

The local 289-tool cohort has unittest-subTest extra call events; its evidence must not be described as strict one-call-per-node phase reconciliation. Hosted source 3,137/29/217 reconciliation does pass. This audit validates existing hosted executions and installation receipts rather than creating new hosted product executions or retrieving original artifact binaries again.

## Recommendation

I6+ engineering development may begin using this qualified hosted environment and the explicitly retained 79-case baseline. Continue to track the production Transfer and identification-wire refusals as unfinished functionality, preserve original assertions and failure evidence, and qualify any future source change at its own HEAD/tree. This judgment does not authorize a merge, release, deployment, or imply that complete I1-I5 end-to-end/full-release acceptance has passed. No I6 implementation was performed during this audit.

## Audit helper peer review

I reviewed root's `audit.py` read-only. The initial helper incorrectly asserted whole-record equality between original and broad non-successes despite four legitimate temporary-path message differences; I reported the issue before publication. The final corrected helper and generated results were reviewed as recorded below.

The corrected helper and generated `audit-results.json` were reviewed. It now compares the original/broad phases, refusal codes and complete frame sequences, and retains message differences separately; its limited pytest-venv-path and observed CompletedProcess-repr normalization leaves substantive exception/trace/refusal text intact. Its recorded 153 installed source/DDL/JSON file hashes agree between both wheel installations and pinned source. Its result numbers match my independent receipt, failure, runtime and coverage checks. Coverage and strict journal/input checks were independently recomputed above; the helper itself copies the existing coverage summary rather than replacing that independent verification.

I recommended that its numerical step-exit inference use actual workflow `run` steps rather than the initial `number >= 5` heuristic, which also selected upload-artifact action steps. GitHub REST does not expose a numerical exit code for each composite action/job. Preserve their observed conclusion, and explicitly distinguish raw-log exit 1, successful-shell exit 0 inference and unexposed/non-process numerical codes. This is a reporting correction outside the reviewed product source; no product rerun is implied.

Final follow-up verified: root replaced the heuristic with exact workflow run-step sets and regenerated results successfully. Upload-artifact and other action/non-process steps now retain null numerical codes while keeping their observed conclusions. The reporting recommendation is resolved; no unresolved material audit finding remains.
