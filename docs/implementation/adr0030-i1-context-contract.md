# ADR 0030 Stage I1: Context Relation Contracts, Schema, and Admission

## 1. Executive Summary & Authorization

Stage I1 establishes the persistent contracts, physical schema, UDF codecs, and admission rules for Context resource-repository relationships in `repo-catalog`, replacing the retired single-column `field_candidates.repository_uuidv4` architecture with typed, auditable multi-relation structures as defined in ADR 0030.

- **Stage**: I1 ("Context relation contracts, schema, and admission")
- **Authorization**: Explicitly authorized by repository owner at `2026-10-19T16:47:01+09:00` JST (`2026-10-19T07:47:01Z`).
- **Base Tree**: `main`
- **Branch**: `impl/adr-0030-i1-context-relations-20261019`
- **Scope**: Isolated Context DDL, domain types, SQLite adapters, UDF validators, enduring recovery invariants, and counterexample test suite.

## 2. Physical Schema & Storage Boundaries

The composed Context store (`context.sql`) contains exactly 19 tables in STRICT WITHOUT ROWID configuration:

1. `store_identity`
2. `providers`
3. `repository_context`
4. `sources`
5. `source_repositories`
6. `resources`
7. `text_bodies`
8. `field_candidates`
9. `resource_relations`
10. `collections`
11. `collection_terminals`
12. `coverage_scopes`
13. `coverage_proofs`
14. `coverage_claims`
15. `source_inventory_evidence`
16. `source_coverage_proofs`
17. `core_references`
18. `resource_repository_relations` (NEW)
19. `repository_mapping_dispositions` (NEW)

### New Tables

- **`resource_repository_relations`**:
  Stores typed Resource--Repository relationships. Primary key is the exact 7-column claim key:
  `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, clock_json, target_json, provenance_json)`.
  Features virtual columns for indexed foreign keys (`repository_uuidv4` referencing `repository_context`), source clock domain/timestamp extraction, and conditional foreign key linking timeline event resources to parent issues.

- **`repository_mapping_dispositions`**:
  Stores immutable, auditable dispositions for Provider repository mapping claims (`represents_repository`).
  Primary key:
  `(service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind, claim_clock_json, claim_target_json, claim_provenance_json, disposition_kind, disposition_clock_json, disposition_provenance_json)`.
  Restricted foreign keys ensure subject claims and replacement claims exist in `resource_repository_relations` before a disposition can be admitted.

### Removed Mechanisms & Invariants

- Generated virtual column `field_candidates.repository_uuidv4` and its index/foreign key have been completely excised.
- The special `field_name='repository_uuidv4'` authority is retired. `CHECK(field_name!='repository_uuidv4')` in `field_candidates` prevents direct SQL insertion.
- `ContextStore.admit_repository()` and `ContextStore.repository_candidates()` are retired; callers must use `admit_repository_relation()` and `repository_relations()`.
- No `witness` table or verification-history ledger exists in Context; all evidence is retained directly in typed relation claims and dispositions.

## 3. Closed Vocabulary & Canonical Codecs

### Closed 6-Role Vocabulary

Relationships are strictly partitioned into 6 roles:

| Relation Role | Resource Kind | Description | Candidate Pruning |
| :--- | :--- | :--- | :--- |
| `represents_repository` | `repository` | Maps Provider repository identity to Core repository UUIDv4 | No (immutable claims) |
| `owning_repository` | `issue` | Issue ownership | Yes (clock-dominated) |
| `base_repository` | `pull_request` | PR target base branch repository | Yes (clock-dominated) |
| `head_repository` | `pull_request` | PR source head branch repository | Yes (clock-dominated) |
| `transfer_from_repository` | `comment` (timeline_event) | Issue transfer origin repository | No (event report) |
| `transfer_to_repository` | `comment` (timeline_event) | Issue transfer destination repository | No (event report) |

### Deterministic SQLite UDF Codecs

Registered deterministic functions validate JSON structure in SQL triggers and CHECK constraints:

- **`p1_mapping_target(target_json)`**: Validates that target is either `"null"` or a canonical lowercase UUIDv4 JSON string (`"<uuid4>"`). Returns 1 or 0 (never SQL NULL).
- **`p1_mapping_clock(clock_json)`**: Validates that clock is a JSON object with a non-empty string `domain` and either a positive integer `at_us` (<= 2^63-1) or `null`.
- **`p1_mapping_provenance(provenance_json)`**: Validates that provenance is a canonical JSON object containing non-empty string `source`, non-null `evidence`, and optional structured `claimed_issuer`.

## 4. Admission Semantics & Candidate Lifecycle

### Current Candidate Pruning vs. Immutable Mapping Claims

1. **Current Candidates (`owning_repository`, `base_repository`, `head_repository`)**:
   - `AFTER INSERT` trigger `rrr_prune_dominated` deletes older candidates within the same Resource, role, and clock domain where `source_clock_us < NEW.source_clock_us`.
   - Incomparable clocks (different clock domain, unclocked `at_us=null`, or equal timestamps) survive concurrently without pruning.
   - Older clock arrivals are rejected as stale by `rrr_no_rebind`.

2. **Immutable Mapping Claims (`represents_repository`)**:
   - Do not undergo pruning; all admitted alternative claims survive.
   - Replay with identical 7-column claim key: returns `"duplicate"` if `observed_at_us` matches, or raises replay conflict error if `observed_at_us` differs.

3. **Dispositions (`withdraw`, `correct`, `dispute`)**:
   - `correct` requires a complete replacement claim (`replacement_clock_json`, `replacement_target_json`, `replacement_provenance_json`) referencing the same Resource but differing from the subject claim.
   - `withdraw` and `dispute` require replacement fields to be strictly NULL.
   - Self-replacement and partial-NULL replacements are rejected by CHECK constraints.
   - Mutually contradictory corrections (correction cycles) remain representable as unresolved reports (`state="unresolved_correction"`) without picking arbitrary winners.

### Transfer report dependency and stored-scope encoding

Transfer rows use only `admit_transfer_event()`, with one exact shared report
provenance. `encode_transfer_supported_provenance(source, evidence, supports)`
accepts `(relation_kind, MappingSupport)` entries. It preserves original evidence
and adds a finite `evidence.transfer_mapping_supports` list of exact
`{relation_kind, target_json, mapping_support}` entries. Each support contains
the actual Provider Repository and complete MappingClaimKey coordinates; role
plus target selects the endpoint's support. Duplicate coordinates, target
mismatches, non-Transfer roles and mixing singular/plural support are rejected.
The existing singular `mapping_support` encoding remains for existing callers.
This is an encoding within the existing provenance/key, not a new table, identity
or Witness. Missing support remains unqualified; another role/provider cannot
supply it implicitly.

`selection_truncated` is an ephemeral report qualifier, preserved on reselection
and rejected at complete admission. It covers omitted alternatives even when
another endpoint of the same role survives. It adds no persisted column or key.
Stored reads and recovery share `TransferEventReport.from_stored_scope()`;
canonical scope fields, clock, event type, supplied roles and exact unique
Provider members must agree with the report. Referenced Provider Resources must
exist. These checks preserve declarations, not Provider authenticity.

## 5. Coverage Scope Scoping & Second-Authority Elimination

- `CoverageScope.repository_relation(repository_uuidv4, resource, relation_kind, coverage_kind)` scopes coverage strictly to the specific relation role.
- General field coverage does not upgrade or imply repository relation completeness.
- `CoverageScope.field(..., "repository_uuidv4", ...)` raises an explicit error.
- Direct raw SQL insertion of `field_name='repository_uuidv4'` into `field_candidates` fails with SQLite CHECK constraint violation. No second authority exists.

## 6. Caller-to-Follow-up-Stage Matrix

Downstream callers requiring semantics from future ADR 0030 stages fail with explicit, coherent contract errors:

| Stage | Files Affected | Status in I1 | Action Required in Target Stage |
| :--- | :--- | :--- | :--- |
| **I2** | `domain/acquisition.py`<br>`application/acquisition.py`<br>`adapters/github/production_intake.py` | Raises `AcquisitionError("UNSUPPORTED_UNTIL_I2")` on relation admission paths | Implement GitHub GraphQL intake for timeline transfer events and multi-relation extraction. |
| **I3** | `domain/exchange.py`<br>`application/exchange.py`<br>`adapters/sqlite/acquisition.py` | Raises `ExchangeError("UNSUPPORTED_UNTIL_I3")` on transfer exchange paths | Implement selective export/import accounting for transfer relations and mapping dispositions. |
| **I4** | `domain/production_query.py`<br>`application/production_query.py`<br>`adapters/sqlite/production_search.py`<br>`recovery.py` | Raises `QueryError("UNSUPPORTED_UNTIL_I4")` on repository resolution | Implement multi-relation query resolution and search index projection over `resource_repository_relations`. |
| **I5** | Test & acceptance suites | Deferred | Combined integration testing and final end-to-end acceptance. |

## 7. Verification Evidence & Counterexamples

The original I1 specification listed 17 counterexamples; the previous reviewed tree added cases 18–20. The contract-freeze gate adds cases 21–29 below. These are focused I1 checks, not full downstream acceptance:

- **Counterexample 1**: Conflicting immutable mappings in reverse arrival order survive; exact resend yields duplicate.
- **Counterexample 2**: Current candidate clock pruning prunes only strictly dominated comparable values.
- **Counterexample 3**: Atomic rollback on insertion/FK failure restores original candidate state.
- **Counterexample 4**: Invalid roles, malformed targets, and wrong parents rejected by CHECK and foreign keys.
- **Counterexample 5**: Transfer event reports preserve one-sided, two-sided, and null endpoints without inventing endpoints.
- **Counterexample 6**: Exact ClaimKey with changed observation time rejected in Python and SQL trigger.
- **Counterexample 7**: Exact DispositionKey with changed observation time rejected in Python and SQL trigger.
- **Counterexample 8**: Partial-NULL, wrong-resource, and self-replacement rejected; cycles yield `unresolved_correction`.
- **Counterexample 9**: Strict canonical grammar, positive timestamp, and bounded payload enforcement.
- **Counterexample 10**: Mapping evaluation preserves evidence without hidden witness ledger.
- **Counterexample 11**: Role-scoped coverage does not upgrade field coverage; source positive membership preserved.
- **Counterexample 12**: Old `repository_uuidv4` field rejected in domain types, APIs, and raw SQL.
- **Counterexample 13**: Foreign key enforcement and trigger order consistency.
- **Counterexample 14**: Expired capabilities, read-only snapshots, and P7 recovery stops enforced.
- **Counterexample 15**: Enduring stored-invariant validation passes on valid conflicting relations.
- **Counterexample 16**: Composed Context has exactly 19 tables matching schema fingerprint and disposition manifest.
- **Counterexample 17**: Direct wheel and package artifacts contain valid schema without retired virtual columns.
- **Counterexample 18**: Mapping ClaimKey support isolation. Unbacked Core relations cannot borrow claims from other Provider Repositories; relations without explicit `MappingSupport` resolve strictly to `missing_supporting_binding`.
- **Counterexample 19**: Transfer event type enforcement. Transfer event roles strictly require genuine `event_type='transferred'` timeline events.
- **Counterexample 20**: Transfer event `selected_repositories` generator normalization. Single-pass generators are normalized at entry to ensure identical filtering across multiple events.

- **Counterexample 21**: Both Transfer roles are rejected by generic admission and result APIs in the reference Store and production Context, including replay; complete reports remain admissible.
- **Counterexample 22**: Stored endpoints without a report scope or explicit `event_type="transferred"` fail read/recovery validation; event type is never inferred.
- **Counterexample 23**: Endpoint FK failure rolls back the event Resource, report scope and all endpoint rows together.
- **Counterexample 24**: Generic `Context.relation()` cannot insert a `transfer_event_report` scope without the complete typed report.

See [the contract-freeze record](adr0030-i1-contract-freeze.md) for current execution and exact review targets.

- **Counterexample 25**: Shared Transfer report provenance retains per-(role,target) exact MappingSupport for both A→B endpoints; disposing A's claim does not dispose or supply B's support.
- **Counterexample 26**: Selection that drops only some alternatives remains `selection_truncated`, including after reselection; it cannot be admitted as a complete report.
- **Counterexample 27**: Empty Provider IDs and non-Timeline comment filters reject before stored-data handlers and do not create P7 stops.
- **Counterexample 28**: Read and recovery use the same stored-report parser to check exact scope fields, provided roles, Provider member coordinates and their existence.

- **Counterexample 29**: All ContextAdmission Protocol keyword names are accepted by the facade, including the relation result wrapper; existing positional ResourceKey overloads still work.

### Public Context Facade Hardening

1. **RelationKind Runtime Validation**:
   - Replaced invalid `RelationKind(x)` instantiation (`typing.Literal` runtime error) with explicit validation against `RELATION_KINDS`.
2. **False Catalog Stop Elimination**:
   - All facade argument validation (`ResourceKey` instance checks, `RelationKind`, `MappingOperationEvidence`, UUID format) is strictly evaluated before entering `with self._stored(...)`. Invalid caller arguments raise standard `TypeError` / `ValueError` without writing `AUTHORITATIVE_CORRUPTION` stop files.
3. **Evidence Propagation**:
   - Added `evidence: MappingOperationEvidence | None = None` support to `evaluate_provider_repository`, `repository_relations`, `relations_for_repository`, and `relations_for_provider_repository`. When omitted, no authority is fabricated from local origins.
4. **Port & Facade Signature Alignment**:
   - Return type of `ContextStore.admit_transfer_event()` aligned to `str`.
   - `require_support: bool = False` forwarded from facade to store implementation.

Historical execution evidence at `ebcf865ede7ee661446b6fd7edf1be6ef7e623a8` (tree `e61ffd6d0aac0f27ae109fb5debedc96cdd2e860`), retained separately from the new gate run:
- `tests/integration/p1`: 337 tests passed (including 20/20 in `test_context_relations.py`).
- `tests/integration/p3`: 76 tests passed.
- `tests/integration/access`: 483 tests passed.
- Total passed: 896 tests.
- Environment: Python 3.12.3, Linux 6.8.0-1018-gcp aarch64.
- Isolated Wheel & Sdist Distribution:
  `scripts/verify_access_distribution.py` built direct wheel and sdist-rebuilt wheel in isolated virtual environments; verified 19 tables in Context DDL, fingerprint `fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`, and UDF registrations on real SQLite 3.51.3.
- Runtime Dependency Note:
  The minimum required SQLite version is 3.51.3 (`MIN_SQLITE = (3, 51, 3)`).
  On this host, executing tests requires providing the verified SQLite 3.51.3 build at `/home/ubuntu/.local/share/git-repo-db-sqlite-3510300/libsqlite3.so.0` via `LD_LIBRARY_PATH="/home/ubuntu/.local/share/git-repo-db-sqlite-3510300"`.

## 8. Categorization and Root Cause Analysis of 37 Post-I1 Integration Failures

GitHub run [39239845865](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39239845865), retrieved again for the freeze gate, reports **1,861 passed / 37 failed** on the previous HEAD. The direct causes below establish blocked downstream execution, not proof that the unexecuted downstream code is correct. No failures are hidden, skipped or marked xfail. The separate Transfer admission defect is fixed and regression-tested by this gate.

### 8.1 Summary Matrix

| Subsystem | Failure Count | Root Cause Code | Assigned Stage | Resolution Requirement |
| :--- | :--- | :--- | :--- | :--- |
| **P5 (Intake / Admission)** | 5 | `UNSUPPORTED_UNTIL_I2` | **Stage I2** | Implement GitHub GraphQL intake for timeline transfer events and multi-relation extraction into `resource_repository_relations`. |
| **P5 (Exchange integration)** | 5 | `UNSUPPORTED_UNTIL_I2` during source fixture intake, before Exchange | **I2 prerequisite → I3** | First restore valid source acquisition in I2; then run Exchange integration under I3. These five failures do not directly observe an I3 error. |
| **P6 (Query / Search)** | 27 | Retired API Dependency (`Context.admit_repository`) | **Stage I4** | Implement multi-relation query projection over `resource_repository_relations`; modernize P6 fixtures in `conftest.py` to use `admit_repository_relation`. |
| **Total** | **37** | | | |

The I3 standalone boundary control `tests/integration/p5/test_exchange.py::test_i1_relation_export_guard_without_i2_acquisition` builds a source via I1 typed admission and directly asserts the existing `UNSUPPORTED_UNTIL_I3` export refusal. That passing refusal check proves only the boundary, not I3 selective Exchange behavior. After I2, rerun the original five integration tests; they remain required.

### 8.2 Detailed Pytest Node Inventory

#### Stage I2 Failures (5 tests)
1. `tests/integration/p5/test_corrections.py::test_repository_unknown_observation_retained_without_fabricated_coordinates`
   - *Root Cause*: `AcquisitionError: UNSUPPORTED_UNTIL_I2` raised on provider relation intake path.
   - *Assigned Stage*: Stage I2 (Provider intake).
   - *Expected Resolution*: Stage I2 admission pipeline handles multi-relation extraction.
2. `tests/integration/p5/test_paired_admission.py::test_core_first_context_second_and_failure_retry_convergence`
   - *Root Cause*: The assertion expecting the later injected `RuntimeError` instead receives an `AdmissionFailure.cause` of `AcquisitionError: UNSUPPORTED_UNTIL_I2`; the intended failure cut is not reached.
   - *Assigned Stage*: Stage I2 (Provider intake).
   - *Expected Resolution*: Coordinated paired admission writes to `resource_repository_relations`.
3. `tests/integration/p5/test_paired_admission.py::test_late_core_dependency_reconciliation`
   - *Root Cause*: `AcquisitionError: UNSUPPORTED_UNTIL_I2` during dependency reconciliation.
   - *Assigned Stage*: Stage I2 (Provider intake).
   - *Expected Resolution*: Late reconciliation resolves candidate status via multi-relation queries.
4. `tests/integration/p5/test_provider_acquisition.py::test_issue_vs_pull_request_intake_isolation`
   - *Root Cause*: `AcquisitionError: UNSUPPORTED_UNTIL_I2` on issue/PR intake.
   - *Assigned Stage*: Stage I2 (Provider intake).
   - *Expected Resolution*: Intake processes timeline relations with `owning_repository` and `base_repository`.
5. `tests/integration/p5/test_provider_acquisition.py::test_explicit_null_vs_missing_fields_and_clock_competition`
   - *Root Cause*: `AcquisitionError: UNSUPPORTED_UNTIL_I2` on clock competition.
   - *Assigned Stage*: Stage I2 (Provider intake).
   - *Expected Resolution*: Intake pipeline manages clock domination and pruning.

#### Exchange integration blocked by I2 (5 tests; later I3 ownership)
1. `tests/integration/p5/test_exchange.py::test_exchange_export_import_repeat_reverse_and_multi_hop`
   - *Root Cause*: `AcquisitionError: UNSUPPORTED_UNTIL_I2`, wrapped in `AdmissionFailure`, while `_setup_source_catalog()` admits the PR relation before export.
   - *Assigned Stage*: I2 prerequisite, then I3 Exchange integration.
   - *Expected Resolution*: I2 supplies the source fixture; I3 then exports/imports typed relation units (no new wire version is fixed here).
2. `tests/integration/p5/test_exchange.py::test_exchange_selective_filters_and_partial_input`
   - *Root Cause*: `AcquisitionError: UNSUPPORTED_UNTIL_I2` during source fixture acquisition, before selective export.
   - *Assigned Stage*: I2 prerequisite, then I3 Exchange integration.
   - *Expected Resolution*: Selective export filters account for relation claim keys and dispositions.
3. `tests/integration/p5/test_exchange.py::test_exchange_refuses_intrinsic_spoofing_without_validated_bytes`
   - *Root Cause*: `AcquisitionError: UNSUPPORTED_UNTIL_I2` during source fixture acquisition, before payload verification.
   - *Assigned Stage*: I2 prerequisite, then I3 Exchange integration.
   - *Expected Resolution*: Exchange verification checks relation payload provenance.
4. `tests/integration/p5/test_exchange.py::test_exchange_refuses_tampered_payloads_without_store_corruption`
   - *Root Cause*: `AcquisitionError: UNSUPPORTED_UNTIL_I2` during source fixture acquisition, before tampered input handling.
   - *Assigned Stage*: I2 prerequisite, then I3 Exchange integration.
   - *Expected Resolution*: Tampered relation payloads trigger rollback without catalog corruption.
5. `tests/integration/p5/test_exchange.py::test_exchange_evaluates_core_dependencies_against_receiver_core`
   - *Root Cause*: `AcquisitionError: UNSUPPORTED_UNTIL_I2` during source fixture acquisition, before receiver Core evaluation.
   - *Assigned Stage*: I2 prerequisite, then I3 Exchange integration.
   - *Expected Resolution*: Receiver Core validates target repositories against imported relations.

#### Stage I4 Failures (27 tests)
All 27 failures directly depend on the retired `Context.admit_repository()` API. Most reach `populate_rich_catalog()` in `tests/integration/p6/conftest.py`; two Context-only tests call the old API directly in `test_queries.py`. The direct exception is `AttributeError`; paired fixtures wrap it in `AdmissionFailure: core+context:ADMISSION_FAILED`. The query engine is not reached by these failing setups.
In accordance with ADR 0030 Section 2, `Context.admit_repository()` was intentionally retired and must NOT be restored as a compatibility shim.

- `tests/integration/p6/test_cli.py::test_cli_all_subcommands_pagination_and_error_handling`
- `tests/integration/p6/test_corrections.py::test_metadata_queries_do_not_hydrate_or_rehash_all_retained_bodies`
- `tests/integration/p6/test_corrections.py::test_core_and_context_snapshot_capabilities_expire`
- `tests/integration/p6/test_corrections.py::test_snapshot_budget_refusal_preserves_ordinary_reads[paired]`
- `tests/integration/p6/test_corrections.py::test_snapshot_budget_refusal_preserves_ordinary_reads[core_only]`
- `tests/integration/p6/test_corrections.py::test_snapshot_budget_refusal_preserves_ordinary_reads[context_only]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases[\u65e5\u672c\u8a9e]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases[\U0001f600]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases[a]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases[*]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases["]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases[\\]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases[\x00]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases[caf\xe9]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases[p6]`
- `tests/integration/p6/test_corrections.py::test_literal_unicode_short_special_search_semantics_and_cost_phases[P6]`
- `tests/integration/p6/test_corrections.py::test_oversize_derivative_row_falls_back_before_text_construction`
- `tests/integration/p6/test_corrections.py::test_derivative_deep_json_falls_back_without_catalog_stop`
- `tests/integration/p6/test_pagination_snapshots.py::test_deterministic_pagination_across_all_endpoints`
- `tests/integration/p6/test_pagination_snapshots.py::test_open_snapshot_isolation_and_stale_cursor_fencing_after_write`
- `tests/integration/p6/test_pagination_snapshots.py::test_malformed_tampered_and_cross_endpoint_cursors_fail_closed`
- `tests/integration/p6/test_queries.py::test_context_only_queries_resources_fields_relations_inventories_and_coverage`
- `tests/integration/p6/test_queries.py::test_paired_cross_store_resolution_present_vs_absent_core_oids[sha1]`
- `tests/integration/p6/test_queries.py::test_paired_cross_store_resolution_present_vs_absent_core_oids[sha256]`
- `tests/integration/p6/test_queries.py::test_verification_aware_byte_reads_detect_corruption_and_fence_catalog`
- `tests/integration/p6/test_search_fallback.py::test_search_projection_and_five_fallback_scenarios_never_stop_catalog[sha1]`
- `tests/integration/p6/test_search_fallback.py::test_search_projection_and_five_fallback_scenarios_never_stop_catalog[sha256]`

*Expected Resolution*: In Stage I4, implement query/search resolution over `resource_repository_relations` and refactor `tests/integration/p6/conftest.py` to use `admit_repository_relation()`. No fake shim will be introduced in I1.

