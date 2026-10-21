# Context extensibility options — evaluation, not decisions

[Main report](context-provider-agnostic-audit.md) and [findings](context-provider-agnostic-findings.md) fix the evidence at main `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`. No option is accepted or implemented here. Preserve meaning before minimizing changes; do not disguise a Discussion as an unrelated allowed resource solely to pass a CHECK.

## Ordered solution space

| Level / option | Fits demonstrated need | Schema and identity | Coverage | Exchange and Search | Backup and verification cost |
| --- | --- | --- | --- | --- | --- |
| 1. Use existing APIs | N01–N04: mapping, annotation, assessment, exact text, Provider relations and typed OID reports | 19 tables unchanged; genuine IDs/provenance unchanged | Existing scoped claims/proofs/terminals | Proven typed selection/receiver reread; current text Search | Existing paired snapshots/validation; add focused use-case probes, low cost |
| 2. Provider adapters / normalization | F02; portion of F04 | Prefer genuine global IDs or defined reversible composite coordinates; no table needed for represented kinds | Provider paging, permissions and comparable observation clocks must be specified; no claim-column change | Existing typed transport works after correct normalization; text projections reusable | Preserve snapshots; specification-derived golden fixtures, transfer/rename/replay and paging tests; medium per-Provider cost |
| 3. Typed API and validation contracts | F03/F04; F05 query/projection; early kind refusal convenience | Define target/actor/relation meanings and local report identity; validate existing fields consistently at admission/read/decode | Explicit semantic scope and aggregate restrictions; partition only genuine observations | Receiver validation must enforce same contract; structured Search remains derivative with scan equivalence | Same DDL may suffice, but semantic restore checks need review; medium cost across layers |
| 4. Extend existing Context vocabulary/relations | F01 where actual kind/parent is unrepresentable | Finite enum/parent rules and fingerprint change; review parent-key implications and natural keys | New information type can use existing claim columns; owner/member contract must be defined | Update typed dependency expansion, decoders and kind-specific views; no automatic completeness | Whole SQLite backup copies rows but semantic decoder/restore must support them; high coherent cross-layer regression cost |
| 5. Add Context relation/entity | Only concrete identity/target need that levels 1–4 cannot preserve | Real semantic PK/FK and provenance required; no Witness, Publication or storage surrogate | Define typed owner/proof rules without widening physical claim columns by default | New wire unit, selection/dependency boundaries and projections | New fingerprint/semantic validation and failure matrix; high cost; no table name selected by audit |
| 6. Change Context responsibility | No demonstrated need in current counterexamples | Requires accepted boundary decision; Core independent/INSERT-only remain protected | Moving completeness authority splits resource/evidence dependencies | Redesign cross-store selection/admission/read trust boundaries | Paired snapshot/recovery manifest/activation semantics change; very high cost and new independent review |
| 7. Independent Mapping/Link store | Only if an actual independent sharing/authority requirement is proven | Another authority; both endpoints cross-file unless duplicating identities | Does not solve Provider clock or namespace semantics | New selection/wire/admission and Search dependencies; no identity/authenticity benefit merely from placement | New coherent backup/restore/permission/failure protocol; highest cost; no present evidence warrants it |

All options preserve permanent UUIDs, Git Core INSERT-only, the five-store boundary unless separately changed by the owner, original clocks/provenance, canonical JSON/direct keys, missing/NULL/unresolved/conflict distinctions, Source known-positive membership, the current five Coverage columns, six ADR 0030 roles, append-only mapping claims, qualified dispositions, no Witness/Publication and Access as connection-authority owner.

## Repository mapping placement comparison

The detailed [mapping research matrix](evidence/context-provider-agnostic/research/mapping.md#placement-alternatives-evaluation-only) covers semantic responsibility, Provider independence, Core independence, SQLite FKs, transactions/faults, backup/restore, selective Exchange, several Context stores, permissions and future bridge growth.

| Choice | Concrete benefit | Concrete cost / missing justification | Assessment |
| --- | --- | --- | --- |
| A. Context (current) | Real local FKs among Provider Resource, registration, mapping claims and disposition references; typed forward/reverse lookup and conflicting alternatives already pass | Core presence remains an application-level check; several Context copies may hold different evidence and qualifications | Baseline recommendation; do not confuse these honest limits with corruption or proof that another DB is needed |
| B. Core | Core Repository endpoint could be local FK | Provider endpoint becomes external/duplicated; Provider authority enters Git Core; expanded writer trust; Core-only backup meaning changes | No demonstrated net gain; requires boundary decision and coordinated redesign |
| C. Mapping/Link store | Possible common service for independently managed Context catalogs | Both endpoints external; additional transactional/authorization/snapshot/recovery/Exchange responsibilities; does not authenticate mapping | Defer absent a concrete sharing/concurrency/trust requirement that Context Exchange cannot satisfy |

SQLite does not enforce an FK into a separately attached database. Moving a mapping table can relocate one FK problem, not eliminate all dependency checks. Existing Context-local UUID registration is deliberately weaker than proof of actual Core registration. Core-first writes can survive later Context failure; neither an extra store nor a shared SQLite connection implies a distributed all-or-nothing transaction. Current paired backup must report its exact component scope and exclude independent saved Access settings.

## Recommendations for designer review

1. Preserve the present 19-table foundation for demonstrated annotations, mappings and scoped collections. Do not make all broader examples mandatory product features.
2. Select concrete Provider/API versions and information types; define stable identity, composite scope, local-authoring and lifecycle rules before writing adapters. Raw API originals/history/binary retention remain out of scope.
3. Prototype typed target/actor and permission/clock contracts over current fields and relations, with actual semantic read/Exchange tests. A new table is not the first step.
4. For a real Issue discussion/repository document/commit review that cannot fit faithfully, compare a narrow kind/parent extension with an independently identified resource and explicit target relation. Preserve existing document semantics unless a separately approved change replaces them.
5. Decide whether nested analysis search and cross-domain Coverage summaries are desired. Keep unsupported semantics explicit until implemented and verified.

Unresolved choices are not blockers to completing this audit. Their eventual implementation requires its own authorization and, where accepted persistent meaning or responsibility changes, the repository's ADR process. This PR creates no accepted ADR and authorizes no migration, runtime switch, deployment or merge.
