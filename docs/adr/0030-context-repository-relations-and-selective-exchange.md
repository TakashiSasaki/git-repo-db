---
status: accepted
date: 2026-10-18
replaces: []
refines:
  - 0003-append-only-git-core-and-context-store.md
  - 0005-common-oid-identity-with-attributed-metadata.md
  - 0006-field-claims-and-observation-scoped-relations.md
  - 0017-domain-keys-without-storage-surrogates.md
  - 0027-unauthenticated-external-capture-origin-reports.md
  - 0028-classified-times-and-sha256-exchange.md
---

# ADR 0030: Typed Repository Context relations and selective Exchange without Witness storage

## Decision

**Owner-selected target, not implemented behavior.** On 2026-10-18 the owner
selected the Context Q-S and Exchange Q-E decisions below, explicitly adopted
the post-experiment decision to retain Dispositions without a Witness table,
and requested a design-only PR. The acceptance reference is the sequence of
explicit selections in the design conversation, including the final message
「この決定です。」 following the proposal not to introduce a Witness table,
followed by 「それでは設計のためのプルリクエストを提出してください。」.
No conversation URL or message identifier was supplied; none is invented here.

This ADR records those decisions, including the negative decision about Witness
storage. The linked physical design is an engineering proposal constrained by
these decisions, not an independently approved implementation or test result.

Add two Context relations: `resource_repository_relations` and
`repository_mapping_dispositions`. Move Resource-to-Core-Repository relation
candidates out of `field_candidates`; preserve Provider-side relations in
`resource_relations`. Do not add `repository_mapping_local_witnesses`, a Witness
counterevidence table, or a disguised verification-history substitute in JSON.
The expected composed Context count is 19 (baseline 17 plus two), including its
existing `store_identity` and shared `coverage_claims`; verify the actual count
when implementation changes the packaged schema.

### Context decision ledger

**Namespace:** Q-S below means the Resource/Repository Context discussion, not
the earlier Access Scope Q-S1--Q-S4 recorded in ADR 0029. Those Access decisions
remain unchanged. Earlier conversation SQL and recommendations are not a second
active specification where the final choices below supersede them.

| Decision | Final rule |
| --- | --- |
| New relation table; Q-S2=A | Fully relocate Resource--Repository relation candidates into `resource_repository_relations`; remove the old special field, generated FK column and write/read paths. Keep general field candidates. |
| Q-S3=A | Canonical JSON `target_json` directly participates in the composite PK; derive the nullable Repository UUID for a real Context-local FK. No row surrogate or hash-only key. |
| Q-S4=B | One relation table distinguishes current single-value candidates, immutable positive mapping claims, and immutable real-event endpoint reports. |
| Q-S5=A | Use the genuine existing Provider Event Resource identity; pair endpoints only within `(EventResourceKey, clock_json, provenance_json)`. No event-report-header table. No invented Transfer from changing affiliation. |
| Q-S6=B | Finite relation vocabulary and Resource compatibility are constrained with CHECK/FK, plus typed admission for semantics SQL cannot prove. |
| Q-S7=B | AFTER INSERT prunes only strictly dominated comparable current candidates, atomically with insertion. Equal clocks, different domains and unknown clocks do not break ties. |
| Q-S8=A | Exactly six roles: `represents_repository`, `owning_repository`, `base_repository`, `head_repository`, `transfer_from_repository`, `transfer_to_repository`. No generic `referenced_repository` role in this release scope. |
| Q-S9=B | `represents_repository` is an immutable, positive, attributed mapping claim. Conflicting Core UUID targets coexist; there is no automatic rekey, merge or latest-clock winner. |
| Q-S10=A | Transfer endpoint rows require an Issue-parented Timeline Event (`comment` / `timeline_event` / parent `issue`) through the typed FK. Admission separately checks the actual event type. |
| Q-S11=A | Preserve Provider Repository references using existing Provider-to-Provider `resource_relations`. Resolve Core UUID mappings separately; unresolved mapping is not an observed NULL. |
| Q-S12=B | Add immutable `repository_mapping_dispositions`: `dispute`, `withdraw`, `correct`, each targeting a complete mapping ClaimKey; correction also references a complete replacement ClaimKey. No separate human winner/adoption authority table. |
| Q-S13=B | Claimed issuer equality alone grants no effect. A withdrawal/correction can have qualified local effect only where genuine currently available operation/issuer evidence supports it. An imported report is not receiver-local verification. |
| Q-S14, final owner override | **Do not introduce the Witness table.** This explicitly reverses the earlier Q-S14=B choice in the conversation. Persist claims and Dispositions; compute current qualified effect from available original evidence. Independent historical local-check auditing is not a required feature. |
| Q-S15=A, surviving principle | Use sufficient genuine existing identity properties; do not issue an extra operation/Witness UUID for storage convenience. `local_operation_key_json` is the agreed terminology where an actual operation key is discussed, not a new mandatory database column. |
| Q-S16=A | No Witness-specific counterevidence table. Re-evaluate available source evidence; do not rewrite claims/Dispositions or hide a Witness history in another table. |

For the six roles, `represents_repository` is non-NULL and immutable;
`owning_repository` applies to Issues, base/head to PRs and permits genuinely
reported NULL; transfer endpoints preserve genuinely reported NULL but do not
turn it into a positive edge. Missing, explicit NULL, unresolved Provider-to-Core
mapping, and conflict remain distinct. PR ownership is not duplicated as both
`owning_repository` and `base_repository`. Review/comment parent relations are
not automatically copied as extra Repository relations.

### Exchange decision ledger

| Decision | Final rule |
| --- | --- |
| Q-E1=C | Select an arbitrary set of permanent Repository UUIDs. |
| Q-E2=C | Different initial Repository seeds do not forbid exchange. An explicitly permitted unknown Repository may be registered using its received permanent UUID, without replacing receiver store identity. |
| Q-E3=C | Explicit Repository and typed OID selections are independent. |
| Q-E4=C | Treat selections as seeds for bounded typed Git metadata graph expansion. Record effective scope and limits; do not imply byte availability or complete Git history. |
| Q-E5=C | Select Context independently and expand only allowed typed relations within explicit bounds. Provider registration is not selection of all its resources. |
| Q-E6=B | Admit complete, internally coherent fact units where possible and explicitly report unadmitted dependencies/units. No fabricated referents, truncated complete claims or hidden durable staging. |
| Q-E7=A | Bind `(sender_catalog_instance_uuidv4, package_id)` to one canonical-content SHA-256. Identical resend retains the key; changed content requires a new package ID; known same-key/different-content is rejected. |
| Q-E8=A | Package binding and receipt records live only in Operational. Loss of these records limits historical same-ID/different-content detection. No additional durable Exchange Witness. Existing request-issuance witnesses are a different, preserved mechanism. |
| Q-E9=B | After package/admission preflight and before any Core/Context commit, atomically bind package ID and digest in Operational; record Core/Context stage checkpoints. Checkpoints never supersede actual committed facts. |
| Q-E10=B | Operational is required for reception. Explicitly initialize/reinitialize it; after loss/reconstruction do not continue the old request or reset its budget. A genuinely new, explicitly issued request may process the unchanged package against existing facts. |

## Constraints / Do NOT

- Preserve Core INSERT-only, permanent Repository UUIDs, common typed OID
  identity, original Capture keys, attributed claims/groups, Source known-positive
  membership, original clocks, Coverage evidence and its five-column claim model.
- Keep original Provider identifiers in their genuine namespaces. Canonical text
  encoding is not permission to derive IDs from URLs, decode opaque IDs, merge
  numeric and opaque ID namespaces, or forge Core UUID correspondences.
- A mapping is not execution authority. Domain Exchange must not initialize,
  populate or activate Access, grant credentials/consent, or transplant approvals.
- Do not introduce PKI, signatures, HMAC, sender-trust winners, verification flags
  as identity, or a general adjudication/history/Publication mechanism. ADR 0027
  directly governs external Captures; this decision applies the same explicit
  authenticity limitation to mapping reports without broadening its old scope
  by implication. ADR 0028's digest remains consistency, not authentication.
- An unknown issuer or unavailable audit basis is not proof of a false report.
  Retain admissible reports; return uncertainty instead of effective revocation.
  A new genuine attributed report may be stored; a mere recheck or relay must not
  be presented as a new withdrawal event or salted into the original provenance.
- Changing Receiver/Source/Access state must not edit original domain keys.
  Partial receive never grants an unselected Repository merely to satisfy an FK.
- No old-format compatibility or real-data migration is required or authorized.
  Do not rewrite historical validation artifacts to imply new-schema acceptance.
- This PR is documentation only: no `src/`, production SQL/fingerprints, tests,
  workflows, Pages allowlist, merge, release, P8 switch or live-catalog operation.
  Implementation PRs require their own explicit authorization.

## Context & Reason

Repository identity is not a URL, Provider object, or access configuration. A PR
can use two different repositories while its commits share OIDs with other
repositories. A Provider Repository may have competing attributed mappings to
Core UUIDs. A generic single `repository_uuidv4` field loses roles; a mutable
mapping pointer loses conflicting evidence. The existing field-candidate clock
rules are appropriate for current affiliation, not for immutable identity claims.

The owner explored separate Witness persistence to distinguish a received
withdrawal report from a genuinely observed local operation. The supplied model
experiments isolated a different requirement: preserving historical check actions
is useful for audit, but is not necessary merely to re-evaluate present effect
from available original evidence. The owner declined that separate audit feature.
This is a scoped negative decision, not a claim that every Witness-like concept
in this repository is prohibited or that source authenticity has been solved.
See the [evidence and implementation handoff](../implementation/context-exchange-design-handoff.md).

A full ADR is justified because these are durable schema, wire-selection and
receiver-boundary decisions. Exact code generation and bounded traversal
algorithms remain engineering work, not another sequence of automatic owner
questions.

## Consequences

Benefits: explicit role/FK semantics, immutable attributed mapping alternatives,
portable direct keys, selective multi-Repository exchange, and no unnecessary
local verification-history subsystem. Costs: wider keys, typed dependency and
conflict handling, possible repeated external-evidence checks, and deliberately
limited receipt continuity after Operational loss. The database alone cannot
reconstruct an unstored historical check, nor can it prove who authored an
unsigned report.

### Preservation and dependency boundary

This ADR adds nonconflicting Context semantics and replaces a prior conversation
choice, not an existing ADR file. `replaces: []` is intentional. ADRs 0003--0028
remain in place within their operative scopes; no blanket retirement is authorized.
The owner-confirmed independent Access decisions remain binding. **Subsequently
on 2026-10-19**, the owner explicitly accepted ADR 0029 as the whole-record
replacement of historical ADR 0003 and approved retirement of ADR 0003 from the
current tracked tree. This subsequent editorial status note does not re-date or
expand the 2026-10-18 decision recorded by this ADR; the original `refines`
metadata remains historical. [ADR 0029](0029-independent-access-store.md) now
owns the active five-store boundary and its carried-forward Core/Context rules.
The [retirement record](../implementation/adr-0029-accepted-retirement-20261019.md)
documents the separate governance action, without runtime or merge approval.

Direct stack parent: PR #103, branch `fix/access-a6-independent-review`, commit
`1134e200eb4ac9ec45bf3fae3be695e2bb786a8d`, tree
`e53755ac9fa35cd436d67afbb8810f3c6c11fdc2`. Its inherited Access chain starts at
PR #95. Main was `b2a87cfc6562413d9ecde7f4329e90c434ae9aad` during preparation.
Future schema/intake/Exchange/review PRs should stack on this design, not silently
implement different conversation alternatives. Recheck refs before any merge.

Known additional **owner-policy blockers for this bounded design: provisionally
0**. This is not runtime readiness: mandatory implementation proof obligations
are listed in the handoff. Any discovered requirement that changes accepted
identity, evidence retention, authorization or backup guarantees must be reported
with an explicit counterexample instead of silently resolved.

## References

- [Context logical/physical contract](../architecture/context-repository-relations.md)
- [Selective Exchange contract](../architecture/selective-exchange-contract.md)
- [Source audit, experiment evidence and stacked implementation handoff](../implementation/context-exchange-design-handoff.md)
- [ADR governance](policy.md), [ADR 0017](0017-domain-keys-without-storage-surrogates.md),
  [ADR 0027](0027-unauthenticated-external-capture-origin-reports.md),
  [ADR 0028](0028-classified-times-and-sha256-exchange.md)
- [Accepted Access boundary and confirmed Scope decisions](0029-independent-access-store.md) (physical/adapter details remain separately proposed)
