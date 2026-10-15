# Production independently durable Context

The opt-in `Context` production adapter persists modeled Provider resources in P1's independently durable SQLite Context. It does not switch the public Schema 21 initializer. P2 and P3 are siblings with the same corrected P1 dependency; no P2 implementation commit is required by P3.

Production interfaces are `domain/ports/production_context.py::ContextPersistence` (an extension of exact P1 `ContextAdmission`) and `adapters/sqlite/production_context.py::Context`. `domain/production_context.py` adds modeled observation units, not duplicate portable identities. All resource, clock, candidate, Coverage and Git OID types remain the original P1 types. P3 changes no DDL or fingerprint; the small Context-only reference refactor exposes its unchanged Coverage algorithm for already pinned read capabilities.

`Context.transaction(directory)` owns a gated Context-only transaction and works without Core, Operational or Search. `Context.for_transaction(db, directory)` binds to the existing P1 coordinator callback and never commits its outer transaction. `Context.snapshot(directory)` pins standalone Context, while `Context.for_snapshot(pair.context, directory)` consumes the actual paired read snapshot. Capabilities require the Context role, expire at block exit and enforce the persistent catalog stop before use and at result completion. Standalone and paired completion share the frozen P1 stop fence.

Provider/service registration, permanent repository registration and Source registration preserve genuine identities and reject service/kind rebinding. Configuration JSON is modeled registration/configuration evidence; acquired Provider state enters typed fields. Nominal PR/Issue/review/comment/thread/document resources retain their genuine service and parent/document coordinates. Ordinary Issue identity is independent of repository attachment and Source registration. Explicit attach, transfer and null detach are current field evidence, never an identity update.

Current fields retain original observation time, provenance and source clock. Absent differs from explicit null. Comparable later clocks replace dominated candidates; equal and incomparable alternatives remain. Explicit field inheritance copies selected candidates from the actual normalized parent with original evidence intact. Resource observations, text references, Source inventories and proof units use savepoints inside the caller transaction. No raw API history or receipt-time substitution is required.

Exact Context text uses P1 UTF-8 SHA-256 identity and real text FKs. Reads select actual bytes, hash them and decode strict UTF-8 before emitting text. Existing-copy replay verifies the retained copy too. A missing body still referenced by an actual current retained-text FK stops the catalog on read or replay; an unknown unreferenced digest remains unavailable. Replay never silently repairs known loss. Context has no ordinary Git blob, ordinary-file archive or file restoration API. Domain text remains Context authority; future authorized text GC is separate.

Known-positive Source pairs survive partial, empty and replayed inventories. Inventory terminal evidence retains actual Source and scope even with no members. Coverage retains exactly five physical claim columns, complete semantic owner keys, original evidence and advisory-only details. Complete without a genuine current terminal remains unknown. Contradictory/superseded terminals cannot prove completeness. Exact head/base/child scope checks compare both requested scope and persisted immutable collection scope. Recognized child collections/relations enforce actual parent and service coordinates.

Portable Git links have two honest scopes. Current attributed reports use typed field evidence with the actual original clock/time and full OID/resource/role/provenance. They may reference unavailable Core without poisoning a sound pair. Required references use the original P1 `link_core` port, receiver availability validation and the coordinator's independent pre-COMMIT dependency check. `core_dependencies` returns both scopes with explicit required/reported and nominal availability qualification; neither a callback nor a sender flag establishes intrinsic verification. Coherent multi-authority claims require the P1 paired snapshots.

Independent review found and corrected missing stop on standalone corrupt opens, corrupted or lost retained-copy replay misclassification, forged in-memory head/base proof scope, swallowed/deferred SQLite faults, unavailable-report poisoning of required references, foreign-parent child collections, invalid persisted UTF-8, last-read/finalizer stop completion and wrong-role capability binding. Incoming invalid units remain ordinary failures and do not falsely trigger corruption recovery. Shared P1 guard/audit/coordinator defects are isolated in the common corrective dependency; P3 does not weaken shared coordination.

Focused tests use disposable durable target stores, actual P1 caller callbacks and pinned snapshots. Fault injection is labeled separately from real persisted corruption. Installed wheel and sdist-wheel smoke tests import the production adapter outside the checkout, round-trip exact Unicode/NUL text and run with no Core. Full release acceptance, live Provider acquisition (P5), integrated CLI/Search (P6), fresh restore/activation (P7), notes acquisition (P4) and the public runtime switch (P8) remain separate. No real catalog, backup, accepted ADR, public initializer, main ref, merge or deployment is modified by P3.

## Verified source and dependency

Final tested executable source: `5e3b373bfc16ff1cad8d8f093af42a7f00d3d320`,
tree `5776bb9b0aa81c9d4a841e446cfea5f3744f4726`.
Common base/merge-base: `fix/p1-intrinsic-provenance`,
`06a4ccd432476af15ee942e8cfcd9fbdf42357c7`, [PR #73](https://github.com/TakashiSasaki/git-repo-db/pull/73),
which depends on P1 [PR #72](https://github.com/TakashiSasaki/git-repo-db/pull/72).
Both production siblings consume this exact shared correction; neither depends
on the other's implementation commits. The common correction is required by
executed intrinsic-authority and existing-corruption-stop counterexamples. P3
itself changes no DDL, fingerprint, shared Coverage contract or coordination port.

The [machine-readable development receipt](p3-execution-evidence.json) binds the
exact selected and executed node IDs, phase outcomes, source hashes, commands
and raw-artifact hashes. [Independent review](p3-independent-review.md) records
all eight independently assessed findings and their final revalidation.

| Local focused category | Executed | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: |
| P3 production Context | 75 | 75 | 0 | 0 |
| P1 regressions | 266 | 266 | 0 | 0 |
| P0 architecture prototypes/audits | 128 | 128 | 0 | 0 |
| Installed P1 schema and P3 production variants | 4 | 4 | 0 | 0 |
| **Total** | **473** | **473** | **0** | **0** |

The final direct pytest run completed in 41.56 seconds. Selection, exactly-once
journal starts, three passing setup/call/teardown phases per node and exact JUnit
node IDs agree. Python 3.12.14, SQLite 3.53.1, Git 2.52.0, uv 0.12.19, pytest
9.1.1 and Ruff 0.16.10 were measured. Ruff check/format (255 Python files), both
P1 schema builders/audits and both baseline architecture/call-site audits passed.
The earlier `9faea8e` broad run had 460 passes and one exact isolated-module audit
failure; the common correction added the missing production port path without
regenerating or weakening the public Schema 21 baseline inventory. It is not
reported as a passing execution. The profiling wrapper was not used; direct
pytest registered the existing journal option once.

The independent final clean-source run executed **250** nodes, all passed,
including 75 P3 tests, 26 independently authored adversaries and two installed
production variants. Its exact source/tree and evidence are in the receipt.
The [archived independent counterexample source](p3-independent-counterexamples.txt)
is byte-identical to that executed script (SHA-256
`3d36cc2a672a6c84057f477328aac0386e89040d7c17da34bc4df9b950c1a37e`).
The text artifact is evidence, not an additional public runtime module.

This is local focused development verification. Hosted development CI and the
coordinator's committed combined P2/P3 tree are separate evidence; no full release
acceptance is claimed. The unchanged Schema 21 Core-only-fixture failure is
separately repaired by PR #71 and was not cherry-picked, skipped, xfailed or
deleted here. The coordinator's integration-readiness report compares its
uncorrected and corrected executions.

## Handoff and ownership

P3 owns its production Context/domain/port modules, focused integration tests,
installed smoke tests and this evidence. Its sole P1 Context edit extracts the
unchanged projection algorithm for already-pinned reads. P2 owns Core/parser
files. Shared defects were escalated and corrected once in PR #73; no simultaneous
uncoordinated edits or duplicate shared interfaces remain.

P5 acquisition/Exchange and P6 query/Search may develop against these stable P3
interfaces and their P2/P4 dependencies. P4 notes work does not require Context.
P7 recovery/activation and P8 public runtime adoption retain their existing DAG
and acceptance boundaries. Use genuine original keys and clocks for every retry;
use P1 coordinator capabilities for paired writes and reads. P3 does not implement
any transport, public CLI switch, paired recovery activation or production migration.

**READY FOR P3 OWNER REVIEW. Unresolved owner-level architectural blockers: 0.**
No PR is merged or deployed by this implementation task. Reusable verified lessons
are handed to the coordinator for the existing invariant and final-tree skills;
no duplicate skill is introduced here.
