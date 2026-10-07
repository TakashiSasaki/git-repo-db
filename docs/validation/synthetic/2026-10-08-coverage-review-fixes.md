# Coverage review corrections: recovered synthetic acceptance

## Outcome and revision

**Final local acceptance passed: 819 ordinary tests plus 2 installed-distribution tests, all 821 selected cases executed exactly once across 48 files.** This is an already-completed execution recovered during the resumed work. That work audited the records and rechecked the gate; it did not rerun either complete lane.

Clean tested commit: `604de8db0e957da28ea33f1e74110bc609d4cf63`; Git tree: `85a104190093492452dc81bcd956f1ee17dd76f0`; local branch: `fix/coverage-review-pr7`. It reconciles successor [PR #7](https://github.com/TakashiSasaki/git-repo-db/pull/7) with the broader local review corrections while retaining both histories. Publication targets `refactor/coverage-model-v2`. Catalog schema 9 and import workspace schema 2 are unchanged.

Later timestamp-evidence, report and handoff edits are documentation follow-ups, not another runtime acceptance. These results remain attributed to `604de8d`; hosted CI needs separate attribution.

Publication uses the connected GitHub Git Data API because command-line Git has no write credential. Each published tree is checked against the local Git tree; parent relationships are reproduced without changing existing remote history. Published commit IDs differ from local IDs and carry `Source-local-commit` and `Source-local-tree` trailers. The PR tracks the published head and its separate hosted validation.

## Verified corrections

| Area | Corrected behavior |
| --- | --- |
| Code targets and races | Finalize observations after complete target enumeration and matching Git acquisition. Newly observed head/code gaps remain incomplete. |
| GraphQL partial data | Preserve valid merge targets; require valid connection/pagination fields. Explicitly absent targets remain advisory `null` without becoming acquisition requirements. |
| Imported reuse and 304 | Retain original authorization, PR observation, marker and time; prevent duplicate completion markers and fresh replay timestamps even after current pointers advance. |
| Rate limits and failed rechecks | Preserve operational responses/retry deadlines without fabricating newer incomplete content claims. Actual incomplete observations still contribute partial coverage. |
| Query scope | Exclude code-only gaps from document-only requests; evaluate completeness independently of page size, byte cutoff and cursor. Share required-role checks between ordinary and historical queries. |
| Storage and timestamps | Make coverage ownership explicit, preserve negative-ID allocation behavior, reject fractional UTC offsets/NUL, and retain raw salvage values with NULL plus diagnostics. |

## Recovered execution

| Check | Result | Profile wall seconds | JUnit seconds |
| --- | --- | ---: | ---: |
| Ordinary, four xdist workers | 819 passed; 47 files | 177.934511 | 177.188 |
| Wheel and sdist-derived wheel, sequential | 2 passed; 1 file | 20.313949 | 7.608 |
| Selection/execution reconciliation | 821 exactly once; 48 files | Passed | — |
| Ruff lint / format | Both exit 0 | 0.076553 / 0.079082 | — |
| FTS / doctor | Both exit 0 | 0.086084 / 0.208720 | — |
| Prose/JSON readability | Passed; 51 files | 0.305527 | — |
| Offline locked dependencies / wheelhouse | Both exit 0 | 0.024484 / 0.201435 | — |

Both lanes began on 2026-10-08 at 02:08:26 JST; exact UTC starts are in the JSON. Profile duration measures the complete command and differs from JUnit duration. Environment: Python 3.12.14, SQLite 3.53.1, Git 2.51.1, uv 0.12.19, Linux x86_64. All ten command profiles match the tested SHA/runtime with `tracked_changes=false` and exit 0.

Installed tests build offline and use separate virtual environments outside the checkout, covering packaged resources, initialization, local Git discovery/sync, search, index rebuild, database checks and CLI entry points. Final records show zero failures, errors, skips or duplicate executions, with no profile advisory warnings or measurement errors. Pytest's stdout warning summary was not retained, so its total warning count is unknown.

## Commands and evidence audit

Recorded profiles contain complete argument vectors. Selection uses `--strict-markers -m 'not live and not benchmark'`, JUnit and `--durations=20`; ordinary execution adds `-n 4`.

```bash
uv sync --offline --locked --group dev
uv run --no-sync python scripts/prepare_wheelhouse.py
uv run --no-sync python scripts/ci_plan.py --full
uv run --no-sync python scripts/ci_execute.py collect
uv run --no-sync python scripts/ci_execute.py run --lane tests
uv run --no-sync python scripts/ci_execute.py run --lane packaging
uv run --no-sync python scripts/ci_execute.py gate
```

A fresh gate also needs successful planning/static/smoke/dependency/report profiles, as produced by the CI workflow; their commands are retained in the JSON.

Independent recovery checks matched raw XML, JSON profiles, selected IDs, plan and manifest exactly once. Read-only plan rebuilding matched the clean tree, current policy and runtime. The gate was rechecked on clean `604de8d` in this resumed turn: exit 0, 821 executed, 48 files, zero unexecuted/excluded acceptance files.

Separate resumed-turn focused checks passed 47 cases: 24 rate-limit/304/authorization/race, 22 malformed-GraphQL/stale-resume, and one explicit-null E2E case. The first E2E attempt lacked `repo-catalog` on PATH; repeating with `.venv/bin` passed without code changes. Three disposable-catalog query probes also passed. These overlapping/ad hoc checks are not added to the 821.

## Preceding failure

The preceding run at `0897fbc2ea1a943eb42264998d85ffcd668d5792` had 818 ordinary passes and one failure; both packaging tests passed. Wall times were 176.040869 and 7.824795 seconds. It has no success manifest.

`tests/e2e/test_github_sync.py::test_pr_documents` raised `KeyError: 'test-merge'` because explicit GraphQL `null` was omitted from advisory metadata. `604de8d` retains that absence; the strengthened regression verifies no acquisition requirement for the absent target and preservation of the actual merge role. The final complete execution passed after this correction.

## Evidence and limits

Recovered files remain under `artifacts/ci-profile/`, separately from `artifacts/ci-profile-0897fbc-failed/`. The adjacent JSON records exact byte lengths, SHA-256 hashes and canonical node-ID selection digests for attribution. It also distinguishes the Git tree OID from the planner's tree digest.

Only disposable synthetic sources were used. Acceptance covers current runtime, partial/incremental resume, interruption, recovery and guarded v2 salvage. Live/benchmark execution, real acquisition, retained-source mutation, active-catalog switching, compatibility migration, main merge, release, multi-catalog transport and additional providers are outside this validation.

An exploratory inherited malformed-input limitation remains: a REST review with `commit_id='not-an-oid'` reaches an uncaught `ValueError` in unchanged Git import `bytes.fromhex` parsing. This lies outside the original nine findings and was not changed by this correction. No real databases, caches, authenticated raw responses or secrets are included.
