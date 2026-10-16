# Access store: locator/configuration separation and implementation contract proposal

**Status: design proposal; no runtime changes.** Read [ADR 0029](../adr/0029-independent-access-store.md)
for the owner-established direction, proposed detailed decisions, invariants and
acceptance-time ADR lifecycle. This document is the concrete storage/source audit
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
It owns no Git bodies, Provider text, Coverage or Source inventory. It is optional
for offline domain use but non-disposable once saved settings exist. It need not
share Core's seed repository or catalog-instance identity; a proposed Access store
is an installation-level configuration namespace and may address several catalogs.
Two files are never conflated merely because both use a scope named `default`.

| Proposed relation | Direct primary key | Principal other columns / constraints |
| --- | --- | --- |
| `access_identity` | `store_role` constrained to `access` | Format/version; exactly one row validated by the initializer; no repository seed or new domain ID required |
| `access_scopes` | `access_scope` | Explicit local resolution/identity-view name, path dialect, description; no automatic hostname-derived portability |
| `repository_locators` | `(access_scope, locator_text)` | `repository_uuidv4`, syntax kind, enabled state; scope FK; UUID syntax validation; unique `(access_scope, locator_text, repository_uuidv4)` for matching preference FKs |
| `connection_configurations` | `(access_scope, configuration_name)` | Transport kind, versioned typed options, optional typed credential reference, local approval/enabled state; scope FK |
| `locator_connections` | `(access_scope, locator_text, configuration_name, purpose)` | Enabled state; composite FKs to locator and configuration, in the same scope |
| `repository_access_preferences` | `(repository_uuidv4, access_scope, purpose)` | Selected locator/configuration; composite FK to the assignment AND to its actual repository binding |

This is a six-relation logical proposal, not a frozen physical table count.
`purpose` initially denotes read acquisition (`git-read`); it is not authorization
to implement push or repository mutation. Different adapters may use that same
purpose; do not create a fake Source entity for it. Required key columns are
non-null with exact comparison. Prefer STRICT/WITHOUT ROWID for direct composite
keys, subject to the implementation contract and actual SQLite validation.

A preference needs **both** relationships: the selected assignment must exist,
and its locator must belong to that same repository. A convenient FK to a locator
alone must not allow repository A to select B's endpoint. All these FKs are local
to Access. The UUID reference to Core is portable/application-checked, not a
cross-file SQLite FK. No Core or Context row depends on an Access row.

Profile names/scopes are intentional local configuration coordinates, not generated
aliases for a hidden natural key. Renaming one requires an explicit atomic local
key/reference update, not a change to domain identity. Human display labels may
change independently. No locator/profile numeric/UUID row surrogate or hash-only
key is introduced. A whole-row digest can be an optimistic-concurrency token,
never domain identity, sender authentication or permission to activate settings.

### Examples of distinct roles

Repository R may bind in scope `workstation` to:
`https://git.example/team/project.git`, `git@git-work:team/project.git`, and
`file:///srv/git/project.git`. Its HTTPS, SSH-agent and local-file configurations
are separate named rows. A shared SSH configuration can serve other repositories'
locators. Another scope `container` can resolve the same file URL differently.

The tuple, not raw URL alone, is the actual key. Within one scope, assigning that
same file URL to repository S conflicts until explicitly rebound. No rule concludes
R equals S. Credential-dependent servers that expose different repositories under
the same URL require different identity-view scopes, not two silently competing
profiles in a scope claiming one repository. Even a matching Git OID set cannot
prove the local UUID assertion to be globally correct.

## 3. Locator grammar and equality contract

The string is an address, not a serialized object containing credentials or an
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

## 5. Resolution, races and repository binding

Proposed application flow:

1. Accept repository UUID, explicit Access store/scope, purpose and optional locator
   or profile selection. Validate local authorization without contacting the target.
2. Read a coherent Access snapshot. Check binding, enabled/approved profile, exact
   assignment and preference, supported transport and credential-reference shape.
   An explicit request is not permission to override a conflicting stored binding.
3. Select the requested eligible assignment, one valid saved preference, or the
   sole eligible candidate. Otherwise return `ACCESS_UNCONFIGURED`,
   `ACCESS_AMBIGUOUS`, `ACCESS_BINDING_CONFLICT` or a typed policy error; do not guess.
4. Freeze the non-secret resolved plan and release Access transactions. Resolve
   secrets locally and check authorization before a new external operation. A
   stale/changed selection before dispatch requires a fresh resolution, not
   silently mixing old location and new credentials.
5. Execute only a supported read adapter under the finite request budget. Supply
   actual repository UUID and original capture/provenance to existing admission.
   No network call occurs while holding a database write transaction.
6. Preserve facts from the completed request's actual plan, even if later settings
   change. Explicit cancel/revocation governs in-flight cancellation; configuration
   edits are not retroactive evidence edits. Retries retain request identity and
   cumulative charges and recheck local approval, never resume at zero after loss.

Same-origin or same-OID checks can identify inconsistencies but cannot prove a
repository UUID binding. Diagnostics must distinguish an operator-established
binding from externally verified content and remote origin. Do not repurpose the
catalog seed as every repository's ID. Add independent multi-repository tests
before lifting the currently observed acquisition restriction.

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
| Access configuration restored/imported | Offline inspection allowed; local scope mapping and approval precede execution |

Domain backups retain existing Git-only or paired Core+Context semantics and
validation. Add explicit Access-inclusion reporting; do not silently redefine an
old certificate as preserving saved connection settings. Access backup uses its
own coherent SQLite snapshot, format/constraints/integrity verification and local
activation checks. An environment bundle may identify both components but must not
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

## 8. Design-first dependency plan

| Stage | Depends on | Deliverable / boundaries |
| --- | --- | --- |
| A0: design acceptance | This design PR | Settle proposed details; complete ADR 0003 carry-forward/retirement and index/current-link updates coherently; no new migration-policy exception |
| A1: Access contract and schema | A0 | Typed locator/scope/profile/assignment values, direct PK/FK constraints, independent schema/initializer and static validators; no default runtime switch |
| A2: resolver and local configuration API | A1 | Deterministic selection, local approval, secret references, immutable request plan and standalone Git-only path |
| A3: Context/Exchange separation | A1 | Key-level routing ledger, typed domain registration JSON, export/import rejection of executable settings, explicit configuration-transfer boundary |
| A4: acquisition integration | A2; A3 where mixed intake applies | Resolve selected repository, fix seed-versus-registry restriction with pairing tests, safe adapter wiring, no ordinary file archival |
| A5: backup/restore integration | A1/A2 and existing P7 | Optional Access snapshot/bundle, scope-aware output and disabled-on-restore activation |
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
5. Equal eligible candidates cause ambiguity; no lexicographic, timestamp, source
   arrival or implicit cross-account fallback chooses a winner.
6. Git-only saved access works with no Context; Core-only offline use works with no
   Access. An imported domain catalog cannot start network work.
7. Different SSH aliases, scp-relative/URI-absolute paths, percent escapes, `.git`,
   trailing slashes, IPv6, symlinks, Windows drive/UNC and relative bases retain the
   declared semantics; unsupported inputs fail without changing files/credentials.
8. Malicious helper syntax, shell options, proxy URLs, embedded secrets and import
   activation attempts are rejected before external side effects; no secrets leak
   to saved plans, logging, manifests or domain Exchange.
9. Deleting a locator/configuration does not remove Source known-positive pairs,
   Core objects/captures or Context evidence.
10. Concurrent configuration edits cannot combine one version's locator with
    another version's credentials; request plans, cancellation and retries are
    consistent and keep original observation identity and cumulative work.
11. Additional repositories beyond the Core seed can acquire independently without
    weakening catalog pairing, UUID selection or cross-repository Exchange fences.
12. An Access backup made with live WAL is coherent; interrupted/invalid restore is
    not activated. Another machine's scopes and approvals are not inherited.
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

## 10. Verification scope of this design update

This is a repository/API source review and documentation change, not a runtime
acceptance run. The ADR index, accepted governance, ADR 0003's full current scope,
current schema manifest, Core identity/claims, Context registration/Exchange path,
acquisition restriction and relevant P7 interfaces were inspected. Official Git
and OpenSSH documentation informed the syntax/scope discussion.

A network-isolated local runtime could not clone the repository. Local checks are
limited to authored Markdown/frontmatter, direct-key/coverage invariants, link
coordinates and exact changed-file diff review; no full checkout-based MkDocs,
pytest, packaged schema construction or independent reviewer execution is claimed.
The PR records actual performed checks and remote changed-file verification.
The counterexamples above remain future acceptance requirements.

## References

- [ADR 0029 proposal](../adr/0029-independent-access-store.md),
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
