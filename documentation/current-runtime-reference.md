# Current runtime reference: Schema 21 and opt-in boundaries

This guide describes the implemented checkout at product baseline
`5d28bb33bf62d7b0eff7e6547a4fda84c1815a9d` (tree `7641496147e6d051dca414d9244ed566ce546b5c`); source code is authoritative if a
later checkout changes. It is separate from the accepted target in
[ADR 0029](../docs/adr/0029-independent-access-store.md), which defines five responsibility
boundaries: Core, Context, Access, Operational and Search. Acceptance of that
architecture does not itself activate all five in the ordinary CLI.

## Ordinary catalog initialization

The normal [`repo-catalog` parser and dispatcher](../src/repo_catalog/cli/main.py)
requires `init --profile`, `--cache-max-bytes` and `--min-free-bytes`; use
`repo-catalog init --help` for current arguments. Global options such as
`--state-dir` precede the subcommand. Initialization requires a new or empty state
directory. [`MaintenanceService.init`](../src/repo_catalog/application/maintenance_service.py)
stages the configuration and directories and initializes one Core catalog before
publication. No count is inferred for an existing user's files.

The implemented composed formats are Core Schema 21, Operational Schema 1 and
Search Schema 1, defined by [schema.py](../src/repo_catalog/adapters/sqlite/schema.py).
Core holds the implemented catalog; Operational holds reconstructible job and
execution state; Search holds rebuildable search projections. The
[Store adapter](../src/repo_catalog/adapters/sqlite/store.py) opens Operational
lazily when requested. Search creation is explicit, such as `index rebuild`;
ordinary reads do not create it. These are runtime paths, not a claim that init
opens three databases or that all deployments have a fixed file count.

## Optional implemented surfaces and accepted target

The opt-in [P1 factory](../src/repo_catalog/adapters/sqlite/p1_schema.py) lists
four entries: Core, Context, Operational and Search. It is not the complete
five-responsibility target and is not the normal CLI initializer. Independent
Access has its own opt-in [schema](../src/repo_catalog/adapters/sqlite/access_schema.py)
and [connections adapter](../src/repo_catalog/adapters/sqlite/access_connections.py).
The standalone [Access workflow](../src/repo_catalog/cli/access_workflow.py) and
[Access acquisition](../src/repo_catalog/cli/access_acquisition.py) CLI modules
use that adapter; ordinary catalog `init` does not activate them. See the scoped
[Access A6 review](../docs/implementation/access-a6-independent-review.md) for evidence
and outstanding limits; implementation does not by itself establish release
acceptance or activate P8.

## Historical documents

[CLI Schema 20](../docs/cli.md) and [data model Schema 20](../docs/data-model.md) preserve their
older descriptions and are not instructions for current Schema 21. The
[implementation status](../docs/implementation-status.md) is an audit at its recorded
`fb3b1fb4` revision, not a continuously updated verification record. Historical
execution receipts retain their original revisions and hashes. Use the
[ADR index](../docs/adr/README.md) for accepted scope and supersessions; use current
source and exact-revision test evidence for present behavior.

## CLI and data model navigation at this milestone

The normal CLI exposes source registration, discovery, synchronization, queries,
maintenance and explicit index rebuild through its [parser and dispatcher](../src/repo_catalog/cli/main.py).
The [README initialization example](../README.md#初期化と収集) supplies an empty
state directory and the three required settings. See `repo-catalog init --help`
for arguments at the selected checkout; do not use a historical Schema 20 CLI
contract as a current command reference. The separate Access modules have their
own help and explicit approval/selection steps; they are not subcommands activated
by ordinary `init`.

For the normal data model start with the composed [SQLite schema factory](../src/repo_catalog/adapters/sqlite/schema.py),
[Store implementation](../src/repo_catalog/adapters/sqlite/store.py), and the
[public schema overview](schema/README.md). The visualization
covers Core/Operational/Search, not all opt-in schemas or the entire accepted
architecture. The product source revision used for schema IR is not evidence that
every manually written explanation has been checked against that revision.

## Status and limits

Implementation is not release acceptance. The opt-in P1 and Access surfaces do not
activate P8 or establish that the five-responsibility target is complete. Accepted
corruption recovery ([ADR 0026](../docs/adr/0026-stop-salvage-restore-merge-after-corruption.md))
and file-content retention ([ADR 0014](../docs/adr/0014-history-and-notes-catalog-without-file-archive.md))
are target decisions; avoid presenting the historical quarantine lifecycle or
ordinary file-body archive as the new target. The [decision index](../docs/adr/README.md)
and [transition plan](../docs/architecture/git-core-context-transition-plan.md) distinguish
accepted scope, remaining work and evidence. Existing Transfer-stage non-successes
and other historic receipts remain scoped to their original runs; this guide does
not reclassify or erase them. See the [validation efficiency architecture](../docs/architecture/verification-efficiency-architecture.md)
for the recorded 43 Transfer-stage non-successes and classification requirements.
