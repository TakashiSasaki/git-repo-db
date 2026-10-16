# P4 opt-in production Notes acquisition

P4 implements local Notes namespace discovery, capture-scoped mapping proof,
exact note retention, independent inventory evidence and cumulative durable work
accounting. It builds on integrated P2/P3 main
`5e778bf61ef660f65bf5fb22bdb08840503b8464` (tree
`2c6eca80e6432a1b4f89a2111e7ded69c6b9a507`). The public initializer still uses
Schema 21. No migration, real catalog, backup replacement, recovery, activation,
merge, release, tag or site deployment is performed by P4.

The [engineering specification](p4-notes-technical-design.md) is proposed by
[design PR #77](https://github.com/TakashiSasaki/git-repo-db/pull/77). [Implementation PR #78](https://github.com/TakashiSasaki/git-repo-db/pull/78)
is stacked on that branch. Engineering corrections and executed verification are
reported here and in the [exact execution receipt](p4-execution-evidence.json),
not represented as new owner-approved ADR decisions. All accepted ADR meanings
and the P2/P3 portable values remain binding. Owner architectural blockers: zero.

## API and ownership

* `adapters.git.notes.GitNotesSource(GitNativeSource(path))` reads bounded local
  native structures, discovers Notes refs and reads only proven note bodies.
* `domain.notes.mapping_proof(capture, target, read_metadata, work)` constructs
  one exact ordered receiver-checked `NotesProof`. `mapping_inventory` returns
  one immutable `NotesInventory`, with its own terminal or frontier/failure.
* `GitCore.admit_notes_inventory` rechecks evidence and atomically admits the
  whole group and individual roles. `notes_inventories` returns separate checked
  groups. Existing P2 claims/groups preserve original reports and conflicts.
* `application.notes.NotesAcquisition` composes discovery, inventory and individual
  note acquisition. It requires an explicit `source_attribution` and checked
  matching Core/Operational request binding. It is opt-in, with no CLI registration.
* `NotesProgress` stores request-local metadata through WorkLedger checkpointed
  continuation APIs. It stores no blob/structural body staging. The Core proof
  bundle/receiver inventory contains permitted native structural evidence.

Create fresh disposable stores with the existing opt-in P1 initializer, then:

```python
source = GitNotesSource(GitNativeSource(git_path))
ledger = WorkLedger(operational_connection)
request = RequestIdentity(issuer_uuidv4, explicit_request_uuidv4)
ledger.new_request(
    request,
    request_scope(repository_uuidv4, catalog_instance_uuidv4, source_name, source.scope),
    NotesLimits.work_limits(),
)
ledger.attempt(request, genuine_attempt_uuidv4)
work = NotesWorkBudget(ledger, request, genuine_attempt_uuidv4, NotesLimits())
acquisition = NotesAcquisition(
    core, source, work, NotesProgress(work), source_attribution=source_name,
)
discovery = acquisition.discover(
    repository_uuidv4, source_name, issuer_uuidv4, discovery_uuidv4, observed_at_us,
    nominated=("refs/custom/annotations",),
)
# Each present observed ref has its own permanent Capture pair.
capture = discovery.captures[0]
inventory = acquisition.inventory(capture)
result = acquisition.acquire_note(capture, typed_target_oid)
if result.body_retained:
    exact_bytes = core.read_note(capture, typed_target_oid, result.note)
```

Imports follow the module ownership above; this example intentionally omits UUID
issuance and empty-discovery handling. Resume constructs a new budget handle for
the original RequestIdentity/attempt or a genuine new attempt under that same
request. It never calls `new_request` to continue missing accounting. Finite
increases use `ledger.increase_limit`; `NotesLimits(note_bytes=...)` explicitly
sets a finite raw-note bound. A genuinely independent request uses new request
identity. Shared OIDs do not grant reuse. Every delivery is actually checked again.

The request scope binds repository, physical catalog, actual local path/native
format and declared Notes acquisition source intent. A local mirror can check an
external Capture without changing its original unauthenticated `Capture.source`.
External attribution is not authentication. A wrong Operational catalog, request
scope or mismatched progress/budget capability is refused before source I/O or
Core capture/body writes. Original discovery results and copy allocations are
pinned before Core admission, preserving lost-ack replay identities.

## Source/ref observation and completeness

Both native formats and bare/working repositories are supported. Full exact names
(including nested namespaces and reversible non-UTF-8 names) are retained. Every
observable `refs/notes/*` ref is a candidate, with explicit full nominated names
added. Prefix membership never proves a body role. Replacements, repository
selection environment and Git lazy fetching are disabled; actual promisor-object
trace tests verify that missing local input causes no fetch.

Discovery performs two bounded local `for-each-ref` enumerations. Successful EOF,
exit zero and equal name/OID sets establish only a stable double-observation for
that local namespace/nominated scope. A→B→A between observations cannot be detected;
this is not an atomic ref snapshot or continuous-stability guarantee. Detected
movement, timeout, interruption, missing enumeration terminal or budget refusal
cannot produce complete/known-empty. Empty successful double enumeration is
positive known-empty evidence; empty unfinished discovery is unknown. Local absence
never implies remote absence or remote inventory completeness.

Discovery replay uses the same original observation UUID pair and its durably
pinned result; it does not rescan current refs. A genuinely new scan uses a new
observation and fresh Capture UUIDs for present refs, including a repeated root.
Movement, deletion and reappearance preserve historical captures. Incompatible
original repository/source/ref/root or discovery binding is rejected.

Four dimensions remain independent:

| Dimension | Actual evidence |
| --- | --- |
| Local namespace discovery | Original exact ref snapshot, scope, two-scan terminal and state |
| Capture mapping inventory | Whole immutable `all-notes-mappings` group with actual structural closure/frontier |
| One mapping | Exact ordered root/tree/path/target/note `NotesProof` |
| Body | Exact retained physical-copy occurrence and actual typed output checks |

No prior complete observation fills a newer partial observation. Groups are never
unioned into a complete set. Original complete/empty reports remain separate
attributed alternatives; receiver evidence does not rewrite them. Body refusal
can coexist with complete metadata inventory or a verified individual role.

## Native proof and exact bytes

The supported grammar is `p4-notes/1`: native commit→first tree, or direct tree;
flat target-OID leaf, or two-lowercase-hex directory fanout followed by the remaining
full lowercase target suffix. Directories use `40000`, note leaves `100644`.
Ambiguity, wrong path/association, unsupported modes/names/fanout and malformed
native syntax fail explicitly. Each native structure is checked for exact storage
format/type/size/OID/SHA-256 and production parser grammar. Only relevant paths
are needed for a single proof; target bodies, commit ancestry and unrelated
subtrees may be missing. A whole inventory requires every supported reachable
fanout tree, every classified entry, unique targets and exhausted frontier.
Unsupported unrelated entries prevent whole-inventory closure.

`known_empty` requires the same complete terminal proof with zero members.
`partial` contains proved members without terminal; `unknown` has no proved members
and no terminal. Ordered actual native bytes, paths and original capture identity
form direct semantic evidence, not hash-only claim IDs. Inventory proof bytes are
in semantic provenance and follow the protected checked-byte output boundary.
The new opt-in `notes_inventory_guard` SQL trigger verifies actual evidence even
through supported raw coordinator callbacks; malformed incoming intrinsic claims
cannot poison a sound catalog and become corruption only on their next read.

The purpose-bound reader checks a locally valid proof before reading only its
note OID. Native blob type, size and hashes are checked again in receiving Core.
Empty bytes, NUL, non-UTF-8 and CRLF are unchanged. A blob used as both a file and a
real note is retained through that genuine role only. Neither the annotated target
nor a valid unrelated blob receives body permission. No generic blob/CAS upload,
file restoration, checkout, hidden Operational/Context/Search/Exchange archive or
implicit network endpoint is added.

Proof, body and physical-copy evidence commit as one P2 admission unit. Separate
already admitted metadata/roles/groups survive body refusal or transaction failure.
Exact copy replay preserves UUID; actual additional copy occurrence gets its own
UUID. Real Core COMMIT denial and process SIGKILL after body INSERT demonstrate
rollback and identity-preserving replay. These are process/engine fault tests,
not verification of host-power-loss durability.

Actual selected/emitted bytes and stored structural evidence are rechecked.
Persisted native, UTF-8 or deeply nested damaged JSON triggers the persistent
catalog recovery stop before ordinary service can continue. No sibling-copy
failover, clearing or P7 recovery is implemented. Incoming invalid data, missing
objects, resource stops and Operational loss do not diagnose Core corruption.

## Resources and durability

Production defaults are 16 MiB per raw note, 256 MiB request input, 2 GiB hash
verification bytes, 1,000,000 metadata/lookup/relation units and 100,000 proof steps.
Native structures default to 64 MiB each; discovery output to 16 MiB per command,
100,000 records/nominations and a 30-second command deadline. All are finite.
Notes limits and four WorkLedger dimensions are configurable; no implicit unlimited
setting or retry reset exists.

Input counts actual consumed native/discovery bytes; header and Git-operation
attempts cost metadata units even when missing. Hash passes cost consumed body
bytes; parser headers/tree entries and relation processing cost metadata units;
structural read/check attempts cost proof steps. Source delivery, domain checks,
receiving Core and SQL CHECK parsing are distinct performed passes. Core replay
is not free. Adapter setup, SQLite durability/index/checkpoint bookkeeping and
system-wide CPU/disk work are not presented as measured acquisition bytes; these
are bounded coordination overhead, not a benchmark or complete hardware meter.

Reservations commit independently in synchronous FULL/EXTRA WAL Operational
before I/O or verification. Normal measured completion settles actual work. A
failed/uncertain permit retains its full reserved cost; process restart cannot
reconstruct a settlement capability and refund it. Core rollback cannot erase
performed work. Oversize header refusal never charges a fictitious full-body read.

Mandatory Operational checkpoints bind actual work, attempts, finite limits,
allocators and exact progress rows. Partial/whole loss or modification is refused
on live continuation and reopen; missing discovery/copy allocations cannot create
new capture/copy identities. New connections or unrecognized writes revalidate the
actual inventory under a short SQLite fence. The SQL allowance guard uses a
cached `request_budgets.spent_or_reserved` total maintained transactionally by
reservation/settlement/delete triggers; subtraction checks avoid int64 overflow.
This total is independently reconciled with actual rows and checkpoint. Per-step
SQL VM regression checks prevent a hidden growing-history SUM scan. Checkpoints are consistency/loss
checks, not authentication against a privileged actor rewriting all matching data.
Operational can be discarded: retained Core/Context remains authoritative, while
old acquisition requests cannot safely continue from invented zero expenditure.

## Executable acceptance and handoff

The dedicated [P4 production suite](../../tests/integration/p4/) uses actual Git
and fresh SQLite stores. The [receipt](p4-execution-evidence.json) lists every final
selected/executed test node and exact phase reconciliation. Prototype C is rerun
separately as design evidence; it is not counted as production adapter coverage.

| Acceptance family | Production assertions |
| --- | --- |
| Discovery/identity/history | `test_discovery_full_scope_original_pair_and_historical_refs`, `test_ref_movement_new_observation_does_not_modify_old_capture`, `test_discovery_detects_change_and_truncated_enumeration` |
| Real Git/native proof | `test_actual_git_notes_command_and_no_lazy_network`, `test_proof_and_terminal_inventory_real_native_git`, native independent adversaries |
| Exact bytes/replay/copies | `test_exact_role_body_inventory_and_replay`, installed P4 smoke variants |
| Purpose/missing dependencies | `test_missing_targets_unrelated_subtrees_and_file_role`, `test_source_wrong_type_and_wrong_proof_never_reads_arbitrary_blob` |
| Terminal/competing evidence | Inventory suite: empty/unknown/partial, unsupported structure, forged closure, original reports and exact semantic replay |
| Atomicity | Core INSERT/constraint rollback, actual SQLite COMMIT denial, SIGKILL after body INSERT, callback guard matrix |
| Cumulative work/loss | Accounting suite: failed/repeated reads, limits/increases, live permits, lost checkpoints/rows/allocations, actual process and lost-ack cuts |
| Corruption/stop | Persisted byte, UTF-8 and deep JSON damage; persistent stop and no sibling fallback |
| Composition | Wrong catalog/source/budget/progress refusal; actual P4+Context paired read after Operational loss; 20 P2/P3 compatibility cases |

P5 may consume original Capture/NotesClaim/NotesGroup/NotesProof, purpose-bound
source inputs, NotesInventory admission and explicit request/progress interfaces.
It must recheck external inputs and preserve original reports; it owns acquisition
transport/Exchange and cross-store intake. P6 owns public queries, CLI/Search,
paging and derived note text. P7 owns journal-preserving salvage/fresh restore,
validated merge and activation. P8 owns the sole public initializer/runtime switch.
P4 does not declare any of those stages integrated or accepted.

The five inherited Schema 21 fixture failures were reproduced unchanged, not
removed/xfail'd/skipped. They remain listed in the receipt and review report.
Hosted Development CI and final local focused verification are separate evidence;
full hosted runtime/installed Release Acceptance was not requested or claimed.
