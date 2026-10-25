# ADR 0031 I7 Recovery & Admission Regression Closure: Integration Milestone Report

## 1. Executive Summary

This milestone completes the implementation of ADR 0031 I7 Recovery (Workstream B) and resolves all inherited authorization-incompatible regression failures (Workstream A), delivering an integrated, independently reviewable, fully tested candidate for `main`.

### Key Verification Metrics

- **Scoped Broad Regression Execution**: 1,851 test nodes executed.
- **Inherited Failures Reconciled**:
  - `INHERITED_ADMISSION_PERMISSION_DENIED`: **0 remaining** (144 resolved).
  - `INHERITED_P7_RECOVERY`: **0 remaining** (14 resolved).
  - `INHERITED_STAGE_TRANSFER`: **43 strictly preserved** (Transfer stage SQL fences intact).
- **Regressions**: **0 new regressions**, **0 changed failures**, **0 added failures**.
- **Acceptance Verdict**: **`PASSED`** (0 blocking violations).
- **Packaging & Distribution**:
  - Sdist contract check: PASS (tar stream, compression, unpacking within budgets).
  - Wheel equivalence: Bit-for-bit identical SHA-256 (`94afbfb2524b10923c6573f6d5a3a6d0ce570ae3b4477a67b4d1a8d7f6491210`).
  - Isolated wheel and sdist-wheel smoke tests outside checkout: PASS (`exit_code: 0`, 19 tables).
- **Code Standards**:
  - `ruff check`: All checks passed.
  - `ruff format`: 462 files formatted, 0 differences.

---

## 2. Baseline and Lineage Architecture

### Repository Baseline
- Repository: `https://github.com/TakashiSasaki/git-repo-db`
- Base Commit (`main`): `b602702822ff20d19e623212a1924bf922f2f90c`
- Main Tree: `e22b59bcb1b268ff260f5fd7ea36eeca296c96ad`

### Integrated Workstreams
1. **Workstream B — ADR 0031 I7 Recovery**:
   - Pull Request: #176 (`feat/adr0031-i7-recovery-20261025`)
   - Commit HEAD: `66a2a8aa063c27467b64c22c328df251f898daae`
   - Remote CI Run: `https://github.com/TakashiSasaki/git-repo-db/actions/runs/40157828789` (PASSED)
   - Scope: Authorized fresh destination recovery coordinator, context salvage admission with finite leases, G-R1 stored candidate reconciliation, G3=A native-I7/reported-I8 Issue support eligibility, durable cumulative work budgets, and suspect source read-only preservation.

2. **Workstream A — Admission Regression Closure**:
   - Pull Request: #177 (`fix/adr0031-admission-regression-closure-20261025`)
   - Commit HEAD: `3f5495f8b11a0562ad09f7722965d5acfe377b01`
   - Remote CI Run: `https://github.com/TakashiSasaki/git-repo-db/actions/runs/40158485217` (PASSED)
   - Scope: Brings 144 inherited `PERMISSION_DENIED` test harnesses across `i2`, `i23`, `i4`, `p1`, `p5`, `p5_p6_compatibility`, and `packaging` into compliance with the accepted ADR 0031 I6-C explicit-authorization contract. Preserves valid denial, omission, and foreign authority tests.

3. **Combined Candidate**:
   - Branch: `integration/adr0031-i7-recovery-and-admission-20261025`
   - Tested Input Commit: `6388c3fb1c04977087fda5699385d951da0de1c7`
   - Tested Tree: `cdde30be7a4f558b961945efec750275e9802a2e`

---

## 3. Workstream A: Authorization Harness Reconciliation Ledger

All 144 inherited `PERMISSION_DENIED` nodes were systematically audited and brought into compliance with the ADR 0031 explicit-authorization model:

| Test Area | Affected Files | Root Cause in Baseline | Resolution | Outcome |
|:---|:---|:---|:---|:---|
| **i2 Provider Intake** | `tests/integration/i2/test_provider_intake.py` | Fixtures performed mutations without bound admission context or credentials | Provided genuine admission context credentials via `LocalAuthorizationPolicy` and finite grants | PASS |
| **i23 Provider Exchange** | `tests/integration/i23/test_provider_exchange.py` | Receiver did not specify permitted resource selections, or provider scopes lacked credentials | Bound explicit receiver authority and credentials matching selective exchange roles | PASS |
| **i4 Query Search Backup** | `tests/integration/i4/test_query_search_backup.py` | Backup verification harnesses attempted direct context writes without leases | Issued finite transaction leases for backup restoration steps | PASS |
| **p1 Context & Relations** | `tests/integration/p1/test_generalized_resources.py` | Context setup bypassed admission leases or used outdated untyped APIs | Used `admit_generalized_resource` with valid authorization context | PASS |
| **p5 Intake & Corrections** | `tests/integration/p5/test_corrections.py` | Corrections fixtures invoked context intake without admission grants | Configured explicit intake authorization policies | PASS |
| **p5/p6 Compatibility** | `tests/integration/p5_p6_compatibility/test_end_to_end_p5_p6.py`, `test_provider_exchange_matrix.py` | Matrix permutations lacked receiver selection tokens or used unpermitted repositories | Set explicit selection tokens and permitted repository UUIDs in test matrices | PASS |
| **Packaging Distribution** | `tests/packaging/test_p5_distribution.py` | Smoke harness exercised direct context mutations without admission authority | Initialized admission service with explicit credentials | PASS |

---

## 4. Workstream B: ADR 0031 I7 Recovery Implementation

Workstream B addresses the P7 Context Salvage Admission defect observed in `src/repo_catalog/adapters/sqlite/recovery.py` where `_merge_salvage_request` constructed `ContextStore(ctx_conn)` without admission authority.

### Key Implementation Components
1. **Recovery Coordinator Authority**:
   - Issued an authorized recovery admission context using `create_local_admission_service` with scoped leases.
   - Guarded transactions with transaction-owned admission leases that revoke at commit boundary.
2. **G-R1 Candidate Reconciliation & R17 Obligations**:
   - Implemented strict candidate validation against existing text and schemas in `recovery_validation.py`.
   - Prevented candidate malformations from suppressing independently admissible subsequent candidates.
3. **Durable Cumulative Work Budget**:
   - `SalvageBudgetTracker` records cumulative traversal steps across retries and continuation, failing closed upon budget exhaustion.
4. **Suspect Source Read-Only Invariant**:
   - Recovery source database is opened in immutable read-only mode (`file:...immutable=1`), strictly preventing mutation of damaged databases.
5. **Issue Support Eligibility (G3=A)**:
   - Evaluated native-I7 vs reported-I8 Issue eligibility, ensuring Issue candidate records conform to G3=A criteria.

All 14 inherited P7 recovery failures were independently reproduced, resolved, and verified across 259 P7 integration tests.

---

## 5. Transfer Stage Fences: Strict Preservation

Per repository policy and ADR 0031:
- `i2_transfer_stage_fence` and `i2_transfer_report_stage_fence` remain strictly active in `p1_ddl/context.sql`.
- Ordinary disk catalogs continue to raise `UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED` upon any Transfer intake attempt.
- All 43 deliberate Transfer stage fences were executed and preserved without exception (`INHERITED_STAGE_TRANSFER: 43`).
- Isolated Transfer-specific tests only use the explicitly reviewed disposable in-memory fixture capability (`_isolated_transfer_fixture`), leaving ordinary production runtime fences completely intact.

---

## 6. Scoped Broad Regression Reconciliation Summary

The scoped broad test execution of 1,851 nodes was reconciled against the baseline manifest (`ordinary.xml.gz`):

```json
{
  "acceptance_verdict": "PASSED",
  "baseline_nodes": 6343,
  "in_scope_baseline_nodes": 1847,
  "out_of_scope_baseline_nodes": 4496,
  "expected_nodes": 1851,
  "current_nodes": 1851,
  "missing_nodes": 0,
  "resolved_count": 231,
  "inherited_count": 43,
  "progressed_barriers_count": 0,
  "new_regressions": 0,
  "added_failures": 0,
  "environment_failures": 0,
  "changed_failures": 0,
  "unexpected_skips": 0,
  "categorized": {
    "RESOLVED": 231,
    "INHERITED_STAGE_TRANSFER": 43,
    "INHERITED_ADMISSION_PERMISSION_DENIED": 0,
    "INHERITED_P7_RECOVERY": 0,
    "INHERITED_OTHER": 0,
    "PROGRESS_KNOWN_BARRIER": 0,
    "ENVIRONMENT_FAILURE": 0,
    "CHANGED_FAILURE": 0,
    "NEW_REGRESSION": 0,
    "ADDED_PASS": 4,
    "ADDED_FAIL": 0,
    "SKIP": 0,
    "PASS": 1573,
    "MISSING_EXECUTION": 0,
    "UNEXPECTED_NODE": 0,
    "OUT_OF_SCOPE_BASELINE": 4496
  },
  "blocking_violations": []
}
```

---

## 7. Distribution and Packaging Verification

1. **Sdist Contract**:
   - `scripts/check_sdist_contract.py --build`: PASSED.
   - Compressed size: 710,041 bytes (budget: 2,097,152 bytes).
   - Unpacked size: 6,100,868 bytes (budget: 8,388,608 bytes).
   - Tar stream size: 6,231,040 bytes (budget: 8,922,624 bytes).
   - Members count: 164 (budget: 512).

2. **Wheel Equivalence**:
   - Direct built wheel SHA-256: `94afbfb2524b10923c6573f6d5a3a6d0ce570ae3b4477a67b4d1a8d7f6491210`
   - Sdist-derived wheel SHA-256: `94afbfb2524b10923c6573f6d5a3a6d0ce570ae3b4477a67b4d1a8d7f6491210`
   - Bit-for-bit identical!

3. **Isolated Smoke Outside Checkout**:
   - Tested in clean temporary virtual environments without repository sources on `sys.path`.
   - Verified 19 schema tables, backup restoration, exchange v5 serialization, and cross-seed operations.
   - Result: `passed`, exit code 0.
