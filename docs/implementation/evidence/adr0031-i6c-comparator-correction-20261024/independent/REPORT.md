# Independent Review Report: Stage 1 (Comparator Acceptance Semantics Correction)

## 1. Executive Summary

- **Repository**: `https://github.com/TakashiSasaki/git-repo-db`
- **Target PR**: PR #170 (`https://github.com/TakashiSasaki/git-repo-db/pull/170`)
- **Target Base Branch**: `fix/adr0031-i6c-regression-hardening-20261024` (PR #168, commit `3a1f112331c87747249f38af370160adc0de108a`)
- **Target Head Branch**: `fix/adr0031-i6c-comparator-correction-20261024` (HEAD commit `55de572bdac4b9b90b131d89025b0ed304cd0159`)
- **Reviewer Role**: Independent Non-Author Reviewer
- **Stage**: Stage 1 (Comparator Acceptance Semantics Correction)
- **Review Decision**: **SCOPED ACCEPTANCE (PASS)**
- **Whole ADR Acceptance**: `false` (Scoped strictly to Stage 1 comparator corrections; Stage 2 Access behavior verification remains pending)

This report presents the independent audit and empirical verification of PR #170, which resolves latent false acceptance shortcuts in `scripts/compare_access_regressions.py` and establishes standalone unit test coverage in `tests/unit/test_compare_access_regressions.py`.

---

## 2. Review Protocol and Two-Stage Commit Separation

In accordance with the repository's `author-correction-protocol`:
1. **Author Tested Input Commit**: `61efe65e23be038cf97314e970b5b500e290ed0a` (Tree SHA: `fa4d7d64692eadef79fd9f3423c71df659432df9`)
2. **Author Final Submission Commit**: `55de572bdac4b9b90b131d89025b0ed304cd0159` (Tree SHA: `a588ff898c968582f8fb1d661e1cdec9fa2bee08`)

### Verification of Executable Code Invariance
An independent Git diff was performed comparing the tested input commit against the final submission commit across all product code, test definitions, scripts, build configuration, and CI workflows:
```bash
git diff 61efe65e23be038cf97314e970b5b500e290ed0a..55de572bdac4b9b90b131d89025b0ed304cd0159 -- src tests scripts pyproject.toml .github
```
**Result**: The command output was completely empty (0 bytes delta). All additions in the submission commit (`55de572b`) were strictly confined to documentation and evidence files under `docs/implementation/evidence/adr0031-i6c-comparator-correction-20261024/`. Two-stage commit separation is verified to be 100% compliant.

---

## 3. Audit of Comparator Logic Corrections

The source changes in `scripts/compare_access_regressions.py` were independently audited against the required acceptance semantics:

### 3.1 Elimination of Test-Name Matching in Stage Transfer Fence (`is_transfer_stage_fence`)
- **Original Defect**: `is_transfer_stage_fence` matched on `test_transfer_reports_never_shrunk_or_mixed in info.get("name", "")`, allowing arbitrary failures in that test to be misclassified as staged Transfer fences.
- **Hardened Implementation**: Test-name matching has been eliminated. The function now requires:
  1. An explicit stage fence error marker in message or text (`i2_transfer_stage_fence`, `i2_transfer_report_stage_fence`, `UnsupportedResourceStage`, `I2_TRANSFER_UNSUPPORTED`), OR explicit refusal code (`I2_TRANSFER_UNSUPPORTED`, `TRANSFER_UNSUPPORTED`).
  2. A compatible exception type (`UnsupportedResourceStage`, `OperationalError`, `IntegrityError`, `DatabaseError`) or error content marker.
- **Verdict**: Verified. Counterexample A is thoroughly eliminated.

### 3.2 Elimination of Unknown Metadata Fallback (`None == None`)
- **Original Defect**: In the general comparison fallback, if both baseline and current failure lacked metadata (`refusal_code=None`, `reached_assertion=None`), `None == None` evaluated to `True`, permitting disparate failures with identical exception types (or even different exception types in early drafts) to pass as inherited unchanged failures.
- **Hardened Implementation**:
  1. Identical non-None `exception_type` is strictly required (`b_exc == c_exc and b_exc is not None`).
  2. A concrete matching signature (`refusal_code` on both sides or `reached_assertion` on both sides) is strictly required (`has_concrete_sig`).
  3. If both sides have unknown metadata, the comparator strictly returns `CHANGED_FAILURE` with reason `"Unknown metadata: missing concrete refusal_code or reached_assertion signature"`.
- **Verdict**: Verified. Counterexample B is thoroughly eliminated.

### 3.3 Elimination of Admission Refusal Category Shortcut
- **Original Defect**: `is_admission_refusal` accepted both `PERMISSION_DENIED` and `INVALID_IDENTIFICATION`. When both baseline and current satisfied `is_admission_refusal`, `compare_failure_details` returned `("INHERITED_ADMISSION_PERMISSION_DENIED", True, None)` without verifying refusal code equality.
- **Hardened Implementation**:
  1. Explicit refusal code equality is enforced: `b_code == c_code and b_code is not None`.
  2. A transition such as `PERMISSION_DENIED` vs `INVALID_IDENTIFICATION` is explicitly classified as `CHANGED_FAILURE`.
  3. Mismatched admission category flags (`b_adm != c_adm`) explicitly return `CHANGED_FAILURE`.
- **Verdict**: Verified. Category shortcuts are completely removed.

### 3.4 P7 Recovery Signature Hardening
- **Original Defect**: Any test with `"p7"` in its classname was lumped into P7 recovery, and divergence in assertions could be masked if refusal codes were absent.
- **Hardened Implementation**:
  1. Compatible exception type matching is required (`exc_match = b_exc == c_exc and b_exc is not None`).
  2. A concrete matching signature is strictly required (`code_match = b_code == c_code and b_code is not None`, or `assert_match = b_assert == c_assert and b_assert is not None`).
  3. If exception or signatures do not match, it returns `CHANGED_FAILURE` with a detailed mismatch reason.
- **Verdict**: Verified.

### 3.5 Enforcement of Execution Completeness & Strict Failure on Unexpected Nodes
- `test_unexpected_nodes_executed_rejected_under_strict` verifies that unexpected test executions beyond the expected manifest trigger an immediate blocking error under `--strict`.

---

## 4. Empirical Test Suite Conformance

The unit test suite for the comparator was executed using the isolated virtual environment:
```bash
.venv/bin/python -m pytest tests/unit/test_compare_access_regressions.py -v
```

### Results
```
tests/unit/test_compare_access_regressions.py::test_empty_xml_rejected PASSED [  4%]
tests/unit/test_compare_access_regressions.py::test_skipped_testcase_rejected_under_strict PASSED [  8%]
tests/unit/test_compare_access_regressions.py::test_duplicate_and_subtest_records_handled_without_overwriting PASSED [ 13%]
tests/unit/test_compare_access_regressions.py::test_added_failing_node_rejected_under_strict PASSED [ 17%]
tests/unit/test_compare_access_regressions.py::test_environment_failure_rejected_under_strict PASSED [ 21%]
tests/unit/test_compare_access_regressions.py::test_changed_failure_rejected_under_strict PASSED [ 26%]
tests/unit/test_compare_access_regressions.py::test_missing_expected_node_rejected PASSED [ 30%]
tests/unit/test_compare_access_regressions.py::test_scoped_baseline_subset_partitions_without_false_deletions PASSED [ 34%]
tests/unit/test_compare_access_regressions.py::test_abnormal_pytest_exit_codes_rejected[2] PASSED [ 39%]
tests/unit/test_compare_access_regressions.py::test_abnormal_pytest_exit_codes_rejected[3] PASSED [ 43%]
tests/unit/test_compare_access_regressions.py::test_abnormal_pytest_exit_codes_rejected[4] PASSED [ 47%]
tests/unit/test_compare_access_regressions.py::test_abnormal_pytest_exit_codes_rejected[5] PASSED [ 52%]
tests/unit/test_compare_access_regressions.py::test_counterexample_a_transfer_stage_fence_requires_error_marker PASSED [ 56%]
tests/unit/test_compare_access_regressions.py::test_counterexample_b_unknown_metadata_fallback_rejected PASSED [ 60%]
tests/unit/test_compare_access_regressions.py::test_admission_refusal_code_mismatch_rejected PASSED [ 65%]
tests/unit/test_compare_access_regressions.py::test_admission_exception_type_mismatch_rejected PASSED [ 69%]
tests/unit/test_compare_access_regressions.py::test_admission_matching_permission_denied_accepted PASSED [ 73%]
tests/unit/test_compare_access_regressions.py::test_p7_recovery_classname_alone_without_matching_signature_rejected PASSED [ 78%]
tests/unit/test_compare_access_regressions.py::test_p7_recovery_matching_signature_accepted PASSED [ 82%]
tests/unit/test_compare_access_regressions.py::test_general_fallback_unknown_metadata_none_none_rejected PASSED [ 86%]
tests/unit/test_compare_access_regressions.py::test_general_fallback_matching_assertion_accepted PASSED [ 91%]
tests/unit/test_compare_access_regressions.py::test_general_fallback_reached_assertion_mismatch_rejected PASSED [ 95%]
tests/unit/test_compare_access_regressions.py::test_unexpected_nodes_executed_rejected_under_strict PASSED [100%]

============================== 23 passed in 0.84s ==============================
```
All 23 unit tests pass cleanly in 0.84 seconds.

---

## 5. Mechanical Evidence Comparison Verification

The mechanical comparison evidence recorded in `docs/implementation/evidence/adr0031-i6c-comparator-correction-20261024/failure-comparison.json` was independently analyzed:

| Metric | Result | Independent Verification |
| :--- | :--- | :--- |
| Baseline Manifest Nodes | 6,343 | Matches baseline #154 manifest |
| In-Scope Baseline Partition | 1,847 | Scoped partition preserved |
| Out-of-Scope Baseline Partition | 4,496 | Correctly quarantined without false deletion |
| Expected Execution Nodes | 1,847 | Matches `raw/regression_collected.txt` |
| Executed Execution Nodes | 1,847 | Matches `raw/regressions.xml` |
| Missing Expected Nodes | 0 | Complete execution |
| Unexpected Nodes Executed | 0 | No unmanifested tests executed |
| Unexpected Skips | 0 | No skipped test evasion |
| Resolved Non-Successes | 72 | Validated remediations |
| Inherited Non-Successes | 201 | 43 Transfer fences, 144 admission `PERMISSION_DENIED`, 14 P7 recovery |
| Changed Non-Successes | **1** | Detected mutation |
| New Product Regressions | 0 | No regressions introduced |
| Added Failures | 0 | No uninherited new failures |
| Environment Failures | 0 | Zero infrastructure/environment aborts |
| Strict Acceptance Verdict | **REJECTED** | Correctly blocked due to 1 changed non-success |

### Empirical Demonstration of Changed Failure Detection
The detected changed failure node is:
`tests.integration.p1.test_generalized_resources::test_selected_real_wire_without_identification_refuses_before_core_effects`

- **Baseline Receipt (#154)**:
  - Phase: `call`
  - Exception: `repo_catalog.domain.context_admission.AdmissionRefused`
  - Refusal Code: `PERMISSION_DENIED`
  - Location: line 411 (`export_package` refused at unauthenticated export barrier)
- **Current Receipt (`raw/regressions.xml`)**:
  - Phase: `call`
  - Exception: `repo_catalog.domain.exchange.ExchangeError`
  - Refusal Code: `INVALID_IDENTIFICATION`
  - Location: line 415 (export succeeded; line 415 failed during envelope row wire validation `ResourceIdentification.from_wire(row)`)

**Significance**: Under the unhardened comparator from PR #168, this node was lumped into "145 admission `PERMISSION_DENIED`" via category matching, masking the failure mode change. Under the corrected comparator:
1. `b_adm != c_adm` (baseline was `AdmissionRefused`, current was `ExchangeError`), triggering `CHANGED_FAILURE`.
2. Even under code comparison, `PERMISSION_DENIED != INVALID_IDENTIFICATION`, triggering `CHANGED_FAILURE`.
3. The comparator strictly marked `acceptance_verdict = REJECTED` and recorded blocking violation `"1 changed non-successes detected"`.

This directly proves that the comparator in PR #170 successfully eliminates false acceptance shortcuts.

---

## 6. Review Findings and Open Non-Author Obligations

### Review Findings
- **Blocking Issues (P0/P1)**: **0**.
- **`findings.json`**: Empty array `[]`.

### Open Stage 2 Obligations
In accordance with ADR 0031 and repository protocols, whole-ADR acceptance is deferred until the subsequent integration stage addresses the substantive Access reconciliation and behavioral obligations:
1. Empty receiver selection: Verification that empty selection scope admits 0 items without failure.
2. Receiver-side subset selection: Verification that receiver-side filtering correctly admits the specified subset while omitting unrequested items.
3. Real COMMIT revocation: Verification that revocation during transaction execution raises `PERMISSION_DENIED` at the commit boundary.
4. Foreign service-issued handles: Verification that foreign UUIDs and mismatched credentials fail closed.
5. Replay revocation: Verification that subsequent replays of revoked authority fail closed.

---

## 7. Review Conclusion

The Author correction in PR #170 is rigorous, sound, and fully verified:
1. All false acceptance shortcuts have been eliminated from `scripts/compare_access_regressions.py`.
2. The standalone unit test suite in `tests/unit/test_compare_access_regressions.py` passes 23/23 tests.
3. Two-stage commit separation is preserved with an empty diff across all code paths.
4. Mechanical failure comparison proves the comparator strictly detects failure mutations and blocks false acceptance.

**Verdict**: **SCOPED ACCEPTANCE (PASS)** for PR #170 (Stage 1).
