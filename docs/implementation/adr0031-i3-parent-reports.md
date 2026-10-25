# ADR 0031 I3: typed semantic Parent reports

This owner-authorized implementation starts at PR #125's exact HEAD
`a54e4432b0514ba5a5fe8e73ddcdbc492f99b95e` (tree
`2006edf82c6cff9ec565d8b78fc828fa5cb97a60`). ADR 0031, its schema contract and
design handoff remain unchanged. I2's two Transfer fences remain in force.
See the [author evidence and independent-review handoff](evidence/adr0031-i3/README.md).

## Complete report and reference contract

`ResourceRelation` with the reserved exact BINARY name `parent` is a typed
singleton specialization in the existing `resource_relations` authority. It
preserves these original values without rewriting or timestamp issuance:

- Subject: the complete child ResourceKey triple.
- `members_json`: canonical ordered JSON array containing exactly one complete
  Parent ResourceKey triple, including its serialized canonical identity TEXT.
- `provenance_json`: the original bounded canonical source/evidence object.
- `scope_json`: exactly `{"clock": FieldClock, "document_kind": subtype-or-null,
  "state": "complete"}` under the existing canonical JSON profile. Clock retains
  its genuine domain and positive microseconds or explicit null.
- `observed_at_us`: original positive microseconds or SQL NULL. Neither absence
  of a comparable clock nor an unknown observation time is repaired locally.

`ParentReportKey` exposes the existing seven direct PK coordinates:
`(service, child-kind, child-ID, 'parent', entire-members-JSON,
original-provenance-JSON, entire-scope-JSON)`. Observation time remains an
immutable attribute of that key; even an IGNORE/DO NOTHING/no-op UPSERT cannot
rebind it. A new provenance, clock, clock domain or Parent member makes a distinct
report, rather than a mutable winner. Exact admitted replay is idempotent through
`Context.relation()`. Plain SQL duplicate INSERT fails the PK; OR IGNORE and DO
NOTHING retain the original. Immutable DELETE/UPDATE guards also reject REPLACE
and UPSERT-update on an admitted report, even if the new values are equal.

Generated read-only `parent_service`, `parent_kind`, `parent_id`,
`source_document_kind` and `report_clock_json` are projections of those originals.
The typed CHECK requires every projection to be non-NULL. Parent targets have a
real triple FK to `resources`; the child has both its triple FK and a four-column
FK through `resources.reference_document_kind`. Explicit scope
`document_kind:null` selects the existing non-NULL empty-string absence
projection. Omission, empty subtype, wrong subtype, noncanonical IDs and NULL
members cannot disable the typed FKs. The row-local deterministic
`p1_parent_report_v1/7` validates finite original JSON/identity contracts without
querying the database. Its bounds reuse the established canonical parser
(262,144 UTF-8 bytes, depth 32, 4,096 values per JSON input) and identity codec.

`parent_report_typed_fk` is a BINARY UNIQUE index over the entire seven-column
report key plus generated child subtype and Parent kind. A downstream typed
reference must supply all nine components, not just child/clock/provenance or
child/Parent. The disposable test consumer proves each individual component is
necessary. `parent_report_target` indexes reverse target lookup. No table, new
surrogate key, writable Parent column or UNIQUE child/clock rule is added.
General coherent multi-member reports keep their existing original ordered
membership and application dependency checks; they are not split into Parent
edges or given generic SQL array referential-integrity claims.

## Admission, resupply and alternatives

Child Resource registration remains independent of Parent existence and creates
no relationship. A missing referent rejects the report with no durable staging,
original-bearing queue or other domain side effect. Parent arrival alone only
registers that Resource. The caller must resupply the original report; it passes
shape/completeness, selection, permission, both stored identifications and
referent checks before duplicate lookup. `Context.relation()` accepts optional
`selected_resources` and `permitted(ResourceKey)` policy parameters and checks
all actual unit members on every invocation. None means the existing trusted
local persistence caller has unrestricted local authority. This is a local
policy seam, not an I6 Exchange wire/permission implementation.

Global Documents, PR-scoped Documents, ordinary/unknown child kinds and
nonleaf Document graphs are supported. A Global Document can parent another
Resource or itself have a reported Parent. The known scoped child contracts keep
their allowed Parent kinds; global/unscoped children accept any actual Resource
kind within the same service. Namespace ID and reported Parent ID are never
required to be equal generally. Thus a lawful I8 Issue Parent report for an Event
natively scoped under I7 is retained alongside I7. It supplies **no** I7-native
Transfer support in this stage. No traversal, transitive permission, completeness
of a wider graph, or single chosen Parent is inferred.

## Cross-layer audit and stage boundaries

| Surface | Result and limit |
| --- | --- |
| DDL/index/FK | Only existing Context relation authority extended; five generated columns, two indexes, one INSERT guard, two added FKs. Resource identity and identifying metadata unchanged. No new domain table. |
| UDF/connection | `p1_context.register_functions` registers deterministic `p1_parent_report_v1/7`; shared factories and recovery connections use it. `verify_connection` requires deterministic registration. Both runtime schema constructors and installed artifacts exercise it. |
| Fingerprints/inventory | Composed Context DDL and physical fingerprint regenerated together with `p1-disposition.json`; other store fingerprints unchanged. Lexical callsite inventory regenerated, with its existing data-flow limitations retained. |
| Public Schema 21 | Existing default schema/initializer unchanged; this remains the explicit isolated P1/product Context family. No compatibility or migration. |
| Writer/reader | Domain construction and SQL validate typed shape; production admission revalidates referents/type/policy before replay. Reads reconstruct original reports and revalidate the selected Parent dependencies. Explicit insert column names retain packaged generated-column compatibility. |
| Stored invariants | Existing stored Context validator now checks Parent syntax, source subtype and both referents using trusted product code. This bounded addition is not full I7 recovery. |
| Source/Coverage | No new Source evidence or Coverage claim is inferred from Parent or namespace; their tables, five claim columns and known-positive membership rules remain unchanged. Broad regression cohort includes their original tests. |
| Core/Access/Operational | No new authority, schema, persisted queue, transport original or store dependency. Child-only Context transactions remain possible. Core remains unchanged. |
| Query/Search | Existing relation reader returns all reports; no winner or Search authority is added. Generalized wire, graph queries and full Search remain I6/I8. |
| Transfer | Both I2 report and endpoint fences retained verbatim. I4 G3=A native-I7 SQL and I5 whole-unit admission are unimplemented. The full-key index alone makes no Transfer eligible. |

The active I2 SQL diagnostic's three lawful Parent fixture scopes now supply the
I3 complete scope rather than `{}`. This preserves all 301 diagnostic groups and
all historical Task E/F/G evidence, which remains byte-identical. Existing
runtime tests and their 79 staging non-successes are neither removed nor
converted to skips/xfails. The I3 runner separately records the dedicated Parent
cohort and the broader inherited cohort; their overlapping passes are not added
as unique tests. Failure classification is derived from the actual retained node
sets and first-failure traces, with later assertions unexecuted.

**Explicit I7 handoff: G-R1 from Task G remains open.** Direct
`Context.candidates()` can expose field evidence despite corrupted Global/Scoped
identification without persisting Recovery Stop; later `identification()` detects
it. I3 Parent reads check their own dependencies, but no unverified direct
FieldCandidate read is claimed to establish full Recovery. Preserve Task G's two
failed counterexamples and four installed failing probes as their historical
results. Full salvage/restore/activation and generalized backup integration are
separate I7 obligations. No merge, release, deployment, P8 or live catalog work.
