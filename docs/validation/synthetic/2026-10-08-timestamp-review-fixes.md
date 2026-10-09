# Timestamp parser review corrections

## Revision and scope

Review finding 3 concerns fractional UTC offsets that Python can collapse to UTC. PR #5 already contained the initial rejection in `9abfdc0eb439a823246e306e7773b775cfaa75e7`. The completed correction is tested at `e54ca1c0232be75b5ce035b95c4117cd0d167b99`, Git tree `087b997afe6a021acc4d63a8f1d974dfc5dc0adb`, on local branch `fix/timestamp-offset-spellings`. The intended publication target is `refactor/unix-microsecond-timestamps`.

The guard now covers hour-only, compact and colon-separated offsets, both signs and decimal separators. Independent review also found that a trailing NUL can be accepted by `datetime.fromisoformat()` after a fractional offset and evade a suffix check. Any NUL in an external timestamp is now rejected. Valid local timestamp fractions and whole-second UTC offsets retain their existing exact conversion behavior.

Guarded Git and PR salvage tests verify that rejected source times become NULL with `GIT_INVALID_TIME` or `PR_INVALID_TIME`, while source values and typed raw evidence remain unchanged. No missing or malformed time is replaced with the current time.

## Completed local verification

On the clean substantive commit above, the timestamp, Git conversion and PR conversion modules passed **173 tests**, with zero failures, errors or skips. Pytest reported 31.92 seconds; JUnit suite time was 31.309 seconds. Ruff lint, formatting and `git diff --check` passed.

```bash
uv run --no-sync pytest tests/integration/test_catalog3_timestamps.py \
  tests/unit/test_conversion_git_domain.py \
  tests/unit/test_conversion_pr_domain.py -q \
  --junitxml=artifacts/timestamp-review-focused-final.xml
```

Environment: Python 3.12.14, SQLite 3.53.1, Git 2.51.1, uv 0.12.19, Linux x86_64. Dependencies came from the locked offline cache. The existing current-runtime and packaging acceptance will also run on the integrated coverage correction; GitHub CI is separately attributed to the published PR head.

## Retained failed attempts

- The first 20-case offset-spelling regression on the upstream guard failed for all four hour-only sign/separator combinations; the other 16 cases passed.
- After extending the offset guard, independent NUL tests failed in all four short/full and positive/negative cases. Rejecting NUL fixed this separate parser acceptance gap.
- The first formatting check rejected one overlong test signature. Formatting was corrected before the clean substantive commit and final test run.
- Earlier 167-test focused runs passed before the NUL finding; they do not cover the final NUL correction and are not substituted for the final 173-test result.

Only synthetic source values were used. No real source acquisition, retained catalog change, main merge or release was performed. This is a boundary-validation correction without a schema version change or compatibility layer. This report and its JSON summary are evidence-only additions after the tested source commit.

## Earlier publication checkpoint

At the end of the original validation, automatic approval review rejected the GitHub push because it interpreted that request as authorizing planning/implementation but not remote publication. A subsequent read confirmed PR #5 still pointed to `9abfdc0eb439a823246e306e7773b775cfaa75e7`. The rejected operation was not retried through another interface. This records the earlier checkpoint; current publication and hosted validation are tracked in [PR #5](https://github.com/TakashiSasaki/git-repo-db/pull/5).
