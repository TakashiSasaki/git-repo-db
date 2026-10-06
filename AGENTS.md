# Coding agent guide

This guide applies repository-wide. Coding-agent task specifications and handoffs are written in English; user-facing explanations may be Japanese.

## Current product and working rules

Catalog3 is the sole ordinary runtime for initialization, source discovery, Git and GitHub collection, resumable synchronization, offline queries/search and essential maintenance. One packaged guarded offline v2 salvage importer writes the same format; explicit finalization establishes readiness. See `docs/schema-hardening/runtime-handoff.md` for implemented behavior, validation and limits. Historical reports are evidence, not standing acceptance gates.

This is an unreleased single-developer application. Backward compatibility with old schemas, CLI/API outputs, converter phases and workspaces is unnecessary. Direct main development, a single branch or stacked PRs are allowed. Intermediate checkpoints may be incomplete. Do not discard uncommitted work or rewrite history for tidiness.

Only disposable synthetic data is authorized. Do not access the user's actual DB/cache, send acquisition requests with real credentials, change an active catalog, publish a release or perform real-data cutover. Preserve acquired data support through one resumable offline v2 salvage importer; preserve source bytes, IDs, raw values, history and attributable diagnostics. No source overwrite or implicit acquisition.

## Architecture

- Dependencies remain `cli -> application -> domain/ports`; adapters own SQLite, Git/HTTP and filesystem operations.
- Authoritative catalog3 DDL belongs in packaged resources, shared by initializer, importer, writer, reader and maintenance. Fresh catalogs do not traverse v2 migrations or historical phase receipts.
- Use normal SQLite locking/transactions for mutable runtime catalogs, FK and recursive triggers on every connection, and the existing OS writer lock. Never use immutable connections against changing catalogs. Offline queries do not migrate, acquire, execute Git or repair indexes.
- Enforce same-owner relations, sealed completed listings and explicit readiness. Optional missing content is partial coverage; critical identity corruption blocks finalization. Current pointers need suitable completed same-owner observations and justified ordering.
- Preserve format-scoped OIDs, raw paths/ref/name bytes, ordered parents, separate origins for shared traversal roots, payload/page history and distinct A->B->A observations. Missing content is not empty bytes.
- Commit pages/progress atomically. Resume does not advance watermarks or replay responses as new remote observations. Scope/identity/principal/API/parser/profile/head/base evidence determines imported reuse; unsupported cursors receive targeted refresh and retain history.
- Imported evidence needed for later audit must remain in the catalog. Runtime caches are isolated from preserved source material. Never reactivate historical jobs/leases/reservations.
- Offline importer guards prohibit source writes and acquisition. Keep legacy schema/parser isolated as import support. Do not disable source/network protection to accommodate a toolchain.

## Development and validation

Use one practical working Python/SQLite binding; inspect actual capabilities and report actual versions. There is no promised minimum-version matrix. Remove independent SQLite-minimum lanes and historical phase compatibility gates. Retain narrowly justified correctness safeguards.

Run focused tests while editing, then compact end-to-end workflows. Final coherent acceptance covers fresh runtime, v2 import into ordinary use, incremental/partial resume with request logs, interruption/preservation/backup and installed packaging. Do not duplicate complete suites per layer. Historical test counts and node IDs are not targets; preserve surviving behavior and safety coverage.

Keep lightweight timing and changed-file selection. Unknown impacts expand testing. SQL/contracts are executable inputs even under docs. Report executed, failed and unexecuted checks honestly. No unconditional full acceptance for every main push or approval gates between subsystems.

## Sources and handoff

Start with `docs/schema-hardening/runtime-handoff.md`, packaged `resources/catalog3.sql`, `adapters/sqlite/schema.py`, the relevant normal runtime services and `adapters/import_v2` domain recipes. Historical P1/P2/P3A/P3B/integrated reports and design SQL are snapshots; they do not require reenactment or exact predecessor support.

Update `docs/schema-hardening/implementation-plan.md` and the relevant operating/CI documentation to the implemented state. Keep one concise functional handoff with starting/final SHAs, branch, runnable ordinary commands, environment/check results, import protection, first-sync request behavior and honest gaps. Real-data dry run and cutover require separate authorization.

Never commit real databases, caches, payloads, tokens or private repository content. Stateful synthetic commands use an explicit disposable `--state-dir`.
