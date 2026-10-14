# ADR 0004: Mandatory metadata-only Git Core

- **Status:** Accepted owner requirement; detailed storage design and implementation pending.
- **Decision date:** 2026-10-14.
- **Decision ID:** GCTX-M01.
- **Owner selection:** Option B: Git Core alone must catalog commit, parent, tree and blob attributes and relationships even when no raw Git object bytes are available.
- **Design baseline:** ADR 0003 in PR #44, commit `2dc0e438c3d029866b847f4e3404a3b7dbaa2b26`, tree `181ab8ef9b1239f1e95e8a6ce61f43d8e46b1840`. The implemented baseline remains Three-Store Core Schema 21 / Operational Schema 1 / Search Schema 1.
- **Predecessor:** [ADR 0003](0003-append-only-git-core-and-context-store.md), narrowly superseded as specified below.
- **Implementation planning:** [Git Core / Context transition plan](../architecture/git-core-context-transition-plan.md).
- **Subsequent identity decision:** [ADR 0005 / GCTX-M02](0005-common-oid-identity-with-attributed-metadata.md) selects one common nominal identity keyed by `(object_format, oid)` with separate attributed metadata.
- **Subsequent recording-granularity decision:** [ADR 0006 / GCTX-M03](0006-field-claims-and-observation-scoped-relations.md) selects per-field attributed scalar claims and observation-scoped, typed relationship groups. Physical schema and conflict-read policy remain open.

## 1. Binding requirement, not an optional optimization

A useful metadata-only Git catalog is a first-class supported mode, not an error, a temporary intake state, an Operational cache, or a Context-only substitute for Git Core.

Git Core MUST support recording, ordinary querying, traversing and exchanging the supplied commit, parent, tree and blob attributes and relationships, and backing up/restoring that catalog, without requiring:

- any retained or newly fetched canonical commit, tree, blob or tag payload;
- prior local OID rehash verification of those objects;
- a Context database or Context-owned row needed to interpret the Git metadata;
- a working remote, cached clone or an implicit fetch when metadata is read.

An importer must be able to consume supplied metadata without requesting raw object bodies. This does not claim that an external producer can discover unknown attributes without a source: a local Git command or remote service may read its own object database to produce the metadata. The receiving catalog must not require possession or reconstruction of those raw bodies.

The requirement is stronger than omitting blobs while retaining commit/tree bodies, and stronger than merely accepting dangling OIDs in ref observations. Complete raw headers, message bytes, tree entry offsets and reconstructible object serialization MUST NOT become disguised mandatory payloads. Individually supplied metadata values, including a message or a byte-preserving name, may still be retained as attributes; they do not certify the complete original object.

Unknown attributes remain unknown. This requirement does not authorize manufacturing object types, sizes, parents, names, offsets, digests or timestamps to satisfy the old schema. The handling of annotated tags must be audited consistently; their detailed attribute contract is not separately selected here.

## 2. What the Core is authoritative about

Git Core may be authoritative that a particular Git metadata value or relationship was supplied/observed with particular provenance. That is not automatically cryptographic proof that the value equals the intrinsic content of the claimed OID.

Keep these propositions distinct:

1. A full, typed OID was supplied or observed.
2. A source reported attributes or relationships about that OID.
3. Exact bytes were checked against a declared format, OID, type and size.
4. A particular metadata assertion was checked against those bytes.
5. Required bytes are retained and currently usable.
6. The required membership/graph scope is complete under its actual contract.

None of these states may silently substitute for another. In particular, successful OID verification of one supplied body does not validate every earlier assertion associated with the same OID. A receiver must not promote a sender's verification claim into receiver-local verification.

This is not permission to accept malformed representations or invent evidence. Structural admission checks that do not require object bytes remain necessary, including supported object-format and full-OID shape, value types/ranges, known-versus-unknown distinctions, provenance and relationship scope. Abbreviated OIDs must not be silently padded into full identities. Exact validation rules, conflict representation and schema constraints remain detailed design work.

The catalog must expose unverified metadata through its normal metadata interface with truthful qualification, rather than hiding it behind the old verified-payload availability gate. Operations that actually require file bytes, canonical object export or verified closure must separately report unavailable/unverified inputs instead of claiming success.

## 3. Append-only remains binding

No application-level UPDATE, DELETE, REPLACE, mutation-enabled repair or GC of admitted Git Core facts is authorized.

When later information becomes available, preserve the original observation/assertion and add the new information without rewriting what was previously reported. Metadata-only admission must not permanently reserve a false type/size/parent as the sole immutable truth of an OID and thereby prevent later correct evidence from being retained.

For example, source S1 reports that commit C has parent P. Later bytes for C match its OID but contain parent Q. Preserve the S1 assertion as S1's assertion; do not overwrite it, declare P byte-verified, or reject the correct bytes solely because P was recorded first. The exact representation of the discrepancy and the normal read policy require a subsequent scoped decision. Receipt time, source popularity and parser version are not implicitly selected as winners.

A nominal OID reference is not a fabricated verified object. Where optional bytes are admitted as a verified representation, the existing exact byte/type/size/OID validation and atomic installation of that representation's intrinsic structure still apply. A metadata-only import is not required to create that representation.

## 4. Git Core / Context boundary

Git object attributes and relationships necessary for this requirement belong to the Git metadata domain even when not independently byte-verified. Lack of verification alone MUST NOT force them into Context.

Required minimal provenance for Core metadata must stand without a live Context row. Provider configuration, credentials, Source registrations, PR/Issue/review state, PR-to-Git associations and Provider text remain Context responsibilities. A provider may supply a modeled Git assertion without its entire API response, full provider state or PR history becoming Core data. Exact detached provenance fields and attribution contracts are not fixed here.

The owner's preceding suggestion to locate verification in Context remains a design topic. Selecting GCTX-M01 does **not** by itself select the physical owner of verification results, move required raw Git bytes into Context, or require a fifth store. Separate the executable verification service, durable evidence, current interpretation and byte-admission checks before choosing that boundary. Whatever is selected, metadata-only Core operation must remain Context-independent and optional byte-integrity guarantees must not be weakened.

Operational may own verification jobs/retries; Search may hold rebuildable derivatives. Neither may become the sole authority for accepted metadata or required evidence.

## 5. Precise supersession and preserved decisions

| Earlier rule or assumption | Effect of GCTX-M01 |
| --- | --- |
| ADR 0003 requires verification and raw bytes before any Git object is accepted into Core | Superseded for metadata admission. Keep strict checks when claiming a byte-verified representation |
| Only byte-derived intrinsic attributes/relations may participate in Core Git catalog queries | Superseded as a universal restriction. Supplied Git attributes and relations must also be usable, clearly distinguished from byte-validated structure |
| Unverified metadata can only be a ref/dangling OID, Context record or intake staging | Insufficient; the Core must support the richer metadata-only object/relationship catalog |
| `git_objects.verified` can be removed because every cataloged object is verified | That rationale is withdrawn. Column removal, retention or replacement is unresolved; no mutable Core flag is authorized |
| `available_git_objects` and payload closure are prerequisites for every Git query/export | Must be split by the guarantee requested: metadata availability versus byte/verified-closure availability |
| Transition-plan negative gate says no unverified object acceptance | Replace with no **false claim** of byte verification; metadata-only admission is required |
| A missing raw body always denotes failed acquisition or CAS corruption | Inapplicable to intentionally absent metadata-only payloads. Actual loss/corruption of previously retained bytes remains an integrity issue |
| An immutable OID row's type/size/parent can never conflict because all inputs are checked bytes | No longer a valid universal assumption; identity, reported attributes and verified evidence need separate treatment |

Preserved: four-store separation; Git Core append-only and Context nondependency; repository UUIDv4 permanence; Q01-B/Q02-B/Q03-B; NO_INDEPENDENT_PUBLICATION; unaffected PF-P01-PF-P17; Source known-positive relationships; Unix epoch microseconds and `_us`; truthful Coverage and its existing five-column/latest-observation semantics; strict verification whenever verification is claimed; CAS integrity, collision handling and CAS-41 for retained bytes; required-byte retention/no Git Core GC; paired full-catalog backup; ADR 0001 development/release validation.

Choosing not to acquire bytes is not authorization to delete previously admitted bytes. Metadata absence must not conceal corruption. Metadata statements that disagree are not automatically hash collisions. A backup complete for a metadata-only catalog is not a recoverable complete Git repository; backup/export manifests and user-facing guarantees must distinguish those scopes without weakening prior physical-integrity checks.

No new universal certificate, Publication replacement, generic event store, blanket API edit history or winner-selection policy is authorized.

## 6. Impact audit required before implementation

The earlier 70-table disposition audit is a baseline inventory, not approval of its verified-only assumptions. Re-audit all affected tables, columns, FKs, views, triggers, writers, readers, validators, Exchange keys and backup/search dependencies.

| Area | Required design work |
| --- | --- |
| Identity and attributes | Separate a nominal format/OID key from unknown, source-reported, contradictory and byte-validated attributes; decide table structure later |
| Commits and parents | Make raw headers/messages/byte offsets unnecessary for metadata admission; preserve parent ordering, partial-list boundaries and provenance without combining unrelated observations into a fictitious parent list |
| Trees and blobs | Allow supplied names/modes/child OIDs and blob attributes without bodies; do not require blob content CAS identities or hashes that were never obtained; keep gitlink semantics distinct |
| Acquisitions and refs | Distinguish metadata observation from actual raw-object acquisition and repository membership evidence; do not retroactively claim bytes were fetched |
| Verification | Separate object-byte identity checks, assertion conformance, structural checks, physical health and graph completeness; choose service/evidence placement explicitly |
| Completion and Coverage | Distinguish metadata-scope completion, byte possession and verified closure. Existing complete claims must not be relabeled to satisfy a weaker scope; exact new scope contracts remain open |
| Queries and Search | Normal metadata traversal/search must not disappear due to missing payloads or Context; expose unverified/conflicting/unknown qualification and retain truthful direct-scan fallback |
| Exchange | Round-trip metadata-only data, provenance and alternatives without sender-verification laundering, fake payloads or mandatory byte promotion; preserve later/reverse/repeat delivery semantics |
| CAS and recovery | Optional raw-object admission still uses exact validation and append-only-safe recovery; no quarantine diagnosis for intentional nonacquisition; preserve CAS-41 for actual stored bytes |
| Backup and restore | A Core-only metadata backup must restore useful metadata without fetching bytes or creating Context; paired backup is still required when Context data is included |
| CLI and validation | Separate catalog validity from byte-backed repository restorability. A clean metadata-only catalog must not be treated as generally invalid just because rehashing is impossible |

## 7. Required counterexamples and acceptance criteria

These are requirements for subsequent implementation tests, **not tests executed by this design PR**.

1. Initialize a catalog with no Context file and no raw object payloads. Import supplied commit/parent/tree/blob metadata. Normal identity/attribute/ancestry/tree-path queries return those values with unverified qualification.
2. Make raw-body retrieval fail if called. Metadata import and normal metadata reads still succeed. No placeholder raw body, fake digest, reconstructed canonical object, hidden clone or mandatory Context registration is created.
3. Exercise unknown type/size, unknown versus known-empty parent/entry lists, partial/out-of-order input and gitlinks. No dummy zero/empty value converts unknown information into an asserted fact.
4. Receive different type/size/parent/entry reports for the same nominal OID. Neither arbitrary arrival order nor forced uniqueness may silently overwrite evidence or block later correct byte admission. Do not union unrelated parent lists or tree inventories as one verified structure.
5. Subsequently acquire bytes that match the OID but disagree with an earlier metadata assertion. Preserve the original assertion and qualify the discrepancy; do not update the old Core row or mark all OID-associated assertions verified.
6. Delete/recreate disposable Operational/Search stores and omit Context. Metadata remains usable; missing/stale Search falls back to Core metadata, not a byte-required view.
7. Metadata-only Exchange and backup/restore round-trip all required values and provenance offline. The result must not claim raw Git export, checkout capability or byte-verified closure that is absent.
8. Separately exercise the existing strict raw-byte checks, collision handling, physical corruption, CAS-41, append-only-safe recovery and paired Context backup. Optional byte acquisition does not authorize weaker checks or silent loss.

## 8. Still unresolved; do not infer owner approval

Physical table names/counts and DDL; whether `git_objects` implements the common nominal registry chosen by GCTX-M02 or a separate table is introduced; exact typed assertion/provenance representation; conflict-read policy; grouping of partial relationship observations; verification service/result location (including the Context proposal); detailed completion scopes; append-only physical repair and revision/fence protocols; Exchange wire versions; cross-store transaction and backup algorithms; GC-03/GC-04.

The next design decisions should address nominal identity versus attributed metadata and conflicting observations before fixing late-FK resolution or deleting `verified`. A conceptual registry/assertions/optional-proof separation is a candidate, not an approved DDL or generic proof system.

## 9. Development workflow and limits

This ADR is stacked on the unmerged ADR 0003 design PR; it does not merge or amend that base branch. Downstream design and implementation must use the combined decisions, with this ADR taking precedence only within its supersession scope. Existing active handoffs and the Phase 2 status documents must be interpreted with this scoped override; their implemented-schema descriptions remain historical/current implementation evidence, not metadata-only acceptance.

No production code, DDL, migrations, schema-version labels, website publication allowlists, live catalogs, credentials or runtime behavior are changed. No release, deployment, data deletion or merge is authorized. Implement only after the necessary detailed design choices are fixed, using stacked PRs and independent review where appropriate. Apply ADR 0001; do not claim runtime acceptance from a documentation-only check.
