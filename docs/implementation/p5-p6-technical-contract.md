# P5/P6 common technical contract

**Current Access A3 refinement:** [domain-only registrations](access-a3-registration-boundary.md)
now use wire `git-repo-db/p5-exchange-v3`, with role-specific Context registration
metadata and exact registration envelopes. Earlier v2 correction notes below remain
source-history context; they are not the current wire acceptance vocabulary. Core
claim encodings remain distinct: RepositoryClaim has direct JSON, ScalarClaim has
known/unknown tags. Scope/connection settings are not ordinary domain Exchange.


## Status and dependency boundary

This describes the existing P5/P6 opt-in implementation contract, including
[ADR 0028](../adr/0028-classified-times-and-sha256-exchange.md). The adopted
target for ref-observation identity and evidence is [ADR 0036](../adr/0036-ref-observations-and-shared-notes-mappings.md), which takes precedence over the older Capture identity below. Adoption does not mean this implementation has changed or that PRs are merged. Public Schema 21 remains the default; P7 recovery and P8 public runtime activation remain separate.

The historical stack is `main → #77 → #78 → #79`. The correction stack adds the
owner-decision design branch `docs/p5-p6-owner-decisions` and one common branch
`fix/p5-p6-time-contract`. The corrected P5 branch
`fix/p5-acquisition-exchange` and P6 branch `fix/p6-query-search` both consume the
same common commits. They remain siblings: neither needs the other's owned
implementation. Exact PR numbers, tested revisions and review results belong to
execution receipts and PR descriptions, not an assumed merge state.

Cross-domain tests are a formal tests-only integration deliverable on
`test/p5-p6-corrected-compatibility`, under
`tests/integration/p5_p6_compatibility/`. That branch explicitly depends on both
corrected siblings. A temporary validation branch alone is not their integration
route. The original v1 wire/example and implementation-unchanged guarantees are
historical; the v2 and scoped shared corrections below replace them.

## Preserved authority and identity

Git Core is INSERT-only; Context is an independently durable authority.
Operational and Search are reconstructible derivatives. Permanent repository
UUIDv4, the existing implementation’s two-UUIDv4 Capture pairs, semantic composite PK/FK, positive Source
associations and five-column Coverage semantics remain unchanged in this implementation. For the adopted target, ADR 0036 instead specifies the origin UUIDv4 / ref-observation UUIDv7 pair and immutable result Claims. A package ID,
local catalog instance, request ID, index generation or checksum is not a new
authoritative Publication or domain row surrogate.

Metadata qualification and byte availability are separate. Reported claims stay
attributed reports. Sender intrinsic/health flags do not replace receiver native
OID, byte, grammar or Notes-role verification. Ordinary file blob bodies and
unproven Notes bodies have no durable staging/pending exception. Missing Git
references can remain valid Context reports without fabricated Core objects.

Detected authoritative corruption persistently stops ordinary operations for the
catalog under ADR 0026. A usable sibling representation, Operational recreation,
or Search fallback cannot clear that stop. Search faults alone are derivative
faults and do not diagnose authoritative corruption.

## Shared contracts and classified time

The shared implementation uses `p1_schema.initialize/connect`, `GitCore`,
`Context`, `PairCoordinator`, `WorkLedger`, `RequestIdentity` and the existing P4
`NotesAcquisition`. P5/P6 own their respective orchestration/query modules; these
are opt-in consumers, not public-initializer imports.

`validate_epoch_us` remains the strict signed-int64 microsecond primitive.
`validate_observation_us` accepts NULL or strict integers 1..INT64_MAX.
`validate_required_observation_us` requires that positive integer and rejects
NULL. Python bool, float and numeric strings are not implicitly coerced.

FieldCandidate observation time, Provider `FieldClock.at_us`, positive Context
relations, repository observation claims and nonterminal Git observation times
can remain unknown. No unknown time is replaced with 0, 1, receipt time or now.
A new genuine local observation can measure its actual current time. Missing
fields and explicit Provider nulls remain distinct. NULL establishes no temporal
order; equal/incomparable clock candidates are preserved. Exact replay preserves
the original clock, observation time and provenance, including NULL.

Coverage, collection/source terminal and proof observation coordinates remain
nonnull positive components of their existing composite keys. Missing required
coordinates cannot establish those proofs or freshness. Git-native author,
committer and tagger times retain signed int64 meaning, including zero and
negative values, through native parsing, storage and Exchange. Their original
bytes and OIDs are unchanged; no caller-controlled flag changes classification.
Durations, elapsed/wait intervals, offsets and counts are separate quantities.

Opt-in DDL, declared fingerprints and disposition are updated explicitly. SQL
CHECKs enforce stored-value constraints, and JSON guards inspect original JSON
types. SQLite affinity may convert an original bound bool/integral float/numeric
string before CHECK; SQL alone does not establish API original-type rejection.
No real catalog migration or public Schema 21 DDL change follows.

## P5 acquisition and cumulative requests

Actual P5 entry points are `GitAcquisition.acquire_from_native`,
`GitAcquisition.acquire_metadata_only`, `ProviderAcquisition`,
`PairedAcquisitionCoordinator.admit_paired`, and `ExchangeService`. GitHub intake
uses `normalize_*` functions and `NormalizedContextUnit` in
`adapters/github/production_intake.py`; there is no `GitHubIntake` class.

Provider inputs require actual service/resource identity and original supported
provenance. Partial input preserves missing versus explicit null and real field
clocks. Nullable field/positive relation reports may survive absent terminal
time; unsupported Coverage/Collection coordinates cannot be invented. Known
positive Source membership is not removed by partial or absent inventory.

External Git/Notes input and validation are bounded and prepared before short
Core callbacks. Selected OID success does not establish repository-wide
`git_metadata` completeness. Ref enumeration, requested object set, native
structure, Notes inventory and retained bodies retain their distinct scope.
Partial/unknown Notes results are not overwritten by a complete outer report.

One explicit `RequestIdentity` accumulates actual input, verification, metadata
and proof work across retry/resume/rollback. Initial requests and continuation are
explicit (`new_request` versus continuation); retries do not create fresh free
budgets or implicitly fall back to in-memory progress. The P5
`OperationalAcquisitionLedger` uses durable request witnesses
`p5-request-witnesses/<origin>/<request>` so loss of all or part of Operational
cannot recreate the same request at zero. A genuinely new explicit request can
retain the actual original Capture while receiving its own request identity.
Accepted Core/Context reads remain valid after derivative loss.

Discovery/Capture and physical-copy allocations distinguish a real new
observation/copy from lost-ack retransmission. Cross-store acceptance remains
Core-first, Context-second, with independent COMMITs. Core success plus Context
failure retains `AdmissionFailure.outcome`; caller-visible Exchange/acquisition
failure must report the actual partial success instead of discarding it.

## Exchange v2 canonical envelope

P5's wire identifier is `git-repo-db/p5-exchange-v2`. The top-level keys are
exactly:

```text
format, digest_sha256, package_id, exported_at_us,
sender_catalog_instance_uuidv4, repository_uuidv4,
selection_scope, core, context
```

`package_id` and sender catalog instance are transport coordinates. Original
Capture, ResourceKey, portable Provider/Source identity, provenance and field
clocks survive selective, repeat, reverse, onward and reordered delivery.
Receiver-local catalog binding is distinct from portable domain identity.
`exported_at_us` is NULL or positive int64 and defaults to unknown unless known.

The declared `digest_sha256` is lowercase 64-hex SHA-256 over the canonical UTF-8
encoding of the complete top-level object **excluding only that digest field**.
Canonical encoding uses sorted string keys, separators `,` and `:`, no
insignificant whitespace, `ensure_ascii=False` and `allow_nan=False`. It applies
no Unicode normalization and preserves list order. Embedded domain `*_json`
strings retain their original supported canonical representation; they are not
silently rewritten into a different provenance/key. Duplicate JSON object keys,
nonfinite values and invalid UTF-8 are rejected.

Native object bodies use lowercase contiguous even-length hex `body_hex`.
Notes proofs use `proof_bundle_json`, a JSON string encoding structural tuples
with their exact body hex; the former invented `proof_bundle_hex` field is not
the implementation. Body expansion and structural proof processing are bounded.
Git-native OIDs remain SHA-1 or SHA-256 according to `object_format`, independent
of the package SHA-256.

Limits are 32 MiB for wire/canonical UTF-8, depth 32, and 200,000 traversed values
including embedded `*_json` values. Finite cumulative input/hash/verification,
metadata and proof budgets additionally apply. Raw bytes/string import requires
an explicit request before parsing. Decoded object/dict input can derive request
identity from sender/package UUIDs. Input/parse work is reserved before execution;
failed work does not erase its cost. Successful receiver verification compares
the sender-declared digest with receiver recomputation **before admission**.

SHA-256 is integrity framing, not sender authentication. Replacing both content
and digest can spoof issuer attribution under the intentionally unauthenticated
policy. There is no HMAC, signature, PKI or key-management feature. Digest
agreement also does not authorize supplied intrinsic flags, Notes retention or
unvalidated text. The receiver independently checks typed fields, exact native
bytes/OID/type/size/grammar, Notes root-to-target role evidence and Context UTF-8
text digests. No unreleased-v1 compatibility layer is required.

Detailed current codecs and section vocabulary live in P5's
`domain/exchange.py` and `application/exchange.py` after that sibling is included;
these P5-owned modules are intentionally absent from the common-only branch.

## P6 query capabilities, pagination and search

The actual service is `ProductionQueryService`; Search storage is handled by
`ProductionSearchAdapter`. There is no separate `ProductionSearchService`.
`core_only`, `context_only` and `paired` reads pin the appropriate authoritative
snapshot. `GitCore.for_snapshot` and `Context.for_snapshot` expire with their
trusted source capability and reject a foreign catalog directory. A typed Core
corruption stop notifies the original owner. Metadata-only operations do not
routinely fetch/re-hash all retained bodies; requested typed byte reads still
verify bytes and stop on detected corruption.

`SnapshotReadLimits` bounds each store (default 64 MiB), stored rows (10,000) and
SQLite VM steps (5,000,000) before unbounded validation/extraction. Limit refusal
is a query budget error, not corruption. Optional metadata-only snapshot digests
stream sorted metadata/keys/declared digests without selecting body/proof/text
payload columns. They do not certify those bytes; full backup validation retains
its complete validation/fingerprint path. Metadata snapshot token generation is
still O(N), not a constant-time revision lookup.

`PairCoordinator.last_read_costs_ns` separately measures successful
`authority_validation` and `snapshot_token_generation`. P6 separately measures
authority search validation and derivative projection scans. Snapshot opening,
preflight, validation, token generation and index lookup costs must not be
misreported as one accelerated lookup.

Pagination uses deterministic semantic keys and an explicit snapshot/catalog,
endpoint and filter binding. The keyless SHA-256 cursor digest is a checksum,
not a signature/MAC or authenticity guarantee. Recomputing it after tampering
cannot bypass independent last-key structure/type/range checks or bindings.
Exact-count list pages still scan the bounded input; the bounded heap retains
at most `limit + 1` views rather than sorting all materialized result views.
Search document/hit materialization has its own finite limits.

Search supports literal case-sensitive codepoint substrings without tokenization
or Unicode normalization, including Japanese, short terms, special characters
and NUL. Empty search is rejected; the term limit is 4,096 codepoints. Invalid
UTF-8 Notes bytes use `backslashreplace` summaries; typed byte output preserves
original bytes. Ordinary file bodies never become Search input. Projection
limits are 1 MiB/document, 16 MiB cumulative text and 10,000 documents.

Current backend names are `verified_projection_scan` and `authority_scan`.
The projection is an ordinary table queried with `instr()`, and its candidates
are compared against an independently complete authoritative scan at the pinned
snapshot. This is conservative correctness verification, **not implemented FTS5
or completed index acceleration**. Absent, stale, incomplete, corrupt or
unverifiable Search falls back to the same authoritative scan. Generation
rebuild/publication and exact snapshot binding do not turn a partial generation
into completeness or replace the required independent scan.

## Owned modules and integration evidence

P5 owns `domain/acquisition.py`, `domain/exchange.py`, acquisition ports,
`application/acquisition.py`, `application/exchange.py`, GitHub production intake,
SQLite acquisition and P5 tests/documents. P6 owns production-query domain/ports,
application service, SQLite production-search adapter, opt-in CLI and P6
tests/documents. Shared fixes are implemented once on their common ancestor.

The tests-only branch requires both corrected implementations. Its integrated
suite covers both Git formats and actual Notes, synthetic Provider input,
Context-before-Git, selective and repeated/reverse/onward Exchange, Search
rebuild/scan equality, derivative loss, persistent authoritative corruption stop
and new time constraints. Its exact committed tree, selection/node IDs,
setup/call/teardown journal, JUnit, environment, commands and hashes are acceptance
evidence. Sibling green CI cannot substitute for that execution. Counts from
overlapping reviews are not added as unique coverage.

Development CI, local tests, installed wheel/sdist-wheel verification,
independent review and Release Acceptance are separate outcomes. Historical P4
897, P5 786/790, P6 780 and combined-five reports remain earlier revision claims;
no current count is inferred from them. Full Release Acceptance is not required
by this correction task. No main merge, real migration/recovery, release/tag,
Pages publication or public runtime activation is authorized.
