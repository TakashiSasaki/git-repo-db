# Production Git Core implementation

P2 supplies an opt-in production `GitCore` adapter and selective local
`GitNativeSource` input against the exact P1 `CoreAdmission`/`CoreRead` types.
The existing public initializer and Schema 21 runtime remain unchanged. P2 and
P3 are sibling implementations; neither consumes the other's commits. The
common P1 contracts and any separately reviewed correction dependency govern both.
No accepted ADR is modified, and this work performs no merge, deployment,
production migration or real catalog recovery.

## Production behavior

`src/repo_catalog/adapters/sqlite/git_core.py::GitCore` implements the original
ports through P1's immutable enforcement and coordination, extending the native
metadata unit with checked author/committer names, addresses, timestamps, exact
message, encoding, parent count, tag name/tagger, lossless header data and decoder
settings. One transaction installs the physical representation, nominal targets,
whole intrinsic relation groups and checked scalar evidence. An injected failure
after native groups but before the author evidence rolls back the entire unit.

The existing supported admission methods remain available for nominal objects,
unknown/known attributed scalar claims, immutable whole groups, repository
claims, ref/root/acquisition/snapshot/manifest observations, Core Coverage and
notes claims/groups. No Context Source registration, child representation or
reachable closure is required. Missing dependencies remain nominal. Original
reports never become receiver verification merely because later exact bytes
agree; genuine contradictory reports survive and remain explicit alternatives.
Exact original-evidence replay uses the same direct P1 semantic keys.

The production class inherits the one local-transaction/savepoint capability,
cooperative writer gate, pinned projections, persistent catalog-stop check,
Capture binding, five-column Coverage behavior and purpose-bound notes storage.
`GitCore.for_transaction(db)` returns the production class and expires at block
exit. P5 owns full acquisition/Exchange composition, and P6 owns public consumers.

`src/repo_catalog/domain/git_native.py` validates both SHA-1 and SHA-256:

- Commit tree, ordered parents, author/committer and optional encoding;
  single-line extensions and folded `gpgsig`, `gpgsig-sha256`, `mergetag` and
  unknown extension headers are preserved without authenticating signatures.
- Tree entries use native binary OID widths, raw binary names, five supported
  canonical modes, Git basename ordering and unique raw-name conflict slots.
  Truncated, duplicate, malformed-mode, null-reference and unsorted trees fail.
- Tags preserve object/type/tag, optional legacy tagger, extensions after tagger
  and exact annotation/signature-bearing message bytes. A present tagger must
  immediately follow the tag header; an absent tagger is explicitly supported
  for historical tag representations, exercised with Git `--literally` fixtures.

Strings use reversible UTF-8/surrogateescape, independent of an asserted encoding.
`header_data` stores exact native header bytes as hexadecimal; `decoder_settings`
states that encoding choice. The acquired exact body remains independently
available only through checked byte reads. Native metadata with NUL bytes, invalid
structural positions, malformed identities, non-HHMM offsets or timestamps outside
signed int64 microseconds is refused with `NATIVE_SYNTAX`. The parser retains P1's
signed timestamp syntax; ordinary Git-generated fixtures use nonnegative dates.
This is the declared supported grammar, not a claim that every historical
malformed object tolerated by arbitrary Git plumbing is accepted.

Tree count is derived from the checked whole `tree_entries` relation. It is not
invented as a checked scalar: P1's frozen four-argument intrinsic scalar SQL guard
has no object-format argument. All supplied `tree_count` reports remain valid
qualified scalar claims. No DDL, common schema fingerprint or physical key was
changed to add a redundant count.

`src/repo_catalog/adapters/git/native.py::GitNativeSource` reads only explicitly
requested metadata OIDs and observable local full refs. It handles bare and
working repositories, verifies storage object format and exact native identity,
and disables replace objects, lazy fetch, optional locks and environment-based
repository redirection. Ordinary blob input is rejected from the metadata path
before its body is read. Finite configurable metadata bytes are checked before
reading output; bounded streaming also has a 30-second local-command timeout.
No network fetch or file restoration endpoint is provided.

## Integrity and notes boundaries

Allowed retained commit/tree/tag bytes require exact format/OID/type/size/digest
checks, plus whole supported structural parsing. Physical copy UUIDv4 values
identify genuine distinct copy occurrences; replay with the same UUID deduplicates
only exact evidence. Metadata projections use historical checked evidence without
rehashing current bytes. Typed byte reads verify the actual selected/emitted copy
and persist catalog-stop on authoritative corruption. A retained-copy row lost
while its intrinsic evidence survives is diagnosed as authoritative loss, not
optional metadata nonacquisition. They do not fall back to a
sibling copy, quarantine an object or repair bytes in place.

Production generic SQL inspection cannot read retained `body` or proof-bundle
columns. This closes an independently identified route around checked byte reads.
P1 row-count assertions now select copy/capture coordinates, preserving their
original behavioral assertions while also exercising the narrower production
boundary. Trusted factory connections remain adapter infrastructure.

Notes use the unchanged actual Capture UUIDv4 pair, immutable ref/root binding,
reported mapping/group alternatives and precisely relevant receiver role proof.
Every supplied commit/tree proof structure passes the production parser before
its mapping can authorize a note blob. A role can be admitted and queried without
a note body or target body. An ordinary file blob's nominal identity, tag relation
or source assertion never grants retention. P4 owns complete notes acquisition,
additional supported proof grammar and whole-inventory completeness. P7 owns
forensic salvage, fresh verified restore and activation; P2 has no stop-clearing
or repair operation.

Actual parsing charges `metadata_units` per inspected header or tree entry, in
addition to the original admitted-unit cost. Repeated Python/SQL checks, exact
replay and rejected parsing cost actual work. Existing `input_bytes`,
`verification_bytes` and `proof_steps` accounting remains active; budget failure
rolls back incomplete authoritative units without refunding performed work or
misdiagnosing corruption. Request-wide durability remains the shared Operational
budget port, rather than a new Core counter.

## Ownership and stage handoff

P2 owns the new three production modules, Core-only native validator extensions
in `domain/p1_core.py`, its production fixtures and focused packaging smoke. The
only P1 test changes replace raw payload/proof `SELECT *` row-count inspection
with semantic coordinate columns. P2 does not edit Context, common Coverage,
coordination, DDL or fingerprints. File collisions with P3 are absent.

P4 may extend notes acquisition against these exact typed boundaries; P5 may
compose selective Git input with Provider intake and Exchange; P6 may implement
public read/search consumers after combined Core/Context verification. These
stages preserve the declared grammar limits and original identities. P7/P8 remain
separate, including complete crash-safe activation and the public runtime switch.
Exact test revisions, local versus hosted coverage, independent findings and any
correction dependency are bound by the execution evidence and integration report.


Domain failures expose `CoreFailure.code` and the smallest available scope:
`NATIVE_SYNTAX`/`NATIVE_INTEGRITY` for incoming representations, `IDENTITY` and
`INCOMPATIBLE_REPLAY` for invalid portable bindings, `NOTES_ROLE`/`NOTES_BODY` for
purpose/association checks, `BUDGET` for finite work refusal, and
`AUTHORITATIVE_CORRUPTION`/`RECOVERY_STOP` for stopped catalog service. Standalone
parser errors name the native kind; production admission syntax errors name the
actual OID. Trusted local SQLite semantic FK/CHECK rejections remain
`sqlite3.IntegrityError`; these do not themselves diagnose catalog corruption.
Git process/start/read failures use `GIT_INPUT` or `OBJECT_UNAVAILABLE` with the
actual path/OID. No assertion claims every SQLite infrastructure failure is a
`CoreFailure`.

Successful ordinary reads also have a final completion linearization against the
persistent stop fence. An independent review published a stop from the final
scalar SELECT and originally observed a normal projection; all public Core read
methods, SQL inspection and outer production byte/notes methods now check final
completion after cleanup. A detector is never blocked behind a read-held
completion lock while doing SQL or parsing. Stops published before completion
withhold the result and allow transaction rollback cleanup. This does not promise
revocation after an operation has already completed. Transaction-bound Core
capabilities rely on the coordinator's enclosing completion boundary.

Additional production-boundary verification closes three late implementation
holes. Transaction-bound Core capabilities verify the physical store role before
installing an authorizer, so shared Coverage table names cannot redirect a Core
admission into Context. Typed readers validate stored scalar/group/provenance
encodings and stop on corrupted UTF-8, JSON or semantic shapes; arbitrary generic
SQL expression failures and caller encoding errors do not diagnose corruption.
The fixed typed SQL path publishes a detected UTF-8 stop before snapshot rollback.

The SQLite native-body guard also checks supported commit/tree/tag grammar after
exact native hashing. A trusted coordinator callback cannot durably insert a
hash-matching malformed representation; actual selected metadata byte reads repeat
the grammar check and stop if privileged storage damage left such a row. Native
blob hashing remains separate from its mandatory notes-role retention FK.

Authoritative SQLite engine failure classification normalizes extended error
codes to their primary CORRUPT, NOTADB or IOERR family. Standalone transaction
BEGIN, body and COMMIT failures publish the persistent stop before rollback or
gate release; constraint, input and budget failures retain ordinary local rollback
semantics. Engine-boundary fault injection exercises real adapter calls and actual
SQLite rollback state, without claiming to reproduce physical media failures.
