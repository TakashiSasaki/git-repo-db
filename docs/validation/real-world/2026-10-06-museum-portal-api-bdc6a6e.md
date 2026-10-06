# Museum-portal PR/API trial — FAIL under original budget

Application: `bdc6a6eb9044f316cd9ebea9e70dd484b49ff406`; installed wheel 0.2.0 outside the checkout. UTC: 2026-10-06T05:43:06.925611+00:00 → 2026-10-06T05:50:01.325265+00:00. Python 3.12.14, native SQLite 3.53.1, Git 2.52.0; Linux-6.18.44-x86_64-with-glibc2.41. Exact wheel digest and representative PR #1 head/base OIDs: [JSON summary](2026-10-06-museum-portal-api-bdc6a6e.json).

Public target `TakashiSasaki/museum-portal` was the smallest useful candidate: 899 KiB and 50 PRs. `museum-portal-aistudio` was 1,067 KiB with zero PRs; `templates` was 20,045 KiB with at least 100. Candidate selection cost seven counted calls. Existing GH_TOKEN authentication, REST and read-only GraphQL worked; remaining provider quota was ample. Stopping was due to the user's original 100-request budget, not GitHub's quota.

| Phase | API calls | Elapsed | Result |
|---|---:|---:|---|
| Discovery | 2 | 0.98 s | One explicitly included repository |
| First sync | 43 | 35.73 s | Cancelled safely before call 44; code #1–4 complete |
| Second sync | 43 | 26.27 s | Cancelled safely before call 44; code #1–5 complete |

Total: 95 API sends including reconnaissance; no retries/API failures. Git: 35 HTTP requests, 15 remote operations. API and Git traffic are counted separately; own-project publication is outside validation. CLI workflow 65.45 s; reconnaissance-to-finish wall clock 414.40 s including inspection/setup pauses, under 600 s. A temporary locked transport gate counted each send before transmission, constrained API methods/targets, admitted at most 96 calls with four conservatively reserved, and split the two syncs into 43-call caps. A shared monotonic deadline supervised commands; Git transfers had 45-second timeouts. Instrumentation never filtered or manufactured API payloads; raw Git headers/traces were discarded in a pipe.

**FAIL criterion:** both full requested syncs must finish within 100 calls and 600 s. The existing CLI syncs all 50 PRs and has no per-PR selector. Detail + reviews + timeline alone require at least 150 calls before other child lists, GraphQL or a second run. Both ordinary syncs returned CANCELLED/exit 130 as designed by the gate.

**PASS criteria:** meaningful partial results, justified reuse, source safety, and backup/restore. Retained: 50 PR identities, 115 observations, 266 document versions, 100 review comments, 63 timeline occurrences, five commits, seven file changes and nine complete code observations. PR #1 queries returned five observations, three documents, 14 timeline occurrences, one commit, one file change and three code links. Literal `museum` search returned 49 rows. All five ordinary queries honestly returned partial coverage/exit 3. Review and thread endpoints returned no reviews/threads for processed PRs; nonempty review/thread history remains untested.

The second sync returned five conditional detail 304s. It sent zero commit/file-list requests for completed unchanged #1–4; its one commit-list and one file-list call acquired previously incomplete #5. Authentication, inventory, incremental comments, current head/base checks and child histories lacking reusable validators still required requests. Endpoint-family counts are in JSON.

Initial/final DB: 14,041,088 / 17,264,640 bytes; final cache: 253,608 bytes. Backup/restored DB: 17,264,640 bytes; restored cache: zero. Full structural checks, backup-manifest checksum and all five normalized query/coverage SHA-256 pairs passed. Backup/restore left the source DB digest unchanged. Cache is excluded, so backup is not a full Git mirror. Digest normalization preserves nested IDs/history/code and ordered rows, omitting only the execution/catalog envelope and cursors.

All workspace/state/cache/backup/restore/measurements used an automatic tempfile root. Command shapes (global `--format json` was used; exact commands/timings in JSON):

```bash
repo-catalog --state-dir ${TRIAL}/catalog-fresh init --profile catalog-text-v1 --cache-max-bytes 134217728 --min-free-bytes 67108864
repo-catalog --state-dir ${TRIAL}/catalog-fresh sources add github --owner TakashiSasaki --include-repo museum-portal
repo-catalog --state-dir ${TRIAL}/catalog-fresh discover --source SOURCE_ID
repo-catalog --state-dir ${TRIAL}/catalog-fresh sync pr --repo REPO_ID  # twice, under transport admission
repo-catalog --state-dir ${TRIAL}/catalog-fresh pr show --repo REPO_ID --number 1
repo-catalog --state-dir ${TRIAL}/catalog-fresh pr documents --repo REPO_ID --number 1
repo-catalog --state-dir ${TRIAL}/catalog-fresh pr timeline --repo REPO_ID --number 1
repo-catalog --state-dir ${TRIAL}/catalog-fresh search pr --repo REPO_ID --literal museum --document-versions observed --limit 1000
repo-catalog --state-dir ${TRIAL}/catalog-fresh db check --full
repo-catalog --state-dir ${TRIAL}/catalog-fresh db backup --output ${TRIAL}/backup/catalog.sqlite3
repo-catalog --state-dir ${TRIAL}/restored db restore --input ${TRIAL}/backup/catalog.sqlite3
# Repeat the five queries and full check offline against restored state.
```

Offline queries/maintenance used the existing network guard. No target remote mutation, source DB/cache mutation, credential/raw authenticated traffic/payload commit or schema cleanup occurred. Temporary pre-acquisition driver setup errors were corrected, without product changes. No application suite was rerun. This report preserves the original budget-limited attempt; any subsequently authorized continuation needs a distinct report.
