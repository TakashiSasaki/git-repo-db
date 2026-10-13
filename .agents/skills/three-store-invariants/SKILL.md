---
name: three-store-invariants
description: Maintain and verify architectural invariants across the Three-Store Boundary (Core, Operational, Search) in git-repo-db under ADR 0002. Use when debugging cross-store isolation, fail-closed cache GC under operational store loss, non-atomic split-write resumption, Core-only maintenance checks, search snapshot pinning, or search freshness fencing.
---

# Three-Store Boundary Architectural Invariants (ADR 0002)

Under binding decisions PF-P01–PF-P17, `git-repo-db` enforces physical separation across three distinct SQLite stores:
- **Core Store (`catalog.sqlite3`)**: Authoritative domain facts, entities, immutable observations, coverage claims, code listings, Git DAG and intrinsic structures, and Exchange staging.
- **Operational Store (`operational.sqlite3`)**: Transient execution state, jobs, job attempts, capacity reservations, and cache leases.
- **Search Store (`search.sqlite3`)**: Disposable FTS5 virtual tables, rebuildable search document projections, and index generations.

Follow these proven patterns to prevent cross-store coupling, data loss, false progress, and spurious integrity failures.

---

## 1. Fail-Closed Cache Protection Under Operational DB Loss

### Symptom
If the Operational DB is lost or recreated, Operational mappings (`active_cache_entries`, `cache_locators`) disappear. A naive cache GC gate checking only Operational tables would find no active leases or locators and delete physical Git packfiles (`cache/<repo_uuid>/<gen>.git`), even though unfulfilled Core preservation obligations still depend on them.

### Rule & Invariant
- Loss of Operational DB must never be interpreted as evidence that physical cached objects are safe to delete.
- Incomplete Core preservation obligations (`preservation_obligations.roots_fixed = 1 AND complete = 0`) unconditionally block deletion of physical cache bytes.
- Missing or uncertain Operational associations fail closed.

### Remediation Pattern
1. **Core-Direct Query in `CacheManager.gate()`:**
   Query Core DB directly for incomplete preservation obligations matching the repository UUID. If any exist, inspect Operational mappings; if Operational records are missing or unlinked, block deletion with `["pending_obligations:" + acq_id]`.
2. **Orphaned Generation Enrollment in `CacheManager.collect()`:**
   Enumerate physical directories under `cache/<repo_uuid>/` on disk. If any physical generation exists that is not registered in Operational DB, safely enroll it into `active_cache_entries` and `cache_locators` before evaluating gates.
3. **Generation Collision Prevention in `GitImporter.sync()`:**
   When allocating a new cache generation, inspect max generation across Core snapshots, Operational progress, and physical disk paths:
   ```python
   generation = max(core_gen, op_gen, disk_gen) + 1
   ```

---

## 2. Core-Only Maintenance and Backup/Restore Isolation (PF-P08, PF-P14, PF-P17)

### Symptom
`repo-catalog check` or backup/restore fails or reports Core corruption when `search.sqlite3` is absent, stale, or corrupt. Or, a read-only check attempts an FTS5 write mutation (e.g., `INSERT INTO fts(fts) VALUES('integrity-check')`) which raises `sqlite3.OperationalError: attempt to write a readonly database`.

### Rule & Invariant
- Core integrity verdict is completely independent of secondary store presence or integrity.
- Absent or corrupt Search DB is an optional derivative-state diagnostic condition, never Core corruption.
- Core-only backup and restore must succeed without Search DB or Operational DB.
- Read-only diagnostics must never execute mutating statements on secondary stores.
- Probe descriptions must be truthful: `LIMIT 0` probes do not verify document contents, only schema queryability.

### Remediation Pattern
1. **Separated Verdict in `MaintenanceService.check()`:**
   - Execute PRAGMA checks and domain invariants on Core DB.
   - If Search DB is absent, report `checks["index"] = {"status": "absent", "checks_performed": [], "generations": []}`.
   - Probe ready index generations with read-only `SELECT rowid FROM <table> LIMIT 0` probes. Accurately report:
     ```python
     checks["index"] = {
         "status": "queryable" if all_queryable else "failed",
         "checks_performed": ["sqlite_integrity", "foreign_keys", "table_queryable_probe"],
         "generations": [{"index_generation_id": gen_id, "probe": "queryable"}],
     }
     ```
   - Do not set `status = "failed"` on the overall check unless Core DB itself is corrupt.
2. **Safe Restoration & CAS-41 Validation:**
   - Backup backs up Core DB (`catalog.sqlite3`) and records `quarantined_payload_count` in the manifest.
   - Restore validates `quarantined_payload_count` against the verified copy before diagnosis, rejects mismatches or malformed counts, restores Core DB only, and initializes fresh instance identities. Search DB is created only upon explicit `index rebuild`.

---

## 3. Reconcile Non-Atomic Core and Operational Writes (PF-P04, PF-P07)

### Symptom
During collection or Git acquisition, a process crashes after committing Operational cursor/complete state but before committing the Core transaction. A subsequent run trusts Operational `state='complete'` and skips remaining pages, or starts from an advanced cursor, producing missing domain evidence.

### Rule & Invariant
- PF-P07 rejects distributed transactions across SQLite databases.
- Core evidence is authoritative; Operational progress is advisory and disposable.
- Operational progress alone cannot establish a complete Collection or valid resource.
- An interrupted incomplete collection must not be grafted onto: discard unproven progress and start a fresh Collection from the initial endpoint under PF-P04/PF-P07.
- For nested GraphQL children, divergence between Core continuations and Operational progress raises `CatalogError("RESUME_UNAVAILABLE")`, requiring fresh root acquisition.

### Remediation Pattern
1. **No-Grafting Recovery in `ApiFacts.begin()`:**
   Before trusting Operational progress, check for Core `completion_markers`. If absent, skip incomplete collections and create a new collection from the initial endpoint (`cursor: None`), preserving previously committed valid resources without grafting onto unproven cursors:
   ```python
   if not has_complete_marker:
       # Incomplete collection: Core lacks terminal evidence.
       # Do not trust unprovable cursor continuation; start fresh.
       continue
   ```
2. **GraphQL Child Divergence Check in `GitHubCollector._thread_child()`:**
   Verify `thread_collection_continuations` matches `collection_progress.cursor`. If diverged or cursor is missing when response is pending, raise `CatalogError("RESUME_UNAVAILABLE")`.
3. **Resilient Querying:**
   In `jobs list`, `jobs show`, and `cache status`, catch `CatalogError` with `code == "NOT_INITIALIZED"` when Operational DB is absent, returning empty records rather than raising an unhandled exception.

---

## 4. Search Snapshot Pinning, Truthful Backend Reporting, and Telemetry Isolation (PF-P15, PF-P16)

### Symptom
- Search reads Core revision, checks index fence, and fetches FTS candidates before opening the Core read transaction. A concurrent writer commits matching resources and advances Core revision, causing subsequent Core iteration to use a newer snapshot with an older candidate set and omit valid results (mixed snapshot).
- PR/Issue search reports `backend: "fts"` while actually executing `literal_match()` scans.
- Rebuilding Search DB fails because Operational telemetry insertion failed, even though the FTS index was built successfully.
- Code search candidate filtering skips objects with decoder conflicts or oversize bodies, suppressing domain coverage diagnostics.

### Rule & Invariant
- Search must establish and pin its Core read transaction snapshot before validating index fence or retrieving FTS candidates. That snapshot is maintained through result production.
- Producer side: `index.rebuild()` pins Core read snapshot during projection, ensuring `core_revision_fence` matches the actual projected data.
- Search queries for PR and Issue truthfully report `backend: "scan"` directly, avoiding unused FTS queries.
- FTS candidates are bounded (max 50,000 keys). Exceeding the bound or requesting explicit non-default decoders falls back cleanly to scan (`candidate_limit_exceeded`, `unsupported_decoder`).
- Candidate filtering must not suppress domain coverage diagnostics (`body_not_saved`, `decoder_conflict`, `oversize`). Diagnostics are evaluated before candidate filtering.
- Rebuild telemetry failure in Operational store is non-fatal: it issues a warning and records the rebuild result as successful.

### Remediation Pattern
1. **Pinned Snapshot in `QueryService.query()`:**
   ```python
   with Store(self.path, readonly=True) as s:
       with s.transaction(read=True):
           local_rev = s.revision()["local_revision"]
           # Validate index fence and fetch FTS candidates while holding Core read snapshot
           ...
           for sortkey, item in self.iter_query(command, opts):
               ...
   ```
2. **Deterministic Concurrency Barrier:**
   Expose `_search_snapshot_barrier` hook in `QueryService` for barrier-controlled concurrency testing.
3. **Telemetry Fault Isolation in `index.rebuild()`:**
   Wrap `store.operational.record_rebuild_metric` on the success path so telemetry errors emit a warning rather than failing index creation.
4. **Index Status CLI:**
   Support `repo-catalog index status` returning `status`, `core_revision`, `core_revision_fence`, `stale`, `age_us`, `generations`, and `cost_estimate`.

---

## 5. Verification Evidence & Test Reconciliation

### Discrepancy Note (118 vs 117)
Earlier PR documentation stated "118 passed" across five suites listing:
- 12 (`test_catalog3_cache.py`)
- 11 (`test_catalog3_store.py`)
- 3 (`test_search_index.py`)
- 4 (`test_database.py`)
- 87 (`test_target_schema.py`)

The actual arithmetic sum of unique executed nodes is exactly **117** ($12 + 11 + 3 + 4 + 87 = 117$).

With the addition of targeted correctness and lifecycle tests for R1–R5:
- `test_catalog3_store.py`: +7 nodes (5 parameterized multi-page recovery cases + 1 GraphQL thread divergence + 1 CAS-41 Core-only lifecycle) = **18**
- `test_search_index.py`: +3 nodes (1 barrier-controlled snapshot isolation + 1 truthful backend equivalence matrix + 1 telemetry failure & status CLI) = **6**

The full targeted integration suite now executes exactly **127** unique nodes:
$$12 + 18 + 6 + 4 + 87 = 127\text{ passed}.$$
