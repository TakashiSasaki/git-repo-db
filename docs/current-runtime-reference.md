# Current runtime reference: Schema 21 and opt-in boundaries

This guide describes the implemented checkout at product baseline
`f0e3022dd8f6dc7b3793e47522dced3ec8be3e8a`; source code is authoritative if a
later checkout changes. It is separate from the accepted target in
[ADR 0029](adr/0029-independent-access-store.md), which defines five responsibility
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
[Access A6 review](implementation/access-a6-independent-review.md) for evidence
and outstanding limits; implementation does not by itself establish release
acceptance or activate P8.

## Historical documents

[CLI Schema 20](cli.md) and [data model Schema 20](data-model.md) preserve their
older descriptions and are not instructions for current Schema 21. The
[implementation status](implementation-status.md) is an audit at its recorded
`fb3b1fb4` revision, not a continuously updated verification record. Historical
execution receipts retain their original revisions and hashes. Use the
[ADR index](adr/README.md) for accepted scope and supersessions; use current
source and exact-revision test evidence for present behavior.
