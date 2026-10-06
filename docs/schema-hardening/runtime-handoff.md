# Catalog3 operational runtime

The ordinary application now uses catalog3 for initialization, registration/discovery, Git and GitHub REST/GraphQL collection, restart, offline queries/search, doctor, index/cache maintenance and backup/restore. The one offline v2 salvage importer writes the same packaged `resources/catalog3.sql` and requires explicit `db finalize` before normal use.

## Revisions and checks

Original checkout: `9a4110185d7e7abffc291f9cfd118ca71587f998`. Latest integrated implementation reused by fast-forward: PR #1 head `3af3df84372354e972772b5c9600dfeeae0f0e15`. Policy checkpoint: `2060110517f35fb7e4981b30fd1789077f520d38`. Final validated implementation: `edce04b646e7b5006f1b15048cab765e3c416bfa` on `design/schema-v2-hardening`, [PR #1](https://github.com/TakashiSasaki/git-repo-db/pull/1). The subsequent handoff-only commit changes these two Markdown reports; it does not change runtime code or claim a fresh full execution.

Hosted [full acceptance run 37412761695](https://github.com/TakashiSasaki/git-repo-db/actions/runs/37412761695), testing merge `eabd80f4edb271e8d9be5df86edafdeb9320b94d`, passed: 330 ordinary tests in 75.87 seconds, plus two isolated installed wheel/sdist tests in 3.74 seconds. Reconciliation recorded 332 executed checks across 40 files, with no unexecuted or excluded ordinary files. Lint, format, SQLite capability/doctor and report checks passed. The Ubuntu 24.04 runner used Python 3.12.14, native SQLite 3.45.1 and uv 0.12.19. Every remaining ordinary test file belongs to current acceptance; opt-in live acquisition is outside this manifest. These are observed results, not future count targets.

Local development used Python 3.12.14, SQLite 3.53.1 and uv 0.12.19. Focused synthetic checks covered fresh/imported collection, resume, preservation and maintenance; no identical complete local suite immediately preceded hosted acceptance. The default rollback journal works on the hosted binding. Optional WAL retains its verified-fix safeguard: unsupported bindings reject writable WAL without modifying the DB; supported bindings preserve active reader snapshots. No minimum-version lane or binding replacement is required.

PR synchronization selects affected checks from the previous feature head to the actual merge tree, conservatively expanding for unknown history or base code changes. The final Markdown-only follow-up checks prose and reports runtime files unexecuted, with `full_acceptance=false`. The linked completed full run above remains the acceptance evidence for the validated implementation; no remote artifact result is reused as a newly executed check.

## Runnable ordinary commands

Global options precede subcommands; use new disposable directories and a local synthetic repository.

```bash
repo-catalog --state-dir /tmp/catalog3-fresh init \
  --profile catalog-text-v1 --cache-max-bytes 67108864 --min-free-bytes 0
repo-catalog --state-dir /tmp/catalog3-fresh sources add local-git \
  --name fixture --url file:///path/to/synthetic.git
repo-catalog --state-dir /tmp/catalog3-fresh discover
repo-catalog --state-dir /tmp/catalog3-fresh sync git
repo-catalog --state-dir /tmp/catalog3-fresh repos list
repo-catalog --state-dir /tmp/catalog3-fresh refs list --repo REPO_ID
repo-catalog --state-dir /tmp/catalog3-fresh commits show --repo REPO_ID --ref refs/heads/main
repo-catalog --state-dir /tmp/catalog3-fresh tree list --repo REPO_ID --ref refs/heads/main
repo-catalog --state-dir /tmp/catalog3-fresh search code --literal sentinel
repo-catalog --state-dir /tmp/catalog3-fresh search commits --literal synthetic
repo-catalog --state-dir /tmp/catalog3-fresh search pr --literal sentinel --document-versions observed
repo-catalog --state-dir /tmp/catalog3-fresh index rebuild --kind all
repo-catalog --state-dir /tmp/catalog3-fresh cache gc
repo-catalog --state-dir /tmp/catalog3-fresh db check --full
repo-catalog --state-dir /tmp/catalog3-fresh db backup --output /tmp/new-catalog3-backup.sqlite3
repo-catalog --state-dir /tmp/catalog3-restored db restore --input /tmp/new-catalog3-backup.sqlite3
```

GitHub source registration plus explicit `sync pr`/`sync all` retain reviews, threads/comments, events, payload/page history, commit/file listings and PR Git roots. After acquiring a synthetic GitHub PR, `repo-catalog --state-dir /tmp/catalog3-fresh pr show --repo REPO_ID --number 41` shows its documents. A previously interrupted runtime job can be continued with `repo-catalog --state-dir /tmp/catalog3-fresh jobs resume JOB_ID`. Production acquisition is explicit; acceptance uses dummy credentials and loopback APIs.

A checkout fixture builder supplies operational v2 FTS/statistics input. Installed applications need neither it nor checkout documents:

```bash
uv run --no-sync python scripts/import_fixture.py --state-dir /tmp/catalog3-v2-fixture --derived
repo-catalog --state-dir /tmp/catalog3-imported import-v2 \
  --source /tmp/catalog3-v2-fixture/catalog.sqlite3 \
  --source-cache /tmp/catalog3-v2-fixture/cache --max-batches 2
repo-catalog --state-dir /tmp/catalog3-imported import-v2 \
  --source /tmp/catalog3-v2-fixture/catalog.sqlite3 \
  --source-cache /tmp/catalog3-v2-fixture/cache
repo-catalog --state-dir /tmp/catalog3-imported db finalize
repo-catalog --state-dir /tmp/catalog3-imported repos list
repo-catalog --state-dir /tmp/catalog3-imported search pr --literal 'saved early-page' --document-versions observed
# Configure a supported current/synthetic source before an explicit first sync:
repo-catalog --state-dir /tmp/catalog3-imported sync pr --repo REPO_ID
```

Resume uses the same source evidence and batch size. Partial coverage returns useful data with exit 3. Finalization validates import completion, structural/owner evidence and critical identity diagnostics. It restores only explicit suitable same-owner saved publication/current assertions. Missing optional content is partial; ambiguous selections remain unset with retained reasons. Import time, integer IDs and guessed observation order never select current facts.

## Preservation, restart and first sync

A dedicated guarded worker seals stopped sidecar-free input, archives exact SQLite storage values, then commits domain facts, stable ID maps, diagnostics and checkpoints atomically. It denies source writes, native network/process acquisition and unguarded SQLite writes. Source/cache fingerprints and typed evidence remain inside the target; queries work after source/import-workspace paths disappear. Legacy jobs have no active attempt, lease or reservation. Writable runtime caches are isolated from source-readonly evidence. Backup uses SQLite's backup API; restore uses a new location and clears operational state.

Multiple refs share traversal roots with separate raw origins. Format-scoped OIDs, raw path/name/ref bytes and ordered parents survive. Missing bytes remain distinct from empty bytes; fresh hash verification requires actual bytes. Payload/body dedup retains A→B→A versions and separate observations. Partial listings retain earlier pages on restart; completed listings are sealed. Watermarks advance only at committed successful observation boundaries, never saved-response replay or mere resume.

Imported-first-sync request logs demonstrate conditional 304 validation of a known ETag, zero commit/file requests for an unchanged eligible saved listing, and targeted acquisition for new/changed/incomplete contexts. Reuse requires current authenticated PR/head/base/count evidence, matching service/binding/source/API/endpoint and principal/permissions where known, plus importer terminal/context proofs. Unknown legacy cursors/watermarks remain nonreusable. Child histories without adequate scope evidence receive a scoped refresh; replay does not create a new remote observation.

Ordinary reads use SQLite transaction snapshots, never immutable connections to mutable DBs. They do not migrate, fetch, run Git, repair indexes or audit the complete source archive. FTS/statistics are derived and do not change catalog identity.

## Retired code and remaining limits

Retired: normal v2 store/migration runner; phase/predecessor conversion protocols; historical phase/export/design-only tests/generators; minimum SQLite binding setup; historical node-ID floor and remote CI artifact reuse. Legacy schema/parser/recipes remain only in packaged `adapters/import_v2` and `resources/import_v2`. Historical design SQL/documents are snapshots, not runtime inputs.

Missing original bytes, unsupported legacy payload shapes and malformed facts retain attributable archive/coverage gaps. Unsupported intermediate workspaces are reimported from preserved v2 input. Additional provider adapters, distributed synchronization, LFS/attachment originals, every historical payload shape and real-data activation are outside this stride.

No actual user DB/cache was opened or converted, no live acquisition used real credentials, and no release or active-catalog cutover occurred. Real-data dry run, capacity/request budgets, deployment and cutover remain separately authorized work.
