# Phase 2: Publication-independent reconstruction

**Current status:** Q01-B/Q02-B/Q03-B, **NO_INDEPENDENT_PUBLICATION**, and
**PF-P01–PF-P17** are accepted. Publication removal and the later Three-Store
implementation have been integrated into `main`. The old Publication-centered
69-table sketch is not the target. This page reconciles status, not policy.

**Accepted newer target, not implemented:** Start with the [current ADR index](../adr/README.md) and [Git Core / Context transition plan](../architecture/git-core-context-transition-plan.md). ADR 0003–0027 narrowly supersede the baseline where stated: INSERT-only Git Core, independently durable Context, metadata-only operation and purpose-bound notes without ordinary file archival. ADR 0026 replaces quarantine/count/release and known-corrupt normal restore with immediate recovery, read-only preservation, fresh verified restore and validated salvage merge. ADR 0027 accepts unauthenticated external-origin reports without application PKI/electronic signatures. These decisions do not certify implementation or authorize execution.

## Current design and implementation instructions

1. Start with the [decision register](decision-register.md) and
   [documentation status audit](documentation-status-audit.md). They separate
   accepted scope, implementation facts, deferred extensions and historical labels.
2. Read [No independent Publication](no-independent-publication-adr.md) for the
   accepted Q01–Q04 decisions and [ADR 0002](../adr/0002-three-store-boundary-architecture.md)
   for the implemented PF-P01–PF-P17 Three-Store baseline and unaffected guarantees;
   apply the current ADR index for scoped target replacements. The old pause and
   pre-implementation work sequence are not instructions to repeat completed work.
3. Use the [packaged schema composition](../../src/repo_catalog/adapters/sqlite/schema.py)
   and [schema map](publication-free-schema-map.json) for implemented structures.
   The inspected baseline uses Core Schema 21, Operational Schema 1 and Search
   Schema 1. [Implementation status](../implementation-status.md) distinguishes
   integration from verification and release acceptance.
4. The [Publication-free architecture](publication-free-design.md),
   [implementation prompt](publication-free-implementation-prompt.md),
   [Schema 20 handoff](publication-free-implementation.md) and
   [test disposition](publication-free-test-disposition.json) explain the earlier
   reconstruction. Preserve their domain guarantees where not superseded, but do
   not mistake dated progress, old DB placement or review instructions for current
   status. [ADR 0001](../adr/0001-validation-lifecycle-architecture.md) governs the
   current development/release validation distinction.

## The decisive boundary

No independent Publication ID, generic input/output manifest, member/seal
registry, selected interpretation or universal publish transition may own or
enable ordinary domain resources. Renaming the same abstraction does not help.

Identity and ownership belong to the actual resource. A coherent local update
commits values, field evidence and applicable conflict/revision state atomically.
Completeness belongs to the exact collection, required children, Git closure or
code target. Exchange validates actual typed dependencies. A valid resource does
not become unusable merely because a larger acquisition is incomplete.

Latest-state choices must not become full edit/roster history hidden in evidence.
Necessary current origins, unresolved candidates and still-used target/scope
evidence remain. Exact retained bytes, domain text and actual database/manifest/
identity/pairing checks remain protected. ADR 0014 scopes retained bodies and ADR
0026 retires the old CAS-41 active-quarantine counter/order for the target.
`advance_local_revision()` / mutable Core `local_revision` describe baseline
mechanisms; the INSERT-only target requires an append-only-safe/fenced replacement.
Revision fencing and atomic installation remain mechanical responsibilities,
not independent domain Publications or a new counter-history authority.

## Integration baseline

The original reconstruction began against Schema 18 and the #22–#29 stack. That
sequence is historical, not a pending integration task. The later Three-Store
stack was [PR #38](https://github.com/TakashiSasaki/git-repo-db/pull/38) followed by
[PR #39](https://github.com/TakashiSasaki/git-repo-db/pull/39).

This status audit inspected `fb3b1fb4d5e1436c58677d2e867708502fbbc64b`. Fetch the
actual current refs for any new work; do not reset to an old design branch.
Neither these links nor an old merge permission authorizes another merge.

## Evidence and remaining policy boundaries

The [previous proposal](proposal-before-no-publication.md),
[pre-no-Publication questionnaire](decision-register-before-no-publication.md),
[pre-reconciliation register](decision-register-before-status-reconciliation.md),
workstreams, prototypes and dated receipts remain checkpoint evidence. Do not
rewrite old failures or old non-execution as later successful tests.

Q05–Q12 are not one undifferentiated pending or resolved bundle. Accepted later
choices settle storage, restart, backup, HTTP ownership, attribute admission and
Search lifecycle. Evidence reclamation, stronger trust, richer disputed-ownership
Exchange and new Git interpretation policies remain separate deferred extensions;
adapter/deployment settings and source-unclear CAS identifiers have different
statuses. See [remaining boundaries](documentation-status-audit.md#remaining-boundaries).

For a documentation-only status correction, perform relevant prose/link/scope
checks. A full suite or four-reviewer cycle is not required merely because those
steps appear in the old large-reconstruction handoff. No new runtime validation
or independent approval is asserted by this page.
