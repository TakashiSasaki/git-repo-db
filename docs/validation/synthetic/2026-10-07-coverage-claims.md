# Immutable coverage claims: synthetic acceptance

## Revision and scope

Base PR #5: `fee685db14e8052d2e9decd5f4b3470d4da80517`. Branch: `refactor/coverage-model`. Clean tested local commit: `48f4f42c6835ad20df20e47fd1bfbf06c3383909`; Git tree: `25df9e9511a5f0c25e68ba631b051d9a070f4b12`. Catalog schema 9 and workspace schema 2, with 65 ordinary tables and the `current_coverage` view.

Claims have immutable scope/time/state identity and separate optional advisory details. Current state derives from the maximum observation time before applying the weak-unknown rule; competing determinate states derive conflict. Atomic admission ignores stale and semantic duplicate inputs without changing details. The latest export selection retains every tied claim; the actual multi-catalog exchange protocol remains deferred.

Tests cover all stored-state subsets/permutations, newer unknown, conflicts, no fallback, exact detail retention, empty scopes, int64/time validation, direct replacement/update/deletion rejection, rollback and competing SQLite writers. Saved CLI coverage/status/snapshots and ordinary/diagnostic PR queries agree on the derived view. Runtime regressions preserve fixed-root and page observation times, exclude repository-wide claims from PR-only Git acquisition, separate unobserved failures from semantic coverage, and include nested pages across resume.

## Completed checks

| Check | Result | Profiled wall time |
| --- | --- | --- |
| Current ordinary acceptance, four workers | 622 passed | 143.177 s |
| Installed wheel and sdist-derived wheel | 2 passed | 14.067 s |
| Planner / collection / execution gate | 624 selected and executed exactly once, 46 files | Passed |

No selected test failed, skipped or remained unexecuted in the final run. Ruff lint/format, prose/JSON validation, STRICT/FTS doctor and locked wheel verification passed. The packaging lane runs independently and installs each distribution variant into its own venv outside the source checkout. Environment: Python 3.12.14, SQLite 3.53.1, Git 2.51.1, uv 0.12.19, Linux x86_64.

The current manifest was planned with `scripts/ci_plan.py --full`, collected before execution, run with `scripts/ci_execute.py run --lane tests` and `--lane packaging`, and reconciled using `scripts/ci_execute.py gate`. All command profiles and the plan identify the same clean tested commit. The adjacent JSON retains compact results.

## Earlier failures and review corrections

An owned runtime run passed 43 tests and failed an old expectation that authentication failure before any new repository observation should overwrite saved semantic complete coverage. The test now checks preserved coverage and the separately visible waiting job; its targeted rerun passed.

The first complete ordinary run on `9c4c6f250edf5e6df78847ed5549e05703385bb5` passed 620 tests and failed one schema assertion that applied the STRICT-table flag to the new view. The assertion now checks actual tables. This failed attempt is separate from the final successful run above.

Read-only review also found that nested GraphQL completion omitted children from earlier root pages after advancing and resuming a root cursor. Child request context now binds each collection to its exact parent, and timestamp selection includes all associated saved pages with matching owners. A regression observes root 100, child 300, interruption, and resumed root 200, plus an unrelated child 900 under another root in the same repository/PR/job. Coverage and the completion marker retain 300; earlier pages are not requested again. The new case and two existing nested-page cases passed before the final full run, and independent review confirmed the fix.

## Limits

Only disposable synthetic sources were used. No real acquisition, retained-source mutation, active-catalog cutover, previous-catalog migration, main merge or release was performed. Source/network/import protections remain enforced. Latest claim export/admission helpers do not provide a multi-catalog wire format or import workflow.

GitHub CI is independently attributed to the published commit and is not asserted by this local report. Publication through the connected GitHub API verifies the resulting Git tree against local Git objects; publication commit identities can differ from local test commits. Evidence-only documentation after this tested revision is not another runtime test run.
