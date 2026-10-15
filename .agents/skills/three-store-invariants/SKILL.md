---
name: three-store-invariants
description: Diagnose the implemented Schema 21 Three-Store baseline under ADR 0002, including cross-store isolation, cache GC, split-write resumption, Core-only maintenance and search fencing, and verify target paired-snapshot coordination experiments. For the newer Git Core/Context target, first apply the current ADR index and scoped replacements; baseline quarantine-count and full-backup recipes are not target requirements.
---

# Three-Store Boundary Architectural Invariants (ADR 0002)

**Applicability:** The concrete tables, methods and recipes below describe the **implemented Core Schema 21 / Operational 1 / Search 1 baseline**. For target work, read the [ADR index](../../../docs/adr/README.md) and [transition plan](../../../docs/architecture/git-core-context-transition-plan.md). [ADR 0003](../../../docs/adr/0003-append-only-git-core-and-context-store.md) separates independently durable Context from INSERT-only Git Core; [ADR 0014](../../../docs/adr/0014-history-and-notes-catalog-without-file-archive.md) excludes ordinary file-body archival. [ADR 0026](../../../docs/adr/0026-stop-salvage-restore-merge-after-corruption.md) replaces quarantine/count/release and same-DB continuation with immediate catalog recovery. [ADR 0027](../../../docs/adr/0027-unauthenticated-external-capture-origin-reports.md) fixes unauthenticated external-origin reports without application PKI/signatures. Preserve unaffected safety principles; do not copy superseded baseline mechanisms into the target or infer new execution permission from this skill.

The **implemented baseline** physically separates three SQLite stores; the following inventory does not assign target authority:
- **Core Store (`catalog.sqlite3`)**: Authoritative domain facts, entities, immutable observations, coverage claims, code listings, Git DAG and intrinsic structures, and Exchange staging.
- **Operational Store (`operational.sqlite3`)**: Transient execution state, jobs, job attempts, capacity reservations, and cache leases.
- **Search Store (`search.sqlite3`)**: Disposable FTS5 virtual tables, rebuildable search document projections, and index generations.

Use the baseline recipes only when diagnosing the current production implementation.
For target implementation, apply each section's target boundary and the current
accepted ADRs. Provider/Source/PR/Issue/review/text evidence moves to independently
durable Context; Git Core keeps permitted Git facts and representations. No
baseline table, surrogate ID, mutable revision or quarantine mechanism is
implicitly grandfathered by a recipe below.

---

## 1. Baseline cache protection under Operational loss

### Symptom
If the Operational DB is lost or recreated, Operational mappings (`active_cache_entries`, `cache_locators`) disappear. A naive cache GC gate checking only Operational tables would find no active leases or locators and delete physical Git packfiles (`cache/<repo_uuid>/<gen>.git`), even though unfulfilled Core preservation obligations still depend on them.

### Target boundary

Preserve the rule that Operational loss cannot invalidate admitted durable data.
Do not implement the baseline's full-file-archive preservation obligations or
mutable Core acquisition flags as target requirements. ADR 0014 excludes ordinary
file bodies, including hidden cache/staging archives. Required allowed bytes must
be durable independently of a disposable cache; target work/progress belongs in
Operational. The exact legacy cache checks below diagnose Schema 21 only and do
not authorize deleting real cache data.

### Baseline rule and recipe
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

## 2. Baseline maintenance isolation and target backup scope (PF-P08, PF-P14, PF-P17)

### Symptom
`repo-catalog check` or backup/restore fails or reports Core corruption when `search.sqlite3` is absent, stale, or corrupt. Or, a read-only check attempts an FTS5 write mutation (e.g., `INSERT INTO fts(fts) VALUES('integrity-check')`) which raises `sqlite3.OperationalError: attempt to write a readonly database`.

### Target boundary

Core and Context are both authoritative. Search/Operational failure must not
invalidate either sound durable store; Context must not be treated as another
disposable secondary. Git-only checks/backups may omit Context with honest scope;
full Context-inclusive validation/backup requires a consistent Core/Context pair.
The baseline overall-check verdict below must not hide target Context corruption,
which triggers ADR 0026's catalog recovery stop. See section 6 for executable
paired-store fence and pre-certification validation checks.

### Baseline rule and recipe
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
2. **Historical implemented restoration & CAS-41 recipe (not target requirements):**
   - Backup backs up Core DB (`catalog.sqlite3`) and records `quarantined_payload_count` in the manifest.
   - Restore validates `quarantined_payload_count` against the verified copy before diagnosis, rejects mismatches or malformed counts, restores Core DB only, and initializes fresh instance identities. Search DB is created only upon explicit `index rebuild`.

   **Current target:** Retire the active-quarantine counter and pre-diagnosis comparison under ADR 0026. Preserve actual database, manifest, identity, retained-byte/domain and pairing validation. A Core-only backup is Git-only; full Context scope requires a consistent Core+Context pair. Authoritative corruption stops ordinary catalog use, preserves the source read-only and requires fresh verified restore plus validated salvage merge. No zero counter, sibling copy or diagnosis INSERT clears that stop.

---

## 3. Baseline split-write resumption (PF-P04, PF-P07)

### Symptom
During collection or Git acquisition, a process crashes after committing Operational cursor/complete state but before committing the Core transaction. A subsequent run trusts Operational `state='complete'` and skips remaining pages, or starts from an advanced cursor, producing missing domain evidence.

### Target boundary

Keep disposable progress subordinate to actual durable domain evidence. The
baseline stores Provider collection markers/continuations in Core; target
Context owns Provider evidence and current state. Do not introduce a required
Core→Context FK or a generic success/publication ledger to mimic these recipes.
Core/Context cross-store work additionally needs a supported admission order,
read fences and validation; this section's Core/Operational retry recipe alone
does not establish two-authority crash consistency. A retry preserves actual
Capture/provenance keys, and notes actual-work budgets accumulate across one
explicit request under ADRs 0024–0025.

### Baseline rule and recipe
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

## 4. Baseline search fencing and target ownership (PF-P15, PF-P16)

### Symptom
- Search reads Core revision, checks index fence, and fetches FTS candidates before opening the Core read transaction. A concurrent writer commits matching resources and advances Core revision, causing subsequent Core iteration to use a newer snapshot with an older candidate set and omit valid results (mixed snapshot).
- PR/Issue search reports `backend: "fts"` while actually executing `literal_match()` scans.
- Rebuilding Search DB fails because Operational telemetry insertion failed, even though the FTS index was built successfully.
- Code search candidate filtering skips objects with decoder conflicts or oversize bodies, suppressing domain coverage diagnostics.

### Target boundary

Retain snapshot consistency, truthful backend reporting and telemetry isolation.
Replace the baseline mutable Core `local_revision` counter/fence in target work;
no UPDATE, mutable verified flag, revision-history surrogate or generic
Publication authority is permitted. Core metadata fallback needs neither bodies
nor Context. Provider/text fallback uses durable Context. The baseline code-search
and cache paths are not permission to archive ordinary file bodies, even through
Search. Target index fencing must identify the actual owning snapshots without
changing these accepted authority boundaries.

### Baseline rule and recipe
- Search must establish and pin its Core read transaction snapshot before validating index fence or retrieving FTS candidates. That snapshot is maintained through result production.
- Producer side: `index.rebuild()` pins Core read snapshot during projection, ensuring `core_revision_fence` matches the actual projected data.
- Search queries for PR and Issue truthfully report `backend: "scan"` directly, avoiding unused FTS queries.
- FTS candidates are bounded (max 50,000 keys). Exceeding the bound or requesting explicit non-default decoders falls back cleanly to scan (`candidate_limit_exceeded`, `unsupported_decoder`).
- Candidate filtering must not suppress domain coverage diagnostics (`body_not_saved`, `decoder_conflict`, `oversize`). Diagnostics are evaluated before candidate filtering.
- Rebuild telemetry failure in Operational store is non-fatal: it issues a warning and records the rebuild result as successful.
- Per-kind index freshness: individual index generations contain their own `core_revision_fence`. Partial rebuild (e.g. `rebuild --kind code`) updates only that kind's generation. Aggregate index status is computed from per-kind results (`ready`, `partial`, `stale`, `incomplete`, `absent`, `corrupt`), never assuming global freshness from a single kind's rebuild.
- Separation of Search health from Operational telemetry: Operational DB corruption or query errors must never cause a healthy Search DB to be reported as corrupt or absent. Telemetry status (`available`, `unavailable`, `uninitialized`) and diagnostics are strictly isolated.
- Job bookkeeping fault tolerance: after index generation is successfully built and committed in Search DB, failures during subsequent Job completion bookkeeping (`JobService.update`) or metrics logging must not mask primary success or report rebuild failure. Truthful warnings are attached to the result.
- Truthful duration estimates: distinguish previous measured duration from historical averages (`estimate_basis: "historical_average"`), returning `None` when zero runs exist.

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
3. **Telemetry Fault Isolation in `index.rebuild()` and `MaintenanceService`:**
   Wrap `store.operational.record_rebuild_metric` and `JobService(s).update(job, "complete")` on the success path so secondary errors attach warnings (`rebuild_telemetry_unavailable`, `job_bookkeeping_unavailable`) rather than aborting index creation.
4. **Per-Kind Index Status in `MaintenanceService.index_status()`:**
   Inspect each kind (`code`, `commits`, `pr`, `issue`) against its ready generation fence, report per-kind status, and derive aggregate status (`ready` when all 4 are fresh; `partial` when some are fresh; `stale` when all are stale; `incomplete` when not fully built).

---

## 5. Verification Evidence & Test Reconciliation

### Historical discrepancy note and cumulative verification

The receipt text below is preserved from the implemented-baseline skill at [commit f5c92d0](https://github.com/TakashiSasaki/git-repo-db/commit/f5c92d0509284cb559c882e61c9703542c78257d). Its counts describe that historical report, not tests executed against a later design/integration HEAD. Consult exact-revision execution evidence before using it for acceptance.

Earlier PR documentation stated "118 passed" across five suites listing:
- 12 (`test_catalog3_cache.py`)
- 11 (`test_catalog3_store.py`)
- 3 (`test_search_index.py`)
- 4 (`test_database.py`)
- 87 (`test_target_schema.py`)

The actual arithmetic sum of unique executed nodes was **117** ($12 + 11 + 3 + 4 + 87 = 117$).

With the addition of targeted correctness and lifecycle tests for R1–R5:
- `test_catalog3_store.py`: +7 nodes (5 parameterized multi-page recovery cases + 1 GraphQL thread divergence + 1 CAS-41 Core-only lifecycle) = **18**
- `test_search_index.py`: +3 nodes (1 barrier-controlled snapshot isolation + 1 truthful backend equivalence matrix + 1 telemetry failure & status CLI) = **6** (bringing the intermediate total to 127).

With the subsequent additions for F1–F4:
- `test_search_index.py`: +4 nodes (`test_per_kind_freshness_and_aggregate_status`, `test_search_health_separated_from_operational_telemetry`, `test_rebuild_tolerates_job_bookkeeping_failures`, `test_rebuild_estimate_truthful_and_distinguished`) = **10** nodes.

That historical report records a full targeted integration suite of **131** unique nodes:
$$12 + 18 + 10 + 4 + 87 = 131\text{ passed}.$$

## 6. Verify independently durable paired-store coordination

Use this procedure for an authorized disposable Core/Context coordination
experiment, not as evidence that the production four-store runtime is implemented.
The executable reference is
[`consistency.py`](../../../tests/integration/architecture_spikes/consistency.py)
and its adversarial assertions are in
[`test_consistency.py`](../../../tests/integration/architecture_spikes/test_consistency.py).

**Observed traps and verified corrections:** independent review found that
post-copy validation alone could leave a completion manifest on an invalid
candidate. A timing-based concurrency test could also pass before its child
actually attempted the writer lock. The corrected experiment validates before
writing the manifest and probes the OS lock at the precise between-copy cut.

1. Use different persistent SQLite files and inspect each file's WAL mode. Do
   not infer crash atomicity for multiple WAL databases from `ATTACH` or a
   transaction in one connection. Test process death at actual pre/post-COMMIT
   cuts and reopen both files to inspect persisted rows and identity-preserving
   retry. A valid committed Core fact survives absent Context without becoming a
   false coherent Context unit.
2. For the experiment's cooperative-gate strategy, take the shared gate while
   opening **and reading** both read transactions. `BEGIN` is deferred: perform
   a SELECT in each database before releasing the gate. Holding only two BEGINs
   does not pin two snapshots. Keep those transactions through result production;
   compare the deliberately unfenced mixed-snapshot counterexample.
3. During paired backup, prevent cooperating writers changing either source
   between copies. Validate both candidate databases, intra-store FKs, repository
   identity and relevant cross-store references **before** emitting a full-pair
   manifest. Repeat those checks when reading the artifact. A later validator's
   rejection does not repair an earlier false certification. Inject invalid FK
   and missing-referent candidates as negative cases, not only changed digests.
4. Prove lock exclusion at the controlled cut with a real subprocess nonblocking
   `LOCK_EX | LOCK_NB` attempt. Require `blocked`; deleting the shared backup gate
   must yield `UNFENCED` independently of process scheduling. A child-start event,
   short sleep or unfinished future alone does not prove the child attempted the
   lock or that the fence caused its blocking.
5. Report the actual fault model. `os._exit` demonstrates abrupt process loss and
   SQLite restart behavior, not host power failure, filesystem/directory fsync
   ordering, hostile writers or final activation/handover durability. The gate is
   an application mechanism, not a new persistent domain authority. Correct
   production durability and corruption-stop/recovery still require separate work.

Reproduce the executable evidence from the repository root:

```bash
uv run --no-sync pytest tests/integration/architecture_spikes/test_consistency.py -q
```

Use exact-tree receipts for results; do not copy a test count or claim these
experiments establish full backup/recovery acceptance.


## 7. Test negative information in immutable complete groups

When checking typed group conflict projections, compare a complete or known-empty
list's excluded slots as well as overlapping positive values. Independent review
of Prototype A reproduced two missed conflicts: known-empty versus a partial
slot 0, and complete `[parent0]` versus a partial slot 1. Both original assertions
were retained correctly; the derived conflict omitted the negative information
that a closed list asserts. Fix the projection, not the immutable evidence.

Require both admission orders to report conflict, and compatible partial/unknown
controls to remain nonconflicting. Do not infer closure for a partial or unknown
group, union partial groups into a complete list, or choose a report as canonical
from arrival order. The narrow Core regression command is:

```bash
uv run --no-sync pytest tests/integration/architecture_spikes/test_core.py -q -k closed_parent_group
```

This procedure tests a claimed group's actual comparable parent-list scope. It
is not permission to infer negative membership for Source known-positive pairs,
change Coverage's five-column/latest-observation contract, or treat a reported
complete group as receiver-verified.

## 8. Check all returned SQL capabilities and mirrored domain projections

For an isolated target adapter, a read-only method name or `query_only=ON` is not
an enforceable capability boundary by itself. Exercise actual supported operations:

1. Try transaction termination and `PRAGMA query_only=OFF` through both the
   connection facade and a returned cursor's `.connection`. Return the same
   restricted facade from cursors; never accidentally expose the trusted factory
   connection. Compose the domain admission authorizer with the coordinator's
   outer-transaction guard so a typed unit cannot commit its caller transaction.
2. Fetch from a cursor after its snapshot capability expires or a persistent
   catalog stop appears. Check both execution and deferred result consumption;
   protecting only `execute()` leaves a second path. Disable SQLite statement
   caching when authorizer decisions depend on a scoped admission capability.
3. Where Core and Context implement the same multi-SELECT projection, run a
   deterministic concurrent-writer counterexample against **both** implementations.
   A pinned Context Coverage test does not protect an unpinned Core implementation.
   Inject a writer between claims and proof reads using a trace/callback instrument;
   require one real before/after SQLite snapshot, never a mixed result. The test
   instrument may use private hooks, but competing writes must use supported APIs.
4. Count physical contract columns with `PRAGMA table_xinfo`, not just
   `table_info`: generated/hidden columns count too. Inspect generated-column
   values and SQLite `typeof`, including oversized JSON integer inputs; STRICT
   alone does not establish every computed expression's domain range.

The P1 regressions are under `tests/integration/p1/`. Reproduce with:

```sh
uv run --no-sync pytest tests/integration/p1/test_core.py tests/integration/p1/test_context.py tests/integration/p1/test_coverage.py tests/integration/p1/test_coordination.py -q
```

These procedures cover supported application capabilities and local snapshots.
They do not protect against arbitrary Python-private access, privileged DDL/file
replacement, or establish P7 power-loss-safe recovery/activation. Apply current
ADRs; the baseline recipes above are not permission to restore quarantine counts.

When testing corruption-stop transitions, place the contender at the actual
transition, rather than checking only that a marker exists after an exception.
A post-unwind handler that releases the writer gate before persisting the stop
allows another cooperating writer to commit in between. Persist the external
stop before releasing the owned fence, avoid recursively acquiring that same
lock, and serialize final COMMIT/candidate certification with stop publication
for faults detected from already pinned readers. Exercise process death at the
transition and restart with Operational absent. The catalog stop is independent
of per-object state; it must not create quarantine counts or clear itself when
another byte copy is available. The complete source-preservation and fresh
activation engine remains P7 work.

## 9. Verify the production adapters at every supported admission and read boundary

Use these target-specific procedures with the P2/P3 adapters and their common P1
contracts. They do not activate the public runtime or establish P7 recovery.
The [production compatibility report](../../../docs/implementation/p2-p3-compatibility.md)
records the actual source revisions, independent findings and executed tests.

- Test direct typed admission **and** supported coordinator callback SQL. A
  correctly hashed native representation can still have malformed commit/tree/tag
  syntax. Construct negative fixtures with matching native OID, type, size and
  body digest so they reach the grammar/role guard. `git hash-object --literally`
  is explicit malformed/legacy fixture construction, not evidence that normal Git
  fsck accepted it. Preserve folded headers losslessly with buffered joins;
  repeatedly concatenating a growing header makes bounded inputs quadratic.
- Do not permit generic SQL to emit retained body or proof byte columns around
  checked typed readers. Exercise direct columns, aliases and SQL expressions.
  Use semantic coordinates or `count(*)` for introspection assertions. Check the
  **selected** native representation again before output, rather than trusting an
  old verified bit. Validate persisted metadata's typed shape/provenance as well
  as JSON syntax; `[]` and a known type value of integer 17 are not valid claims.
- Separate immutable original reports from receiver checks in physical intrinsic
  link guards. Matching local bytes cannot mark the old `reported` alternative
  checked. Test scalar and whole-group links through actual callback SQL, with
  unchanged report projections, atomic rollback and genuine receiver replay.
- Diagnose stored-data failures in their real scope. SQLite `integrity_check`
  can raise `SQLITE_ERROR` when a semantic CHECK UDF encounters invalid persisted
  UTF-8, rather than returning corruption rows. Translate that validated storage
  failure and notify pinned read owners **before** a caller can catch it. Keep
  incoming malformed units, cancelled validation and resource/capability errors
  separate from persisted corruption; a generic user SQL error is not evidence
  of a damaged catalog.
- Inject corruption or a stop at the last SQL step/deferred fetch and before
  snapshot rollback. Persist the external stop before cleanup or caller error
  handling, and recheck completion after producing a typed result. Acquire the
  short completion fence after SQL stepping, not while a same-process trace can
  publish a stop and recursively take that fence. Verify both read and replay
  when a known retained-text FK loses its body: replay must not silently repair
  the stopped source. Unknown unreferenced digests remain unavailable evidence.
- Bind transaction/read capabilities to the actual `store_identity.store_role`.
  Context and Core have identically named Coverage tables; accepting the wrong
  database capability can otherwise change physical ownership without an SQL
  error. Reject the caller's wrong role before installing a writer capability,
  preserving the caller transaction and avoiding a false corruption stop.
- Compare required proof scope with the **persisted** evidence selected by its
  full semantic key. Comparing two agreeing caller-supplied objects is insufficient
  when the terminal FK omits immutable `scope_json`; it allowed head A evidence
  to certify head C. Include normalized parent-child ownership in collection and
  relationship admission so PR B's review cannot certify PR A's review list.
- Preserve unavailable attributed Core-reference candidates separately from
  validated required cross-store links. Retain their actual original field clock,
  observation time, role, provenance and full typed OID. A normal paired read must
  report that acquisition dependency honestly, without turning nonacquisition
  into catalog corruption. Validate reserved reference fields through ordinary
  field admission too, not just the convenience method.

Use the committed production suites under `tests/integration/p2/` and
`tests/integration/p3/`, the P1 contract regressions, and the committed disposable
combined test tree identified by the compatibility report. Independent reviewers
must revalidate corrected material findings against exact commits; a green earlier
suite does not cover a newly demonstrated counterexample.
