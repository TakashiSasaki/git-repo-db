# P5 Independent Review and Verification

Final executable reviewed: `e41a8de307004e15be8883e7bda086c57235e72d`, tree
`7584db95e8f0e19b588fa1cfa7b6086401602be3`. The implementation commit
preserves every executable, packaging, schema, and test input at that revision;
the [receipt](p5-execution-evidence.json) records their exact SHA-256 values.
Review agents were read-only, independently inspected executable source, and
verified execution against P1–P4 contracts and ADR 0027 decisions. None authored
its reviewed implementation. These are local independent reviews, not GitHub
approvals or Release Acceptance.

## Findings and Revalidation

| Finding | Investigated Risk / Requirement | Verification and Status | Final Status |
| --- | --- | --- | --- |
| P5-R1 | Native Git acquisition retaining ordinary file blob contents would violate zero-blob retention invariant. | Verified: `GitAcquisition` only retains commit, tree, and tag representations (`retained_metadata`), explicitly rejecting ordinary file blobs. Verified via `test_git_acquisition_sha1_and_sha256`. | Independently closed |
| P5-R2 | Mixed SHA-1 and SHA-256 OIDs within a single Pull Request or Git acquisition request could poison cross-store integrity. | Verified: `AcquisitionError("MIXED_OBJECT_FORMATS")` raised if head/base/merge OIDs mix object formats. Verified via `test_pr_mixed_formats_rejected`. | Independently closed |
| P5-R3 | Untyped or unverified Exchange packages accepted into durable store. | Verified: Strict wire-envelope decode, mandatory schema versioning, SHA-256 digest validation, and optional HMAC authentication prevent corrupted/tampered package intake. Verified via `test_exchange_tamper_detection`. | Independently closed |
| P5-R4 | Cross-catalog Exchange preserving foreign `catalog_instance_uuidv4` as local identity. | Verified: Admitted items are registered under receiving service instance identity while preserving sender provenance in `provenance_json`. Verified via `test_exchange_roundtrip_core_and_context`. | Independently closed |
| P5-R5 | Context CoreReferences referencing non-existent Core objects admitted into Core directly without validation. | Verified: Core-first dependency model enforces that unverified Git references remain in Context `core_references` with unresolved status until Git acquisition arrives and `reconcile_core_dependencies` runs. No synthetic Core objects are minted. Verified via `test_paired_admission_core_first_enforcement`. | Independently closed |

## Independent Execution Evidence

| Reviewer | Verification Scope | Result |
| --- | --- | --- |
| Reviewer A — Native Git & Notes | Real Git repositories (SHA-1 and SHA-256), metadata-only intake, Notes proof delegation | 6 integration tests passed; zero skips/errors |
| Reviewer B — Provider & Context Admission | GitHub PR, Issue, Review, Thread, Comment intake, canonical JSON, clock monotonically increasing | 5 integration tests passed; zero skips/errors |
| Reviewer C — Typed Exchange | Deterministic JSON/JSONL packaging, envelope hashing, HMAC verification, replay safety | 5 integration tests passed; zero skips/errors |
| Reviewer D — Paired Coordination | Cross-store admission, Core-first dependency resolution, deferred promotion | 4 integration tests passed; zero skips/errors |
| Packaging & Distribution | Installed wheel and sdist-wheel outside checkout for SHA-1 and SHA-256 | 4 distribution tests passed; zero skips/errors |
| Architecture & Boundaries | All four repository audits (`audit_implementation_boundary.py`, `audit_p1_schema.py --check`, `audit_callsite_dependencies.py`, `audit_publication_free.py`) | 4 audits passed; 0 DDL or reference drift |
| Full Regression Suite | P1, P2, P3, P4, P5 suites | 786 tests passed; zero failures/skips |

## Verification Limits

The local run is focused development verification. Hosted Development CI
runs selected inexpensive checks, not complete hosted runtime/packaging Release
Acceptance. No real catalog, authenticated external acquisition, main merge,
deployment, or release was performed.
