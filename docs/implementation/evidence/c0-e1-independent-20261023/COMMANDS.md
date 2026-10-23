# Reproduction and execution receipts

Run from the pinned #139 checkout with its own locked development venv; preserve
existing outputs. Python/SQLite identities are in `raw/local-runtime.json`.

```sh
UV_CACHE_DIR=/tmp/c0-independent-uv-cache uv sync --locked --group dev --python /path/to/selected/python
.venv/bin/python docs/implementation/evidence/c0-e1-independent-20261023/verify_boundaries.py --output /tmp/NEW_EMPTY_BOUNDARY_DIRECTORY
.venv/bin/python docs/implementation/evidence/c0-e1-independent-20261023/run_checks.py
.venv/bin/python docs/implementation/evidence/c0-e1-independent-20261023/reconcile.py
```

The boundary helper requires the exact reviewed source HEAD for its independent
source binding. The published evidence commit adds only this directory; use a
separate checkout of its #139 parent and copy the helper externally for replay.
Do not run `run_checks.py` over an existing evidence directory: it records outputs
under its own `raw/`; copy the review helper directory to a new location first.
Tests execute from the pinned source root and use that checkout's own venv.

`raw/boundary-executions.json` records helper attempt outcomes (1, 1, then 0),
setup and the dependency inventory failure. Calibration child exit 99 is intentional
construction-only evidence; final full emitter child exits are 0/1 as specified.
`raw/checks.json` lists each actual collection/test/lint/format/policy command,
working directory, duration, raw log and exit status. `raw/execution.json` and
`raw/reconciliation.json` independently check completion and unchanged inputs.

The hosted retrieval used live `gh api` read-only calls for
`repos/TakashiSasaki/git-repo-db/actions/runs/39887549016`, `/jobs`, `/artifacts`
and `/logs`; the latter returned the normal run-log ZIP. Its actual `1_offline.txt`
and `0_sqlite-policy.txt` are retained losslessly as `.log.gz` under `raw/`. The supported GitHub connector
`download_workflow_artifact` was called once for artifact 12472429473. The returned
normal file reference was retrieved once (HTTP 200); its URL is deliberately omitted.

```sh
.venv/bin/python docs/implementation/evidence/c0-e1-independent-20261023/verify_hosted.py \
  --log docs/implementation/evidence/c0-e1-independent-20261023/raw/author-hosted-offline.log.gz \
  --run 39887549016 \
  --head 3e2609baa07a9e92c8f2dc4dd1608f311021a1cb \
  --base 8ede5f8f3f525baf90ad8c9b4f3f0729c19a7b82 \
  --artifact docs/implementation/evidence/c0-e1-independent-20261023/raw/author-hosted-artifact.zip \
  --output /tmp/NEW_HOSTED_VERIFICATION.json
```

Fetch the normal #139 merge ref or verified hosted checkout before this read-only
verification; its parents/tree are checked rather than inferred from a CI badge.
Final report/helper/index checks and predecessor-preservation checks are retained
in `raw/final-checks.json`. Publication identity and review-PR CI are independently
read after Draft submission and reported in the PR/final handoff.
