# Separate import workspace: synthetic validation

## Revision and scope

Starting main: `314cfb4466c4206401c7e0c994eedd9481283c88`. Branch: `refactor/import-workspace-db`.

Clean substantive tested commit: `23941ef421e3459d38becc65878e2c14b96576d5`. Tested tree: `a938da1ed1b83fc26b52074de9e0ca98293894c7`.

Catalog3 schema 7 contains 65 ordinary tables (previously 73). Eight import/finalization tables moved to `import-v2/workspace.sqlite3`, together with one private target/schema-binding table. The workspace persists through interruptions and finalization; it is disposable afterward, not automatically deleted. No changes to the frozen v2 source schema or prior evidence were made.

## Completed acceptance

| Check | Result |
| --- | --- |
| Current ordinary acceptance | 396 passed; four workers; profiled wall 48.9149 s |
| Independent wheel and sdist-derived wheel | 2 passed; sequential; profiled wall 3.0862 s |
| Existing planner/collection/profile gate | 398 selected and executed exactly once; 43 files; no failures, errors, skips or unexecuted files |
| Ruff lint and format | Passed; 119 Python files |
| STRICT/FTS doctor and prose validation | Passed |
| Offline dependency/wheel verification | 24 compatible Linux-required wheels verified against uv.lock |

Actual environment: Python 3.13.5, SQLite 3.46.1, Git 2.47.3, uv 0.10.0 on Linux x86_64. The environment-only development install used an installed wheel and source-path override after editable preparation lacked the `editables` module. Independent packaging checks do not use that override. The wheel artifact excludes Windows-only colorama, which is not required by the Linux marker. No repository dependency or guard was weakened.

## Boundary and failure coverage

Regression tests verify ordinary schema absence of all eight tables and of cross-file legacy FKs; automatic creation and explicit import/finalize-only attachment; preservation of typed original values in scratch; immutable workspace-to-target/schema binding; missing, wrong-catalog, symlink, hardlink, changed-schema and WAL workspace rejection; arbitrary ATTACH rejection; crash recovery between the two initial filename publications; and process death after target data, after mappings, before commit and after commit. Target rows, mappings and batch receipts recover consistently. Original synthetic source hashes remain unchanged.

The paired writer uses one SQLite transaction with on-disk DELETE journals and synchronous=EXTRA for both databases. This follows SQLite's attached-database atomic-commit contract; it is not two independent application commits. Tests inject process death, not a physical power cut or faults in the storage controller.

After successful finalization, removing the disposable synthetic workspace leaves queries, idempotent finalize, full DB check, backup and restore functional. No scratch tables appear in the restored catalog. Normalized gap reasons remain without `legacy_record_id` references; conversion attribution stays in workspace mappings/diagnostics. Source/network guards, the writer lock, semantic coverage and justified current selection remain enforced.

## Earlier incomplete attempts

Two full-suite tool invocations were terminated by the tool execution limit; neither produced completed acceptance and neither is counted above. Focused runs passed 75 and 13 tests. Final acceptance is the separately completed clean-commit planner/collection/run/gate described above.

## Evidence hashes

- `validation-manifest.json`: `c5abab634f2c5d2063219e0629210cf552eb38319226b9f1ffd34bb4e71b88de`.
- `tests.xml`: `535d35fae1ccaaf1198f62eb48556bb6a60525ea2eca5bc850c2f7ef11062d8f`.
- `packaging.xml`: `9427e63eca7b7ca88e6a0e22bd77e512849285878ecd90f90263822d2a1d6710`.

## Limits and transport

The editing environment cannot resolve external hosts. Temporary GitHub Actions transport supplies public tracked source and publishes the tested Git objects after bundle and tree hash verification. Temporary transport files/workflows are absent from the final diff; transport history is retained. This report and its handoff link are evidence-only follow-ups, not another runtime test run.

No real user DB/cache, live provider acquisition, main merge, release, active-catalog cutover, multi-catalog exchange, original-source deletion or automatic workspace purge was performed. Failed/unfinalized workspaces remain required for resume. SQLite references: https://sqlite.org/lang_attach.html and https://sqlite.org/atomiccommit.html.
