# Stage 3 Integration Report: ADR 0031 I6-C Exchange, Scanner Budget Defense, and Minimal Sdist

**Date:** 2026-10-24  
**Author:** Integration Implementation Agent (Author role)  
**Branch:** `integration/adr0031-i6c-scanner-integration-20261024`  
**Base Branch:** `fix/adr0031-i6c-regression-hardening-20261024`  
**Base Commit:** `55de572bdac4b9b90b131d89025b0ed304cd0159` (PR #170 HEAD)  
**Tested Input Commit:** `363eb6fdb8c12f854676f4273ed040968f701b3a`  
**Tested Input Tree:** `3c955abc101b23991da764de3310e6b5a0f99be8`  
**Author Status:** Author-complete  
**Independent Acceptance Verdict:** INCOMPLETE / PENDING_INDEPENDENT_REVIEW  

---

## 1. Executive Summary

This integration completes Stage 3 of the ADR 0031 I6 implementation by unifying two major development lineages on top of the hardened base:
1. **The I6-C Exchange & Authority Lineage**: Full sender package export, finite receiver grants (`DependencySet`), `LocalAuthorizationPolicy`, receiver-local selective admission without core dependency coupling, transaction boundary revocation checks, idempotent replay control, and durable Core-first acquisition failure state.
2. **The Scanner Defense & Minimal Sdist Lineage**: Bounded recursive traversal in `charge_input` with strict work capacity pre-reservation, dataclass selection work limit defense, sequence snapshotting against mutating containers, single refusal charge accounting, and the ADR 0033 minimal product sdist packaging contract with verified bit-for-bit wheel equivalence.
3. **The I6-C Behavioral Verification Suite**: Independent test suite covering all 10 obligations of ADR 0031 I6-C.

All empirical tests across preflight, scanner budgets, packaging contracts, behavioral obligations, scoped access acceptance, and the broader unit suite pass with 100% success (0 failures, 0 errors).

---

## 2. Integration Ledger

### 2.1 Included Lineages & Commit Identities

| Lineage / Component | Source PR / Ref | Source Commit SHA | Key Features Integrated |
|:---|:---|:---|:---|
| **Base: I6-C Comparator Correction** | PR #170 | `55de572bdac4b9b90b131d89025b0ed304cd0159` | Strict failure signature comparator (`scripts/compare_access_regressions.py`), manifest partition, pytest exit code checking |
| **I6-C Regression Hardening** | PR #168 | `3a1f112331c87747249f38af370160adc0de108a` | Two-stream CI workflow separation, `scripts/preflight_access.py`, single-command collection signature preservation |
| **I6-C Behavioral Verification** | PR #169 | `634d8f63084cee578aa7beafcd27485a6da8e37a` | `tests/integration/access/test_i6c_behavioral_verification.py` (10 obligations) |
| **Scanner Line: Dataclass Selection** | PR #165 (reviewed #167) | `d81951868ac4fc252f8c0f38c22cf2c38d6146d4` | Dataclass reflection & member capacity pre-reservation against selection work limit |
| **Scanner Line: Bounded Iteration & Mutation** | PR #160, #162 | `7b07eb603ca7bf2fc16a6ce467a2d1d0c5d5e5b3`, `bebc039ed9772edf0737caf8f5520134907317e0` | Bounded sequence snapshots, dict traversal bounds, single refusal charge accounting |
| **Scanner Line: Queue Pre-reservation** | PR #158 | `1888b9c85de399e887b11000b09a01fe2e9936b8` | Remaining work calculation and child queue pre-reservation before allocation |
| **Minimal Sdist Packaging Contract** | PR #142, #144, #155 (ADR 0033) | `fee364c63bece9f1a25db8d94db1307b0ec2299d` | Hatchling sdist `only-include`, `scripts/check_sdist_contract.py`, finite tar stream inflation bounding, packaging test suites |

### 2.2 Semantic Conflict Resolutions

1. **`src/repo_catalog/domain/context_admission.py`**:
   - *Conflict*: The scanner line rewrote `charge_input` with bounded traversal defenses, remaining work budgets, sequence snapshots, and dataclass capacity checks, but was based on an older admission model before I6-C. The I6-C line had relaxed `AdmissionSelection` without core (`not self.include_core and deps.object_oids`), added mapping disposition dependency extraction (`MappingDispositionKey` and `hasattr(item, "disposition_key")`), and introduced `LocalAuthorizationPolicy` with `create_local_admission_service`.
   - *Resolution*: Merged the scanner's full bounded `charge_input` implementation into the I6-C file. Preserved I6-C's `AdmissionSelection` rule allowing repositories without core (`not self.include_core and deps.object_oids`), preserved disposition extraction in `dependencies(unit)`, and retained `LocalAuthorizationPolicy` and `create_local_admission_service` intact.
2. **`scripts/verify_access_distribution.py`**:
   - *Conflict*: The scanner line introduced `check_sdist` and `compare_wheels` to verify the ADR 0033 packaging contract during distribution builds, while the I6-C line had added ADR 0031 v5 exchange packaging, finite receiver grants, replay control, and transfer SQL fence verification in the installed smoke routine.
   - *Resolution*: Retained I6-C's comprehensive SMOKE routine (testing v5 format, finite grants, idempotent replay, denial fail-close, and transfer fences) and integrated the sdist contract and wheel equivalence verification steps into `main()`.
3. **`tests/support/distributions.py` & `tests/unit/test_test_efficiency.py`**:
   - *Conflict*: `tests/support/distributions.py` in the sdist lineage requires `sdist` and `sdist_contract` in `KEYS`, causing `test_test_efficiency.py` in the baseline to fail on missing keys in mock product dictionaries.
   - *Resolution*: Synchronized `tests/unit/test_test_efficiency.py` with the accepted ADR 0033 distribution fixtures, adding `sdist` and `sdist_contract` to the mock builder and parameterizing contract invalidation tests.

### 2.3 Excluded Unrelated Changes

- Historical intermediate trial scripts, transient benchmarks, and reviewer scratch logs outside the formal evidence path were excluded.
- Existing historical evidence directories from previous review cycles were preserved without modification.

---

## 3. Two-Stage Commit Separation Record

1. **Stage 1 (Tested Input)**:
   - **Commit SHA**: `363eb6fdb8c12f854676f4273ed040968f701b3a`
   - **Tree SHA**: `3c955abc101b23991da764de3310e6b5a0f99be8`
   - **Message**: `feat(integration): integrate ADR 0031 I6-C exchange, scanner budget defense, and minimal sdist`
   - **Scope**: All executable product code in `src/`, test suites in `tests/`, tool scripts in `scripts/`, `pyproject.toml`, `.github/workflows/`, and authoritative ADR documentation.
2. **Stage 2 (Final Submission)**:
   - **Scope**: Strictly `docs/implementation/evidence/adr0031-i6c-scanner-integration-20261024/`
   - **Equivalence Invariant**:
     ```bash
     git diff 363eb6fdb8c12f854676f4273ed040968f701b3a..HEAD -- src tests scripts pyproject.toml .github
     ```
     Must be strictly empty (0 lines).

---

## 4. Test Execution Receipts

### 4.1 Fast Preflight
Command: `python scripts/preflight_access.py`
Outcome: `PASS`
```json
{
  "status": "PASS",
  "python_version": "3.12.13",
  "executable": "/home/ubuntu/github/git-repo-db/integration/adr0031-i6c-scanner-integration-20261024/.venv/bin/python",
  "locked_dependencies": {
    "httpx": "0.28.1",
    "pytest": "9.1.1",
    "ruff": "0.16.10",
    "pytest-xdist": "3.8.0",
    "hatchling": "1.32.4",
    "jsonschema": "4.26.0"
  },
  "sqlite": {
    "sqlite_version": "3.53.1",
    "journal_mode": "wal",
    "strict_tables": true,
    "fts5_trigram": true
  },
  "isolation": {
    "initial_umask": "0o2",
    "enforced_umask": "0o022"
  }
}
```

### 4.2 Strict Regression Comparator Unit Tests
Command: `pytest tests/unit/test_compare_access_regressions.py -v`
Outcome: `23 passed in 0.84s` (100% PASS)

### 4.3 Admission Scanner Budget Defense Suite
Command: `pytest tests/unit/test_admission_scanner_budget.py -v`
Outcome: `37 passed in 56.03s` (100% PASS)
- Defends capacity pre-reservation before queue extend
- Defends dataclass reflection against selection work limit
- Defends sequence snapshots against container mutations
- Defends dictionary key/value expansion bounds
- Asserts single refusal accounting without double charging

### 4.4 I6-C Behavioral Verification Suite
Command: `pytest tests/integration/access/test_i6c_behavioral_verification.py -v`
Outcome: `8 passed in 12.08s` (100% PASS)
- Obligation 1, 2, 3: Single package receiver selections & exact SQLite rowsets
- Obligation 4: Context-only and paired Core+Context import paths
- Obligation 5: Foreign authorization handle rejection (fail-closed)
- Obligation 6: Boundary permission revocation at COMMIT boundaries
- Obligation 7: Exact replay and cached receipt behavior after revocation
- Obligation 8: Independent permissions for Source, MappingClaim, Disposition
- Obligation 9: Paired Core-first failure and operational recovery state
- Obligation 10: Retention of Transfer SQL fences and UnsupportedResourceStage

### 4.5 Sdist Packaging Contract & Hardening Suite
Command: `pytest tests/packaging/test_sdist_contract.py tests/packaging/test_sdist_hardening.py -v`
Outcome: `131 passed in 4.04s` (100% PASS)
- Contract check: `scripts/check_sdist_contract.py --build` passed:
  - Compressed bytes: 705,705 (budget: 2,097,152; 33.6% used)
  - Unpacked bytes: 6,064,489 (budget: 8,388,608; 72.3% used)
  - Tar stream bytes: 6,195,200 (budget: 8,922,624; 69.4% used)
  - Logical members: 164 (budget: 512; 32.0% used)
  - Source inventory SHA-256: `2b856a85f8f685f9cae10ce395455649305441c2e1ef2c2c21fbd998f4f67f46`

### 4.6 Distribution & Outside-Checkout Verification
Command: `python scripts/verify_access_distribution.py`
Outcome: `PASS` (exit_code: 0)
- Direct wheel SHA-256: `ab679e600ceda7f783c4e70e63e6da0c7b5f9072c852e9b053d1e54add4da0de`
- Derived wheel SHA-256: `ab679e600ceda7f783c4e70e63e6da0c7b5f9072c852e9b053d1e54add4da0de`
- Bit-for-bit equivalence: `equal_full_zip_bytes = true`
- Installed smoke: all domain smokes executed in isolated venvs passed with exit code 0.

### 4.7 Scoped Access Acceptance Suite
Command: `pytest -q tests/unit/test_access*_values.py tests/unit/test_context_registration_values.py tests/unit/test_native_acquisition_values.py tests/integration/access`
Outcome: `947 passed in 241.80s` (100% PASS, 0 failures, 0 errors)

### 4.8 Full Unit Test Regressions
Command: `pytest tests/unit/ -q`
Outcome: `1614 passed, 57 subtests passed in 115.91s` (100% PASS, 0 failures, 0 errors)

### 4.9 Static Analysis & Formatting
Command: `ruff check src tests scripts && ruff format --check src tests scripts`
Outcome: `All checks passed! 461 files already formatted`

---

## 5. Non-Author Review Handoff

In adherence to repository quality standards and Author correction guidelines, the Author declares `Author-complete` status while preserving the review verdict as **`INCOMPLETE / PENDING_INDEPENDENT_REVIEW`**. Full acceptance requires independent verification on the opened Draft PR.
