---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0023-configurable-finite-notes-resource-budgets.md
  - 0024-actual-notes-resource-work-accounting.md
---

# ADR 0025: Cumulative acquisition-request budgets and scoped architectural blockers

**Current post-corruption override:** [ADR 0026 / GCTX-M10](0026-stop-salvage-restore-merge-after-corruption.md) requires stopping ordinary catalog operation, preserving the suspect source read-only, serializing salvage candidates, restoring a verified backup into a fresh destination and merging only revalidated admissible data. Prior post-fault metadata service, same-DB failover, known-corrupt normal backup/restore and references to M10 as pending are historical in that scope. Ordinary sound-catalog rules and unrelated open work remain. No implementation or merge is authorized.

- **Decision ID:** B02-R04; **owner selected Option A**, accepted 2026-10-15, with the explicit correction that resource limits and their implementation details are not architectural owner blockers.
- **Direct base:** [PR #65 / ADR 0024](https://github.com/TakashiSasaki/git-repo-db/pull/65), verified HEAD `45f7da24924caa8d4da7a00107e32dc03c6bb416`, branch `codex/adr-0024-actual-notes-resource-accounting`. Direct documentation-only successor; no implementation or merge.
- **Inherited:** ADR 0014–0024, KEY-P01 and GCTX-M01–M09. Proposed [PR #52 / ADR 0011 governance](https://github.com/TakashiSasaki/git-repo-db/pull/52) remains unadopted.
- **Implemented baseline:** Three-Store Catalog3 Core Schema 21 / Operational 1 / Search 1, unchanged. These are accepted target rules and an owner-directed correction to task classification, not executed product behavior.

## 1. Accepted A: one explicit acquisition request accumulates actual work

An aggregate work budget belongs to **one explicit acquisition request**, including its continuations, interruption/resume and retries. Work already performed within that request continues to count under ADR 0024, even when processing failed, admission rolled back or exact domain replay deduplicates. An automatic retry cannot silently replenish the allowance.

The caller may explicitly increase the finite allowance. A genuinely separate, explicitly requested acquisition has its own finite envelope. This is neither a permanent lifetime quota on a Capture nor a global catalog-size limit. It does not require an authoritative generated request ID in Git Core or a new domain Capture for each attempt.

For illustration only, a request with a 128 MiB allowance that spent 80 MiB has 48 MiB left after interruption. Processing another 70 MiB cannot complete under the unchanged allowance; an explicit sufficient finite increase can permit it. These numbers describe a body-read component, not adopted defaults or a complete work metric. Safe reuse and actual repeated processing retain ADR 0024's distinct charges.

Operational owns settings, counters and progress. Its loss/rebuild cannot invalidate or delete admitted Core facts. The implementation must handle unavailable accounting honestly rather than claiming known zero prior cost for the same resumed request; its recovery, conservative reservation or inability-to-resume mechanics are engineering work under this rule. No durable Core success ledger, mutable Core counter, per-attempt Capture/claim UUID, sender-verification shortcut or new Publication is introduced.

## 2. Owner correction: stop treating resource detail as an architectural gate

Earlier current summaries incorrectly promoted a sequence of resource questions into mandatory owner blockers. **Remove that classification.** B02-R01's receiver-local structural/body admission rule and accepted B02-R02–R04 resource policies remain binding; their acceptance does not mean every implementation parameter needs another owner ADR.

| Item | Current responsibility and dependency |
| --- | --- |
| Finite configurable raw-note, aggregate-work and proof limits | Accepted B02-R02 policy; preserve honest stops, exact bodies and atomic units |
| Actual-work charging and safe-reuse distinction | Accepted B02-R03 basis; no free reprocessing from SQL deduplication |
| One request's cumulative continuation/resume/retry allowance | Accepted B02-R04 A; no silent automatic reset |
| Numeric defaults, precise counters/units, configuration representation and validation | Agent-owned tunable engineering choices within the accepted policies; document and verify in the affected authorized implementation |
| Partial-read charging, progress persistence/recovery, concurrency reservations and resume mechanics | Agent-owned engineering work that must enforce finite cumulative accounting truthfully; not successive owner-option questions merely because details remain unfinished |
| Supported notes proof/parser representation and concrete completeness evidence | Remaining scoped design/engineering work under B02-R01 and GCTX-M03/M04; do not reopen accepted partial/complete/known-empty/unknown or canonical/report distinctions without a concrete conflict |
| Post-corruption operation and recovery, formerly GCTX-M10 disposition/count | Subsequently fixed by ADR 0026: stop, preserve read-only, salvage candidates, fresh verified restore, validated merge. No further owner selection among the former A/B/C options |

Open work is not automatically an architectural owner blocker. For a proposed blocker in this design stack, identify the unresolved domain meaning, trust/admission authority or serialized backup meaning, show the concrete conflicting outcomes, and name the affected dependent stage. Routine values, counters, algorithms and synchronization mechanisms can be designed and tested by the implementing agent within accepted policy. Escalate a concrete policy conflict if one is discovered; do not manufacture a new owner questionnaire from every unfinished parameter.

This correction does not claim notes/wire/DDL, cross-store consistency or Context GC-03/04 work is finished, nor automatically authorize any of it. ADR 0027 subsequently fixes unauthenticated external-origin admission without PKI/signatures and estimates provisionally 0 known owner blockers in the current migration scope; deferred features and engineering work are distinct from those blockers. It scopes actual dependencies and preserves accepted requirements. It does not adopt the sibling governance proposal or introduce a new repository-wide approval process.

## 3. Consistency with accepted decisions

| Decision | Preserved constraint |
| --- | --- |
| ADR 0014/0015 | No ordinary file-body archive or hidden pending/cache storage; observable notes-ref discovery is not role proof or complete enumeration |
| ADR 0016/0018 | Actual two-UUIDv4 Capture identity denotes the genuine observation; request/retry boundaries do not mint observations |
| ADR 0017 / KEY-P01 | Direct domain composite PK/FK; no authoritative storage-only request, claim or group surrogate |
| ADR 0019–0021 | Compatible immutable additions, provenance-bound exact replay, attributed alternatives and atomic whole groups are independent of work attempts |
| ADR 0022 / B02-R01 | Receiver-local relevant notes structure and exact body checks precede new durable body retention; no source/sender flag replaces them |
| ADR 0023/0024 | Finite configurable limits, actual-work accounting, safe reuse and honest stops remain; cumulative request scope refines only the previously open carry/reset boundary |
| GCTX-M01/M02 | Metadata-only, Context-free, zero-body operation remains; nominal OID identity does not imply bytes, type, verification or performed work |
| GCTX-M03/M04 | Scoped coherent groups and truthful canonical/report/conflict/partial/complete/known-empty/unknown reads remain; no silent union or fabricated closure |
| GCTX-M05/M06 | Immutable admission/essential physical evidence belongs in Core; progress in reconstructible Operational; no per-attempt Core ledger |
| GCTX-M07–M09 | Check actual selected/emitted bytes; retain damaged copies and diagnoses; derive eligible candidates from evidence. Budget stops are not physical corruption or CAS-41 reclassification |
| Other fixed rules | Core INSERT-only/no UPDATE/DELETE/REPLACE/GC; permanent repository UUIDv4; known-positive Source; five-column/latest-observation Coverage; Unix epoch microseconds; NO_INDEPENDENT_PUBLICATION; Q01-B/Q02-B/Q03-B; unaffected PF-P01–PF-P17; durable independent Context; paired full backup; ADR 0001 |

No accepted product policy is reversed. The superseded material is the **classification** of unfinished budget details as owner blockers and any current statement that B02-R04 remains unselected. No numeric defaults, exact DDL/wire or GCTX-M10 disposition option is selected here.

## 4. Historical GCTX-M10 active-quarantine question, superseded by ADR 0026

**Subsequent owner decision:** ADR 0026 replaces the continuing-operation premise of this comparison. It selects the recovery workflow, not A/B/C retirement, and retains the budget-detail correction above. The comparison below is historical.

[ADR 0013 sections 4 and 7](0013-deterministic-cas-instance-eligibility.md#4-quarantine-and-cas-41-what-m09-fixes-and-leaves-for-m10) already leave this decision explicitly open. A damaged physical copy I1 stays retained with its immutable diagnosis; independently validated I2 can supply the same logical payload. I2 never repairs I1, makes it eligible or automatically lowers its count. What remains undecided is whether a separate terminal disposition can remove I1 from **active outstanding quarantine**. This changes the counted physical-instance set serialized and checked by backup/restore, so that affected manifest contract cannot be finalized by choosing a tunable number.

| Option | I1/I2 example | Benefits | Costs |
| --- | --- | --- | --- |
| A — Every known-damaged retained copy stays actively quarantined forever | I1 contributes 1 even after usable I2 arrives, forever | Simple, conservative predicate | Active count accumulates permanently and cannot distinguish outstanding work from terminal exclusion |
| **B — Explicit immutable terminal disposition (recommended, not selected)** | I1 contributes 1 until a narrow audited disposition permanently excludes it from service; then 0 active, with bytes and incident still retained | Distinguishes active obligations from permanent history; explicit and auditable | Must define authorized disposition evidence and its coherent CAS-41/manifest interpretation |
| C — Derive terminal disposition automatically from independently qualifying evidence | I1 stops counting only when a fixed terminal predicate holds, never merely because I2 exists | Less manual disposition work | More complex predicate; less obvious reasons for count changes |

All options retain damaged bytes and fault history, forbid Core GC/in-place repair, and never make damaged I1 eligible. CAS-41 still counts distinct physical instances, not diagnosis events or unavailable logical payloads. Verify the archived count against the copied/verified database before adding restore-time diagnoses; an unknown/unreliable count fails closed. Only the affected disposition/count/manifest work waits on M10; independent design work need not stop. **No A/B/C selection is implied by this ADR.**

## 5. Future verification and authorization

Future authorized implementation must verify cumulative actual work across interruption/retry, no silent reset or fabricated zero after progress loss, finite configurable enforcement, safe reuse versus real reprocessing, exact replay/atomic groups and preservation of already admitted facts/bytes. Counter/default choices should have risk-relevant checks in that implementation, not a new owner-decision chain. These are future requirements, not executed product tests.

The present task changes documentation and the existing reusable ADR-workflow skill reference only. Its checks cover final Markdown scope, links/frontmatter/status consistency and the skill instructions, plus selected hosted development/documentation CI for the published tree. They do not prove product runtime behavior, full release acceptance or an independent review.

No application/SQL/DDL/schema-label/workflow/dependency change, executable product test, source acquisition, real catalog mutation/migration, implementation, release, deployment, merge or auto-merge is authorized.
