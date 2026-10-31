# ADR 0036 I1 Core contract and stack boundary

Current opt-in OID spelling and fresh-format versions follow the
[OID naming contract](object-oid-naming-contract.md). Pinned baseline examples
below retain their historical spelling and do not provide compatibility APIs.

This is the I1 implementation contract on the accepted ADR 0036 design. It
covers the opt-in P1 Core only. It does not activate normal Schema 21, perform
catalog conversion, or claim I2 acquisition/enumeration or I3 Exchange/backup
integration. The actual acceptance and integration status follow the PR and
its exact review/validation evidence.

For the subsequent acquisition implementation and remaining I3/coverage
limits, see [the I2 acquisition contract](adr0036-i2-acquisition-contract.md).
For the later candidate integration, see [the I3 contract](adr0036-i3-exchange-query-backup-contract.md).

## Observation, result and original report

`RefObservationKey` is directly the canonical `(observation_origin_uuidv4,
ref_observation_uuidv7)` pair. `RefObservation` fixes repository, lossless raw
ref bytes, source attribution, visibility and optional observed time. A reused
pair with changed subject fails. Each `RefObservationClaim` is an immutable,
source-attributed report; equality uses its entire result and provenance. The
source/observation/coordinate identifies the original report, so changing only
a decoder label cannot rebind that coordinate. Independently attributable known
target or comparable present/confirmed-absent claims coexist and project an
explicit conflict; an unknown target followed by a known target is not itself a
conflict. No ordering, UUID time, received-at time or sender flag chooses truth.

`RefAbsenceEvidence` records a named ref, actual reported source/visibility,
completed lookup or completed bounded enumeration, and a completion coordinate.
It is an unauthenticated source-qualified report, not proof of remote
identity. I1 requires a complete enumeration to cover the exact name and refuses
failure, partial status or subject mismatch. I2 must provide the actual
`RefEnumerationObservation` event identity, explicit member/absence links and
durable issuance/retry semantics; the I1 completion coordinate is not a
substitute for those event links.

## Shared interpretation and receiver proof

`NotesMapping` contains a typed root, interpretation contract/scope, annotated
object, note OID and actual optional path. Equal full content can be shared
across independently observed keys. `NotesMappingClaim` and
`NotesMappingGroup` retain the original result claim, provenance, immutable
scope, whole membership and value. A group is visible atomically, and unrelated
partial groups are never unioned into a complete inventory.

`NotesMappingEvidence` is receiver-local evidence for the exact immutable
result claim and its typed root. In I1 the one supported checked grammar is
`git-notes` version `1`, decoder `native-notes` version `1`, and verification
scope `single-path`; arbitrary reported interpretation labels remain metadata
only. The actual root/tree/target/note path is rechecked on admission and the
SQLite constraint independently checks the same proof. The same checked unit
is also `NotesRoleEvidence`; this is a semantic role, not a new surrogate. A
note body is admitted only with that exact claim-specific evidence plus its own
native blob, size, OID and SHA-256 validation. Receiver proof reads are charged
to the supplied work budget; exhaustion is not corruption. An actual stored
proof or body integrity failure enters the catalog-wide stop path. Mapping
and ref-result projection also have explicit finite row and byte limits. Each reserves its scan
before work, rejects an over-limit result rather than returning a partial one,
and charges text before materializing it. Callers can set smaller limits to fit
their remaining durable work budget.

`read_ref_note` requires a `WorkBudget`. It uses the role lookup index to pick
one eligible physical copy, checks finite body, proof and metadata limits, and
reserves all variable-width columns before fetching a row. Dependent Claim and
observation rows are separately bounded and charged on every actual fetch.
Caller metadata and encoded provenance, paths and proof bundles are bounded
before their corresponding materialization. Local proof/body verification and
retries consume work again.
Budget exhaustion is not corruption and cannot return an unverified body.

An admission replay checks any existing same-key copy's bytes, digest, original
claim and role evidence under the writer cut before insertion. It compares the
full supplied Claim with its immutable original even for an exact-copy replay.
A discovered conflicting copy is diagnosed across both new and transitional
legacy note tables under the same cut with finite copy, proof and metadata
bounds. Legacy evidence can diagnose its own stored copy but does not authorize
a new Claim. A new-copy insertion first bounds existing-copy comparisons and
reserves their byte cost before the SQL representation guards run; an exact
replay avoids that insertion. A proven invalid stored unit stops the catalog; an unrelated
constraint error, incompatible replay or exhausted diagnostic budget does not
itself establish corruption. No failure repairs or overwrites the old copy.

## Coverage and transitional fences

Coverage retains its five claim columns and existing latest/stale/conflict
rules; `ref_observation` adds the new exact owner pair. I1 has no typed complete
ref-enumeration verifier: generic OID membership cannot establish a complete
ref-observation scope, so ref-observation Coverage proof insertion is refused
until I2 supplies the necessary typed evidence. A complete claim without that
proof projects unknown rather than borrowing an older complete state.

The existing Capture and old Notes tables/API remain as explicitly transitional
I1-stack code so acquisition and Exchange work can be reviewed in their proper
I2/I3 stages. They do not establish authority for new result Claims or new role
proofs. They must be retired or fully reconciled when their consumers are moved;
no old UUIDv4 observation is relabelled as UUIDv7. The new Core DDL has changed
fingerprints, so previously initialized opt-in P1 Core stores fail the physical
schema check; no migration is provided. The normal Schema 21 initializer remains
unchanged.

The pre-I3 Exchange exporter refuses Core exports containing new observations,
rather than emitting a deceptively complete old-format package. Backup/restore
validation likewise refuses to certify a Core containing I1 ref-observation data
until the manifest accounts for it. Salvage marks these new records partial and
does not stage new note bodies or proof bundles as generic metadata. These
explicit limitations preserve the stop/recovery and no-unproven-body boundaries;
I3 must replace them with typed, validated roundtrip support. Unsupported work
is not reported as corruption and does not stop a healthy catalog.
