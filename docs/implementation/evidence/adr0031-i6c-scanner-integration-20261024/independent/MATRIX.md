# Supplementary Review Traceability Matrix

| Requirement / Obligation | Target Test Function / Command | Verification Verdict | Notes |
|:---|:---|:---|:---|
| **Passing Behavioral Contract (Wire ID)** | `tests/integration/p1/test_generalized_resources.py::test_selected_real_wire_without_identification_refuses_before_core_effects` | **PASS** | Resolves wire envelope contract: Core selection succeeds, Context selection raises `UnsupportedIdentificationStage` before core effects |
| **Comparator Counterexample 1 Rejection** | `tests/unit/test_compare_access_regressions.py::test_counterexample1_baseline_invalid_identification_rejected` | **PASS** | Baseline `INVALID_IDENTIFICATION` transitioning to Current `INVALID_IDENTIFICATION` rejected as `CHANGED_FAILURE` |
| **Comparator Counterexample 2 Rejection** | `tests/unit/test_compare_access_regressions.py::test_counterexample2_assertion_error_with_substring_rejected` | **PASS** | Assertion text substring inference prohibited, rejected as `CHANGED_FAILURE` |
| **Unreviewed Node Barrier Rejection** | `tests/unit/test_compare_access_regressions.py::test_progress_known_barrier_unreviewed_node_rejected` | **PASS** | Progression barrier strictly constrained to verified target node |
| **Mechanical Manifest Reconciliation** | `scripts/compare_access_regressions.py ... --strict` | **PASS** | `acceptance_verdict: "PASSED"`, 73 resolved, 201 inherited, 0 progressed barriers, 0 blocking violations |
| **CI Stream 1: Scoped Acceptance** | Workflow `Access registry focused verification` (step 8) | **PASS** | 947 passed, 0 failures, 0 errors |
| **CI Stream 2: Broad Regressions** | Workflow `Access registry focused verification` (step 9-10) | **PASS** | 1,847 nodes reconciled under `--strict` (exit code 0) |
| **CI Hosted Execution (Commit `a700676b`)** | GitHub Actions Run `40147504587` | **PASS** | All 43 steps completed with `success` (7m6s) |
| **ADR 0031 Obligation 1-3 (Rowsets)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_1_2_3_single_package_receiver_selections_and_rowsets` | **PASS** | Direct SQLite table assertions |
| **ADR 0031 Obligation 4 (Imports)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_4_context_only_and_paired_import_paths` | **PASS** | Context-only and paired Core+Context paths verified |
| **ADR 0031 Obligation 5 (Foreign Handle)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_5_foreign_authorization_handle_rejected` | **PASS** | Fail-closed foreign service handle rejection |
| **ADR 0031 Obligation 6 (Revocation)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_6_permission_revocation_at_commit_boundaries` | **PASS** | Boundary revocation at commit boundaries |
| **ADR 0031 Obligation 7 (Replay)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_7_exact_replay_and_cached_receipt_revocation` | **PASS** | Idempotent replay control verified |
| **ADR 0031 Obligation 8 (Permissions)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_8_independent_source_mapping_claim_and_disposition_permissions` | **PASS** | Independent Source, MappingClaim, Disposition checks |
| **ADR 0031 Obligation 9 (Core Failure)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_9_paired_core_first_failure_and_operational_recovery_state` | **PASS** | Core durability and operational state tracking |
| **ADR 0031 Obligation 10 (Fences)** | `tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_10_transfer_sql_fences_and_unsupported_resource_stage` | **PASS** | SQL fences & `UnsupportedResourceStage` active |
| **Distribution Outside-Checkout** | `scripts/verify_access_distribution.py` | **PASS** | Bit-for-bit wheel equivalence (`974366bd21726931bba05958c102ec1a9128845fc4728595346d2bf2b727a1f7`) and isolated runtime smoke |
| **Two-Stage Commit Invariant** | `git diff 91d2bc7e..a700676b -- src tests scripts pyproject.toml .github` | **PASS** | Strictly empty (0 lines diff outside evidence directory) |
