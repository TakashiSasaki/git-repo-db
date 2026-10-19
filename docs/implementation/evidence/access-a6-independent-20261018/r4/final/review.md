# R4 final independent review: actual execution and semantic gates

Reviewer: R4, independent of the correction author. Baseline review:2026-10-18 12:36:09–12:45:01 JST. Post-fix review start:2026-10-18 12:51:29 JST. Final actual end:2026-10-18 13:15:03 JST.

Tested source HEAD: `536ad33941283a439825ad606b8718c88c967ffa`.
Tested tree: `169b5d7ad5dea4fa271f71bea96863bc318fb332`.
Read-only final worktree: `/workspace/access-review-typed`, clean throughout and at completion. R4 made no product/source changes and did not run product pytest, packaging or MkDocs. Root authored corrections and performed those executions; R4 independently reviewed their actual raw evidence and frozen source.

## Outcome

R4's assigned independent source/assertion/evidence/ADR review is complete, with no remaining material issue in that scope. Baseline R4-01 gate separation and R4-02 positive-grammar/full-history evidence references are addressed. Implementation item16 now has actual successful finite verification at the tested source; its earlier pending source-checkpoint wording is resolved by current execution evidence, not by transferring a superseded PASS. Item11 remains partial for the explicit cross-seed Exchange contract; item15 remains the optional unimplemented extractor and excluded real-data operation. Whole-record ADR approval, merge, P8 and release remain separate gates.

## Actual evidence independently checked

R4 independently parsed collection, JUnit and the per-node journal, rather than accepting a count or root's reconciliation alone:

- **1,877 unique selected nodes** agree exactly across collection, JUnit and journal starts. Every node has exactly one passed setup/call/teardown, no failed/error/skipped result, and one successful completed journal finish. All64 linked ledger functions actually ran.
- Compared with this session's actual minimum-SQLite baseline collection, **75 nodes were added and zero removed**. All additions belong to the new correction module. They are a subset of1,877, not another independent test count.
- The previously interrupted P4 `test_actual_git_notes_command_and_no_lazy_network` nodes ran again and passed all phases. Neither the f81a exit2 checkpoint nor8dcb's interruption-associated failed call/SIGTERM exit-15 is treated as full acceptance or hidden as a skip.
- The focused run actually executed **2026-10-18 13:05:30–13:09:19 JST**, with pytest reporting228.72 seconds. Root's process wrapper measured229.57 seconds including startup/exit. The loaded runtime was **Python3.13.5 / SQLite3.51.3**, source ID `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
- All six required audits, Ruff lint, Ruff format and cumulative whitespace checks have actual exit0 at this same source/tree. Normalized workflow collection/execution targets equal the actual argv; workflow SHA256 is `8679801b74fe63cc15b4df13158cd28a908ea8f4b696d5a611e1e78282d603bd`.
- A separate **49-node compatibility cohort** has exact collection/JUnit/journal and passed-phase equality. Its node set is disjoint from the focused cohort. It is supplementary selected compatibility evidence, not complete ordinary/release validation.

`typed-source/actual-execution-review.json` records these independent calculations, exact interrupted-node outcomes, commands/times, package provenance and gates. `typed-source/root-raw-receipt-hashes.json` binds the inspected raw files by length/SHA256. R4's parser/hashing work is evidence inspection, not another product test run.

## Complete source and distribution binding

All450 recorded selected inputs match the read-only tested source. R4 additionally verified **all2,662 tracked-source hashes and exact path-set equality**; this complete snapshot includes ledger/design/disposition/ADR files that the smaller450 map does not. The clean Git archive used by packaging has the declared536ad commit comment and exactly the same full member/hash map. Its SHA256 is `58150752ce0c72584c5bfbe264a274aea7a8a7fc61d13046c3f26b775b695b7d`.

Both direct wheel and sdist-derived wheel actually passed isolated installed smoke. Their recorded module origins are in separate environments' `site-packages`, under their own interpreter prefixes and outside checkout/source archive. The inspected helper uses fresh environments, removes PYTHONPATH and invokes `-I`; this is not a source-overlay result. Actual SQLite/source ID and supported local Git acquisition, inactive Access restore and Scope fork are recorded for both. Both wheels have SHA256 `441dc6f00b71046a98c6d28d454bc40f32ed4e4350b380bb3209376ed7b52542`; their built sdist has SHA256 `816ab86e8abec5af0ee3c2c7f5fca1c66b65f9b8574b3c1434a309f655f14530`. These are installed smoke checks, not the full pytest cohort run against each installation.

Before the later evidence-only commit, R4 rehashed every original source file in the working branch: only `docs/implementation/access-a6-independent-review.md` changed, and every new staged path was under the frozen evidence directory. `evidence-only-precommit-proof.json` records that actual check. The final PR/evidence commit and hosted CI must still be named separately; R4 does not claim a future commit/tree or CI execution has already occurred.

## Documentation, ADR and skills

The actual existing-allowlist MkDocs command returned exit0 with zero broken links and zero sensitive/disallowed outputs. R4 inspected all **ten actual staged SVGs**: each exactly equals the placeholder emitted by `--no-mermaid`. The legacy summary's wording "Mermaid Diagrams Rendered:10 SVGs" therefore describes placeholders in this run, not fresh Mermaid rendering. No deployment is performed or inferred, and internal Access documents are not automatically part of the public site allowlist.

All accepted ADR content, accepted0003, proposed/date-null0029 and AGENTS are byte-unchanged. The independent43-clause carry-forward map remains valid for those unchanged ADR bytes, with no material preserved-clause loss found after existing0004/0014/0026/0028 refinements. This is preservation review, not owner approval of the whole replacement.

At the exact tested536ad source, the complete filename inventory is **28 files /54 occurrences**;25/26 is explicitly the historical baseline inventory. Added review artifacts contain historical identifiers and copied source inventories, not new current authority. Current guidance, historical dependencies/plain metadata and immutable receipts retain distinct handling. New evidence files can add further historical mentions, so actual future retirement still needs a fresh final-tree scan.

Updated skill guidance and links were reviewed independently, frontmatter retained, and all26 changed-Markdown relative links resolve. The lessons retain actual BOM/guard/nested-source/stored-Capture counterexamples and their limits without granting permissions or changing architecture.

## Final26-item and authority disposition

`typed-source/semantic-acceptance-verified.md` / `.json` give every item's current implementation status, actual linked execution and precise limits. The finite implementation result is **24 covered, item11 partial, item15 deferred**. In particular:

| Gate | Final R4 disposition |
| --- | --- |
| Item16 implementation verification | Passed for the exact focused runtime/schema/P7/installed-smoke scope above |
| R4 independent source/assertion/receipt review | Completed within assigned scope; separate R2/R3 behavior reviews retain their own authorship |
| Item11 multi-repository Exchange | Explicit partial contract remains; mismatch/pairing guards preserved, no invented repository-set/receiver-target meaning |
| Item15 legacy extractor / real data | Optional extractor absent; classifier is not extraction; real-data operation not authorized or performed; no blanket migration gate |
| Whole-record ADR replacement | Explicit human acceptance and actual acceptance date still required; no retirement or accepted-status change performed |
| Merge / auto-merge / default-P8 activation | Not authorized or performed by R4; passing tests supplies no authority |
| Release qualification / release / tag / deployment | Not requested or performed; focused and supplementary checks do not establish full release eligibility |

Full ordinary/release pytest, full installed pytest cohorts, hardware power-loss guarantees, privileged-writer adversarial guarantees, remote SSH/HTTPS/container execution and real-user data operations remain outside the claimed execution. Stored remote settings are not remote execution support. No missing real-data authorization or release gate was used to stop the authorized corrections.
