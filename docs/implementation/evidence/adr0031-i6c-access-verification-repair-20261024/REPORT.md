# ADR 0031 I6-C Access Verification Infrastructure Repair and Evidence Reconciliation Report

## 1. Executive Summary

- **Repository**: `https://github.com/TakashiSasaki/git-repo-db`
- **Phase**: Author correction of verification infrastructure and demonstrated product defects.
- **Branch**: `fix/adr0031-i6c-access-verification-repair-20261024`
- **Target Base**: `fix/adr0031-i6c-access-reconciliation-20261024` (PR #163 HEAD: `2b33405b1a95eeddea277789e3bcc7b6b7307759`, base tree: `0970b876c8152a2faefa343e43c5b366ddd7a568`)
- **Tested Input Commit**: `6287e5a581635dae769fb9d18231580d36135076`
- **Tested Input Tree**: `cb5346dbd790bebfebe3f112eae63c1f0eb477fe`
- **Submission Status**: Author-complete (Draft PR targeting #163; no self-declared independent review acceptance)

This report supersedes the earlier report published in `docs/implementation/evidence/adr0031-i6c-access-reconciliation-20261024/REPORT.md`. The historical evidence directory and raw artifacts have been fully preserved as committed. This document corrects the accounting discrepancies, rectifies the classification of inherited non-successes, documents the environment preflight and test isolation repairs, and reports the mechanical regression reconciliation against baseline #154.

---

## 2. Tested Input vs Submission Identity

| Property | Tested Input Commit / Tree | Final Submission Commit / Tree | Equivalence Proof |
| :--- | :--- | :--- | :--- |
| **Commit SHA** | `6287e5a581635dae769fb9d18231580d36135076` | `HEAD` (Evidence commit stacked on top) | Product code, test definitions, scripts, and CI workflows are byte-for-byte identical. |
| **Tree SHA** | `cb5346dbd790bebfebe3f112eae63c1f0eb477fe` | (Evidence-only delta) | `git diff 6287e5a5...HEAD -- src tests scripts pyproject.toml .github` is empty. |
| **Executable Files** | Unchanged | Unchanged | Zero executable modifications were made after test execution. |

---

## 3. Raw Evidence Accounting Reconciliations

### 3.1 Ordinary-Node versus Subtest Accounting
In PR #163's raw execution receipt (`ordinary.xml` / `ordinary.log`):
- `ordinary.log` reported: `255 failed, 6040 passed, 92 errors, 57 subtests passed in 1434.79s`.
- `ordinary.xml` root `<testsuite>` attributes: `tests="6444"`, `failures="255"`, `errors="92"`.
- Individual `<testcase>` XML elements total: **6,387** (`6040 passed + 255 failed + 92 errors = 6,387`).

**Accounting Principle**:
Pytest's JUnitXML plugin counts subtests (`pytest-subtests`) by adding subtest passes to the root `<testsuite tests="...">` counter, while only top-level test functions generate distinct `<testcase>` XML elements:
$$\text{Root testsuite } tests = \text{Top-level testcases } (6,387) + \text{Subtest passes } (57) = 6,444$$

The identical accounting holds for the authoritative #154 baseline (`source-full-final/ordinary.xml.gz`):
- Top-level testcases: 6,343
- Subtest passes: 57
- Root testsuite `tests` attribute: 6,400 ($6,343 + 57 = 6,400$)

### 3.2 Resolution of Historical Baseline 6,343 vs 6,344 Discrepancy
Raw records in baseline PR #154 (`docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/`) contained two different node collections:
1. `source-full/all-collection.nodes.txt`: **6,344 nodes**.
   This collection was run unfiltered (`pytest -q --collect-only -o addopts= tests`) prior to commit `d68dc43`. It included the 2 live/benchmark tests:
   - `tests/live/test_smoke.py::test_selected_repository`
   - `tests/e2e/test_github_sync.py::test_nested_pagination_stress_workload`
   At that commit, ordinary tests were 6,342 ($6,342 + 2 = 6,344$).
2. `source-full-final/ordinary-collection.nodes.txt`: **6,343 nodes**.
   In commit `d68dc43`, test `test_zero_budget_preserves_fixed_envelope_hard_cap_before_row_indexing` was added (+1), while `-m "not live and not benchmark"` deselected the 2 marked live/benchmark tests (-2):
   $$6,342 + 1 = 6,343 \text{ ordinary test nodes}$$

Thus, **6,343** is the true, authoritative ordinary test node count of baseline #154.

Between baseline #154 and the current tree, exactly 44 new test nodes were added:
- 43 in `tests/integration/i6/test_i6c_authority_and_exchange.py`
- 1 in `tests/unit/test_context_scan_budget.py`
$$6,343 + 44 = 6,387 \text{ total ordinary testcases}$$

---

## 4. Reclassification of Baseline Non-Successes & Demonstrated Defects

PR #163's `node-comparison.json` erroneously claimed 84 resolved failures, 215 unchanged Transfer-stage failures, and 0 new regressions. Detailed investigation revealed multiple contradictions in that accounting:

### 4.1 `test_transfer_reports_never_shrunk_or_mixed` is NOT Resolved
`test_transfer_reports_never_shrunk_or_mixed` in `tests/integration/i3/test_selective_exchange.py` was claimed resolved in PR #163. Inspection of `raw/ordinary.xml` shows that it actually failed with:
`UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED: admit_transfer_event requires reviewed I3-I5 support`.
The test remains an inherited staged Transfer fence failure. Therefore, the true resolved count in `test_selective_exchange.py` is **58** (not 59), and total resolved baseline non-successes is **83** (not 84).

### 4.2 Distinguishing Transfer Stage Fences from Admission Refusals
PR #163 misattributed all 215 non-successes as "Transfer-stage failures". The actual 216 inherited non-successes belong to three distinct technical categories:

1. **`INHERITED_ADMISSION_PERMISSION_DENIED` (157 nodes)**:
   Tests that invoke Provider intake, Exchange import, or Context mutations without receiver grants, failing closed with `AdmissionRefused("PERMISSION_DENIED")` or `INVALID_IDENTIFICATION`. These are intentional admission authorization fences, not Transfer stage fences.
2. **`INHERITED_STAGE_TRANSFER` (45 nodes)**:
   43 nodes failing with `UnsupportedResourceStage` (including `test_transfer_reports_never_shrunk_or_mixed`) and 2 nodes tripping SQL trigger fences `i2_transfer_stage_fence` and `i2_transfer_report_stage_fence`. These are staged Transfer fences.
3. **`INHERITED_P7_RECOVERY` (14 nodes)**:
   11 nodes in `test_bounded_input`, 1 in `test_adversarial_contract_cases`, 1 in `test_exact_replay`, and 1 in `test_missing_required_authority`.
   In particular, `test_malformed_primitive_shape_is_one_rejection_not_merge_abort[bad0]` reaches assertion `assert receipt.rejected_units == receipt.admitted_units == 1` with `rejected_units=2` and `admitted_units=0` because candidate 2 (`context_document`) is refused with `Context admission error: PERMISSION_DENIED` due to missing write authority, rather than Transfer fences.

### 4.3 Elimination of Environment Failures (142 nodes in PR #163)
In PR #163 `ordinary.xml`, 347 non-successes occurred. 142 of those were purely environment failures:
- **138 nodes** failed with `FileNotFoundError: 'repo-catalog'`: Subprocess calls in integration tests failed because `.venv/bin` was not in `PATH`.
- **2 nodes** failed with `Run scripts/prepare_wheelhouse.py`: Packaging tests failed because locked wheels had not been prepared.
- **2 nodes** in `test_notes.py` failed with `Git author identity unknown` and editor failure.

**Repairs Made in `tests/conftest.py`**:
- Auto-discovery and prepending of `sys.executable`'s parent directory (`.venv/bin`) to `PATH`.
- Default umask set to `0o022` with cleanup restoration, preventing `EXECUTOR_PERMISSIONS` failures in `LocalDirectoryExecutor`.
- Standard Git author and committer environment variables and non-blocking `GIT_EDITOR="true"` exported for isolated test subprocesses.

Under these repairs, all 142 environment failures were completely eliminated. Product regressions remain strictly **0**.

---

## 5. Verification Infrastructure Architecture

### 5.1 Fast Runtime Preflight (`scripts/preflight_access.py`)
A sub-0.2s preflight check executes before test suites:
- **Interpreter**: Python >= 3.12 verified.
- **Locked Dependencies**: Core runtime and test dependencies checked.
- **Console-script Availability & Identity**: Ensures `repo-catalog` is on `PATH`, executes `--help`, and verifies identity without fallback.
- **SQLite Capabilities**: Verifies SQLite >= 3.51.3 (measured native 3.53.1), source ID `2026-05-05 10:34:17 c88b2201...`, `STRICT` table support, `json_extract()` capability, WAL safety, and required PRAGMAs.
- **Isolated Test State**: Enforces and tests umask `0o022`.
- Outputs `artifacts/access-registry/preflight.json` and `runtime.json`.

### 5.2 Separation of Scoped Acceptance and Broad Regression Streams
In `.github/workflows/access-registry.yml`:
1. **Scoped Access Acceptance Receipt**:
   - Collects and executes ONLY the 939 Access acceptance test nodes:
     `tests/unit/test_access*_values.py`, `tests/unit/test_context_registration_values.py`, `tests/unit/test_native_acquisition_values.py`, `tests/integration/access`.
   - Results: **939 passed, 0 failures, 0 errors** in 84.32s.
   - `scripts/audit_access_acceptance.py` validates `tests.xml` against `collected.txt` and `access-a6-acceptance.json` with exit code 0.
2. **Broad Regression Receipt**:
   - Executes broad regression targets (1,847 test nodes across `i2`, `i23`, `i4`, `i5`, `p1`, `p2`, `p3`, `p4`, `p5`, `p6`, `p7`, `p5_p6_compatibility`).
   - Results: **1,645 passed, 182 failed, 20 errors** in 268.94s.
   - `scripts/compare_access_regressions.py` mechanically reconciles `regressions.xml` against baseline #154 manifest:
     - 72 resolved in broad regression suite (+25 in Access suite = 83 resolved overall)
     - 202 inherited non-successes (staged Transfer fences, unauthenticated admission, P7 recovery)
     - **0 new regressions** (strict check passes).

---

## 6. Outside-Checkout Distribution Verification

Distribution verification (`scripts/verify_access_distribution.py`) executed across two independent outside-checkout environments:
1. `wheel`: Built directly via `hatchling`.
2. `sdist-wheel`: Rebuilt from source distribution tarball without Git on `PATH`.

| Artifact Property | Direct Wheel | Sdist-derived Wheel | Status |
| :--- | :--- | :--- | :--- |
| **SHA-256** | `c3a147b2111e...` | `c3a147b2111e...` | **Identical (byte-for-byte)** |
| **Python Version** | 3.12.13 | 3.12.13 | Verified |
| **SQLite Version** | 3.53.1 | 3.53.1 | Verified |
| **Table Count** | 19 tables | 19 tables | Verified |
| **Installed Smoke** | Passed | Passed | Exit code 0 |
| **Cross-Seed & Query/Search** | Passed | Passed | Exit code 0 |

---

## 7. Non-Author Review Handoff

- **Target PR**: Targeting PR #163 branch `fix/adr0031-i6c-access-reconciliation-20261024`.
- **Reviewer Instructions**:
  1. Verify two-stage commit separation: Stage 1 commit `6287e5a5` contains all code/test/script/workflow changes; Stage 2 commit adds solely `docs/implementation/evidence/adr0031-i6c-access-verification-repair-20261024/`.
  2. Confirm `git diff 6287e5a5...HEAD -- src tests scripts pyproject.toml .github` is empty.
  3. Validate that `scripts/preflight_access.py` and `scripts/compare_access_regressions.py` pass linting and formatting.
  4. Note that 216 inherited non-successes remain visibly failing and staged outside scoped Access acceptance; full release readiness is neither claimed nor requested.
