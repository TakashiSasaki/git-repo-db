---
name: ci-final-tree-verification
description: Verify git-repo-db CI status and test execution against the exact feature HEAD and effective Git tree. Distinguish ordinary development checks (lightweight CI + local focused testing) from explicit release acceptance (independent local + hosted complete execution with test-node reconciliation). Use before PR submission, review, or release qualification.
---

# Verify the exact accepted tree

Use `docs/change-aware-ci.md`, `docs/testing.md`, and `scripts/ci_dependencies.json` as the live contracts. Distinguish ordinary development validation from explicit release acceptance.

## Development validation loop (ordinary PRs and stacked iterations)

1. Run focused tests locally while editing. Validate both lint **and format** for source/test changes:
   ```bash
   uv run --no-sync ruff check src tests scripts
   uv run --no-sync ruff format --check src tests scripts
   ```
   Passing `ruff check` alone does not imply format compliance.
2. Freeze the corrected commit and record `git rev-parse HEAD` and `git rev-parse HEAD^{tree}`. Distinguish GitHub's temporary test merge commit from the PR feature commit; compare their effective trees.
3. In ordinary development, local verification is the primary correctness method. Hosted GitHub Actions runs inexpensive static checks, formatting/lint, configuration verification, and smoke checks. Do not require or expect complete hosted test suite execution for ordinary development PRs.
4. Verify that hosted development CI passed its planned checks. A passing development CI run (`acceptance_status=development_checks_passed`) confirms development infrastructure integrity; it does not represent complete release acceptance.
5. On an evidence follow-up, verify unchanged input hashes, tree binding, and recorded test evidence rather than claiming unexecuted tests were rerun.

## Explicit release acceptance loop (release qualification only)

1. Release validation is an explicit, user-invoked operation requiring complete independent testing in both environments (local AND hosted).
2. Local requirement: execute the complete applicable ordinary pytest suite and packaging checks locally on a clean tree, generating a verified receipt:
   ```bash
   python scripts/ci_execute.py receipt --output-dir artifacts/ci-profile
   ```
3. Hosted requirement: execute the complete hosted suite (invoked via workflow dispatch with `mode: release`), isolated wheel/sdist packaging tests, schema/integrity checks, and exact test-node reconciliation.
4. Read the actual workflow job logs and `validation-manifest.json`. Require `full_acceptance=true`, `acceptance_status=complete_release_passed` (or `hosted_release_passed` reconciled via `python scripts/ci_execute.py reconcile-release`), zero unexpected failures/skips, exactly-once selected/executed node reconciliation, and exact input binding.
5. An explicit release validation does not authorize merge, release, publication, or deployment without separate explicit owner authorization.

## Frequent failure modes

- Ruff formatting fails even though lint passed.
- Mistaking a passing development check (`development_checks_passed`) for complete release acceptance.
- Attempting to force full hosted test execution on ordinary development PRs where local verification suffices.
- Stale test receipts presented against a changed Git tree or differing input hash.
- Synthetic or fabricated test node IDs presented in local receipts (rejected fail-closed by strict reconciliation).
- A raw SQLite fixture omits native UDF registration required by the composed production DDL.

Use actual receipts and explicit validation modes, not historical counts or prose claims, to resolve these issues.
