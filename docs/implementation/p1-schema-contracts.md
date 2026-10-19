# P1 four-store physical schema and interface contracts

P1 is an isolated, executable foundation for the accepted architecture. It depends
on PR #70, parent `eb84be9b2061b026ad82b780cc95e062928f838a`. Its DDL and reference
adapters are not imported by the normal CLI initializer. Catalog3 Schema 21
continues to be the public runtime until P8. P1 does not migrate a catalog.

## Access A3 registration-boundary refinement

The opt-in Context registration columns retain domain-only metadata under
[the A3 boundary](access-a3-registration-boundary.md). Executable access settings
are not portable domain registrations. The authored
[A3 routing ledger](access-a3-routing.json) explicitly overrides the legacy mixed
JSON routes referenced by `p1-disposition.json`; the older column mappings remain
baseline lineage, not permission to insert/transfer arbitrary configuration JSON.
Run `python scripts/audit_context_registration.py` together with the existing
schema/disposition checks. Historical execution receipts keep their original
source revisions; this refinement does not retroactively change their results.

## Entry points and physical ownership

`repo_catalog.adapters.sqlite.p1_schema` composes packaged `p1_ddl/*.sql` and
immutable guards. `initialize(path, store, repository_uuidv4,
catalog_instance_uuidv4)` creates exactly one new database with exclusive file
creation. `connect(path, store)` opens an existing target only, registers required
deterministic UDFs, enables foreign keys and recursive triggers, and verifies the
actual SQLite schema against its packaged composition. This is trusted adapter
infrastructure; it is not an application admission port.

The minimum supported P1 SQLite binding is **3.51.3** (including the verified WAL
reset fix). Initialization checks JSON, WAL, STRICT, foreign keys and recursive
triggers. Connections disable prepared statement caching. `synchronous=EXTRA`
applies to SQLite durability; it does not supply a complete filesystem backup or
activation protocol. Only cooperating POSIX processes on local filesystems with
SQLite WAL locking and `flock` are supported by the reference coordination adapter.
Unsupported platforms fail explicitly; P7 must supply and validate additional
platform adapters before claiming support.

| Store | Durable authority | Mutation and absence |
| --- | --- | --- |
| Core | Repository registrations, nominal full typed OIDs, attributed claims, whole relation groups, observations, captures, checked intrinsic structure, allowed metadata and role-proven notes representations, Core Coverage | INSERT only, including technical identity rows; valid with no Context or bytes |
| Context | Provider/Source/resource identities, current field candidates, exact UTF-8 text, contextual relationships, collection/terminal evidence, known-positive Source associations, Context Coverage, portable Core references | Independently durable; current candidates may change under source clocks; absence is unavailable, never a cache miss |
| Operational | Explicit requests/attempts, finite work reservations and actual charges, scoped continuation/retry/cache locators | Reconstructible; missing prior accounting prohibits resuming that request at zero |
| Search | Semantic document projections tied to exact authoritative snapshots | Reconstructible; stale, missing or invalid index uses direct authority scans |

`store_identity` binds the physical role, initial repository seed and catalog
instance. Its seed is a pairing anchor, not a single-repository restriction:
Core's `repositories` registry admits further permanent repository UUIDv4s.
Repository names, endpoint strings and shared OIDs never merge repository identities.
Context registration and Source membership have their own independent keys.

Run `uv run --no-sync python scripts/build_p1_schema.py --check` to reproduce the
DDL and executed `sqlite_schema` fingerprints. The checked-in fingerprint manifest
also lists actual tables. No user database participates in generation. Installed
wheel and sdist-wheel tests construct all four stores outside the checkout.

## Keys, whole values and supported connections

All target tables use STRICT and WITHOUT ROWID with explicit semantic primary
keys. UUIDs identify accepted real repository, producer/capture, physical copy,
request/attempt or catalog-instance entities; there is no additional row UUID or
integer join alias. Full typed OIDs identify nominal objects independently of
repository, possession and truth of reported attributes.

Whole immutable group membership and original provenance participate directly in
the composite identity. Canonical JSON is a reversible encoding of the entire
value: array positions and types, exact strings, escaped Unicode and binary hex
coordinates are retained. Validation rejects noncanonical encodings, omitted
identity coordinates, fabricated positions and unsupported group types. Digests
never replace claim, group or Coverage identity. SHA-256 identifies exact domain
text and expected physical byte content; separate real copies remain distinguishable.

Core's `Core` adapter is the supported admission boundary. Public SQL inspection
is read only; its authorizer denies generic DML, DDL, ATTACH, transaction controls
and PRAGMA changes. Every Core table additionally has UPDATE and DELETE rejection
triggers. Recursive triggers close SQLite REPLACE's implicit-delete path; tests
exercise REPLACE, mutating upserts, generic SQL and repeated preparation after an
admission capability has closed. Foreign keys and domain UDF checks remain active.

A privileged process can drop triggers, change Python, disable connection settings
or replace filesystem bytes. P1 claims application enforcement, not protection
against its database owner. Raw factory connections and adapter-private attributes
are trusted infrastructure, never plugin or user SQL APIs.

`CoreAdmission` methods own one Core transaction in standalone use. A
`Core.for_transaction(...)` capability binds the same typed port to a coordinator
transaction, uses savepoints for individual units and never commits the outer
transaction. The capability expires at block exit. Context methods participate
in a caller-owned transaction; field candidate replacement has an internal
savepoint. Parent positions may be explicitly unreported; known ordinals and unpositioned
membership normalize without inventing an order. No transaction spans network
acquisition. Scalar claims and whole relation groups are separate immutable units; admitting a nominal relation does
not require child bodies or entire Git closure.

## Coverage: five actual authoritative columns

Both authorities compose the same physical `coverage_claims` relation:

```text
owner_kind, owner_coordinates_json, observed_at_us, coverage_state, details_json
PK(owner_kind, owner_coordinates_json, observed_at_us, coverage_state)
FK(owner_kind, owner_coordinates_json) -> coverage_scopes
```

There are **five columns in `PRAGMA table_xinfo`**, including any hidden/generated
columns; it is not a view. No observation ID is invented. `owner_kind` is the
actual typed ownership discriminator. `owner_coordinates_json` encodes every real
owner coordinate and coverage kind, checked against normalized local FK columns
in `coverage_scopes`. For example, a Context collection scope includes full
service/resource identity, collection kind, original collection provenance and
coverage kind. Repository, Source, Source-only inventory, resource and field
scopes retain their own complete coordinates. Core has repository, capture,
object and field scopes. Dependent proofs use the full four-column semantic
claim key and actual proof subjects, never an alias or digest.

`details_json` is advisory. Exact scope/time/state replay, including differing
advisory details, does not create another claim or use details as a tie-break.
The latest actual observation time determines the complete candidate set. A
newer unknown or partial observation cannot borrow an older complete result.
Equal-time different states remain a conflict. No terminal evidence is unknown;
a real complete empty terminal may establish known-empty only for its actual
owning scope. Source known-positive pairs survive a partial or empty inventory. Actual proof
ownership/category and latest terminal candidates are checked at admission and
again in the pinned projection; a complete report alone does not establish a
complete observed scope. Superseded or conflicting terminals cannot prove empty.
Required nested/head/base/child scopes remain separate, rather than borrowing
another resource's terminal or a prior head's evidence.

## Current Context state and provenance

Provider/service and Source-registration UUIDs are genuine domain identities.
Resources use service/kind/provider identity; ordinary Issues do not use repository
membership as identity. A PR document/review/child uses its actual parent, kind
and provider document ID in a lossless composite representation with a matching
local parent FK. Detached resources require no fabricated Source or repository.

Each current field candidate preserves its own source clock, actual original
provenance and observation time. Missing has no candidate; explicit JSON null is
an observed value. Comparable later source clocks replace dominated candidates;
equal and incomparable alternatives remain accessible. No local processing time,
sender verification flag or receiver check overwrites original source evidence.
Current repository membership supports attachment, transfer and explicit observed
null detachment without changing Issue identity. Exact retained-text-reference
fields have a real FK; supplied digest reports are separately qualified. Generated
source clocks check SQLite result types as well as JSON syntax/int64 API ranges. P1 stores current necessary alternatives, not full API originals
or a normalized history of every Provider edit.

## Coordination, snapshots, partial success and recovery

The reference coordinator holds one permanent OS gate across Core-first admission
and the independent Context transaction. Each database has its own COMMIT. A
Context failure cannot roll back already committed valid Core evidence. Lost
acknowledgement replays the same original keys; it does not create another capture.
Context portable references are checked against committed Core evidence before
Context COMMIT. Nominal resolution does not establish byte verification or closure.

Paired readers hold a shared gate while opening both transactions and executing
SELECT in each, then keep both snapshots pinned through result production. BEGIN
alone is deferred and insufficient. Snapshot tokens bind repository seed, catalog
instance, schema and full authoritative content; they are conservative derivative
freshness fingerprints, not domain primary keys, revision counters or completion
records. No mutable Core revision or append-only counter history is introduced.

A backup candidate copies both authorities while the gate excludes writers,
validates schema/domain/FKs/identities/dependencies, and writes its certificate
last. Interrupted candidates have no full-pair certificate. Certificates explicitly
state that P1 does **not** implement the power-loss-safe P7 installation/activation
engine. Revalidation of candidate content is required even if file hashes match.
Git-only read availability and absent Context are tested independently.

COMMIT and candidate certification use a separate short completion fence with a
final stop check, so a fault detected by an already pinned reader can stop an
in-flight completion. The persistent marker is published before unwinding the
writer gate; it is never delayed until an exception handler can reacquire it.

Detected authoritative corruption requires a catalog-wide stop outside the suspect
database and outside Operational. Ordinary service cannot resume after restart or
loss of derivatives. There is no quarantine flag/count, byte repair in place,
sibling-copy continuation or stop-clearing operation. P7 owns read-only forensic
preservation of journals/WAL, typed untrusted salvage, fresh verified restore,
revalidated merge and later activation. P1 does not claim to implement that engine.

## Notes and retained bytes

Notes captures use the original `(capture_origin_uuidv4,capture_uuidv4)` directly.
Exact replay preserves both; a genuine repeat observation has its own capture.
Ref/root/source/repository binding is immutable and independent of Context. External
origin reports remain unauthenticated attribution under ADR 0027, without PKI or
signatures. Neither UUID equality nor sender verification creates local authority.

The notes role gate checks the exact captured root, required commit/tree path,
target-to-note mapping and native body format/OID/type/size/digest. The narrow
reference grammar supports direct-tree or commit roots, standard hex/fanout paths
and appropriate Git tree modes. Unsupported grammar fails closed. It needs no
annotated target body, complete notes enumeration or implicit network request.
`notes_projection(capture, target)` returns metadata-only attributed claims/groups,
explicit conflicts and only precisely relevant receiver-checked mapping preference.
`admit_notes_role` can check one structural mapping without retaining a note body.
Binary and empty notes, multiple namespaces, unknown target possession and a
shared file/note OID are valid. Retention permission stays attached to the proven
notes role; it does not authorize a file-body API.

Commit/tree/tag exact representations have separate typed admission. Ordinary
blob admission is rejected by the metadata schema/API; notes blobs require a
verified role FK and actual local checks. No generic raw-body, unproven-body
staging, file text or file restoration endpoint is added. Canonical reads use only
specifically checked intrinsic fields/groups and preserve all original reports.
Historical metadata reads need no present-body rehash; byte-returning reads check
the actual returned bytes and stop on retained authoritative corruption.

Finite request budgets reserve work durably before processing, then record actual
cost. Unsettled reservations remain conservative after a crash, distinct from
reported actual work. Replay/rejected processing still costs real work; rollback
cannot refund it. An explicit finite increase retains prior costs. Operational
loss leaves old continuation unavailable and leaves admitted facts valid.

## Implementation limits and stage ownership

P1 provides executable DDL, validators, stable typed ports, reference behavior and
adversarial contract fixtures. P2 implements the complete production Core adapter
and parser; P3 implements complete Provider/current Context behavior. P4 extends
notes grammar/acquisition; P5 acquisition/Exchange; P6 CLI/search consumers; P7
backup/recovery/activation; P8 switches the integrated runtime. A green focused
P1 run is not complete P8 runtime or release acceptance.

The [reconciliation](p1-reconciliation.md) accounts for every baseline table and
column. [P2](p2-git-core-handoff.md) and [P3](p3-context-handoff.md) have independent
file ownership and executable start commands. [Verification](p1-execution-report.md)
and [independent review](p1-independent-review.md) distinguish executed evidence
from future stage requirements. P1 implements accepted decisions; its reversible
encoding/locking choices are engineering details, not a new product ADR or
retirement of historical decisions.

## ADR 0028 classified-time correction (unmerged opt-in implementation)

The shared target now separates the signed-int64 conversion primitive
`validate_epoch_us` from `validate_observation_us` (NULL or strict positive
int64) and `validate_required_observation_us` (strict positive int64, no NULL).
Git author/committer/tagger native times retain their signed meaning and exact
original representations; storage in Core does not make observation times native.
No caller-controlled classification flag can bypass these contracts.

`FieldCandidate.observed_at_us`, `FieldClock.at_us`, `ResourceRelation` time,
repository observation claims and nonterminal Git observation timestamps permit
NULL without inventing temporal order. Missing fields remain absent candidates;
an explicit Provider null remains a candidate whose JSON value is `null`.
An exact replay cannot change the original observation time, including NULL.
Coverage's five columns and composite PK/FK remain unchanged and nonnull;
collection/source terminal and proof coordinates remain required positive int64.
A terminal Git observation also requires its positive observation coordinate.

Python constructors reject bool, float and numeric strings before SQL binding.
JSON clock and Core observation checks validate their original decoded types.
STRICT tables and positive CHECK constraints enforce stored values; SQLite column
affinity can convert bound bool, integral floats or numeric strings before CHECK,
so SQL alone does not prove rejection of those original input types. Seconds or
ISO dates must pass explicit conversion boundaries before classified validation;
valid microsecond values are never rescaled by guessing from their magnitude.

This changes only fresh opt-in target schemas. The declared DDL/physical schema
fingerprints and audited disposition were regenerated after inspecting the new
constraints. No key, source-positive guarantee, authoritative boundary, public
Schema 21 initializer, real catalog or migration changed. Earlier receipts above
remain historical executions and are not claims for this new target tree.
