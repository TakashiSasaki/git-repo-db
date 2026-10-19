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
