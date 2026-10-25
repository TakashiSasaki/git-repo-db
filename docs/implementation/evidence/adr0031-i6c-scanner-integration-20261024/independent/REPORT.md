# Supplementary Independent Review Report: Verification of PR #172 Acceptance Correction

**Date:** 2026-10-25  
**Reviewer:** Supplementary Independent Reviewer (strictly Non-Author Reviewer role)  
**Target Branch:** `integration/adr0031-i6c-scanner-integration-20261024`  
**Target PR:** [#172](https://github.com/TakashiSasaki/git-repo-db/pull/172)  
**Target Submission Commit:** `a700676b317e60566f2925222b6cbc5582a525ef`  
**Target Tested Input Commit:** `91d2bc7e6c47a3c1ec46949211ab16cb4ac7900f`  
**Review Branch:** `review/adr0031-i6c-scanner-integration-followup-20261024`  
**Review PR:** [#174](https://github.com/TakashiSasaki/git-repo-db/pull/174)  
**Decision:** **NON-AUTHOR INDEPENDENT ACCEPTANCE (PASS)**  
**Merge Recommendation:** Ready for repository owner merge decision (merge to `main`, deployment, Release dispatch, and Transfer activation remain strictly unauthorized and unperformed).

---

## 1. Explicit Supersession Statement

This supplementary independent review **explicitly supersedes the earlier conclusions of PR #174 regarding `PROGRESS_KNOWN_BARRIER`**, while preserving historical audit evidence.

### Background and Prior State
In the initial review under PR #174, `test_selected_real_wire_without_identification_refuses_before_core_effects` was treated as an unreached test progressing from an admission permission barrier (`AdmissionRefused("PERMISSION_DENIED")`) to an envelope validation barrier (`ExchangeError("INVALID_IDENTIFICATION")`). Under comparator commit `a57e456d`, this transition was accepted under the classification `PROGRESS_KNOWN_BARRIER`.

### Acceptance Correction & Contract Resolution
The Author has now fully resolved the underlying behavioral contract and hardened the comparator semantics:
1. **Passing Behavioral Contract**:
   In `src/repo_catalog/domain/exchange_rows.py` and `src/repo_catalog/application/exchange.py`, staged identification for paired packages (`core is not None`) is deferred to preflight (`preflight_i2_resources`), enabling Core-only selection (`selection=scope(include_context=False)`) to succeed cleanly without failing on context wire validation. When Context is selected (`want_context == True`), `preflight_i2_context` executes before `validate_context`, raising `UnsupportedIdentificationStage`. Standalone context wires (`core is None`) continue to strictly enforce wire identification validation.
   As a direct result, `test_selected_real_wire_without_identification_refuses_before_core_effects` now **PASSES 100% as an executable behavioral test** without skipping or weakened assertions. In mechanical regression comparison, it transitions to **`RESOLVED`** (73 total resolved nodes), rendering `PROGRESS_KNOWN_BARRIER` count **0**.
2. **Comparator Hardening & Counterexample Rejection**:
   In `scripts/compare_access_regressions.py` (lines 352-376), `PROGRESS_KNOWN_BARRIER` is strictly constrained:
   - Constrained strictly to `target_node == "tests.integration.p1.test_generalized_resources::test_selected_real_wire_without_identification_refuses_before_core_effects"`.
   - Requires exact baseline signature: `b_exc == "AdmissionRefused"` and `b_code == "PERMISSION_DENIED"`.
   - Requires exact current signature: `c_exc == "ExchangeError"` and `c_code == "INVALID_IDENTIFICATION"` (exact equality, NO assertion text substring inference).
   - Rejection of Counterexample 1 (`test_counterexample1_baseline_invalid_identification_rejected`): Baseline `INVALID_IDENTIFICATION` transitioning to Current `INVALID_IDENTIFICATION` is rejected as `CHANGED_FAILURE`.
   - Rejection of Counterexample 2 (`test_counterexample2_assertion_error_with_substring_rejected`): Current `AssertionError` with substring match is rejected as `CHANGED_FAILURE`.
   - Rejection of unreviewed nodes (`test_progress_known_barrier_unreviewed_node_rejected`): Unreviewed nodes are rejected as `CHANGED_FAILURE`.

---

## 2. Independent Audit & Verification Receipts

### 2.1 Fast Preflight
- **Command:** `.venv/bin/python scripts/preflight_access.py`
- **Verdict:** `PASS`
- **Environment:** Python `3.12.13`, SQLite `3.53.1` (WAL journal mode, STRICT tables, FTS5 trigram), umask `0o022` enforced.

### 2.2 Hardened Comparator Unit Tests
- **Command:** `.venv/bin/python -m pytest tests/unit/test_compare_access_regressions.py -v`
- **Verdict:** `27 passed in 0.92s` (100% PASS)
- **Key Tests Verified:**
  - `test_counterexample1_baseline_invalid_identification_rejected`: PASSED
  - `test_counterexample2_assertion_error_with_substring_rejected`: PASSED
  - `test_progress_known_barrier_unreviewed_node_rejected`: PASSED
  - `test_admission_refusal_code_mismatch_rejected`: PASSED
  - `test_admission_exception_type_mismatch_rejected`: PASSED

### 2.3 Passing Behavioral Contract
- **Command:** `.venv/bin/python -m pytest tests/integration/p1/test_generalized_resources.py -k test_selected_real_wire_without_identification_refuses_before_core_effects -v`
- **Verdict:** `1 passed, 69 deselected in 2.32s` (100% PASS)
- **Verification:** Test executes real SQLite fixtures, asserts `UnsupportedIdentificationStage` before core effects, confirms pristine authorities and empty context resources, and verifies successful independent Core admission on replay with `selection=scope(include_context=False)`.
- **Command:** `.venv/bin/python -m pytest tests/integration/access/test_i6c_behavioral_verification.py -v`
- **Verdict:** `8 passed in 12.54s` (100% PASS, all 10 obligations verified against real databases).

### 2.4 Mechanical Regression Reconciliation
- **Command:**
  ```bash
  .venv/bin/python scripts/compare_access_regressions.py \
    --current docs/implementation/evidence/adr0031-i6c-scanner-integration-20261024/raw/regressions.xml \
    --baseline docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/source-full-final/ordinary.xml.gz \
    --expected docs/implementation/evidence/adr0031-i6c-scanner-integration-20261024/raw/regression_collected.txt \
    --pytest-exit-code 1 \
    --output /tmp/review-failure-comparison.json \
    --strict
  ```
- **Reconciliation Verdict:** `acceptance_verdict: "PASSED"` (0 blocking violations, exit code 0)
- **Manifest Metrics:**
  - Baseline nodes: 6,343 (1,847 in-scope, 4,496 out-of-scope)
  - Current executed nodes: 1,847 (expected: 1,847, missing: 0, unexpected: 0)
  - Resolved nodes: 73 (includes `test_selected_real_wire_without_identification_refuses_before_core_effects`)
  - Inherited non-successes: 201 (43 Transfer stage fence, 144 Admission permission denied, 14 P7 recovery)
  - Progress to known barrier: 0
  - Changed failures: 0
  - New regressions: 0
  - Added failures: 0
  - Environment failures: 0

### 2.5 Distribution and Packaging Outside Checkout
- **Command:** `.venv/bin/python scripts/verify_access_distribution.py`
- **Verdict:** `PASS` (exit code 0)
- **Artifacts Verified:**
  - Direct built wheel SHA-256: `974366bd21726931bba05958c102ec1a9128845fc4728595346d2bf2b727a1f7`
  - Rebuilt wheel from sdist SHA-256: `974366bd21726931bba05958c102ec1a9128845fc4728595346d2bf2b727a1f7`
  - Bit-for-bit equivalence: 100% match.
  - Isolated venv smoke (wheel and sdist-wheel): PASSED.

### 2.6 Hosted GitHub Actions CI Verification
The Reviewer inspected hosted GitHub Actions runs triggered by submission commit `a700676b317e60566f2925222b6cbc5582a525ef` on PR #172:

| Workflow | Run ID | Status | Conclusion | Duration |
|:---|:---|:---|:---|:---|
| **Access registry focused verification** | `40147504587` | completed | **success** | 7m 6s |
| **tests** | `40147504588` | completed | **success** | 29s |
| **pages** | `40147504592` | completed | **success** | 1m 9s |

Key steps in Run `40147504587`:
- Step 7: Verify runtime environment preflight: `success`
- Step 8: Verify scoped Access acceptance suite: `success` (947 passed)
- Step 9: Execute broad regression suite and record receipts: `success` (1,847 nodes)
- Step 10: Reconcile regression manifest against baseline evidence: `success` (0 blocking violations)
- Step 11: Installed I2 I3 I4 I5 on both distribution artifacts offline: `success`
- Step 12: Inventory offline and unexecuted coverage: `success`
- Step 13: Verify wheel and sdist-derived wheel outside checkout: `success`
- Step 14: Check isolated module ownership and baseline evidence: `success`
- Step 15: Reconcile Access acceptance ledger and exact test nodes: `success`
- Step 16: Build allowlisted MkDocs sources with placeholder diagrams, no deployment: `success`
- Step 17: Check formatting of the exact committed files: `success`

---

## 3. Two-Stage Commit Separation Audit

The Reviewer audited the Git object identities for PR #172:
- **Tested Input Commit**: `91d2bc7e6c47a3c1ec46949211ab16cb4ac7900f`
- **Tested Input Tree**: `d35ca8d7212bddd9aa6ad1646d43a3fe062d619e`
- **Submission Commit**: `a700676b317e60566f2925222b6cbc5582a525ef`
- **Submission Tree**: `3f191b7d3f82cb34220b330ec02882a88dc18042`

Verification command:
```bash
git diff 91d2bc7e6c47a3c1ec46949211ab16cb4ac7900f..a700676b317e60566f2925222b6cbc5582a525ef -- src tests scripts pyproject.toml .github
```
Result: Strictly empty (0 lines). The submission commit touches only files under `docs/implementation/evidence/`.

---

## 4. Final Review Decision

The Supplementary Independent Reviewer issues **NON-AUTHOR INDEPENDENT ACCEPTANCE (PASS)**:
1. **Resolution of Contract**: The wire identification behavioral contract is cleanly resolved, with `test_selected_real_wire_without_identification_refuses_before_core_effects` verified passing locally and on hosted CI.
2. **Comparator Hardening**: Progression semantics in `scripts/compare_access_regressions.py` are strictly bounded to the reviewed test, require exact refusal codes, reject Counterexamples 1 & 2, and reject unreviewed nodes.
3. **Reconciliation Zero Defect**: 73 resolved, 201 inherited non-successes, 0 progressed barriers, 0 changed failures, 0 new regressions, 0 blocking violations under `--strict`.
4. **All CI Checks Green**: Hosted runs `40147504587`, `40147504588`, and `40147504592` completed with `success`.
5. **Two-Stage Commit Invariant**: Strictly observed between `91d2bc7e` and `a700676b`.
6. **Fences Preserved**: Transfer SQL fences and `UnsupportedResourceStage` remain fully active.
