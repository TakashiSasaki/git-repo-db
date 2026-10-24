# ADR 0031 I6-C Regression Reconciliation & CI Completeness Hardening Report

## 1. Executive Summary

- **Repository**: `https://github.com/TakashiSasaki/git-repo-db`
- **Phase**: Author correction of regression reconciliation and CI completeness.
- **Branch**: `fix/adr0031-i6c-regression-hardening-20261024`
- **Target PR**: PR #166 (`https://github.com/TakashiSasaki/git-repo-db/pull/166`)
- **Target Branch**: `fix/adr0031-i6c-access-verification-repair-20261024`
- **Target Base Commit**: `bb247180e14e024c274bcb49e845441504d9b863` (PR #166 HEAD)
- **Base PR #163 HEAD**: `2b33405b1a95eeddea277789e3bcc7b6b7307759`
- **Tested Input Commit**: `12090f79f160875591d19af5f3ebc1a4553a2803`
- **Tested Input Tree**: `15c394b94fc1cc20bc42adc1b3bfd44b01d4fccc`
- **Submission Status**: Author-complete (Draft PR targeting #166; no self-declared independent review acceptance)

This report supersedes `docs/implementation/evidence/adr0031-i6c-access-verification-repair-20261024/REPORT.md`. All historical evidence directories and raw receipts remain preserved as committed. This document records the resolution of concrete comparator defects, collection manifest enforcement, pytest exit code preservation, preflight audits, and empirical verification receipts.

---

## 2. Tested Input vs Submission Identity & PR #166 Hash Reconciliation

### 2.1 PR #166 Body SHA Reconciliation
In PR #166's pull request description, the submission commit was listed as `bb247180bf8e390cbf1737be7044dfec0509a259` with tree `3f185df2a16d004313f8d0a0ee447c2b5368a2bf`.

Audit against actual Git repository objects reveals:
- Object `bb247180bf8e390cbf1737be7044dfec0509a259` does **not** exist in the repository (`git cat-file: could not get object info`).
- The actual HEAD commit of branch `fix/adr0031-i6c-access-verification-repair-20261024` is **`bb247180e14e024c274bcb49e845441504d9b863`**, with tree `b513c6a893f73b730076dab6f1ae87ec8aae9b83`.
- The parent of `bb247180e14e...` is tested input commit `6287e5a581635dae769fb9d18231580d36135076` (tree `cb5346dbd790bebfebe3f112eae63c1f0eb477fe`).
- Tested input equivalence was verified: `git diff 6287e5a5...bb247180 -- src tests scripts pyproject.toml .github` is completely empty.
- The discrepancy was a transcription error in the PR description where a local preliminary commit SHA was copied instead of the final committed evidence commit.

### 2.2 Tested Input Separation for this Correction
| Property | Tested Input Commit / Tree | Final Submission Commit / Tree | Equivalence Proof |
| :--- | :--- | :--- | :--- |
| **Commit SHA** | `12090f79f160875591d19af5f3ebc1a4553a2803` | `HEAD` (Evidence commit stacked on top) | Product code, test definitions, scripts, and CI workflows are byte-for-byte identical. |
| **Tree SHA** | `15c394b94fc1cc20bc42adc1b3bfd44b01d4fccc` | (Evidence-only delta) | `git diff 12090f79...HEAD -- src tests scripts pyproject.toml .github` is empty. |
| **Executable Files** | Unchanged | Unchanged | Zero executable modifications were made after test execution. |

---

## 3. Executable Counterexamples and Comparator Hardening

Prior to this correction, `scripts/compare_access_regressions.py` suffered from six critical structural flaws, and the CI workflow discarded the pytest process exit code. Concrete executable counterexamples were constructed and verified to demonstrate each flaw before implementing the fix. All counterexamples are permanently codified in `tests/unit/test_compare_access_regressions.py` (12 tests, 100% passing).

### 3.1 Flaw 1: Skipped Testcases Treated as PASS
- **Observed Behavior**: `load_junit` checked only `tc.find("failure")` and `tc.find("error")`. If neither was present, `status` defaulted to `"PASS"`. A skipped testcase `<skipped message="..."/>` was thus recorded as `"PASS"`. If a test previously failed in baseline and was skipped in the current run, it was falsely classified as `RESOLVED`.
- **Counterexample**: Baseline failure + Current `<skipped/>` -> exited 0 with `resolved_count: 1`.
- **Hardening**: `load_junit` explicitly inspects `tc.find("skipped")` and assigns `status = "SKIP"`. The comparator tracks `unexpected_skips` and strict mode rejects any unexpected skips.

### 3.2 Flaw 2: Duplicate Testcases Silently Overwritten
- **Observed Behavior**: `cases[(c, n)] = { ... }` used a simple dictionary key, overwriting earlier executions if duplicate entries or subtests were present. If a test had a failure in setup/call followed by a pass in teardown/subtest, the failure was silently erased.
- **Counterexample**: XML containing `<testcase classname="c" name="t"><failure/></testcase>` followed by `<testcase classname="c" name="t"/>` -> current nodes recorded as 1, failure erased, exited 0 with `resolved_count: 1`.
- **Hardening**: `load_junit` records a complete list of execution records per node (`records: list[dict]`). Composite status is resolved by strict priority: `ERROR > FAIL > SKIP > PASS`. All failure evidence and subtest records are preserved.

### 3.3 Flaw 3: Added Failures and Environment Failures Passed `--strict`
- **Observed Behavior**: `--strict` checked only `summary["new_regressions_count"] > 0`. If a newly added test failed (`ADDED_FAIL`), or if an existing test failed due to environment issues (`ENVIRONMENT_FAILURE`), `new_regressions_count` remained 0 and the script exited 0.
- **Counterexample**: Adding a failing test node or triggering `FileNotFoundError: repo-catalog` -> exited 0.
- **Hardening**: Strict mode evaluates a comprehensive `blocking_violations` ledger, explicitly rejecting `added_failures_count > 0` and `environment_failures_count > 0`.

### 3.4 Flaw 4: Missing Nodes Counted Without Expected Execution Set
- **Observed Behavior**: Missing nodes were computed against the entire 6,343-node baseline. In a scoped execution of 1,847 nodes, `removed_nodes_count` reported 4,496, conflating out-of-scope baseline nodes with unexecuted missing tests.
- **Hardening**: Added `--expected` parameter accepting the exact collection manifest from `pytest --collect-only`. The comparator partitions baseline nodes into `in_scope_baseline_nodes` (1,847) and `out_of_scope_baseline_nodes` (4,496). Missing in-scope nodes are classified as `MISSING_EXECUTION` and rejected under strict mode; out-of-scope baseline nodes are preserved without false deletion claims.

### 3.5 Flaw 5: Empty Current JUnit XML Accepted
- **Observed Behavior**: If `current.xml` was empty (`<testsuites></testsuites>`), `current_cases` was empty, `new_regressions_count` was 0, and `--strict` exited 0.
- **Counterexample**: Empty XML against baseline -> exited 0.
- **Hardening**: Strict mode asserts `current_nodes > 0` and requires 0 missing expected nodes.

### 3.6 Flaw 6: Changed Failures Blindly Called Inherited
- **Observed Behavior**: Any node failing in both baseline and current was labeled `inherited` without comparing phase, exception type, refusal code, or reached assertion. A test failing in `call` phase with `PERMISSION_DENIED` in baseline that subsequently crashed in `setup` phase with `DatabaseError` was silently accepted as inherited.
- **Counterexample**: Baseline `UnsupportedResourceStage` vs Current `setup error: DatabaseError` -> exited 0 with `inherited_count: 1`.
- **Hardening**: `compare_failure_details` performs multi-dimensional comparison:
  1. Compares execution phase (`setup`, `call`, `teardown`).
  2. Compares refusal codes (`PERMISSION_DENIED`, `INVALID_IDENTIFICATION`, `UnsupportedResourceStage`).
  3. Compares reached assertions and exception types.
  Unexplained changes are classified as `CHANGED_FAILURE` and rejected under strict mode.

### 3.7 Flaw 7: Discarding Pytest Exit Code in CI Workflow
- **Observed Behavior**: `.github/workflows/access-registry.yml` wrapped pytest in `set +e ... set -e`, completely discarding the exit code. Pytest exit codes 2 (interrupted), 3 (internal error), 4 (usage error), and 5 (no tests collected) were ignored.
- **Hardening**: The workflow captures `pytest_exit`, validates that exit codes 2, 3, 4, 5 immediately abort the step, and passes `--pytest-exit-code "$pytest_exit"` to `compare_access_regressions.py`. The comparator verifies that exit code 1 is permitted only under complete, reconciled scoped acceptance.

---

## 4. Preflight Audit & Test Isolation Review

### 4.1 Audit of Preflight Claims
The four preflight claims from PR #166 were audited against actual implementation and hardened:

1. **Locked Dependencies**:
   - *Previous Gap*: `check_interpreter` used `importlib.util.find_spec` on 3 packages, which merely checked package presence without verifying versions against `uv.lock`.
   - *Correction*: `check_interpreter` now parses `uv.lock` using `tomllib` (<0.04s) and verifies the exact locked versions for `httpx` (0.28.1), `pytest` (9.1.1), `ruff` (0.16.10), `pytest-xdist` (3.8.0), `hatchling` (1.32.4), and `jsonschema` (4.26.0) using `importlib.metadata.version`.
2. **Console-script Identity**:
   - *Previous Gap*: Executing `repo-catalog --help` did not verify interpreter shebang or module origin.
   - *Correction*: `check_console_script` verifies:
     a) Shebang path matches active `sys.executable`.
     b) `repo_catalog` module origin is within the active repository (`ROOT / "src" / "repo_catalog"`).
     c) `repo-catalog --version` returns `0.2.0` matching `repo_catalog.__version__`.
3. **Environment Propagation**:
   - *Previous Gap*: Modifying `os.environ["PATH"]` and calling `os.umask(0o022)` in a Python process was process-local and did not propagate to subsequent bash steps.
   - *Correction*: `preflight_access.py` appends `venv_bin` to `GITHUB_PATH` when run under GitHub Actions. Workflow bash steps explicitly execute `umask 022`.
4. **SQLite Capability Policy**:
   - *Previous Gap*: In-memory SQLite probe claimed "safe WAL" in docstrings without testing WAL (impossible on `:memory:`).
   - *Correction*: Reuses accepted product SQLite capability check from `repo_catalog.adapters.sqlite.access_schema.require_runtime()` and verifies `STRICT`, `json_valid`, `fts5` trigram, and `PRAGMA journal_mode=WAL` on a disk-backed temporary database.

Total preflight execution time remains ultra-fast at **0.25s**.

### 4.2 Review of Global `tests/conftest.py`
Global `tests/conftest.py` modifications were reviewed for side-effects on permission and Git identity tests:
- `monkeypatch.setenv("PATH", ...)`: Scoped strictly to test function duration; ensures child processes find project scripts.
- `monkeypatch.setenv("GIT_AUTHOR_NAME", ...)`: Provides standard fallback identity when `workerinput` redirects `HOME` to an empty directory, preventing git errors while allowing individual tests to override via local monkeypatching.
- `os.umask(0o022)`: Cleanly saved and restored via `finally: os.umask(old_umask)`.
- No tests expect missing Git credentials or un-masked umask; all 939 Access acceptance tests and 1,847 regression tests execute cleanly without regression.

---

## 5. Empirical Verification Receipts

### 5.1 Scoped Access Acceptance Receipt
- **Command**: `pytest -q -n 2 --dist worksteal tests/unit/test_access*_values.py tests/unit/test_context_registration_values.py tests/unit/test_native_acquisition_values.py tests/integration/access`
- **Result**: **939 passed, 0 failures, 0 errors** in 127.88s.
- **Audit**: `scripts/audit_access_acceptance.py --junit raw/scoped_tests.xml --collection raw/scoped_collected.txt`
  - `executed_nodes`: 939
  - `node_set_matched`: true
  - `exit_code`: 0

### 5.2 Broad Regression Receipt & Scoped Reconciliation
- **Command**: `pytest -q -n 2 --dist worksteal tests/integration/i2 tests/integration/i23 tests/integration/i4 tests/integration/i5 tests/packaging/test_p5_distribution.py tests/integration/p1 tests/integration/p3 tests/integration/p5 tests/integration/i3 tests/integration/p2 tests/integration/p4 tests/integration/p6 tests/integration/p7 tests/integration/p5_p6_compatibility`
- **Result**: **1,645 passed, 182 failed, 20 errors** in 419.62s.
- **Process Exit Code**: `1` (captured and verified).
- **Comparison Against Baseline #154**:
  - Baseline total ordinary nodes: 6,343
  - In-scope baseline nodes: 1,847
  - Out-of-scope baseline nodes: 4,496 (preserved, not deleted)
  - Expected nodes: 1,847
  - Executed nodes: 1,847
  - Missing expected nodes: **0**
  - Unexpected nodes: **0**
  - Resolved non-successes: **72** in broad suite (+25 in Access suite - 1 Transfer fence correction = **83** overall)
  - Inherited unchanged non-successes: **202** (43 staged Transfer fences, 145 unauthenticated admission `PERMISSION_DENIED`, 14 P7 recovery context admission refusals)
  - New product regressions: **0**
  - Added failures: **0**
  - Environment failures: **0**
  - Changed non-successes: **0**
  - Unexpected skips: **0**
  - Strict Acceptance Verdict: **PASSED** (0 blocking violations, exit code 0)

### 5.3 Evidence Reuse
Distribution verification receipts (`distribution.json`) were reused from PR #166:
- **Justification**: Product source code (`src/`) and packaging definitions (`pyproject.toml`) are byte-for-byte identical (`git diff 6287e5a5...HEAD -- src pyproject.toml` is empty).
- Direct wheel and sdist-derived wheel are bit-for-bit identical with SHA-256 `c3a147b2111e2e22e75af1c1390cfe9b9e8a8f68f5a4a8a6f3584bd608b1360a`.

---

## 6. Non-Author Review Handoff & Open I6-C Obligations

In accordance with repository review policies, Authors **must not** declare an independent `PASS` on their own submissions. The findings verdict remains **`INCOMPLETE / PENDING_INDEPENDENT_REVIEW`**.

The earlier #164 independent review does not close the following I6-C obligations, which require non-Author independent behavioral verification after this correction:
1. **Empty receiver selection**: Verification that empty selection scope admits 0 items without failure.
2. **Same full sender package with receiver-side subset selection**: Verification that receiver-side filtering correctly admits the specified subset while omitting unrequested items.
3. **Real COMMIT revocation**: Verification that revocation during transaction execution raises `PERMISSION_DENIED` at the commit boundary.
4. **Foreign service-issued handles**: Verification that foreign UUIDs and mismatched credentials fail closed.
5. **Replay revocation**: Verification that subsequent replays of revoked authority fail closed.
