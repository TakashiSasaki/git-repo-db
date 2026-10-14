# Architecture Decision Records (ADRs)

This directory contains formal Architecture Decision Records for the `git-repo-db` project.

## Accepted Records

| ADR | Title | Decision Date | Status |
|---|---|---|---|
| [ADR 0001](0001-validation-lifecycle-architecture.md) | Development and Release Validation Lifecycle Architecture | 2026-10-12 | Accepted target design |
| [ADR 0002](0002-three-store-boundary-architecture.md) | Three-Store Boundary Architecture (PF-P01–PF-P17) | 2026-10-12 | Accepted historical baseline; store placement/backup scope superseded by ADR 0003 |
| [ADR 0003](0003-append-only-git-core-and-context-store.md) | Append-only Git Core and Durable Context Store | 2026-10-14 | Accepted **target** design; metadata admission narrowly superseded by ADR 0004; implementation pending |
| [ADR 0004](0004-metadata-only-git-core.md) | Mandatory Metadata-only Git Core (GCTX-M01) | 2026-10-14 | Accepted owner requirement; detailed design and implementation pending |
| [ADR 0005](0005-common-oid-identity-with-attributed-metadata.md) | Common OID Identity with Attributed Git Metadata (GCTX-M02) | 2026-10-14 | Accepted common identity; grouping fixed by ADR 0006 |
| [ADR 0006](0006-field-claims-and-observation-scoped-relations.md) | Field-level Claims and Observation-scoped Git Relation Groups (GCTX-M03) | 2026-10-14 | Accepted hybrid granularity; normal reads fixed by ADR 0007 |
| [ADR 0007](0007-verification-aware-git-metadata-reads.md) | Verification-aware Canonical Git Metadata Reads (GCTX-M04) | 2026-10-14 | Accepted normal-query policy; verifier responsibility fixed by ADR 0008 |
| [ADR 0008](0008-domain-split-git-verification-ownership.md) | Domain-split Git Verification Ownership (GCTX-M05) | 2026-10-14 | Accepted responsibility split; evidence/health representation pending |
| [Transport-Independent Core](../transport-independent-core-adr.md) | Transport-independent core persistence and minimal parser provenance | 2026-10-10 | Accepted target design |
| [Phase 2 No Independent Publication](../phase2/no-independent-publication-adr.md) | No Independent Publication in Phase 2 Architecture | 2026-10-10 | Accepted target design |
