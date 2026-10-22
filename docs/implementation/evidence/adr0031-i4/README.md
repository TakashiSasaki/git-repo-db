# ADR 0031 I4 author evidence and independent-review inputs

See the [implementation and I5 contract](../../adr0031-i4-transfer-sql.md).
This directory will bind the frozen execution inputs to author-only runtime
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
