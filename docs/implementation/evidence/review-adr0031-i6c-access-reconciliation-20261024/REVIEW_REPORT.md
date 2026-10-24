# Independent Acceptance Review Report: ADR 0031 I6-C Access Reconciliation

## 1. Executive Summary & Review Target

- **Review Role**: Independent Non-Author Reviewer
- **Track**: ADR 0031 I6-C (Access Reconciliation & Provider Selective Exchange)
- **Target Pull Request**: [PR #163](https://github.com/TakashiSasaki/git-repo-db/pull/163)
- **Target Branch**: `fix/adr0031-i6c-access-reconciliation-20261024`
- **Reviewed HEAD SHA**: `2b33405b1a95eeddea277789e3bcc7b6b7307759`
- **Reviewed Tree SHA**: `0970b876c8152a2faefa343e43c5b366ddd7a568`
- **Author Tested Input Commit**: `e4967ca7d1d129a726cf03a8d2e6ff31c0e56250`
- **Author Tested Input Tree**: `1108b1ce553eb9d84c8c7869f04725d27dedf5cc`
- **Base Branch**: `fix/adr0031-i6c-positive-authority-followup-20261024` (PR #161 HEAD: `328dadf4b939bb2d1a3771fb1a9fcbad49fb16c6`, tree `dfa2a72e03ca87a99f5d349a7c01caa31a6e0bf5`)
- **Review Branch**: `review/adr0031-i6c-access-reconciliation-20261024`
- **Python / SQLite**: Python 3.12.13, native environment-loaded SQLite 3.53.1 (`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`)
- **Final Decision**: **SCOPED ACCEPTANCE (PASS)**

---

## 2. Tested-Input vs Submission Commit Equivalence Verification

We verified the identity between the Author tested input commit (`e4967ca7d1d129a726cf03a8d2e6ff31c0e56250`) and the final PR #163 submission HEAD (`2b33405b1a95eeddea277789e3bcc7b6b7307759`).

```bash
git diff e4967ca7d1d129a726cf03a8d2e6ff31c0e56250..2b33405b1a95eeddea277789e3bcc7b6b7307759 -- src tests scripts pyproject.toml
```

- **Result**: Output is completely empty (zero changes to executable code, tests, build configuration, or scripts).
- **Delta Analysis**: Commit `2b33405b` contains only saved markdown and evidence JSON files in `docs/implementation/evidence/adr0031-i6c-access-reconciliation-20261024/`.
- **Verdict**: Proven identical. All test executions, distribution packages, and regression numbers correspond directly to the submitted code.

---

## 3. Behavioral Obligations & Independent Verification Matrix

| # | Behavioral Obligation | Verification Method | Result | Evidence / Details |
|---|---|---|---|---|
| 1 | **Receiver-local finite grants construction** | Independent test | **PASS** | `test_independent_receiver_local_finite_grants` in `tests/integration/i6/test_i6c_independent_acceptance.py`. Receiver constructs finite `DependencySet` without sender authority; real rows persist in `resource_relations` and `resource_repository_relations`. |
| 2 | **Authorized paired Provider & Exchange receiver paths** | Independent test & focused suite | **PASS** | Successfully admitted batch and exported/imported ADR 0031 v5 Exchange package (`"git-repo-db/adr0031-exchange-v5"`). Real rows verified in `providers`, `repositories`, `resources`, `resource_relations`. |
| 3 | **Empty, strict-subset, and full receiver selections** | Independent test | **PASS** | `test_independent_receiver_selections_empty_subset_full`. Full selection imports cleanly; unauthorized strict-subset payload fails closed with `AdmissionRefused("PERMISSION_DENIED")` and zero row mutations; authorized subset scope succeeds. |
| 4 | **Missing, foreign, and commit-time revoked authority** | Independent test | **PASS** | `test_independent_missing_foreign_and_revoked_authority`. Missing authority raises `PERMISSION_DENIED`; foreign principal rejected with `PERMISSION_DENIED`; mid-lease policy revision bump aborts commit with `PERMISSION_DENIED`. |
| 5 | **Core-first paired failure semantics** | Independent test | **PASS** | `test_independent_core_first_paired_failure_semantics`. Paired acquisition executes Core commit first; subsequent Context error raises `AdmissionFailure` with `core_committed=True` and `context_committed=False`; durable `core.sqlite3` retains repository while `context.sqlite3` rolls back cleanly. |
| 6 | **Outside-checkout wheel distribution probes** | Independent execution | **PASS** | Executed `scripts/verify_access_distribution.py`. Both direct wheel and sdist-derived wheel built cleanly, yielding identical SHA-256 (`c3a147b2111e2e22e75af1c1390cfe9b9e8a8f68f5a4a8a6f3584bd608b1360a`). Installed into 2 isolated venvs outside checkout; verified 19 tables, UDFs, Transfer fences, and smoke tests (exit code 0). |
| 7 | **Normal Transfer fence preservation on native SQLite** | Independent test | **PASS** | `test_independent_transfer_fence_preservation`. Transfer timeline intake refused with `UnsupportedResourceStage("Provider Transfer intake")`. SQL trigger fences `i2_transfer_stage_fence` and `i2_transfer_report_stage_fence` verified active in `sqlite_schema`. Native SQLite 3.53.1 used throughout. |
| 8 | **Broad node-level regression reconciliation** | Node inventory audit | **PASS** | Verified against PR #154 baseline (6,343 ordinary nodes, 299 non-successes). 84 non-successes resolved (25 Access + 59 selective exchange). 215 unchanged inherited failures attributable strictly to staged Transfer SQL fences. **0 new regressions**. |
| 9 | **Three prompt inquiries resolution** | Code audit & adversarial test verification | **PASS** | (1) Grants-based fallback is internal receiver-only, fails closed without grants. (2) Preflight validation prevents malformed records from reaching Context despite exception suppression in relation decoding. (3) Derive-grants helper `receive()` is strictly a test-only harness in `test_selective_exchange.py` for legacy fixtures. |

---

## 4. Independent Executions vs Reused Evidence

### 4.1 Independent Executions Conducted by Reviewer

1. **New Independent Acceptance Suite**:
   - File: `tests/integration/i6/test_i6c_independent_acceptance.py`
   - Command: `python3 -m pytest -c pyproject.toml tests/integration/i6/test_i6c_independent_acceptance.py`
   - Outcome: **5 passed in 4.46s** (exit code 0)
   - Scope: Receiver grants independence, selection controls (empty/subset/full), denial/revocation, Transfer fence preservation, Core-first paired failure semantics.

2. **Author Focused Integration Suite Execution**:
   - File: `tests/integration/i6/test_i6c_authority_and_exchange.py`
   - Command: `python3 -m pytest -c pyproject.toml tests/integration/i6/test_i6c_authority_and_exchange.py`
   - Outcome: **43 passed in 19.93s** (exit code 0)
   - Scope: Comprehensive suite covering all I6-C positive authority, exchange import, boundary defense, and caller Privilege checks.

3. **Outside-Checkout Distribution Verification**:
   - Script: `scripts/verify_access_distribution.py`
   - Outcome: **exit_code: 0** in both `wheel` and `sdist-wheel` outside-checkout virtual environments.
   - Verified:
     - Direct wheel SHA-256: `c3a147b2111e2e22e75af1c1390cfe9b9e8a8f68f5a4a8a6f3584bd608b1360a`
     - Rebuilt wheel from sdist SHA-256: `c3a147b2111e2e22e75af1c1390cfe9b9e8a8f68f5a4a8a6f3584bd608b1360a`
     - Source sdist SHA-256: `0686173aea894ed1993f58551623aea993a17af32730ea4ecfb9208feb7b09cf`
     - Module origin: confirmed outside workspace in virtual environment `site-packages`.
     - SQLite runtime: native 3.53.1 without spoofing or version overrides.
     - DDL fingerprint: `89bcafeda815150fa4770f5758edf7d2d36d505b76717aa19054f9ad689765da`.

4. **Access Acceptance Audit Tool**:
   - Script: `scripts/audit_access_acceptance.py`
   - Outcome: **exit code 0**, confirmed 24 covered requirements, 2 deferred/partial requirements (#11, #15), 64 unique test references.

### 4.2 Reused Evidence Audit and Validity Assessment

- **PR #154 Baseline Ordinary Suite** (`docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/source-full-final/ordinary.xml.gz`):
  - Author recorded 6,343 ordinary nodes with 279 failures and 20 errors (299 non-successes).
  - Reviewer audited the exact node reconciliation in `node-comparison.json`:
    - 25 resolved nodes in `tests.integration.access.*`: verified to pass under fixed test setup.
    - 59 resolved nodes in `tests.integration.i3.test_selective_exchange`: verified to pass with the test fixture receive helper.
    - 215 inherited unchanged failures: verified that all 215 failures correspond to staged Transfer SQL fences (`i2_transfer_stage_fence`, `i2_transfer_report_stage_fence`) or related staged barriers.
    - 0 new regressions.
  - Reused raw execution logs (`ordinary.log`, `ordinary.xml`) match the reported node IDs and timestamps. Running all 6,343 nodes again mechanically is unnecessary because the source and test trees are identical (`git diff` is empty) and environmental prerequisites match.

---

## 5. Review Findings & Blocking Evaluation

Following the Antigravity High-Signal Blocking PR Review rules:
- **P0 Findings**: None.
- **P1 Findings**: None.
- **Non-blocking Observations**:
  - `docs/implementation/access-a6-acceptance.json` correctly notes requirement 11 (distributed sync) and requirement 15 (backup restore verification) as deferred/partial until downstream phases, as permitted by accepted contracts.
  - No production code path derivations of receiver grants from sender packages exist.
  - Transfer fences are strictly active in ordinary operation.

---

## 6. Scoped Acceptance Decision

**Decision: SCOPED ACCEPTANCE (PASS)**

The changes in PR #163 (`fix/adr0031-i6c-access-reconciliation-20261024`, commit `2b33405b1a95eeddea277789e3bcc7b6b7307759`) successfully satisfy all behavioral, architectural, and security requirements for ADR 0031 I6-C.

- **Scope Distinction**: This review grants scoped acceptance for the I6-C track (Provider Selective Exchange and Access reconciliation). It does **not** authorize merge to `main`, release dispatch, deployment, or removal of staged Transfer fences for future phases (I7/I8).
