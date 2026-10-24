# Author Final Correction Report: Admission Scanner Callback Containment & Acceptance Evidence

- **Role**: Author Correction (Draft PR)
- **Target PR**: PR #160 (`fix/adr0031-i155-m01-iterator-followup-20261024`), stacked on PR #158
- **Base Commit**: `1a508cac857b7d828920f68500128edeae7594f6` (Tree: `3f595003a66acfbab4837c85690091e0f3513bf6`)
- **Fix Branch**: `fix/adr0031-i155-m01-scanner-correction-20261024`
- **Tested Input Commit**: `c664ee5b62b7ae4d0c950a7c493cf0e6bba84b90` (Tree: `737f20d5a2b98aad1272b92040731c7e21c1c05e`)
- **Verdict**: **INCOMPLETE / FAIL** (Author correction submitted as Draft PR for subsequent independent non-Author acceptance; no self-approval)

---

## 1. Executive Summary & Defect Remediation

### 1.1 Unhandled User Callback Exceptions in Iteration & Reflection
In PR #160 (`1a508cac`), sequence iteration (`for child in it:`) and dictionary iteration (`for val in item.values():`, `for key in item.keys():`) as well as dataclass member reflection (`fields(item)`) and attribute access (`getattr(item, member.name)`) were not uniformly defended against user-defined callback exceptions. When an arbitrary container subclass or custom property raised an exception during traversal (such as `RuntimeError`, `ValueError`, or `KeyError`), the exception escaped unhandled into the caller instead of being charged as a contractual 1-unit refusal fee with `AdmissionRefused("INPUT_LIMIT")`.

### 1.2 Dataclass Member Capacity Pre-Reservation
While sequence and dictionary containers enforced element-by-element or total capacity bounds before queue allocation, dataclass instances previously iterated and extended `pending` with all fields without pre-verifying that the field count was within `remaining_work()`.

### 1.3 Remediation Applied
In `src/repo_catalog/domain/context_admission.py`:
1. **Protected Sequence Iteration**: Wrapped `for child in it:` in `try ... except AdmissionRefused: raise except Exception: charge(work=1); raise AdmissionRefused("INPUT_LIMIT")`. Any exception raised during iterator advancement immediately halts traversal, charges 1 refusal work unit, and fails closed.
2. **Protected Dictionary Iteration**: Wrapped `.values()` and `.keys()` loops in `try ... except AdmissionRefused: raise except Exception: charge(work=1); raise AdmissionRefused("INPUT_LIMIT")`.
3. **Protected Dataclass Reflection & Access**: Guarded `fields(item)` and `getattr(item, member.name)` against arbitrary user exceptions, charging 1 refusal unit and raising `AdmissionRefused("INPUT_LIMIT")` if access fails.
4. **Bounded Dataclass Member Capacity**: Enforces `rem_work = context.budget.work_limit - context.budget.used_work; if count > rem_work or len(pending) + count > rem_work: charge(work=1); raise AdmissionRefused("INPUT_LIMIT")` before pending queue extension. Member tuples are materialized into a separate local list (`members`) before extending `pending`, preventing unbounded queue growth.
5. **Exact 1-Unit Refusal Accounting**: All trapped exceptions charge exactly 1 unit of refusal work, strictly preventing double charging.

---

## 2. Supported Input Grammar & Contract Boundaries

### 2.1 Supported Types
In accordance with Accepted ADRs 0031, 0032, and 0033:
- **Primitives**: `int`, `float`, `str`, `bytes`, `bool`, `NoneType`
- **Sequences**: `tuple` (zero-copy fast path), `list`, `frozenset`
- **Mappings**: `dict`
- **Structured Records**: Standard Python `dataclass` instances

### 2.2 Distinction: Internal Queue Bounds vs. Arbitrary Callback Allocations
- **Internal Queue & Snapshot Storage**: `ContextAdmissionService` strictly bounds internal data structures:
  - `pending` (traversal queue): bounded at all times by `remaining_work()`.
  - `children` (snapshot buffer): bounded element-by-element by `remaining_work()`.
- **Arbitrary Python Callbacks**: When user-defined code (such as custom `__iter__`, `__len__`, `keys()`, or `@property` getters) executes, any internal allocations inside that callback occur within user Python space. The scanner cannot intercept allocations made inside arbitrary CPython bytecode once invoked.
- **Fail-Closed Contract**: Any user callback that raises an exception or attempts to yield more elements than declared immediately halts traversal, incurs the 1-unit refusal fee, and fails closed with `AdmissionRefused("INPUT_LIMIT")`.

---

## 3. Before / After Measurements Across Cohorts

Probes were executed across four distinct environments:
1. `source160-unfixed` (Control: PR #160 HEAD `1a508cac857b7d828920f68500128edeae7594f6`)
2. `source-fixed` (Working tree source at tested input commit `c664ee5b62b7ae4d0c950a7c493cf0e6bba84b90`)
3. `direct` (Installed wheel built directly)
4. `derived` (Installed wheel built from unpacked sdist without Git on PATH)

### 3.1 Scanner & Callback Scenarios (`reproduce_reviewer_finding.py`)

| Scenario | PR #160 Baseline (`source160-unfixed`) | Fixed Correction (`source-fixed` / `direct` / `derived`) | Status |
|---|---|---|---|
| **Case 1: Appending list** (init 2, appends 1000) | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 2: Changing length** (init 2, appends 500) | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 3: Same final length** (init 2, appends 1000) | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 4: Deceptive `__len__`** (reports 2, yields 1000) | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 5: Exceeds during snapshot** | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | queue: 1, snapshot: 2, used: 2, `INPUT_LIMIT` | PASS |
| **Case 6: Exact boundary** (legitimate list & tuple) | list_used: 6, tuple_used: 6 | list_used: 6, tuple_used: 6 | PASS |
| **Case 7: Dataclass capacity** | queue: 1, used: 2, `INPUT_LIMIT` | queue: 1, used: 2, `INPUT_LIMIT` | PASS |
| **Case 8: Broken iterator** | **UNHANDLED `RuntimeError`** (escapes) | **`INPUT_LIMIT`**, used: 2 | **RESOLVED** |
| **Case 8: Broken dict values** | **UNHANDLED `ValueError`** (escapes) | **`INPUT_LIMIT`**, used: 2 | **RESOLVED** |
| **Case 8: Broken dict keys** | **UNHANDLED `KeyError`** (escapes) | **`INPUT_LIMIT`**, used: 2 | **RESOLVED** |
| **Case 8: Broken dataclass attr** | **UNHANDLED `RuntimeError`** (escapes) | **`INPUT_LIMIT`**, used: 2 | **RESOLVED** |
| **Case 9: Single refusal charge** | list_used: 2, dict_used: 2 | list_used: 2, dict_used: 2 | PASS |
| **Real Store Relation** (1000 members) | queue: 6, snap: 2, used: 9, db_rows: 0, fence: true | queue: 6, snap: 2, used: 9, db_rows: 0, fence: true | PASS |

In all fixed cohorts (`source-fixed`, `direct`, `derived`):
- All 4 unhandled callback exception vectors fail closed cleanly with `INPUT_LIMIT` and `used_work == 2`.
- `max_queue_len` is strictly bounded (`<= 1` for direct inputs, `<= 6` for store relations).
- `max_snapshot_len` is strictly bounded (`<= 2`).
- SQLite database row state is unchanged (`db_rows == 0`), transfer fences remain intact, transaction rolls back cleanly.

---

## 4. Packaging Contract & Sdist Equivalence

- **Sdist Budgets** (`scripts/check_sdist_contract.py` on `repo_catalog-0.2.0.tar.gz`):
  - Compressed size: 703,102 bytes (<= budget 2,097,152 bytes)
  - Unpacked size: 6,046,824 bytes (<= budget 8,388,608 bytes)
  - Member count: 164 (<= budget 512 members)
  - Tar stream bytes: 6,184,960 bytes (<= budget 8,922,624 bytes)
  - Contract verdict: **PASSED**
- **Wheel Bit-Level Equivalence**:
  - Direct wheel: `repo_catalog-0.2.0-py3-none-any.whl`, 791,865 bytes, SHA-256 `ed424c735d5ffe355c7c4d991f61e4487f90593ad723d38af70572564fb6401d`, 164 members.
  - Derived wheel (built from unpacked sdist without Git on PATH): 791,865 bytes, SHA-256 `ed424c735d5ffe355c7c4d991f61e4487f90593ad723d38af70572564fb6401d`, 164 members.
  - `equal_full_zip_bytes`: **true** (100% bit-for-bit identical).

---

## 5. Automated Regression Test Execution

- **Focused Admission & Scanner Regressions**:
  - `tests/unit/test_admission_scanner_budget.py` (29 passed in 41.56s)
  - Tests verify bounded queue lengths, bounded snapshot sizes, refusal single-charging, dataclass capacity reservation, and callback failure modes.
- **Broad Regression Suite**:
  - Executed 953 test nodes in `tests/unit/` covering admission, context, domain, and transfer adapters.
  - 748 passed, 47 failed, 158 errors (all 47 failures and 158 errors match inherited baseline failures in Transfer/Wire adapters). Zero new or changed failures introduced.
- **Linter & Formatter**:
  - `ruff check src tests scripts` (0 errors)
  - `ruff format --check src tests scripts` (455 files clean)

---

## 6. Commit Separation & Provenance Integrity

- **Tested Input**:
  - Commit: `c664ee5b62b7ae4d0c950a7c493cf0e6bba84b90`
  - Tree: `737f20d5a2b98aad1272b92040731c7e21c1c05e`
  - Contains all executable product code and test suite additions.
- **Final Submission**:
  - Contains tested input plus evidence artifacts located strictly in `docs/implementation/evidence/adr0031-i155-m01-final-correction-20261024/`.
  - Zero modifications to executable product code or tests post-validation.
  - All historical evidence directories remain intact and explicitly superseded.
