# I155-M01 Dataclass Selection-Budget Defect Verification Matrix

Author correction matrix verifying the remediation of the dataclass selection-budget defect against PR #162 (`fix/adr0031-i155-m01-scanner-correction-20261024`, commit `bebc039ed9772edf0737caf8f5520134907317e0`).

## 1. Implementation Requirements Matrix

| Req ID | Requirement Description | Implementation Location | Verification Evidence |
|---|---|---|---|
| **REQ-DC-1** | Consistent remaining work computation considering both `context.budget.work_limit` and `context.selection.max_work` | `context_admission.py:462` (`reserve_children(count)`) | `test_dataclass_selection_lower_than_budget_1000_fields`, `case_7b` (`used_work=2`, `max_queue_len=1`) |
| **REQ-DC-2** | Bounded intermediate `members` list materialization prior to attribute access | `context_admission.py:462-473` | `test_dataclass_selection_lower_than_budget_1000_fields` (`max_members_len == 0`) |
| **REQ-DC-3** | Bounded attribute accesses (`getattr`) when capacity is exceeded | `context_admission.py:462-473` | `test_dataclass_selection_lower_than_budget_1000_fields` (`attribute_accesses == 0`) |
| **REQ-DC-4** | Pending sibling queue items count against remaining work capacity | `context_admission.py:378` (`len(pending) + count > rem`) | `test_dataclass_existing_pending_siblings` (`used_work=3`, `max_queue_len<=4`) |
| **REQ-DC-5** | Strict 1-unit fixed refusal charge without double-charging across dataclass failures | `context_admission.py:379, 460, 473` (`charge(work=1)`) | All refusal cases verify exact 1-unit charge (`used_work == 2` on root inputs) |
| **REQ-DC-6** | Exact positive boundaries preserved across selection and budget limits | `context_admission.py:370-380` | `test_dataclass_exact_boundaries_selection_and_budget` (cost 7 succeeds at 7; fails at 6) |
| **REQ-DC-7** | Zero and exhausted capacity handling fails closed immediately | `context_admission.py:365, 378` | `test_dataclass_zero_and_exhausted_capacity` (capacity 0 refuses at 1; 1 field at capacity 1 refuses at 2) |
| **REQ-DC-8** | Exception containment in `fields()` reflection and attribute access without double charging | `context_admission.py:458, 471` (`except AdmissionRefused: raise`) | `test_dataclass_callback_and_reflection_containment` |
| **REQ-DC-9** | Real Store relation transaction rollback, transfer fences intact, 0 row changes | `Context.owned_transaction` and native SQLite isolation | `reproduce_reviewer_finding.py::real_store_relation` (db_rows=0, fence=true, in_tx=false) |
| **REQ-DC-10** | Packaging contract & sdist reproducibility: direct wheel == derived wheel | `scripts/check_sdist_contract.py`, build scripts | `build-measurements.json` (`equal_full_zip_bytes: true`), `wheel-members.json` (164 members) |

---

## 2. Test Vector Coverage Matrix

| Vector ID | Description | Test Identifier | Baseline PR162 (`source162-unfixed`) | Fixed Correction (`source-fixed` / `direct` / `derived`) |
|---|---|---|---|---|
| **V01-V29** | Retained 29 regression test vectors from PR #162 | `test_admission_scanner_budget.py` (29 tests) | PASS (29/29) | **PASS** (all 29 pass cleanly) |
| **V30** | Dataclass selection budget with 1,000 fields (audit reproduction) | `test_dataclass_selection_lower_than_budget_1000_fields`, `case_7b` | queue: 1000, members: 1000, accesses: 1000, used: 8 | **PASS** (queue: 1, members: 0, accesses: 0, used: 2, `INPUT_LIMIT`) |
| **V31** | Dataclass budget lower than selection (budget 6, selection 10000) | `test_dataclass_budget_lower_than_selection` | PASS (queue 1, used 2) | **PASS** (queue: 1, members: 0, used: 2, `INPUT_LIMIT`) |
| **V32** | Dataclass prior cumulative work | `test_dataclass_prior_cumulative_work` | N/A (untested) | **PASS** (prior 9995, used 9997, queue 1, members 0) |
| **V33** | Dataclass existing pending siblings | `test_dataclass_existing_pending_siblings` | N/A (untested) | **PASS** (used 3, queue <= 4, members 0) |
| **V34** | Dataclass exact boundaries (sufficient vs 1 below) | `test_dataclass_exact_boundaries_selection_and_budget` | N/A (untested) | **PASS** (exact 7 succeeds; 6 fails with used 2) |
| **V35** | Dataclass zero and exhausted capacity | `test_dataclass_zero_and_exhausted_capacity` | N/A (untested) | **PASS** (cap 0 used 1; cap 1 used 2; empty used 1) |
| **V36** | Dataclass callback & reflection exception containment | `test_dataclass_callback_and_reflection_containment` | N/A (untested) | **PASS** (reflection error used 2; AdmissionRefused not double-charged) |
| **V37** | Real Store relation selection work limit 7 | `test_i155_m01_real_store_selection_work_limit_7`, `store_case[3]` | queue: 6, used: 8 | **PASS** (queue: 1, used: 3, `INPUT_LIMIT`) |
| **V38** | Real Store relation selection work limit 8 | `test_i155_m01_real_store_selection_work_limit_8` | N/A (untested) | **PASS** (queue: 6, used: 9, `INPUT_LIMIT`) |
| **V39** | Real Store relation with armed mutating list (1000 members) | `reproduce_reviewer_finding.py::real_store_relation` | PASS (queue 6, snap 2, used 9, db 0) | **PASS** (queue 6, snap 2, used 9, db 0, fence true) |
| **V40** | Packaging contract: direct wheel == derived wheel | `run_experiments.py::build_and_verify_distribution` | PASS | **PASS** (100% bit-for-bit identical, 164 members) |
| **V41** | Ruff linter & formatter | `ruff check`, `ruff format --check` | PASS (0 errors) | **PASS** (0 errors across 455 files) |
