# Independent corrected-tree review: acquisition and completeness

Status: **scope-2 acquisition/completeness review accepted on the exact frozen candidate below**. All ten initial acquisition findings are resolved in independently executed counterexamples. No unresolved mandatory issue was found within the reviewed scope. This is a scoped review receipt, not full architecture, Git/Exchange/CAS, package or hosted-CI acceptance.

Reviewer: fresh independent subagent `/root/review_acquisition`; did not author the production changes. Model and reasoning effort: **not exposed**. No additional subagents were used. The original review context, initial scripts, failure results and initial receipt remain preserved; the initial failed tree is not retroactively accepted.

## Exact source and execution binding

- Corrected worktree: `/workspace/reviews/publication-free-acquisition-corrected`.
- Final tested commit: `b86ff2c96d7558379b2230489e1494630b073ef7`.
- Final tree: `085be492d5fbd8cfbcaa7eb4be3d1db27af84fee`.
- Packaged composed DDL SHA-256, computed from the imported production `schema.DDL_SHA256`: `f1ec742a1d9778dab4ed7950bef0f257d0d368ee8c3d89f945cba61ed23ebd04`.
- Initial reviewed commit/tree: `41dbe5550afaac248971d13994ae4a8c37274197` / `1a518382d4aefdbea1441cf0ae9965b7025b40bd`.
- Whole implementation comparison baseline: `0bd5704caca2f6e3723bef22531b065cd4d7bad0`.
- Interpreter: `/workspace/git-repo-db/.venv/bin/python`; Python 3.12.14, SQLite 3.53.1.
- Independently verified import: `/workspace/reviews/publication-free-acquisition-corrected/src/repo_catalog/__init__.py`.
- `git status --porcelain` was empty after execution. No production source, executable tests, Git history or retained catalog was edited by this reviewer. All mutations were in disposable Git/SQLite fixtures; HTTP was synthetic localhost/dummy-token only.

The first corrected checkpoint was `e810427fba1f205c9dd5c1a8abe75a3412402b6e`, tree `553485873684e22d1f2c15261c22d3f58ee79a7d`. A 35-node exploratory run passed there. Before the final runs, the isolated checkout was rebound to b86. Independently inspected e810-to-b86 changes: only the two completed test-disposition rationale JSONs changed; production, executable tests and composed DDL were identical. The final receipt nevertheless uses fresh b86 executions.

Read the repository/Phase-2 AGENTS instructions, full design, ADR, decision register and implementation prompt during the initial review. Reinspected their continuing applicability, the implementation handoff, updated schema map and acquisition-related test dispositions. Saved the full baseline-to-b86 diff as `corrected-baseline-full.diff`, the initial-to-corrected production delta as `corrected-production-delta.diff`, and the complete correction inventory as `corrected-diff-inventory.txt`. Production review concentrated on acquisition/current-state/completeness paths and affected shared guards; unreviewed cross-domain boundaries are disclosed below.

## Independently executed results

| Final-bound run | Collected | Passed | Failed/errors | Skipped | Reported elapsed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Preserved initial probes, minimally adapted closed-vocabulary context | 35 | 35 | 0 | 0 | 297.70 s |
| Newly authored corrected-tree counterexamples | 15 | 15 | 0 | 0 | 139.51 s |
| Total | **50** | **50** | **0** | **0** | — |

Independent scripts use existing disposable Git/localhost setup support, but do not call implementer-authored test functions. The initial 35-node snapshot remains untouched in `frozen-probes-v1/`. Corrected copies are in `corrected-probes-v1/`; the sole adaptation changed unsupported `request_context.distinct='resume-case'` to supported `state='all'` in two calls, preserving every cancellation, restart, cache-loss and resource-usability assertion. This is required by the corrected closed vocabulary, rather than weakening the behavior assertion.

Final commands, CWD the isolated corrected worktree:

```sh
PYTHONPATH=/workspace/reviews/publication-free-acquisition-corrected/src:/workspace/reviews/publication-free-acquisition-corrected:/workspace/review-artifacts/acquisition/corrected-probes-v1 PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python -m pytest -q /workspace/review-artifacts/acquisition/corrected-probes-v1 --tb=short --junitxml=/workspace/review-artifacts/acquisition/b86-independent-35-results.xml > /workspace/review-artifacts/acquisition/b86-independent-35-results.txt 2>&1

PYTHONPATH=/workspace/reviews/publication-free-acquisition-corrected/src:/workspace/reviews/publication-free-acquisition-corrected:/workspace/review-artifacts/acquisition/corrected-probes-v1 PATH=/workspace/git-repo-db/.venv/bin:$PATH /workspace/git-repo-db/.venv/bin/python -m pytest -q /workspace/review-artifacts/acquisition/corrected-new-probes.py --tb=short --junitxml=/workspace/review-artifacts/acquisition/b86-new-v2-results.xml > /workspace/review-artifacts/acquisition/b86-new-v2-results.txt 2>&1
```

Script SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| `corrected-probes-v1/test_independent_acquisition.py` | `31e0c15293750501076835171e31e37cfc9ad0d89185b8516d8c8a10966aec12` |
| `corrected-probes-v1/test_independent_invariants.py` | `1b159d16be95514b89c31b04796b5cdb53a96a66761493d3e29f3abd8bfc5ddc` |
| `corrected-new-probes.py` | `8e442e78ca4e267d9a2fb53bcb9b5ea6d784a03891db0f938ab2a08d2f780d2e` |

`corrected-artifact-sha256.json` binds scripts, logs, JUnit files and reviewed diffs. Earlier runs are preserved separately: `e810-exploratory-results.*`, and `b86-new-exploratory-fixture-errors.*`. The first 15-node exploratory attempt had two reviewer fixture errors: it seeded unsupported PR1 before the full-sync fixture (which serves PR41–43), and queried nonexistent `job_attempts.started_at_us`. Those fixture mistakes were corrected to use the real fixture roster and `created_at_us`; no production change was made, and their original script/logs remain preserved. The corrected 15-node run has zero errors/failures. Concurrent acceptance suites ran elsewhere during these executions; elapsed times are not comparative performance evidence.

## Initial finding resolution

| Finding | Initial severity | Independently verified corrected behavior and relevant source change |
| --- | --- | --- |
| ACQ-01 capped commits prevent independent files | High | `_code_collect` independently attempts commits and files, retaining actual partial listing results. The capped-251-commits counterexample now requests/adopts the independent file. `test_capped_commits_still_collect_independent_files` passes. |
| ACQ-02 lost partial listing IDs | High | The collector retains durable listing tuples through failures and sync passes them to assessment. Full synthetic capped-commits sync now links the assessment to its persisted partial commits listing. `test_partial_listing_ids_recoverable_for_assessment` passes. |
| ACQ-03 missing per-field observed permissions | Medium | `current_context` includes `observed_permissions`. Both the initial direct-context probe and a new real `/user` `x-oauth-scopes` transport probe pass; stored body-field origin contains sorted `['read:org','repo']`. |
| ACQ-04 REST sparse title rejected | Medium | `rest_item` validates title only when present; sparse body-only detail updates body and inherits original title/origin. The sparse test and missing-versus-null provenance matrix pass. Explicit malformed title remains invalid. |
| ACQ-05 stale redirect fence | Medium | `request_get` captures and attaches receiver revision before each actual request. A verified rename no longer leaves the final GET fenced to the old URL's revision. The initial unclocked live rename probe passes. A new counterexample advances revision during the final response and is correctly rejected, proving the fence is not refreshed after response to manufacture authority. |
| ACQ-06 foreign GraphQL PR owner completes local roster | High | PR projection retains real REST `node_id`; root query also requests number. Root collection requires matching retained opaque identity or typed requested number and rejects contradictory supplied values. Initial foreign-id attack and six new foreign/missing/bool/matching owner variants pass. No opaque alias is fabricated when none was retained. |
| ACQ-07 assessment175 overwrites complete300 | High | `_assess_code` preserves a newer same-target assessment against older/unknown results. The genuine full-sync complete300 then older175 counterexample passes. Existing independent head-A-to-B probe still confirms B cannot borrow A. |
| ACQ-08 escaped Issue field-clock alias | Medium | Generated SQL reconstructs decoded canonical JSON path arrays, rejecting `["\\u0062ody"]` as a second semantic body evidence key. Direct SQL guard probe passes; Python and SQL now agree on canonical path spelling. |
| ACQ-09 code-check304 with lost representation | Medium | `code_check` performs an unconditional fresh-body fetch after 304 and requires an actual representation. The real-fetch two-request counterexample passes. Existing detail repeat304 probe still returns `REUSE_UNAVAILABLE` without hiding admitted resources. |
| ACQ-10 opaque current/pending replica capture | High | Capture/context metadata uses a closed typed vocabulary before both admission and dependency staging; corresponding SQL guards enforce it. Initial Python current/missing-parent attacks reject. Four new direct-SQL current-scope, field-scope, pending-scope and pending-field-scope attacks reject; valid catalogs remain readable and validate. |

## Shared corrections and adversarial coverage

- Store and shared atomic units: outer/nested body and statement failure, deferred COMMIT and nested deferred-constraint failure, inner rollback preserving outer work, revision rollback, and rollback-cleanup failure retirement while preserving the original error. Current row/value/presence/evidence/text/revision remain all-or-none under a real constraint failure.
- Sparse current fields retain module/version and clock origins through v1/v2 updates; omitted field inherits while explicit null participates as a value. Imported check timestamps do not advance receiver-local checks. Unknown-clock changes require actual matching scope and pre-request revision; equal/imported alternatives remain unresolved.
- Genuine acquisition and direct claims exercise complete100 → identifiedpartial200 → oldercomplete175 → complete300, then equal-time/unknown candidate behavior. Valid committed page resources remain usable through larger list errors.
- Genuine empty terminal differs from absent terminal. Required child omissions prevent parent completion. A new direct domain attack installs a valid independent thread and terminal parent page but omits its required-child relation; both normal finish and a forged flat complete marker reject. A new real GraphQL child continuation returning a foreign thread ID fails while the valid root thread remains eligible and coverage remains partial.
- Source R1/R2 positive pairs survive a later partial R1 inventory; R2 row/evidence are unchanged, v1 inherited name evidence and v2 new-field evidence remain distinct. Detached captured IDs remain portable without invented registrations and reject a later contradictory known binding.
- Cancellation preserves a committed prefix. Operational cursor deletion produces `RESUME_UNAVAILABLE`; admitted domain resources remain usable. Detail304 and code-check304 exercise genuine safe fetch/reuse outcomes. Optional external archive and warning-hook failures are bounded/nonfatal and do not retain arbitrary raw error content.
- New missing-credential-before-acquisition probe removes the credential only after frozen-job setup. It performs no HTTP, creates no Source inventory observation, classifies the Source as operationally skipped with partial result and complete attempt, preserves an already admitted document and retains no dummy token in frozen job JSON.
- HTTP callbacks assert no write transaction over tested requests. Current module/version provenance remains evidence rather than profile/certificate/generic-batch validity gating. Parent/child completion proof is domain-specific; it is not a generic Publication owner.

Inspected affected production paths: GitHub collector/parser/persistence; Store/shared transaction helper; current-resource field engine; CurrentApiState and Source association/inventory admission; current collection proof and SQL triggers; generated current/Source/staging JSON guards; collection-service credential classification; Coverage candidates; PR exact target/current assessment selection; optional recording and transport-304 boundary. Shared Exchange and Git changes were inspected only where they touched current typed admission/capture/target dependencies; their complete behavior is another independent scope.

The updated disposition rationale preserves existing parameter dimensions for normalized empty terminal, required child, cross-parent/thread/capture/head/base attacks. The independent probes in this receipt establish the behavior directly; implementer execution claims in the disposition file are not used as independent acceptance evidence.

## Limits and remaining acceptance

Not independently executed here: complete ordinary suite, isolated installed wheel/sdist suites, hosted CI, selected-scale benchmarks, all DDL triggers, canonical Git-object/decoder ambiguity, whole Exchange reverse/closure/onward-export semantics, CAS repair/quarantine/backup/restore, 10,000-update retention growth, real OS/I/O/process-kill faults or writer-lock concurrency. Their completion remains with the other scopes and root verifier. SQLite deferred constraints and injected cleanup failures were exercised instead of claiming real storage-fault coverage.

This review adopted no unapproved deletion-on-absence, GC/retention, provider-trust, total clock ordering, Source negative-membership, decoder preference or generic batch eligibility policy. Scope-2 sign-off is bound to b86/source/tree/DDL above. Subsequent affected source changes require renewed review; metadata-only changes can be rebound by content identity but do not silently change this receipt's tested SHA.
