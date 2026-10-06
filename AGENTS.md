# Coding agent guide

This guide applies repository-wide. Coding-agent task specifications and handoffs are written in English; user-facing explanations may be Japanese.

## Current product and working rules

Catalog3 is the sole ordinary runtime for initialization, source discovery, Git and GitHub collection, resumable synchronization, offline queries/search and essential maintenance. One packaged guarded offline v2 salvage importer writes the same format; explicit finalization establishes readiness. See `docs/schema-hardening/runtime-handoff.md` for implemented behavior, validation and limits. Historical reports are evidence, not standing acceptance gates.

This is an unreleased single-developer application. Backward compatibility with old schemas, CLI/API outputs, converter phases and workspaces is unnecessary. Direct main development, a single branch or stacked PRs are allowed. Intermediate checkpoints may be incomplete. Do not discard uncommitted work or rewrite history for tidiness.

The v2 importer is a one-time salvage facility for already-acquired development data, not a public backward-compatibility contract. Keep it only while retained v2 data may still need recovery; it may be simplified or removed once no retained v2 data depends on it.

Use disposable synthetic data unless the current task/session authorizes real sources or a repository/operation scope and budget. Automatically create temporary directories for workspaces, converted catalogs, backups, restores, measurements and disposable copies; do not ask the user to select temporary paths. Public read-only validation is permitted only for an explicitly authorized repository, operation scope and request/time budget. Access to retained local user data, destructive operations, active-catalog switching, release publication, retained-source deletion or remote mutation requires separate explicit authorization. Discover existing state conservatively from configured/default locations and any additional locations the user explicitly names. If a real source is missing or ambiguous, report the exact candidates before mutation. Keep original DB/cache read-only: never move, overwrite, migrate in place or delete them. Preserve source bytes, IDs, raw values, history and attributable diagnostics through the packaged offline v2 salvage importer when that importer is used. No implicit acquisition.

## Architecture

- Dependencies remain `cli -> application -> domain/ports`; adapters own SQLite, Git/HTTP and filesystem operations.
- Authoritative catalog3 DDL belongs in packaged resources, shared by initializer, importer, writer, reader and maintenance. Fresh catalogs do not traverse v2 migrations or historical phase receipts.
- Use normal SQLite locking/transactions for mutable runtime catalogs, FK and recursive triggers on every connection, and the existing OS writer lock. Never use immutable connections against changing catalogs. Offline queries do not migrate, acquire, execute Git or repair indexes.
- Preserve portable CSPRNG-generated `service_instance_uuidv4` namespaces, without URL-based identity merging. Documents use `(change_request_id, kind, provider_change_request_document_id)` directly: do not reintroduce a document-local ID or a version table. Observations reference unique exact-UTF-8 text SHA-256; reject conflicting bodies and use explicit same-document current-observation pointers. See `docs/data-model.md`.
- Enforce same-owner relations, sealed completed listings and explicit readiness. Optional missing content is partial coverage; critical identity corruption blocks finalization. Current pointers need suitable completed same-owner observations and justified ordering.
- Preserve format-scoped OIDs, raw paths/ref/name bytes, ordered parents, separate origins for shared traversal roots, payload/page history and distinct A->B->A observations. Missing content is not empty bytes.
- Commit pages/progress atomically. Resume does not advance watermarks or replay responses as new remote observations. Scope/identity/principal/API/parser/profile/head/base evidence determines imported reuse; unsupported cursors receive targeted refresh and retain history.
- Imported evidence needed for later audit must remain in the catalog. Runtime caches are isolated from preserved source material. Never reactivate historical jobs/leases/reservations.
- Offline importer guards prohibit source writes and acquisition. Keep legacy schema/parser isolated as import support while the salvage importer exists. Do not disable source/network protection to accommodate a toolchain.

## Development and validation

Use one practical working Python/SQLite binding; inspect actual capabilities and report actual versions. There is no promised minimum-version matrix. Do not reintroduce independent SQLite-minimum lanes, Python/SQLite compatibility matrices or historical converter-phase compatibility gates. Retain narrowly justified correctness safeguards.

Run focused tests while editing, then compact end-to-end workflows. Final coherent acceptance covers the current catalog3 runtime and preservation/recovery paths, including incremental/partial resume with request logs, interruption handling, backup/restore and installed packaging. Keep synthetic coverage for the one-time v2 salvage importer while that importer exists. A real retained-v2 trial is required only when a genuine retained source exists and its use is separately authorized. Do not duplicate complete suites per layer. Historical test counts and node IDs are not targets; preserve surviving behavior and safety coverage.

Keep lightweight timing and changed-file selection. Unknown impacts expand testing. Only files explicitly identified as current runtime or CI contracts are executable inputs. Historical schema-hardening SQL/JSON/CSV and design reports are immutable design/evidence snapshots unless a current source-of-truth document explicitly states otherwise. Report executed, failed and unexecuted checks honestly. No unconditional full acceptance for every main push or approval gates between subsystems.

## Sources and handoff

Start with `docs/schema-hardening/runtime-handoff.md`, packaged `resources/catalog3.sql`, `adapters/sqlite/schema.py`, the relevant normal runtime services and `adapters/import_v2` domain recipes while the salvage importer exists. Historical P1/P2/P3A/P3B/integrated reports and design SQL are snapshots; they do not require reenactment, compatibility support or synchronized edits when current runtime code changes.

Update `docs/schema-hardening/implementation-plan.md` and relevant operating/CI documentation only when a milestone, architecture, supported behavior or known limitation materially changes. Keep one concise functional handoff with starting/final SHAs, branch, runnable ordinary commands, environment/check results, import protection, first-sync request behavior and honest gaps. Evidence-only validation runs should normally add their Markdown/JSON evidence and one link from the handoff; do not rewrite multiple planning documents solely to restate the same result.

Never commit real databases, caches, payloads, tokens or private repository content. Stateful synthetic commands use an explicit disposable `--state-dir`.

Every real-world validation attempt, including failures, gets a concise Markdown report and adjacent JSON summary under `docs/validation/real-world/`, linked from the relevant handoff or PR. Use a distinct run identifier and retain previous reports. Bind evidence to the exact application commit, public target/ref/OID, environment, commands, scope, enforced request/time budget, measured requests/time/sizes, query results, backup/restore, diagnostics and explicit PASS/FAIL criteria. Include SHA-256 comparisons of representative normalized fresh/restored queries where useful; distinguish unexecuted scopes. Commit summaries only, never databases, caches, raw authenticated traffic, secrets or private payloads. GitHub Issues track actual defects or unresolved follow-up work, not successful validation evidence.
