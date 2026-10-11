# Independent post-implementation review: acquisition and completeness

Status: initial frozen tree is **not accepted**. Corrections and an independent corrected-tree re-review are required. This report is not final sign-off.

Reviewer: fresh scope-2 subagent `/root/review_acquisition`; did not author the reviewed production changes. Model and effort: **not exposed**. No additional subagents were used.

## Exact source and execution binding

- Worktree: `/workspace/reviews/publication-free-acquisition`.
- Commit: `41dbe5550afaac248971d13994ae4a8c37274197`.
- Tree: `1a518382d4aefdbea1441cf0ae9965b7025b40bd`.
- Comparison baseline: `0bd5704caca2f6e3723bef22531b065cd4d7bad0`.
- Packaged composed DDL SHA-256: `f66a3d1bf3b6636b20c8f58254012ce037beb0c5506cc45a08628e812924f1fe`.
- Interpreter: `/workspace/git-repo-db/.venv/bin/python`, Python 3.12.14; SQLite 3.53.1.
- Import checked: `/workspace/reviews/publication-free-acquisition/src/repo_catalog/__init__.py`.
- Production worktree remained unmodified. Full baseline diff saved as `reviewed-baseline-full.diff`.
- All catalog mutations were in disposable fixture state. Real HTTP fixtures bound only to localhost and used `fixture-dummy`; no live authenticated requests, retained catalogs, production edits, Git-history edits, push or merge occurred.

Read the repository and Phase-2 AGENTS instructions, the complete design, ADR, decision register and implementation prompt. Read the implementation handoff and relevant schema-map/test-disposition groups. Inspected source and baseline changes across the reviewed modules. The reviewed baseline includes the whole integrated diff; the executable review is scoped as described below.

## Independent executed results

The review scripts are independently authored outside the worktree. They use the existing disposable Git/localhost-server setup support but do not invoke implementer-authored test functions.

The final initial-tree probe snapshot is `frozen-probes-v1/`:

| File | SHA-256 |
| --- | --- |
| `test_independent_acquisition.py` | `31e0c15293750501076835171e31e37cfc9ad0d89185b8516d8c8a10966aec12` |
| `test_independent_invariants.py` | `5338cbc2b0257678ea834e3a2b84ec7a664ee3ced67a092a8ed38f7b7038284d` |
| `repro_scope_replica.py` | `75e8d7d46be9d48516f0d90fe6a505031c6e20dbfc390f30e37c3ea16c212fe4` |

Executed command, CWD the frozen worktree:

```sh
PYTHONPATH=/workspace/reviews/publication-free-acquisition/src:/workspace/reviews/publication-free-acquisition:/workspace/review-artifacts/acquisition/frozen-probes-v1 PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python -m pytest -q /workspace/review-artifacts/acquisition/frozen-probes-v1 --tb=short --junitxml=/workspace/review-artifacts/acquisition/initial-frozen-results.xml > /workspace/review-artifacts/acquisition/initial-frozen-results.txt 2>&1
```

Result: **35 collected, 24 passed, 11 failed, no skips, 55.32 seconds**. These 11 failed nodes represent 10 root findings; the replica admission finding has current and pending variants. This is review evidence, not a comparative performance benchmark or the complete ordinary/package suite. Earlier exploratory runs are preserved separately and do not replace this frozen probe snapshot.

Standalone replica reproduction:

```sh
PYTHONPATH=/workspace/reviews/publication-free-acquisition/src:/workspace/reviews/publication-free-acquisition:/workspace/review-artifacts/acquisition PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python /workspace/review-artifacts/acquisition/repro_scope_replica.py
```

Recorded result in `scope-replica-result.json`: accepted current scope and field proof both retain `raw-provider-sentinel`; a missing-parent pending candidate retains the same replica with `missing_dependency`; `stored_bytes` remains zero. Retirement of original-byte tables alone does not close this route.

## Reproducible findings

| ID | Severity | Concrete counterexample and root cause | Independent node |
| --- | --- | --- | --- |
| ACQ-01 | High | Provider reports 251 commits but returns a capped shorter terminal list. `_code_collect` calls commits first and propagates `API_CAP`, so the independent files endpoint is never requested or admitted. A failed larger collection prevents acquisition of valid independent files. | `test_capped_commits_still_collect_independent_files` |
| ACQ-02 | High | Full synthetic sync persists a partial commits listing for PR 41, then `_assess_code` receives `listings=None` because `sync.attempt` swallowed `_code_collect`'s exception. The assessment's `commit_code_listing_id` is NULL despite the actual durable listing. Partial enumeration evidence becomes disconnected from the assessment. | `test_partial_listing_ids_recoverable_for_assessment` |
| ACQ-03 | Medium | With known `facts.permissions=['repo','read:org']`, `current_context` omits `observed_permissions`, so field captures lose the observed permission scope. Collection scope and current field capture do not carry equivalent relevant context. | `test_field_capture_records_observed_permissions` |
| ACQ-04 | Medium | Newer REST detail has a body and canonical PR identity but omits title. The pure parser supports sparse projection; `rest_item` demands title unconditionally, rejecting the body update instead of inheriting the old title and origin. | `test_sparse_rest_detail_preserves_title` |
| ACQ-05 | Medium | Verified same-provider-ID redirect confirms the Source pair and advances local revision before the final renamed resource GET. `detail` retains the revision captured before the original URL request. An unclocked but valid final live update is rejected as `CURRENT_STATE_UNRESOLVED`; it cannot use the actual pre-final-request fence. | `test_redirect_live_response_refreshes_fence_before_final_request` |
| ACQ-06 | High | A GraphQL root carrying a foreign opaque PR id and an empty terminal thread roster is accepted as complete for the requested local PR. The static query requests opaque `id`, omits `number`/canonical database ID, and `threads` validates only an optionally returned number. REST `node_id` supplied by the fixture is dropped by the PR projection, so it is not a retained identity against which the response is checked. This needs verifiable typed response-owner binding, not opaque-alias authority. | `test_graphql_foreign_root_id_is_rejected` |
| ACQ-07 | High | A genuine complete same-target assessment created by a full synthetic sync at observation 300 becomes partial at 175 when an older job is assessed. `_assess_code` computes a target/scope-stable key and unconditionally upserts listing IDs, state, observation time and details. It has no maximum-observation candidate protection before its pre-import reset or final update. | `test_older_code_assessment_cannot_replace_newer_complete` |
| ACQ-08 | Medium | Standalone SQL accepts both `["body"]` and the escaped semantic alias `["\\u0062ody"]` in Issue field evidence. Python requires decoded canonical path encoding; the generated SQL uses `json(e.key)=e.key`, which preserves the escape spelling instead of rebuilding a decoded canonical array. The duplicate semantic origin slot bypasses the intended guard. | `test_escaped_field_alias_is_rejected_by_sql` |
| ACQ-09 | Medium | `code_check` receives 304 followed by an available fresh 200 body. It performs only the first request and raises `API_SCHEMA` on empty JSON. It lacks the unconditional refetch/reuse-unavailable behavior implemented by `detail` and general `collection`. No fabricated observation was seen, but the authorized safe-fetch path is incomplete. | `test_code_check_304_cache_loss_fetches_real_representation` |
| ACQ-10 | High | A current document candidate with a newer comparable clock and `acquisition_scope.provider_response` containing a whole body/header/unknown-field replica is accepted and retained in both top-level scope and per-field proof. A missing-parent variant retains it in `exchange_staging.record_json`. `_acquisition_shape` checks identities, endpoint and forbidden reference-key names but allows arbitrary nested vocabulary; pending admission carries it forward. Current/pending API-original retirement is therefore incomplete. | `test_capture_cannot_hide_provider_response_replica[False]`, `[True]`; standalone reproduction |

Production anchors: `adapters/github/collector.py` (`request_get`, `rest_item`, `threads`, `_code_collect`, `_assess_code`, `sync`, `code_check`); `adapters/github/persistence.py` (`current_context`); `adapters/sqlite/json_contracts.py` (`_acquisition_shape`, `_check_schema`, `guard_sql`); `adapters/sqlite/current_resources.py` (`_stage`, admission/capture validation).

Findings were delivered as they reproduced. The root reported that ACQ-08 has been corrected in its working tree; that correction has not yet been independently checked by this reviewer. Authors are working on other reported paths. Nothing in this receipt approves those unreviewed corrections.

## Passing adversarial coverage

- Store and shared `atomic_unit`: caught nested body/statement failure, deferred outer COMMIT failure, nested deferred constraint failure, retained outer work after an inner rollback, revision rollback, and Store/shared rollback-cleanup failure with connection retirement and primary error preservation.
- Actual current document constraint failure: current row including presence/evidence remains unchanged; newly interned domain text and local revision do not leak.
- Sparse fields, inherited producer/version/clock evidence, explicit provider-null body, stale body rejection and imported equal-clock conflict.
- Five-column Coverage: complete100, identified partial200, older successful175, complete300; equal-time complete/partial conflict; later unknown. The timestamp sequence was exercised through both direct claims and genuine localhost acquisition with identified malformed input.
- Known empty terminal versus no terminal; required child omitted; no complete parent marker is fabricated.
- Cancellation during a later page retains committed resources; deletion of operational cursor produces `RESUME_UNAVAILABLE` without hiding admitted resources.
- Detail 304 without representation performs a real unconditional second request and then returns `REUSE_UNAVAILABLE` if 304 repeats.
- Source R1/R2 known pairs, later partial R1, unchanged R2 identity/evidence and inherited Source v1 field origin while a new field gains v2 origin.
- Imported successful-check timestamps do not advance receiver-local checks; stale revision and mismatched scope cannot resolve unclocked differences; a genuine current live fence can.
- Detached Issue-comment captured repository/binding/Source identifiers survive without fabricated registrations; a later known contradictory binding is rejected.
- Optional archive callback and warning-hook failures remain nonfatal, diagnostics omit arbitrary exception text, current domain body remains readable, API-original bytes are not stored.
- Full synthetic complete assessment for head A followed by current head B: ordinary `_code_observation` does not borrow A; A's minimal assessment remains without a full PR observation table.
- Explicit request callbacks assert no SQLite write transaction is held over the tested HTTP paths. Source code also places collection HTTP outside page-write units.

## Reviewed and unreviewed boundaries

Reviewed production paths: Store/transaction helper; current-resource field engine and current API admission; GitHub pure projections/persistence, REST collection/detail/inventory, GraphQL root/child continuation/targets, PR code collection/assessment; Source discovery changes in `collection_service`; Coverage candidate behavior; current collection proof; relevant generated current evidence/capture guards; exact head/base selection in `pr_queries`; optional transport recording boundary and 304 handling. No current reader in those tested paths required parser certificates, profile selection, a generic Publication row, or a generic batch seal.

This scope is **not** a complete architecture/DDL, Git, Exchange, CAS or package acceptance review. Unreviewed here: canonical single-Git-object installation and decoder ambiguity, whole Exchange wire admission/closure/reverse/onward export, provider authenticity and coherent omission boundaries, CAS repair/quarantine/backup/restore, selected-volume performance, full CLI/package distribution, hosted CI binding, and 10,000-update retention growth. Standalone SQL inspection was focused on current evidence/capture guards rather than every trigger. Real storage I/O faults, process kill during COMMIT, OS writer-lock concurrency and credential-provider behavior were not exercised; SQLite deferred constraints and injected cleanup failures were exercised.

The remaining owner choices remain paused. This review selected no new deletion-on-absence, GC/retention, provider-trust, total domain clock ordering, Source negative-membership, decoder/version preference, or generic batch eligibility policy.

Return the corrected frozen SHA/tree to this reviewer, including the shared JSON guard changes, for the same probes plus affected path reinspection. Any subsequent source change invalidates the affected re-review binding.
