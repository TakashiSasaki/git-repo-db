# Prototype A: append-only, metadata-only Core

This executable experiment is isolated in
[`tests/integration/architecture_spikes/core.py`](../../tests/integration/architecture_spikes/core.py).
It does not change Schema 21, the packaged initializer, CLI, or production
catalog operations. Its focused adversarial assertions are in
[`test_core.py`](../../tests/integration/architecture_spikes/test_core.py).

## Implemented contract

`Core(path)` initializes or reopens one disposable SQLite database. It has no
Context path, source registration, fetcher, network client, raw-body prerequisite,
mutable revision, or global publication record. `admit_object`, `admit_claim`,
`admit_group`, `scalar` and `parents` operate without body acquisition or hashing.
An OID reference creates only a nominal identity, never a verified child object,
repository membership or acquired-body claim. A permanent repository UUIDv4 can
be admitted independently.

The two supported object formats are SHA-1 and SHA-256; abbreviated, uppercase or
incorrectly sized OIDs are rejected. Objects use `(object_format,full_oid)` as
their primary key. Type/size are separate attributed claims. Absent claims,
explicitly unknown values, known zero, known empty lists, partial lists and
complete **reported** lists have different encodings and qualifications.

The scalar key contains the full typed subject, field, losslessly encoded typed
value, original source/observation/evidence coordinates, decoder/version and
provenance qualification. Genuine separate source observations remain distinct;
exact retries deduplicate without adding an observation or receipt. Contradictory
values at genuinely separate coordinates coexist. A claimed immutable scalar or
group coordinate that changes its value fails explicitly rather than receiving
a fabricated coordinate. Attribution is reported and unauthenticated, consistent
with ADR 0027.

The parent-group primary key includes its full subject, relation, actual scope,
status, complete recoverable ordered asserted membership and original qualified
provenance. Canonical compact JSON is a narrow experimental lossless encoding
of this **entire value**, not its hash or another identifier. Each member has a
foreign key containing the full owning group key and a separate typed-OID FK.
Actual parent ordinals are supplied explicitly; a partial list may contain holes.
Unknown order with nonempty members is intentionally unsupported rather than
inventing ordinals. Unknown and known-empty observations have no members but
different status components. Complete reported groups require a witnessed
contiguous order; this is an assertion, not receiver verification of closure.

An atomic group transaction inserts nominal references, the whole immutable
group and every member. The full membership key plus a membership trigger denies
later extension; UPDATE/DELETE triggers deny changes. A partial group followed
by a separately evidenced coherent complete group creates two assertions.
Readers do not union them. Group conflict detection compares overlapping actual
parent slots and mutually incompatible full-list assertions and positive slots excluded by a
complete/known-empty list, rather than merely
comparing primary-key inequality. `parents` preserves every original alternative.

## Local verification and the byte boundary

`admit_verified_commit` is the only byte-admission method. It requires actual
bytes, exact supplied size and matching native `commit size\0body` SHA-1/SHA-256.
A deliberately narrow parser checks a tree header, ordered parent headers and
single author/committer headers; unsupported extensions and multiline headers
fail closed. It installs the allowed exact commit body, its physical SHA-256,
tree relation, parent group, type and size in one transaction. Referenced trees
and parents need no bytes. This is not a full Git parser or fsck implementation.

The admitted representation plus full semantic claim/group foreign keys supplies
bounded immutable historical check evidence. Rechecking the same representation
does not create a successful-attempt ledger. `scalar`/`parents` prefer only the
precisely receiver-derived values that have these evidence links; reports remain
accessible, with explicit conflict. No source text, sender verified assertion,
arrival order or agreement count independently creates canonical metadata.

Reported attribution and actual receiver derivation are different immutable
provenance qualifications. The report API cannot request receiver derivation.
The qualification itself is not verification: the separately representation-linked
evidence determines checked reads. This prevents an external report using the
receiver's source/decoder strings and intrinsic coordinates from poisoning a
later genuine local admission or becoming canonical. There is no generic blob
upload or body-reading service. Supplying an ordinary blob OID/body to the commit
verifier fails its native-type hash check. Prototype C separately tests legitimate
notes-role body retention.

## Enforcement boundary

Supported SQL inspection is read-only. The connection authorizer rejects generic
INSERT/UPDATE/DELETE/REPLACE, DDL, transaction-control and PRAGMA commands. Internal
admission permits only INSERT, reads and transaction boundaries. Statement caching
is disabled so authorization is reevaluated when an internal admission capability
has closed. Direct application methods never issue UPDATE/DELETE/REPLACE.

SQLite FKs, WITHOUT ROWID semantic PKs, no-mutation triggers and the member
membership trigger support this policy. Separate-writer tests actually exercise
triggers and full composite FKs. As in the accepted application-level policy,
this does not protect against a database owner disabling triggers/FKs, modifying
the file or reaching private Python internals. Another unrestricted writer could
insert a group header without its members or forge verification rows; it is
outside the supported connection/admission contract. Production work must enforce
connection ownership and validate incoming databases, not mistake SQL triggers
for cryptographic verification. Opening an arbitrary existing file also requires
production fingerprint/domain validation; the spike only reopens its own fixture.

## Executed evidence

Baseline `origin/main`: `57de60b65c2ef29420a885b0c2102dc90e11fa75`.
The final integrated feature SHA/tree and combined receipts are recorded in the
implementation report; this file does not claim its own future commit hash.

Measured environment: Python **3.12.14**, SQLite **3.53.1**, Git **2.52.0**.
SQLite JSON functions, WAL, foreign keys and recursive triggers are exercised by
the test fixture and separate-connection assertions.

Commands actually executed:

```bash
uv run --no-sync pytest tests/integration/architecture_spikes/test_core.py -q
uv run --no-sync ruff check tests/integration/architecture_spikes/core.py tests/integration/architecture_spikes/test_core.py
uv run --no-sync ruff format --check tests/integration/architecture_spikes/core.py tests/integration/architecture_spikes/test_core.py
uv run --no-sync python -c 'import platform, sqlite3; print(platform.python_version(), sqlite3.sqlite_version); print(sqlite3.connect(":memory:").execute("select json_valid(?)", ("[]",)).fetchone())'
git --version
```

Final focused result after independent-review correction: **43 passed, 0 failed,
0 skipped**, in 0.17 seconds.
Focused Ruff checks passed and both files were formatted. An earlier Ruff run
identified one import-order error; `ruff check --fix` corrected it and the final
check passed. Initial behavioral run passed 31 cases; subsequent self-review
added qualification/poisoning, inconsistent-group-coordinate and native blob
retention regressions before a passing 35-case run. Independent review then
found that a closed parent list did not conflict with a partial assertion of an
extra slot. The new regression invocation below reproduced **4 failed, 4 passed,
35 deselected** before correction. The implementation compared positive overlap
and full-list alternatives, omitting the negative information asserted by a
complete/known-empty group. It now compares every observed positive slot against
each closed group's actual slot set. Both admission orders and four compatible
partial/unknown controls pass in the final 43-case run.

```bash
uv run --no-sync pytest tests/integration/architecture_spikes/test_core.py -q -k closed_parent_group
```

No behavioral failure was retried without diagnosis. These are development experiments, not release or
whole-product acceptance.

The deterministic group failure hook runs immediately after the first member
INSERT. A different SQLite connection sees **zero groups** while the transaction
is open. The injected exception rolls back the group, members and all nominal
objects created by that admission. Retry then commits the complete two-member
group. This exercises real SQLite visibility and rollback, not a simulated row
counter. Process-kill and two-authoritative-store experiments belong to B.

## Remaining implementation work

The demonstrated contracts support a coherent Core schema/admission PR after the
four-store interface/key boundary is fixed. This spike does not implement general
Git scalar types, raw tree/tag parsers, notes Capture persistence, full completeness
proofs, metadata Exchange/backup, production connection/fingerprint validation,
physical instance recovery, resource-scale performance or read-output integrity.
Generic source observation coordinates are actual producer evidence coordinates;
this is not a new universal observation ledger. Notes Capture's accepted UUIDv4
pair is neither replaced nor approximated here. Evidence coordinates must come
from real upstream observations; an upstream interface that supplies insufficient
identity must refuse that keyed assertion rather than minting a storage ID.

Wide semantic keys and repeated membership values are accepted proof-of-contract
costs. Encoding bounds, indexes and performance need measurement in the schema
implementation PR, retaining exact equality and full matching FKs. No owner
policy decision or new ADR is required by these engineering choices.
