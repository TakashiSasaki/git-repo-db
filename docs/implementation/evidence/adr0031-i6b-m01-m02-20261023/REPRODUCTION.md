# Reproduce Author verification

Use a fresh checkout/worktree of executable freeze
`fe9e48bfac750a276b2622da2c50d3d4559de338` or the published evidence HEAD after
checking its equality with `INPUTS.json`. Keep all outputs, venvs and disposable
catalogs outside the immutable build source. Use only the SQLite actually loaded
by the selected environment Python; record `sqlite3.sqlite_version`,
`select sqlite_source_id()`, compile options, interpreter and imported module
origins before testing. Do not obtain a test-only SQLite engine.

The locked dev and docs groups are needed. Use a writable external uv cache and
prepare the locked offline wheelhouse before distribution tests. Preserve setup
failures separately from tests. Use explicit `PATH` for each tested venv so child
`repo-catalog` commands use that installation.

For the two new source regression files, pytest loads the repository conftest
itself; do not load it a second time with `-p tests.conftest`:

```sh
.venv/bin/python -m pytest -o addopts= -q \
  tests/unit/test_context_scan_budget.py \
  tests/unit/test_exchange_received_digest.py \
  --junitxml=/absolute/fresh-output/new.xml \
  --journal=/absolute/fresh-output/new.jsonl
```

For unchanged external saved probes, copy the historical `.py.txt` bytes into a
fresh external probe directory. The saved33 are
`../adr0031-i6b-independent-20261023/wire/test_digest_contract.py.txt` and
`../adr0031-i6b-independent-20261023/planner/test_planner_work_budget_contract.py.txt`.
Use the selected source's explicit `-c pyproject.toml`, external `--rootdir` and
`--confcutdir`, and load its `tests.conftest` once using `-p tests.conftest`.
Collection/JUnit/journal identities and every normal phase must reconcile, not
only passing counts. Each execution JSON stores the actual complete invocation.
The before/after hashes must show byte-identical probes and stale vectors.

`reproduce/` retains the actual source drivers/observer/comparator and probe bytes.
The complete ordinary source lane uses one process invocation with xdist workers,
explicit collected node IDs and separate all/ordinary inventories. Do not combine
partial/nonfinal runs or focused lanes to manufacture a full result. Keep the
actual known 299 unsuccessful nodes, compare primary exceptions/refusals/frames
and diagnostic assertion entry, and retain all extra subtests with their real
controller types.

For artifacts, inspect `distribution/final-root-guard/` build/install commands, frozen source
inventory, full sdist/wheel member manifests and exact input/artifact hashes.
Build direct and sdist-derived wheels independently from the same frozen archive;
install into distinct venvs outside checkout and execute the recorded safety,
wire, independent, Author, saved-contract and new-regression lanes. Record actual
site-packages paths, all installed RECORD rows and before/after product equality.
The original minimal Access smoke is expected to fail at the current unwired
export; retaining its actual failure and unexecuted assertions is required.

The current sdist's exclusion of 120 historical `artifacts/` evidence files is
recorded as a source-retention audit failure, not repaired by this task. Do not
replace that with an all-source-retained claim. All product files must match.

Final HEAD CI verification uses the supported GitHub run/job metadata and logs.
The read-only helper under `ci/` verifies compact receipt markers, bytes/SHA256,
all indexed payloads, feature/base/checkout parents/effective tree and manifest.
It never triggers a workflow, bypasses an unavailable artifact or certifies
independent Release acceptance. Final-HEAD receipts are externally bound in the
PR description and `/workspace/i6b-fix-final-ci` to avoid a circular self-hash.
