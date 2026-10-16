# Schema 21 collection contract restoration

PR: https://github.com/TakashiSasaki/git-repo-db/pull/93

Final owned cohort: **244 passed, 0 failed, 0 errors, 0 skipped**. All 172 inherited
failures in this owned cohort are resolved. The original cohort had 243 nodes;
one explicit positive/negative physical-boundary regression was added. This is
owned-cohort acceptance, not a claim that the whole repository passes.

Frozen tested executable source: `76d3389ab4d450462c2be47e91f5228cdefae71a`; Git tree `ed9179b121412e5a68da4b69c0b3d7af8c87af58`.
The final manifest reconciles 332 executable Python/SQL/resource/configuration
inputs with that source. Follow-up changes only record evidence, documentation
and test-node disposition metadata; the owned cohort does not consume that
metadata. Production source and all schemas are unchanged.

| Run | Passed | Failed | Meaning |
|---|---:|---:|---|
| Before | 71 | 172 | Original executable test modules imported from main at collection |
| Initial routing diagnostic | 142 | 101 | Revealed layered obsolete continuation expectations |
| Later diagnostic | 241 | 3 | Remaining cancellation/aggregate-clock expectations |
| Final frozen source | 244 | 0 | Complete owned cohort after corrections |

All four JUnit/journal node sets and outcomes reconcile exactly. Raw logs, JUnit
and per-phase journals are gzip-compressed under `runs/`, including every failed
experiment. `classification.json` / `.csv` records all 172 original failed node
IDs, original messages, expected physical owner, layered cause, fix PR and final
result. `node-renames.json` maps all five renamed functions with unchanged
parameter suffixes. `artifact-sha256.json` binds stored artifacts.

The before subprocess imported unchanged main modules before editing began;
the worktree was subsequently edited while that diagnostic ran. Traceback source
snippets can therefore reflect later lines. The parent coordinator's independent
clean-worktree baseline is authoritative for exact original source locations.
Intermediate working-tree runs are diagnostic counterexamples. Final executable
inputs stayed frozen throughout its complete run.

Independent A architecture and C fixture reviews reported no blocker for the
frozen source; their narrow scopes and execution limits are in `reviews.json`.
Independent integrated per-node execution, full Schema 21/P1–P6, packaging and
remaining root-owned failure groups belong to parent integration evidence.
Owner merge authorization remains pending; no merge or activation occurred.

Final command (repository default marker policy preserved):

```sh
uv sync --locked --group dev
uv run pytest -n 4 -q --tb=short \
  tests/integration/test_catalog3_github_runtime.py \
  tests/integration/test_catalog3_rest_boundaries.py \
  tests/integration/test_phase1_retirement.py \
  tests/integration/test_current_collection_rejection_clocks.py \
  tests/integration/test_current_review_query_coverage.py \
  tests/integration/test_catalog3_review_coverage.py \
  tests/integration/test_publication_free_acquisition.py \
  --junitxml=/external/evidence/final.xml --journal=/external/evidence/final.jsonl
```

Ruff check and format passed across all eight changed Python files. The active
publication-free disposition audit accounts for all 1950 historical baseline
nodes against the actual 3492 default collected nodes on this branch (collection
proof only). A pre-existing cache test rename is recorded with its actual two
same-store FK assertions, without claiming the retired cross-owner-cache test
semantic was preserved. The historical baseline inventory is unchanged.

## Checkpoint history and contract explanation

Base: `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c` (unchanged public main).

The public three-store contract is ADR 0002 PF-P04/P06/P07/P12. Core owns
collection identity, normalized resources, pages and terminal evidence;
Operational owns jobs, attempts and collection progress. Tests previously queried
Operational tables through Core or joined them into Core SQL. The shared `sync`
fixture did so before many behavioral assertions were reached.

`collection_rows` performs two explicit, independent read snapshots after the
operation is quiescent. It offers no cross-store atomicity, completion authority,
ATTACH, aliases or compatibility tables. Existing domain-behavior assertions are
preserved. Restart checks now follow `ApiFacts.begin`: without a terminal Core
marker, fresh root acquisition preserves admitted resources and does not complete
the old collection. Retired `incremental_scans` is asserted absent from schema,
while the surrounding real incremental-acquisition behavior remains exercised.

Checkpoint: the added positive/negative physical-boundary regression passed
(1 node; JUnit and per-phase journal under `checkpoint`). Ruff passed across the
eight changed test/fixture files. The complete owned cohort is still under
investigation at this checkpoint; this is not final acceptance evidence.

Explicit replacement-node map (parameter suffixes preserved):

- `test_resumed_child_observation_governs_its_thread_without_new_root_request`
  -> `test_resumed_child_observation_governs_its_thread_after_fresh_root_request`.
- `test_thread_children_resume_from_normalized_committed_prefix`
  -> `test_thread_children_restart_with_retained_normalized_committed_prefix`.

No production implementation or schema has changed.

Additional replacement-node map (parameter suffixes preserved):

- `test_partial_listing_resumes_same_items_and_no_completed_pages`
  -> `test_partial_listing_restarts_with_retained_items_and_fresh_pages`.
- `test_current_incremental_watermark_stays_at_original_scan_start`
  -> `test_current_incremental_watermark_uses_actual_fresh_scan_start`.

Layered counterexamples after fixing store selection also demonstrate why mere
SQL relocation is insufficient: old partial collection IDs must stay partial,
new collection IDs receive terminal proofs, fresh root pages are requested before
children, and an incremental restart's watermark uses its actual new start time.
A later valid terminal Core collection can safely be reused by an older job.
The initial diagnostic runs are preserved externally until the final receipt;
they include failed expectations rather than hidden skips or xfails.

- `test_current_terminal_cancellation_finishes_locally_without_false_partial`
  -> `test_current_terminal_cancellation_reacquires_without_false_partial`.

A further layered check distinguishes page-level completion from job-level
acceptance: when a retried child is older than a rejected observation, or equal in
time with conflicting completeness, new terminal pages do not make aggregate PR
sync complete. The public sync correctly retains `PR_PARTIAL`; equal-time thread
coverage stays conflicted and PR/code summaries stay partial. No rejected clock
is borrowed to manufacture a successful completion.
