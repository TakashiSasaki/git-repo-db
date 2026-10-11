# Phase 2 owner decision register

**Current status: four owner decisions fixed; further option selection paused.**
Read [No independent Publication](no-independent-publication-adr.md) first.
The former [questionnaire and recommendations](decision-register-before-no-publication.md)
are preserved verbatim as a superseded proposal checkpoint, not active choices.
The original A recommendation is not approved where the owner selected B.

| ID | Current status | Consequence |
| --- | --- | --- |
| P2-Q01 | B accepted | Latest accepted PR state plus necessary evidence; no general PR-state edit history. |
| P2-Q02 | B accepted | Latest PR title/body/conversation comments and independent thread state plus necessary evidence. |
| P2-Q03 | B accepted | Current known Source Inventory plus necessary scoped evidence; no historical roster-value service. |
| P2-Q04 | NO_INDEPENDENT_PUBLICATION accepted | No independent Publication entity/subsystem; reassess the complete design before implementing. |
| P2-Q05–Q12 | No option selected; interview paused | Reevaluate necessity, formulation and dependencies under the accepted choices. Do not request the next answer during this reassessment. |

The pause is not approval of a default, and not proof that every remaining
question is still necessary. It includes Q08-S/G and Q10-T. No new policy is
chosen merely because a prior prototype or a separate bug-fix PR passes tests.

## P2-Q01 — PR state observation lifecycle

**B accepted.** Retain latest accepted PR state and only necessary provenance,
conflict, collection or domain-target evidence. Do not retain all old attributes
indirectly through Publication outputs. Latest does not mean last-received.
No retention duration or physical GC is decided.

## P2-Q02 — PR conversation and independent thread history

**B accepted.** PR title/body, conversation comments and independent thread state
use latest accepted values plus necessary evidence. Existing ordinary Issue and
Review latest-state contracts are unchanged. Do not resurrect old comment bodies
for a generic historical proof. Preserve actual distinct comments and identities;
latest-state does not mean keeping only the latest comment in a conversation.

## P2-Q03 — Source inventory scan lifecycle and identity

**B accepted.** Keep current known Source roster and necessary scope/member/
completion/conflict evidence, not all historical roster attributes. A partial
scan does not prove that an unobserved repository was deleted. Source ownership
is not Repository ownership. No new Source assessment clock, delete-on-absence
rule or expansion of repository Exchange is selected.

## P2-Q04 — Atomic domain-publication identity

**NO_INDEPENDENT_PUBLICATION accepted.** This replaces the earlier deferral.
The semantic identifier is used because earlier versions assigned different
letters to the no-Publication and defer options.

The target has no independent Publication ID, member ledger, seal or generic
publish prerequisite. Family-specific or renamed wrappers whose only purpose is
the same abstraction are not an implementation of this decision. Transactions,
domain constraints and meaningful collection/Git/operational evidence retain
their distinct responsibilities. Local revision counters and atomic filesystem
installation are not independent domain Publications.

Whole-design reassessment precedes implementation. The earlier assumption that
an independent Publication must be selected before other modeling is withdrawn.

## P2-Q05 — Normalized collection membership and terminal proof

**Selection paused.** Reassess the minimum scope/member/terminal evidence needed
without Publication. Do not automatically retain every fragment or adopt a final-
set seal. Partial-versus-complete honesty and Coverage v2 remain established.

## P2-Q06 — Nested GraphQL obligations and code targets

**Selection paused.** Review required children and exact code targets in terms of
actual parents/acquisitions, not Publication-owned immutable outputs. No new
obligation-table or embedded-manifest option is approved.

## P2-Q07 — HTTP 304 ownership and reuse

**Selection paused.** Separate live confirmation and disposable HTTP state from
core validity. Neither disabling conditional GET nor selecting a cache layout is
implied by independent-Publication rejection.

## P2-Q08 — Historical Git interpretation and PR/Git selection

**Q08-S and Q08-G selection paused.** Preserve verified Git content and actual
parser provenance. Review domain validity/current selection without independent
Publication or parser-profile authority; do not select an interpretation history
or resolution-assertion system by implication.

## P2-Q09 — Retained domain-field contract

**Selection paused.** Review the old field inventory under Q01–Q03-B. No broad
F01–F19 bundle, minimal subset or extension framework is approved. Necessary
field evidence is not permission to retain a whole API response or all old values.

## P2-Q10 — Receiver-verifiable normalized Exchange evidence

**Q10 and Q10-T selection paused.** Review dependency/ownership/completeness checks
for actual retained domain data and evidence, without sender Publication authority.
Do not infer old values from new values or approve a new sender-trust policy.

## P2-Q11 — Physical content separation and legacy quarantine

**Selection paused.** Required domain text/Git bytes and CAS-41 remain. Shared
physical hashes and API-only consumers require precise analysis; this is not GC
or retained-data deletion authorization.

## P2-Q12 — Durable checkpoint guarantee and placement

**Selection paused.** Review local atomic changes, crash/retry boundaries and
operational fencing independently of permanent domain ownership. Same-DB,
separate-journal and fresh-scan options remain unselected.

## Recommended decision order and implementation impact

The former sequence of four approval bundles is no longer the active plan.
First reassess all areas for consistency with Q01-B/Q02-B/Q03-B and no independent
Publication; then review the integrated design; then implement its justified
changes. Do not resume the questionnaire or turn a remaining recommendation into
an owner decision while this work is in progress.

The [decision ADR](no-independent-publication-adr.md) contains the impact map,
concrete counterexamples and completion criteria. It records accepted direction,
not completed replacement DDL or successful runtime verification.
