# P5/P6 Technical Contract — Production Acquisition, Typed Exchange, Authoritative Query, and Search

## Status and Scope

This document defines the shared technical contract for **P5** (Production acquisition orchestration, cross-store admission, and portable typed Exchange) and **P6** (Production authoritative query APIs, Search integration, consistent snapshots, pagination, and opt-in CLI access).

- **Upstream baseline**: Stacked directly on the reviewed P4 production implementation (`codex/p4-production-notes`, commit `b024ca5103e8658d4ea9717e2cbe534905552610`, executable tree `501f7ca965c0b361819e8ba2b3f5154c7d45c061`).
- **Execution model**: P5 (`feat/p5-production-acquisition-exchange`) and P6 (`feat/p6-production-query-search`) branch as parallel, independent sibling workstreams from this contract HEAD. Neither sibling contains the other's implementation commits. Combined cross-workstream verification runs on a temporary integration branch (`validation/p5-p6-combined-integration`).
- **Out of scope**: Default public runtime activation (reserved for P8) and authoritative recovery/salvage/restore/activation workflows (reserved for P7). Owner-accepted [ADR 0028](../adr/0028-classified-times-and-sha256-exchange.md) supersedes the earlier freeze of P1–P4 shared time/DDL/fingerprints only as needed for its classified time contract. Public Schema 21 remains default.

---

## Explicit Architectural Distinctions

Both P5 and P6 enforce the following six architectural distinctions across all domain values, ports, SQLite adapters, Exchange envelopes, queries, and CLI outputs:

1. **Domain identity vs. transport envelope identity**
   - *Domain identity* consists of permanent repository `repository_uuidv4`, Context `service_instance_uuidv4`, `source_uuidv4`, `ResourceKey(service_instance_uuidv4, resource_kind, provider_resource_id)`, typed Git `OID(object_format, full_oid)`, and Notes `Capture(capture_origin_uuidv4, capture_uuidv4, repository_uuidv4, source_attribution, notes_ref, root)`.
   - *Transport envelope identity* (`package_id`, `exported_at_us`, `sender_catalog_instance_uuidv4`, pagination cursor framing, or HTTP/REST page URLs) is ephemeral delivery metadata. Transport envelopes never become durable PK/FK identities, never create a `publications` authority table, and never rewrite original observation provenance on replay or onward forwarding.

2. **Original source reports vs. receiver-checked facts**
   - *Original source reports* (`ScalarClaim`, `RelationGroup(authority='reported')`, `NotesClaim`, `NotesGroup(authority='reported')`, external `Capture` records, Context `FieldCandidate`, `CoreReference` reports) preserve the attributing source's `provenance_json` and observation coordinates.
   - *Receiver-checked facts* (`authority='intrinsic'` scalar/relation claims derived by `GitCore.admit_metadata`, `note_roles` derived by `GitCore.admit_notes_role`, `retained_metadata`, `retained_notes`, and receiver-verified `text_bodies` SHA-256 digests) are admitted only after the receiving catalog independently validates the exact bytes, object format, native OID hash, structural grammar, or Notes path proof. Sender flags claiming prior verification are never trusted as a substitute for receiver verification.

3. **Metadata completeness vs. byte availability**
   - *Metadata completeness* (`complete`, `partial`, `unknown`, `known_empty`) describes whether a relation group, Notes inventory, Context collection, or Coverage claim enumerates its full structural membership.
   - *Byte availability* describes whether `retained_metadata` (for `commit`/`tree`/`tag`), `retained_notes` (for a proven note blob), or `text_bodies` (for a Context UTF-8 text digest) is physically stored and verified in the local catalog. A commit, tree, tag, note, or Context resource may have complete or reported metadata without retained raw bytes, and conversely retained bytes for one object do not imply child or parent closure.

4. **Context availability vs. Git Core availability**
   - `core.sqlite3` and `context.sqlite3` are independently durable authorities. A catalog may operate as Git-only (`core.sqlite3` without `context.sqlite3`), Context-only (`context.sqlite3` without `core.sqlite3`), or paired (`core.sqlite3` + `context.sqlite3`).
   - Context resources may record portable Git OID references (`core_references` with `core_required = 0` plus `field_candidates` under `core_ref:<role>`) before the referenced Git object exists in `core.sqlite3`. When `core.sqlite3` is present and contains the referenced `(object_format, full_oid)`, `Context.link_core` promotes `core_required = 1` without mutating `core.sqlite3`.

5. **Durable authority vs. Operational progress**
   - `core.sqlite3` and `context.sqlite3` hold authoritative domain facts.
   - `operational.sqlite3` (`acquisition_requests`, `request_budgets`, `acquisition_attempts`, `work_accounting`, `request_continuations`, `retry_state`, `cache_locators`) holds reconstructible progress, finite cumulative actual-work accounting, continuation checkpoints, and retry/backoff state. Deleting and recreating `operational.sqlite3` invalidates old in-flight continuations (`CONTINUATION_UNAVAILABLE`) while preserving all committed Core and Context facts intact.

6. **Authoritative query results vs. derivative Search candidates**
   - `search.sqlite3` (`search_projections`, `search_documents`) is a disposable, reconstructible candidate index restricted to `projection_kind IN ('git_metadata', 'notes', 'context_text')`.
   - Every P6 search response validates candidate keys against the pinned authoritative snapshot (`core`, `context`, or `PairSnapshot`) before returning results, and transparently falls back to an authoritative snapshot scan (`backend = 'authority_scan'`) whenever `search.sqlite3` is absent, unbuilt, stale for the pinned snapshot token, incomplete, or corrupt.

---

## 1. Consumption of P1–P4 Ports and Adapters

P5 and P6 consume the following P1–P4 contracts. Their shared time/types/opt-in DDL are corrected once under ADR 0028 and the identical shared commit is incorporated by both siblings:

- **P1 Schema & Store Initialization (`repo_catalog.adapters.sqlite.p1_schema`)**:
  - `STORES = ("core", "context", "operational", "search")`, `compose`, `fingerprint`, `verify_declared`, `initialize`, `connect`.
  - Classified time constraints and nullable observation types may change opt-in DDL. Regenerate and audit fingerprints and disposition; do not hide the change or alter public Schema 21.
- **P1/P2 Git Core (`repo_catalog.domain.p1_core`, `repo_catalog.domain.ports.p1_core`, `repo_catalog.adapters.sqlite.git_core`, `repo_catalog.adapters.git.native`, `repo_catalog.domain.git_native`)**:
  - `GitCore` (`admit_repository`, `admit_repository_claim`, `admit_observation`, `admit_coverage_scope`, `admit_coverage`, `admit_coverage_proof`, `admit_object`, `admit_claim`, `admit_group`, `admit_capture`, `admit_notes_claim`, `admit_notes_group`, `admit_notes_role`, `admit_metadata`, `admit_note`, `admit_notes_inventory`, `scalar`, `relations`, `coverage`, `read_metadata`, `read_note`, `notes_projection`, `notes_inventories`, `catalog_identity`, `sql`, `for_transaction`).
  - `GitNativeSource` (`metadata`, `refs`, `object_format`, `metadata_bytes`).
- **P1/P3 Context (`repo_catalog.domain.p1_context`, `repo_catalog.domain.production_context`, `repo_catalog.domain.ports.production_context`, `repo_catalog.adapters.sqlite.production_context`)**:
  - `Context` (`transaction`, `snapshot`, `for_transaction`, `for_snapshot`, `provider`, `repository`, `source`, `source_repositories`, `associate_source`, `inventory`, `resource`, `resources`, `observe`, `inherit_fields`, `relation`, `relations`, `collection`, `collection_coverage`, `prove_collection`, `prove_inventory`, `text`, `read_text`, `admit_text`, `candidates`, `admit_field`, `admit_repository`, `repository_candidates`, `scope`, `admit_coverage`, `coverage`, `link_core`, `report_core_reference`, `core_dependencies`).
- **P1 Coordination, Work Ledger, and Derivative Search (`repo_catalog.domain.p1_coordination`, `repo_catalog.adapters.sqlite.p1_coordination`)**:
  - `PairCoordinator` (`admit`, `snapshots`, `core_snapshot`, `stop`, `backup_candidate`, `validate_backup`), `PairSnapshot`, `SnapshotToken`, `WorkLedger`, `NotesWorkBudget`, `SearchProjection`.
- **P4 Production Notes (`repo_catalog.domain.notes`, `repo_catalog.domain.ports.notes`, `repo_catalog.application.notes`, `repo_catalog.adapters.git.notes`, `repo_catalog.adapters.sqlite.notes`)**:
  - `NotesAcquisition` (`discover`, `acquire_note`, `inventory`, `admit_external_capture`, `admit_external_claim`), `GitNotesSource`, `NotesProgress`.

---

## 2. Acquisition Input and Observation Identity Contracts (P5)

### 2.1 Metadata-First Git Acquisition (`GitAcquisition`)
- **Inputs**:
  1. Local repository via `GitNativeSource` (and optional `GitNotesSource` / `NotesAcquisition` delegation for `refs/notes/*`), or
  2. Explicit metadata-only claims/observations (`ScalarClaim`, `RelationGroup`, `GitObservation`, `CoverageClaim`, `NativeObject` for `commit`/`tree`/`tag`) when raw object bodies or full repository closure are unavailable.
- **Identity & Provenance**:
  - Repository identity is a canonical lowercase UUIDv4 (`repository_uuidv4`).
  - Every `GitObservation` carries `(capture_origin_uuidv4, capture_uuidv4, repository_uuidv4, observation_kind, subject, value, provenance_json)`.
  - Ref observations (`observation_kind = "ref"`) record `ref` name, `observed_at_us`, `target` `(object_format, full_oid)`, `target_type`, and optional peeled target `(object_format, full_oid)` without requiring the target or peeled object body to be retained.
  - Selected `commit`, `tree`, and `tag` objects are acquired either as verified native representations (`GitCore.admit_metadata`) or as nominal object identities (`GitCore.admit_object`) plus reported claims/relations (`GitCore.admit_claim`, `GitCore.admit_group`), preserving missing child/parent/tree/tag target OIDs as nominal entries in `git_objects`.
  - Ordinary file blobs (`kind == "blob"` outside proven Notes role paths) are rejected at every acquisition boundary with `CoreFailure("RETENTION_PURPOSE", ...)`.
  - Git Notes discovery, proof verification, note body retention, and inventory persistence delegate directly to P4's `NotesAcquisition`.

### 2.2 Provider Acquisition into Context (`ProviderAcquisition` & `GitHubIntake`)
- **Supported GitHub Intake Surface**:
  - Normalizes GitHub REST and GraphQL observations into typed domain records for P3 `Context`:
    - Service instance registration (`service_instance_uuidv4`, `provider_type = "github"`, `configuration_json`).
    - Repository registration (`repository_uuidv4`, `attributes_json`) and repository-level `FieldCandidate` observations.
    - Source registration (`source_uuidv4`, `service_instance_uuidv4`, `configuration_json`), known-positive `associate_source(source_uuidv4, repository_uuidv4)`, and `SourceInventory` observations (`complete`, `partial`, `unknown`, `known_empty`).
    - Root resources: `issue` (`ResourceKey(service_instance_uuidv4, "issue", canonical_db_id)`) and `pull_request` (`ResourceKey(service_instance_uuidv4, "pull_request", canonical_db_id)`). Issues API entries containing `"pull_request"` are filtered from ordinary issue intake so PRs and Issues never alias.
    - Child/document resources with explicit parent and document-kind coordinates:
      - `pr_title` and `pr_body` documents under `pull_request`
      - `review` summaries under `pull_request` (no synthetic update clock; `submitted_at_us` and `state` recorded with observation clock)
      - `review_thread` resources under `pull_request` (`resolved`, `outdated`, diff anchors)
      - `review_comment` documents under `pull_request` with `ResourceRelation` edges to `review` and `review_thread` / `in_reply_to`
      - `issue_comment` documents under `issue` or `pull_request`
      - `timeline_event`, `pr_commit`, and `pr_file` context observations (recording path/status/additions/deletions/patch metadata as Context fields/text without retaining Git file blobs in Core).
  - **Field Clocks, Explicit Nulls, and Text**:
    - Every field observation produces a `FieldCandidate` with a typed `FieldClock(domain, value)` (`int` microsecond timestamp for provider clocks such as `github:issue:updated_at`, `github:pr:updated_at`, `github:comment:updated_at`, or `None` for unknown Provider time; compare observation times only when both are known and comparable, retaining incomparable alternatives).
    - Missing fields in partial REST/GraphQL payloads are omitted (never erasing prior candidates), whereas explicit provider `null` values are encoded as JSON `"null"` (`FieldCandidate(..., value_json="null", ...)`).
    - Text bodies (`body`, `title`, `diff_hunk`, `patch`) are stored once in `text_bodies` via `Context.admit_text` / `Context.text` (keyed by exact UTF-8 SHA-256) and linked via `text_body_sha256` or field-specific candidate attributes.
    - Detached issue-attachment transfer preserves `ResourceKey` identity, all existing `FieldCandidate` provenance, and adds the new `repository_uuidv4` candidate or association without rewriting prior history.

---

## Classified times and integrity (binding owner correction)

ADR 0028 governs all below examples and historical v1 descriptions. Observation,
acquisition and Provider absolute times are NULL or positive int64; required
Coverage/terminal coordinates remain positive nonnull. Git-native times remain
signed int64 even through Exchange. FieldCandidate unknown observation is nullable.
Never fabricate unknown coordinates or use receipt order for incomparable clocks.

The corrected wire version declares canonical-data SHA-256 and import compares
that declaration with receiver recomputation before domain admission. Exact
normalization, binary encoding, finite limits and framing belong to the P5
implementation contract. No HMAC/PKI/signature/authentication is implemented or
required. P6's keyless cursor digest is a checksum with independent semantic
validation. The earlier v1 shape below is an implementation starting point, not a
compatibility requirement or a claim that digest comparison was already present.

## 3. Typed Exchange Vocabulary and Wire Contract (`git-repo-db/p5-exchange-v1`)

### 3.1 Deterministic Envelope Structure
Exchange packages are deterministic, canonical JSON objects (UTF-8, sorted keys, no insignificant whitespace in canonical digest calculation) with schema identifier:

```json
{
  "format": "git-repo-db/p5-exchange-v1",
  "package_id": "<transport-envelope-uuidv4>",
  "exported_at_us": 1700000000000000,
  "sender_catalog_instance_uuidv4": "<uuidv4>",
  "repository_uuidv4": "<uuidv4>",
  "selection_scope": { ... },
  "core": {
    "repositories": [ ... ],
    "repository_claims": [ ... ],
    "git_objects": [ ... ],
    "scalar_claims": [ ... ],
    "relation_groups": [ ... ],
    "git_observations": [ ... ],
    "captures": [ ... ],
    "notes_claims": [ ... ],
    "notes_groups": [ ... ],
    "notes_inventories": [ ... ],
    "retained_metadata": [ ... ],
    "note_roles": [ ... ],
    "retained_notes": [ ... ],
    "coverage_scopes": [ ... ],
    "coverage_claims": [ ... ],
    "coverage_proofs": [ ... ]
  },
  "context": {
    "providers": [ ... ],
    "repositories": [ ... ],
    "repository_candidates": [ ... ],
    "sources": [ ... ],
    "source_repositories": [ ... ],
    "source_inventories": [ ... ],
    "resources": [ ... ],
    "resource_relations": [ ... ],
    "collections": [ ... ],
    "text_bodies": [ ... ],
    "field_candidates": [ ... ],
    "core_references": [ ... ],
    "coverage_scopes": [ ... ],
    "coverage_claims": [ ... ],
    "coverage_proofs": [ ... ]
  }
}
```

### 3.2 Binary Payload Encoding in Exchange
- Raw bytes in `core.retained_metadata` (`body`), `core.note_roles` (`proof_bundle`), and `core.retained_notes` (`body`, `proof_bundle`) are encoded in JSON as lowercase hexadecimal (`body_hex`, `proof_bundle_hex`) alongside `declared_size` and `digest_sha256`.
- No ordinary Git blob is ever exported or imported in `retained_metadata`.

---

## 4. Receiver-Side Validation vs. Sender-Attributed Claims

When importing a `git-repo-db/p5-exchange-v1` package:

1. **Envelope Identity**: `package_id` and `sender_catalog_instance_uuidv4` are used only for Operational receipt/idempotency tracking if `operational.sqlite3` is present; they are never written into `core.sqlite3` or `context.sqlite3`.
2. **Original Provenance Preservation**: All imported claims, groups, observations, captures, field candidates, collections, and coverage claims retain their original `provenance_json`, `(capture_origin_uuidv4, capture_uuidv4)`, and `observed_at_us` untouched across initial import, repeat import, reverse import (B→A), and onward multi-hop forwarding (A→B→C).
3. **Strict Receiver Verification of Intrinsic & Byte Artifacts**:
   - **Sender-attributed `authority='intrinsic'` claims/groups without accompanying `retained_metadata` bytes**: A sender cannot force a receiver to accept `authority='intrinsic'` scalar claims or relation groups merely by labeling them `intrinsic`. Reported claims (`authority='reported'`) are admitted directly via `admit_claim` / `admit_group`. Intrinsic claims/groups on the receiver are produced **exclusively** when the receiver validates the accompanying `NativeObject` in `retained_metadata` via `GitCore.admit_metadata`!
   - **Retained metadata (`commit`, `tree`, `tag`)**: Receiver reconstructs `NativeObject` from `body_hex`, verifies `declared_size`, `digest_sha256`, native Git OID hash (`native_oid(object_format, native_type, body)`), and full native grammar (`parse_metadata`), and admits via `GitCore.admit_metadata`. Any tampering or ordinary `blob` entry is refused with `CoreFailure` before mutating Core.
   - **Notes roles and retained notes**: Receiver reconstructs `NotesProof` from the structural objects in `proof_bundle_hex`, verifies full root-to-leaf path and fanout geometry via `GitCore.admit_notes_role` (and verifies note blob OID/digest/size via `GitCore.admit_note`). Unproven note mappings are admitted only as `NotesClaim` / reported `NotesGroup`, never as `note_roles` or `retained_notes`.
   - **Context text bodies**: Receiver computes `sha256(text_value.encode("utf-8"))` and rejects any `text_bodies` entry whose declared `text_sha256` does not match (`ContextError("TEXT_HASH_MISMATCH", ...)`).
   - **Context Core references**: Imported `core_references` are always checked against the receiver's own `core.sqlite3` availability. Even if the sender exported `core_required = True`, if the receiver's `core.sqlite3` is absent or does not yet contain `(object_format, full_oid)`, the receiver admits the reference via `report_core_reference` (`core_required = False`, `available = False`) and promotes it via `link_core` (`core_required = True`, `available = True`) only when the receiver's own `core.sqlite3` contains the OID.

---

## 5. Core-First Dependent Context Admission Behavior

- Cross-store admission uses `PairCoordinator.admit(core_unit, context_unit, cut=...)`:
  1. **Step 1 (Core)**: `core_unit(core_db)` executes inside a `BEGIN IMMEDIATE` transaction on `core.sqlite3` using `GitCore.for_transaction(core_db)` and commits first.
  2. **Step 2 (Context)**: `context_unit(context_db)` executes inside a `BEGIN IMMEDIATE` transaction on `context.sqlite3` using `Context.for_transaction(context_db, directory)`, with an availability callback querying committed `core.sqlite3` for `git_objects` existence.
- **Failure & Retry Semantics**:
  - If `core_unit` fails, neither store changes (`PairAdmission(False, False)`).
  - If `core_unit` commits and `context_unit` fails (`PairAdmission(True, False)`), Core facts remain durably committed and immutable, while Context rolls back completely. Retrying the same acquisition or Exchange package is idempotent on Core (preserving original `physical_copy_uuidv4`, `capture_uuidv4`, and `provenance_json`) and completes the Context admission on retry (`PairAdmission(True, True)`).
- **Late Core Arrival**:
  - If Context admission runs first (in Context-only mode or before Git objects are fetched), `CoreReference` entries are recorded via `report_core_reference` (`available = False`, `required = False`).
  - When subsequent Git acquisition or Exchange admits the referenced `OID` into `core.sqlite3`, `PairedAcquisitionCoordinator.reconcile_core_dependencies()` (or paired Exchange admission) promotes matching `core_references` to `core_required = 1` via `Context.link_core`.

---

## 6. Operational Ownership of Retry and Unresolved Processing State

- `operational.sqlite3` owns all non-authoritative execution state via `WorkLedger` and `OperationalProgress` (`adapters/sqlite/acquisition.py`):
  - **Finite Work Accounting**: Every acquisition or Exchange request registers a `RequestIdentity(capture_origin_uuidv4, request_uuidv4)` and finite `work_limits` (`input_bytes`, `verification_bytes`, `metadata_units`, `proof_steps`) in `WorkLedger`. Actual work is pre-reserved before execution and never refunded on rollback or retry.
  - **Continuation Checkpoints**: Resumable progress uses `WorkLedger.checkpoint` with the mandatory `["work-ledger", "checkpoint", 1]` count/XOR digest verification against `work_accounting`.
  - **Retry & Unresolved State (`retry_state` & `cache_locators`)**:
    - Transient transport failures, rate limits, partial page interruptions, lost Exchange acknowledgments, and unresolved Core OID dependencies awaiting future fetch are recorded in `operational.sqlite3.retry_state(scope_key_json, attempt_count, next_retry_at_us, state_json)` and `cache_locators`.
    - Deleting `operational.sqlite3` clears all retry schedules, cache locators, and continuations without affecting `core.sqlite3` or `context.sqlite3`.

---

## 7. Git-Only, Context-Only, and Paired Query Semantics (P6)

`ProductionQueryService` (`application/production_query.py`) supports three explicit catalog topologies without requiring unused stores to exist on disk:

1. **Git-Only (`core_only`)**:
   - Opens `core.sqlite3` in a read-only snapshot transaction (checking `p1-recovery-stop.json` before and after every read).
   - Queries repository identity/claims, Git objects (`commit`, `tree`, `tag`, nominal `blob`/missing OIDs), scalar claims (`canonical` vs `alternatives` + `reported_conflict`), relation groups (`commit_tree`, `commit_parents`, `tree_entries`, `tag_target`), ref/root `git_observations`, Notes captures/projections/inventories, Core `coverage_claims`, and verification-aware bytes (`read_metadata`, `read_note`).
2. **Context-Only (`context_only`)**:
   - Opens `context.sqlite3` via `Context.snapshot(directory)`.
   - Queries providers, repositories, sources, source inventories, resources (`issue`, `pull_request`, `review`, `review_thread`, `review_comment`, `issue_comment`, etc.), current `FieldCandidate` winners (including competing incomparable/equal candidates and explicit `"null"` vs unobserved), child/document hierarchies, `ResourceRelation` edges, `CollectionObservation` coverage, `CoreReference` dependencies (with `available = False` when `core.sqlite3` is absent), Context `coverage_claims`, and verified UTF-8 text bodies (`read_text`).
3. **Paired (`paired`)**:
   - Opens a pinned two-store snapshot via `PairCoordinator(directory).snapshots()`, validating repository/instance UUID identity and recovery-stop absence across both stores (`PairSnapshot` with `SnapshotToken`).
   - Resolves cross-store queries (`PairedResourceView`) within the pinned snapshot: for any PR, review, review comment, or commit context resource, joins Context `core_references` (`head`, `base`, `merge`, `target_commit`, `original_commit`) against Core `git_objects`, scalar claims, relation groups, Notes projections, and retained metadata availability at that exact `SnapshotToken`.

### Verification-Aware Byte Reads
- Retained metadata bytes (`GitCore.read_metadata`), retained note bytes (`GitCore.read_note`), and Context text bodies (`Context.read_text`) always verify size, SHA-256, UTF-8/nativeOID/grammar/proof integrity on read.
- If a representation is not retained locally, the query returns a typed `ByteReadResult(available=False, body=None, ...)` without error.
- If a retained representation in `core.sqlite3` or `context.sqlite3` fails integrity verification on read, the store immediately persists `p1-recovery-stop.json` and raises `AUTHORITATIVE_CORRUPTION` (`CoreFailure` or `ContextError`), fencing further normal operations.

---

## 8. Snapshot Tokens, Pagination, and Search Freshness/Fallback (P6)

### 8.1 Snapshot / Freshness Tokens
- Every P6 query and search response carries a deterministic `SnapshotFenceToken`:
  - In `paired` mode: wraps `PairSnapshot.token` (`SnapshotToken(repository_uuidv4, catalog_instance_uuidv4, core_commit_ marker, context_commit_marker)`).
  - In `core_only` or `context_only` mode: computes a canonical single-store snapshot token over `(mode, repository_uuidv4, catalog_instance_uuidv4, store_state_digest)` using the same canonical JSON format so single-store pagination and single-store `search.sqlite3` projections are fenced identically to paired snapshots.

### 8.2 Deterministic Pagination
- All list/collection/search endpoints accept `PageRequest(limit: int, cursor: str | None = None, expected_token: str | None = None)` and return `PageResult(items, snapshot_token, next_cursor, has_more, total_count)`.
- Ordering is strictly deterministic by canonical semantic primary keys:
  - Git objects: `(object_format, full_oid)`
  - Git observations: `(observation_kind, subject_json, capture_origin_uuidv4, capture_uuidv4)`
  - Captures: `(notes_ref, capture_origin_uuidv4, capture_uuidv4)`
  - Context resources: `(service_instance_uuidv4, resource_kind, provider_resource_id)`
  - Field candidates: `(field_name, clock_domain, source_clock, observed_at_us, provenance_json)`
  - Search hits: `(projection_kind, document_key_json)`
- `PaginationCursor` encodes `(endpoint_kind, filter_digest, snapshot_token, last_semantic_key)`.
- If a caller supplies a cursor or `expected_token` whose `snapshot_token` does not match the catalog's current snapshot (or if the cursor is malformed or belongs to a different endpoint/filter), P6 raises a typed `QueryError("SNAPSHOT_MISMATCH" | "INVALID_CURSOR", ...)` rather than silently mixing rows across different catalog states.

### 8.3 Derivative Search and Fallback (`ProductionSearchAdapter` & `ProductionSearchService`)
- Supported `projection_kind` values in `search.sqlite3`:
  - `git_metadata`: commit/tag messages, author/committer/tagger identities, tag names, ref names, and decoded tree entry names (never ordinary file-blob contents).
  - `notes`: verified/reported note UTF-8 text or hex-safe summaries keyed by `(capture_origin_uuidv4, capture_uuidv4, target_format, target_oid, note_oid)`.
  - `context_text`: current Context string fields and resolved `text_bodies` (`text_body_sha256`) keyed by `(service_instance_uuidv4, resource_kind, provider_resource_id, field_name, provenance_json)`.
- **Freshness, Completeness, and Fallback**:
  - A projection in `search.sqlite3` is used (`backend = "projection"`) only when `search_projections` has a row for `(projection_kind, snapshot_token_json)` matching the pinned authoritative snapshot token AND candidate keys pass authoritative verification against the pinned snapshot.
  - If `search.sqlite3` is missing, unreadable, corrupt (`sqlite3.DatabaseError`), missing tables, stale (different `snapshot_token_json`), or has candidate rows that fail authoritative snapshot verification, `ProductionSearchService` catches the derivative failure without writing `p1-recovery-stop.json` and executes an authoritative snapshot scan (`backend = "authority_scan"`), returning identical verified `SearchHit` results.

---

## 9. Exclusive File and Module Ownership (P5 vs. P6)

To guarantee conflict-free parallel execution and clean sibling merges, file ownership is partitioned as follows:

### Shared Technical Contract PR (`docs/p5-p6-technical-contract`)
- `docs/implementation/p5-p6-technical-contract.md`
- `scripts/audit_callsite_dependencies.py` (registers both P5 and P6 isolated module paths in `ISOLATED_NEXT_STAGE_MODULES`)
- `tests/integration/p1/test_disposition.py` (extends isolated import guard parametrization for P5 and P6 module paths)

### P5 Exclusive Ownership (`feat/p5-production-acquisition-exchange`)
- `src/repo_catalog/domain/acquisition.py`
- `src/repo_catalog/domain/exchange.py`
- `src/repo_catalog/domain/ports/acquisition.py`
- `src/repo_catalog/application/acquisition.py`
- `src/repo_catalog/application/exchange.py`
- `src/repo_catalog/adapters/github/production_intake.py`
- `src/repo_catalog/adapters/sqlite/acquisition.py`
- `tests/integration/p5/__init__.py`
- `tests/integration/p5/conftest.py`
- `tests/integration/p5/test_git_acquisition.py`
- `tests/integration/p5/test_provider_acquisition.py`
- `tests/integration/p5/test_paired_admission.py`
- `tests/integration/p5/test_exchange.py`
- `tests/packaging/test_p5_distribution.py`
- `docs/implementation/p5-production-acquisition-exchange.md`
- `docs/implementation/p5-execution-evidence.json`
- `docs/implementation/p5-independent-review.md`

### P6 Exclusive Ownership (`feat/p6-production-query-search`)
- `src/repo_catalog/domain/production_query.py`
- `src/repo_catalog/domain/ports/production_query.py`
- `src/repo_catalog/application/production_query.py`
- `src/repo_catalog/adapters/sqlite/production_search.py`
- `src/repo_catalog/cli/production_query.py`
- `tests/integration/p6/__init__.py`
- `tests/integration/p6/conftest.py`
- `tests/integration/p6/test_queries.py`
- `tests/integration/p6/test_pagination_snapshots.py`
- `tests/integration/p6/test_search_fallback.py`
- `tests/integration/p6/test_cli.py`
- `tests/packaging/test_p6_distribution.py`
- `docs/implementation/p6-production-query-search.md`
- `docs/implementation/p6-execution-evidence.json`
- `docs/implementation/p6-independent-review.md`

### Combined Integration Verification Branch (`validation/p5-p6-combined-integration`)
- Merges `feat/p5-production-acquisition-exchange` and `feat/p6-production-query-search` cleanly with zero file conflicts.
- Adds cross-workstream compatibility and end-to-end adversarial suites under:
  - `tests/integration/p5_p6_compatibility/__init__.py`
  - `tests/integration/p5_p6_compatibility/test_end_to_end_p5_p6.py`

---

## 10. Integrated P5+P6 Acceptance Test Requirements

While P5 tests verify acquisition/admission/Exchange against P1–P4 stores and P6 tests verify queries/pagination/Search/CLI against P1–P4 stores, the following end-to-end acceptance tests require the integrated P5+P6 tree (`tests/integration/p5_p6_compatibility/test_end_to_end_p5_p6.py`):

1. **End-to-End Git + Notes + Provider Acquisition into Query & Search (SHA-1 and SHA-256)**:
   - Acquire commits, trees, tags, refs, and proven Git Notes via P5 (`GitAcquisition`) and GitHub PRs/Issues/reviews/threads/comments/Core-references via P5 (`ProviderAcquisition` / `PairedAcquisitionCoordinator`), then query via P6 (`ProductionQueryService` and opt-in CLI) across `core_only`, `context_only`, and `paired` modes, verifying exact byte reads, Coverage projections, and `Search` candidate indexing + fallback.
2. **Multi-Hop Exchange (A → B → C) and Reverse Exchange (B → A) into P6 Queries and Search**:
   - Export selective and full packages from Catalog A using P5 `ExchangeService`, import into Catalog B and onward to Catalog C, and verify via P6 queries, pagination, and Search that all provenance, competing field candidates, Notes proofs/claims, Coverage states, and paired Core-reference resolutions match across catalogs without transport-envelope leakage.
3. **Late Core Dependency Resolution Across Exchange and P6 Paired Reads**:
   - Import Context PR/review observations with Core commit OID references into Catalog B before the Git commits exist (`available = False` in P6 paired query), then import the Git Core package via P5 Exchange, reconcile dependencies, and verify via P6 that the new `SnapshotFenceToken` reflects `available = True, required = True` while older pagination cursors fail closed with `SNAPSHOT_MISMATCH`.
4. **Derivative Loss (`operational.sqlite3` and `search.sqlite3` deletion/corruption) Under Active P5 + P6 Workload**:
   - Delete or corrupt `operational.sqlite3` and `search.sqlite3` after P5 acquisition and Search index build; verify that P6 authoritative queries and Search fallback (`authority_scan`) return identical results without triggering `p1-recovery-stop.json`, and that P5 rejects stale Operational continuations while admitting new requests cleanly.
5. **Authoritative Corruption Stop Propagation Across P5 and P6**:
   - Tamper with a committed `retained_metadata` or `retained_notes` byte row in `core.sqlite3`; verify that P6 verification-aware byte read detects the mismatch, writes `p1-recovery-stop.json`, and raises `AUTHORITATIVE_CORRUPTION`, after which both P5 admissions/Exchange imports and P6 queries/CLI commands fail closed with `RECOVERY_STOP` / `RECOVERY_REQUIRED`.
