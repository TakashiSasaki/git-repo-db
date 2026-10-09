# Integrated data model handoff

Work starts from PR #10 `1c69a868f65b9637a7b8cf00d2c68a4ba05b2faa`, branch `fix/pr-stack-review`. The new implementation branch is `refactor/integrated-data-model`; the prior stacked branches remain unchanged. Local acceptance is recorded below; final published HEAD and hosted acceptance are recorded in the submitted PR body.

## Fresh-catalog workflows

Initialize with `repo-catalog --state-dir PATH init --profile catalog-text-v1 --cache-max-bytes 33554432 --min-free-bytes 0`. Add a Source, discover it, then run `sync git`, `sync pr` or `sync all`. Use `sources configure --source SOURCE_ID --input SETTINGS_JSON` to configure an imported Source locally without changing its registration UUID.

Job plans freeze registration identities, target repositories and non-secret acquisition settings; resume uses those saved values and resolves only credential references from the environment.

Repository list/show responses expose `inventory_observations` as separate Source-owned interpretations with result/observation UUIDs and decoded metadata. Shared repository metadata is local registration data and is not populated from later parsers.

`parser reparse FETCH_UUID [--select]` parses saved bytes without creating another remote observation. The default preserves the new result as history. `parser register`, `parser verify`, `parser select-profile` and `parser select-fact` accept JSON keyword arguments for the corresponding `ParserModel` methods using `--input FILE`. `parser trust VERIFICATION_UUID [--revoke]` explicitly changes local trust; `parser invalidate VERIFICATION_UUID --reason TEXT` adds immutable invalidation. `parser status` exposes definitions, evidence, scopes, selections and staging. Profile verification requires evidence for every declared capability and the exact immutable definition. New observations never silently change an established profile selection.

`identity relation --input FILE`, `identity cancellation --input FILE` and `identity status` admit and inspect explicit equivalence evidence. A relation never merges repository rows, facts or coverage; missing cancellation targets remain staged.

`exchange export --repo REPOSITORY_UUID --output FILE`, `exchange import --input FILE` and `exchange staging` handle one-repository portable exchange. Source-wide inventory, local quarantine/trust and validator caches are outside the unit. Received Source settings remain historical provenance and never configure or overwrite receiver-local operational settings. Importing history never makes remote verification locally trusted automatically.

`db verify-payloads`, `db repair-payload --sha256 HEX --input FILE`, `db check --full`, `db backup --output FILE` and `db restore --input FILE` expose integrity maintenance. Restore requires a new explicit state directory; backup requires unused database and companion manifest destinations. Failed restore stages are retained.

## Removed compatibility-only work

The unreleased product no longer ships `adapters/import_v2`, the v2 conversion contract/migrations/workspace, `application/import_service.py`, import-only finalization, `scripts/import_fixture.py`, `scripts/offline_convert.py`, `import-v2` or `db finalize`. Normal text-digest/FK/SQLite validation moved to `application/catalog_validation.py`.

The following suites existed solely for conversion, salvage or old-workspace admission and were retired: `test_import_archive.py`, `test_conversion_git_domain.py`, `test_conversion_pr_domain.py`, `test_runtime_import.py`, `test_catalog3_import_workspace.py`, `test_catalog3_finalization.py`, and `test_catalog3_time_admission.py`. Their obsolete legacy fixture builders were removed. Timestamp unit/range tests, raw object and document integrity tests, current acquisition/resume behavior, Source identity, coverage v2 and ordinary maintenance remain and are adapted to the new model.

Two imported-first-sync scenarios (five parameterized cases) in the GitHub runtime suite were removed with the importer. Ordinary fresh and resumed GitHub tests remain. The two packaging variants now validate the fresh result model and backup/restore instead of an installed salvage importer. This is intentional retirement of unsupported legacy behavior, not a test-count preservation exercise.

## Parser verification regeneration

The test-only bootstrap is an explicit synthetic local trust fixture. It is excluded from installed distributions; no production environment-variable bypass exists. A source change requires a new genuine evidence artifact:

```bash
uv run --no-sync python scripts/verify_builtin_parser.py --capture artifacts/parser-definition.json
REPO_CATALOG_TEST_BOOTSTRAP=1 uv run --no-sync pytest tests/unit tests/integration tests/e2e -n 4 --junitxml=artifacts/bootstrap.xml
uv run --no-sync python scripts/verify_builtin_parser.py --snapshot artifacts/parser-definition.json --junit artifacts/bootstrap.xml
uv run --no-sync pytest tests/unit tests/integration tests/e2e -n 4
uv run --no-sync pytest tests/packaging
```

The generator rejects a changed implementation/schema snapshot or failed report. The final two commands deliberately run without the bootstrap flag.

## Acceptance

The final unflagged local run passed **1,014 ordinary tests** (96.46s) and **2 packaging tests** (4.71s), with zero failures/errors/skips. Wheel and sdist-derived-wheel tests use isolated installed packages. The genuine packaged verification artifact binds 21 implementation files, semantic settings and all composed DDL to passing evidence for all 11 declared capabilities. Final ordinary/package tests do not use the development bootstrap flag.

Fresh initialization and all composed DDL passed: schema 12, 98 tables, 30 views, 376 triggers and 91 named indexes. `PRAGMA foreign_key_check` returned no rows; `PRAGMA integrity_check` returned `ok`. Coverage claims retain exactly five columns. Ruff lint, format (172 files), whitespace checks and synthetic-report validation passed.

Local environment: Python 3.12.14, SQLite 3.53.1, Git 2.51.1, uv 0.12.23, Linux x86_64. Exact commands, JUnit hashes and DDL/object inventory are in [`2026-10-09-integrated-model.json`](validation/synthetic/2026-10-09-integrated-model.json). The final hosted run, published commit and tree identity are recorded in the submitted PR body after publication. This avoids changing the accepted HEAD merely to add its own CI receipt.

Not executed: live authenticated-source acquisition, physical hardware power-loss testing and non-Linux atomic restore. Synthetic Git/GitHub acquisition and an actual interrupted repair process are tested. Remaining model gaps and their next implementation steps are enumerated in the decision matrix.
