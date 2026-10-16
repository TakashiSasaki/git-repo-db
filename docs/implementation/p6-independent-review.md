# P6 Independent Review and Verification

This is the historical baseline review record. Current correction and fresh
independent execution are tracked in [P6 corrections](p6-corrections.md). The
former FTS5 matching description was inaccurate: the implementation used ordinary
`instr()` scans with complete authority verification. The old report cited nonexistent abbreviated test names; the table below now
names their actual behavioral counterparts and does not establish a new
independent execution for the old SHA. Historical node counts
remain attributed to the executable below; they are not new correction results.

Final executable reviewed: `d7de65737a44bd1d8f72c3fb1ed191a05822a2e3`, tree
`8c3f2b6652def984f1bb6cda0e7cc355d6db241e`. The implementation commit
preserves every executable, packaging, schema, and test input at that revision;
the [receipt](p6-execution-evidence.json) records their exact SHA-256 values.
Review agents were read-only, independently inspected executable source, and
verified execution against P1–P4 contracts and ADR 0027 decisions. None authored
its reviewed implementation. These are local independent reviews, not GitHub
approvals or Release Acceptance.

## Findings and Revalidation

| Finding | Investigated Risk / Requirement | Verification and Status | Final Status |
| --- | --- | --- | --- |
| P6-R1 | Default CLI `src/repo_catalog/cli/main.py` mutated or Schema 21 entry point altered. | Verified: Schema 21 default CLI was untouched (0 diffs). Opt-in CLI is exposed via separate entry point `python -m repo_catalog.cli.production_query` (`main`). Verified via audit and CLI tests. | Independently closed |
| P6-R2 | Derivative Search loss or corruption causing recovery stop or blocking authoritative queries. | Verified: Loss of `search.sqlite3` or corruption triggers transparent fallback to `authority_scan` without writing `p1-recovery-stop.json`. Verified via `test_search_projection_and_five_fallback_scenarios_never_stop_catalog`. | Independently closed |
| P6-R3 | Snapshot token inconsistency across pagination requests. | Verified: Pagination cursors include deterministic snapshot token and ordering; mismatched snapshot tokens reject or fence inconsistent cursor replay. Verified via `test_deterministic_pagination_across_all_endpoints`. | Independently closed |
| P6-R4 | Authoritative corruption on Core or Context not triggering immediate stop. | Verified: Authoritative tampering triggers immediate `CoreFailure("AUTHORITATIVE_CORRUPTION")`, writes `p1-recovery-stop.json`, and halts all subsequent queries with `CoreFailure("RECOVERY_STOP")`. Verified via `test_verification_aware_byte_reads_detect_corruption_and_fence_catalog`. | Independently closed |
| P6-R5 | Cross-store DDL or schema drift in SQLite databases. | Verified: `schema.py` and all four store schemas (`core`, `context`, `operational`, `search`) remain bit-for-bit identical to P4. Verified via `audit_p1_schema.py --check`. | Independently closed |

## Independent Execution Evidence

| Reviewer | Verification Scope | Result |
| --- | --- | --- |
| Reviewer A — Authoritative Queries | Git Core object views, Notes proof queries, Context views, Paired resolution | 6 integration tests passed; zero skips/errors |
| Reviewer B — Derivative Search | Projection rebuild, ordinary substring matching, freshness validation, transparent authority_scan fallback | 4 integration tests passed; zero skips/errors |
| Reviewer C — Pagination & Snapshots | Stable cursor decoding, ordered pagination, snapshot token fencing | 2 integration tests passed; zero skips/errors |
| Reviewer D — Opt-in CLI & Stop Fencing | Subcommands (git-object, context, paired, search, search-rebuild), exit codes, recovery stop fencing | 2 integration tests passed; zero skips/errors |
| Packaging & Distribution | Installed wheel and sdist-wheel outside checkout for SHA-1 and SHA-256 | 4 distribution tests passed; zero skips/errors |
| Architecture & Boundaries | All four repository audits (`audit_implementation_boundary.py`, `audit_p1_schema.py --check`, `audit_callsite_dependencies.py`, `audit_publication_free.py`) | 4 audits passed; 0 DDL or reference drift |
| Full Regression Suite | P1, P2, P3, P4, P6 suites | 780 tests passed; zero failures/skips |

## Verification Limits

The local run is focused development verification. Hosted Development CI
runs selected inexpensive checks, not complete hosted runtime/packaging Release
Acceptance. No real catalog, authenticated external acquisition, main merge,
deployment, or release was performed.
