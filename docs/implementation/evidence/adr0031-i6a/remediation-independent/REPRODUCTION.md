# Reproduction and evidence provenance

Start with a clean checkout at `08fbb956c2e470e245146b0dbae747ed0690ea40`.
The tracked product tree was clean throughout execution. New reviewer code and
receipts live only in this evidence directory and were untracked during product
runs. This is development review evidence, not an ADR0001 clean release receipt.

Use the environment's actual Python/SQLite. This execution used Python3.12.14
with built-in SQLite3.53.1. No SQLite component download, build, installation,
replacement, loader override or matrix was performed. Prepare locked dev/docs:

```sh
UV_CACHE_DIR=/workspace/uv-cache UV_PROJECT_ENVIRONMENT=/workspace/review-runtime uv sync --frozen --group dev --group docs
/workspace/review-runtime/bin/python scripts/prepare_wheelhouse.py --output /workspace/review-wheelhouse
```

The first `uv sync` used its default read-only `/home/agent/.cache/uv` and failed
before dependencies were prepared; selecting the writable cache above succeeded.
This was a filesystem setup failure, with no automatic approval rejection.

`run_full.py` and `run_installed_safety.py` are explicitly attributed adaptations
of frozen Author execution drivers. Test execution is new; results are not copied.
Their fixed `/workspace` locations describe this execution. `reproduce/` retains
the actual report-class plugin; copy it to `/workspace/review-tools/` before the
ordinary runner. Set UV_CACHE_DIR=/workspace/uv-cache for every runner, PATH to the selected runtime, TMPDIR to a sufficiently large
workspace location, and REPO_CATALOG_WHEELHOUSE to the hash-verified wheelhouse.
Do not import product source in installed children.

The full runner takes checkout and new output-directory arguments. The installed
runner uses I6A_HARNESS_ROOT, I6A_ARTIFACT_OUTPUT and I6A_SOURCE_COMMIT; the latter
must be the exact frozen public HEAD above. It archives tracked files with git,
builds direct wheel/sdist, rebuilds a wheel from the sdist in an independent
source directory, installs each in its own outside-checkout venv, and checks
in-process module paths and hashes before and after pytest. It reuses existing
product/test harness code; independent harness negative controls are in
`probe_installed_harness.py`.

`verify_installed_completeness.py` independently verifies complete direct/derived
wheel members, every RECORD entry, all 158 product files (including GraphQL),
source/wheel/site-packages equality and actual CLI doctor/module execution.
`authorization/` defines a separate finite principal policy and SQL faults.
`originals/` defines separate evidence coordinates and endpoint/Parent vectors.
The malformed-original probe intentionally exits 1 while ORIGINALS-M1 exists.
All original failures, reviewer setup failures and expected negative subprocess
exits remain evidence; they are never added to passing pytest totals.

`failure-audit/` independently parses original archived receipts, AST and first
failure semantics, then compares new source execution and diagnostic traces.
`ci/` records fresh read-only GitHub metadata, actual job logs and hash-bound
receipts. Redirected CLI log downloads were Forbidden; supported GitHub connector
reads succeeded, and that denied route was not retried. Signed URLs are redacted.

Raw receipts are retained in compressed form when large, with byte hashes in
`artifact-index.json`. Synthetic database work directories, venvs, wheels and
source archives are external execution workspaces and are not committed; their
complete manifests/hashes and actual execution commands are retained. Relative
subreport links resolve in this directory; compressed raw evidence is inspectable
with gzip/zip stdlib tools. Counts across source/focused/installed/diagnostic lanes
overlap and must not be summed into unique acceptance coverage. Concurrent review
runs supply no comparable benchmark timing claim.

The adapted full-suite wrapper returns normally after recording a failed pytest
invocation. Its outer exit0 is not product acceptance: the authoritative inner
ordinary.execution.json, JUnit and journal preserve pytest exit1. Typed subtests
are reconciled separately from the legacy duplicate-call predicate.

The pristine743 reproduction wrapper is failure-audit/run_clean743.py; the actual
historical driver/command/env/hashes are retained in clean743-launch.json and its
raw archive. The wrapper uses
/workspace/i6a-review-clean and /workspace/review-clean-runtime, disables pytest
cache and bytecode writes, and binds every worker's actual loaded product hashes
to clean source before/after tests. It selects exactly the original743 failed
identities, including all444 resolved nodes, with the independent assertion and
exception tracer. Raw full-source and pristine743 invocations stay distinct.
