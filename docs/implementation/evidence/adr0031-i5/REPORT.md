# ADR 0031 I5 author verification

**Author verification complete for ADR 0031 I5 Typed Transfer Admission. Independent
non-Author review is pending. Whole-product acceptance remains NOT READY.** Both
SQL Transfer fences and application refusals remain enabled in the product.
No merge, release, deployment, P8 or real-catalog/Provider action was performed.

## Exact input and publication binding

- Base: PR #128 HEAD `2003a9ee4f25907bcf96a634980b8caffc133c4e`, tree
  `7a662517644541c3c321a111b9325e97ea5667a8`.
- Referenced independently reviewed I4 product tree:
  `3dd1e39e06d347883a6fb493e7b9b06fb6dbfb62` (HEAD `a9d4c3585806622b66d3c41132c2a9f8ab5c6f9e`).
- **Executed product/tests/runners HEAD:
  `3a749541fe4c41eb72e7ded9f36528f0abeb05ff`; tree:
  `6a494efb510713dbfb3cebf6ef5ff85e703e0d18`.** Both final regression lanes report
  a clean tracked worktree and identical unchanged input hashes. Distributions
  were built from a clean Git archive of precisely this commit.
- Initial live latest-PR and complete branch searches found no equivalent I5.
  Prepublication rechecks confirmed no new I5 and confirmed #128 still at its exact
  instructed HEAD. Existing PRs (#126, #127, #128) were not changed.

## Changes and effective Domain / SQL contract

The [implementation contract](../../adr0031-i5-typed-admission.md) defines every domain,
adapter, and validation requirement.

| Files | Effective change |
| --- | --- |
| `domain/p1_context.py` | Updated `TransferEventReport` to 9-element canonical scope (`clock`, `endpoints`, `event_type`, `from_provider_repository_id`, `parent_members_json`, `parent_provenance_json`, `parent_scope_json`, `provided_roles`, `to_provider_repository_id`), added `parent_issue` property, and enforced that endpoint relations match report members/scope when untruncated. Extended `ResourceRepositoryRelation` to support nullable `event_report_members_json` and `event_report_scope_json`. |
| `adapters/sqlite/p1_context.py` | Implemented complete `admit_transfer_event(report)`: pre-bind strict type checking on `observed_at_us` and `clock.at_us` (rejecting bool, float, str, negative, zero); G3=A permanent violation check (`reported_issue != native_issue`) vs diagnosable dependency checks; SAVEPOINT `p1_transfer_event` atomicity; idempotent exact replay vs mutation rebind rejection. Implemented `transfer_event_reports` query reading the full 10-column relations schema without cross-borrowing across different `EventReportKey`s. |
| `adapters/sqlite/production_context.py` | Guarded `admit_transfer_event` and `transfer_event_reports` to check `has_transfer_fence(self.db)` and immediately raise `UnsupportedResourceStage` on normal fenced databases, preserving exact call trace frames and preventing spurious recovery stop files. |
| `domain/resource_stage.py` | Added `has_transfer_fence(db)` inspection; guarded `validate_stage_storage` so that disposable test databases where fences were explicitly dropped pass validation, while normal product databases continue to enforce I2 stage fences. |
| `domain/selective_exchange.py` | Updated `relation()` helper to map endpoint reference fields `event_report_members_json` and `event_report_scope_json`. |
| `tests/integration/p3/test_transfer_admission.py` | 29 focused integration tests exercising all I5 requirements through composed SQL and product factory. |
| New verification and comparison scripts | `verify_i5.py`, `verify_i5_distribution.py`, `compare_i5_failures.py`. |

Context schema and DDL are completely unchanged from I4. Composed Context DDL SHA-256 on both runtimes:
`924cc7557fb3da6211ea070185881f5fcaeff9bf52b6e237a361a238a2ea0c6e`.

## Semantic, Policy, and Dependency Admission Guarantees

1. **G3=A native identity distinction**:
   - When the reported Parent Issue does not match the Event's native parent Issue, Admission raises `ValueError("G3=A permanent violation: ...")`. This is a permanent structural violation and cannot be cured by later dependency arrivals.
   - When the native I7 Resource, Parent report, Provider repository, or supporting `MappingClaimKey` is missing, Admission raises `ValueError("Missing dependency: ...")`. This condition is diagnosable and can be resolved by resupplying the missing dependencies and resubmitting the original unit.
2. **Provider event meaning and native contract**:
   - Requires `event_type == 'transferred'` and `resource_kind == 'comment'`.
   - Declared original member, clock, provenance, and observation times are preserved without alteration or replacement with SQLite/SQL-generated timestamps.
3. **Pre-bind type strictness**:
   - `observed_at_us`: strictly Python `int` (rejecting `bool`, `float`, `str`, negative values, and zero where positive epoch is required).
   - `clock.at_us`: strictly positive integer `int` (rejecting `bool`).
   - SQLite affinity conversions are never relied upon as a substitute for pre-bind validation.
4. **Selection, Permission, and Completeness**:
   - Provider-declared member completeness: declared endpoints must be present without truncation (`selection_truncated` or `omitted_roles` cannot be admitted).
   - Genuine 1-sided transfers and explicit-null targets are admitted when lawfully declared, distinct from truncation or omitted roles.
5. **Atomic Admission and Idempotency**:
   - Atomicity via `SAVEPOINT p1_transfer_event`: any failure during report or endpoint insertion rolls back the entire savepoint, leaving zero partial writes.
   - Idempotent replay: an exact duplicate submission succeeds with return value `"duplicate"`.
   - Mutation rejection: replaying with modified timestamps, provenance, or target payload triggers a pre-conflict guard and raises `ValueError("Transfer report original payload/time rebind")`.

## Fenced product versus isolated SQL

Both SQL transfer fences:
- `i2_transfer_stage_fence`
- `i2_transfer_report_stage_fence`

and application-level staged refusals in `_preflight_units` remain active and byte-identical in product DDL.
Normal product execution paths continue to reject Transfer operations with `I2_TRANSFER_UNSUPPORTED`.
Positive typed admission is validated exclusively in disposable isolated test databases where the exact product schema is verified against `expected_schema('context')` and then the two fences are explicitly dropped. Fenced normal product databases continue to reject Transfer operations.

## Actual runtime execution

Official-source amalgamations were executed with dynamic CPython **3.12.3** loading each selected library:
- 3.51.3: `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
- 3.53.1: `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.

| Lane per runtime | Executed | Pass | Failure | Error | Skip/xfail | Exit |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Broad regression | 3,137 | 3,058 | 59 | 20 | 0/0 | 1 |
| Focused I5, overlapping broad | 29 | 29 | 0 | 0 | 0/0 | 0 |
| Focused I4, overlapping broad | 217 | 217 | 0 | 0 | 0/0 | 0 |
| Existing I3 subset, overlapping broad | 65 | 65 | 0 | 0 | 0/0 | Broad exit 1 |
| Existing SQL diagnostic groups | 301 | 301 | 0 | 0 | 0/0 | 0 |

All **79 baseline non-successes** remain identical on both runtimes:
- 45 Transfer call failures, 20 Transfer setup errors, 14 I6 Wire call failures.
- Zero regressions introduced; exact matching node names, test phases, refusal messages, and trace frame paths and functions.
- Every reconciliation check (node execution uniqueness, JUnit/journal reconciliation, single execution of setup/call/teardown) succeeded on both runtimes.

## Installed wheel and sdist-derived wheel

A clean archive of executed HEAD produced a direct wheel and sdist; the latter was unpacked and independently built into a second wheel. Four fresh installations outside checkout ran both real runtimes.

- Direct and sdist-derived wheels: 762,725 bytes each, SHA-256
  `22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842`.
- Built sdist: 77,620,267 bytes, SHA-256
  `85ba00e9a4a9f338cb59d418ee736f06dbed8e18b60fa7c7dee3de6a917cce12`.
- Source Git archive SHA-256:
  `e1831c60ef369e69dd39ddbcd4b4e73a0043be1e1a5d97eeda91c3a3c5741d2a`.

In each of the four isolated environments:
- 29/29 I5 cases passed (exit 0).
- 217/217 I4 cases passed (exit 0).
- Unchanged I2/I3 probes passed (exit 0).
- Original Access smokes failed at Transfer preflight as expected (exit 1).
- Orchestration exited 1, properly preserving actual nonzero staging refusals without mask.

## Retained development checks and audits

- Composed DDL and physical schema fingerprints match all four stores (`build_p1_schema.py --check` exit 0).
- P1 reconciliation audit matches 84 baseline tables, 625 columns, 48 target tables, zero unclassified (`audit_p1_schema.py --check` exit 0).
- Call-site dependency source index matches (`audit_callsite_dependencies.py --check` exit 0).
- Context registration and implementation boundary audits pass (`audit_context_registration.py`, `audit_implementation_boundary.py` exit 0).
- Ruff check on `src`, `tests`, and `scripts` passes with zero errors; ruff format check reports all files already formatted.

## Carryover findings

- **I4-E1 (Low)**: Discrepancy between documentation/script inputs in review tree vs historical sdist scope; carried forward unresolved.
- **Task G G-R1 (Medium)**: Context.candidates() global/scoped identity exposure carried forward for ADR 0031 I7.

## Frozen independent-review handoff

Review the executed product/tests at the exact HEAD/tree above. Verify the indexed
archive hashes, full Parent/native-I7/Event references, original evidence,
pre-conflict paths, normal fences, actual connection setup and all four installed
lanes. This task freezes inputs for a different non-Author agent; no independent
review or approval is claimed here.

I6 will implement the generalized Identification Wire protocol, relations, collections, and exchange.
Transfer operations will remain refused behind stage fences until I6 and all downstream integration acceptance gates are completed.
