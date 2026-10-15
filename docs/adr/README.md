# Architecture Decision Records (ADRs)

Read the current scope before implementation. This index describes accepted target decisions, not implemented or verified behavior.

**Latest product scope: [ADR 0014 / GCTX-S01](0014-history-and-notes-catalog-without-file-archive.md).** The product does not archive ordinary repository-file blob bodies. It retains Git metadata, commit/tree/tag representations when acquired, and purpose-bound Git notes content. Notes are blobs at the Git object layer, so a blanket blob ban is incorrect. [ADR 0015 / B01-R01](0015-automatic-git-notes-ref-discovery.md) fixes automatic notes namespace discovery plus explicit additional ref names, **not** note-body admission or complete enumeration. Earlier raw-body admission/repair decisions apply only to retained metadata/notes and legacy obligations. B01-R02 observation identity is fixed by [ADR 0016](0016-immutable-notes-ref-capture-observations.md); B01-R03 capture issuance/replay rules and GCTX-M10 remain unresolved.

## Accepted Records

| ADR | Decision | Date | Current applicability |
| --- | --- | --- | --- |
| [0001](0001-validation-lifecycle-architecture.md) | Development and release validation lifecycle | 2026-10-12 | Accepted; execution evidence is separate |
| [0002](0002-three-store-boundary-architecture.md) | Three-store PF-P01–PF-P17 baseline | 2026-10-12 | Placement/full-backup superseded by 0003; other clauses preserved |
| [0003](0003-append-only-git-core-and-context-store.md) | Append-only Git Core and durable Context | 2026-10-14 | Four-store target preserved; admission narrowed by 0004 and 0014 |
| [0004](0004-metadata-only-git-core.md) | GCTX-M01: metadata-only Core | 2026-10-14 | Fully supported; optional body admission now restricted by 0014 |
| [0005](0005-common-oid-identity-with-attributed-metadata.md) | GCTX-M02: shared nominal OID identity | 2026-10-14 | Preserved; note and file roles do not duplicate identity |
| [0006](0006-field-claims-and-observation-scoped-relations.md) | GCTX-M03: field claims and typed relation groups | 2026-10-14 | Preserved; notes require appropriately scoped associations |
| [0007](0007-verification-aware-git-metadata-reads.md) | GCTX-M04: canonical values with explicit alternatives | 2026-10-14 | Preserved; never imply ordinary blob verification from its parent tree |
| [0008](0008-domain-split-git-verification-ownership.md) | GCTX-M05: verifier domain ownership | 2026-10-14 | Core checks retained metadata/notes; Context owns Provider assessment |
| [0009](0009-bounded-byte-admission-and-physical-health.md) | GCTX-M06: bounded immutable admission evidence | 2026-10-14 | Retained metadata/notes; not an ordinary file-body archive |
| [0010](0010-operation-scoped-cas-physical-integrity.md) | GCTX-M07: operation-scoped physical integrity | 2026-10-15 | Actual allowed-body output verified; whole repository restoration is out of scope |
| [0012](0012-append-only-multiple-cas-physical-instances.md) | GCTX-M08: append-only physical recovery | 2026-10-15 | Retained bodies and legacy obligations; no general blob archival API |
| [0013](0013-deterministic-cas-instance-eligibility.md) | GCTX-M09: evidence-derived candidate selection | 2026-10-15 | Retained bodies; GCTX-M10 quarantine/count predicate still open |
| [0014](0014-history-and-notes-catalog-without-file-archive.md) | GCTX-S01: history/structure/notes catalog, no ordinary file archive | 2026-10-15 | Accepted scope revision; notes ref discovery refined by 0015 |
| [0015](0015-automatic-git-notes-ref-discovery.md) | B01-R01: auto-discover `refs/notes/*` and explicitly nominated notes refs | 2026-10-15 | Accepted discovery policy; capture identity refined by 0016 |
| [0016](0016-immutable-notes-ref-capture-observations.md) | B01-R02: immutable capture-scoped notes-ref observation identity | 2026-10-15 | Accepted distinct genuine captures and idempotent same-capture replay; B01-R03 portable origin/replay key, B02 and B03 still open |
| [Transport-independent Core](../transport-independent-core-adr.md) | Domain persistence and provenance independent of transport replay | 2026-10-10 | Preserved in unsuperseded scope |
| [No Independent Publication](../phase2/no-independent-publication-adr.md) | Publication-free domain authority | 2026-10-10 | Preserved; no new generic notes/retention seal |

**Concurrent allocation:** ADR 0011 is reserved by proposed [governance PR #52](https://github.com/TakashiSasaki/git-repo-db/pull/52). Its policy/templates are not adopted or merged here. ADRs 0014 and 0015 follow accepted ADR 0013; the shared index and AGENTS.md changes require reconciliation during a later explicitly authorized sibling-stack integration. No ADR is deleted and no historical decision ID is reused.

The [transition plan](../architecture/git-core-context-transition-plan.md) describes the redesigned implementation sequence. Old Phase 2 handoffs and accepted records remain evidence of their original decisions, subject to the explicit scoped override in ADR 0014. Neither old wording nor a passing documentation check is authority to implement an excluded file-storage path.
