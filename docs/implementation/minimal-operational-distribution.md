# Minimum durable Operational distribution

This OP-08/09 prerequisite starts at reviewed Search PR #248,
`a02c9ffef8af64d1ce16064661bcf83bed17eaaa`, tree
`5a7e1a0329f10d15b6bb74cd8546634bfa72b1e6`. The
[operation contract](../architecture/module-independence-contract.md),
[ADR 0024](../adr/0024-actual-notes-resource-work-accounting.md),
[ADR 0025](../adr/0025-cumulative-request-budgets-and-scoped-blockers.md) and
[ADR 0038](../adr/0038-scoped-recovery-and-optional-initialization.md) retain their
accepted scope. This is ownership and development verification, not a new store
design, completed acquisition minimum or release acceptance.

`repo-catalog-operational` depends only on runtime and contracts. Its actual
three-product minimum contains no concrete Core/Context/Access/Search, Git
acquisition, Exchange or Recovery orchestration. Installation creates no DB.
Explicit `p1_schema.initialize(path, "operational", repository, instance)` prepares
only O; normal acquisition requires prepared durable accounting. The ordinary
Schema21 startup and its Operational1 resource remain unchanged.

| Canonical file | Owner and scope |
| --- | --- |
| `adapters/sqlite/operational_coordination.py` | Operational: existing WorkLedger and NotesWorkBudget, moved without changing class algorithms. |
| `adapters/sqlite/acquisition.py` | Operational: existing request witnesses, budget/attempt setup, continuations, retry/cache/receipt metadata. |
| `adapters/sqlite/notes.py` | Operational: existing request-local progress and scan guards; no incoming body staging. |
| `adapters/sqlite/p1_ddl/operational.sql` | Operational: byte-identical existing opt-in DDL. |
| `domain/request_scope.py` | Contracts: existing canonical explicit request-scope function. Original Notes port reexports this same function; no concrete Core dependency. |
| Rich `adapters/sqlite/p1_coordination.py` | Reexports the same O classes alongside composed pair admission/backup; no copied accounting implementation. |

Imported nominal errors/UUID/canonical codecs are existing shared definitions.
Core authority and Notes evidence are not moved into O. The existing in-memory
Query budget remains distinct; ordinary durable acquisition is not replaced by
that helper. Provider/Context acquisition, Exchange and paired Recovery continue
to compose the same O mechanisms without an independent-installation claim.

Reservations commit before actual work on the original autocommit/WAL durable
connection. Unsettled work remains conservatively spent after a crash. Identity,
frozen request intent, attempt/allocation, checkpoints, full inventory validation,
finite increases, progress pinning, live-handle/inode checks and concurrency
guards retain their existing meanings. Partial or whole O loss cannot resume an
old request at zero expenditure, including a caller relabeling it as new. Existing
request witnesses are coordination state, not a new domain ledger. Deliberately
new requests remain possible. O failure does not invent authority corruption.

Runtime's existing-store opener uses SQLite URI `mode=rw` after the existing file
check, so disappearance before open cannot create an empty replacement. Explicit
fresh initialization and its in-memory capability probe retain their original
behavior. Schema/identity validation and safety pragmas are unchanged.

[Installed tests](../../tests/packaging/test_operational_distribution.py) resolve
direct and sdist-derived artifacts offline outside checkout. Their
[consumer](../../tests/support/operational_probe.py) checks exact owners/origins,
optional-code absence, explicit initialization, cumulative intent/budget/progress,
abrupt process termination with an outstanding reservation, partial/full loss,
live replacement and disappearance without DB creation. Existing P4 accounting
tests retain SIGKILL, concurrent allocation, cached-history/VM-work, int64 and
checkpoint-loss controls. These checks do not prove host-power-loss durability.

Execution and independent source/artifact review bind exact candidates in the PR;
failures and original input bindings remain local. The next dependent increment
is Git-only and Access-approved orchestration with C+G+O and A+C+G+O, physically
without Context/Search. Full OP-08/09, Exchange OP-10/11 and independent paired
Recovery remain separate until those real consumers are demonstrated.
