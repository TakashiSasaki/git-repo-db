# Independent Acceptance Review Report: PR #165 (Dataclass Selection-Budget Enforcement)

- **Review Phase**: Independent Acceptance Review (Non-Author)
- **Target PR**: PR #165 (`https://github.com/TakashiSasaki/git-repo-db/pull/165`)
- **Target Branch**: `fix/adr0031-i155-m01-dataclass-selection-20261024`
- **Frozen Reviewed HEAD SHA**: `d81951868ac4fc252f8c0f38c22cf2c38d6146d4`
- **Frozen Reviewed Tree SHA**: `f7eabd5623dba6d39183ce88d4d57e5852676e2e`
- **Base Commit**: `bebc039ed9772edf0737caf8f5520134907317e0` (PR #162)
- **Author Tested Input Commit**: `fbfd7a35b6f11befcf45e41eb52ba019f9dc28d2`
- **Author Tested Input Tree**: `08df9ffe3bfb2c98cc9f4196ff082c5c1024283e`
- **Environment**: Linux x86_64, Python 3.12.3, Native SQLite 3.45.1 (no version spoofing or matrix overrides)
- **Review Decision**: **SCOPED ACCEPTANCE (PASS)**
- **Release Readiness**: **BLOCKED ON INHERITED TRANSFER FENCE & SQLITE 3.51.3 BASELINE**

---

## 1. Git Object Identity Resolution & Executable Equivalence

### 1.1 Submission Commit SHA Reconciliation
The PR #165 description stated:
- `Final Submission Commit: d8195186f913d0859c258d4a9829285038ec10ea (Tree: f7eabd5623dba6d39183ce88d4d57e5852676e2e)`
whereas GitHub API and git remote refs returned:
- `headRefOid: d81951868ac4fc252f8c0f38c22cf2c38d6146d4`

**Independent Reconciliation**:
1. An inspection of git objects via `git cat-file -t` confirmed that `d81951868ac4fc252f8c0f38c22cf2c38d6146d4` is the genuine, valid Git commit object at `refs/heads/fix/adr0031-i155-m01-dataclass-selection-20261024` and `remotes/github/fix/adr0031-i155-m01-dataclass-selection-20261024`.
2. The hash string `d8195186f913d0859c258d4a9829285038ec10ea` does not exist as an object in the repository; it represents an inadvertent transcription/reporting discrepancy where the common prefix `d8195186` was shared.
3. Both the genuine commit object `d81951868ac4fc252f8c0f38c22cf2c38d6146d4` and the PR body claim reference the exact same tree SHA: `f7eabd5623dba6d39183ce88d4d57e5852676e2e`.

### 1.2 Two-Stage Commit Separation
- Tested Input commit: `fbfd7a35b6f11befcf45e41eb52ba019f9dc28d2` (Tree `08df9ffe3bfb2c98cc9f4196ff082c5c1024283e`).
- Submission commit: `d81951868ac4fc252f8c0f38c22cf2c38d6146d4` (Tree `f7eabd5623dba6d39183ce88d4d57e5852676e2e`).
- Executable equivalence: `git diff fbfd7a35...d8195186 -- src tests scripts pyproject.toml` is completely empty (0 bytes). All added changes between the tested-input commit and the submission commit are strictly non-executable documentation and evidence in `docs/implementation/evidence/adr0031-i155-m01-dataclass-selection-20261024/`.

---

## 2. Review Obligations & Verification Results

### Obligation 1: Genuine Service-Issued Context with 1,000-Field Dataclass
- **Target**: Genuine context issued by `ContextAdmissionService.context()` scanning a 1,000-field dataclass under `work_limit=10000` and `selection.max_work=7`.
- **Result**: **PASS**
- **Observed**:
  - `AdmissionRefused("INPUT_LIMIT")` raised immediately.
  - `used_work == 2` (1 for initial root object pop + 1 fixed contractual refusal fee).
  - Executed via `tests/unit/test_dataclass_selection_independent_acceptance.py::test_genuine_service_issued_context_1000_fields`.

### Obligation 2: Strict Refusal Prior to Field Access, Materialization, and Queue Extension
- **Target**: Ensure zero field attribute accesses, zero `members` list materialization, and queue bound to initial item.
- **Result**: **PASS**
- **Observed**:
  - Attribute accesses: `0` (not a single `f_{i}` getter was invoked).
  - Maximum `members` length: `0` (never initialized).
  - Maximum `pending` queue length: `1` (initial item).
  - Maximum `snapshot` length: `0`.

### Obligation 3: Budget vs. Selection Permutation Matrix
- **Target**: Comprehensive permutation matrix covering:
  1. Budget lower than selection (`work_limit=6, max_work=100` -> `INPUT_LIMIT`, `used_work=2`).
  2. Selection lower than budget (`max_work=6, work_limit=100` -> `INPUT_LIMIT`, `used_work=2`).
  3. Prior cumulative work (`prior=14, limit=20` -> `INPUT_LIMIT`, `used_work=16`).
  4. Pending siblings congestion (`pending=4 siblings, count=6, remaining=8` -> `len(pending)+count=10 > 8` -> `INPUT_LIMIT`, `used_work=3`).
  5. Exact boundary conditions (`budget=7, selection=7` -> `used_work=7` SUCCESS; `budget=6` -> `used_work=2` FAIL; `selection=6` -> `used_work=2` FAIL).
  6. Zero and exhausted capacity (`work_limit=0` -> `used_work=1`; `work_limit=1` -> `used_work=2`).
  7. Single refusal charging: no double-charging on refusal.
- **Result**: **PASS** (all 8 scenarios independently implemented and verified).

### Obligation 4: fields() Reflection Allocations and Custom Callback Behaviors
- **Target**: Containment of `fields()` reflection errors, arbitrary attribute getter exceptions, `AdmissionRefused` passthrough, and explicit distinction between exception containment and bounded arbitrary callback execution.
- **Result**: **PASS**
- **Observations**:
  - Reflection exceptions trapped fail-closed with `INPUT_LIMIT` and `used_work=2`.
  - Arbitrary attribute getter exceptions (e.g. `ValueError`) trapped fail-closed with `INPUT_LIMIT` and `used_work=2`.
  - Direct `AdmissionRefused` raised by a custom getter is passed through with `used_work=1` (no double-charging).
  - **Conceptual Distinction**: If arbitrary code executes inside a callback, it cannot be interrupted by the scanner during execution. The remediation provides safety because `reserve_children(count)` executes **before** any attribute getters are called; when capacity is exceeded, arbitrary getters (`BombDataclass`) are never executed.

### Obligation 5: Real-Store Counterexamples, Rollback, and Lease Cleanup
- **Target**: Real Store relation under `Context.owned_transaction` with mutating container, verifying rollback, 0 persistent rows, inactive transaction, and lease cleanup.
- **Result**: **PASS**
- **Observations**:
  - Store relation traversal refused with `INPUT_LIMIT`.
  - Persistent SQLite rows: `db_rows == 0` (clean rollback).
  - Transaction outcome: `db.in_transaction == False`.
  - Transfer SQL fence remains active (`has_transfer_fence(db) == True`).
  - Temporary lease directory freed on exit (`temp_path.exists() == False`).

### Obligation 6: Outside-Checkout Distribution Cohorts
- **Target**: Probes executed against source, direct installed wheel, and sdist-derived installed wheel in separate outside-checkout virtual environments.
- **Result**: **PASS**
- **Observations**:
  - All 3 cohorts executed from `/tmp/` outside checkout:
    1. `source`: `case_1000_refusal: INPUT_LIMIT, used_work: 2, accesses: 0, store_db_rows: 0, fence: true`
    2. `direct_wheel`: `case_1000_refusal: INPUT_LIMIT, used_work: 2, accesses: 0, store_db_rows: 0, fence: true`
    3. `derived_wheel`: `case_1000_refusal: INPUT_LIMIT, used_work: 2, accesses: 0, store_db_rows: 0, fence: true`
  - Bit-for-bit wheel equivalence: direct wheel SHA-256 and derived wheel SHA-256 are both `7dbbcfee566998e614cab97d5831c2ac941303b952c0d79183989c7d1d9c75c9` (`equal_full_zip_bytes: True`).

### Obligation 7: Minimal Sdist Contract & Transfer SQL Fences
- **Target**: Minimal sdist contract validation (`scripts/check_sdist_contract.py`) and transfer SQL fences.
- **Result**: **PASS**
- **Observations**:
  - Sdist compressed bytes: `703,090` (budget <= `2,097,152`).
  - Sdist unpacked bytes: `6,046,753` (budget <= `8,388,608`).
  - Sdist member count: `164` (budget <= `512`).
  - Transfer SQL fences verified in setup and post-rollback states.

### Obligation 8: Independent Audit of Focused and Broad Test Suites
- **Target**: Audit 37-pass focused claim and 670 PASS / 8 FAIL / 8 ERROR broad claim against raw evidence and node identities.
- **Result**: **PASS**
- **Observations**:
  - `tests/unit/test_admission_scanner_budget.py`: 37 passed in 47.10s.
  - Broad regression suite (`pytest tests/unit/test_context_*.py tests/unit/test_admission_*.py tests/unit/test_transfer_*.py`):
    - Collected: 686 items.
    - Result: **670 passed, 8 failed, 8 errors in 60.35s**.
    - Audited 8 errors in `test_context_coordinator_admission.py`: all 8 are `SchemaError: P1 requires SQLite >= 3.51.3` due to native environment SQLite 3.45.1.
    - Audited 2 failures in `test_context_fixture_authority.py`: both are `SchemaError: P1 requires SQLite >= 3.51.3` due to native environment SQLite 3.45.1.
    - Audited 6 failures in `test_context_fences_i6a.py`: coordinator/disk catalog capability profile.
    - Zero new regressions; all 16 non-successes are 100% identical to inherited baseline PR #162.

---

## 3. Scoped Scanner Acceptance vs. Release Readiness

- **Scoped Acceptance Decision**: **PASS**.
  The author correction in PR #165 (`d81951868ac4fc252f8c0f38c22cf2c38d6146d4`) fully and correctly remediates the dataclass selection-budget defect identified in PR #162. Bounded capacity enforcement is strictly verified before attribute access, members materialization, and queue extension across all cohorts.
- **Distinction from Release Readiness**:
  This acceptance applies strictly to the I155-M01 Admission Scanner remediation scope. It does **NOT** certify Release readiness, as the broader baseline contains 8 errors and 8 failures requiring SQLite >= 3.51.3 and Transfer adapter integration before main release deployment.

---

## 4. Execution Manifest & Evidence Hashes

| File | Relative Path | SHA-256 |
|---|---|---|
| Independent Acceptance Tests | `tests/unit/test_dataclass_selection_independent_acceptance.py` | `a1afc7ac2f5b4dc5f091d8d1fb4a0450fe542e0b2a5790caae053e24153a39da` |
| Distribution Script | `scripts/verify_dataclass_selection_distribution.py` | `50f5c41a19a748379e4840c7e96de2385e2c53578e4b5c119875fa5c436a3fad` |
| Review Findings | `docs/implementation/evidence/review-adr0031-i155-m01-dataclass-selection-20261024/findings.json` | `20265965f0faf8d5209d9cfabe0cbdf30e082d32be213d8814f4eb5f0bb9c5d1` |
| Sdist Contract Audit | `docs/implementation/evidence/review-adr0031-i155-m01-dataclass-selection-20261024/distribution/check-sdist-contract.json` | `f511d4c51489b348e16e1531c0e72b132f80d8af56259b94ee398095a7d1718e` |
| Wheel Comparison | `docs/implementation/evidence/review-adr0031-i155-m01-dataclass-selection-20261024/distribution/wheel-comparison.json` | `48b1e841833515523d88b106eeb7604cc042e7bd68bc8b494a63e46e5c1573c4` |
| Wheel Members | `docs/implementation/evidence/review-adr0031-i155-m01-dataclass-selection-20261024/distribution/wheel-members.json` | `d0657f0e90f03ae16054cfd479e9ad7d3c18bec4daddff6eaaddfe522d83a4f9` |
| Cohort Probes Evidence | `docs/implementation/evidence/review-adr0031-i155-m01-dataclass-selection-20261024/scanner/cohort-probes.json` | `f77af343ce4421d22f24c1dae5260672a164a1739f9d7f088159a8f7be730bd1` |
| Executions Evidence | `docs/implementation/evidence/review-adr0031-i155-m01-dataclass-selection-20261024/scanner/executions.json` | `700f9dd14f7e66663ec483acb62f8eaa3cc8e8f837c4f35cd09ab1f1293e22f0` |
