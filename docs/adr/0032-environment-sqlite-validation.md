---
status: accepted
date: 2026-10-22
replaces: []
refines: [0001-validation-lifecycle-architecture.md]
---

# ADR 0032: Validate with the execution environment's SQLite

- **Decision & Context:** Development tests, hosted CI, independent reviews and
  release validation use the SQLite library actually loaded by that environment's
  Python. One SQLite version per execution environment is sufficient. Local and
  hosted versions may differ; neither an exact version/source ID nor agreement
  between environments is a test-start or acceptance condition. Record actual
  Python version/executable, SQLite version/source ID and relevant capabilities,
  options/PRAGMAs with the input hashes and execution results. Record failures and
  unexecuted checks honestly. Required functionality, data integrity, transaction
  behavior and schema constraints must still be tested.

- **Constraints / Do NOT:** Do not download, source-build, additionally install or
  replace a SQLite library solely for tests/CI, including dynamic-library overrides
  or alternative SQLite bindings. Do not require minimum-plus-newer runs, a SQLite
  version matrix or multiple SQLite engines for development or release. Do not
  change Python implicitly during dependency preparation or child execution.
  Separate wheel and sdist-derived-wheel installations and independent reviewers
  remain required where already applicable; they use their environment's library
  without preparing two SQLite engines. Preserve offline/network guards, input and
  artifact hashes, environment identity, exit codes, exact node reconciliation and
  failure comparisons. Matching a receipt to its own measured invocation remains
  valid; it must not enforce a chosen SQLite release across environments.

  Product compatibility and safety requirements are a separate contract. Preserve
  `p1_schema.py`/`access_schema.py`'s SQLite >=3.51.3 WAL-reset safety floor and
  STRICT/JSON requirements, and `store.py`'s WAL safety predicate (including its
  recognized backports). This ADR changes none of those predicates, DDL,
  fingerprints or behavioral assertions. If the environment fails a required
  capability/safety check, retain the failure and report affected/unexecuted work;
  do not install another SQLite secretly, skip/xfail the failure, spoof a version
  or bypass a guard. A product support change requires its own justified decision.

  An exception, such as reproducing a defect on a particular release, requires a
  report of the reason, exact affected scope and proposed setup, followed by the
  owner's **explicit approval before execution**. A historical two-engine receipt
  or a prior setup recipe is not approval for a new exception.

- **Reason & Ref:** The owner explicitly decided this repository-wide workflow in
  the 2026-10-22 task “SQLite検証方針の統一とCI改善（PR #130からのStacked PR）”
  and authorized recording and implementing it without reapproval. Building and
  swapping test SQLite libraries adds setup cost and misleading environment
  assumptions; reproducibility comes from measured identities and preserved input
  and outcome evidence. Level 2 Mini-ADR: reversible development convention, no
  product support, safety or persistent-data change.

  This additively refines [ADR 0001](0001-validation-lifecycle-architecture.md):
  focused development versus explicit full independent local **and** hosted
  release validation, distribution verification, provenance and failure
  reconciliation remain binding. The two environments do not imply two SQLite
  versions. No accepted product ADR is reversed or retired. [ADR 0031](0031-generalized-context-resources.md)
  retains its domain contracts and independent I1–I8/V1/V2 obligations; the live
  [handoff V1](../implementation/context-resource-design-handoff.md) now uses this
  environment policy. Earlier minimum/newer execution reports, source-build logs,
  ZIPs and frozen review evidence remain unchanged historical facts, not current
  instructions. I5's known Transfer/Wire regression failures are neither caused nor
  resolved by this decision.

  Number allocation checked the index watermark (0031), all fetched remote heads,
  reachable ADR history including deletions and all open PRs on 2026-10-22; no
  higher allocation was found. Policy/documentation PR A starts at PR #130 HEAD
  `b4ede5d8a87f3ce7b1f6df8fda5b3051c3865ba2`; dependent PR B changes CI/tools and
  adds a lightweight recurrence check. Acceptance of this policy is separate from
  implementation/test completion and grants no merge, release or deployment.
