# Reproduce the independent review

Pin source `61e44291e293f773904a0127606e20c8cb83c95e` and first compare all
`INPUTS.json` files with actual Git blobs. Do not apply new product fixes, merge
siblings, alter old assertions or substitute another SQLite. Use the selected
Python's actual loaded library and retain version/source ID, compile options,
PRAGMAs, imports, all exits and unexecuted stages.

The executed source environment was prepared with:

```sh
UV_PROJECT_ENVIRONMENT=/workspace/rr-env UV_CACHE_DIR=/workspace/uv-cache \
  uv sync --locked --group dev --group docs
/workspace/rr-env/bin/python scripts/prepare_wheelhouse.py \
  --output /workspace/rereview-wheelhouse
```

The read-only `broad/tools/run_source.py.txt` uses the actual original driver's
collection/execution/journal helpers. Restore its `.py` suffix and its neighboring
observer files to `/workspace/rereview-core/tools/`; inspect its recorded paths
before execution. Paths and the editable-venv assertion are harness bindings,
not product changes. For a different workspace, change only those bindings and
preserve the modified harness hash separately. Never reuse populated output or
basetemp directories.

```sh
/workspace/rr-env/bin/python /workspace/rereview-core/tools/run_source.py \
  --root /workspace/git-repo-db --out /workspace/rereview-core/source-full \
  --mode full --workers 4
/workspace/rr-env/bin/python /workspace/rereview-core/tools/run_source.py \
  --root /workspace/git-repo-db --out /workspace/rereview-core/source-diagnostic \
  --mode diagnostic --workers 4
```

Both actual invocations exit1 because known failures remain. A diagnostic is
never part of the complete ordinary count. The full command, start time, elapsed
time and actual child exit are in `broad/source-full/ordinary.execution.json`.
Observe original report classes to distinguish genuine SubtestReports from
ordinary phases. Use `broad/tools/independent_compare.py.txt` with historical
#152 `broad/full-final-v3` or `diagnostic745`, the fresh output, `--name ordinary`
or `diagnostic`, and a fresh comparison directory. It independently checks the
historical input hashes against actual #152 Git blobs, not merely its prose.

For focused probes, restore the original bytes recorded by `TRANSPORT.json` and
the scoped transports. `.gz` files contain losslessly compressed originals;
`.py.txt` is the original executable Python text. Verify both transport and
decompressed SHA256 before use. Exact original commands are retained in each
scope's execution/commands JSON. External probes use the selected source's
explicit `-c pyproject.toml`, external root/confcutdir and exactly one
`tests.conftest` registration. They must not append themselves to ordinary
source collection or bypass its offline guard.

`planner/`, `wire/` and `admission/` retain new independent source probes and
their preserved failed harness attempts. `wire/reused/` separately replays
byte-identical normal208, Author34 and saved33. Author34's design remains
attributed. Source full subsets are exact node intersections recorded in
`broad/source-full/subsets.json`; I4/I5 here name historical p3 modules.

Distribution reproduction uses the recorded `distribution/prepare.py.txt`,
`review_distribution.py.txt`, `install_validate.py.txt`, extra/fresh/smoke drivers
and exact execution binding. Build fresh direct wheel and sdist-derived wheel
independently from one complete Git archive. Use two external venvs and external
test directories; assert site-packages and subprocess CLI origin. The indexed
member, metadata, RECORD, source retention and product equality results are
reproducible inputs, not a substitute for running the installed entry points.
Do not copy the review's venvs or disposable databases into the repository.

Hosted verification is read-only. `ci/verify_independent_ci.py.txt` verifies raw
run/job logs and the delivered receipt ZIPs, without executing their contents.
All 21/121 payloads are inside those ZIPs; `ci/DELIVERY.json` records intentionally
omitted redundant expanded copies. Retain incomplete raw receipt views and
require exact BEGIN length/SHA and END SHA; the Access recovery uses only
complementary observed chunks. `ci/compare_source_hosted.py.txt` compares the
fresh source 299 with the actual hosted lanes, preserving differences.

The final evidence PR's own exact HEAD/tree/CI binding belongs in its PR body
and final handoff. It cannot be inserted into a committed file without changing
that file's enclosing commit/tree. A green development receipt is never Release
acceptance, and no workflow dispatch, merge or deployment is part of reproduction.
