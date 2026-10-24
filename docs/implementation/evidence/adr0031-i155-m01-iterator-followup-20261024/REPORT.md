# Author Follow-up Correction Report: Admission Scanner Iterator Mutation & CI Remediation

- **Role**: Author Follow-up Correction (Draft PR)
- **Review Target / Base Branch**: `fix/adr0031-i155-m01-admission-scanner` (HEAD: `1888b9c85de399e887b11000b09a01fe2e9936b8`, Tree: `090c6a678c96ec298ade1ff0a2c7bc14fc463653`)
- **Fix Branch**: `fix/adr0031-i155-m01-iterator-followup-20261024`
- **Reviewed GitHub Codex Review**: [PR #158 Review Comment discussion_r4366012662](https://github.com/TakashiSasaki/git-repo-db/pull/158#discussion_r4366012662)
- **Hosted CI Failure**: [Run 40051883585](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40051883585) (Job 120746140614, Ruff I001 / F401)
- **Verdict**: **INCOMPLETE / FAIL** (Author correction submitted as Draft PR for non-Author independent re-review; no self-approval)

---

## 1. Executive Summary & Defect Root Cause

### 1.1 Codex Review Finding (P2: Unbounded Snapshots & Post-Snapshot Mutation Bypass)
GitHub Codex identified a P2 boundary defect in PR #158's initial implementation:
1. **Unbounded Intermediate Materialization**: In `charge_input()`, container traversal executed `children = tuple(item)` before validating the resulting child count. If an iterable's `__iter__` yields an arbitrarily large number of elements (or mutates during iteration), `tuple(item)` immediately materializes all yielded children in memory, bypassing the work budget during snapshot creation.
2. **Post-Snapshot Mutation Bypass**: In PR #158, the secondary reservation check executed `if len(children) != len(item): reserve_children(len(children))`. If a container subclass (such as a `list` subclass initially containing 2 elements) mutates itself during `__iter__` by appending 1,000 elements, both `len(children)` and `len(item)` evaluate to 1,002 after `tuple(item)`. Because the lengths match (`1002 == 1002`), the secondary reservation check is skipped, allowing `pending.extend()` to expand the pending queue to 1,002 entries before eventual refusal.

### 1.2 Hosted Development CI Failure
Hosted Development CI [run 40051883585](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40051883585) failed Ruff linting:
- `I001`: Import block un-sorted / un-formatted at `tests/unit/test_admission_scanner_budget.py:11`
- `F401`: `json` imported but unused at `tests/unit/test_admission_scanner_budget.py:12`

---

## 2. Implementation Remediation

### 2.1 Bounded Snapshot Traversal (`snapshot_sequence`)
In `src/repo_catalog/domain/context_admission.py`, unbounded `tuple(item)` snapshotting was replaced with `snapshot_sequence()`:
1. **Initial Pre-reservation**: Obtains `declared = len(container)` and enforces `reserve_children(declared)` against remaining cumulative and selection budgets before beginning iteration.
2. **Immutable Fast Path**: If `type(container) is tuple`, returns `container` directly with zero copy and zero extra allocation.
3. **Element-by-Element Budget Enforcement**: Iterates `container` element by element. Before accepting each child into the snapshot, verifies:
   ```python
   if len(children) >= declared or len(pending) + len(children) + 1 > remaining_work():
       charge(work=1)
       raise AdmissionRefused("INPUT_LIMIT")
   children.append(child)
   ```
   If the iterator yields more elements than declared, or if admitting another element would breach remaining work, traversal halts immediately, charges the contractual 1-unit fixed refusal fee, and raises `AdmissionRefused("INPUT_LIMIT")` without allocating subsequent items.
4. **Post-Traversal Invariant Checks**: Verifies `len(children) == declared` and `len(container) == declared`. Any discrepancy (such as misleading `__len__` or container mutation) triggers an immediate 1-unit refusal charge and `INPUT_LIMIT`.
5. **Dictionary Traversal Protection**: Dictionaries similarly enforce element-by-element capacity verification during key and value iteration.

### 2.2 Ruff CI Cleanup
- Removed unused `json` import from `tests/unit/test_admission_scanner_budget.py`.
- Formatted and sorted imports adhering to project Ruff conventions.
- Both `ruff check src tests scripts` and `ruff format --check src tests scripts` pass with zero errors across all 455 files.

---

## 3. Before / After Measurements Across Cohorts

All probes were executed across four cohorts:
1. `source158-unfixed` (Control: checkout at base HEAD `1888b9c85de399e887b11000b09a01fe2e9936b8`)
2. `source-fixed` (Working tree source)
3. `direct` (Installed wheel built directly)
4. `derived` (Installed wheel built from unpacked sdist without Git on PATH)

### 3.1 Reviewer Mutation Scenarios (`reproduce_reviewer_finding.py`)

| Scenario | PR #158 Baseline (`source158-unfixed`) | Fixed Correction (`source-fixed` / `direct` / `derived`) |
|---|---|---|
| **Case 1: Appending list** (init 2, appends 1000, max_work 3) | `max_queue: 1002`, `max_snapshot: 1002`, `used: 4` **(DEFECT)** | `max_queue: 1`, `max_snapshot: 2`, `used: 2` **(RESOLVED)** |
| **Case 2: Changing length** (init 2, appends 500, max_work 3) | `max_queue: 1`, `max_snapshot: 500`, `used: 2` **(DEFECT)** | `max_queue: 1`, `max_snapshot: 2`, `used: 2` **(RESOLVED)** |
| **Case 3: Same final length** (init 2, appends 1000, final 1002) | `max_queue: 1002`, `max_snapshot: 1002`, `used: 4` **(DEFECT)** | `max_queue: 1`, `max_snapshot: 2`, `used: 2` **(RESOLVED)** |
| **Case 4: Deceptive `__len__`** (reports 2, yields 1000) | `max_queue: 1000`, `max_snapshot: 1000`, `used: 4` **(DEFECT)** | `max_queue: 1`, `max_snapshot: 2`, `used: 2` **(RESOLVED)** |
| **Case 5: Exceeds during snapshot** (before `pending.extend`) | `max_queue: 1`, `max_snapshot: 1000`, `used: 2` **(DEFECT)** | `max_queue: 1`, `max_snapshot: 2`, `used: 2` **(RESOLVED)** |
| **Case 6: Exact boundary** (legitimate list & tuple, max_work 6) | `list_used: 6`, `tuple_used: 6` **(PASS)** | `list_used: 6`, `tuple_used: 6` **(PASS)** |
| **Real Store Relation** (`Context.owned_transaction`, armed list) | `max_queue: 1006`, `max_snapshot: 1002`, `used: 26` **(DEFECT)** | `max_queue: 6`, `max_snapshot: 2`, `used: 9` **(RESOLVED)** |

In all fixed cohorts:
- `max_queue_len` is strictly bounded (`<= 1` for direct calls, `<= 6` for store relations).
- `max_snapshot_len` is strictly bounded (`<= 2`).
- Fixed refusal charge is strictly 1 unit (`used_work == 2` for root containers).
- Zero rows added to SQLite database (`db_rows == 0`), transfer fences intact, transaction rolled back cleanly.

### 3.2 Original Store Cases (`store_case.py`)

| Case | PR #158 Baseline | Fixed Cohorts |
|---|---|---|
| Case 0 (16 members, rem 8, sel 10000) | used: 10001, queue_max: 6 | used: 10001, queue_max: 6 |
| Case 1 (1000 members, rem 8, sel 10000) | used: 10001, queue_max: 6 | used: 10001, queue_max: 6 |
| Case 2 (1000 members, rem 0, sel 10000) | used: 10001, queue_max: 1 | used: 10001, queue_max: 1 |
| Case 3 (1000 members, rem 10000, sel 7) | used: 8, queue_max: 6 | used: 8, queue_max: 6 |

---

## 4. Packaging Contract & Sdist Verification

- `scripts/check_sdist_contract.py` evaluated the generated sdist archive `repo_catalog-0.2.0.tar.gz`:
  - Compressed size: 703,078 bytes (<= budget 2,097,152 bytes)
  - Unpacked size: 6,046,103 bytes (<= budget 8,388,608 bytes)
  - Member count: 164 (<= budget 512 members)
  - Tar stream: 6,184,960 bytes (<= budget 8,922,624 bytes)
  - Status: **PASSED**
- **Wheel Equivalence**:
  - The derived wheel built from unpacked sdist without Git on `PATH` is byte-for-byte identical to the direct wheel (`repo_catalog-0.2.0-py3-none-any.whl`, 791,842 bytes, SHA-256 `af11b7e36d104f4c6867a314416e5dbab5b66342502a0a8260896c9916433b0a`).

---

## 5. Automated Regression Test Suite

- `tests/unit/test_admission_scanner_budget.py`:
  - Total tests: 26 (21 retained original tests + 5 new mutation regression tests)
  - Outcome: 26 **PASSED**, 0 failed
- Related admission suites:
  - `test_context_admission.py`: 48 PASSED
  - `test_context_admission_bounds_i6a.py`: 2 PASSED
  - `test_context_oid_admission_i6a.py`: 12 PASSED
- Baseline inherited non-successes (279 failures, 20 errors under native SQLite 3.45.1) preserved without regressions.

---

## 6. Handoff for Independent Review

1. **Target Branch**: `fix/adr0031-i155-m01-admission-scanner` (PR #158)
2. **Proposed Branch**: `fix/adr0031-i155-m01-iterator-followup-20261024`
3. **Draft Pull Request**: Created directly against `fix/adr0031-i155-m01-admission-scanner`.
4. **Reproduction Commands**:
   ```bash
   PYTHONPATH=src:. /home/ubuntu/venv/bin/python docs/implementation/evidence/adr0031-i155-m01-iterator-followup-20261024/run_experiments.py
   pytest tests/unit/test_admission_scanner_budget.py -v
   ruff check src tests scripts
   ruff format --check src tests scripts
   ```
