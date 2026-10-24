# I155-M01 Final Author Correction Verification Matrix

Author final correction matrix verifying the remediation of user callback exception containment, dataclass member capacity reservation, and packaging reproducibility against PR #160 (`fix/adr0031-i155-m01-iterator-followup-20261024`, commit `1a508cac857b7d828920f68500128edeae7594f6`).

## 1. Implementation Requirements Matrix

| Req ID | Requirement Description | Implementation Location | Verification Evidence |
|---|---|---|---|
| **REQ-FIN-1** | Element-by-element iterator traversal protects against unhandled iterator/callback exceptions | `context_admission.py:401-414` (`try ... for child in it ... except Exception`) | `test_user_callback_exception_fails_closed_without_leak`, `reproduce_reviewer_finding.py::case_8` (returns `INPUT_LIMIT`, used_work=2) |
| **REQ-FIN-2** | Dictionary value and key iteration protects against custom callback exceptions | `context_admission.py:488-508` (`try ... except Exception`) | `test_user_callback_exception_fails_closed_without_leak`, `reproduce_reviewer_finding.py::case_8` (values/keys fail closed with `INPUT_LIMIT`) |
| **REQ-FIN-3** | Dataclass reflection and member attribute access (`getattr`) protected against callback exceptions | `context_admission.py:455-474` (`try ... except Exception`) | `test_user_callback_exception_fails_closed_without_leak`, `reproduce_reviewer_finding.py::case_8` (attribute access fails closed with `INPUT_LIMIT`) |
| **REQ-FIN-4** | Dataclass member capacity pre-reservation bounds pending queue allocation | `context_admission.py:461-466` (`count > rem_work or len(pending) + count > rem_work`) | `test_dataclass_capacity_and_queue_bounded`, `reproduce_reviewer_finding.py::case_7` (`max_queue_len <= 1`) |
| **REQ-FIN-5** | Strict 1-unit fixed refusal charge without double-charging across all callback exceptions and mutations | `context_admission.py:413, 460, 465, 473, 504` (`charge(work=1)`) | All mutation and callback test vectors verify `used_work == 2` |
| **REQ-FIN-6** | Distinction between internal queue/snapshot bounds and arbitrary Python callback allocations | Documented in `REPORT.md` Section 3 and supported input contract | Internal `pending` and `children` strictly bounded; arbitrary callback space clearly separated |
| **REQ-FIN-7** | Preservation of supported input grammar without altering Accepted ADRs (0031/0032/0033) | Supported types: int, float, str, bytes, bool, None, tuple, list, frozenset, dict, dataclass | `test_exact_sufficient_budget_vs_one_below`, `reproduce_reviewer_finding.py::case_6` |
| **REQ-FIN-8** | Exact positive boundaries preserved for legitimate data structures | `context_admission.py:392-393, 460` | `test_exact_sufficient_budget_vs_one_below` (list/tuple work=6), `test_dataclass_capacity_and_queue_bounded` (work=7) |
| **REQ-FIN-9** | Real Store relation transaction rollback, transfer fences intact, 0 row changes | `Context.owned_transaction` and native SQLite isolation | `reproduce_reviewer_finding.py::real_store_relation` (db_rows=0, fence=true, in_tx=false) |
| **REQ-FIN-10** | Packaging contract & sdist reproducibility: direct wheel == derived wheel | `scripts/check_sdist_contract.py`, build scripts | `build-measurements.json` (`equal_full_zip_bytes: true`), `wheel-members.json` (164 members) |

---

## 2. Test Vector Coverage Matrix

| Vector ID | Description | Test Identifier | Baseline PR160 | Fixed Correction (`source-fixed` / `direct` / `derived`) |
|---|---|---|---|---|
| **V01-V26** | Retained 26 regression test vectors from PR #158 and PR #160 | `tests/unit/test_admission_scanner_budget.py` (26 tests) | PASS | **PASS** (all 26 pass cleanly) |
| **V27** | Dataclass capacity pre-reservation and queue bounded | `test_dataclass_capacity_and_queue_bounded` | N/A (untested) | **PASS** (queue <= 1, used 2 on short budget; work 7 admits cleanly) |
| **V28** | Broken iterator exception containment | `test_user_callback_exception_fails_closed_without_leak` | UNHANDLED `RuntimeError` | **PASS** (trapped, `INPUT_LIMIT`, used_work=2) |
| **V29** | Broken dict values & keys exception containment | `test_user_callback_exception_fails_closed_without_leak` | UNHANDLED `ValueError` / `KeyError` | **PASS** (trapped, `INPUT_LIMIT`, used_work=2) |
| **V30** | Broken dataclass attribute access exception containment | `test_user_callback_exception_fails_closed_without_leak` | UNHANDLED `RuntimeError` | **PASS** (trapped, `INPUT_LIMIT`, used_work=2) |
| **V31** | List subclass appending during `__iter__` (Case 1 & Case 3) | `reproduce_reviewer_finding.py::case_1`, `case_3` | PASS (queue 1, snap 2, used 2) | **PASS** (queue 1, snap 2, used 2) |
| **V32** | Changing length during iteration (Case 2) | `reproduce_reviewer_finding.py::case_2` | PASS (queue 1, snap 2, used 2) | **PASS** (queue 1, snap 2, used 2) |
| **V33** | Deceptive `__len__` (Case 4) | `reproduce_reviewer_finding.py::case_4` | PASS (queue 1, snap 2, used 2) | **PASS** (queue 1, snap 2, used 2) |
| **V34** | Exceeds during snapshot (Case 5) | `reproduce_reviewer_finding.py::case_5` | PASS (queue 1, snap 2, used 2) | **PASS** (queue 1, snap 2, used 2) |
| **V35** | Exact boundaries for legitimate list & tuple (Case 6) | `reproduce_reviewer_finding.py::case_6` | PASS (work 6) | **PASS** (work 6) |
| **V36** | Dataclass capacity check in reproducer (Case 7) | `reproduce_reviewer_finding.py::case_7` | PASS (queue 1, used 2) | **PASS** (queue 1, used 2) |
| **V37** | Callback containment across all 4 types in reproducer (Case 8) | `reproduce_reviewer_finding.py::case_8` | 4 UNHANDLED exceptions | **PASS** (all 4 return `INPUT_LIMIT`, used_work=2) |
| **V38** | Single refusal charge across list and dict mutation (Case 9) | `reproduce_reviewer_finding.py::case_9` | PASS (used 2) | **PASS** (used 2) |
| **V39** | Real Store relation with armed list (1000 members) | `reproduce_reviewer_finding.py::real_store_relation` | PASS (queue 6, snap 2, used 9, db 0) | **PASS** (queue 6, snap 2, used 9, db 0) |
| **V40** | Ruff linter & formatter | `ruff check`, `ruff format --check` | PASS (0 errors) | **PASS** (0 errors across 455 files) |
