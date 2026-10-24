# I155-M01 Requirement and Test Verification Matrix

Author correction matrix verifying the resolution of I155-M01 (Admission scanner queue allocation without remaining budget reservation).

## 1. Implementation Requirements Matrix (Section 4)

| Req ID | Requirement Description | Implementation Location | Verification Evidence |
|---|---|---|---|
| **REQ-1** | No variable-sized child queue constructed after relevant remaining budget is exhausted | `context_admission.py:374-380` (`reserve_children`), `390-398` (strings), `404-411` (dataclass), `414-419` (tuples/lists/frozensets), `421-428` (dicts) | `test_admission_scanner_budget.py::test_i155_m01_real_store_counterexample_prevented`, `test_large_tuple_list_frozenset_queue_never_constructed_without_budget`; Store Case 1 `queue_max` 1002 → 6 |
| **REQ-2** | Any variable work performed before refusal must be accounted for | `context_admission.py:362-368` (`charge`), `385` (pop charge), `401` (string chunk charge) | `test_exact_sufficient_budget_vs_one_below`, `test_strings_chunking_and_unicode_precedence`; `budget.used_work` matches exact sequence |
| **REQ-3** | Refused reservation incurs contractually defined fixed refusal-accounting unit (1 unit); distinguished from unauthorized variable work | `context_admission.py:377` (`charge(work=1)`), `396` (`charge(work=1)`), `408` (`charge(work=1)`) | `test_i155_m01_real_store_counterexample_prevented` (`used_work=10001` at `limit=10000`), `test_i155_m01_real_store_selection_work_limit_7` (`used_work=8` at `selection=7`) |
| **REQ-4** | No work already performed is refunded after rejection or rollback | `context_admission.py:362-368` (invokes `budget.charge` directly without rollback or decrement) | `test_repeated_admission_and_exact_replay`, `tests/unit/test_context_admission.py::test_request_budget_charges_failures_and_rollbacks_without_refunds` |
| **REQ-5** | Preserve legitimate exact-boundary successes and completed independently admissible semantic units | `context_admission.py:375` (`count <= rem and len(pending) + count <= rem`) | `test_exact_sufficient_budget_vs_one_below` across 9 parameterized boundary shapes |
| **REQ-6** | Preserve bounded cycle/depth behavior and canonical identity parsing | `context_admission.py:386-388` (`depth > depth_limit`) | `test_nested_depth_and_cyclic_reference_stops`, `test_context_admission_bounds_i6a.py`, `study.py` (22 codec cases preserved) |
| **REQ-7** | Do not double-charge the same work when moving accounting from traversal time to reservation time | `reserve_children` validates capacity and charges 1 unit ONLY on refusal; actual traversal charges 1 per popped node | `test_exact_sufficient_budget_vs_one_below` (verifies exact equality between sufficient budget work and actual work consumed) |
| **REQ-8** | Do not allow input mutation between reservation and use to bypass bounds | `context_admission.py:415-418` (`tuple(item)` snapshot + re-check), `422-426` (`values`/`keys` snapshot + re-check) | `test_mutation_defense_iterator_mismatch` |
| **REQ-9** | Maintain typed `INPUT_LIMIT` refusal and established authorization/selection/native-semantics precedence | `context_admission.py:367`, `378`, `397`, `409` (`raise AdmissionRefused("INPUT_LIMIT")`) | `test_permission_denial_and_selection_omission`, `tests/unit/test_context_admission.py` (42/42 PASS) |
| **REQ-10** | Preserve existing policy leases, outer transaction rollback, and source evidence | `Context.owned_transaction` context manager preserved, `DenyPolicy` untouched | `test_i155_m01_real_store_counterexample_prevented` (`sql[-1] == "ROLLBACK"`, `policy_calls == 0`, `rows_after == 0`) |

---

## 2. Test Vector Coverage Matrix (Section 5)

| Category # | Vector Description | Test Identifier | Result |
|---|---|---|---|
| **V01** | Saved 1,000-member real Store case | `test_admission_scanner_budget.py::test_i155_m01_real_store_counterexample_prevented` | **PASS** (queue 6 <= 6, used 10001) |
| **V02** | Prior work 9,992 of 10,000 (8 remaining) | `test_admission_scanner_budget.py::test_i155_m01_real_store_counterexample_prevented` | **PASS** (refuses at 10001, queue max 6) |
| **V03** | Completely exhausted prior work (0 remaining) | `test_admission_scanner_budget.py::test_i155_m01_real_store_exhausted_prior_work` | **PASS** (refuses on first pop, queue max 1) |
| **V04** | Selection work limit 7 | `test_admission_scanner_budget.py::test_i155_m01_real_store_selection_work_limit_7` | **PASS** (queue 6 <= 6, used 8) |
| **V05** | Zero remaining work / zero work limit | `test_admission_scanner_budget.py::test_i155_m01_zero_work_limit` | **PASS** (refuses at used 1, queue max 1) |
| **V06** | Exact sufficient budget | `test_admission_scanner_budget.py::test_exact_sufficient_budget_vs_one_below[*]` | **PASS** (9 container shapes succeed) |
| **V07** | One unit below sufficient budget | `test_admission_scanner_budget.py::test_exact_sufficient_budget_vs_one_below[*]` | **PASS** (9 container shapes refuse with INPUT_LIMIT) |
| **V08** | Small legitimate inputs | `test_admission_scanner_budget.py::test_exact_sufficient_budget_vs_one_below[empty-*]` | **PASS** (empty tuple/list/dict succeed) |
| **V09** | Large tuples, lists, and frozensets | `test_admission_scanner_budget.py::test_large_tuple_list_frozenset_queue_never_constructed_without_budget` | **PASS** (10,000 items refused with queue_max 1) |
| **V10** | Dictionary key and value expansion | `test_admission_scanner_budget.py::test_dictionary_key_value_expansion_bounded` | **PASS** (5,000 entries refused with queue_max 1) |
| **V11** | Dataclass member expansion | `test_admission_scanner_budget.py::test_dataclass_member_expansion` | **PASS** (50-field dataclass bounded by remaining budget) |
| **V12** | Strings, escaped Unicode, and invalid Unicode | `test_admission_scanner_budget.py::test_strings_chunking_and_unicode_precedence` | **PASS** (4096-byte chunking, UTF-8 surrogate check) |
| **V13** | Nested containers and depth/cycle limits | `test_admission_scanner_budget.py::test_nested_depth_and_cyclic_reference_stops` | **PASS** (depth > depth_limit refuses, cycles stop) |
| **V14** | Repeated admission and exact replay | `test_admission_scanner_budget.py::test_repeated_admission_and_exact_replay` | **PASS** (two successive relations charge and persist cleanly) |
| **V15** | Permission denial and selection omission | `test_admission_scanner_budget.py::test_permission_denial_and_selection_omission` | **PASS** (authenticator/selection precedence verified) |
| **V16** | Exception cleanup, no partial SQL, policy release | `test_admission_scanner_budget.py::test_repeated_admission_and_exact_replay` & `store_case.py` | **PASS** (fences intact, rollback verified, zero leaks) |
