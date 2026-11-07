# Minimum local Git acquisition distributions (OP-08/09)

This increment stacks on the reviewed Operational prerequisite #249 at
`3ea623ce0c35b1a488bdd37e99d75a9839eea20c`, tree
`79aff4d45e0db1b15f58a6364b1ece2a65bd16cf`. The
[operation contract](../architecture/module-independence-contract.md),
[ADR 0029](../adr/0029-independent-access-store.md),
[ADR 0036](../adr/0036-ref-observations-and-shared-notes-mappings.md) and cumulative
actual-work decisions [0024](../adr/0024-actual-notes-resource-work-accounting.md)
and [0025](../adr/0025-cumulative-request-budgets-and-scoped-blockers.md) retain
their meanings. Execution, artifact binding and independent review are recorded
against exact candidates in the PR, separately from release qualification.

## Ownership and supported operations

`repo-catalog-git-acquisition` requires Core, Operational, runtime and contracts.
C+G+O therefore resolves five products; A+C+G+O resolves six. Context, Search,
paired Query and the rich product are absent from both installations. Access is
an optional explicit addition and retains zero Python runtime dependencies.
Basic Core contains no high-level Git acquisition/source/Notes orchestration.
Installation performs no DB creation, Git command, network or credential lookup.

| Canonical file | Owner and responsibility |
| --- | --- |
| `application/git_acquisition.py` | G: existing GitAcquisition, bounded preparation and shared Core/O opening helpers. Rich acquisition reexports the same implementation; Provider/paired orchestration remains rich. |
| `domain/git_acquisition.py` | G: existing Git-only request/report/Notes-input values. Rich domain reexports these same types and retains Provider/Context values. |
| `domain/native_acquisition.py` | G: canonical frozen request intent and bounded supplied-ref processing. |
| `application/notes.py`, `application/ref_observations.py`, `domain/ports/notes.py` | G: acquisition orchestration/ports; pure Core Notes/RefObservation models and receiver verification remain Core-owned. |
| `adapters/git/native.py`, `adapters/git/notes.py` | G: explicit local Git adapters. No saved-settings resolver is loaded for this mode. |
| `adapters/git/access_native.py`, `application/access_acquisition.py`, `cli/access_acquisition.py` | G: optional Access-approved integration. Concrete Access imports are deferred from CLI entry until capability is available; ordinary G imports do not load Access. |
| `domain/acquisition_errors.py` | Contracts: one existing shared input error, reexported by the Git/rich model owners. |

Use `GitAcquisition(catalog, operational=catalog).acquire_from_native(source,
request, new_request=True)` for an explicitly supplied local `GitNativeSource`.
Core and durable O must already be deliberately prepared. Saved Access execution
uses `AccessGitAcquisition` and the existing separately invoked
`python -m repo_catalog.cli.access_acquisition` with Access installed. No new
local CLI framework or ordinary Schema21/default topology switch is introduced.
Unsupported Access transports/layouts remain refused under the existing
[local execution contract](access-a4-local-acquisition.md).

The existing `acquire_metadata_only(GitMetadataInput, ...)` is supplied typed Core
admission, including composed paired preparation. Its preexisting caller-managed
work/progress interface remains distinct from OP-08's native-input durability
guarantee. No independent Provider acquisition, Exchange or general Recovery
installation is claimed by shipping that shared class method.

## Durable and authority boundaries

Every native call validates its **effective** resolved accounting before semantic
or source processing, including constructor overrides. Supplied accounting must
be the canonical current SQLite NotesWorkBudget, WorkLedger and NotesProgress;
progress must use that exact work capability. Existing ledger validation checks
Core's physical catalog seed/instance identity, request/attempt, original native
or Notes scope, inode/stamps and checkpoints. A caller flag or a duck-typed ledger
cannot certify durability. Existing alternatives to that implementation are not
designed or qualified here.

The default request is the original capture pair; an explicitly chosen request
identity must match the supplied durable capability. Access and paired callers
forward their already-selected original request, preserving legitimate custom
UUIDs. Target repository UUID remains distinct from physical catalog seed.
Volatile accounting, foreign catalogs, split work/progress, changed scopes and
constructor progress substitutions refuse before native input. No old request
can reset expenditure through retry, a new flag or lost/recreated O. Genuine new
requests remain possible. WorkLedger's algorithms/DDL, conservative reservation,
finite limits, cumulative processing, progress/scan guards and crash semantics
remain those of the [Operational owner](minimal-operational-distribution.md).

Actual native metadata and selected permissible bodies retain the original
INSERT-only Core admission rules. RefObservation keys and Claim alternatives,
root-specific Notes mappings, Claim-local receiver eligibility and checked bytes
remain Core authority. One Claim's retained body does not certify another Claim;
local structural verification does not authenticate ref freshness or issuer.
Ordinary repository-file bodies remain outside retention.

Explicit direct local mode requires no fabricated Access/Provider/Source
registration. Access mode retains exact Scope, locator/configuration/purpose
approval, current grant rechecks, revoked/ABA refusal and frozen `a4-access-plan`
and physical source intent. It releases Access transactions before external
execution. Changed requests/routes cannot silently retry against latest settings;
imported/restored settings still supply no local execution approval. Synthetic
reviewers/TTYs in tests are not real consent.

The shared Core opener fences normal completion after owned Core/O cleanup.
Borrowed live/prepared Core uses Core's canonical completion boundary; paired
transaction ownership remains with its coordinator. Access uses that same opener
for its outer owned Core, so a stop published by final close cannot be followed
by success. Exceptional exits retain their original errors. Caller/capability/
budget/input-callback errors do not manufacture authoritative corruption; actual
known authority corruption and persistent catalog-wide stop remain binding.
Reads and acquisition never repair authorities or silently initialize lost O.

## Verification and remaining boundary

[Artifact lanes](../../tests/packaging/test_git_acquisition_distribution.py) use
normal offline dependency resolution outside checkout for direct and sdist-derived
five/six-product installs. The [consumer](../../tests/support/git_acquisition_probe.py)
uses disposable real local Git, actual API and existing Access CLI, checked Core/
Notes bytes, exact Claim qualifications, frozen/cumulative retry, capability/
budget/callback refusals, O loss, Access revalidation and completion fences. It
checks owners/origins/hashes and actual missing optional code; separate basic
Core and Access installs retain their smaller closures. Full source/ref tests,
independent counterexamples and affected composed consumers supplement these
bounded installation proofs; no new SQLite/CPU/all-module matrix is required.

Next, Exchange OP-10/11 still owns high-level selection/admission/receipt and
coordination in rich code, using these canonical G/O mechanisms where needed.
Paired Recovery likewise retains rich pairing/activation and O/S reconstruction;
their existing composed regressions are not independent installation proofs.
Context Transfer remains intentionally unsupported. No merge, release, manual
deployment, real collection or general Transfer repair belongs to this increment.
