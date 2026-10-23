# Domain registration boundaries: validate before writes, preserve positive evidence

Use with the current ADR index and Access A3 contract. These lessons concern
Context registration metadata and typed Exchange, not general text redaction or
an authenticated remote execution boundary.

- Shared JSON syntax is not shared semantics. RepositoryClaim stores a direct JSON
  value, while ScalarClaim stores known/unknown tagged arrays. A round-trip of an
  ordinary URL reproduced a SECOND-CHARACTER truncation caused by `value[1]` at
  the RepositoryClaim importer. Always exercise positive preservation, including
  strings of length zero/one, Unicode, nullable times and repeated/reverse import.
- Check all present registration envelopes before ANY store admission, including
  sections not selected by a package flag. Recompute a hostile package's checksum
  in tests; a valid checksum must not turn executable configuration into domain
  metadata or make unknown sibling fields disappear silently.
- Incoming invalid data is rejection, not corruption. Invalid persisted data is
  not permission to overwrite it with sanitized values. Exercise both writer and
  snapshot/export/query paths with privileged disposable corruption fixtures, and
  assert diagnostics do not copy secret canaries into stop records.
- Adding earlier constructor validation can move a deliberate SQLite fault ahead
  of the operation a test intended to exercise. Preserve the initial setup failure,
  then allow only the new fixed bootstrap reads in the test stub before arming the
  original fault. Do not weaken the real validation or stop behavior to keep a fake
  connection working.
- If a mutation changes packaged SQL, its old fingerprint can mask the intended
  data-constraint test. Record that setup detection separately, build a coherent
  DISPOSABLE mutant manifest and rerun the exact attack. Restore all real sources
  and verify their hashes before ordinary tests/publication.

Current checks:

```sh
python scripts/audit_context_registration.py
python -m pytest -q tests/unit/test_context_registration_values.py tests/integration/access/test_context_boundary.py
```

The A3 report records author-run failures, corrections and tested scope. Neither
this note nor a green checksum/test result establishes human or sender identity.

## Provider intake must bind native coordinates before qualification

For ADR 0030 I2, preserve opaque GitHub Repository Node IDs in their own
namespace, even when databaseId is also observed. A numeric ID or successful
Core/OID/URL operation cannot establish the Core Repository mapping. Exercise
same-target/different-Provider ClaimKeys and retain raw Provider scopes when
mapping is unresolved or later disputed. For current ownership, use
provider_repository_roles(): a newer unresolved Provider owner must not fall
back to an old materialized Core-target relation. I4 consumers must carry this
qualified-read distinction through their integration.

Bind Transfer type evidence to the exact Event Resource, parent, clock,
observation and provenance. A parent_resource override cannot discard a
contradictory parent_id. For a GraphQL Node/database parent alias, require an
actual Issue payload containing both exact original coordinates; do not decode
opaque IDs or accept a different Node ID with the same claimed database ID.
Replay the same original report after Mapping changes without reissuing its
EventReportKey or observation provenance. Test caller-owned Context batches with
a caught mid-batch exception: the complete batch needs its own savepoint.

Reproduce with tests/integration/i2/test_provider_intake.py, including parent
contradiction, event replay, latest unresolved affiliation and external-capability
rollback cases. See the [I2 handoff](../../../../docs/implementation/adr0030-i2-provider-intake.md).
These checks prove typed observation consistency, not remote origin authenticity.

## Complete typed reports must close every public admission route

For ADR 0030 Transfer work, do not infer event type from an Issue-parented
Timeline Event identity. The typed FK proves the Resource shape; it cannot prove
that the Provider reported a Transfer. A constructor check on TransferEventReport
does not protect generic endpoint or ResourceRelation admission. Exercise both
Transfer roles through the reference Store, production Context, result wrappers
and generic scope API before declaring the typed gate closed. Route writes through
the complete report's savepoint and replay comparison; retain explicit event type
in its existing resource_relations scope. Never reconstruct a missing stored type
as transferred. SQL constraints and typed semantic admission have distinct scope;
this does not implement live Provider authenticity or authorize I2 acquisition.

Run the Transfer tests in tests/integration/p1/test_context_relations.py and the
generic scope test in tests/integration/p3/test_production_context.py. Include
valid one-sided/two-sided reports, repeat delivery, whole-unit rollback and invalid
stored-scope controls. See the [freeze record](../../../../docs/implementation/adr0030-i1-contract-freeze.md).

For a multi-endpoint report, test supported A→B and multiple alternatives: one
shared provenance must retain separate exact MappingClaimKeys for each role and
target. A singular support object cannot describe two different targets. Keep
selection truncation explicit even when some alternatives of a role remain;
reselection cannot restore an omitted fact. Validate retained provided_roles and
Provider members against the same canonical report parser used by recovery.
Prevalidate complete caller filter coordinates outside stored-data fault handlers:
an empty Provider ID or ordinary comment filter must not create a P7 stop.

At a public API freeze, compare Protocol parameter names against both reference
and production adapters, then execute protocol-shaped keyword calls. Matching
positional calls alone missed facade names claim/resource/service_or_resource
that rejected the declared relation/provider_repository/service_instance_uuidv4
keywords. Retain intentional positional overloads and verify them separately.
Use test_context_admission_protocol_keyword_calls in the P3 Context suite.

## Selective wire review: exercise receiver controls and exact decoding

For a new versioned Exchange, test the receiver's own empty R/O/C sets, disabled
include flags, zero unit/byte/work limits, and unregistered dependencies using
valid I1-only fixtures. A filtered sender export is not evidence that an untrusted
receiver enforces the same controls. Require a nonempty package to respect these
receiver requests; retain independent valid objects when a Repository claim has
no actual registered referent. Compare decoded scalar/group keys with the exact
wire encoding: accepting any two-element tagged list can turn `["bogus",1]` into
a new `["known",1]` fact. Reject unknown row fields and noncanonical embedded JSON.

Exercise PackageKey digest binding through two connections and distinct genuine
requests, not just same-request replay. Verify the PackageKey includes the sender,
and inspect its lookup plan/global uniqueness. Probe UPDATE/DELETE/REPLACE/UPSERT
under the required recursive-trigger setting. A per-request progress slot alone
is not a globally unique immutable PackageKey unless the shared transaction and
SQL guards enforce it. Check live facts after an actual subprocess exit between
domain commit and checkpoint; an exception-only probe cannot prove that window.
Before claiming bounded prevalidation, duplicate an original direct key with a
different non-key observation timestamp or payload, then add an independent Core
OID. Verify rejection occurs before binding or Core admission. Repeat against an
already populated receiver, including MappingDisposition and whole EventReportKey
endpoint sets: identical scope JSON alone need not identify the Core targets.
Reconcile both PRIMARY KEY and immutable UNIQUE constraints with the actual I1
writer. Capture identity is a pair; a GitObservation using that pair also includes
Repository, kind, scope and provenance. Test valid alternatives as well as invalid
rebinding. Constructor checks alone may omit writer-enforced modeled parent and
Source/service checks. Assert redundant wire coordinates (for example a Notes
root) equal their original typed proof coordinates rather than silently rebuilding
them. Preserve expressly advisory fields such as Coverage details as advisory.
For composed intake/Exchange trees, inventory writer-only semantic subtypes as
well as constructors. `ResourceRelation` alone does not validate I2
`provider_repository_roles`; preflight must call the same exact-role/member/time
validator as admission. Reported Core-reference fields likewise need their exact
nonempty role and typed OID pair checked before binding. Exercise invalid units
with Context disabled or empty receive selection: selection cannot conceal bad
input. Check v4 primitive text types before SQLite affinity so numeric kinds are
not rewritten into strings. Assert no Package Binding, no Core/Context mutation
and no false Recovery Stop, alongside valid I2 round-trip controls. Reproduce with
`pytest -q tests/integration/i23`; see the
[integration handoff](../../../../docs/implementation/adr0030-i23-integration.md).

Check every Coverage owner against its full typed FK, not only the first
coordinate. Source coverage needs the Source/Repository membership and Repository
permission; collection coverage needs ResourceKey, collection kind and original
provenance. Admit original collections before their scopes. Verify a legitimate
collection-owned scope without a proof, a missing collection, an already-present
receiver collection and a permission-cut Source scope. Missing owners withhold
units rather than aborting independent Context facts after Core commit.

Repeat zero-work budget probes with an empty package and an omitted receiver
selection. Incidental database reads in a populated fixture can mask a missing
processing ceiling. Once an implicit selection is decoded, its ceiling must count
already performed decode work before binding; learning it cannot refund work.
See the executable [I3 counterexamples](../../../../tests/integration/i3/test_selective_exchange.py)
and [I3 handoff](../../../../docs/implementation/adr0030-i3-selective-exchange.md).

## Trace nested canonical values separately from the package digest

### Preserve native versus serialized identity boundaries and contract intent

For ADR 0031 identity work, inventory constructor calls and Provider helpers
before replacing plain IDs. A helper may return a native decimal string on one
path and serialized composite Node ID TEXT on another. Make its output contract
uniform, then use explicit encode/parse operations at each boundary. Blindly
encoding every string can quote scalar IDs twice or turn a native composite
into a string. Row/wire/Coverage/MappingSupport/cursor coordinates already carry
serialized identity TEXT and require strict reconstruction, even when a public
checksum has been recomputed. Keep the envelope serializer independent.

Probe a global native Document array that is byte-identical to a known scoped
layout. Key equality alone cannot select its identification contract. Preserve
the explicit factory/admission contract; refuse unsupported global persistence
before duplicate lookup as well as before INSERT. Do not add a key discriminator
or infer a semantic Parent from shape. I1's in-memory intent guard is not durable
contract metadata or a generic Exchange guarantee; those remain I2/I6 work.

Reproduce the bounded regressions with:

```sh
python -m pytest tests/unit/test_resource_key_identity.py tests/unit/test_github_identity_boundaries.py tests/integration/p1/test_resource_identity_sql.py tests/integration/p1/test_context.py -q
```

The [I1 implementation report](../../../../docs/implementation/adr0031-i1-canonical-resource-identity.md)
records the independently reproduced shape/replay and cursor counterexamples.
This procedure does not generalize packaged DDL or establish global Document,
generic Exchange, semantic Parent, recovery or Search acceptance.

### Close active validation fixtures after the canonical-key cutover

Collect the complete ordinary suite before focused execution. Module-level native
IDs can prevent whole modules from collecting. Adapt genuine native fixtures with
`ResourceKey.from_native`; retain strict constructors for rows, wire values and
canonical Provider-helper outputs. Audit SQL reference parameters, nested role
scopes, Search projection keys, accessor string overloads and CLI `--id` together.
Use the key's canonical ID at those reference boundaries. A negative semantic test
needs a structurally valid key so it reaches its intended guard. Do not convert
unrelated public Schema 21 Provider metadata merely because it also says ID.

Bind both direct and unpacked-sdist `uv build --no-build-isolation` commands to
`--python sys.executable` in packaging fixtures. An outside-checkout rebuild can
otherwise choose an interpreter without Hatchling despite a correctly prepared
parent venv. Verify actual installed origins and SQLite source IDs. Keep genuine
GraphQL Node arrays when a repaired fixture reaches the packaged scalar-local
storage refusal; stringifying them would erase the counterexample. Attempt both
distribution variants, retain each failure, and still return a nonzero exit.

The [I1b validation closure](../../../../docs/implementation/adr0031-i1b-validation-closure.md)
records full collection, both supported runtimes, passing P1–P7/packaging cases
and the remaining I2 Event failures. Reproduce the packaging boundary with
`python -m pytest tests/packaging/test_p[1-7]_distribution.py -q` in the prepared
runtime. These fixtures do not establish complete product/distribution acceptance.

For node reconciliation, reuse the existing `junit_key` procedure in
`efficient-repository-investigation/scripts/summarize_pytest.py`: split class/test
separators only before the parameter suffix. IPv6 and `ext::` parameter values
contain literal `::`; splitting the whole ID invents missing JUnit cases. Preserve
raw receipts and issue a separate correction when a work-only parser was wrong.

### Keep inner identity and outer digest profiles separate

Use this source-inspection procedure when reviewing identity/JSON wire changes.
A single word such as canonical can hide distinct profiles: at the
[fixed ADR 0030 product revision](https://github.com/TakashiSasaki/git-repo-db/tree/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9),
Context canonical() uses ensure_ascii=True while Exchange _canonical_content() uses
ensure_ascii=False over the package minus digest_sha256. Resource IDs are strings
inside that envelope. Applying the envelope serializer to an embedded key can
change its spelling; a valid outer checksum cannot establish inner canonicality.
The design research for [ADR 0031](../../../../docs/implementation/context-resource-design-handoff.md)
verified this distinction by reading the actual callsites, without claiming new
schema execution.

Trace the field from constructor through writer, embedded wire value, digest and
receiver validator. Inspect each encoder's flags, hashed scope and exact comparison.
Also compare domain parser, SQL helper and writer checks: the current canonical()
encoder alone can emit lone-surrogate escapes, and SQL p1_json roundtrip does not
apply every bound/Unicode check of _parse_canonical_json. Do not infer uniform
validation from shared names. Reproduce the source inventory with:

```sh
rg -n 'def canonical|def _parse_canonical_json|ensure_ascii|def _json' src/repo_catalog/domain/p1_context.py src/repo_catalog/adapters/sqlite/p1_schema.py
rg -n '_canonical_content|ensure_ascii|digest_sha256|verify_digest' src/repo_catalog/domain/exchange.py
```

Reread current implementations after any source change; these historical flags
are not a mandate for every JSON contract. Do not canonicalize an embedded key
after package binding and reuse the old digest. Specification vectors and source
inspection are distinct from executed parser/schema tests; an unresolved future
identity or FK design must not become skill policy.

### Charge embedded identities at their actual typed position

For ADR 0031 wire bounds, test individually valid Identity TEXT inside a complete
package. Forty-nine distinct 4,096-node identities can exceed the enclosing
200,000-value cap, and a 32-array identity can exceed the enclosing depth once
its Resource row and section are counted. Per-ID validation alone misses both.
Reuse `parse_identity` and charge decoded values, escaped bytes and enclosing
depth at each modeled Resource, member, Coverage, selection and support-key
position. Retain work already spent when a later scan or unit fails.

Keep the typed position explicit while scanning. A generic attributed evidence
dictionary may contain keys resembling a Resource triple or `resource_keys`
without declaring a typed reference. Parsing those by key shape introduced an
overrestriction in I6-B; top-level and nested evidence preservation controls
expose it. Do not infer a native identification contract or traversal edge from
array/dictionary shape. Explicit Source-registration references retain their
separately defined meaning.

Reproduce the aggregate limits, opaque-evidence preservation and planner work
boundaries with `python -m pytest tests/unit/test_context_wire_v5.py
tests/unit/test_context_dependencies.py -q`. The
[I6-B Author matrix](../../../../docs/implementation/evidence/adr0031-i6b-author-20261023/MATRIX.md)
links these controls to the frozen execution receipts. They establish the pure
codec/planner boundary, not Provider authenticity, receiver authorization,
I6-C route integration or full Release acceptance.

### Verify a typed report projection without duplicating authority

When extending an existing JSON report with typed FKs, retain the complete
original report key and derive all reference columns with GENERATED ALWAYS.
Exercise explicit-null subtype absence against a non-NULL target projection;
an omitted field must fail the row-local predicate rather than disable a
composite FK through SQL NULL. Run raw SQL as well as typed admission: source
and target absence must fail, every component of a disposable full-key consumer
must be necessary, and IGNORE/DO NOTHING/no-op UPSERT must not hide an immutable
observation-time rebind. Compare complete pre/post rowsets after rejection,
multirow failure and savepoint/transaction rollback. Keep lawful competing
reports and ordinary ordered multi-member reports as positive controls.

Use `python -m pytest tests/integration/p3/test_parent_reports.py -q` and the
outside-checkout `scripts/verify_i3_distribution.py` probe with the environment's
single Python-loaded SQLite under [ADR 0032](../../../../docs/adr/0032-environment-sqlite-validation.md).
Measure `SELECT sqlite_version(),sqlite_source_id()` in each child process and
retain the selected Python. Do not download/build/install/swap SQLite or require
multiple versions; preserve capability/WAL safety checks and honest failures.
Never overwrite a reported version. The I3 evidence's two official-source builds
are historical facts, not a current setup procedure.
These checks establish the bounded Parent contract, not I4/I5 Transfer support,
I6 generalized Exchange, full I7 Recovery or Provider authenticity.

Register each new opt-in implementation module by its exact path in the
callsite audit's isolated-module set, then rerun the existing public-runtime and
Access isolation tests. Regenerating a lexical inventory alone does not verify
that classification. Keep the explicit-path tests intact; do not replace the
registry with a broad prefix exclusion that could hide a public-runtime import.
