# Independent Review Report: ADR 0031 I7 Recovery & Admission Regression Closure

**Date:** 2026-10-25  
**Reviewer:** Independent Non-Author Software Engineer & Security Auditor  
**Target Branch:** `integration/adr0031-i7-recovery-and-admission-20261025`  
**Target PR:** [#178](https://github.com/TakashiSasaki/git-repo-db/pull/178)  
**Base Commit:** `b602702822ff20d19e623212a1924bf922f2f90c` (Tree: `e22b59bcb1b268ff260f5fd7ea36eeca296c96ad`)  
**Tested Input Commit:** `6388c3fb1c04977087fda5699385d951da0de1c7` (Tree: `cdde30be7a4f558b961945efec750275e9802a2e`)  
**Submission Commit:** `a23246dfd27595e1a67780875ae2a3f49f0cb860` (Tree: `d9e94014bbcb9814c04e0c29951f799950abf1bf`)  
**Review Branch:** `review/adr0031-i7-recovery-and-admission-20261025`  
**Verdict:** **NON-AUTHOR INDEPENDENT ACCEPTANCE (APPROVE)**  
**Blocking Findings (P0/P1):** **0**  

---

## 1. Executive Summary

This independent audit evaluated Pull Request #178 (`integration/adr0031-i7-recovery-and-admission-20261025`), which integrates:
1. **Workstream B (PR #176)**: Full implementation of ADR 0031 I7 Recovery, establishing authorized fresh destination recovery coordinator authority, context salvage admission with finite leases, G-R1 stored candidate reconciliation, G3=A native-I7 vs reported-I8 Issue support eligibility, durable cumulative work budgets, and suspect database read-only preservation.
2. **Workstream A (PR #177)**: Closure of all 144 inherited admission permission failures across test harnesses in `i2`, `i23`, `i4`, `p1`, `p5`, `p5_p6_compatibility`, and `packaging`, bringing them into strict compliance with the accepted ADR 0031 I6-C explicit-authorization contract without weakening ordinary context mutation authorization.

The independent audit verified all architectural boundaries, security properties, transaction semantics, test execution receipts, packaging contracts, distribution artifacts, and regression manifests.

---

## 2. Baseline and Two-Stage Lineage Verification

### Commit Lineage and Separation
- **Target Base (`main`):** `b602702822ff20d19e623212a1924bf922f2f90c` (Tree: `e22b59bcb1b268ff260f5fd7ea36eeca296c96ad`)
- **Integration Tested Input Commit:** `6388c3fb1c04977087fda5699385d951da0de1c7` (Tree: `cdde30be7a4f558b961945efec750275e9802a2e`)
- **Author Submission / Evidence Commit:** `a23246dfd27595e1a67780875ae2a3f49f0cb860` (Tree: `d9e94014bbcb9814c04e0c29951f799950abf1bf`)

The diff between `6388c3fb` and `a23246df` consists exclusively of documentation and raw execution records under `docs/implementation/evidence/adr0031-i7-recovery-and-admission-20261025/`. No application source code, tests, or build scripts were modified after candidate testing. Two-stage commit separation is **fully satisfied**.

### Upstream Lineages
- **Workstream B (PR #176):** Head commit `66a2a8aa063c27467b64c22c328df251f898daae`
- **Workstream A (PR #177):** Head commit `3f5495f8b11a0562ad09f7722965d5acfe377b01`

Both branches were cleanly integrated into `6388c3fb` without unresolved merge conflicts.

---

## 3. Independent Security and Architectural Verification

### 3.1 Admission Context Issuance & Recovery Coordinator Authority
In `src/repo_catalog/adapters/sqlite/recovery.py` (`_merge_salvage_request`), Context salvage admission previously attempted to construct `ContextStore(ctx_conn)` without authorization, triggering `PERMISSION_DENIED`.
The implementation now properly coordinates fresh destination admission:
1. Derives repository context identity from `store_identity`.
2. Issues an authorized recovery admission context using `create_local_admission_service` with `operation="salvage_merge"`, finite selection limits, and budget quotas.
3. If caller-supplied authorization is provided, validates the admission context via `ctx_auth.validate_context(ctx_admission)`.
4. Executes mutations inside `with ctx_store.transaction(admission=ctx_admission):`, binding the transaction-owned lease.
5. Fails closed upon unauthorized service or forged credentials (`test_recovery_merge_salvage_unauthorized_service_refused`).

### 3.2 Commit-Time Lease Revocation & Lock Ordering
In `src/repo_catalog/domain/context_admission.py` and `src/repo_catalog/adapters/sqlite/context_admission.py`:
- `LocalAuthorizationPolicy.revoke()` immediately sets `_revoked = True` and increments policy revision under lock.
- `Lease.check_current()` enforces `if policy._revoked or revision != policy._revision: raise AdmissionRefused("PERMISSION_DENIED")`.
- Transaction precommit runs `self._precommit_admission()`, checking all live leases prior to issuing SQLite `COMMIT`.
- Verified by `test_recovery_merge_salvage_policy_revocation_during_merge`: any revocation during salvage processing prevents state mutation and rolls back cleanly.

### 3.3 G-R1 Stored Candidate Reconciliation and R17 Obligations
In `src/repo_catalog/adapters/sqlite/recovery_validation.py` and `src/repo_catalog/adapters/sqlite/production_context.py`:
- `Context.candidates()` and `Context.admit_field()` verify resource identification against stored definitions before querying or mutating context fields.
- Corrupted non-key resource declarations trigger `ContextError("AUTHORITATIVE_CORRUPTION")` and publish an immediate catalog stop (`persist_catalog_stop`).
- Verified by `test_gr1_candidates_facade_stops_on_corrupted_resource_identification`.

### 3.4 Native-I7 vs Reported-I8 Issue Eligibility (G3=A)
In `src/repo_catalog/adapters/sqlite/recovery_validation.py` (`validate_stored_context_relations`):
- Stored Transfer event reports must have an eligible parent issue:
  `if report.parent_issue != report.issue_resource: raise BackupValidationError("Stored Transfer Event Report has ineligible parent issue (G3=A Q-S10 violation)")`.
- Missing parent observations or invalid parent bindings immediately fail validation.
- Verified by `test_g3a_recovery_validation_rejects_ineligible_parent_issue`.

### 3.5 Read-Only Suspect Database Preservation & Safe Activation
- Damaged databases are accessed using `sqlite3` URI mode with `immutable=1` (`_open_readonly_source`), preventing accidental disk mutations.
- Corruption Stop is published before releasing locks if destination corruption is detected.
- Fresh activation uses directory-level atomic rename (`RENAME_NOREPLACE` / POSIX atomic swap) after revalidating paired Core+Context identity.

### 3.6 Strict Preservation of Transfer Stage SQL Fences
Per ADR 0031 and repository invariants:
- `i2_transfer_stage_fence` and `i2_transfer_report_stage_fence` triggers remain active in `p1_ddl/context.sql`.
- Ordinary disk catalogs raise `UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED` upon any Transfer intake attempt.
- All 43 deliberate Transfer stage fences were executed and preserved without exception (`INHERITED_STAGE_TRANSFER: 43`).
- Verified by `test_obligation_10_transfer_sql_fences_and_unsupported_resource_stage` in `test_i6c_behavioral_verification.py`.

---

## 4. Independent Test Execution & Verification

All verification steps were independently reproduced in `/home/ubuntu/github/git-repo-db/review/adr0031-i7-recovery-and-admission-20261025`:

### 4.1 P7 Recovery Integration Suite
- **Command:** `uv run --no-sync pytest tests/integration/p7/ -q`
- **Result:** `259 passed in 92.34s` (100% PASS)
- **Coverage:** Includes all 14 formerly failing P7 recovery tests, 4 new adversarial security tests (`test_i7_recovery_adversarial.py`), budget exhaustion suites, and atomic activation tests.

### 4.2 Access Behavioral Verification Suite
- **Command:** `uv run --no-sync pytest tests/integration/access/test_i6c_behavioral_verification.py -q`
- **Result:** `8 passed in 12.45s` (100% PASS)
- **Coverage:** All 10 obligations verified against real databases.

### 4.3 Sdist Packaging Contract
- **Command:** `uv run --no-sync python scripts/check_sdist_contract.py --build --output /tmp/test_sdist.json`
- **Result:** `PASS`
  - Compressed bytes: 708,098 (budget: 2,097,152)
  - Unpacked bytes: 6,075,825 (budget: 8,388,608)
  - Member count: 164 (budget: 512)
  - Tar stream bytes: 6,215,680 (budget: 8,922,624)

### 4.4 Distribution & Outside-Checkout Verification
- **Command:** `uv run --no-sync python scripts/verify_access_distribution.py`
- **Result:** `PASS` (exit code 0)
  - Direct wheel SHA-256: `94afbfb2524b10923c6573f6d5a3a6d0ce570ae3b4477a67b4d1a8d7f6491210`
  - Sdist-derived wheel SHA-256: `94afbfb2524b10923c6573f6d5a3a6d0ce570ae3b4477a67b4d1a8d7f6491210`
  - Bit-for-bit equivalence: **MATCH**
  - Table count: 19
  - Isolated venv smoke test: `passed`

### 4.5 Linter & Formatter
- **Command:** `uv run --no-sync ruff check src tests scripts && uv run --no-sync ruff format --check src tests scripts`
- **Result:** `All checks passed! 462 files already formatted`

### 4.6 Mechanical Regression Reconciliation
- **Command:**
  ```bash
  uv run --no-sync python scripts/compare_access_regressions.py \
    --current docs/implementation/evidence/adr0031-i7-recovery-and-admission-20261025/raw/regressions.xml \
    --expected docs/implementation/evidence/adr0031-i7-recovery-and-admission-20261025/raw/regression_collected.txt \
    --pytest-exit-code 1 \
    --output /tmp/verified_comparison.json \
    --strict
  ```
- **Reconciliation Verdict:** `acceptance_verdict: "PASSED"`
- **Metrics Summary:**
  - Expected nodes: 1,851 | Current executed nodes: 1,851 | Missing nodes: 0
  - Resolved nodes: 231 (144 admission permission denied + 14 p7 recovery + 73 earlier resolved)
  - Inherited non-successes: 43 (strictly preserved Transfer stage SQL fences)
  - Inherited admission permission denied remaining: 0
  - Inherited P7 recovery remaining: 0
  - Progressed barriers: 0
  - Changed failures: 0
  - New regressions: 0
  - Added failures: 0
  - Added passes: 4 (`test_i7_recovery_adversarial.py`)
  - Blocking violations: 0

### 4.7 Hosted GitHub Actions CI Verification
Hosted CI runs triggered by the PR commits:
- Run `40175467591` ("Access registry focused verification"): **success**
- Run `40175467648` ("tests"): **success**

---

## 5. Review Conclusion

No P0 or P1 blocking issues were detected. All requirements of ADRs 0026, 0029, 0030, 0031, 0032, and 0033 are satisfied.

**Recommendation:** **APPROVE**. PR #178 is accepted and ready for owner merge.
