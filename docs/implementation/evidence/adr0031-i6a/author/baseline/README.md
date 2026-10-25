# Frozen #141 baseline execution

This is new author-supporting development evidence, not release acceptance. The
isolated detached worktree `/workspace/i6a-baseline` is frozen at #141
`dc6e663ea90e55210ed5674cae6c332f66a4ac18`, tree
`3d70218ecf98f751eb550e6a328a21f65069066f`. Product, historical tests and
historical evidence were not modified. Root implementation proceeds separately.

The selected environment Python is 3.12.14 at
`/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3.12`.
It directly loads its built-in SQLite 3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
No SQLite component was obtained, installed, replaced or overridden. The actual
product capability/safety check succeeded. The locked development and docs groups
were installed in `/workspace/i6a-baseline-venv`, with writable UV cache
`/workspace/i6a-uv-cache`; the editable product origin is the isolated worktree.
The dependency setup, runtime identities, loader mappings, wheelhouse manifest,
input hashes and process receipts are retained here.

## Complete collection and historical reproduction

Collection found 5,744 nodes: 5,742 ordinary and two live/benchmark nodes. The
historical I5 broad cohort contains 3,137 ordinary nodes, exactly the node multiset
in the preserved author ZIP's `author-3.53.1/regressions.selected.txt`.
`historical-node-selection-comparison.json` proves zero additions/removals.

| Separate execution | Result | Wall time | Workers |
| --- | --- | --- | --- |
| I5 Transfer Admission | 29 passed | 1.967 s | 0 |
| I4 Transfer SQL | 217 passed | 9.338 s | 0 |
| Historical broad cohort | 3,058 passed, 59 failed, 20 setup errors | 142.170 s | 4 |

The 29/217 dedicated runs overlap the historical broad cohort and are not added
to its unique-node count. No node was skipped/xfail. The historical broad process
exited 1; this failed outcome is preserved. Its JUnit and journal reconcile exactly
to all 3,137 selected nodes and include completed process/finish receipts.
The 456 code/test/script/workflow/configuration input files, HEAD and tree stayed
identical, and the isolated checkout stayed clean.

All 79 non-successes match the historical nodes, phases, exception types and
first-failure source path/functions; none is added or resolved. Seventy-five raw
messages match exactly. Four P5 installed-package AssertionError raw messages
differ in pytest temporary roots/usernames/run numbers and CompletedProcess repr
clipping. Their original `assert 1 == 0`, causal
`I2_IDENTIFICATION_WIRE_UNSUPPORTED`, installed product frames and script frames
match. Both the unnormalized comparison and the supplemental semantic analysis
are preserved; these remain failures.

## Additional ordinary coverage

The disjoint remaining 2,605 ordinary nodes all passed in 411.593 seconds
(process wall time; pytest reported 411.10 s and 57 passing subtests). Both ordinary
cohorts together executed all 5,742 collected ordinary nodes exactly once: 5,663
passed, 59 failed and 20 setup errors, with no skips/xfail. Their elapsed process
times sum to 553.763 seconds; this is two sequential disjoint invocations, not a
single pytest invocation or a benchmark speed comparison. The separate dedicated
I4/I5 checks overlap and are excluded from this aggregate.
`ordinary-outside-historical-unexecuted.txt` retains its original pre-execution
selection name, and its nodes were subsequently executed by `remaining-ordinary`.
`full-ordinary-summary.json` binds the disjoint node union, unchanged inputs, clean
source and completed per-cohort JUnit/journal/process receipts. The two live/benchmark
nodes remain unexecuted. Large raw artifacts are gzip-compressed losslessly;
`compression-index.json` binds both original and compressed byte identities.

## Reproduction

Exact executable/argv/cwd/timing/status is in each `*.execution.json`; exact
selections are in `*.selected.txt`. The archived launcher sources are in
`../raw/baseline-{prepare,run,remaining,compare}.py.txt`.

The historical command is the existing `verify_i5_offline.run_cohort` command:

```sh
PATH=/workspace/i6a-baseline-venv/bin:$PATH \
UV_CACHE_DIR=/workspace/i6a-uv-cache \
UV_PROJECT_ENVIRONMENT=/workspace/i6a-baseline-venv \
REPO_CATALOG_WHEELHOUSE=/workspace/i6a-wheelhouse \
/workspace/i6a-baseline-venv/bin/python -m pytest -q \
-o addopts=--strict-markers -o junit_family=xunit1 \
@/workspace/git-repo-db/docs/implementation/evidence/adr0031-i6a/author/baseline/regressions.selected.txt \
--junitxml=/workspace/git-repo-db/docs/implementation/evidence/adr0031-i6a/author/baseline/regressions.xml \
--journal=/workspace/git-repo-db/docs/implementation/evidence/adr0031-i6a/author/baseline/regressions.jsonl \
-n 4 --dist worksteal
```

Run it from the isolated worktree, using a **new empty output directory** and
correspondingly updated paths; the journal is append-only and existing receipts
must not be overwritten. The launchers use direct pytest, preserving the existing
conftest's journal registration exactly once.

Relevant existing skills were used: efficient-repository-investigation,
ci-final-tree-verification and lessons-to-skills. No new generalizable procedure
beyond those existing skills has been established by this baseline setup.

The legacy phase helper does not distinguish pytest 9 unittest subTest reports.
The 2,605-node remainder has 57 passing subtests recorded as extra call reports;
its strict no-duplicate-call check therefore fails. Selected nodes, JUnit nodes,
journal starts and setup/teardown counts still match exactly. The raw ambiguity
is preserved, and this is not claimed as strict phase acceptance. The corrected
source run records actual report types/context in a separate sidecar.
