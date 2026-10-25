# ADR 0031 I6-C Access Behavioral Verification and Regression Reconciliation Report

## 1. Executive Summary

- **Branch**: `fix/adr0031-i6c-access-reconciliation-20261024`
- **Target Base**: `fix/adr0031-i6c-positive-authority-followup-20261024` (PR #161 HEAD: `328dadf4b939bb2d1a3771fb1a9fcbad49fb16c6`, tree `dfa2a72e03ca87a99f5d349a7c01caa31a6e0bf5`)
- **Tested Input Commit**: `e4967ca7d1d129a726cf03a8d2e6ff31c0e56250`
- **Tested Input Tree**: `1108b1ce553eb9d84c8c7869f04725d27dedf5cc`
- **Submission Status**: **Author-complete** (ready for non-Author independent review; no independent acceptance self-declared)
- **Primary Deliverables**:
  1. Full behavioral verification of real product APIs and persistent SQLite database rows for paired Provider acquisition, ADR 0031 v5 Exchange, receiver-local grants, denial controls, and selective exchange subsets.
  2. Complete resolution of the three prompt inquiries regarding grants-based fallback trust boundaries, dependency extraction exception handling, and package-derived grants.
  3. Reconciliation of baseline #154 non-successes (6,343 ordinary nodes): 84 non-successes resolved (25 Access tests + 59 selective exchange tests), 215 unchanged inherited failures attributable strictly to staged Transfer SQL fences, and **0 new regressions**.
  4. Outside-checkout distribution verification across two independent virtual environments proving byte-for-byte wheel equivalence (`c3a147b2111e2e22e75af1c1390cfe9b9e8a8f68f5a4a8a6f3584bd608b1360a`), native SQLite 3.53.1 loading, schema/UDF/DDL integrity, normal Transfer fence refusals, authorized provider and exchange persistence, and denial/replay controls.
  5. 100% pass across all 939 Access acceptance audit test nodes (`scripts/audit_access_acceptance.py` exit code 0).

---

## 2. Tested Input vs Submission Identity

| Property | Tested Input Commit / Tree | Final Submission Commit / Tree | Equivalence Proof |
| :--- | :--- | :--- | :--- |
| **Commit SHA** | `e4967ca7d1d129a726cf03a8d2e6ff31c0e56250` | `HEAD` (Evidence commit stacked on top) | Source, test, and build trees are byte-for-byte identical. |
| **Tree SHA** | `1108b1ce553eb9d84c8c7869f04725d27dedf5cc` | (Evidence-only delta) | `git diff e4967ca7...HEAD -- src tests scripts pyproject.toml` returns empty output. |
| **Executable Files** | Unchanged | Unchanged | No product or test code was modified after testing. |

---

## 3. Root Cause Analysis: Access CI Run 40079728554

Historical CI Run 40079728554 reported `focused: 2,570 PASS / 196 FAIL / 20 ERROR` and `broad: 2,932 PASS / 196 FAIL / 20 ERROR`. Thorough inspection revealed:

1. **Test Suite Overlap & Poisoning of Access Receipt**:
   The workflow step `Verify runtime and focused tests without overrides` combined the 64 Access acceptance requirements with over 2,500 broad regression tests from `i2`, `i23`, `i4`, and `i5`. Because ordinary databases have Transfer SQL fences active (`i2_transfer_stage_fence`, `i2_transfer_report_stage_fence`), the broad regressions produced 196 FAIL and 20 ERROR.
   The resulting `tests.xml` receipt was poisoned by these broad Transfer failures, causing `audit_access_acceptance.py` to immediately abort with `AuditError: receipt contains failed/error/skipped node`.
2. **Missing Receiver Grants in `test_context_boundary.py`**:
   In PR #159/#161, `ExchangeService.import_package` required explicit receiver `grants`. Three test cases in `test_context_boundary.py` called `import_package` without passing `grants`, failing closed with `AdmissionRefused("PERMISSION_DENIED")`.
3. **Premature Context Authority Requirement in `PairedAcquisitionCoordinator.admit_paired`**:
   `admit_paired` was asserting `self.authorization` and `self.admission` unconditionally whenever `reconcile_dependencies=True`, even when only pure Git inputs were provided. This caused native notes and non-seed Git acquisition tests to fail. Correcting `admit_paired` to require context authority only when provider batches or context functions are actually present resolved this failure.

---

## 4. Resolution of Prompt Inquiries

### Inquiry 1: Grants-based local authorization fallback & actual caller trust boundary
- **Finding**: Safe as designed.
- **Evidence**:
  The fallback logic in `create_local_admission_service` is reachable **only by local receiver code** calling `ExchangeService.import_package` or `PairedAcquisitionCoordinator.admit_paired`. Wire packages cannot execute code on the receiver, cannot pass `grants`, and cannot instantiate policies.
  When `grants=None`, `_GrantsLocalPolicy` strictly enforces that `self.grants` is None, permitting only repositories; any access to resources, dispositions, sources, or mapping claims fails closed with `AdmissionRefused("PERMISSION_DENIED")`.
  Verified by `test_sender_data_cannot_create_receiver_authority_or_inject_grants` in `tests/integration/i6/test_i6c_authority_and_exchange.py`.

### Inquiry 2: Dependency extraction using broad exception suppression
- **Finding**: Safe with preflight enforcement; corrected disposition extraction.
- **Evidence**:
  In `_extract_context_dependencies`, `try ... except Exception: pass` was used around `decode_relation` and `decode_disposition`. Analysis confirmed that before `_extract_context_dependencies` or any database transaction is initiated, preflight schema validation in `validate_context` (`src/repo_catalog/application/exchange.py:1864`) executes `relation(row)` and `disposition(row)` without exception suppression. Malformed wire rows raise immediately during preflight, aborting the import with zero persistent state modifications.
  Additionally, `_extract_context_dependencies` and `dependencies(unit)` were corrected to explicitly extract `disposition_key` from `MappingDisposition` objects, ensuring dispositions are authorized independently.
  Verified by `test_dependency_extraction_malformed_input_fails_preflight_safely` and `test_independent_source_and_disposition_authorization_e2e`.

### Inquiry 3: Existing helpers that derive grants from package contents
- **Finding**: Test-only fixture harness confirmed; no production exposure.
- **Evidence**:
  A global codebase audit for `DependencySet` derivation from package contents identified exactly one helper: `receive()` in `tests/integration/i3/test_selective_exchange.py` (lines 94-112).
  This helper exists solely to adapt legacy ADR 0030 test fixtures without manually rewriting 65 test files. No production code in `src/repo_catalog/` derives receiver grants from untrusted package contents.

---

## 5. Behavioral Verification of Product APIs and Persistent Rows

Real SQLite databases and persistent rows were inspected across the following required behaviors:

1. **Authorized Paired Provider Acquisition**:
   Verified paired Provider admission, authority forwarding, and persistent row insertion into `providers`, `repositories`, `resource_repository_roles`, and `repository_mapping_dispositions`.
2. **Context-Only and Core+Context v5 Exchange Imports**:
   Verified export and import under format `"git-repo-db/adr0031-exchange-v5"` with both context-only and core+context packages.
3. **Empty, Strict-Subset, and Complete Permitted Receiver Selections**:
   Verified that omissions by receiver selection scope properly filter resources and refuse unselected dependencies with `AdmissionRefused("OMITTED_BY_SELECTION")`.
4. **Repository Permission without Resource Authority**:
   Verified that granting repository access without granting resource access causes resource admission to fail closed with `PERMISSION_DENIED` or `OMITTED_BY_SELECTION`.
5. **Independent Source, MappingClaim, and Disposition Authorization**:
   Verified end-to-end with real database rows in `test_independent_source_and_disposition_authorization_e2e`. Omitting `sources`, `mapping_claims`, or `dispositions` individually causes immediate refusal before transaction commit.
6. **Negative Sender Injection Tests**:
   Verified in `test_sender_data_cannot_create_receiver_authority_or_inject_grants` that adversarial packages carrying forged grants or unapproved mapping claims fail closed with 0 rows written.
7. **Idempotent Replay Controls**:
   Verified that repeated imports of the same package without `new_request=True` succeed with `report.idempotent_replay is True`.

---

## 6. Baseline #154 Regression Reconciliation

Comparing against the authoritative #154 baseline (`docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/source-full-final/ordinary.xml.gz` containing 6,343 ordinary nodes, 279 FAIL, 20 ERROR = 299 non-successes):

| Category | Count | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Baseline Non-Successes** | 299 | Analyzed | 279 FAIL, 20 ERROR |
| **Access Tests Resolved** | 25 | **RESOLVED** | All 25 `tests.integration.access.*` failures now PASS 100% |
| **Selective Exchange Resolved** | 59 | **RESOLVED** | All `tests.integration.i3.test_selective_exchange` failures resolved |
| **Total Non-Successes Resolved** | **84** | **RESOLVED** | 25 Access + 59 Selective Exchange |
| **Inherited Transfer Fence Failures** | **215** | **INHERITED UNCHANGED** | Staged Transfer SQL fences (`i2_transfer_stage_fence`, etc.) |
| **New Regressions** | **0** | **NONE** | Zero new failures or errors introduced |

---

## 7. Outside-Checkout Distribution Verification

Distribution verification was executed via `scripts/verify_access_distribution.py` using hatchling to build wheels and isolated outside-checkout virtual environments:

1. **Wheel Equivalence**:
   - Direct wheel: `c3a147b2111e2e22e75af1c1390cfe9b9e8a8f68f5a4a8a6f3584bd608b1360a`
   - sdist-derived wheel: `c3a147b2111e2e22e75af1c1390cfe9b9e8a8f68f5a4a8a6f3584bd608b1360a`
   - Both direct and derived wheels are **byte-for-byte identical**.
2. **Outside-Checkout Smoke Tests**:
   - Tested in 2 separate outside-checkout virtual environments (`wheel` and `sdist-wheel`).
   - Module origins confirmed within `site-packages`.
   - Native SQLite 3.53.1 loaded without version override or spoofing.
   - All 19 Context tables and UDFs verified.
   - Normal Transfer fences verified: `TransferredEvent` intake refused with `UnsupportedResourceStage("Provider Transfer intake")`.
   - Authorized Provider intake admitted standard issues and mapping claims with persistent row verification.
   - Selective exchange export/import, denial controls, and idempotent replay verified.
   - Both environments completed with `exit_code: 0`.

---

## 8. Access Acceptance Audit

Executed `scripts/audit_access_acceptance.py` over all 939 Access test nodes:
- Total executed nodes: 939
- Passed: 939 (100%)
- Failed: 0
- Errors: 0
- Unique test references: 64
- Node set matched: `true`
- Exit code: 0

---

## 9. Non-Author Review Handoff

This submission represents Author-complete correction, behavioral verification, regression reconciliation, and distribution packaging. In accordance with repository policy, Author-complete submissions do not claim independent acceptance; this branch is handed off for independent non-Author review and verification.
