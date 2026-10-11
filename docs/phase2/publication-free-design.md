# git-repo-db: Publication-independent architecture

Status: design reconstruction under the owner's accepted constraints; not a deployed schema or a claim of completed independent implementation review.
Date: 2026-10-10.

## 1. Authority and verified integration baseline

The owner chose P2-Q01-B, P2-Q02-B and P2-Q03-B: latest accepted PR state, PR text/conversation/thread state, and current known Source inventory, with genuinely necessary evidence rather than a complete history of previous values. P2-Q04 is **NO_INDEPENDENT_PUBLICATION**. Further multiple-choice decisions are paused.

These decisions, the transport-independent ADR and Phase 1 retirements override the Publication-centered draft. Preserve repository/service/Source identity, natural document keys, int64 epoch microseconds, the five-column Coverage contract, truthful per-field module/version provenance, missing/null distinctions, conflicts, transfers, exact domain text/Git bytes and CAS-41. No new deletion-on-absence, retention duration, provider trust or Git interpretation policy is silently selected here.

Verified main: `20e0f8d78b77c6c8d37826fd6d639819631e166b` (Schema 18). PR #22 contains the superseded proposal. PR #23 (`162581dfcfb501311d4993e90cdd160fb64d6e35`) contains Schema 19 correctness/index fixes. PR #24 (`52a36cab26f2287591ff9296cac151fe135cc55a`) improves tests. PR #25 (`0bd5704caca2f6e3723bef22531b065cd4d7bad0`) supplements the audit. These form #22 -> #23 -> #24 -> #25. PR #26 (`26c5972d0187c52e4780f55cc9e307b84c71cbee`) records the no-Publication decision on a sibling branch based on #22. Re-fetch before implementation; integrate the decision overlay without losing #23-#25 corrections. None is implicitly authorized for merge by this document.

## 2. Remove the abstraction, not just its name

The target has no generic Publication identity, member registry, input/output seal, selected interpretation, publication dependency graph or publish transition for ordinary resource eligibility. Do not recreate one as a batch, bundle, generation, receipt, revision history or family-specific Publication.

A retained grouping must answer a domain/operational question independent of committing database writes: which files belong to an exact PR comparison; which refs were observed in a Git acquisition; which members were enumerated under a scope; which unresolved record lacks its parent. It must not become the universal creator/owner of heterogeneous resources.

**Counterfactual test:** if the same domain facts are committed in two local transactions instead of one, their semantic identities and availability do not acquire a new Publication identity. Database transactions are execution boundaries, not cataloged domain objects.

**Dependency-direction test:** collection membership/proof refers to resources or their required identity evidence; an otherwise valid resource does not need a complete collection/proof in order to exist or be read.

## 3. Target responsibility map

| Responsibility | Durable information and ownership | Ordinary use condition |
|---|---|---|
| Identity | Existing repositories, services, Source registrations, bindings, natural document/Issue/Review/thread identities | Typed identity and owner constraints |
| Current domain values | Current PR attributes; current document values keyed by the existing document key; current thread state; existing Issue/review stores; current known Source associations | Direct resource validity, required parent availability and unresolved-domain-conflict rules |
| Necessary evidence | Current fields' producer/clock/capture; unresolved candidate evidence; minimal still-used code targets; scoped enumeration evidence | The specific domain question, never a generic transaction seal |
| Git content and capture | Verified object identity/bytes and intrinsic relations; observed refs/roots/acquisition context | Object integrity and exact domain dependencies; scope completeness is separate |
| Collections/Coverage | Scope, observed members, meaningful terminal/child evidence, actual observation boundaries; existing five-column claims | Only complete-list/target queries require their completeness predicate |
| Operations | Jobs, fences, restart cursors, cache hints, local revision, import processing state | Required to execute/retry work, not to validate already committed domain facts |
| Exchange | Actual domain records, their typed dependencies and permitted scoped evidence | Per-record admission; missing dependencies/conflicts remain explicit |
| Search/maintenance | Rebuildable projections; domain CAS/quarantine; verified backups and atomic catalog installation | Derived from valid retained domain data, not HTTP or Publication history |

This is a logical model, not eight mandatory tables. Prefer existing typed families. Do not create a universal `(table_name, opaque_key, payload)` store to avoid proper keys/FKs. The obsolete 69-table sketch is neither a target nor a count requirement.

### Reference row layout (implementation mapping, not a new lifecycle choice)

| Typed family | Key / representative retained columns | Direct dependencies |
|---|---|---|
| PR identity + current state | Existing `change_request_id`; repository/binding; state, draft, head/base format and OIDs; field evidence | Repository/binding only, not a fetch or result |
| Document current state | Existing `(change_request_id, kind, provider_change_request_document_id)`; author/URL; explicit body status; current text digest; field evidence | PR natural owner and required current text |
| Thread current state | Existing `(change_request_id, provider_resource_id)`; current resolved/outdated attributes; necessary exact code anchor; field evidence | Same PR and referenced domain targets |
| Existing Issue/review families | Existing typed natural identities/current membership and current values | Preserve parent/reply/thread, capture, conflict and local-check contracts |
| Source roster | Existing Source-to-repository association key; current known association and applicable scope/confirmation evidence | Source registration and repository identity |
| Code list/assessment | Actual comparison target identity; head/base/role; entry ordinal/path/OID; required-domain status | Exact target, list entries and verified objects when present |
| Git intrinsic facts | Object-format/OID identity; existing internal object ID if useful; ordered parents/entries, raw names; actual decoder provenance | Verified owning Git object, not acquisition-wide parser output |
| Collection evidence | Exact domain scope + observation/assessment identity only where required; known members/terminal/gaps/child context | Resources' stable identities and the specific domain evidence |
| Pending/conflict data | Typed resource key, candidate values/evidence, unresolved reason | Actual missing parent/owner or conflicting current candidate |

`change_request_state` and `document_state` are useful descriptive names, not mandatory extra tables: retain or combine identity/state tables when constraints remain clear. Optional minimal evidence IDs need not imply a global observation table. Do not duplicate a PR body/title into two independent authoritative value stores. Use the existing kind codes and exact natural-key semantics. A generic JSON `payload` is not the target schema.

A normal reader is governed conceptually by `valid_identity AND valid_owner AND required_parent_available AND content_valid AND no_relevant_unresolved_conflict`. Its query does not join a Publication/result/profile table, check a job's success or require an entire collection to be complete. A query explicitly asking for a complete list adds that list's separate scope/evidence predicate. Unknown content or a conflicted parent must be reported accurately rather than bypassed by an unconditional row read.

## 4. Current-state storage and evidence

Keep existing identity tables and add/merge the current value columns within their typed resource family. A PR's title/body or conversation comment uses the existing document natural key; do not add document version identity. PR metadata, document content, thread attributes and Source membership reference their own domain owners directly, not `parsed_result_uuidv4` or a fetch.

For each retained field or shared-origin group, retain: actual module/version, provider clock and its comparability scope where known, actual observed time, necessary parsed time and capture/owner context, plus explicit presence. Inline closed evidence JSON or typed dependent rows are implementation layouts, not a new observation ledger. An inherited value retains its old evidence. A newer title-only update does not reattribute the old body. Evidence itself may legitimately be stronger even when the value is equal.

Latest accepted is not last received. Reuse established provider-ordering, live revision/scope fencing and conflict semantics. An incomparable differing candidate is retained as an unresolved domain candidate; ordinary undisputed-current readers must not arbitrarily choose it. Imported confirmation time does not advance the receiver's local check time. A clock may be unknown; do not manufacture it from parsing/commit time.

No unconditional append of a prior PR/comment/roster state for each update. Necessary evidence is bounded by what it certifies: current values, actual unresolved alternatives, retained scope assessments or live domain targets. It is not permission to mirror every old value. A code assessment can retain head/base OIDs and role/scope even after the PR changes, but not the entire old PR body merely for provenance.

Current-only does not itself implement physical garbage collection. Shared text may have unreferenced bytes until an independently authorized reclamation policy exists; do not claim those bytes were erased or expose them as supported edit history. Never add mandatory old-value references solely to prevent their deletion. Actual provider event occurrences are domain events, not automatically edit history of a mutable PR; preserve existing event meaning unless explicitly superseded.

## 5. Local atomicity replaces transaction-publication bookkeeping

A coherent resource update executes: validate normalized input and scope; begin the existing writer transaction; recheck the live fence; admit required identities/content and the current values/evidence/conflict changes; write any genuinely observed collection progress/assessment; advance the local catalog revision when relevant; commit. No Publication row is inserted.

Remote requests, large byte decoding and optional logging occur outside long write transactions where possible. Parse failure does not admit a value. A genuine identified in-scope rejected resource can still justify partial evidence under the existing contract; transport-only errors cannot invent observations. Partial evidence written after rollback must preserve the original failure and actual response clock, and obey the job fence.

Value, presence and evidence are one atomic unit. SQLite's usual statement ABORT does not mean the whole transaction rolled back. Use the transaction context to explicitly roll back the unit on error, including a failed COMMIT; preserve the original error if cleanup fails. Nested units use correct savepoint discipline. No network call is held open to manufacture a giant all-collection transaction.

Committed prefix resources may remain useful when a later request fails. Resources committed earlier do not become invalid merely because a larger enumeration is partial. Multi-query readers use one database snapshot when coherence is required.

`Store.publish()` currently only increments `database_identity.publication_seq`. Rename this role to `advance_local_revision()` / `local_revision` with all consumers and tests, or document an equivalent mechanical name. Keep one local counter, not a row per commit. It serves stale-read/pagination/live fences and is not portable provider freshness. Catalog installation's building/validated state is likewise not a domain Publication.

## 6. Collection completeness without Publication

Separate four propositions: a resource is valid; admitted members are known; the requested scope is complete; the latest Coverage state is complete. None follows merely from COMMIT.

A domain collection assessment answers one exact scope: typed owner (repository/PR or Source), resource family, query/visibility context relevant to comparability, parent or head/base where applicable, observation boundary, admitted membership and known completeness/gaps. Its scope exists independently of the local transactions used to collect it. Source-wide assessment remains separate from repository Coverage and the current one-repository exchange format.

At the logical level, complete requires: scope consistency; valid required membership; justified enumeration termination; satisfied required child/target obligations; and no unresolved evidence that invalidates the asserted scope. Known empty with termination differs from no observed members with no termination. Counts/hashes alone do not establish all of these propositions.

This reconstruction does not choose Q05's permanent fragment-versus-final-set policy, a lifetime for old receipts, or a new universal seal. Preserve the established current-resource receipt semantics and the required historical flat/nested outcomes. Replace original-message references by the minimum normalized domain information needed to express those outcomes. The implementation must explain each remaining evidence record's consumer and use, rather than mechanically copying all HTTP pages. HTTP message hashes, cursor tokens and headers cannot become core validity prerequisites.

If historical receipt C says a current resource had digest H at time 100 and its value is now different at 200, do not require today's value to hash to H, fetch the old API response, or restore a full value history. H identifies an attested earlier value; it does not reconstruct it. Retain stable subject identity and only the proof necessary for the assessed scope. The representation and trust of historical attestations must not become broader than the existing admitted-evidence boundary.

Nested collection requirements bind a child to the actual parent/thread and capture/target context. A complete thread roster with one unfinished replies list is not a complete tree. A child's old completion cannot discharge a later distinct parent requirement merely because its provider thread ID matches. Use domain-specific relations or the existing closed evidence representation; no generic heterogeneous member registry is required.

Preserve `coverage_claims`' five columns and current maximum-observation-time candidate-set rule. Details remain advisory and a claim is not made structurally invalid merely because it lacks a Publication/certificate. Acquisition services and exchange qualification validate justified completeness separately. Later partial/unknown does not fall back to earlier complete; equal-time incompatible determinate states derive conflict. Do not add an implicit Source coverage type or evidence/trust column.

## 7. Git and code without generic output seals

Verified Git object content is a domain object. Commit-parent rows, tree entries and tag relations have that object as their intrinsic subject. Validate the canonical object's format, type, size and OID, then install its structural row set in one object-scoped transaction. A fully parsed parent sequence must not appear as half a commit. A transaction/guard is not a separate Git Publication entity.

Large imports commit independently valid object units, not one repository-sized transaction. A missing descendant makes the requested reachable Git scope incomplete, not all previously verified objects unreadable. Ref/root capture and acquisition identity retain their actual domain meaning; they are not generic owners of all decoded output. Any object/acquisition completeness bit must be backed by the actual domain predicate, not merely accepted as a renamed seal. Missing observed targets remain explicitly unavailable; never fabricate an object to satisfy a FK.

Code listings and assessments bind to explicit head/base/role/OID context, with normalized ordered entries and required Git references. Old head A's code cannot be displayed as current head B's complete code after PR replacement. Preserve only still-needed target anchors; no prior PR body or generic result record is required. Membership keys must be independent of API page IDs.

Git-only reanalysis and decoder/byte-offset evidence remain legitimate. Q04 does not select a new Q08 interpretation retention or ref-current rule. Preserve existing explicit domain snapshot/ref addressing and supported decoding semantics; remove parser-profile authority rather than replacing it with greatest-version-wins. Report a concrete irreducible decoder/candidate-policy conflict instead of inventing a universal order. API latest-state decisions do not automatically delete observed Git ref/snapshot history.

## 8. Inventory and operational boundaries

Source owns inventory assertions; the repository is the subject. Current known Source associations retain evidence sufficient to distinguish last confirmation, scope and incomplete latest scans. A scan of R1 ending early cannot delete previously known R2. Even terminal absence does not by itself authorize repository identity deletion or a new membership-removal policy. Identity deduplication uses established service/provider keys, never URL/name similarity.

Normalize restart necessities at acquisition time while the response exists in memory: known child IDs, observed target roles/OIDs, meaningful partialness and confirmed scopes. Operational cursor/checkpoint data refers to these domain targets, not the reverse. Missing operational state cannot invalidate committed domain facts. Never acknowledge a resume point ahead of its durable prefix; cross-store atomicity must not be assumed.

No permanent cache/checkpoint placement policy is selected. Preserve applicable live-retry outcomes with a documented mapping. Conditional reuse is allowed only for the exact still-corresponding scoped retained domain state and producer/field contract. A cache miss, state mismatch or changed parser cannot be treated as successful 304 evidence: make a genuine fresh request when authorized by the collection or report that reuse is unavailable. This is a correctness fallback, not an automatic adoption of a universal no-cache policy. Do not build a new original-body cache to satisfy this design.

Optional logging remains external, nonfatal and unnecessary for reads, exchange and restore. Failed/accepted-partial input cannot be smuggled into generic job JSON or staging as a replacement response archive. Keep only normalized accepted facts, justified gap information and genuinely operational continuation. No new automatic archive deletion or GC is authorized.

## 9. Exchange without portable commit groups

An export reads a coherent database snapshot and selects actual resources, required typed parents/identities, current-field evidence, applicable domain collection/target information and necessary domain bytes. Its transport envelope may have counts, checksums and an ID for transfer validation/idempotency. That envelope is not persisted as the creator of resources, a universal fact membership table or the authority that makes them usable.

Receiving a record checks schema/closed field vocabulary, natural identity, owner, required dependencies, byte identity and current-state/conflict rules. Parent-before-child processing or local deferred constraints can handle available dependencies. Missing remote dependencies go to normalized pending state; they are not satisfied by disabling FKs. Admission and promotion must behave consistently under reverse order, repetition, reopen and onward export.

Partial transfer does not automatically prevent use of valid independent resources. It does prevent a broad complete-scope assertion when required member/child closure is absent. A sender transaction's atomicity is not replayed or certified at the receiver. No incoming Publication or arbitrary `requires` hint can authorize foreign content.

Normalized pending/conflict entries keep only the required domain candidate and dependency/conflict reason. Import attempt IDs and operational receipts must be discardable without invalidating admitted facts, though duplicate delivery must remain safe. Do not retain whole API envelopes or every previously accepted current value.

Validate exact retained values when they exist. For a current-only family, old member evidence cannot require superseded body values. Preserve the existing admitted-attestation boundary; do not invent new sender trust or auto-promote an unprovable complete claim. A coherent sender can omit a provider member from both declaration and digest: internal validation cannot detect that alone. Cryptographic content integrity is not provider authenticity. A genuinely undecided stronger trust promise is an explicit residual issue, not solved by Publication.

Build closure from selected roots with indexed lookups and bounded traversal. Include actual same-repository unselected growth, not only unrelated repositories, in performance tests. Preserve #23-#25 findings and tests; the #25 23-record selective-export overhead is a measured issue, not a policy blocker.

## 10. Search, content and maintenance

Search current API resources according to their accepted current/conflict semantics. Rebuild from retained domain text, not originals or old parser results. Historic API edit-list commands must be retired or honestly re-scoped; do not silently return current values labeled history. Existing legitimate Git/domain-event queries remain separate.

Shared CAS protects real Git/text/domain content. Remove `decoded_api` registrations and original-byte authorization after all corresponding consumers are replaced. Do not delete a shared physical digest merely because one former reference was API-origin. Preserve exact-byte checks, real SHA-1/SHA-256 Git verification, quarantine/repair and CAS-41 copied-database accounting.

Backups contain the retained catalog/domain content and necessary evidence. Optional logs/caches are not required to restore usable facts. Physical catalog verification/installation remains atomic/no-overwrite and distinct from domain Publication. No retained user database migration, cleanup or destructive byte reclamation is performed by this design.

## 11. Old-to-new responsibility disposition

| Existing/proposed object | Target action |
|---|---|
| `repository_publications`, `source_publications`, generic members/seals in old candidate | Do not introduce; discard as target topology |
| `parsed_results`, `parsed_result_inputs`, `parsed_result_publications` | Remove generic interpretation owner/input/output-publication role; attach resource/Git/list facts to direct domain subjects |
| `parser_profiles`, capabilities, verification, invalidation, local trust (5 tables) | Remove ordinary-domain authority; use actual producer strings and supported decoder facts |
| `parser_profile_selection_*`, `fact_selection_*` (10 tables) | Remove selection DAGs; preserve direct domain conflict/availability outcomes without a substitute global chooser |
| `git_acquisition_publications` and generic sealed-output manifests | Remove Publication role; preserve required object/root/ref acquisition predicates with their actual subjects |
| `change_request_observations`, `document_observations`, `review_thread_observations` | Replace historical mutable-API value series with typed current state and necessary evidence |
| Inventory root/member historical observations | Implement current known Source roster/evidence, preserving Source ownership and partial-scan honesty |
| Code entries whose keys include fetch/result IDs | Re-key to actual comparison/list identity and entry position; keep exact target context |
| `fetch_occurrences`, `source_input_observations` | Remove API-original owner role and eventually stores; retain only independently needed normalized observation meaning elsewhere |
| API payload links, replay manifests and original-bearing JSON fields | Remove; closed modeled domain fields replace opaque replicas, not a renamed payload column |
| Collection scope/membership/terminal records | Keep/reexpress only specific enumeration responsibility; not a universal owner or prerequisite for individual resource reads |
| Generic `published`/eligible views tied to results/profiles | Replace with resource validity/conflicts or exact requested domain completeness predicates |
| `Store.publish`, `publication_seq` | Retain local revision/fencing role; mechanical rename with all consumers, no durable commit ledger |
| Jobs/cursors/validators | Operational only; no core-domain existence dependency or original replay |
| Exchange bookkeeping | Keep legitimate pending/conflict/idempotency functions, remove Publication/original authority |
| Git/text CAS, search indexes, catalog validation/restore | Keep independent content/projection/installation duties |

Inspect all FKs, composite keys, generated capability columns, JSON paths, views, triggers, implicit dispatch and package resources before removing a structure. This map specifies responsibility changes, not permission to drop shared semantics. No table count or old schema migration is promised.

## 12. Review/implementation gate and remaining boundaries

The architectural topology is reconstructed: no generic publication owner, current API values, direct domain relations, local atomic writes, separate completeness, and normalized exchange. This document is not a fully executed replacement DDL and does not silently accept Q05-Q12 options. Physical field grouping, evidence compaction, checkpoint placement, Git decoder policy and any stronger trust promise must be justified independently.

A mechanism may be changed without another owner choice when the agent can demonstrate that observable accepted behavior is preserved. A new retention, current-winner, negative-membership, completeness/trust or cache guarantee cannot be inferred from implementation convenience. Keep the questionnaire paused; report an irreducible issue precisely, implement all independent work, and never mark a failing/undefined path accepted.

Required counterexamples: rollback of value/evidence/revision together; statement failure does not leak earlier writes; sparse v1/v2 evidence; complete100/partial200/stale175/complete300; terminal empty versus missing terminal; partial/foreign nested child; stale head/base target; interrupted current inventory; partial Git object relations; reverse/partial/repeated exchange; coherent-sender omission limits; corrupted shared digest; logging/checkpoint loss; no hidden API value history; no generic seal under another name.

After implementation, separate subagents MUST review the submitted integrated tree: (A) architecture/DDL/no hidden Publication or history, (B) acquisition/current state/completeness, (C) Git/Exchange/CAS/performance, and (D) independent integrated acceptance. Implement fixes, add reproducing tests, rerun affected and full checks, and return to the original reviewer for verification. Changed reviewed source invalidates old approval; repeat until no unresolved mandatory issue remains or report a concrete blocker. Ordinary CI does not substitute for these reviews.

## Sources and evidence limits

Repository references are the exact PRs/SHAs above and `no-independent-publication-adr.md`, the active decision register, `Store.transaction/publish/revision`, current admission/receipts and Phase 2 workstream audits. SQLite primary references: https://www.sqlite.org/lang_transaction.html ; https://www.sqlite.org/isolation.html ; https://www.sqlite.org/foreignkeys.html . These establish local transaction/isolation/FK semantics, not remote truth or end-to-end application correctness.

This reconstruction includes static source/document analysis and responsibility/counterexample review. It does not claim a local full-repository test run, an implemented runtime, a new independently executed subagent review, a merge or a release. Implementation and independent verification are the next delegated work.
