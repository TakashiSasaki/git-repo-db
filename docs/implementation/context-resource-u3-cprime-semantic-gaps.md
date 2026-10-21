# C′ semantic coverage follow-up

The original experiment remains **DEMONSTRATED within its stated subset** at
`e9aba86f4530b2e683c77e23a4fe58bdf02192c5`. This follow-up corrects independently
identified Document admission and makes the namespace encoding explicit. It
does **not** demonstrate the broader ADR 0031 acceptance contract: G3 exposes
one unresolved Q-S10 interpretation. No accepted ADR or product file changes.

## Three-gap findings

| Gap | Executed finding | Final classification |
| --- | --- | --- |
| G1: independent Documents | Both scalar and composite Provider-global `document` identities fail the original Resource CHECK. The correction admits their explicit complete form, later attributed Parent reports and Document children, while retaining PR-scoped coordinates and refusing omitted/partial known input. | **CLOSED — corrected and independently verified** |
| G2: canonical Parent representation | Both encodings are individually injective/reversible, but produce different keys for the same native Resource; their union can alias different Parents. The corrected scoped-document format uses canonical Parent ID TEXT as its second component. | **CLOSED — corrected and independently verified** |
| G3: identity I7 / reported Parent I8 | Original SQL and admission accept a Transfer citing the exact I8 report. SQL remains structurally valid. Supported admission now withholds this unresolved case without removing Parent reports or declaring them intrinsically invalid. | **OWNER DECISION REQUIRED — actual unresolved architectural conflict** |

[Evidence and commands](evidence/context-resource-u3-cprime/semantic-gaps/README.md)
include actual errors, SQL traces, transactions, rowsets and FK/integrity checks.
Python assertions and qualification checks are not labeled as FKs.

## Exact sources and execution

Fresh remote inspection matched the supplied historical baselines:

| Source | Actual inspected identity |
| --- | --- |
| Product main | `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9` |
| #113 audit | `24f593861327328fa00dab0b83f956cec330a0ac` |
| #114 proposed ADR/schema | `5244b98a9a302f082a07a526480faf438fc91838` |
| #115 before follow-up | `22b58ce7ff59478f1a4c8c8ef89b17d2f0068590` |
| Earlier reviewed executable freeze | `e9aba86f4530b2e683c77e23a4fe58bdf02192c5` |
| Independently rerun corrected executable freeze | `9eeacb28f7e4a426114a9ce40e2324b4da302817` |
| Corrected executable tree | `8f78de68058582327beddbb656207659507d43c6` |
| Corrected composed SQL SHA-256 | `2892a5fb0bcef8a0e0ea916fc1b71687a0a2afe545849e27dec4f7fd3600171f` |

[Input manifest](evidence/context-resource-u3-cprime/semantic-gaps/input-freeze.json)
binds candidate fragments, predicates, author harness, focused probe, drivers and
imported product inputs. Author receipts record the prior HEAD because exact
bytes were executed before committing. The independent reviewer ran a detached
freeze. Later evidence/prose commits are not another candidate execution.

| Runtime | SQLite | Source ID |
| --- | --- | --- |
| Python 3.12.14 | 3.53.1 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |
| Python 3.13.5 with pinned official library | 3.51.3 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |

Both lanes reran nine packaged-baseline controls and all 15 prior author groups /
163 steps, plus three focused groups / 46 steps. Prior fixtures explicitly use
the new encoding. T06's I8 Transfer is now labeled a **structural diagnostic**.
New G3 tests exercise supported withholding, direct SQL insertion, clean FK and
integrity checks inside the diagnostic transaction, and rollback.

The independent reviewer also ran the prior 75 reviewer observations with
explicit encoding/structural-diagnostic adaptations and 39 separately authored
focused observations on each runtime. These counts overlap and are not summed.
See the [independent review](evidence/context-resource-u3-cprime/semantic-gaps/independent-review/final-review.md)
for exact scripts, hashes, source interpretation and limits.

## G1: explicit native contracts, same Document kind

Two forms use the unchanged ResourceKey triple and `resource_kind='document'`:

| Form | Canonical `provider_resource_id` | Existing metadata columns |
| --- | --- | --- |
| Provider-global native identity V | `J(V)` | Namespace kind/ID and document subtype NULL; required `provider_document_id=J(V)` |
| PR-scoped native document D | `J(["pull_request",J(PR),subtype,D])` | Namespace kind `pull_request`, namespace ID `J(PR)`, actual nonempty subtype, local document ID `J(D)` |

`J` is the existing exact ASCII-escaped canonical JSON serializer constrained
to recursive strings/arrays. Genuine complete empty strings/arrays remain valid;
they cannot stand in for missing coordinates. The independent form infers no
subtype or namespace. Its repeated native ID is checked non-key metadata in an
existing column, not another identity, surrogate, table or Parent authority.

`document_input` takes the adapter's explicit genuine native contract:
`provider_global` or `pr_scoped`. It never retries a failed PR contract as global.
Missing PR namespace/subtype/local identity fails before SQL. Direct SQL rejects
all-omitted and partial coordinates too. A fully rewritten payload falsely
claiming a global native contract cannot be authenticated by SQLite; admission
must know the Provider contract. This is the same boundary as determining that
an empty native identity is genuinely complete.

Generated `reference_document_kind=coalesce(document_kind,'')` supplies a disjoint
**non-key typed absence marker**. Existing nonempty subtypes keep their meaning.
The marker is not native identity or a placeholder for missing identity. A Parent
scope must explicitly contain `document_kind:null` for an independent Document.
Matching projections and a real typed source FK prevent a PR-scoped Document
from claiming the independent form, or the reverse. Missing scope fields fail
CHECK; NULL cannot disable this source FK.

Independent Parent reports may target an actual same-Provider Resource. The
target FK rejects missing referents. The child can precede its Parent; arrival
alone creates no report. Original report re-supply succeeds, including independent
attribution and a Document with a Document child. Generic multi-member relations
retain their previous application dependency checks. No Document is relabeled
as an unknown kind.

Focused cases include a genuine global four-component array shaped like a scoped
document, so syntax heuristics cannot reject valid global composites. Actually
distinct native namespaces that collide under service/kind/value still require a
meaningful native discriminator under U2; no universal discriminator is added.

## G2: one explicit encoding for the unreleased format

For Parent ID TEXT `["project","7"]`, subtype `body`, local native ID `D`:

```text
Canonical-TEXT component: ["pull_request","[\"project\",\"7\"]","body","D"]
Decoded-array component: ["pull_request",["project","7"],"body","D"]
```

Each encoding is injective on valid coordinates: canonical serialization has a
unique inverse, arrays preserve order/boundaries, and all four coordinates remain.
The TEXT form reverses by parsing the outer value and then its second string;
the nested form reads the second value directly. Both preserve the genuine PR
identity, document subtype and Provider document ID. ADR 0017 fixes these semantic
coordinates, not their JSON nesting. Choosing TEXT is explicit engineering work
for the unreleased format, not an accepted semantic-key amendment.

Silently switching encoders nevertheless generates different keys for the same
native Resource. Accepting both profiles also aliases TEXT encoding of array
Parent V with nested encoding of a **different literal-string Parent whose native
ID is `J(V)`**. Canonical JSON alone cannot resolve that mixed-profile ambiguity.
The candidate accepts only the TEXT profile for known scoped documents and rejects
the nested alternative against the supplied coordinates. No dual decoding,
compatibility guessing or extra discriminator is needed. Future production key
occurrences must consistently use this profile. Historical keys stay untouched.

## G3: precise owner question

The Event's native namespace is Issue I7, but an attributed Parent report names
Issue I8. The results are separate:

1. B3 permits identity coordinates and relationship facts to differ. Retaining
   I8 alongside I7 does not claim either is currently true.
2. Actual FKs allow Transfer support through the exact I8 report attached to the
   same Event with `comment` / `timeline_event` / `issue` properties. Prior absent,
   wrong-type and cross-paired support failures remain.
3. Structural success does not establish semantic Transfer qualification. The
   original helper checked `event_type='transferred'`, leaving this conflict open.
   It survives as diagnostic `structural_admit`. Supported `admit` now raises
   `QualificationRequired` before writes for the unresolved mismatch. Independent
   Resources/reports survive; there is no winner, Witness or stored approval flag.
4. ADR 0030 Q-S10 requires an Issue-parented Timeline Event plus actual-event
   checking, but its old model conflates identity and Parent. The linked design
   calls the identity coordinate the real parent Issue. #114 acceptance item 4
   requires "different Issue" rejection without defining that comparison after
   B3. Neither B3 nor the old typed FK settles the new semantic case.

**Owner decision required:** does reserved Q-S10 mean **A**, I7 is the Event's
semantic Issue as well as its native namespace, so I8 can be retained as a report
but cannot support this Event's Transfer; or **B**, I7 is only the native namespace
and a separately, genuinely qualified I8 Parent report can support Transfer of
that same Event? Under B, specify the required semantic evidence/qualification;
an attributed report's existence is insufficient. This is Q-S10-specific, not a
request for Parent equality throughout the graph.

Estimated owner blockers in this newly examined semantic scope: **1**. This
increases the earlier structural scope's zero because the follow-up tests a
previously excluded interpretation. Transfer semantic admission and ADR 0031's
broader acceptance verdict depend on it. G1/G2 engineering does not.

Separating identity/report concepts or retaining I8 alone needs no demonstrated
amendment. If B reverses the accepted meaning that I7 is the actual Event Issue,
an explicit scoped successor and carry-forward under ADR policy §6 is necessary;
it cannot be hidden as a representation fix. If the owner establishes that Q-S10
already allowed B, document that nonconflicting refinement and prove qualification.
Under A, engineer/test the scoped typed SQL reference required by #114; a Python
equality guard does not replace any required FK. This investigation chooses neither.
The temporary withholding guard is not a permanent equality policy.

## Updated enforcement matrix

| Layer | Demonstrated guarantee / limit |
| --- | --- |
| FK | Actual Parent target; independent-vs-subtyped Document source; exact full Parent/event support; Timeline Event / Issue typing; existing Repository endpoints |
| CHECK + bounded row-local UDF/generated projection | Canonical recursive identity; complete global/scoped forms; one scoped encoding; explicit Parent scope/member syntax; non-NULL typed absence projection; endpoint declaration |
| Trigger | Existing immutable mutation/replay guards, including identification metadata; generated projection cannot be written independently |
| Typed admission | Genuine native-contract dispatch without fallback; actual normalized event type; original-time validation; complete endpoint/dependency unit and savepoint rollback |
| Temporary withholding | Unresolved namespace/Parent mismatch raises qualification requirement; Python behavior, not FK/authenticity/permanent policy |
| Selection/evaluation | General member dependency closure, whole-unit selection, current qualification of competing evidence; no inferred winner |

There remain 19 Context tables and five Coverage columns. No production writer,
reader, Exchange, backup, recovery validator or Provider adapter was changed or
tested against this candidate. Context-only reconstruction/snapshot scenarios
are not Product Exchange or paired-backup acceptance.

## Earlier evidence and recommendation to ADR 0031 author

All old successes and failures retain exact hashes and original scope. The old
SQL hash is `c2c325532279f35ba51b36aacbeea30ceda4040e80b5d31512cbb9e19d564dee`.
G1 adds missing coverage; it does not falsify the old known-document scenarios.
G2 explicitly changes representation; old receipts are not relabeled as new-format
executions. T06 is still valid structural evidence, not Q-S10 qualification of I8.
The earlier independent review is unchanged.

For #114, incorporate the explicit global/scoped Document contracts and single
canonical-TEXT encoder with their SQL/admission boundaries. Cite the corrected
freeze only within its verified scope. Resolve G3 and sharpen "different Issue"
before declaring the broader U3 gate demonstrated. The current conclusion is:
**earlier experimental subset demonstrated; G1/G2 coverage corrected; broader
ADR 0031 acceptance unresolved**. This work does not accept, merge or implement
ADR 0031, deploy or release.

The repository lessons-to-skills procedure was assessed. A verified lesson about
mixed encodings and native-contract dispatch is proposed in the evidence README;
skill files remain unchanged because this follow-up is confined to experiments.
