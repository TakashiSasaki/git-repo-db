# ADR 0036 I3 Exchange, Query and backup contract

This describes the opt-in P1 I3 integration on top of I2. It does not activate
the ordinary Schema 21 runtime, migrate existing catalogs, establish release
acceptance, or authorize a merge. The fixed I1 and I2 contracts describe those
earlier stages and their then-current fences.

## Exchange

The typed Exchange envelope is `git-repo-db/adr0036-exchange-v6`; it has exact
section and row shapes and a receiver-recomputed SHA-256 digest. This is a
format change from v5, with no implicit old-wire migration. A digest does not
authenticate an issuer. Observations keep their original UUIDv4/UUIDv7 pair,
immutable subject, source/visibility and all selected original result claims.
Ref names and symbolic targets are lossless bytes. Presence, scoped absence,
unknown target, direct, symbolic, resolved, peeled and root values remain
distinct. A changed subject or reused result-evidence coordinate is refused;
independent conflicting reports remain visible as alternatives.

Selection may use explicit observation keys independently of Git object OIDs.
An object-only selection finds observations by an actual selected root and
does not infer rootless matches. Selecting a member by ref can expand the whole
original enumeration and its required member observations. If an object-only
selection cannot include the entire event without adding unrelated members,
the event is omitted as a whole and the omission is reported. Empty events,
whole groups, dependency omissions and bounds must not be converted into a
fictitious complete list. The Core export uses a consistent SQLite snapshot.

Mapping content and original mapping reports retain their complete semantic
coordinates. Export validates the actual selected role proof and each emitted
physical note copy. Imported proof and note bodies are untrusted inputs: the
receiver recomputes the exact Claim/root/structure/body relationship and native
object hashes before admission. The original evidence coordinate is preserved
only after this validation; a separate receiver-local evidence coordinate
records the new check. Repeat, reverse and onward delivery do not rebind a
physical copy or replace an existing observation. Structural proof is not
authority to retain an annotated ordinary file body.

Selection and decoding use finite bounds, reserve before variable-sized reads
and encoding, and charge actual processing across the same Operational receive
request. Limits and incomplete selection are not catalog corruption. Core-only
receive still requires Operational accounting; omitting Context from the wire
does not bypass validation of a coexisting Context store.

Core Exchange uses fixed selectors to measure and charge metadata before
materialization, including historical Coverage Claims and legacy Notes evidence.
Each emitted retained note or structural metadata copy is checked by its own
physical identity.
Stored text decode failures stop the catalog; unrelated SQL or work-callback
failures are not reclassified as corruption.
Context metadata is likewise read under finite reservations and checked before
graph expansion and export; historical Coverage claims and proofs remain bound
to their original stored evidence.

## Query and Coverage

The production Query service exposes typed observation, enumeration, mapping
and claim-specific note-body reads inside its existing pinned snapshot. `auto`
and explicit `core_only` retain their existing store-opening rules. Generic SQL
cannot read the new proof or retained note body columns; typed readers validate
selected bytes and do not lend that capability to caller-supplied budget
callbacks.

Coverage still has five authoritative claim columns and uses the latest
candidate set with existing stale and conflict behavior. For the supported
`notes-mapping-inventory` kind, a typed proof must refer to one exact result
Claim, root and original complete or known-empty Group. The receiver replays
the entire ordered supported commit/tree traversal and compares the resulting
whole group. Separate partial groups, a single-path proof or a sender flag do
not establish inventory completeness. Other ref Coverage kinds without a
supported typed proof remain unknown; a source enumeration report alone is not
receiver-authenticated completeness. Exchange preserves their original Claim
metadata without fabricating an inventory proof, and the receiver retains the
unknown derived state.

## Backup, restore and recovery

Git-only and paired Core/Context backups include the new authoritative rows,
independent proof and eligible retained copies. Before publication or restore,
the adapter checks physical schema, typed subjects/claims/events, all relevant
group and proof dependencies, each selected note copy and its digest, and the
manifest's scope/count/byte and pairing rules. Validation has finite work
limits; exhaustion is a retryable refusal, not evidence of corruption.
Confirmed corruption of the source stops the catalog; a malformed untrusted
backup is rejected without declaring the healthy source corrupt.

Typed salvage of this new family remains fenced and reports partial recovery;
it does not export unvalidated proof or note bodies. Access backup remains a
separate scope, and Operational and Search are reconstructible rather than
authority for admitted Core facts.
