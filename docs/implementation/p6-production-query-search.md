# P6 production authoritative query APIs, derivative Search, and opt-in CLI

P6 implements authoritative query services, consistent snapshot fencing, opaque signed cursor pagination, derivative Search projection with transparent fallback to authoritative scan, verification-aware byte access, and opt-in CLI query access (`repo_catalog.cli.production_query`). It builds on the P5/P6 technical contract committed in PR #79 (`2a5862b76ea3a4ca976dc3de5cd6962563560101`) stacked on PR #78 (`b024ca5103e8658d4ea9717e2cbe534905552610`). The default runtime CLI (`repo_catalog.cli.main`) remains Schema 21. No migration, real catalog mutation, activation, release, or tag is performed by P6.

The technical contract is specified in [docs/implementation/p5-p6-technical-contract.md](p5-p6-technical-contract.md). Execution evidence and verification results are documented here and in [docs/implementation/p6-execution-evidence.json](p6-execution-evidence.json).

## Implemented modules and exclusive ownership

P6 owns and implements the following production modules and integration tests exclusively:

1. `src/repo_catalog/domain/production_query.py`:
   - Query modes: `CatalogReadMode` (`core_only`, `context_only`, `paired`).
   - Snapshot fencing: `SnapshotFenceToken` with deterministic JSON serialization, table-state digest calculation, and parser.
   - Deterministic pagination: `PageRequest`, `PageResult`, `PaginationCursor` (encoding endpoint kind, filter digest, snapshot token, and last key, failing closed with `SNAPSHOT_MISMATCH` or `INVALID_CURSOR`).
   - Verification-aware byte reading: `ByteReadResult`.
   - Core view projections: `GitRepositoryView`, `GitObjectView`, `GitObservationView`, `NotesCaptureView`, `NotesTargetView`, `NotesInventoryView`, `CoverageView`.
   - Context view projections: `ProviderView`, `SourceView`, `ContextResourceView`, `PairedResourceView`.
   - Search domain models: `SearchQuery`, `SearchHit`, `SearchResponse`.
2. `src/repo_catalog/domain/ports/production_query.py`:
   - Abstract Protocols: `ProductionQueryPort`, `ProductionSearchPort`.
3. `src/repo_catalog/adapters/sqlite/production_search.py`:
   - `ProductionSearchAdapter`: indexes authoritative metadata, notes, and Context text into `search.sqlite3` (`search_projections`, `search_documents`). Checks snapshot token freshness and structural completeness; returns candidate hits when fresh, or signals unindexed/stale state for transparent authoritative scan fallback without ever triggering false recovery stops. Ordinary file blobs are strictly excluded from indexing.
4. `src/repo_catalog/application/production_query.py`:
   - `ProductionQueryService`: provides unified read APIs across single-store (`core_only`, `context_only`) and `paired` catalogs. Enforces stop-file checking, opens consistent snapshots (`PairCoordinator.snapshots`), executes verification-aware byte reads (halting immediately on detected authoritative corruption), and executes searches with candidate verification against pinned authoritative snapshots and fallback to authoritative scan when `search.sqlite3` is unbuilt, stale, or corrupt.
5. `src/repo_catalog/cli/production_query.py`:
   - Isolated opt-in CLI entry point invokable via `python -m repo_catalog.cli.production_query`. Subcommands output canonical deterministic JSON to stdout: `status`, `git-object`, `git-objects`, `git-observations`, `notes`, `context-resource`, `context-resources`, `paired-resource`, `paired-resources`, `search-rebuild`, and `search`. Does not touch `repo_catalog.cli.main`.
6. Test suite:
   - `tests/integration/p6/test_queries.py`: 6 tests covering Core-only, Context-only, and Paired queries across SHA-1 and SHA-256; views, claims, notes, relations; cross-store paired resource resolution; and corruption-halting byte reads.
   - `tests/integration/p6/test_pagination_snapshots.py`: 3 tests covering deterministic pagination ordering, snapshot isolation against concurrent writers, cursor token mismatch detection, and invalid cursor rejection.
   - `tests/integration/p6/test_search_fallback.py`: 3 tests covering search projection indexing, automatic fallback to authority scan across unbuilt, stale, or corrupted `search.sqlite3`, and non-indexing of ordinary file blobs.
   - `tests/integration/p6/test_cli.py`: 2 tests exercising all opt-in CLI subcommands and JSON outputs.
   - `tests/packaging/test_p6_distribution.py`: 4 tests verifying installed wheel and sdist-wheel execution across SHA-1 and SHA-256 in isolated virtual environments.

## Verification summary

All tests and audits executed and passed:
- Total tests executed: 18 P6 tests (14 integration + 4 packaging) + 762 P1–P4 regression tests = 780 tests.
- Ruff check & format: 0 errors, 100% compliant.
- Schema build check (`scripts/build_p1_schema.py --check`): clean match across all four store schemas.
- Schema audit (`scripts/audit_p1_schema.py --check`): exact table-set equality, zero unclassified tables.
- Implementation boundary audit (`scripts/audit_implementation_boundary.py --check`): passes with zero violations.
- Call-site dependencies audit (`scripts/audit_callsite_dependencies.py --check`): clean match.
