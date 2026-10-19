# Context provider independence and extensible metadata audit

## Conclusion and decision boundary

The current opt-in Context is **Provider-namespaced but not an unrestricted metadata model**. Its existing 19 tables can preserve many external annotations, assessments, exact text, Provider relations, typed Git OID reports, mapping alternatives and Collection/Coverage evidence. Generic normalized synthetic data survives typed persistence, selective Exchange and receiver reread. Those results do not establish non-GitHub API normalization support.

Retain Context as the baseline location for Provider↔Core mapping. Multiple Provider repositories per permanent Core UUID already work; moving mappings into Core or a sixth store has no demonstrated advantage for these cases. The main obstacles to broader use are finite Resource/parent semantics, missing Provider-specific identity normalization contracts, and explicit target/clock/search conventions. No approved decision is changed or new feature declared mandatory by this audit.

**Current findings: 0 Blocking, 3 Major, 2 Minor; 0 demonstrated Implementation Defects or Architectural Conflicts.** Four consolidated Non-Issues are listed separately. Severity describes suitability for the proposed broader use, not release qualification. See [findings](context-provider-agnostic-findings.md), [options](context-provider-agnostic-options.md) and the detailed evidence linked below.

## 1. Fixed source, environment and scope

| Coordinate | Value |
| --- | --- |
| Repository | https://github.com/TakashiSasaki/git-repo-db |
| Freshly fetched main / audited product commit | `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9` |
| Product tree | `117d580b31098ecb8287281bd843894fdfad71fc` |
| Main integration | PR #112 merged; prior #95–#106 and ADR 0029/0030 available in this ancestry |
| Open/Draft PRs at start | None; actual timestamp and API result in [initial receipt](evidence/context-provider-agnostic/results/initial-github-state.json) |
| Investigation date | 2026-10-19 UTC / 2026-10-20 JST; use actual UTC receipts, not the user's calendar premise as an execution timestamp |
| Runtime | Python 3.12.14, actual SQLite 3.53.1, supported ≥3.51.3; not an exact-minimum run |
| Dependencies | `uv sync --locked --group dev` using the existing supported interpreter; product default initializer unchanged |
| Stores under test | Disposable opt-in production Core/Context/Operational and Search as needed; no real Catalog or Provider credential use |

[Environment, SQLite source ID and schema manifest](evidence/context-provider-agnostic/results/environment-schema.json) and [probe input hashes](evidence/context-provider-agnostic/results/probes/input-hashes.json) bind the evidence. The product source/tests/dependency tree is unchanged from the fixed main. Audit scripts and reports are additional files, not product features. Historical ADR wording such as “not implemented” records the original decision/PR scope; actual runtime claims here come from this commit and new executions. The ordinary Schema 21 initializer has not been switched to the opt-in model.

Authority reviewed: [AGENTS](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/AGENTS.md), [ADR index](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/docs/adr/README.md), [operating policy](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/docs/adr/policy.md), [0029](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/docs/adr/0029-independent-access-store.md), [0030](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/docs/adr/0030-context-repository-relations-and-selective-exchange.md), and their carried-forward identity, Coverage, clock, origin and Core constraints. No approved ADR text, DDL, fingerprint or production code is edited.

## 2. Logical model and physical schema

Resource identity is `(service_instance_uuidv4, resource_kind, provider_resource_id)`. `provider_kind` describes the service family; the service UUID distinguishes independent instances, including two instances of the same family. The database does not discover whether two URLs denote one service. Provider Resource identity and Core repository UUID remain separate.

The composed Context has exactly these **19** tables:

| Family | Tables |
| --- | --- |
| Catalog / registration | `store_identity`, `providers`, `repository_context`, `sources`, `source_repositories` |
| Resources / content / relations | `resources`, `field_candidates`, `text_bodies`, `resource_relations`, `core_references` |
| Collection / Coverage | `collections`, `collection_terminals`, `coverage_claims`, `coverage_scopes`, `coverage_proofs`, `source_inventory_evidence`, `source_coverage_proofs` |
| Repository mapping | `resource_repository_relations`, `repository_mapping_dispositions` |

Composed DDL SHA-256: `fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`.
SQLite schema SHA-256: `0a98df73ce1f9f81d8e76a64eb2b36a18b262cb0ff742ed9a088977f105e1134`.
`verify_declared()` passed against the packaged manifest. Access's independent DDL is not a missing twentieth Context table. [Schema composition](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_schema.py#L89) and [Context DDL](https://github.com/TakashiSasaki/git-repo-db/blob/efb55af84ccbf1183d47547d22bb6c57d8fbc8f9/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql#L1).

Resource kinds are `repository`, `pull_request`, `issue`, `review`, `comment`, `thread`, `document`, `assessment`, `identity`, `endpoint`, `annotation`, `lfs`. Review/document require a PR parent; thread requires PR/review; comment permits PR/Issue/review/thread. Their key includes the actual parent kind/ID, document kind and Provider document ID as canonical JSON. Other kinds have no parent columns; relate them with explicit Resource relations. Unsupported kind strings construct a `ResourceKey` but fail persistence. This is a layered validation boundary, not proof that arbitrary kinds are supported.

## 3. Provider-independence conformance matrix

| Requirement / stage | Finding at fixed main | Evidence / boundary |
| --- | --- | --- |
| Different Provider or instance, same ID | Supported | PR01, mapping forward/reverse; service UUID separates IDs |
| Project-local vs global ID | Contract required | PR02: bare iid collides; genuine tagged project+ID coordinate preserves distinction |
| Provider repository↔Core identity | Supported, attributed | 9 mapping probes, qualified effect distinct from Core presence and Access |
| Repository annotation / external assessment | Supported for existing generic semantics | PR06/07/08 and four-provider normalized roundtrip |
| Independent repository document / Issue discussion / commit review | Not faithfully supported by existing dedicated kinds | PR03/04/05; correct rejection exposes requirement gap |
| Provider event with independent identity | Restricted | Existing Issue timeline event is parent-keyed comment; hypothetical unrelated event kind rejected |
| Collection / partial / empty / permissions | Supported under explicit observation scope | CE partial/empty/missing and scoped-provenance probes |
| Incomparable Coverage clocks | No generic reconciliation | Numeric latest-observation rule requires adapter scope/time contract; CE unpartitioned characterization |
| Non-GitHub live normalization | Not implemented/verified here | Production intake routes currently use GitHub normalizers; normalized synthetic cases do not fill this gap |
| Exchange / dependency withholding / replay | Supported for exercised admitted units | 37 probes plus existing i3/i23/i4 cohort |
| Search / fallback / backup | Existing supported projections preserved | I4 cohort; structured JSON has narrower Search coverage than typed read |

## 4. Provider identity comparison

Official API evidence, successful retrieval timestamps, URLs, content hashes, excerpts and failed retrieval attempts are in [provider sources](evidence/context-provider-agnostic/research/provider-sources.json). This is public-document research; no live account data was acquired. Detailed namespace and kind analysis: [Provider/Resource research](evidence/context-provider-agnostic/research/provider-resource.md).

| Provider | Genuine identity distinction | Consequence for normalization |
| --- | --- | --- |
| GitHub | REST numeric IDs, GraphQL opaque node IDs, repository-local Issue/PR numbers | Keep API identity namespaces distinct; do not decode opaque IDs or substitute number/URL. Existing GitHub normalization has tagged node identity handling. |
| GitLab | Global `id` versus project-local `iid`; project-scoped discussions/notes and commit discussions | Prefer actual global ID when specified; otherwise preserve the real project+local-ID namespace with a reviewed reversible encoding. Merge Request is not supported merely by relabeling an unreviewed payload PR. |
| Gerrit | Change number and composite project/branch/Change-Id; Change-Id alone is not globally unique; revisions and robot comments have their own scope | Preserve the documented complete coordinate and stable API identity; branch/project movement cannot be silently solved with a URL key. |
| Gitea | Issue/PR API addresses include owner/repository/index; payload exposes ID and index; review/comment endpoints have separate scopes | Do not assume a repository-local index is a service-wide key; versioned API source is retained as evidence. |

The actual-spec counterexample is GitLab's repeated project `iid`; the probe uses synthetic values derived from that documented namespace rule. Independent service same-ID and immutable parent-rebinding scenarios are synthetic architectural counterexamples. No fetched documentation establishes universal ID non-reuse across all Provider versions. Rename, transfer, delete/recreate, import and ID-reuse rules therefore require Provider/version-specific contracts; do not manufacture a lifecycle generation or merge identities based on URL/name/OID. Existing Issue identity is independent of its affiliation; document/review identity deliberately includes its parent, so a hypothetical independently movable document would change key under this schema.

## 5. Resources, Annotation and targets

| Target / information | Present representation | Remaining semantic boundary |
| --- | --- | --- |
| Provider Repository / Resource | Annotation or assessment ResourceKey; exact text/field candidates; explicit ResourceRelation members | Relation names beyond built-in semantics need a documented meaning; generic relation is not an ADR 0030 repository role |
| Commit / Git object | `CoreReference` using `(object_format, full_oid)`; `report_core_reference` retains unacquired reports | Reported reference is distinct from `link_core` required validated dependency, Git type, repository membership and retained bytes |
| File / commit-relative location | Path, line/range and side can be scalar/JSON field data | No audited typed target schema validates path bytes, revision association, line basis or range; JSON storage alone is not semantic support |
| Several repositories | Explicit relation members pointing at distinct Provider Repository resources; mappings remain separate | Cannot invent `owning_repository` for annotations or a seventh generic Core relation role |
| Author / source / issuer | Resource fields/identity relations plus mandatory attributed provenance | A source string, author name and claimed issuer are different assertions, not authentication; local observation identity needs a genuine producer/operation contract |
| Current value vs independent report | Field clock candidates retain current equal/incomparable alternatives; separate genuine Provider resource IDs can represent separate reports | Dominated current fields are pruned; not a full edit/event archive; never create fresh IDs merely for retry |

PR07 executes absent-OID assessment admission/read and required-link refusal. The generic Exchange probe preserves assessment JSON and annotation text/relations; it does not claim a typed file-location or every OID-reference combination was round-tripped. Missing field, explicit JSON NULL and same-clock competing scores are checked separately. No new raw API retention, complete edit history or arbitrary binary requirement is introduced.

## 6. Mapping and store placement

[Mapping research](evidence/context-provider-agnostic/research/mapping.md) traces all requested tables, six role constraints, forward/reverse API calls, SQL/FK boundaries and placement alternatives. Forward: `evaluate_provider_repository(ResourceKey(...,'repository',id))`. Reverse: `relations_for_repository(uuid, 'represents_repository')`; preserve claim alternatives while optionally deduplicating ResourceKeys for display.

Claims are append-only positive correspondences. Different UUID targets coexist as conflict; neither later clock nor URL/OID/name equality elects a winner. Dispute/withdraw/correct reports persist; supplied current operation evidence can qualify effect without a Witness table. The synthetic evidence object used in tests establishes evaluator behavior, not an authenticated real-world operation. Context-local registration is required by FK; an active UUID candidate can exist without any Core or Access DB. Actual Core presence/acquired bytes and saved-access approval must be checked independently.

Retaining **A: Context** preserves local FKs to resources/claims/dispositions, existing paired snapshots and Exchange. **B: Core** moves external Provider authority into Git Core and loses independence unless identities are duplicated or externally joined. **C: Link store** makes both endpoints cross-file, adds an authority/failure/backup boundary, and still needs identity and trust rules. Sharing exact claims between Context stores through Exchange is already possible; sharing one mutable authority across them is a distinct unproven requirement. The full comparison includes transactions, crash outcomes, restore, selective Exchange, permissions and growth; none is decided by this audit.

## 7. Collection and Coverage

Collection kind is extensible text and its owner is an existing Resource; nested semantics can be validated for recognized relations. Provenance and explicit scope distinguish real acquisition observations, permission views and provider namespaces. A terminal with zero members can prove empty; no terminal is unknown. Existing members do not imply enumeration completeness. Partial terminals cannot prove complete, and a newer unknown terminal invalidates an older complete projection. Missing selected dependencies cause withholding, not manufactured registration/completeness.

The **five physical Coverage Claim columns remain unchanged**. Observation selection compares positive numeric `observed_at_us` within the precise owner key; this is not field-clock domain arbitration. Different providers/permission views/clock domains must not be merged into one owner with incomparable numbers. Distinct actual collection provenance/scope can partition evidence, but a future generic collector needs a written acquisition-clock and ownership contract (F04), particularly for resource/repository summary scopes. No new clock column is proposed as an automatic answer. See [Coverage/Exchange research](evidence/context-provider-agnostic/research/coverage-exchange.md).

## 8. Whole-path verification and limits

| Path segment | Executed evidence | Limit |
| --- | --- | --- |
| Provider payload → normalization → admission | Existing i23 GitHub synthetic REST/GraphQL fixtures and PR10 | No GitLab/Gerrit/Gitea live or raw-payload normalizer acceptance |
| Normalized generic unit → SQLite → typed read | PR/Mapping/CE probes, actual production Context facade + packaged DDL | Not raw-SQL-only success; parent/kind refusals recorded |
| Typed selection → Exchange → different catalog → reread | Four Provider labels in CE; existing i3/i23 | Labels are synthetic normalized inputs, not independently implemented adapters |
| Partial dependencies / replay | CE missing member, Mapping missing claim, i3; unchanged observations on resend | Operational receipt continuity after loss remains scoped by ADR 0030; no authenticity guarantee |
| Search rebuild / missing-stale-damaged Search fallback | Existing I4 | Plain text/string projections; arbitrary nested JSON analysis is not automatically indexed |
| Paired backup / fresh disposable restore | Existing I4 | No real Catalog restore; Access deliberately outside ordinary domain backup |

The added probes **37/37 passed**; existing focused i3/i23/i4 **126/126 passed**, with exact collection/JUnit/journal reconciliation (378 phases). These are 163 distinct focused cases, not the full repository suite or release acceptance. Independent reviewers' reruns overlap and are not added to that total. [Reproduction README](evidence/context-provider-agnostic/README.md), [case matrix](evidence/context-provider-agnostic/case-matrix.json), [probe receipt](evidence/context-provider-agnostic/results/probes/receipt.json), [existing reconciliation](evidence/context-provider-agnostic/results/existing-reconciliation.json).

## 9. Classification and severity

[F01–F05](context-provider-agnostic-findings.md) include conditions, actual/expected meaning, code lines, ADRs, impact and options. F01 is Requirement Coverage Gap; F02/F03/F04 are Engineering Contract Gaps; F05 is Extension Opportunity. N01–N04 consolidate confirmed Non-Issues. No correct rejection is classified as an implementation defect. No guessed ID reuse guarantee, universal event model or unsupported live acquisition is reported as verified.

## 10. Improvement order and impacts

Use current tables and typed APIs first where they preserve meaning. Next define Provider normalization and canonical identity contracts; add typed semantics/validation for genuine new targets and views. Only then consider extensions to Context vocabulary or relations. A new entity, responsibility change or store requires a concrete unresolved meaning/ownership need. [Options](context-provider-agnostic-options.md) compare all seven requested levels across identity, Coverage, Exchange, Search, backup and verification cost.

## 11. Independent review

Two separate agents **approved this documentation audit** after reviewing R1/R2 and R3/R4 directly against the fixed product source and frozen audit commit `19ff4031440e541eeff9a119605b2b564ca5dd6d` (tree `c5f8f3cecf30b6ba11f65ff7cd2aad3bdb248c9e`). [R1/R2](evidence/context-provider-agnostic/independent-review/r12.md) independently repeated the 37 probes, 118 existing cases and 14 direct assertions. [R3/R4](evidence/context-provider-agnostic/independent-review/r34.md) independently ran 11 I4 cases and reconciled execution evidence; it verified the two minor wording corrections recorded in its receipt. No unresolved reviewer finding remains. These overlapping runs are not added to the 163 author cases. Investigator research is not independent review, and review approval does not select the proposed designs.

## 12. Designer decisions still needed

1. Which additional resource identities/parent relationships are genuinely required (repository documents, Issue discussions, commit reviews, independent events), and whether existing annotation/assessment semantics are sufficient for each.
2. Provider/version identity namespace, composite encoding, movement/reuse and local-authoring contracts; no implicit identity rewrite.
3. Typed target coordinates and query behavior for files/commit-relative positions, author versus issuer, and multiple repositories.
4. Comparable Coverage acquisition times and evidence partitioning/aggregation per owner and permission view while retaining the five-column model.
5. Whether structured metadata needs field-specific Search projections beyond current text behavior.

The recommendation is to preserve the existing five stores, UUIDs, claims/dispositions, no-Witness decision, original provenance/clocks, Source known positives, Coverage columns, selective Exchange boundaries and independent Access. The audit supplies counterexamples and alternatives; it does not accept any new design.
