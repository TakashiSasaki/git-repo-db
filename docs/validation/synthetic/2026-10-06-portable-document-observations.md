# Portable namespaces and direct document observations: PASS

- Baseline: `1ce7fccdb63ab7de74daf6694d2c7187fcddd835`.
- Clean substantive revision: `b6cca875b9a303989bc8947dc56dddb04d7b9ec2`, branch `refactor/portable-document-observations`.
- Format: `repo-catalog/catalog3`, schema 5; 73 ordinary tables. DDL SHA-256: `38464e3d77d5a71f9f455ccce4c82311f7df871d4acb20680e4d0e5b730348c8`.
- Actual local environment: Python 3.13.5, SQLite 3.46.1, Git 2.47.3, uv 0.10.0. Normal delete journal mode; unchanged WAL safety restrictions.

## Executed

Current ordinary acceptance: **358 passed**, 44.97 seconds (pytest time), four workers. Independent installed wheel and sdist-derived wheel: **2 passed**, 3.08 seconds, sequential. The existing planner, collection, profile and gate reconciled **360 selected / 360 executed exactly once**, 41 files, no failures/skips/unexecuted ordinary files. Ruff lint/format (114 Python files), STRICT/FTS doctor and prose validation passed. Adjacent JSON contains the exact commands, profile times and selected node IDs.

New regression tests bind the decisions to canonical UUIDv4 service namespaces, namespace-scoped provider IDs without URL merging, document composite keys without surrogate/version columns, exact UTF-8 SHA-256 identity, artificial collision failure/rollback, direct A->A->B->A observations, replay fencing, same-document current pointers and unresolved-current coverage. Source current-version assertions are tested against real observations, including timestamp ties, unknown timestamps and orphan versions; no fabricated observation is admitted.

Existing acceptance covers normal Git collection, query/search, REST/GraphQL history and interrupted resume, deterministic SQL-work scaling, conditional detail checks and saved-listing reuse on first sync after v2 salvage, source protection, typed evidence, integrity checks and backup/restore. Installed checks create fresh schema-5 catalogs outside the checkout, perform Git collection/search/index/check, and exercise both CLI entry points.

## Environment and limits

This editing container cannot resolve external hosts. Public tracked source and locked Linux wheels were supplied through a temporary read-only GitHub Actions artifact. Each supplied wheel was checked against `uv.lock`; platform-conditional Windows colorama is not required. The development virtualenv points at the working source using a disposable `.pth` file; isolated distribution checks install real built packages and confirm their origin outside the checkout.

An earlier full invocation was cut off by the tool timeout before completion, so it is not a successful validation claim. The completed clean-revision run above is the acceptance record. Prior focused test failures during editing were corrected; their partial results are not added to the final count.

No real user database/cache, retained-source discovery, public provider acquisition, multi-catalog exchange, open-ended provider support, release publication or active-catalog cutover was performed. Temporary implementation transport files are absent from the final application tree. Historical v2 schema resources and historical validation/design snapshots remain unchanged. Subsequent evidence-only edits do not imply another full test execution.
