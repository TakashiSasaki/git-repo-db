# Independent reviewer A — Schema 21 architecture initial audit

Reviewer: `/root/review_a`, not author of remediation implementation.
Reviewed public main: `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`, tree `1b16e6589b0e7931f0eb24322127684479771c79`.
Read-only reviewed checkout `/workspace/review-a`; disposable state only.

Read AGENTS, ADR index and scoped ADR 0001/0002/0003/0022/0026/0027/0028, three-store-invariants and ci-final-tree-verification skills. Authority is user's current implementation authorization and preserved ADR0002 public baseline scope; opt-in ADR0003+ architecture is not a public migration.

## Findings

1. Production JobService/Capacity bind Operational explicitly. ApiFacts and GitHubCollector route collection_progress and job fencing to Operational. GitImporter/CacheManager use Operational acquisition progress/cache/leases. Search index and query/maintenance APIs use explicit SearchStore. No concrete production misrouting defect found in these inspected paths.
2. The shared tests.support.github_runtime.sync helper queries jobs using Core store.one after JobService already created its job in Operational. This is a stale fixture and explains its entire dependent cohort stopping before collector execution.
3. Many tests join Core fetch_collections and Operational collection_progress on a single Core connection. Correct tests must combine explicit reads using actual fetch_collection_id and preserve result/filter semantics; no ATTACH, compatibility view, duplicated table or Core fallback is warranted.
4. E2E Search corruption fixture reads index_generations and drops FTS using catalog.sqlite3; correct physical target is Search database. Search fallback behavior remains required.
5. incremental_scans is a retired mechanism; compatible terminal Core fetch collection proof and original start/since behavior are the surviving guarantee.
6. Seven non-SQL inherited assertion failures all require mandatory fine-grained reuse/no new root request. ApiFacts.begin intentionally starts a fresh collection for incomplete/unproven progress (ADR0002 PF-P04/P07). Tests must retain immutable committed evidence, safe partial/complete and truthful new observation behavior. In particular, a new root with 100 comments and failed required child makes current selected thread partial even when a previous observation was complete; former child-only test assumption does not apply.
7. No genuine CI planner coverage gap found: src/** is shared input; any public/P7 production source sets all ordinary acceptance files as required locally and static+smoke selected in Development; Release selects full tests and packaging. Ordinary green Development is not runtime acceptance. No separate CI correction proposed.

## Independent executions

- tests/unit/test_ci_plan.py: 90 passed, exact baseline tree; JUnit and per-phase journal adjacent.
- physical-boundary-probe.json: public Maintenance/Store/Job/Query APIs, real disposable SQLite databases; Core contains no jobs/progress/Search tables, connection database_list contains only main, read-only jobs query does not create Operational, Search creation explicit; committed Operational state survives independently rolled-back Core work and persists after reopened connections. No cross-store atomicity claim.
- ci-source-selection.json: disposable Git histories passed through current planner, paths store.py, persistence.py, operational.sql and synthetic P7 source; Development requires all local files while leaving runtime execution explicitly unexecuted, Release selects full acceptance.

This is initial architecture diagnosis, not approval of a future remediation commit. Final revised source must be reviewed at its exact SHA with retained behavioral regressions and complete cohort results.
