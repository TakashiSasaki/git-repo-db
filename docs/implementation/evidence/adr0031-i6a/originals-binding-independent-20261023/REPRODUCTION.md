# Reproduce the independent Task C review

Freeze public #148 at `268025f67841285d105737b5a0d7bd15b1a6f59c`
(tree `e5fa0437f19f31fa414d488ec10f483ef68f03fa`) in a fresh checkout.
Read AGENTS.md and the applicable local skills/ADR0032 first. Keep the environment's
selected Python and its actual loaded SQLite; do not install or swap SQLite.

Run `python check_artifacts.py` in this evidence directory. Inspect the indexed
ZIP members and extract only reviewed `tools/*.py` helpers to external storage.
Recorded paths are `/workspace/git-repo-db` (source) and `/workspace/task-c`
(external work). Adapt only external driver paths, retain the pinned commit/tree,
and record the new driver hashes. Every execution needs a fresh output path.

```sh
export UV_CACHE_DIR=/workspace/task-c/cache
export UV_PROJECT_ENVIRONMENT=/workspace/task-c/runtime
uv sync --frozen --group dev --group docs
export PATH=/workspace/task-c/runtime/bin:$PATH
python scripts/prepare_wheelhouse.py --output /workspace/task-c/wheelhouse
export REPO_CATALOG_WHEELHOUSE=/workspace/task-c/wheelhouse
mkdir -p /workspace/task-c/raw /workspace/task-c/tmp
```

Record actual Python executable/version and SQLite version/source before work.
Execute one controlled product workload at a time; these timings are not benchmarks.

1. `run_full.py SOURCE NEW_OUTPUT` collects all nodes, selects ordinary
   `not live and not benchmark`, measures inputs before/after and executes the
   complete set once. Expected current exit1 is5,777 PASS/279 FAIL/20 ERROR and57
   passing subtests. `independent_receipt.py NEW_OUTPUT` independently reconciles
   node/main/subtest phases and exit. `compare_full.py` compares separate Author,
   #146 raw and #146 combined-map evidence without combining current outcomes.
   Reconstruct its Author-selected input directory from the indexed parent Task A
   ZIP; its #146 raw inputs are checked against that archive's receipt index.
2. `run_source_extra.py` runs source27 authorization, new132 intake cases and the
   saved originals19 and malformed4/fence2 probes. Corrected output is
   source-extra-v3; retain both prior attempts. `reviewer_policy.py` is unchanged
   #146 finite policy/SQL setup; new vectors are `test_task_c_originals.py`.
3. Inspect and run `run_installed.py`. It archives public #148, records every
   source/sdist member, builds direct and sdist-derived wheels, verifies every
   RECORD/member/source byte and installs each with hash-pinned offline dependencies
   into external venvs. Each form executes626 safety,27 authorization and132 new
   cases separately, saved19 and malformed4/fence2 probes, doctor/help and runtime
   measurements. Stage custom tests under `tests/review_task_c` for the reused
   repository-ID parser. Use different collection/execution sidecars. Actual pytest
   configuration, installed imports/all158 file hashes, schema/PRAGMAs/fences and
   integrity are checked inside pytest. `audit_installed.py` independently audits
   real artifact/receipt bytes.
4. `run_foreign.py` separately executes four explicit foreign allow-all-handle
   vectors in source/direct/derived environments. `audit_foreign.py` reconciles
   every node/phase and full-rowset refusal; the foreign callback must not run.
5. Set `REVIEW_DIAGNOSTIC_COHORT=743` and run `run_diagnostic.py NEW_OUTPUT`.
   `reviewer_trace.py` records actual local assert statement entry, caught
   AdmissionRefused/UnsupportedResourceStage type/code/stacks and loaded source
   paths. `analyze_task_a_diagnostic.py` uses the attributed #146 second parser
   and frozen clean743. Also apply the new independent receipt parser. Run
   `analyze_task_a_boundaries.py` and `check_boundary16.py` for per-node proof.
   Diagnostic outcomes never replace the single full invocation.
6. `check_bindings.py` loads the frozen old classifier and reproduces both actual
   gzip false-consistent results; it checks the fixed classifier on unchanged
   archives and13 separately copied compressed controls. Preserve original hashes.
7. Archive only #146 `src` and `tests` externally and use
   `run_baseline_bound_final.py` for the known-bad product counterexample. It binds
   every imported product module to that archive. The separate OS process receipt
   in `pr146-bound-final/` records expected exit1. This is not current acceptance.

JUnit/journal/typed logs, exits, SQL observations, inputs and helper versions are
indexed. Temporary catalogs, venvs, wheelhouses, full source tarballs and product
artifact binaries are intentionally excluded; complete manifests/hashes are
included. Historical copied full receipts and symlink aliases remain referenced
at unchanged parent paths. No real retained catalog is archived.

Hosted #148 logs and their decoded checksum/index-verified receipt prove selected
development checks only. Do not dispatch release CI, integrate #147/#142/#144,
remove ordinary fences, merge or deploy during reproduction.
