# Independent Git / Exchange / CAS corrected-candidate QA receipt

This receipt closes this reviewer's original D1–D6 counterexamples on the exact candidate below. It is scoped review evidence, not overall implementation acceptance. The parent reported a remaining scope-1 A1 direct-SQL current-candidate staging defect and is correcting it on another branch; a later DDL/candidate requires a new exact-source rerun. This reviewer authored no production changes and has no new scoped runtime finding from the executed corrected probes.

## Source and runtime binding

- Source: `b86ff2c96d7558379b2230489e1494630b073ef7`.
- Tree: `085be492d5fbd8cfbcaa7eb4be3d1db27af84fee`.
- Isolated detached worktree: `/workspace/reviews/publication-free-domain-qa-corrected`, clean `git status --short` before and after execution.
- DDL SHA-256: `f1ec742a1d9778dab4ed7950bef0f257d0d368ee8c3d89f945cba61ed23ebd04`, Schema 20.
- Interpreter: `/workspace/git-repo-db/.venv/bin/python`; Python 3.12.14; SQLite 3.53.1.
- Imported module: `/workspace/reviews/publication-free-domain-qa-corrected/src/repo_catalog/__init__.py`, explicitly verified in probes. Every execution used that worktree as CWD and `PYTHONPATH=worktree/src:worktree`.
- Reviewer model / reasoning effort: **not exposed**. No extra subagents.
- The worktree was created at e810427, then rebound to b86 before executions. `git diff --stat e810427` established that b86 changed only the two completed test-disposition rationale JSONs. All measured executions bind to b86, not e810 or dirty root source.

Initial cafa8a8 scripts/results and the authentic old 41dbe55 selected-coverage baseline remain preserved. Corrected scripts and outputs are separate in this directory. No production/history changes, authenticated collection, network/system interaction, or retained catalog mutation occurred. Catalogs were synthetic disposable local fixtures; the two scale fixture catalogs were removed after recording results.

## Executed independent correctness coverage

**52 distinct independently authored nodes have passing evidence on b86.** The original full 26-node suite passed in one execution (`pytest-26.txt`). Fresh corrected cross-module coverage contributes 22 nodes, plus four exact-code-proof nodes. The initial 19 successful cross-module nodes were unchanged by the subsequent fixture corrections and were not pointlessly rerun; the corrected remaining three and new four have separate passing logs.

| Execution | Result | Interpretation |
| --- | --- | --- |
| Original corrected 26 nodes | 26 passed | Complete original set, including SHA-1/SHA-256, NUL boundary width 2/2048, tree and parent interruption, actual subprocess death/rollback, reverse/repeat/reopen/onward Exchange, stale/equal-clock current values, old head A/current B separation, shared-digest quarantine/repair, backup/restore/CAS-41 and receiver-local revision. |
| New cross-module v1 | 19 passed, 3 failed | The failures were this reviewer's fixture selectors/expectation, described below; no production defect inferred from these three failures. |
| Corrected cross-module v2 plus new code-proof nodes | 5 passed, 2 failed, 19 deselected | Cross-domain proof and all four code-proof nodes passed; the two still-failing fixture selectors were corrected after inspecting their actual portable shape. |
| Corrected cross-module v3 targeted remainder | 2 passed, 20 deselected | Both malformed-candidate / valid-sibling cases pass with parent present and missing. |

New passing cases independently check duplicate tree names, same-length blob-map digest contradiction, ref type and peeled-OID disagreement under both formats, read-only TargetReader predicate registration/no writes, supported uppercase header OIDs/octal spelling/Gitlinks, all three decoder families with forged-before-valid and forged-after-valid arrival, detached transferred Issue captures with missing parents and strict rejection of a contradictory registered capture, malformed current candidates rejected individually without suppressing valid siblings, typed cross-domain proof refusal, incorrect list kind/head/base context, and promotion only after real late terminal-list proof.

Fixture adaptations are explicit. The original inconsistent-ref test now permits the actual SQL completion guard to reject, then still requires unavailable snapshot and canonical acquisition rejection. The complete-list fixture uses recognized `pr-commits`/`pr-files` and nested captured head/base `sha` values, aligning the stronger typed proof contract; three independent wrong-context tests protect that boundary. The new malformed-document fixture initially compared a portable typed reference with a scalar ID, then searched an escaped nested key incorrectly. Inspecting actual normalized references led to decoding the referenced document key directly. The new cross-domain fixture initially expected an invalid complete claim to be exported; production already omitted it. The corrected test asserts that truthful omission, then explicitly appends the normalized invalid claim to exercise receiver refusal. All exploratory scripts/logs remain available as v1/v2 copies; no historical result was overwritten.

## Closure of mandatory original findings

| Finding | Actual production correction reviewed | Independent corrected result |
| --- | --- | --- |
| D1 canonical intrinsic availability | Pure `domain/git_intrinsic.py` parsers shared by installation/full checking; computed SQLite predicates in `adapters/sqlite/git_intrinsic.py` and `git_facts.sql`. | Dot, dotdot, slash names, duplicate tree names, malformed tag type/header boundaries and duplicate commit tree headers stay unavailable or meet an enforced guard; valid supported spelling stays usable. |
| D2 false raw Git identity | Canonical physical format/OID/type/size/digest predicate in availability and raw-mapping insertion trigger. | Genuine raw bytes cannot assert a fake verified OID through direct SQL; ordinary raw-mapping insertion rejects. |
| D3 inconsistent exact ref capture | `valid_ref_captures` governs both readers and snapshot completion, matching raw name, format, target OID, type and peeled OID. | Original name mismatch plus fresh type/peeled mismatches reject completion or remain unavailable; canonical validator also rejects. |
| D4 selected export scans unrelated pending state | Indexed exact record-key/owner pending traversal; selected export authorization excludes unselected staging. | Same-repository 0/1000/5000 genuine missing-root candidates yield bounded selected work and identical selected records (table below). |
| D5 quadratic Python Git authorization | One pass precomputes actual repository-associated object keys before mappings are validated. | Actual instrumented record table visits grow linearly at volumes 32/128/512/1024, with correct authorization cardinality. |
| D6 complete code roundtrip loses listing progress | Receiver derives exact code-list progress from actual matching captured context, pages and validated completion markers. | Complete assessment imports with both complete progress rows; wrong kind/head/base stays partial; missing terminal proof keeps assessment pending, and late genuine proof promotes. |

The previous reviewer’s embedded-NUL tree-boundary correction also passes all four independent SHA-1/SHA-256 × 2/2048-width probes. Those fixtures use the canonical byte hash and ordinary table/constraint boundaries rather than disabling schema guards.

## Sequential deterministic work-count probes

These three workloads ran sequentially in order: coverage history, pending history, selected Git authorization volume. Only one comparative probe workload was active at a time. Independent correctness/ordinary/package tests could run in the background on the shared machine. **No exclusive wall-time or comparative latency claim is made.** VM steps and instrumented Python visits describe exact deterministic work for the controlled operation; fixture preparation and pytest durations are not benchmarks.

| Workload | Size | VM steps / actual Python visits | Statements / records |
| --- | --- | --- | --- |
| Unrelated same-scope coverage claims | 0 / 1000 / 5000 | 13166 / 13060 / 13060 VM steps | 320 statements; same 14 records at all sizes |
| Unrelated same-repository pending roots | 0 / 1000 / 5000 | 12013 / 12045 / 12045 VM steps | 265 statements; same 24 records at all sizes |
| Selected canonical Git objects | 32 / 128 / 512 / 1024 | 320 / 1280 / 5120 / 10240 Python table-record visits | 160 / 640 / 2560 / 5120 wire records; 128 / 512 / 2048 / 4096 authorized records |

The small constant first-versus-later differences are reported as measured; there is no count proportional to unrelated history. No detailed cause or latency inference is claimed from these counts. The old 41dbe55 exact coverage baseline was 10102/19055/55055 VM steps. Initial cafa8a8 pending counts were 8940/25983/93983. Initial authorization visits were 3760/58048/920320/3675648. Original measurements remain bound to their original frozen source; corrected output paths never use the old script’s hardcoded original JSON path.

`git_authorization_scale.py` counts actual `record['table']` accesses in the production canonical-byte authorization algorithm using validated synthetic wire records. It proves the identified repeated full scan has been replaced with linear selected-record traversal. It does not certify all end-to-end CLI throughput or every other Python/SQL operation.

## Structural map and test disposition binding

The complete current schema map was regenerated and compared programmatically to the committed map: **exact equality**, including DDL, tables/columns/PK/FK, views, triggers, indexes, baseline delta and responsibility groups. Fresh checks compile all views, find no FKs, report integrity `ok`, and establish generated JSON SQL equals packaged SQL. Actual inventory: 84 tables, 17 views, 367 triggers, 54 indexes. The new coverage-marker relation is a direct indexed immutable declaration of real marker subjects; actual collection/owner/closure validation remains separate. No generic admission/member seal is inferred from its existence.

Fresh ordinary collection on b86 found **2003** nodes. The committed `tests/support/publication_free_node_dispositions.json` still binds to 2002/current SHA `a120050ce70322bb26677249cccfa139ad1ae49847ee6db746a6a92005c1aca9`; the omitted new node is `tests/integration/test_git_canonical_availability.py::test_same_length_content_map_cannot_contradict_canonical_blob_digests`. The parent was informed promptly. Own current-node SHA is `37ab170ac4d8cab081b67df450b077ba386d5b2d81785e48ce4bc336d2d29f8a`. Authentic baseline list has 1950 nodes and SHA `48e0222fede0f74ac6146f9b0215cb0d5c73b56199ac065debacc7ab23c04fef`, matching the committed baseline binding.

The disposition audit against those exact lists succeeds outside the repository: 1950 baseline nodes accounted for, 482 explicit mappings, 1468 same-node survivors, 2003 current nodes. The generated complete report and committed full schema/disposition artifacts are captured here. This establishes counterpart existence/rationale coverage, not execution of ordinary nodes or semantic sufficiency of every mapping. Architecture scope must independently assess the retired/replacement contract rationales.

## Reviewed and unreviewed paths / limits

Initial receipt `../receipt-cafa8a8.md` remains the baseline review ledger. It records full reads of the implementation prompt, design, ADR/handoff, Git parser, Exchange, CAS/payload/Store/current collection/catalog validation/Git context/Exchange service and all intrinsic/capture SQL, plus full baseline diffs of importer, Store, CAS/payloads/transaction helper, maintenance, validation/context/service.

This corrected pass reread root and Phase 2 AGENTS and the complete implementation handoff. It read both new intrinsic modules entirely, current Git parser entirely, CAS integrity and TargetReader, the complete Exchange correction diff and affected current admission/export/promotion methods, the correction diffs for current API/current resources/current collection proof, typed scope/staging JSON validation/generation, Git availability/ref/capture SQL, Exchange indexes/proof-subject relation, schema/disposition audit scripts and relevant exact code/parent/capture consumers. Canonical SQL registration paths in Store/connection port/Graph/TargetReader were traced. The updated full map/disposition artifacts were loaded, compared/audited and preserved, with selected scope-specific mappings inspected.

The complete #25-to-b86 integrated diff is preserved (`full-baseline-diff.patch`, 105299 lines), along with the production/correction supporting-test diff (`production-correction-diff.patch`, 4268 lines). **This reviewer did not consume the entire integrated diff line by line.** The old removed parser/DAG/profile/Exchange implementations, broad GitHub collector/persistence policy, all query/index/CLI/resource schema changes, every generated SQL JSON guard, every old-to-new test rationale and all other changed docs/tests are outside this receipt’s manual completeness claim. Reading generators and fresh equality does not independently trace every guard through every caller.

No complete ordinary execution, lint/format, installed wheel/sdist, hosted CI, full installed package fixture, full selected-volume end-to-end CLI benchmark, snapshot concurrency experiment or authenticated acquisition was run by this reviewer. Those remain separate implementer/final-verifier gates. Scope-1 A1 remains a reported overall blocker on b86; this scope-specific D1–D6 closure must not be turned into overall acceptance or transferred unqualified to changed DDL/source.

## Reproduction commands and artifact preservation

All execution commands used CWD `/workspace/reviews/publication-free-domain-qa-corrected` and this environment:

```bash
export PYTHONPATH=/workspace/reviews/publication-free-domain-qa-corrected/src:/workspace/reviews/publication-free-domain-qa-corrected
export PATH=/workspace/git-repo-db/.venv/bin:$PATH
```

Let `QA=/workspace/review-artifacts/domain-qa/b86ff2c96d7558379b2230489e1494630b073ef7` for the following exact verification commands:

```bash
git rev-parse HEAD HEAD^{tree}
git status --short
/workspace/git-repo-db/.venv/bin/python -m pytest "$QA/test_independent_domain_qa.py" -vv > "$QA/pytest-26.txt" 2>&1
/workspace/git-repo-db/.venv/bin/python "$QA/selected_coverage_scale.py" > "$QA/selected-coverage-scale.txt" 2>&1
/workspace/git-repo-db/.venv/bin/python "$QA/selected_pending_scale.py" > "$QA/selected-pending-scale.txt" 2>&1
/workspace/git-repo-db/.venv/bin/python "$QA/git_authorization_scale.py" > "$QA/git-authorization-scale.txt" 2>&1
/workspace/git-repo-db/.venv/bin/python -m pytest "$QA/test_corrected_crossmod.py" -vv > "$QA/pytest-crossmod-v1.txt" 2>&1
/workspace/git-repo-db/.venv/bin/python -m pytest "$QA/test_corrected_crossmod.py" "$QA/test_corrected_code_proof.py" -vv -k 'malformed_current_candidate or issue_terminal_marker or wrong_listing_capture or complete_code_assessment_waits' > "$QA/pytest-crossmod-fixture-v2-code.txt" 2>&1
/workspace/git-repo-db/.venv/bin/python -m pytest "$QA/test_corrected_crossmod.py" -vv -k malformed_current_candidate > "$QA/pytest-crossmod-fixture-v3.txt" 2>&1
/workspace/git-repo-db/.venv/bin/python scripts/audit_publication_free.py > "$QA/schema-map-actual.json"
git diff 0bd5704caca2f6e3723bef22531b065cd4d7bad0 > "$QA/full-baseline-diff.patch"
git diff cafa8a8b143fe095b79f282690a6edf98e6f660e -- src/repo_catalog tests/integration/test_git_canonical_availability.py tests/integration/test_publication_free_architecture_corrections.py > "$QA/production-correction-diff.patch"
/workspace/git-repo-db/.venv/bin/python -m pytest --collect-only -q -m 'not live and not benchmark' tests/unit tests/integration tests/e2e > "$QA/current-ordinary-collection.txt" 2>&1
/workspace/git-repo-db/.venv/bin/python scripts/audit_publication_free_test_dispositions.py --baseline "$QA/baseline-ordinary-nodes.txt" --current "$QA/current-ordinary-nodes.txt" --output "$QA/disposition-actual.json" > "$QA/disposition-audit.txt" 2>&1
```

The original corrected 26-script was copied from the immutable initial script and only the explicitly described fixture adaptations applied. The coverage script was copied from the original reviewer and changed only output/provenance recording, not its workload. V1/V2 cross-module script copies bind their exploratory logs; `test_corrected_crossmod.py` is final fixture v3. A small disposable inspection printed only the normalized document key/reference/resolved provider ID to correct the selector; it made no production changes. Static inspection used `cat`, bounded `sed`, `rg`, `git diff`, `git worktree list` and complete JSON loads/comparisons. `metadata.json` captures exact source/runtime/module path, source file hashes and all artifact hashes; source files and historical artifacts remain untouched.

On the next corrected candidate, preserve this receipt/results, copy final scripts to its separate exact-commit directory, rebind CWD/PYTHONPATH, and rerun the affected full independent set against actual new DDL. Pure Git source-file equality can explain unaffected code, but cannot substitute for the changed-schema fixture execution.
