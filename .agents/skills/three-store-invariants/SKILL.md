---
name: three-store-invariants
description: Maintain and verify architectural invariants across the Three-Store Boundary (Core, Operational, Search) in git-repo-db under ADR 0002. Use when debugging cross-store isolation, fail-closed cache GC under operational store loss, non-atomic split-write resumption, Core-only maintenance checks, or search freshness fencing.
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

### Remediation Pattern
1. **Separated Verdict in `MaintenanceService.check()`:**
   - Execute PRAGMA checks and domain invariants on Core DB.
   - If Search DB is absent, report `search.status = "absent"`.
   - Probe Search DB with read-only statements (`SELECT rowid FROM catalog_fts LIMIT 0` and `PRAGMA integrity_check`). If corrupt, report `search.status = "corrupt"`.
   - Do not set `status = "failed"` on the overall check unless Core DB itself is corrupt.
2. **Safe Restoration:**
   - Restore restores Core DB only, validates quarantine and Core integrity, creates fresh instance identities, and lazily initializes fresh Operational DB. Search DB is created only upon explicit `index rebuild`.

---

## 3. Reconcile Non-Atomic Core and Operational Writes (PF-P04, PF-P07)

### Symptom
During collection or Git acquisition, a process crashes after committing Operational cursor/complete state but before committing the Core transaction. A subsequent run trusts Operational `state='complete'` and skips remaining pages, producing missing domain evidence.

### Rule & Invariant
- PF-P07 rejects distributed transactions across SQLite databases.
- Core evidence is authoritative; Operational progress is advisory and disposable.
- Operational progress alone cannot establish a complete Collection or valid resource.
- An Operational cursor cannot skip a page whose Core evidence did not commit.

### Remediation Pattern
1. **Core Verification in `Persistence.begin()`:**
   Before trusting Operational `state='complete'`, verify that Core DB contains the corresponding `completion_markers` entry for the collection. If Core lacks completion, reject the Operational state and fall back safely to a fresh acquisition (PF-P04).
2. **Cursor Verification:**
   Before resuming from an Operational cursor, check that Core DB has committed pages matching that cursor. If Core lacks evidence, reset the cursor to the latest Core-confirmed page or fall back to start.
3. **Resilient Querying:**
   In `jobs list`, `jobs show`, and `cache status`, catch `CatalogError` with `code == "NOT_INITIALIZED"` when Operational DB is absent, returning empty records rather than raising an unhandled exception.

---

## 4. Honest Search Backend Reporting & Freshness Fencing (PF-P15, PF-P16)

### Symptom
Query service reports `backend: "fts"` even when falling back to Core scanning because the index is stale or absent, or query service crashes when Search DB rebuild metrics have no recorded runs.

### Rule & Invariant
- Queries report `backend: "fts"` only when candidate keys were retrieved from a healthy, fresh FTS5 virtual table.
- Index freshness is bound by `core_revision_fence == local_revision`.
- Stale, absent, or corrupt indexes transparently fall back to Core scanning with `backend: "scan"`, `search_fallback: true`, and truthful `search_fallback_reason`.
- Rebuild cost estimation returns `None` (or null in JSON) when `runs == 0`, never an unvalidated average or crash.

### Remediation Pattern
1. In `QueryService.query()`:
   Check `search_store.is_ready()` and compare `core_revision_fence` against `core.local_revision()`.
   If stale or unavailable, use Core table scan with:
   ```python
   execution = {
       "backend": "scan",
       "search_fallback": True,
       "search_fallback_reason": "stale_index" if stale else "index_unavailable",
   }
   ```
2. In `OperationalStore.estimate_rebuild_cost()` and `SearchStore.estimate_rebuild_cost()`:
   If recorded runs is zero, return `{"runs": 0, "estimated_duration_ms": None}`.
