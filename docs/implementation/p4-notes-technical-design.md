# P4 production Notes technical contract

Status: proposed engineering specification under accepted ADRs 0001, 0003 and
0014–0027. Owner architectural blockers: zero. This document does not assert owner
approval, implemented behavior, release acceptance or a public runtime switch.

## Dependency and ownership

Baseline independently fetched on 2026-10-16: main
`5e778bf61ef660f65bf5fb22bdb08840503b8464`, tree
`2c6eca80e6432a1b4f89a2111e7ded69c6b9a507`; no open PRs. Main Development CI
run 38823843606 succeeded; complete hosted runtime acceptance was not run.
P2/P3 are integrated. The old checkout was preserved in its original worktree.
The implementation PR targets this design branch; neither PR is to be merged
by the implementing agent. P4 depends on P2. P5/P6 consume P4 after integration;
P7 recovery and P8 public activation remain separate.

Production ownership:

* `domain/notes.py`: bounded proof traversal, mapping inventory and terminal
  grammar, immutable values and typed diagnostics. It uses the production
  `git_native` decoder and P1 OID/Capture/NotesProof/NotesGroup types.
* `adapters/git/native.py` and `adapters/git/notes.py`: bounded local native input,
  purpose-bound note reader, namespace enumeration. No network operations.
* `adapters/sqlite/git_core.py`: receiver-checked inventory admission/read using
  existing whole `notes_groups` and semantic provenance; P2 role/body admission
  remains the atomic authority. No new arbitrary SQL write or blob endpoint.
* `application/notes.py`: opt-in orchestration, explicit discovery observation,
  genuine capture issuance, original-pair replay, progress and scoped outcomes.
* `p1_coordination.py` domain/SQLite adapters: existing durable WorkLedger and
  NotesWorkBudget, request binding and measured pre-reservations.
* `tests/integration/p4/`: disposable real Git and SQLite acceptance; packaging
  tests exercise installed artifacts outside checkout. Documentation/status and
  verified procedural lessons are updated after executable validation.

Core physical schema changes are not planned: existing semantic groups and
GitObservation support the required values. If execution demonstrates a schema
necessity, regenerate fingerprints and reconcile every disposition explicitly.
P3 Context contracts and the public Schema 21 initializer are unchanged.

## Local source and observation boundary

GitNativeSource identifies one explicit bare or working-tree repository and
storage format (SHA-1 or SHA-256), disables replacement objects and lazy fetching,
and ignores ambient repository-selection environment. P4 observes all local refs
under `refs/notes/`, recursively, plus explicitly nominated full ref names. Exact
ref bytes use reversible UTF-8/surrogateescape at the API and existing native-ref
hex encoding in Core. A nominated missing ref is represented by positive local
scan evidence, never by a fabricated root/capture. Full source attribution is
caller-supplied and retained; it is not authentication.

Enumeration uses a bounded streaming command with a deadline and finite output
and record limits. Every consumed output byte and processed record is charged.
A successful EOF and exit code zero establish completeness only of the command's
local enumeration scope, at that enumeration. A second bounded enumeration
compares the exact name/OID set. Equality gives a stable double-observation,
not an atomic ref database snapshot: an undetectable A→B→A movement is outside
this guarantee. Any detected difference, failure, timeout or budget stop withholds
terminal stable evidence. No assertion of continuously unchanged refs, remote
inventory, remote absence or freshness is made. Ref movement after either scan
never changes an admitted capture or invalidates proof relative to its pinned OID.

The immutable discovery evidence is a typed GitObservation snapshot: original
observation UUIDv4 pair, repository/source, timestamp in signed int64 epoch
microseconds, nominated scope, exact refs, state and terminal evidence. This is
an observation of Git data, not a generic success ledger. Partial results remain
partial; an empty unfinished scan is unknown. Known-empty requires both successful
terminal scans with no matching refs. A later partial observation cannot borrow
an earlier terminal. Original discovery evidence can be replayed unchanged.

Each genuinely observed present ref issues a new Capture UUIDv4 under the genuine
issuer UUIDv4, even if its root matches a prior observation. Retries accept and
retain the original Capture pair and pinned root; they do not rediscover/rebind
that capture or mint one. Root/ref/repository/source disagreement fails
`INCOMPATIBLE_REPLAY`. Disappearance issues no fictitious present capture;
reappearance is a new genuine observation. Discovery alone grants no byte role.

## Structural proof grammar

Version `p4-notes/1` supports a native commit root followed by its first tree,
or a direct native tree root, without a fabricated commit. Native structures
are validated for format, exact bytes, size, typed OID, SHA-256 and the full
production commit/tree grammar. Commit history and annotated target bodies are
never read. Sibling descendant objects need not be available for a single mapping.

A mapping path concatenates to the full lowercase target OID. It is either one
flat filename or zero or more directories of exactly two lowercase hexadecimal
characters followed by the remaining lowercase hexadecimal filename. Directories
have native mode `40000`; leaves have mode `100644`. Empty path components,
uppercase, odd or alternate fanout, symlink/executable/gitlink note leaves,
ambiguous flat plus fanout for the same target, wrong association and extraneous
proof links are refused. A valid native non-note entry can remain unrelated for
a narrow mapping proof, but prevents whole-inventory terminal closure. No
unsupported entry is silently interpreted as a note or silently omitted from a
complete inventory. Additional grammar requires actual Git fixtures and review.

NotesProof preserves Capture, typed target and note OIDs, actual slash path and
the full ordered native structural chain. Its existing direct composite semantic
key includes the exact proof bundle, not a hash-only identity. Native validation
is repeated at the receiving Core boundary, independent of source callbacks or
sender flags. A source mapping report remains reported; proof adds separate
receiver-intrinsic evidence and never authenticates issuer/ref freshness.

## Exact body authorization and transactions

A purpose-bound native reader requires a locally validated NotesProof before
reading a blob. It accepts only the proof's note OID in the same native storage
format; checks type and declared size before bounded input; preserves empty,
NUL, binary, non-UTF-8 and CRLF bytes; computes SHA-256 and typed Git hash over
actual bytes. Ordinary metadata reading continues to refuse blobs. An OID used
as both a file and a genuine note is allowed only through the proven note role.
There is no generic CAS upload, arbitrary file read, checkout or restore API.

Core rechecks and atomically admits proof, exact body and physical-copy occurrence
using P2 `admit_note`. Interrupted or failed BEGIN/INSERT/constraint/COMMIT rolls
back that whole unit; independently committed captures, reports and whole groups
survive. Physical-copy UUIDv4 denotes a genuine copy occurrence; callers preserve
it for exact lost-ack replay and supply a new one only for a genuine new copy.
Identical replay is idempotent but actual repeated processing costs work again.
The implementation does not implement a shared-OID safe-reuse optimization.

Selected/emitted body bytes are rechecked through `GitCore.read_note`; generic
SQL cannot expose protected payloads. Authoritative byte/role damage publishes
the existing persistent catalog stop and never tries a sibling copy after the
fault. Existing stop blocks P4 before further acquisition. Missing incoming
objects, invalid proof, budget refusal, input errors and metadata competition
are domain failures, not catalog corruption. P4 does not clear stops or recover.

## Four independent evidence dimensions

1. Discovery state belongs to the exact local enumeration observation/scope.
2. Mapping inventory state belongs to the exact Capture/root and whole immutable
   `all-notes-mappings` group; reports and local terminal evidence are distinct.
3. Individual mapping structure is proven only by its actual NotesProof.
4. Body availability/verification belongs to the actual retained physical copy
   and the typed checked read; no inventory state promises healthy retained bytes.

Inventory traversal is deterministic depth-first native tree order. A complete
terminal requires the root plus every reachable supported fanout tree to be read
and validated, every entry classified under the grammar, all target slots unique,
and no remaining traversal frontier. Targets and note bodies are not closure
dependencies. `known_empty` requires this same terminal proof with zero mappings.
`partial` contains only actually proved mappings and no terminal; `unknown` has
no proved mappings and no terminal. Missing subtree, unsupported entry, limit or
interruption cannot create a terminal. Successful single-mapping proof does not
prove inventory. A body refusal does not retract admissible inventory metadata.

A receiver inventory admission takes actual native structural evidence and
recomputes the group membership/closure, rather than accepting a `verified` or
`terminal` boolean. The complete structural value and terminal grammar are stored
in direct semantic provenance coordinates of the immutable NotesGroup. A typed
reader exposes each separate group and its checked scope and revalidates retained
local terminal evidence. It does not union fragments, choose a latest group or
inherit evidence across captures. External complete/empty reports remain distinct
reported alternatives; receiver evidence never rewrites them. The existing notes
projection continues to expose contradictory same-slot claims and independent
receiver roles. Unknown and partial remain valid without Context or body storage.

## Resource protocol and production defaults

All values are finite configurable signed int64 quantities. Proposed defaults:
16 MiB raw bytes per note; 256 MiB cumulative input; 2 GiB cumulative verification
bytes; 1,000,000 metadata/relation/lookup units; 100,000 structural proof steps;
64 MiB per structural object; 16 MiB per discovery command output; 100,000 refs;
30-second command deadlines. These are engineering defaults, not owner decisions.
The four WorkLedger work kinds remain input_bytes, verification_bytes,
metadata_units and proof_steps. Discovery bytes count as input; processed refs,
headers, tree entries, queries and relation work count metadata units; attempted
structural reads/checks count proof steps; each actual hash pass counts the bytes
it consumes. Parser and SQLite CHECK work are charged through existing
account_verification instrumentation. Reading, decoding and Core verification
are distinct real processing; the implementation documents each charge point.

One explicit RequestIdentity owns all attempts/continuations. Starting and
resuming are separate operations. Scope binds repository/catalog/source and
original acquisition intent. Missing request, budgets, attempt, wrong store or
scope mismatch refuses continuation; it never starts from zero automatically.
Explicit new requests have independent finite allowances. Explicit finite budget
increases preserve earlier expenditures. Per-note bounds may be explicitly raised
without deleting earlier immutable facts. Operational stores no body staging.

Before external I/O or hash/parser work, reserve a conservative finite upper bound
in the separately committed Operational database. After completion settle only
measured work. Core rollback cannot roll back reservations. Exceptions and process
termination leave unsettled reservations charged at their full bound; retries
create new processing coordinates and charge again. No resume refunds a potentially
performed permit. Read loops reserve before each bounded chunk; oversize header
refusal does not charge a hypothetical full body. Hash/metadata instruments reserve
before performing work. An early charge of its exact reserved amount is conservative
prepayment, not post-work accounting. Settlements must not permit forged or repeated
refunds. Existing autocommit, FULL/EXTRA synchronous SQLite coordination settings
are required. Tests prove process-kill/reopen behavior; host-power-loss durability
is not claimed by simulated interruption. Lost Operational never invalidates Core.

## Diagnostics and public boundary

The opt-in application accepts production GitCore, local Git source, explicit
request/work budget and caller provenance; it has no implicit public initializer,
CLI registration, Context or network dependency. Typed outcomes retain the smallest
scope: source/namespace, Capture/root, target/path, note/physical copy or request.
Codes include `GIT_INPUT`, `OBJECT_UNAVAILABLE`, `NATIVE_FORMAT`,
`NATIVE_SYNTAX`, `NATIVE_INTEGRITY`, `NOTES_ROLE`, `NOTES_BODY`,
`NOTES_INVENTORY`, `REF_CHANGED`, `BUDGET`, `INCOMPATIBLE_REPLAY`,
`CONTINUATION_UNAVAILABLE`, `ACCOUNTING_TRANSACTION` and existing catalog stop
codes. Unexpected SQLite failures propagate; only genuine authoritative engine
corruption/I/O and retained-data integrity failures use existing stop policy.
No broad exception handler labels every failure corruption or completeness.

## Adversarial acceptance matrix

All rows require production adapters, real disposable Git/SQLite and both native
formats where relevant. Prototypes are rerun separately, never counted as P4 proof.

| Family | Required observable assertion |
| --- | --- |
| Namespace/ref scope | Nested and nominated refs, exact source/name, bare/worktree, no fetch |
| Identity/history | Fresh observations distinct, original replay stable, movement/deletion/return preserves old facts |
| Narrow proof | Commit/direct tree, flat/two-hex fanout, missing target/sibling accepted, no invented commit |
| Malicious inputs | Wrong OID/type/format/size/digest/mode/name/path/association cannot retain body |
| Purpose | File-only blob refused; same file/note OID allowed only for actual note role |
| Exact bytes | Empty, binary, NUL, non-UTF-8, CRLF round-trip byte equality |
| Competing evidence | Independent reports persist; sender verification insufficient; exact local scope separate |
| Terminal inventory | Unknown/partial/known-empty/complete distinct; missing/unsupported/changing/interrupted scope never closes |
| Atomicity | Core INSERT, constraint, COMMIT and interruption leave no partial body/group; old metadata survives |
| Replay/copies | Exact unit replay deduplicates, actual new copy distinct, repeated work charged |
| Finite bounds | Per-note/input/verification/metadata/proof/discovery refusal is scoped, no fictitious body charge |
| Durable accounting | Retry/resume cumulatively bounded, explicit increase, killed unsettled permits retained, lost Operational refuses old request |
| Corruption | Actual retained-byte damage persists catalog stop, no sibling failover, old stop blocks acquisition |
| Installation | Wheel and wheel-from-sdist import/functional P4 smoke outside checkout; installed DDL matches |
| Regression | P1/P2/P3 and 20 compatibility cases; known five legacy fixture failures separately reproduced |

Independent read-only reviewers inspect Git proof/input, immutable database
contracts, resource/failure paths and complete stacked integration separately.
Material findings require executable reproduction, correction, regression and
revalidation at exact corrected SHA/tree. Local agent reviews are not GitHub
approvals. Final evidence records actual selected/executed nodes and outcomes,
packaging, Ruff, four audits and hosted Development CI separately. Full Release
Acceptance is outside scope. No tests are skipped/xfail'd to conceal a failure.


## Executable implementation refinements — 2026-10-16

Independent counterexamples required two focused opt-in DDL refinements: a
`notes_inventory_guard` trigger locally validates actual receiver-intrinsic
inventory evidence through supported coordinator SQL, and Operational
`request_budgets.spent_or_reserved` maintains finite conservative expenditure
without scanning all earlier work for every reservation. These are receiving
checks and resource mechanics under accepted ADRs, not new owner decisions.
No table or domain key is added; the single new mutable column belongs only to
Operational. Core remains INSERT-only. Generated schema fingerprints and authored
physical disposition evidence are reconciled; public Schema 21 is unchanged.

WorkLedger mandatory loss-detecting checkpoints cover actual work, budgets,
attempts, allocator and progress rows. NotesProgress accesses them only through
`get_progress` / `set_progress_once`. App composition requires actual matching
Core/Operational repository/catalog identity and `request_scope` for the selected
local path, object format and Notes source intent. An externally attributed
Capture keeps its original source when the receiver checks it from a local mirror.

Typed inventory readers use trusted stored-value decoding for UTF-8 and nested
JSON errors before publishing output, and supported raw callbacks cannot claim
intrinsic inventory without its real native evidence. The
[production handoff](p4-production-notes.md) and [execution receipt](p4-execution-evidence.json)
record final executable interfaces, limits, reviewed corrections and test evidence.
