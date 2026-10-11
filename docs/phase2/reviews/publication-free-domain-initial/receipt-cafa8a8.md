# Independent Git / Exchange / CAS domain QA — initial frozen-tree receipt

This is an initial review receipt, **not a signoff**. Mandatory corrections and exact corrected-tree re-review remain open.

## Binding and independence

- Worktree: `/workspace/reviews/publication-free-domain-qa`.
- Commit: `cafa8a8b143fe095b79f282690a6edf98e6f660e`.
- Tree: `477726d0f1fe7cb6f939a1fa577b35ab9e5ba96b`.
- Comparison baseline: `0bd5704caca2f6e3723bef22531b065cd4d7bad0`.
- Composed Schema 20 DDL SHA-256: `d06f7699e5281a32a02e44a17012932d61b3754ddd1865272991ba981aabe389`.
- Python: 3.12.14; SQLite: 3.53.1. Interpreter: `/workspace/git-repo-db/.venv/bin/python`.
- Every correctness test fixture verifies `repo_catalog.__file__` lies inside the review CWD. The scale scripts record its exact value, `/workspace/reviews/publication-free-domain-qa/src/repo_catalog/__init__.py`.
- Model and effort: **not exposed**. This reviewer authored no reviewed production changes and did not edit production, history, or retained user catalogs. All writes were synthetic disposable catalogs or review artifacts. No external system, authenticated collection, or real user data was used.
- Worktree Git status was empty at the recorded endpoint. `metadata-cafa8a8b143fe095b79f282690a6edf98e6f660e.json` contains artifact hashes and source binding.
- The immutable initial test copy is `test_independent_domain_qa.cafa8a8b143fe095b79f282690a6edf98e6f660e.py`. Its hash matches the script used for the final initial-tree run. Corrected-tree adaptations must use separate copies and outputs.

## Executed result set

The final independent correctness run collected **26 nodes: 18 passed, 8 failed**. `pytest-cafa8a8-final.txt` identifies every node and failure. The failed nodes deliberately assert required behavior against ordinary invalid-data or genuine dependency fixtures; they reproduce the issues below.

The passing nodes independently cover:

- SHA-1/SHA-256 canonical identity rejection through the normal installer; missing tree targets retain their OIDs and NULL real-object links; incomplete tree installation rolls back bytes, intrinsic rows, and local revision together.
- Original reported NUL-boundary correction: both formats, canonical widths 2 and 2,048. The compressed malformed name is rejected by composed DDL and the object remains unavailable.
- Two disagreeing Git decoder candidates for blob, commit metadata/message and tree name; explicit Latin-1 selection; reverse record order; duplicate receipt; close/reopen; onward delivery; full catalog checks on the receiver and onward receiver.
- A current document before its typed parents/body, genuine late dependency arrival after reopen, newer value replacement, stale replay, receiver-local checks remaining NULL, and onward export containing only the current value.
- Incremental Git delivery with raw physical bytes arriving after object/mapping/root records. Pending records contain normalized domain dependencies; onward export preserves them; no object/snapshot becomes available early; late bytes finish promotion.
- Equal-clock differing current candidates survive repeat and onward export, and ordinary eligible-current reads expose neither arbitrary candidate.
- Fake API-original representation and foreign repository envelope rejection before byte/object admission.
- Shared raw physical digest across SHA-1/SHA-256, corruption diagnosis, idempotent quarantine, rejected false repair, true canonical repair, backup with quarantine, changed receiver database identity, preserved local counter, no-overwrite restore, and source quarantine preservation.
- CAS-41 ordering: a checksum-valid copied database with unexplained corrupted bytes and a mismatching manifest quarantine count fails before new quarantine/diagnostic insertion in the stage.
- Receiver-local revision advances on real import, does not import the sender's artificial value 987,654,321, and is unchanged by repeated unchanged import.
- A current PR changing head A to B cannot select A's assessment. Retained assessment A keeps its original target, and missing head/base acquisition roles remain explicit gaps.
- SHA-1/SHA-256 commit-parent interruption and **actual child process death** after a parent prefix preserve the independently committed blob prefix, roll back the incomplete commit/bytes, and preserve revision.

An initial exploratory run returned 9 passed / 3 failed because my fixture omitted the required `peeled` field and supplied API OIDs as bytes instead of canonical text. I corrected these **QA input errors**, then all original 12 nodes passed (`pytest-cafa8a8-fixture-v2.txt`). They are not implementation findings. Subsequent independent tests extended the script to the final 26-node set. Focused logs remain preserved.

## Finding D1 — availability is weaker than complete canonical intrinsic structure

`src/repo_catalog/resources/git_facts.sql:36` defines `available_git_objects`. The tree branch checks NUL, sequence offsets/lengths and reconstruction but permits `.` / `..` / names containing `/`. `GitParsing.tree` at `src/repo_catalog/adapters/git/parsing.py:540` explicitly rejects them. The tag branch matches `type blob` as a prefix of `type blob-extra`, without its full line boundary. The commit branch can accept two `tree <OID>` headers represented by one `commits` row, although the canonical parser requires exactly one.

Each synthetic fixture uses real SHA-256 bytes, genuine canonical Git hash/type/size declarations, ordinary inserts through composed DDL, enabled FKs and untouched triggers. Each becomes available, while `verify_git_object_structure` rejects it. The five failed nodes are `test_invalid_intrinsic_tree_names_cannot_be_available[.]`, `[..]`, `[dir/file]`, and `test_available_intrinsic_headers_match_canonical_parser[tag]`, `[commit]`.

This is the same validity boundary as the prior NUL finding, with further concrete counterexamples. It does not claim the normal canonical installer emits these rows; its failure tests pass. Correction must preserve one complete canonical definition rather than patching only the originally reported name shape.

## Finding D2 — a raw Git mapping can assert a fake verified OID

`git_object_payloads_length` at `src/repo_catalog/resources/git_facts.sql:26` verifies size, but does not validate the object OID/type/header against mapped bytes. `git_objects` accepts a correctly sized SHA-1 OID plus `verified=1`. A real interned raw body, fake OID `b'x' * 20`, mapping and raw blob-content row become available through untouched DDL. Full canonical verification rejects the declaration.

Reproducer: `test_direct_raw_git_mapping_cannot_assert_fake_oid`; focused log `pytest-cafa8a8-fakeoid.txt`. Normal installer and Exchange fake-identity checks remain separately enforced and were exercised. A canonical raw-mapping constraint is a narrow repair option that need not hash every ordinary read.

## Finding D3 — same-count ref captures can contradict their actual declared roots

`available_snapshots` and `snapshots_complete_update` in `src/repo_catalog/resources/git_facts.sql:70` compare counts and target closure, but do not compare the exact captured name/type/peeled tuple to `git_acquisitions.roots_manifest`.

The disposable fixture declares `refs/heads/declared` in the normalized manifest, records `refs/heads/different` with the same genuine verified target OID/type, then updates the snapshot to complete. The update succeeds and the snapshot is available/current. `GitParsing.validate_acquisition` rejects the exact mismatch. No constraints or triggers were removed.

Reproducer: `test_inconsistent_ref_capture_cannot_qualify_available_snapshot`; focused log `pytest-cafa8a8-late.txt`. This concerns capture truth, separately from object completeness.

## Finding D4 — selected export scans unrelated same-repository pending records

`Graph._export` at `src/repo_catalog/adapters/sqlite/exchange.py:1081` queries every non-current pending record in the repository, deserializes it, and then checks selected keys in Python. The synthetic candidates are normalized `root_origins` whose real typed root parent has not arrived; normal `Graph.receive` stages them as `missing_dependency`.

One selected Git acquisition stays identical at **24 records / 241 SQL statements**:

| Unrelated pending roots | Exact SQLite VM steps |
| ---: | ---: |
| 0 | 8,940 |
| 1,000 | 25,983 |
| 5,000 | 93,983 |

`selected_pending_scale.py` and `selected-pending-scale-cafa8a8b143fe095b79f282690a6edf98e6f660e.json` preserve the executable and binding. This is deterministic VM work, not a wall-time comparison. Each instrumented size ran sequentially. Other review/test processes existed in the shared machine; no claim of exclusive machine timing is made.

## Finding D5 — selected Git byte authorization does quadratic Python record work

`Graph._git_authorizations` at `src/repo_catalog/adapters/sqlite/exchange.py:1260` scans `by_key.values()` to find an association independently for each Git mapping. SQLite statement/VM counters do not count those Python visits.

The independent script wraps otherwise ordinary typed record dicts and counts real reads of their `table` key inside the production algorithm. All input records pass `Graph.validate_record`, each Git body has the correct canonical object hash and physical digest, and all expected 4N authorized records are returned:

| Selected Git objects | Wire records | Actual record visits |
| ---: | ---: | ---: |
| 32 | 160 | 3,760 |
| 128 | 640 | 58,048 |
| 512 | 2,560 | 920,320 |
| 1,024 | 5,120 | 3,675,648 |

Artifacts: `git_authorization_scale.py`, `git-authorization-scale-cafa8a8b143fe095b79f282690a6edf98e6f660e.json`. Sequential work counts only, no wall-time claim. A precomputed associated-object-key set can replace the repeated full scan.

## Finding D6 — independent minimal code-list roundtrip reproduces the known package cause

Two exact head/base code listings each have a genuine empty terminal page, completion marker and complete source enumeration progress. Their complete assessment is valid in the sender. Export/import omits receiver derivation of the listing progress, so the complete assessment remains staged as `invalid:domain_constraint`.

Reproducer: `test_complete_exact_code_listing_roundtrip_derives_receiver_progress`; focused log `pytest-cafa8a8-code-list.txt`. This is independently authored minimal data, not the implementer's package fixture. It supports the parent's earlier 23-record package diagnosis but does not independently execute or certify the full installed distribution fixture. The assessment constraint must remain; repairing derived exact-list progress is the relevant boundary.

## Prior artifact correction and schema-map binding

At the parent's request I regenerated the original reviewer baseline by running its unchanged `selected_coverage_scale.py` with CWD/PYTHONPATH of frozen commit `41dbe5550afaac248971d13994ae4a8c37274197`, not this worktree. It reproduced 10,102 / 19,055 / 55,055 VM steps, 302 statements, 14 identical records and the scope-wide lookup plan. This restored `/workspace/review-artifacts/git-exchange-cas/selected_coverage_scale.json` after an implementer accidentally overwrote it with dirty corrected-source measurements. The parent reported a separately named working-source artifact preserves those exploratory correction measurements. I did not use that dirty artifact as frozen acceptance evidence.

The provided `publication-free-schema-map.json` has DDL digest `f66a3d1b...`, preceding the NUL correction. I loaded the complete map programmatically, reviewed its responsibility groups and all 34 changed contract summaries, then generated the full current structural inventory into `schema-map-actual-cafa8a8b143fe095b79f282690a6edf98e6f660e.json`. All map fields were compared: only `tree_entries` SQL and `available_git_objects` SQL hashes differ; table-column/PK/FK topology and other objects match. The final implementation must regenerate the repository map after its corrections. This is an intermediate artifact binding issue, not an additional runtime finding.

## Reviewed and outstanding paths

Read entirely: root and Phase 2 AGENTS, implementation prompt, reconstructed design, implementation handoff, no-independent-publication ADR, previous scope-3 partial receipt. Read the full current production modules `adapters/git/parsing.py`, `adapters/sqlite/exchange.py`, `cas_integrity.py`, `payloads.py`, `store.py`, `current_collections.py`, `application/catalog_validation.py`, `git_query_context.py`, `exchange_service.py`, and the intrinsic/capture definitions in `resources/git_domain.sql` and `git_facts.sql`. Read the full baseline diff of Git importer, Store, CAS/payloads/transaction helper, maintenance, catalog validation, Git context and Exchange service. Read all of `tests/integration/test_git_direct_objects.py` and `tests/support/domain_facts.py` as supporting context, without using them as independent fixtures.

Partially inspected: `current_api.py` candidate vocabulary/validation and current merge entry points; `resources/current_api.sql` code/list/target/owner triggers; `resources/catalog3.sql` relevant content/list/snapshot/Coverage/progress definitions; `json_contracts.py` ref-capture vocabulary and generated guards; `application/pr_queries.py` current state/exact code-assessment/role-gap readers; relevant existing Exchange/CAS test definitions; schema-map groups and changed-contract summaries. The complete schema-map content was loaded/compared programmatically; this does not mean every FK was manually traced through all live callers.

The complete integrated diff is preserved as `full-diff-cafa8a8b143fe095b79f282690a6edf98e6f660e.patch` (67,370 lines). **I did not consume that entire 138-file diff line by line.** The old removed Exchange/profile/DAG implementations, broad GitHub collector/persistence/current-state changes, all query/target/index/CLI changes, every generated JSON guard, all retired-to-replacement test mappings and all other changed docs/tests are not certified by this review. The captured Git schema diff was retained as an artifact, while current schema and structural disposition were inspected directly.

This reviewer did not run the complete repository ordinary suite, lint/format, isolated wheel/sdist, hosted CI, full installed package 23-record fixture, selected-volume end-to-end CLI benchmarks, read-snapshot concurrency test, or authenticated acquisition. Those remain the implementation/final-verifier gates; passing implementer tests would not substitute for this receipt's independent executed counterexamples. Source inventory/transfer/acquisition policy paths are outside this review's independently exercised scope and need the other mandated reviewers.

## Exact reproduction commands

Use the indicated CWD. Every command below that mutates catalog state operates on explicit disposable paths.

```bash
cd /workspace/reviews/publication-free-domain-qa
git rev-parse HEAD HEAD^{tree}
git status --short
git diff 0bd5704caca2f6e3723bef22531b065cd4d7bad0 > /workspace/review-artifacts/domain-qa/full-diff-cafa8a8b143fe095b79f282690a6edf98e6f660e.patch
env PYTHONPATH=/workspace/reviews/publication-free-domain-qa/src:/workspace/reviews/publication-free-domain-qa PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python -m pytest -v /workspace/review-artifacts/domain-qa/test_independent_domain_qa.py --tb=short --basetemp=/workspace/review-artifacts/domain-qa/disposable-cafa8a8-final > /workspace/review-artifacts/domain-qa/pytest-cafa8a8-final.txt 2>&1
env PYTHONPATH=/workspace/reviews/publication-free-domain-qa/src:/workspace/reviews/publication-free-domain-qa PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python /workspace/review-artifacts/domain-qa/selected_pending_scale.py > /workspace/review-artifacts/domain-qa/selected-pending-scale-cafa8a8.txt 2>&1
env PYTHONPATH=/workspace/reviews/publication-free-domain-qa/src:/workspace/reviews/publication-free-domain-qa PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python /workspace/review-artifacts/domain-qa/git_authorization_scale.py > /workspace/review-artifacts/domain-qa/git-authorization-scale-cafa8a8.txt 2>&1
env PYTHONPATH=/workspace/reviews/publication-free-domain-qa/src:/workspace/reviews/publication-free-domain-qa PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python scripts/audit_publication_free.py > /workspace/review-artifacts/domain-qa/schema-map-actual-cafa8a8b143fe095b79f282690a6edf98e6f660e.json

cd /workspace/reviews/publication-free-git-exchange-cas
env PYTHONPATH=/workspace/reviews/publication-free-git-exchange-cas/src:/workspace/reviews/publication-free-git-exchange-cas PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python /workspace/review-artifacts/git-exchange-cas/selected_coverage_scale.py
```

The earlier correctness commands used the same interpreter/environment and `-m pytest -v /workspace/review-artifacts/domain-qa/test_independent_domain_qa.py --tb=short`, with these exact selector / disposable-basetemp / log suffixes:

| Selector | Basetemp suffix | Log |
| --- | --- | --- |
| all initial 12 nodes | `disposable-cafa8a8` | `pytest-cafa8a8.txt` |
| all corrected original 12 fixtures | `disposable-cafa8a8-fixture-v2` | `pytest-cafa8a8-fixture-v2.txt` |
| `-k invalid_intrinsic_tree_names` | `disposable-cafa8a8-invalidnames` | `pytest-cafa8a8-invalidnames.txt` |
| `-k available_intrinsic_headers` | `disposable-cafa8a8-invalidheaders` | `pytest-cafa8a8-invalidheaders.txt` |
| `-k 'git_late_physical or fake_original or inconsistent_ref'` | `disposable-cafa8a8-late` | `pytest-cafa8a8-late.txt` |
| `-k commit_parent_interruption` | `disposable-cafa8a8-crash` | `pytest-cafa8a8-crash.txt` |
| `-k direct_raw_git_mapping` | `disposable-cafa8a8-fakeoid` | `pytest-cafa8a8-fakeoid.txt` |
| `-k 'equal_clock_current or cas41_mismatch'` | `disposable-cafa8a8-conflicts` | `pytest-cafa8a8-conflicts.txt` |
| `-k complete_exact_code_listing` | `disposable-cafa8a8-code-list` | `pytest-cafa8a8-code-list.txt` |

All suffixes are under `/workspace/review-artifacts/domain-qa/`. Logs record the script version's actual selected/collected/deselected counts. Static inspection used ordinary `cat`, bounded `sed`, `rg`, `git diff`, JSON loads and exact SHA/hash queries; no analysis command modified production.

## Re-review requirements

Give this reviewer the next frozen corrected commit/tree. Preserve this receipt, initial scripts and initial result artifacts. Adapt invalid-data fixtures in separate corrected-tree copies to treat actual SQL guard rejection as success, or otherwise require that the record remain unavailable. Re-run the complete independent set, both work-count probes and affected cross-module roundtrips, including derived code progress. Reconcile source changes and artifact hashes. No source change or implementer summary alone resolves the findings.
