# Museum-portal complete PR/API continuation — PASS

Exact application: `64da7222c96d5cd31b7f08a35d77552394c64e46`, wheel 0.2.0 built from that clean checkout and installed into a temporary venv. Target: public `TakashiSasaki/museum-portal`, all 50 PRs. [Machine-readable summary](2026-10-06-museum-portal-api-continuation-64da722.json) includes exact wheel digest, PR head/base OIDs, commands, sizes, criteria and SHA-256 pairs.

Window: 2026-10-06T15:03:34.050005+09:00 → 2026-10-06T15:21:06.928108+09:00 (Asia/Tokyo; UTC also recorded). Python 3.12.14, native SQLite 3.53.1, Git 2.52.0; Linux-6.18.44-x86_64-with-glibc2.41. Existing GH_TOKEN used through the normal transport; token/headers were never printed or retained.

## Continuity and budget

This resumes the [prior budget-limited attempt](2026-10-06-museum-portal-api-bdc6a6e.md), whose report is unchanged. The prior state still existed: DB identity/publication `2840c781-b053-4782-b571-2dcb944cc662` / 221, all recorded row counts and all five normalized query hashes matched the durable report. Its complete DB/config/cache file tree was copied byte-for-byte into a different automatic temporary root. Only the copy was written. Original tree SHA-256 `599a047e116522383377b35e87457e76f2553c4564b702a2752fb099697f4c05` matched again after continuation. No discovery or v2 search was repeated.

Authorized cumulative API limit: 1,000, with 95 previously consumed, so at most 905 additional. The initial additional wall-clock limit was 600 seconds. It safely interrupted the second sync after 29 detail validators. The user then explicitly authorized more time; the remaining second job was resumed under another 600-second window, preserving all counters and established state. A locked send-admission counter included retries and started at 95; a shared monotonic deadline supervised all commands/descendants. The previous 43-call phase caps were removed. Git acquisition was limited to target ls-remote/fetch with 45-second transfer timeouts; raw trace headers were discarded in a pipe. All state, backup, restore, cache and measurements used an automatic tempfile root; queries/recovery ran with the existing offline network guard.

| Phase | API sends | Elapsed | Result |
|---|---:|---:|---|
| Resume interrupted job to first complete repository sync | 408 | 364.75 s | complete |
| Subsequent normal repository-wide sync | 357 | 303.55 s | complete |

Additional API sends: **765**; cumulative **860 / 1,000**. Entire resumed sync/query/recovery workflow: **1052.88 s** including the stopped interval and user-response/preparation time. Initial bounded window 599.04 s; post-authorization window 220.69 s / 600 s. Git acquisition: 335 HTTP requests, 143 remote operations (separate from API sends). Provider API failures: 0; one admitted send was deliberately cut short by the original deadline (ReadTimeout), and is included in the count. Observed remaining quota: REST 14817 initially / 14127 last (minimum 14127); GraphQL 9935 initially / 9819 last (minimum 9819). Provider quota never caused interruption.

## Request behavior

| Endpoint family | Resumed first | Second sync |
|---|---:|---:|
| authentication | 2 | 2 |
| comments | 89 | 100 |
| events | 46 | 52 |
| graphql | 45 | 50 |
| incremental_issue_comments | 0 | 1 |
| incremental_review_comments | 1 | 1 |
| pr_commits | 45 | 0 |
| pr_detail | 90 | 100 |
| pr_files | 45 | 0 |
| pr_inventory | 0 | 1 |
| reviews | 45 | 50 |

The temporary URL admission gate initially rejected GitHub's legitimate canonical numeric-ID pagination URLs. The completed response/catalog supplied the verified repository ID `1195783174`; the gate was narrowed to also allow `/repositories/1195783174/...`, and the same job resumed. The initial partial step was a measurement-scope error, not a GitHub or product failure. Its 404 counted API sends (all HTTP 200) and 362.19 seconds remain counted; recovery kept the original cumulative counter/deadline. A subsequent normal second sync stopped at that deadline, after which only the user's explicit time-extension authorization changed the deadline; the API count never reset.

The post-deadline offline probe initially used default current scope for PR code search; the CLI correctly rejected it because current permits heads only. Using supported `--scope history --pr` completed the intended query. No product defect or regression test was warranted by this invocation correction.

Status counts: resumed first {"200": 408}; second {"200": 306, "304": 50, "None": 1}. Second sync used 50 conditional requests. It made no commit/file-list requests when previously sealed head/base/count/context evidence remained valid. Current-state authentication, inventory, incremental comments and child histories without reusable validators still required requests; these refreshes preserve observations rather than blindly reacquiring established listings. The 50 PR head/base/state/update tuples from the completed first job's retained code observations matched the completed second sync (digest in JSON); neither the validation nor this task changed any remote GitHub state.

## Meaningful results and recovery

Collected totals include retained prior and newly acquired history: 50 PR identities, 305 observations, 430 document versions, 121 reviews, 79 review threads, 143 review comments, 1238 timeline occurrences, 207 retained listing commit rows and 137 file-change rows. Counts include distinct observations/listing versions and are not advertised as unique remote events/commits. All 50 current PR code observations were complete. Representative PR #42 was selected for useful review/document coverage; its observations, documents, reviews, events and code listings returned meaningful data. A real thread query was included when available, plus literal PR and code search. Query row counts and coverage are below. PR identity/history/documents/events/search and thread queries were complete. Broad code history search honestly reported 270 unsaved ancestor bodies and five policy exclusions; it returned a bounded 1,000-row page with more matches. This is the documented catalog-text-v1 retention scope (README lines 74–76), not a synchronization defect. A separate read-only join across all 50 current PR code roots confirmed zero eligible root-tip bodies missing. No historical body was silently presented as empty.

| Query | Rows | Coverage complete | Matching SHA-256 |
|---|---:|---|---|
| pr_identity | 50 | True | `2ce62d08b7b7a5ad2e7a8ec024c6ef34c37592cfd7754ea170051edeeaf7e257` |
| pr_history | 1 | True | `71a36913f9fa86ab3f1e8751fac505ed983e15f4e2d636d6044fe6ade4d77b03` |
| documents | 183 | True | `c6bb03275d7ceecd9dcb357d7dea3b6d48c8544d10519e8d9593eea830e3d5ab` |
| events | 302 | True | `38c2d49349eb41e09fe31e6d939510af5a48d5768d28b7a8ed850bb2c0f3c29d` |
| pr_search | 66 | True | `ed7480c89546f3e22efd377d22f1c0025499a74cb3ac7a265166413a20b6f307` |
| code_search | 1000 | False | `34b592c9477ec87885f3a2b8272dd0c52ce70f9d3805932964fcac75f7ec41d8` |
| thread | 4 | True | `84dab83063f8103bad813d02d03f261d81397895a1305a26325fb58ea4d3fb7a` |

Full `db check --full` passed on the completed and restored catalogs: SQLite OK, no foreign-key or ownership-evidence violations. Backup manifest checksum matched. Backup/restore did not alter the completed source DB. The restored catalog, in another empty temporary destination, returned identical normalized representative results and coverage. Final DB 101138432 bytes; cache 1961272 bytes. Backup/restored DB 101138432 bytes; restored cache 0 bytes. Cache is excluded; this is not a full Git mirror.

## Commands, criteria and limits

```bash
repo-catalog --state-dir ${TRIAL}/catalog --format json jobs resume 3f810d30-a192-4fac-a1d7-64a8e22656c8
repo-catalog --state-dir ${TRIAL}/catalog --format json sync pr --repo REPO_ID
# After the original deadline interrupted the second job, explicit time extension allowed:
repo-catalog --state-dir ${TRIAL}/catalog --format json jobs resume 589b11e4-5aae-4f67-9f4f-a52cdd654367
repo-catalog --state-dir ${TRIAL}/catalog --format json pr list --repo REPO_ID --limit 1000
repo-catalog --state-dir ${TRIAL}/catalog --format json pr show --repo REPO_ID --number PR_NUMBER
repo-catalog --state-dir ${TRIAL}/catalog --format json pr documents --repo REPO_ID --number PR_NUMBER --limit 1000
repo-catalog --state-dir ${TRIAL}/catalog --format json pr timeline --repo REPO_ID --number PR_NUMBER --limit 1000
repo-catalog --state-dir ${TRIAL}/catalog --format json pr thread --thread-id THREAD_ID --limit 1000
repo-catalog --state-dir ${TRIAL}/catalog --format json search pr --repo REPO_ID --literal museum --document-versions observed --limit 1000
repo-catalog --state-dir ${TRIAL}/catalog --format json search code --scope history --repo REPO_ID --pr PR_NUMBER --literal museum --limit 1000
repo-catalog --state-dir ${TRIAL}/catalog --format json db check --full
repo-catalog --state-dir ${TRIAL}/catalog --format json db backup --output ${TRIAL}/completed-backup/catalog.sqlite3
repo-catalog --state-dir ${TRIAL}/completed-restored --format json db restore --input ${TRIAL}/completed-backup/catalog.sqlite3
# Repeat representative queries and full check offline against completed-restored state.
```

PASS requires complete first/second sync within request/time budgets, unchanged remote head/base/state evidence, meaningful complete or honestly scoped representative queries and code listings, justified listing reuse, both full DB checks, valid backup checksum, matching restored query hashes, and unchanged prior DB/cache/report evidence. Each criterion is recorded explicitly in JSON. Result: **PASS**; failure details: null.

No product defect was discovered, product code/schema was unchanged, and no broad application suite was rerun. Prior retained-real-v2 classification stays N/A without another search. No databases/caches/tokens/raw authenticated traffic/private payloads are committed. This read-only continuation does not publish branches, update PRs, create Issues, switch active catalogs or declare a release candidate. The next architectural stride remains schema naming cleanup.
