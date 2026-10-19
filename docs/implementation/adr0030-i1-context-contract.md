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
| `owning_repository` | `issue` | Issue or pull request ownership | Yes (clock-dominated) |
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

## 5. Coverage Scope Scoping & Second-Authority Elimination

- `CoverageScope.repository_relation(repository_uuidv4, resource, relation_kind, coverage_kind)` scopes coverage strictly to the specific relation role.
- General field coverage does not upgrade or imply repository relation completeness.
- `CoverageScope.field(..., "repository_uuidv4", ...)` raises an explicit error.
- Direct raw SQL insertion of `field_name='repository_uuidv4'` into `field_candidates` fails with SQLite CHECK constraint violation. No second authority exists.

## 6. Caller-to-Follow-up-Stage Matrix

Downstream callers requiring semantics from future ADR 0030 stages fail with explicit, coherent contract errors:

| Stage | Files Affected | Status in I1 | Action Required in Target Stage |
| :--- | :--- | :--- | :--- |
| **I2** | `domain/acquisition.py`<br>`application/acquisition.py`<br>`adapters/github/production_intake.py` | Raises `ContextError("UNSUPPORTED_UNTIL_I2")` on relation admission paths | Implement GitHub GraphQL intake for timeline transfer events and multi-relation extraction. |
| **I3** | `domain/exchange.py`<br>`application/exchange.py`<br>`adapters/sqlite/acquisition.py` | Raises `ContextError("UNSUPPORTED_UNTIL_I3")` on transfer exchange paths | Implement selective export/import accounting for transfer relations and mapping dispositions. |
| **I4** | `domain/production_query.py`<br>`application/production_query.py`<br>`adapters/sqlite/production_search.py`<br>`recovery.py` | Raises `ContextError("UNSUPPORTED_UNTIL_I4")` on repository resolution | Implement multi-relation query resolution and search index projection over `resource_repository_relations`. |
| **I5** | Test & acceptance suites | Deferred | Combined integration testing and final end-to-end acceptance. |

## 7. Verification Evidence & Counterexamples

The full test suite validates all 17 counterexamples specified in ADR 0030 Section 6 in `tests/integration/p1/test_context_relations.py`:

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

Test execution evidence:
- `tests/integration/p1`: 334 tests passed.
- `tests/integration/p3`: 76 tests passed.
- Total: 410 passed in 83.15s.
- Environment: Python 3.12.3, Linux 6.8.0-1018-gcp aarch64.
- Runtime Dependency Note:
  The minimum required SQLite version is 3.51.3 (`MIN_SQLITE = (3, 51, 3)`).
  On this host, the default system SQLite package is 3.45.1.
  Executing tests requires providing the verified SQLite 3.51.3 build at `/home/ubuntu/.local/share/git-repo-db-sqlite-3510300/libsqlite3.so.0` via `LD_LIBRARY_PATH="/home/ubuntu/.local/share/git-repo-db-sqlite-3510300"`.
  When `LD_LIBRARY_PATH` is omitted, `p1_schema.py` strictly enforces `SchemaError: P1 requires SQLite >= 3.51.3 with safe WAL, STRICT and JSON`, blocking schema initialization tests as designed.
