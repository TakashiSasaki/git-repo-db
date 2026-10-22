# ADR 0031 I4: G3=A Transfer SQL contract

Base: PR #126 `614ccaac3512a0df4291653fc83901df211f00f6`, tree
`0e35eccffd996c5b7ed175a53adebf2ac76b16cb`. Its independently reviewed I3
product tree is `6f259f7239d7330bea4d1dd1b6e04c316561728f`. Initial live
GitHub PR/complete branch inspection found no equivalent I4 implementation.
The accepted ADR and design inputs remain unchanged.

## Persistent contract

Only the existing `resource_relations` and `resource_repository_relations`
authorities are extended. ResourceKey retains its three-column PK and native
identification, including the absence of any namespace-existence FK. There is
no new domain table, surrogate, Parent winner or writable duplicate support.

A reserved `transfer_event_report` keeps the original Event ResourceKey,
`members_json`, `provenance_json`, `scope_json` and `observed_at_us`. Its canonical
scope contains all of the original five Event scope fields (`clock`,
`event_type`, `from_provider_repository_id`, `to_provider_repository_id`,
`provided_roles`) plus the original `endpoints` declarations and three complete
support strings: `parent_members_json`, `parent_provenance_json`,
`parent_scope_json`. This is an explicit new-format SQL contract for I5; it does
not retrofit the still-fenced old Transfer domain constructor or wire format.

Eight GENERATED ALWAYS columns project the sole support payload and reserved
types. The full seven-component ParentReportKey, plus its generated child
subtype and Parent kind, references the existing `parent_report_typed_fk`.
A second six-component FK references `resources_native_event_fk` for the same
Event, `timeline_event`, `issue`, and the support's canonical Issue ID. The
support service equals the Event service; all required projections are explicitly
non-NULL. The row-local `p1_transfer_event_v1/7` validates the bounded canonical
shape without database lookups. Resource identification already requires the
canonical ID to reconstruct its native metadata. Thus native I7 and reported I8
cannot match, even if I8 and its lawful Parent report both exist. Missing correct
I7 Resource/report instead fails the dependency FK; re-supply the original
report after adding dependencies. Arrival alone does not synthesize any report.

`report_clock_json` now also projects original Event clocks. A partial UNIQUE
index over `(EventResourceKey, original-clock, original-provenance)` defines
EventReportKey ownership of one whole immutable members/scope/time group. This
does not select a Parent globally: reports under different genuine clocks or
provenance remain separate. Parent and Event clocks, provenance and observation
times are independent. Explicit unknown original times stay SQL NULL.

Endpoints add two original full-report reference fields:
`event_report_members_json` and `event_report_scope_json`. A generated reserved
report kind plus the Event ResourceKey and original provenance references all
seven direct Event relation PK components. `p1_transfer_endpoint_v1/4` requires
the original clock and a declared `(role, canonical-target-JSON)` pair. An SQL
trigger binds the endpoint's observation time to the referenced report,
including NULL equality. Non-Transfer roles require both new fields to be NULL.

Pre-conflict Event and endpoint guards reject original payload/time rebinding
before IGNORE, DO NOTHING or UPSERT can skip later constraints. Existing immutable
UPDATE/DELETE guards reject REPLACE and UPSERT updates. Exact IGNORE/DO NOTHING
replay preserves the old row. Original direct report and endpoint PKs remain;
all six relation roles, Source positives, five-column Coverage, Resource metadata
and other store schemas remain unchanged. FK/index equality is BINARY.

The shared `p1_context.register_functions` registers all three new deterministic
UDFs; `p1_schema.verify_connection` requires their exact arities/flags. Existing
factory, expected-schema, production writer/reader and recovery registration
paths use that entry point. Packaged DDL, physical/composed fingerprints and
introspected schema inventory change together. The callsite audit explicitly
classifies the one new opt-in module without a prefix exclusion. Schema 21 stays
the public default; no compatibility or migration is added.

## Fences and isolated verification

Both I2 SQL Transfer fences remain byte-identical, as do the application refusal
and impossible-storage recovery boundaries. No product connection can accept a
Transfer in this stage. The required non-NULL endpoint reference fields have no
meaning for ordinary relation roles, whose existing writer remains unchanged.

`tests/integration/p3/test_transfer_sql.py` uses both fresh composed product SQL
and the product initialize/connect factory. Each isolated fixture first compares
its entire actual schema to `expected_schema('context')`, then executes exactly:

```sql
DROP TRIGGER i2_transfer_stage_fence;
DROP TRIGGER i2_transfer_report_stage_fence;
```

No other schema, function, pragma, FK, index or trigger is replaced. This applies
only to disposable synthetic databases, without a subsequent normal-schema reopen.
The raw evidence records both removed definitions and complete SQL traces/rowsets.
Normal configurations separately reject reports/endpoints through all conflict
verbs; normal typed Admission still raises `I2_TRANSFER_UNSUPPORTED`.
Success in the isolated fixture proves the bounded SQL constraints only.

## I5 and later handoff

I5 must supply the exact scope/support/reference fields above and distinguish
permanent native-Issue mismatch from missing eligible dependencies before writes.
Validate genuine normalized `transferred` meaning, actual native contract and
Provider-declared members, selection/permission and referent existence, original
timestamp types before SQLite affinity, supplied versus truncated endpoint
completeness, and mapping dependencies. Savepoint the complete unit, including
second-endpoint failure; exact replays must revalidate eligibility. Parent
arrival must never replay a withheld original. No hidden original-bearing queue.

SQL validates structure and reference existence, not Provider authenticity. A
nonempty original event type other than `transferred` is deliberately structurally
representable in the isolated SQL lane; I5 must refuse it as Transfer support.
SQL storage affinity cannot prove the caller's original bool/float/string input
for an INTEGER column. JSON clock types are strictly checked; pre-affinity
observation-time checks and whole-unit admission remain I5 duties. Arbitrary
SQL does not prove that every declared endpoint was supplied atomically.

Do not remove either fence until reviewed I5 Admission and corresponding routes
are complete. I6 wire remains unimplemented. **Task G G-R1 remains open for I7:**
direct FieldCandidate reads do not establish full Recovery. Full recovery,
paired backup and query/Search acceptance are separate work. No existing PR
changes, merge, release, deployment, P8 or real-catalog/Provider operations.

See [author evidence and frozen review inputs](evidence/adr0031-i4/README.md).
