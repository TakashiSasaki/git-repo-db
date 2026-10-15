# Prototype B: two authoritative SQLite stores

This isolated experiment lives in `tests/integration/architecture_spikes/consistency.py`.
It does not alter the packaged schema, initializer, CLI, catalogs or existing runtime.
Its miniature Provider issue observation is a transaction fixture, **not** a proposed
replacement for the product's current-state/field-provenance model.

## Tested mechanism and recommendation

Use one catalog-wide OS writer/handover gate shared by **all** cooperating authoritative
writers, consistent readers and backup operations. The gate is reconstructible
process coordination, has no domain ID, stores no facts and authorizes no resource.
It is not a Publication authority. Never hold a SQLite write transaction over network
work: gather/validate input first, then enter the gate for bounded local admission.

1. Validate/admit independent immutable Git facts and COMMIT Core first.
2. Validate the referenced typed Core dependencies, then admit a coherent Context
   unit in one Context transaction. Missing Context never invalidates committed Core.
   A nominal resolved OID proves identity resolution only, not bytes or Git closure.
3. A lost acknowledgement retries the same genuine domain evidence coordinates.
   Exact replay deduplicates; incompatible immutable evidence coordinates fail.
   Context current-state updates will additionally need the existing per-field clocks,
   candidate conflicts and latest-observation rules; this fixture does not model them.
4. Combined readers take a shared gate, BEGIN both transactions and actually read
   each DB to pin **both** snapshots before releasing the gate. BEGIN alone is
   deferred in SQLite and does not pin a snapshot. Readers then use only that pair.
   Fail conservatively for absent/unresolved required dependencies.
5. Full backup takes the same shared gate through SQLite backup of both databases,
   excluding writers. Certify the finished pair only after both copies exist and
   identity/dependency checks pass. The manifest binds the exact file bytes.
   Interrupted copies without the final manifest are not full backups. Core alone
   can be used as Git-only data; it cannot be certified as Context-inclusive.

Core-first is a dependency ordering, not a distributed atomic COMMIT guarantee.
An orphan valid Core fact is intentional and recoverable. A Context transaction
cannot assert committed dependencies based solely on Operational progress.
All future Context mutation APIs must enforce this ordering and the read fence.
The physical writer gate is held across the two commits; a crash releases it.
On restart, durable Context units are the acknowledged-or-retry domain evidence;
there is no mutable Core revision, all-attempts log or outbox authority in this probe.

## Executed process-death cuts

`os._exit(86)` terminates a **subprocess** without Python cleanup. Each fixture has
separate persistent `core.sqlite3` and `context.sqlite3` files/inodes, WAL journaling,
`synchronous=FULL`, foreign keys and recursive triggers. A fresh connection reads
persisted state after each death. Counts are `(Core objects, Context units, links)`.

| Cut | Observed after restart | Retry |
| --- | --- | --- |
| Before Core COMMIT | `(0,0,0)` | `(1,1,1)` |
| After Core COMMIT, before Context | `(1,0,0)` | `(1,1,1)` |
| During Context, after unit header before member | `(1,0,0)` | `(1,1,1)` |
| After Context COMMIT, before acknowledgement | `(1,1,1)` | unchanged `(1,1,1)` |
| During backup, after Core copy | Core copy exists; no manifest | new destination completes and validates |

Additional automated assertions reproduce the naive mixed-snapshot defect, preserve
pinned old/old snapshots while a writer commits new/new, block a reader at the
Core/Context vulnerable cut, reject a mismatched backup file pair, roll back a
Context FK failure, and retain Core usability without Context.

Reproduce:

```sh
uv run --no-sync pytest tests/integration/architecture_spikes/test_consistency.py -q \
  -o junit_family=xunit1 --junitxml=/tmp/spike-b.xml
```

Initial execution: **11 passed**. The first run used default JUnit xunit2 and produced
four `record_property` compatibility warnings; rerunning with xunit1 preserved the
four actual persisted-state properties and produced **11 passed, no warnings**.
No runtime failure was hidden or retried to obtain green.

## Alternatives evaluated and limits

| Candidate | Assessment |
| --- | --- |
| Independent commits and unfenced reads/copies | Rejected: mixed Core/Context state is reproduced by an actual old Core snapshot/new Context read |
| `ATTACH` transaction spanning WAL databases | Not adopted; no crash-atomic multi-WAL claim. The test does not simulate/purport to establish SQLite multi-WAL COMMIT behavior |
| Core-first + cooperating OS gate + pinned pair reads | Recommended conservative first implementation; experiment demonstrates process-death and reader properties above |
| Durable universal publication/outbox/resource-seal ledger | Not needed and not introduced; would require separate justification against NO_INDEPENDENT_PUBLICATION |
| Higher concurrency via domain dependency tokens and snapshot validation | Possible later optimization; must independently prove stale/fork/current-state and backup behavior |

This is **process-death evidence, not a power-loss/filesystem/hardware proof**.
`FULL` requests SQLite durability but tests do not emulate torn sectors, lost fsync,
OS death or WAL checkpoint corruption. The backup manifest write is not fsync/rename
hardened; production needs file/directory fsync, interrupted restore/activation tests,
immutable schema fingerprint validation, retained-byte/domain verification and
no-overwrite destination publication. A manifest hash is artifact binding, not issuer
authentication or proof of all domain semantics. An attacker who replaces files and
rewrites manifests is outside this prototype's certification model.

All participants must use the supported gate/API; arbitrary SQL, alternate paths or
privileged filesystem replacement bypass coordination. Handover needs the gate at a
stable catalog location and a validated pair locator: existing handles must be bound
to the chosen instance, and restart must revalidate identity and any recovery stop.
This fixture tests reader activity, not atomic installation/handover of catalog paths.
No production corruption stop/salvage/restore/merge engine is implemented: ADR 0026
still requires stopping ordinary service before any write to damaged authority,
read-only preservation and fresh verified restore plus validated merge. Operational
and Search are absent here; neither is required to recover the tested durable facts.

## Independent review corrections

A read-only reviewer reproduced a **Major** certification defect: backup originally
wrote its final manifest after dependency checks but before repository/FK/integrity
validation. A wrong-repository Context therefore received a manifest even though
later validation rejected it. `validate_pair` now runs the same candidate checks
**before** certification and after artifact transfer. Three negative fixtures
(wrong repository, orphan FK and unresolved Core dependency) all assert no manifest
is produced. Corrected B suite: **14 passed, 0 failed/skipped**.

A **Minor** concurrency-test weakness was also corrected: starting a writer child
between file copies did not prove it had attempted the gate before the second copy.
The child now attempts `LOCK_EX | LOCK_NB` at that exact cut and must report
`blocked` before backup continues. Removing the backup gate yields `UNFENCED`
regardless of scheduling. It subsequently performs the actual admission and the
backup remains the old/old pair. This makes the negative meaningful without relying
on a sleep or scheduler race. Independent recheck is recorded in the review report.
