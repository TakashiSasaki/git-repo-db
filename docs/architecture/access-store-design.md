# Access store: locator/configuration separation and implementation contract proposal

> **Current navigation:** The audit and proposal below describe their dated S0/S1
> checkpoints, not the present implementation status. ADR 0029 was accepted; the
> separate opt-in Access implementation is in [access_schema.py](../../src/repo_catalog/adapters/sqlite/access_schema.py)
> and [AccessConnections](../../src/repo_catalog/adapters/sqlite/access_connections.py).
> The [A6 review](../implementation/access-a6-independent-review.md) records its
> actual scoped evidence and remaining gates. Ordinary catalog initialization is
> separate. The historical checkpoint in section 10 remains historical.

**Status: complete ADR 0003 replacement by ADR 0029 approved on 2026-10-19;
physical/schema/adapter contracts remain engineering proposals; no runtime change.**
Read [accepted ADR 0029](../adr/0029-independent-access-store.md) for confirmed
Scope Q-S1-Q-S4/history decisions and the carried-forward Core/Context rules.
The [acceptance/retirement closure](../implementation/adr-0029-accepted-retirement-20261019.md)
records the explicitly authorized 2026-10-19 governance change. This document is the concrete storage/source audit
and handoff. Table names and error codes below are proposed vocabulary, not current
SQL or public API. Preserve existing decisions; do not implement by analogy to an
old `repository_endpoints` table alone.

## 1. Two explicit code baselines

- **S0, initially reviewed codebase:** `5e778bf61ef660f65bf5fb22bdb08840503b8464`.
- **S1, current implementation/design PR parent:** `b2a87cfc6562413d9ecde7f4329e90c434ae9aad`;
  tree `4ac3a7d33bb01515e3448af5f630589406303165`.

The review uses S0 as the requested conceptual starting point and S1 for actual
integration, not a rollback of subsequent work. S1 includes P5/P6/P7 and ADR 0028.
The four opt-in stores still contain 18/17/8/3 tables. Core/Context/Operational DDL
fingerprints changed after S0; do not copy the first conversation's fingerprints,
all-signed observation-time convention, HMAC wording or old open-PR status into a
new implementation. Search DDL remains `a1bce192ebf67bc3846f47a5bc63ba2927a97bddf65eb62706ec2e9f9fc5d303`.
S1 Core/Context/Operational DDL hashes respectively are
`3f9f828ad0aff5fae1039f30a3baa29165dbabe6decc5a4f204e78e674b940fe`,
`3a05d872988cb7b20c31d236ef6cb45184f5c289a1a37c4deff3d2a173f5a3f8`, and
`980360b31d11c54b0d556b7fffd6aeeae74919e264b4d19bc34ecca70c7d73cb`.
These identify inspected baseline artifacts, not a schema-build test run.

### Implemented source and proposed routing

Paths are relative to the repository and refer to S1 unless noted otherwise.

| Inspected surface | Implemented meaning / issue | Target action |
| --- | --- | --- |
| `adapters/sqlite/p1_ddl/core.sql`: `repositories` | One permanent UUIDv4 column, already present in S0 | Preserve unchanged |
| Same file: `repository_claims`, `git_observations`, `captures` | Attributed endpoint/path/source/capture evidence | Retain self-contained historical evidence; never use it as the current connection registry |
| `adapters/sqlite/p1_ddl/context.sql`: `repository_context`, `providers`, `sources` | Canonical registration/configuration JSON | Classify each key; move executable transport settings, retain domain identity/evidence |
| Same file: `source_repositories` | Durable known-positive Source/repository associations | Preserve, separate from Access enablement/deletion |
| `adapters/sqlite/production_context.py`: registration methods | Replace configuration JSON under stable registrations | Add typed domain-only validation after Access contracts settle; do not blanket-remove JSON facts |
| `application/exchange.py`: `_export_context` | Serializes provider/repository/source configuration JSON | Domain-only allowlist; never activate imported settings or silently import Access |
| `domain/acquisition.py`, `application/acquisition.py` | Input contains repository UUID and a separately supplied `GitNativeSource` | Insert Access resolution outside Core and native parsing, producing an explicit request plan |
| `application/acquisition.py`: native acquisition scope check | Request UUID is compared with Core `store_identity` seed | Reconcile with the multi-repository registry before claiming arbitrary saved-locator acquisition works |
| `adapters/git/native.py`: `GitNativeSource` | Explicit local path input; not a saved-setting resolver or general remote fetch implementation | Preserve narrow input and retention rules; add transport adapters separately |
| `adapters/sqlite/p1_ddl/operational.sql`: `cache_locators` | Reconstructible metadata/verified-notes cache positions | Keep here; not the durable user's locator registry |
| `resources/catalog3.sql`: `repository_endpoints` | Legacy Schema 21 URL/transport rows in old Core | Evidence for an explicitly authorized extractor only, not the new ownership model |
| `adapters/sqlite/p1_schema.py`, `p1_ddl/fingerprints.json` | Four-store composition and exact schema validation | Introduce a distinct Access schema/initializer in a later PR; do not mislabel S1 as five-store |
| P7 `application/recovery.py`, `adapters/sqlite/recovery.py`, recovery design | Domain backup/restore/activation and persistent stop | Preserve existing domain certificates; design optional Access packaging and local activation separately |

The source paths above start under `src/repo_catalog/` except the P7 design at
`docs/implementation/p7-backup-recovery-technical-design.md`.
The seed check is an observed contract gap, not permission to rewrite catalog
pairing, relax cross-repository selection, or change Capture ownership in this PR.

## 2. Logical Access relations and direct keys

Propose an independent `access.sqlite3`, selected explicitly by the application.
It holds no Git bodies, Provider text, Coverage or Source inventory. It is optional
for offline domain use but non-disposable once configuration/history exists.
Installation-level sharing between catalogs remains a proposal, not a new approval
of earlier Q1. Do not make Scope UUID equal to a Core seed, catalog instance,
Access physical-file identity or execution host ID.

| Relation | Direct key / candidate key | Meaning and constraints |
| --- | --- | --- |
| `access_identity` | `store_role = 'access'` | Proposed format/version singleton; do not inherit P1's required repository seed mechanically |
| `access_scopes` | `scope_uuidv4` | Canonical UUIDv4 identity; display name, description/path dialect are attributes, not external join keys |
| `scope_locators` | Proposed `(scope_uuidv4, registered_at_us, scope_locator_uri)` | Append-only registration facts in one table; Scope FK, exact validated URI, actual registration time; old rows retained |
| `repository_locators` | `(scope_uuidv4, locator_text)` | At most one current `repository_uuidv4`; Scope FK; matching unique triple for preferences |
| `connection_configurations` | `(scope_uuidv4, configuration_name)` | Versioned typed transport settings and credential references; mutable local control, no secrets |
| `locator_connections` | `(scope_uuidv4, locator_text, configuration_name, purpose)` | Matching composite locator/profile FKs; assignment enablement, separate locally verified approval |
| `repository_access_preferences` | `(repository_uuidv4, scope_uuidv4, purpose)` | Reference both an existing assignment and its actual repository binding |

These are seven conceptual relations, **not a frozen physical table count**.
The approval representation may need further matching coordinates/state; do not
claim these rows alone implement Q-S4. No separate `scope_locator_history`,
`scope_locator_current` authority, mutable current-Scope-URI column or latest-row
pointer is required. Read views/indices are implementation choices. The history
rule applies to Scope Locator registrations, not a complete history of all settings.

Scope and repository identities are distinct. One Scope serves several repositories;
one repository has several scoped repository locators. The first-choice Scope
Locator identifies an execution/discovery route, not a repository identity and not
a recursive arbitrary configuration fetch. A stored URI must have an explicit
supported-adapter meaning before it can be executed. Documentation links and a
Scope UUID's URN rendering are not automatically execution routes.

### 2.1 Identity and local constraints

All durable Scope references, including cross-database references, use UUIDv4.
Do not add a short integer/UUID row alias for any known direct key. Scope UUID is
an owner-approved identity of a continuing environment, not a claimed natural key
and not an alias for URI text. Display names may coincide and change without FK
updates. Profiles retain meaningful configuration-name keys; their explicit rename
updates local references, not Scope identity. A digest may fence content/concurrency,
never replace semantic identity or authenticate imported configuration.

Preferences need **both** an assignment FK and its repository-binding FK, so R1
cannot select R2's locator. FKs are local to Access. A reference to Core Repository
UUID is checked at the relevant application boundary, not a cross-file SQL FK.
Core/Context authority must remain readable without an Access row. Existing Git
observation `scope`, Coverage scope and Operational request-scope fields do not
become Access Scope UUIDs through a global rename.

The same Scope Locator URI may be registered for different Scopes without merging
their identities. This does not relax the distinct repository-locator uniqueness
rule. URI-only lookup can return several Scope UUIDs and must report ambiguity.

### 2.2 Registration facts and exact replay: A1 contract proposal

Candidate required fields are `scope_uuidv4`, `scope_locator_uri`,
`registered_at_us`. The proposed direct triple records a registration **fact**, not
the count of every attempted write. Same triple replay is idempotent; same URI at
a new real time is a new fact; equal-time different URIs coexist. Do not assert
that wall-clock microseconds are unique or invent `timestamp + 1`, rowids, generated
ordinals or fresh UUIDs to force an order. Two independent identical triples are
indistinguishable in this fact-set proposal; an event-count/provenance requirement
would need an explicit identity contract, not a silent extra surrogate.

A1 must review this key before product DDL is implemented. The proposed time field
is required positive int64 Unix epoch microseconds, with bool/float/string/range
rejection at API boundaries. This is local registration time, not Git-native time,
external valid-from time or receipt time. Undated legacy input cannot be given a
fake time or default to restore time; leave it unranked/unadmitted with an explicit
extraction diagnostic under the reviewed input contract. A genuinely new local
registration may use its actual measured now; a replay may not.

Immutable registration coordinates cannot be updated, deleted, replaced or lost
through a Scope-deletion cascade in ordinary configuration operations. Local
approval, disablement or retirement must not erase the history or mutate its time.
A1/A2 must define controls for disabling all access without deleting facts. No
new global event store, valid-time history or full Provider edit history is added.

### 2.3 First-choice projection and authorization

For a Scope with registrations, select the entire maximum-time set:

```sql
SELECT scope_uuidv4, scope_locator_uri, registered_at_us
FROM scope_locators
WHERE scope_uuidv4 = :scope_uuidv4
  AND registered_at_us = (
      SELECT MAX(registered_at_us)
      FROM scope_locators
      WHERE scope_uuidv4 = :scope_uuidv4
  );
```

This is selection pseudocode over the proposed relation, **not production DDL**.
Do not reduce a tie with `LIMIT 1`. Stable lexical display ordering is permitted
only for presentation, never to create a unique semantic winner. Zero rows means
no saved Scope route, not a missing Scope identity. A-to-B-to-A at increasing
actual registration times retains all three rows and selects the third.

Rank before considering grants. An unapproved/disabled/unsupported latest route
remains the default first choice with a truthful blocking diagnostic; filtering
it out must not silently promote an older route. Explicit choice of a locally
approved historical registration is separate from default ranking. If times tie,
report the candidate set even when only one candidate has a grant. Import can
change the displayed set but never auto-adopt routes or start network work.

Clock rollback preserves the actual lower time and reports the ordering consequence.
Future-looking imported times require validation/diagnostics; rank is not proof
of clock quality or permission. A1's range validation cannot detect every honest
clock error. Registration/replay/import/restore must remain distinct operations.

### 2.4 Concrete continuity and fork example

S1 is a Scope UUID with display label `build`. Its Scope Locator registrations are
`https://runner-a.example/environments/build` at T1 and
`https://runner-b.example/environments/build` at T2. These are illustrative adapter
addresses, not a claim that a generic HTTPS route can execute Git. A repository
locator `(S1, file:///repos/app.git)` continues to bind R1 through the migration.
An explicitly supplied local environment can work with no saved Scope Locator.

For confirmed continuity/recovery, keep S1 and original T1/T2. For an independent
fork, create S2 and register adopted current locators with their actual new times.
Never rewrite S1/T1 into S2/T1. Keep original history as S1 evidence in the source,
backup or separately attributable records; an origin link does not equate S1/S2.
Same URI, repository contents or hostname cannot infer continuity. An offline
backup is not an independently active fork. Destination-local reapproval is always
separate from copying facts. Concurrent independent S1 environments are not
implicitly authorized, nor does this design supply a distributed fencing service.

## 3. Repository Locator grammar and equality contract

The repository-locator string is an address, not a serialized object containing credentials or an
arbitrary command. URI/scp/local-path syntax is classified explicitly with a known
platform dialect. Proposed registration behavior:

| Input case | Required handling |
| --- | --- |
| `https://host/team/repo.git` | Retain exact validated locator; credentials resolved separately |
| `ssh://git@host:2222/srv/repo.git` | Preserve user, explicit port and path; profile must not silently override an explicit conflicting coordinate |
| `git@alias:team/repo.git` | Preserve scp-like grammar and relative remote path; do not rewrite to an absolute SSH path |
| `file:///srv/repo.git` versus `/srv/repo.git` | Distinct locator spellings/semantics; do not automatically coalesce |
| `../repo`, `~/repo`, `./foo:bar` | Require explicit base/home/path dialect; resolve registration input without later CWD dependence; no implicit symlink identity collapse |
| Windows drive and UNC paths | Classify using explicit Windows scope, not a generic colon-as-SSH heuristic |
| `.git`, trailing slash, case, percent escapes | No automatic equivalence/identity merge; preserve the accepted text |
| `ext::...`, custom helpers, ambiguous syntax | Reject execution unless a separately reviewed adapter/allowlist supports it; never shell-evaluate |
| NUL/control characters, secret-bearing URL, unsupported raw-byte path | Reject with a precise input error; no lossy normalization or secret persistence |

Git's supported URI/scp/local forms, URL rewrites, and OpenSSH host aliases are
external compatibility constraints, not new product permissions. Store the chosen
locator; external configuration cannot supply hidden changes to its repository
binding. If environment-specific expansion is allowed, validate the resulting
route under the selected scope and approved profile before use. A URL username
can identify an account without being a password; preserve explicit SSH users and
validate transport-specific userinfo rather than globally deleting all usernames.

The implementation must publish a finite supported grammar and length/option
limits. Query strings and fragments need a reviewed non-secret allowlist; initial
support can reject them rather than trying to recognize every secret name. Do not
claim URI canonicalization alone solves Git locator equality.

Scope Locator URIs have a separate typed adapter contract: scheme support,
resolution environment, execution meaning, route/configuration compatibility and
finite input limits. Do not assume a URI's syntax proves its safety or dereference
it merely to validate it. `urn:uuid:` identity rendering cannot substitute for
Scope UUID joins or actual environment resolution. The first implementation may
remain explicit/local-only until a remote-environment adapter is reviewed.

## 4. Connection configuration and secret boundaries

Use versioned typed documents by transport, not a free-form `git -c` or shell
command JSON bucket. Candidate non-secret fields include SSH account/default port,
explicit approved SSH profile reference, agent/key reference, known-host policy,
HTTPS credential-helper reference and proxy reference, local path dialect and
permitted filesystem scope. Exact vocabulary and conflict precedence are a later
contract; an explicit locator coordinate wins only when consistent, otherwise fail.

Private key bytes, tokens, passwords, passphrases, secret-bearing proxy URLs and
cookies stay in external facilities. A reference is resolved only in the local
execution context, with appropriate file/agent access controls. Import must not
probe it. The same reference spelling on another machine does not inherit trust.
External settings capable of executing commands require local approval; no remote
configuration may disable TLS/host verification or smuggle shell/helper behavior.
Transport authentication does not authenticate an Exchange sender under ADR 0028.

Access must have restrictive filesystem permissions and non-secret diagnostics.
Typed validation, not just suspicious-key scanning, controls admitted settings.
Treat usernames, private hosts, key paths and credential references as potentially
sensitive even when they contain no secret values. Keep them out of default domain
queries and transfer outputs. Do not claim historical Core provenance is similarly
absent: its separate disclosure policy and original values must remain explicit.

Q-S4 A approval is at the repository-locator/configuration/purpose assignment,
but validity also covers the selected **full Scope registration key**, the actual
Repository binding, reviewed profile contents and destination-local environment.
A-to-B-to-A requires approval for the new A registration, not reuse of T1's grant.
Changes to a Scope route may affect every assignment in that Scope. A display-only
rename need not invalidate grants. Design the full matching approval references
before treating any mutable `approved` bit on a profile as sufficient.

## 5. Resolution, races and repository binding

Proposed application flow:

1. Accept Repository UUID, Scope UUID, explicit Access-store selection and purpose,
   with optional explicit registration/repository-locator/profile selectors.
2. In one coherent Access snapshot, obtain the maximum-time Scope registration set.
   Return a tie or missing saved route without arbitrary winners. An explicit
   supplied local environment can bypass saved route lookup, not authorization.
3. Check the actual repository binding, eligible assignment, local adoption and
   approval of the selected registration/profile/route. The first-choice set is
   not filtered into an implicit older authorized winner. Existing explicit/saved
   repository-locator preferences retain their separate meaning.
4. Freeze non-secret resolved coordinates and reviewed settings into a request plan.
   Release DB transactions before external work; resolve secrets locally. Check
   relevant changes/revocation before dispatch without mixing old and new settings.
5. Execute only a supported read adapter under cumulative finite budgets. Supply
   the actual Repository UUID and unchanged genuine observation/Capture provenance.
6. Reuse the same frozen intent for retries. Do not re-resolve to the newest Scope
   Locator inside an old request or reset its costs. If its route is no longer
   approved, stop continuation; a new explicit operation is not a forged replay.

UUID consistency and matching OIDs cannot authenticate the operator's Scope or
Repository binding. The existing native-acquisition seed check must be reconciled
with registry membership without relaxing catalog pairing or cross-repository
selection. Test multiple repositories independently. Extending Scope management
is not permission to execute arbitrary remote commands or archive ordinary blobs.

## 6. Missing stores, corruption and backup scopes

| Situation | Required behavior |
| --- | --- |
| Core exists; Context and Access absent | Offline Git facts and correctly scoped backup/Exchange remain usable |
| Access exists; Context absent | Saved local/SSH/HTTPS Git settings require no Provider/Source entity |
| Access absent/corrupt | Disable operations depending on those saved settings; diagnose; no silent reconstruction from historical URLs |
| Operational lost | Core/Context/Access remain intact; old continuation/accounting is unavailable, not zero-cost restart |
| Search lost | Existing correct-authority fallback; Access is not a new search authority |
| Core/Context corruption or existing stop | Keep P7 catalog-wide stop; Access must not bypass it |
| Access-only fault independently isolated | Do not falsely mark proven-sound Git history corrupt; broader suspected storage failure still invokes ordinary recovery policy |
| Access configuration restored/imported | Preserve history and original times; candidate display is not execution; destination-local approval precedes use |

Domain backups retain existing Git-only or paired Core+Context semantics and
validation. Add explicit Access-inclusion reporting; do not silently redefine an
old certificate as preserving saved connection settings. Access backup uses its
own coherent SQLite snapshot of **all registrations**, format/constraints/integrity
verification and local activation checks. Preserve Scope UUIDs/times for continuity;
independent fork creates new identity and new registrations without rewriting origin
history. Imported/restored approval is inactive regardless of timestamps or hashes. An environment bundle may identify both components but must not
claim a new atomic three-store domain snapshot. Domain recovery can finish while
access remains unconfigured. SHA-256 checks detect changed bytes, not trusted origin.

No existing P7 protocol, recovery stop file, schema fingerprint or activation
implementation is modified by this proposal. New component formats and ordering
need focused crash/restart tests before shipping. Do not silently delete an old
Access store because it looks rebuildable.

## 7. Context separation and existing data

Do a key-level audit of each provider/repository/source configuration object and
its writers/readers/export/import paths. Preserve real domain attributes and known
Source associations; keep access settings in Access and request-specific frozen
execution settings in Operational. Do not rename the entire existing JSON column
and claim the boundary is solved. Unknown legacy keys require explicit disposition
and a diagnostic, not automatic execution, loss or relocation to an opaque bucket.

This unreleased project needs no runtime backward-compatibility layer. Any later
extraction from a real catalog is an explicit operation into a fresh format with a
report of included, excluded and unresolved information. Leave the original
catalog/backups untouched. Never transform a historical endpoint observation into
an enabled connection, invent a source observation, silently export old credentials,
or rewrite an immutable claim to fit the new model. The current task performs no
real extraction and does not authorize one.

### Current implementation mismatches to correct, not policy to reopen

- `p1_schema.STORES` has four roles; its shared `store_identity` requires a seed
  Repository UUID and catalog-instance UUID. A1 needs independent Access identity
  composition, not merely adding `access` to that tuple.
- `_export_context` copies provider/repository/source configuration JSON. A3 must
  classify actual fields and writers/readers, preserving Source known-positive
  memberships and observed domain URLs while excluding executable settings.
- `acquire_from_native` compares request Repository UUID to the Core seed and
  freezes `source.path`/intent in progress. A4 must support registry membership
  without weakening pairing and must preserve that frozen-retry invariant.
- `GitNativeSource` is explicit/local, not a Scope-URI executor. Storage support
  must not be advertised as container/SSH/HTTPS execution support.
- P7's `git_only`/`paired` artifacts cover Core/Context, not Access. Preserve these
  meanings; A5 independently includes registration history and inactive grants.
- Schema 21 `repository_endpoints` is a repository address registry, not Scope
  history. No automatic rename/extraction can infer Scope UUID or registration time.

## 8. Design-first dependency plan

| Stage | Depends on | Deliverable / boundaries |
| --- | --- | --- |
| A0: design acceptance | PR #95 and later design/independent reviews; ADR 0029 accepted 2026-10-19 | **Completed governance step**: preserve Scope Q-S choices and the ADR 0003 carry-forward, retire the old active file and update current links. A1 physical-key/registration review remains independent |
| A1: Access contract and schema | A0 | Scope UUID/registration/profile/assignment types, direct PK/FK and immutable-history guards, independent Access schema/initializer and static validators; no default runtime switch |
| A2: resolver and local configuration API | A1 | Append registration, list history, maximum-time candidate set, full-registration-aware approval, secret references and frozen request plan |
| A3: Context/Exchange separation | A1 | Key-level routing ledger, typed domain registration JSON, export/import rejection of executable settings, explicit configuration-transfer boundary |
| A4: acquisition integration | A2; A3 where mixed intake applies | Resolve selected repository, fix seed-versus-registry restriction with pairing tests, safe adapter wiring, no ordinary file archival |
| A5: backup/restore integration | A1/A2 and existing P7 | All-registration Access snapshot/bundle, continuity versus fork, original time preservation and disabled-on-restore activation |
| A6: independent integration review | A3/A4/A5 | Exact-tree attack/packaging tests and handoff; any P8/default switch is separately authorized |

A2 and A3 may be sibling workstreams after the common A1 contract. A5 may proceed
in parallel with A4 when shared interfaces are fixed. Assign disjoint file ownership;
shared coordination/schema changes require one explicit dependency PR. Subagents
and independent reviewers are permitted. Do not repeat entire historical suites
merely for prose or mistake a development smoke pass for release acceptance.

## 9. Required counterexamples (not executed tests)

1. One repository has HTTPS, SSH and local locators; editing one leaves its UUID
   and earlier Core evidence byte-for-byte unchanged.
2. Same locator text in two scopes resolves independently; conflicting UUIDs for
   the same scoped locator are rejected without merging or overwriting either ID.
3. Multiple profiles are reusable across locators; profile rotation does not
   change locator keys, captures or Source memberships.
4. A preference for repository A cannot point to repository B's assignment;
   composite FK attacks and missing parents fail.
5. Scope Locators use maximum registration time; equal-time first choices remain
   ambiguous. No lexical/rowid/arrival tie-break or implicit cross-account fallback.
   Repository/profile preferences do not inherit this new timestamp rule.
6. Git-only saved access works with no Context; Core-only offline use works with no
   Access. An imported domain catalog cannot start network work.
7. Different SSH aliases, scp-relative/URI-absolute paths, percent escapes, `.git`,
   trailing slashes, IPv6, symlinks, Windows drive/UNC and relative bases retain the
   declared semantics; unsupported inputs fail without changing files/credentials.
8. Malicious helper syntax, shell options, proxy URLs, embedded secrets and import
   activation attempts are rejected before external side effects; no secrets leak
   to saved plans, logging, manifests or domain Exchange.
9. Disabling a Scope route retains all registration facts. Removing mutable
   repository/profile configuration does not delete Scope history, Source
   known-positive pairs, Core objects/captures or Context evidence.
10. Concurrent configuration edits cannot combine one version's locator with
    another version's credentials; request plans, cancellation and retries are
    consistent and keep original observation identity and cumulative work.
11. Additional repositories beyond the Core seed can acquire independently without
    weakening catalog pairing, UUID selection or cross-repository Exchange fences.
12. An Access backup made with live WAL is coherent; interrupted/invalid restore is
    not activated. Continuity preserves Scope UUID/history, but another machine's local execution
    binding and approvals are not inherited.
13. Missing/isolated corrupt Access yields honest access errors; proven-sound domain
    reads still work; a real Core/Context stop is never bypassed.
14. Context key classification preserves provider facts/observed URLs but rejects
    transport configuration in ordinary domain Exchange. Historical provenance is
    not silently redacted or advertised as free of location information.
15. Real-data extraction is opt-in, leaves sources unchanged and reports excluded
    or unclassified legacy settings instead of guessing or executing them.
16. Wheel/sdist behavior, schema/FK/immutability checks and P7 domain backup scope
    remain consistent at the exact integrated tree; ordinary file bodies remain
    excluded and ADR 0028 time/trust rules remain intact.

17. Same display name with different Scope UUIDs remains distinct; rename leaves
    FK/external references unchanged; a URI/URN is never a substitute identity.
18. A(T1), B(T2), A(T3) retains three rows; T3 wins; exact replay keeps row count/time.
19. Same-time different URIs coexist; query returns both regardless of insertion
    order and regardless of only one being approved.
20. Clock rollback, late replay and restore never fabricate a fresh timestamp;
    unknown/invalid/bool/float/string/overflow input receives the reviewed diagnostic.
21. Newest unapproved/disabled/unsupported route blocks default execution; it never
    silently promotes an older approved route. Imported future times grant no trust.
22. Changing Scope route/profile/binding invalidates affected reviewed plans;
    returning to the same URI at T3 cannot reuse approval for T1.
23. A continuing Scope migration preserves UUID and old facts; an independent fork
    allocates new Scope UUID and does not relabel original S1 history as S2 history.
24. Backup/restore round-trips every registration, not just MAX(time), with local
    reapproval; Core offline operations still work without Access.
25. Generic UPDATE/DELETE/REPLACE/mutating upserts and Scope-deletion cascades cannot
    erase or rewrite immutable registration coordinates on supported connections.
26. Current request replay cannot silently switch routes after a newer registration;
    unchanged old intent and cumulative-work accounting remain intact.

## 10. Execution checkpoint and remaining gates

The checkpoint below is historical. For the integrated A1-A5 candidate and the
remaining A6 review gates, see [A6 integration review](../implementation/access-a6-integration-review.md).


The 2026-10-17 task begins with design documentation, not production DDL or a P8
switch. The reviewed main is S1 and the starting PR #95 HEAD is
`2fec656e61a9c247e50ceefc3ee6bb7af213951a`. The two original design-document bytes
were verified against their Git blob hashes before editing. A fresh local clone
attempt failed DNS resolution; the GitHub connector is used for source review and
atomic publication. The local SQLite binding is 3.46.1, below P1's required 3.51.3;
any disposable SQL semantic probe is not a P1/Access runtime acceptance test.

Progress sequence: baseline/authority review -> confirmed-decision reconciliation
-> local diff/frontmatter/reference and disposable selection probes -> one atomic
PR-branch commit -> remote changed-file/HEAD/CI verification. The actual PR update
reports executed checks and any failures. Full-checkout MkDocs, product pytest,
packaged Access DDL, installed wheel/sdist tests and independent-agent review are
not claimed by this documentation checkpoint. The 26 counterexamples are future
product acceptance requirements even where a small isolated probe demonstrates
one SQL property. No production test or source file is added or changed here.

A0's **complete replacement acceptance/ADR 0003 retirement was explicitly
approved on 2026-10-19** and documented in a separate stacked governance PR.
Historical checkpoints above remain historical; A1's engineering choices and
actual implementation/merge/release gates are not thereby approved.
Confirmed owner choices are not reopened. A1 must review the direct
registration-fact key, typed option/URI support, immutable controls and precise
approval references. These engineering contracts do not justify another generic
owner questionnaire. A request to begin work does not silently accept every old
sharing/scheme/adapter proposal or authorize a merge. Independent executable
review and explicit runtime adoption remain distinct gates.

## References

- [Accepted ADR 0029](../adr/0029-independent-access-store.md),
  [ADR operating policy](../adr/policy.md).
- [P1 schema contracts](../implementation/p1-schema-contracts.md),
  [P1 routing reconciliation](../implementation/p1-reconciliation.md),
  [P7 recovery design](../implementation/p7-backup-recovery-technical-design.md).
- [S0 Core DDL](https://github.com/TakashiSasaki/git-repo-db/blob/5e778bf61ef660f65bf5fb22bdb08840503b8464/src/repo_catalog/adapters/sqlite/p1_ddl/core.sql).
- [S1 Core DDL](https://github.com/TakashiSasaki/git-repo-db/blob/b2a87cfc6562413d9ecde7f4329e90c434ae9aad/src/repo_catalog/adapters/sqlite/p1_ddl/core.sql),
  [S1 schema manifest](https://github.com/TakashiSasaki/git-repo-db/blob/b2a87cfc6562413d9ecde7f4329e90c434ae9aad/src/repo_catalog/adapters/sqlite/p1_ddl/fingerprints.json),
  [S1 Context DDL](https://github.com/TakashiSasaki/git-repo-db/blob/b2a87cfc6562413d9ecde7f4329e90c434ae9aad/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql),
  [S1 Exchange export](https://github.com/TakashiSasaki/git-repo-db/blob/b2a87cfc6562413d9ecde7f4329e90c434ae9aad/src/repo_catalog/application/exchange.py#L831-L889),
  [S1 acquisition](https://github.com/TakashiSasaki/git-repo-db/blob/b2a87cfc6562413d9ecde7f4329e90c434ae9aad/src/repo_catalog/application/acquisition.py).
- [Git URL forms](https://git-scm.com/docs/git-clone#_git_urls),
  [Git URL rewriting and protocol configuration](https://git-scm.com/docs/git-config),
  [OpenSSH host/profile resolution](https://man.openbsd.org/ssh_config).
- [UUID/URN representation and security](https://www.rfc-editor.org/rfc/rfc9562.html),
  [SQLite SELECT](https://www.sqlite.org/lang_select.html),
  [SQLite foreign-key limitations](https://www.sqlite.org/foreignkeys.html).
