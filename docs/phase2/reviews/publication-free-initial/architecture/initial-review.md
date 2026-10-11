# Initial independent architecture / DDL review

Status: **changes required; no initial-tree signoff**. This receipt is limited to the frozen initial candidate. Corrected source requires a new exact commit/tree and re-review by this reviewer. The reviewer did not author the implementation and remains available for that follow-up.

## Binding and authority

- Reviewed worktree: `/workspace/reviews/publication-free-architecture`.
- Feature commit: `41dbe5550afaac248971d13994ae4a8c37274197`.
- Feature tree: `1a518382d4aefdbea1441cf0ae9965b7025b40bd`.
- Integrated comparison: `0bd5704caca2f6e3723bef22531b065cd4d7bad0..41dbe5550afaac248971d13994ae4a8c37274197`.
- Composed Schema 20 SHA-256: `f66a3d1bf3b6636b20c8f58254012ce037beb0c5506cc45a08628e812924f1fe`.
- Interpreter: `/workspace/git-repo-db/.venv/bin/python`, Python 3.12.14, SQLite 3.53.1. Import resolution was explicitly checked: `/workspace/reviews/publication-free-architecture/src/repo_catalog/__init__.py`.
- Model and reasoning effort: **not exposed**.
- Read fully: root `AGENTS.md`, `docs/phase2/AGENTS.md`, `publication-free-design.md`, `no-independent-publication-adr.md`, `decision-register.md`, `publication-free-implementation-prompt.md`, and the implementation handoff. Truncation of the initial combined documentation read was corrected with separate reads.
- Accepted owner choices applied: latest accepted PR/document/thread/known Source roster, actual field module/version provenance, no independent/renamed Publication, no mandatory API originals or replay, no new retention/deletion/trust/Git interpretation policy. No authenticated live networking or retained catalog mutation occurred.

The full integrated diff is archived as `integrated.diff`. This review used the actual composed DDL, old-to-new structural map, changed source and test contracts, and executed independent counterexamples. It did not treat the handoff's success narrative as proof.

## Findings and reproductions

### A1 — High / P1: opaque API originals remain admitted in capture and pending JSON

`json_contracts.py:_acquisition_shape` (line 93), `_sql_capture_conditions` (line 269), and the registry distinguish reference categories but do not close actual capture field vocabulary. `CurrentApiState._missing` returns for an absent parent before validating its capture. `Issue`/`Review` metadata also lack the closed specs applied to the new PR families.

Independent `probe_scope_replica` supplied a valid current PR candidate with `acquisition_scope.raw_api_response = {data: {pullRequest: {body: synthetic marker, title: superseded}}}` and an encoded response field. Admission returned `accepted`. The complete provider-shaped replica was retained in the current scope and copied into per-field evidence. Full `validate_catalog` passed. `Graph.export` included it and a fresh receiver admitted five records with zero rejection/staging, retaining the replica in both scope and field evidence. This is an actual Exchange admission route, rather than hypothetical arbitrary manual disk corruption.

`probe_pending_replica` supplied the same modeled candidate with an absent PR parent. It returned `missing_dependency` and retained the replica in `exchange_staging.record_json`; full catalog JSON validation passed. `probe_issue_metadata_replica` independently admitted a current ordinary Issue with `metadata.raw_api_response.data.body`, passed full catalog JSON validation and exported the replica.

The adjacent `probe_staging_vocab` showed the standalone DDL and full catalog validator accept `exchange_staging.table_name='not_a_domain_table'` and arbitrary `record_json` containing an entire original-bearing object. The generated `staging-envelope` guard is only a duplicate-key/JSON shape guard, not a typed pending-candidate contract. This is part of A1's incomplete JSON retirement boundary; it does not imply that every such direct SQL row is admitted by `Graph.receive`.

Required correction: retain the actual modeled capture/metadata fields with Python and standalone SQL parity; reject unmodeled original-bearing content before missing-parent staging; validate the actual typed shape/owner of pending candidates. This neither requires API replay nor invents a retention policy.

### A2 — High / P1: Source inventory completeness accepts foreign ownership and invalid members

`current_api.py:assess_source_inventory` (line 846) validates a timestamp and terminal flag but does not bind `scope_json` to its `source_id` or validate the scalar member array. The `inventory-members` registry category recursively checks named references; ordinary scalar strings never become references. Neither generated guards nor full `validate_catalog` establish the actual Source/member relationship.

Independent `probe_source_assessment_owner_and_members` created Source A and B and a repository associated only with B. It stored a **complete** assessment under A with a scope naming B's registration and members containing B's repository. It then stored another complete A assessment with members `['not-a-repository', {'raw_api_response': {'body': synthetic marker}}]`. Both passed full catalog JSON validation while A had zero known associations. `QueryService.prepare_coverage` consumes these rows' `source_id` and `state` for inventory completeness, without repairing the mismatched scope.

Required correction: preserve canonical Source/service scope ownership and real known positive repository pairs, and close the actual member shape. Incomplete scans must continue to retain prior associations. This is an internal typed-consistency check, not a stronger provider-authenticity promise.

### A3 — High / P1: an unrelated domain collection qualifies complete Git Coverage

`exchange.py:Graph.proof_requirements` (lines 631–667) qualifies complete coverage by repository and optional PR only. It does not match the coverage scope's kind/domain to the collection's subject.

Independent `probe_cross_domain_coverage_proof` created one empty terminal `issues` collection with a valid pages marker, then a five-column complete claim with `coverage_scopes.kind='git'` and advisory details naming that marker. `proof_requirements('coverage_claims', ...)` returned a qualified dependency set. Export included the claim. A fresh receiver admitted all nine records, no rejected or pending records, and exposed `current_coverage.kind='git', coverage_state='complete'` with **zero Git acquisitions or objects**.

Required correction: qualify Exchange completeness using the actual exact domain/scope relationship. Keep five claim columns and advisory-details structural semantics; a locally structurally valid claim must not gain an unrelated completeness proof on transfer. This counterexample is distinguishable from undetectable coherent sender omission: the retained typed subjects explicitly disagree.

### A4 — High / P1: an explicit thread roster member requires no replies obligation

`CurrentCollectionProof.is_complete_marker` (line 106), the `current_collection_tree_completion_valid` trigger, and `Graph.proof_requirements` enumerate whatever `thread_collection_requirements` rows happen to exist. They never require an obligation for each explicit thread in the parent roster.

Independent `probe_missing_thread_obligation` admitted one current thread, inserted a `threads` collection receipt with that thread as an explicit typed member, and inserted a complete `current-resource-tree-v1` marker with `fetch_collection_ids=[]`. There were **zero** replies requirements/children. Both local proof validators qualified it. Export and a fresh receiver admitted all nine records, including the complete marker and thread, without any replies requirement.

Required correction: establish the exact parent roster/required-child correspondence before tree completion; preserve valid empty terminal rosters. Existing tests exercise an already-present missing/incomplete child and foreign child, but do not test omission of the obligation for an explicit roster member. This is another detectable internal omission, not a request to authenticate an unknown provider member.

### A5 — Medium / P2: exact test-retirement reconciliation is incomplete

All 42 mechanism-retirement entries reference actual surviving functions (41 unique functions). Nevertheless, comparing the baseline ASTs of every changed test file against this frozen tree found 192 original test functions removed or renamed. The two exact maps cover 79 of those functions; **113 have no old-node-to-replacement-node mapping**. `replacement_families` is empty.

See `unmapped-retired-functions.json`. This is a function-level count, not a parametrized collected-node count. It **does not mean 113 behaviors were lost**: many are clear renamed ports. It means the required exact behavioral reconciliation cannot be verified from the supplied retirement artifact. The missing set includes Phase 1 original-retirement, Phase 2 collection integrity, Git decoder and selective Exchange tests. A4 illustrates why an explicit mapping and actual behavioral inspection matter.

Required correction: map each removed/renamed collected baseline node to its actual surviving behavioral node, or identify a truly retired mechanism assertion and justify the supersession. Preserve meaningful assertions; do not repair the map by silently excluding tests.

### A6 — Medium / P2: unchanged live tests still require retired schema/API objects

The whole-source SQL inventory found no failed production literal SQL preparations, but found stale references in ordinary test paths outside the changed-test roster. Three selected live tests were executed against this exact frozen source and all failed in 2.38 seconds:

- `tests/integration/test_catalog3_cache.py::test_gc_obligations_and_preserved_source`: inserts removed `preservation_obligations.published`.
- `tests/integration/test_catalog3_job_plans.py::test_manual_inventory_has_source_owned_raw_input_and_result`: queries removed `inventory_observations` / `parsed_results`.
- `tests/integration/test_database.py::test_constraints_and_transaction_atomicity`: calls removed `Store.publish`; it also contains the old `publication_seq` reference.

Exact traceback evidence: `stale-live-tests.log`. Other static stale test sites appear in `test_catalog3_job_plans.py` and `test_catalog3_portable_identity.py`. They were not all executed here, so this review does not assign additional failure counts to them. Intentionally invalid adversarial SQL and dynamically created test tables were separated from these stale positive paths.

Required correction: port the cache obligations, manual Source/job and revision/rollback behavioral tests to the actual domain/revision contract. The initial ordinary gate is demonstrably red; obsolete names must not be made compatible merely to pass tests.

## Independently verified positive behavior

`positive_probes.py` is independently authored and uses no implementer fixtures:

- 10,000 alternating comparable PR-state updates left exactly one `change_request_state` row, zero `exchange_staging`, zero collection rows and one revision counter at 10,000. The only nonempty tables were the identities, singleton and current PR table. No normalized PR edit history or renamed transaction ledger appeared. This probe did not update distinct document bodies, so it makes no physical-text GC claim.
- An injected `AFTER UPDATE` failure inside a nested current admission rolled back the resource, field evidence and local revision while an unrelated intended outer edit committed.
- Injected failure on the second tree entry rolled back the entire new intrinsic object for both SHA-1 and SHA-256, while an unrelated verified blob remained available.
- Successful tree installation preserved missing child OIDs and NULL real-object FKs without fabricating child objects.
- Actual UTF-8 versus Latin-1 blob decoders produced two explicit candidates; the unselected decoded fact was `None` with `decoder_conflict=True`, with no version/time winner.
- Removing discardable `exchange_admissions` and `exchange_local_identities` indexes did not unblock a genuine current conflict. Unresolved alternatives are retained domain evidence, not mere intake receipts.

These executed probes support narrow invariants. They do not override A1–A6 or constitute final acceptance.

## Composed DDL and reference audit

The active generated map was regenerated from exact production composition and compared equal to `publication-free-schema-map.json`. All 83 tables were present in the responsibility groups; there were 615 columns, 139 FK constraints, 16 views, 362 triggers and 51 explicit indexes. The native schema audit prepared all 16 views and 249 insert/update/delete shapes, including trigger accesses. All compiled; foreign keys and recursive triggers were enabled, `foreign_key_check=[]`, `integrity_check=ok`, and generated JSON guard text equaled the packaged resource. Fifty authored JSON columns were inventoried.

The map confirms retirement of generic result/input/publication tables, parser profile/certificate/trust registries and selection DAGs. The retained identities, current API rows, intrinsic Git objects, actual acquisitions/ref captures, enumeration evidence, code comparison anchors, content integrity, physical installation singleton and operational indexes have independently recognizable subjects. The executed current-state probe requires no generic Publication/result/seal row. No new generic renamed commit-group owner was identified in these traced paths. The false-proof findings concern incomplete exact-domain validation, rather than an excuse to restore Publication.

Static SQL/call inventory covers the whole checkout, including `Store.one/all` and local forwarders. Production source had 439 compiled literal SQL sites and 138 dynamic/non-DML sites; none of the production literal sites failed preparation. Dynamic SQL remains dynamic evidence, not a proof of dead code or complete runtime reachability. The remaining `parser_profile` branches in production query readers explicitly reject the retired option. CLI current PR/search has no API history/profile selector; remaining `history`/`recorded` options address legitimate Git capture scope.

The historical `scripts/audit_phase2_dependencies.py` full entrypoint was also executed against this current tree and fails on removed `exchange.EXCLUDED` (then would reference `ORIGINAL_PROOF_TABLES`). `legacy-audit.log` records this. Historical documentation explicitly binds that script's original receipts to older schemas; the current `audit_publication_free.py` works. This is disclosed tooling limitation, not counted as an additional production correctness finding.

## Reviewed and unreviewed scope

Detailed source/constraint review and counterexample tracing covered the composed resources (`catalog3`, `git_domain`, `git_facts`, `cas_integrity`, `exchange`, `identity_relations`, `current_resources`, `current_api`, `current_collections`, generated JSON guards), their full table/PK/FK/view/trigger inventories, `schema.py`, `json_contracts.py`, `current_api.py`, `current_resources.py`, `current_collections.py`, `exchange.py`, `store.py`, `target.py`, `transactions.py`, Git direct installation/decoder paths, `catalog_validation.py`, `git_query_context.py`, PR/query/source/repository identity consumers, GitHub persistence and collection scope creation, CLI parser/retired option routes, the implementation/schema maps and retirement artifacts. Changed architecture/source/test files were compared against the full integrated diff; whole-checkout static SQL/dispatch inventory includes unchanged callers.

Acquisition/conditional HTTP/cancellation/restart paths in the large collector, full Git network acquisition/cache behavior, complete Exchange reverse/repeat/CAS/backup/restore/performance scenarios, target diagnostics and installed distribution behavior were only inspected where they interact with the architectural findings. They were **not comprehensively executed or approved by this scope**. No full ordinary suite, wheel/sdist suite, hosted CI or comparative scale benchmark was run here. Those remain the other required independent scopes/final verifier's obligations. The 138 dynamic/non-DML production SQL sites are not all independently exercised by this review.

## Reproduction commands and artifacts

Every Python command ran with CWD `/workspace/reviews/publication-free-architecture` and:

```sh
PYTHONPATH=/workspace/reviews/publication-free-architecture/src:/workspace/reviews/publication-free-architecture PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python
```

Main commands, with that exact prefix:

```sh
/workspace/git-repo-db/.venv/bin/python /workspace/review-artifacts/architecture/counterexamples.py
/workspace/git-repo-db/.venv/bin/python /workspace/review-artifacts/architecture/positive_probes.py
/workspace/git-repo-db/.venv/bin/python scripts/audit_phase2_dependencies.py --output /workspace/review-artifacts/architecture/legacy-audit.json
/workspace/git-repo-db/.venv/bin/python -m pytest -q tests/integration/test_catalog3_cache.py::test_gc_obligations_and_preserved_source tests/integration/test_catalog3_job_plans.py::test_manual_inventory_has_source_owned_raw_input_and_result tests/integration/test_database.py::test_constraints_and_transaction_atomicity
```

The first command exits 0 while recording the reproduced **vulnerable initial behavior**; its assertions intentionally demonstrate admission on this tree. It is not a green correctness test. A corrected re-review must require rejection/no retention for A1/A2, no incorrect qualification for A3/A4 and preserve the positive probes. Do not overwrite the initial results when running corrected source.

Artifacts in this directory: `counterexamples.py`, `counterexamples-results.json`, `counterexamples.log`, `positive_probes.py`, `positive-results.json`, `positive-probes.log`, `audit-runtime.json`, `native-schema-dependencies.json`, `source-sql-call-inventory.json`, `json-inventory.json`, `integrated.diff`, `unmapped-retired-functions.json`, `stale-live-tests.log`, `legacy-audit.log`. Native/static audit helpers were run in an in-memory catalog and their full results are retained, with the limits described above.

No implementation or Git history was edited. Reproduction script files were written only in the review artifact directory; temporary disposable pytest catalogs were under `/tmp`.
