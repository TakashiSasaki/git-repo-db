# I5 independent test inventory and offline execution

Base under test: commit `a54cb218226e3c91c44e979ee0df0543ea459502`, tree `cc2eafaaeb8e3305270c17e74ae69edc42c0a50b`. I5 adds no production changes. Initial inventory was performed while I5 test-only work was in progress; its 19 new nodes are explicitly separated from tracked base nodes using `git ls-tree HEAD tests`. Final candidate collection includes the frozen 20 I5 nodes. Frozen I5 source commit `20198151a6af2f8eefa43e85074307e9d77527b7`, tree `74b164f111859c96396ca751a5c90df7e0a5f53a`, is bound in `base-to-frozen-executable-binding.json`: 419 original src/tests/scripts/dependency files remain byte-identical. Final accepted execution source after the explicit test-fixture correction is `c2c3735439a714bbc9d4128421e7be2c0e88f5b4`, tree `fdafb830ba63a7f547c5882fe677f9d25ae36bd3`. `base-to-final2-executable-binding.json` proves 418 of 419 original executable files unchanged; only the deliberately corrected P5 packaging fixture differs. No production source changed.

## Actual runtime

Python 3.13.5 `/workspace/i5-runtime/venv/bin/python`, dynamically loaded SQLite **3.51.3**, source ID `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.

`runtime.json`, `sqlite-source-hash.json`, `runtime-artifact-sha256.txt`, locked installation logs, `installed-locked-dependencies.txt`, and `runtime-reproduction.sh` retain environment/reproduction details. Official sqlite3.c SHA3-256 was checked before compiling the library with `-DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_FTS5`. No reported exact-minimum result relies on a monkeypatched SQLite version. The session default Python 3.12 embeds a different SQLite and was not used for these accepted test commands.

Launch wrapper `/workspace/i5-runtime/python` prepends the venv binary directory to PATH and the SQLite library directory to LD_LIBRARY_PATH, preserving both for Python children. Dependencies: `uv sync --locked --group dev --group docs --python /usr/bin/python3.13` with `UV_PROJECT_ENVIRONMENT=/workspace/i5-runtime/venv`. PyYAML comes from the locked docs group. `scripts/prepare_wheelhouse.py` downloaded and hash-verified 48 locked compatible wheels before packaging tests; tests use offline/no-index/find-links and retain the network guard.

## Complete collection

| Scope | Base nodes | Final I5 additions | Final candidate |
|---|---:|---:|---:|
| All `tests/`, marker filtering overridden | 4,914 | 20 | 4,934 |
| Default ordinary, not live/benchmark | 4,912 | 20 | 4,932 |
| Non-live, benchmark included | 4,913 | 20 | 4,933 |
| Original registry CI cohort | 2,329 | 0 | 2,329 |
| First-freeze expanded I5 registry CI cohort | 2,329 | 20 | 2,349 |
| Final registry CI, corrected packaging nodes included | 2,333 | 20 | 2,353 |
| Historical additional ordinary outside original CI | 2,583 | 0 | 2,583 |
| Ordinary outside final registry CI | 2,579 | 0 | 2,579 |
| Benchmark outside default selection | 1 | 0 | 1 |
| Live not executed | 1 | 0 | 1 |

Final collection receipts are in `final2-inventory/` (frozen c2c37354 source; first-freeze and candidate receipts are also retained): all four collections exited 0, had no duplicate nodes, and full executable-input hashes matched before/after. Initial `audit/` collection saw 19 in-progress I5 nodes and therefore 4,933 all/4,931 ordinary. Normalized `*.base.nodes.txt` preserve the original base selection. `base-selection-summary.json` lists each omitted directory/module and count.

The 2,583 additional ordinary nodes comprise 49 E2E, 24 packaging, 237 unit, and 2,273 integration nodes, including architecture spikes, P2/P3 compatibility, legacy/public Schema 21, current-state, Coverage, Git, Exchange, CI-tooling and transport tests. They were not selected by the focused registry CI path list; this omission does not make them unimportant. All are safe synthetic/temp-directory offline tests and were executed. The single benchmark tests local nested pagination with 10,201 reply resources and is executable without external acquisition. The single live test `tests/live/test_smoke.py::test_selected_repository` requires a real GitHub repository plus real network acquisition, which the user explicitly prohibited, so it is retained as **not executed**, never counted as skip/pass.

## Execution results

| Execution set | Selected | Executed | Pass | Fail | Error | Skip | Xfail | Xpass | Process |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Base registry CI | 2,329 | 2,329 | 2,329 | 0 | 0 | 0 | 0 | 0 | exit 0 |
| Additional ordinary, corrected environment | 2,583 | 2,583 | 2,579 | 4 | 0 | 0 | 0 | 0 | exit 1 |
| Local benchmark workload | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | exit 0 |
| Final I5 E2E | 20 | 20 | 20 | 0 | 0 | 0 | 0 | 0 | separate E2E-agent receipt |
| Corrected P5 packaging fixture, author retest | 4 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | separate correction receipt |
| Corrected P5 fixture, read-only independent retest | 4 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | separate independent receipt |
| Prohibited live acquisition | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | not launched |

Base CI: `audit/ci-run.{selected.txt,xml,jsonl,execution.json,reconciliation.json}`, 258.309 seconds wall time, 4 xdist worksteal workers. Collection/starts/JUnit match at 2,329; 6,987 phases pass exactly once; successful journal finish and genuine subprocess exit 0. The original collection supervisor was canceled **after** writing its normal CI subprocess return-code receipt, before any redundant supplemental child, as documented in `audit/supervisor-cancellation.json`. No exit was synthesized from process state.

Corrected additional: `base-additional-fixed-path/`, 4 xdist worksteal workers, 606.999 seconds, genuine pytest subprocess exit 1; the exact 2,583 base node list excludes mutable I5 work. All 2,583 selected/JUnit/journal nodes and setup/call/teardown phases reconcile exactly. The four failures are all SHA-1/SHA-256 × direct/sdist-wheel permutations of `tests/packaging/test_p5_distribution.py::test_p5_installed_acquisition_and_exchange`, failing on `TypeError: ProviderPullRequestIntake.__init__() got an unexpected keyword argument repository_uuidv4`. This is the obsolete pre-I2 test fixture calling the intentionally removed Core-target shortcut. Full tracebacks are preserved in `failures.json` and the original exit-1 result remains unchanged. A separate author owns the fixture correction and targeted retest, with independent review; no production change is needed. The correction-author retest passed exactly those same four logical nodes, and the read-only independent reviewer separately passed all four on frozen c2c37354. The old fixture SHA-256 `92f6bda18d12ea18087eb6855ab65ec2bd43a339a0f2431cf660f4b1fe81ca24` becomes `a094ca2a1804bb87db09c43a51d2ab4386a124c85f316f1dd8dd2a3a33ed514d`; the mapping is explicit in `final-combined-summary.json`. The old four failures and exit 1 remain preserved. Benchmark: `base-benchmark/`, single worker, 51.764 seconds. Benchmark and supplemental execution overlap, so these wall times are **not comparable sequential benchmark measurements**.

The runner records exact commands and source/input hashes; quiet stdout/stderr goes to files, preserving complete failure evidence without sending bulk logs to the model. It compares selected/JUnit/journal multisets and all expected phase boundaries; failed setup may legitimately lack a call phase, while passing setup must have one call. Ordinary and benchmark sets are disjoint to avoid duplicate execution. No xfail/xpass marker exists in this collected tree; reported zero xpass is supported by that inspection.

## Preserved setup failures and corrections

- First all-node collection under dev-only dependencies: 4,906 nodes observed (including 19 in-progress I5), **one collection error** for missing `yaml` in `tests/unit/test_build_docs_site.py`; no test execution acceptance. Installing the locked docs group exposed 27 additional documentation-test nodes and resolved collection. Raw log and exit are `collection-all-initial.*`.
- The first supplemental launch had correct Python/SQLite but lacked venv/bin on PATH. Public CLI subprocess tests failed with `FileNotFoundError: repo-catalog`; this was an execution-environment defect. The run was deliberately interrupted, exit 2: selected 2,583; JUnit records 252 completed cases (203 pass, 2 fail, 47 setup errors), journal 253 starts with one unfinished case. Pytest's interrupt console reported 200 pass because concurrent worker reports were still arriving; the retained JUnit/journal are authoritative for the stated detailed counts. This incomplete run is **not** accepted evidence and does not claim all selected tests ran.
- `legacy-cli-counterexample.log` preserves the one-test missing-PATH failure; `legacy-cli-counterexample-path-fixed.log` reran the same test and passed 1/1 after adding venv/bin to PATH. A read-only independent triage agent also reran CLI/backup representatives, 3/3 passed, with actual installed CLI/interpreter identity recorded.
- `base-additional/` retains the interrupted invalid-environment run. Its failures are not silently relabeled as successful product tests. The full corrected additional set was executed separately as reported above.

## Reusable execution mechanism

`scripts/verify_i5_offline.py --output EMPTY_DIR --execute --workers 4` derives the focused selection from the actual workflow, collects all/default/non-live/CI nodes, runs disjoint CI/additional/benchmark sets, and records selection/command/runtime/JUnit/journal/summary evidence. It requires exact SQLite source ID, current-lock wheelhouse hashes, and an empty output directory. Full executable inputs (`src`, `tests`, `scripts`, workflows, pyproject, lock) are hashed before/after and a changed input causes failure. This helper is not a release receipt or merge approval. Ruff check and format pass for the helper.

## Final effective coverage after the explicit fixture correction

`final-combined-summary.json` compares the full final non-live node multiset with successful JUnit nodes from base CI 2,329 + unchanged supplemental 2,579 + local benchmark 1 + new I5 E2E 20 + corrected packaged P5 4. The result is **4,933 unique successful nodes**, exactly all final non-live tests, with no overlap or missing nodes. The read-only independent corrected-P5 JUnit matches the same four keys. The only unexecuted final node is the prohibited live acquisition test. There are no unresolved test failures after that explicit resolution; historical failures remain in their original run receipts.

This is a source-bound union of disjoint earlier execution evidence and a four-node correction retest, **not** a claim that one monolithic final-HEAD pytest process passed 4,933 tests. The final current CI cohort has 2,353 nodes (2,329 original + 20 I5 + 4 corrected packaging), leaving 2,579 ordinary tests plus the benchmark outside that hosted cohort. All 2,353 current CI nodes are included in local successful coverage. Hosted CI evidence is owned and reported separately by the root agent.
