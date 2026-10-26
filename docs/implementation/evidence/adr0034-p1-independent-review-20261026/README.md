# Independent PR192 repair review

**Scoped code verdict: PASS. Integration gate: blocked by failed exact-source
Access CI, pending a successful verified retry.** This is independent reviewer
evidence over PR192, not final PR186 integration approval or release acceptance.

Reviewed commit `55759a2ac02512a17f4ed637c49caccf34ff4763`, tree
`7a28c0626a5b9ca0da613d224b4f939051f24d3d`; PR186 base
`049cc13b129223239cf987590a70c1394e035524`.
The review evidence commit contains this candidate unchanged plus this directory.
No approval carries forward to a different source or final integration tree.

## Findings and closures

- **R192-01 / P1 / FAIL:** at `4dd03f4520ed30d468222623027be513f53b7417`,
  adding `.hgignore` left the identity unchanged and reused legitimate artifacts,
  while a fresh backend build refused the archive. Closed at `aa639262` and
  independently rechecked at the final reviewed SHA.
- **R192-02 / P1 / FAIL:** at `aa639262deb8c1243741bb2643de2e345d19bf78`,
  adding `$XDG_CONFIG_DIRS/uv/uv.toml` without changing environment values left
  the identity unchanged and hid uv's fresh-build refusal. Closed at the final
  reviewed SHA. Historical failures remain in `historical-r192-01.json` and
  `historical-r192-02.json`; they are not relabeled as passes.
- **No new code findings** within the current Linux uv 0.12.19/Hatchling recipe.
  Both retained counterexamples now invalidate, refuse cached/fresh builds and
  restore original reuse on removal. A separate actual-backend check shows that
  cache-ancestor configuration reaches and rejects the extracted-sdist wheel
  build. Arbitrary future hook dependencies and other platforms are not covered.

## Independent checks

The separate reviewer worktree ran these through its verified project runtime,
with `UV_CACHE_DIR` set to a writable workspace cache:

```sh
scripts/local-run.sh pytest -q -n 2 tests/unit/test_build_input_identity.py \
  tests/unit/test_uv_build_configuration.py tests/unit/test_test_efficiency.py \
  tests/packaging/test_sdist_hardening.py --junitxml=focused.xml
scripts/local-run.sh pytest -q -n 2 tests/packaging/test_p1_distribution.py \
  tests/packaging/test_distribution.py --junitxml=packaging.xml
```

**169 + 4 passed**, both exits 0; one shared normal packaging build receipt.
This is 173 focused checks, not a full-suite or release claim. Runtime:
Python 3.12.15, actual loaded SQLite 3.53.1; identity is in `runtime.json`.
No SQLite was separately installed, built, replaced or spoofed.
Author source-byte bindings and compressed JUnit counts were independently checked.

Reproduce the counterexamples using the prepared locked wheelhouse:

```sh
scripts/local-run.sh python \
  docs/implementation/evidence/adr0034-p1-independent-review-20261026/reproduce.py
```

The portable reproducer creates disposable copies, uses the real backend and
prints only factual booleans. It can inspect a historical checkout via
`--repository` and `--wheelhouse`; old defective identities return nonzero.
Original independent results are sanitized in `counterexample-results.json` and
`sdist-context-result.json`. Configuration contents and environment values are
not published. `summary.json` preserves original evidence hashes, exact identities,
limits and reviewer setup/probe failures. Compressed JUnit has hostname removed;
absolute scratch/worktree paths in published results are replaced by labels.
`index.json` hashes the published files after sanitization.

## Exact-source CI and remaining gate

Development run **40282065987 succeeded**. Access run **40282065961 failed**:
`prepare_wheelhouse.py` received `URLError` / TLS `UNEXPECTED_EOF_WHILE_READING`.
The wheelhouse manifest was missing afterward; preflight/scoped Access acceptance
were skipped and dependent acceptance checks failed. This is an external
preparation blocker, not an independently reproduced repair defect. A same-source
retry is authorized separately; no retry success is claimed by this record.

Verified temporary merge `c1394bb494a678fce1da41d86ea6149afb87a4ba` has parents
PR186's base and the reviewed repair HEAD, and the exact reviewed effective tree.
After checking all **38 indexed receipt members**, the reviewer independently
reran `compare_access_regressions.py --strict` against the retained baseline:
**1,851 nodes, 43 inherited Transfer non-successes, zero new/changed failures,
zero missing/unexpected nodes or unexpected skips; comparator exit 0.** Actual
pytest exit was **1**, not an all-tests-pass result. The full CI run still failed.

Both Transfer SQL fences, product source, comparator and proposed ADR status are
unchanged. Remaining integration gates are a verified successful same-source CI
retry and a separate final integration-tree review. No merge or deployment was
performed. Existing `ci-final-tree-verification` lessons already cover both
review findings; this evidence PR does not change skills or author implementation.
