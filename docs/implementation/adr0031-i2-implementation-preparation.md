# ADR 0031 I2 implementation preparation — Task C

The completed design reconciliation and disposable SQL investigation are now
published for implementation planning:

- [Complete file-level implementation plan](evidence/adr0031-i2-preparation/I2-IMPLEMENTATION-PLAN.md).
- [Proposed Resources schema](evidence/adr0031-i2-preparation/resources.sql),
  [bounded UDF proposal](evidence/adr0031-i2-preparation/resource_udfs.py), and
  [external composer](evidence/adr0031-i2-preparation/compose_proposal.py).
- [Evidence and reproduction guide](evidence/adr0031-i2-preparation/README.md).

The proposal keeps the direct ResourceKey triple and exact BINARY comparison,
reuses the I1 codec through deterministic SQL predicates, opens kinds while
preserving reserved contracts, and records complete non-key global/scoped
identification metadata. It allows complete child identity before namespace or
Parent existence without creating semantic Parent evidence.

On each actual SQLite 3.51.3 and 3.53.1 runtime, 133 disposable diagnostic cases
passed, including 88 expected SQL refusals with unchanged rowsets. The experimental
helper's acceptance of 33 nested empty arrays demonstrates why the shared I1
codec must replace that parser. These are prototype observations, not product tests.

The plan supplies exact file/index/FK dependencies, a production test matrix,
staged PR dependencies, non-author review gates and packaging/fingerprint checks.
I3 owns semantic Parent reports, I4 native-I7 SQL enforcement, and I5 Event
semantics/atomic Admission. A proposed temporary Transfer fence prevents a partial
I2 implementation from claiming those later guarantees. Generalized Exchange,
recovery and Search integration retain their separate I6–I8 obligations.

This publication is based on exact #118 and changes no product source, packaged
DDL/fingerprint, accepted ADR, runtime workflow or existing PR. The original plan,
prototype inputs and evidence remain byte-identical. The new Draft PR publishes
completed preparation; it does not implement I2 or grant merge/release authority.
