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
   Passing `ruff check` alone does not imply format compliance. Before committing
   newly generated/untracked artifacts, stage the intended files and run
   `git diff --cached --check`; plain `git diff --check` does not inspect untracked
   content. Fix whitespace in the generator and regenerate instead of hand-editing
   an output that the deterministic checker will later reject.
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


## Focused-profile bootstrap failure: preserve evidence and use direct pytest

If `scripts/ci_profile.py profile ...` fails before collection with
`ValueError: option names {'--journal'} already added`, inspect both registrations
before interpreting the run as a product-test failure. The current wrapper loads
`-p scripts.ci_journal`; `tests/conftest.py` also delegates `pytest_addoption` to
that module. Loading both registers the same option twice. A missing JUnit file
then reflects failed bootstrap, not passing or failing test assertions.

Preserve the failed profile's output, command and exit status. When this duplicate
registration is present and CI-infrastructure changes are outside the task's
scope, use the existing conftest registration once through direct pytest:

```bash
focused_artifact_dir=$(mktemp -d)
uv run --no-sync pytest tests/integration/architecture_spikes -q \
  -o junit_family=xunit1 \
  --junitxml "$focused_artifact_dir/junit.xml" \
  --journal "$focused_artifact_dir/journal.jsonl"
```

Use the task's actual focused targets. Do not add `-p scripts.ci_journal` to this
fallback. Check the exit status, selected/executed node IDs, JUnit and journal;
record HEAD/tree and commands with these raw artifacts. A direct run does not
create a wrapper profile/complete release receipt. Report the wrapper failure
separately, and remove this workaround only after verifying that option
registration has one owner and the wrapper succeeds. The implementation-preparation
run diagnosed the duplicate registration and verified this direct invocation; it
did not repair unrelated production CI tooling or claim release acceptance.

## Recover bounded CI receipts from the job log

If a completed run's artifact download is unavailable (for example, the artifact
blob endpoint returns HTTP 403), do not infer receipt contents from a green badge
or change network policy. This repository's tests workflow also emits a bounded
receipt ZIP in its job log. Retrieve the normal GitHub log through the supported
CLI and inspect the actual emitted `CI_RECEIPTS_BEGIN_V1`, `CI_RECEIPTS_DATA_V1`
and `CI_RECEIPTS_END_V1` records. The implementation-preparation run verified this
fallback after an artifact-endpoint 403; the same completed run's log was readable.

```bash
receipt_work_dir=$(mktemp -d)
gh run view RUN_ID --log > "$receipt_work_dir/job.log"
```

1. Parse actual timestamp-prefixed output records, excluding the echoed shell
   script that contains the marker names. Concatenate DATA payloads in order and
   strictly base64-decode them. Verify the exact BEGIN byte length and SHA-256;
   require a matching END digest. Fail closed on missing/duplicate/truncated blocks.
2. Read the ZIP in memory; do not execute contents or blindly extract paths.
   Check every `receipt-index.json` entry's byte count and SHA-256 against its
   archive member. Read `receipt-binding.json` and `validation-manifest.json`.
3. Check run ID/attempt, feature SHA, checkout HEAD and tree. Fetch the actual
   PR merge ref and compare its effective tree with the feature tree; GitHub's
   temporary merge commit SHA normally differs. The manifest's acceptance input
   hash is a separate input contract, not a replacement for identity checks.
4. Report `acceptance_status`, `full_acceptance`, actual hosted executed tests
   and unexecuted coverage. `development_checks_passed` with zero hosted runtime
   tests does not establish full acceptance or validate every local test file.
5. Preserve the verified receipt digest and run URL in the PR/handoff. This is
   an alternative retrieval of the workflow's existing receipt, not a new receipt
   format or permission to bypass a blocked destination, re-sign evidence, claim
   unavailable artifacts were downloaded or launch release qualification.

If `gh run view RUN_ID --log` exits successfully but produces an empty file,
do not classify that as an empty job or missing execution. Retrieve the supported
run-log ZIP using `gh api repos/OWNER/REPO/actions/runs/RUN_ID/logs` and inspect
its text members without executing or blindly extracting them. The final P7
integration-readiness review reproduced empty CLI logs for both Development and
Pages, then obtained actual logs through this REST endpoint. Apply the same
bounded receipt checks above to actual timestamped output, excluding echoed
shell source. Preserve the empty-log attempt and the successful retrieval method;
never infer runtime coverage from a successful API/CLI exit alone. This fallback
does not authorize a new workflow, release validation, deployment or policy bypass.

## Bind child Python processes to the intended worktree

In parallel worktrees, use a separate editable environment for each tested tree:

```sh
uv sync --locked --group dev
uv run --no-sync python -c 'import repo_catalog; print(repo_catalog.__file__)'
uv run --no-sync pytest <focused-targets> -q
```

P2/P3 review reproduced a misleading failure when a reviewer launched pytest with
another worktree's venv and supplied only `PYTHONPATH`: the repository's autouse
network fixture replaced `PYTHONPATH` for child processes. Main-process imports
used the intended source, but child audit commands imported the other editable
checkout. Repeating with the tested worktree's own `uv` environment corrected the
binding and passed the unchanged tests. Record the working directory, interpreter,
actual imported module paths and child environment behavior when diagnosing this.
Do not infer subprocess source identity from the parent's import path or a passed
`PYTHONPATH` alone. This procedure retains the network guard; do not remove it to
force another checkout to import.

For imported contract replay tests, reconcile collected node IDs with JUnit
`classname` and test `name`, not its `file` attribute alone. P2's imported P1 test
functions correctly run with the production fixture under a P2 collection module,
while JUnit `file` still identifies the original P1 function definition. Counting
by that attribute would misclassify production verification. The paired receipts
verify all selected IDs against journal starts, each phase and JUnit identities.
For each installed distribution, also assert duplicate-free equality among the
collected node set, normalized JUnit identities and journal starts, with exactly
one setup/call/teardown result per executed node. Equal passing counts alone can
accept substituted node sets. Independent review of the integration-readiness
driver found that gap; explicit three-way identity checks passed on both stored
installed P7 executions. Keep these checks even when their counts agree.
