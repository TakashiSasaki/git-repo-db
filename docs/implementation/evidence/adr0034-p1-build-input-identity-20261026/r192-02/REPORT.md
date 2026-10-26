# R192-02: bind uv configuration discovery in every build context

Old HEAD `aa639262deb8c1243741bb2643de2e345d19bf78`, tree
`4beaf56d86453f1902afe35e9a4e006b316fd392`: independent re-review closed
R192-01 but returned **scoped FAIL, R192-02/P1**. Creating an invalid
`$XDG_CONFIG_DIRS/uv/uv.toml` after warming the cache did not change the key;
a fresh uv build refused the file. Keep this FAIL and the earlier findings.

Old Development run 40279533110 and Access run 40279533104 both succeeded.
106 indexed Access receipt members were verified; the actual temporary merge's
tree equals the old feature tree. Broad pytest exited 1 with 1,851 exact nodes,
43 inherited Transfer non-successes and zero new/changed failures; strict
reconciliation PASSED. These results do not clear the independent FAIL or verify
the corrected source. See old-head-terminal-ci.json; full original downloaded
log/receipts are preserved in `/tmp/git-repo-db-assessment/access-40279533104*`.

## Established contract and correction

Code `104c77666005f83b056455a5532bda5a1eecee85`, tree
`8e67ff8221b43a879fff9d4eec76ca7e2369a99f`.

The actual selected tool is Linux uv 0.12.19. Primary source is pinned to tag
commit [`bea138450f0e620a4ce5765b0e38cff7b9f0799f`](https://github.com/astral-sh/uv/tree/bea138450f0e620a4ce5765b0e38cff7b9f0799f):
[uv-dirs](https://github.com/astral-sh/uv/blob/bea138450f0e620a4ce5765b0e38cff7b9f0799f/crates/uv-dirs/src/lib.rs),
[uv-settings](https://github.com/astral-sh/uv/blob/bea138450f0e620a4ce5765b0e38cff7b9f0799f/crates/uv-settings/src/lib.rs),
and [top-level selection](https://github.com/astral-sh/uv/blob/bea138450f0e620a4ce5765b0e38cff7b9f0799f/crates/uv/src/lib.rs).
The etcetera 0.11.0 source crate checksum was matched to uv's pinned Cargo.lock;
its XDG strategy confirms absolute XDG_CONFIG_HOME or HOME/.config fallback.
Source hashes are recorded in summary.json; no dependency was installed from
this inspection and no real home configuration contents were copied.

| Source/context | Verified rule and coverage |
| --- | --- |
| Project | uv.toml precedes pyproject tool.uv; workspace/project ancestor discovery is conservatively bound by source controls. |
| User | Absolute XDG_CONFIG_HOME/uv/uv.toml; otherwise HOME/.config/uv/uv.toml. Missing files and mutations are bound. |
| System | Ordered XDG_CONFIG_DIRS candidates; unset/empty defaults to /etc/xdg; first empty component stops XDG traversal; /etc/uv fallback. All candidates, including absence, are conservatively hashed. |
| Overrides | Absolute UV_CONFIG_FILE contents are bound. Actual uv tests check explicit override and UV_NO_SYSTEM_CONFIG masking; this helper does not disable config discovery. |
| Source vs sdist cwd | Cache/build ancestry participates in the key. Receipt schema 2 seals generated child configuration and key-specific ancestry, checked before returning artifacts. |
| Unsupported contexts | Linux only. Relative external settings, relative HOME and UV_PROJECT/UV_WORKING_DIR redirects refuse reuse before build because source/sdist CWDs differ. No Windows/macOS claim. |

All file contents are represented by hashes; no config values or credentials are
emitted. Masked candidates are hashed conservatively, so changing an ignored file
can cause an extra build, but identical inputs reuse efficiently. Existing build
flags, uv's own priority/rejection rules, artifact hashes, per-key locking,
input-drift checks and atomic publication remain. This is not a generic dependency
discovery guarantee for arbitrary future custom build-hook programs.

## Test matrix and evidence

- Original XDG warm-cache regression against the old implementation: **1 failed**.
- Actual backend tests with old aa639262 identity loaded from the Git blob and
  patched in memory: **3 failed**, all DID NOT RAISE (single XDG dir, earlier
  candidate appearing, later candidate appearing). This is an isolated old-identity
  control, not a full old-tree run.
- Actual uv matrix covers ordered dirs, later masking, empty-component stopping,
  explicit override, system disable, user HOME and XDG paths. uv itself decides
  rejection/priority; no hardening check is weakened.
- Unit coverage includes defaults/order, additions/same-path changes, content
  privacy, unsupported contexts, six build-ancestor control kinds and generated
  or key-specific configuration tampering.
- Final focused: **173 passed**, exit 0, 96.39s.
- Final xdist 2-worker: **61 passed**, exit 0, 24.02s.
- Ruff lint/format and whitespace passed (474 files formatted).

One intermediate unit run was 59 passed / 1 failed because its synthetic helper
used a file named sdist and the new test attempted to create sdist/package beneath
it. The test path was corrected to a generated directory; this was a test-fixture
error, not a product/configuration result. The earlier 24-case matrix and the
58-pass intermediate unit checkpoint were not rerun merely to repeat evidence.

Final commands through the unchanged verified Python 3.12.15 / SQLite 3.53.1:

```sh
UV_CACHE_DIR=/workspace/.cache/uv scripts/local-run.sh pytest -q \
  tests/packaging/test_p1_distribution.py tests/packaging/test_sdist_hardening.py \
  tests/packaging/test_distribution.py tests/unit/test_build_input_identity.py \
  tests/unit/test_uv_build_configuration.py tests/unit/test_test_efficiency.py \
  --junitxml=artifacts/p1-cache-repair/r192-02-focused.xml
UV_CACHE_DIR=/workspace/.cache/uv scripts/local-run.sh pytest -q -n 2 \
  tests/unit/test_build_input_identity.py tests/unit/test_uv_build_configuration.py \
  tests/packaging/test_sdist_hardening.py \
  -k 'build_input_identity or uv_build_configuration or real_backend_control or shared_cache_never or real_uv_configuration' \
  --junitxml=artifacts/p1-cache-repair/r192-02-parallel.xml
```

Hashes, artifact receipts and compressed red/green JUnit/logs are retained.
Final runs used the recorded working bytes immediately before the code commit;
this evidence-only follow-up is not a test rerun. Product source, both Transfer
fences, comparator, remaining 43 known non-successes and ADR status are unchanged.
New exact-head CI and independent fixed-commit re-review are required before
integrating into #186. No integration, merge, release or I8 work is included.
