# Unix epoch microsecond normalization: synthetic acceptance

## Revision and scope

Base PR #4: `307ab6a8df3bc05a99670495676ef25b7c613289`. Branch: `refactor/unix-microsecond-timestamps`. Clean tested local commit: `27ab5e37ae5fefbccfee4e8217c657356961c3ef`; Git tree: `5a5c0225d98ce2d6d70b068f2f0728ee97ce2fb0`. Catalog schema 8 and workspace schema 2.

All normalized persisted absolute timestamps use signed 64-bit integer Unix microseconds with `_us` names. Raw provider/Git and typed legacy source evidence remain unchanged. Boundary tests cover timezone equivalence, epoch 0 and negative instants, adjacent microseconds, int64 limits, high-precision decimal conversion and invalid-time diagnostics. Runtime tests cover exact ordering, job retries, cache TTL, API date parameters, replay, finalization and source/workspace recovery.

## Completed checks

| Check | Result | Profiled wall time |
| --- | --- | --- |
| Current ordinary acceptance, four workers | 500 passed | 110.470 s |
| Installed wheel and sdist-derived wheel, sequential | 2 passed | 16.382 s |
| Planner / collection / execution gate | 502 selected and executed exactly once, 44 files | Passed |

No selected test failed, skipped or remained unexecuted in the final run. Ruff lint/format, prose validation, STRICT/FTS doctor and locked wheel verification passed. Both distribution variants install into separate venvs and execute outside the source checkout. Environment: Python 3.12.14, SQLite 3.53.1, Git 2.51.1, uv 0.12.19, Linux x86_64.

The current manifest was planned with `scripts/ci_plan.py --full`, collected before execution, run with `scripts/ci_execute.py run --lane tests` and `--lane packaging`, and reconciled using `scripts/ci_execute.py gate`. Commands were bound to the same clean tested commit. The adjacent JSON retains the compact results.

## Earlier failures and review

An initial full run passed 499 tests and failed one obsolete schema-version assertion. The next run passed all 500 ordinary tests, but both distribution tests retained the old schema-7 assertion. These expectations now read the active schema contract; the final clean-commit acceptance above is separate. These failed attempts are not counted as passing runs.

Independent review identified a decimal-context rounding defect near a microsecond boundary. Exact digit/exponent conversion fixed it, and positive/negative, extreme-exponent and low-context-precision regressions pass.

## Limits

No real provider acquisition, retained source mutation, active-catalog cutover, release or main merge was performed. GitHub CI is independently attributed to the published commit and is not asserted by this local evidence. Publication through the connected GitHub API verifies the resulting Git tree against local Git objects; publication commit identities can differ from local test commits.
