---
name: three-store-invariants
description: Diagnose the implemented Schema 21 Three-Store baseline under ADR 0002, including cross-store isolation, cache GC, split-write resumption, Core-only maintenance and search fencing, and verify target paired-snapshot coordination experiments. For the newer Git Core/Context target, first apply the current ADR index and scoped replacements; baseline quarantine-count and full-backup recipes are not target requirements.
---

# Three-Store Boundary Architectural Invariants (ADR 0002)

**Applicability:** The concrete tables, methods and recipes below describe the **implemented Core Schema 21 / Operational 1 / Search 1 baseline**. For target work, read the [ADR index](../../../docs/adr/README.md) and [transition plan](../../../docs/architecture/git-core-context-transition-plan.md). [ADR 0029](../../../docs/adr/0029-independent-access-store.md) is the accepted five-store successor to historical ADR 0003; it preserves independently durable Context and INSERT-only Git Core while separating Access; [ADR 0014](../../../docs/adr/0014-history-and-notes-catalog-without-file-archive.md) excludes ordinary file-body archival. [ADR 0026](../../../docs/adr/0026-stop-salvage-restore-merge-after-corruption.md) replaces quarantine/count/release and same-DB continuation with immediate catalog recovery. [ADR 0036](../../../docs/adr/0036-ref-observations-and-shared-notes-mappings.md) fixes unauthenticated external-origin reports without application PKI/signatures. Preserve unaffected safety principles; do not copy superseded baseline mechanisms into the target or infer new execution permission from this skill.

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

## Diagnose public-runtime test observations before changing storage

For Schema 21 `no such table` failures, first identify the actual connection and
the packaged DDL owner. `JobService(Store(...))` already writes to Operational;
a test reading `jobs` through `Store.one()` is inspecting Core. Use
`store.operational` for jobs, attempts, collection/acquisition progress, leases
and locators, and an explicitly opened `store.open_search()` context for index
generations and projections. Install failure-injection triggers on the same
physical connection used by the production writer.

Never repair these tests by adding Core tables/views, SQL-routing wrappers,
implicit ATTACH or duplicate state. After the operation is quiescent, read
Operational identifiers and inspect matching Core evidence with separate queries.
Do not claim this test observation is a cross-store atomic snapshot. Use real
JobService creation or an Operational transaction for the deferred job/attempt
foreign-key pair. Assert schema absence for retired `incremental_scans` and
`content_locations`; keep their original behavioral coverage through actual
request watermarks, retained Core facts and excluded backup cache state.

An incomplete Core collection cannot become complete merely because Operational
has a cursor or success flag. On retry, check the new root request, distinct
collection identity, retained admitted resources, and genuine new terminal
evidence. Do not require reuse of an incomplete collection's cursor or observation
time. A genuinely complete Core terminal can still support safe reuse after
Operational loss. Preserve old-to-new node mapping if renaming obsolete mechanism
tests. See the [Schema 21 checkpoint](../../../docs/implementation/evidence/schema21-baseline-20261016/ROOT-CHECKPOINT.md)
for real loss and split-write counterexamples; this procedure does not apply the
five-store target to the public runtime.

Run the entire affected lifecycle cohort after correcting a connection: a missing
table can mask a second stale continuation assertion. Check old partial versus
fresh collection IDs, preserved admitted prefixes and actual fresh scan times.
Do not report aggregate sync as complete while newer or equal-clock selected
Coverage remains partial/conflicting. Classify both layers in per-node evidence.

For repeated Search rebuilds, scanning public PR/Issue queries alone cannot prove
projection correctness. Retain documents referenced by an old generation until
replacement succeeds, but admit only the pinned Core snapshot's current keys to
the new generation. Test a stale-only 200-row batch before current documents, real cancellation
with the old ready index intact, repeated and empty rebuilds, and retained Core
text. Unreferenced Search derivatives may be removed after promotion; this does
not authorize deleting authoritative text or promise atomicity of all rebuild
and cleanup phases.

Use a dedicated workspace `TMPDIR` and `--basetemp` for sustained/parallel full
suites when `/tmp` has a smaller capacity. Record disk exhaustion separately from
product errors; preserve JUnit/journals and rerun the affected exact nodes with
sufficient capacity. Remove only confirmed completed disposable test directories,
never another active worktree's fixtures or real catalogs.
Run pytest through the intended worktree's `uv run --no-sync`, or prepend that
venv's `bin` to `PATH` when invoking its Python directly: CLI helpers spawn
`repo-catalog` by name. A correct parent import alone does not bind child commands.

---

## Classified time and checksum policy for target work

Read [ADR 0028](../../../docs/adr/0028-classified-times-and-sha256-exchange.md)
before applying older time fixtures: nullable observation/Provider values must
be positive when known; Coverage/terminal coordinates stay required positive;
native Git times stay signed. Preserve the purpose of a changed fixture and map
its old node to replacement/additional coverage. Do not claim SQLite affinity
checks validate original Python/JSON types. Exchange compares declared and local
canonical SHA-256; cursor SHA-256 is a checksum, not sender authentication. Actual
executed lessons require exact-revision evidence; this paragraph states accepted
policy, not an executed implementation result.

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
experiment, not as evidence that the production five-store runtime is implemented.
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


### P4 verified extensions to section 9

Apply to opt-in P4 Notes and future intrinsic group/read extensions; these do
not activate the public runtime or change accepted policy.

- Exercise every new typed reader directly and through its public callers.
  Decorators on an overridden base method do not transfer automatically, and a
  protected caller does not protect the method it calls. Persisted invalid UTF-8
  and bounded but excessively nested JSON must publish the persistent catalog
  stop before returning. Catch decoder failures only in trusted stored-value
  scopes; invalid user SQL or incoming input is not storage corruption. Verified
  regressions: `test_persisted_inventory_invalid_utf8_publishes_stop` and
  `test_persisted_inventory_deep_json_publishes_stop` in the P4 inventory suite.
- Add receiving SQL guards for every new receiver-intrinsic group meaning, not
  just a Python convenience method. A supported coordinator callback previously
  committed a forged known-empty inventory and poisoned the next read. The
  corrected trigger joins the actual full Capture FK and rechecks native
  structure, exact membership/path and terminal scope. Test valid controls,
  forged closure and original reported alternatives through real callback SQL;
  input refusal must leave the catalog sound. See `test_inventory_callback.py`.

## 10. Verify conservative request accounting beyond clean retries

Use the production P4 accounting suite and actual disposable SQLite/process
faults; Prototype C's post-read charge is not production crash-gap evidence.

1. Reserve durably before actual work on a dedicated autocommit Operational
   connection with WAL, foreign keys and synchronous FULL/EXTRA. Test process
   SIGKILL and a failure after an actual read but before its acknowledgement.
   An unsettled permit remains charged; a reconstructed/restarted permit cannot
   settle it to zero. Use one-shot live settlement capabilities.
2. Allocate processing coordinates atomically in the existing domain request
   and attempt. `count(*)` is not a safe next occurrence after failed allocations
   or concurrent handles. Never mint a Capture solely to retry work.
3. Test partial loss as well as missing files: remove a settled/unsettled work
   row, budget, allocator, attempt, discovery or physical-copy allocation. A
   mandatory checkpoint must refuse old continuation, not report known zero or
   regenerate identity. Reconcile cached totals against actual rows on reopen
   and unknown writes under a SQLite fence; cache only recognized own transitions.
   Core/Context reads remain valid without Operational. Checkpoints detect
   consistency/loss, not an attacker rewriting all matching database evidence.
4. Inspect SQL triggers as well as Python for growing-history scans. Actual VM
   steps via `set_progress_handler` reproduced a per-reservation increase from
   310 to 16,308 instructions over 0→2,000 rows despite cached Python validation.
   Corrected cached Operational cost plus trigger checks stayed at 326 steps.
   Regression compares VM work, not noisy wall-clock timing. Use subtraction
   limit checks and `spent - old_cost + new_cost` to avoid intermediate int64
   overflow; revalidate cached cost against ledger/checkpoint on resume.
5. Bind application acquisition to actual Core/Operational catalog identities,
   selected local source path/format and explicit request intent. Optional caller
   conventions permitted charging a foreign catalog's request. Preserve external
   Capture attribution separately; local mirror checking does not authenticate
   or rename the original capture issuer/source.

Verification: `uv run --no-sync pytest tests/integration/p4 -q`, P1/P2/P3 and
cross-domain regressions, installed wheel/sdist-wheel tests and the four required
audits. In a shared virtualenv, explicitly set `PYTHONPATH` for standalone scripts
in each worktree: editable imports otherwise inspect another branch's schema.
These tests prove process/SQLite fault behavior, not host-power-loss durability,
P7 recovery or release acceptance. The [P4 report](../../../docs/implementation/p4-production-notes.md)
and [review findings](../../../docs/implementation/p4-independent-review.md)
bind procedures to executable source and independent revalidation.

## Classified target time and typed snapshot owner checks

Verified at shared executable `f17dd2154f22f965883d8a1943c140f9cc439ae8`;
see [shared correction and raw evidence](../../../docs/implementation/p5-p6-shared-time-correction.md).
Keep generic signed-int64 conversion distinct from nullable-positive observation/
Provider validation and required-positive Coverage/terminal coordinates. Change
old negative-observation fixtures without losing their provenance/overflow
failure purpose; positive unrelated coordinates isolate those negative checks.
SQL affinity enforces stored values, not the original bound Python type. JSON
clock checks must reject bool/real/string/overflow before generated-column use.

A typed read factory must bind the actual live coordinator snapshot owner, not
an unrelated caller path. Independently reproduced catalog A snapshot/directory B
misbinding routed a real retained-byte stop to B. The corrected factory rejects
that binding, preserves the owner's error callback and expires with its snapshot.
A caught typed corruption still fences ordinary helper completion and persistently
stops A. Metadata-only tokens omit payload certification; typed byte reads retain
their verification boundary. These lessons are tested shared behavior, not P7
recovery, host-power-loss validation or P8 activation evidence.

### P6 verified read and derivative review procedures

- Test escaped typed read capabilities after the snapshot context closes, and try
  binding a live snapshot to an unrelated catalog directory. Typed expiry and
  owner routing must survive both cases; private `__new__` assembly in an
  application bypassed the supported binding checks. Use `GitCore.for_snapshot`
  and the original snapshot's catalog owner, not an unverified caller path.
- Recompute public cursor checksums in adversarial tests. Corrupt key arity,
  element types and OID ranges independently; unchanged-digest tampering alone
  never verifies content validation. Accepting a different valid position cannot
  be described as origin authentication.
- Guard the entire stored-row construction, including JSON indexing and `*args`
  unpacking before a typed constructor. A constructor-only wrapper missed valid
  JSON scalar provenance. Search's raw projection extractors need the same typed
  reconstruction and stop boundary as ordinary views. Preserve invalid external
  cursor and finite query-limit failures as non-corruption outcomes.
- Put disposable Search byte/row/VM and encoded-document size checks before
  substring evaluation or `fetchall()`. A post-allocation dictionary check
  accepted allocation of a malicious multi-MiB derivative row. Verify fallback
  before Python document construction. Catch parser-depth exhaustion inside
  derivative lookup so it cannot enter an authoritative corruption boundary.
  Exercise binary Notes with invalid
  UTF-8 bytes in rebuild/scan equivalence tests.
- Report actual `instr()` plus full authority verification as a verified scan.
  A fresh projection token and matching candidates do not establish an FTS
  accelerator. Measure metadata token generation, authority validation and
  derivative lookup separately; keep metadata queries out of retained-body reads.

Formal checks: `tests/integration/p6/test_corrections.py` and
`tests/integration/test_snapshot_read_limits.py`. These use disposable catalogs,
finite-work refusal, growing candidate sets and tracked live objects. They do not
prove full release acceptance, power-loss durability or indexed acceleration.
## Revalidate transport and request boundaries with independent counterexamples

### Fence every representation of a staged unsupported operation

When a schema stage temporarily removes a prior typed guarantee, enumerate every
durable representation: report/header rows, both endpoint roles, generic facades,
typed intake, and replay. An endpoint-only fence previously allowed a Provider-only
Transfer report. Use unconditional pre-conflict SQL guards for all representations
and retain immutable UPDATE guards; test true PK collisions and no-op UPSERTs too.

For real Exchange, validate wire/digest rules first, then fence the receiver's
selected atomic operations before dependency rewriting, package replay or authority
effects. A guard during the first sender-selection traversal also blocked a lawful
independent Core-only receive. Test mixed order, report-only units and primed replay
through the actual importer, not only a normalized model. Do not interpret arbitrary
metadata text or case variants as reserved operation names.

Explicit unsupported reads must refuse on empty stores. Distinguish that input
outcome from impossible rows in an exact trusted schema: the latter must enter the
existing authoritative-corruption stop before normal query/export/Search exposure.
Do not catch an unsupported input inside a stored-decoder corruption wrapper.
Preserve diagnostic injected rows and compare complete pre/post rowsets.

Author regression commands: `pytest tests/integration/p1/test_generalized_resources.py`
and `python scripts/verify_i2_sql_counterexamples.py REPOSITORY NEW_DIR`.
The [I2 implementation record](../../../docs/implementation/adr0031-i2-implementation.md)
states the stage limits. These checks are not independent acceptance or substitutes
for later typed support, wire integration or release qualification.

P5's [corrected-source review](../../../docs/implementation/evidence/p5-correction/independent/review.md)
independently reproduced missing declared-digest comparison, free request restart,
retry UUID changes, broad Coverage promotion, partial-outcome loss and paired
export races. Its exact-node receipt distinguishes baseline failures from the
corrected execution and Provider-order cases that already passed the baseline.

- Recompute a valid SHA-256 after modifying domain data to reach independent
  domain validation. A checksum mismatch test alone cannot verify receiver
  Notes/native checks or cursor/content structure; rewriting content plus digest
  is possible without a key and proves no authenticity.
- Remove all SQLite accounting and reopen with the same identities, then try
  continuation and repeated initial-creation flags. A missing budget/request
  must refuse the old request, including after restart. Preserve accepted reads;
  explicit new work gets a distinct request identity and may retain its Capture.
- Count durable physical-copy rows and compare actual Capture pairs across
  lost-ack retry. Counting objects alone misses new copy allocations. Reserve
  before external reads and meter repeated verification/parser work even when
  Core insertion is idempotent.
- Place a separate writer contender during real source I/O and during export
  extraction. Verify input preparation allows the writer lock, paired extraction
  blocks conflicting writes, and a stop injected before final return prevents
  completion. Exercise an actual subprocess `LOCK_EX | LOCK_NB` at the cut, as in
  `tests/integration/p5_p6_compatibility/test_export_gate.py`; an Event set before
  a lock call and a short incomplete wait alone are scheduling evidence. A
  snapshot opened and closed before extraction does not fence it.
- Inspect built sdist members. The current backend includes untracked `work/`
  scratch despite local Git excludes. Build distribution acceptance artifacts
  from a clean committed archive with evidence stored outside that source tree;
  install wheel and sdist-wheel into isolated environments outside checkout.
  This is packaging input hygiene, not a source cleanup or deletion recipe.

## Recovery replay must pass authoritative admission checks

A retained-byte digest match alone bypassed native type/size checks, Capture
repository identity, role proofs and physical-copy distinctions in P7 salvage.
The focused baseline counterexamples and corrected executions are retained in
[the replay checkpoint](../../../docs/implementation/evidence/p7-replay/README.md).

- Run the same typed production admission on replay as on new input, including
  immutable-row equality, before counting replay. Work performed by revalidation
  is still actual work. A new physical copy is not an exact replay; missing
  original identity cannot be repaired by inventing a copy UUID.
- Validate every original Capture binding coordinate, including repository,
  source/ref/root and both UUIDs. Compare duplicate envelope/payload coordinates;
  forensic extraction provenance is not original domain provenance.
- Let the typed Notes unit install Capture, role and body atomically. Independently
  admitting Capture before proof/body validation leaves authority after rejection.
- For each mutation in the identity/role/body matrix, compare all authoritative
  tables before and after rejection, then include successful exact replay and new
  independent-copy controls. This avoids tests that pass solely by refusing all
  candidates. Include zero-byte bodies/text as legitimate input controls.

Use `uv run pytest tests/integration/p7/test_exact_replay.py -q` for the focused
checks. This procedure does not grant authenticity to attributed reports, imply
full typed recovery of unsupported Context resource candidates, or establish
host-power-loss guarantees.
### P7 recovery-request reservation boundary

For disposable fresh-destination salvage merge, keep request accounting outside
Operational/Search. Bind a canonical path-safe request ID to one immutable finite
contract; serialize its complete attempts with a permanent process lock. Reserve
before input or admission work, fsync the reservation checkpoint before updating
its report, and retain the greater checkpoint expenditure after interrupted
report publication. Settle a successful live measurement with the reverse order
(report first, checkpoint second), so interruption cannot refund uncertain work. A missing/corrupt record refuses continuation; never interpret
it as zero. Explicit new work must use a distinct ID. Do not infer that removing
all external accounting evidence is detectable or that process-crash tests prove
host power-loss durability.

Reproduce with `uv run pytest tests/integration/p7/test_durable_budget.py -q`.
The suite uses spawned processes and SIGKILL before work, after work and after
actual authoritative admission, concurrent retries, lowered reports, missing
records, invalid IDs and Operational/Search deletion. Keep these counterexamples
at the real work boundary when changing the reader or admission code.
## Target recovery: bound materialization and preserve unknown scope

When extending P7 salvage, keep input limits ahead of allocation. A `SELECT *`
followed by a Python `len()` check has already materialized an untrusted SQLite
row. Apply finite SQLite length/column/SQL/VM limits and bounded projections.
SQLite can reject a very large source row before a CASE projection runs; report
that table as unreadable/incomplete rather than inventing a recovered candidate
or diagnosing confirmed corruption from `SQLITE_TOOBIG`.

Reserve bounded binary JSONL chunks before reads. Check lexical JSON nesting and
element counts before `json.loads`, then validate the parsed shape. Bound base64
and proof hex representations before decoding. Charge malformed/rejected input
as actual request work. At a limit, stop reading; do not scan an arbitrary suffix
just to count omissions. Mark omitted counts as lower bounds and enumeration as
incomplete. Count an unread suffix only when prefetched/buffered bytes or the
regular file's size and current offset establish that it exists; uncertainty
alone cannot justify inventing another omitted candidate. An oversized partial candidate must also make the extraction receipt
partial. Keep serialization/output budgets separate from proof of completeness.

Reproduce these boundaries with `python -m pytest
 tests/integration/p7/test_bounded_input.py` (one shell line). The tests cover
Python allocation for BLOB/text, SQLite unreadable scope, streamed-copy growth,
JSON limits and rejected-input work. They do not establish host power-loss
semantics or authorize recovery on real catalogs; use disposable synthetic
catalogs and retain independent process/filesystem evidence for those claims.
## P7 standalone snapshot and descriptor lessons

A SQLite backup can preserve WAL journal mode even though its data is fully in
its main database. Subsequent read-only validation can then create zero-byte WAL
and SHM sidecars. For a standalone P7 backup artifact, switch the **new snapshot**
to DELETE journal mode before closing it; do not change the suspect source's
mode or delete its journals. Reject undeclared backup sidecars during restore
rather than accepting unmanifested bytes. Verify with
`pytest tests/integration/p7/test_filesystem_hardening.py tests/integration/p7/test_consistent_backup.py`.

For untrusted restore inputs, pin directory and regular-file descriptors with
no-follow opens, bound manifest reads, and hash the bytes actually copied.
A prior file hash followed by a pathname-based copy does not bind the copied
bytes. Use directory-relative publication and fsync; distinguish a failure after
rename from an unpublished result. The regression tests include symlink/parent
substitution, separate-process no-overwrite publication and SIGKILL during
copying. These verify Linux local-filesystem ordering and process interruption,
not physical host power-loss durability or protection against privileged writers.

An activation directory pin must remain open through validation, derivative
initialization, both catalog gates and locator publication. Opening and closing a
directory descriptor before validation does not pin later pathname operations.
Perform catalog I/O through the retained descriptor and compare the advertised
pathname's inode before and after publication. On a detected substitution, reject
the receipt and restore the prior locator (or remove the newly created locator).
Exercise both publication sides and both absent/existing locators with
`pytest tests/integration/p7/test_filesystem_hardening.py -k catalog_path_swap`.
These checks do not make directory names immutable against arbitrary
noncooperating writers after activation; preserve the supported cooperating-process
namespace contract.

When an incoming Context text digest matches an existing key, verify the stored
exact UTF-8 bytes as well. Rejecting a valid candidate after finding a damaged
stored digest is insufficient: publish the recovery stop while the catalog writer
cut is still held. Reserve byte allocation and hashing/comparison work before
fetching the stored BLOB; read its size and body in one transaction. A finite
verification refusal or invalid incoming digest proves no stored corruption.
The focused controls are `tests/integration/p7/test_context_corruption_stop.py`.

The same existing-authority rule applies to a retained Git physical copy: before
calling a matching key replayed, boundedly verify that stored native bytes/type/
size/digest and retained Notes Capture/root/role still validate. An immutable
coordinate conflict alone does not prove either side corrupt. Recheck only the
selected copy under the writer cut; reserve allocation before fetching bodies
and use the existing actual-verification meter. Finite proof-parser refusals must
remain typed resource refusals, never confirmed stored corruption. Regression
controls are `tests/integration/p7/test_stored_copy_corruption_stop.py`.
### P7 trusted CHECK and TEXT revalidation

Do not equate read-only `PRAGMA integrity_check` with application-domain CHECK
validation. A disposable Core with exact schema but invalid `captures.ref`
returned `ok` through a read-only connection while a writable connection exposed
its failed UDF CHECK. Decode bounded chunks of actual stored TEXT bytes before
SQLite/Python UDF decoding, then explicitly evaluate every CHECK expression from
the trusted packaged CREATE TABLE SQL. Parse balanced parentheses and SQL quoting
and comments; never execute recovered SQL. Use `WHERE NOT(expression)` so NULL
retains SQLite's CHECK meaning. Keep binary Notes/native BLOBs outside UTF-8
validation and preserve empty text and split multibyte sequences.

Reproduce with `uv run pytest tests/integration/p7/test_stored_constraints.py -q`.
Those regressions retain exact schema, corrupt Capture refs and metadata TEXT,
exercise a valid-UTF8 false UDF CHECK, and include binary Notes/empty/long Unicode
positive controls. The procedure verifies stored authority; it grants no source
attribution authenticity or host power-loss guarantee.
Keep work dimensions distinct: a reserved JSONL read does not reserve decoded
body input, and a record counter does not charge nominal domain lookup/admission
work. Reserve decoded base64/hex/UTF-8 byte bounds before allocation and settle
measured success; retain conservative failed-decode expenditure. Production
Core processing repeats actual input work and keeps its own charges. Give test
fixtures enough allowance for both real passes rather than exempting decoding.
Verify nominal repository/object/Capture replays and rejected candidates against
their own finite metadata/input ceilings, using
`python -m pytest tests/integration/p7/test_work_dimensions.py`.

Treat missing required destination bytes as corruption before salvage can
reinsert them: an existing text FK claim proves its Context body is required;
existing intrinsic claims/groups prove their metadata physical copy is required.
A Notes role alone does not prove a body was retained. When dependency columns
lack a complete lookup index, reserve finite SQLite VM work before the lookup,
settle only live measured work, and refuse at the cap without inferring absence.
Use `tests/integration/p7/test_missing_required_authority.py` to distinguish
missing required authority, genuinely new content and finite-query refusal.

### Verify constraints behind a retained staged-operation fence

When a stage adds SQL constraints but the product operation must stay refused,
use the actual packaged product DDL and compare the complete constructed schema
before touching the disposable test database. Remove only the named fence
triggers in that disposable database; record their exact definitions and removal
statements. Keep every other CHECK/FK/index/UDF/pragma identical. Test both raw
composition and the product factory, plus normal connections with the fences
present. Never reopen the modified schema through the normal validator or count
isolated success as product operation availability. Preserve the application
refusal and impossible-storage recovery controls until their owning later stage.

The I4 tests in `tests/integration/p3/test_transfer_sql.py` exercise this procedure
for native-I7 SQL. Run `scripts/verify_i4.py` with the environment's Python-loaded SQLite under
[ADR 0032](../../../docs/adr/0032-environment-sqlite-validation.md) and
`scripts/verify_i4_distribution.py` outside the source artifact through its fresh
installed environments. Bind the evidence to an executed commit/tree and retain
nonzero inherited staging failures. A structurally stored original Event type
does not establish its Provider meaning; I5 owns semantic Admission. Whole-unit
completeness and pre-affinity original timestamp types cannot be inferred from
successful SQL references.

The I5 tests in `tests/integration/p3/test_transfer_admission.py` exercise Typed
Transfer Admission for native-I7 SQL. Run `scripts/verify_i5.py` with the environment's single Python-loaded SQLite
under [ADR 0032](../../../docs/adr/0032-environment-sqlite-validation.md) and `scripts/verify_i5_distribution.py` outside the source artifact through its fresh
installed environments. Both SQL transfer stage fences (`i2_transfer_stage_fence`,
`i2_transfer_report_stage_fence`) remain present in product DDL; normal production paths
reject Transfer operations with `I2_TRANSFER_UNSUPPORTED`. I5 enforces semantic Admission,
pre-affinity original timestamp validation, atomicity via SAVEPOINT, and G3=A permanent
violation vs dependency missing classification, leaving Identification Wire and Exchange to I6.


An older impossible-storage corruption fixture can fail at injection after a new
constraint is added. Keep its original corrupt values and downstream stop/rowset
assertions. Bypass additional guards only inside the explicit corruption
injector, then restore all original DDL and required settings and verify the
complete product schema before exercising the reader. This is distinct from the
constraint-verification lane, whose integrity settings must remain enabled.
The eight retained I2 matching-schema poison nodes demonstrate this distinction;
a prior 67-failure/20-error run records the additional eight injection failures.

When comparing archived regression failures, select the receipt for the actual
final reviewed execution, not a filename that merely contains `author`. An
archive can preserve both superseded failures and a later final run. Retain raw
messages and frames; compare refusal code/text and source function paths while
recording line offsets and temporary installation-path differences explicitly.
The I4 comparison helper targets I3's `final-{version}/regressions.xml`; its
separate initial 81-fault receipts are not the final 79-fault baseline.

## Service-bound Context admission and commit ownership (ADR 0031 I6-A)

Apply this procedure to the I6-A branch's guarded Context API; it is not a grant
for ordinary Transfer activation or I6-B/C/I7 integration. Both packaged Transfer
fences remain authoritative. Caller-provided principals, policies and stored
replay rows do not establish current local authority.

A dependency scan that handles only direct relation objects misses semantically
reserved carriers. The I6-A supporting review reproduced an OID-only permission
bypass through `link_core` primitive arguments, and found the same semantic OID
inside `FieldCandidate("reported_core_reference:...")`. Enumerate typed scope
Source coordinates and those reserved field values as well as direct
`CoreReference`, report members, mappings and Disposition replacements. Test each
public carrier separately, including exact replay after OID-only revocation;
assert no callback/dependency lookup and no durable row difference. Do not infer a
local Source registration from an arbitrary provenance `source` string.

Retain a serialized policy lease until the actual outer COMMIT. A SAVEPOINT
release is not a commit boundary. Checking revision after COMMIT cannot undo
writes, so validate all live leases before COMMIT and require the trusted port to
serialize revocation through lease release. An unconnected caller-owned
coordinator transaction must fail closed until its commit boundary can retain the
lease. Test a successful first endpoint INSERT followed by a second-INSERT
trigger failure; preflight rejection does not exercise that rollback. Also test
actual deferred COMMIT failure followed by explicit ROLLBACK and unchanged
preexisting Parent/Event evidence. Charge work already performed after failure.

When expanding current mapping candidates or Source positives, bound and charge
rows before accumulating or decoding the full set. Prefer exact relevant-pair
lookups over loading a whole Source roster. Current schema inspection must
preserve lifecycle stop and SQLite CORRUPT/NOTADB exceptions. Reverify connection
profiles on raw connections, while respecting the existing coordinator's exact
restricted capabilities, whose factory already verified its connection before
installing the authorizer. Do not relax that authorizer to execute PRAGMA.

Verified reproductions and limits:

```sh
pytest -q tests/unit/test_context_admission.py \
  tests/unit/test_context_fences_i6a.py \
  tests/unit/test_context_oid_admission_i6a.py \
  tests/integration/i6a tests/integration/p3/test_transfer_admission.py \
  tests/integration/p3/test_transfer_sql.py
```

These are Author regressions and supporting review probes, not independent
acceptance. See the new [I6-A evidence](../../../docs/implementation/evidence/adr0031-i6a/author/REPORT.md)
for exact executed source bindings, outcomes and unconnected routes. Never apply
these procedures by weakening the product's schema fingerprint, SQL constraints,
fences or original pre-affinity input validation.

For an explicitly authorized paired Context write, the coordinator is the outer
commit owner. Bind its local service at construction, require its issued
invocation on admission, and let only the exact expiring transaction capability
share the commit-owned lease stack with Store/Facade. Accepting a replacement
service per call would recreate the foreign allow-all attack. Keep Provider and
Exchange wiring separately refused until their assigned integration stage.
Exercise the original cross-store/crash/recovery assertions with finite fixture
authority; a missing context is not proof those assertions executed. The I6-A
coordinator cohort preserves all original assertion ASTs and runs under this
explicit binding. Include cursor close and canonical CoverageClaim paths: a
re-exported domain type's actual `__module__` can differ from the import module,
so an explicit type/module allowlist must cover the genuine definition without
an opaque fallback.

## Reserve preparatory work and verify received checksums before normalization

For a finite planner, give its shared hard-cap scanner the remaining cumulative
request budget before scanning already decoded input. Reserve character passes,
embedded JSON/identity parsing and queue growth before their allocation or work;
a later refusal cannot undo a complete preliminary scan. Keep the wire element
counter distinct from character-inclusive request work. Document the fixed cost
of a failed reservation and preserve only completed whole semantic units.
Exercise zero/small/exhausted-prior budgets on large, already validated but
unselected input; instrument actual parser calls and lengths. Include exact scan
and full-plan work, depth/byte boundaries and lawful/caller cycles. Output-only
counters do not establish a bound on preparatory work.

For transport integrity, hash the bounded received dictionary, excluding only
the declared digest, before constructing a domain type that normalizes sets.
Reuse the existing canonical encoder and selection `to_dict()` authority. Reject
received duplicate or noncanonical set arrays even after their raw checksum has
been recomputed; never silently repair them. Test stale and freshly recomputed
digests across dictionary/text/UTF-8 carriers, with canonical positive controls.
A checksum proves neither Provider authenticity nor current admission authority.

Reproduce the Author correction with
`pytest tests/unit/test_context_scan_budget.py tests/unit/test_exchange_received_digest.py tests/unit/test_context_dependencies.py`.
The [M01/M02 evidence](../../../docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/REPORT.md)
retains the failed frozen review probes and corrected observations. This procedure
does not activate Provider/Exchange routes, retire Transfer fences or substitute
for separate non-Author review.

## Replay and bounded note-copy reads

When a valid incoming note replay conflicts with a stored copy, validate the
existing copy's native bytes, digest and exact claim/root/role evidence under
the writer cut before treating the input as an incompatible replay. A constraint
error alone does not prove corruption; explicitly diagnose the stored unit and
persist the catalog stop only for a confirmed authoritative invariant failure.
If the conflicting representation is another copy, bound and charge the
diagnostic scan across every table actually compared, including transitional
legacy copies, and preserve an ordinary refusal for a checked valid collision.
Account for comparisons performed by SQL INSERT triggers too: reserve the
bounded existing-copy byte cost before they run, retaining the reservation if
an interruption makes actual comparison work uncertain.

Select one eligible copy by an indexed semantic scope before loading body bytes.
Measure all variable-width columns, enforce finite limits, and reserve cumulative
input work before fetching each row, including dependent claim and subject rows.
Bound caller metadata and its encoded form before serialization; copied identity
coordinates do not substitute for comparing the complete immutable claim.
Charge actual repeated proof and body verification;
an exhausted budget must not be converted to a corruption stop. Include a
same-length damaged body, missing role, valid replay, unrelated constraint
failure, interrupted reservation and several large copies as separate controls.
For SQLite's supported P1 version, `octet_length(column)` obtains a TEXT or
BLOB byte length from storage metadata; `length(CAST(text AS BLOB))` may load
the unbudgeted text first. See SQLite's [core functions](https://sqlite.org/lang_corefunc.html#octet_length).
Exercise the synthetic regression with
`scripts/local-run.sh pytest -q -n 2 tests/integration/p1/test_ref_observation_i1.py`.
This is an opt-in Core boundary; it does not implement I2/I3 or establish release
acceptance.
