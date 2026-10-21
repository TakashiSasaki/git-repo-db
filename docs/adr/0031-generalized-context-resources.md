---
status: proposed
date: null
replaces: []
refines:
  - 0017-domain-keys-without-storage-surrogates.md
  - 0028-classified-times-and-sha256-exchange.md
  - 0029-independent-access-store.md
  - 0030-context-repository-relations-and-selective-exchange.md
---

# ADR 0031: Generalized Context Resource identity and relationships

## Decision

This **proposed complete design package** records logical choices already selected
by the owner in the task “git-repo-db: Record the agreed generalized Context
Resource design in a Draft PR”, sections 3–7. The choices below are fixed for
this design; they are not unanswered option questions. The package, its physical
realization and engineering proposals have not been accepted. No conversation
URL or approval of the complete package is invented.

**READY FOR OWNER DESIGN ACCEPTANCE.** G3 meaning is decided; the bounded SQL
delta and non-author reviews are complete. Whole-package owner acceptance is
still separate.
On **2026-10-21**, the owner explicitly selected **G3=A** in the task
“git-repo-db: G3=A integration, Q-S10 SQL differential demonstration and ADR 0031
acceptance preparation”. The native Issue I7 is the semantic Issue of this
Q-S10 Event. This is one scoped decision, not acceptance of ADR 0031 or its
experimental implementation. [Pinned evidence and obligation mapping](../implementation/evidence/context-resource-design/cprime-integration.md)
separate the historical F2 construction, the new [G3=A evidence](../implementation/evidence/context-resource-design/g3-a/README.md),
independent review and future product integration. The ADR stays proposed until
explicit whole-package owner acceptance.

Keep the Resource primary key:

```sql
PRIMARY KEY (service_instance_uuidv4, resource_kind, provider_resource_id)
```

`provider_resource_id` is TEXT containing the canonical JSON serialization of
`IdentityValue := String | Array<IdentityValue>`. The common parser/serializer,
exact equality and admission boundaries are specified in the companion
[schema contract](../architecture/context-resource-schema.md). This changes the
representation of currently plain-string IDs; it does not issue new identities.

### Owner-selected ledger

| Selection | Meaning and consequences |
| --- | --- |
| **A3 — open vocabulary, typed known contracts** | A new unknown kind need not be added to a closed DDL enum to satisfy the generic Resource contract. Known kinds, relations and operations retain their explicit constraints. Invalid known input cannot be retried as opaque data to bypass those constraints. |
| **B3 — coordinates versus Parent** | Include namespace/Parent coordinates in identity only when native identification actually needs them. Semantic containment, affiliation, reply-to and Parent are separately evidenced facts; the graph need not be a tree and Documents need not be leaves. Parsing an arbitrary Provider ID never establishes a Parent report. |
| **U3=C′ — existing `resource_relations`** | That table is the sole authority for semantic Parent reports. Extend existing tables/constraints/indexes or generated projections; add no Parent domain table. Preserve coherent multi-member reports. `members_json` and supporting columns cannot be independent writable accounts of one fact. Historical F2 demonstrates the bounded construction; G3=A adds the native-Issue SQL obligation. Product integration remains unimplemented. |
| **U4=B — independent admission** | Admit a complete child identity without a registered Parent. Withhold the Parent report and dependent typed operations while their referents/evidence are missing, and report the dependency. Do not fabricate a Parent or retain an unadmitted relationship payload in a hidden queue. Later Parent arrival alone does not recreate it; resupply the original report with its identity, times and provenance. |
| **U5=A — generic preservation and exchange** | Store, read and exchange unknown kinds through the supported common format without kind-specific interpretation. Explicit selection/permission, complete atomic units, dependency/provenance checks and finite work limits still apply. Unknown kinds are not unknown wire versions; arbitrary JSON or a relationship name grants no traversal, authority, completeness or business meaning. |
| **U1=B — Provider-scoped meaning** | Interpret a kind in its service-instance namespace. Two Providers using the same unknown name do not establish equivalence. Reserved common names retain known typed contracts. Kind is a stable key component, never a mutable display label. No new Provider-prefix rule, global registration table or universal per-resource tags. Future typed support cannot silently reinterpret or rekey old opaque Resources. |
| **U2=A — recursive identity value** | Use only strings and recursively nested arrays, canonically encoded as TEXT. Reject JSON numbers, booleans, objects and null in identity. Adapters normalize genuine native IDs, including lossless numeric-coordinate conversion to strings when their contracts call for it. The common layer does not stringify arbitrary input. Distinct native ID namespaces must remain distinct; tags are permitted when meaningful, not universally required. |
| **U2-E2 — meaningful empties** | `""` may be a complete native ID; `[]` may identify a genuine singleton using service+kind alone. Neither is a missing/unknown/placeholder value. Nested empties need actual coordinate meaning too. `""`, `[]`, `[""]`, `[[]]` are four distinct values. The grammar permits them; adapter evidence establishes legitimacy. SQL cannot infer a Provider singleton from syntax. |
| **G3=A — Q-S10 semantic Issue (2026-10-21)** | For Event E natively identified under Issue I7, I7 is its semantic Issue. Preserve a lawful attributed Parent report for I8, but permanently reject that I8 support for E's Transfer as a Q-S10 violation. Missing correct I7 support is a dependency failure, revalidated only on original-report re-supply. Eligible I7 support succeeds only with every other Q-S10 condition. This constraint is confined to Q-S10, not general Resource namespace/Parent equality. |

For example, native service-wide string `"731"`, native scoped value
`["project-a","731"]`, and a native no-additional-coordinate singleton `[]`
are possible identities under different explicit identification contracts.
`"731"` and `["731"]` differ. These are illustrations, not new Provider adapters.

### Document identity and the decided Q-S10 Issue contract

A genuine Provider-global Document uses its complete scalar or recursive-array
identity with kind `document`; no PR namespace is invented. A genuine PR-scoped
Document retains every accepted PR/subtype/local-ID coordinate. Native-contract
dispatch must not retry malformed known PR input as a global Document.

For known scoped documents, specify one new-format representation:
`J([namespace_kind, J(namespace_identity), document_kind, native_document_id])`,
where `J` is the canonical identity serializer. The second component is a string
containing canonical namespace ID TEXT, never its decoded array. This explicit
engineering choice preserves semantic coordinates; dual-profile decoding is
forbidden. [G1–G3 reconciliation](../architecture/context-resource-schema.md#semantic-gap-dispositions)
defines the tested forms and their SQL/admission boundaries.

For Q-S10 Event E natively identified under I7, only a qualifying complete I7
Parent report can support E's Transfer. An I8 report remains separately retained;
it must not be deleted, corrected, selected as a winner or used as E's Transfer
support. I8 support is permanently ineligible for this E, not awaiting additional
qualification. Missing I7 Resource/report is instead a dependency failure: later
arrival does not replay the withheld unit; re-supply its original report.
I7 in Identity proves neither its Resource row nor a Parent/Event report,
endpoints, original times/provenance or Provider authenticity. The historical F2
`QualificationRequired` guard records temporary handling before this decision;
it is not the current disposition. No general Parent-equality rule is adopted.

## Constraints / Do NOT

- Preserve accepted PR Document semantic coordinates
  `(change_request_id, kind, provider_change_request_document_id)` where that
  contract applies. Represent them reversibly within the Resource key; do not
  drop a genuinely required coordinate under the name of generalization.
- Document is a Resource kind, not a parallel identity system. An Issue's text
  does not by itself require a separate Document Resource. Resource identity,
  exact content identity and observations/reports are different identities.
- Do not repair incomplete identity using arrival/acquisition time, arbitrary
  tags, hashes, local row numbers or new UUIDs. Preserve permanent
  `repository_uuidv4`, service identities, genuine Capture pairs and other
  already approved domain identities under ADR 0017.
- Keep Core, Context, Access, Operational and Search separate. Context retains
  Provider Repository ↔ Core Repository mapping authority, immutable claims,
  Dispositions and their qualification rules. Preserve all six ADR 0030 roles.
- Q-S10 still requires an Issue-parented Timeline Event with typed SQL reference
  guarantees **and** admission checking of actual event semantics. A structural
  SQL reference does not authenticate an external event. SQL must reject an I8
  Transfer support even without Admission, while retaining the general I8 report.
- Preserve Core INSERT-only, Source known-positive membership, original clocks,
  competing alternatives, exact retained text and the five-column Coverage
  model. Q-E5/Q-E6 selection and no-fabricated-referent rules remain binding.
- Do not add Mapping Witness storage, Publication, another link store, whole API
  response archives, universal edit histories or ordinary Git blob bodies.
- No backward compatibility or real-data migration is required for this
  unreleased redesign. Historical evidence must keep its original scope/result.
  This task changes no production code, packaged DDL/fingerprint, dependency,
  existing runtime test, workflow or default runtime; it authorizes no P8,
  merge/auto-merge, release/deployment or live-catalog/Provider operation.

## Context & Reason

The fixed [PR #113 audit](../implementation/context-resource-design-handoff.md#fixed-baselines-and-evidence)
shows a Provider-namespaced 19-table Context whose finite kinds and universal
parent restrictions exclude broader independently identified Resources. The
owner selected generalization while preserving typed known semantics and the
existing store boundary. Native ID normalization/lifecycle and new adapters are
separate work; their absence does not reopen the common choices.

This is a Level 3 full ADR: it changes shared durable schema/wire/admission
contracts and typed-reference responsibilities, even without legacy migration.
Costs include wide semantic keys, consistent canonicalization at every reference,
explicit dependency withholding and re-supply, and renewed cross-layer validation.

`refines` above identifies only nonconflicting logical extensions: domain keys,
canonical integrity, independent Context and bounded typed Exchange. The current
closed Resource DDL and universal Parent columns are physical constraints being
generalized, not a reason to erase accepted identity or typed-reference meanings.
The [clause matrix and conditional carry-forward plan](../architecture/context-resource-schema.md#adr-compatibility-and-lifecycle-plan)
identifies two potential substantive reversals, both excluded by this design:
dropping genuine PR-document coordinates and weakening Q-S10 to application-only
validation. Q-S6's finite vocabulary is the six Resource-to-Core roles, which
remain closed. `replaces: []` means no accepted file is retired. If a concrete
conflict is discovered, report it and follow policy §6's replacement process;
do not relabel it refinement. G3=A preserves Q-S10's semantic Issue and adds its
explicit scoped realization; it does not reverse the accepted meaning or permit
application-only enforcement. This task performs no accepted-ADR body edits.

## Consequences

The logical design permits a complete child before its Parent and preserves
unknown kinds without pretending to understand them. Identification scope stays
stable while relationship reports remain separately attributed and competing.
All key occurrences must agree on the canonical text and exact comparison.

**Historical U3=C′ evidence demonstrates its earlier subset, extended by G1/G2;
G3=A now has separate frozen SQL-delta evidence and independent execution.**
The [new receipts and reviews](../implementation/evidence/context-resource-design/g3-a/README.md)
cover the scoped addition on both real runtimes. Historical reviewed executable
freeze `9eeacb28f7e4a426114a9ce40e2324b4da302817` preserves 19 Context tables and
uses real typed FKs, CHECK/projections and replay triggers. Whole Transfer units
still require application admission, strict original timestamps, declared member
checks and atomic endpoint handling. Neither SQL nor these checks authenticate
Provider reports. The [acceptance contract](../architecture/context-resource-schema.md#u3c-experimental-acceptance-contract)
and evidence map retain each obligation and distinguish the new G3=A evidence.

The [implementation handoff](../implementation/context-resource-design-handoff.md)
separates fixed choices, proposed engineering bounds, future implementation
sequence, verification requirements and actual documentation checks. This Draft
remains proposed pending explicit owner acceptance of the whole package. The old
163-case audit and original C′ freeze retain their original scopes. Product
Exchange, stored integrity, paired backup, query/Search and packaging integration
remain future work; disposable SQL evidence does not implement those paths.

## References

- [ADR index](README.md), [operating policy](policy.md), [ADR 0011](0011-adr-governance.md).
- [ADR 0017](0017-domain-keys-without-storage-surrogates.md),
  [0028](0028-classified-times-and-sha256-exchange.md),
  [0029](0029-independent-access-store.md),
  [0030](0030-context-repository-relations-and-selective-exchange.md).
- [Schema/equality/compatibility contract](../architecture/context-resource-schema.md).
- [Fixed-source evidence, implementation and review handoff](../implementation/context-resource-design-handoff.md).
