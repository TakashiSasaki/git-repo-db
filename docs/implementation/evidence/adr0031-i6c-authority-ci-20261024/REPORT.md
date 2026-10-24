# ADR 0031 I6-C Authority Boundaries, Selection Widening, and CI Remediation Report

**Verdict: INCOMPLETE / FAIL (Author Verification Pending Independent Review)**

This report documents the review, remediation, and verification of PR #157 ("ADR 0031 I6-C Provider / Selective Exchange and genuine originals"). PR #157 reached Draft PR publication but failed Development CI and contained code-level implicit authority, receiver selection widening, and wire identification bypass concerns.

This correction branch (`fix/adr0031-i6c-authority-ci-20261024`) targets `impl/adr0031-i6c-provider-selective-exchange` directly. In accordance with repository practice, Author verification cannot grant a PASS; this submission remains `INCOMPLETE / FAIL` pending independent audit.

---

## 1. Exact Starting Point and Ancestry

| Coordinate | Value |
|---|---|
| Repository | `https://github.com/TakashiSasaki/git-repo-db` |
| Base Branch | `impl/adr0031-i6c-provider-selective-exchange` (PR #157) |
| Base HEAD | `5df40eace63d8487c34a95777f19e05caf55da75` |
| Base Tree | `cc2e42ac6cbed31bd18b12d4e28d496f73f1c8b2` |
| Fix Branch | `fix/adr0031-i6c-authority-ci-20261024` |
| Excluded Stacks | PR #155/#156 / PR #158 (I155-M01 Admission scanner work-budget fix, separate track) |

No foreign commits from PR #155/#156 were integrated or cherry-picked. PR #157 was neither modified in place nor force-pushed.

---

## 2. CI Remediation (Development Workflow Run 40048212414 / 40048212481)

### 2.1 Observed Defect
Development CI run 40048212414 failed in the `offline` job during Ruff linting with 11 errors:
- Unused import `validate_replay_consistency` in `src/repo_catalog/domain/exchange.py:820` (F401)
- Unused imports and unsorted imports in `tests/integration/i3/test_selective_exchange.py` (F401, I001)
- Formatting check in run 40048212481 reported 4 files in `src/` requiring reformatting.

### 2.2 Root Cause & Fix
- Removed the unused imports in `src/repo_catalog/domain/exchange.py` and `tests/integration/i3/test_selective_exchange.py`.
- Formatted and sorted all import blocks according to repository rules.
- Reformatted all changed and related files with `ruff format`.
- Verified locally: both `ruff check src tests scripts` and `ruff format --check src tests scripts` report `All checks passed!` across 452 files with 0 errors.

---

## 3. Critical Security Investigation A — Implicit Authority Elimination

### 3.1 Observed Defect
In PR #157, `create_local_admission_service` defaulted to `grants=None`, `selection=AdmissionSelection(all_selected=True)`, a hardcoded principal `"local-user"`, and `"local-credential"`. In `LocalAuthorizationPolicy`, if `grants is None` and `permitted_repositories is None`, requests were not strictly bounded. Furthermore, in `ProviderAcquisition._open_context`, `admit_paired`, and `reconcile_core_dependencies`, if no authorization or admission service was passed, the code manufactured a permissive local admission service.

### 3.2 Root Cause & Fix
- In `src/repo_catalog/domain/context_admission.py`:
  - `create_local_admission_service` now requires explicit `selection` and `grants` (or `permitted_repositories`). Omitting both raises `AdmissionRefused("PERMISSION_DENIED")`. It enforces credential authentication before returning the service and policy.
  - `LocalAuthorizationPolicy` checks `principal` matching, verifies `operation in OPERATIONS`, and verifies that requested dependencies are a strict subset of `self._grants`.
- In `src/repo_catalog/application/acquisition.py`:
  - `ProviderAcquisition._open_context` now immediately checks `if auth is None or adm is None: raise AdmissionRefused("PERMISSION_DENIED")` before any filesystem access or context instantiation.
  - `PairedAcquisitionCoordinator.admit_paired` and `reconcile_core_dependencies` fail closed (`AdmissionRefused("PERMISSION_DENIED")`) when authorization or admission service is omitted.
- In `src/repo_catalog/application/exchange.py`:
  - `import_package` requires explicit local authorization and admission when context is imported. If omitted and receiver permissions are not satisfied, it fails closed (`raise AdmissionRefused("PERMISSION_DENIED")`).

### 3.3 Test Coverage
Covered by 9 focused adversarial and boundary tests in `tests/integration/i6/test_i6c_authority_and_exchange.py`:
- `test_missing_local_authorization_fails_closed`
- `test_create_local_admission_service_requires_explicit_arguments`
- `test_local_authorization_policy_enforces_finite_grants`
- `test_local_authorization_policy_refuses_unauthorized_source_and_mapping`
- `test_local_authorization_policy_forged_principal_fails_closed`
- `test_local_authorization_policy_foreign_operation_fails_closed`
- `test_policy_revocation_during_lease_aborts_transaction`
- `test_caller_supplied_privileges_ignored_local_policy_controls`
- `test_cached_receipt_shortcut_fails_closed_on_revocation`

---

## 4. Critical Security Investigation B — Receiver Selection Widening Elimination

### 4.1 Observed Defect
In PR #157 `src/repo_catalog/application/exchange.py` (lines 1777-1799 and lines 1878-1900), the receiver's admission selection was mutated:
```python
admit_selection = replace(admit_selection, resource_keys=tuple(ResourceKey(...) for r in context_data["resources"]))
```
This allowed sender-provided resources in the wire package to overwrite the receiver's selection scope, widening the receiver's authorization and admitting resources never requested by the receiver.

### 4.2 Root Cause & Fix
- Completely removed lines 1777-1799 and lines 1878-1900 from `src/repo_catalog/application/exchange.py`.
- Enforced strict isolation between receiver selection and sender package contents.
- When receiver specifies `resource_keys = ()`, exactly 0 resources are admitted. When receiver specifies a subset, only selected resources are admitted, and unselected resources are omitted before policy evaluation.

### 4.3 Test Coverage
Covered by 2 regression tests in `tests/integration/i6/test_i6c_authority_and_exchange.py`:
- `test_receiver_empty_selection_admits_zero_resources`
- `test_receiver_selective_subset_omits_unselected_sender_resources`

---

## 5. Critical Validation Investigation C — Wire Identification Bypass & Stage Handling

### 5.1 Observed Defect
In PR #157 `src/repo_catalog/domain/exchange_rows.py`, a special case was introduced:
```python
if row.get("provider_resource_id") == '["global",[]]':
    pass
else:
    ResourceIdentification.from_wire(row)
```
This bypassed envelope validation for malformed resources with `provider_resource_id == '["global",[]]'` and `provider_document_id == None`. Furthermore, in `src/repo_catalog/domain/selective_exchange.py`:
- `validate_context_bindings` caught `(ValueError, TypeError)` and did `pass`, swallowing identification parsing exceptions.
- `preflight_i2_resources` caught `Exception` and converted all exceptions to `UnsupportedIdentificationStage`.

### 5.2 Root Cause & Fix
- Investigation revealed this bypass was introduced by PR #157's author to avoid an `ExchangeError("INVALID_IDENTIFICATION")` failure in an older test (`test_selected_real_wire_without_identification_refuses_before_core_effects`) when constructing an `ExchangePackage`.
- Removed the `provider_resource_id == '["global",[]]'` bypass from `src/repo_catalog/domain/exchange_rows.py`.
- Restored unconditional, strict `ResourceIdentification.from_wire(row)` for all `context.resources` rows during envelope validation (Stage 1).
- Restored strict 7-column identification validation during domain admission (Stage 2).
- Restored `preflight_i2_resources` converting only genuine coordinate parsing `(ValueError, TypeError)` to `UnsupportedIdentificationStage` without catching broad `Exception` (Stage 3).
- Removed exception swallowing (`pass`) from `validate_context_bindings`.

### 5.3 Test Coverage
Covered by 11 focused test vectors in `tests/integration/i6/test_i6c_authority_and_exchange.py`:
- `test_valid_global_document_identification`
- `test_valid_scoped_document_and_entities`
- `test_unknown_kind_with_canonical_nested_identity`
- `test_known_kind_with_inconsistent_namespace_fails`
- `test_missing_or_null_required_column_fails`
- `test_absence_of_bypass_for_global_empty_list`
- `test_preflight_i2_resources_raises_unsupported_identification_stage`
- `test_validate_context_bindings_does_not_swallow_exceptions`
- `test_wrong_native_scope_fails`
- `test_seven_column_resource_identification_roundtrip`
- `test_child_first_registration`

---

## 6. Packaging and Distribution Verification

Packaging and distribution verification was conducted in accordance with Section 10:
1. **Direct Build**: `hatchling build -t wheel -t sdist` produced:
   - Wheel: `repo_catalog-0.2.0-py3-none-any.whl` (792,373 bytes, SHA-256 `260dea2cf9581f0fe718a2252c1e639b75150f555ef0162df898d4d84d6b9eb5`)
   - Sdist: `repo_catalog-0.2.0.tar.gz` (183,690,640 bytes, SHA-256 `65997f572cbd45409a7410dfe4e86a9c4c17cdbda758825853a64c223f478bcb`)
2. **RECORD Hashes**: All RECORD entries in the direct wheel were verified against SHA-256 hashes and byte lengths; all match.
3. **Derived Wheel**: The sdist was unpacked and a derived wheel was built without `git` on PATH. The derived wheel is **byte-for-byte identical** (792,373 bytes, SHA-256 `260dea2cf9581f0fe718a2252c1e639b75150f555ef0162df898d4d84d6b9eb5`).
4. **Isolated Venv Installation**: The wheel was installed into an isolated virtual environment with `--no-deps`. Importing `repo_catalog` and `ResourceIdentification` outside the checkout succeeded cleanly.

Full execution log recorded in `raw/packaging_verification.log`.

---

## 7. Regression Reconciliation under ADR 0032

Under ADR 0032, host SQLite 3.45.1 is native. On-disk catalogs check `sqlite3.sqlite_version_info < MIN_SQLITE (3, 51, 3)` and refuse with `SchemaError`.
- **SQLite validation policy**: `scripts/check_sqlite_validation_policy.py` reported 0 violations.
- **SQLite policy unit tests**: `tests/unit/test_sqlite_validation_policy.py` passed 31/31 tests.
- **CI Python runtime unit tests**: `tests/unit/test_ci_python_runtime.py` passed 4/4 tests.
- **Genuine originals revalidation**: `tests/integration/i6a/test_originals_revalidation.py` passed 75/75 tests under native SQLite.
- **I6-C Authority & Exchange tests**: `tests/integration/i6/test_i6c_authority_and_exchange.py` passed 23/23 tests.
- **Transfer fences**: Exactly 1 expected test failure in `tests/integration/i3/test_selective_exchange.py` caused by the active Transfer fences (`i2_transfer_stage_fence`, `i2_transfer_report_stage_fence`). Assertions and fences were strictly preserved without mocking or weakening.

---

## 8. Note on Parallel Track: I155-M01 Scanner Defect

The I155-M01 Admission scanner work-budget violation is addressed in a separate parallel correction track (PR #158 targeting PR #156). It is not integrated or cherry-picked here, preventing conflict and maintaining strict separation of concerns between I6-A scanner review and I6-C authority/exchange remediation.
