# Schema 21 public-runtime contract checkpoint

Base: `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c` (unchanged main).

ADR 0002 PF-P04/PF-P07 permits safe fresh acquisition after an incomplete
collection. The unresolved-terminal regression now expects two distinct actual
Core collection receipts, no completion marker, and no admitted unresolved resource.
It preserves its node ID for exact inherited-cohort reconciliation.

Two new physical-boundary regressions exercise real JobService/ApiFacts APIs:
completed Core evidence survives Operational loss while old jobs cannot resume;
a separately committed Operational completion cannot certify a rolled-back Core
collection. They reject shadow tables and attached databases explicitly.

Executed with the locked worktree-local dev+docs environment:
`uv run --no-sync pytest tests/integration/test_schema21_runtime_contract.py tests/integration/test_catalog3_current_collection.py -q --tb=short --junitxml=... --journal=...`

Result: **10 passed**, no skipped tests. Raw JUnit, journal and exact-revision
bindings will be retained in the final integration evidence. This is a focused
checkpoint, not complete repository acceptance. No production code or DDL changed.
