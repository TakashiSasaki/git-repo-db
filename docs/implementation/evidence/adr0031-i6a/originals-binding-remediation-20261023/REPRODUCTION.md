# Reproduce Task A without rewriting historical evidence

Use the current environment's selected Python and its own loaded SQLite. Record
`sys.executable`, `sys.version`, `sqlite_version()` and `sqlite_source_id()` before
and inside each artifact venv. Preserve the product safety/capability guards.
Never prepare another SQLite library or version matrix for this procedure.

The tested product/test commit is
`f777d195bd219398a51d2a90553377f61fb39370`, tree
`7ccc8685e06253e2102d46369110c7150d34a587`, directly on frozen #146.
Final publication adds only evidence/skill files. Copy the execution drivers
from this directory's indexed ZIP into external storage before using a separate
checkout of that frozen commit. They are implementation execution helpers,
adapted from attributed #146 helpers, not independent acceptance certificates.

Start by running the stdlib artifact checker:

```sh
python check_artifacts.py
```

Inspect ZIP member names and hashes before extracting selected scripts to a new
external directory. Do not execute arbitrary archive contents or restore any
database. No database, venv, dependency wheelhouse or full product artifact is
included in the evidence ZIP. All original #146 evidence stays in the base tree.

## Prepare dependencies once with a writable cache

The recorded execution uses `/workspace/git-repo-db` and external paths below.
Use a fresh output directory for every attempt and retain nonzero exits.

```sh
export UV_CACHE_DIR=/workspace/uv-cache
export UV_PROJECT_ENVIRONMENT=/workspace/task-a-runtime
uv sync --frozen --group dev --group docs
export PATH=/workspace/task-a-runtime/bin:$PATH
python scripts/prepare_wheelhouse.py --output /workspace/task-a-wheelhouse
export REPO_CATALOG_WHEELHOUSE=/workspace/task-a-wheelhouse
mkdir -p /workspace/task-a-tmp /workspace/task-a-tools
```

Set the writable cache in the parent environment for **all** uv subprocesses,
including offline `uv pip install` into each external artifact venv. An initial
failure caused by omitting it is saved under `installed/`; successful retry is
`installed-v2/`. Artifact/source/member hashes are identical across those attempts.

## Targeted source regressions and unchanged saved counterexamples

```sh
python -m pytest -q tests/integration/i6a/test_originals_revalidation.py \
  tests/unit/test_i6a_regression_bindings.py
PYTHONPATH=src:. python \
  docs/implementation/evidence/adr0031-i6a/remediation-independent/originals/probe_invalid_carrier.py \
  /workspace/fresh-invalid-carrier.json
PYTHONPATH=src:. python \
  docs/implementation/evidence/adr0031-i6a/remediation-independent/originals/probe_originals.py \
  /workspace/fresh-originals.json
```

On the unchanged #146 product freeze the first probe intentionally exits1, with
initial insert/replay duplicate and four failed safety predicates. On the Task A
freeze it exits0 with four exact `INCOMPLETE_ORIGINAL_REPORT` refusals and two
ordinary-fence controls. No normal Transfer route is enabled. Positives use only
the explicit disposable in-memory fixture after verification of the exact schema.

`run_source_safety.py` collects and executes the larger source control cohort,
including actual217 I4/29 I5 nodes plus the new tests. It writes separate
JUnit/journal/typed sidecar and full synthetic SQL rowsets under `source-safety/`.
`run_source_probes.py` runs unchanged #146 authorization vectors from an external
copy so their SQL observations cannot overwrite frozen evidence. Its external
collection has fileless `::test_*` IDs; the actual JUnit `file` attribute and
staged test hash bind the file, and exact starts/JUnit/phase reconciliation is
retained in `source-auth/reconciled-execution.json`.

## One complete ordinary execution and separate diagnostics

Copy `reproduction-tools/i6a_report_types.py` to `/workspace/task-a-tools/`.
With the fixed source checked out and a new empty output path:

```sh
python /external/run_full.py /workspace/git-repo-db /workspace/fresh-full
```

The driver collects all nodes and then ordinary `not live and not benchmark`
nodes. It records runtime and before/after source/test hashes, executes exactly
that selected set once with four xdist workers, saves JUnit/journal/typed reports,
and propagates the actual pytest exit1. Preserve all6076 outcomes rather than
replacing the run with a node-wise combination or a historical count.

The separate `run_diagnostic.py` and `reviewer_trace.py` record actual assertion
statement entries, caught admission stacks, product module origins and input
hashes for the original743 cohort. They take their frozen original identity set
from unchanged evidence. Inspect their recorded command/environment in
`diagnostic743/diagnostic.execution.json` and `diagnostic-bootstrap-correction.json`;
keep this invocation distinct from the full ordinary run. Tracing does not prove
subexpression, spawned-process or spawned-thread coverage.

`analyze_task_a_full.py`, `analyze_task_a_diagnostic.py` and
`analyze_task_a_boundaries.py` retain the actual comparisons. Their binding checks
use the corrected classifier on both ordinary and gzip-only transports. The
original raw #146 full run and its multi-invocation latest map remain separate
comparands. The unchanged #146 stdlib parser is attributed as a second parser;
new captured stacks are implementation-author evidence, not independent review.

The raw full legacy generic phase predicate is false because of57 passing
subtest reports. Inspect the typed audit rather than rewriting that predicate:
every main setup/call/teardown and every typed subtest is separately reconciled.

## Direct and sdist-derived installations

Inspect `run_installed.py` before execution. Its explicit COMMIT/TREE and external
ROOT/OUT/WORK/WHEELHOUSE constants describe this recorded execution. In a fresh
environment either recreate those external paths or change only the external
driver paths and record its new hash. Never change product/DDL/authority/fixtures
to accommodate the harness. The initial executed driver is separately saved as
`run_installed-v1.py`; the successful driver hash is in its execution binding.

The driver archives frozen Git, records **all** source build entries, builds direct
wheel+sdist, extracts the trusted locally built sdist with the data filter, builds
the derived wheel and records every sdist member. Each external venv installs its
artifact and locked dependencies without network and checks exact wheel RECORD,
all158 product member/file bytes, actual SQLite, schema/UDFs/PRAGMAs/fences/FKs and
integrity. Explicit pytest configuration excludes the checkout pythonpath.

Each form actually executes the same626 safety nodes and27 authorization nodes,
with before/after and in-pytest import bindings. It also runs the unchanged19
originals probes, four malformed-carrier checks and two normal-fence controls,
plus CLI doctor/module help. Imported modules must resolve inside that venv's
site-packages; source/test paths are not interchangeable acceptance evidence.

Full build-source and sdist inventories differ from runtime-only input inventories.
The later evidence publication has not had its full sdist rebuilt or qualified.
The intentionally unintegrated #142/#144 minimization series is outside Task A.

## Publication and review

`artifact-index.json` binds every published payload except itself; the Git tree
binds the index. `raw-index.json` binds every ZIP member and preserves its original
relative execution path. CI selected after Draft PR creation is bound to its exact
public HEAD and effective merge tree in the PR body; success means selected
development checks, never full Release acceptance. No workflow dispatch is used.

Task C must run in a new non-Author thread after submission. Reproduce both fixes
against the final public tree and both artifact forms, review refusal precedence
and zero-write/lease/rollback evidence, and retain the299 unimplemented-stage
failures. This implementation did not start that independent review or merge,
release, deploy or retire either Transfer fence.
