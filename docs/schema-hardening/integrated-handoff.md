# Integrated stored-data conversion and read-only target queries

This milestone converts stored Git and GitHub PR facts into normal catalog3
tables and makes them inspectable offline. Only disposable synthetic input was
used. The ordinary application still uses v2; the independent target remains
`building`, publication/current pointers remain unset, and activation is forbidden.

Work continues on `design/schema-v2-hardening`, PR [#1](https://github.com/TakashiSasaki/git-repo-db/pull/1).
The inspected starting feature was `94b838d685a075ec4bc5117ef4a09448f9a71945`,
base `9a4110185d7e7abffc291f9cfd118ca71587f998`. Historical P3B acceptance is in
[p3b-handoff.md](p3b-handoff.md); it is not evidence for this implementation.

## Runnable synthetic flow

Use Linux/local storage, Python 3.12+ and audited SQLite >=3.46.1 for the guarded worker.
Run from the repository after `uv sync --locked --group dev`. These paths must
be new disposable directories. Dependencies/repository preparation is outside
the converter; conversion workers deny network, child processes and source writes.

```bash
uv run --no-sync python scripts/integrated_demo.py \
  --state-dir artifacts/integrated-source --derived
uv run --no-sync python scripts/offline_convert.py seal \
  --work-dir artifacts/integrated-target \
  --source artifacts/integrated-source/catalog.sqlite3 \
  --source-cache artifacts/integrated-source/cache
uv run --no-sync python scripts/offline_convert.py integrated \
  --work-dir artifacts/integrated-target --batch-size 50 --max-batches 2
uv run --no-sync python scripts/offline_convert.py integrated \
  --work-dir artifacts/integrated-target --batch-size 50
uv run --no-sync python scripts/offline_convert.py verify-stored \
  --work-dir artifacts/integrated-target
```

`integrated` establishes the necessary current archive/handoff/identity owners
before stored-data conversion. `--max-batches` bounds the integrated domain stage;
its committed checkpoints resume with the same batch size and exact fingerprints.
For an already complete supported P3B target, use `stored --work-dir WORK` followed
by `verify-stored --work-dir WORK`. The authentic reviewed P3B predecessor is
accepted through a bounded source/output verifier, never by editing old receipts.

The fixture repository and merge commit are deterministic:

```bash
uv run --no-sync repo-catalog --format json target \
  --database artifacts/integrated-target/target.sqlite3 --allow-building repos
uv run --no-sync repo-catalog --format json target \
  --database artifacts/integrated-target/target.sqlite3 --allow-building commit \
  --repo 00000000-0000-4000-8000-000000000106 \
  --commit sha1:b784c338a1dfe57fc97ccacb44c55482b48bdb3b
uv run --no-sync repo-catalog --format json target \
  --database artifacts/integrated-target/target.sqlite3 --allow-building file \
  --repo 00000000-0000-4000-8000-000000000106 \
  --commit sha1:b784c338a1dfe57fc97ccacb44c55482b48bdb3b --path src/app.py
uv run --no-sync repo-catalog --format json target \
  --database artifacts/integrated-target/target.sqlite3 --allow-building pr \
  --repo 00000000-0000-4000-8000-000000000106 --number 7 --limit 1000
uv run --no-sync repo-catalog --format json target \
  --database artifacts/integrated-target/target.sqlite3 --allow-building search \
  --repo 00000000-0000-4000-8000-000000000106 --kind code --literal 'searchable sentinel'
uv run --no-sync repo-catalog --format json target \
  --database artifacts/integrated-target/target.sqlite3 --allow-building search \
  --repo 00000000-0000-4000-8000-000000000106 --kind commits --literal merge
uv run --no-sync repo-catalog --format json target \
  --database artifacts/integrated-target/target.sqlite3 --allow-building search \
  --repo 00000000-0000-4000-8000-000000000106 --kind pr --literal 'saved early-page'
```

Building/missing-content/partial-listing reads return a partial envelope and exit
code 3, with useful data and coverage reasons. This is expected for this fixture.
Use `tree` for raw path fields, `file --path-b64` for non-UTF8 paths, and `file
--path lost.txt` to see unavailable original content without fabricated empty text.
PR output contains separate record kinds for identity, observations, documents,
versions, reviews, threads, events and code listings. Pagination uses `next_offset`.
Queries verify target identity/schema, use a sidecar-free immutable read, detect
file changes, and never initialize state, migrate, fetch, run Git or repair indexes.
Immutable reads require SQLite >=3.37.0 for STRICT schema parsing and checked
read capabilities; actual SQLite 3.45.1 query tests pass. This does not change
the audited SQLite >=3.46.1 requirement for conversion, writing or recovery.

## Converted data and source-table dispositions

The authoritative recipe order, write ownership, target keys and disposition for
all 53 legacy core tables live in `conversion-contract.json:p3_integrated`.
Invalid/unsupported records in a supported table keep exact archive values and
attributed diagnostics; archival fallback is not claimed as working normalization.

| Source family | Implemented normalized result |
|---|---|
| P3B identity + inventory_runs | Services/sources/repositories/bindings/endpoints/names/membership and inventory observations; original IDs, nullable values and times. |
| collection_runs, git_objects, commits, commit_parents, tree_entries, tag_objects | Git acquisitions, format-scoped objects, exact raw commit/tag/name bytes and ordered edges. Shared OIDs do not merge repository identities. |
| contents, content_digests, blob_content_map, repository_object_sources | Available exact text, missing-content metadata, original digest evidence/maps and same-repository acquisition provenance. |
| snapshots, ref_observations, acquisition_roots, root_manifests, root_manifest_entries | Snapshots/refs, one traversal root with all separate ref/PR origins, raw paths/modes and checked stored manifests. |
| api_responses, collections, collection_pages, collection_memberships | Payload bytes, scoped collections, page occurrences/membership, original assertions/cursors, safe nonreusable legacy resume evidence. |
| pull_requests, pr_observations, pr_documents, document_versions, resource_observations | Binding-scoped PR identity/history, exact bodies, distinct versions and observations; source and saved-page A→B→A. |
| pr_reviews, review_threads, review_comments, pr_events | Normalized review/thread/comment/event identity, relationships and stored payloads. |
| pr_code_observations, pr_commits, pr_file_changes, pr_git_links | Independent head/base listing contexts, preserved early pages/items, partial/sealed progress and exact Git root links where supported. |
| jobs, sync_checkpoints | Minimum job/attempt context needed by saved collections, known pending/validator links, unresolved scope evidence. No online writer is activated. |

`search_documents` stays archived; search scans preserved original code/commit/PR
text. `catalog_meta` and `schema_migrations` stay archived with authenticated source
identity. `cache_entries`, `cache_leases`, `content_locations`, `coverage_components`,
`index_generations`, `index_membership`, `preservation_obligations` and
`space_reservations` are explicitly deferred operational state in the archive;
source/cache evidence remains sealed. They do not become active target cache/index
state or fabricated effective coverage claims.

## Verification and restart boundaries

The new `p3-integrated/1` receipt binds the complete immutable P3B parent, source,
target identity, converter/contract hashes and explicit domain write set. Parent
archive/receipt/identity bytes are frozen. Compact checkpoints reference keys and
row hashes instead of duplicating raw payloads. Rows, maps, diagnostics, decisions
and checkpoint commit atomically. Freshly demonstrated Git verification is tied
to the conversion run and source-derived output proof, separately from archived
legacy flags. Original `roots_manifest` array bytes remain exact; generated origin
ordinals describe deterministic source-key reconstruction, not a lost capture time.

A locked integrated invocation performs one deep authenticated entry/resume audit,
validates new batches, then one streamed source-to-target comparison after new committed batches and a
parent immutability hash at exit. Unchanged complete checkpoints reuse the entry
comparison instead of reconstructing the same output twice. Recovery or native-open changes invalidate entry reuse.
`verify-stored` retains a deliberate deep read-only audit. Its ownership ledger
uses SQLite keys/hashes rather than retaining complete domain payloads. Source
batches are limited by row count and an 8 MiB typed-record byte budget; a larger
single record remains preserved in an isolated batch. Referenced-page replay
uses one source record per batch and a 32 MiB page/JSON decoding limit, matching
the current acquisition page limit. Replay materializes bounded JSON documents
and derived operations for one source record at a time; these byte limits are
not a total-process RSS bound.
Oversized replay keeps exact stored payloads and direct normalized facts with
an attributed partial diagnostic. Metadata still scales with committed output count.

Measured resumed P3B deep archive passes and identity reconstruction passes each
fell from 4 to 2 per invocation. Its final deep audit remains. Integrated tests
instrument the actual parent verifier to require one invocation-level entry call,
and a 200-document synthetic timing/proof-size check guards against obvious
repeated scans or payload-manifest copies. These are synthetic measurements, not
real-data performance claims. The existing `ci_profile.py` measured a 200-document
full synthetic pipeline at 17.409 seconds locally (Python 3.12.14, SQLite 3.53.1);
this includes archive and identity preparation, not just the new domain writer.

Focused acceptance includes operational FTS/ANALYZE input, meaningful Git/PR queries
and all three searches, exact archive/edge/path/ID/order comparisons, malformed
facts with attributed diagnostics, stable mappings, saved pagination and A→B→A,
actual pre/post-COMMIT process termination with hot-journal recovery, source/cache
immutability/network denial and interrupted upstream phase recovery. The existing
CI dependency planner registers new conversion tests in native/minimum-p2 and
query tests in schema; minimum-SQLite, offline packaging and the final fail-safe
gate remain required. Final fresh/reused CI status is recorded in PR checks and
the task report, not inferred from historical runs.

## Precise limits and remaining work

- Missing raw Git originals remain unavailable; cache Git execution/retrieval is
  not introduced. Verification requires reconstructable exact bytes. Manifest
  traversal deeper than 256 directories stays explicitly partial.
- Saved replay handles supported REST/GraphQL/document/listing gaps; overwritten
  or absent historical payloads cannot be recreated. Unknown payload shapes and
  ambiguous PR-role/checkpoint scopes retain diagnostics/archive evidence.
  Reanalysis above the 32 MiB decoding budget is deferred while original payloads
  and supported direct normalized facts remain preserved.
- Legacy principals/parser/profile scopes, opaque GraphQL cursors and unproven
  watermarks do not gain reusable first-sync status. Replay never advances a
  watermark or creates a new observation time.
- Neither normalized completion nor diagnostic queries publish current pointers
  or validate the target for activation. New online runtime/first-sync gates,
  additional scoped reconstruction, real-data dry run and production cutover
  remain later work. No real user DB/cache was opened or converted, no default
  catalog was changed, and no PR merge/main commit is part of this milestone.
