# P5 production acquisition orchestration and typed Exchange

**Current correction:** [ADR 0028 implementation and v2 contract](p5-owner-corrections.md) supersedes the v1/accounting/verification claims below. The remaining original report is historical; use the new exact-tree correction receipt for current executed results.

P5 implements metadata-first Git acquisition, Provider (GitHub) intake normalization into Context, Core-first plus Context-second paired admission, operational retry tracking, and versioned portable typed Exchange (`git-repo-db/p5-exchange-v1`). It builds on the P5/P6 technical contract committed in PR #79 (`2a5862b76ea3a4ca976dc3de5cd6962563560101`) stacked on PR #78 (`b024ca5103e8658d4ea9717e2cbe534905552610`). The public runtime CLI remains Schema 21. No migration, real catalog mutation, activation, release, or tag is performed by P5.

The technical contract is specified in [docs/implementation/p5-p6-technical-contract.md](p5-p6-technical-contract.md). Execution evidence and verification results are documented here and in [docs/implementation/p5-execution-evidence.json](p5-execution-evidence.json).

## Implemented modules and exclusive ownership

P5 owns and implements the following production modules and integration tests exclusively:

1. `src/repo_catalog/domain/acquisition.py`:
   - Typed models for Git metadata-first acquisition: `GitNativeAcquisitionRequest`, `GitAcquisitionReport`, `NotesAcquisitionSpec`.
   - Typed models for Provider intake: `ProviderRegistration`, `RepositoryRegistration`, `SourceRegistration`, `ProviderIssueIntake`, `ProviderPullRequestIntake`, `ProviderReviewIntake`, `ProviderReviewThreadIntake`, `ProviderReviewCommentIntake`, `ProviderIssueCommentIntake`, `ProviderTimelineIntake`, `ProviderCommitContextIntake`, `ProviderFileContextIntake`, `DetachedResourceTransfer`, `ProviderIntakeBatch`, `ProviderAcquisitionReport`, `PairedAcquisitionResult`.
2. `src/repo_catalog/domain/exchange.py`:
   - Wire contract `FORMAT = "git-repo-db/p5-exchange-v1"`.
   - Typed models: `ExchangeSelectionScope`, `ExchangePackage`, `ExchangeImportReport`, `ExchangeError`.
   - Canonical deterministic JSON encoding (`encode_package`), decoding (`decode_package`), envelope validation (`validate_package_envelope`), and SHA-256 package digest calculation (`package_digest_sha256`).
3. `src/repo_catalog/domain/ports/acquisition.py`:
   - Abstract Protocols: `GitNativeAcquisitionPort`, `ProviderIntakePort`, `OperationalAcquisitionPort`, `ExchangePort`.
4. `src/repo_catalog/adapters/sqlite/acquisition.py`:
   - `OperationalAcquisitionLedger`: transactional operational ledger managing `WorkLedger` budgets, retry backoff states (`retry_state`), cache locators (`cache_locators`), request continuations, and Exchange package receipt deduplication.
5. `src/repo_catalog/adapters/github/production_intake.py`:
   - Pure, deterministic normalization of GitHub REST and GraphQL payloads into P3 `Context` resources: issues vs PRs separation, review summaries, review threads, review comments, issue comments, timeline events, PR commits, and PR file metadata with patch text (strictly excluding ordinary Git file blobs).
6. `src/repo_catalog/application/acquisition.py`:
   - `GitAcquisition`: orchestrates metadata-first acquisition from `GitNativeSource` with optional native representation retention, nominal missing reference support, and P4 Notes acquisition delegation.
   - `ProviderAcquisition`: orchestrates batch admission of normalized provider observations into `Context`.
   - `PairedAcquisitionCoordinator`: orchestrates Core-first, Context-second admission using `PairCoordinator`, with idempotent retry convergence and deferred `CoreReference` dependency reconciliation.
7. `src/repo_catalog/application/exchange.py`:
   - `ExchangeService`: verification-aware export (re-reading stored bytes through checked adapter methods so corrupt local stores halt the export) and validating import (verifying every native object, note proof bundle, text body digest, rejecting ordinary file blobs, and never trusting sender-claimed intrinsic authority without validated bytes).
8. Test suite:
   - `tests/integration/p5/test_git_acquisition.py`: 6 tests covering SHA-1/SHA-256 repositories, metadata-only mode, hybrid retention, Notes delegation, and finite work budget exhaustion.
   - `tests/integration/p5/test_provider_acquisition.py`: 5 tests covering provider/source/repo registration, PRs vs issues isolation, reviews, threads, comments, patch text without blob retention, and explicit null handling.
   - `tests/integration/p5/test_paired_admission.py`: 4 tests covering Core-first + Context-second cut failure rollback & idempotent convergence, late Core dependency promotion, operational retry ledger recreation resilience, and stop-file propagation.
   - `tests/integration/p5/test_exchange.py`: 5 tests covering export/import cycles, multi-hop A->B->C, selective filters, intrinsic spoofing rejection, tampered payload rejection, and receiver-checked Core dependency evaluation.
   - `tests/packaging/test_p5_distribution.py`: 4 tests verifying installed wheel and sdist-wheel execution across SHA-1 and SHA-256 in isolated virtual environments.

## Verification summary

All tests and audits executed and passed:
- Historical total reported: 786 (the earlier 790 prose was incorrect; this is not a new execution) (20 P5 integration tests + 4 packaging tests + 762 P1–P4 regression tests).
- Ruff check & format: 0 errors, 100% compliant.
- Schema build check (`scripts/build_p1_schema.py --check`): clean match across all four store schemas.
- Schema audit (`scripts/audit_p1_schema.py --check`): exact table-set equality, zero unclassified tables.
- Implementation boundary audit (`scripts/audit_implementation_boundary.py --check`): passes with zero violations.
- Call-site dependencies audit (`scripts/audit_callsite_dependencies.py --check`): clean match.
