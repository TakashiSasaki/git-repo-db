# Independent Architecture / DDL re-review — frozen b86

**Outcome: changes required; no acceptance.** Original A2–A4 and the original-bearing part of A1 are corrected in independently executed probes. Two mandatory residuals remain: malformed current pending candidates pass SQL/catalog validation, and three ordinary portable-identity cases still query the removed inventory table. Exact baseline-node reconciliation is complete, but its recorded current count/hash is stale by one new node. The reviewer remains available for an exact corrected-tree affected-path re-review.

## Binding, authorization and independence

- Exact executed candidate: `b86ff2c96d7558379b2230489e1494630b073ef7`; tree `085be492d5fbd8cfbcaa7eb4be3d1db27af84fee`.
- Isolated detached worktree: `/workspace/reviews/publication-free-architecture-corrected`. Initially bound to `e810427fba1f205c9dd5c1a8abe75a3412402b6e` / tree `553485873684e22d1f2c15261c22d3f58ee79a7d`, then rebound before actual execution. The b86 delta contains only two rationale JSONs; production/executable tests are unchanged from e810.
- Schema 20 composed DDL SHA-256: `f1ec742a1d9778dab4ed7950bef0f257d0d368ee8c3d89f945cba61ed23ebd04`.
- Python `/workspace/git-repo-db/.venv/bin/python`, Python 3.12.14, SQLite 3.53.1. `repo_catalog.__file__` explicitly verified as `/workspace/reviews/publication-free-architecture-corrected/src/repo_catalog/__init__.py`, again after execution.
- Model and reasoning effort: **not exposed**.
- Original context, complete owner-instruction reads and immutable independently authored scripts/results are retained. `sha256sum -c /workspace/review-artifacts/architecture/artifact-sha256.txt` passed for both original scripts, integrated original diff and initial receipt. The initial review remains bound to 41dbe555; it has not been rewritten as a success receipt.
- Required owner documents were read fully in the initial review: both applicable AGENTS.md files, design, no-independent-publication ADR, decision register, implementation prompt and handoff. Their instructions persist. The updated implementation handoff was read fully; updated schema map and dispositions were regenerated/compared. Full integrated diffs are retained for both `0bd5704c...` (#25) and `6ca31eb9...` (merged baseline including the design) to b86, as well as the correction diff from the original reviewed tree.
- This reviewer did not author implementation. New scripts are independently authored, use original reviewer-owned memory fixtures, and import no implementer test fixtures. No production/test source, Git history, retained catalog, credentials or authenticated/live networking was changed or used. Existing selected integration tests use disposable local fixture state; no user catalog was opened.

## Open mandatory residuals

### A1-R — Medium / P2: current pending shape and internal owner consistency remain unchecked

The current-state branch of `json_contracts._validate_staging_record` validates an optional closed field dictionary and capture vocabulary. It does not require the minimum candidate context/provenance or correlate candidate and capture ownership. Generated `_staging_conditions` has the corresponding gap. Closing vocabulary alone does not establish a valid typed candidate.

Independent `residual_pending_shape_owner()` in `rejection_probes.py` inserts a seven-column `exchange_staging` row with table `change_request_state`, reason `current_state:missing_dependency`, an actual repository UUID, a disposable origin UUID and SHA-256 of its JSON. The local key is `nonsense:record`.

1. Candidate `{"kind":"change-request","acquisition_scope":{}}` is accepted by standalone SQL. `validate_catalog` reports 50 JSON columns / four records checked. `Graph.export(actual_repository)` raises `KeyError('change_request_id')`.
2. A complete reviewer PR candidate has its `acquisition_scope.change_request_id` replaced with a different UUID while its own `change_request_id` is unchanged. Standalone SQL and `validate_catalog` accept it; repository export emits five records.

This is a reproduced local typed-pending validation and export-availability defect. It does **not** establish current admission through the corrected API adapter: that early adapter path rejects malformed capture before staging. Nor does it claim an exported mismatched candidate becomes an eligible receiver value. Genuine unresolved parents must remain allowed; minimum candidate fields and internal owner/capture consistency are independent of dependency existence. Preserve the existing detached Issue-comment capture exception when correcting this root cause.

Evidence is immutable in `rejection-results.run1.json`, `rejection-probes.run1.log` and `rejection_probes.run1.py`; the corrected harness also contains the same residual reproduction. The parent/schema author received this finding promptly and is fixing it in a separate worktree, leaving b86 source frozen.

### A6-R — Medium / P2: ordinary portable-identity tests still require retired inventory observations

Independent execution of the whole `tests/integration/test_catalog3_portable_identity.py` file completed **3 failed, 15 passed in 26.02 seconds**. Exact failed collected nodes:

- `tests/integration/test_catalog3_portable_identity.py::test_no_usable_source_rejects_before_job_and_observation[None]`
- `tests/integration/test_catalog3_portable_identity.py::test_no_usable_source_rejects_before_job_and_observation[first]`
- `tests/integration/test_catalog3_portable_identity.py::test_batch_skip_retains_diagnostic_without_remote_observation`

The first two fail at line 147 on `SELECT count(*) FROM inventory_observations`; the third fails at line 164 on `SELECT source_id FROM inventory_observations`. Each ends at `Store.execute`, line 162, with `sqlite3.OperationalError: no such table: inventory_observations`. These unchanged positive test paths were named as additional static stale sites in the initial A6 receipt. Their original Source configuration/skip/no-evidence and batch diagnostic behavior must be ported to actual current Source pairs/assessments, rather than excluded or supported with a compatibility table.

Exact tracebacks and JUnit: `portable-identity-tests.log`, `portable-identity-tests.xml`. The parent received exact nodes/results promptly. The ordinary gate is demonstrably red on b86 independent of any other ongoing full-suite result.

### Disposition metadata discrepancy — Low / P3, refresh required

The checked-in disposition receipt records 2,002 current nodes. Independently collected b86 has **2,003** ordinary nodes with the exact documented marker selection. Comparing the shared 2,002-node roster finds one added node and no absent nodes: `tests/integration/test_git_canonical_availability.py::test_same_length_content_map_cannot_contradict_canonical_blob_digests`. This does not invalidate any replacement mapping; it makes the recorded current count/hash stale. Refresh final roster metadata after all source/test corrections.

## Independently executed corrected behavior

**A1 original-bearing routes:** eleven malformed capture/context/SQL-origin variants are rejected. Unknown top-level original/encoded-response fields, an object in a permissions slot, an extra object under a modeled head target, direct current-scope mutation, per-field capture mutation and an escaped alias of a canonical field-path key all reject. Cases with missing real PR parents leave zero current and staging rows. Actual visibility, permission arrays, head target and page-size fields are accepted. Ordinary Issue metadata rejects an original-bearing field while a real milestone keeps nested sparse inheritance and distinct title/state field origins. Three malformed/unknown standalone staging envelopes reject. A wire record with malformed modeled metadata rejects with no parents and leaves no staging; a valid sibling in the same delivery still admits (five valid records, one rejected, zero staged).

**A2 Source ownership:** eight malformed API cases and seven SQL counterparts reject wrong Source, wrong service, foreign positive pair, invalid identity, object-shaped member, duplicate member, nonterminal completeness and a nonboolean API terminal. A valid complete assessment succeeds. A later partial empty scan preserves the existing positive Source/repository pair.

**A3 exact domain qualification:** the original empty terminal issues enumeration cannot qualify complete Git Coverage. The new marker-reference relation exists for its declared marker but does not change `Graph.proof_requirements=None`. Export/receive produce no complete Git Coverage. Insertion of an unrelated marker in that relation rejects.

**A4 exact thread roster:** an explicit thread without its replies obligation fails Python proof qualification, Graph proof qualification and SQL marker insertion. A genuinely observed empty terminal thread roster accepts its exact empty tree proof. The updated real thread fixture tests retain both child-evidence parameters and all parent/thread/capture/head/base damage parameters.

**Rollback and bounded current state:** the unchanged independent positive invariants pass after adapting only the copied artifact import/output locations. A nested injected statement failure rolls back current value, per-field evidence and local revision while preserving an unrelated outer edit. Intrinsic second-entry failure rolls back a whole new tree for SHA-1 and SHA-256 while an unrelated blob remains available. Missing children retain actual OIDs and NULL real-object FKs. UTF-8 versus Latin-1 yields two explicit disagreeing candidates, no selected fact and no version/time winner. Ten thousand comparable PR edits leave exactly one current PR row, no pending row, no collection row and a singleton local revision of 10,000. Only identity/singleton/current PR tables are nonempty; no accepted normalized PR history or generic renamed transaction owner appears. This workload does not claim physical text GC.

**Operational deletion:** deleting `exchange_admissions` and `exchange_local_identities` leaves a genuine current conflict blocked. The same deletions leave a valid intrinsic tree available. Conflict candidates are domain evidence; the deleted indexes are not admission authority.

**New composed boundaries:** independent SHA-1/SHA-256 probes accept valid canonical tree sequences, reject duplicate physical names, reject a NUL-bearing intrinsic SQL name, and compute correct versus contradictory MD5/SHA-1/SHA-256 content digest predicates. Two hundred genuine unrelated pending collection envelopes with absent PR parents do not enter or change a selected collection export. EXPLAIN confirms its key/repository stage lookup uses `exchange_staging_record_owner`.

**Representative existing behavior ports:** selected original cache/manual-discovery/transaction nodes, all current Phase 2 collection-integrity nodes and the selected-Git unrelated-pending scale node completed **27 passed in 104.82 seconds**. JUnit/log retained. This execution confirms the three originally demonstrated A6 failures are ported, but does not cover the separate A6-R cases above.

### Harness correction, not a weakened product assertion

The first new rejection run used `outcome['rejected']` instead of the actual public result key `rejected_records` in the wire sibling probe. That reviewer harness raised KeyError and was archived unchanged as run1. The harness key was corrected, and the affected wire probe was independently re-executed successfully in `wire-focused.log` / `wire-focused-results.json`. Its assertions still require one rejected malformed record, a usable valid sibling and zero staging. No production source or product fixture was altered for this harness correction. All other first-run assertions completed successfully apart from the explicitly recorded A1-R residual, which intentionally demonstrates remaining acceptance. A successful probe-script exit alone is not an acceptance gate.

## Exact baseline behavioral reconciliation

A second detached worktree at `6ca31eb95d2dca91adcf20af88fbb54387595375` / tree `7c3e1795162a2083f6df363a1afa53afa2e29333` was used only to collect the real baseline ordinary tests. Its source import was verified as that baseline worktree. It collects **1,950 nodes**; both the node set and sequence equal `tests/support/publication_free_baseline_nodes.txt` exactly.

The corrected tree independently collects **2,003** ordinary nodes. Running `audit_publication_free_test_dispositions.resolve` through its actual CLI against these two actual rosters succeeds: **482 explicit baseline mappings + 1,468 same-node survivors = all 1,950 baseline nodes; all 193 removed/renamed baseline functions mapped**. All replacement targets are actually collected, with no missing target. Every regenerated mapping entry equals the checked-in disposition entry. Mappings by section: schema 240, Exchange 83, mechanism-only 56, acquisition 37, other 35, Git 31. The recorded count/hash differs only as described above.

Behavioral inspection distinguishes legitimate fixture changes from assertion loss. Unknown provider metadata was reexpressed as real label objects and milestone fields while preserving nested merge and sparse body/null assertions. Eight boolean/integer/array/object pure-merge parameters retain their identities and equality/dominance/origin assertions in an explicit persistence-sink fixture, because the closed provider schema does not support those shape alternatives; that matrix no longer claims end-to-end provider admission. Neighboring real persisted body/metadata/transfer cases, and independent real-milestone probes, cover actual row admission. Malformed sibling tests now assert rejection/no retention plus intact good sibling, instead of requiring an invalid archive. Cache preservation complete flags and revision rollback assertions preserve the actual domain/physical obligations. Thread fixture changes enumerate the actual root member and use the corresponding tree proof; no parameter disappears. Git maps identify genuine capture/bytes/ambiguity obligations separately from retired profile/publication assertions.

Mapping existence is not assertion sufficiency or execution proof. A6-R demonstrates why same collected names cannot certify surviving behavior. Full ordinary/package/final verification remains separate.

## Composed DDL, generated JSON and live consumer inventory

The regenerated schema map equals the packaged map exactly. Current composition contains **84 tables, 617 columns, 141 FK constraints, 17 views, 367 triggers and 54 explicit indexes**. Every table is classified once. All 17 views and 252 insert/update/delete shapes prepare independently, covering trigger accesses. FK and recursive-trigger modes are enabled; fresh FK check is empty and integrity check is `ok`. All 50 JSON columns are inventoried. Python-generated JSON guard text exactly equals the packaged SQL. Actual production SQL has **447 compiled literal sites, 142 dynamic/non-DML sites and zero failed literal preparations**.

The added marker relation is a typed projection of an immutable claim's declared marker references. It carries no independent completeness rule; the executed wrong-domain probe demonstrates that its presence does not qualify Coverage. Pure Git SQL predicates recompute actual byte identities/structure/ref correspondence rather than installing an acquisition or decoder certificate. Selected pending traversal uses indexed exact typed keys and leaves unrelated pending work outside selection. Tables still have recognizable identity, current value, object structure, real capture, enumeration, integrity or local-operation subjects. No restored generic Publication/result/profile authority was identified in the reviewed paths.

The full source inventory includes live adapters, readers, CLI, Store forwarders, unchanged consumers and test SQL. Retired positive test references are reported rather than hidden among intentionally invalid adversarial statements. The old historical `audit_phase2_dependencies.py` entrypoint still references removed `EXCLUDED`/`ORIGINAL_PROOF_TABLES`; only its functioning native/static helpers were used here. Its initial-tree full-entrypoint failure remains archived. It is not represented as a working final acceptance command.

Native runtime verification here is SQLite **3.53.1 only**. The parent/schema author reports a separate SQLite 3.45.1 generated-SQL parser-depth correction underway. This reviewer did not independently execute that runtime yet; newer-runtime compilation cannot approve that older-runtime compatibility boundary.

## Reviewed and unreviewed paths

`path-review-manifest.json` enumerates **all 187 changed paths** from the merged baseline to b86 with exact review depth, plus unchanged explicitly reviewed source/test helpers. `changed-since-initial-paths.txt` separately enumerates every correction-era touched path. The complete native table/column/PK/FK/view/trigger/index and JSON inventories, and whole-checkout SQL/call inventory, are retained. Architecture constraint/consumer review covers all composed resource groups and current API/current resources/current collection/JSON/Exchange/identity/Store/transaction paths, direct Git installation and pure computed readers, target function registration, Source/query/current coverage consumers, CLI retirement/current code command, actual parser metadata/capture projection and correction-era collector changes.

Acquisition HTTP/conditional/restart/cancellation/incremental state machines, comprehensive Git network/cache/traversal runtime, full Exchange reverse/repeat/CAS repair/backup/restore/package scenarios, all dynamic SQL dispatch and scale bounds beyond the executed selected checks were only inspected at relevant architectural boundaries. They were not comprehensively executed or approved by this scope. Other reviewers' archived programs/results were not rerun as if they were this reviewer's evidence. Most changed tests receive exact collected-node/static-disposition inspection rather than full manual assertion-body review; the manifest says so. No full ordinary suite, installed wheel/sdist suite, hosted CI or older-SQLite acceptance was run here. These limits remain material even after the two mandatory residuals are corrected.

## Exact executed commands and artifacts

All corrected-source Python commands used CWD `/workspace/reviews/publication-free-architecture-corrected` and this prefix:

```sh
env PYTHONPATH=/workspace/reviews/publication-free-architecture-corrected/src:/workspace/reviews/publication-free-architecture-corrected PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python
```

Executed scripts: `rejection_probes.py` (run1 archived, wire-result-key harness correction disclosed), focused `wire_no_parent_and_valid_sibling()` import, `positive_probes.py`, `cross_module_probes.py`, `composed_audit.py`, and `scripts/audit_publication_free_test_dispositions.py --baseline <artifact>/baseline-nodes.txt --current <artifact>/ordinary-nodes.txt --output <artifact>/resolved-node-dispositions.json`.

Actual ordinary collection command: `-m pytest --collect-only -q -m 'not live and not benchmark' tests/unit tests/integration tests/e2e`. An earlier broad `not live_network` exploratory collection was also retained as `collection.log` and is not used for ordinary-count proof. Baseline collection used the same documented selection with CWD and PYTHONPATH bound to `/workspace/reviews/publication-free-architecture-test-baseline`.

Representative execution command: `-m pytest -q tests/integration/test_catalog3_cache.py::test_gc_obligations_and_preserved_source tests/integration/test_catalog3_job_plans.py::test_manual_inventory_has_source_owned_current_roster_and_assessment tests/integration/test_database.py::test_constraints_and_transaction_atomicity tests/integration/test_phase2_collection_integrity.py tests/integration/test_phase1_exchange_scaling.py::test_selected_git_work_ignores_unrelated_same_repository_pending_roots --junitxml=<artifact>/representative-tests.xml`.

Residual A6 execution command: `-m pytest -q tests/integration/test_catalog3_portable_identity.py --junitxml=<artifact>/portable-identity-tests.xml`.

Artifact directory is `/workspace/review-artifacts/architecture/corrected-e810427` (name reflects its initial binding; all actual executions above bind b86). It contains complete diffs, scripts, run1 immutable receipts, focused corrected wire receipt, positive/cross-module results, actual baseline/current rosters and logs, resolved exact mappings, native/static/JSON audits, selected JUnit/logs and path manifest. Original evidence outside this subdirectory and the initial archived repository receipt remain unchanged. This receipt records b86 evidence only and does not anticipate results of author corrections or the parent's ongoing full execution.
