# Independent distribution replay of PR #153

This scope passes the exercised product/distribution contracts, subject to the retained source-archive omission and original Access smoke failure. This is no Release acceptance or I6-C implementation.

Target: `61e44291e293f773904a0127606e20c8cb83c95e`, tree `4aa8ddf49fb52d0b903db0b0bfce00ccea2fae0c`, parent review `8521158f2996f125d2fcaac36ea79ac1296a7cf7`. The reviewer changed no product/test/assertion/ADR/history files. AGENTS, ADR0032 and applicable isolation/investigation procedures were consulted; no alternate SQLite was acquired or installed.

## Artifact construction and input completeness

One complete `git archive` of the target supplies both builds. Direct wheel and sdist were built separately, then the extracted sdist independently built its wheel. All build/install subprocesses exit0. The archive's 8,279 original files were checked individually against Git blob hashes, lengths and modes. Every original file is byte-identical after builds and testing (`frozen-input-invariance.json`). The procedural build/isolation/measurement harness was adapted from the attributed Author `distribution/final-root-guard` scripts after inspection; all result files here are newly executed independent measurements, not copied receipts. Newly designed probes are separately identified by their own input hashes.

| New artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Direct wheel | 791300 | `2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8` |
| Sdist | 165713022 | `88e2496b9335f475bbcaa6857832ce0d9dabc128b10bbf5aa0b08336039d52dc` |
| Sdist-derived wheel | 791300 | `2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8` |

The new sdist is identified by its own measured hash; neither an Author freeze sdist nor the hosted sdist is represented as these bytes. The two complete wheel archive byte streams agree, including per-member ZIP metadata; all 164 wheel members agree byte-for-byte between the two wheels, including METADATA, WHEEL, entry points and RECORD. Every archive RECORD row validates. All 160 product files / 6,025,551 bytes equal the frozen source. Separate outside-source venvs install each wheel with hash-pinned locked dependencies. Session-start/finish checks establish actual site-packages origins of all loaded product modules and exact product files. The runtime measurements independently validate every installed RECORD row, including generated installed rows; all archive members other than the installer-rewritten RECORD agree exactly with actual installed members. Installed METADATA/WHEEL agree with their archives. `repo-catalog doctor` enters the actual installed CLI and exits0.

The sdist has 8,160 files: 8,159 retained original source files plus PKG-INFO, which equals wheel METADATA. All retained source bytes and modes match Git. It omits **120 historical evidence files**, all under `docs/implementation/evidence/adr0031-i6b-independent-20261023/ci/author-access/artifacts/`. The exact omitted paths are recorded in `sdist-source-retention.json`. Both omitted files and `.gitignore` equal the parent-review blobs. All product, test, script, workflow, lock and build inputs are retained exactly. Thus exhaustive historical-source retention is incomplete; no product-input omission was observed. No #144/#147 sdist improvement was integrated or presumed.

Runtime: each installation uses environment Python 3.12.14 and actual loaded SQLite 3.53.1, with source ID, `_sqlite3` origin, compile options, STRICT/JSON checks and foreign-key/recursive-trigger PRAGMAs recorded in runtime JSON. No version matrix or engine replacement occurred.

## Actual executions

Each row is a separate invocation in each of the two isolated installations. Collection IDs, JUnit identity multisets, journal starts, exactly-once setup/call/teardown and completed exit agree in every lane. Passing lanes have zero failures/errors/skips/xfail/xpass. Rows are overlapping scopes and must not be summed into a unique whole-source result.

| Each installed form, separately | Actual result | Exit |
| --- | --- | ---: |
| Existing safety | 626 PASS | 0 |
| Existing wire/planner | 212 PASS | 0 |
| Saved independent normal wire/planner/admission | 204 PASS | 0 |
| Separate saved resolved V07 alternatives | 4 PASS | 0 |
| Saved Author external probes, attributed reuse | 34 PASS | 0 |
| Saved unchanged M01/M02 contracts | 33 PASS | 0 |
| Author new M01/M02 regressions | 56 PASS | 0 |
| Fresh independent M01 budget probes | 38 PASS | 0 |
| Fresh independent M02/wire probes | 61 PASS | 0 |
| Fresh independent admission/COMMIT probes | 13 PASS | 0 |
| Original Access smoke | 1 FAIL | 1 |

The historical I4 217 and I5 29 map to actual `p3/test_transfer_sql.py` and `p3/test_transfer_admission.py` nodes **inside safety626**; they are not extra cases. Full-scope source testing belongs to the parent's separate single invocation and is not inferred from these lanes.

A separate actual-input replay executes all 30 saved raw digest vectors in both installations. Every canonical control is accepted unchanged, every stale digest is `DIGEST_MISMATCH`, and every correctly rehashed noncanonical changed selection is `INVALID_SELECTION`. Those are overlapping measurements, not 90 new tests.

The original smoke literal was extracted unmodified from `scripts/verify_access_distribution.py`; its SHA and fixture/guard/launcher hashes are retained. It was run separately in a minimal outside-source venv for each artifact. Both actual child and pytest exit1, typed `PERMISSION_DENIED` at the unconnected export. The smoke's 26 earlier assertions are reached; all 28 assertions from line188 onward are unreached. The line-trace sidecars, actual traceback and child process receipt retain this limitation. No later export/import assertion is called successful and no privilege was broadened.

Commands, cwd, source/input/artifact hashes, process exit, logs, JUnit, journal and import/runtime sidecars are retained alongside this report. Run timings overlapped the parent's source workload and establish no comparative benchmark. No live Provider acquisition, normal Transfer activation, fence retirement, merge, release or deployment occurred.
