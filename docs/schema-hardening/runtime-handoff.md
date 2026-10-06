# Catalog3 runtime handoff

The ordinary runtime uses [packaged catalog3 DDL](../../src/repo_catalog/resources/catalog3.sql) for initialization, discovery, Git/GitHub collection, restart, offline queries/search, finalization, cache/index maintenance and backup/restore. [Runtime identity](../../src/repo_catalog/adapters/sqlite/schema.py) retains `repo-catalog/catalog3` and advances schema version **3 → 4** for the incompatible naming rewrite.

## Schema naming stride

Starting main: `2566522c79c41aad9b410c2a3db6e699e2acdf65`, exactly the expected commit. The workspace initially contained the earlier merged PR #1 commit; the new branch `refactor/catalog3-schema-names` starts from fetched current main. PR #1 is historical, merged work.

The audit covered **74 tables and 148 FK components**. **135 columns** change names; no tables or logical relationships change. Entity PKs use `<entity>_id`; neutral FKs use the identical name, including composite owner components. Role references retain explicit target types, such as `current_change_request_observation_id`, `commit_code_listing_id`, `tree_git_object_id` and `parent_git_object_id`. Resume/coverage scopes, cache locators/active entries, conversion/acquisition sources and catalog/provider IDs have distinct namespaces. See [current data model](../data-model.md) for JOIN examples and scalar/composite-key exceptions.

`oid` remains Git BLOB bytes, scoped by `object_format`; `git_object_id` is the catalog row identifier. Singleton and attempt/ordinal keys remain scalars. Source-format field names and raw provider payload keys remain unchanged. The v2 importer translates old source columns and identity-context keys into current target projections while retaining exact source evidence in the typed archive.

Fresh catalogs use only version 4. Earlier catalog3 development databases/backups are rejected. There is no catalog3 upgrade migration, compatibility view, alias, dual write or alternate old-name query path. The existing one-time offline v2 salvage tool is retained for acquired source evidence.

Current runtime/packaged import/CI contracts select acceptance tests. CI policy explicitly lists historical schema-hardening SQL/JSON/CSV as report inputs; real-world JSON remains evidence/report input. Unknown files still select broader testing. Historical snapshots are unchanged.

## Validation

The naming stride uses disposable synthetic Git repositories, loopback API fixtures and unchanged-format v2 fixtures. Actual environment: Python 3.12.14, SQLite 3.53.1, uv 0.12.19. Focused checks cover schema/owner/sealing rules, Git SHA-1/SHA-256 collection/restart, GitHub pages/history/listing reuse, v2 preservation/finalization, queries, cache, backup/restore and CI classification. A schema comparison confirms identical tables, column types/defaults/PK positions and FK actions after applying the rename map.

Final substantive revision and final acceptance/packaging results are recorded here after execution. Historical real-world evidence below is not a fresh version-4 validation claim.

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
repo-catalog --state-dir /tmp/catalog3-imported search pr --literal 'saved early-page' --document-versions observed
```

## Preservation and restart

The guarded offline worker prohibits source writes, network/process acquisition and unguarded SQLite writes. Exact source/cache fingerprints, typed values, stable mappings, attributable diagnostics and batch checkpoints remain inside the target. Queries work after source/import-workspace paths disappear. Missing content remains distinct from empty bytes; partial optional evidence remains useful with exit 3. Critical identity/owner corruption blocks finalization. Only explicit suitable same-owner saved publication/current assertions are restored; import time and integer ordering never select current facts.

Runtime connections use SQLite locking/transaction snapshots, FK and recursive triggers plus the existing OS writer lock. Shared Git traversal roots retain separate raw origins. Ordered parents and raw paths/refs/names survive. API payload/body dedup preserves A→B→A observations. Completed listings/manifests remain sealed. Resume/replay never advances watermarks as a new remote observation.

Synthetic imported-first-sync logs check conditional detail 304s and zero commit/file requests for eligible unchanged saved listings. Reuse still requires matching service/binding/source, endpoint/API/parser/profile, principal/permissions where known, current authenticated head/base/count and terminal/context proofs. Unknown legacy cursors/watermarks receive targeted refresh. Legacy jobs/leases/reservations never become active, and runtime caches remain isolated from preserved source material.

## Retained evidence and limits

Pre-refactor evidence remains unchanged:

- [Public Git acquisition/recovery PASS](../validation/real-world/2026-10-06-museum-portal-git-04f23c7.md), application `04f23c7082b1b9d0cd96df1062459b7b71049bb0`.
- [Initial bounded PR/API trial](../validation/real-world/2026-10-06-museum-portal-api-bdc6a6e.md), application `bdc6a6eb9044f316cd9ebea9e70dd484b49ff406`; stopped under its original budget.
- [Complete PR/API continuation PASS](../validation/real-world/2026-10-06-museum-portal-api-continuation-64da722.md), application `64da7222c96d5cd31b7f08a35d77552394c64e46`; all 50 PRs, 121 reviews and 79 real threads, with interruption/recovery and backup/restore.
- [Retained-v2 discovery N/A](../validation/real-world/2026-10-06-retained-v2-discovery-bdc6a6e.md); no genuine retained source was found.

These are evidence for the schema-version-3 operational milestone. This naming stride does not repeat museum-portal/API trials, retained-source searches or real-data activation. Historical P1/P2/P3A/P3B/integrated SQL/JSON/CSV/reports remain snapshots, not current contracts or acceptance gates.

Missing originals, unsupported payload shapes and malformed facts retain attributable coverage gaps. Additional providers, distributed synchronization, multi-catalog exchange, LFS/attachment originals, release publication and active-catalog cutover remain outside scope. Prior catalog3 DB compatibility is intentionally unsupported.
