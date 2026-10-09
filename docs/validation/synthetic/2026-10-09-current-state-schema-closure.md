# Final local current-state schema closure acceptance

This schema 15 follow-up starts from PR #13 HEAD `db3a5ecfbf95b4c1318198aa308ca6dc749876a1` on
`refactor/latest-state-transport`; branch `fix/current-state-schema-closure` is
stacked directly on that verified checkpoint. The final local tests used the
uncommitted implementation snapshot `437eec577d913b62dacc20146ea7df273f46bf0f65e36848756205753763932e`.
The [JSON receipt](2026-10-09-current-state-schema-closure.json) records every
source/test/configuration input hash, commands, selected IDs, JUnit hashes,
parser certificate and superseded runs. Published HEAD, tested merge/tree and
hosted CI are recorded in the submitted PR body after publication; this local
receipt does not claim hosted execution.

## Final executed local acceptance

| Gate | Result |
|---|---|
| Ordinary production suite | **1,452 passed**, 276.786s JUnit duration; four workers. No failures/errors/skips; no parser bootstrap. |
| Installed wheel and sdist-derived wheel | **2 passed**, 66.772s JUnit duration; sequential isolated installs outside checkout. No failures/errors/skips; no parser bootstrap. |
| Selection reconciliation | 1,455 available, 1,454 selected/executed/passed; selected and JUnit IDs match exactly. Only opt-in `tests/live/test_smoke.py::test_selected_repository` excluded. |
| Fresh complete DDL | Schema 15; 103 tables, 48 views, 500 triggers, 108 named indexes. Every view queried and named index accessed; 291 DML statements compiled for 97 trigger-target tables. FK check empty; integrity `ok`. Compilation does not execute every trigger branch. |
| JSON registry / generated guards | 57 classified fields; generated SQL equals the registry; authored-reference audit passes. Dedicated evidence guards enforce canonical paths, ancestors, signed-int64 time, profile capability and capture ownership. |
| Parser certificate | Exact final definition and DDL match the captured snapshot; 13 capabilities verified from 287 genuinely passing development cases. Synthetic bootstrap used only for generation evidence; final ordinary/package acceptance uses the genuine artifact. |
| Static checks | Ruff lint, formatting of 162 Python files, whitespace and report validation pass. |

Ordinary JUnit SHA-256: `e7eaaec117fcde2c73b5c5e101aca7216eb6727c4587069ad836601e66a82e2d`. Packaging JUnit SHA-256:
`01af7c71e9e5856abcf9bb9cc094ddf30931f47d7d130d43efab133074ae98b5`. Complete DDL SHA-256: `20ec2e5c3b2fe7a064aa4e9a122d6b452d0f6b1a5be00113ce1dbd948f8f3826`.
Parser certificate SHA-256: `d60e33e92facfcfb6a55103ea553b01f5180410f7a2f0fa8304498b27a054293`.
Runtime: Python 3.12.14, SQLite 3.53.1,
git version 2.52.0, uv 0.12.19 (x86_64-unknown-linux-gnu), Linux x86_64.

## Finding closure and executable evidence

The attached review's isolated probes seeded production reproductions. They
are not counted as executed full-application acceptance. All six findings were
reproduced against the reviewed application/complete DDL and corrected; new
regressions execute the shared writer and/or real synthetic HTTP collector,
normal readers, application exchange and Graph.

| Finding | Corrected behavior / production regression |
|---|---|
| F1 | Typed staging ownership preserves three-plus current variants across receipt, reopen and reexport; immutable envelopes still follow their own competing-variant rules. `test_current_exchange_followup.py::test_competing_current_variants_keep_typed_staging_on_later_receipt` and application import test. |
| F2 | Same semantic content with stronger provider evidence reaches admission and refreshes staged evidence; exact repeats remain idempotent. `test_semantically_duplicate_candidate_admits_stronger_provider_evidence` and `test_staged_same_value_refresh_retains_new_clock_with_other_conflict`. |
| F3 | One same-row field-proof map distinguishes supplied values from inherited defaults; compatible sparse/full receipt orders converge and older full responses can fill unknown fields. `test_current_projection_followup.py`, actual REST/GraphQL collector tests and mixed-evidence Graph permutations. Contradictory overlapping values remain disputed. |
| F4 | Transfer cascades current child membership only, preserving original Source/endpoint/capture and field proofs. Full export/import/reexport does not pull the old repository/Source into destination B. `test_issue_transfer_followup.py`; real destination refresh updates genuine supplied proofs. |
| F5 | Allowlisted bounded recorder diagnostics are saved before best-effort warnings; warning-as-error/output-hook failure cannot abort valid collection. Transport/parser/storage/cancellation errors keep their semantics. Unit and actual transport/collector `test_recording_followup.py` cases; collection retains the last 100 diagnostics. |
| F6 | Initial, identical and edited authoritative local acquisitions advance the local check under the revision/scope fence; sender checks and replay do not advance it. `test_initial_and_changed_live_checks_advance_local_check_time`, imported-check tests and exact isolated installed exchange assertions. |

Independent combined-case review additionally corrected object/scalar ordering,
stale live overwrites, exact review capture ownership, unsupported field-profile
attribution, missing metadata ancestor proof, direct-SQL int64 overflow and
malformed Graph proof-time exception containment. The final scoped review and
its limits are in [the independent receipt](2026-10-09-current-state-followup-independent-review.md).
Independent and focused tests overlap ordinary acceptance and are not added to
its totals. [Schema checks](2026-10-09-current-state-schema-checks.md) preserve
exact scoped development checkpoints, including their explicit bootstrap use.

## Actual cleanup, retention and performance

Both current stores retain their typed natural keys. Two `field_evidence_json`
columns are added; `review_resources.title` is removed because no supported
producer or semantic reader exists. The unreachable historical thread lookup
and three absent current-pointer exchange exclusions are removed. Required
native FKs and generated discriminators, real preferred-endpoint exclusion,
independent threads and unaffected PR/Git/history/CAS/coverage contracts remain.
The [complete inventory](../../current-state-schema-inventory.md) and
[liveness matrix](../../current-state-schema-liveness.md) justify each role.
Previously deleted review marker tables/columns are not counted as new removals.

A disposable 20-edit fixture retained one current row, no immutable document
observations and 20 bodies; 19 older bodies (19,380 bytes) were unreferenced.
The same-row map stayed at seven current proofs, final 3,009 bytes. Repeated
unchanged imports did not add body/current writes; live checks update only
changed columns. Actual membership changes alone cascade children. Logical
latest-only reads do not imply physical GC. No shared bytes or history were
deleted; body/collection-receipt retention policy remains a separate deferred
product decision.

The first integrated 101-thread by 101-comment pagination run exceeded its
unchanged 60-second subprocess limit (60.49s call). Profiling traced repeated
field-context/reference validation. Distinct capture/profile checks and a
single reference pass replace redundant per-field full-map scans. A focused
optimized run passed in 22.96s call. Final same-session 22-field SQL-update
measurement, with 100 updates per round and three rounds, records before median
1.001159s and final median
0.170218s; approximate VM steps fell from
20,816,000 to 3,145,000. This synthetic comparison ran while capability workers
were active; it is not a cross-machine guarantee. The final ordinary suite
passed the original pagination case in 29.94s call under its unchanged deadline.

Two preliminary ordinary assertions and both preliminary package assertions
failed solely because they expected portable sender check times. They now
compare portable domain fields exactly and explicitly require receiver checks
to remain local; backup/restore and reindex equality still include check times.
Two subsequent partial ordinary runs were deliberately stopped when independent
review required a new SQL guard and exception-containment correction. Their
partial successes are recorded as superseded, not final acceptance. The schema
receipt likewise preserves the temporary native schema-version mismatch and
its corrected reruns.

## Commands and boundaries

```bash
uv run --no-sync pytest tests --ignore=tests/packaging -n 4 --strict-markers -m 'not live and not benchmark' --junitxml=artifacts/current-state-followup/ordinary.xml --durations=20 -q
uv run --no-sync pytest tests/packaging -q --junitxml=artifacts/current-state-followup/packaging.xml --durations=2
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
git diff --check
python scripts/ci_execute.py reports
```

All state and HTTP payloads are disposable synthetic fixtures. No live
authenticated acquisition, retained user catalog/cache/archive mutation,
physical hardware power loss, non-Linux restore, merge or release is exercised.
CAS-76/CAS-77, automatic archive deletion, comprehensive deletion propagation
and physical retention policy remain deferred.
