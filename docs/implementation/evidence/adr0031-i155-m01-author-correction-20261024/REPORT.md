# Author Correction Report: I155-M01 Admission Scanner Work-Budget Violation

- **Role**: Author Correction (Draft PR)
- **Review Target**: `review/adr0031-i6b-sdist-c0-independent-20261024` (HEAD: `d8d7138dd4bea6f5274b1b0df79699ff6a2f315e`)
- **Fix Branch**: `fix/adr0031-i155-m01-admission-scanner`
- **Reviewed Source #155 HEAD**: `fee364c6d61a5feebf08dbdd830a5a57ee2d872b` (Tree: `ace7e44cd89194d189a30a0aa6cf513a45b3b87c`)
- **Verdict**: **INCOMPLETE / FAIL** (Author correction submitted as Draft PR for non-Author independent re-review; no self-approval)

---

## 1. Executive Summary & Defect Root Cause

Independent Review PR #156 identified Medium finding **I155-M01**: the I6-A Admission input scanner in `src/repo_catalog/domain/context_admission.py` allocated a variable-sized child queue (e.g. extending from 2 to 1,002 entries) after remaining cumulative work budget or selection work budget had already been exhausted.

### Root Cause Analysis
1. **Total vs. Remaining Work Check**: In `ContextAdmissionService.charge_input()`, container length checks performed `if len(item) > context.budget.work_limit:`. When `work_limit = 10000`, `prior_work = 9992`, and `len(item) = 1000`, the remaining work was only 8 units, but `1000 > 10000` evaluated to `False`. The queue was extended with all 1,000 children prior to checking if sufficient work remained.
2. **Delayed Selection Budget Evaluation**: `context.selection.max_work` was only evaluated at the bottom of the `while pending:` loop. In the counterexample with `selection.max_work = 7`, popping the container node charged 1 work unit, bringing `used_work` to 8. Because the container branch executed `pending.extend()` before the loop bottom was reached, 1,000 child elements were enqueued at `used_work = 8`, prior to the loop bottom raising `AdmissionRefused("INPUT_LIMIT")`.

---

## 2. Implementation Remediation

The remediation in `src/repo_catalog/domain/context_admission.py` enforces strict pre-reservation of work and byte limits prior to any variable allocation:

1. **Immediate Selection Bound Enforcement**:
   ```python
   def charge(*, work=0, bytes_=0):
       context.budget.charge(work=work, bytes_=bytes_)
       if (
           context.budget.used_work > context.selection.max_work
           or context.budget.used_bytes > context.selection.max_bytes
       ):
           raise AdmissionRefused("INPUT_LIMIT")
   ```
2. **Remaining Work Calculation**:
   ```python
   def remaining_work():
       return (
           min(context.budget.work_limit, context.selection.max_work)
           - context.budget.used_work
       )
   ```
3. **Child Queue Pre-Reservation (`reserve_children`)**:
   ```python
   def reserve_children(count):
       rem = remaining_work()
       if count > rem or len(pending) + count > rem:
           charge(work=1)
           raise AdmissionRefused("INPUT_LIMIT")
   ```
4. **Protected Container Traversal & Mutation Defense**:
   - `tuple`, `list`, `frozenset`: Evaluates `reserve_children(len(item))`, takes a shallow snapshot `children = tuple(item)`, re-verifies length against mutation, and only then extends `pending`.
   - `dict`: Evaluates `reserve_children(2 * len(item))`, captures `values = tuple(item.values())` and `keys = tuple(item.keys())`, re-checks total length, and extends `pending`.
   - Dataclass: Evaluates remaining cumulative work against `len(fields(item))`, charging 1 refusal unit if capacity is insufficient before extending `pending`.
   - Strings: Evaluates `remaining_work() <= 0 or remaining_bytes <= 0` before slicing and encoding 4096-byte chunks, charging 1 refusal unit on exhausted budget.

---

## 3. Real Store Counterexample Verification

We evaluated the unchanged independent counterexample driver (`store_case.py`) across all four cohorts:
1. `source155-unfixed` (Control, extracted from base commit `d8d7138dd4bea6f5274b1b0df79699ff6a2f315e`)
2. `source-fixed` (Working tree source checkout)
3. `direct` (Wheel built directly via `hatchling` and installed outside checkout)
4. `derived` (Wheel built from unpacked sdist without Git and installed outside checkout)

### Before / After Measurements

| Cohort | Case 0 (16 members, rem 8, sel 10000) | Case 1 (1000 members, rem 8, sel 10000) | Case 2 (1000 members, rem 0, sel 10000) | Case 3 (1000 members, rem 10000, sel 7) |
|---|---|---|---|---|
| **source155-unfixed** (Control) | used: 10001, queue_max: **18** | used: 10001, queue_max: **1002 (DEFECT)** | used: 10001, queue_max: 1 | used: 8, queue_max: **1002 (DEFECT)** |
| **source-fixed** | used: 10001, queue_max: **6** | used: 10001, queue_max: **6 (RESOLVED)** | used: 10001, queue_max: 1 | used: 8, queue_max: **6 (RESOLVED)** |
| **direct** (Installed Wheel) | used: 10001, queue_max: **6** | used: 10001, queue_max: **6 (RESOLVED)** | used: 10001, queue_max: 1 | used: 8, queue_max: **6 (RESOLVED)** |
| **derived** (Sdist Wheel) | used: 10001, queue_max: **6** | used: 10001, queue_max: **6 (RESOLVED)** | used: 10001, queue_max: 1 | used: 8, queue_max: **6 (RESOLVED)** |

In all fixed cohorts:
- `max_queue_length` is strictly bounded by the fixed dataclass field count (<= 6) and never allocates the 1,000 child elements.
- Case 1 charges exactly 1 fixed refusal-accounting unit (`used_work = 10001`).
- Case 3 charges exactly 1 fixed refusal-accounting unit at the selection boundary (`used_work = 8`).
- Database state remains clean (0 rows added, `in_transaction = False`, `ROLLBACK` issued, Transfer fences intact).
- `study.py` (17 admission cases) confirms `max_queue_length = 1` for all bulk list and dictionary inputs.

---

## 4. Distribution Verification & Packaging Contract

- **Sdist Verification**: `scripts/check_sdist_contract.py` evaluated the generated sdist archive `repo_catalog-0.2.0.tar.gz`:
  - Compressed size: 702,764 bytes (<= budget 2,097,152 bytes)
  - Unpacked size: 6,043,584 bytes (<= budget 8,388,608 bytes)
  - Total members: 164 (<= budget 512 members)
  - Tar stream: 6,174,720 bytes (<= budget 8,922,624 bytes)
  - Status: **PASSED**
- **Wheel Equivalence**:
  - The derived wheel built from unpacked sdist source in an isolated environment without Git on `PATH` is byte-for-byte identical to the direct wheel (`repo_catalog-0.2.0-py3-none-any.whl`, 688,527 bytes, SHA-256 `69d301b44ec2136c1e13cb90c6ca7e6aa546ae9eb38c4f2bb73950efd02a0a2d`).
  - `dist-info/RECORD` integrity and member listings verified cleanly.

---

## 5. HCI-L01 Evidence Precision

PR #156 reported Low finding **HCI-L01** regarding historical whitespace-stripped SHA-256 calculations.
- **Historical Evidence**: All historical evidence files, measurements, and commits are preserved completely untouched.
- **New Evidence**: For all new evidence files generated in this Author correction, SHA-256 hashes are computed strictly over exact complete Git blob bytes (`read_bytes()`, without `.strip()` or text decoding). Both complete-byte SHA-256 digests and Git blob OIDs are recorded in `provenance.json`.

---

## 6. Automated Regression Tests

21 automated regression tests were added in `tests/unit/test_admission_scanner_budget.py`, covering:
- Real store cases (1,000 members, prior work 9,992 and exhausted prior work)
- Selection max_work = 7 boundary
- Zero work limit
- Exact sufficient budget vs. one unit below budget across 9 container shapes
- Large container queue reservation defense (10,000 items)
- Dictionary key/value expansion bounds (5,000 entries)
- Dataclass member expansion bounds
- Strings chunking (4096-byte chunks) and Unicode precedence
- Nested depth and cyclic reference termination
- Repeated admission and exact replay
- Permission denial and selection omission precedence
- Input mutation defense

**Test Outcomes**:
- `tests/unit/test_admission_scanner_budget.py`: 21 executed, 21 **PASSED**, 0 failed
- Existing admission tests (`test_context_admission.py`, `test_context_admission_bounds_i6a.py`, `test_context_oid_admission_i6a.py`): All **PASSED**
- Baseline inherited non-successes (279 failures, 20 errors under ADR 0032 native SQLite 3.45.1) preserved without regressions.

---

## 7. Handoff for Independent Review

1. **Target Branch**: `review/adr0031-i6b-sdist-c0-independent-20261024`
2. **Author Submission**: Draft Pull Request. Non-Author independent review is required to verify the remediation and issue an independent PASS/FAIL determination.
3. **Reproduction Command**:
   ```bash
   PYTHONPATH=src /home/ubuntu/venv/bin/python docs/implementation/evidence/adr0031-i155-m01-author-correction-20261024/run_experiments.py
   pytest tests/unit/test_admission_scanner_budget.py -v
   ```
