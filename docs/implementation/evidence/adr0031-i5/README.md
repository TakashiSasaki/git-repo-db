# ADR 0031 I5 author evidence and independent-review inputs

See the [implementation and I5 contract](../../adr0031-i5-typed-admission.md).
This directory binds the frozen execution inputs to author-only runtime
receipts. Independent non-Author review is pending; no acceptance is inferred.

Reproduce using the unchanged `uv.lock`, dynamic Python >=3.12 and actual
SQLite 3.51.3 / 3.53.1 libraries. Measure `sqlite_source_id()` in the executing
process, never substitute a reported version. The runtime build provenance and
all process logs are retained in the evidence archive.

```sh
python scripts/verify_i5.py --sqlite 3.51.3 --output /absolute/new-evidence
python scripts/verify_i2_sql_counterexamples.py /absolute/repository 3.51.3 /absolute/new-sql-evidence
python scripts/build_p1_schema.py --check
python scripts/audit_p1_schema.py --check
python scripts/audit_callsite_dependencies.py --check
python scripts/audit_context_registration.py
python scripts/audit_implementation_boundary.py
python scripts/verify_i5_distribution.py --output /absolute/new-distributions --minimum-library /absolute/sqlite3513 --newer-library /absolute/sqlite3531
```

Repeat the first two commands on actual 3.53.1. Distribution verification builds
from a clean Git archive, builds a second wheel from its sdist, creates fresh
installed environments outside checkout and runs both runtimes. It retains the
unchanged original Access smoke's nonzero Transfer-stage outcomes. The broad
runner intentionally exits nonzero while inherited Transfer/Wire refusals remain.
Overlapping focused tests and SQL diagnostics must not be added as unique tests.

Both SQL transfer fence triggers (`i2_transfer_stage_fence` and `i2_transfer_report_stage_fence`)
and application preflight refusals (`_preflight_units`) remain active and byte-identical in
product DDL. Normal product paths continue to reject Transfer operations with `I2_TRANSFER_UNSUPPORTED`.
Positive typed admission is validated exclusively in disposable isolated test databases where
the exact product schema is verified against `expected_schema('context')` and then the two fences
are explicitly dropped.

## Final author results

Read the [author report](REPORT.md), [machine summary](summary.json),
[all-79 first-failure comparison](failure-classification.json),
[indexed raw evidence](author-evidence.zip) and [payload index](artifact-index.json).
Executed HEAD is `3a749541fe4c41eb72e7ded9f36528f0abeb05ff`, tree
`6a494efb510713dbfb3cebf6ef5ff85e703e0d18`.

Both actual SQLite versions execute 3,137 selected nodes: 3,058 pass, 59 call
failures, 20 setup errors, no skips/xfails. The original 79 failure node/phase
pairs and refusal positions persist; 14 call failures remain I6 Wire-owned.
I5's focused 29, I4's 217, I3's 65 and I2's dedicated 86 are successful overlapping
subsets. All 301 SQL diagnostic groups pass. All four fresh installed wheel
combinations pass 29/29 I5 tests, 217/217 I4 tests and the unchanged I2/I3 probes; four original
Access smokes still fail at Transfer preflight. Both product fences remain.

Carryover findings:
- **I4-E1 (Low)**: Discrepancy between documentation/script inputs in review tree vs historical sdist scope; carried forward unresolved.
- **Task G G-R1 (Medium)**: Context.candidates() global/scoped identity exposure carried forward for ADR 0031 I7.
