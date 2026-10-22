# ADR 0031 I4 author evidence and independent-review inputs

See the [implementation and I5 contract](../../adr0031-i4-transfer-sql.md).
This directory binds the frozen execution inputs to author-only runtime
receipts. Independent non-Author review is pending; no acceptance is inferred.

Reproduce using the unchanged `uv.lock`, dynamic Python >=3.12 and actual
SQLite 3.51.3 / 3.53.1 libraries. Measure `sqlite_source_id()` in the executing
process, never substitute a reported version. The runtime build provenance and
all process logs are retained in the evidence archive.

```sh
python scripts/verify_i4.py --sqlite 3.51.3 --output /absolute/new-evidence
python scripts/verify_i2_sql_counterexamples.py /absolute/repository 3.51.3 /absolute/new-sql-evidence
python scripts/build_p1_schema.py --check
python scripts/audit_p1_schema.py --check
python scripts/audit_callsite_dependencies.py --check
python scripts/audit_context_registration.py --check
python scripts/audit_implementation_boundary.py --check
python scripts/verify_i4_distribution.py --output /absolute/new-distributions --minimum-library /absolute/sqlite3513 --newer-library /absolute/sqlite3531
```

Repeat the first two commands on actual 3.53.1. Distribution verification builds
from a clean Git archive, builds a second wheel from its sdist, creates fresh
installed environments outside checkout and runs both runtimes. It retains the
unchanged original Access smoke's nonzero Transfer-stage outcomes. The broad
runner intentionally exits nonzero while inherited Transfer/Wire refusals remain.
Overlapping focused tests and SQL diagnostics must not be added as unique tests.

Only the two named Transfer fence triggers are dropped in disposable isolated
SQL fixtures, after exact product-schema comparison. Normal product SQL and
Admission remain refused. The report distinguishes these environments and
structural integrity from I5 Provider semantics, original input types and
whole-unit atomic admission. Task G G-R1 remains unresolved for I7.

## Final author results

Read the [author report](REPORT.md), [machine summary](summary.json),
[all-79 first-failure comparison](failure-classification.json),
[indexed raw evidence](author-evidence.zip) and [payload index](artifact-index.json).
Execution HEAD is `f4d8c3d123552e765ef3f0ddaf4e83deaaa0e9c6`, tree
`764414d23797179c6988349ca4a236c6b929a44e`.

Both actual SQLite versions execute 3,108 selected nodes: 3,029 pass, 59 call
failures, 20 setup errors, no skips/xfails. The original 79 failure node/phase
pairs and refusal positions persist; 14 call failures remain I6 Wire-owned.
I4's focused 217, I3's 65 and I2's dedicated 86 are successful overlapping
subsets. All 301 SQL diagnostic groups pass. All four fresh installed wheel
combinations pass 217/217 I4 tests and the unchanged I2/I3 probes; four original
Access smokes still fail at Transfer preflight. Both product fences remain.

The final publication includes a separately executed correction to the archive
comparison helper and skill guidance after the product freeze. It does not
change product, tests or packaged files. The exact final public HEAD/tree is
bound in the new Draft PR's author-report body. Independent review is pending.
