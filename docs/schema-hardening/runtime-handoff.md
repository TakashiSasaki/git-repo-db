# Catalog3 runtime handoff

The ordinary runtime uses [packaged catalog3 DDL](../../src/repo_catalog/resources/catalog3.sql) and [runtime identity](../../src/repo_catalog/adapters/sqlite/schema.py): `repo-catalog/catalog3`, **schema version 6**. Earlier catalog3 databases/backups are rejected; there is no v4/v5 migration, compatibility alias or dual runtime path. The packaged v2 salvage importer is retained.

## Identity and observation stride

Starting main: `1ce7fccdb63ab7de74daf6694d2c7187fcddd835`. Working branch: `refactor/portable-document-observations`. [Current data model](../data-model.md) specifies the agreed rules and join examples. The public source was transported through a temporary read-only GitHub Actions bundle/wheel artifact because this editing container cannot resolve external hosts; the temporary workflow is removed from the final tree. No real source was acquired or activated.

- Service namespaces are `service_instance_uuidv4`; new values use CSPRNG UUIDv4 and the DDL validates canonical v4 representation. `service_kind` retains the existing enum. URL equality never merges distinct namespaces. Provider-native values are retained.
- Documents have a composite natural key, not `document_id` or a renamed substitute. Related FKs use the full key. `reviews.review_id`, formerly the synthetic document-ID alias, is removed with that alias.
- `text_bodies.sha256` uniquely identifies exact UTF-8 content, with no normalization. Hash/body disagreement is an integrity failure. `text_body_id` remains catalog-local; observations reference SHA-256 directly.
- `document_versions` is removed. Each real observation retains its body identity and provenance; A->A->B->A remains four observations sharing two bodies. `current_document_observation_id` must reference the same document. Missing current selection is reported, never inferred from maximum ID.
- Normal REST/GraphQL collection, offline query/search, import/finalization and backup/restore use the new schema. PR search indexes each body once and still returns each requested observation. CLI uses `--document-observations current|all`, `--provider-change-request-document-id`, `--document-kind` and `--observation`.

## Provider-resource stride (schema 6)

Resumed from `e51be9e8b8a1af2bdf1b82db0acf11318e5d386d` on the same PR branch. Change-request identity uses `(Repository portable identity, change_request_kind, provider_change_request_number)`. Normalized `provider_node_id` columns and synthetic `review_thread_id` are removed; review threads use `(change_request_id, provider_resource_id)` with same-parent comment FKs. The resource value is not assumed globally unique across a service or all provider types.

GitHub documents require their database identity (`id` / `fullDatabaseId`), without Node-ID fallback or alternate-key matching. Node-only response evidence is retained with partial diagnostics and retryable pagination. Node IDs remain raw provider evidence and are used as opaque review-thread resource handles where required by GraphQL. CLI uses `--provider-change-request-number`, `--change-request-kind` and scoped `--provider-resource-id` for thread selection.

Current completed validation: clean substantive commit `db69fe28dbf279627b9e3631682b1f009e20c362`, **383 ordinary + 2 independent packaging tests passed**, with 385 selected tests executed exactly once. See [schema-6 synthetic evidence](../validation/synthetic/2026-10-07-provider-resource-identity.md) and adjacent JSON for environment, timing, initial failures and unexecuted scopes. The publication wrapper preserves the tested Git objects; evidence-only follow-ups do not constitute a separate runtime test run.

## Prior schema-5 validation

Clean substantive revision: `b6cca875b9a303989bc8947dc56dddb04d7b9ec2`. Current acceptance: **358 passed** (44.97s); isolated installed wheel/sdist-wheel: **2 passed** (3.08s). Planner/collection/profile reconciliation confirms **360 selected and executed once**, no failures/skips/unexecuted files. Ruff lint/format, STRICT/FTS doctor and prose validation passed. See [synthetic evidence](../validation/synthetic/2026-10-06-portable-document-observations.md) and its adjacent JSON. Subsequent evidence-only documentation is not fresh runtime validation.

Work uses Python 3.13.5, native SQLite 3.46.1 and uv 0.10.0 in one practical environment, with delete journaling. Dependencies are installed offline from locked wheel hashes; development imports resolve the working source. The isolated distribution checks install genuine built wheels outside the checkout and do not use that development path.

Focused checks cover natural-key relationships, current-pointer ownership, exact UTF-8/hash conflict handling, UUIDv4/namespace rules, API history/replay/scaling, preserved v2 conversion and imported-first-sync listing reuse. One prior tool-limited acceptance invocation was interrupted and is not counted as successful. The completed run is recorded in the linked evidence.

## Runnable ordinary commands

Global options precede subcommands. Use a new disposable directory and a local synthetic repository.

```bash
repo-catalog --state-dir /tmp/catalog3-fresh init \
  --profile catalog-text-v1 --cache-max-bytes 67108864 --min-free-bytes 0
repo-catalog --state-dir /tmp/catalog3-fresh sources add local-git \
  --name fixture --url file:///path/to/synthetic.git
repo-catalog --state-dir /tmp/catalog3-fresh discover
repo-catalog --state-dir /tmp/catalog3-fresh sync git
repo-catalog --state-dir /tmp/catalog3-fresh repos list
repo-catalog --state-dir /tmp/catalog3-fresh refs list --repo REPOSITORY_ID
repo-catalog --state-dir /tmp/catalog3-fresh commits show --repo REPOSITORY_ID --ref refs/heads/main
repo-catalog --state-dir /tmp/catalog3-fresh search code --literal sentinel
repo-catalog --state-dir /tmp/catalog3-fresh index rebuild --kind all
repo-catalog --state-dir /tmp/catalog3-fresh cache gc
repo-catalog --state-dir /tmp/catalog3-fresh db check --full
repo-catalog --state-dir /tmp/catalog3-fresh db backup --output /tmp/new-catalog3-backup.sqlite3
repo-catalog --state-dir /tmp/catalog3-restored db restore --input /tmp/new-catalog3-backup.sqlite3
```

Keep the backup and adjacent `.manifest.json` together. Git cache contents are excluded. Restore uses a new location/database instance and clears operational state. CLI row projections expose the new identifiers, including `repository_id`, `repository_endpoint_id`, `snapshot_id`, `git_acquisition_id`, `code_observation_id` and `active_cache_entry_id`.

A synthetic fixture builder is checkout-only; installed import uses packaged resources:

```bash
uv run --no-sync python scripts/import_fixture.py --state-dir /tmp/catalog3-v2-fixture --derived
repo-catalog --state-dir /tmp/catalog3-imported import-v2 \
  --source /tmp/catalog3-v2-fixture/catalog.sqlite3 \
  --source-cache /tmp/catalog3-v2-fixture/cache --max-batches 2
repo-catalog --state-dir /tmp/catalog3-imported import-v2 \
  --source /tmp/catalog3-v2-fixture/catalog.sqlite3 \
  --source-cache /tmp/catalog3-v2-fixture/cache
repo-catalog --state-dir /tmp/catalog3-imported db finalize
repo-catalog --state-dir /tmp/catalog3-imported search pr --literal 'saved early-page' --document-observations all
```

## Preservation and restart

The guarded worker still prohibits source writes and acquisition. Original v2 document/version IDs, source body hashes, typed values, payloads and batch evidence remain in the catalog; source layouts are unchanged. Target document mappings contain composite keys, not replacement IDs. Legacy parser version tuples are transient import support only.

A source version without an actual observation contributes text and archived evidence, not a fabricated observation. Finalization translates a saved current-version assertion only to a suitable same-document source observation of that version. The latest unambiguous recorded observation is used; ties, unknown times, missing observations and conflicting current assertions remain unresolved. Current selection never follows integer/import ordering. New observations are not invented by replay/import, and history/jobs/leases are not reactivated.

Normal SQLite transactions, foreign keys, recursive triggers, OS writer locks, completed-listing sealing, raw bytes and ordered Git parents remain enforced. Imported first-sync reuse still requires matching source/binding/principal/API/parser/profile/head/base and terminal-context evidence. Runtime caches remain separate from retained source material. Backup/restore copies local IDs and resets operational state; it is not multi-catalog exchange.

## Retained evidence and limits

Pre-refactor evidence remains unchanged:

- [Public Git acquisition/recovery PASS](../validation/real-world/2026-10-06-museum-portal-git-04f23c7.md), application `04f23c7082b1b9d0cd96df1062459b7b71049bb0`.
- [Initial bounded PR/API trial](../validation/real-world/2026-10-06-museum-portal-api-bdc6a6e.md), application `bdc6a6eb9044f316cd9ebea9e70dd484b49ff406`; stopped under its original budget.
- [Complete PR/API continuation PASS](../validation/real-world/2026-10-06-museum-portal-api-continuation-64da722.md), application `64da7222c96d5cd31b7f08a35d77552394c64e46`; all 50 PRs, 121 reviews and 79 real threads, with interruption/recovery and backup/restore.
- [Retained-v2 discovery N/A](../validation/real-world/2026-10-06-retained-v2-discovery-bdc6a6e.md); no genuine retained source was found.

These are evidence for the schema-version-3 operational milestone. This identity/observation stride does not repeat museum-portal/API trials, retained-source searches or real-data activation. Historical P1/P2/P3A/P3B/integrated SQL/JSON/CSV/reports remain snapshots, not current contracts or acceptance gates.

Missing originals, unsupported payload shapes and malformed facts retain attributable coverage gaps. Additional providers, distributed synchronization, multi-catalog exchange, LFS/attachment originals, release publication and active-catalog cutover remain outside scope. Prior catalog3 DB compatibility is intentionally unsupported.
