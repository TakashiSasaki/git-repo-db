# Documentation status audit — scoped decision reconciliation

**Historical audit and current successor:** This audit examined the implemented Three-Store format before the owner's 2026-10-14 acceptance of [historical ADR 0003](https://github.com/TakashiSasaki/git-repo-db/blob/bb878eda47cf17268dd821c74343bac64d769ea7/docs/adr/0003-append-only-git-core-and-context-store.md). The original four-store target and its then-valid supersession of prior physical placement remain evidence of that checkpoint. **As of 2026-10-19**, [accepted ADR 0029](../adr/0029-independent-access-store.md) replaces ADR 0003 and defines Git Core (strictly INSERT-only), durable Context, independent Access, Operational and Search as five distinct responsibilities; accepting that design alone does not switch the Three-Store runtime. Future manual Provider-text GC remains Context-only, not Git Core.

- **Audit date:** 2026-10-14.
- **Inspected baseline:** `fb3b1fb4d5e1436c58677d2e867708502fbbc64b`.
- **Baseline tree:** `ac15a5c264daa55c15f6a3a5c22b7705e7046da8`.
- **Scope:** Documentation status and source traceability only. No new owner decision, production change, retention permission, merge or deployment.
- **Current decision index:** [Phase 2 register](decision-register.md).

## Finding and correction

The baseline register simultaneously described all Q05–Q12 as resolved and kept
"Selection paused" in their individual sections. The scoped Phase 2 instructions
said no cache/checkpoint policy was selected even though ADR 0002 accepts
PF-P01–PF-P17. The Phase 2 overview still described whole-design reassessment as
future work, and the implementation-status page described Schema 20 as active.
These are conflicting status labels, not evidence that accepted design must be
reopened or that every old alternative was approved.

The correction separates three axes:

| Axis | Evidence required | What it does not imply |
| --- | --- | --- |
| Decision status | Explicit owner decision, accepted ADR, or scoped supersession | That every related feature, lifetime or optional guarantee is selected |
| Implementation/integration status | Current code/DDL and actual merged history | Independent verification, arbitrary-input correctness or release qualification |
| Verification status | Actual execution/review evidence tied to a revision and scope | That old tests were rerun, or that one passing subset proves all current behavior |

"Accepted", "established implementation detail", "deferred extension",
"operational choice", "source clarification needed" and "obsolete premise" in
the register are documentary classifications. They are not new design decision
IDs, new runtime states or approvals of optional work.

## Authority and document reading map

| Source | Current role | How to interpret dated status text |
| --- | --- | --- |
| [No independent Publication ADR](no-independent-publication-adr.md) | Binding Q01–Q04 decisions and architectural exclusions | Its 2026-10-10 integration baseline, blanket questionnaire pause and future work sequence describe that checkpoint, not a current implementation backlog. |
| [ADR 0002](../adr/0002-three-store-boundary-architecture.md) | Canonical PF-P01–PF-P17 owner decisions | "Accepted target design" is policy status, not a claim that implementation is still absent. Apply each row's scope; do not infer new trust, lifetime or interpretation policy. |
| [Publication-free design](publication-free-design.md) | Earlier design reconstruction and retained domain guarantees | Preserve unsuperseded guarantees. Later ADR 0002 supersedes old cache/checkpoint/physical-placement indecision within its explicit scope. |
| [Phase 2 register](decision-register.md), [overview](README.md) and [scoped instructions](AGENTS.md) | Current entry points | Read their scoped mappings instead of old pause/resolved umbrella labels. |
| [Packaged schema composition](../../src/repo_catalog/adapters/sqlite/schema.py) | Implemented format source | At the inspected baseline: Core 21, Operational 1, Search 1. A version alone is not a behavior or acceptance certificate. |
| [PR #38](https://github.com/TakashiSasaki/git-repo-db/pull/38) and [PR #39](https://github.com/TakashiSasaki/git-repo-db/pull/39) | Design and implementation integration history | PR #39 merged as `a93d438644f4578452dd53568197bc978072cc30`. Later `main` changes remain intact; this audit does not reset to that merge. |
| [Schema 20 implementation handoff](publication-free-implementation.md) and [original implementation prompt](publication-free-implementation-prompt.md) | Reconstruction responsibility/test-disposition history | A dated implementation/verification gap is not automatically a current gap. Original review/full-test instructions do not supersede the later ordinary-development policy. |
| [ADR 0001](../adr/0001-validation-lifecycle-architecture.md), root [AGENTS.md](../../AGENTS.md), [testing guide](../testing.md) | Current development/release validation distinction | Apply current scope. A documentation correction does not request full release qualification or four reviewers. |
| [Architecture](../architecture.md), [data model](../data-model.md), [operations](../operations.md) | Mixed-era explanation and retained contracts | Do not treat old Schema 20 headings as current physical placement, or invalidate every still-applicable contract merely because a heading is old. Use the current schema/ADR for physical layout. |
| [Pre-no-Publication questionnaire](decision-register-before-no-publication.md), [proposal](proposal-before-no-publication.md), workstreams and dated validation artifacts | Historical evidence | Preserve their exact bytes, option wording, failures, counts and hashes. They are not new owner decisions or current execution receipts. |

This is a bounded status reconciliation, not a rewrite of every historical
document or the public website. The dated design and validation sources above
are deliberately retained, with their applicability made explicit in the current
entry points. A genuinely contradictory *domain guarantee* still requires a
concrete report; a newer date alone never authorizes changing it.

## Q05–Q12 supersession map

| Old question | Later authority or established boundary | What remains outside that decision |
| --- | --- | --- |
| Q05 | Q01–Q04 completeness/ownership; PF-P02 removes the general historical-list requirement; PF-P03 permits full acquisition without a baseline | Lifetime/compaction of evidence no longer needed by current consumers; no indiscriminate deletion or new universal seal |
| Q06 | Required children and exact code targets in Publication-free design, retained by ADR 0002's Core boundary | No new permanent fragment/manifest layout or retention promise |
| Q07 | PF-P09 assigns HTTP cache/304 semantics to the transport adapter | Adapter-specific settings and optional external archive retention |
| Q08-S/Q08-G | Actual Git bytes/captures, explicit provenance and no Profile/Publication authority remain | Extra persistent interpretation selection/history/retention or new ref-current policy |
| Q09 | PF-P10 permits explicitly modeled fields for concrete uses | No blanket old F01–F19 choice or speculative extension namespace |
| Q10/Q10-T | Existing typed Exchange, current conflict and completeness checks remain; PF-P06 keeps semantic evidence out of disposable operations | Stronger trust/authenticity guarantees and richer cross-repository disputed-ownership exchange |
| Q11 | Domain bytes/CAS-41 retained; PF-P05 declines current text GC; PF-P08/PF-P14 settle normal backup scope | Future manual-GC eligibility and any extension to other retained evidence/bytes |
| Q12 | PF-P04/PF-P06/PF-P07/PF-P11–PF-P13 settle resume guarantee, Operational placement/lifecycle/retention | Ordinary implementation choices within those guarantees, not an unanswered same-DB versus journal policy |

PF-P14–PF-P17 also settle Search separation, direct-scan fallback and notification,
explicit index updates with measured/best-effort estimated duration, and explicit
Search creation/recovery. Their differing lifecycle from Operational DB is
intentional, not an inconsistency to normalize away.

## Remaining boundaries

**Subsequent target clarification (2026-10-19):** The table below records the
2026-10-14 baseline, not a blanket deferral of later accepted decisions.
[ADR 0030](../adr/0030-context-repository-relations-and-selective-exchange.md)
now selects immutable competing Repository mapping claims/Dispositions and
bounded selective cross-seed Exchange within DS-R05's former unresolved area.
Its accepted scope has no mapping Witness table and does not approve broader
ownership/trust extensions or establish runtime implementation. Other DS items
retain only their unsuperseded scope; future Context text GC remains separately
governed. The baseline guard/test references below are historical implementation
evidence, not instructions to reject ADR 0030's selected target.

The following IDs are audit cross-references only, **not new owner decisions or
mandatory implementation tasks**. No option is selected by listing it here.

| Audit ID | Classification | Existing contract to maintain | Question only when a concrete need arises |
| --- | --- | --- | --- |
| DS-R01 | Deferred extension | PF-P02/PF-P03 keep currently needed evidence without guaranteeing a historical-list service or permanently retained incremental baseline | Which now-unused Collection evidence could be compacted/reclaimed, and what guarantees would be lost? |
| DS-R02 | Deferred extension with an explicit future intention | PF-P05: no current domain-text GC; future explicit manual GC is planned | Define deletion eligibility, dependencies, dry-run/concurrent-change handling and preservation obligations before implementing manual text GC. Do not expand its scope to Git/quarantine by implication. |
| DS-R03 | Deferred extension | Existing verified Git content, real captures, explicit decoding/provenance and genuine ambiguities remain | Is persistent interpretation preference/history/cleanup or broader ref selection actually needed? |
| DS-R04 | Deferred extension | Existing Exchange checks validate internal domain consistency, not provider authenticity | Is any stronger sender authentication, trust or completeness attestation required? No signature/registration system is selected. |
| DS-R05 | Deferred extension | Current one-repository Exchange explicitly refuses unrepresentable disputed ownership | Is a richer portable unresolved cross-repository ownership format needed? Do not equate this boundary with failure to support ordinary confirmed transfers. |
| DS-R06 | Operational choice | PF-P09 keeps optional cache/archive outside Core validity; normal Core backup excludes it | If an adapter archive is used, choose its retention, storage budget and separate preservation for that deployment. |
| DS-R07 | Deferred extension | Q03/PF-P01 preserve known-positive associations and no absence-based automatic exclusion | Does a future application need explicit negative visibility/membership/deletion semantics? Permanent resource identity must remain separate. |
| DS-R08 | Source clarification needed; existing deferral retained | CAS-76/CAS-77 are recorded as deferred in root instructions and operational notes | Locate the original specification before assigning meaning, approval, implementation scope or test requirements. |

Evidence for DS-R05 is the [boundary explanation](../current-state-boundaries.md)
and the current `CURRENT_STATE_CROSS_REPOSITORY_CONFLICT` guard in
[current_resources.py](../../src/repo_catalog/adapters/sqlite/current_resources.py).
A [regression test source](../../tests/integration/test_current_boundaries_independent.py)
also references that rejection; the test was not rerun by this documentation audit.

[Operational notes](../operations.md) distinguish optional archive retention and
per-deployment collection budgets. LFS/attachment body retrieval, semantic search,
a data-browsing Web GUI and non-Linux restore validation are separate future
feature/platform topics, not unanswered prerequisites for Three-Store operation.
The published developer documentation/schema viewer is not that data-browsing GUI.

The inspected CAS-76/CAS-77 search results were deferral references in root
instructions, operational notes and dated model/validation records, not recovered
original option definitions. This is a bounded source-finding result, not a claim
that no definition exists anywhere in Git history or prior conversations.
**CAS-41 is different:** its quarantine-count backup/restore contract is already
established; old "CAS-41 unselected" receipts remain historical, not current policy.

## History preservation

`decision-register-before-status-reconciliation.md` reuses the exact original
register blob from the inspected baseline:

```text
original path: docs/phase2/decision-register.md
baseline:      fb3b1fb4d5e1436c58677d2e867708502fbbc64b
blob SHA-1:    0857a74baaf30b962a32e04fdbac55cbfa9420d0
```

The snapshot is intentionally unchanged, including the inconsistent old headings
that motivated the audit. Its current/historical role is stated here and in all
current entry points rather than inserted into its preserved bytes. The earlier
pre-no-Publication snapshots, prototypes, JSON/SQL inventories and execution
receipts are not edited. The old implementation-status text remains verbatim in
that page's explicitly labeled historical section.

## Verification boundary

This audit reconciles owner-decision scope against the pinned documents, schema
version declarations, merge record and focused code/search anchors. It does not
claim to retest every PF-P behavior, prove all lifetimes, or conduct a new
independent runtime review. Checks for this PR should cover Markdown/link
structure, unchanged Q01–Q04 meaning, all Q05–Q12 mappings, preservation of the
exact snapshot and historical text, and an exclusively documentation diff.

The PR's actual CI result must be reported against its submitted HEAD/effective
tree. A passing development or Pages documentation build is not release
acceptance. No production code, DDL, migration, dependency, generated schema
artifact, workflow, retained data or existing acceptance receipt is changed by
this documentation status reconciliation.
