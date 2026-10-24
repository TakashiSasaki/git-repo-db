# Superseding Author Correction Report: Dataclass Selection-Budget Defect & Acceptance Evidence

- **Role**: Author Correction (Draft PR)
- **Target PR**: PR #162 (`fix/adr0031-i155-m01-scanner-correction-20261024`)
- **Base Commit**: `bebc039ed9772edf0737caf8f5520134907317e0` (Tree: `fb25412fccaeb192f34eef563a8d068182c65690`)
- **Fix Branch**: `fix/adr0031-i155-m01-dataclass-selection-20261024`
- **Tested Input Commit**: `fbfd7a35b6f11befcf45e41eb52ba019f9dc28d2` (Tree: `08df9ffe3bfb2c98cc9f4196ff082c5c1024283e`)
- **Verdict**: **INCOMPLETE / FAIL** (Author correction submitted as Draft PR for subsequent independent non-Author acceptance; no self-approval)

---

## 1. Reconciliation of Tested-Input SHA Strings in PR #162

An inspection of PR #162 identified differing tested-input commit SHA strings between the PR body and its embedded `REPORT.md`:
- **PR #162 Body**: `c664ee5b9707688e248ca41f5af7ccb225e2a687` (Tree: `737f20d5a2b98aad1272b92040731c7e21c1c05e`)
- **PR #162 `REPORT.md`**: `c664ee5b62b7ae4d0c950a7c493cf0e6bba84b90` (Tree: `737f20d5a2b98aad1272b92040731c7e21c1c05e`)

### Reconciliation Finding:
1. Verification against actual Git repository objects via `git cat-file -t` and `git rev-parse` confirms that **`c664ee5b9707688e248ca41f5af7ccb225e2a687`** is the genuine, valid Git commit object in the repository history (`bebc039e~1`).
2. The hash string `c664ee5b62b7ae4d0c950a7c493cf0e6bba84b90` recorded in lines 7 and 114 of PR #162's `REPORT.md` does not correspond to an existing Git commit object; it represents an inadvertent transcription/reporting mismatch.
3. Both strings shared the exact same tree SHA `737f20d5a2b98aad1272b92040731c7e21c1c05e`.
4. Historical evidence in `docs/implementation/evidence/adr0031-i155-m01-final-correction-20261024/` is preserved untouched. This superseding report in `docs/implementation/evidence/adr0031-i155-m01-dataclass-selection-20261024/` formally supersedes and reconciles the identity.

---

## 2. Defect Remediation: Dataclass Selection-Budget Enforcement

### 2.1 The Concrete Defect in PR #162
In `ContextAdmissionService.charge_input()` at PR #162 (`bebc039e`), the dataclass branch executed:
```python
rem_work = context.budget.work_limit - context.budget.used_work
if count > rem_work or len(pending) + count > rem_work:
    charge(work=1)
    raise AdmissionRefused("INPUT_LIMIT")
```
This calculation evaluated only `context.budget.work_limit` and completely ignored `context.selection.max_work`. When `selection.max_work` was lower than `budget.work_limit` (e.g. `work_limit = 10000`, `max_work = 7` with a 1,000-field dataclass):
1. `rem_work` evaluated to `9999`, bypassing capacity enforcement.
2. All 1,000 attribute getters (`getattr(item, member.name)`) were executed.
3. A 1,000-element `members` intermediate list was allocated.
4. The `pending` queue was extended by 1,000 elements.
5. Traversal continued until `used_work = 8`, which eventually triggered `INPUT_LIMIT` during subsequent while-loop popping.

### 2.2 Independent Reproduction with Genuine Service-Issued Context
Using a genuine context issued by `ContextAdmissionService.context()`:
- Input: Standard dataclass with 1,000 integer fields.
- `budget.work_limit = 10000`, `selection.max_work = 7`.
- **Observed**: `max_pending = 1000`, `max_members = 1000`, `attribute_accesses = 1000`, eventual `INPUT_LIMIT` at `used_work = 8`.
- In real store relations with `selection.max_work = 7` (`ResourceRelation` having 6 fields):
  `ResourceRelation` was improperly expanded to 6 entries on pending queue, reaching refusal only at `used_work = 8`.

### 2.3 Applied Remediation
In `src/repo_catalog/domain/context_admission.py`:
1. Replaced the custom dataclass work calculation with the unified `reserve_children(count)` helper, which computes:
   `remaining_work() = min(context.budget.work_limit, context.selection.max_work) - context.budget.used_work`
2. Enforced capacity and pending sibling bounds (`count < 0 or count > rem or len(pending) + count > rem`) **strictly before** dataclass attribute access, intermediate `members` list materialization, and `pending` queue extension.
3. Defended `fields(item)` reflection and `getattr(item, member.name)` attribute access:
   - Added `except AdmissionRefused: raise` to prevent double-charging pre-trapped exceptions.
   - Handled any callback exception via `except Exception: charge(work=1); raise AdmissionRefused("INPUT_LIMIT")`.
4. Strictly preserved single refusal accounting (`used_work == 2` on root failures).

---

## 3. Before / After Measurements Across Cohorts

Probes were executed across four distinct environments using `run_experiments.py`:
1. `source162-unfixed` (Control: PR #162 HEAD `bebc039ed9772edf0737caf8f5520134907317e0`)
2. `source-fixed` (Working tree source at tested input commit `fbfd7a35b6f11befcf45e41eb52ba019f9dc28d2`)
3. `direct` (Installed wheel built directly)
4. `derived` (Installed wheel built from unpacked sdist without Git on PATH)

### 3.1 Scanner & Callback Scenarios (`reproduce_reviewer_finding.py`)

| Scenario | PR #162 Baseline (`source162-unfixed`) | Fixed Correction (`source-fixed` / `direct` / `derived`) | Status |
|---|---|---|---|
| **Case 7b: Dataclass selection 1000 fields** (`work_limit=10000`, `max_work=7`) | queue: 1000, members: 1000, accesses: 1000, used: 8 | **queue: 1, members: 0, accesses: 0, used: 2, `INPUT_LIMIT`** | **RESOLVED** |
| **Case 7: Dataclass capacity** (`work_limit=6`, `max_work=100`) | queue: 1, used: 2, `INPUT_LIMIT` | queue: 1, used: 2, `INPUT_LIMIT` | PASS |
| **Store Case 3: Selection limit 7** (`ResourceRelation` 6 fields, 1000 members) | queue: 6, used: 8, `INPUT_LIMIT` | **queue: 1, used: 3, `INPUT_LIMIT`** | **RESOLVED** |
| **Case 1: Appending list** | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 2: Changing length** | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 3: Same final length** | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 4: Deceptive `__len__`** | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 5: Exceeds during snapshot** | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 6: Exact boundary** | list_used: 6, tuple_used: 6 | list_used: 6, tuple_used: 6 | PASS |
| **Case 8: Broken iterator callback** | `INPUT_LIMIT`, used: 2 | `INPUT_LIMIT`, used: 2 | PASS |
| **Case 8: Broken dict values callback** | `INPUT_LIMIT`, used: 2 | `INPUT_LIMIT`, used: 2 | PASS |
| **Case 8: Broken dict keys callback** | `INPUT_LIMIT`, used: 2 | `INPUT_LIMIT`, used: 2 | PASS |
| **Case 8: Broken dataclass attr callback** | `INPUT_LIMIT`, used: 2 | `INPUT_LIMIT`, used: 2 | PASS |
| **Case 9: Single refusal charge** | list_used: 2, dict_used: 2 | list_used: 2, dict_used: 2 | PASS |
| **Real Store Relation** (1000 members armed) | queue: 6, snap: 2, used: 9, db_rows: 0, fence: true | queue: 6, snap: 2, used: 9, db_rows: 0, fence: true | PASS |

---

## 4. Packaging Contract & Sdist Equivalence

- **Sdist Budgets** (`scripts/check_sdist_contract.py` on `repo_catalog-0.2.0.tar.gz`):
  - Compressed size: 703,090 bytes (<= budget 2,097,152 bytes)
  - Unpacked size: 6,046,753 bytes (<= budget 8,388,608 bytes)
  - Member count: 164 (<= budget 512 members)
  - Tar stream bytes: 6,184,960 bytes (<= budget 8,922,624 bytes)
  - Contract verdict: **PASSED**
- **Wheel Bit-Level Equivalence**:
  - Direct wheel: `repo_catalog-0.2.0-py3-none-any.whl`, 791,849 bytes, SHA-256 `7dbbcfee566998e614cab97d5831c2ac941303b952c0d79183989c7d1d9c75c9`, 164 members.
  - Derived wheel (built from unpacked sdist without Git on PATH): 791,849 bytes, SHA-256 `7dbbcfee566998e614cab97d5831c2ac941303b952c0d79183989c7d1d9c75c9`, 164 members.
  - `equal_full_zip_bytes`: **true** (100% bit-for-bit identical).

---

## 5. Automated Regression Test Execution

- **Focused Admission & Scanner Regressions**:
  - `tests/unit/test_admission_scanner_budget.py`: 37 passed in 46.89s (0 failures).
  - Includes 8 new targeted regression tests covering:
    - `test_dataclass_selection_lower_than_budget_1000_fields`
    - `test_dataclass_budget_lower_than_selection`
    - `test_dataclass_prior_cumulative_work`
    - `test_dataclass_existing_pending_siblings`
    - `test_dataclass_exact_boundaries_selection_and_budget`
    - `test_dataclass_zero_and_exhausted_capacity`
    - `test_dataclass_callback_and_reflection_containment`
    - `test_i155_m01_real_store_selection_work_limit_8`
- **Broad Regression Comparison (686 tests in admission/context/transfer suites)**:
  - Baseline PR #162 (`bebc039e`): 662 passed, 8 failed, 8 errors.
  - Fixed PR (`fbfd7a35`): 670 passed, 8 failed, 8 errors.
  - Net change: +8 passed, 0 new or changed failures/errors.
  - Failure classification:
    - 8 errors: `test_context_coordinator_admission.py` (environment SQLite 3.45.1 < required 3.51.3).
    - 6 failures: `test_context_fences_i6a.py` (disk catalog / coordinator capability profile).
    - 2 failures: `test_context_fixture_authority.py` (facade fixture initialization with SQLite 3.45.1).
    - All 16 errors and failures are 100% identical between baseline and fix.
- **Linter & Formatter**:
  - `ruff check src tests scripts` (0 errors)
  - `ruff format --check src tests scripts` (455 files clean)

---

## 6. Commit Separation & Provenance Integrity

- **Base PR**: #162 (`fix/adr0031-i155-m01-scanner-correction-20261024`)
- **Base Commit**: `bebc039ed9772edf0737caf8f5520134907317e0` (Tree: `fb25412fccaeb192f34eef563a8d068182c65690`)
- **Tested Input Commit**: `fbfd7a35b6f11befcf45e41eb52ba019f9dc28d2` (Tree: `08df9ffe3bfb2c98cc9f4196ff082c5c1024283e`)
- **Final Submission**: Adds evidence strictly in `docs/implementation/evidence/adr0031-i155-m01-dataclass-selection-20261024/`.
- No modifications to executable product code or tests post-validation.
