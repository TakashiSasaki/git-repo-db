# Phase 2 owner decision register

**Policy status:** Q01-B, Q02-B, Q03-B, **NO_INDEPENDENT_PUBLICATION**, and **PF-P01–PF-P17 are accepted**. This register reconciles their scope; it does not make a new owner decision.

**Implementation status:** Publication removal and the later Three-Store implementation have reached `main`. The inspected baseline is `fb3b1fb4d5e1436c58677d2e867708502fbbc64b` (Core Schema 21, Operational Schema 1, Search Schema 1). This is not a statement of full release acceptance or a new runtime test result.

Read [No independent Publication](no-independent-publication-adr.md) for Q01–Q04 and [ADR 0002](../adr/0002-three-store-boundary-architecture.md) for the canonical PF-P01–PF-P17 decisions. The [documentation status audit](documentation-status-audit.md) records the evidence, remaining boundaries and reading rules for dated documents.

The old [pre-no-Publication questionnaire](decision-register-before-no-publication.md) and the [register before this status reconciliation](decision-register-before-status-reconciliation.md) are preserved verbatim as historical checkpoints. Their option letters, recommendations, blanket pause and blanket resolved labels are not current approvals. In particular, an old A recommendation is not approved where the owner selected B.

## Status vocabulary and scope

| Label | Meaning |
| --- | --- |
| Accepted | An explicit owner decision or an unsuperseded accepted contract settles the stated scope. Implementation and test status must still be checked separately. |
| Established implementation detail | An existing representation realizes an accepted guarantee; it is not an additional owner policy or a permanent retention promise. |
| Deferred extension | A broader feature or guarantee is not selected. Preserve the current behavior; the extension is not a mandatory backlog item. |
| Operational choice | A deployment or adapter may need settings for a concrete use. No universal Core policy is inferred. |
| Source clarification needed | A historical identifier is recorded, but its original specification has not been located in the inspected sources. Do not infer its meaning. |
| Obsolete premise | A Publication-dependent choice or past work sequence no longer applies. This does not approve one of its old alternatives. |

| ID | Current status | Settled scope and residual boundary |
| --- | --- | --- |
| P2-Q01 | B accepted | Latest accepted PR state plus necessary evidence; not a general PR-state edit history. Physical text lifetime is addressed separately by PF-P05. |
| P2-Q02 | B accepted | Latest title/body, distinct conversation resources and independent threads plus necessary evidence; no generic edit history. |
| P2-Q03 | B accepted; absence boundary settled by PF-P01 | Known-positive Source associations. No automatic absence-based exclusion; broader negative-membership semantics remain a deferred extension. |
| P2-Q04 | NO_INDEPENDENT_PUBLICATION accepted | The independent Publication abstraction is removed. Its old implementation prerequisite is obsolete. |
| P2-Q05 | Established completeness contract; PF-P02/PF-P03 accepted | Keep evidence needed by current consumers; general historical Collection-list queries and permanently retained incremental baselines are not requirements. Evidence reclamation remains deferred. |
| P2-Q06 | Established completeness and target contract | Required child collections and exact head/base/role evidence remain meaningful without Publication. This does not select a new universal manifest or lifetime policy. |
| P2-Q07 | Core/transport boundary settled by PF-P09 | Persistent HTTP caching is not a Core requirement. Adapter-specific cache/304 behavior and archive retention are operational choices where needed. |
| P2-Q08-S / Q08-G | Existing Git guarantees retained; extensions deferred | Real Git captures, verified bytes and explicit decoder provenance remain. No new interpretation-history or resolution-assertion policy is approved. |
| P2-Q09 | Attribute-admission rule settled by PF-P10 | Add explicitly modeled attributes for concrete uses. No blanket F01–F19 bundle or generic extension framework is approved. |
| P2-Q10 / Q10-T | Existing Exchange checks retained; stronger guarantees deferred | Actual typed closure and current conflicts are handled without Publication. Stronger sender trust and richer disputed-ownership transfer remain separate extensions. |
| P2-Q11 | Preservation/no-current-text-GC boundary settled | Keep genuine domain bytes and CAS-41; PF-P05 plans future manual text GC but authorizes no current deletion machinery. PF-P08/PF-P14 settle normal backup scope. |
| P2-Q12 | Settled by PF-P04/PF-P06/PF-P07/PF-P11–PF-P13 | Dedicated Operational SQLite; best-effort same-Job resume; no cross-store atomic commit requirement; explicit corruption recovery; no automatic Job TTL. |
| PF-P01–PF-P17 | Accepted; implementation integrated | [ADR 0002](../adr/0002-three-store-boundary-architecture.md) remains canonical. PF-P14–PF-P17 also settle Search separation, fallback, notification, explicit updates and creation/recovery. |

The blanket pause ended when the subsequent decisions were accepted. Conversely, **not every question embedded in old Q05–Q12 was resolved by those decisions**. Use the per-item scope below, not an umbrella "all resolved" statement.

## P2-Q01 — PR state observation lifecycle

**B accepted.** Retain latest accepted PR state and only necessary provenance, conflict, collection or domain-target evidence. Do not retain all old attributes indirectly through Publication outputs. Latest does not mean last-received.

PF-P05 settles the current action: no domain-text GC; unreferenced bytes may remain. Future manual deletion conditions are still deferred, not permission to restore a general edit-history service.

## P2-Q02 — PR conversation and independent thread history

**B accepted.** PR title/body, conversation comments and independent thread state use latest accepted values plus necessary evidence. Existing ordinary Issue and Review latest-state contracts are unchanged. Do not resurrect old comment bodies for a generic historical proof. Preserve actual distinct comments and identities; latest-state does not mean keeping only the latest comment in a conversation.

## P2-Q03 — Source inventory scan lifecycle and identity

**B accepted, supplemented by PF-P01.** Keep current known Source associations and necessary scope/member/completion/conflict evidence, not all historical roster attributes. A partial scan does not prove deletion. PF-P01 explicitly declines automatic absence-based exclusion, including treating a later roster as a deletion list.

Repository identity remains permanent and separate from visibility. A general representation of negative association, permission loss or provider deletion has not been selected. Source-wide completeness must not be inferred from repository-scoped Exchange.

## P2-Q04 — Atomic domain-publication identity

**NO_INDEPENDENT_PUBLICATION accepted.** This replaces the earlier deferral. Use the semantic identifier because earlier versions assigned different letters to the no-Publication and defer options.

There is no independent Publication ID, heterogeneous member ledger, seal or generic publish prerequisite. Renaming that abstraction does not satisfy the decision. Transactions, direct domain constraints, meaningful collection/Git evidence, local revisions and atomic filesystem installation retain distinct responsibilities.

The whole-design reassessment and subsequent implementation are historical completed stages, not new prerequisites to repeat. Integration does not prove freedom from defects or full release qualification; see [implementation status](../implementation-status.md).

## P2-Q05 — Normalized collection membership and terminal proof

**Completeness guarantees retained; historical-query and incremental-retention requirements settled by PF-P02/PF-P03.** Current domain-scoped membership, page, terminal and conflict evidence realizes those guarantees. Its existence is an implementation fact, not approval to keep all old rosters indefinitely.

General retrospective Collection-list queries are not required. An unavailable incremental baseline permits a genuine full acquisition; an older complete observation cannot replace newer partial/unknown/conflicting Coverage. Necessary evidence cannot be discarded solely because history queries are not required.

The lifetime or compaction of evidence no longer needed by current consumers remains a deferred policy. Neither the old fragment-versus-final-set alternatives nor a universal seal is adopted by implication.

## P2-Q06 — Nested GraphQL obligations and code targets

**Established guarantees and their domain-specific implementation remain.** A complete parent roster does not complete required child collections. Evidence for head A is not proof for head B. Page failure does not invalidate separately admitted valid resources.

The implementation's child requirements, code targets and completion predicates are not a new Publication mechanism. Preserve their consumers and consistency rules. A different evidence layout or retention guarantee would need its own justified change; this status update selects neither an obligation-table alternative nor an embedded universal manifest.

## P2-Q07 — HTTP 304 ownership and reuse

**Core responsibility settled by PF-P09.** HTTP validators, 304 handling, optional caching and its placement belong to the transport adapter, not a permanent Core-original store. Loss of a cache must not invalidate admitted facts or fabricate a new observation.

The decision neither bans adapter-private caching nor mandates one universal cache layout. Concrete adapter cache settings and optional external archive retention are operational choices when a use requires them; they are not an unanswered choice about Core DB ownership.

## P2-Q08 — Historical Git interpretation and PR/Git selection

**Q08-S/Q08-G: existing guarantees retained; additional policies deferred.** Verified Git content, real captures/ref/root context, Git-only reanalysis, supported explicit decoding and actual module/version provenance remain. API latest-state decisions do not delete Git history.

The old Publication/Profile-selection premise is obsolete. Persistent preferred interpretations, interpretation-history retention or resolution assertions are not approved merely because decoder facts exist. Do not rank incomparable results by parser version, receipt time or local IDs. Only a concrete need for a broader guarantee calls for a new owner decision.

## P2-Q09 — Retained domain-field contract

**PF-P10 accepted.** Add an attribute for a concrete use, including internal validation, Coverage and Exchange, with an explicit type and truthful provenance. Typed columns and closed JSON contracts remain available.

No broad F01–F19 bundle, arbitrary extension vocabulary, complete provider response or all-old-values archive is implicitly approved. Adding an actually needed field is future scoped modeling work, not a reason to reopen latest-state decisions.

## P2-Q10 — Receiver-verifiable normalized Exchange evidence

**Existing domain checks implemented; Q10-T's stronger trust promise remains deferred.** Preserve actual typed dependencies, ownership, exact content, current conflicts, scoped completeness and truthful partial transfer without sender Publication authority. Pending/conflicting domain evidence is not discardable merely because transport bookkeeping is disposable.

Sender checksums do not prove provider authenticity or expose a member consistently omitted from both a declaration and digest. New signatures, trust registration or stronger attestations have not been selected.

The current one-repository format explicitly refuses unrepresentable disputed ownership with `CURRENT_STATE_CROSS_REPOSITORY_CONFLICT`. A richer cross-repository conflict representation is a possible extension, not proof that ordinary Exchange is unimplemented. See the [boundary explanation](../current-state-boundaries.md) and [current implementation](../../src/repo_catalog/adapters/sqlite/current_resources.py).

## P2-Q11 — Physical content separation and legacy quarantine

**Preservation contract retained; current GC and backup scopes settled.** Exact domain text, verified Git bytes, shared-digest integrity, quarantine and CAS-41 remain. API-original removal does not authorize deletion of genuine domain bytes.

PF-P05 requires no domain-text GC now and records the owner's future manual-GC intention. Deletion eligibility, concurrency and the eventual manual procedure remain deferred. PF-P08/PF-P14 make normal backup Core-only with necessary manifest/integrity data; Operational and Search are excluded. CAS-41 is not reopened as unselected.

This does not expand future text GC to Git bytes, evidence or quarantine, and grants no retained-data cleanup permission.

## P2-Q12 — Durable checkpoint guarantee and placement

**Settled by PF-P04, PF-P06, PF-P07 and PF-P11–PF-P13.** Each Catalog has dedicated Operational SQLite. Same-Job resume is best-effort; a genuine safe reacquisition is sufficient. Core commits remain atomic, but no atomic Core/Operational COMMIT or generally durable fine-grained continuation is required.

Missing Operational DB is automatically created when needed. Corruption or foreign ownership is not silently overwritten; explicit administrator recovery includes deletion of a corrupt DB under a safe procedure. Existing Job records have no automatic TTL and may be explicitly cleaned up without invalidating domain facts.

The former same-DB/separate-journal/fresh-scan choice is no longer open. Specific progress rows or retry algorithms are implementation details subject to the settled guarantees, not a new exact-resume promise. Search has a deliberately different explicit-creation lifecycle under PF-P14–PF-P17.

## Recommended decision order and implementation impact

Do not restart the old four approval bundles or the Q05-onward questionnaire. Maintain the accepted implementation, report concrete defects against its guarantees, and ask only about a genuinely new policy needed for a specific use.

Use the [remaining-boundary register](documentation-status-audit.md#remaining-boundaries) to distinguish deferred extensions, operational choices and source clarification. These entries are not approvals or mandatory features. The original design ADRs retain their decision authority within scope; their pre-implementation work instructions and old pause statements describe their dated checkpoints.

The [status audit](documentation-status-audit.md#verification-boundary) explains what this documentation-only reconciliation checked and what it did not execute. No implementation, DDL, merge, release or retained-data operation is authorized by this register.
