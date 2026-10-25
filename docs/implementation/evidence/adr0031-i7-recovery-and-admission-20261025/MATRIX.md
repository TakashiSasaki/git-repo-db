# ADR 0031 I7 Recovery + Admission Regression Closure Traceability Matrix

| Requirement / Obligation | Lineage / Authority | Implementation Location | Test Verification Suite | Status |
|:---|:---|:---|:---|:---|
| **ADR 0031 I7 Recovery Coordinator Authority** | ADR 0031 (PR #176) | `src/repo_catalog/adapters/sqlite/recovery.py`, `src/repo_catalog/adapters/sqlite/context_admission.py` | `pytest tests/integration/p7/ -q` | PASS (259 tests) |
| **P7 Context Salvage Admission into Fresh Destination** | ADR 0031 (PR #176) | `src/repo_catalog/adapters/sqlite/recovery.py` (`_merge_salvage_request`) | `pytest tests/integration/p7/test_i7_recovery_adversarial.py` | PASS (14 formerly failing nodes resolved) |
| **G-R1 Stored Candidate Reconciliation & R17 Obligations** | ADR 0031 (PR #176) | `src/repo_catalog/adapters/sqlite/recovery_validation.py` | `tests/integration/p7/test_i7_recovery_adversarial.py` | PASS |
| **Native-I7 vs Reported-I8 Issue Support Eligibility (G3=A)** | ADR 0031 (PR #176) | `src/repo_catalog/application/recovery.py`, `src/repo_catalog/adapters/sqlite/recovery.py` | `tests/integration/p7/test_bounded_input.py`, `test_i7_recovery_adversarial.py` | PASS |
| **Durable Cumulative Work Budgets Across Retry & Continuation** | ADR 0031 (PR #176) | `src/repo_catalog/adapters/sqlite/recovery.py` (`SalvageBudgetTracker`) | `tests/integration/p7/test_bounded_input.py` | PASS |
| **Paired Core+Context Identity and Fresh Activation** | ADR 0031 (PR #176) | `src/repo_catalog/adapters/sqlite/recovery.py` | `tests/integration/p7/test_process_isolation.py` | PASS |
| **Read-Only Preservation of Suspect Source Database** | ADR 0031 (PR #176) | `src/repo_catalog/adapters/sqlite/recovery.py` (`_open_readonly_source`) | `tests/integration/p7/test_i7_recovery_adversarial.py` | PASS |
| **Workstream A: Explicit-Authorization Harness Repair (i2)** | ADR 0031 I6-C (PR #177) | `tests/integration/i2/test_provider_intake.py` | `pytest tests/integration/i2/` | PASS |
| **Workstream A: Explicit-Authorization Harness Repair (i23)** | ADR 0031 I6-C (PR #177) | `tests/integration/i23/test_provider_exchange.py` | `pytest tests/integration/i23/` | PASS |
| **Workstream A: Explicit-Authorization Harness Repair (i4)** | ADR 0031 I6-C (PR #177) | `tests/integration/i4/test_query_search_backup.py` | `pytest tests/integration/i4/` | PASS |
| **Workstream A: Explicit-Authorization Harness Repair (p1)** | ADR 0031 I6-C (PR #177) | `tests/integration/p1/test_generalized_resources.py` | `pytest tests/integration/p1/test_generalized_resources.py` | PASS |
| **Workstream A: Explicit-Authorization Harness Repair (p5 & p5_p6)** | ADR 0031 I6-C (PR #177) | `tests/integration/p5/`, `tests/integration/p5_p6_compatibility/` | `pytest tests/integration/p5/ tests/integration/p5_p6_compatibility/` | PASS |
| **Workstream A: Packaging Test Harness Repair** | ADR 0031 I6-C (PR #177) | `tests/packaging/test_p5_distribution.py` | `pytest tests/packaging/test_p5_distribution.py` | PASS |
| **Preservation of Ordinary Transfer Fences** | Repository Policy / ADR 0031 | `src/repo_catalog/adapters/sqlite/p1_ddl/context.sql`, `src/repo_catalog/domain/resource_stage.py` | `pytest tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_10_transfer_sql_fences_and_unsupported_resource_stage` | PASS (43/43 deliberate stage fences preserved) |
| **Scoped Broad Regression Reconciliation (1,851 Nodes)** | Acceptance Mandate | Baseline comparator `scripts/compare_access_regressions.py` | Scoped broad test execution | PASS (0 new regressions, 0 changed failures, 0 blocking violations) |
| **Minimal Product Sdist Contract & Budgets** | ADR 0033 | `scripts/check_sdist_contract.py` | `python scripts/check_sdist_contract.py --build` | PASS |
| **Distribution Verification Outside Checkout** | Release Hardening | `scripts/verify_access_distribution.py` | `python scripts/verify_access_distribution.py` | PASS (Wheel & sdist-wheel identical, exit code 0) |
| **Repository Code Formatting & Linting** | Repository Standards | `src/`, `tests/`, `scripts/` | `ruff check src tests scripts && ruff format --check src tests scripts` | PASS (462 files clean) |
