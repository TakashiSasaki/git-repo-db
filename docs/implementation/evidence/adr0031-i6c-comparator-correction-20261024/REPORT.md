# ADR 0031 I6-C Comparator Acceptance Semantics Correction Report

## 1. Executive Summary

- **Repository**: `https://github.com/TakashiSasaki/git-repo-db`
- **Phase**: Author correction of comparator acceptance semantics and strict failure signature verification
- **Branch**: `fix/adr0031-i6c-comparator-correction-20261024`
- **Target Base PR**: PR #168 (`https://github.com/TakashiSasaki/git-repo-db/pull/168`)
- **Target Base Branch**: `fix/adr0031-i6c-regression-hardening-20261024`
- **Target Base Commit**: `3a1f112331c87747249f38af370160adc0de108a` (PR #168 HEAD)
- **Tested Input Commit**: `61efe65e23be038cf97314e970b5b500e290ed0a`
- **Tested Input Tree**: `fa4d7d64692eadef79fd9f3423c71df659432df9`
- **Submission Status**: Author-complete (Draft PR targeting #168; no self-declared independent review acceptance)

This report supersedes `docs/implementation/evidence/adr0031-i6c-regression-hardening-20261024/REPORT.md`. All historical evidence directories and raw receipts remain preserved as committed. This document records the elimination of false acceptance shortcuts in `scripts/compare_access_regressions.py`, comprehensive regression unit testing in `tests/unit/test_compare_access_regressions.py`, and empirical re-evaluation of the broad regression suite against baseline #154.

---

## 2. Tested Input Separation & Two-Stage Protocol

In accordance with the repository's `author-correction-protocol` (Skill 3 & 4):
1. **Stage 1 (Tested Input)**:
   - All executable product code, script modifications, and test suite additions were committed in Stage 1 commit `61efe65e23be038cf97314e970b5b500e290ed0a` (Tree SHA: `fa4d7d64692eadef79fd9f3423c71df659432df9`).
   - Zero modifications to `src/`, `tests/`, `scripts/`, `pyproject.toml`, or `.github/` occur after this commit.
2. **Stage 2 (Evidence Generation)**:
   - The superseding evidence directory `docs/implementation/evidence/adr0031-i6c-comparator-correction-20261024/` was created, raw receipts copied from PR #168, comparator receipts generated, and provenance metadata computed.
   - Strict equivalence is verified: `git diff 61efe65e23be..HEAD -- src tests scripts pyproject.toml .github` is strictly empty.

| Property | Tested Input Commit / Tree | Final Submission Commit / Tree | Equivalence Proof |
| :--- | :--- | :--- | :--- |
| **Commit SHA** | `61efe65e23be038cf97314e970b5b500e290ed0a` | `HEAD` (Evidence commit stacked on top) | Product code, test definitions, scripts, and CI workflows are byte-for-byte identical. |
| **Tree SHA** | `fa4d7d64692eadef79fd9f3423c71df659432df9` | (Evidence-only delta) | `git diff 61efe65e...HEAD -- src tests scripts pyproject.toml .github` is empty. |
| **Executable Files** | Unchanged | Unchanged | Zero executable modifications were made after test execution. |

---

## 3. Flaws Identified, Counterexamples, and Comparator Hardening

Review of PR #168 identified that `scripts/compare_access_regressions.py` contained latent false acceptance shortcuts that permitted non-identical failure signatures to be falsely classified as unchanged inherited failures. Concrete executable counterexamples were codified in `tests/unit/test_compare_access_regressions.py` and hardened:

### 3.1 Counterexample A: Test Name Matching in Transfer Stage Fence
- **Defect**: `is_transfer_stage_fence` included `or "test_transfer_reports_never_shrunk_or_mixed" in info.get("name", "")`.
- **Symptom**: If baseline failed with `UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED` and current failed with an unrelated `AssertionError: assert 1 == 2`, `compare_failure_details` returned `("INHERITED_STAGE_TRANSFER", True, None)`.
- **Correction**: Removed test-name matching from `is_transfer_stage_fence`. Stage fences now strictly require explicit stage fence error markers (`i2_transfer_stage_fence`, `UnsupportedResourceStage`, `I2_TRANSFER_UNSUPPORTED`) AND compatible exception types (`UnsupportedResourceStage` or database trigger errors).
- **Unit Test**: `test_counterexample_a_transfer_stage_fence_requires_error_marker` verifies that unrelated `AssertionError` in `test_transfer_reports_never_shrunk_or_mixed` is rejected as `CHANGED_FAILURE`.

### 3.2 Counterexample B: Unknown Metadata Fallback (None == None)
- **Defect**: In `compare_failure_details`, the general fallback compared `b_info.get("refusal_code") == c_info.get("refusal_code") and b_info.get("reached_assertion") == c_info.get("reached_assertion")`.
- **Symptom**: If both baseline and current had unknown metadata (`refusal_code=None`, `reached_assertion=None`), `None == None` evaluated to `True`, classifying mismatched exception types (e.g. `ValueError` vs `TypeError`) as `("INHERITED_OTHER", True, None)`.
- **Correction**: Enforced that `exception_type` must be non-None and identical (`b_exc == c_exc`). Enforced that a concrete matching signature (`refusal_code` or `reached_assertion`) must exist on both sides. Rejected `None == None` unknown metadata fallback as `CHANGED_FAILURE`.
- **Unit Test**: `test_counterexample_b_unknown_metadata_fallback_rejected` and `test_general_fallback_unknown_metadata_none_none_rejected`.

### 3.3 Admission Refusal Code Equality & Category Shortcut Elimination
- **Defect**: `is_admission_refusal` accepted both `PERMISSION_DENIED` and `INVALID_IDENTIFICATION`, and `compare_failure_details` returned `("INHERITED_ADMISSION_PERMISSION_DENIED", True, None)` whenever both sides satisfied `is_admission_refusal`, without verifying that refusal codes were identical.
- **Symptom**: A test that transitioned from `PERMISSION_DENIED` to `INVALID_IDENTIFICATION` was falsely treated as an unchanged inherited failure.
- **Correction**: Enforced that both sides must have identical non-None refusal codes (`b_code == c_code and b_code is not None`). Explicitly classified refusal code mismatch (`PERMISSION_DENIED` vs `INVALID_IDENTIFICATION`) and exception type mismatch as `CHANGED_FAILURE`.
- **Unit Tests**: `test_admission_refusal_code_mismatch_rejected` and `test_admission_exception_type_mismatch_rejected`.

### 3.4 P7 Recovery Signature Hardening
- **Defect**: `is_p7_recovery` checked classname containing `"p7"`. If reached assertions differed and refusal codes were `None`, `None == None` matched.
- **Correction**: Required matching non-None refusal code or matching non-None reached assertion and compatible exception type (`AssertionError`). Classname containing `"p7"` alone without matching signature is classified as `CHANGED_FAILURE`.
- **Unit Tests**: `test_p7_recovery_classname_alone_without_matching_signature_rejected` and `test_p7_recovery_matching_signature_accepted`.

---

## 4. Test Suite Execution & Unit Conformance

### 4.1 Comparator Unit Test Suite
- **Command**: `pytest -q tests/unit/test_compare_access_regressions.py`
- **Results**: **23 passed in 0.88s** (100% pass).
- **Coverage**:
  - Counterexample A (test name matching rejected)
  - Counterexample B (unknown metadata None==None rejected)
  - Admission refusal code mismatch (`PERMISSION_DENIED` vs `INVALID_IDENTIFICATION`)
  - Admission exception type mismatch
  - Admission matching `PERMISSION_DENIED` accepted
  - P7 recovery classname alone rejected
  - P7 recovery matching signature accepted
  - General fallback None==None rejected
  - General fallback matching assertion accepted
  - General fallback assertion mismatch rejected
  - Unexpected skips rejected under `--strict`
  - Empty XML rejected under `--strict`
  - Added failing nodes rejected under `--strict`
  - Environment failures rejected under `--strict`
  - Missing expected nodes rejected under `--strict`
  - Unexpected nodes executed rejected under `--strict`
  - Duplicate record preservation & composite priority (`ERROR > FAIL > SKIP > PASS`)
  - Scoped baseline partitioning (in-scope vs out-of-scope)
  - Pytest exit code validation (rejecting codes 2, 3, 4, 5)

### 4.2 Full Repository Unit Test Suite
- **Command**: `pytest tests/unit/`
- **Results**: **1,558 passed in 54.08s** (100% pass, 0 failures, 0 errors).

### 4.3 Fast Runtime & Isolation Preflight
- **Command**: `python scripts/preflight_access.py`
- **Results**: **PASS in 0.25s**.
- **Verified Invariants**: Python 3.12.13, locked dependencies from `uv.lock` (`httpx` 0.28.1, `pytest` 9.1.1, `ruff` 0.16.10, `pytest-xdist` 3.8.0, `hatchling` 1.32.4, `jsonschema` 4.26.0), console-script shebang matching active interpreter, module origin resolving to repository source tree, SQLite 3.53.1 WAL and `STRICT` capabilities, and umask `0o022` enforcement.

---

## 5. Re-Comparison Against Baseline #154 Evidence

The corrected comparator was applied to the exact evidence from PR #168:
- `--current docs/implementation/evidence/adr0031-i6c-comparator-correction-20261024/raw/regressions.xml`
- `--baseline docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/source-full-final/ordinary.xml.gz`
- `--expected docs/implementation/evidence/adr0031-i6c-comparator-correction-20261024/raw/regression_collected.txt`
- `--pytest-exit-code 1`

### 5.1 Mechanical Comparison Results
| Metric | Value | Meaning |
| :--- | :--- | :--- |
| **Total Baseline Nodes** | 6,343 | Authoritative baseline #154 manifest |
| **In-Scope Baseline Nodes** | 1,847 | Expected nodes partition |
| **Out-of-Scope Baseline Nodes** | 4,496 | Preserved unexecuted (not deleted) |
| **Expected Test Nodes** | 1,847 | Pytest collection manifest |
| **Executed Test Nodes** | 1,847 | Exact match with expected manifest |
| **Missing Expected Nodes** | **0** | Complete execution |
| **Unexpected Nodes Executed** | **0** | No rogue tests |
| **Unexpected Skips** | **0** | No skipped test evasion |
| **New Product Regressions** | **0** | No passing tests broken |
| **Added Failures** | **0** | No failing new tests |
| **Environment Failures** | **0** | Clean execution environment |
| **Resolved Non-Successes** | **72** | Successfully remediated |
| **Inherited Unchanged Failures** | **201** | Genuinely identical failure signatures |
| **Changed Non-Successes** | **1** | Detected signature transition |
| **Pytest Exit Status** | `RECONCILED_FAILURES` | Exit code 1 reconciled against scoped receipt |
| **Strict Acceptance Verdict** | **REJECTED** | Blocked under `--strict` due to 1 changed failure |

### 5.2 Inherited Failure Signature Breakdown
- **`INHERITED_STAGE_TRANSFER`**: **43**
  - All 43 testcases contain genuine error content markers (`UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED`, `i2_transfer_stage_fence`, or trigger fences). None relied on test-name matching.
- **`INHERITED_P7_RECOVERY`**: **14**
  - All 14 testcases exhibit identical non-None reached assertions (`AssertionError`), identical refusal code (`PERMISSION_DENIED`), and identical exception types in both baseline and current runs.
- **`INHERITED_ADMISSION_PERMISSION_DENIED`**: **144**
  - All 144 testcases exhibit identical refusal code `PERMISSION_DENIED` with compatible admission refusal exception types (`AdmissionRefused`, `AdmissionFailure`, `AssertionError` with `AdmissionRefused` cause).

---

## 6. Root Cause and Reconciliation of Detected Changed Failure

### 6.1 The Detected Changed Failure Node
`tests.integration.p1.test_generalized_resources::test_selected_real_wire_without_identification_refuses_before_core_effects`

### 6.2 Empirical Signature Comparison
- **Baseline #154 Receipt**:
  - `status`: `FAIL` (phase: `call`)
  - `exception_type`: `AdmissionRefused`
  - `refusal_code`: `PERMISSION_DENIED`
  - `failure_point`: `tests/integration/p1/test_generalized_resources.py:411`
  - `failure_text`: `package = ExchangeService(a).export_package(selection=scope())` raised `repo_catalog.domain.context_admission.AdmissionRefused: PERMISSION_DENIED` because context export was unimplemented in baseline #154.
- **Current Receipt (`raw/regressions.xml`)**:
  - `status`: `FAIL` (phase: `call`)
  - `exception_type`: `ExchangeError`
  - `refusal_code`: `INVALID_IDENTIFICATION`
  - `failure_point`: `tests/integration/p1/test_generalized_resources.py:415`
  - `failure_text`: Line 411 context export succeeded. Line 415 `hostile = replace(package, context=data, digest_sha256=None)` invoked envelope row validation `ResourceIdentification.from_wire(row)`, which raised `ExchangeError: resources:INVALID_IDENTIFICATION` because `provider_resource_id='["global",[]]'` was invalid identity syntax.

### 6.3 Audit Finding
In PR #168, this node was reported as part of "145 unauthenticated admission `PERMISSION_DENIED`" because `is_admission_refusal` lumped both `PERMISSION_DENIED` and `INVALID_IDENTIFICATION` together without verifying refusal code equality.

Under the corrected strict comparator semantics:
- Refusal code changed: `PERMISSION_DENIED` -> `INVALID_IDENTIFICATION`
- Exception type changed: `AdmissionRefused` -> `ExchangeError`
- Failure location changed: line 411 -> line 415
- The comparator correctly classifies this node as **`CHANGED_FAILURE`**.
- Under `--strict`, the comparator correctly blocks and outputs:
  ```
  Strict comparison failed with 1 blocking violation(s):
   - 1 changed non-successes detected
  ```

This demonstrates that the hardened comparator functions exactly as designed: it completely eliminates false acceptance shortcuts and detects failure signature mutations that prior comparators concealed.

---

## 7. Non-Author Review Handoff & Open I6-C Obligations

In accordance with repository review policies and `author-correction-protocol/SKILL.md` Section 5:
- Authors **must not** declare an independent `PASS` on their own submissions.
- The findings verdict remains **`INCOMPLETE / PENDING_INDEPENDENT_REVIEW`**.

The open I6-C obligations remain preserved for independent non-Author behavioral verification:
1. **Empty receiver selection**: Verification that empty selection scope admits 0 items without failure.
2. **Same full sender package with receiver-side subset selection**: Verification that receiver-side filtering correctly admits the specified subset while omitting unrequested items.
3. **Real COMMIT revocation**: Verification that revocation during transaction execution raises `PERMISSION_DENIED` at the commit boundary.
4. **Foreign service-issued handles**: Verification that foreign UUIDs and mismatched credentials fail closed.
5. **Replay revocation**: Verification that subsequent replays of revoked authority fail closed.
