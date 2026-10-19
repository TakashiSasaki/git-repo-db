---
status: accepted
date: 2026-10-19
replaces:
  - 0003-append-only-git-core-and-context-store.md
refines:
  - 0017-domain-keys-without-storage-surrogates.md
---

# ADR 0029: Independent Access store for locators and connection configurations

## Decision

**Whole-record replacement accepted on 2026-10-19; physical/adapter implementation contracts remain separately reviewable.**
On 2026-10-17 the owner selected Q-S1 A (Scope UUIDv4), Q-S2 A (continuing logical
resolution environment), Q-S3 A (continuity inherits identity; independent fork
gets a new identity), and Q-S4 A (local reapproval per repository locator,
configuration and purpose). The owner subsequently explicitly approved separate
Scope identity and Scope location, UUID-only identity/reference, timestamped
Scope Locator registrations retained in one table, and the newest registration
as first-choice candidate. The instruction to plan and begin work authorizes
this documentation update. These choices must not be reopened as pending options.

On **2026-10-19**, the owner explicitly approved ADR 0029 as the **complete
successor to ADR 0003**, including deletion of ADR 0003 from the current tracked
tree, after preservation of all still-binding clauses. The owner's confirmation
was: 「はい、ADR0003を原稿から削除することも含めて承認します。」 The actual date,
not the earlier partial Scope-choice date, is recorded in this frontmatter.
Unselected physical-schema/adapter details remain proposals or constrained
engineering contracts; the whole-record approval does not select them by
implication. The historical ADR 0003 is accessible via its [pre-retirement
Git revision](https://github.com/TakashiSasaki/git-repo-db/blob/bb878eda47cf17268dd821c74343bac64d769ea7/docs/adr/0003-append-only-git-core-and-context-store.md). Its ongoing guarantees are carried forward below.
No product implementation, merge, deployment, real-catalog extraction or P8
switch is performed by this documentation change.

| Owner decision | Binding direction under the accepted five-store architecture |
| --- | --- |
| Existing Access boundary | Independent durable Access; Repository UUIDv4 stays in Core; separate repository locators and connection configurations |
| Q-S1 A | Canonical UUIDv4 is the Scope identity; names and URI/URN forms do not replace the UUID in PK/FK or external Scope references |
| Q-S2 A | Scope is a continuing logical locator-resolution environment, not a physical host/container instance |
| Q-S3 A | Confirmed continuity may retain Scope UUID through migration/reconstruction/restore; independently operated copies receive new Scope UUIDs |
| Q-S4 A | Reapprove each repository-locator/configuration/purpose assignment locally; identity continuity is not authorization continuity |
| Locator history decision | Append registrations in `scope_locators`; keep old registrations there, not in a separate history or current-value authority |
| First-choice decision | Maximum original registration time within the Scope determines the default first-choice set; ties remain explicit and ranking is not permission |

No unrelated six-table sketch, globally unique scope-name rule or URI-as-Scope-PK
proposal becomes accepted by implication. Original questions about Access-store
sharing and detailed adapter vocabulary are not silently answered by this ledger.

The accepted target has five stores with separate responsibilities:

| Store | Responsibility | Lifetime |
| --- | --- | --- |
| Git Core | Permanent repository identities, attributed Git facts, captures, checked structure, allowed retained metadata/notes and Core Coverage | Application-level INSERT-only domain authority |
| Context | Provider/Source identities, known-positive memberships, current PR/Issue/review/text and contextual evidence | Independently durable domain authority; permitted current-state mutation |
| **Access** | Scope UUID identities, same-table Scope Locator registration history, current repository-locator bindings, connection configurations and local approvals | Durable configuration with immutable registration facts and separately mutable control state; not a cache |
| Operational | Attempts, finite cumulative work accounting, continuation/retry state and cache locations | Reconstructible execution state |
| Search | Derivatives of the requested Core/Context domain | Rebuildable, not authority |

Access must not require Context or a fabricated Provider/Source registration for
local Git or SSH access. Missing Access prevents resolving saved access settings,
not reading, validating, exchanging or restoring existing Core/Context facts.
An explicitly supplied one-shot local source remains possible without persisting
Access. A standalone Access configuration can refer to an as-yet-unregistered
repository UUID; successful acquisition still uses ordinary typed Core admission.

### ACC-01: Two identities, two location layers and connection configuration

`repository_uuidv4` permanently identifies a repository. `scope_uuidv4` permanently
identifies a logical locator-resolution environment. Scope display names may change
or coincide; hostnames, container names, URI equality and successful authentication
are not Scope identity. Use the UUID for all durable Scope references, including
references from another database; SQLite cross-file FK enforcement is not assumed.
This does not require a Core row to depend on Access to remain readable.

A **Scope Locator** is a URI locating/discovering the execution environment of a
Scope. A **Repository Locator** is the human-readable Git URL-like address to a
repository interpreted in that Scope. Neither is the other's identifier. They are
not automatically concatenated. A URI for documentation or a UUID's `urn:uuid:`
serialization is not automatically an executable Scope Locator. UUID URN output
can be derived from the UUID; do not maintain it as a second editable identity.

A **Connection Configuration** supplies typed local connection behavior and external
credential references. Profiles may serve several repository locators, and a
repository locator may have several profiles. Zero saved Scope Locators is valid
for offline identity and explicitly supplied local execution; it does not promise
saved remote-environment resolution. Storing a URI does not implement its adapter.

Each repository has zero or more scoped repository locators. URL equality,
redirects, common commits, DNS aliases and matching content never merge repository
or Scope identities. Rebinding future access cannot rewrite past Core evidence.

### ACC-02: UUID Scope keys and two distinct locator relations

The repository-locator key becomes `(scope_uuidv4, locator_text)`. Within one Scope,
the same repository-locator text has at most one current `repository_uuidv4`
binding. Conflicting registration fails rather than upserting another UUID.
Different Scopes may interpret identical strings differently. Explicit rebinding
must check the expected prior binding and invalidate affected local approvals.

`access_scopes` is keyed by canonical `scope_uuidv4`; its display name is not a key.
Connection configurations retain the proposed direct key
`(scope_uuidv4, configuration_name)`; assignments and repository preferences use
matching composite FKs. No second Scope row ID, locator UUID or digest alias is
introduced. Scope UUID is an explicitly owner-approved issued entity identity,
not claimed to be a natural key and not a shortened encoding of a URI. This extends
ADR 0017's genuine-identity reasoning to Access without allowing storage surrogates.

`scope_locators` holds **registration facts**, including `scope_uuidv4`,
`scope_locator_uri` and `registered_at_us`. Preserve old registrations in that same
table. A change or genuine re-registration appends; A at T1, B at T2, A at T3 must
remain three facts. Normal mutation cannot update/delete those coordinates, replace
a previous row, or cascade away the history. Disablement and approval are separate
controls, not reasons to erase registration facts. This does not require full
history for every other Access or Provider setting.

Do not add `scope_locator_history`, a current-URI authority column, or a mutable
latest-registration pointer merely to implement this rule. An index/read view is
allowed. The [companion design](../architecture/access-store-design.md) proposes a
direct registration key and its exact-replay semantics for A1 review; timestamp
alone is not assumed unique. Scope Locator URI alone is not a globally unique
Scope key. Repository-locator uniqueness does not impose that different rule.

### ACC-02A: Latest registration is first choice, not an execution grant

For one Scope, first-choice registrations are all locally held valid registration
facts whose **original `registered_at_us` is maximal**. Preserve equal-time
alternatives; no URI lexical ordering, rowid, UUID order or insertion order picks
a semantic winner. This explicitly selected rule applies only to Scope Locator
ranking, not Git/Context freshness or repository/profile preference selection.

Registration time records the actual registration, not when an external container
moved, last contact time, current reachability, a receipt clock or restore time.
Use int64 Unix epoch microseconds with `_us`. Newly performed registration needs a
real measured time. The proposed required positive-time contract and handling of
undated legacy input are reviewed in A1 under ADR 0028. Preserve the original
coordinates on replay/restore/forwarding. A clock rollback may produce a non-first
new row; diagnose it instead of fabricating a monotonic timestamp. A future-looking
imported time is not permission to execute or evidence of clock accuracy.

Rank first, then check local adoption, disablement, supported route and approval.
The newest registration remains first choice even when not executable: report the
actual failure, do not silently select an older approved locator. An explicit,
locally approved selection of an older registration is a distinct operation and
must not pretend it was the default. Imported facts may affect the displayed
candidate set but never cause network work or automatic authorization. Retaining
an old URI neither certifies it usable nor means it has expired.

### ACC-02B: Scope continuity, fork and restoration

Confirmed logical continuity may preserve `scope_uuidv4` through host migration,
container recreation, rename or restoration. Moving the Scope can append a new
Scope Locator without changing Repository UUIDs or external Scope references.
Ensure the former environment is not independently operated as the same Scope;
no distributed single-writer/fencing guarantee is claimed by a UUID or this PR.

An independently operated clone receives a new Scope UUID. Copying current settings
into that new Scope is a new registration act with its actual time. Do not rewrite
old S1 history rows into S2 at their old timestamps. Source history remains evidence
about S1, preserved there or in the untouched source/backup; any origin link is
non-executable provenance, not identity equivalence. Repository UUIDs remain the
same when the repositories are the same. An offline backup/copy preserves original
UUIDs/times and is not an active clone merely because its bytes exist.

Both continuity restoration and independent fork require destination-local
reapproval. Display-name changes alone need not revoke approval, but execution
namespace, route, binding or credential-reference changes must be checked.

### ACC-03: Conservative Git-compatible repository-locator representation

For repository locators, preserve the validated text exactly for equality and display. Parse and
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

Repository-locator/profile selection honors an explicit choice or valid saved
preference; otherwise it requires exactly one eligible assignment. Scope Locator
ranking separately follows ACC-02A. A tie or unavailable/unauthorized first choice
must not be hidden by filtering down to another route. No historical Core URL,
Provider URL, other account or imported profile is an implicit fallback.

Q-S4 A grants local approval per
`(scope_uuidv4, locator_text, configuration_name, purpose)` assignment. Approval
validity must also bind the selected Scope Locator registration, actual repository
binding, reviewed profile content and local execution context. Matching names or
URI text alone do not revive a stale grant: A(T3) is not approval for A(T1).
Scope Locator changes can affect every repository assignment in that Scope;
recheck each affected grant. Exact physical approval keys/state are A1/A2 work,
not an authorization granted by this prose. Transport authentication never proves
Scope or Repository UUID equivalence or Exchange-sender authenticity.

### ACC-07: Durability, backup and failure boundaries

Access is not reconstructible from Core/Context: restoring historical observations
cannot recover the user's current connection intent. Back it up explicitly with
its own format validation and coherent SQLite snapshot, including all Scope Locator
registrations, not only the newest. Do not copy only a live
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
says; the accepted Access boundary introduces no recovery bypass or same-database repair.

### ACC-08: Snapshot execution without new domain dependencies

Resolve and validate Access in one read snapshot; copy the selected non-secret
settings into an immutable request plan; then release that transaction before
network work. Operational may hold a request-scoped plan and credential references
for retries, not the only copy of current configuration. Re-resolve secrets at use.
Check local approval/disablement before each new externally initiated operation.
An existing request cannot silently switch to the latest Scope Locator on retry;
keep its frozen source intent and original Capture/request budget identity. If the
old plan is no longer locally permitted, stop that continuation instead of
resetting cost or substituting a new route.
An in-flight operation's cancellation semantics must be documented rather than
claiming instantaneous credential revocation. Never relabel completed evidence
with newer settings. Core-first/Context-second admission, finite cumulative work,
original Capture identity and replay rules remain unchanged.

## Constraints / Do NOT

- No Core UPDATE/DELETE/REPLACE, locator/profile FK dependency, new mutable Core
  revision, or destructive rewriting of observation provenance.
- No name/URI-derived Scope identity, Scope-URI external join or rewriting forked
  history with a new Scope UUID. No timestamp-only winner among equal candidates.
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
machine/identity-view-dependent interpretation. A mutable single Scope URI loses
A-to-B-to-A history; separating history/current tables is unnecessary for the
selected first-choice rule. UUID identity plus same-table dated registrations
keeps location changes out of external joins. Separate Access accepts additional
schema, backup and administration costs in exchange for explicit boundaries.

### Complete carry-forward from retired ADR 0003

The `replaces` entry records a **substantive whole-record replacement explicitly
accepted on 2026-10-19**. The superseded ADR 0003 is removed from the current
tracked tree in the same coherent acceptance/retirement commit; its exact content
remains reachable through [pre-retirement Git history](https://github.com/TakashiSasaki/git-repo-db/blob/bb878eda47cf17268dd821c74343bac64d769ea7/docs/adr/0003-append-only-git-core-and-context-store.md). Its former
explicit four-store count is superseded by five independent responsibilities.
The following table carries forward its still-binding rules and rationale rather
than relying on a live link to a deleted file. The earlier independent R4 review
[traced 43 ADR 0003 clauses](../implementation/evidence/access-a6-independent-20261018/r4/adr-clause-map.md)
without finding material loss under the already accepted scoped refinements.
See the [acceptance/retirement closure](../implementation/adr-0029-accepted-retirement-20261019.md)
for the actual current-link changes and historical-reference treatment. Preserve
the exact original execution receipts and do not expand the governance policy's
pre-adoption migration exception.

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
| Preserved and deferred contracts | Keep UUID, Q01-Q04, five-column Coverage and PF-P01-P04/P09-P13/P16-P17 in unsuperseded scope; apply ADR 0028's classified times and ADR 0026's actual validation, not old CAS-41 counters; GC-03/04 and DS-R01/03/04/06/07/08 retain their unsuperseded deferred scope. DS-R05's selected mapping/Exchange scope now follows ADR 0030; broader unselected extensions remain deferred |
| Non-goals and six acceptance criteria | No implementation/real migration/GC/merge by prose; preserve the six concrete future evidence requirements below under ADR 0001 |

These preserved rules are **binding requirements of this accepted successor**, not
merely references to a removed file. ADRs 0004-0010 and 0012-0028 remain
active in their own scopes: metadata-only and attributed/shared OIDs, exact
allowed-body checks, notes capture/group/role rules, finite work, recovery,
unauthenticated reports and classified times are not re-decided here.

### Preserved implementation acceptance requirements

Before claiming implementation completion, independent reviewers must verify all
six inherited evidence families. These are requirements, not tests run by this ADR:

1. A new Git-only catalog works without a Context database: genuine local-Git
   capture and queries round-trip through backup/restore, and supplied
   commit/parent/tree/blob metadata works with zero raw payloads under ADR 0004.
2. SQLite and application tests reject Core UPDATE, DELETE and REPLACE, including
   recovery, intake, later byte admission, dependency resolution and administration.
   Force-push and repeated-ref observations retain both observations and older facts.
3. PR/Issue/comment current-state updates and Context conflicts do not put their
   bodies or domain authority in Core. Missing Context is never a successful full
   paired domain-catalog restore.
4. PR-induced acquisitions leave independent genuine Git evidence. Stale/missing
   cross-store dependencies fail closed for guarantees requiring them; partial
   failed writes cannot fabricate complete roots, refs or Context Coverage.
   Unverified metadata is not itself a failed verified-byte acquisition.
5. Backup/restore and Exchange preserve retained exact bytes, SHA integrity,
   permanent Repository identity, original provenance and verified scope, and
   accurately support metadata-only catalogs. Apply ADR 0026's stop and verified
   fresh recovery, not obsolete CAS-41 quarantine counters. Search rebuild/fallback
   and Operational loss preserve domain authority and cumulative-work truth.
6. Bind evidence to the exact effective code/DDL tree, with focused development
   checks and relevant independent review under ADR 0001. Full release
   qualification requires an explicit request; design acceptance is not execution.

[ADR 0030](0030-context-repository-relations-and-selective-exchange.md) selects
typed conflicting Repository mapping reports and bounded selective cross-seed
Exchange within DS-R05's former unresolved area. It does not select broader
ownership/trust extensions or certify their implementation. Preserve its no-Witness
decision and distinguish this accepted scope from the older single-repository
implementation boundary in the [status audit](../phase2/documentation-status-audit.md).

## Consequences

Benefits: Git-only access need not create Context; local configuration can change
without rewriting evidence; profiles are reusable; missing credentials/Access are
not missing Git history; domain Exchange no longer carries executable settings.

Costs: another durable file and administrative surface; long composite keys;
explicit scope/profile selection; configuration backup and activation policy;
column-level separation of existing JSON and source-aware migration diagnostics;
registration history growth, clock-quality diagnostics and same-time candidates.
No claim is made that all URL equivalence can be computed or that Git authenticates
the catalog's repository UUID. The operator's binding remains a local assertion.

Next work follows the dependency plan and counterexamples in the companion design.
Exact packaged DDL, typed option vocabularies, supported adapters, local policy
revocation mechanics and CLI spelling require implementation-contract review before
coding. The settled architectural direction is not reopened by those details.

## References

- Owner instructions in the Access Scope conversation, 2026-10-17: explicit
  Q-S1/Q-S2/Q-S3/Q-S4 Option A choices; subsequent approval of Scope UUID-only
  reference, separate Scope Locator, same-table registration history and latest
  registration first choice; then "plan and begin work". Earlier URI-as-PK and
  separate-history-table alternatives are not selected.
- [Storage model, source audit and implementation plan](../architecture/access-store-design.md).
- [ADR 0029 whole-replacement readiness audit](../implementation/adr-0029-replacement-readiness-20261019.md) (historical, prepared before final approval).
- [ADR 0029 acceptance/retirement closure](../implementation/adr-0029-accepted-retirement-20261019.md) (2026-10-19).
- [ADR governance](policy.md), [key policy](0017-domain-keys-without-storage-surrogates.md),
  [recovery](0026-stop-salvage-restore-merge-after-corruption.md),
  [origin trust](0027-unauthenticated-external-capture-origin-reports.md),
  [classified times and SHA-256](0028-classified-times-and-sha256-exchange.md).
- [Git URL syntax](https://git-scm.com/docs/git-clone#_git_urls),
  [Git configuration](https://git-scm.com/docs/git-config),
  [OpenSSH configuration](https://man.openbsd.org/ssh_config).
- [UUID/URN format and security](https://www.rfc-editor.org/rfc/rfc9562.html),
  [SQLite SELECT ordering](https://www.sqlite.org/lang_select.html),
  [SQLite foreign-key limits](https://www.sqlite.org/foreignkeys.html).
