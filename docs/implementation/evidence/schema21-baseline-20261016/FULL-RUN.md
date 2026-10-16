# Exact committed-source full run

Source: `74f90adae40ae60076dca33629fa2edbf5763474`

Tree: `b11075b53eb0bda4febc710c46c059dc6edf4054`

Result: **3495 passed, 1 failed, 0 errors**, exit1;3496 selected.
The default marker policy excluded these two nodes (not executed):

- `tests/e2e/test_github_sync.py::test_nested_pagination_stress_workload`
- `tests/live/test_smoke.py::test_selected_repository`

The sole failure is `tests/unit/test_build_docs_site.py::test_staging_allowlist_and_transformation`: missing `chrome-headless-shell155.0.8059.79` in the isolated worker HOME. No browser was downloaded or policy bypassed. All228 specified inherited runtime nodes and the additional main-only fencing node passed. Independent strict node/phase reconciliation is recorded in the subsequent integration report.

Raw actual JUnit/journal/stdout and the pre-execution source manifest are in `final-full/`. Gzip is deterministic transport only; original results are unchanged. Runtime source/test/config inputs are frozen; later evidence/procedure commits do not mean tests were reexecuted at those HEADs. This is not an all-green full repository or complete release-acceptance claim.

Use the final integration README and classification for complete before/after, independent review, distribution, and owner merge prerequisites. No merge or auto-merge has been performed.
