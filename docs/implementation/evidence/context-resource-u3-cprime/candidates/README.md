# Candidate C′ construction and enforcement

The [semantic-gap follow-up](../semantic-gaps/README.md) now extends independent
Document admission and specifies canonical namespace ID TEXT within scoped
identities. A generated typed absence projection preserves source FKs. Notes
below document the earlier freeze and history; see the follow-up for current
representation and the unresolved Q-S10 qualification question.

This is an isolated experiment derived from the exact packaged
`p1_schema.compose("context")` at the frozen product baseline. It replaces only
three table definitions and adds indexes/triggers inside the experimental SQL.
The resulting main schema has the same 19 table names. Product factories reject
its different schema; this is not an activation path.

## Identity and authority

`resources` has no semantic Parent column or Parent FK. Its optional
`identifier_namespace_kind` / `identifier_namespace_id` columns preserve the
existing common document identification coordinates, with consistency checked
against the canonical identity value. They are not a registered referent or
relationship authority. A complete Issue-scoped Timeline Event can therefore
exist while its identifying Issue is unregistered. A later semantic Parent report
may identify a different Issue: the tests preserve that attributed alternative.

Known document kinds retain explicit common typed coordinate checks. Other kinds
can use canonical strings and recursive string arrays; their meanings remain
Provider scoped. The synthetic `synthetic.opaque` and `vendor.future` contracts
accept any complete string/recursive-array value, including empty coordinates;
those fixtures explicitly supply complete identities. SQLite cannot establish
that a real Provider uses empty coordinates or singleton resources.

The row-local identity predicate limits input to 262,144 UTF-8 bytes, 4,096 nodes
and 32 array levels. JSON parsing first bounds lexical nesting to 40 levels.
Identity encoding uses the baseline ASCII-escaped canonical JSON profile; decoded
strings are not trimmed, folded, numerically coerced or normalized. Parent and
Transfer projections extract already validated common report fields, never an
unknown Provider's opaque ID layout. No UDF queries SQLite or external state.

## Existing relations and exact support

The reserved `parent` relation is an explicitly typed singleton report for the
baseline common document kinds. Its complete membership and scope remain in the
existing `resource_relations` primary key. Generated columns expose the target
ResourceKey and the source document kind. Real composite FKs reference the target
Resource and the source Resource's typed document contract. There is no
`UNIQUE(event)` or `UNIQUE(event,parent)` restriction. Distinct members, original
clocks/scopes and provenance remain distinct reports. Unknown-kind relation
vocabularies remain generic; this candidate does not infer their Parent meaning.

The preexisting `transfer_event_report` relation still carries the coherent whole
report. Its experimental scope adds the exact Parent report members/scope and the
complete normalized endpoint list. Its Parent reference includes the same
EventResourceKey and the explicitly supplied original Parent provenance/scope.
Parent and Transfer clocks, provenance and observation times may differ; none
is rewritten to match the other. The full Parent report key plus generated `timeline_event` and
`issue` properties is a real composite FK. This does not pick a winner between
competing Parent reports; the supplied original Transfer report states its support.

Transfer endpoint rows reference both that exact Parent report and that exact
existing event report using real FKs. A row-local CHECK ensures each endpoint
belongs to the referenced whole report, including its clock. A trigger preserves
its original observation time. No Event header, Witness, Mapping authority,
surrogate relationship identifier or verification history is added. All six
Resource-to-Core-Repository roles and their existing maintenance rules remain.

## Layer boundaries

| Invariant | Enforcement |
| --- | --- |
| Canonical recursive identity / known document coordinates | CHECK invoking bounded row-local deterministic predicates; NOT NULL |
| Complete singleton Parent report syntax / no missing projection | CHECK; generated columns |
| Parent target Resource and typed source document exist | Real composite FKs |
| Transfer references exact admitted Parent/report and Timeline Event/Issue properties | Real composite FKs, with non-NULL conditional CHECKs |
| Endpoint is declared in the exact supplied event report | Row-local CHECK plus exact-report FK |
| Report/endpoint time and immutable payload rebinding | BEFORE INSERT/UPDATE/DELETE triggers; recursive triggers required for REPLACE |
| Full supplied Transfer unit, including all declared endpoints, is atomically admitted | Experimental typed admission and savepoint; no SQL COMMIT hook claimed |
| Actual normalized event type is `transferred` | Typed admission; deliberately false internally consistent SQL passes in T12 |
| Arbitrary-length generic relation member existence and selected dependency closure | Experimental reconstruction application checks; not a projected-array FK |
| Current semantic winner / qualified mapping effect / external authenticity | Not inferred; read-time qualification remains outside this structural experiment |

The SQL API proves structural rejection through direct writes without the typed
admission wrapper. It cannot prove a report's external truth. Generic group
syntax remains row-local; the reconstruction helper withholds the original whole
group if a selected referent is absent. It neither shrinks a complete group nor
adds unrelated Resources to selection. This is a Context-only harness, not the
product Exchange, integrity recovery or paired backup implementation.

## Retained failed candidate

`../results/development-02/` retains an executed candidate defect: an endpoint
with an existing semantic PK and altered non-key support-reference members was
silently ignored by `ON CONFLICT DO NOTHING`, because SQLite did not reach FK
validation for the ignored row. The final candidate adds
`cp_endpoint_no_rebind`, a BEFORE INSERT trigger comparing both new non-key
reference fields. This is a trigger guarantee, not an FK guarantee. The final
T08 exercises the same adverse path and receives a real rejection.

The failed run also contains a harness error-precedence mismatch in T05: an
immutable-report trigger rejected the malformed fixture before the expected
CHECK. The final fixture uses distinct attribution to isolate the CHECK. Earlier
`development-01` includes an expected-error precedence mismatch and an INSERT
placeholder-count error; neither is counted as a successful matrix run.

Every file in `development-02/inputs/` matches that run's recorded SHA-256 input.
To rerun the failed snapshot, create a disposable checkout of the experiment
branch, then copy its `inputs/cprime.py` and `inputs/*.sql` over that checkout's
`candidates/` files and `inputs/run.py` over `reproduction/run.py`. Run the normal
Python command with a fresh external output directory. Do not overlay the final
reviewed checkout. The old run is expected to fail T05 and T08 and must not be
reported as a final-candidate regression. Its `candidate.sql` is the complete
executed generated DDL, not merely a suggested fragment.

## Independent-review corrections (v2)

The first frozen candidate required Parent and Transfer clock/provenance equality.
That was an unselected restriction, not a demonstrated architectural necessity.
After independent review reproduced it, v2 added the explicit complete Parent
provenance coordinate to the support projection and removed the clock-equality
assumption. The new T05 case admits an earlier, independently attributed Parent
report as explicitly supplied support, preserves both originals, and rejects
cross-paired or missing support coordinates. Whether a separately attributed
Parent report qualifies semantically for a particular operation remains a
separate admission/evaluation question; the FK does not infer a winner.

Independent review also reproduced a Resource replay blind spot: conflict-ignore
could skip the coordinate consistency CHECK when an existing Resource key was
supplied with contradictory identifying metadata. V2 adds
`cp_resource_no_rebind` before insertion; T08 rejects changed payloads through
INSERT, IGNORE, REPLACE and DO NOTHING. The stored row had remained valid in v1,
but silently ignoring inadmissible input was not evidence of validated replay.
The first freeze and all original receipts remain retained separately.

## Independent-review correction (v3)

Independent review found that v2 typed admission checked the Parent/report FKs
but omitted the existence check for arbitrary-length declared Provider Repository
members in `transfer_event_report.members_json`. A structurally valid report
could consequently be admitted while such a member was absent. V3 checks each
full member ResourceKey inside the Transfer savepoint, before any group or
endpoint writes. This is an application dependency check, not an added FK or a
Python lookup disguised as one; SQL and row-local predicates are unchanged.

The added T11 case proves missing-member refusal leaves the original child and
Parent report intact, creates neither the missing member nor a durable event
unit, and admits the exact original report only after the actual selected member
arrives and the report is supplied again. The unresolved Provider endpoint stays
unresolved; no Core endpoint or observed NULL is invented. Exact replay preserves
membership, scope, original observation time and provenance. All v2 receipts and
the independently reproduced counterexample remain retained.

## Original timestamp input correction (v4 harness)

Independent review additionally reproduced pre-affinity time acceptance through
the experimental Transfer admission helper: Python booleans, floats and numeric
strings could become SQL INTEGER values. V4 calls the actual baseline
`validate_observation_us` for the report and every supplied endpoint before
replay comparison or insertion. This also prevents Python's `True == 1` or
`100.0 == 100` equality from making invalid original input look like exact replay.
The baseline time-validator source hash is included in the input manifest.

The added T12 case rejects those input types, zero/negative/out-of-range values,
and accepts genuine positive integers and `None` without changing their meaning.
A direct SQL control deliberately demonstrates SQLite's INTEGER-affinity
coercion: stored-value CHECKs cannot validate original Python input types. This
is an admission-layer correction; candidate SQL and row-local predicates are
unchanged from v2. V3 author receipts remain retained rather than overwritten.
