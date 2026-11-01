# Operation-scoped module-independence contract

**Accepted target contract under [ADR 0037](../adr/0037-operation-scoped-module-independence.md).**
Owner-selected M-01–M-04 and M-05–M-07 are recorded there. Complete records were accepted on 2026-10-31, including [ADR 0038](../adr/0038-scoped-recovery-and-optional-initialization.md).
This is a future installation guarantee, not evidence that the current wheel is
split. Main investigated: `c2ae058b6402e0f5055c864fba1ed4ec7992a8aa` (2026-10-31).
The [implementation map](../implementation/core-independence-contract-matrix.md)
retains its older, explicitly dated code/test scope.

## Vocabulary and common obligations

C, T, A, O, S mean Core, Context, Access, Operational and Search. G, X and R mean
Git acquisition orchestration/adapters, Exchange orchestration and Recovery
implementation; they are not stores or predetermined packages. Shared values
(including OID, identity, provenance and required typed contracts), coordination
and stop fencing must not transitively install unused concrete stores. They have
one definition, without mandatory conversion layers or duplicated models.

Every row below includes these obligations:

1. Python API and existing corresponding CLI entry points obey the same dependency
   boundary. The target concerns physically absent feature code, not just no DB
   opening or lazy imports. Optional public APIs are absent with their feature.
2. Required authority snapshots, format/schema/identity/dependency and exact-byte
   checks remain. Persistent catalog stop fences ordinary operations and their
   completion. No coexisting store is declared healthy without inspecting it.
3. If required checks cannot run because code is absent, refuse explicitly before
   publishing success or admitting dependent units. Do not silently change topology,
   ignore supplied data, or use a fallback to bypass an authority check. Unsupported
   input, missing capability, resource exhaustion and confirmed authoritative
   corruption must remain distinguishable. Only actual authority-integrity failures
   trigger the catalog corruption stop; input rejection or budget stops alone do not.
4. Installing code never creates/mutates a catalog DB. Ordinary reads never create
   missing DBs or repair derivatives. Explicit initialization and bounded writes
   create only their documented stores. Existing creation preconditions still apply.
5. Preserve full semantic keys, exact replay, original attributed provenance,
   coherent atomic units, Core INSERT-only, finite actual work across request
   retries/continuations, and truthful missing/incomplete scopes. A successful
   operation establishes only its stated scope, not all data recovery or future health.

DB names below are logical current filenames, not proposed import/package names.
Locks, external persistent stop state and Recovery request/usage/reservation files
are permitted coordination state, not optional Operational DBs or a new domain
authority. Reuse existing durability/fail-closed semantics; do not disguise all O
implementation as shared code. No in-memory accounting replacement is selected.

## Required code and databases by operation

Each ID's second table supplies coexistence/input/refusal conditions; both tables
are one contract. “May be absent” means code actually need not be installed. In
addition to listed feature code, necessary genuinely shared contracts apply.

| ID / operation / decisions | Required concrete code and composition | Required DBs; permitted creation | Feature implementations that may be absent |
| --- | --- | --- | --- |
| OP-01 Core initialization; explicit Core-only reads (M-01, M-05) | C factory, typed admission/integrity and Query; shared coordination/stop fences | Explicit initialization creates only `core.sqlite3` in an eligible fresh destination. Reads open existing Core; create no authority/O/S DB. | T, A, O, S; G and X are not prerequisites |
| OP-02 Git-only consistent backup and complete recovery (M-01, M-04) | C with its included R: stop/preserve, read-only salvage, backup/restore, local typed merge, final validation and activation. Reused typed semantics must not require installing high-level X. | Backup/salvage inspect selected source Core/preserved evidence; backup output is new. Restore creates fresh Core stage; merge writes admitted units there. Activation validates that Core and safely changes only the intended locator. No T/A/O/S DB is required or initialized. External durable Recovery accounting remains. | T, A, O, S, high-level G/X; R needed for this minimum cannot be separately optional |
| OP-03 explicit Context-only reads (M-02, M-06) | T reader plus shared values/qualified-reference contracts; no GitCore or other concrete C adapter, even transitively | Existing `context.sqlite3` only; no other DB creation. This row grants no new Context initialization/mutation/recovery minimum. | Concrete C, A, O, S; G/X/R not prerequisites |
| OP-04 paired reads (M-05) | C + T + explicit pairing/snapshot integration | Existing Core + Context; no DB creation | A, O, S |
| OP-05 explicit Core Search (M-03, M-05) | C + S and Core-authority integration; authority-scan fallback is S | Existing Core; `search.sqlite3` optional on read. Only explicit S initialization/rebuild creates/repairs Search; never creates T/O/A. | T, A, O |
| OP-06 explicit Context Search (M-02, M-03, M-05) | T + S + shared values/Context-authority integration; no concrete C | Existing Context; Search DB optional, created/repaired only by explicit S initialization/rebuild. No Core/O/A creation. | Concrete C, A, O |
| OP-07 Access configuration management and Access-only backup (M-05) | A configuration, approval and coherent backup/validation code | Explicit A initialization creates `access.sqlite3`; management requires it. Backup reads coherent Access incl. necessary WAL and creates separate output. No domain/O/S creation or silent damaged-A recreation. | Concrete C, T, O, S |
| OP-08 acquisition from explicitly supplied local Git (M-05) | C + G + required durable O accounting/continuation capabilities; no saved-settings resolver | Existing Core + explicitly prepared durable O capabilities (ordinary implementation: `operational.sqlite3`). Acquisition does not silently reinitialize lost O. Deliberate provisioning is separate; creates no T/A/S. | T, A, S |
| OP-09 Access-approved Git acquisition (M-05) | A + C + G + O; snapshot Access to frozen execution intent, release transaction before external work | Existing Access/Core and explicitly prepared O. Create no T/S; no catalog writes merely from package installation. | T, S |
| OP-10 Core-only Exchange export (M-05) | C + X export; T validation capability when coexistence requires it | Existing Core; additionally open coexisting Context for identity/pair checks. No DB creation; O not required. | A, O, S; T only when no coexistence validation needs it |
| OP-11 Core-only Exchange reception (M-05) | C + O + X reception; T validation/admission contracts when coexistence or supplied sections require them | Existing Core + explicitly initialized O; existing coexisting Context must be checked. Core-only selection creates no T/A/S DB and does not initialize O. | A, S; T only when neither coexistence nor supplied sections require it |
| OP-12 paired backup/recovery, for contrast | C + T + R pairing/domain integration; established paired activation still reconstructs O/S | Consistent Core+Context backup and fresh paired destination; both authorities validated before activation. Retain existing Operational/Search initialization/rebuild obligations for paired activation. Access backup separate. | A; no new O/S installation-independence promise for paired activation |

OP-05/06 explicitly select their authoritative scope. They do not redefine `auto`,
paired Search, default Query topology, or existing selection semantics. Calling a
Core-only Search with Context present must remain an explicit Core-authority
operation, without claiming Context validation.

## Coexistence, supplied input, success and refusal

| ID | Coexisting stores and supplied input | Success scope and required refusal |
| --- | --- | --- |
| OP-01 | Explicit Core-only Query does not open/pair coexisting Context. Known catalog-wide stop still applies; an existing catalog is not overwritten by initialization. | Healthy selected Core facts/checked bytes only. Preserve final completion fence; certify no uninspected Context. Refuse stopped/invalid required authority or unsupported initialization destination. |
| OP-02 | Git-only scope does not authorize discarding coexisting source Context, WAL/journal or incident evidence. Preserve original suspect catalog as a whole as needed for evidence, using filesystem-level preservation without requiring T interpretation. Salvage/merge only supported Core candidates. Supplied Context/paired material cannot silently become a Git-only restore or a Context success claim; refuse unsupported scope. Fresh Git-only destination has no unvalidated Context. | Suitable revalidated Git-only baseline, fresh target, bounded receiver-typed merge, final validation and safe activation. No working backup means no restored operational success. Invalid units may be withheld only under the inherited honest partial-unit contract; unverifiable required baseline/final checks prevent activation. Missing T code is no excuse to reinterpret a paired source artifact. Report unrecovered/uninspected Context explicitly. |
| OP-03 | Explicit Context-only mode does not pair a coexisting Core; global stop still fences it. Return actual T authority and unresolved Core qualifications. | No unavailable Core facts, byte checks or invented registrations. Refuse checks needing absent capability rather than asserting resolution. |
| OP-04 | Both stores required with valid pair identity and cross-store dependencies. No silent single-authority fallback for a paired request. | Qualified combined snapshot; refuse missing capability, mismatched pair or required dependency/validation failure. |
| OP-05 | Pin Core snapshot. Absent/stale/incomplete/corrupt S uses authority scan with diagnostics and no implicit repair. Validate indexed candidates and completeness against authority; a matching freshness token is insufficient. Preserve exact-Claim RefObservation/Notes authority. | Core Search results with actual completeness limits. Index-only damage does not diagnose authoritative corruption; actual Core corruption stops catalog service. Missing S code means no Search API/operation, even though basic C reads remain. |
| OP-06 | Same derivative/snapshot/candidate/completeness safeguards against T. Core references stay qualified/unresolved without C; do not fetch or certify C facts. | Context Search under T authority; scan fallback belongs to S. Missing S refuses feature; missing C does not defeat T-only search. |
| OP-07 | Coexisting authority DBs are not needed for standalone A management/backup. Imported/restored settings are data, not local grants. Credential references never become stored secrets or automatic execution. | Preserve registrations, durability, identity/approval and trust boundaries; no complete domain backup claim. Isolated A damage disables affected A operations, not sound offline facts; doubt about authority still invokes normal stop rules. |
| OP-08 | Explicit local source needs no fabricated Access/Provider/Source registration. Unsupported settings/sources are refused. Required authority/global stop and frozen request semantics still apply. | Genuine typed Core admission with actual finite cumulative work and continuation truth. No volatile shortcut, no retry reset or old-request continuation after O loss. Alternative durable O implementation is neither designed nor required here. |
| OP-09 | Check local approval, disablement, selected binding/route/profile/purpose and credential references. Freeze actual intent; a retry cannot switch to latest settings. | Existing Access execution rules plus OP-08 accounting/admission. Refuse unavailable/ambiguous/unauthorized choices, without hidden route fallback. |
| OP-10 | Selection controls output, not topology. Coexisting T identity/pair validation remains necessary even with `include_context=False`; absent T validation code requires refusal. | Checked selected Core export, no authority for uninspected scopes. Export is not explicit Core-only Query and never inherits its no-Context-open rule. |
| OP-11 | Validate **all supplied sections**, including unselected Context, plus required coexisting identities/pairs and permitted dependencies. With T absent and no T sections/coexistence, C+O+X suffices. Missing required validation code refuses, never ignores a section. | Freeze RequestIdentity and material request semantics; full bounded preflight and atomic PackageKey/canonical digest binding. Exact same-key/same-digest resend is allowed; known same-key/different-digest content is rejected. Core commit/checkpoint then any selected Context commit/checkpoint; honest partial outcomes. Explicit O initialization required. No extra durable Exchange Witness; preserve existing request-issuance witnesses. O loss/reconstruction cannot resume an old request with reset work; only genuinely new explicitly issued request under existing rules. |
| OP-12 | Full Context recovery requires consistent paired baseline and validated references. Cannot drop Context from paired input or claim success with one store missing. | Preserve stop, evidence, fresh restore, typed merge, final pair validation and established paired O/S reconstruction. M-04 adds no paired exemption and no Context-only recovery lifecycle. |

## Current implementation, existing evidence and missing verification

The links below identify implementation and verification inputs, not execution
receipts. The A+B Core distribution and subsequent scoped Recovery implementation
use real direct-wheel and sdist-derived installations; revision-bound PR/run
evidence records what actually passed. Import guards or test existence alone do
not establish absent-code installation. The normal runtime still uses Core
Schema 21, Operational 1 and Search 1; P1 is opt-in. No target row switches it.

| Rows | Inspected implementation and reusable regression evidence | Minimal unimplemented or unverified target delta |
| --- | --- | --- |
| OP-01 | Core/contracts distribution introduced in PR #236; [selected factory](../../packages/core/src/repo_catalog/adapters/sqlite/p1_schema.py), [Core Query](../../packages/core/src/repo_catalog/application/core_query.py), [installed OP-01/OP-02 tests](../../tests/packaging/test_core_distribution.py) and [external OP-01 driver](../../tests/support/core_op01_probe.py). | Dependency-resolved direct/sdist-derived Core-only installation, physical optional absence, typed admission, API/CLI reads and persistent/completion stop controls. Use actual revision-bound results; remaining combinations and release qualification are separate. |
| OP-02, OP-12 | [Core Recovery service](../../packages/core/src/repo_catalog/application/core_recovery.py), [Core adapter](../../packages/core/src/repo_catalog/adapters/sqlite/core_recovery.py), [durable budget](../../packages/core/src/repo_catalog/adapters/sqlite/recovery_budget.py), [Core validation](../../packages/core/src/repo_catalog/adapters/sqlite/core_recovery_validation.py), explicit [paired composition](../../src/repo_catalog/adapters/sqlite/recovery.py) and [Context validation](../../src/repo_catalog/adapters/sqlite/recovery_validation.py). [Scope controls](../../tests/integration/p7/test_git_only_scope.py), [external OP-02 driver](../../tests/support/core_op02_probe.py), existing P7 safety tests and [paired installed scenario](../../tests/packaging/test_p7_distribution.py) cover distinct scopes. [Ownership and public entry contract](../implementation/minimal-core-distribution.md#recovery-ownership-and-scope). | Core includes the complete Git-only lifecycle without O/S initialization, with scope/request/baseline binding, opaque Context preservation and truthful receipts. Paired validation and O/S reconstruction remain composed. OP-02 requires both minimum artifact paths plus applicable R6 evidence; bounded paired regression is not independent proof of all OP-12 guarantees. |
| OP-03, OP-04 | [Query application](../../src/repo_catalog/application/production_query.py) imports GitCore at module load; [domain query](../../src/repo_catalog/domain/production_query.py) includes Search types. [Context reader](../../src/repo_catalog/adapters/sqlite/production_context.py) uses shared OID types; their name/location does not itself prove a concrete dependency. Existing [query/corrections](../../tests/integration/p6/test_corrections.py) and paired tests remain. | Context API/CLI reads with concrete C physically absent, shared contract dependency closure verified; paired refusal/no downgrade and completion fences. |
| OP-05, OP-06 | Search API/types and authority-scan fallback are absent from the basic Core distribution after PR #236, and remain in composed Query. The optional [Search adapter](../../src/repo_catalog/adapters/sqlite/production_search.py) imports GitCore. Existing [fallback](../../tests/integration/p6/test_search_fallback.py), [ref search](../../tests/integration/p6/test_ref_search_transition.py) cover authority safeguards. | Independent C+S without T and T+S without concrete C installations remain pending. Validate fallback/no DB creation, corrupt/stale/incomplete index and exact-Claim bodies in each minimum scope. |
| OP-07 | [Access backup](../../src/repo_catalog/adapters/sqlite/access_backup.py), [registry isolation](../../tests/integration/access/test_registry_isolation.py), [backup tests](../../tests/integration/access/test_backup.py) already implement Access-scoped behavior. Existing Access independence must not be described as wholly future. | Actual A-only artifact installation/management/backup with concrete C/T/O/S absent, preserving approval invalidation and coherent backup. |
| OP-08, OP-09 | [Acquisition](../../src/repo_catalog/application/acquisition.py) imports concrete Context alongside Git and O ledger. [Git acquisition](../../tests/integration/p5/test_git_acquisition.py), [Access Git acquisition](../../tests/integration/access/test_git_acquisition.py) and Access workflow are existing behavior. | C+G+durable O without T/A/S; A+C+G+O without T/S; frozen intent, cumulative retry/loss and approval regressions through real supported entry points. |
| OP-10, OP-11 | [Exchange](../../src/repo_catalog/application/exchange.py), [Core import isolation](../../tests/integration/p5/test_exchange_core_import_independence.py), [coexisting Context boundary](../../tests/integration/access/test_context_boundary.py), [selective admission](../../tests/integration/i3/test_selective_exchange.py); detailed accepted [selective contract](selective-exchange-contract.md). | Actual minimal export/receive installations, with missing T both permitted and refused according to topology/input. Keep all-section checks, package binding/resend/conflict, checkpoint/crash, work and O-loss coverage. |

For each affected distribution, future verification compares direct wheel and
sdist-built wheel metadata/members and isolated behavior, per
[ADR 0033](../adr/0033-minimal-product-sdist.md). Exercise actual public APIs and
existing CLIs with unwanted implementations **physically absent**, rather than
only intercepting imports in a monolithic checkout. Preserve existing stop,
INSERT-only, bytes/Notes, cumulative budgeting, package-binding, preservation and
Search correctness regressions. Bind changed-code and installed-artifact evidence
to exact commits/trees and inputs, distinguishing executed checks from existing
files and historical receipts. Use focused delta tests; no exhaustive combination,
SQLite-version matrix or full release qualification is implied by this contract.

## Engineering decisions and authorization boundary

Exact distribution count/names, import namespaces, dependency version syntax,
public class names, shared-code placement, physical separation mechanics and
implementation PR sequence remain engineering choices. Shared contract ownership
must respect M-01/M-02/M-03 rather than transitively pull unwanted implementation
back in. Initially synchronized releases in one repository suffice.

Design acceptance includes the reviewed ADR 0026 carry-forward. The owner separately
authorized design merge; product implementation still needs separate authorization. This change touches no
product/runtime/build/DDL/test/CI input, performs no real catalog operation and
claims no installation target implemented. Existing functionality outside these
minimums is not removed. No new mandatory follow-up tracker, public-site refresh
or comprehensive CLI is required.
