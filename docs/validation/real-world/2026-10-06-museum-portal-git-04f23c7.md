# Museum-portal: public Git acquisition and offline recovery

**PASS for the recorded Git-only scope.** Run `2026-10-06-museum-portal-git-04f23c7`, 2026-10-06 14:19:08–14:19:19 JST. [JSON summary](2026-10-06-museum-portal-git-04f23c7.json) records all 28 workload commands, four installation commands, timings, sizes, diagnostics and the 23 explicit criteria. Each criterion is FAIL if its stated condition does not hold; excluded scopes are unexecuted.

Application commit: `04f23c7082b1b9d0cd96df1062459b7b71049bb0`; package 0.2.0. Its wheel was built from a detached worktree, installed with locked dependencies into a separate venv, and executed outside the checkout. Environment: Linux x86_64 / glibc 2.41, Python 3.12.14, SQLite 3.53.1 (rollback journal; STRICT/FTS5 trigram available), Git 2.52.0, uv 0.12.19. The wheel SHA-256 and source-tree Git identity are in JSON.

Target: [TakashiSasaki/museum-portal](https://github.com/TakashiSasaki/museum-portal), ref `refs/heads/museum-portal`, commit `sha1:05603220b2dad79cae15c40ddcebcc69d9e62ba7`. Manual public Git registration acquired this repository's heads/tags: three ref/OID pairs. Initial and subsequent syncs completed; those pairs and the selected commit were unchanged. Both snapshot identities are retained in JSON. No account inventory or API/PR acquisition was performed.

## Commands, scope and enforced budget

`${TRIAL}` denotes an automatically created temporary root containing the workspace, venv, catalogs, backup/restore, dependency cache and measurements. Key commands below used `--format json`; exact arguments, returned IDs and repeated fresh/restored queries are in JSON.

```bash
repo-catalog --state-dir "$TRIAL/catalog" sources add git-url --name TakashiSasaki/museum-portal --url https://github.com/TakashiSasaki/museum-portal.git
repo-catalog --state-dir "$TRIAL/catalog" discover --source "$SOURCE"
repo-catalog --state-dir "$TRIAL/catalog" sync git --repo "$REPO"  # once initially, once subsequently
repo-catalog --state-dir "$TRIAL/catalog" file show --repo "$REPO" --ref refs/heads/museum-portal --path README.md
repo-catalog --state-dir "$TRIAL/catalog" search code --repo "$REPO" --ref refs/heads/museum-portal --literal portal --limit 1000
repo-catalog --state-dir "$TRIAL/catalog" db check --full
repo-catalog --state-dir "$TRIAL/catalog" db backup --output "$TRIAL/backup/catalog.sqlite3"
repo-catalog --state-dir "$TRIAL/restored" db restore --input "$TRIAL/backup/catalog.sqlite3"
```

Enforced budget: **600 seconds, at most three Git remote operations, zero GitHub API requests**. A temporary supervisor bounded the whole workload and terminated tracked descendants on expiry. A locked Git admission gate accepted only `ls-remote`/`fetch` for the exact target URL and rejected a fourth operation before launch. The application's Git transfer timeout was set to 120 seconds. Offline queries/maintenance used a DNS/socket guard and executed no Git commands. Query timeout was not treated as an aggregate sync limit.

Measured traffic: **7 Git HTTP requests**—3 advertisement GETs and 4 upload-pack POSTs. Initial `ls-remote`: 2; initial fetch: 3; unchanged fetch: 2. Three proxy CONNECT handshakes were counted separately. The per-HTTP count is a measurement; the enforced request cap was three Git remote operations. A temporary stderr observer counted outbound request lines and discarded raw headers/bodies in memory. GitHub API calls: 0. Earlier connector metadata reconnaissance is outside this application trial.

## Observed PASS criteria

| Condition | Result |
|---|---|
| Exact installed package; doctor creates no state; discovery registers exactly the target | PASS |
| Both syncs complete; selected commit and all ref/OID pairs stay unchanged | PASS |
| Independent Git reads match the stored tree OID, two-parent order and README bytes | PASS |
| Offline repository/ref/commit/tree/file/content queries and literal search work | PASS: 108 tree rows, 37 search hits including README |
| Full fresh/restored checks have SQLite `ok` and no FK/owner errors | PASS |
| Backup checksum matches its manifest; source DB stays unchanged; restore uses a new destination | PASS |
| Six complete normalized query results match after cache-free restore | PASS |
| Workload ≤600 seconds; remote operations ≤3; HTTP counts observed; offline queries invoke no Git | PASS |

Elapsed workload: **10.4896 seconds**; installation: 2.1225 seconds separately. Largest child peak RSS: 23,520 KiB, including temporary observer overhead. All workload commands exited 0; diagnostics, warnings and partial coverage: none. No application defect was observed.

| Storage | Bytes |
|---|---:|
| DB after initial sync | 7,081,984 |
| DB after subsequent sync / backup / restored DB | 7,622,656 each |
| Git cache after initial / subsequent sync | 897,604 / 897,727 |
| Restored cache | 0 |
| Backup manifest | 1,412 |

Cache sizes sum regular-file logical sizes. Catalog growth retains the subsequent observation. The backup excludes cache and unsaved originals; it is not a full Git mirror.

## Fresh/restored SHA-256 comparison

Normalization: UTF-8 JSON of `command`, `items`, `coverage`; sorted object keys, compact separators, `ensure_ascii=false`. Preserve row/parent order, raw byte encodings and stable IDs; exclude envelope instance/execution fields and continuation cursors. All six outputs had complete coverage and no further pages. JSON records both sides of these matching pairs.

| Query | Rows | Matching SHA-256 |
|---|---:|---|
| refs | 3 | `739df9fb2494241cb5746d8a860710fc5e8142f198f57915985e670c923773ff` |
| commit | 1 | `7893ba3be12ec60b7d98235fa31eef5827df26e7336927ec816f09011e04e65c` |
| tree | 108 | `b384796dbc153194b3567ab9dee76785edd2003de45db9c9d903c59e4cfa7d8f` |
| file | 1 | `41f1ee4df2d28ee7dac0f39d3a6fb4c62b6ded8f6b83486c80b01178db45f962` |
| content | 1 | `f0baddf99f8bfea61821b1224422ef487d8f13197dbd149475f23642872b35d8` |
| code_search | 37 | `4f4d11955385b89f5a95219d72b3b6189a2d136b9b8320484bd9e87298248f81` |

README raw-byte SHA-256: `886fc1f9546866d089cb07688b93bce10e1a562af6f24683209e72180bbc001d`, 71 bytes, independently matched to its acquired Git blob.

The exercised public Git workflow is usable for personal operation. API/PR synchronization, authenticated permissions/rate limits and real v2 salvage/finalization remain unexecuted; complete release-candidate acceptance is pending. Next action: a separately bounded PR/API trial on this repository, or a real offline salvage trial when an unambiguous preserved v2 source is available. No active catalog or remote repository was changed, source deleted or release published. Only summary evidence enters Git.

Evidence-change checks: 60 CI-selection/execution tests passed in 4.54 seconds; changed-file Ruff lint/format, prose/JSON validation and whitespace checks passed. The first test attempt stopped before execution because temporary development dependencies lacked `jsonschema`; installing its locked version resolved collection. The application suite and hosted CI were not rerun. CI recognizes these measurement JSON files as reports while retaining executable-document checks elsewhere. GitHub Issues remain for defects/follow-up work; no Issue is the success record.
