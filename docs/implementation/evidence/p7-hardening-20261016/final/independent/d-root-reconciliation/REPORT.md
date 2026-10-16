# Independent reconciliation of final root acceptance and main reproductions

Reviewed final executable commit **178ddbaa8fa06f52aff4993730205c5a38da91f4**, tree **9740ad1a91f367192bb31ce9777d039c2bb4729b**. No repository source or documentation was changed by this reconciliation.

The final root full-suite result is **3517 passed / 229 failed / 2 setup errors**, **3748 selected**, exit **1**, with 4 warnings. Pytest reports 566.77s; command wall time is 567.414s. This is a failed whole-project run and remains so after supplementary tests.

## Identity and scope

`reconcile.py` independently maps the actual collected node IDs to JUnit classname/name identities (including imported compatibility tests), then compares the per-node journal. It verifies:

- Exactly 3748 unique collected nodes, 3748 unique JUnit testcases and 3748 unique journal starts; no missing, duplicated or extra execution.
- Exactly 11242 phase records. The 3746 non-setup-error cases each have setup/call/teardown; the two setup errors correctly have no call phase. All 229 assertion/error failures occur in call, both errors in setup, and teardown passes. One completed journal finish records exit 1.
- All 368 declared executable input hashes match the frozen review worktree, and the declared aggregate input hash recomputes exactly. The driver uses the intended `/workspace/p7` environment, explicit overlay TMPDIR and a new explicit basetemp; reviewed command records contain the actual exit codes.
- The all-markers collection contains 3750 unique nodes. Its exact difference from the default selection is only `tests/e2e/test_github_sync.py::test_nested_pagination_stress_workload` and `tests/live/test_smoke.py::test_selected_repository`. These two live/benchmark nodes were collected but not executed. No selected test is skipped or silently excluded.

| Scope | Passed | Failed | Setup errors |
|---|---:|---:|---:|
| P1–P6 plus P2/P3 and P5/P6 compatibility integration | 937 | 0 | 0 |
| Complete P7 integration | 255 | 0 | 0 |
| P7 distribution cases | 2 | 0 | 0 |
| Other packaging | 20 | 0 | 2 |
| Documentation site unit tests | 5 | 1 | 0 |
| Other selected project tests | 2298 | 228 | 0 |

The 255 P7 nodes exactly equal the node sets independently executed from both installed distributions by D. All eight listed post-suite schema/boundary/dependency/publication/Ruff/schema-visualization commands exit 0. These checks do not convert the failed global pytest result into complete acceptance.

## Main comparison: causes as well as node IDs

All **231** final failure/error nodes were selected once across four fresh main batches: **149 + 75 + 6 + 1**. Each batch records main **b86c46761ec0c3f3843a19edd4f3e106ef5ef58c**, uses its own new basetemp on overlay, and completes exit 1. The batch JUnit and journal identities independently reconcile exactly with their selected IDs. Together, their node set equals the entire final failure/error set with no omission or duplicate.

For **every one of the 231 nodes**, final and main have the same failure kind, the same normalized exception/assertion message, and the same final failing source filename/line. Normalization changes only worktree paths, generated temporary paths, worker HOME paths and memory addresses; assertion numbers, expected/actual values, SQL table names and missing-browser versions are preserved. Thus this is symptom/callsite equivalence, not merely node-name equality. Full original messages from both revisions and comparisons remain in `reconciliation.json`.

Classification:

- **228 preexisting public-runtime test failures**, reproduced with the same messages/callsites on main: **221 missing-table errors** and **7 unchanged assertion failures**. The originally reported **five Schema 21 failures are an exact subset**, leaving **223 additional reproduced runtime failures**. Do not report the inherited count as five or silently omit the other 223.
- **1 documentation environment failure**: both branches attempt a real Mermaid render during staging unit tests and lack `chrome-headless-shell` version 155.0.8059.79. Worker cache paths differ, but the missing executable/version and failing renderer location match. PR #89 is separate and is not merged into either branch to hide this failure.
- **2 generic packaging setup errors**: both branches lack the offline wheelhouse manifest. Neither failed setup executed the package test call phase.

D also independently executed two representative runtime failures in separate correctly bound main/final environments earlier. Both actual synthetic catalogs keep `jobs`, `job_attempts` and `collection_progress` in Operational, while the failing assertions query Core; relevant test/store/schema files are byte-identical. That provides a direct root-cause example for stale store routing. The current comparison establishes identical reproduced symptoms for all 228; it does not claim to have designed or validated repairs for every legacy assertion.

## Supplemental generic packaging execution

The initial global two setup errors remain unchanged in the raw full run. Root then prepared the documented external locked wheelhouse and attempted the two generic distribution nodes:

1. `distribution-corrected`: **2 failed**, exit 1. The package origins are correctly under the installed venv, but the fixture checks checkout exclusion with a broad string `startswith`. The sibling temp prefix `/workspace/p7-distribution-corrected` begins with checkout prefix `/workspace/p7`, causing a false fixture rejection. These failures are retained.
2. `distribution-final`: **2 passed in 54.15s**, exit 0 (54.610s command wall time), using `/workspace/distribution-acceptance-178` and the same external wheelhouse. Source is unchanged. JUnit, journal and exact command records reconcile both nodes and six passed phases, with no skip/error/failure.

The successful corrective run establishes the two generic installed-distribution cases after their prerequisites were supplied; it does not retrospectively erase either the original setup errors or the intermediate fixture-prefix failures.

## Limits

Main batches reran the complete failed/error set, not every passing main node. They are not a successful complete main acceptance run. Earlier tmpfs/ENOSPC-contaminated runs are retained and are not used as final correctness results. Whole-project acceptance remains blocked by the existing runtime failures and the local documentation browser environment. Unexecuted live/stress and full hosted release validation are disclosed scope, not newly invented ordinary merge requirements. No release, merge, deployment or production recovery was performed.

The root README's two material wording issues were sent to root: partial valid salvage can activate after final domain validation without becoming a completeness claim; and future release/live validation must not be presented as a new ordinary merge gate. Root confirmed both were corrected before the evidence commit.
