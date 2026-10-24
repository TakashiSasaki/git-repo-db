# I155-M01 Follow-up Requirement and Test Verification Matrix

Author follow-up correction matrix verifying the remediation of GitHub Codex review finding [discussion_r4366012662](https://github.com/TakashiSasaki/git-repo-db/pull/158#discussion_r4366012662) and hosted Development CI Ruff failures ([run 40051883585](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40051883585)).

## 1. Implementation Requirements Matrix

| Req ID | Requirement Description | Implementation Location | Verification Evidence |
|---|---|---|---|
| **REQ-FOL-1** | Bounded snapshot consumption: element-by-element capacity enforcement during iterator traversal | `context_admission.py:382-423` (`snapshot_sequence`) | `reproduce_reviewer_finding.py::case_1`, `case_2`, `case_5`; snapshot size bounded at `<= 2` (was 1002/500/1000) |
| **REQ-FOL-2** | Defense against list subclass appending children during `__iter__` | `context_admission.py:400-410` | `test_mutation_defense_appending_during_iteration_bounded`; `max_queue_len <= 1`, `max_snapshot_len <= 2` |
| **REQ-FOL-3** | Defense against matching final length after mutation (`len(children) == len(item)`) | `context_admission.py:400-410` (bounds check on each yielded item) | `reproduce_reviewer_finding.py::case_3_same_final_length`; `max_queue_len <= 1`, `max_snapshot_len <= 2` |
| **REQ-FOL-4** | Defense against deceptive or dynamically changing `__len__` | `context_admission.py:401-417` (`len(children) != declared` and `len(container) != declared`) | `test_mutation_defense_deceptive_or_dynamic_len_bounded`; `max_queue_len <= 1`, `max_snapshot_len <= 2` |
| **REQ-FOL-5** | Abort snapshot creation before variable-sized allocation or `pending.extend` | `context_admission.py:404-406` | `test_mutation_defense_snapshot_bounded_before_queue_extend`; `pending` queue extended with 0 items |
| **REQ-FOL-6** | Contractual 1-unit fixed refusal-accounting charge without double charging | `context_admission.py:377, 405, 412, 417, 469` (`charge(work=1)`) | All mutation tests verify `used_work == 2` (1 initial root pop + 1 fixed refusal charge) |
| **REQ-FOL-7** | Preserve exact positive boundaries for legitimate containers | `context_admission.py:392-393` (fast path for tuple, bounded pass for list) | `test_exact_sufficient_budget_vs_one_below`, `reproduce_reviewer_finding.py::case_6` |
| **REQ-FOL-8** | Real Store relation transaction rollback, transfer fences intact, 0 row changes | `Context.owned_transaction` and native SQLite isolation | `test_mutation_defense_real_store_relation_armed_list`, `reproduce_reviewer_finding.py::real_store_relation` |
| **REQ-FOL-9** | Resolve hosted Development CI Ruff failures (I001 import ordering, F401 unused `json`) | `tests/unit/test_admission_scanner_budget.py:11-34` | `ruff check src tests scripts` (0 errors), `ruff format --check src tests scripts` (455 clean) |
| **REQ-FOL-10** | Retain all 21 original scanner tests and PR #156 source/installed vectors | `tests/unit/test_admission_scanner_budget.py` (26 total passed) | `pytest tests/unit/test_admission_scanner_budget.py` (26/26 PASS), `store_case.py` (4/4 PASS across 4 cohorts) |

---

## 2. Test Vector Coverage Matrix

| Category # | Vector Description | Test Identifier | Baseline PR158 | Fixed Correction |
|---|---|---|---|---|
| **V01-V16** | Retained original 16 test vector categories from PR #158 | `tests/unit/test_admission_scanner_budget.py` (21 tests) | PASS | **PASS** (all 21 pass cleanly) |
| **V17** | List subclass appending 1,000 items during `__iter__` (Case 1 & Case 3) | `test_mutation_defense_appending_during_iteration_bounded` | FAIL (queue 1002, snapshot 1002) | **PASS** (queue <= 1, snapshot <= 2, used 2) |
| **V18** | Declared small length changing during iteration (Case 2) | `test_mutation_defense_changing_length_during_iteration_bounded` | FAIL (snapshot 500) | **PASS** (queue <= 1, snapshot <= 2, used 2) |
| **V19** | Misleading or dynamic `__len__` (Case 4) | `test_mutation_defense_deceptive_or_dynamic_len_bounded` | FAIL (queue 1000, snapshot 1000) | **PASS** (queue <= 1, snapshot <= 2, used 2) |
| **V20** | Snapshot creation exceeds remaining work before `pending.extend` (Case 5) | `test_mutation_defense_snapshot_bounded_before_queue_extend` | FAIL (snapshot 1000) | **PASS** (queue <= 1, snapshot <= 2, used 2) |
| **V21** | Real Store relation admission with `ArmedMutatingList` | `test_mutation_defense_real_store_relation_armed_list` | FAIL (queue 1006, snapshot 1002) | **PASS** (queue <= 6, snapshot <= 2, 0 rows, rollback) |
| **V22** | Exact-boundary legitimate list and tuple | `test_exact_sufficient_budget_vs_one_below` & Case 6 | PASS (used 6) | **PASS** (used 6) |
| **V23** | Ruff linter and import ordering | `ruff check src tests scripts` | FAIL (I001, F401) | **PASS** (0 errors) |
| **V24** | Ruff formatter | `ruff format --check src tests scripts` | FAIL (1 reformat) | **PASS** (0 reformat) |
