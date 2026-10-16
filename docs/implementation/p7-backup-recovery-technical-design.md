# P7 Production Consistent Backup, Corruption Stop, Read-Only Salvage, and Fresh Restore Technical Design

Status: Proposed engineering specification under accepted ADR 0026 and supporting decisions ADR 0001, ADR 0003, ADR 0014–0025, ADR 0027, and ADR 0028.
Owner architectural blockers: Zero.
Scope: Implements production backup, corruption stop, read-only forensic preservation, untrusted typed salvage, verified fresh restore, and safe activation for `git-repo-db`.

---

## 1. Architectural Foundation and ADR 0026 Mandate

Under accepted ADR 0026, the recovery architecture establishes a strict operational lifecycle:
$$\text{Ordinary Operation} \longrightarrow \text{Authoritative Corruption Detected} \longrightarrow \text{Persistent Catalog Recovery Mode (Stop)}$$

Key Architectural Invariants:
1. **No Quarantine State or Lifecycle:** No per-object or per-payload quarantine flag, active set/count, release or retirement lifecycle belongs to the target format. The legacy CAS-41 quarantine predicates and comparison counts are fully retired.
2. **Whole-Catalog Stop:** When authoritative corruption (retained-byte digest mismatch, SQLite structural failure, or domain constraint invalidation) is detected in Git Core or Context, the affected catalog instance is immediately stopped. Ordinary queries, acquisition, Exchange admission/output, background writes, and normal backup completions are fenced.
3. **No In-Place Modification:** The suspect catalog source files, journals, WAL files, and forensic incident markers must be preserved strictly read-only. No diagnostic `INSERT`, repair trigger, in-place SQLite `.recover`, `VACUUM`, or schema mutation may alter the suspect source.
4. **Untrusted Typed Salvage:** Salvaged records extracted from a stopped suspect catalog are untrusted candidate data. Salvage serialization preserves candidate identity, original Capture UUIDv4 pair, source attribution, genuine recoverable bytes, and honest unreadable/incomplete bounds. No salvaged row or sender flag grants intrinsic receiver authority.
5. **Fresh Verified Destination:** Restoration always proceeds into a fresh, distinct directory stage, never in place over the suspect source or an existing destination. A baseline verified backup is restored, revalidated across actual domain bytes and Core/Context paired constraints, merged with independently admissible salvaged candidates via typed receiver interfaces, re-audited, and activated via an atomic locator/handover boundary.

---

## 2. Technical Design Specifications

### 2.1 Git-Only and Paired Backup Scopes

The backup subsystem supports exactly two explicit scopes:
- `git_only`: Captures the authoritative Git Core store (`core.sqlite3`), permanent repository identity (`repository_uuidv4`), catalog instance identity, schema fingerprints, and retained metadata/notes byte representations. Context is omitted and explicitly declared absent.
- `paired`: Captures a mutually consistent snapshot of both authoritative stores: Git Core (`core.sqlite3`) and Context (`context.sqlite3`), along with paired consistency evidence (`paired_cut_evidence.json`).

Reconstructible stores (`operational.sqlite3`, `search.sqlite3`) are never included in normal backups. They are reconstructed afresh during activation.

### 2.2 Consistent Core+Context Snapshot Protocol

To achieve a consistent snapshot across independent SQLite databases without holding long-lived write locks:
1. **Writer Fencing:** Acquire the common catalog coordinator writer lock (`catalog_gate` via `p1-writer.lock`).
2. **Transactional Snapshot Cut:** Open read-only snapshot transactions on both `core.sqlite3` and `context.sqlite3` using SQLite WAL read transactions.
3. **Paired Integrity Anchor:** Record the maximum commit sequence / transaction state and compute cross-store referential bounds: verify that any Context reference to a Git Core commit or object format references an entity present within the Core snapshot.
4. **Online VACUUM INTO / Backup API:** Stream the snapshot pages into temporary backup files (`core.sqlite3.bak`, `context.sqlite3.bak`) via SQLite online backup API (`sqlite3_backup_*`) or `VACUUM INTO`, ensuring page-level consistency without dirty partial reads.
5. **Release Writer Lock:** Release `catalog_gate`. All subsequent validation, hashing, and archive packaging proceed out of band.

### 2.3 Backup Artifact Structure and Manifest Schema

The durable backup artifact is a single directory containing:
```text
backup-<backup_id>/
├── manifest.json
├── manifest.json.sha256
├── stores/
│   ├── core.sqlite3
│   └── context.sqlite3 (if paired)
└── evidence/
    ├── core-fingerprints.json
    ├── context-fingerprints.json
    └── paired_cut_evidence.json
```

#### Manifest Schema (`manifest.json`):
```json
{
  "manifest_version": 1,
  "backup_id": "uuidv4",
  "created_at_us": 1729065600000000,
  "repository_uuidv4": "permanent-repo-uuidv4",
  "catalog_instance_uuidv4": "source-catalog-instance-uuidv4",
  "scope": "git_only | paired",
  "stores": {
    "core": {
      "path": "stores/core.sqlite3",
      "bytes": 1048576,
      "sha256": "64-hex-digest",
      "schema_fingerprint": "core-ddl-sha256"
    },
    "context": {
      "path": "stores/context.sqlite3",
      "bytes": 524288,
      "sha256": "64-hex-digest",
      "schema_fingerprint": "context-ddl-sha256"
    }
  },
  "retained_byte_summary": {
    "commit_count": 42,
    "tree_count": 84,
    "tag_count": 5,
    "notes_body_count": 12,
    "total_retained_bytes": 142050
  },
  "overall_sha256": "64-hex-digest-of-content-hash"
}
```

### 2.4 Catalog/Repository Instance Identity and Scope Binding

- `repository_uuidv4` is permanent across all backups, clones, restorations, and active instances of the repository.
- `catalog_instance_uuidv4` identifies the specific physical catalog installation that produced the backup.
- Identities are authoritatively extracted from `store_identity` (`store_role`, `repository_uuidv4`, `catalog_instance_uuidv4`). If `store_identity` is missing or corrupt, backup and restore fail closed; synthetic random IDs are never fabricated.
- Restoration verifies that `repository_uuidv4` in the backup matches the target destination's configuration. Cross-repository restoration into a different `repository_uuidv4` is strictly rejected.

### 2.5 Per-File and Whole-Artifact SHA-256 Verification

- Every file listed in `manifest.json` has its exact byte length and SHA-256 recorded.
- `manifest.json` itself is digested into `manifest.json.sha256`.
- Restore preflight computes SHA-256 on all raw payload files before opening any SQLite connection. Any byte discrepancy, truncation, or unexpected file aborts restore immediately.
- Store file paths are validated against path traversal, symlink escapes, absolute paths, and parent directory references (`..`), failing closed if any path escapes the backup root.

### 2.6 Actual Retained-Byte and Semantic-Domain Validation

A matching file hash certifies transport integrity, not semantic validity. Normal backup completion and restore activation require deep validation against authoritative target P1 schema tables:
1. **SQLite PRAGMA integrity_check:** Run on restored database copies.
2. **SQLite PRAGMA foreign_key_check:** Verify that all foreign key constraints are strictly satisfied.
3. **Schema and DDL Fingerprint Check:** Check exact table definitions against authoritative compiled DDL fingerprints (`p1_schema.fingerprint(store)`).
4. **Retained Git Metadata Verification (`retained_metadata`):**
   - Query: `SELECT object_format, full_oid, physical_copy_uuidv4, native_type, body, size, digest_sha256 FROM retained_metadata`.
   - Recompute SHA-256 of `body`: assert matches `digest_sha256`.
   - Validate `size == len(body)`.
   - Recompute native Git object OID using object header `f"{native_type} {len(body)}\0".encode() + body` with `object_format` algorithm: assert matches `full_oid`.
   - Verify `native_type IN ('commit', 'tree', 'tag')`.
5. **Retained Git Notes Verification (`retained_notes`):**
   - Query: `SELECT object_format, full_oid, physical_copy_uuidv4, body, size, digest_sha256, capture_origin_uuidv4, capture_uuidv4, root, target, path, proof_bundle FROM retained_notes`.
   - Recompute SHA-256 of note `body`: assert matches `digest_sha256`.
   - Validate `size == len(body)`.
   - Recompute native Git blob OID: assert matches `full_oid`.
   - Verify corresponding `note_roles` row exists, satisfying ADR 0022 structural proof requirements and ADR 0014 non-ordinary-file exclusion rules.
6. **Context Text Body Verification (`text_bodies`):**
   - Query: `SELECT sha256, text_value FROM text_bodies`.
   - Recompute SHA-256 of `text_value.encode("utf-8")`: assert matches `sha256`.
   - Verify non-empty valid UTF-8 string.

If any retained byte fails hash or domain verification, backup/restore is immediately rejected.

### 2.7 SQLite Database, Journal, WAL, and SHM Handling

- Active databases operate in WAL mode (`PRAGMA journal_mode=WAL;`).
- When creating backups, safe snapshots are copied via the SQLite Backup API (`sqlite3_backup_*`), capturing the complete committed state without dangling `-wal` / `-shm` dependencies in the backup.
- Suspect catalog preservation captures the exact triad: `database.sqlite3`, `database.sqlite3-wal`, and `database.sqlite3-shm` (or rollback journal if rollback mode).
- Diagnostic reads against suspect stores must never use shared memory or WAL checkpointing that mutates the suspect files. Diagnostic reads are performed on isolated read-only file copies or with read-only connection URIs (`file:...mode=ro`).

### 2.8 Filesystem Durability, Temporary Paths, Fsync, and Atomic Publication

1. **Safe Staging:** All backup creation and fresh restore operations write to unique temporary directories on the same filesystem (e.g. `<destination>.tmp.<uuidv4>`).
2. **Path Traversal Guards:** All paths in manifests and candidate archives are strictly canonicalized and validated to be relative children of the staging root. Symlinks, hardlinks, absolute paths, and `..` segments are rejected.
3. **Fsync Ordering:**
   - Write store and artifact files.
   - Flush and `os.fsync()` each file descriptor.
   - Write `manifest.json` and `os.fsync()`.
   - Flush and `os.fsync()` the directory file descriptor.
4. **Atomic Rename with No-Overwrite:** Atomically publish the temporary directory to the final destination path via `os.replace()` while verifying destination existence under directory locking, ensuring that concurrent destination creation is never overwritten.

### 2.9 External Persistent Catalog-Stop Marker and Operation Fencing

When authoritative corruption is detected:
1. **Marker Publication:** Create the authoritative persistent marker file `p1-recovery-stop.json` (as standardized across P2–P6 in `p1_coordination.py`) via `persist_catalog_stop(catalog_dir, reason)`. Maintain `recovery.stop` compatibly alongside it.
   - The marker contains JSON: timestamp (`_us`), reason, scope (`"catalog"`), and suspect catalog instance ID.
   - The marker is written directly to the filesystem and `fsync`'d under `p1-stop-fence.lock`. It does NOT depend on a successful `INSERT` into the damaged database.
2. **Operation Fencing:** Every public entry point across P2–P6 and P7 (query, search, acquisition, exchange, backup, worker) checks for `p1-recovery-stop.json` (or `recovery.stop`) before execution. If present, it raises `CatalogStoppedError` / `CoreFailure("RECOVERY_STOP")` immediately.
3. **Survives Restart:** Process restart, cache clearing, or deletion of `operational.sqlite3` / `search.sqlite3` does not clear `p1-recovery-stop.json`. Only verified activation of a fresh restore updates the active catalog locator.

### 2.10 Read-Only Suspect Evidence Preservation

- Upon entering recovery mode, suspect databases and WAL files are preserved strictly read-only.
- Preserved suspect databases are never cleaned, vacuumed, repaired in place, or deleted.

### 2.11 Bounded Untrusted Typed Salvage Serialization

- Explicit diagnostic salvage scans the suspect database table by table in streaming mode without buffering all rows in memory (`cursor.fetchall()` prohibited).
- Untrusted candidate records are serialized into typed JSONL records (`salvage_candidates.jsonl`):
  - `candidate_id`: Composite domain identity (e.g. `f"{object_format}:{full_oid}:{physical_copy_uuidv4}"` or `sha256`)
  - `candidate_type`: `"retained_metadata" | "retained_note" | "context_text" | "context_field" | "git_metadata"`
  - `capture_origin_uuidv4`: UUIDv4 (if present)
  - `capture_uuidv4`: UUIDv4 (if present)
  - `provenance`: Preserved original provenance
  - `payload`: Typed data including exact payload bytes (encoded as base64 so exact representations are not lost)
  - `extraction_status`: `"clean" | "partial" | "corrupt_boundary"`
- Resource bounds (`max_records`, `max_bytes`) enforce bounded execution. If a table or page is unreadable, it is recorded in `salvage_report.json` as `unreadable_scope`, without aborting salvage of independent readable units.

### 2.12 Receiver-Checked Merge into a Fresh Destination

- The fresh destination is initialized from the validated restore baseline.
- Salvage candidates are ingested exclusively via existing typed receiver interfaces:
  - Git metadata and commits/trees/tags via `Core.admit_metadata`.
  - Evidenced Notes via `Core.admit_note`.
  - Context text bodies via `ContextStore.text`.
  - Context fields via `ContextStore.admit_field`.
- Every candidate is re-checked against ADR 0022 notes-role proof, ADR 0028 classified times, ADR 0018 UUIDv4 capture rules, and ADR 0020/0021 conflict preservation.
- Candidates that fail validation or domain constraints are rejected and logged in `merge_audit.json`; valid independent units are committed into destination tables, demonstrably persisting newly admitted domain rows. Rejected candidates cause no mutation.

### 2.13 Validation and No-Overwrite Activation

- Before activation, the merged destination undergoes:
  1. Full PRAGMA integrity check on Core and Context.
  2. Full PRAGMA foreign_key_check on Core and Context.
  3. Full hash verification of all retained bodies and documents.
  4. Authoritative DDL fingerprint match.
- **Activation:** Atomically updates the active catalog pointer (symlink or locator file `active_catalog_instance.json`) with fsync durability.
- If target path already exists as an active regular directory, no-overwrite protection requires keeping the suspect directory intact and publishing via the locator file or failing closed if clobbering would occur.

### 2.14 Operational and Search Reconstruction After Restoration

- Operational store (`operational.sqlite3`) and Search store (`search.sqlite3`) are never restored from backup or salvage.
- They are initialized clean using compiled DDL and populated by rebuilding projections from the newly activated authoritative Core and Context stores.

### 2.15 Precise Resource, Interruption, and Fault Reporting

- All recovery operations return structured receipts (`BackupReceipt`, `RestoreReceipt`, `SalvageReceipt`, `ActivationReceipt`, `MergeReceipt`).
- In case of process interruption or crash at any step, temporary staging directories are distinguishable by `.tmp.` suffixes.

### 2.16 Adversarial Acceptance and Fault Injection

Dedicated integration test suite `tests/integration/p7/` exercises all 18 required adversarial cases:
1. A real retained commit survives backup/restore exactly.
2. A retained byte modified without updating its recorded digest is detected.
3. A forged backup with recalculated manifest SHA-256 but invalid domain bytes is rejected.
4. An actual verified Notes body survives recovery.
5. A Notes blob lacking role evidence is not admitted.
6. Actual Context text survives with verified SHA-256.
7. Valid salvage candidates cause observable new rows in the restored catalog.
8. Rejected candidates cause no authoritative mutation.
9. Original Capture and provenance survive replay when supported.
10. Read-only salvage preserves the original SQLite DB/WAL/journal evidence.
11. A writer cannot cross the declared paired backup cut.
12. Concurrent destination creation cannot be overwritten.
13. Symlink and path traversal inputs cannot escape the recovery staging root.
14. An interrupted activation cannot publish a partially validated destination.
15. The catalog stop survives process restart and loss of Operational/Search.
16. Existing P5/P6 readers and writers actually reject the stopped catalog.
17. Both SHA-1 and SHA-256 Git formats are exercised.
18. Wheel and sdist-derived wheel installations can execute meaningful P7 recovery operations.
