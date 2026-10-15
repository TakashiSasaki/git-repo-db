# Prototype C: receiver-proven Git notes retention

This executable spike implements **one mapping's** receiver-local structural and
native-body checks. It is isolated in
[`notes.py`](../../tests/integration/architecture_spikes/notes.py) and
[`test_notes.py`](../../tests/integration/architecture_spikes/test_notes.py).
It does not initialize a production catalog, alter packaged DDL, add a CLI
command, migrate data, or claim the four-store product is implemented.

Authority: ADRs 0014–0027, especially 0018/0021 (semantic identity), 0022
(receiver-checked notes role and exact body), 0023–0025 (finite cumulative actual
work), and 0027 (qualified unauthenticated reports). This is an engineering
proof grammar within those decisions, not a replacement ADR.

## Executed behavior

```sh
uv run --no-sync pytest -q tests/integration/architecture_spikes/test_notes.py
uv run --no-sync ruff check tests/integration/architecture_spikes/notes.py tests/integration/architecture_spikes/test_notes.py
uv run --no-sync ruff format --check tests/integration/architecture_spikes/notes.py tests/integration/architecture_spikes/test_notes.py
```

Executed on Git 2.52.0, Python 3.12.14, SQLite 3.53.1: **67 passed**, zero
skipped (latest focused execution: 1.96 seconds). Ruff check and format check
passed. These are development spike tests, not production/release acceptance.
All Git repositories and SQLite files are pytest disposable fixtures. Both
SHA-1 and SHA-256 run every Git-related case; invalid-limit cases add five
unparameterized nodes.

The first 61-node implementation passed. Adding a real loose-object corruption
counterexample initially produced **2 failed, 65 passed**: Git creates loose
objects read-only, so the fixture's direct overwrite raised `PermissionError`
before exercising verification. The fixture now changes permissions only on
that disposable incoming object before deliberately changing its bytes. The
corrected test reaches the independent native-OID check and fails admission for
the intended reason. Subsequent complete focused runs passed all 67 nodes. Independent review then
identified that the object-format negative initially used old-format OID widths,
which reached lexical validation before the adapter-format fence. The corrected
test constructs syntactically valid opposite-format root/target/note identities
and asserts the precise `object-format mismatch` reason; size/digest/type cases
also assert their intended refusal reasons. The complete 67-node rerun passed.

## Boundary and supported grammar

`Capture` preserves the original `(origin UUIDv4, capture UUIDv4)` pair and
immutable repository UUIDv4, source attribution, complete ref name, object
format and captured root. A new real observation uses a new Capture even when
the root repeats. Replays keep the pair. Source/ref/root rebinding fails closed.
No origin authentication, sender-verification authority or PKI is added.

`NotesCore.metadata()` admits only nominal full typed OIDs. `report()` admits
immutable mapping alternatives with original provenance and the explicit
`unauthenticated-report` qualification. Sender `verified` is ignored as local
authority. Report admission does not retain supplied bytes. A later local proof
adds separate evidence while preserving the report and Capture unchanged.

`admit_note()` accepts a local Git input containing the relevant objects. It
never fetches, reads the annotated target, follows commit history, or requires
unrelated descendant objects. It verifies:

1. Captured root is a native, correctly hashed commit or tree. A commit's first
   `tree` header must link to the checked tree. A direct tree needs no fabricated
   commit. Native body length and full typed Git hash are recomputed locally.
2. The tree path encodes exactly the target's full lowercase OID, either flat or
   split into two-hex-digit directory components followed by the remaining
   lowercase hex filename. Only native `40000` directories and `100644` note
   leaves are supported. Ambiguous flat-plus-fanout paths, wrong note OIDs,
   unsupported relevant modes and malformed trees fail closed. Unrelated trees
   may remain unavailable. This intentionally narrow grammar covers the tested
   standard `git notes` output; broader Git-compatible grammars need their own
   tests before expansion.
3. The exact candidate is a native blob of the declared size; its native-format
   Git OID and separate SHA-256 retained-byte digest match actual bytes.
   Correct blob hashing without the relevant mapping never permits retention.

The actual standard `refs/notes/commits` fixture is produced with `git notes
add --allow-empty -C`, and `git notes list` confirms the mapping independently.
Direct-tree and multi-level fanout fixtures use real binary tree objects. A
corrupted loose blob demonstrates that trusting `git cat-file` output without
recomputing the Git hash would be insufficient on the tested Git version.

Only after all checks succeed does one SQLite transaction insert checked
commit/tree representations, the exact note body, its immutable role evidence,
and ordered proof links. An injected interruption after body insertion rolls
the whole unit back. Earlier independently admitted metadata survives; no
unproven bytes are staged in Core or Operational. Empty and binary notes remain
exact bytes. A valid ordinary-file blob is rejected because its required
mapping is absent, rather than merely because its native type is `blob`.

`read_note(Capture, target, note)` requires that exact checked role and immutable
Capture binding, and checks the actual emitted bytes' native hash, size and
SHA-256 digest. There is no general blob-read, file archive, checkout, cache,
Exchange-body, or restoration service. An OID's bytes may be used both as a file
and a legitimate note; only the demonstrated note role grants this API access.
Later ref movement/deletion and lower configured limits do not revoke earlier
admitted facts or bytes.

## Direct identities and enforcement

All spike Core tables are `WITHOUT ROWID`, with direct composite PKs and FKs.
`git_objects` uses `(object_format, full_oid)`; Capture uses its actual two UUIDs.
Reported mappings key directly on Capture, format, target, note, original
provenance and qualification. Role evidence keys directly on Capture, format,
target, note, actual path, the **full ordered structural proof chain** and check
method. The chain is canonical JSON of actual `(OID, native type)` values, not
a hash-only proof key. Ordered proof links carry that full semantic composite
FK and a real traversal ordinal; they reference checked structural objects.
Body FKs include typed OID, exact size and retained-byte digest. No per-proof,
per-claim, per-attempt or local row UUID is invented.

SQLite FKs enforce corresponding references, and recursive UPDATE/DELETE guards
reject mutation including REPLACE of admitted rows. The supported application
API validates UUID/OID semantics, exact representation equality, path grammar,
full proof membership and transaction boundaries. Arbitrary privileged SQLite
writers can drop guards or fabricate locally checked rows; SQLite is not an
adversarial privilege boundary. These are not claims of safety against a client
allowed to replace database schema/files. Corruption detection here raises an
explicit refusal; ADR 0026's complete catalog stop/salvage/restore workflow
remains future production work.

## Finite work experiment

Test-only defaults are 4,096 raw bytes per note, 65,536 aggregate input bytes,
64 attempted structural-object checks, and 256 metadata processing units. They
are **not proposed production defaults**. Every setting must be a positive
finite integer fitting SQLite's integer range; zero, negative, infinity,
fractional values and booleans are rejected. Finite lower settings exercise
resource stops; a deliberate finite increase permits retry without minting a
new Capture or rewriting facts.

`RequestWork` stores mutable counters and effective settings only in a separate
Operational SQLite file, keyed by repository UUID and the caller's explicitly
named acquisition request. Explicit `start` and `resume` are different APIs;
resuming missing counters or a different effective configuration fails closed.
An explicit settings assignment records the new finite settings while leaving
all spent counters intact. Reopening the same request preserves work spent by
a failed attempt. Loss of Operational counters refuses that resume and does not
invalidate admitted Core reads.

The measured units are intentionally separate:

- Input bytes actually read by the receiver from structural/note objects and
  notes-ref discovery. Reads use bounded ephemeral buffers; one extra byte may
  be consumed and charged to detect exhausted input allowance.
- Attempted structural-object checks, including genuine failed lookups, and
  metadata/reference processing units. A missing-object attempt still costs
  lookup work; it produces no false proof.
- Independent raw-note size checked before reading an oversized body.

Every reprocessed delivery is actually read/reverified and charged again even
when semantic insertion deduplicates. The spike implements no safe-reuse
optimization and therefore invents no fictitious second full-body charge.
Core transaction rollback cannot undo already committed Operational work.
Discovery is bounded too; namespace-prefix discovery grants no retention
permission and asserts no full remote inventory completeness.

**Accounting limitation:** actual I/O and its following Operational charge are
not crash-atomic. A process kill in that gap needs conservative pre-reservation
or equivalent production accounting. This spike demonstrates failed attempts,
SQLite rollback and clean reopen accounting, not power-loss-safe exact metering,
concurrent multi-worker reservations, or autonomous restart fencing. The
production acquisition PR must close that gap; this does not require a new
owner policy choice. Git command/header overhead is represented by bounded
metadata/check units rather than presented as a full CPU/I/O benchmark.

## Required counterexamples and assertions

| Required case | Executed assertion(s) |
| --- | --- |
| Ordinary file blob | `test_ordinary_file_metadata_allowed_body_refused`: nominal identity retained; no body; no generic read API |
| Valid notes relationship | `test_standard_git_notes_actual_commit_root_and_exact_binary`: actual Git notes commit/tree/body |
| Empty note | Same standard-Git test, empty bytes parameter |
| Binary note | Same standard-Git test, NUL/non-UTF-8/CRLF parameter |
| Annotated target unavailable | `test_target_not_available_direct_tree_and_unrelated_missing_subtree`: missing target and sibling tree, successful narrow proof |
| Same file/note OID | `test_same_blob_file_and_note_roles_do_not_create_file_service`: single nominal identity; no unrelated-role access |
| Multiple/nested namespaces | `test_namespace_discovery_nested_and_explicit_refs`: all observable nested refs plus explicitly nominated ref |
| Direct tree root | Missing-target test; one tree retained, no commit invented |
| Standard ref/root semantics | Standard-Git test confirms native commit root and `git notes list` association |
| Later ref update/deletion | `test_ref_update_delete_preserves_prior_capture_and_genuine_observations`: historical reads and distinct genuine Capture pairs |
| External unverified/API report | `test_external_sender_verified_report_cannot_authorize_then_later_local_proof`: no body until local proof; report qualification unchanged |
| Malformed path/mode/association | `test_malformed_path_or_unsupported_relevant_mode`, `test_competing_reports_kept_but_only_relevant_proof_authorizes` |
| Correct hash, no attachment | `test_standalone_hash_and_notes_prefix_do_not_prove_attachment`: exact native blob hash does not prove wrong target |
| Resource stop | Individual-note, proof-object, aggregate-byte, metadata and discovery limits; failed units never retain bodies |
| Replay/later proof | Exact report/proof replay preserves counts and pair, spent work increases; later proof appends evidence without rewriting report |

Additional tests cover actual corrupted incoming native bytes, supplied
size/digest/type/format mismatch, atomic SQL interruption after body insertion,
Capture rebinding on admission/output, missing Operational accounting, all
mutation guards, two-level fanout, and invalid/unbounded settings.

## Implementation handoff

Reuse candidates are typed Capture validation, the pure native tree-path
parser, and the role-scoped admission contract after independent review.
Consolidate them into the product Git domain during the planned notes/proof
implementation PR, rather than importing a tests package from production.
Production work still needs complete supported grammar/wire encoding,
streaming native-object adapters, durable conservative request accounting,
receiver-local evidence isolation across Exchange, physical-instance integrity
and ADR 0026 recovery integration. Integrate only after Core semantic-key and
atomic-admission interfaces are fixed. Broader complete/partial inventory
assertions, source authenticity, paired backup and whole-product readiness are
not demonstrated by this one-mapping proof.
