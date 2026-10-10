# Coding agent guide

This guide applies repository-wide. Task specifications and agent handoffs are written in English; user-facing explanations may be Japanese.

## Product and authorization

Catalog3 Schema 20 is the active fresh format. It implements the owner-approved [Publication-independent reconstruction](docs/phase2/publication-free-design.md), [decision](docs/phase2/no-independent-publication-adr.md) and [implementation instruction](docs/phase2/publication-free-implementation-prompt.md). See the [implementation handoff](docs/phase2/publication-free-implementation.md) and its exact-revision review/acceptance receipts. Implementation does not imply review-complete acceptance. Schema 19 and earlier reports remain preserved historical evidence.

The project is unreleased and has one developer. No old database, internal API, CLI or migration compatibility is required. Preserve Git history and others' uncommitted work. Active task authorization permits an integrated feature branch, ordinary prerequisite merges into that branch, commits, push and PR submission. Do not merge PRs into main, release, deploy, tag, mutate retained user catalogs or run authenticated live collection. Synthetic stateful commands require an explicit disposable `--state-dir`. Never commit real catalogs, credentials, private content or raw authenticated traffic.

## Decision authority

Apply explicit current owner decisions first, then accepted ADRs and scoped supersessions, then unsuperseded production contracts, then historical evidence. The current owner accepted Q01-B, Q02-B, Q03-B and **NO_INDEPENDENT_PUBLICATION**. Further option selection is paused. Do not reopen the questionnaire or adopt unchosen cache, collection, checkpoint, Exchange trust, retention/deletion or Git interpretation policies.

Distinguish accepted design, implemented behavior, verified behavior and unresolved boundaries. Never claim full completion from historical receipts or passing focused tests. No generic result/batch/bundle/member-seal owner or eligibility layer may recreate Publication under another name. Local revision, per-object atomicity, domain scope completeness and physical installation readiness have independent responsibilities.

## Architecture and domain invariants

- Dependencies remain `cli -> application -> domain/ports`; adapters own SQLite, Git/HTTP and filesystem operations.
- `adapters/sqlite/schema.py` composes the sole packaged production DDL, including generated JSON guards. Initializer, writers, readers, Exchange, maintenance and installed distributions use its exact fingerprint. Fresh format only; no compatibility shim.
- Enable foreign keys and recursive triggers on every connection. Use SQLite snapshots/savepoints and OS `locks/writer.lock`. Do not use immutable connections against mutable catalogs or hold a write transaction over network work. Roll back intended units on body/constraint/COMMIT failure.
- Service, repository and Source-registration UUIDv4 are portable identities; local Source IDs are distinct. Names/URLs do not merge identities. Explicit equivalence/cancellation assertions do not rewrite facts or coverage.
- Absolute times are signed int64 Unix epoch microseconds with `_us` suffixes. NULL is unknown; zero and negative values are valid. Parsing time, receipt order, UUID order and parser version do not establish domain freshness.
- PR attributes, natural-key title/body/conversation documents, independent threads and known Source roster retain latest accepted state with necessary current-field provenance. No normalized full API edit history. Missing differs from explicit null; inherited values retain their original clock/capture/module/version. Genuine equal/incomparable-clock alternatives remain unresolved.
- Ordinary Issue identity is service/provider ID, independent of current repository membership/number. Review identity is PR/kind/provider document ID. Transfer updates membership while preserving capture. Detached captured IDs may survive Exchange without inventing registrations; verify relationships when present. Receiver-local checks advance only on accepted authoritative live acquisition with pre-request revision/scope fences, never sender checks.
- Documents use `(change_request_id, kind, provider_change_request_document_id)`. Exact UTF-8 SHA-256 identifies domain text. No document surrogate/version table or duplicate PR title/body authority.
- Coverage retains exactly five claim columns and explicit typed ownership. The latest observation's candidate set determines current complete/partial/unknown/conflict; no fallback to older complete. Details are advisory. Valid individual resources remain usable when a larger list fails. Empty terminal and no terminal differ; nested required-child and exact head/base evidence must be truthful.
- Source associations are known positive pairs. Partial inventory R1 cannot delete previously known R2. No new negative membership or deletion policy.
- Retain actual provider events and minimal code head/base/role anchors. Current head B cannot borrow an assessment of A or require the entire old PR as provenance.
- Verify canonical Git format/OID/type/size against physical bytes. Install each object's entire intrinsic structure atomically. Missing targets keep actual OIDs and nullable real-object FKs, never fabricated objects. Retain genuine captures. Reanalysis is Git-only; explicit decoder differences do not create profile authority or silently rank versions.
- No required API transport originals or replay. Normalize accepted partial GraphQL requirements/continuations/targets in memory. Reject opaque provider replicas and hidden original-bearing pending/job JSON. Optional external recording/warning failures remain nonfatal with bounded allowlisted diagnostics.
- Shared CAS admits only explicit real Git representation. Preserve domain text, verified raw Git bytes, shared-digest integrity, quarantine and actual canonical Git repair authorization. CAS-41 checks verified copied-database physical quarantine count before restore diagnosis. Restore validates in a fresh stage and publishes atomically without overwrite. No physical retained-data cleanup or new GC policy.
- Exchange resolves direct typed resources/dependencies from a consistent snapshot. Transport envelope/idempotency records do not own admitted domain validity. Keep real missing/conflicting candidates, handle reverse/repeat/late promotion/onward export, and do not infer broad complete closure from partial arrival or authenticate provider completeness from sender digests alone.
- `local_revision` is the single receiver-local counter for paging/fences; `advance_local_revision` replaces the old mechanical publish call. No counter-history table or sender-revision freshness import.
- Jobs freeze Source registrations and nonsecret settings. Resume resolves credential references at execution. Operational progress/cache deletion cannot invalidate admitted domain facts. Cache loss requires a genuine safe fetch or reuse-unavailable outcome; no fabricated remote observation.

LFS pointer bytes and attachment source text/URLs retain existing meanings; automatic external body fetching, broader deletion propagation, transport recording retention and CAS-76/CAS-77 remain deferred.

## Implementation, review and acceptance

The active implementation prompt requires a separate design pass, coherent cross-module implementation, four fresh independent post-implementation review scopes, executed counterexamples, root-cause correction/regression/re-review and exact final verification. Subagents may work in disjoint modules or isolated review worktrees. Authors are not independent reviewers of their own changes.

Run focused checks during edits, then complete applicable ordinary tests, fresh DDL/FK/integrity and JSON checks, lint/format, isolated installed wheel/sdist tests and controlled selected-scale checks on the final corrected tree. Preserve meaningful behavior tests; retire only obsolete mechanism assertions with exact replacement-node mapping. Disclose failures, skips, exclusions and unexecuted tests. Report real Python/SQLite versions and feature SHA/tree; bind hosted CI to the submitted feature/effective checkout. Removed parser certificates/bootstrap are not acceptance gates.

Use one controlled workload at a time for comparative performance; concurrent test timings are not sequential benchmark evidence. Historical reports remain intact. Update active docs for materially changed behavior. Submit actual PR dependencies and review findings; no main merge without new explicit authorization.
