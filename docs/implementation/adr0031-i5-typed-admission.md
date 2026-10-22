# ADR 0031 I5: Typed Transfer Admission Contract

Base: PR #128 HEAD `2003a9ee4f25907bcf96a634980b8caffc133c4e`, tree `7a662517644541c3c321a111b9325e97ea5667a8`.
Reviewed product HEAD: `a9d4c3585806622b66d3c41132c2a9f8ab5c6f9e`, tree `3dd1e39e06d347883a6fb493e7b9b06fb6dbfb62`.

## 1. Domain and Persistent Contract

I5 implements typed Transfer Admission consuming the structural SQL constraints established in ADR 0031 I4:

1. **9-Element Canonical Scope**:
   `TransferEventReport.scope_json` encodes exactly 9 sorted canonical keys:
   - `clock`: canonical serialization of `FieldClock`
   - `endpoints`: list of declared `[role, canonical_target_json]` pairs
   - `event_type`: string, strictly `'transferred'`
   - `from_provider_repository_id`: string or `None`
   - `parent_members_json`: canonical JSON of parent members
   - `parent_provenance_json`: canonical JSON of parent provenance
   - `parent_scope_json`: canonical JSON of parent scope
   - `provided_roles`: tuple of provided repository relation roles
   - `to_provider_repository_id`: string or `None`

2. **Endpoint Reference Fields**:
   `ResourceRepositoryRelation` extends with two nullable reference columns:
   - `event_report_members_json`: references the parent report's `members_json`
   - `event_report_scope_json`: references the parent report's `scope_json`
   Both are bound automatically when untruncated and verified by the I4 foreign key constraints.

3. **Pre-Bind Strict Type Validation**:
   - `observed_at_us`: strictly Python `int` (rejecting `bool`, `float`, `str`, negative values, and zero where positive epoch is required).
   - `clock.at_us`: strictly positive integer `int` (rejecting `bool`).
   - SQLite affinity conversions are never relied upon as a substitute for pre-bind validation.

4. **Semantic and Policy Validation**:
   - Provider event meaning: requires `event_type == 'transferred'` and `resource_kind == 'comment'`.
   - G3=A native identity distinction:
     - If the reported Parent Issue does not match the Event's native parent Issue, Admission raises `ValueError("G3=A permanent violation: ...")`. This violation is permanent and cannot be cured by later dependency arrivals.
     - If the native I7 Resource, Parent report, Provider repository, or supporting `MappingClaimKey` is missing, Admission raises `ValueError("Missing dependency: ...")`. This condition is diagnosable and can be resolved by resupplying the missing dependencies and resubmitting the original unit.
   - Provider-declared member completeness: declared endpoints must be present without truncation (`selection_truncated` or `omitted_roles` cannot be admitted).
   - Selection and permission: genuine 1-sided transfers and explicit-null targets are admitted when lawfully declared, distinct from truncation or omitted roles.

5. **Atomic Admission and Idempotency**:
   - Execution is protected by `SAVEPOINT p1_transfer_event`. Any failure during report or endpoint insertion rolls back the entire savepoint, leaving zero partial writes.
   - Idempotent replay: an exact duplicate submission succeeds with return value `"duplicate"`.
   - Mutation rejection: replaying with modified timestamps, provenance, or target payload triggers a pre-conflict guard and raises `ValueError("Transfer report original payload/time rebind")`.

## 2. Fences and Verification Isolation

The two SQL transfer fences:
- `i2_transfer_stage_fence`
- `i2_transfer_report_stage_fence`

remain active and byte-identical in packaged DDL and normal product connections. Application-level staged refusals in `_preflight_units` also remain active.

Normal I5 positive validation is performed exclusively in disposable isolated test databases where the exact product schema is verified against `expected_schema('context')` and then the two fences are explicitly dropped. Fenced normal product databases continue to reject Transfer operations with `I2_TRANSFER_UNSUPPORTED`.

## 3. Handoff to Later Stages

- **I6 (Generalized Identification Wire / Relations / Collections / Exchange)**: Wire protocol for Transfer and multi-hop selective exchange.
- **I7 (Stored Validation, Recovery, Paired Backup, Task G Medium G-R1)**: Reconcile candidates() global/scoped exposure.
- **I8 (Query / Search)**: Transfer-aware query and search filters.
- **V1 / V2**: Full multi-store runtime and packaging acceptance.
- **I4-E1 Low**: Carried forward as an open finding regarding sdist documentation/script inputs.
