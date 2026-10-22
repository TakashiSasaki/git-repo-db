# ADR 0031 I6 wire, admission and Exchange boundary contract

Status: **Design Author freeze for separate non-Author review; implementation
not performed or accepted.** Task D6, 2026-10-22 UTC. This is an implementation
contract under accepted ADR 0031, not a new ADR or an amendment to an accepted
decision. Transfer remains refused by both SQL fences and ordinary routes.

Read with the [vectors/test matrix](adr0031-i6-vectors-and-tests.md) and
[source map, implementation graph and review handoff](adr0031-i6-change-map-and-handoff.md).
Requirement IDs below are stable across I6-A/B/C.

## 1. Authority and baseline

The fixed decisions are A3, B3, U3=C′, U4=B, U5=A, U1=B, U2=A, U2-E2 and
G3=A in [ADR 0031](../adr/0031-generalized-context-resources.md). The
[schema contract](../architecture/context-resource-schema.md),
[original handoff](context-resource-design-handoff.md), [I4](adr0031-i4-transfer-sql.md),
[I5](adr0031-i5-typed-admission.md), and the reproduced
[independent findings](evidence/adr0031-i5/independent/findings.json) are inputs.
Where the historical I5 report describes an I8 failure as a missing dependency,
the accepted G3=A decision controls: I8 support is permanently ineligible for
this I7-native Event. Do not edit that historical evidence to reconcile wording.

Live GitHub PRs and all remote branches were fetched before authoring. No I6
design PR was found. Initial #130/#131/#132 and main matched the assignment.
The owner then explicitly selected **newest #133 base** in this task, superseding
the assignment's exact-#132 stacking instruction:

| Reference | Exact commit | Tree / branch |
| --- | --- | --- |
| #130 independent I5 review | `b4ede5d8a87f3ce7b1f6df8fda5b3051c3865ba2` | `review/adr0031-i5-independent-20261022` |
| #131 accepted ADR 0032 docs | `01b427e392243e06eb9be0e3a50bb09ecacd0d5f` | `docs/sqlite-runtime-policy-20261022` |
| #132 tooling ancestor | `a022dd3efb9c8116cf9dc0abc13ab1d5bbc88e37` | `1fa9c2624a3913d97439f16fcd6bc8641c56b17f` |
| **Sole design parent: #133** | `f16e5b1713bde9a2f18263a25397c4b450fd5773` | `6bfa580baafa9f6a117b7a0b610c4e65cd031b86`; `fix/adr0032-host-runtime-20261022` |
| main, read only | `cb532242c7aa86c6af5b6232b71c0906ea38f5c5` | Not the design base |

#133 changes tooling, not the investigated product modules. Inspect both its
effective tree and #132; do not apply this source map to main alone. The PR
description binds final Author HEAD/tree and change inventory. A file cannot
contain the hash of its own final Git tree; that binding is external to it.

**R01 — Invariants.** `resource_relations` remains the sole semantic Parent
authority. No new Parent table/header, writable duplicate Parent, winner,
Mapping Witness, Publication, pending original-bearing queue, surrogate key,
API archive, compatibility shim or real-data migration. A complete child can be
registered before its namespace Resource or any Parent report. Native
identification metadata does not assert semantic Parent existence. Native-I7
typed SQL enforcement remains additional to complete Parent/Event report FKs.
Identity parsing may check a known native contract; it must never infer a report.

## 2. Versioned wire and finite grammar

**R02 — Version.** I6-B introduces exactly
`git-repo-db/adr0031-exchange-v5`. It replaces v4 for new-format authoring and
intake; no v4-to-v5 inference or compatibility decoder is required in this
unreleased product. A v5-only reader rejects v4, unknown versions and missing
`format` with `UNSUPPORTED_WIRE_VERSION`, before domain mutation. Existing v4
receipts stay historical. An opaque Resource kind is permitted within v5; an
unknown version, field envelope or reserved operation is not. I6-B may expose a
pure codec while all product Transfer gates remain in force.

V5 retains the exact top-level field set, required selection fields, Core section
row grammars and Context section names of `domain/exchange.py` and
`domain/exchange_rows.py` at the pinned base, with only the following row changes:

| Row | Exact v5 fields / change |
| --- | --- |
| `context.resources` | Existing `service_instance_uuidv4`, `resource_kind`, `provider_resource_id`, plus mandatory `identifier_namespace_kind`, `identifier_namespace_id`, `document_kind`, `provider_document_id` |
| `context.resource_repository_relations` | Existing eight fields plus mandatory `event_report_members_json`, `event_report_scope_json`; both NULL for non-Transfer roles, both canonical strings for Transfer endpoints |
| All other rows | Exact pinned `ROW_KEYS` profiles, types and known semantic validators; no optional extra-field escape hatch |

The inherited top-level fields are `format`, `sender_catalog_instance_uuidv4`,
`package_id`, `exported_at_us`, `repository_uuidv4`, `selection_scope`,
`selection_report`, `core`, `context`, `digest_sha256`. The Repository envelope
coordinate is preserved and is not a blanket grant over Context. Both section
fields are present; NULL means section absent,
otherwise every named section array is present (an empty array is allowed).
Provider, Repository, Source and membership configuration stays restricted to
the existing non-executable domain-registration grammar, with no Access secrets,
URLs, executable routing or approvals. No new `verified` field is introduced.

**R03 — Parsing and canonicality.** Strict UTF-8, Unicode scalar strings,
duplicate-object-key rejection, finite JSON, exact field sets and strict
primitive types apply to received bytes and caller-owned decoded objects.
Reject missing required fields; NULL is legal only where the field's declared
contract allows it. Never translate an omitted field to NULL. Optional fields
inside existing field-value/provenance contracts retain their existing omitted
versus NULL semantics; that is not permission to omit row-envelope keys.

`ResourceKey := [UUIDv4, nonempty-kind-TEXT, CanonicalIdentityTEXT]` in embedded
references; resource rows use the named triple. UUIDs use canonical lowercase
hyphenated UUIDv4. Identity grammar is exactly String or recursive Array of
IdentityValue, serialized by `resource_identity.encode_identity`; its ASCII JSON
TEXT remains a string in outer JSON, even for a scalar ID. Numbers, bools,
objects, NULL, coercion, trimming, normalization and alternate serialized
spellings are forbidden. Keep BINARY equality at every key/reference occurrence.
The [accepted canonical vectors](../architecture/context-resource-schema.md#canonicalization-specification-vectors)
remain normative, including meaningful `""`, `[]`, `[""]`, `[[]]` distinctions.

For report `*_json` fields, use the existing Context canonical profile
(`ensure_ascii=True`, sorted keys, compact separators, no nonfinite numbers),
strictly parse and require exact roundtrip text; do not repair transported keys.
The **outer digest** retains `ensure_ascii=False`, sorted keys, compact UTF-8,
and hashes the entire package dictionary excluding only `digest_sha256`.
Receiver recomputes SHA-256; a corrected package requires a new PackageKey.
Checksum integrity proves neither Provider origin nor semantic eligibility.

**R04 — Limits.** Inclusive per-identity caps are 262,144 canonical ASCII bytes,
32 array containers on a path and 4,096 nodes. Keep the outer 32 MiB, depth 32,
200,000-element caps; embedded JSON/key parsing counts toward aggregate work and
depth, including escaped size. Existing registration caps (65,536 bytes, depth
12, 2,048 elements) remain. Default selection is depth 8, 10,000 units, 16 MiB,
10,000,000 work units. Configured values must be finite strict nonnegative
integers within the existing 100,000,000 setting ceiling and outer hard caps;
zero permits no corresponding expansion/work. Count owner/report/member checks,
DB dependency reads, decoded embedded values and replay work, not only inserts.
Charge cumulative actual work across a request's retries/continuations under
ADRs 0023–0025; rollback does not refund work. Scan bounds before allocation or
recursive decoding; cyclic in-memory inputs also stop finitely. No truncation,
partial atomic report, silently raised budget or hidden staging at a limit.
An individually valid ID need not fit an enclosing unit/package.

## 3. Identification, generic Relations, Collections and Source

**R05 — Identification.** The four mandatory metadata fields encode exactly
`ResourceIdentification.columns`, validated against the same ResourceKey:

| Native contract | namespace kind / ID | subtype / local ID |
| --- | --- | --- |
| Unscoped kind outside reserved scoped kinds | NULL / NULL | NULL / NULL |
| Global `document` | NULL / NULL | NULL / complete canonical Resource ID TEXT repeated |
| Known scoped review/comment/thread/PR-document | Allowed namespace kind / canonical namespace ID TEXT | nonempty subtype / canonical native-local ID TEXT |

The scoped Resource ID must equal
`J([namespace_kind, namespace_id_TEXT, subtype, decoded_native_local])`.
Use only the canonical-TEXT namespace profile. Known namespace sets remain those
in `resource_identification.SCOPED_NAMESPACES`. Dispatch by the explicit native
contract, never an array shape; malformed PR documents cannot fall back to global
or opaque kinds. Unknown kinds use the unscoped metadata form while their
IdentityValue may itself include genuine native scope coordinates. No new kind
registry or arbitrary tags. Global/scoped Documents can own children. Export and
import preserve all seven resource columns; duplicate admission rechecks them.

**R06 — Whole generic reports.** A ResourceRelation carries owner ResourceKey,
nonempty relation kind, ordered unique ResourceKey members, original canonical
provenance/scope and original positive-or-NULL observation time. The existing
seven direct relation PK coordinates identify the report; time is immutable
payload. Preserve order, empty membership and attributed alternatives; do not
split or union reports. Reserved `parent`, Provider-role reports and Transfer
keep their typed contracts. Unknown relation names preserve a bounded list of
actual references; the name supplies no business semantics or extra traversal.
Only explicit common member dependencies may expand selection.

A Collection header is `(owner, collection_kind, provenance_json)` with immutable
scope. Its real terminal is `(owner, collection_kind, provenance_json,
observed_at_us, terminal_state, members_json)` with ordered unique members and
required positive observation time. V5 flattens a header plus each real terminal
into the existing Collection row profile. `terminal_state` is exactly `unknown`,
`partial` or `complete`; `complete` with `[]` is known empty, `partial` with `[]`
is a real partial observation, and no row means no terminal. Never manufacture a
terminal from a surviving member list, transport end or omission diagnostic.
Same-time different member/state candidates remain unresolved; later observations
do not union them or borrow an older complete terminal. Repeated header scope
must match. Header-only storage, if encountered, conveys no terminal or Coverage;
this wire profile withholds it rather than inventing a row.

**R07 — Source/Coverage.** Source registration UUIDs are portable; local integer
Source IDs are not. Source inventory is its existing set-valued canonical
repository list (sorted), unlike ordered Collection membership. Preserve actual
`terminal` boolean and state; no terminal does not become known empty. Partial
inventory never deletes an existing positive Source–Repository pair. Validate
Source service binding and every referenced known-positive pair.

Keep exactly the five Coverage claim columns. Use existing `CoverageScope`,
`validate_context_proofs`, `terminal_key`, `terminal_slot` and
`preserve_context_coverage` contracts: proof must match every original terminal
field, original claim, required scope and observation relation. Withholding any
relevant terminal alternative withholds its associated completeness claim/proof;
never relabel a complete assertion as partial or fall back to an older complete
candidate. Details stay advisory. Individually admissible Resources/fields may
survive withheld Collections, inventories, relations or Transfer units.

## 4. Independent originals and endpoint declaration

**R08 — Mandatory original Parent.** Admission-capable `TransferEventReport`
must require an explicit `ParentReportKey` and its original observed time; remove
all Event-based defaults from constructors, `from_targets`, wire and recovery
reconstruction. The existing direct key is:

```text
ParentReportKey = (child ResourceKey, "parent", members_json,
                   provenance_json, scope_json)
scope_json = J({"clock": original_Parent_FieldClock,
                "document_kind": actual_subtype_or_null,"state":"complete"})
```

The flattened key has seven SQL components. `members_json` is the original
singleton Parent ResourceKey list. The Parent report row carries its own
`observed_at_us`; this is an immutable payload comparison, not another key.
The Event support's three `parent_*_json` scope strings quote that exact key's
members/provenance/scope and bind the same child. Lookup may use only the complete
key, never "any Parent for Event", native-ID traversal, latest clock or a winner.
The accompanying Parent row may come from the package or an authorized validated
local dependency. Compare supplied original time against the actual row.
There is no inferred Parent-time field in Event scope: decode the actual Parent
observation row by this full key before constructing an admission-capable object.
If its coordinates are explicit but that row is unavailable, return
`MISSING_DEPENDENCY`; if coordinates themselves are absent, return
`INCOMPLETE_ORIGINAL_REPORT`. A validated authorized local original row may supply
its genuine observation time, never the Event clock, arrival time or NULL default.

```text
EventReportKey = (Event ResourceKey, original_Event_clock_json,
                  original_Event_provenance_json)
Event relation PK = (Event ResourceKey, "transfer_event_report",
                     original_members_json, original_provenance_json,
                     original_scope_json)
```

One EventReportKey owns its whole immutable members/scope/time payload. Parent
and Event clocks/provenance/observation times are independent; only endpoint
clock/provenance/time must equal its own Event's originals, including NULL
equality. A full Parent row with clock 50 and provenance P is valid support for
an Event clock 100 with provenance E. Missing original Parent coordinates are
`INCOMPLETE_ORIGINAL_REPORT`, never synthesized evidence. A complete child still
admits independently. Use a separate `IncompleteTransferCandidate` for bounded
in-memory normalization/diagnostics if needed; it cannot serialize as an admitted
Transfer, call store admission or persist in a queue. This design chooses
**mandatory originals in admission-capable types**, not optional defaults.

**R09 — Explicit original endpoint set.** Require a
`ProviderEndpointDeclaration` at construction, before selection/filtering. It is
a total declaration over `transfer_from_repository` and
`transfer_to_repository`; each role is `not_reported`, `explicit_null`, or
`provider_repository(ResourceKey)`. `not_reported` means genuinely absent in the
original normalized Provider report under its checked adapter contract, never
lost/filtered/unknown. At least one role is reported. A partial Provider response
that cannot establish this distinction yields an incomplete candidate.

This is a typed view of the existing nine-key Event scope, **not a second stored
authority** or a new wire section. Serialize its reported roles into mandatory
`provided_roles`, and its Provider IDs into mandatory
`from_provider_repository_id` / `to_provider_repository_id` (canonical ID TEXT or
NULL). The mandatory `endpoints` list contains the original translated endpoint
declarations `[role, canonical_target_json]`; it is captured before filtering,
not reconstructed from endpoint rows. The other six scope fields remain `clock`,
`event_type`, `parent_members_json`, `parent_provenance_json`, `parent_scope_json`
and `endpoints` itself. Scope has exactly the nine I4/I5 keys. All are required.

| Original role state | Scope / received endpoint obligation |
| --- | --- |
| `not_reported` | Role absent from `provided_roles`; Provider ID NULL; no endpoint for that role. Genuine one-sided report allowed. |
| `explicit_null` | Role present; Provider ID NULL; exactly one declared and received target string `"null"`. SQL NULL/missing row is not explicit NULL. |
| Provider repository, unresolved | Role present; Provider ID non-NULL; zero translated endpoints for the role. Preserve Provider-only state; no invented Core UUID or null endpoint. |
| Provider repository, resolved | Role present; Provider ID non-NULL; nonempty exact target set with complete original MappingSupport; received set equals declarations. Multiple genuine mapping alternatives stay distinct. |

Sort the set-valued `provided_roles` and unique endpoint pairs by exact role then
target text; reject duplicates/noncanonical order. This ordering does not reorder
Collection/relation members. A declared mapped endpoint that is absent from
received rows is `INCOMPLETE_ENDPOINT_SET` regardless of receiver rows, import
order or repeated delivery. A declared Provider role lacking usable qualification
may be retained as Provider-only attributed evidence; it creates no resolved
Transfer effect. Do not downgrade a declared resolved endpoint to unresolved.
Unqualified supplied mapping support withholds the dependent unit.

The admission type takes both the explicit original declaration and the exact
received endpoint tuple; compares them; and checks that its encoded scope matches
the supplied scope byte for byte. No `endpoints=None`, inferred `provided_roles`,
or completion from existing SQL rows is permitted. `selection_truncated` and
`omitted_roles` are diagnostics on incomplete candidates, never admissible report
data. Sender filtering withholds the complete Event report plus **all** endpoints
when any required part is excluded. It cannot rewrite the declaration. Adversarial
coherent rewriting cannot be authenticated by SHA-256: retain only the allowed
attributed-report meaning, and never grant live verification/eligibility from it.

## 5. Enforceable selection and authorization boundary

**R10 — Public API.** Introduce domain/port types with this stable shape (names
are proposed public APIs, not claims of current implementation):

```text
AdmissionContext(principal, operation, selection, authorizer, budget)
operation := provider_intake | exchange_import | exchange_export | salvage_merge
selection := frozen Resource/Repository/Source seeds + bounded closure policy
             + explicit all_selected flag (and existing Core/OID controls)
authorizer.check(principal, operation, DependencySet, current_policy_revision)
Context.admit_transfer_event(report, *, admission: AdmissionContext)
ContextStore.admit_transfer_event(report, *, admission: AdmissionContext)
    -> insert | duplicate | typed refusal
```

Every external-input mutation entry point, including generic relation,
Collection, field, mapping and Source admission used by these routes, requires
this context. There is **no default unrestricted context**, nullable callback,
wire-deserialized permission grant or exported "trusted=True" switch. The
composition root supplies a local authorization port; a missing context or
unsupported policy implementation fails closed before duplicate lookup/writes.
The store/facade is bound at construction to the trusted local policy service;
it verifies that the context's policy handle belongs to that service. A caller
cannot supply a replacement allow-all authorizer or self-assert another
principal. The principal comes from the local authenticated invocation/session
boundary, never a Provider field, package, claimed issuer or Source UUID.
An internal structural writer may be private behind this boundary but is not an
alternative public untrusted route. Disposable tests inject an explicit test
authorizer; production does not infer trust from stack frames or Python type
names. The raw SQLite handle is trusted infrastructure, outside caller-facing
authorization; its structural constraints still apply. SQL alone cannot enforce
principal permissions.

Selection uses the existing four seed dimensions; omitted selection is rejected
unless an explicit local `all_selected` request exists. Empty sets select none.
Sender selection metadata describes its export, never authorizes the receiver.
Receiver intersects it with its own requested bounded closure and current local
permission scope. A service registration grants no Resource access. Parent/member
dependencies enter the effective selection only through the explicit bounded
dependency policy; no namespace traversal, all-Provider expansion or permission
expansion. Resources need an independent Resource grant; Repository permission
alone is not authority for unrelated globally identified Resources. Source grants
are separately checked and cannot be inferred from a claimed provenance string.

**R11 — DependencySet and current checks.** Enumerate every referenced Resource
(Event, native I7 coordinate as a Resource dependency for Transfer only, reported
Parent, every report/member, both Provider repositories, support subjects), every
Core Repository target, every provenance Source registration, relevant known
positive Source–Repository association, complete MappingClaimKeys and referenced
Disposition/replacement claims. Parent/member presence in SQL never grants access.
Where provenance identifies an external attributed issuer without a local Source
registration, preserve the allowed external claim and its omission/NULL state;
never invent a Source. Any actual Source reference must resolve and be authorized.

Before admission **and exact replay**, under the same operation snapshot, check
effective selection, current permission for every dependency, original native and
event semantics, full Parent key/time, selected members, Source service/known
positives, mapping support and current qualified evaluation (including any
operation-scoped Disposition evidence). Reusing the original mapping payload is
required; recalculation must not mint a new Event provenance or bind a different
target. Existing rows, sender flags and the digest are insufficient. A receiver
may preserve lawful attributed reports without claiming authenticated Provider
origin. Normalized event type/native-contract checks and current operation
evidence are distinct from structural FK existence and origin authentication.

The authorizer issues a short-lived local policy revision/lease held through
commit. Revocation before commit invalidates the lease and rolls back; acquisition
must not hold a DB write transaction over network calls. Read dependencies in a
consistent snapshot, acquire the normal writer lock, and recheck snapshot/policy
revision and qualification inside the write unit. Restart bounded validation on
revision drift, charging actual work. Never cache a grant in a report or durable
"verified" column. A prior accepted unit can remain historical evidence after
revocation, while replay/export/current effective use still requires fresh checks.

**R12 — Outcomes.** Parse/known-contract failures refuse the unit, with no opaque
fallback. For syntactically valid identifiers, perform authorization before local
existence lookups; do not reveal denied dependency contents/existence. Use:

| Code | Meaning / allowed next action |
| --- | --- |
| `PERMISSION_DENIED` | Local policy refuses a dependency or operation. Zero unit writes; no existence-sensitive details. New authorization and explicit resubmission required. |
| `OMITTED_BY_SELECTION` | Needed part outside effective selection. Withhold whole dependent unit; selecting it later still requires explicit resubmission. |
| `MISSING_DEPENDENCY` | Authorized selected exact dependency unavailable. No fabrication; original resupply after arrival. |
| `UNQUALIFIED_MAPPING` | Supplied mapping support fails current operation qualification; preserve independent lawful reports, no resolved effect or substitution. |
| `QS10_PARENT_INELIGIBLE` | Reported I8 differs from E's native I7; permanent for this support. Retain lawful I8 Parent report separately. |
| `INCOMPLETE_ORIGINAL_REPORT` / `INCOMPLETE_ENDPOINT_SET` | Original coordinates/declaration or received endpoint set incomplete. No conversion to one-sided. |
| `INPUT_LIMIT` | Actual finite limit stop; preserve completed independent units and charge work. |
| `IMMUTABLE_REPLAY_CONFLICT` | Same immutable key, changed payload/time. Reject changed unit; never patch or choose a winner. |

For multiple applicable outcomes, syntax first, then authorization denial, then
selection omission, then permanent semantic/type violation, then missing or
unqualified dependencies, then replay comparison. No DB-dependent diagnostic
precedes authorization. Ordinary untrusted bad input is not itself stored
corruption. A proven invalid retained authoritative row invokes Recovery Stop.

## 6. Closure, ordering, replay and transactions

**R13 — Closure.** From a consistent snapshot, start only with explicit seeds.
Enumerate actual common report/member, Collection, Source/proof and typed mapping
dependencies. Resource registration needs Provider registration plus complete
identification, **not a namespace/Parent Resource/report**. Parent relations need
their actual referents. Transfer needs its exact Parent report and Event, declared
Provider roles/endpoints, mappings and Source supports. Collection/proof units
need all original members/terminal alternatives required by their scope. Do not
traverse identifiers to infer a Parent. Visit each semantic dependency once for
closure; charge all actual checks and cap edges/work as well as nodes/depth.
Cycles stop via visited sets. No topological-sort requirement may reject a
lawful cyclic generic graph: register independent Resources first, then whole
reports. Cyclic impossible support dependencies are withheld with diagnostics.

Sender closure can add permitted dependencies only under the requested policy;
receiver computes its own closure and does not trust sender reports. If a member,
Source, target, support or real terminal is missing/denied/unselected/over-limit,
withhold that whole atomic unit and associated completeness, not just the member.
Selected, authorized, validated local dependencies may satisfy receiver closure;
their mere existence is insufficient. Sender must itself validate the full unit
before emitting it. Diagnostics use bounded codes and authorized coordinates,
never full unadmitted original payloads. No durable pending original-bearing jobs.

**R14 — Admission order and replay.** Validate whole package envelopes/digest
before mutation; plan independent units in memory. Admit registrations and all
complete Resource identities without Parent ordering, then Source positives,
mapping claims/Dispositions, generic and Parent reports, then whole Transfer
units, then genuine terminals/proofs/Coverage. Validate and admit within snapshot
and authorization fences. This corrects the current Transfer-before-Parent import
order. Each unit is transactional; a withheld unit does not invalidate independent
child identity. Malformed envelope/digest yields no package writes.

PackageKey binding/checkpoints remain Operational only, using Q-E7–E10's current
precommit and loss rules. Package replay must re-evaluate current selection,
permission and eligibility before any cached success; receipt existence is not
admission authority. Same PackageKey with changed content is refused. Exact
accepted report replay is `duplicate` only after all current checks, with no new
observation time/provenance. A previously refused unit is never auto-replayed on
Parent/mapping arrival, reopen, checkpoint resume or reverse Exchange. Explicit
resupply preserves originals. A changed filtered package needs a new PackageKey;
reversing/onward forwarding preserves the original report keys, not the relay's
clock. An originally unresolved Provider role cannot be silently rewritten in the
same immutable EventReportKey when a mapping arrives; explicit original resupply
may only add support through a separately justified genuine domain observation,
never a fabricated new clock/provenance or amendment of the old report.

**R15 — SQL and rollback.** Keep I4's complete ParentReport FK, native-I7 typed
Resource FK/UNIQUE, endpoint-to-complete-EventReport FK, BINARY comparisons,
mandatory projections, row-local bounded deterministic UDFs, pre-conflict guards
and immutable originals. Do not weaken them to satisfy new wire cases. Validate
original timestamp/input types before SQLite affinity: strict int 1..int64-max or
NULL for nullable observations/Provider times; required Coverage/terminal times
are positive non-NULL; native Git times retain their signed contract. Reject
bool/float/numeric strings and missing required fields before binding.
Transfer Event clock `at_us` remains a required positive integer as in I5;
nullable clocks on other lawful report types retain their separate contracts.

The writer uses `SAVEPOINT p1_transfer_event` around Event report and **all**
endpoint INSERTs, validates complete rows after writing, and rolls back on any
constraint, policy-revision, postcondition, release or outer COMMIT failure.
Never catch an endpoint failure and return partial success. Dependencies admitted
as independent earlier units need not roll back, but no partial Transfer row or
mutated preexisting original may survive. Keep required FK/CHECK/recursive-trigger
settings and verified schema/UDF registrations on every supported connection.
Arbitrary direct SQL is not claimed to provide authorization, original input-type
validation or whole-unit endpoint atomicity. The in-flight second-INSERT test is
mandatory; a preflight refusal does not test SAVEPOINT rollback.

**R16 — Fence state.** I6-A replaces asymmetric `has_transfer_fence()` inspection
with a full expected-state check: both expected definitions present = staged;
only one/malformed/uninspectable = unsupported schema/fail closed; neither is
permitted only in explicitly isolated synthetic fixtures, or the later reviewed
integrated schema that retires them. Ordinary schema validation remains mandatory.
No helper result may enable Transfer when one fence is missing. I6-A/B/C retain
both packaged SQL triggers and normal application refusals. Identification wire
refusal can retire for reviewed non-Transfer v5 routes in I6-B/C; that does not
retire any Transfer fence.

## 7. I7, I8 and final gate

**R17 — Recovery.** I7 owns enduring stored validation, Task G G-R1 candidate
global/scoped exposure, schema/FK/UDF/trigger tampering checks, pairing and
backup/recovery. Decode with trusted code without executing recovered schema.
Reconstruct explicit complete original reports and all endpoint references;
recheck native-I7 and full support, actual terminals, Source positives and
Coverage. `foreign_key_check` alone is insufficient. Keep lawful I8 Parent
reports without using them as Transfer support. Proven retained-data corruption
stops ordinary reads/writes/export/Search/normal backups immediately under ADR
0026; preserve source read only, salvage as untrusted candidates, restore fresh
paired Core+Context with separate Access scope, validate merge before activation.
Salvage intake uses the same mandatory authorization boundary and current policy;
no sender/stored flags authorize recovery or hidden replays. Historical retained
evidence and current qualified effectiveness are separate; policy revocation
alone is not corruption or permission to delete a report.

**R18 — Query.** I8 owns semantic Parent querying separately from identifier
namespace filters, generic unknown/global/scoped/non-leaf reads, Transfer summary
and Source/Coverage/conflict projection, Search/fallback/rebuild agreement and
generation/snapshot fences. It must not infer Parent by ID, select a report
winner, use ineligible I8 support, or treat Provider-only endpoints as resolved.
Stored rows/Search flags cannot bypass current qualified interpretation or caller
permission. Basic generic reads may follow I6-B; Transfer query acceptance waits
for I7 and integrated tests. No arbitrary structured Search promise is added.

**R19 — Retirement prerequisite.** A separately authorized integrated PR may
remove both SQL fences and ordinary Transfer refusals only after non-Author
acceptance of frozen I6-A/B/C, I7 and I8 inputs, end-to-end permission/selection
and recovery/query routes, both distribution forms outside checkout, all SQL
adversarial cases, and honest full regression reconciliation. Update DDL/UDF
checks/fingerprints and every normal route together; no piecemeal trigger drop,
runtime flag or private production bypass. This design PR authorizes no such
retirement, merge, deployment, release, P8 or real Provider/catalog operation.

All new executions follow [ADR 0032](../adr/0032-environment-sqlite-validation.md):
the selected environment Python's actual SQLite only, measured identities and
unchanged product safety/capability floors. No additional test SQLite engines,
version matrix or loader replacement. Historical two-engine receipts are facts,
not instructions. Design test vectors are specifications, not executed results.
