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
4. **Untrusted Typed Salvage:** Salvaged records extracted from a stopped suspect catalog are untrusted candidate data. Salvage serialization preserves candidate identity, original Capture UUIDv4 pair, source attribution, and honest unreadable/incomplete bounds. No salvaged row or sender flag grants intrinsic receiver authority.
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
1. **Writer Fencing:** Acquire the common catalog coordinator writer lock (`locks/writer.lock`).
2. **Transactional Snapshot Cut:** Open read-only snapshot transactions on both `core.sqlite3` and `context.sqlite3` using SQLite WAL read transactions.
3. **Paired Integrity Anchor:** Record the maximum commit sequence / transaction state and compute cross-store referential bounds: verify that any Context reference to a Git Core commit or object format references an entity present within the Core snapshot.
4. **Online VACUUM INTO / Backup API:** Stream the snapshot pages into temporary backup files (`core.sqlite3.bak`, `context.sqlite3.bak`) via SQLite online backup API or `VACUUM INTO`, ensuring page-level consistency without dirty partial reads.
5. **Release Writer Lock:** Release `locks/writer.lock`. All subsequent validation, hashing, and archive packaging proceed out of band.

### 2.3 Backup Artifact Structure and Manifest Schema

The durable backup artifact is a single directory or tar archive containing:
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
- Restoration verifies that `repository_uuidv4` in the backup matches the target destination's configuration. Cross-repository restoration into a different `repository_uuidv4` is strictly rejected.

### 2.5 Per-File and Whole-Artifact SHA-256 Verification

- Every file listed in `manifest.json` has its exact byte length and SHA-256 recorded.
- `manifest.json` itself is digested into `manifest.json.sha256`.
- Restore preflight computes SHA-256 on all raw payload files before opening any SQLite connection. Any byte discrepancy, truncation, or unexpected file aborts restore immediately.

### 2.6 Actual Retained-Byte and Semantic-Domain Validation

A matching file hash certifies transport integrity, not semantic validity. Normal backup completion and restore activation require deep validation:
1. **SQLite PRAGMA integrity_check:** Run on restored database copies.
2. **Schema and DDL Fingerprint Check:** Check exact table definitions against authoritative compiled DDL fingerprints.
3. **Retained Body Digest Verification:** Iterate all retained native Git objects (commits, trees, tags, notes bodies) in `core_retained_bytes` and Context text in `context_documents`: re-hash the stored payload bytes against their claimed OID/SHA-256. If any retained byte fails hash verification, the backup is rejected.
4. **Domain Invariants:** Validate that notes bodies satisfy ADR 0022 structural proof requirements and ADR 0014 non-ordinary-file exclusion rules.

### 2.7 SQLite Database, Journal, WAL, and SHM Handling

- Active databases operate in WAL mode (`PRAGMA journal_mode=WAL;`).
- When creating backups, SQLite WAL checkpoint is flushed or safe snapshots are copied via the SQLite Backup API (`sqlite3_backup_*`), preventing dangling `-wal` / `-shm` state.
- Suspect catalog preservation captures the exact triad: `database.sqlite3`, `database.sqlite3-wal`, and `database.sqlite3-shm` (or rollback journal if rollback mode).
- Diagnostic reads against suspect stores must never use shared memory or WAL checkpointing that mutates the suspect files. Diagnostic reads are performed on isolated read-only file copies or with OS-level write locks.

### 2.8 Filesystem Durability, Temporary Paths, Fsync, and Atomic Publication

1. **Safe Staging:** All backup creation and fresh restore operations write to unique temporary directories on the same filesystem (e.g. `<destination>.tmp.<uuidv4>`).
2. **Path Traversal Guards:** All paths in manifests and candidate archives are strictly canonicalized and validated to be relative children of the staging root. Symlinks, hardlinks, absolute paths, and `..` segments are rejected.
3. **Fsync Ordering:**
   - Write store and artifact files.
   - Flush and `os.fsync()` each file descriptor.
   - Write `manifest.json` and `os.fsync()`.
   - Flush and `os.fsync()` the directory file descriptor.
4. **Atomic Rename:** Atomically rename the temporary directory to the final destination path via `os.replace()` or `renameat2` with no-overwrite protection (`RENAME_NOREPLACE`).

### 2.9 External Persistent Catalog-Stop Marker and Operation Fencing

When authoritative corruption is detected:
1. **Marker Publication:** Create an external persistent marker file in the catalog directory: `recovery.stop`.
   - The marker contains JSON: timestamp (`_us`), detection site, reason, error type, and suspect catalog instance ID.
   - The marker is written directly to the filesystem and `fsync`'d. It does NOT depend on a successful `INSERT` into the damaged database.
2. **Operation Fencing:** Every public entry point (query, search, acquisition, exchange, backup, worker) checks for `recovery.stop` before execution. If present, it raises `CatalogRecoveryModeError` immediately.
3. **Survives Restart:** Process restart, cache clearing, or deletion of `operational.sqlite3` / `search.sqlite3` does not clear `recovery.stop`. Only verified activation of a fresh restore updates the active catalog locator.

### 2.10 Read-Only Suspect Evidence Preservation

- Upon entering recovery mode, the catalog directory permissions may be set to read-only (`0555` / `0444`), or a forensic copy snapshot is created at `<catalog>.suspect.<timestamp_us>`.
- Preserved suspect databases are never cleaned, vacuumed, repaired in place, or deleted.

### 2.11 Bounded Untrusted Typed Salvage Serialization

- Explicit diagnostic salvage scans the suspect database page by page or row by row.
- Untrusted candidate records are serialized into typed JSONL records (`salvage_candidates.jsonl`):
  - `candidate_id`: UUIDv4
  - `candidate_type`: `"git_metadata" | "notes_mapping" | "retained_note_body" | "context_resource" | "context_document"`
  - `capture_origin_uuidv4`: UUIDv4 (if present)
  - `capture_uuidv4`: UUIDv4 (if present)
  - `provenance`: Attributed unauthenticated report
  - `payload`: Raw or structured typed data
  - `extraction_status`: `"clean" | "partial" | "corrupt_boundary"`
- Resource bounds (max rows, max bytes, timeout) enforce bounded execution. If a table or page is unreadable, it is recorded in `salvage_report.json` as `unreadable_scope`, without aborting salvage of independent readable units.

### 2.12 Receiver-Checked Merge into a Fresh Destination

- The fresh destination is initialized from the validated restore baseline.
- Salvage candidates are ingested exclusively via existing typed receiver interfaces:
  - Git metadata and notes via P2/P4 `GitCore` admission.
  - Context documents and claims via P3 `Context` admission.
- Every candidate is re-checked against ADR 0022 notes-role proof, ADR 0028 classified times, ADR 0018 UUIDv4 capture rules, and ADR 0020/0021 conflict preservation.
- Invalid, corrupted, or unproven candidates are rejected and logged in `merge_audit.json`; valid independent units are committed in separate atomic transactions.

### 2.13 Validation and No-Overwrite Activation

- Before activation, the merged destination undergoes:
  1. Full PRAGMA integrity check on Core and Context.
  2. Full hash verification of all retained bodies and documents.
  3. Paired cross-store referential integrity audit.
  4. Authoritative DDL fingerprint match.
- **Activation:** The active catalog pointer (e.g. catalog directory link or config locator) is updated to point to the freshly verified directory.
- The original suspect directory remains untouched at its preserved forensic location.

### 2.14 Operational and Search Reconstruction After Restoration

- Operational store (`operational.sqlite3`) and Search store (`search.sqlite3`) are never restored from backup or salvage.
- They are initialized clean using compiled DDL and populated by rebuilding projections from the newly activated authoritative Core and Context stores.

### 2.15 Precise Resource, Interruption, and Fault Reporting

- All recovery operations return structured receipts (`BackupReceipt`, `RestoreReceipt`, `SalvageReceipt`, `ActivationReceipt`).
- In case of process interruption or crash at any step, temporary staging directories are distinguishable by `.tmp.` suffixes.

### 2.16 Adversarial Acceptance and Fault Injection

Dedicated integration test suite `tests/integration/p7/` exercises:
1. Core-only consistent backup and restore.
2. Paired Core+Context backup with concurrent write contenders.
3. Persistent `recovery.stop` creation upon bit-flip byte corruption.
4. Fencing of queries, exchange, and backup when `recovery.stop` is present.
5. Inability of restart or operational loss to clear `recovery.stop`.
6. Read-only preservation of suspect database and WAL files.
7. Salvage of valid units mixed with corrupt pages.
8. Rejection of unproven notes bodies during salvage merge.
9. Fresh restore rejecting tampered manifest or mismatched repo UUID.
10. Atomic activation with no-overwrite protection.
