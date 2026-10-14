# Architecture Decision Records (ADRs)

Start here before design, implementation or review. Scan the applicable decisions
below, then read the relevant records; this index is not a replacement for their
scope and rationale. It describes the checked-out design stack, not proof of the
currently implemented or deployed behavior.

**Operating policy:** [Shared developer/agent policy](policy.md) (proposed for owner
review by ADR 0011). Until adopted, existing owner decisions and authorizations
remain controlling. Full and [Mini-ADR](template-mini.md) authoring use the
[templates](template.md); the optional [workflow skill](../../.agents/skills/adr-workflow/SKILL.md)
is a procedure, not another policy authority.

## Active Decisions

Only accepted decisions appear here. Older records remain binding solely in their
unsuperseded scope. The source text has **not yet been fully migrated** to the new
lifecycle: see policy section 9. In particular, do not read ADR 0002's old placement
or ADR 0003's verified-only admission clauses as the current target.

| Record | Scope | Current decision, one-line summary | Constraints / Do NOT | Applicability |
| --- | --- | --- | --- | --- |
| [0001](0001-validation-lifecycle-architecture.md) | Validation | Separate risk-based local/development checks from explicit full release validation | Do not infer runtime/release acceptance from selected checks or duplicate full testing on every prose edit | Accepted validation policy; execution evidence is separate |
| [0002](0002-three-store-boundary-architecture.md) | PF-P01-PF-P17 | Preserve clauses not explicitly changed by later accepted ADRs | Do not treat its old three-store placement/full-backup scope as the new target | Legacy partial record; ADR 0003 overrides named clauses |
| [0003](0003-append-only-git-core-and-context-store.md) | Durable stores | Append-only Git Core; durable Context; separate Operational and Search; correct full-backup scope | No Core UPDATE/DELETE/REPLACE/GC; no mandatory Context for Git-only validity | Accepted target; apply ADR 0004's admission override |
| [0004](0004-metadata-only-git-core.md) | GCTX-M01 | First-class Git metadata and relationship cataloging with no raw bytes or Context | No hidden fetching or verified-byte gate on metadata-only operations | Accepted target; identity/read/evidence refinements below |
| [0005](0005-common-oid-identity-with-attributed-metadata.md) | GCTX-M02 | Common nominal `(object_format, oid)` identity with separately attributed claims and optional bytes | No implied type, possession, membership or verified closure from nominal identity | Accepted identity; physical layout remains separate |
| [0006](0006-field-claims-and-observation-scoped-relations.md) | GCTX-M03 | Field-level scalar claims and typed observation-scoped ordered relation groups | No cross-observation union, fabricated order/completeness or mutable hydration | Accepted granularity; later reads/verification refine it |
| [0007](0007-verification-aware-git-metadata-reads.md) | GCTX-M04 | Prefer precisely receiver-verified byte-derived values; expose unverified alternatives and conflicts | No source/time/decoder winner or metadata-wide verification promotion | Accepted read policy; ADRs 0008-0010 refine assurance |
| [0008](0008-domain-split-git-verification-ownership.md) | GCTX-M05 | Core owns Git verification evidence; Context owns provider assessments; Operational owns jobs | No mandatory Context authority, generic success ledger or sender-proof laundering | Accepted domain split |
| [0009](0009-bounded-byte-admission-and-physical-health.md) | GCTX-M06 | Atomic, bounded immutable local byte-admission evidence, separate from current physical health | No mutable verified bit, per-scan success history or old-proof healthy-now inference | Accepted evidence; ADR 0010 fixes operation scope |
| [0010](0010-operation-scoped-cas-physical-integrity.md) | GCTX-M07 | Operation-scoped integrity; verified output checks the actual emitted bytes; preserve CAS-41 | No verify-A/output-B, unchecked successful export or silent quarantine bypass | Accepted target; GCTX-M08 and detailed repair/snapshot protocols open |
| [Transport-independent Core](../transport-independent-core-adr.md) | Transport/provenance | Domain persistence does not depend on retained API originals; actual parser identity is provenance | No transport-replay dependency or parser-version selection authority | Legacy path; retained scope, historical baseline annotations |
| [No Independent Publication](../phase2/no-independent-publication-adr.md) | Q01-Q04 / Publication | Latest accepted resource state with necessary evidence; no independent Publication layer | No renamed generic batch/bundle/seal eligibility authority or full-history inference | Legacy path; later explicit scoped decisions govern old pending notes |

For actual implementation and exact-revision evidence, use the
[implementation status](../implementation-status.md), [decision register](../phase2/decision-register.md),
[status audit](../phase2/documentation-status-audit.md) and
[Git Core / Context transition plan](../architecture/git-core-context-transition-plan.md),
applying the accepted overrides above. An older status statement does not undo an
accepted target or prove it implemented.

## Proposed changes — not active decisions

| Record | Proposal | Status |
| --- | --- | --- |
| [0011](0011-adr-governance.md) | Shared ADR operating policy, source reconciliation and thin procedural skill | Proposed; owner review required for adoption and repository-specific adaptations |

## Allocation and maintenance

**Highest allocated ADR number: 0011**, including the proposal above. This is not
permission to assume the next number is free: check live branches/PRs and history.
Retirement or rejection does not free an ID. Synchronize this index with lifecycle
changes; preserve still-binding clauses before retiring an older file. No existing
ADR was deleted or renumbered by this policy bootstrap.
