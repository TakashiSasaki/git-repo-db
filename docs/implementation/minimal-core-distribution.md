# Minimal Core distribution: A+B implementation boundary

This implements the bounded OP-01 milestone under accepted ADR0037/0038.
It does not complete M-01, Git-only Recovery (OP-02), the remaining minimal
combinations, normal Schema 21 migration, or release qualification.

## Ownership and entry points

All distributions have synchronized version 0.2.0 in this repository and use the
`repo_catalog` PEP 420 namespace. Each installed file has exactly one owner.
No distribution owns a namespace `__init__.py`; `_version.py` belongs to contracts.

| Distribution / source root | Owns | Runtime dependencies / public entry |
| --- | --- | --- |
| `repo-catalog-contracts` / `packages/contracts/src` | Nominal OID/provenance and their validation errors; time/Coverage values; snapshot/Query value contracts; shared Coverage DDL fragment; version | No dependencies; `domain.shared_values`, `domain.query_contracts` |
| `repo-catalog-core` / `packages/core/src` | Typed Git/Notes admission and integrity; Core adapter/schema/UDF validation, Core DDL and fingerprint declarations; finite Query work helper; persistent stop/locking/completion and Core snapshots; Core Query API/port/CLI | Exact-version contracts; `p1_schema.initialize(..., "core", ...)`, `GitCore`, `CoreQueryService`, `repo-catalog-query` / existing `python -m repo_catalog.cli.production_query` |
| `repo-catalog` / `src` | Existing normal Schema 21 product, Context/Access/Operational/Search, acquisition/Exchange/Recovery and explicit paired/optional Query composition | Exact-version Core/contracts plus `httpx`; existing `repo-catalog` / `python -m repo_catalog` |

Core-only operation uses the opt-in P1 format. The normal entry remains Schema 21.
An explicit Core read opens only Core, including when an opaque Context DB exists.
The Core service refuses Context/paired requests; `auto` refuses a coexisting
Context when its integration is unavailable. The existing CLI adds optional
commands/service composition only when its explicit optional module is installed;
a broken installed dependency is propagated, rather than silently downgraded.
Search types, ports, CLI commands and authority-scan fallback stay in the rich
artifact. The original rich Python service remains explicit optional composition.

Shared types have one definition, rather than a second model or conversion layer.
Core's large admission/native-validation domain remains Core-owned. The small
finite Query helper is not a replacement for durable acquisition/reception or
Recovery accounting. PairCoordinator retains the existing paired integration;
its common algorithms are inherited from the single Core coordination definition.

## Resources and validation

The exact existing composed DDL, UDF predicates, physical schema expectations,
INSERT-only and retained-byte checks remain. Core owns the complete fingerprint
declaration (four store names/hashes are declarations, not feature code), and
selective Core verification still strictly checks inventory, format and Core's
DDL/physical fingerprint. Context/Operational/Search DDL is owned by the rich
distribution and is absent from the minimum. The shared Coverage fragment has one
contracts owner. All-store validation still requires the full installation.

## Build and evidence inputs

Each project has its own positive product-sdist inventory and metadata. Its sdist
rebuilds a wheel without Git, the checkout, development documents/tests or helper
scripts. Workspace source mappings are development-only; wheel metadata uses
ordinary exact-version requirements. The existing hardened builder validates
sdist members/limits, wheel RECORD and direct/derived content and metadata equality,
then seals artifacts with content-bound cache inputs. Product source roots,
selected project metadata and workspace lock/metadata enter those inputs; existing
CI selection binds the new package roots. The verified environment also binds all
workspace project metadata and refuses inventory/content drift until resynchronized.

`tests/packaging/test_core_distribution.py` installs each Core variant with normal
offline dependency resolution against prepared matching contracts artifacts in a
fresh environment outside the checkout. Its Core-only probe checks physical
absence, unique ownership, public API/CLI behavior and safety failures. Existing
focused Core/Query/coordination/resource and distribution-hardening regressions
remain separate evidence. Executed results, input hashes and exact source binding
belong to the PR/run artifacts; this document is an implementation rationale.

Required complete Git-only Recovery ultimately belongs in this same Core basic
installation. The current rich Recovery implementation is unchanged in this
milestone; it is not a mandatory Recovery add-on design. OP-02 through OP-12
installation guarantees and final combination evidence remain follow-up work.
