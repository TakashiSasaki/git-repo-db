# P7 Production Consistent Backup, Corruption Stop, Read-Only Salvage, and Fresh Restore Technical Design

Current target: [ADR 0038](../adr/0038-scoped-recovery-and-optional-initialization.md) replaces ADR 0026;
[ADR 0037](../adr/0037-operation-scoped-module-independence.md) and the
[operation contract](../architecture/module-independence-contract.md) require Git-only
activation without Operational/Search code or DB initialization. Paired scope is
unchanged. The implementation checkpoints described below still initialize both
stores; this acceptance does not implement the new Git-only guarantee.

Status: Engineering specification, reconciled during crash hardening; execution results remain separately revision-bound, under the historical ADR 0026 baseline and supporting decisions ADR 0001, ADR 0003, ADR 0014–0025, ADR 0027, and ADR 0028.
Owner architectural blockers: Zero.
Scope: Implements production backup, corruption stop, read-only forensic preservation, untrusted typed salvage, verified fresh restore, and safe activation for `git-repo-db`.

---

## 1. Architectural Foundation and ADR 0026 Mandate

Under the accepted successor ADR 0038, the retained recovery architecture establishes a strict operational lifecycle:
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
- `paired`: Captures a mutually consistent snapshot of both authoritative stores: Git Core (`core.sqlite3`) and Context (`context.sqlite3`). The shared protected writer cut and matching repository/instance identities establish the paired artifact; no separate pairing-evidence file is implemented.

Reconstructible stores (`operational.sqlite3`, `search.sqlite3`) are never included in normal backups. The documented implementation initializes empty compiled derivative stores on activation; Git-only target behavior must instead follow ADR 0038. A separate P6 rebuild is required to populate Search projections; initialization alone is not a rebuild.

### 2.2 Consistent Core+Context Snapshot Protocol

To achieve a consistent snapshot across independent SQLite databases, the shared writer gate spans the complete protected copy cut:
1. **Writer Fencing:** Acquire the common catalog coordinator writer lock (`catalog_gate` via `p1-writer.lock`).
2. **Protected Snapshot Cut:** Hold the writer gate while the SQLite Backup API copies both authoritative stores, including genuine committed WAL state. Cooperating writers cannot change either store during this cut.
3. **Paired Integrity Anchor:** Require matching permanent repository and catalog-instance identities. Preserve legitimate unresolved attributed Context/Core references; they are not proofs of available Core data and do not require fabricated referents. No mutable Core transaction-sequence authority is introduced.
4. **SQLite Backup API:** Write standalone snapshot files through `sqlite3_backup_*`, then use DELETE journal mode on those copies to remove sidecar dependencies. Bound BUSY/LOCKED backup retries; a transient lock is not proof of authoritative corruption.
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
1. **SQLite Structural and Stored-Domain Checks:** Run PRAGMA integrity_check on restored copies, then explicitly evaluate all trusted packaged CHECK predicates. Read-only SQLite PRAGMA checks alone can miss UDF/CHECK violations. Verify every authoritative TEXT value as UTF-8 before UDF evaluation; binary Notes bodies remain BLOBs.
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
   - Verify exact valid UTF-8, including the legitimate empty string.
7. **Stored Admission Invariants:** Recheck enduring packaged relational guards, including intrinsic claims/groups versus retained representations, Notes inventory/format and Coverage ownership. PRAGMA checks do not rerun INSERT triggers. Exclude insertion-time replay/current-terminal predicates: later evidence does not invalidate legitimate historical proofs.

If any retained byte fails hash or domain verification, backup/restore is immediately rejected.

### 2.7 SQLite Database, Journal, WAL, and SHM Handling

- Active databases operate in WAL mode (`PRAGMA journal_mode=WAL;`).
- When creating backups, safe snapshots are copied via the SQLite Backup API (`sqlite3_backup_*`), capturing the complete committed state without dangling `-wal` / `-shm` dependencies in the backup.
- Suspect catalog preservation captures the exact triad: `database.sqlite3`, `database.sqlite3-wal`, and `database.sqlite3-shm` (or rollback journal if rollback mode).
- Diagnostic reads against suspect stores must never use shared memory or WAL checkpointing that mutates the suspect files. Diagnostic reads and source revalidation run only on isolated working copies of the protected evidence set. A `mode=ro` SQLite connection alone does not guarantee unchanged source WAL/SHM files.

### 2.8 Filesystem Durability, Temporary Paths, Fsync, and Atomic Publication

1. **Safe Staging:** All backup creation and fresh restore operations write to unique temporary directories on the same filesystem (e.g. `<destination>.tmp.<uuidv4>`).
2. **Path Traversal Guards:** All paths in manifests and candidate archives are strictly canonicalized and validated to be relative children of the staging root. Symlinks, hardlinks, absolute paths, and `..` segments are rejected.
3. **Fsync Ordering:**
   - Write store and artifact files.
   - Flush and `os.fsync()` each file descriptor.
   - Write `manifest.json` and `os.fsync()`.
   - Flush and `os.fsync()` the directory file descriptor.
4. **Atomic Rename with No-Overwrite (`renameat2`):** Atomically publish the temporary directory to the final destination path via `renameat2(parent_fd, src, parent_fd, dst, RENAME_NOREPLACE)` on Linux using a pinned common-parent descriptor. There is no unsupported-platform fallback; unavailable primitives fail closed. This eliminates check-then-replace race conditions and guarantees that concurrent destination publication attempts fail closed without overwriting existing data.

### 2.9 External Persistent Catalog-Stop Marker and Operation Fencing

When authoritative corruption is detected:
1. **Marker Publication:** Create the authoritative persistent marker file `p1-recovery-stop.json` (as standardized across P2–P6 in `p1_coordination.py`) via `persist_catalog_stop(catalog_dir, reason)`. Maintain `recovery.stop` compatibly alongside it.
   - The P1 marker contains reason and scope (`"catalog"`). The supplemental `recovery.stop` records the positive `_us` stop time and available diagnostic details; no missing catalog identity is fabricated.
   - The marker is written directly to the filesystem and `fsync`'d under `p1-stop-fence.lock`. It does NOT depend on a successful `INSERT` into the damaged database.
2. **Operation Fencing:** Every public entry point across P2–P6 and P7 (query, search, acquisition, exchange, backup, worker) checks for `p1-recovery-stop.json` (or `recovery.stop`) before execution. If present, P7 raises `CatalogStoppedError`, P5/P6 application gates raise `CoreFailure("RECOVERY_STOP")`, and lower coordinator fences raise `CoordinationError("RECOVERY_REQUIRED")`.
3. **Classification:** Reconfirm staged defects against a bounded protected forensic source copy. Confirmed data/schema/pair damage persists Stop before releasing the writer cut. Staging-only damage rejects the backup while leaving healthy authority unstopped. Environmental/resource/unsupported failures return indeterminate integrity, never a false healthy or confirmed-corrupt verdict.
4. **Survives Restart:** Process restart, cache clearing, or deletion of `operational.sqlite3` / `search.sqlite3` does not clear `p1-recovery-stop.json`. Only verified activation of a fresh restore updates the active catalog locator.

### 2.10 Read-Only Suspect Evidence Preservation

- Upon entering recovery mode, suspect databases and WAL files are preserved strictly read-only.
- Preserved suspect databases are never cleaned, vacuumed, repaired in place, or deleted.
- Even after Stop, extraction first drains in-flight writers through the exclusive writer gate, then takes the shared completion fence. Diagnostic extraction copies the suspect database, WAL, and SHM files into an isolated temporary workspace before opening them, guaranteeing that SQLite shared-memory initialization or WAL rollback cannot alter the suspect evidence files bit-for-bit.

### 2.11 Bounded Untrusted Typed Salvage Serialization

- Explicit diagnostic salvage scans the suspect database table by table in streaming mode without buffering all rows in memory (`cursor.fetchall()` prohibited).
- Execution is strictly bounded by a configurable `RecoveryBudget` with finite, non-infinite defaults:
  - `max_input_records`: default 100,000 rows.
  - `max_input_bytes`: default 512 MiB.
  - `max_payload_bytes`: default 16 MiB per candidate.
  - `max_json_depth`: default 16 levels.
- Untrusted candidate records are serialized into typed JSONL records (`salvage_candidates.jsonl`):
  - `candidate_id`: Composite domain identity (e.g. `f"{object_format}:{full_oid}:{physical_copy_uuidv4}"` or `sha256`)
  - `candidate_type`: `"retained_body" | "notes_mapping" | "context_document" | "context_resource" | "git_metadata"`; supported legacy semantic aliases are not required compatibility.
  - `capture_origin_uuidv4`: UUIDv4 (if present)
  - `capture_uuidv4`: UUIDv4 (if present)
  - `extraction_provenance`: Forensic source coordinates (`{"store": ..., "table": ...}`)
  - `provenance`: Preserved original domain provenance
  - `payload`: Typed data including exact payload bytes (encoded as base64 so exact representations are not lost)
  - `extraction_status`: `"clean" | "partial" | "corrupt_boundary"`
- Resource bounds enforce finite execution. If a table or page is unreadable, it is recorded in the returned `SalvageReceipt.unreadable_scope`, without aborting salvage of independent readable units.

### 2.12 Receiver-Checked Merge into a Fresh Destination

- The fresh destination is initialized from the validated restore baseline.
- Salvage candidates are ingested exclusively via existing typed receiver interfaces:
  - Git metadata and commits/trees/tags via `Core.admit_metadata`.
  - Evidenced Notes via `Core.admit_note`.
  - Context text bodies via `ContextStore.text`.
  - Other Context resources/fields and unsupported metadata remain qualified non-authoritative observations. This P7 implementation does not claim complete typed reconstruction of every Context table.
- Every candidate produces exactly one accurately reported disposition:
  - `admitted`: Genuinely new authoritative domain unit written to destination.
  - `replayed`: Exact replay of an already admitted domain unit.
  - `observation`: Accepted as a qualified non-authoritative recovery observation without domain mutation.
  - `rejected`: Refused due to validation or domain constraint failure.
  - `deferred`: Deferred due to unresolved prerequisite dependencies.
  - `unprocessed`: Not processed due to budget or resource exhaustion.
- Fallthrough non-mutating candidates are counted as `observation_units` and never falsely reported as `admitted_units`.
- Every candidate is re-checked against ADR 0022 notes-role proof, ADR 0028 classified times, ADR 0018 UUIDv4 capture rules, and ADR 0020/0021 conflict preservation.
- Candidates that fail validation or domain constraints are rejected and included in the structured merge receipt; valid independent units are committed into destination tables, demonstrably persisting newly admitted domain rows. Rejected candidates cause no mutation.

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
- The documented implementation initializes both stores cleanly from compiled DDL (not the new Git-only target). Search remains `initialized_empty`; actual projection population requires the separate P6 rebuild. This receipt does not assert that full Search reconstruction occurred.

### 2.15 Precise Resource, Interruption, and Fault Reporting

- All recovery operations return structured receipts (`BackupReceipt`, `RestoreReceipt`, `SalvageReceipt`, `ActivationReceipt`, `MergeReceipt`).
- In case of process interruption or crash at any step, temporary staging directories are distinguishable by `.tmp.` suffixes.

### 2.16 Adversarial Acceptance and Fault Injection

The following cases describe required behavior, not a self-certifying test count. Exact committed execution evidence and independent reports identify which nodes were actually run:
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


### 2.17 Durable cumulative recovery requests

A request is scoped to one fresh destination and a canonical 1–64 character ASCII
ID matching `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`. Omission means the stable `default`
request. Retry retains that ID; explicitly independent work uses a distinct ID.
The complete finite RecoveryBudget contract is immutable for that request,
including input records/bytes, payload/depth and work ceilings. A retry cannot
increase ceilings or reset accounting through Operational/Search loss.

Permanent request/registry locks serialize cooperating processes. Files beside
the fresh destination authority (outside Operational/Search) anchor registry,
contract, reservation checkpoint and expenditure report. Reserve before input,
decoding/verification and admission work: fsync a temporary checkpoint, atomically
replace it, fsync its directory, then publish the report the same way. Lost
acknowledgement retains the greater reservation. Normal measured completion can
settle a live permit by writing the smaller report first, then the checkpoint;
a crash between those writes restores the greater expenditure. Restart cannot
refund a lost permit. Missing, unreadable, truncated, type-invalid, duplicate-key
or conflicting records fail closed. Deliberate removal/rewrite of every external
anchor is outside this cooperating-process contract.

### 2.18 Bounds, receipts and tested platform contract

Stream and cumulatively bound actual forensic DB/WAL/SHM/journal bytes, detect
file growth/substitution, and refuse nonregular input before blocking reads.
Limit SQLite cells/rows/VM work before Python materialization; bound binary JSONL
chunks before reading, JSON lexical depth/elements before parsing, and base64/hex
proof expansion before decoding. Reserve repeated native parsing/hashing work,
including rejected candidates, before execution. Budget limits are resource
outcomes, not evidence of corruption. A partial candidate makes extraction
partial; unreadable/missing scope never implies complete enumeration.

At a limit do not scan an arbitrary suffix merely to count omissions. Receipts
separate `input_complete`, `unprocessed_count_exact` and known unprocessed lower
bounds. Exact replay requires all immutable identity/copy/Capture/role/native
attributes through the same typed admission checks. Notes Capture/role/body
admission is one atomic unit; forensic provenance never replaces original
attribution. Valid independent partial units may remain, with omissions explicit.
Final activation validates the authority, not a claim of complete salvage.

The supported implementation uses Linux local filesystems, `/proc/self/fd`,
POSIX flock, SQLite WAL locking, fsync and renameat2, with cooperating writers.
Pin manifest/store/catalog/parent descriptors, verify copied bytes, and check
named-directory identities around publication. Preserve/restore the prior
locator when a tested activation substitution is detected. Unsupported primitives
and uncertain sync failures fail closed; a rename followed by failed directory
fsync has an explicitly uncertain durability outcome. Tests include genuine
separate processes and SIGKILL. They do not establish actual host power-loss,
network-filesystem or privileged/hostile namespace-mutation guarantees. The public
Schema 21 initializer/runtime is not switched by P7.
