# ADR 0031 I6 canonical vectors and adversarial test plan

Companion to the [normative contract](adr0031-i6-wire-admission-exchange.md).
These are design specifications; none is presented as new product execution.
Synthetic fixture values below do not claim an actual Provider observation.
Stable V/T IDs must appear in later implementation and independent receipts.

## Canonical input vectors

`J` means the exact Context canonical encoder from R03, not an arbitrary JSON
serializer. JSON blocks showing rows are outer JSON; strings ending `_json` or
containing identity TEXT have the literal escaped inner representation shown.
Whitespace in these outer examples is for reading; hash the canonical dictionary
under R03. Do not replace inner canonical strings with decoded values.

**V01 — Global Document, no Parent dependency.** Register the Provider and this
row; no namespace Resource or Parent report is supplied or required:

```json
{
  "service_instance_uuidv4": "11111111-1111-4111-8111-111111111111",
  "resource_kind": "document",
  "provider_resource_id": "\"D\"",
  "identifier_namespace_kind": null,
  "identifier_namespace_id": null,
  "document_kind": null,
  "provider_document_id": "\"D\""
}
```

**V02 — Scoped Event, namespace Resource absent.** This identity is independently
complete and valid for Resource registration. It does not create an I7 Parent
report or permit Transfer:

```json
{
  "service_instance_uuidv4": "11111111-1111-4111-8111-111111111111",
  "resource_kind": "comment",
  "provider_resource_id": "[\"issue\",\"\\\"I7\\\"\",\"timeline_event\",\"E\"]",
  "identifier_namespace_kind": "issue",
  "identifier_namespace_id": "\"I7\"",
  "document_kind": "timeline_event",
  "provider_document_id": "\"E\""
}
```

**V03 — Original Parent row.** After independently registering I7, this complete
report can support V02's Event. It has clock 50, observation 51 and provenance P:

```json
{
  "service_instance_uuidv4": "11111111-1111-4111-8111-111111111111",
  "resource_kind": "comment",
  "provider_resource_id": "[\"issue\",\"\\\"I7\\\"\",\"timeline_event\",\"E\"]",
  "relation_kind": "parent",
  "members_json": "[[\"11111111-1111-4111-8111-111111111111\",\"issue\",\"\\\"I7\\\"\"]]",
  "provenance_json": "{\"evidence\":\"P\",\"source\":\"fixture-provider\"}",
  "scope_json": "{\"clock\":{\"at_us\":50,\"domain\":\"provider\"},\"document_kind\":\"timeline_event\",\"state\":\"complete\"}",
  "observed_at_us": 51
}
```

**V04 — Genuine one-sided explicit-NULL Event.** This exact decoded scope is
canonicalized to `scope_json` on an Event report with Event clock 100,
observation 101, provenance `{"evidence":"E","source":"fixture-provider"}`,
`members_json="[]"`. Its EventReportKey is independent of V03's clock/provenance.
The scope's three Parent strings quote V03 exactly:

```json
{
  "clock": {"at_us": 100, "domain": "provider"},
  "endpoints": [["transfer_to_repository", "null"]],
  "event_type": "transferred",
  "from_provider_repository_id": null,
  "parent_members_json": "[[\"11111111-1111-4111-8111-111111111111\",\"issue\",\"\\\"I7\\\"\"]]",
  "parent_provenance_json": "{\"evidence\":\"P\",\"source\":\"fixture-provider\"}",
  "parent_scope_json": "{\"clock\":{\"at_us\":50,\"domain\":\"provider\"},\"document_kind\":\"timeline_event\",\"state\":\"complete\"}",
  "provided_roles": ["transfer_to_repository"],
  "to_provider_repository_id": null
}
```

Its sole endpoint row has V02's triple, `relation_kind=transfer_to_repository`,
`clock_json=J({"at_us":100,"domain":"provider"})`, `target_json="null"`,
the same original Event provenance and time 101,
`event_report_members_json="[]"`, and `event_report_scope_json=J(the exact block)`.
No from endpoint exists. The synthetic adapter must explicitly establish the
original one-sided declaration; row absence alone never supplies that evidence.
In normal I6 product connections this still returns the Transfer-stage refusal;
positive admission is executable only in the isolated lane until R19 passes.

**V05 — Two-sided explicit-NULL report and its truncation.** Starting with V04,
set `provided_roles` to
`["transfer_from_repository","transfer_to_repository"]` and `endpoints` to
`[["transfer_from_repository","null"],["transfer_to_repository","null"]]`.
Supply both endpoint rows bound to that new exact scope. This is a complete
synthetic two-sided report. Supply only the to row with that declaration and
expect `INCOMPLETE_ENDPOINT_SET`, zero Event/endpoint writes. Repeated/reversed
transport of individual rows must not accumulate a pending report. The full
original unit must be explicitly resupplied. This and V04 use separate disposable
databases, or a genuinely different synthetic Event: changing the scope under
V04's already admitted EventReportKey is an immutable replay conflict.

**V06 — Provider-only unresolved mapping.** Starting with V04, set
`provided_roles=["transfer_to_repository"]`, `to_provider_repository_id="\"R\""`,
`endpoints=[]`, and `members_json` to
`[["11111111-1111-4111-8111-111111111111","repository","\"R\""]]` encoded with J.
Register the actual Provider repository Resource R. There are no translated
endpoint rows. Preserve this attributed report with unresolved Provider state;
no resolved Core Repository effect or explicit NULL follows. A later mapping
does not update this report or automatically replay an earlier refused unit.

**V07 — Resolved mapping, complete direct keys.** For an independently supplied
synthetic resolved report, use Provider repository R and Core Repository
`22222222-2222-4222-8222-222222222222`. The exact MappingClaimKey dictionary is:

```json
{
  "service_instance_uuidv4": "11111111-1111-4111-8111-111111111111",
  "resource_kind": "repository",
  "provider_resource_id": "\"R\"",
  "relation_kind": "represents_repository",
  "clock_json": "{\"at_us\":80,\"domain\":\"provider\"}",
  "target_json": "\"22222222-2222-4222-8222-222222222222\"",
  "provenance_json": "{\"evidence\":\"M\",\"source\":\"fixture-provider\"}"
}
```

MappingSupport is the existing exact
`{"provider_repository_id":"\"R\"","supporting_claims":[the dictionary]}`
profile. Build original Event provenance using
`encode_transfer_supported_provenance("fixture-provider","E",
[("transfer_to_repository",support)])`. Explicitly declare the to endpoint's
canonical UUID target string before filtering; all endpoint rows use that exact
Event provenance/scope/time. This is a deterministic fixture construction, not
permission to mint production provenance on replay. Admission must re-evaluate
the same support's current eligibility. Missing claim is `MISSING_DEPENDENCY`;
unqualified supplied support is `UNQUALIFIED_MAPPING`; an unauthorized target is
`PERMISSION_DENIED`. None becomes explicit NULL or V06.

**V08 — Concrete invalid mutations.** Apply each independently to a fresh
fixture; rechecksum the outer package where appropriate. Expected unit writes
are zero. Independent valid child identities can remain admitted under U4=B.

| Mutation | Required result |
| --- | --- |
| V01 omits `provider_document_id`, or sets it NULL | Missing/incomplete identification; not a global Document |
| V02 changes namespace ID to `"\"I8\""` without changing Resource ID | Reject native reconstruction mismatch |
| V02 uses decoded nested `issue` namespace identity instead of canonical TEXT string | Reject wrong scoped profile |
| V01/V02 stores raw `D`, numeric `7`, `true`, `null`, `[1]` or `{}` as canonical ID | Reject; never stringify |
| ID text ` "D" `, `"\u0044"`, raw non-ASCII `"é"` | Reject noncanonical text; decoded scalar U+00E9 encodes as `"\u00e9"` |
| Change kind to an unknown name only after failing a known-contract validation | Reject dispatch downgrade; no opaque retry |
| Omit any V04 `parent_*_json`, or use NULL | `INCOMPLETE_ORIGINAL_REPORT`; no Event-based values |
| V04 quotes Parent clock 100 / provenance E while only V03 exists | `MISSING_DEPENDENCY` for that exact different key; do not borrow V03 |
| V03 member I8, quoted exactly by Event while native namespace remains I7 | Lawful attributed Parent retained; `QS10_PARENT_INELIGIBLE` for Transfer, including direct SQL bypass |
| Omit V04 `endpoints` or pass constructor `endpoints=None` | `INCOMPLETE_ORIGINAL_REPORT`; no construction from surviving rows |
| V04 endpoint `target_json` is JSON NULL instead of string `"null"` | Reject input type; explicit NULL is canonical target text |
| V05 drops one endpoint row but keeps original scope | `INCOMPLETE_ENDPOINT_SET` regardless of stored endpoint rows |
| V05 filters from role and rewrites `provided_roles`/`endpoints` | Sender contract violation; same EventReportKey conflicts if prior original exists; receiver cannot authenticate a coherent first-delivery forgery |
| V07 declares target but removes supporting claim / substitutes a different target claim | Missing/invalid support; no locally recomputed replacement |
| Set any nullable observation time to `true`, `1.0`, `"101"`, 0, -1 or int64-max+1 | Reject before SQLite affinity; NULL is valid only for nullable times |
| Set Event clock `at_us` to NULL | Reject Transfer's required positive Event clock; general nullable-clock contracts are unchanged |
| Add sender top-level `verified:true` or unknown row field | Reject exact envelope; a verified flag inside permitted attributed evidence is never authority |
| Set `format` to v4, v6, empty, NULL, or omit it | `UNSUPPORTED_WIRE_VERSION`; no fallback |
| Duplicate an outer/inner object key, malformed UTF-8, lone surrogate, NaN/Infinity | Reject strict parse before writes |
| Same PackageKey with changed original or filtered content | Package content-binding conflict; new content needs new package ID |

**V09 — Generic order and real terminals.** Owner V01 may own a new Document
child and an unknown-kind Resource `x-widget` whose ID is `["p",[]]`; the Provider
adapter must establish those synthetic native contracts. A generic relation
`links` with members `[child,x-widget]` is distinct from `[x-widget,child]`.
No semantic Parent is inferred from `links` or identifier components.
For Collection kind `related`, provenance `{"source":"fixture","evidence":"C"}`
and scope `{}`, these are four distinct inputs:

| Time / state / members | Meaning |
| --- | --- |
| No row | No terminal, no completeness |
| 200 / `complete` / `[]` | Genuine known-empty terminal |
| 201 / `partial` / `[]` | Genuine partial terminal, not known empty |
| 202 / `unknown` / `[child]` | Real observation with unknown completeness |
| 203 / `complete` / `[child,x-widget]` | Complete ordered membership |

At 204 send partial `[child]`; current Coverage cannot fall back to the complete
203 report. At 205 supply both complete order alternatives; retain conflict.
Selecting only child withholds the original two-member terminal and associated
Coverage; it never exports `complete [child]`. Required terminal times cannot be
NULL. Duplicate members are invalid. Same header/provenance with changed scope
is an immutable conflict. Partial Source inventory `{R1}` must leave a previously
known positive `{Source,R2}` intact.

## Independently executable test matrix

Each case must be runnable by its stable ID without the Author's database,
network, credentials or real Provider. Later PRs add implementation tests; this
design PR adds no executable production/test changes. Fixtures use disposable
state with explicit state directories. For isolated Transfer positives, first
verify exact composed product schema/UDFs/PRAGMAs, record and drop **only** the
two stage fences, keep FK/CHECK/recursive triggers enabled, and never reopen
that altered fixture as a normal product catalog. Separate normal-route refusal
tests keep both fences. Do not bypass production gates to make end-to-end tests
green; use an explicitly isolated synthetic harness until R19.

For every refusal, capture typed code, reached phase, before/after rowsets and
transaction state, not merely an exception matching any error. Check immutable
preexisting rows too. Distinguish refusal before SQL from injected in-flight
failure and COMMIT failure. Unit IDs below are minimum obligations, not a cap on
reviewer-designed counterexamples.

| ID | Independently executable setup/action and assertions | Owner / requirements |
| --- | --- | --- |
| T01 | Parse/encode canonical scalar, recursive/empty IDs; every accepted schema vector; all caps at limit and +1; strict decoded subtype/cycle controls; API/SQL/embedded-key BINARY equality | A/B; R03–05 |
| T02 | V01/V02 register before namespace/Parent; export/import same seven columns; later add Parent only, assert zero synthesized relationships/Transfer; original resupply only then succeeds | A/B/C; R01/05/08/14 |
| T03 | V03 clock 50/P/51, Event 100/E/101; full-key roundtrip and replay preserve both originals. Omitting coordinates fails; a second lawful Parent with different provenance never becomes a winner | A; R08 |
| T04 | Keep I7 and I8 Resources plus both lawful attributed Parent reports; native-I7 Event using I8 support gets permanent code; isolated direct SQL fails native-I7 FK; I8 row survives. Missing I7 support gets dependency code; later original resupply rechecks all gates | A; R01/08/15 |
| T05 | V04 genuine one-sided, V05 complete two-sided then truncate; constructor and decoder cannot infer declaration; replay cannot borrow old endpoint rows; full explicit resupply restores only complete original | A/B/C; R09 |
| T06 | Separately test not-reported role, explicit target `"null"`, missing field, Provider-only V06, unqualified V07, and sender selection omission. Assert six distinct meanings/outcomes and no fake Core UUID | A/B/C; R09/12 |
| T07 | Grant Event but deny Parent, one member, Provider repository, Core target, Source, mapping claim or replacement support one at a time; assert `PERMISSION_DENIED`, zero dependent writes and no existence leak | A/C; R10–12 |
| T08 | Admit authorized unit, revoke grant then exact replay through store, facade, Provider and Exchange including cached package receipt; assert denial rather than duplicate. Revoke between preflight and commit; lease/fence rolls back | A/C; R10–12/14 |
| T09 | Give Repository grant without Resource/Source grants; `all_selected=true` and sender claimed permission still cannot admit; empty selection is none; omitted seed dimension without local all opt-in fails | A/C; R10/13 |
| T10 | Rechecksum malformed known ID, forged support, false event type, altered Parent key and dropped endpoint. Domain checks refuse. Coherent forgery with permitted attributed evidence stays unauthenticated, never advances local verification or qualifies a Disposition by sender flag | B/C; R02/03/09/11 |
| T11 | Generic cyclic member graph A↔B and non-leaf global/scoped Document; register Resources first, reports after; expansion terminates deterministically. Unknown names do not add traversal. Node/edge/depth/byte/work 0, exact limit and +1 stop without partial reports | B/C; R04–06/13 |
| T12 | V09 empty/partial/unknown/complete/no terminal and ordered member alternatives; late partial prevents old complete fallback; withheld terminal alternative removes associated completeness; nested required-child/head/base proof checks remain | B/C; R06/07 |
| T13 | Partial Source inventory retains R2 positive; cross-service Source, absent association, unselected/denied Source and proof mutations fail; Source registration alone selects no Provider Resources | A/B/C; R07/11 |
| T14 | Sender/receiver disjoint selections and locally existing authorized dependencies; whole Transfer, relation, Collection/proof withholding. Local but unauthorized or unselected dependencies cannot rescue unit; no member-list shrinking | C; R10–14 |
| T15 | Deliver dependency/child/report late, repeated and reversed in two/three disposable catalogs; explicit resupply preserves clocks/provenance; onward/reverse Exchange unchanged report keys. No arrival/reopen/resume auto-replay and no durable pending payload | C; R08/13/14 |
| T16 | Import package lists Transfer before Parent; planner registers Resources/Parent before dependent Transfer. Withhold Parent and assert child survives while Transfer does not. Permute arrays and arrival order; same complete result after explicit full resupply | C; R13/14 |
| T17 | Isolated two-endpoint fixture: temporary BEFORE INSERT trigger aborts only second endpoint. SQL trace proves first endpoint INSERT ran and was visible in transaction, second failed, ROLLBACK TO occurred; 0 new Event/endpoints remain, preexisting originals unchanged. Separate outer COMMIT-failure test | A; R15; I5-D1 |
| T18 | Omitted/partial-NULL support, wrong service/subtype/Issue, all INSERT/IGNORE/DO NOTHING/REPLACE/UPSERT/UPDATE/DELETE paths and deferred COMMIT; preserve complete Parent/Event FKs and pre-conflict guards; no assertion weakened from 217 I4 cases | A; R15 |
| T19 | Normal schema, each single missing fence, both missing, altered definition and schema-read error; helper and facade fail closed. Isolated fixture removes only exact two verified fences; normal reopen refuses it. Both wheel forms preserve expected triggers | A; R16; I5-F1 |
| T20 | FK disabled, recursive triggers disabled, required UDF missing/wrong flags, modified schema/fingerprint, poisoned rows despite clean FK check; reject normal connection or Recovery Stop on proven stored violation. Restore fixture schema before observing normal routes | A/I7; R15–17 |
| T21 | I7 trusted stored decoder reconstructs full endpoint reference fields and originals; invalid retained native support/terminal/body triggers source Stop plus restore refusal. IO/lock/budget errors remain indeterminate, not fabricated corruption | I7; R17 |
| T22 | Paired Core+Context restore and separate Access scope; read-only suspect, untrusted salvage under current authorization, fresh validation before activation. No source mutation, same-DB failover or automatic restart after Operational loss | I7; R17 |
| T23 | I8 namespace versus semantic Parent queries, unknown/global/scoped/nonleaf views, no Parent winner, Provider-only versus qualified Transfer, Source/Coverage conflicts; scan/Search/fallback/rebuild equal under snapshot/generation and permission revocation | I8; R18 |
| T24 | Build direct wheel and sdist-derived wheel from exact frozen inputs; install separately outside checkout with same selected Python/library; assert site-packages origins and installed code/DDL/UDF/fingerprint hashes; run positive/negative v5 and admission probes on both | A/B/C/I7/I8; R19 |
| T25 | Run unchanged broad targets and original Access smoke, preserve every nonzero exit, compare full node/phase/exception/frame inventory to inherited 79. No skip/xfail, omitted assertion or selection narrowing; map each honest resolution to replacement/now-reached assertions | All stages; R19 |
| T26 | Normal Provider `_preflight_units`, `admit_unit`, `admit_units`, `admit_batch`, timeline adapter, Exchange export/import/onward, lower-level facade/store, salvage entry points: missing context fails closed; every declared operation dispatches to guarded boundary. Inject a deny-all policy to prove zero bypass paths | A/C/I7; R10/16/17 |
| T27 | Replay immutable key with changed original observation, membership/order, clock, provenance or scope; reject rebind. Independent lawful report keys survive as alternatives. Same PackageKey changed digest/content refuses, Operational loss never grants validity | A/B/C; R06/08/14 |

## Evidence and inherited failures

Later executable PRs must retain commands, exact source commit/tree/input hashes,
selected Python executable/version, actual SQLite version/source ID/options,
PRAGMAs/UDF flags/schema fingerprints, selected/collected/executed node IDs,
JUnit plus journal and process exit, refusal codes/SQL error codes/trace/rowsets,
artifact bytes/hashes and installed import origins. Inventory unexecuted cases.
Use only the environment's actual SQLite under ADR 0032; a deficient runtime is
failed/unexecuted evidence, not an invitation to install a test SQLite engine.
Independent reviewers write and execute their own counterexamples, referencing
the frozen Author tree. Their outcome is not predeclared by this matrix.

Inherited #132/#133 receipts report 3,058 pass, 59 call failures and 20 setup
errors: **79 non-successes** (45 Transfer calls, 20 Transfer setup, 14 I6/query
boundary calls). Those are historical measured counts, not this design PR's
results or a required final failure count. Keep the exact target set and raw
first-failure comparison; I6 identification support may legitimately move a node
past an old failure to a new failure, or resolve a wire failure. Document old/new
node, phase, exception, frames, reached assertions and owning stage. A changed
first failure does not prove later Transfer/query assertions ran. Every removed
obsolete mechanism assertion needs an explicit replacement mapping and review.
Both original Access artifact smokes may still refuse Transfer until R19; keep
their exit 1. Do not claim complete release acceptance from development CI.

I4-E1 remains an evidence-scope carryover: freeze complete sdist input inventory
separately from runtime/wheel inputs. Evidence published after execution may
change full sdist bytes; record tested source and later publication trees and
compare actual input sets. Never rewrite historical ZIPs/receipts or call the
later sdist tested solely because runtime blobs match.
