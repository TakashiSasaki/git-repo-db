# P2/P3 implementation ownership and dependency ledger

Both implementation branches start at P1
`67e8be65c3061b494c2c7373e2fd151398435f62` (tree
`1d9b73e363e5b8a2bfe252fdcb87c7571d012e37`). They are siblings targeting
`feat/p1-four-store-schema-contracts`; neither consumes the other's commits.
The owner explicitly authorized implementation, local synthetic testing,
independent subagents and creation of the two PRs. Merging, auto-merge, deployment,
real-data migration and switching the public initializer are excluded.

This ledger was established before parallel editing. Each implementer uses a
separate Git worktree. Reviewers inspect source and execute tests read-only;
they do not edit the production changes they review.

| Owner | Allowed implementation paths and responsibilities |
| --- | --- |
| P2 | New native Git parser and production Core adapter; Core-owned P1 domain/adapter corrections; `tests/integration/p2/`; P2-specific packaging checks and execution/review documentation |
| P3 | New typed Context observations and production Context adapter; Context-owned P1 adapter corrections; `tests/integration/p3/`; P3-specific packaging checks and execution/review documentation |
| Integration coordinator | Read-only P0/P1 integration preflight; common handoff and ownership documentation; disposable committed combined validation tree and tests; evidence reconciliation and PR creation |
| Independent reviewers | Git semantics/integrity; Context identity/provenance/Coverage; cross-domain coordination/schema consistency; external disposable reproductions and review reports |

Frozen shared files include `p1_schema.py`, `domain/p1_coverage.py`,
`p1_ddl/coverage.sql`, `p1_ddl/fingerprints.json`, and coordination domain, ports
and adapter. Original P1 semantic identities, physical ownership, five-column
Coverage and cross-store snapshot/retry rules are common authority. Neither
implementer may independently change these contracts or edit the other domain.
A necessary shared correction must first demonstrate a failure, then become one
coordinated reviewed dependency with tests for both consumers.

Core-only operation does not require Context. Context remains durable without
Core and reports unavailable Git dependencies honestly. A certified paired
operation uses the frozen P1 coordinator, including Core-first independent
commits and pinned snapshots. No multi-WAL crash-atomic commit is claimed.

The public Schema 21 runtime remains active until P8. P4 owns full notes
acquisition/completeness and budgets integration; P5 acquisition/Exchange; P6
public readers/Search; P7 paired backup, salvage, recovery and activation; P8
coherent public integration. No accepted ADR is changed by this implementation.

## Final collision and shared-correction disposition

A concrete callback report-promotion counterexample and persisted semantic-UDF
corruption-stop failure required one shared dependency, PR #73. Both siblings
consume the exact same final `06a4ccd432476af15ee942e8cfcd9fbdf42357c7` history.
The common correction alone owns Core guard/fingerprint regeneration, coordinator
validation corrections and the explicit historical-audit isolation list. Neither
implementer independently edited those shared files.

The independent final comparison of P2 `8ce2fc4b...` and P3 `5e3b373b...` against
that common dependency found **zero intersecting changed paths**. P2 owns
`adapters/git/native.py`, `adapters/sqlite/git_core.py`, Core-owned P1 domain/adapter
extensions, Core tests and its evidence. P3 owns `adapters/sqlite/production_context.py`,
`domain/production_context.py`, `domain/ports/production_context.py`, Context-only
P1 projection extraction, Context tests and its evidence. Production DDL changes
outside the single common correction: **none**.

Coordinator-owned compatibility/integration reports, gated plan and the two
existing skill updates are carried in P2's evidence-only follow-up. P3's runtime
validity does not depend on those documentation commits. Combined tests live only
on the committed disposable validation branch, not as an implementation dependency
in either sibling. Shared Git blob equality and unchanged portable dataclass ASTs
are recorded in `p2-p3-contract-identity.json`.
