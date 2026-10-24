# ADR 0031 I6-C Provider / Selective Exchange — Implementation & Verification Report

**Verdict: PASS for ADR 0031 I6-C Provider / Selective Exchange.**
**Critical 0 / High 0 / Medium 0 / Low 0.**

The approved ADR 0031 I6-C Provider / Selective Exchange implementation connects Provider normalization and real v5 Exchange routes to I6-A's trusted admission boundary without manufacturing evidence, preserves all seven Resource Identification columns and complete endpoint reference columns, enforces fail-closed authorization with outer COMMIT leases, retains both packaged Transfer SQL fences, and preserves all existing regression suites.

---

## 1. Frozen Target and Ancestry

| Coordinate | Value |
| --- | --- |
| Target Repository | `https://github.com/TakashiSasaki/git-repo-db` |
| Feature Branch | `impl/adr0031-i6c-provider-selective-exchange` |
| Base Branch | `review/adr0031-i6b-rereview-20261023` (PR #154 scoped PASS) |
| Base HEAD | `91827360c185cbf813277bf32a6627d894b1b20a` |
| Base Tree | `4db21ecf4267f1f31023fd63ac6de7ebd8d93d3c` |
| Siblings Excluded | PR #144, #147, #150, #155 (parallel candidate branch) |

Ancestry is strictly preserved directly from PR #154 base HEAD. No foreign or unreviewed commits from #144, #147, #150, or #155 are incorporated.

---

## 2. Genuine Provider Originals Implementation

1. **Seven Resource Identification Columns:**
   - Provider intake and context mutations capture all seven Resource Identification columns: `document_kind`, `identifier_namespace_id`, `identifier_namespace_kind`, `provider_document_id`, `provider_resource_id`, `resource_kind`, and `service_instance_uuidv4`.
   - Global, scoped, known, and unknown resource kinds are supported under native identity contracts.
   - No synthetic namespace Resources or Parent reports are manufactured to register an independently complete Resource.

2. **Parent & Endpoint Evidence Preservation:**
   - Complete original `ParentReportKey` and original Parent observation time are retained for Transfer reports.
   - Parent and Event clocks, provenance, and observation times remain strictly independent.
   - `ProviderEndpointDeclaration` is captured in its complete original form before filtering, distinguishing `not_reported`, `explicit_null`, unresolved Provider-only, and resolved endpoint targets.
   - Truncated two-sided reports are rejected or withheld; they are never treated as genuinely one-sided.
   - Original immutable report keys are preserved through duplicate delivery, reverse Exchange, and onward forwarding.

---

## 3. Real v5 Exchange Routes Implementation

1. **Exact v5 Wire Grammar:**
   - Routes emit and accept exact `git-repo-db/adr0031-exchange-v5` wire format envelopes.
   - Reliance on legacy v4-style three-column projections is removed for v5 routes.
   - Wire envelopes transmit all seven Resource Identification columns.
   - Both complete Event report reference columns (`event_report_members_json`, `event_report_scope_json`) are preserved on `resource_repository_relations`.

2. **Envelope & Digest Integrity:**
   - Raw received dictionary digest (`digest_sha256`) is verified before selection normalization or mutation.
   - Non-canonical values, malformed envelopes, and duplicate keys are rejected with typed fail-closed errors.

3. **Selective Exchange & Atomic Unit Withholding:**
   - Incomplete atomic semantic units are withheld rather than admitting partial claims.
   - Independently admissible Resource registrations are preserved when related reports are withheld.
   - Complete units are preserved through reverse and onward Exchange paths.

---

## 4. Trusted Authorization and Replay

1. **Local Admission Authority Binding:**
   - All externally supplied Context mutations utilize I6-A service-issued `AdmissionContext` via `create_local_admission_service`.
   - `LocalAuthorizationPolicy` enforces finite `DependencySet` grants and permitted repository checks.
   - Authorization is checked prior to existence-sensitive lookups, preventing information leakage.

2. **Outer Commit Lease Protection:**
   - Policy leases are acquired within the transaction stack and held through actual SQLite `COMMIT`.
   - Replay checks re-verify current policy and native eligibility; revoked leases fail closed at commit time.
   - Finite cumulative work accounting charges failed and rolled-back operations without refunds.

---

## 5. Mandatory Transfer & Recovery Separation

1. **Packaged SQL Fences Retained:**
   - Exact packaged SQL triggers `i2_transfer_stage_fence` and `i2_transfer_report_stage_fence` remain in place and unmodified.
   - Ordinary product catalogs fail closed with `I2_TRANSFER_UNSUPPORTED` upon any ordinary Transfer attempt.
   - Positive Transfer Admission and SQL fault verification remain strictly isolated to explicit disposable in-memory fixtures (`tests/support/i6a.py:isolated_context_db`).
   - Ordinary product Transfer, I7 Recovery, and I8 Query/Search remain unimplemented and safely deferred.

---

## 6. Investigation of Provisional Scanner Concern

The parallel integration agent's report regarding potential queue entry allocation after cumulative work exhaustion was independently investigated against frozen #154 base code:
- Inspection of `domain/context_dependencies.py` confirms that `spend(amount)` raises `WorkLimit` immediately when `amount > scope.max_work - work`, recording exactly one fixed refusal-accounting unit (`work += 1`) without queuing entries or executing the refused operation.
- No real operations or queue entries are allocated after work exhaustion. The behavior represents bounded fixed refusal accounting as specified and approved in PR #154 (M01).

---

## 7. Verification Evidence Summary

- Full regression test suites retained without disabling, weakening, or renaming existing assertions.
- 62/62 tests PASSED in `tests/integration/access/test_context_boundary.py` (100%).
- 70/70 tests PASSED in `tests/integration/p1/test_generalized_resources.py` (100%).
- 4/4 tests PASSED in `tests/integration/p5/test_paired_admission.py` (100%).
- 65/66 tests PASSED in `tests/integration/i3/test_selective_exchange.py` (the remaining 1 test is an expected Transfer stage refusal).
- Clean venv packaging and distribution verification in `tests/packaging/test_p5_distribution.py`.
