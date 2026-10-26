# ADR 0034 shared-build input identity repair

Author checkpoint; independent review is pending. This does not supersede PR
#191's historical REQUEST_CHANGES or claim release acceptance.

Base PR #186: `049cc13b129223239cf987590a70c1394e035524`, tree
`4aaeb468ec21fb40aae00776e75c4032e47052e8`.
Repair: `a183ca07076f7ae9dcf51f82b7946439490a1f19`, tree
`ebe257ea5b2edee57747c597cbd736c79bd3bba0`.

## Finding mapping

PR #191 P1: a normal shared build could bypass the poisoned-sdist gate because
ready.json bound output hashes but not the source/build inputs.

- `package_build_inputs` binds working product bytes (including untracked files),
  required packaging files, uv.lock presence/content, the helper/checker/runner
  contract, selected Python and uv executable bytes, wheelhouse files and build
  environment. Identical content can reuse across paths; changed content at the
  same path cannot. The current recipe is the repository's declared Hatchling
  recipe, not a universal discovery mechanism for future custom build hooks.
- Both packaging fixtures use the same sanitized environment and checked runner.
  Test/worker display coordinates are excluded from input identity. Raw environment
  values are not written into receipts. Real focused packaging used one complete
  normal wheel/sdist-wheel build key; synthetic normal/hostile controls have their
  own keys and are not real package-build measurements.
- `build_once` requires an input-fingerprint callback, locks per key, rechecks
  inputs before building, before receipt publication and before returning, seals
  exact artifact hashes, and atomically publishes an fsynced receipt. No receipt
  permits only a full checked rebuild; bad/mismatched receipts and changed/missing
  sealed artifacts fail closed. The supported cache assumes the input tree remains
  stable during execution; detected changes fail rather than certify mixed inputs.
- `test_shared_cache_never_launders_hostile_sdist` tests normal-to-hostile and
  hostile-to-normal order with the real poisoned archive/checker. The original
  refusal-before-extraction/rebuild/install test remains in the focused cohort.
- `test_build_input_identity.py` covers identical and distinct trees, same-path
  edits, untracked product bytes, lock/config/environment/wheelhouse/runner changes,
  missing/corrupt evidence, mid-build mutation, exact artifact hashes and xdist
  one-builder/many-reader behavior. Existing cache recovery/corruption tests remain.

## Verification

Python 3.12.15, actual loaded SQLite 3.53.1; full identity and source ID are in
summary.json. Environment prepared using the supported workspace `--home` option.
No SQLite component was separately installed, built, replaced or spoofed.

Commands (one workload at a time):

```sh
UV_CACHE_DIR=/workspace/.cache/uv scripts/local-run.sh pytest -q \
  tests/packaging/test_p1_distribution.py tests/packaging/test_sdist_hardening.py \
  tests/packaging/test_distribution.py tests/unit/test_build_input_identity.py \
  tests/unit/test_test_efficiency.py --junitxml=artifacts/p1-cache-repair/focused.xml
UV_CACHE_DIR=/workspace/.cache/uv scripts/local-run.sh pytest -q -n 2 \
  tests/unit/test_build_input_identity.py --junitxml=artifacts/p1-cache-repair/xdist.xml
scripts/local-run.sh ruff check src tests scripts
scripts/local-run.sh ruff format --check src tests scripts
```

Focused: **130 passed**, exit 0, 56.33s. xdist: **16 passed**, exit 0, 2.20s.
Lint/format and staged whitespace checks passed. Source-byte hashes, exact package
artifact SHA-256s, compressed raw JUnit/logs and prior environment failures are
retained in summary.json and neighboring gzip files. These tests ran on the
recorded working bytes immediately before the repair commit; the evidence-only
follow-up is not a test rerun.

No product src, production DDL/fingerprints, Transfer SQL fences or regression
comparator changed. The 43 inherited Transfer non-successes remain the existing
scoped evidence; no broad regression rerun or new failure reconciliation is
claimed here. ADR 0034 is still proposed at this checkpoint. No I8 implementation,
release, deployment or main merge is included.

## Review handoff

Review the complete repair against the fixed PR #186 base, including the skill
lesson. Verify both callers, runner/environment equivalence, input coverage and
fail-closed cache behavior. Review CI against the final Draft PR HEAD separately.
Do not treat this author report or passing checks as independent approval.
