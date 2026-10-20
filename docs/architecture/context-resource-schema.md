# Generalized Context Resource schema contract

This document accompanies [proposed ADR 0031](../adr/0031-generalized-context-resources.md).
The owner's A3/B3/U3=C′/U4=B/U5=A/U1=B/U2=A/U2-E2 logical selections are fixed.
This complete package is proposed; physical design and the numerical engineering
bounds below are not separately approved. Nothing here changes runtime behavior.

## Identity, meaning and report boundaries

`ResourceKey = (service_instance_uuidv4, resource_kind, provider_resource_id)`.
Keep the existing primary-key columns and service UUIDv4 contract. Kind is a
nonempty stable string under the existing key rules. It is interpreted within
the service namespace; a reserved known name continues to invoke its explicit
common typed contract. Display names are fields. Same unknown kind text in two
services is no evidence of semantic equivalence. Do not add global kind registry,
mandatory Provider prefixes or universal tags.

An adapter must supply a complete native identification contract before producing
a key. Service-wide IDs need no artificial parent. A native local ID needs its
genuine namespace coordinates. Native ID namespace distinctions (for example an
opaque API ID versus a decimal ID) cannot be collapsed on coincident text. An
adapter may use a meaningful string/array discriminator when its native contract
needs one; the common layer does not prescribe a tag for every Resource.

For existing PR Documents, retain actual PR identity, document kind and Provider
document ID. The current implementation's four-component parent/document encoding
is evidence of that scope, not permission to require every future Resource to
have a registered PR. A future encoder must preserve those semantic coordinates
using the common grammar consistently. The existing document encoder embeds
`parent.provider_resource_id` as a **string**, not as its decoded identity array.
Preserve that distinction in a future explicit encoding contract; swapping it
for a decoded nested value is another representation change, never an incidental
parser repair. A compatible engineering proposal is to retain the four-component
layout with the parent's new canonical identity TEXT as that string component.
Native recursive-array identities elsewhere need not use this document layout.
Exact adapter spellings/normalization are outside this package.

There are three distinct things:

| Thing | Authority and equality |
| --- | --- |
| Resource | Complete native identity under the key triple; neither text hash nor observation time |
| Content | Existing exact retained UTF-8 text and its SHA-256; identical content does not merge Resources |
| Report/observation | Its actual semantic coordinates, entire coherent membership/scope, original provenance and clocks; replay is not another observation |

Document is an ordinary Resource kind with its own identification contract.
Documents can participate in relationships and have children. Text on an Issue
may remain an Issue field; creating a Document requires a genuine Document entity.
No new UUID, row ID, content hash, arbitrary tag or acquisition clock supplies a
missing native coordinate. Existing repository/service/Capture identities remain.

## Common grammar and canonical equality

```text
IdentityValue := String | Array<IdentityValue>
```

Strings contain Unicode scalar values. Arrays preserve order and nesting.
Numbers, booleans, objects and null are invalid at **every** identity depth.
This restriction is confined to Resource identity; existing fields, clocks,
provenance and other JSON contracts retain their own permitted value types.
SQL NULL is forbidden in all three key columns. JSON `null` is not an empty ID.

Store canonical JSON TEXT for **every** ID, including scalar strings. Native
`731` represented as the common string value becomes SQL text `"731"` (including
the JSON quote characters), rather than unquoted SQL text `731`. Encoding is
reversible and adds no identity-bearing surrogate. An empty native string is
stored as two quotes; an empty array is stored as two brackets. Both are nonempty
SQL text. Empty values/components must be genuinely complete coordinates under
the adapter contract, not placeholders. The database can validate syntax but
cannot infer Provider-side singleton or namespace completeness.

### Shared serializer and parser contract

Reuse the compatible **identity subset** of the project's existing
`domain/p1_context.py:canonical` and `_parse_canonical_json` profile at the
[fixed product source](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/domain/p1_context.py#L178).
It uses `json.dumps(..., ensure_ascii=True, sort_keys=True,
separators=(",", ":"), allow_nan=False)`. Object sorting is irrelevant to the
identity grammar; it does not permit objects here. No RFC 8785 conformance claim
is made. Do not change the existing general JSON profile as a side effect.

The shared identity encoder must first validate exact string/array input types,
Unicode scalar validity and finite bounds, then serialize:

- No whitespace outside strings, no BOM or trailing newline/data.
- Strings use JSON quotes; `"` and `\` escape as `\"` and `\\`. Solidus `/`
  is unescaped. Backspace, form feed, newline, carriage return and tab use
  `\b`, `\f`, `\n`, `\r`, `\t`; other U+0000–U+001F controls use lowercase
  `\u00xx`. Printable ASCII U+0020–U+007E is literal except quote/backslash.
- U+007F and non-ASCII BMP scalars use lowercase four-digit `\uxxxx`.
  Supplementary scalars use their lowercase UTF-16 surrogate-pair escapes
  (for example U+1F600 becomes `\ud83d\ude00`). A valid scalar encoded as that
  pair is allowed; lone/misordered surrogates or an unpaired in-memory surrogate
  are rejected. Reject invalid UTF-8 before JSON decoding.
- Preserve scalar sequence exactly. No case folding, trimming, Unicode
  normalization, array sorting, flattening or implicit type coercion.

The canonical-key parser takes serialized TEXT, enforces finite byte/structural
bounds before unbounded decoding, parses strict JSON, validates the restricted
grammar and Unicode, re-encodes through the same encoder, and requires **exact
text equality**. It rejects noncanonical alternative spellings instead of silently
repairing a key. Reject duplicate keys at the general JSON boundary; objects
are invalid identity values regardless. Reject invalid types before SQLite
affinity or a programming language's bool/int equivalence can coerce them.

For an admitted Resource, equality means the same canonical UUIDv4, exact stable
kind and exact canonical identity TEXT. SQL PK/FK/unique-index comparison must
use the same exact BINARY text rules, with no NOCASE/custom normalization.
Queries, joins, generated references, JSON-embedded ResourceKeys, Collection and
Coverage owners/members, Claim/Disposition supports, cursors and Exchange must
use that same representation. In an enclosing JSON ResourceKey,
`provider_resource_id` remains a **string containing canonical identity JSON**;
the outer serializer escapes that string normally. It is not sometimes decoded
inline and sometimes double-encoded. Derived extraction must return exactly the
stored canonical key TEXT. Compare canonical representations, not SQL-coerced
numbers or decoded array sets.

### Three different boundary operations

| Operation | Required behavior |
| --- | --- |
| Encode an already validated identity value | Adapter performs native identification normalization first. The common encoder validates only its allowed types/scalars/bounds and emits one canonical text. Lossless numeric-to-string conversion is an explicit adapter operation, never common coercion. |
| Receive serialized canonical key | Validate exact received text, grammar, bounds and canonical spelling. Reject a noncanonical key; do not normalize it into a different durable reference behind the sender's back. |
| Verify Exchange package digest | Apply the supported version's existing outer canonical-data rules to the declared hashed scope and compare the receiver's SHA-256 before domain admission. This establishes content consistency, not Resource validity or origin authenticity. Independently validate every embedded canonical key and typed dependency. |

An outer package can be digest-consistent and still contain a noncanonical or
ill-typed identity; domain admission must refuse it. Do not mutate an embedded
identity after PackageKey/digest binding and claim the original digest identifies
the changed content. Corrected content requires a new package ID under Q-E7.
The current outer profile (`domain/exchange.py:162`) uses `ensure_ascii=False`,
sorted object keys, compact separators, finite numbers and UTF-8, over the full
package dictionary with **only `digest_sha256` removed**. It includes format,
sender/package identity, export time, selection/report, Core and Context. Outer
input spelling may be canonicalized for that digest; an inner ID is still a
string whose backslashes/text remain digest-significant. Do not substitute the
identity encoder's `ensure_ascii=True` for this existing envelope profile.
Envelope canonicalization is not native ID normalization, and an unknown Resource
kind is not permission to accept an unknown Exchange version. Retain Q-E8–E10's
Operational-only binding, precommit fence, checkpoints and loss limitations.

### Proposed finite engineering bounds

Use the existing canonical JSON profile as the initial common identity ceiling:
**262,144 UTF-8 bytes of canonical text, 32 nested array containers, and 4,096
total value nodes including root, arrays and strings**. An empty array/string
counts as one node; root scalar depth is zero and root array depth is one. At
most 32 arrays may occur on a path; the string inside the 32nd array is allowed.
The baseline parser already uses 262,144 bytes, depth 32 and 4,096 nodes. These
are proposed reused engineering defaults, not new owner-selected numbers or
proof that current ResourceKey already enforces this grammar.

Enforce bounds on encoding, parsing and SQL admission consistently, including
escape expansion in serialized size. Use bounded iterative validation/pre-scan
before recursive library work; do not rely on interpreter recursion errors.
Embedded keys consume the enclosing unit/package's byte/node budget as well;
do not waive aggregate limits because each key passes individually. Existing
Exchange byte/unit/depth/work limits and cumulative request accounting remain.
An enclosing supported contract can impose a lower finite limit and report an
honest limit stop; it cannot truncate/rekey an identity or split an atomic report.
Changing a finite local setting does not authorize deleting admitted data.
Boundary values and limit+1 must be tested in a later implementation; numeric
defaults remain engineering choices under ADRs 0023–0025.

### Canonicalization specification vectors

These vectors are **specifications, not executed new-schema tests**. Code spans
show literal serialized JSON text unless the input column says “decoded”.

| Input / condition | Required result |
| --- | --- |
| decoded string `731` | `"731"` |
| decoded array containing string `731` | `["731"]`, distinct from `"731"` |
| `"00731"` versus `"731"` | Both canonical, different keys unless native adapter normalization happened before encoding |
| `""`, `[]`, `[""]`, `[[]]` | All canonical and distinct; adapter must justify completeness |
| `["project-a",["731",[]]]` | Canonical; preserve nesting and meaningful empty component |
| `["a","b"]` versus `["b","a"]` | Both canonical, unequal |
| `[["a"],"b"]` versus `["a","b"]` | Both canonical, unequal |
| decoded string U+00E9 | `"\u00e9"` |
| decoded U+0065 U+0301 | `"e\u0301"`, unequal to U+00E9 |
| decoded U+65E5 U+672C | `"\u65e5\u672c"` |
| decoded U+1F600 | `"\ud83d\ude00"` |
| decoded quote, backslash, slash | `"\"\\/"` |
| decoded LF, TAB, NUL, DEL | `"\n\t\u0000\u007f"` |
| `" A "` versus `"a"` | Both canonical, unequal; preserve whitespace/case |
| `"12345678901234567890123456789012345678901234567890"` | Exact decimal-string preservation; no int64/float conversion |
| serialized raw non-ASCII `"é"` or `"😀"` | Reject as noncanonical; encode decoded scalars to escapes instead |
| `"\u0061"`, `"\/"`, `"\u00E9"` | Reject noncanonical spellings; canonical forms are `"a"`, `"/"`, `"\u00e9"` |
| whitespace-padded ` ["731"] `, trailing newline/data, BOM | Reject canonical-key input |
| `731`, `true`, `false`, `null`, `{}`, `{"id":"731"}` | Reject forbidden root type; no stringify/opaque fallback |
| `["731",null]`, `[1]`, `[[false]]`, `[{}]` | Reject forbidden nested type |
| `"\ud800"`, `"\udc00"`, reversed pair, invalid UTF-8 | Reject invalid Unicode, including before serialization |
| malformed JSON, unescaped control, NaN/Infinity | Reject |
| SQL NULL in UUID/kind/ID | Reject |
| bytes >262,144; array depth 33; nodes 4,097 | Reject proposed bounds without truncation |

## Parent authority, missing references and unknown kinds

`resources` identifies entities. It must not retain a second independently
writable semantic Parent authority. Genuine namespace coordinates may remain in
identity even when they name a Parent; their presence alone is neither an FK
assertion nor proof of semantic Parent. Identity extraction helpers must not
invent relationships from arbitrary Provider-specific IDs.

`resource_relations` owns semantic Parent reports, preserving whole membership,
scope, provenance and original observation coordinates. A singleton typed Parent
report is a constrained report specialization, not a mandate to split every
coherent ordered multi-member relation into unrelated edges. No global UNIQUE
child constraint may erase genuine competing Parent reports. A deterministic
generated projection can expose a report for indexing/FKs if proven; independently
writable duplicate member/parent columns cannot contradict `members_json`.

| Situation | Admission and later behavior |
| --- | --- |
| Child's complete native identity, missing Parent row | Admit the child if its independent generic/known identity contract passes. Report missing dependency for the Parent report and dependent typed operations. |
| Incomplete child identity | Withhold child; do not manufacture namespace coordinates, singleton semantics or a surrogate. |
| Parent arrives later | Admit Parent if valid. No automatic replay/relationship creation from old withheld payloads. |
| Original relationship report supplied again | Revalidate selection, permission, complete unit, references and evidence; preserve original report key, time and provenance. Exact admitted replay is idempotent. |
| Competing genuine reports | Preserve separate reports; do not choose by arrival, event ID alone or latest arbitrary time. |
| Known event with missing/wrong Issue/Parent support | Event identity may be independently admissible; Parent/Transfer unit remains withheld or rejected as appropriate. No fabricated referents. |
| Unknown kind in a supported common wire version | Generic identity/field/report preservation and exact reread/export are allowed, subject to all common constraints. No kind-specific interpretation. |
| Invalid known kind/relation/operation input | Reject/withhold under its typed contract. Do not dispatch it through an opaque path. |
| Unknown relation name or arbitrary payload | Preserve only what the common format explicitly permits; do not infer traversal direction, membership, authority, event semantics or completeness. |
| Unknown wire version | Follow wire-version refusal; unknown-kind support does not override it. |

Generic exchange selects unknown Resources explicitly or through an already
specified bounded common structural dependency. Provider registration does not
select all Resources; an unknown name does not enable speculative graph walking.
Dependencies required by a known common fact unit still apply to an unknown-kind
subject. Preserve the complete unit or withhold it with a diagnostic; no hidden
durable relationship queue, original-bearing jobs or partial complete list.
Permission denial and omission by selection remain distinct from absence.
Future typed support needs an explicit compatibility review for previously
opaque resources; no silent reinterpretation or key rewrite.

## U3=C′ experimental acceptance contract

**Open, unproven gate.** No executed experiment evidence was available when this
package was authored. A separate agent is investigating. The documentation may
ship as Draft with the gate open. No sample DDL here is an executable solution.

The experiment must use disposable data and identify exact script, commit/tree,
actual SQLite version/source ID, schema/helper definitions, commands and observed
assertions. A toy projection success alone is insufficient. Required obligations:

1. Represent a singleton typed Parent report in existing `resource_relations`;
   extend only existing tables/constraints/indexes/projections. Add no domain
   table, relationship-header table, storage-only key or second Parent authority.
2. Admit complete child identity before Parent. Missing Parent blocks relationship
   and dependent Transfer, not independent child. Resupply is required after
   Parent arrival; no automatic durable deferred payload replay.
3. Preserve Q-S10's structural Issue-parented `comment` / `timeline_event`
   guarantee by **typed SQL references**, alongside independent admission
   checking of actual Transfer-event semantics. Application-only validation is
   not a preserved typed FK and SQL structure is not external authenticity.
4. Transfer cannot cite a nonexistent Event, wrong Event kind/subtype, wrong
   Parent kind, different Issue or nonexistent Parent report. Preserve exact
   support-report coordinates wherever required, including whole membership,
   scope and provenance and the original clock/time binding; event-ID-only
   joins or arbitrary support selection cannot stand in for that identity.
5. Preserve ADR 0030 `(EventResourceKey, clock_json, provenance_json)` endpoint
   pairing and equal original observation-time rules. Different reports must
   not be fused by event ID, receipt time or arbitrary winner. Genuine competing
   reports, existing coherent multi-member reports and exact replay survive.
6. Demonstrate that `members_json` and projected/support columns cannot disagree.
   Do not use nullable key components, CHECK's NULL truth value, conditional
   composite-FK NULL exemption or a mismatched UNIQUE index to bypass typing.
7. Exercise direct INSERT/UPDATE/DELETE, INSERT OR REPLACE/REPLACE, UPSERT and
   no-op conflict paths, explicit SQL NULLs, wrong types, malformed JSON,
   transaction/savepoint failure and deferred COMMIT behavior, reordered and
   repeated delivery. Probe supported connections with FK/recursive-trigger
   settings enabled; disabling enforcement is not an accepted write path.
8. Show rollback leaves no partially admitted report/Transfer or mutated original
   identity/time/provenance. Capture failure cases and actual exception/result,
   not merely `foreign_key_check` over successful fixtures.

Exact support-column/key grammar is an engineering proposal to be supplied by
the experiment and reviewed against these invariants. The gate is **unproven**
until executed evidence covers the required scope; a limited success must retain
its limits. If impossible, report the minimal concrete conflict/counterexample
to the owner and affected implementation stage. Do not silently add a table,
weaken the FK to an application predicate or declare another architecture chosen.
Future evidence must be cited at its own fixed commit; citing it is not a new
execution of the experiment in this design PR.

## ADR compatibility and lifecycle plan

Read the actual accepted records and [policy §§5–6](../adr/policy.md). The
classifications below separate durable meaning from old physical representation.
No accepted ADR body is changed or retired here. The owner-selected logical
choices take precedence within this task, while the complete proposed package
still requires coherent acceptance/lifecycle work before integration.

| Existing clause | Classification | Required treatment |
| --- | --- | --- |
| ADR 0017 KEY-P01 §1: real semantic composite PK/FK; no extra row surrogate | Preserved invariant | Same key triple; canonical whole identity is reversible semantic representation. Supporting report keys carry actual coordinates, never a new storage ID. |
| ADR 0017 §1 PR-document key and §2 established repository/capture/instance identities | Preserved invariant | Keep genuine PR/document coordinates and approved issued identities. Generality cannot erase a namespace or flatten distinct observations. |
| ADR 0017 unknown identity admission and wide composite-key costs | Generalization | Missing semantic Parent row no longer prevents independently complete identity. Incomplete native identity remains unadmitted. |
| ADR 0028 classified clocks, required Coverage coordinates, missing/NULL | Preserved invariant | Positive-or-NULL observation/Provider clocks; required positive times; signed native Git times. Never substitute arrival time or coerce numeric strings in those separate contracts. |
| ADR 0028 versioned canonical SHA-256, finite decode/work, no authentication | Preserved invariant | Identity validation is additional domain validation; outer digest binding remains original canonical content. No RFC 8785/HMAC claim. |
| ADR 0029 five-store authority and DS-R01–DS-R05 carried-forward rules | Preserved invariant | Context owns Provider mapping/state/text/evidence; Access configuration/approvals separate; Core INSERT-only; Operational/Search derived; paired backup meaning preserved. |
| ADR 0029 Context Q01–Q04 and Context rules 1–5 carry-forward | Preserved invariant / potential substantive reversal excluded | Existing PR-document semantic coordinates, field clocks, exact text and evidence survive. Dropping genuinely required PR coordinates would reverse accepted identity and is not selected. Generic extension relaxes baseline universal parent-registration constraints only for independently complete identities. |
| Existing plain scalar ID TEXT and flattened compound encoding | Representation-only change when semantics unchanged | Canonical string/recursive-array TEXT everywhere. Retain all genuine native namespaces and existing PR coordinates. Historical data/evidence are not retroactively re-encoded. No legacy migration required. |
| ADR 0030 Q-S2/Q-S3/Q-S4/Q-S7/Q-S9 | Preserved invariant | Dedicated Resource-to-Core relation authority; target_json semantic PK; immutable positive mapping alternatives versus current candidates; only strictly dominated comparable current candidates pruned. |
| ADR 0030 Q-S5: genuine Event, endpoint ReportKey and no header/surrogate | Preserved invariant | Preserve actual Event identity and pair only same clock/provenance report with coherent original observation time; changing affiliation alone is not Transfer. |
| ADR 0030 Q-S6 finite relation vocabulary and typed compatibility | Preserved invariant / generalization | Its closed vocabulary is the six Resource-to-Core Repository roles, not a universal Resource-kind enum. Open Resource kinds do not erase known role/type CHECK/FK constraints plus admission validation. |
| ADR 0030 Q-S8 exact six roles | Preserved invariant | `represents_repository`, `owning_repository`, `base_repository`, `head_repository`, `transfer_from_repository`, `transfer_to_repository`; no extra role or PR owning/base duplication. |
| ADR 0030 Q-S10 Issue-parented Timeline Event typed FK plus event validation | Preserved invariant / unproven physical realization | Parent authority moves to existing resource_relations, but typed SQL structural references and semantic admission must both survive. U3=C′ is not proven. |
| ADR 0030 Q-S11 Provider references in resource_relations | Generalization | Keep that authority and extend it to semantic Parent reports; Provider mapping unresolved is not explicit NULL. Preserve coherent multi-member units. |
| ADR 0030 Q-S12/Q-S13, final Q-S14 override, Q-S15/Q-S16 | Preserved invariant | Immutable Dispositions and complete ClaimKey references; genuine current qualification required; no Witness/history/counterevidence substitute or new operation UUID. |
| ADR 0030 Q-E1–Q-E4 | Preserved invariant | Independent bounded Repository/OID seeds; permitted unknown permanent UUID registration is not unselected referent fabrication. |
| ADR 0030 Q-E5/Q-E6 | Generalization preserving invariant | Independently select unknown kinds within common typed/structural bounds; withhold unsupported dependencies/whole incomplete units honestly. No blanket Provider selection or hidden staging. |
| ADR 0030 Q-E7–Q-E10 | Preserved invariant | Original PackageKey/content digest binding, Operational ordering/checkpoints/loss limits; new content needs new ID. |
| ADR 0029/0030 Source, clocks, competing reports, five Coverage columns, retained text, no ordinary bodies | Preserved invariant | No new provenance/coverage dimension or broad retention policy follows from generic identity. Unknown names/JSON never prove completeness. |

**Conditional lifecycle plan:** no substantive reversal is selected: dropping
genuine PR-document coordinates and weakening typed Q-S10 FKs are excluded.
Changing a physical proposal while preserving accepted guarantees needs no
retirement merely because columns move. If a concrete conflict is discovered,
first review its exact scope against ADR 0029's full carry-forward map and ADR
0030's clauses. A substantive reversal requires an accepted successor (or split
accepted successors) that
carries forward **all** still-binding clauses/rationale and scoped negative
lessons from each affected record. Obtain independent clause-map review and
explicit owner acceptance; only then retire whole affected files, set `replaces`,
and update index/inbound current instructions coherently under policy §6.
If a clause is demonstrably nonconflicting, record only that scoped refinement.
Do not extend the pre-policy exception to ADRs 0029–0030, erase PR-document
coordinates, or silently use `refines` to mask a reversal. This PR proposes that
plan; it performs none of the retirement/acceptance actions.

See the [handoff](../implementation/context-resource-design-handoff.md) for fixed
source coordinates, current-code impacts, future sequencing and actual checks.
