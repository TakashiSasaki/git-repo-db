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

Additional fixture correction checkpoint: Operational job/attempt pairs and
collection progress in `test_catalog3_pr_scope_coverage` use an explicit
Operational transaction, leaving partial domain markers in Core. Git lease and
capacity checks inspect Operational; fixed-ref recovery resolves Operational
acquisition IDs before reading the real Core capture. Core-only CurrentApiState
admission asserts Operational tables are absent instead of counting a nonexistent
Core jobs table. No compatibility views, aliases or production routing changed.

Focused verification of the four additional changed modules: **87 passed**
(`test_catalog3_pr_scope_coverage`, `test_publication_free_current_api`,
`test_catalog3_git_runtime`, `test_git_direct_objects`; actual JUnit/journal).
The earlier untouched-main root cohort reproduced **8 failed, 62 passed**; the
separate canonical full-main baseline supplies the complete original node mapping.

The three-store Agent Skill now records the independently verified physical
observation and safe fresh-acquisition procedure. Whole-stack independent review
and exact committed-tree execution remain required before final acceptance.
