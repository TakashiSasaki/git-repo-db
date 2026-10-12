# Architecture Decision Record: Three-Store Boundary (PF-P01–PF-P17)

- **Status:** Accepted target design; canonical decision register for Three-Store architecture.
- **Decision date:** 2026-10-12.
- **Preceding Decisions:** Q01-B, Q02-B, Q03-B, NO_INDEPENDENT_PUBLICATION, ADR 0001 (Validation Lifecycle).
- **Binding Decisions:** PF-P01 through PF-P17.

---

## 1. Context and Motivation

Following the successful removal of independent Publication machinery (Schema 20), the catalog architecture retained operational state (jobs, attempts, cache leases, space reservations), rebuildable search structures (FTS5 tables, index generations), and core domain facts within a single monolithic SQLite schema.

This monolithic arrangement produced operational liabilities:
1. Operations like backups and crash recovery mixed durable domain facts with transient process tracking and disposable derivative search indexes.
2. Search indexes (using SQLite FTS5) required maintenance and rebuild steps inside the core domain database transaction space.
3. Operational crashes or unclean terminations left stale checkpoints and leases in the same database containing immutable historical facts.

The repository owner has accepted binding decisions **PF-P01 through PF-P17** to establish a clean, coherent Three-Store boundary:
- **Core Store (`catalog.sqlite3`)**: Houses all authoritative domain facts, entities, immutable observations, coverage claims, code listings, and Exchange staging.
- **Operational Store (`operational.sqlite3`)**: Houses transient execution state, jobs, job attempts, capacity reservations, and cache leases.
- **Search Store (`search.sqlite3`)**: Houses disposable FTS5 virtual tables, rebuildable search document projections, and index generations.

---

## 2. Binding Owner Decisions (PF-P01–PF-P17)

| ID | Binding Decision | Scope & Impact | Superseded Wording | Preserved Guarantees | Status |
|---|---|---|---|---|---|
| **PF-P01** | Do not automatically exclude a known repository from Source-selected PR/Issue acquisition merely because it is absent from a later inventory. | Source discovery & acquisition | Stale assumptions that repository absence in newer roster implies deletion or exclusion | Preserve known-positive associations and permanent identities. No automatic deletion propagation. | Accepted target design |
| **PF-P02** | General-purpose retrospective queries over arbitrary historical API Collection membership lists are not a requirement. | API collection retention | Claims that full historical API rosters must be kept indefinitely | Retain evidence needed by current functionality, completeness, conflicts, and Exchange. No indiscriminate historical deletion. | Accepted target design |
| **PF-P03** | Incremental acquisition is an optimization. Use a compatible, valid baseline when available; otherwise perform a normal full acquisition of the requested scope. | Collection & sync | Assumptions that permanent retention is guaranteed solely for incremental speed | Older complete baseline never overrides newer partial/unknown/conflicting Coverage. Full acquisition fallback is always valid. | Accepted target design |
| **PF-P04** | Resuming the same Job is best-effort. Preserve useful safe reuse, but safe new acquisition is sufficient when restart context is absent or invalid. | Job execution | Mandatory resumption across restarts or missing context | Committed domain data survives. New acquisition is not a fabricated continuation of an old observation. | Accepted target design |
| **PF-P05** | Do not implement domain-text GC in this task. Unreferenced domain text may remain. | Shared domain text storage | Speculative automatic GC implementations | Domain text remains write-once and preserved. Explicit manual GC is planned for future tasks; no deletion machinery now. | Accepted target design |
| **PF-P06** | Physically separate operational state from the core database. Move or simplify actual execution management, not evidence whose loss changes domain meaning. | Storage architecture | Monolithic single-DB schema (`catalog3.sql`) | Clean physical separation into Core and Operational databases. Durable domain evidence remains strictly in Core. | Accepted target design |
| **PF-P07** | Combine A+C: require no atomic commit across core and operational databases, and generally do not persist fine-grained execution checkpoints. | Transaction & commit boundaries | Two-phase commit, ATTACH coordination, or Publication ledgers | Keep core transactions atomic, tolerate lagging operational bookkeeping, and safely reacquire after interruption. | Accepted target design |
| **PF-P08** | Normal backups contain the core database, not the operational database. | Backup & restore | Backing up jobs, leases, or whole state-dir | Preserve required backup manifests/configuration and integrity metadata. Restoration starts with fresh operational state. | Accepted target design |
| **PF-P09** | Persistent HTTP caching is not a core requirement. HTTP validators, conditional requests, 304 handling, cache placement/retention, and transport optimizations belong to the transport adapter. | Transport adapter | Embedding HTTP cache locators and headers into core tables | Transport-private caching permitted in adapter. Cache loss never invalidates core facts or justifies invented observations. | Accepted target design |
| **PF-P10** | Add a domain attribute only for a concrete use, including genuine internal validation/coverage/Exchange needs. Explicitly model its type and provenance. | Domain modeling | Speculative generic extension framework or opaque provider replicas | Explicit typed columns or closed JSON contracts with truthful provenance. | Accepted target design |
| **PF-P11** | Each core Catalog owns one dedicated operational SQLite database. Do not share one operational database across Catalogs. | Store ownership | Shared multi-catalog operational databases | Strict 1:1 ownership between Core Catalog and Operational DB. Ownership verified to prevent cross-catalog use. | Accepted target design |
| **PF-P12** | Create a missing operational DB automatically when an operation needs it. Never silently delete/overwrite a corrupt or foreign DB. Require explicit recovery for corruption. | Operational DB lifecycle | Manual-only operational DB creation or automatic deletion of corrupt DBs | Core-only operations remain fully functional without a working operational DB. Corrupt/foreign DBs fail closed. | Accepted target design |
| **PF-P13** | Do not automatically delete completed/failed/cancelled Job records or introduce a retention TTL. Administrators may explicitly clean them up. | Operational retention | Automatic TTL cleanup of job records | Job history preserved in Operational DB until explicit administrator cleanup. | Accepted target design |
| **PF-P14** | Each Catalog owns a separate search SQLite database for FTS5 and rebuildable search derivatives. Exclude it from normal backups. | Search storage | Search tables inside core database | FTS5 and search projections isolated in `search.sqlite3`. Rebuildable derivatives excluded from backup. | Accepted target design |
| **PF-P15** | Fall back to direct core-data scanning when no valid applicable search index is usable, including missing, stale, incomplete, or detected corrupt indexes. | Search queries | Search failure when index is missing/corrupt | Direct core-data scan fallback. Notify users of index condition and fallback reasons. Distinguish index from domain coverage. | Accepted target design |
| **PF-P16** | Update/rebuild search indexes only by explicit operation. Display index age/staleness information where determinable. | Search maintenance | Automatic background rebuild schedulers | Explicit `index rebuild` only. Monotonic elapsed duration measurement and transparent empirical cost estimation. | Accepted target design |
| **PF-P17** | Search DB creation and recovery are always explicit. Ordinary reads/searches must not create, replace, or repair it. Explicit `index rebuild` may initialize an absent search DB. | Search DB lifecycle | Automatic creation of search DB during query | Ordinary reads/searches never create, replace, or repair Search DB. Foreign/corrupt Search DBs fail closed without silent overwrite. | Accepted target design |

---

## 3. Store Disposition Map

### 3.1 Core Database (`catalog.sqlite3`)
Authoritative domain facts, relationships, observations, and evidence.
- **Identity & Schema:** `database_identity`, `service_instances`, `sources`, `repositories`, `repository_bindings`, `repository_endpoints`, `repository_names`, `identity_relations`, `identity_relation_cancellations`
- **Domain Resources:** `change_requests`, `text_bodies`, `documents`, `review_threads`, `issue_resources`, `review_resources`
- **Current State Projections:** `change_request_state`, `document_state`, `review_thread_state`, `source_repositories`, `source_inventory_assessments`
- **Coverage & Evidence:** `coverage_scopes`, `coverage_claims`, `completion_markers`, `fetch_collections`, `collection_memberships`, `code_listings`, `code_listing_progress`, `thread_collection_requirements`, `thread_collection_continuations`, `thread_collection_targets`, `current_collection_pages`
- **Git Domain & Intrinsic Structure:** `git_acquisitions`, `snapshots`, `acquisition_roots`, `root_origins`, `git_objects`, `commits`, `commit_parents`, `tree_objects`, `tree_entries`, `tag_objects`, `contents`, `content_digests`, `blob_content_map`, `repository_object_sources`, `ref_observations`, `root_manifests`, `root_manifest_entries`
- **Git Facts & Code Assessments:** `git_object_payloads`, `git_commit_facts`, `git_text_facts`, `git_name_facts`, `code_assessments`, `code_acquisitions`, `code_commits`, `code_file_changes`, `change_request_events`
- **CAS & Quarantine:** `stored_bytes`, `payloads`, `payload_quarantine`, `payload_admission_staging`, `unresolved_payloads`
- **Exchange:** `exchange_local_identities`, `exchange_admissions`, `exchange_staging`, `exchange_blocked_coverage_claims`, `coverage_claim_markers`, `identity_relation_staging`

### 3.2 Operational Database (`operational.sqlite3`)
Transient and execution state. Automatically created when needed (PF-P12); missing/corrupt state never compromises Core facts.
- **Identity:** `operational_identity` (bound to `catalog_db_instance_id`, `created_at_us`)
- **Jobs & Execution:** `jobs`, `job_attempts`
- **Cache & Leases:** `cache_locators`, `active_cache_entries`, `cache_leases`, `space_reservations`
- **Acquisition Tracking:** `acquisition_progress`, `collection_progress`
- **Rebuild Telemetry:** `search_rebuild_metrics` (rebuild durations, document counts, elapsed monotonic measurements)

### 3.3 Search Database (`search.sqlite3`)
Rebuildable FTS5 derivatives. Explicitly initialized and rebuilt (PF-P16, PF-P17). Excluded from backups (PF-P14).
- **Identity:** `search_identity` (bound to `catalog_db_instance_id`, `core_revision_fence`)
- **Search Projections:** `search_documents`
- **Generations & Membership:** `index_generations`, `index_membership`
- **FTS5 Virtual Tables:** Dynamic `catalog_fts_<generation_id>` tables

### 3.4 Retired / Removed Structures
- `resume_cursors`: Retired. Replaced by direct fetch collection progress in operational store and normal full acquisition fallback.
- `incremental_scans`: Retired. Replaced by lightweight collection progress and coverage scopes.
- `content_locations`: Consolidated into Core `contents` and Operational `cache_locators`.
- `preservation_obligations.cache_locator_id`: Unlinked from disposable locators; preservation obligations retain immutable acquisition IDs.

---

## 4. Failure and Recovery Model

1. **Missing Operational DB:** Auto-created with fresh identity bound to the current Core `db_instance_id`. Core domain reads and direct-scan search operate unhindered.
2. **Corrupt / Foreign Operational DB:** Fails closed with `DATABASE_CORRUPT` or `WRONG_CATALOG_OWNER`. Administrator must explicitly remove or recover the file. Never silently overwritten.
3. **Missing Search DB:** Direct core-data scan fallback is selected (PF-P15). Explicit `index rebuild` creates and populates it.
4. **Corrupt / Stale Search DB:** Fails closed during indexed path, falling back immediately to direct core-data scanning with structured diagnostic notifications (`search_fallback_reason: stale_or_corrupt_index`).
5. **Split-Write Interruption:** Core transactions commit atomically. Operational bookkeeping updates follow. A crash between Core commit and Operational commit leaves Core authoritative; subsequent runs reacquire or recheck rather than fabricating state.
6. **Backup and Restore:** Backup copies and validates Core DB (`catalog.sqlite3`) only. Restore validates physical quarantine and core integrity, creates fresh instances, and lazily initializes fresh operational DB. Search DB is created only upon explicit administrator rebuild.
