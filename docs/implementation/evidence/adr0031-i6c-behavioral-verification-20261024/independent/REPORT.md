# Independent Behavioral Verification Report: ADR 0031 I6-C Obligations (Stage 2)

## Review Metadata
- **Review Target**: PR #168 (`fix/adr0031-i6c-regression-hardening-20261024`)
- **Target HEAD SHA**: `3a1f112331c87747249f38af370160adc0de108a`
- **Review Branch**: `review/adr0031-i6c-behavioral-verification-20261024`
- **Review Role**: Independent Non-Author Reviewer (Stage 2)
- **Suite**: `tests/integration/access/test_i6c_behavioral_verification.py`
- **Suite Metrics**: 8 passed in 12.04s (`ruff check` clean, `ruff format` clean)
- **Decision**: **ACCEPTANCE (PASS)**

---

## Executive Summary

Stage 2 independent behavioral verification was executed to close all coverage and verification gaps identified in earlier review #164. Using real public application and domain APIs (`ExchangeService`, `PairedAcquisitionCoordinator`, `ProviderAcquisition`, `Context`, `GitCore`, `create_local_admission_service`) and native SQLite persistent-state inspections across `core.sqlite3`, `context.sqlite3`, and `operational.sqlite3`, all 10 obligations have been conclusively verified.

Zero regressions or blocking issues were discovered. All 10 obligations are marked **PASS**.

---

## Obligation Decision Table

| Obligation | Description | Decision | Test Node |
|---|---|:---:|---|
| **1** | Single sender package & receiver-local finite grants (`DependencySet` without sender authority) | **PASS** | `test_obligation_1_2_3_single_package_receiver_selections_and_rowsets` |
| **2** | Empty, strict-subset, and complete receiver selection on that same package | **PASS** | `test_obligation_1_2_3_single_package_receiver_selections_and_rowsets` |
| **3** | Exact admitted/omitted SQLite rowsets and accepted atomic-unit semantics | **PASS** | `test_obligation_1_2_3_single_package_receiver_selections_and_rowsets` |
| **4** | Both Context-only (`ExchangeService.import_package`) and paired Core+Context (`PairedAcquisitionCoordinator`) paths | **PASS** | `test_obligation_4_context_only_and_paired_import_paths` |
| **5** | Genuine handle issued by foreign authorization service passed into product routes fails closed | **PASS** | `test_obligation_5_foreign_authorization_handle_rejected` |
| **6** | Permission revocation triggered at actual transaction/COMMIT boundaries | **PASS** | `test_obligation_6_permission_revocation_at_commit_boundaries` |
| **7** | Exact replay and cached receipt behavior after revocation (fail-closed receipt invariants) | **PASS** | `test_obligation_7_exact_replay_and_cached_receipt_revocation` |
| **8** | Source, MappingClaim, and Disposition permissions verified independently with withholding tests | **PASS** | `test_obligation_8_independent_source_mapping_claim_and_disposition_permissions` |
| **9** | Paired Provider acquisition and Core-first failure/recovery bookkeeping (Core durable, Context rolled back, Operational state tracked) | **PASS** | `test_obligation_9_paired_core_first_failure_and_operational_recovery_state` |
| **10** | Retention of both Transfer SQL fences (`i2_transfer_stage_fence`, `i2_transfer_report_stage_fence`) and ordinary refusal with `UnsupportedResourceStage` | **PASS** | `test_obligation_10_transfer_sql_fences_and_unsupported_resource_stage` |

---

## Detailed Obligation Analysis

### Obligation 1: Single Sender Package & Independent Receiver-Local Finite Grants
- **Requirement**: Sender package must not be pre-narrowed to mimic receiver selection. Receiver must independently construct finite grants without ambient sender authority.
- **Verification Evidence**:
  - Sender exports a single full package (`full_pkg`) containing 2 repositories (`repo_a`, `repo_b`), 1 source (`source_1`), 4 resources (`r_repo`, `res_a1`, `res_a2`, `res_b1`), 1 mapping claim (`claim_rep`), 1 disposition (`disp_rep`), and 1 resource relation (`rel_a1_a2`).
  - Receiver builds its own local `DependencySet` without reading or inheriting sender grants.
  - Result: **PASS**

### Obligation 2 & 3: Receiver Selection & Exact SQLite Rowsets & Atomic Units
- **Requirement**: Exercise empty, strict-subset, and complete receiver selection on the same package; inspect SQLite tables (`repository_context`, `resources`, `resource_repository_relations`, `resource_relations`, `repository_mapping_dispositions`, `sources`, `source_repositories`). Sender package narrowing is not receiver selection. Atomic-unit semantics must be enforced.
- **Verification Evidence**:
  - **Empty Selection**:
    - `report.admitted_context_resources == 0`.
    - SQLite inspection confirmed 0 rows across `repository_context`, `resources`, `resource_repository_relations`, `resource_relations`, `repository_mapping_dispositions`, `sources`, and `source_repositories`.
  - **Strict-Subset Selection** (`repo_a`, `res_a1`, `max_depth=0`):
    - `report.admitted_context_resources == 1`.
    - SQLite inspection confirmed `repository_context` contains only `repo_a` (`repo_b` omitted); `resources` contains only `res_a1` (`res_a2`, `res_b1`, `r_repo` omitted).
    - `resource_relations` contains 0 rows: `rel_a1_a2` was omitted because member `res_a2` was unselected, strictly verifying atomic-unit integrity.
    - `resource_repository_relations` contains 0 rows: mapping claim was omitted because `r_repo` was unselected.
  - **Complete Selection**:
    - `report.admitted_context_resources == 4`.
    - SQLite inspection confirmed `repository_context` (2 rows), `resources` (4 rows), `resource_repository_relations` (1 row), `resource_relations` (1 row), `repository_mapping_dispositions` (1 row), `sources` (1 row), and `source_repositories` (1 row).
  - Result: **PASS**

### Obligation 4: Context-Only and Paired Core+Context Import Paths
- **Requirement**: Exercise both Context-only (`ExchangeService.import_package`) and paired Core+Context (`PairedAcquisitionCoordinator`) import paths.
- **Verification Evidence**:
  - **Context-Only Path**: Target directory initialized without `core.sqlite3`. `ExchangeService.import_package` successfully imports Context facts (`context_imported=True`, `core_imported=False`, 1 resource admitted). Confirmed `core.sqlite3` does not exist and was not opened.
  - **Paired Path**: `PairedAcquisitionCoordinator.admit_paired(core_fn=core_step, context_fn=context_step)` executes atomic Core-first and Context-second steps. Confirmed durable persistence in both `core.sqlite3` (`repositories`) and `context.sqlite3` (`repository_context`, `resources`).
  - Result: **PASS**

### Obligation 5: Foreign Authorization Handle Rejection
- **Requirement**: Pass a genuine handle issued by another authorization service into product routes and assert fail-closed rejection.
- **Verification Evidence**:
  - Service 1 issues genuine handle `adm1`. Service 2 issues genuine handle `adm2`.
  - When `adm1` is passed to product routes configured with Service 2:
    - `auth2.validate_context(adm1)` raises `AdmissionRefused("PERMISSION_DENIED")`.
    - `Context.transaction(catalog, authorization=auth2, admission=adm1)` raises `AdmissionRefused("PERMISSION_DENIED")`.
    - `ProviderAcquisition(catalog, authorization=auth2, admission=adm1).admit_batch(...)` raises `AdmissionRefused("PERMISSION_DENIED")`.
    - `PairedAcquisitionCoordinator(catalog, authorization=auth2, admission=adm1).admit_paired(...)` raises `AdmissionRefused("PERMISSION_DENIED")`.
    - `ExchangeService(catalog).import_package(..., authorization=auth2, admission=adm1)` raises `AdmissionRefused("PERMISSION_DENIED")`.
  - Exactly 0 rows were written to target SQLite databases.
  - Result: **PASS**

### Obligation 6: Permission Revocation at Actual Transaction/COMMIT Boundaries
- **Requirement**: Trigger permission revocation at actual transaction/COMMIT boundaries (not just a standalone `lease.check_current()` call).
- **Verification Evidence**:
  - **Direct Context.transaction**: Inside the transaction block, resource writes succeed. `policy.grants = DependencySet()` is called to revoke permissions. Upon exiting the block, `_precommit_admission` calls `lease.check_current()`, detects the revision increment, raises `AdmissionRefused("PERMISSION_DENIED")`, and triggers `db.rollback()`. SQLite contains 0 rows.
  - **ExchangeService.import_package cut hook**: `cut` hook at `"during_context"` triggers `policy.grants = DependencySet()`. Precommit checks fail before COMMIT, raising `AdmissionFailure(cause=PERMISSION_DENIED)`. Target Context store contains 0 rows.
  - Result: **PASS**

### Obligation 7: Exact Replay and Cached Receipt Behavior After Revocation
- **Requirement**: Verify exact replay and cached receipt behavior after revocation (assert fail-closed or receipt invariants).
- **Verification Evidence**:
  - Initial import of package succeeds (`idempotent_replay is False`).
  - Replay import with active authority succeeds (`idempotent_replay is True`).
  - `policy.grants = DependencySet()` revokes permission.
  - Subsequent replay attempt fails closed, raising `AdmissionRefused("PERMISSION_DENIED")`. Prior receipts do not grant ambient authority or bypass active checks.
  - Target SQLite store remains intact and uncorrupted.
  - Result: **PASS**

### Obligation 8: Independent Source, MappingClaim, and Disposition Permissions
- **Requirement**: Verify Source, MappingClaim, and Disposition permissions independently (assert rejection when each single permission is withheld while others are granted).
- **Verification Evidence**:
  - **Source Withheld**: `policy.lease` raises `PERMISSION_DENIED`; `ExchangeService.import_package` raises `PERMISSION_DENIED`; `Context.transaction` `ctx.source(...)` raises `PERMISSION_DENIED`.
  - **MappingClaim Withheld**: `policy.lease` raises `PERMISSION_DENIED`; `ExchangeService.import_package` raises `PERMISSION_DENIED`.
  - **Disposition Withheld**: `policy.lease` raises `PERMISSION_DENIED`; `ExchangeService.import_package` raises `PERMISSION_DENIED`; `Context.transaction` `ctx.admit_mapping_disposition(...)` raises `PERMISSION_DENIED`.
  - In each scenario, all other permissions were granted. Orthogonality confirmed.
  - Result: **PASS**

### Obligation 9: Paired Core-First Failure and Operational Recovery Bookkeeping
- **Requirement**: Execute authorized paired Provider acquisition and supported Core-first failure/recovery bookkeeping. Verify Core commit is durable, Context rolled back, and operational recovery state is tracked. Do not assume cross-store atomic rollback.
- **Verification Evidence**:
  - Paired admission executed where Core commits successfully, followed by an intentional failure during the Context stage.
  - `AdmissionFailure` returned with `outcome.core_committed is True` and `outcome.context_committed is False`.
  - **Core durability**: `core.sqlite3` `repositories` table contains `repo_id`.
  - **Context rollback**: `context.sqlite3` `repository_context` table does NOT contain `repo_id`; `resources` table has 0 rows.
  - **Operational recovery tracking**: `operational.sqlite3` `request_continuations` table contains durable record under `adr0030-partial` storing `{"core_committed": true, "context_committed": false}`.
  - Direct test on `PairedAcquisitionCoordinator.admit_paired` confirmed identical durable Core and rolled-back Context semantics.
  - Result: **PASS**

### Obligation 10: Retention of Both Transfer SQL Fences
- **Requirement**: Retain both Transfer SQL fences (`i2_transfer_stage_fence`, `i2_transfer_report_stage_fence`) and prove ordinary Transfer remains refused with `UnsupportedResourceStage`.
- **Verification Evidence**:
  - SQLite `sqlite_schema` inspection confirmed `i2_transfer_stage_fence` on `resource_repository_relations` and `i2_transfer_report_stage_fence` on `resource_relations`, both containing `I2_TRANSFER_UNSUPPORTED`.
  - `ProviderAcquisition.admit_batch(...)` with timeline `TransferredEvent` intake refused with `UnsupportedResourceStage("Provider Transfer intake")`.
  - Direct SQL `INSERT` of `transfer_from_repository` relation aborted by database trigger with `I2_TRANSFER_UNSUPPORTED`.
  - Direct SQL `INSERT` of `transfer_event_report` relation aborted by database trigger with `I2_TRANSFER_UNSUPPORTED`.
  - Zero rows inserted into either table.
  - Result: **PASS**

---

## Test Execution Evidence

```
rootdir: /home/ubuntu/github/git-repo-db/review/adr0031-i6c-behavioral-verification-20261024
configfile: pyproject.toml
plugins: anyio-4.15.1, platformdirs-4.13.0, xdist-3.8.0
collected 8 items

tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_1_2_3_single_package_receiver_selections_and_rowsets PASSED [ 12%]
tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_4_context_only_and_paired_import_paths PASSED [ 25%]
tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_5_foreign_authorization_handle_rejected PASSED [ 37%]
tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_6_permission_revocation_at_commit_boundaries PASSED [ 50%]
tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_7_exact_replay_and_cached_receipt_revocation PASSED [ 62%]
tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_8_independent_source_mapping_claim_and_disposition_permissions PASSED [ 75%]
tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_9_paired_core_first_failure_and_operational_recovery_state PASSED [ 87%]
tests/integration/access/test_i6c_behavioral_verification.py::test_obligation_10_transfer_sql_fences_and_unsupported_resource_stage PASSED [100%]

============================== 8 passed in 12.04s ==============================
```

- **Code Quality**:
  - `ruff check tests/integration/access/test_i6c_behavioral_verification.py`: All checks passed! (0 errors)
  - `ruff format --check tests/integration/access/test_i6c_behavioral_verification.py`: 1 file already formatted!

---

## Conclusion

The independent behavioral verification test suite thoroughly verifies all 10 obligations of ADR 0031 I6-C with real public APIs and persistent-state SQLite assertions. The earlier gaps from review #164 have been fully closed.
Decision: **ACCEPTANCE (PASS)**.
