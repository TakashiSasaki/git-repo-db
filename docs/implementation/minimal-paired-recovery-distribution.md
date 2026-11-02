# Minimum paired Recovery distribution (OP-12)

This increment builds on #251 at
`681fbc557c80d53c664db3d233321cb38e45388a`, tree
`a252952653dd2ab38cdd39a07118ef2d08c6f229`. It implements the accepted
[OP-12 contract](../architecture/module-independence-contract.md) under
[ADR 0038](../adr/0038-scoped-recovery-and-optional-initialization.md).
It does not extend the Git-only optional-initialization exemption to paired work.

## Installation and canonical ownership

`repo-catalog-paired-recovery` requires Core, Context, Operational, Search, runtime
and contracts: seven distributions for the complete paired lifecycle. Context
owns its authority validation and admission. Operational and Search own the schema
resources required by paired activation. No concrete Access, Git acquisition,
high-level Exchange, paired Query or rich product is required. Installation
creates no databases. Backup and restore do not initialize O/S merely because
their code is installed; paired activation retains its reconstruction obligations.

| Installed file | Canonical responsibility |
| --- | --- |
| `application/recovery.py` | Paired service composition over CoreRecoveryService |
| `adapters/sqlite/recovery.py` | Context validation, typed merge integration, paired identity and O/S reconstruction hooks |
| `adapters/sqlite/recovery_validation.py` | Context stored-domain and exact retained-text validation |
| Core `application/core_recovery.py`, `adapters/sqlite/core_recovery.py` | One shared lifecycle, trusted baseline guard, bounded read-only salvage, receiver-local typed admission and safe activation |
| Core `adapters/sqlite/recovery_budget.py` | Existing external durable request/reservation/usage accounting, independent of reconstructible O |

The three existing paired files move without a second recovery engine, model or
codec. Rich entry points keep their installed module names by namespace ownership.
Core retains the complete Git-only lifecycle with T/A/O/S and this integration
absent. Supplied paired material is refused by the Core-only capability rather
than silently treated as Git-only.

Context's canonical AdmissionSelection is recognized before inspecting its
optional Exchange adapter. Recovery uses that existing type directly, so it does
not need X orchestration merely to construct local admission authority. Unsupported
foreign selections still refuse. This creates no new Context mutation or recovery
guarantee beyond the selected paired operation.

## Preserved boundaries and completion checks

The suspect source remains stopped and preserved, including actual DB/WAL/journal
evidence. Salvage opens preserved copies and retains honest unknown/rejected scope;
it is never a trusted restore baseline. All candidate families require the same
fresh, verified baseline/scope/identity guard before merge writes. Core remains
INSERT-only, and Notes bytes retain exact original Claim/proof qualification.

Paired scope validates both authorities and their identities. Activation
reconstructs O/S using their canonical resources. The Search receipt remains
`initialized_empty`; it does not claim a complete rebuilt Search projection.
Context resource candidates that lack supported typed dependency reconciliation
remain qualified non-authoritative observations. Restored baseline resources and
actual admitted text retain their own authority; partial salvage does not mean
every former Context fact was recovered.

Missing paired schema capability refuses before authority or derivative writes, without
diagnosing authority corruption. Git-only scope retains its separate exemption.
The shared lifecycle now checks stop after owned Core/Context, request and
directory/locator descriptor cleanup, using the captured directory identity and
canonical completion fence. It does not call a closed descriptor as a live
capability. A late stop after locator publication may leave that locator pointing
to a stopped target; no successful activation receipt or ordinary service is
allowed. Existing rollback of an interrupted or substituted publication remains.

On normal completion the existing durable Recovery request rechecks its registry,
marker, report and reservation against the active known state. Lost accounting is
refused, never recreated from memory or reclassified as authority corruption.
Committed independent facts remain committed. Crash-conservative reservations,
request locks, frozen budgets and original supported POSIX filesystem limits
remain unchanged; process-crash tests do not establish host power-loss safety.

## Verification scope

`tests/packaging/test_p7_distribution.py` now uses ordinary offline dependency
resolution of direct and sdist-derived paired minima, outside the checkout. It
replaces its former broad `--no-deps` installation with actual absence proofs,
unique owners, loaded origins and artifact hashes. Its consumer exercises actual
Core/Context content, committed WAL preservation, Notes salvage and receiver
verification, replay, budget loss, baseline/capability refusals and O/S activation.
The original installed lifecycle scenario remains covered with stronger scope.

The basic Core OP-02 consumer is rerun because shared lifecycle/accounting changed.
Focused source and independent actual-artifact counterexamples supplement these
minimum installs. The operation-level closeout separately distinguishes current
executions, unchanged-input reuse, unsupported paths and unresolved failures.
No complete Python surface, Provider acquisition, Transfer, Context-only Recovery,
normal Schema21 transition or release qualification is claimed.
