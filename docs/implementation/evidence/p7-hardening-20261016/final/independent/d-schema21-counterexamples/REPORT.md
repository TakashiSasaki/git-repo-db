# Independent reproduction of two broader-suite failures

Both selected failures reproduce independently on final P7 commit `178ddbaa8fa06f52aff4993730205c5a38da91f4` and unchanged remote main `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`. Each revision has its own worktree and editable virtual environment. Parent and separate child import probes identify the respective worktree source, so these failures are not explained by importing another checkout.

Actual command in each worktree, using its own `uv run --no-sync` environment:

```
pytest tests/integration/test_application_contract.py::test_operational_failure_retains_resumable_job 'tests/integration/test_catalog3_github_runtime.py::test_graphql_error_only_response_retains_backoff_and_resume_boundary[RATE_LIMITED-RATE_LIMIT-60000000-null-root]' -q -o junit_family=xunit1 --junitxml <revision>-junit.xml --journal <revision>-journal.jsonl
```

Final: **2 failed in 6.98s**, exit 1. Main: **2 failed in 7.63s**, exit 1. No test was omitted, converted to skip or repaired.

- `test_operational_failure_retains_resumable_job` queries `jobs`/`job_attempts` through `Store.one`, whose connection is Core, and fails `sqlite3.OperationalError: no such table: jobs`.
- The selected GraphQL retry test similarly queries `collection_progress` through the Core connection and fails `no such table: collection_progress`.

Read-only inspection of both actual disposable fixture catalogs confirms all three tables exist in `operational.sqlite3` and are absent from `catalog.sqlite3`. The relevant two test modules, `store.py`, `schema.py`, `tests/conftest.py` and CLI helper are byte-identical between revisions. This is direct evidence that **these two** failures are inherited assertions using the wrong store after the accepted store separation. No production catalog was examined or changed.

This finding does not classify every failure in the broader suites. The original reported five Schema 21 failures are not an exhaustive verified count; root's complete final and main runs must be reconciled by actual node IDs. The overall project suite is not green. No unrelated Schema 21 test or runtime change was made.

`reproduction-binding.json`, both raw pytest traces, JUnit, journals and import probes retain exact identity and failed assertions.
