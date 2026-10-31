---
status: proposed
date: null
replaces: []
refines:
  - 0029-independent-access-store.md
---

# ADR 0037: Operation-scoped module and installation independence

## Decision

**Proposed Full ADR.** The owner selected the directions below in the 2026-10-31
module-independence task and authorized one design-only PR. Those selections are
settled inputs; acceptance of this complete record and the recovery successor is
still pending. Neither proposal changes the running product or accepts additional
clauses by implication. Detailed operation obligations have one home in the
[operation contract](../architecture/module-independence-contract.md).

| ID | Selected direction |
| --- | --- |
| M-01 | The Core-centric basic installation includes initialization, Core reads, typed admission/integrity validation and the complete Git-only backup, stop/preservation, bounded read-only salvage, verified fresh restore, receiver-validated typed merge, final validation and safe activation lifecycle. Concrete Context, Access, Operational and Search implementations may be uninstalled. Its required Recovery implementation is included, not an optional Recovery prerequisite. |
| M-02 | Explicit Context-only reads require no concrete Core implementation or adapter, including transitively. Genuine shared values such as typed OIDs are allowed. Results establish no unavailable Core facts or Core-side byte verification. |
| M-03 | Search-specific implementation and public API require an additional installation. Authority-scan fallback belongs to Search too. Shipping it all in the basic wheel with lazy imports does not meet the guarantee. |
| M-04 | Git-only activation requires neither Operational/Search code nor their DBs, initialization or rebuilding. Initialize those features when subsequently enabled and needed under their existing rules. This changes recovery completion and timing only; paired activation is unchanged. |
| M-05 | Guarantee the minimal combinations in the operation contract, for Python APIs and existing corresponding CLIs. High-level acquisition and Exchange orchestration are additional features. No new comprehensive CLI is required. |
| M-06 | Context's new minimum is reading. Existing supported initialization/mutation is retained; any added independence guarantees are operation-specific. Context-only backup/recovery is separately scoped. |
| M-07 | Use logical responsibilities and one definition of shared contracts. Wheel count, names, namespaces, class names and dependency syntax remain engineering choices. Neither five wheels, duplicate domain models, conversion layers, generic Store abstraction nor plugin registry is required. Initially use one repository and synchronized releases; independently released distribution compatibility is not required. |

C/T/A/O/S denote Core/Context/Access/Operational/Search responsibilities; G/X/R
are acquisition/Exchange/Recovery capabilities, not new authoritative stores or
mandated distributions. Ordinary runtime's three stores, the P1 four-store
factory subset, five architectural responsibilities, Python modules, artifacts
and operation composition have different counts and meanings.

## Constraints / Do NOT

- Distinguish separate DBs, avoiding DB opens, avoiding concrete imports, actual
  code absence at installation, and explicit multi-module composition. No import
  test alone proves installation independence.
- Missing validation capability requires explicit refusal, never skipped checks,
  silent paired-to-single downgrade or ignored supplied Context sections.
  Missing capability, unsupported input, exhausted resources and confirmed stored
  authoritative corruption have different diagnoses.
- Preserve Core INSERT-only and shared typed identities; catalog-wide persistent
  stops including in-flight completion; original/WAL preservation; fresh restore;
  receiver-local typed admission; finite cumulative actual-work budgets; exact
  replay, package binding and honest partial scope. No volatile accounting shortcut.
- Explicit Core-only reads do not inspect coexisting Context. Exchange still
  validates required coexisting authority identities/pairs and **all supplied
  sections**, independently of selection. Keep current auto/paired defaults.
- Search remains derivative with pinned authority, candidate/content/completeness
  validation and authority-scan fallback. Freshness tokens alone prove no result
  correctness; ordinary reads create/repair no Search DB. Preserve exact-Claim
  RefObservation/Notes body authority under ADR 0036.
- Access remains durable configuration, not Core/Context authority or automatic
  execution permission. Isolated Access loss/damage does not prevent sound offline
  reads; restored/imported settings require local approval and credential/trust
  boundaries. No package installation mutates catalog databases.
- Do not move all Operational code into Core under another name. Shared locks,
  stop fences and durable Recovery accounting are not automatically optional O.
- These targets authorize no product split, wheel/dependency/DDL/test/CI change,
  migration, normal Schema 21 switch, implementation PR, merge or deployment.

## Context & Reason

PRs #210–#213 already isolated opt-in initialization, Query and Exchange at
particular import/open boundaries. PRs #226–#230 completed the RefObservation
transition, including independent review outside GitHub; #231–#234 improved
navigation and standardized opt-in `object_oid`. These are baseline work, not
new implementation tasks. The single wheel still ships all features. Context
reads import concrete Core, Search API remains in the shared Query surface and
Recovery imports Context and initializes optional stores on activation.

Level 3 applies because this changes public/distribution boundaries and recovery
availability, with long-lived cross-module obligations. Lazy loading alone cannot
provide absent-code installations. Read-only Core would omit its existing typed
admission and the owner's complete recovery requirement. Mandatory optional-store
reconstruction defeats Git-only activation on a basic installation.

This record additively specifies ADR 0029's logical boundaries. M-04 **reverses**
ADR 0026 §5 and §6.9 for Git-only recovery; it is not a `refines` relationship to
0026. The complete proposed [ADR 0038](0038-scoped-recovery-and-optional-initialization.md)
contains its surviving obligations and clause audit, applying ADR 0036's later
supersession. The two proposals must be reconciled/accepted together for M-04;
0026 remains accepted during review. No contradictory pair is marked accepted.

## Consequences

The target makes supported small installations explicit, at the cost of separating
shared contracts, feature code and integration entry points, and maintaining
isolated build/install evidence. Exact packaging and implementation sequence remain
engineering work after design acceptance and separate authorization. Existing
supported functionality outside the minimum is not removed by omission.

Before integration, the owner must review/accept complete 0037/0038 text and the
carry-forward audit. Acceptance/retirement of 0026 must update all effective
references coherently under policy §6, after preservation review. Acceptance,
integration, implementation and executed verification remain separate.

## References

- Owner task, 2026-10-31: “Record the agreed module-independence design in
  git-repo-db”; subsequent instruction to proceed only through design PR submission.
- [ADR policy](policy.md), [ADR 0029](0029-independent-access-store.md),
  [ADR 0036](0036-ref-observations-and-shared-notes-mappings.md).
- [Recovery successor and audit](0038-scoped-recovery-and-optional-initialization.md),
  [current implementation snapshot](../implementation/core-independence-contract-matrix.md).
- Investigation base: main `c2ae058b6402e0f5055c864fba1ed4ec7992a8aa`.
  Index watermark, all fetched remote heads, reachable filename history including
  deletions and open PRs checked 2026-10-31: highest allocation 0036, no open PRs.
  Allocate 0037 and 0038 in this single design PR. Execution/review evidence belongs
  in the PR, not in this decision's authority.
