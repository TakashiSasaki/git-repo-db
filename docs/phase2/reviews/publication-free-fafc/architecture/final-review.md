# Independent Architecture / DDL re-review — frozen fafc1b2

**Scope 1 outcome: re-review completed; no open mandatory architecture finding identified in the reviewed and executed boundaries.** A1–A6 and the b86 A1/A6 residuals are corrected in the evidence below. This is an exact-source architecture receipt, not full ordinary/distribution/hosted-CI acceptance. The original 41dbe555 and b86 failure receipts remain unchanged.

## Exact binding and independence

- Source SHA: `fafc1b2d4d2e1986768143cc71a0e55cba943ba3`.
- Tree: `6f566cb3e91e25facda60671c40108e0a9f8965b`.
- Detached worktree: `/workspace/reviews/publication-free-architecture-final-fafc1b2`; final `git status --porcelain` is empty.
- Schema 20 composed DDL SHA-256: `bf6deb09471a361918ab9d9e97ca1ba204060ffc78420972775a914357912f26`.
- Primary interpreter: `/workspace/git-repo-db/.venv/bin/python`, Python **3.12.14**, SQLite **3.53.1**.
- Additional native compatibility execution: `/workspace/review-artifacts/schema-a1-b86/native345-venv/bin/python`, Python **3.13.5**, SQLite **3.45.1**, with `LD_LIBRARY_PATH=/workspace/review-artifacts/schema-a1-b86/sqlite345/lib`. The shared interpreter has its own SQLite runtime; setting that library path does not switch its SQLite. The additional runtime is therefore recorded separately, not described as the shared interpreter.
- Both audits and both negative/boundary programs explicitly verify that `repo_catalog.__file__` resolves inside the exact final worktree. The direct reviewer-owned inventory also asserts SHA and tree.
- Model and reasoning effort: **not exposed**.
- No production/test source or Git history was edited. All own catalogs are in memory; existing pytest fixtures create disposable local state. No user catalog, credential, authenticated traffic or external service was used.

Original full owner-document reads and review context survive: root and Phase 2 AGENTS.md, design, no-independent-publication ADR, decision register, implementation prompt and implementation handoff. Applicable AGENTS.md files were checked again on this final tree. The final handoff delta was read in full; previous full handoff and baseline-to-integrated architecture review are retained. New full diffs are stored from both #25 (`0bd5704c...`) and the merged design baseline (`6ca31eb9...`) to this candidate, plus the complete b86 correction diff. This review did not rely on a success summary.

`original-hash-check.log` and `b86-hash-check.log` prove that the original manifests still validate. Original scripts/results are not reinterpreted as passes. New scripts/results live only in this directory or its `native345` subdirectory. Own fixture copies supply memory setup and synthetic candidates; their legacy initial-probe entrypoint was not invoked. Existing selected pytest programs are identified separately from independently authored programs.

## Findings and corrected behavior

| Finding | Final evidence and outcome |
| --- | --- |
| A1: original-bearing/open modeled JSON; b86 A1-R: incomplete typed pending candidate and capture-owner mismatch | Both runtimes reject 11 closed-capture variants and malformed modeled Issue metadata. Bad wire metadata is rejected before missing-parent staging while valid sibling records admit. Three malformed standalone pending envelopes reject. A strengthened independent probe uses a correctly shaped `current-state:` key and rejects **26** minimum/nullable identity, producer, capture-owner/parent, boolean and out-of-int64 clock variants in both Python and direct SQL. A genuine missing PR parent stages, later promotes, and leaves usable export. Full catalog validation passes afterward. |
| A2: foreign Source assessment or malformed roster member accepted | Eight API and seven direct SQL variants reject wrong Source/service, foreign positive pair, invalid identity, object-shaped or duplicate member, nonterminal completeness and nonboolean API terminal. A valid complete assessment succeeds; a later partial empty assessment preserves the known positive pair. |
| A3: unrelated domain marker qualifies Git completeness | An empty terminal issues enumeration cannot qualify Git Coverage through Python/Graph. The new marker-reference index mirrors the declared typed reference, but its presence does not qualify Coverage. Export/receive do not create complete Git Coverage from it. |
| A4: thread roster completion omits replies obligation | A present thread without its replies obligation fails Python/Graph qualification and native marker insertion. A genuinely observed empty terminal roster accepts its exact empty tree proof. |
| A5: removed behavioral functions lack exact replacement mapping | All **1,950** actual baseline nodes are accounted for by **487** explicit mappings plus **1,463** same-node survivors. All **193** removed/renamed functions are mapped, every replacement is actually collected, and every mapping carries a rationale. This closes the missing-map finding; collection existence does not by itself prove every replacement assertion sufficient. |
| A6: live positive tests still require removed authority; b86 A6-R: portable identity queries removed inventory table | Original cache/manual-Source/transaction ports and representative collection/selected-pending checks pass: **27 passed**. The whole portable-identity file now passes all **18** cases; timestamp file **115** and transaction file **5** pass as well, totaling **138 passed**. No stale compatibility table was restored. |

The b86 residual reproduction remains immutable. The final pending regression is stronger than that reproduction: it uses a valid operational key shape, requires both Python and native rejection, requires zero retained stage rows, validates the catalog, checks export remains usable, and separately demonstrates legitimate missing-dependency promotion. No malformed assertion was weakened to make the script succeed.

Additional independently authored final checks execute on **both SQLite versions**:

- Real Issue label/milestone/creator metadata is valid. Six malformed nested creator/label shapes reject through Python and direct SQL. Escaped recognized property names retain their type guards; a decoded duplicate property is rejected.
- SHA-1 and SHA-256 decoder candidates with a real producer key but text inconsistent with canonical bytes reject at ordinary native insertion. A separate disposable memory-only fixture drops that local guard to simulate a retained malformed row: computed valid-candidate views and readers exclude it, full check reports its specific `GIT_DECODER_FACT`, and the healthy candidate remains usable. No production trigger was dropped.
- Pure canonical tree predicates accept a real tree sequence and reject duplicate names; a NUL-bearing SQL intrinsic name rejects. Correct and contradictory MD5/SHA-1/SHA-256 digest predicates are checked against bytes. Operational receipt/alias deletion leaves the valid intrinsic tree available.
- Two hundred genuine unrelated pending collection records with absent PR parents leave selected export unchanged. The exact key/repository lookup uses `exchange_staging_record_owner` in EXPLAIN.

The primary-runtime independently authored positive program also completes:

- A caught injected inner statement failure rolls back current values, field evidence and local revision, while an unrelated outer edit commits.
- Failure at a tree's second intrinsic entry leaves no partial new owner/entries for either canonical OID format; an unrelated valid object remains available. Missing children retain actual OIDs and NULL real-object links.
- UTF-8 and Latin-1 decoding yield two genuine disagreeing candidates, no selected fact, and no producer-version/time winner.
- **10,000** comparable accepted PR edits leave exactly **one** current PR row, **zero** pending rows, **zero** collections, and singleton local revision 10,000. The only nonempty tables are database identity, service/repository/binding, PR identity and PR current state. No unconditional normalized PR history or generic transaction/result owner is installed. This is not a physical text-GC claim.
- A genuine equal-clock current conflict remains blocked after deleting `exchange_admissions` and `exchange_local_identities`; these processing indexes do not determine domain admissibility.

## DDL, generated JSON and live consumers

The independent direct PRAGMA program, without the repository inventory helpers, verifies:

| Native object | Count |
| --- | ---: |
| Product tables | 84 |
| `table_xinfo` columns | 617 |
| Generated columns included above | 3 |
| FK constraints / FK column rows | 141 / 190 |
| Views | 20 |
| Triggers | 556 |
| Explicit indexes, excluding SQLite autoindexes | 55 |

Generated columns are `issue_resources.parent_kind`, `review_resources.parent_review_kind` and `review_resources.reply_kind`. `direct-pragma-inventory.json` retains every table's full DDL, PK, columns, FK rows and indexes, plus all view/trigger/index SQL. Both additional composed audits independently run the functioning repository map/dependency helper functions against new memory catalogs; both match these counts. All **20 views** and **252 insert/update/delete shapes** compile, including trigger accesses. Foreign keys and recursive triggers are enabled, FK check is empty, integrity check is `ok`, and all **50 JSON columns** are inventoried.

On both runtimes, freshly generated Python JSON guards equal the packaged SQL exactly, and the regenerated whole schema map equals the checked map exactly. Both whole-checkout SQL inventories find **450 compiled production literal SQL sites**, **143 dynamic/non-DML sites**, and **zero failed literal preparations**. Dynamic sites remain an explicit limit, not converted into a compile pass. Native SQLite 3.45.1 additionally executes all **63** pending-contract regression cases, including signed epoch boundaries, escaped keys, field-origin/value correlation, usable missing-parent promotion and the detached Issue-comment capture exception.

The bounded tree SQL enforces decoded property paths and array depth using flat predicates rather than parser-deep expression nesting. Candidate shape and envelope validation are distinct from dependency existence. Pure Git candidate views derive validity from canonical bytes and concrete decoding; they do not store a new eligibility/profile certificate. The marker reference and selected-stage indexes mirror typed references rather than create completeness authority. Actual subject tables still represent identity, current value, intrinsic object structure, capture, enumeration/completeness, physical integrity or local operation. No renamed independent Publication/result/batch/member seal was found in the reviewed boundaries.

A final `rg` of production and corrected portable tests for retired inventory/parser/publication tables finds no live production reference; the portable tests explicitly assert that `inventory_observations` is absent. Historical archived receipts remain historical. The old historical `audit_phase2_dependencies.py` full entrypoint was not represented as a working final gate: only its functioning schema/source helpers were invoked. Its known initial entrypoint failure remains in the original receipt.

## Test mapping and fixture port review

Final ordinary collection completes with the documented selection: **2,128 nodes collected in 28.52s**. The earlier independently collected actual merged-design baseline supplies exactly **1,950** nodes. Re-running the disposition CLI with these actual rosters accounts for every baseline node and all 193 removed/renamed functions. `direct_inventory.py` independently checks disjoint complete coverage, actual target existence, rationale presence, and equality of every semantic field in the generated versus checked exact-node receipt.

The own command requests `tests/unit tests/integration tests/e2e` in that order. The tracked collection orders the same nodes differently. Own ordered-list SHA is `bae7189a8b50bca59a19f13501cfb9e833f1cd61551fd7a16cba2f1a97ba7d20`; tracked SHA is `88ce59a32b14839d01f2d7d9363583621d6ced3bb3e1ac8282877fc197d84852`. Their byte lengths and complete node sets match. Baseline SHA is `48e0222fede0f74ac6146f9b0215cb0d5c73b56199ac065debacc7ab23c04fef`. The first direct-inventory attempt demanded whole receipt equality and stopped at this ordering-only hash difference; `direct_inventory.run1.py` and `direct-inventory.run1.log` preserve it. The final harness compares all semantic fields and verifies the independently collected set against the actual retained tracked-list bytes and hash. No product assertion or mapping was removed.

Portable test corrections preserve `NO_USABLE_SOURCE`/`SOURCE_UNCONFIGURED`, no job/evidence effects, the exact configured Source's complete assessment, actual positive membership and skip checkpoint diagnostic. Assertions against the removed observation table are replaced with an explicit absence assertion and the real current pair/assessment subjects. All three formerly failing b86 nodes are among the 18 passing cases. Timestamp fixtures use the sole composed DDL and real SQL-function registration; signed storage/range/order and invalid-type assertions remain. The removed `reanalysis_runs` branch was already unreachable under the one remaining fixture parameter; no parameter was excluded by the final fix.

Earlier rationale/body inspections remain valid: real labels/milestones replace unsupported opaque provider objects while preserving sparse/nested provenance; pure-merge shape matrices are explicitly persistence-sink tests rather than claims of valid provider admission; malformed sibling tests assert rejection and good-sibling survival; thread proofs enumerate actual obligations; Git retirement mappings preserve real capture/bytes/ambiguity separately from removed profiles and publication. The executed own probes cover those concrete architectural obligations. No blanket claim is made that collection/mapping proves every surviving behavioral assertion sufficient.

## Exact execution commands and results

All primary commands use CWD `/workspace/reviews/publication-free-architecture-final-fafc1b2` and prefix:

```sh
env PYTHONPATH=/workspace/reviews/publication-free-architecture-final-fafc1b2/src:/workspace/reviews/publication-free-architecture-final-fafc1b2 PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python
```

The following own programs complete with exit 0 and complete JSON/logs: `rejection_probes.py`, `positive_probes.py`, `cross_module_probes.py`, `new_boundary_probes.py`, `composed_audit.py`, and the corrected `direct_inventory.py`. They are invoked by absolute artifact path. The first direct-inventory run exits 1 for the disclosed ordered-hash assertion; its corrected rerun exits 0. No incomplete positive/10k result was substituted for completion. The interrupted previous turn was not an implementation failure; existing complete outputs were verified, and additional needed runs completed in this resumed review.

Additional native prefix:

```sh
env LD_LIBRARY_PATH=/workspace/review-artifacts/schema-a1-b86/sqlite345/lib PYTHONPATH=/workspace/reviews/publication-free-architecture-final-fafc1b2/src:/workspace/reviews/publication-free-architecture-final-fafc1b2 PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/review-artifacts/schema-a1-b86/native345-venv/bin/python
```

It executes separate `native345/rejection_probes.py`, `native345/cross_module_probes.py` and `native345/new_boundary_probes.py`, all exit 0. Native composed audit invokes the root `composed_audit.py` with `ARCHITECTURE_AUDIT_OUTPUT=/workspace/review-artifacts/architecture/final-fafc1b2/native345`; exit 0. It also runs `-m pytest -q tests/integration/test_publication_free_pending_contract.py --junitxml=<artifact>/native345/pending-contract-tests.xml`: **63 passed in 63.57s**, no failures/skips.

Primary commands and complete results:

```sh
-m pytest -q tests/integration/test_catalog3_portable_identity.py tests/integration/test_catalog3_timestamps.py tests/integration/test_publication_free_transactions.py --junitxml=<artifact>/behavioral-ports.xml
# 138 passed in 63.52s; no failures/skips

-m pytest -q tests/integration/test_catalog3_cache.py::test_gc_obligations_and_preserved_source tests/integration/test_catalog3_job_plans.py::test_manual_inventory_has_source_owned_current_roster_and_assessment tests/integration/test_database.py::test_constraints_and_transaction_atomicity tests/integration/test_phase2_collection_integrity.py tests/integration/test_phase1_exchange_scaling.py::test_selected_git_work_ignores_unrelated_same_repository_pending_roots --junitxml=<artifact>/representative-tests.xml
# 27 passed in 70.00s; no failures/skips

-m pytest --collect-only -q -m 'not live and not benchmark' tests/unit tests/integration tests/e2e
# 2128 collected, collection only

scripts/audit_publication_free_test_dispositions.py --baseline /workspace/review-artifacts/architecture/corrected-e810427/baseline-nodes.txt --current /workspace/review-artifacts/architecture/final-fafc1b2/ordinary-nodes.txt --output /workspace/review-artifacts/architecture/final-fafc1b2/resolved-node-dispositions.json
# 1950 accounted for; 487 explicit mappings; 2128 collected; exit 0

sha256sum -c /workspace/review-artifacts/architecture/artifact-sha256.txt
sha256sum -c /workspace/review-artifacts/architecture/corrected-e810427/artifact-sha256.txt
# all retained entries OK
```

`<artifact>` denotes this artifact directory. Logs are the corresponding `*-probes.log`, `composed-audit.log`, `native345-composed-audit.log`, `direct-inventory.log`, `behavioral-ports.log`, `representative-tests.log`, `ordinary-collection.log` and native pending log. Every executed own program retains its source and JSON result. Native/static inventories and regenerated whole map are retained in both runtime directories. Timings are execution receipts from concurrent QA, not sequential comparative benchmarks.

## Reviewed and unreviewed scope

`path-review-manifest.json` enumerates **all 246 changed paths** from the actual merged baseline to final, with per-path review depth, plus unchanged explicit owner/source helpers. `changed-since-b86-paths.txt` enumerates all **78** correction-era paths, including archived receipts. This reviewer inspected the original integrated architectural change and then the final current API/resources, generated JSON, typed staging, Exchange, pure Git decoding/intrinsic, query/index/full-check, schema-audit and fixture-port corrections. Native inventories cover every composed table/column/PK/FK/view/trigger/index and JSON slot; static caller inventory covers live production, CLI and test SQL. Archives are enumerated but are not re-executed or treated as this reviewer's final proof.

Most changed test files receive actual-node/static-disposition inspection rather than full manual assertion-body review or execution. The manifest says so. Comprehensive acquisition HTTP/restart/cancellation/incremental machines, live Git collection and cache traversal, exhaustive Exchange reverse/repeat/late-ref/CAS/backup/restore/package behavior, all 143 dynamic/non-DML SQL sites, and scale bounds beyond the executed synthetic checks are outside this receipt's full execution claim. Full ordinary execution, installed wheel/sdist execution and hosted CI are not performed or accepted here. These remain the parent's separate mandatory final gates; no authenticated collection or retained catalog test is permitted by this task.

The review remains available for another exact-tree affected-path review if subsequent source changes occur. This receipt applies only to fafc1b2 and does not anticipate or replace final integrated gate results.
