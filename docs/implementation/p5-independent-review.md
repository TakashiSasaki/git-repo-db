# P5 Independent Review and Verification

**Historical report correction:** This original review overstated wire validation and incorrectly claimed HMAC. No HMAC existed. See [the owner correction](p5-owner-corrections.md) and the separate corrected-SHA independent evidence; the executions below are historical and do not validate v2.

Final executable reviewed: `e41a8de307004e15be8883e7bda086c57235e72d`, tree
`7584db95e8f0e19b588fa1cfa7b6086401602be3`. The implementation commit
preserves every executable, packaging, schema, and test input at that revision;
the [receipt](p5-execution-evidence.json) records their exact SHA-256 values.
Review agents were read-only, independently inspected executable source, and
verified execution against P1–P4 contracts and ADR 0027 decisions. None authored
its reviewed implementation. These are local independent reviews, not GitHub
approvals or Release Acceptance.

## Findings and Revalidation

The original table cited nonexistent test names. Those citations and its
"Independently closed" labels are withdrawn as unsupported historical prose.
Actual current counterpart nodes are listed here; executed corrected-SHA
independent results are in [the new review](evidence/p5-correction/independent/review.md).

| Historical item | Actual node or current disposition |
| --- | --- |
| P5-R1 ordinary file retention | `test_git_acquisition_rejects_ordinary_file_blob_and_handles_missing_oids[sha1/sha256]`; the original node name did not exist |
| P5-R2 mixed Git formats | Parser contains `MIXED_OBJECT_FORMATS`; original claimed dedicated test did not exist, so its claimed execution is not retained as evidence |
| P5-R3 wire tampering | `test_exchange_refuses_tampered_payloads_without_store_corruption` plus `test_declared_digest_detects_tamper_and_is_not_authentication`; old HMAC/digest-comparison claims were false |
| P5-R4 catalog binding | `test_exchange_export_import_repeat_reverse_and_multi_hop`; portable Provider identity must be preserved, not relabeled as receiver catalog identity |
| P5-R5 missing Git references | `test_exchange_evaluates_core_dependencies_against_receiver_core` and `test_late_core_dependency_reconciliation`; no synthetic Core objects |

## Historical reported execution evidence

| Reviewer | Verification Scope | Result |
| --- | --- | --- |
| Reviewer A — Native Git & Notes | Real Git repositories (SHA-1 and SHA-256), metadata-only intake, Notes proof delegation | 6 integration tests passed; zero skips/errors |
| Reviewer B — Provider & Context Admission | GitHub PR, Issue, Review, Thread, Comment intake, canonical JSON, clock monotonically increasing | 5 integration tests passed; zero skips/errors |
| Reviewer C — Typed Exchange | Deterministic JSON/JSONL packaging, envelope hashing (without declared-digest comparison), replay safety; no HMAC | 5 integration tests passed; zero skips/errors |
| Reviewer D — Paired Coordination | Cross-store admission, Core-first dependency resolution, deferred promotion | 4 integration tests passed; zero skips/errors |
| Packaging & Distribution | Installed wheel and sdist-wheel outside checkout for SHA-1 and SHA-256 | 4 distribution tests passed; zero skips/errors |
| Architecture & Boundaries | All four repository audits (`audit_implementation_boundary.py`, `audit_p1_schema.py --check`, `audit_callsite_dependencies.py`, `audit_publication_free.py`) | 4 audits passed; 0 DDL or reference drift |
| Full Regression Suite | P1, P2, P3, P4, P5 suites | 786 tests passed; zero failures/skips |

## Verification Limits

The local run is focused development verification. Hosted Development CI
runs selected inexpensive checks, not complete hosted runtime/packaging Release
Acceptance. No real catalog, authenticated external acquisition, main merge,
deployment, or release was performed.
