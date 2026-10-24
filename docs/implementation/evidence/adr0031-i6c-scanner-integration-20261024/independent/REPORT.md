# Stage 4 Final Independent Integration Review Report: PR #172

**Date:** 2026-10-24  
**Reviewer:** Final Independent Integration Reviewer (Reviewer role for Stage 4)  
**Target Pull Request:** [PR #172](https://github.com/TakashiSasaki/git-repo-db/pull/172) (`integration/adr0031-i6c-scanner-integration-20261024`)  
**Target PR URL:** `https://github.com/TakashiSasaki/git-repo-db/pull/172`  
**Target HEAD Commit:** `68c9ebb3c8877c522a51be268588f0adefd5d58d` (Tree: `c1e1a2e62a08afd22852cb9890c3fa5d26c36bb8`)  
**Tested Input Commit:** `363eb6fdb8c12f854676f4273ed040968f701b3a` (Tree: `3c955abc101b23991da764de3310e6b5a0f99be8`)  
**Base Branch:** `fix/adr0031-i6c-regression-hardening-20261024`  
**Base Commit:** `55de572bdac4b9b90b131d89025b0ed304cd0159` (PR #170 HEAD)  
**Review Branch:** `review/adr0031-i6c-scanner-integration-20261024`  
**Independent Acceptance Verdict:** **SCOPED ACCEPTANCE / PASS**  
**Blocking Findings (P0/P1):** **0**  

---

## 1. Executive Summary & Review Verdict

As the designated non-Author independent reviewer for Stage 4, I have conducted an exhaustive, independent verification and audit of PR #172 (`integration/adr0031-i6c-scanner-integration-20261024`). PR #172 unifies the ADR 0031 I6-C Exchange & Authority lineage with the Admission Scanner Budget Defense and ADR 0033 Minimal Product Sdist Packaging lineages.

### Summary of Independent Review Findings:
- **Two-Stage Commit Separation**: Strictly adhered to. The diff between tested input commit `363eb6fdb8c12f854676f4273ed040968f701b3a` and final submission commit `68c9ebb3c8877c522a51be268588f0adefd5d58d` across executable paths (`src`, `tests`, `scripts`, `pyproject.toml`, `.github`) is strictly empty (0 lines).
- **Lineage Integrity & Conflict Resolution**: All lineages (I6-C Exchange & Authority, Scanner Budget Defenses, Minimal Sdist Packaging, and I6-C Behavioral Suite) are fully integrated without regressions. Semantic conflict resolutions in `context_admission.py`, `verify_access_distribution.py`, and test fixtures were audited and confirmed correct.
- **Safety Boundaries & Invariants**: No unauthorized I7/I8 features were introduced. Transfer resource staging remains strictly excluded via `UnsupportedResourceStage` exceptions and active `i2_transfer_stage_fence` SQL triggers. Core dependency decoupling is preserved.
- **Empirical Test Suites**: All empirical test suites passed with 100% success (0 failures, 0 errors) across preflight, strict comparator tests, scanner budget tests, I6-C behavioral verification (all 10 obligations), packaging contracts, outside-checkout distribution smoke tests, scoped access acceptance (947 passed), and full unit regressions (1614 passed, 57 subtests passed).
- **Packaging Equivalence**: Direct and derived wheels achieved bit-for-bit equivalence (`equal_full_zip_bytes: true`, SHA-256: `ab679e600ceda7f783c4e70e63e6da0c7b5f9072c852e9b053d1e54add4da0de`). Sdist package budgets and inflation limits remain strictly enforced.
- **Code Hygiene**: 0 linter violations, 461 files formatted cleanly according to repository standards.

**Final Verdict:** **`SCOPED ACCEPTANCE / PASS`**. PR #172 satisfies all requirements of ADR 0031 I6-C, the scanner budget defenses, and the ADR 0033 packaging contract. Merging into `fix/adr0031-i6c-regression-hardening-20261024` is recommended.

---

## 2. Frozen Identities & Target Coordinates

| Role / Ref | Commit SHA | Tree SHA | Notes |
|:---|:---|:---|:---|
| **Base Commit (PR #170 HEAD)** | `55de572bdac4b9b90b131d89025b0ed304cd0159` | `a588ff898c968582f8fb1d661e1cdec9fa2bee08` | `fix/adr0031-i6c-regression-hardening-20261024` |
| **Tested Input Commit** | `363eb6fdb8c12f854676f4273ed040968f701b3a` | `3c955abc101b23991da764de3310e6b5a0f99be8` | Executable code frozen input |
| **Final Submission Commit (PR #172 HEAD)** | `68c9ebb3c8877c522a51be268588f0adefd5d58d` | `c1e1a2e62a08afd22852cb9890c3fa5d26c36bb8` | Author submission with evidence |
| **Review Commit (Stage 4)** | Recorded in git log | Recorded in git tree | Independent review deliverables |

---

## 3. Audit of Two-Stage Commit Separation Protocol

In accordance with repository standards and the Author Correction Protocol, all executable product modifications must be frozen in Stage 1, while Stage 2 must contain solely documentary evidence.

Independent verification command:
```bash
git diff 363eb6fdb8c12f854676f4273ed040968f701b3a..68c9ebb3c8877c522a51be268588f0adefd5d58d \
  -- src tests scripts pyproject.toml .github
```
**Result:** 0 lines (exit code: 0). The diff is strictly empty.

Inspection of changes in commit `68c9ebb3c8877c522a51be268588f0adefd5d58d` confirmed that only files within `docs/implementation/evidence/adr0031-i6c-scanner-integration-20261024/` were touched. The Two-Stage Commit Separation protocol is completely satisfied.

---

## 4. Audit of Integration Ledger & Lineages

The integration merges two distinct development lineages onto the base:

1. **I6-C Exchange & Authority Lineage**:
   - **Base**: PR #170 (`55de572bdac4b9b90b131d89025b0ed304cd0159`) containing strict comparator corrections.
   - **Regression Hardening**: PR #168 (`3a1f112331c87747249f38af370160adc0de108a`) containing two-stream CI separation and preflight verification.
   - **Behavioral Verification**: PR #169 (`634d8f63084cee578aa7beafcd27485a6da8e37a`) containing comprehensive behavioral coverage for all 10 ADR 0031 I6-C obligations in `tests/integration/access/test_i6c_behavioral_verification.py`.

2. **Admission Scanner Budget Defense & Minimal Sdist Lineage**:
   - **Dataclass Selection**: PR #165 / PR #167 (`d81951868ac4fc252f8c0f38c22cf2c38d6146d4`) enforcing dataclass reflection and member capacity pre-reservation against selection work limit.
   - **Bounded Sequences & Anti-Mutation**: PR #160 / PR #162 (`7b07eb603ca7bf2fc16a6ce467a2d1d0c5d5e5b3`, `bebc039ed9772edf0737caf8f5520134907317e0`) introducing sequence defensive snapshots, dict traversal bounds, and single refusal charge accounting.
   - **Queue Capacity Pre-reservation**: PR #158 (`1888b9c85de399e887b11000b09a01fe2e9936b8`) preventing memory inflation before queue extension.
   - **Minimal Sdist Packaging Contract**: PR #142 / #144 / #155 (ADR 0033) implementing Hatchling `only-include`, `check_sdist_contract.py`, and bit-for-bit wheel equivalence.

### Audit of Semantic Conflict Resolutions:
- **`src/repo_catalog/domain/context_admission.py`**:
  Successfully integrated the bounded scanner `charge_input` implementation (including `remaining_work()`, `reserve_children()`, `snapshot_sequence()`, dataclass reflection containment, and single refusal charging) while retaining I6-C's relaxed `AdmissionSelection` without core (`not self.include_core and deps.object_oids`), disposition extraction (`MappingDispositionKey`), and `LocalAuthorizationPolicy`.
- **`scripts/verify_access_distribution.py`**:
  Preserved I6-C's comprehensive smoke verification (testing v5 format, finite grants, idempotent replay, denial fail-close, and transfer fences) and integrated the sdist contract and wheel equivalence verification steps.
- **`tests/support/distributions.py` & `tests/unit/test_test_efficiency.py`**:
  Synchronized distribution fixtures with ADR 0033 requirements.

---

## 5. Independent Test Execution Receipts

All verification commands were independently re-executed in the review worktree:
`review/adr0031-i6c-scanner-integration-20261024` using `.venv/bin/python`.

### 5.1 Fast Preflight & Environment Verification
- **Command:** `python scripts/preflight_access.py`
- **Exit Code:** `0`
- **Output:**
  ```json
  {
    "status": "PASS",
    "python_version": "3.12.13",
    "executable": "/home/ubuntu/github/git-repo-db/review/adr0031-i6c-scanner-integration-20261024/.venv/bin/python",
    "locked_dependencies": {
      "httpx": "0.28.1",
      "pytest": "9.1.1",
      "ruff": "0.16.10",
      "pytest-xdist": "3.8.0",
      "hatchling": "1.32.4",
      "jsonschema": "4.26.0"
    },
    "console_script": {
      "repo_catalog_script": "/home/ubuntu/github/git-repo-db/review/adr0031-i6c-scanner-integration-20261024/.venv/bin/repo-catalog",
      "shebang_interpreter": "/home/ubuntu/github/git-repo-db/review/adr0031-i6c-scanner-integration-20261024/.venv/bin/python",
      "module_origin": "/home/ubuntu/github/git-repo-db/review/adr0031-i6c-scanner-integration-20261024/src/repo_catalog/__init__.py",
      "version": "0.2.0"
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

### 5.2 Strict Regression Comparator Unit Tests
- **Command:** `pytest tests/unit/test_compare_access_regressions.py -v`
- **Result:** `23 passed in 1.07s` (100% PASS)
- **Verified:** Rejection of empty/truncated XML, unexpected skips, added failing nodes, environment failures, and abnormal pytest exit codes (2, 3, 4, 5).

### 5.3 Scanner Budget Defense Suite
- **Command:** `pytest tests/unit/test_admission_scanner_budget.py -v`
- **Result:** `37 passed in 56.19s` (100% PASS)
- **Verified:**
  - Real store counterexamples prevented
  - Capacity pre-reservation before queue extend
  - Dataclass selection work limit defense (1,000 fields, prior cumulative work, existing pending siblings, exact boundaries)
  - Defensive sequence snapshots against mutating containers
  - Dictionary key/value expansion bounds
  - Single refusal accounting without double charging

### 5.4 I6-C Behavioral Verification Suite
- **Command:** `pytest tests/integration/access/test_i6c_behavioral_verification.py -v`
- **Result:** `8 passed in 12.24s` (100% PASS)
- **Verified Obligations:**
  - `Obligation 1, 2, 3`: Single package receiver selections & exact SQLite rowsets
  - `Obligation 4`: Context-only and paired Core+Context import paths
  - `Obligation 5`: Foreign authorization handle rejection (fail-closed)
  - `Obligation 6`: Boundary permission revocation at COMMIT boundaries
  - `Obligation 7`: Exact replay and cached receipt behavior after revocation
  - `Obligation 8`: Independent permissions for Source, MappingClaim, Disposition
  - `Obligation 9`: Paired Core-first failure and operational recovery state
  - `Obligation 10`: Retention of Transfer SQL fences and `UnsupportedResourceStage`

### 5.5 Sdist Packaging Contract & Hardening Suite
- **Command:** `pytest tests/packaging/test_sdist_contract.py tests/packaging/test_sdist_hardening.py -v`
- **Result:** `131 passed in 4.13s` (100% PASS)
- **Verified:** Sdist member classification, path traversal defenses, gzip header validation, and tar inflation bounding.

### 5.6 Sdist Contract Check
- **Command:** `python scripts/check_sdist_contract.py --build --output /tmp/test_sdist_contract.json`
- **Result:** `PASS`
  - Compressed bytes: `705,705` (budget: `2,097,152`; 33.6% used)
  - Unpacked bytes: `6,064,489` (budget: `8,388,608`; 72.3% used)
  - Tar stream bytes: `6,195,200` (budget: `8,922,624`; 69.4% used)
  - Logical members: `164` (budget: `512`; 32.0% used)
  - Source inventory SHA-256: `2b856a85f8f685f9cae10ce395455649305441c2e1ef2c2c21fbd998f4f67f46`

### 5.7 Outside-Checkout Distribution Smoke
- **Command:** `python scripts/verify_access_distribution.py`
- **Result:** `PASS` (exit code: 0)
  - Direct wheel SHA-256: `ab679e600ceda7f783c4e70e63e6da0c7b5f9072c852e9b053d1e54add4da0de`
  - Derived wheel SHA-256: `ab679e600ceda7f783c4e70e63e6da0c7b5f9072c852e9b053d1e54add4da0de`
  - Bit-for-bit equivalence: `equal_full_zip_bytes = true`
  - Wheel and sdist-wheel isolated smoke executions passed with exit code 0.

### 5.8 Scoped Access Acceptance Suite
- **Command:** `pytest -q tests/unit/test_access*_values.py tests/unit/test_context_registration_values.py tests/unit/test_native_acquisition_values.py tests/integration/access`
- **Result:** `947 passed in 239.62s` (100% PASS, 0 failures, 0 errors)

### 5.9 Full Unit Test Suite
- **Command:** `pytest tests/unit/ -q`
- **Result:** `1614 passed, 57 subtests passed in 117.23s` (100% PASS, 0 failures, 0 errors)

### 5.10 Boundary and Schema Audits
- `python scripts/audit_callsite_dependencies.py --check`: `PASS`
- `python scripts/build_p1_schema.py --check`: `PASS`
- `python scripts/audit_p1_schema.py --check`: `PASS`
- `python scripts/audit_implementation_boundary.py --check`: `PASS`
- `python scripts/audit_context_registration.py`: `PASS`

### 5.11 Static Analysis & Formatting
- **Command:** `ruff check src tests scripts && ruff format --check src tests scripts`
- **Result:** `All checks passed! 461 files already formatted`

---

## 6. Safety Boundaries, Explicit Exclusions & Limitations

### 6.1 Explicit Exclusions
- **Transfer Resource Staging**: Normal Provider Transfer intake remains deferred to subsequent ADR stages. Attempts to admit or export Transfer events continue to raise `UnsupportedResourceStage`, and database triggers (`i2_transfer_stage_fence`) actively block insertion into relations tables. This behavior was independently verified by `Obligation 10`.
- **I7 / I8 Scope**: No I7 or I8 architectural features were introduced or enabled.

### 6.2 Outstanding Limitations
- **SQLite Database Permissions**: Database files are generated under umask `0o022`, requiring directory and file permissions to adhere to standard non-world-writable conventions.
- **Offline Inventory Collection Signature**: Offline inventory tools parse single collection command signatures from workflow files; the current CI configuration maintains exact conformity.

---

## 7. Non-Author Acceptance Decision & Merge Recommendation

Based on the independent execution of all verification suites, the strict observance of the two-stage commit separation protocol, and the verification of zero blocking findings (P0=0, P1=0):

- **Independent Review Verdict:** **`SCOPED ACCEPTANCE / PASS`**
- **Recommendation:** Merge PR #172 (`integration/adr0031-i6c-scanner-integration-20261024`) into `fix/adr0031-i6c-regression-hardening-20261024`.
