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
| `repo-catalog-runtime` / `packages/runtime/src` | Existing selective SQLite factory, declared fingerprints, catalog locks/stop/completion, read snapshot guards, Query input/stored-error helpers and canonical Query CLI | Exact-version contracts; no concrete store dependency |
| `repo-catalog-context` / `packages/context/src` | Canonical Context adapter, schema/UDF/admission/domain validation, Context transaction guard and Resource/exact-text reader | Exact-version contracts/runtime; `ContextQueryService`, existing `context-resource` CLI |
| `repo-catalog-core` / `packages/core/src` | Typed Git/Notes admission and integrity; Core adapter/schema/UDF validation and Core DDL; finite Query work helper; Core-specific snapshots using shared runtime; Core Query API/port/CLI; Git-only Recovery and its durable budget; typed Ref codecs/reconstruction and finite encoding | Exact-version contracts/runtime; `p1_schema.initialize(..., "core", ...)`, `GitCore`, `CoreQueryService`, `CoreRecoveryService`, `repo-catalog-query` / existing `python -m repo_catalog.cli.production_query` |
| `repo-catalog-access` / `packages/access/src` | Access configuration, registry, local approval/workflow, coherent backup and inactive restore/fork | No Python runtime dependencies; existing workflow/maintenance CLI modules; [OP-07 contract](minimal-access-distribution.md) |
| `repo-catalog` / `src` | Existing normal Schema 21 product, Operational/Search, acquisition/Exchange orchestration, Context/paired Recovery integration and explicit paired/optional Query composition | Exact-version Access/Core/Context/contracts plus `httpx`; existing `repo-catalog` / `python -m repo_catalog`; composed `RecoveryService` |

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
INSERT-only and retained-byte checks remain. The shared runtime owns the complete fingerprint
declaration (four store names/hashes are declarations, not feature code), and
selective Core verification still strictly checks inventory, format and Core's
DDL/physical fingerprint. Context DDL is Context-owned; Operational/Search DDL is rich-owned and is absent from the minimum. The shared Coverage fragment has one
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
Callers explicitly pass `BackupScope.GIT_ONLY` to Core backup and salvage.
The inherited paired backup default is conservative and refuses in the minimum
installation. Restore, merge and activation derive scope from the checked
manifest/baseline rather than guessing from available modules.

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

## Bounded Context reader pilot (2026-11-02)

Planning and actual implementation base: main
`502762f725753c706946a426ad05df56fe2663ff`, tree
`69c1a414688f8e4e33a46250b331c942a2abb64b`; fetched main and open PRs
were checked before implementation (no open PRs). The supplied older analysis
used `e967dcda`; only timing/guidance changed between those snapshots. PR239's
restored-baseline preflight is fixed, not an open modularization defect. Normal
Schema21 remains unchanged and P1 remains opt-in.

Hypothesis: a meaningful existing Context Resource/text read can run with concrete
Core/Access/Operational/Search physically absent, without changing persisted
meaning, format, admission or recovery policy. This is a pilot of OP03, not its
completion: `get_context_resource(..., include_text=True)`, `read_context_text()`
and existing `python -m repo_catalog.cli.production_query context-resource` are
the selected slice. The minimum public service is `ContextQueryService`. Other
Context lists/Coverage/Provider/Source APIs, paired resolution, Search, acquisition,
Exchange, Access extraction, Context-only recovery and normal runtime activation
are excluded. The composed `ProductionQueryService` retains its supported surface.

Before: Context read -> Core Query inheritance, Core-owned factory/fences,
combined pair/ledger/Search coordination and Core-owned CLI. After: both concrete
readers -> one runtime + contracts; Context's selected read implementation/view
is composed directly into rich Query, while Core and pair implementations remain
in their owners. The existing selective factory is relocated, not replaced by a
universal Store/plugin abstraction. Core UDF predicates and initial repository
admission remain Core-owned and are loaded only for the explicitly selected Core
profile. Context still owns its complete stored-value/schema/UDF checks. Runtime
ships no Core DDL/typed admission, pair coordinator, WorkLedger or Search engine.
The shared fingerprint declarations identify formats; they cannot initialize or
certify absent concrete stores. Ordinary default/all-profile helpers continue to
require all applicable capabilities; selected Context reads request Context only.

The canonical CLI is runtime-owned. Rich commands require rich composition; the
minimum Context adds `context-resource`, `context-resources` and status. Core commands appear only
with Core installed. Missing paired/Core capability refuses explicitly, including
`auto` with coexisting Core; explicit `context_only` never inspects that file.
Existing catalog-wide stops and completion fences still apply. Coordination files
are permitted; implicit C/A/O/S database creation is not.

Acceptance: both direct and sdist-derived dependency-resolved installations outside
the checkout, unique wheel ownership and installed origins, existing API/CLI parity,
exact verified text, original qualified unresolved Core references, opaque
coexisting Core isolation, prior/in-flight/final completion stop, stored text and
required-value corruption without writing the authority, and distinct input,
unavailable text, budget and missing-capability failures. The richer producer
constructs synthetic state through current typed admission and supplies a hashed
closed fixture plus expected composed results; none of its code enters consumers.
The affected minimum Core OP01/OP02 and baseline guard are regressions because
factory, fence and CLI ownership changed. Tests and independent review results
bind actual artifacts/source revisions separately; this contract is not a PASS.

Maintenance judgment must distinguish successful dependency closure from its
cost: two narrowly scoped distributions, explicit feature composition, moved
canonical definitions and source-root/build ownership updates. No schema/model
copy, Store registry or second timing/evidence ledger is introduced. Remaining
full OP03 and later module combinations need their own bounded tasks.

### Context Resource enumeration (OP-03B)

The Context-owned reader now supplies `list_context_resources` to minimum and
composed Query. Runtime owns the single bounded generic pager; concrete owners
supply their endpoint key validators. Context Resource cursor semantics stay in
Context, paired/Search semantics remain composed, and Core imports no Context.
The existing signature, filters, exact counts and full semantic-key order remain.
Caller page/filter/ResourceKey/cursor validation precedes stored reconstruction;
actual snapshot equality is checked against the pinned token before enumeration.
Only selected rows resolve and verify text after metadata selection. Qualified
mapping alternatives and operation evidence remain part of filtering and cursor
identity; they establish no unavailable Core facts. Parent remains explicitly
unsupported, and Transfer activation remains excluded.

Minimum direct/sdist-derived probes cover empty/populated pages, continuation,
filters and mapping alternatives/dispositions, malformed and mismatched cursors,
authority changes, opaque coexisting Core, budgets, actual stored corruption and
prior/in-flight/post-cleanup stops. Composed artifact probes cover Context-only
and paired list/CLI parity. Execution and independent findings are revision-bound
in the PR; test existence is not a PASS. Provider/Source listings and Coverage
are the next OP-03C scope; independent paired installation remains OP-04 work.

### Remaining Context metadata reads (OP-03C)

The existing public Context read surface is now owned by `ContextReader` and
available through `ContextQueryService`: Resource/exact-text and Resource lists,
plus `list_providers`, `list_source_views` and `get_context_coverage`.
`ProviderView` and `SourceView` live in Context; composed imports re-export the
same definitions. The existing CLI has no dedicated Provider/Source/Coverage
commands, so this extraction creates none. Resource/list/status commands retain
their established semantics and capability discovery.

Provider/Source registration metadata retains its finite domain vocabulary and
original provenance. Source inventories remain attributed observations and
positive memberships survive partial inventories. Source membership certifies no
Core fact. Coverage delegates the existing latest-observation candidate/proof
projection: no fallback to an older complete report; unknown does not displace a
determinate report, conflicting determinate reports stay conflict, and explicit
empty completion differs from no observation. No extra claim or history owner,
Context mutation/recovery minimum or Transfer activation is added.

Caller Source filters and reconstructed Coverage scopes are checked before
stored-row classifiers. Stored identities, inventory structure and values are
checked on reconstruction, with real corruption persisting catalog stop. All
three operations retain in-flight and post-cleanup completion fences, finite
read budgets, pinned Context-only tokens and no optional DB creation. Real
minimum direct/sdist-derived and composed installations, adversarial probes and
independent review remain revision-bound evidence; the contract alone is no
execution claim. OP-04 independent paired installation, Search combinations,
acquisition and Exchange remain separate module-independence increments.
