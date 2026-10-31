# Opt-in Core independence: operation and test matrix

This is a source and test map for the opt-in P1/P5/P6 implementation at main
`4404a06870f3b7f9427278337debbddba41c559c`; it is not a new design decision,
a release claim, or activation of the normal Schema 21 runtime. Accepted
[ADR 0038](../adr/0038-scoped-recovery-and-optional-initialization.md),
[ADR 0029](../adr/0029-independent-access-store.md) and the
[selective Exchange contract](../architecture/selective-exchange-contract.md)
remain authoritative. Read current source when this snapshot ages.

The accepted [operation-scoped installation contract](../architecture/module-independence-contract.md)
and [ADR 0037](../adr/0037-operation-scoped-module-independence.md) describe future
guarantees, not a reinterpretation of this snapshot as physically isolated wheels.
Its per-operation delta table checks the newer base
`c2ae058b6402e0f5055c864fba1ed4ec7992a8aa`, including the already completed
RefObservation transition. The accepted recovery successor has its own
[ADR 0026 carry-forward audit](../adr/0038-scoped-recovery-and-optional-initialization.md#clause-level-reconciliation-of-adr-0026).
Existing tests linked below are not newly executed by that design task. In
particular, this decision does not remove Exchange's coexisting-Context checks, change
default selections, or make Operational optional for reception.

| Operation | Implementation and local stores used | Coexistence, validation and stop boundary | Regression evidence |
| --- | --- | --- | --- |
| Query, explicit `core_only` | Core snapshot and Core implementation; ordinary Core reads do not import Context or Search, or require their databases or Operational. A Search operation deliberately loads Search. | A coexisting Context is not opened or paired. The persistent catalog stop still fences the operation, including completion; an uninspected Context is not certified healthy. | [Core Query isolation](../../tests/integration/p6/test_core_import_independence.py); [Core and byte-integrity queries](../../tests/integration/p6/test_queries.py). |
| Query, `auto` / `paired` | `auto` chooses paired when both authoritative stores exist; paired snapshots open Core and Context and validate the pair. Search is lazy until requested. | Pair identity and dependencies are checked; confirmed authoritative corruption and existing catalog stops fence ordinary results. `auto` selects the single available authority when only one exists. | [Core Query isolation](../../tests/integration/p6/test_core_import_independence.py); [snapshot corrections](../../tests/integration/p6/test_corrections.py). |
| Query, explicit `context_only` | Opens Context without requiring a Core database; the Query module still imports the Core adapter, even though that database is not opened. Context-only results cannot establish missing Core facts. | A coexisting Core is not paired by this explicit query mode. Persistent catalog stops still apply. | [Context-only queries and checked text](../../tests/integration/p6/test_queries.py); [mode and stop corrections](../../tests/integration/p6/test_corrections.py). |
| Exchange export, `include_context=False` | Emits selected Core section without Context or Operational when Context is absent; Context-specific implementation need not load in that case. The flag selects output sections, not local catalog topology. | When Context coexists, `_store_identity()` opens and validates it and checks pairing even for Core-only selection. Invalid stored registration or a known catalog stop blocks export. This is not proof of undetected Context health outside the checked scope. | [Core Exchange isolation](../../tests/integration/p5/test_exchange_core_import_independence.py); [invalid coexisting Context](../../tests/integration/access/test_context_boundary.py). |
| Exchange import, Core-only selection | Core plus Operational are required for admission, cumulative actual-work accounting, package binding, checkpoints and receipts. Without Context and without supplied Context sections, no Context implementation is needed. | All supplied sections are validated even when unselected. When Context coexists, identity is checked before admission and paired admission rechecks it; `include_context=False` does not bypass either. Stops fence admission and commit. | [Core Exchange isolation](../../tests/integration/p5/test_exchange_core_import_independence.py); [unselected invalid registrations](../../tests/integration/access/test_context_boundary.py); [selection and stops](../../tests/integration/i3/test_selective_exchange.py). |
| Context-inclusive Exchange | Context data, Context validation and applicable authorization are required for selected Context admission. If Core coexists, identity/pair checks remain in force even when Core output is not selected. | Supplied sections are validated independently of selection; Core references, receiver permissions, genuine provenance, checked retained bytes and catalog stops retain their existing gates. | [Context boundary](../../tests/integration/access/test_context_boundary.py); [selective Exchange](../../tests/integration/i3/test_selective_exchange.py). |
| P1 selected / full manifest | `verify_declared("core")` verifies the format and full set of store names, but recomputes and compares only Core's contents; Core initialization and connection use it. `verify_declared()` compares the full manifest and all stores. The distribution remains monolithic. | A selected check does not certify another store's fingerprint or its stored data. Neither selected verification nor an absent store overrides a previously detected catalog-wide stop. | [P1 factory tests](../../tests/unit/test_p1_core_factory_independence.py); [schema tests](../../tests/integration/p1/test_schema.py); [installed P1 distribution](../../tests/packaging/test_p1_distribution.py). |

The tests above demonstrate particular operations and fixtures, not exhaustive
corruption detection or permanent physical health. Removing the coexisting
Context pairing checks, changing default selection, omitting Operational on
receipt, or splitting the package would be future work requiring its own
contract and review; this map makes no such change.
