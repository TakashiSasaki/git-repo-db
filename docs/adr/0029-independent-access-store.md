---
status: proposed
date: null
replaces:
  - 0003-append-only-git-core-and-context-store.md
refines:
  - 0017-domain-keys-without-storage-surrogates.md
---

# ADR 0029: Independent Access store for locators and connection configurations

## Decision

**Review proposal, not implementation or merge authorization.** The owner has
already chosen the architectural direction: permanent repository UUIDv4 stays in
Core; transport-specific access settings stay outside Core; one repository may
have multiple Git-compatible URL-like locators; Locator and Connection
Configuration are different entities; Access is independent of Context. The
current task authorizes documenting this direction after the earlier deferral.
The detailed rules below are proposals for review, not additional owner approvals.

Propose five stores with different responsibilities:

| Store | Responsibility | Lifetime |
| --- | --- | --- |
| Git Core | Permanent repository identities, attributed Git facts, captures, checked structure, allowed retained metadata/notes and Core Coverage | Application-level INSERT-only domain authority |
| Context | Provider/Source identities, known-positive memberships, current PR/Issue/review/text and contextual evidence | Independently durable domain authority; permitted current-state mutation |
| **Access** | Current repository-locator bindings, execution scopes, named connection configurations and explicit selection preferences | Durable, mutable local configuration; not a disposable cache |
| Operational | Attempts, finite cumulative work accounting, continuation/retry state and cache locations | Reconstructible execution state |
| Search | Derivatives of the requested Core/Context domain | Rebuildable, not authority |

Access must not require Context or a fabricated Provider/Source registration for
local Git or SSH access. Missing Access prevents resolving saved access settings,
not reading, validating, exchanging or restoring existing Core/Context facts.
An explicitly supplied one-shot local source remains possible without persisting
Access. A standalone Access configuration can refer to an as-yet-unregistered
repository UUID; successful acquisition still uses ordinary typed Core admission.

### ACC-01: Identity, location and connection are separate

`repository_uuidv4` remains the permanent repository identity. A **Locator** is a
human-readable Git URL-like string, not a repository ID, credential, connection
profile, or captured observation. A **Connection Configuration** supplies the
local authentication references and connection behavior needed to use a locator.
A profile may serve multiple locators, and a locator may have multiple profiles.

A repository has zero or more locators (one-to-many when locations are known).
URL equality, redirect targets, common commits, DNS aliases, matching content or
successful authentication never merge repository identities or authenticate an
external repository-identity report. Explicit rebinding changes future access
configuration only; it cannot rewrite old Core captures or UUIDs.

### ACC-02: A URL is a lookup coordinate, not a global configuration key

Propose the direct locator key `(access_scope, locator_text)`, not a new
`locator_uuid` or a hash. A scope is an explicitly named local resolution context
covering the execution environment and identity view. SSH aliases, filesystem
namespaces and credential-dependent views can differ between scopes even when
the string is identical. Scope names are meaningful operator-selected addresses,
not generated storage IDs, and are not portable domain authority.

Within one scope, one locator has at most one current repository binding. Registering
the same scoped locator for another UUID is a conflict, not an upsert or a merge.
Different scopes may bind the same text to different UUIDs. Changing a binding
requires an explicit configuration operation with the expected prior binding;
ordinary discovery/import cannot do it. The inverse one-to-many relation from
repository to scoped locators is preserved.

Connection configurations have direct `(access_scope, configuration_name)` keys.
Names designate operator-managed profiles; optional labels do not replace keys.
Locator/profile assignments and preferences use matching composite FKs. No
storage-only surrogate IDs are added; ADR 0017 also applies to Access. The
[logical design](../architecture/access-store-design.md) specifies candidate tables
and constraints; these are not packaged DDL or an implemented table count.

### ACC-03: Conservative Git-compatible locator representation

Preserve the validated locator text exactly for equality and display. Parse and
classify it without silently changing its addressing semantics. URI-style HTTPS,
SSH and file locators, Git's scp-like SSH syntax, and explicitly scoped absolute
local paths are representable. Representation support is not permission to execute
every protocol supported by Git or a remote helper.

Do not automatically strip `.git`, fold path case, collapse symlinks, decode
reserved percent escapes, merge `file://` with local-copy semantics, or translate
scp-relative paths into SSH absolute paths. Relative-path input needs an explicit
base and path dialect before registration; no later working directory may supply
missing identity coordinates. A proposed initial implementation rejects unsupported
or ambiguous syntax without lossy Unicode replacement. Windows drive/UNC rules,
IPv6 authorities and Git helper syntax need explicit adapter tests.

DNS resolution, SSH `HostName`, Git `insteadOf` rewrites, proxy routing and secret
resolution are execution concerns, never normalization authority for the key.
No parsing or ordinary configuration import contacts a host or reads a key file.

### ACC-04: Core retains evidence, not an executable address book

Keep genuine historical `repository_claims` for `endpoint`/`git_path` and actual
acquisition/ref/source provenance when they describe what was observed. Their
values must remain intelligible without an Access or Context row. They are not
current settings, automatic connection candidates or proof of present reachability.

Do not replace original provenance with a mutable profile name or Access FK.
Do not rewrite previously admitted facts when a URL, credential reference, local
scope, preference or profile changes. Current access configuration is excluded
from Core; minimal non-secret observed location values are permitted as evidence,
not as a dependency on a transport implementation. Existing evidence is not
silently sanitized or deleted by this design. Excluding Access from Exchange does
not imply that exported historical observations contain no paths or hostnames.

### ACC-05: Separate configuration from Context domain facts

Classify existing `repository_context`, `providers` and `sources` configuration
JSON by meaning, not by the column name. Move executable connection choices,
local filesystem/SSH/proxy settings, credential references and locator selection
to Access. Retain Provider/Source registration facts, provider-reported URLs and
contextual evidence in Context. An observed Provider URL is descriptive data;
using it as an active locator requires an explicit local admission step.

Do not move all Source data to Access, or equate `source_repositories` known-positive
membership with enabled access. A disabled/deleted locator does not remove a
Source association or imply remote deletion. Native Git access requires no fake
Context Source. The transport-neutral registration JSON needs a typed allowlist,
not an unconstrained bucket for settings with a different lifetime.

### ACC-06: Credentials, imports and execution trust

Access stores typed **references** to external credentials, not tokens, passwords,
private keys, passphrases, cookies or secret-bearing URLs. Such references and local
paths are still sensitive configuration and are not ordinary domain-Exchange data.
A missing reference is an access error, never a reason to persist its secret.

Propose typed option allowlists and explicit protocol support. Untrusted imported
settings must not enable remote helpers, shell commands, `ProxyCommand`, arbitrary
Git configuration, disabled host/TLS checks or redirected credentials. Approved
local SSH/credential integration can be supported without banning those external
tools globally. Import parses data only; activation requires local scope mapping
and explicit approval. A profile label is not proof that its external config is safe.

Resolution selects one approved locator/profile for the requested UUID, scope and
purpose. Honor an explicit selection or one valid saved preference; otherwise
require exactly one eligible candidate. Ambiguity fails closed, without arbitrary
lexical/UUID/arrival-time tie-breaking. Do not fall back to a historical Core URL,
Provider-supplied URL, another account, or an imported profile to make a request
succeed. Route rewrites cannot silently change the selected identity view.

### ACC-07: Durability, backup and failure boundaries

Access is not reconstructible from Core/Context: restoring historical observations
cannot recover the user's current connection intent. Back it up explicitly with
its own format validation and coherent SQLite snapshot. Do not copy only a live
main database file while ignoring its WAL, or include secret-store contents.

Preserve the existing **Git-only** and **paired Core+Context domain-catalog** backup
scopes. They remain valid without Access. Their manifests/output must state that
saved access configuration is not included; do not claim complete operational
environment restoration. An optional **environment bundle** can additionally
contain an independently validated Access snapshot and explicit component scope.
It is backup packaging, not a new Publication authority or three-authority commit.
Operational/Search remain reconstructible and excluded as before.

Ordinary domain Exchange excludes Access and any transport configuration leaking
through Context. A later explicitly requested configuration transfer is separate,
selective, non-secret and disabled on import until approved locally. Restored
profiles do not inherit source-machine approval merely because hashes match.
SHA-256 remains corruption detection, not sender authentication (ADR 0028).

An isolated missing/corrupt Access store disables its configuration writes and
saved-setting acquisitions; do not silently recreate it or clear its diagnostic
state. Independently sound Core/Context remain readable. If a failure also casts
doubt on their integrity, ADR 0026's catalog-wide stop applies fully. An existing
Core/Context stop always blocks ordinary acquisition/admission, whatever Access
says; this proposal introduces no recovery bypass or same-database repair.

### ACC-08: Snapshot execution without new domain dependencies

Resolve and validate Access in one read snapshot; copy the selected non-secret
settings into an immutable request plan; then release that transaction before
network work. Operational may hold a request-scoped plan and credential references
for retries, not the only copy of current configuration. Re-resolve secrets at use.
Check local approval/disablement before each new externally initiated operation.
An in-flight operation's cancellation semantics must be documented rather than
claiming instantaneous credential revocation. Never relabel completed evidence
with newer settings. Core-first/Context-second admission, finite cumulative work,
original Capture identity and replay rules remain unchanged.

## Constraints / Do NOT

- No Core UPDATE/DELETE/REPLACE, locator/profile FK dependency, new mutable Core
  revision, or destructive rewriting of observation provenance.
- No URL-derived repository identity, silent same-URL repository merge, fabricated
  Source, or generic publication/eligibility ledger.
- No secrets in any new Access/Context/Core/Operational representation, query
  output, logs or transfer package; registration must reject secret-bearing input.
- No implicit acquisition, credential probing, execution of imported commands,
  cross-account fallback, or activation caused merely by import/restore.
- No ordinary file-body archive, compatibility wrapper restoring excluded
  behavior, automatic migration, retained-data deletion, release or merge.
- Do not treat the proposed Access schema or acceptance examples as executed
  implementation. Do not reopen settled UUID, notes, Coverage, time or trust rules.

## Context & Reason

**Level 3, substantive boundary replacement.** This changes persistence, security,
availability and backup responsibilities, so a full ADR is appropriate even though
the project is unreleased and needs no backward-compatible runtime transition.

The first codebase examined in the conversation was `5e778bf61ef660f65bf5fb22bdb08840503b8464`.
The implementation review base is `b2a87cfc6562413d9ecde7f4329e90c434ae9aad`.
The latter retains four opt-in stores (18 Core, 17 Context, 8 Operational, 3 Search)
and integrates P5/P6/P7; the ordinary initializer still uses Schema 21. Its
`ExchangeService._export_context` exports registration configuration JSON. Generic
JSON storage is not an implemented, isolated Access model. The accompanying design
records precise source paths, current gaps and a staged implementation plan.

Keeping Access in Context would couple Git-only saved access to Provider-domain
persistence and risk transferring local settings with domain facts. Keeping it in
Operational would make loss of a supposedly disposable store erase nonreconstructible
intent. Merging Locator and Configuration would make credential rotation and shared
profiles unnecessarily change location identity. A raw global URL PK cannot model
machine/identity-view-dependent interpretation. Separate Access accepts additional
schema, backup and administration costs in exchange for explicit boundaries.

### Complete carry-forward and acceptance-time retirement of ADR 0003

The `replaces` entry is **prospective** on this proposed review branch. ADR 0003
remains accepted here; it is not deleted or quietly overridden. Changing its
explicit four-store count is not an additive refinement. Before integration,
obtain approval for this replacement, set the actual acceptance date, carry the
following still-binding clauses into the accepted snapshot, remove ADR 0003 and
update its current inbound links/index in the same coherent change. Historical
execution receipts remain historical evidence, not material to rewrite. Do not
expand the governance policy's pre-adoption migration exception.

| ADR 0003 clause family | Successor and preserved meaning |
| --- | --- |
| Store boundaries and domain-based partition | Decision table, ACC-04/05/07: add Access; preserve independent Core/Context authority and derivative stores |
| Core rules 1-3 | Metadata-only qualified admission without bodies/Context; actual immutable ref/capture evidence; unreachable Git facts retained, no Core content GC |
| Core rules 4-5 | Application-visible INSERT-only, including technical rows; exact replay comparison; no REPLACE/upsert/drop-recreate loophole or mutable verification/revision/progress pointer |
| Core rule 6 | Preserve decoder provenance, scoped intrinsic checks and atomic structure; no generic winner or in-place repair; use ADR 0026 rather than obsolete quarantine/count requirements |
| Core rule 7 | ACC-01/04: permanent UUID and self-contained minimum provenance, no Provider/Source/URL-registration dependency |
| Context rules 1-2 | Preserve Q01-Q04, field clocks, missing versus null, conflict alternatives, child/head/base/role evidence and portable typed Core references; no Core dependency on Context |
| Context rules 3-5 | ACC-05: split mixed tables by meaning; preserve exact UTF-8/SHA-256 Context text, no hidden complete API edit history or Publication |
| Git-only path and cross-store references/writes | ACC-08: Git-only initialization/local input/query/metadata-only exchange/backup remain independent; validate cross-file dependencies at application boundary; Core survives later Context failure |
| Snapshot/read and retention | Coherent pinned Core or paired snapshots; no fabricated closure, stale dependency borrowing, cascading Git deletion or ref-history loss |
| Backup/restore | ACC-07: truthful Git-only versus paired scope, actual domain/format/hash/pairing checks, atomic no-overwrite installation and fresh recovery; no file checkout/restorability claim |
| Search and Operational | Correct-authority scan fallback with diagnostics, explicit Search creation/rebuild; loss of execution/cache state never erases domain facts or resets an old cumulative request |
| PF-P06/P08/P05/P14/P15/P07 mapping | Five-store placement; paired domain backup; no current text GC and future Context GC-01/02 only; correct search sources; relaxed Operational atomicity never licenses inconsistent Core/Context authority |
| Preserved and deferred contracts | Keep UUID, Q01-Q04, five-column Coverage and PF-P01-P04/P09-P13/P16-P17 in unsuperseded scope; apply ADR 0028's classified times and ADR 0026's actual validation, not old CAS-41 counters; GC-03/04 and DS-R01-R08 remain deferred |
| Non-goals and six acceptance criteria | No implementation/real migration/GC/merge by prose; preserve independent Git-only tests, append-only attacks, Context isolation, partial-write truth, backup/Exchange integrity and exact-tree independent evidence under ADR 0001 |

These preserved rules are requirements of the proposed successor, not merely
references to a file that would be deleted. ADRs 0004-0010 and 0012-0028 remain
active in their own scopes: metadata-only and attributed/shared OIDs, exact
allowed-body checks, notes capture/group/role rules, finite work, recovery,
unauthenticated reports and classified times are not re-decided here.

## Consequences

Benefits: Git-only access need not create Context; local configuration can change
without rewriting evidence; profiles are reusable; missing credentials/Access are
not missing Git history; domain Exchange no longer carries executable settings.

Costs: another durable file and administrative surface; long composite keys;
explicit scope/profile selection; configuration backup and activation policy;
column-level separation of existing JSON and source-aware migration diagnostics.
No claim is made that all URL equivalence can be computed or that Git authenticates
the catalog's repository UUID. The operator's binding remains a local assertion.

Next work follows the dependency plan and counterexamples in the companion design.
Exact packaged DDL, typed option vocabularies, supported adapters, local policy
revocation mechanics and CLI spelling require implementation-contract review before
coding. The settled architectural direction is not reopened by those details.

## References

- Owner instructions in this conversation: separate Locator/Connection
  Configuration; independent Access; preserve UUIDv4; now update the storage design.
- [Storage model, source audit and implementation plan](../architecture/access-store-design.md).
- [ADR governance](policy.md), [key policy](0017-domain-keys-without-storage-surrogates.md),
  [recovery](0026-stop-salvage-restore-merge-after-corruption.md),
  [origin trust](0027-unauthenticated-external-capture-origin-reports.md),
  [classified times and SHA-256](0028-classified-times-and-sha256-exchange.md).
- [Git URL syntax](https://git-scm.com/docs/git-clone#_git_urls),
  [Git configuration](https://git-scm.com/docs/git-config),
  [OpenSSH configuration](https://man.openbsd.org/ssh_config).
