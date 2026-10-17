# A1b Access repository bindings, connection settings and local consent

Status: opt-in implementation on A1a PR #96, exact parent
`9d44a58867f32a42d2eee90d81bd9f7f2cc2a456` (tree
`1a6ea243909c305e0a7eb9caad05e3fd7a32b5d2`). The owner requested continuing
implementation on 2026-10-17. Read the [A1 contract](access-a1-contract.md)
and [Scope registry stage](access-a1a-registry.md). This work does not retire
ADR 0003, mark all of ADR 0029 accepted, merge a branch, migrate real data,
activate P8, or implement a transport executor.

## 1. Physical format and ownership

This is a fresh unreleased Access format `repo-catalog/access-2`, schema version 2.
The registry-only version is rejected, not migrated or silently rewritten. Core,
Context, Operational, Search and the normal Schema 21 initializer are unchanged.
Do not add Access to P1's repository-seed/instance loop.

The existing four Access tables remain: access_identity, access_scopes,
scope_locators, scope_locator_controls. Six further relations are now packaged:

| Relation | Direct key and purpose |
| --- | --- |
| scope_execution_contexts | Scope UUID; declared executor/identity view and enablement |
| repository_locators | Scope UUID + exact Git locator; one current Repository UUID |
| connection_configurations | Scope UUID + operator profile name; canonical typed options |
| locator_connections | Scope + locator + profile + git-read purpose |
| repository_access_preferences | Repository UUID + Scope + purpose, with BOTH assignment and repository-binding FKs |
| local_access_grants | Assignment key; full original Scope registration triple, Repository UUID and exact reviewed options/context |

All ten tables are STRICT/WITHOUT ROWID. No second locator history, event UUID,
sequence, digest identity, mutable current-Scope-locator pointer or Core FK is added.
The separate context row is current execution configuration, not Scope identity or
historical location. Labels may repeat and change without rekeying Scope.

Scope registrations keep `(scope_uuidv4, registered_at_us, scope_locator_uri)`.
Exact replay does not retimestamp, restore deleted controls, enable a route or
restore consent. Repository rebinding is an explicit expected-prior-value operation;
it revokes grants and removes preferences belonging to the former binding in the
same transaction. Initial registration conflicts instead of overwriting a UUID.

## 2. Module and API boundary

- `domain/access_connections.py`: finite validated configuration/selection/grant values.
- `domain/ports/access_connections.py`: typed opt-in persistence/read contracts.
- `adapters/sqlite/access_connections.py`: AccessConnections extends AccessRegistry.
- `access_ddl/connections.sql`: local FKs, grant-content guards, transport consistency
  and transactional invalidation triggers.
- `access_schema.py`: packaged composition, stored-value validation and unchanged
  real SQLite >=3.51.3/POSIX gate. `access_registry.py` allows trusted trigger-driven
  DELETE only on current grants, never registration history.

Writes use full expected-prior-value comparisons. Omitted expected values mean
initial registration/exact replay, not blind upsert. No-op updates keep grants.
Explicit settings updates, reference checks and invalidation commit as one unit;
body/constraint/COMMIT failure rolls everything back. No public generic SQL exists.
Only three additional Python modules are added to the exact isolated ownership
list; no prefix exclusion or baseline audit regeneration is introduced.

## 3. Finite input grammar, not execution support

Repository locators retain exact supported HTTPS/SSH/local file URIs, absolute
ASCII POSIX paths, and a bounded scp-like subset with multi-character host names.
No relative caller path, Windows drive/UNC, helper syntax, query, fragment,
embedded password, whitespace/control byte or implicit normalization is admitted
by this first POSIX adapter. Unsupported Git forms are explicitly unsupported,
not declared universally invalid. A1a Scope URI grammar remains separate.

Profile JSON is canonical and versioned. File profiles require POSIX dialect;
HTTPS may reference a named local credential helper; SSH may reference an agent/key
name and an approved local SSH profile name. These references use bounded local
names, not filesystem reads, tokens, keys or commands. Options outside the allowlist,
including TLS/host-check overrides and ProxyCommand, are rejected. Normal path
segments/reference names can still contain sensitive operator information; this
is not a detector for secrets intentionally disguised as names.

The execution-context record has version, executor_kind, executor_ref, identity_view
and POSIX dialect. It is a locally DECLARED value, not attestation of an actual
machine. local/ssh/container values are representable; remote/container execution,
credential lookup and probing are not implemented by this stage.

## 4. Review, consent and first-choice ordering

`review_plan` reads one coherent snapshot. Default Scope selection computes the
complete maximum original registration-time set BEFORE controls or grants. Ties
require explicit selection, even if only one route is enabled/approved. No eligible
newest route means an error, not fallback to an old registration. An older route
can be chosen explicitly and requires that exact registration's grant.

Repository selection is separate: explicit assignment, valid saved preference or
one eligible assignment. It never uses grant availability to pick among ambiguous
accounts/profiles. A disabled saved preference is not permission to choose another.
Bounded candidate overflow is a limit error, not truncation to a winner.

`record_local_approval(plan, approved_at_us)` is a TRUSTED LOCAL ADMINISTRATION call,
not an import/intake endpoint. It rechecks the entire shown plan before replacing
one current grant. SQL checks prove matching references/settings; they do not prove
that a human clicked approve. A2 still owns the actual local review UI and separately
activated executor. `current_grant` returns stored consent, NOT a dispatch capability.
No current API starts network work, accepts imported approval flags or resumes work.

Material profile/context/binding/assignment/route changes remove affected grants in
the same transaction. A -> B -> A never revives an old grant. Same-content updates
and display labels alone do not revoke. A new registration does not erase an old
explicit-route grant, but cannot borrow it for the new registration (including
A-at-T1 -> B -> A-at-T3). Failed reapproval restores the prior committed grant.

Each A1b operation validates the complete Access snapshot before joining candidates.
This catches missing parents that a join would otherwise hide as "unconfigured".
Stored schema/domain/FK errors cannot become a valid alternate route. This choice
has O(registry size) validation cost per call and is not a large-catalog throughput
claim. Future optimization must retain equivalent evidence without a mutable domain
counter or suppressed integrity checks. Existing Access-only stop and read-only
preflight remain; P7 power-loss/completion-fencing guarantees are NOT claimed here.

## 5. Verification and retained failures

Executed locally on Python 3.13.5 with ACTUAL SQLite 3.51.3 from the SHA-256-verified
A1a CI artifact. sqlite_source_id matched the official 3.51.3 release. No minimum
runtime override exists. Focused tests: **219 passed**, zero failures/errors/skips;
this includes the prior 114 cases plus 105 new cases. A separate existing P1 schema
cohort passed **15 tests**. Four baseline audits passed without regenerating their
historical inventories. Ruff 0.16.10 lint and format are checked before publication.

Seven deliberate mutations produced one assertion failure each, with zero setup
errors: profile/context/route ABA revocation, profile REPLACE guard, enabled-filtered
latest ranking, replay reenablement, and snapshot validation before FK-sensitive
joins. Some are detected by remaining integrity defenses rather than by permission
execution; this is not an exhaustive mutation score or independent review.

Initial new tests had 204 passes and two setup failures: a JSON-reading trigger
rejected a privileged malformed-UTF8 profile UPDATE before corruption was stored.
The fixture was changed to corrupt the execution-context TEXT while keeping product
triggers intact; no detector was weakened. Two schema-audit launches initially lacked
PYTHONPATH and failed to import repo_catalog; reruns with PYTHONPATH=src succeeded.
Retain those raw failures alongside corrected receipts.

Focused CI is extended to all Access values and both installed distribution variants.
Hosted results must be read from the exact PR HEAD/effective tree, not inferred from
this local report. The local environment initially lacked hatchling and could not
retrieve its locked wheel; local build results must not be fabricated. No independent
subagent or reviewer has been launched. Test and mutation review is author-performed.

See the [reusable consent/SQLite review note](../../.agents/skills/three-store-invariants/references/access-consent-guards.md).

## 6. Remaining stages

A2: actual operator review, executor activation/context verification and pre-dispatch
revocation boundaries. A3: Context/Exchange key-level separation. A4: acquisition and
multi-repository seed reconciliation, original retry-plan identity. A5: coherent
Access backup, disabled-on-restore consent removal, UUID continuity versus fork.
A6: independent exact-tree integration review and ADR replacement completion.
No backup/import API is added here; copying privileged raw files is outside supported
transfer and must never be treated as executor approval. These limitations remain
explicit even when every storage test passes.
