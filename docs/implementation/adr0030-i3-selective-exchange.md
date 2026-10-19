# ADR 0030 I3: selective Exchange v4

This is the I3 implementation handoff for accepted ADR 0030 Q-E1–Q-E10. It
starts at the frozen I1 PR #107 commit
`9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7`, tree
`14c694218109de1e3dfebc93e7776d48ad79faf3`. The branch is a sibling of I2;
Provider intake files and I2 work-in-progress commits are not dependencies.
Accepted ADRs and the architecture contract are unchanged. No P8/public-runtime
switch, I2 fetching, I4 Query/Search/Backup integration, or release is included.

## Consumer interface

`repo_catalog.application.exchange.ExchangeService(directory)` exports
`git-repo-db/adr0030-exchange-v4`. A v3 envelope is rejected; there is no v3
import fallback. `domain/exchange_rows.py` declares exact row envelopes and
canonical embedded JSON. Native Git refs use the original reversible
`["native-ref", hex]` representation, including non-UTF-8 bytes. `ExchangePort` matches the service's keyword API.

`export_package(selection=ExchangeSelectionScope(...), package_id=..., exported_at_us=...)`
uses independent `repository_uuidv4s` (R), `object_oids` (O), and
`resource_keys`/`source_uuidv4s` (C) roots. A tuple, including `()`, is explicit;
`None` is an omitted selector and needs `all_selected=True`. An OID is always
`OID(object_format, full_oid)`. Include flags and Notes ref selection further
restrict these roots. Related Provider registrations, exact Mapping support,
parents, collections and Coverage are typed Context dependencies, not Repository
registration authority. Selecting a Repository never implicitly selects all
Provider resources or claims object membership from shared OIDs.

Expansion follows actual stored typed Git relation groups and Context
parent/member/support edges. It is cycle-safe. `max_depth`, `max_units`,
`max_bytes` and `max_work` are finite controls. Export work counts SQLite VM
steps, including scans rather than only emitted rows; selected retained bodies
are checked before emission. Unit and byte bounds cover emitted domain rows
and their canonical UTF-8 payload bytes; envelope/report overhead has the
separate global 32 MiB wire limit. A budget cut withholds whole units and records
its reason. `selection_report` records actual effective roots, dependency reasons,
limits and omitted unit references. It is informational, digest-bound data and
provides no authority to the receiver.

`import_package(package, request=..., new_request=..., selection=...,
permitted_repository_uuidv4s=(...))` is the receiver API. The receiver defaults to
no Repository permission. Explicit permissions and optional independent receive
selection are frozen to the genuine cumulative request and checked on retry.
Both sender-declared selection and receiver selection apply; include flags,
retained-body restriction and empty selectors cannot be overridden by payload
rows. The receiver independently recomputes closure and whole-unit bounds.

Operational must already have been explicitly initialized. Default request
coordinates are the sender/package UUID pair; raw JSON needs an explicit
`RequestIdentity`. A genuinely new request requires `new_request=True`.
Arbitrary/free work budgets cannot bypass durable accounting. Caller-supplied
budgets must belong to the actual Operational file and same request. Receive
work uses cumulative metadata/proof processing units, measured wire parsing and
verification bytes, and bounded domain dependency reads. Snapshot VM/read-row
limits bound scans separately. `max_work` limits cumulative receiver processing;
requests that cannot reserve bounded prevalidation work fail before domain
commits. Failed or crashed performed work remains charged.

## Package binding and commit order

Caller-owned Package/dictionary data is bounded and privately copied before
digest or domain validation, and the same owned snapshot is used through
admission. The canonical envelope, excluding only `digest_sha256`, has one SHA-256 digest.
The sender's seed Repository is descriptive envelope data; it is not compared
with the receiver seed. Receiver `store_identity` rows and existing UUIDs stay
unchanged. New permitted Repository rows use their supplied original UUIDs.

The key `(sender_catalog_instance_uuidv4, package_id)` is bound to its digest
inside Operational before Core or Context commits. The existing semantic
`request_continuations` slot holds only the key and digest. A partial unique
index enforces global PackageKey uniqueness across request owners. Short
`BEGIN IMMEDIATE` transactions serialize first binding and comparison; SQL
guards prevent UPDATE, DELETE, REPLACE and UPSERT from changing a binding.
There is no Mapping witness, new fact alias, payload staging table or verification
history table. Context retains its 19 tables and six roles.

The Operational fingerprint changes for these index/trigger guards. Existing
I1 Operational files are not silently upgraded or reset: explicit disposable
store initialization is required, retaining request issuance witnesses. Core
and Context I1 schema fingerprints do not change.

The order is bounded envelope/domain/permission/dependency preflight; atomic
PackageKey binding; Core transaction/commit; Operational Core checkpoint;
Context transaction/commit; Operational Context checkpoint and summary. Paired
and single-store paths use the same stage semantics. Checkpoints describe actual
outcomes, including partial admission. They do not replace reinspection of live
domain facts. A process exit after either domain commit but before its checkpoint
is recoverable by rechecking original keys and replaying admissible units.

Operational loss refuses continuation of the old request, even after explicit
reinitialization and `new_request=True`. Existing issuance witnesses are retained.
A genuinely new request may reconcile existing facts and consumes new finite
accounting. A digest match does not authenticate origin.

## Whole units and I2/I4 contract

Resource–Repository rows and Mapping Dispositions carry their original direct
keys, clock, provenance and observation time. Mapping claims are admitted before
relations using them. Exact supporting keys are required; missing dependencies
are omitted rather than borrowed from another Provider Repository. Original
Provider-to-Provider scopes survive withdrawal or dispute of Mapping support.
No Provider fetch or mapping resolution is performed here.

Every Transfer scope and all its original endpoint alternatives form one
EventReportKey unit. Rehydration uses I1 `TransferEventReport.from_stored_scope`;
admission uses only `Context.admit_transfer_event`. Permission/depth/budget cuts
never turn a two-ended report into an apparently original one-ended report.
Original one-ended, explicit NULL, unresolved Provider-only, and unreported
endpoints retain their distinct I1 encoding. No destination is inferred from
current Issue ownership. I2 must supply genuine normalized I1 reports; I3 does
not authenticate a Provider timeline observation.

Wire Coverage proofs must exactly match the original complete terminal FK,
including membership, state, provenance, time and terminal marker. Contradictory
proofs are rejected before PackageKey binding. Competing terminals remain in the
same completeness unit; selecting away a terminal cannot strengthen Coverage.

A Source inventory terminal, original membership, associated Coverage assertion
and proof travel intact or are withheld intact. Independent positive Source
memberships may remain useful. Collection/Coverage proof membership is likewise
not truncated or unioned. Core Notes and Capture units retain original identities
and receiver-local byte/role/proof verification. Ordinary file bodies remain
excluded. Context Core references do not assert object ownership. A missing Core
OID withholds the link; original reported field evidence retains its exact clock
and provenance. No synthetic transfer-clock field candidate is generated.

Access settings, approvals and secrets are neither transported nor activated.
P7 Stop fences preflight, binding and domain commit completion. Cancellation and
crashes preserve actual independent commits, rollback incomplete transactions,
and retain work accounting.

I4 should consume `ExchangeSelectionScope`, `ExchangePackage`,
`ExchangeImportReport` (including exact omission reasons and checkpoint fields)
and the matching `ExchangePort`. I2 should emit only committed I1 domain values
and canonical `ProviderRepositoryScope`/Transfer scopes. The original five P5
Exchange integration cases still require I2 setup; their first failure is
`UNSUPPORTED_UNTIL_I2`, so they do not directly demonstrate an I3 failure.
P6 legacy `Context.admit_repository()` callers remain I4 work. They are retained
without skip/xfail/deletion. The final PR records exact tests and review SHA/tree.

## Review and reproducible evidence

Independent preliminary read-only reviews executed counterexamples for Mapping
registration order, malformed primitive UUIDs, empty/disabled receiver selection,
missing Core dependencies, zero receive limits and malformed scalar tags. These
are covered in `tests/integration/i3/test_selective_exchange.py`, alongside real
process exits, competing bindings, SQL mutation probes, Source/Transfer whole
units, Notes checks and Access/Stop invariants. The [first exact-tree review](evidence/adr0030-i3/first-independent-review.md)
found two further executed blockers, corrected with additional regressions.
The [second exact-tree review](evidence/adr0030-i3/second-independent-review.md)
found contradictory original-key payloads that failed only after Core commit;
preflight now rejects these conflicts before Package Binding, including existing
MappingDisposition and complete Transfer endpoint-set conflicts.
The [third exact-tree review](evidence/adr0030-i3/third-independent-review.md)
reconciled I1 UNIQUE bindings separately from composite PKs and added modeled
Collection parent/service and exact Notes-root checks. Valid same-Capture reports
for different Repositories remain separate. Coverage details remain advisory,
with unchanged I1 semantic duplicate handling.
Final review targets the exact
committed/pushed HEAD/tree and is recorded in the PR body.

The former I1 guard node
`test_i1_relation_export_guard_without_i2_acquisition` is replaced by
`test_i3_relation_export_without_i2_acquisition`; the five original integration
nodes are preserved. Existing same-seed refusal tests now exercise explicit
cross-seed permission and identity preservation. A3 fixtures explicitly initialize
Operational and grant Repository permission; no free-budget compatibility path
is retained. Finite JSON real-number tests now use a complete v4 row envelope.

Run from this worktree's own locked environment:

```sh
uv sync --locked --group dev
uv run --no-sync pytest -q tests/integration/i3
uv run --no-sync python scripts/build_p1_schema.py --check
uv run --no-sync python scripts/audit_p1_schema.py --check
uv run --no-sync python scripts/audit_context_registration.py
uv run --no-sync python scripts/audit_callsite_dependencies.py --check
uv run --no-sync python scripts/audit_implementation_boundary.py --check
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
```

The registry workflow includes I3 nodes in both collection and execution and
verifies actual SQLite 3.51.3. Local Python 3.12.14 embeds SQLite 3.53.1; local
results alone are not claimed as minimum-runtime evidence. Isolated installed
wheel/sdist smoke uses explicit v4 selection, initialized Operational and explicit
permissions, with no `httpx` dependency. No test opens real user catalogs.
