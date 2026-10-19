# ADR 0030 I2: Provider intake and qualified reads

I2 starts at frozen I1 PR #107 HEAD
`9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7`, tree
`14c694218109de1e3dfebc93e7776d48ad79faf3`. I3 PR #108 is a sibling,
not an implementation dependency. Its interface was read at
`5c5b816998f7051703ca400e8cfeab377254c435`, tree
`a4c0ea69a0cf5f31b6ffcdaba918b52de1ed6c91`.
Accepted ADRs 0029/0030, the 19-table Context schema, six roles and direct keys
are unchanged. No Mapping Witness, winner/history table, I3 implementation,
I4 Query/Search/Backup integration or P8 switch is included.

## Recovery and scope

No published I2 PR, remote branch, committed I2 work or stash was found during
recovery. The existing I2 worktree contained six uncommitted source files based
on the exact frozen I1. They were backed up before any changes and reused rather
than reset. [recovery.json](evidence/adr0030-i2/recovery.json) records original
file hashes and patch SHA-256. The original patch is preserved in the task
workspace under `/workspace/i2-recovery-20261019/`.

The recovered normalizers and qualified reader were incomplete: application
intake still used the removed Core-UUID arguments and `UNSUPPORTED_UNTIL_I2`.
This change connects those paths and closes independently reproduced identity,
Transfer and transaction gaps. No history rewriting or force push is needed.

Intake consumes actual REST/GraphQL observation payloads through typed batch
ports. This validation uses deterministic Provider fixtures, not live GitHub
calls. It does not add a credential/approval workflow or claim remote origin
authentication. Existing Access execution remains a separate boundary.

## Public producer API

- `ProviderRepositoryIntake(payload, observed_at_us, provenance_json, graphql=...)`
  represents a native Provider Repository observation without a Core UUID.
- `ProviderIssueIntake` and `ProviderPullRequestIntake` no longer accept the
  retired single `repository_uuidv4` authority. Issue `repository` becomes
  `owning_repository`; PR `base.repo` / `head.repo` (GraphQL `baseRepository` /
  `headRepository`) become separate roles, never an additional PR owning role.
- `ProviderTimelineIntake(..., graphql=..., parent_resource=...)` supports native
  Timeline events and an already-normalized parent. Supplied parent coordinates
  must agree. A Node/database alias requires the actual `payload.issue` to bind
  the exact supplied Node ID and database ID; an override cannot invent a parent.
- `ProviderIntakeBatch.mapping_claims` and `.mapping_dispositions` carry original
  I1 typed claims/dispositions. The application admits them through I1 APIs.
  Claims must explicitly concern `represents_repository`.
- `RepositoryRegistration` registers a portable Context Repository. Optional raw
  Provider metadata registers an independent Provider resource, without asserting
  their identity. `DetachedResourceTransfer` is rejected with
  `ACTUAL_TRANSFER_EVENT_REQUIRED`; affiliation changes cannot create events.

GitHub GraphQL Repository `id` is an opaque Node ID encoded reversibly as
`["github:node_id", original_id]`. A simultaneously observed `databaseId` does
not erase that namespace. REST positive canonical decimal IDs are distinct.
Generic Issue/PR resources can use a genuinely observed `fullDatabaseId` or
`databaseId`; otherwise they retain the opaque Node ID. Timeline string arguments
in GraphQL are original Node IDs; integer arguments are database IDs. No Node ID
is decoded or guessed. URLs, names, OIDs, clone/connection success and numeric IDs
do not establish Core UUID identity or permit borrowing another Provider's claim.

## Provider-qualified current affiliation

Canonical I1 `ProviderRepositoryScope` is retained in `resource_relations` under
`provider_repository_roles`, with exact members, original clock, observation time
and provenance. Missing fields produce no role entry; actual NULL produces an
explicit-null entry; a native Provider reference without Mapping remains
unresolved. Equal, unknown and incomparable clock alternatives remain visible.
Strictly dominated candidates are pruned only within the same role/clock domain.

`ContextStore.provider_repository_roles(resource, *, evidence=None)` and the
production `Context` / `ContextPort` method return
`QualifiedProviderRepositoryRole` values. Qualification uses I1 Mapping evaluation
and genuine caller-supplied `MappingOperationEvidence`; a claimed issuer alone
does not authenticate disposition authority. Conflicts preserve all candidates.
Supports contain exact original `MappingClaimKey` values for the same Provider
Repository and service. Withdrawal, correction and dispute never delete original
Provider relationship reports, claims, dispositions or provenance. The typed
result rejects an evaluation or active supporting claim for a different Provider.

**I4 must use this Provider-qualified read for current ownership/base/head.**
Materialized Core-target `repository_relations()` alone can retain an earlier
mapped owner after a newer unresolved Provider owner arrives. The newer unknown
owner is not fabricated as NULL and does not authorize deleting the older original
Core-target evidence. The new read returns the latest unresolved Provider
candidate, without falling back to the older mapped owner. Query/Search/Backup
integration of this distinction remains I4 work.

## Transfer reports

Only REST `event == "transferred"` or GraphQL
`__typename == "TransferredEvent"` enables the dedicated report route. The type
candidate must belong to the exact event, clock, observation and provenance of
that normalized unit. A flag, Timeline Resource shape, current Issue Repository
or unrelated event's type evidence is insufficient.

Native Event ID, actual Issue parent, original Provider event time (including
unknown), observation time and provenance are retained. Current ownership never
supplies an unreported destination. From/to endpoints are qualified independently
using exact per-role/target original Mapping support; unresolved references,
explicit NULL, absent roles and competing targets remain distinct. One report's
endpoints are never paired with another report's endpoints. Transfer roles cannot
enter through the generic Provider current-role scope.

Registration uses complete I1 `TransferEventReport` / `admit_transfer_event`.
Reacquiring the same original observation replays its original EventReportKey,
endpoint snapshot, observation time and supported provenance. Later Mapping or
Disposition changes cannot rewrite that report or mint a new original observation.
Original Provider references remain available for later I1 qualification. Conflicting
replay times or contradictory parent/event coordinates are rejected.

## Transactions, Recovery Stop and Access

Every application unit/batch has a Context savepoint, including a caller-owned
Context capability. A failure rolls back the intended complete batch even if the
caller catches it. Core-first paired admission ordering is unchanged. Reported
Core references retain their original clock/provenance even when actual Core
validation also establishes a link; shared OIDs do not assert Repository ownership.
No network operation is performed in a write transaction.

P7 Stop propagates through hierarchy creation rather than being swallowed by a
broad exception. Invalid incoming data is ordinary rejection; invalid retained
Provider scope detected by the production reader creates Recovery Stop. Source
membership/inventory and Coverage retain their existing positive-evidence meaning.
Access credentials, settings, approvals and connections are neither changed nor
created by Provider admission.

## I3 and I4 handoff

I3 consumes I1 `ProviderRepositoryScope`, `TransferEventReport`, direct Mapping
keys/dispositions, typed Core references and unchanged Source/Coverage units.
The scope JSON and report codecs are the frozen I1 codecs, not an I2 wire format.
I2 preserves original provenance/clock and registers required Provider resources.
I3 must preserve a complete original Transfer unit when selection excludes one
endpoint; its existing whole-unit omission/reporting contract applies.

The original five P5 Exchange tests remain. On standalone I2, four now pass
acquisition setup and directly reach `UNSUPPORTED_UNTIL_I3`; the Context-excluding
Core-only case passes its existing I1 path. This is not proof of I3 v4 acceptance.
I3 has explicit R/O/C selection, Repository permission, initialized Operational and
new-request requirements; original P5 calls must be adapted in a later combined
integration branch, rather than silently adding I3 implementation here. P6's 27
legacy `Context.admit_repository()` dependencies remain I4 work.

## Reproducible validation

New counterexamples are in `tests/integration/i2/test_provider_intake.py`.
The five requested P5 acquisition nodes are preserved and exercised through the
new contract; no skip/xfail, test deletion or old API restoration is used.
Run focused development validation with the supported SQLite interpreter:

```sh
python -m pytest -q tests/integration/i2 tests/integration/p5/test_paired_admission.py tests/integration/p5/test_provider_acquisition.py tests/integration/p5/test_corrections.py
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python scripts/build_p1_schema.py --check
python scripts/audit_p1_schema.py --check
python scripts/audit_context_registration.py
python scripts/audit_callsite_dependencies.py --check
python scripts/audit_implementation_boundary.py --check
python scripts/verify_access_distribution.py
```

Exact committed/pushed review coordinates, runtime/counts, residual failure nodes,
packaging hashes and hosted CI results are recorded in the evidence directory by
follow-up validation. A green development `offline` check is not full runtime or
release acceptance. This task authorizes no merge, release or real-data operation.
