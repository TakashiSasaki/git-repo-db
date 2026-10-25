# Task F evidence guide

Read [the independent report](REPORT.md). Verdict: **READY WITH CONDITIONS** for
starting the ADR 0031 I2 product implementation at #122's exact reviewed HEAD.
This does not accept a product implementation, merge or release.

The reviewer used a new checkout, official-source builds of SQLite 3.51.3 and
3.53.1 and independently authored synthetic cases. Final execution is 343/343
case groups per runtime, with actual child and runner exits 0. The 42 model
groups are separate from SQL constraints. The original successful 322-case run
is historical and is not added to the final total. The author's 119 cases were
audited as archived evidence and were not rerun or counted as independent cases.

## Published files

- `REPORT.md`: findings, scope, layer boundaries, design verdict and conditions.
- `review_sql.py`, `run_review.py`, `build_runtimes.py`: independent execution.
- `audit_evidence.py`: read-only author/archive and independent-result audit.
- `F1-reproduction.sql`: unchanged Task D literal SQL.
- `counterexamples.sql`: selected concrete independent SQL traces, with expected
  refusals and snapshot rollback; install target DDL/UDFs before running.
- `minimum-summary.json`, `newer-summary.json`: runtime/source/PRAGMA and case
  inventories, actual physical FK/index/UDF information.
- `task-f-evidence.zip`: full SQL, full pre/post rowsets, runtime construction,
  complete reviewed-file manifest, both attempts, measured process exits,
  evidence audit and public source/ref observations. No catalogs or binaries.
- `artifact-index.json`: SHA-256 and sizes of the published artifacts.

The archive has its own complete member index. Both internal/external indexes
exclude their own bytes, avoiding a circular hash claim. Final publication
commit/tree are in the Draft PR metadata; the archive binds executed inputs to
`2199a882d79c9c707fffcba3a8327ef96a3fc384` /
`b1595725bce322d04baf0f3b9b340cfdc71552a0`.

## Fresh reproduction

Start with a fresh clone at the exact #122 HEAD, and an empty scratch directory.
Copy `build_runtimes.py`, `review_sql.py` and `run_review.py` into that scratch
directory. Do not modify reviewed product files, overwrite original receipts,
use an author binary or alter SQLite version constants.

```sh
python3 /ABS/SCRATCH/build_runtimes.py /ABS/SCRATCH/runtime
/usr/bin/python3.13 /ABS/SCRATCH/run_review.py /ABS/FROZEN/REPO /ABS/SCRATCH/final-run
```

The dynamic interpreter must actually load each new library. The probe checks
`sqlite_version()` and records `sqlite_source_id()`; changing LD_LIBRARY_PATH
alone is insufficient on statically embedded interpreters. `run_review.py`
records both actual lane exits. An independent parent subprocess should also
record the actual runner returncode, as `final-launcher.json` does here.

Expected: both lanes 343 passed, zero failures, runner exit 0, original reviewed
files unchanged. The before-composition Task D report is intentionally accepted;
that is a successful defect-reproduction diagnostic, not approval of the old
design. The after-composition report must fail 1811 with exactly equal rowsets.
Injected unsupported rows are diagnostic fixtures only and the exact fences
are restored before their tested replay or reader operation.

Do not install the prototype stage_contract.py as a production API or treat its
normalized-operation checks as tests of the real wire parser, selection engine,
Core-only Exchange, Query/Search, catalog stop or installed distributions.
