---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0023-configurable-finite-notes-resource-budgets.md
  - 0022-receiver-verified-notes-role-admission.md
  - 0019-monotonic-notes-capture-fact-admission.md
  - 0021-direct-semantic-notes-claim-group-keys.md
---

# ADR 0024: Account for actual notes-processing work, including reprocessed deliveries

**Current post-corruption override:** [ADR 0026 / GCTX-M10](0026-stop-salvage-restore-merge-after-corruption.md) requires stopping ordinary catalog operation, preserving the suspect source read-only, serializing salvage candidates, restoring a verified backup into a fresh destination and merging only revalidated admissible data. Prior post-fault metadata service, same-DB failover, known-corrupt normal backup/restore and references to M10 as pending are historical in that scope. Ordinary sound-catalog rules and unrelated open work remain. No implementation or merge is authorized.

**Subsequent accepted refinement:** [ADR 0025 / B02-R04 A](0025-cumulative-request-budgets-and-scoped-blockers.md) fixes cumulative actual work for one explicit request across continuation/resume/retry. Resource settings, counters/defaults and progress mechanics are engineering work, not further owner blockers. Section 8 preserves the historical comparison with A now selected.

- **Decision ID:** B02-R03; **owner selected Option A**, accepted 2026-10-15.
- **Direct base:** [PR #64 / ADR 0023](https://github.com/TakashiSasaki/git-repo-db/pull/64), verified HEAD `6975fbda577323291b922ddc6a89369dcdab0bbb`, branch `codex/adr-0023-configurable-notes-resource-budgets`. Direct documentation-only successor; no implementation or merge.
- **Inherited:** ADR 0014–0023, KEY-P01, GCTX-M01–M09 and strictly append-only Git Core. Proposed [PR #52 / ADR 0011 governance](https://github.com/TakashiSasaki/git-repo-db/pull/52) remains unadopted.
- **Implemented baseline:** Three-Store Catalog3 Core Schema 21 / Operational 1 / Search 1, unchanged. Accepted design, implemented behavior, executed verification and merge permission remain separate.

## 1. Binding decision: actual work, not logical multiplicity or new rows

Aggregate resource accounting MUST reflect **work actually performed**: pertinent input actually read/decoded/checked, actual relation/metadata processing, and actual proof exploration within the explicit acquisition-request scope fixed by ADR 0025. Preserve ADR 0023's independent finite configurable individual raw-note, aggregate-work and proof-traversal limits.

- A newly read or rechecked repeated body costs processing work **again**, even when its accepted OID, semantic assertion or SQL insertion is an exact idempotent replay. Domain-fact deduplication does not erase already performed input/verification work.
- Reusing already checked data without another body read/check must not invent another full-body processing charge merely because many mappings reference the same blob. The actual reference handling, lookups and proof exploration still have their own real work; this is not free processing for an arbitrary number of mappings.
- Shared proof dependencies follow the same distinction: reuse can avoid work, while a real revisit/read/check consumes work again. A common tree OID, claimed digest or sender-local row key alone does not establish that reuse was valid.
- Work actually spent on a rejected, interrupted or unsuccessful input/proof attempt is still spent. Failure, nonadmission, SQL rollback or duplicate detection cannot retroactively turn that performed work into zero. ADR 0025 / B02-R04 A makes one explicit request cumulative across continuation/resume/retry; remaining mechanics are engineering work, not an implicit permanent lifetime budget.
- Do not charge a hypothetical full body solely from an unverified sender size claim or a metadata-only reference. Such claims retain their attribution and may inform conservative acquisition planning, but actual-work reporting must not call unperformed work performed.

The unselected Option B, a full logical body/proof allowance for every mapping/delivery regardless of actual reuse, is not the adopted accounting basis. Internal planning reservations may be distinct from actual charges, but cannot be mislabeled as performed work or silently replace this decision.

## 2. Measurement precision deliberately left open

This ADR chooses **the basis of accounting**, not a concrete counter implementation. Wire bytes, decoded/raw bytes, verifier passes, object reads, relation operations, proof steps, wall time and storage growth are different dimensions. Do not add unlike units into an unexplained single number or present newly retained CAS bytes as all processing cost.

The individual-note size limit continues to concern the exact raw note body under ADR 0023. Precise aggregate/proof counter units, which processing stages are measured separately, charging of partial/failed reads, numeric defaults, configuration encoding, concurrency reservations and durable progress mechanics are agent-owned follow-up engineering choices under ADR 0025, not architectural owner blockers. The choice of actual work must hold under those contracts; it does not authorize selecting optimistic units that leave the required work envelope unbounded.

The examples below illustrate an explicitly stated **body-read byte component**, not a complete CPU/I/O benchmark or adopted counter/default. Per-operation finite limits are not a new global catalog-size quota, retention deletion policy or Core GC mechanism.

## 3. Safe reuse is separate from identity and physical health

Reuse must be justified by the actual evidence and coherent scope/fences of the operation; a shared OID or a cache label is insufficient. This ADR does not choose that lifetime/fencing protocol, allow unverified cross-operation trust, or import a sender's verification as receiver-local authority.

- B02-R01 still requires the receiver's relevant checked captured-root/tree-to-target-to-note association and exact body identity before new durable body admission. Lower accounting charges cannot authorize an unproven body.
- GCTX-M04/M06 allow the receiver's own historical checked intrinsic facts to support their precise metadata interpretation without a mandatory full rehash for ordinary metadata queries. Reusing such facts must retain their scope and provenance rather than promote unrelated reports.
- GCTX-M07 still checks actual selected/emitted bytes when claiming current byte-verified output. Historical success, a prior processing charge or reuse cannot substitute for that check. Any relevant check actually performed is real work under its applicable scope.
- M08/M09's physical-copy distinctions, durable diagnoses and evidence-derived candidates remain; nominal OID equality cannot erase work done on a second physical instance or automatically prove it healthy.

No required Context registration, hidden live fetch, all-attempt Core verification ledger or generic Publication is introduced to justify reuse. Metadata-only operation remains useful without bytes, Context or processing jobs.

## 4. Domain replay and work accounting have different owners

Keep original Capture UUIDv4 pair, immutable source/ref/root and ADR 0021 semantic claim/group composites. Actual repeated work is **not** a new source observation, claim occurrence, group member or physical instance merely because another attempt happened.

Operational owns scoped work counters/progress/retries under ADR 0025's cumulative request rule; the implementing agent owns their concrete mechanics. Git Core retains actual eligible immutable domain/admission/physical facts; no mutable Core resource counter, per-replay success ledger, receiver-only accounting surrogate or lifetime Capture budget owner is selected. Losing/rebuilding Operational cannot invalidate or delete admitted Core evidence. The implementing agent must handle lost accounting truthfully under ADR 0025, never fabricate zero prior cost for the same resumed request; this is not another owner-option question.

At a limit, ADR 0023 still preserves independently admissible metadata and complete atomic units, withholds unfinished/oversize/unproven bodies or units, and reports the actual stop. No truncation, false complete/empty inventory, in-place group extension or durable unproven-body staging is permitted. Ref rewrites, budget changes and replay do not authorize Core deletion, physical fault reclassification or CAS-41 changes.

## 5. Worked counterexamples

| Scenario | Required accounting and domain result |
| --- | --- |
| One 2 MiB N1 body is read/checked once and safely reused for 100 actual mappings | Body-read byte component is 2 MiB, not 200 MiB solely because of reference count. Actual mapping/proof processing still counts separately; all mapping evidence retains its true scope |
| The same 2 MiB body is read in 100 body-bearing deliveries | Body-read component is 200 MiB; idempotent fact/CAS insertion does not make those reads free |
| A known N1 OID appears in metadata only, without reading N1 bytes | No invented full-body read charge; actual metadata/lookup/proof work still counts. No body availability or verification inferred |
| A proof tree is safely reused, then a later step actually rereads it | Only actually avoided work is avoided; the later real read/check counts again under the eventual metric |
| Input is read/checked and then rejected, or admission rolls back | Count work already performed within the applicable scope, without accepting the failed body or inventing a new Core success event |
| A retained instance is damaged after earlier verification | Old work/reuse claims do not prove health. Apply M07–M09 diagnosis/selection; no zero-cost or healthy-now claim from OID equality |
| Work stops and resumes or retries | ADR 0025 / B02-R04 A keeps one explicit request cumulative; concrete counters/recovery/fences are engineering work |

## 6. Consistency with inherited decisions

| Decision | Preserved/refined constraint |
| --- | --- |
| ADR 0014/0015 | No ordinary file-body archive or hidden staging; observable notes ref discovery is not role proof or complete inventory |
| ADR 0016/0018 | Genuine immutable observations remain separate; retry retains actual two-UUIDv4 Capture identity |
| ADR 0017 / KEY-P01 | Direct domain composite PK/FK, no extra authoritative accounting/claim surrogate |
| ADR 0019–0021 | Compatible immutable additions, exact provenance-bound replay, competing alternatives and whole-group atomic identity stay distinct from processing attempts |
| ADR 0022 / B02-R01 A | Receiver-local structural role proof plus exact body checks remain mandatory; reuse is not sender-verification laundering |
| ADR 0023 / B02-R02 A | Finite configurable raw-note/aggregate/proof limits, honest stops and explicit finite-increase retry remain; no numbers selected |
| GCTX-M01/M02 | Metadata-only zero-body/no-Context operation; one nominal typed full OID does not imply possession/verification or performed work |
| GCTX-M03/M04 | Immutable coherent groups and truthful field-specific canonical/report/conflict reads; no implicit complete union or arbitrary winner |
| GCTX-M05/M06 | Core owns bounded immutable admission/physical evidence; Operational work; no per-attempt permanent success ledger |
| GCTX-M07–M09 | Actual-output checks, immutable copies/diagnoses and evidence-derived candidates preserved; budget accounting is not physical health |
| Other fixed rules | Strict Core INSERT-only/no UPDATE/DELETE/REPLACE/GC, permanent repository UUIDv4, known-positive Source, five-column/latest-observation Coverage, Unix epoch microseconds, NO_INDEPENDENT_PUBLICATION, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, durable Context, paired full backup and ADR 0001 |

No prior accepted decision requires reversal. B02-R03 A and B02-R04 A are accepted by ADR 0024/0025. Counter/default/resume details are engineering work, not owner blockers. Remaining scoped work includes notes proof grammar, B03 completeness, origin trust, GCTX-M10 quarantine/count, exact DDL/wire/fences/backup pairing and Context GC-03/04.

## 7. Future adversarial cases (NOT executed product tests)

1. One body reused across many mappings avoids fictitious repeated body charges, while real metadata/proof operations remain bounded.
2. Repeated body-bearing input consumes actual processing work despite exact SQL/domain replay; reverse/onward Exchange preserves provenance.
3. Metadata-only references and sender-declared sizes do not fabricate body reads, actual size or byte-verification results.
4. Failed/truncated/rolled-back attempts do not refund performed work or publish an accepted partial body/group.
5. Shared proof reuse and real re-traversal remain distinguishable under the eventual metric/fence protocol.
6. Prior verification/accounting cannot waive current byte-output checks, physical-copy identity or durable damage diagnosis.
7. No per-attempt Capture/claim UUID, mutable Core counter, lifetime Capture quota or generic Publication is introduced.
8. Numeric defaults and counter units are not accidentally inferred from the 2 MiB/100-reference example.
9. Work stopping preserves eligible metadata/atomic units, exact body meaning and honest coverage; no hidden durable pending body.
10. Operational loss/rebuild preserves Core validity; subsequent resumed/fresh accounting must follow an explicit protocol rather than fabricated zero cost.

## 8. Historical B02-R04 comparison; A accepted by ADR 0025, budget details are not owner blockers

The prior question asked what bounded work one aggregate budget covers and when its actual-work counter may reset. The owner subsequently selected **A**, fixed by ADR 0025, and corrected the classification of remaining resource details as architectural blockers. This is not Capture identity or a new domain-validity owner; B remains historical and unselected.

Illustrative numbers only: a caller requests one acquisition with a 128 MiB aggregate allowance, spends 80 MiB before interruption, and a retry would process 70 MiB more. Does it have 48 MiB remaining or a fresh allowance? These are not adopted defaults or a precise byte metric.

- **A — One explicit acquisition request, cumulative across its continuations/resumes/retries (recommended):** keep spent actual work within that declared work scope; an explicit higher finite allowance may permit more work. A genuinely separate caller-requested acquisition can have its own finite budget; Capture identities remain independent. **Pros:** automatic retry cannot evade a request's limit; reporting explains actual total work. **Cons:** requires reliable scoped Operational progress, restart/loss rules and fences; exact persistence/concurrency mechanics remain follow-up work.
- **B — Each attempt has a fresh budget, with a separate finite outer retry/work bound:** make the reset explicit and independently bound the whole request's retry count/time/work. **Pros:** attempts are easier to isolate and restart. **Cons:** 80+70 MiB may exceed the nominal single-attempt allowance for the request as a whole; another outer bound/configuration is needed to prevent unbounded repeated attempts, with more coordination and reporting.

Both options preserve actual-work charging, finite configurable limits, semantic replay, atomic groups and Core/Operational separation. Accepted A does not fix concrete lost-progress recovery, units/defaults, settings storage or worker reservations; these are agent-owned engineering choices under ADR 0025. Proof grammar/B03 remain scoped work under accepted semantics; GCTX-M10 is still an unselected disposition/count/backup policy.

## 9. Authorization and verification boundary

The owner selected **B02-R03 A** after B02-R01 A and B02-R02 A. ADR 0023's alternative logical-per-reference accounting is historical and unselected. This is a documentation-only design PR; B02-R04 A is subsequently accepted by ADR 0025 together with the owner's correction of the blocker classification. The owner additionally requested proactive skill capture for verified repeated workflows, so this PR also updates the existing `lessons-to-skills` Markdown instructions and adds a linked procedural reference; this does not adopt a product decision or authorize implementation.

No implementation, application source/SQL/DDL/schema labels, executable product tests, workflows/dependencies, live-source acquisition, real-catalog mutation/migration, deployment, release, merge or auto-merge is authorized. Static document/skill checks and selected hosted development/documentation CI are distinct from product runtime/release acceptance. The future cases above are not executed tests. No independent review is implied; the existing skill update captures a verified procedure, not this individual design choice as reusable policy.
