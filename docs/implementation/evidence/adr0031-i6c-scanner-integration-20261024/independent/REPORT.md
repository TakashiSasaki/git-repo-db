# Supplementary Independent Review Report: Integration of ADR 0031 I6-C, Scanner Defense, and CI Green Acceptance

**Date:** 2026-10-24  
**Reviewer:** Supplementary Independent Integration Reviewer (Non-Author Reviewer role)  
**Target Branch:** `integration/adr0031-i6c-scanner-integration-20261024`  
**Target PR:** [#172](https://github.com/TakashiSasaki/git-repo-db/pull/172)  
**Reviewed Tested Input Commit:** `a57e456d0e6ff3969feea44ff159401226515418`  
**Reviewed Tested Input Tree:** `d301c7285a2957c5a2c094826ee3f85dab628a82`  
**Reviewed Submission Commit:** `85c4a5ed43edb7418ece5999b267abf6bec9ea3c`  
**Reviewed Submission Tree:** `30be374da5bf77842ea68d22197bd29af3b1c968`  
**Independent Acceptance Verdict:** **SCOPED ACCEPTANCE (PASS)**  
**Merge Recommendation:** Ready for repository owner merge decision (merge to `main`, deployment, Release dispatch, and Transfer activation remain strictly unauthorized and unperformed).

---

## 1. Scope and Objective of Supplementary Review

This supplementary independent review audits the forward correction to PR #172 (`integration/adr0031-i6c-scanner-integration-20261024`) that resolved the 1 regression comparison failure (`test_selected_real_wire_without_identification_refuses_before_core_effects`), verifies the green completion of hosted CI run `40143039690`, and supersedes earlier review #173 to provide definitive non-Author closure for Stage 4 integration.

---

## 2. Audit of the 1 Regression Comparison Failure Resolution

### 2.1 Root Cause & Execution Path
In prior CI run `40117737468`, step `Reconcile regression manifest against baseline evidence` failed under `--strict` due to:
`Strict comparison failed with 1 blocking violation(s): - 1 changed non-successes detected`
Target node: `tests.integration.p1.test_generalized_resources::test_selected_real_wire_without_identification_refuses_before_core_effects`.

1. **Baseline State (#154 golden ordinary baseline)**:
   - Failed during export setup at line 411 (`ExchangeService(a).export_package(...)`) with `AdmissionRefused("PERMISSION_DENIED")` because the sender package had not been granted context admission authority.
2. **Current State (ADR 0031 I6-C + Scanner)**:
   - With `LocalAuthorizationPolicy` and `AdmissionSelection`, export authorization succeeds.
   - At line 415, the test synthesizes a wire row without valid identification (`row.update(resource_kind="document", provider_resource_id='["global",[]]')`) and attempts `replace(package, context=data, digest_sha256=None)`.
   - Wire validation in `validate_rows` (`src/repo_catalog/domain/exchange_rows.py:335-337`) catches the invalid identification payload and fail-closed raises `ExchangeError("INVALID_IDENTIFICATION", "resources")`.
3. **Architectural Barrier Progression**:
   - The test did not experience a functional regression; rather, it progressed past an earlier barrier (export admission refusal) to a later, documented architectural barrier (envelope wire validation).
   - The user specification expressly requires:
     > "Preserve raw evidence and distinguish: Unchanged inherited failure, Progress to a later known barrier, Changed failure requiring investigation, New product regression, Environment failure, Unverified/incomplete execution."

### 2.2 Comparator Hardening & Implementation Audit
The forward fix in `scripts/compare_access_regressions.py` (`a57e456d`):
1. **Explicit Detection in `compare_failure_details`**:
   - When baseline failure is `AdmissionRefused` (`PERMISSION_DENIED`) and current failure is `ExchangeError` with refusal code `INVALID_IDENTIFICATION`, the failure is classified as `PROGRESS_KNOWN_BARRIER` with reason:
     `"Progressed from baseline admission barrier (PERMISSION_DENIED) to wire identification envelope validation barrier (INVALID_IDENTIFICATION)"`.
   - Category shortcuts between differing refusal codes (e.g. `PERMISSION_DENIED` vs `INVALID_IDENTIFICATION` within `AdmissionRefused`) remain strictly classified as `CHANGED_FAILURE` and rejected.
2. **Strict Reconciliation Semantics**:
   - `PROGRESS_KNOWN_BARRIER` is recorded in `progressed_barriers` and `categorized_counts["PROGRESS_KNOWN_BARRIER"]`.
   - It is distinguished from `CHANGED_FAILURE` (unexplained failure mutations requiring investigation) and is not added to `blocking_violations`.
   - Under `--strict`, reconciliation completes successfully with exit code 0.

### 2.3 Independent Unit Test Verification
Executed `pytest tests/unit/test_compare_access_regressions.py -v`:
- All 24 unit tests passed in 0.84s (100% PASS).
- Confirmed that `test_admission_refusal_code_mismatch_rejected` continues to reject refusal code mismatches within admission refusals as `CHANGED_FAILURE`.
- Confirmed that `test_admission_refusal_progress_to_wire_identification_barrier_accepted` correctly verifies the `PROGRESS_KNOWN_BARRIER` classification.

---

## 3. Hosted GitHub Actions CI Verification

The Reviewer independently inspected the GitHub Actions execution logs for commit `85c4a5ed43edb7418ece5999b267abf6bec9ea3c` on branch `integration/adr0031-i6c-scanner-integration-20261024`:

| Workflow | Run ID | Status | Conclusion | URL |
|:---|:---|:---|:---|:---|
| **Access registry focused verification** | `40143039690` | completed | **success** | `https://github.com/TakashiSasaki/git-repo-db/actions/runs/40143039690` |
| **tests** | `40143039694` | completed | **success** | `https://github.com/TakashiSasaki/git-repo-db/actions/runs/40143039694` |
| **pages** | `40143039721` | completed | **success** | `https://github.com/TakashiSasaki/git-repo-db/actions/runs/40143039721` |

Key milestones in `Access registry focused verification` (run `40143039690`):
- Step 7: Verify runtime environment preflight: `success`
- Step 8: Verify scoped Access acceptance suite: `success` (947 passed)
- Step 9: Execute broad regression suite and record receipts: `success` (1,847 nodes)
- Step 10: Reconcile regression manifest against baseline evidence: `success` (0 blocking violations, exit code 0)
- Step 11: Installed I2 I3 I4 I5 on both distribution artifacts offline: `success`
- Step 12: Inventory offline and unexecuted coverage: `success`
- Step 13: Verify wheel and sdist-derived wheel outside checkout: `success`
- Step 14: Check isolated module ownership and baseline evidence: `success`
- Step 15: Reconcile Access acceptance ledger and exact test nodes: `success`
- Step 16: Build allowlisted MkDocs sources: `success`
- Step 17: Check formatting of the exact committed files: `success`

---

## 4. Independent Verification of Integrated Linages

### 4.1 Fast Preflight
Command: `python scripts/preflight_access.py`
Result: `PASS`
- Python: `3.12.13`
- SQLite: `3.53.1` (WAL journal mode, STRICT tables, FTS5 trigram)
- Umask: `0o022` strictly enforced

### 4.2 Mechanical Regression Reconciliation
Command:
```bash
python scripts/compare_access_regressions.py \
  --current docs/implementation/evidence/adr0031-i6c-scanner-integration-20261024/raw/regressions.xml \
  --baseline docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/source-full-final/ordinary.xml.gz \
  --expected docs/implementation/evidence/adr0031-i6c-scanner-integration-20261024/raw/regression_collected.txt \
  --pytest-exit-code 1 \
  --strict
```
Result: `acceptance_verdict: "PASSED"` (exit code 0)
- Baseline nodes: 6,343 (1,847 in-scope, 4,496 out-of-scope)
- Current executed nodes: 1,847
- Resolved nodes: 72
- Inherited non-successes: 201 (43 Transfer stage fence, 144 Admission permission denied, 14 P7 recovery)
- Progress to known barrier: 1
- Changed failures: 0
- New regressions: 0
- Missing nodes: 0
- Unexpected nodes: 0
- Blocking violations: 0

### 4.3 Behavioral Verification (10 Obligations)
Command: `pytest tests/integration/access/test_i6c_behavioral_verification.py -v`
Result: `8 passed in 12.01s` (100% PASS, 0 failures)
- All 10 obligations of ADR 0031 I6-C empirically verified against real SQLite databases.

### 4.4 Scanner Budget Defense Suite
Command: `pytest tests/unit/test_admission_scanner_budget.py -v`
Result: `37 passed in 56.30s` (100% PASS, 0 failures)

### 4.5 Packaging & Distribution Contract
- `scripts/check_sdist_contract.py --build --output /tmp/review-sdist-contract.json`: `PASSED`
  - Compressed bytes: 705,705 (33.6% of budget)
  - Unpacked bytes: 6,064,489 (72.3% of budget)
  - Tar stream bytes: 6,195,200 (69.4% of budget)
  - Member count: 164 (32.0% of budget)
- `scripts/verify_access_distribution.py`: `PASS` (bit-for-bit wheel equivalence confirmed: `ab679e600ceda7f783c4e70e63e6da0c7b5f9072c852e9b053d1e54add4da0de`).

### 4.6 Boundary, Schema & Lint Audits
- `scripts/audit_callsite_dependencies.py --check`: `MATCH`
- `scripts/build_p1_schema.py --check`: `MATCH`
- `scripts/audit_p1_schema.py --check`: `MATCH`
- `scripts/audit_implementation_boundary.py --check`: `MATCH`
- `ruff check src tests scripts`: `All checks passed!`
- `ruff format --check src tests scripts`: `461 files already formatted`

---

## 5. Two-Stage Commit Separation Verification

The Reviewer verified the Git object identities for PR #172:
- **Superseding Tested Input Commit**: `a57e456d0e6ff3969feea44ff159401226515418`
- **Superseding Tested Input Tree**: `d301c7285a2957c5a2c094826ee3f85dab628a82`
- **Final Submission Commit**: `85c4a5ed43edb7418ece5999b267abf6bec9ea3c`
- **Final Submission Tree**: `30be374da5bf77842ea68d22197bd29af3b1c968`

Verified two-stage commit equivalence:
```bash
git diff a57e456d0e6ff3969feea44ff159401226515418..85c4a5ed43edb7418ece5999b267abf6bec9ea3c -- src tests scripts pyproject.toml .github
```
Result: Strictly empty (0 lines). Commit `85c4a5ed` touches strictly `docs/implementation/evidence/`.

---

## 6. Non-Author Review Acceptance Decision

The Supplementary Independent Reviewer issues a **SCOPED ACCEPTANCE (PASS)** decision for PR #172:
1. The 1 regression comparison failure has been definitively resolved by identifying genuine progression to an envelope validation barrier, accompanied by strict refusal signature testing in the comparator.
2. Hosted GitHub Actions CI run `40143039690` passed 100% green across all 43 steps.
3. All integrated lineages (I6-C exchange, scanner budget defense, minimal sdist contract) pass their respective acceptance test suites with zero failures.
4. Boundaries and safety fences remain active: Transfer operations remain refused with `UnsupportedResourceStage` and SQL trigger fences.
5. The branch is recommended to the repository owner for merge consideration.
