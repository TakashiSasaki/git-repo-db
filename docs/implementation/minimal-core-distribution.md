# Minimal Core distribution and scoped Recovery

The A+B milestone introduced the bounded OP-01 distribution under accepted
ADR0037/0038. The C implementation extends the same distribution with Git-only
Recovery. Executed acceptance and remaining gaps belong to revision-bound PR
evidence; this contract alone proves neither OP-02 nor M-01. Other minimal
combinations, normal Schema 21 migration and release qualification remain separate.

## Ownership and entry points

All distributions have synchronized version 0.2.0 in this repository and use the
`repo_catalog` PEP 420 namespace. Each installed file has exactly one owner.
No distribution owns a namespace `__init__.py`; `_version.py` belongs to contracts.

| Distribution / source root | Owns | Runtime dependencies / public entry |
| --- | --- | --- |
| `repo-catalog-contracts` / `packages/contracts/src` | Nominal OID/provenance and their validation errors; time/Coverage values; snapshot/Query value contracts; shared Coverage DDL fragment; version | No dependencies; `domain.shared_values`, `domain.query_contracts` |
| `repo-catalog-core` / `packages/core/src` | Typed Git/Notes admission and integrity; Core adapter/schema/UDF validation, Core DDL and fingerprint declarations; finite Query work helper; persistent stop/locking/completion and Core snapshots; Core Query API/port/CLI; Git-only Recovery and its durable budget; typed Ref codecs/reconstruction and finite encoding | Exact-version contracts; `p1_schema.initialize(..., "core", ...)`, `GitCore`, `CoreQueryService`, `CoreRecoveryService`, `repo-catalog-query` / existing `python -m repo_catalog.cli.production_query` |
| `repo-catalog` / `src` | Existing normal Schema 21 product, Context/Access/Operational/Search, acquisition/Exchange orchestration, Context/paired Recovery integration and explicit paired/optional Query composition | Exact-version Core/contracts plus `httpx`; existing `repo-catalog` / `python -m repo_catalog`; composed `RecoveryService` |

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

## Recovery ownership and scope

`application.core_recovery.CoreRecoveryService` composes the Core-owned
`adapters.sqlite.core_recovery.CoreRecoveryAdapter`. The existing
`application.recovery.RecoveryService` explicitly composes the optional
Context/paired integration. Composed backup keeps its paired default; Core's
entry requires no optional implementation. Missing paired capability is a
`RecoveryCapabilityError`, not a corruption diagnosis or permission to downgrade.

The canonical Recovery domain/ports and durable request accounting belong to
Core. The typed wire definitions in `domain.ref_exchange` are codecs, not
high-level Exchange orchestration; `application.ref_reconstruction` owns the
shared reconstruction and `application.query_encoding` owns finite encoding.
Exchange connects its aggregate measurement explicitly while Core always charges
performed work. Selection, envelopes, package/request binding, reception and
Operational accounting stay optional. There is no second model or codec copy.

Backup scope is explicit. Salvage interprets only its effective supported scope;
topology-based defaults never depend on which modules happen to be installed.
The durable request binds scope and source/baseline identity in addition to its
finite budget. Changing an output path cannot reset an explicit source-bound
request. Retry, crash reservations and accounting-loss refusal keep the existing
durable machinery; finite in-memory Query work is not a substitute.

Git-only preservation copies coexisting Context authority and necessary sidecars
as opaque evidence. It reports that scope as uninspected/unrecovered, never
healthy. Paired manifests, baselines and supplied material cannot be silently
reinterpreted. A fresh Git-only active destination contains no unvalidated Context.
Git-only activation validates the trusted restored Core and publishes the locator
under the existing completion fence without creating Operational/Search DBs.
Its receipt reports no reconstructed stores, `clean_operational=None` and
`search_derivative_state="not_initialized"`. Paired activation retains Context
validation and Operational/Search reconstruction. Original source evidence and
its persistent stop remain preserved in either scope.

The external OP-02 driver reuses the direct/sdist-derived Core build and normal
offline dependency resolution, separately from the rich paired P7 scenario.
The OP-01 driver remains a regression. Full OP-02 evidence must cover the complete
lifecycle and the applicable ADR0038 R6.1–R6.10 controls; existence of these tests
alone is not execution evidence or release acceptance.
