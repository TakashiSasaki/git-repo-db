# Catalog3 operational runtime

The ordinary application now uses catalog3 for initialization, registration/discovery, Git and GitHub REST/GraphQL collection, restart, offline queries/search, doctor, index/cache maintenance and backup/restore. The one offline v2 salvage importer writes the same packaged `resources/catalog3.sql` and requires explicit `db finalize` before normal use.

## Real operational validation completed, 2026-10-06

**Ready for schema naming cleanup.** The [complete PR/API continuation](../validation/real-world/2026-10-06-museum-portal-api-continuation-64da722.md) and adjacent JSON record PASS for exact application commit `64da7222c96d5cd31b7f08a35d77552394c64e46`. Both repository-wide syncs for public `TakashiSasaki/museum-portal` completed, covering all 50 PRs, 121 reviews and 79 real review threads. The original temporary state was authenticated against its identity/counts and five durable query hashes, then continued in an exact disposable copy; original DB/cache fingerprints and earlier reports remain unchanged. Discovery and retained-v2 search were not repeated.

The resumed first sync used 408 API sends in 364.75 seconds of command execution; the subsequent sync, including its time-limit interruption/resume, used 357 sends in 303.55 seconds. Added sends: 765; cumulative with the earlier 95: **860 / 1,000**. Second sync returned 50 detail 304s and made zero commit/file-list calls; all 50 PR head/base/state/update tuples were unchanged. Normal authorization, child-history refresh and Git-head validation still required requests. The initial 600-second window stopped safely; the user explicitly authorized more time, and completion/recovery used 220.69 seconds of a new bounded 600-second window. Overall elapsed time including stopped/user-response/preparation intervals was 1,052.88 seconds. One deadline-aborted request is counted; no provider rate-limit/authentication/permission or product failure occurred. A temporary measurement URL filter was corrected to allow verified same-repository numeric-ID pagination; product code was unchanged.

Full DB checks passed before/after backup/restore, and seven normalized query/coverage digest pairs matched. PR/history/documents/events/search and thread queries were complete. Broad history code search returned a 1,000-row page and honestly reported 270 unsaved historical bodies plus five policy exclusions, as documented for `catalog-text-v1`; no required text at current acquired roots was missing. Final/backup/restored DB: 101,138,432 bytes; final cache: 1,961,272 bytes; restored cache: zero. Backup excludes the Git cache. No product code or naming cleanup was performed, and no broad application suite was rerun for this evidence-only change; report/JSON checks and whitespace checks passed. The continuation is committed locally without modifying remote GitHub state. Schema naming cleanup is the next stride; this is not a release-candidate declaration.

Verified local commits `04f23c7082b1b9d0cd96df1062459b7b71049bb0` and `bdc6a6eb9044f316cd9ebea9e70dd484b49ff406`, their ancestry and the prior Git report, preserving the checkout. Published both to `design/schema-v2-hardening` / [PR #1](https://github.com/TakashiSasaki/git-repo-db/pull/1); the earlier Git-only PASS was not repeated.

The [first PR/API trial](../validation/real-world/2026-10-06-museum-portal-api-bdc6a6e.md) at exact installed application commit `bdc6a6eb9044f316cd9ebea9e70dd484b49ff406` is **FAIL under the original budget**. The existing credential and read-only REST/GraphQL access worked. `museum-portal` was the smallest useful candidate with 50 PRs. Reconnaissance/discovery used nine calls; initial and subsequent normal syncs each used 43 calls and were deliberately cancelled before exceeding their admission caps. Total 95 API sends, 35 Git HTTP requests; sync durations 35.73 / 26.27 seconds. Already completed #1–4 commit/file listings were reused; five detail validations returned 304. Useful partial queries, structural checks and backup/restore succeeded; all five normalized query/coverage digest pairs matched. No product defect was inferred from the intentional interruption, and no product code or schema changed.

[Retained real v2 discovery](../validation/real-world/2026-10-06-retained-v2-discovery-bdc6a6e.md) is **N/A**: default state is absent, and all six DBs in known application/catalog trial locations are identified catalog3 artifacts. Read-only classification left their digests unchanged; existing caches were untouched. No synthetic or newly collected source was represented as real v2.

The original 100-request attempt remains a distinct unchanged report. The subsequently authorized complete continuation above supersedes its budget blocker. Retained-real-v2 remains N/A, and the earlier Git-only PASS was reused. These close the requested operational validation scopes without synthesizing legacy data or changing the schema.

## Authorized public Git trial, 2026-10-06

[Museum-portal Git acquisition and recovery report](../validation/real-world/2026-10-06-museum-portal-git-04f23c7.md) and its adjacent JSON record a PASS at exact application commit `04f23c7082b1b9d0cd96df1062459b7b71049bb0`. The installed CLI collected one public repository, re-synced unchanged heads/tags, checked independent commit/parent/blob evidence, queried offline, and backed up/restored to a fresh cache-free location. Six normalized query digests matched. Workload: 10.49 seconds; three admitted Git remote operations, seven Git HTTP requests and zero GitHub API calls. All working state and measurements used automatically created temporary storage; only summaries are retained in Git.

This supports personal use of the exercised public Git workflow. No application defect appeared. The later bounded API attempt and retained-v2 discovery are recorded above; active-catalog cutover and release publication remain unexecuted. Previous synthetic and hosted results below retain their original scope and dates.

## Practical preparation, 2026-10-06

Selected current feature head `07a100c13bafa812df3183854d237a9086860d55` without resetting history; preparation uses local branch `operational-trial-preparation`. Runtime code remains the validated implementation below. A wheel built from this head was installed with locked runtime dependencies into a separate venv and exercised outside the checkout. Environment: Python 3.12.14, SQLite 3.53.1, uv 0.12.19.

One disposable synthetic trial passed: doctor without state creation, fresh init/empty repository query, local Git registration/discovery/sync, repository/ref/commit/tree/file queries, literal code search, full DB check, backup, restore into a new location and restored search. CLI workflow elapsed time was 1.55 seconds; largest child peak RSS was 20,736 KiB. Wheel size was 176,590 bytes; collected DB, backup and restored DB were each 1,122,304 bytes. Local detailed output is retained in ignored `artifacts/operational-trial-20261006/smoke-results.json`. These small-fixture measurements do not estimate real import cost.

No runtime defect appeared. Guidance now includes wheel installation, retaining the backup/manifest pair, consistent-copy preparation without deleting source sidecars, and the absence of an aggregate sync budget in query timeouts. Existing prose validation and `git diff --check` passed. No full suite, v2 import, PR-history trial or authenticated GitHub acquisition was rerun; prior hosted acceptance remains historical evidence. Application GitHub requests: zero; no live budget was authorized.

The installed basic workflow is usable with disposable data. Personal-data acceptance and release-candidate closure remain pending the authorized practical trials. Next action: supply a preserved consistent v2 DB/cache (or explicitly absent cache), a separate destination and offline-import permission. Then perform one import/finalize/query/preservation/backup trial. Live synchronization additionally needs one approved repository/operation scope, normal secret configuration and an enforceable request/time budget. Publication, active-catalog switching and source deletion remain separately instructed actions.

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

The historical synthetic acceptance above did not use real credentials or retained user data. Later separately authorized public Git/API trials are recorded at the top. No real retained v2 conversion, release or active-catalog cutover occurred.
