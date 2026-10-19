# I3 reproducible stage evidence

Reviewed runtime source: HEAD `35929d3a06c56545c5982fc8fb57c8d97fc965a2`,
tree `b02e8f98c43047ce775e43f7dc088b227d376594`. The final evidence-only
commit has identical runtime inputs; its exact HEAD/tree and read-only follow-up
review are recorded in Draft PR #108, stacked on frozen I1 PR #107.

- `local-focused.json`: 66 I1-only I3 tests passed; exact runtime input digest.
- `registry-local.json`: 1,987 actual JUnit nodes, **1,950 passed / 37 failed**,
  no errors/skips; exact failure-node equality with the frozen I1 baseline.
  Each failure has its direct cause, owner stage and resolution condition.
- `runtime-independent-review.md`: independent exact pushed runtime PASS, with
  all four earlier CHANGES REQUIRED records retained alongside it.
- `distribution.json`: clean committed-source archive; direct wheel and rebuilt
  sdist-wheel installed outside checkout, both passed. Records actual wheel,
  sdist and schema digests, 19 Context tables and v4 wire version.
- `offline-receipt.json`: verified actual development CI receipt, with checkout
  and feature identities/tree, ZIP and member digests. Offline executed zero
  runtime tests; it does not establish full acceptance. The separate registry
  CI executes the focused selection on actual SQLite 3.51.3; its latest run and
  observed results are recorded in the PR body.

The 37 failures are retained: **10 P5 first fail at I2 intake**, including five
Exchange setups that have not reached Exchange; **27 P6 fail through retired
Context registration API dependencies**, tracked for I4. These do not directly
observe an I3 Exchange error. I2 integration must rerun the original five nodes.
No legacy API restoration, skip, xfail or deletion hides them.

Reproduction from a clean checkout, using the locked development environment:

```sh
uv sync --locked --group dev
uv run --no-sync pytest -q tests/integration/i3 --tb=short
uv run --no-sync python scripts/build_p1_schema.py --check
uv run --no-sync python scripts/audit_p1_schema.py --check
uv run --no-sync python scripts/audit_context_registration.py
uv run --no-sync python scripts/audit_callsite_dependencies.py --check
uv run --no-sync python scripts/audit_implementation_boundary.py --check
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
```

For the registry selection, run the unchanged full pytest argument list in
`.github/workflows/access-registry.yml` with `--junitxml`; exit status 1 and the
same 37 downstream nodes are expected at this stage. Compare actual JUnit
`classname`/`name` pairs with `registry-local.json`, retaining parameter IDs and
multiplicity, rather than substituting counts for node equality. P1/P3/Access
and P7 selected tests all passed (150/80/483/255 respectively).

For isolated distribution, archive the committed source into a fresh temporary
directory and run that archive's `scripts/verify_access_distribution.py` using
the locked interpreter. It builds a direct wheel and sdist-derived wheel and
runs installed checks outside the checkout without `httpx`.

The runtime input SHA-256 covers sorted paths under `src`, `tests`, `scripts`,
`.github/workflows` with suffix `.py`, `.sql`, `.json`, `.yml`, `.yaml` (excluding
`__pycache__`), plus `pyproject.toml` and `uv.lock`. Hash each path's UTF-8 bytes,
a NUL, then the raw SHA-256 digest of its bytes. Documentation/evidence updates
are outside this runtime digest. It is not a substitute for final HEAD/tree
identity checks or independent review.

This is focused I3 development evidence. Unselected legacy, e2e and packaging
pytest suites were not executed as full release acceptance. I2 Provider intake,
I4 Query/Search/Backup integration and I5 final integration remain separate.
