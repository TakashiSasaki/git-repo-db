# ADR 0036 I2 acquisition contract

Current opt-in OID spelling and fresh-format versions follow the
[OID naming contract](object-oid-naming-contract.md). Pinned baseline examples
below retain their historical spelling and do not provide compatibility APIs.

This describes the opt-in P1 acquisition stack after I2; the ordinary Schema 21
runtime is unchanged. The direct parent is I1. I3 Exchange, Query and typed
backup/restore integration remain separate, and neither real-catalog migration
nor release acceptance follows from this implementation.

For the subsequent integration, see [the I3 contract](adr0036-i3-exchange-query-backup-contract.md).

## Original reads and replay

A local `for-each-ref` execution is one enumeration occurrence. Each completed
occurrence receives its own `(observation_origin_uuidv4, enumeration_uuidv7)`;
each reported item receives a fresh `(observation_origin_uuidv4,
ref_observation_uuidv7)` and immutable result Claim. Both UUIDv7 values identify
actual occurrences, not receipt order or observed time. Core atomically stores
the event, its ordered item/absence links and each subject/Claim, with a stored
link count to detect missing or extra authority on bounded reads. A replay with
changed event, membership, subject or Claim is rejected. A repeated physical
scan uses a new event and new item IDs, even if all OIDs are unchanged.

The original request result and issuance are pinned in Operational before Core
admission. Before reading Git, a bounded set of catalog-local advisory lock
stripes serializes read-and-pin for the same request and normalized slot.
An overlapping operation on that stripe receives `ACQUISITION_BUSY` and
may retry; it does not perform a second read and discard its result. The guard
holds no database transaction over Git I/O and releases on process exit or
exception. After a pin, retry and concurrent redelivery use the pinned event and
results, with actual processing charged again. If execution ends before a pin,
the next scan is a new occurrence; Operational loss makes old continuation
unavailable, without invalidating Core facts or resetting a continuing budget.
Operational stores only bounded metadata, not Git object or note bodies. Event
and progress reads reserve variable-width metadata and dependent rows before
materializing them. Exact per-request work remains cumulative through retries.
Replaying an existing event first revalidates its stored event, links and
dependencies under the writer cut within finite configurable bounds. Confirmed
stored damage stops the catalog; a changed incoming event or exhausted budget
alone is an ordinary refusal. Prepared Core lookups charge each operation and
link examined.

The ordinary Git adapter records direct, symbolic, resolved and peeled values
only where `for-each-ref` actually provides them, preserving raw ref bytes. Its
visibility is explicitly the locally resolvable listing: dangling symbolic refs
can be omitted by that command. Notes discovery performs two separate local
scans. Their individual results remain distinct even if they agree or differ;
the operation does not assert an atomic or remote snapshot. The Notes scan
records its observed root but does not invent a direct/symbolic form that its
adapter did not read.

A caller can nominate specific raw ref names for exact local `show-ref --exists`
lookups. A successful exit indicating missing creates a named, source- and
visibility-qualified absence Claim linked to that actual lookup. A present but
unresolved symbolic ref is present with unknown target. Failure, an invalid ref,
partial scans and names not selected do not create absence. Unsupported Git
versions or lookup failures remain failures; no negative result is fabricated.

## Notes and remaining boundaries

An actual whole-root Notes inventory produces a separately attributed immutable
`NotesMappingGroup` for the exact result Claim and its root. Complete and
known-empty groups require exhaustion of the supported local grammar; partial
or unknown groups retain only their own admitted members and are not combined
into completeness. This group is an attributed report, not body authority or a
replacement for a typed Coverage proof.

For a requested target, the receiver reads the relevant commit/tree path and
constructs `NotesMappingEvidence` for the exact Claim, root, interpretation,
path and note OID. The receiver checks those structures before body input and
Core independently verifies the body and proof before retention. A direct tree
needs no invented commit; no target file body is fetched. Metadata-only work can
admit the checked role without retaining a note body. Separate Claims require
separate receiver evidence even when Mapping content is shared. Acquisition
failures, budget exhaustion and malformed incoming data do not establish catalog
corruption; confirmed damage to stored authority invokes the catalog-wide stop.

During this stack the existing Capture/old Notes APIs and their historical
consumers remain transitional; their evidence is never used as authority for a
new Claim. A normal object or Notes acquisition can therefore produce both
legacy facts and new Claim-specific facts until those consumers are reconciled.
The opt-in P1 Core DDL and fingerprint change; existing P1 databases are not
migrated. No empty or nonempty new enumeration may be silently omitted from an
old Exchange package or backup: both retain the I3 refusal fence. Generic
ref-observation Coverage proof remains refused until a typed completeness
verifier exists. No result here asserts remote authenticity or release readiness.
