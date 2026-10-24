# Supplementary Review Traceability Matrix

| Requirement / Obligation | Target Test Function / Command | Verification Verdict | Notes |
|:---|:---|:---|:---|
| **Progression Barrier Semantics** | `tests/unit/test_compare_access_regressions.py::test_admission_refusal_progress_to_wire_identification_barrier_accepted` | **PASS** | Distinguishes known barrier progression from changed failures |
| **Strict Category Mismatch** | `tests/unit/test_compare_access_regressions.py::test_admission_refusal_code_mismatch_rejected` | **PASS** | Rejects refusal code mismatches within admission refusals |
| **Mechanical Manifest Reconciliation** | `scripts/compare_access_regressions.py ... --strict` | **PASS** | `acceptance_verdict: "PASSED"`, 0 blocking violations |
| **CI Stream 1: Scoped Acceptance** | Workflow `Access registry focused verification` (step 8) | **PASS** | 947 passed, 0 failures, 0 errors |
| **CI Stream 2: Broad Regressions** | Workflow `Access registry focused verification` (step 9-10) | **PASS** | 1,847 nodes reconciled under `--strict` (exit code 0) |
| **CI Hosted Execution** | GitHub Actions Run `40143039690` | **PASS** | All 43 steps completed with `success` |
| **ADR 0031 Obligation 1-3 (Rowsets)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_1_2_3_single_package_receiver_selections_and_rowsets` | **PASS** | Direct SQLite table assertions |
| **ADR 0031 Obligation 4 (Imports)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_4_context_only_and_paired_import_paths` | **PASS** | Context-only and paired Core+Context paths verified |
| **ADR 0031 Obligation 5 (Foreign Handle)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_5_foreign_authorization_handle_rejected` | **PASS** | Fail-closed foreign service handle rejection |
| **ADR 0031 Obligation 6 (Revocation)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_6_permission_revocation_at_commit_boundaries` | **PASS** | Boundary revocation at commit boundaries |
| **ADR 0031 Obligation 7 (Replay)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_7_exact_replay_and_cached_receipt_revocation` | **PASS** | Idempotent replay control verified |
| **ADR 0031 Obligation 8 (Permissions)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_8_independent_source_mapping_claim_and_disposition_permissions` | **PASS** | Independent Source, MappingClaim, Disposition checks |
| **ADR 0031 Obligation 9 (Core Failure)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_9_paired_core_first_failure_and_operational_recovery_state` | **PASS** | Core durability and operational state tracking |
| **ADR 0031 Obligation 10 (Fences)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_10_transfer_sql_fences_and_unsupported_resource_stage` | **PASS** | SQL fences & `UnsupportedResourceStage` active |
| **Scanner Dataclass Budget Defense** | `tests/unit/test_admission_scanner_budget.py` | **PASS** | 37 tests passing |
| **Minimal Sdist Contract (ADR 0033)** | `scripts/check_sdist_contract.py --build` | **PASS** | All 4 budgets satisfied (32-72% utilization) |
| **Distribution Smoke Outside-Checkout** | `scripts/verify_access_distribution.py` | **PASS** | Bit-for-bit wheel equivalence and isolated runtime smoke |
