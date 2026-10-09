# Coding agent guide

This guide applies repository-wide. Coding-agent task specifications and handoffs are written in English; user-facing explanations may be Japanese.

## Product and authorization

Catalog3 schema 16 is the sole runtime for fresh initialization, source discovery, Git/GitHub acquisition, scoped current state and retained immutable parsing histories, offline queries/search, portable repository exchange and maintenance. The application is unreleased and has one developer. No old database, internal API, CLI or migration compatibility is required. The v2 salvage importer and its workspace have been retired under the October 2026 integration task. Historical reports are evidence, not acceptance gates.

Preserve existing Git history and uncommitted work. Commits and stacked PRs are permitted when authorized by the active task. Never merge or release without authorization. Use disposable synthetic data; never commit real databases, caches, raw authenticated traffic, credentials or private repository content. Stateful synthetic commands require an explicit disposable `--state-dir`. No implicit acquisition, live-source testing or retained-data mutation.

## Current-state and transport contracts

Ordinary Issues and their comments share one physical current-state table. Reviews and review comments share a second current-state table. Keep every distinct resource at its latest accepted state; ordinary Issue retention does not apply to PR conversation comments. Issue identity is service plus provider Issue ID, independent of current repository membership/number. Review logical identity remains change request plus kind plus provider document ID. Provider clocks are endpoint-specific evidence, not total-order clocks; incomparable conflicting updates remain visible and cannot produce an undisputed current winner.

Each current row's `field_evidence_json` attributes only retained current values and metadata paths. Omitted fields retain their original clock/capture/profile; an older complete response may fill unknown fields without replacing newer known values. Keep genuine equal-clock contradictions unresolved. Current Issue/comment membership is separate from the original acquisition snapshot: transfer changes repository/binding/number while retaining captured endpoint, Source and times. Detached captured identifiers may survive exchange without importing the old repository/Source registration; validate existing captured relationships when present. `last_checked_at_us` is receiver-local and advances only for accepted authoritative live acquisition with the pre-request revision/scope fence, never from sender checks or replay.

The transport boundary and recording adapters own supplementary message recording and archive reading. Recording is optional for current-state resources. Domain bodies, typed owners, parser/profile attribution and collection-completeness evidence remain durable without supplementary archive access. PR/Git immutable inputs and independent thread contracts retain their required evidence. Never seal a mutable row as an immutable parser output. Preserve minimal stable code/review-target references rather than retaining normalized review edit histories.

Recorder callback and warning-output failures remain nonfatal to valid acquisition. Sanitize recorder codes through the bounded allowlist and retain only the latest 100 transport diagnostics; cancellation, transport, parser and catalog failures retain their ordinary behavior.

CAS-41 is selected: backup manifests require the verified copied database's active physical `payload_quarantine` count, strictly checked before restore diagnosis. D2 is retired/not applicable; fabricated identity remains prohibited. LFS collection preserves Git pointer bytes; attachments preserve source text/URLs. Body acquisition, automatic external URL fetching, transport archive retention/deletion, broad deletion propagation and CAS-76/CAS-77 remain deferred.

## Architecture and immutable contracts

- Dependencies remain `cli -> application -> domain/ports`; adapters own SQLite, Git/HTTP and filesystem operations.
- Packaged production DDL is composed by `adapters/sqlite/schema.py`. Initializer, writers, readers, exchange and maintenance use the same complete DDL and fingerprint.
- Enable foreign keys and recursive triggers on every connection. Use ordinary SQLite snapshot/transaction semantics and the OS `locks/writer.lock`; never immutable connections against a mutable catalog.
- Service, repository and Source registration UUIDv4 are portable identity. Local Source IDs are separate. URLs/names never merge identity; explicit equivalence assertions do not rewrite facts or coverage.
- Persist signed int64 Unix epoch microseconds with `_us` suffixes. Null is unknown; zero and negative values are valid.
- Preserve coverage v2: exactly five claim columns and explicit ownership. Latest observation time determines the set of candidate states, including unknown; no fabricated remote claims or completion.
- Documents use `(change_request_id, kind, provider_change_request_document_id)`. Exact UTF-8 text SHA-256 identifies text bodies. No document surrogate/version table or mutable parser metadata in shared identity rows.
- For retained immutable interpretations, retrieval UUIDs and parsed-result UUIDs are distinct. Results have one repository or Source owner, typed owned inputs, direct generated-fact foreign keys and sealed immutable input/output membership. Current Issue/review resources use the scoped attribution contracts above.
- Parser definitions include implementation, settings, output schema and all supported capabilities. Passed verification covers the entire definition. Specific verification evidence, invalidation and receiver-local trust remain distinct. No version-label-only identity or implicit profile upgrade.
- Retained fact selection and parser/profile selection derive from immutable predecessor DAGs. Missing dependencies and forks remain unresolved, independent of timestamps, UUID ordering or receipt order. A conflicted child scope cannot inherit its parent selection. Mutable resource admission follows proven provider ordering or serialized live context, with incomparable candidates staged as conflict.
- Physical bytes are keyed by SHA-256 BLOB32; logical payloads by `(representation,sha256)`. Hash admission and exact-byte comparison are mandatory. Corruption is diagnosed durably, quarantined locally and repaired only explicitly and atomically.
- Exchange is one repository with required owners, acquisition context and bytes. Exclude all Source-wide inventory evidence, receiver-local trust/quarantine and operational validator caches. Preserve unknown dependencies and conflicts durably without blocking independent valid records.
- Backup verifies source and copied bytes and records active physical quarantine count; restore checks the count before diagnosis and uses a fresh retained stage and atomic no-overwrite publication. Known quarantined bytes are retained with their diagnostics.
- Job plans fix Source registrations and non-secret acquisition settings at creation. Resume restores the plan and resolves credential references at execution. CAS-76/CAS-77 remain deferred.

## Verification and evidence

Use one practical Python/SQLite environment and report actual versions. Run focused tests during integration, then the complete ordinary suite, fresh DDL/FK/integrity checks, lint/format and isolated wheel/sdist installs. Test counts are evidence rather than targets. Retired migration-only cases are documented separately from current-contract replacements. Preserve meaningful behavioral tests and disclose failures, skips and unexecuted checks separately.

The built-in parser verification artifact binds exact implementation hashes to capability test evidence. Regenerate it only from successful relevant tests; final acceptance runs without test bootstrap overrides. Hosted acceptance must correspond to the submitted final HEAD.

[Current boundaries](docs/current-state-boundaries.md) and [schema 16 inventory](docs/current-state-boundaries-inventory.json) describe the active follow-up. See `docs/model-integration-audit.md`, `docs/model-integration-status.md` and `docs/model-integration-handoff.md` for the integration contract, reproductions, decision mapping and runnable workflows. [Current closure](docs/current-state-schema-closure.md), [column liveness](docs/current-state-schema-liveness.md) and [complete schema inventory](docs/current-state-schema-inventory.md) describe the schema 15 follow-up. Historical schema-hardening SQL/reports are snapshots, not production DDL or compatibility requirements. Update current documentation when architecture or supported behavior materially changes; do not rewrite historical evidence to match the present implementation.
