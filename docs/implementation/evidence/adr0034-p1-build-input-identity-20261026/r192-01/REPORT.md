# R192-01: backend control inputs missing from the shared build key

Old PR #192 HEAD `4dd03f4520ed30d468222623027be513f53b7417` / tree
`519c7cbf95382893023fdfea64a5d628f09e04aa` received **independent FAIL**:
R192-01/P1. Adding root `.hgignore` did not invalidate the input key, so a cached
normal artifact hid a fresh backend/sdist rejection. Preserve this finding and
PR #191's earlier REQUEST_CHANGES; neither is rewritten as approval.

Old-head Development and Access CI succeeded. Access run 40277819487 was bound
to merge `ee46ee79550f99638c4477d8ac3c49d11b8373d7`, parents PR #186 and the
old repair HEAD, with exactly the old repair tree. 106 indexed receipt members
were checksum-verified. Broad pytest exited 1: 1,851 nodes, 43 inherited Transfer
non-successes, zero new/changed failures, zero missing/unexpected nodes/skips;
strict reconciliation PASSED. This was scoped evidence, not all tests passing
or release/independent acceptance. Terminal evidence is retained alongside this
report; complete downloaded log/receipts remain under `/tmp/git-repo-db-assessment`.
The direct raw-job-log Azure Blob redirect returned Forbidden; the already
available `gh run view --log` download supplied the receipt. Only exact job/step
presentation columns were removed before the existing strict payload/index
verifier; original downloaded bytes were preserved.

## Correction

Code commit `3a234d57a206be6b2fe07ffe267f8da2a9cd5a63`, tree
`70f4acce2b79f4dc3b53c2cd0617cb09578ad351`.

Inspection of installed Hatchling identified `sdist.get_default_build_data`'s
root `hatch.toml`/`hatch_build.py` inclusion and config's discovered `.gitignore`
and `.hgignore`, including ancestor searches stopped by the corresponding VCS
boundary. uv's local help confirms ancestor/user configuration discovery and
`UV_CONFIG_FILE`.

`backend_control_inputs` now conservatively hashes **every root regular file**,
not just named symptoms, plus inherited VCS controls, ancestor build/config files
and user/system/explicit uv configuration. It records missing discovered settings
and rejects linked or non-file controls. Same-path content changes, addition and
removal invalidate reuse. Existing build-input, artifact-digest, atomic publication,
per-key locking and input-drift checks remain. No rejection gate was weakened.
The current declared Hatchling recipe is covered; this is not a generic oracle
for dependencies read by arbitrary future custom hook programs.

## Red/green evidence

- New unit controls against the old implementation: **4 failed**, including
  `.hgignore`, `hatch.toml`, `hatch_build.py`, `uv.toml`.
- New **real backend** warm-cache tests with old `package_build_inputs` loaded
  from the frozen Git blob and patched in memory: **4 failed**, all DID NOT RAISE.
  This isolates the old identity function; it is not a full old-tree test run.
- Corrected real backend subset: **4 passed**. The test builds a legitimate
  locked/offline distribution, adds a control, requires a fresh builder call and
  actual refusal, then removes the control and checks original-artifact reuse.
- Final focused cohort: **140 passed**, exit 0, 66.11s.
- Final xdist 2-worker cohort: **28 passed**, exit 0, 8.54s.
- Full Ruff lint/format and whitespace checks passed.

Final commands used the existing verified Python 3.12.15 / actual SQLite 3.53.1:

```sh
UV_CACHE_DIR=/workspace/.cache/uv scripts/local-run.sh pytest -q \
  tests/packaging/test_p1_distribution.py tests/packaging/test_sdist_hardening.py \
  tests/packaging/test_distribution.py tests/unit/test_build_input_identity.py \
  tests/unit/test_test_efficiency.py --junitxml=artifacts/p1-cache-repair/r192-01-focused.xml
UV_CACHE_DIR=/workspace/.cache/uv scripts/local-run.sh pytest -q -n 2 \
  tests/unit/test_build_input_identity.py tests/packaging/test_sdist_hardening.py \
  -k 'build_input_identity or real_backend_control or shared_cache_never' \
  --junitxml=artifacts/p1-cache-repair/r192-01-parallel.xml
```

Inputs, raw log/JUnit hashes and compressed red/green evidence are in summary.json.
Tests ran on the same working bytes immediately before the code commit. This
report's evidence-only follow-up is not a test rerun.

No product src, Transfer fence, comparator, I8 or ADR status change. Both fences
and the current 43 known non-successes remain. New exact-head CI and independent
fixed-commit re-review are required before integrating into #186.
