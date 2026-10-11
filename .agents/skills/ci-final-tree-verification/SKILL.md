---
name: ci-final-tree-verification
description: Verify git-repo-db CI acceptance against the exact feature HEAD and effective Git tree, including Ruff formatting, changed-file versus full runs, installed wheel/sdist checks, SQLite capabilities, and test-node reconciliation. Use before PR-ready, merge, or release judgments and when CI claims contradict results.
---

# Verify the exact accepted tree

Use `docs/change-aware-ci.md`, `docs/testing.md`, and `scripts/ci_dependencies.json` as the live contracts. A green selected-checks run does not automatically establish complete acceptance.

## Correct development loop

1. Run focused tests locally while editing. Validate both lint **and format** for source/test changes:
   ```bash
   uv run --no-sync ruff check src tests scripts
   uv run --no-sync ruff format --check src tests scripts
   ```
   Passing `ruff check` alone does not imply format compliance.
2. Freeze the corrected commit and record `git rev-parse HEAD` and `git rev-parse HEAD^{tree}`. Distinguish GitHub's temporary test merge commit from the PR feature commit; compare their effective trees.
3. Obtain final complete hosted acceptance on that tree when changing runtime, test, schema, CI shared/policy inputs, or a required integration boundary. For a manual complete run use the workflow's `full=true` option. Do not run an identical full local suite merely because hosted CI also runs it; keep local full validation for release or demonstrated diagnosis.
4. Read the actual workflow job logs and `validation-manifest.json`. Require `full_acceptance=true`, `acceptance_status=full_acceptance_passed`, no unexpected failure/skip, complete selected/executed node reconciliation, and the feature/tested SHA, tree, environment and DDL fingerprint. A passing prose-only or focused run is **not** this gate.
5. On an evidence-only follow-up, verify unchanged `acceptance_input_hash`, source/tree binding and existing complete receipt rather than claiming old tests were rerun.
6. After sequential PR merges, compare the resulting main tree with the previously accepted integration tree. If the effective inputs differ, obtain new relevant validation before declaring success. Never bypass protection rules.
7. Record actual Python/SQLite versions and whether native SQLite UDFs were registered in the connection being tested. Do not introduce permissive fake UDFs to make a fixture pass.

## Frequent failure modes

- Ruff formatting fails even though lint passed.
- An early CI failure skips ordinary/packaging execution, so a reconciliation error is secondary.
- Running a partial PR synchronization plan produces a green job but `selected_checks_only`.
- Old feature SHA checks are reported as though they accepted a newer effective tree.
- A raw SQLite fixture omits native UDF registration required by the composed production DDL.

Use the actual job receipts, not historical counts or a prose claim, to resolve these issues.
