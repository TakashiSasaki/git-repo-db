# A1 Access registration and local-approval contract

Status: engineering review contract, 2026-10-17. This specifies the next step after
PR #95 at `cf90c093089911acbfd3c8c2c7778a9ff8904bc6`; it does not activate Access,
accept unselected sharing policies, retire ADR 0003 or switch the public runtime.
Owner-confirmed Q-S1-Q-S4 A and same-table timestamped registration history in
[ADR 0029](../adr/0029-independent-access-store.md) are inputs, not open questions.
The [replacement review](access-adr-replacement-review.md) separates the remaining
lifecycle gate from this scoped contract. Product implementation is still downstream.

## 1. Direct keys and registered-fact meaning

Use these complete semantic keys, without storage-only aliases:

| Value | Ordered coordinates | Equality / lifecycle |
| --- | --- | --- |
| Scope | `scope_uuidv4` | Canonical UUIDv4; same logical environment survives location changes |
| Registration | `scope_uuidv4, registered_at_us, scope_locator_uri` | Exact fact-set equality; same triple replays once |
| Repository binding | `scope_uuidv4, locator_text` | At most one current repository UUID |
| Profile | `scope_uuidv4, configuration_name` | Named mutable local settings, not a host identity |
| Assignment | `scope_uuidv4, locator_text, configuration_name, purpose` | One locator/profile/use relationship |
| Preference | `repository_uuidv4, scope_uuidv4, purpose` | Must reference both assignment and matching repository binding |
| Local grant | Assignment key | One current permission for the full reviewed plan; not an event-history UUID |

For registration, URI A at T1 and A at T3 are different facts. Different URIs at
one time coexist. Independent identical triples intentionally collapse to one
registration fact; this does not count write attempts or identify independent
Git captures. Capture occurrence rules remain untouched. API retries must carry
the original triple, not request another timestamp on every attempt. A new user
registration measures a real time; no timestamp+1, sequence or extra UUID forces order.

All key columns are non-null and exact. Scope UUID strings use the existing
canonical lowercase UUIDv4 validator. Registration time is required positive int64
Unix epoch microseconds; Python input rejects bool, float, numeric text and overflow
before SQL. No default now() exists in DDL. Undated old material stays outside the
active registration relation with a diagnostic; an explicit new local registration
may record now as a NEW operation, never as the unknown past. Restore retains times.

Human labels may repeat. Scope renaming changes labels, not UUID/FKs. URI-only
search returns candidates, not identity equivalence. Scope URI syntax is separate
from repository Git URI/scp/path syntax. This contract does not authorize executing
an arbitrary stored URI. Finite grammar/option limits belong to the adapter contract.

## 2. Immutable registrations and mutable controls

`scope_locators` contains the three immutable registration coordinates. Its UPDATE,
DELETE and implicit REPLACE-delete paths are rejected on supported connections.
Exact INSERT replay is compared/deduplicated without touching approval or controls.
There is no separate history table, mutable current-location column or latest-row ID.

The executable probe additionally models `scope_locator_controls`, directly keyed
by that registration triple, for current route enablement. It is NOT a second copy
of history or a selected-current-locator authority. Missing controls mean not enabled;
registration history still exists. It illustrates one engineering way to keep facts
immutable while permits can be disabled. Combining controls elsewhere is acceptable
only with equivalent tested invariants; the final product table count is not fixed.

Creating a new registration and its initial controls is one transaction/savepoint.
Repeating the same registration cannot recreate deleted controls, re-enable a route
or reinstate a grant. A failed second statement rolls back both statements.

## 3. Ranking before permission checks

The default first-choice set is the maximum original `registered_at_us` among
registrations of that Scope. Do NOT filter by enabled/approved/available before MAX:
otherwise disabling the newest location silently promotes an older one.
A read view/ordered index can compute the set; a total-order row ID cannot resolve ties.

| State | New default request |
| --- | --- |
| No registrations | Unconfigured; no implicit network acquisition |
| One latest registration and valid local grant | Resolve and verify actual executor context before dispatch |
| Several latest registrations | Ambiguous; an explicit choice is necessary even if only one has a grant |
| Latest unapproved, disabled, unsupported or unavailable | Report that state, not automatic fallback |
| An older registration is selected explicitly | Require that exact registration's still-valid grant; no inherited approval from another record |
| Clock goes backwards | Maximum timestamp remains first; diagnose anomaly, do not invent order |

Explicit selection is deliberate route choice, not automatic failover. It cannot
bypass Scope/repository binding or local authorization. This Scope-location rule
does not replace Repository preference/assignment selection with registration order.
An already frozen retry continues only its original permitted plan; it must never
re-resolve to the latest location under the same request/Capture/budget identity.

## 4. Approval references: exact rows AND exact content

Proposed `local_access_grants` uses the assignment PK and stores:

- `repository_uuidv4` with FK `(scope_uuidv4, locator_text, repository_uuidv4)`
  to the actual binding's matching UNIQUE tuple;
- `registered_at_us, scope_locator_uri` with FK of the full registration triple;
- full canonical reviewed profile options and reviewed execution-context values;
- an actual local `approved_at_us`, advisory for audit, never a ranking key.

The assignment FK includes purpose; no cross-Scope profile can satisfy it. The
profile/Scope/route/assignment/binding must all be enabled. Approval is a trusted
explicit local operation after the user sees the resolved non-secret plan. SQL
constraints prove references/content match; they do NOT prove that a human clicked
approve. The application authorization boundary owns that fact. Restored or imported
rows never constitute a new local grant merely because their keys or hashes match.

The reviewed context contains the selected route, executor identity-view, adapter
version and relevant non-secret resolution inputs. It is an exact structured value,
not a hash-only authority or a new domain ID. External adapters supply and recheck
real inputs such as path dialect, approved alias resolution and host verification
policy. No URI lookup dereferences arbitrary configuration or executes imported code.
The probe uses a tiny fixed fixture JSON instead of pretending to implement this.

### 4.1 No ABA permission resurrection

Content comparison at dispatch alone is insufficient: options A -> B -> A would
match an old A grant again. Therefore supported edits invalidate affected grants
in the SAME transaction, even if settings later return to their former values.

| Change | Required invalidation |
| --- | --- |
| Profile options/credential reference/enablement | All grants using that profile |
| Repository binding/locator enablement | Grants for that repository locator |
| Assignment enablement or identity | Grants for that assignment |
| Scope execution-context/enablement | Grants in that Scope |
| Route controls disabled/deleted | Grants selecting that exact registration |
| Display label only | No invalidation solely for label change |
| New registration | Old grant cannot authorize new triple; default ranking changes independently |

No-op content-preserving profile updates need not invalidate. Scope/profile/assignment
REPLACE is not an alternative to the explicit update/review path. Removing current
grants is permitted; it does not delete historical locator facts or Core evidence.
A failed reapproval rolls back and leaves the prior committed permission unchanged.

### 4.2 Dispatch and local activation

A safe new-request sequence is: choose coherent Scope/Repository candidates; read
one Access snapshot; compare exact references and full reviewed values; require
locally established executor activation; freeze a non-secret plan; release DB
transactions; verify local permission/context just before external dispatch. No DB
write transaction spans network work. No global instantaneous revocation claim is
made: cancellation boundaries and already-running operations must be explicit.

A boolean supplied by an imported record is NOT executor activation. Supported
restore/import APIs create a fresh target, remove local grants and disable route
controls before exposing it. Activation/reapproval uses local authority that is not
part of a transfer package. Raw privileged DB replacement is outside the supported
API; the design does not claim filesystem-owner tamper resistance. Core/Context
recovery stop always takes precedence, even with apparently valid Access permits.

## 5. Continuity, fork and backup

For logical continuation, retain Scope UUID and all original registrations. Recheck
actual execution context locally. For an independent fork, allocate a new Scope UUID;
copy intended CURRENT settings only through explicit new registration operations.
Do not rewrite S1/T1 history to S2/T1. The original history remains attributable to
S1; no ancestry table or historical-event UUID is needed for this scoped contract.
Repository UUIDs are not changed by Scope fork, migration or approval.

Access backup includes ALL registration rows. Restoring a backup is not registering
every old URI now; otherwise old locations jump to first place. Back up with SQLite's
coherent backup interface, including committed WAL state. Supported restore clears
local execution permissions, preserves facts, validates FKs/domain/format, and never
silently repairs/overwrites a suspect source. Existing P7 git_only/paired domain
backup meanings and catalog-instance/seed pairing remain intact. Access deployment
sharing policy is intentionally not selected by this one-explicit-store contract.

## 6. Product handoff and ownership

The existing main remains `b2a87cfc6562413d9ecde7f4329e90c434ae9aad`. Its P1 schema
requires four role/seed/instance identities; Access must not be added to that loop
without an independent ownership/initializer contract. Reuse validated UUID/time
helpers without importing Core or Context as a runtime dependency of Access.
No Access FK enters Core and no Git observation/Coverage `scope` is renamed.

A1 product implementation owns typed Access values/ports, packaged DDL/initializer,
trusted writer/read boundaries, constraints and installed-distribution tests. Freeze
those module names/ports in one shared PR before sibling A2/A3 work. A2 owns actual
resolver/local approval operations and supported adapters; A3 owns Context registration
key classification and Exchange exclusion. A4 integrates acquisition without replacing
its frozen source intent or weakening multi-repository/pairing fences; A5 owns Access
backup integration separately from unchanged P7 domain guarantees. Independent A6
must exercise the exact combined tree, not infer validity from this prototype.

Outstanding product gates: supported SQLite >=3.51.3 and packaged schema audit;
finite typed URI/profile grammar and real authorization adapter; product concurrency/
crash/restore tests; exact-tree independent review; ADR replacement integration.
No generic owner questionnaire is needed for the confirmed direct-key/ranking work.
Unselected multi-catalog sharing and arbitrary remote/container execution remain
out of this narrow contract, not implicit new promises or global blockers.

## 7. Executable review artifacts and limits

Run only in a disposable checkout or extracted artifact directory:

```sh
python docs/implementation/access-a1-review/contract_probe.py --json /tmp/access-a1.json --junit /tmp/access-a1.xml
python docs/implementation/access-a1-review/mutation_probe.py --json /tmp/access-a1-mutations.json
```

The [SQL model](access-a1-review/schema_probe.sql) and
[contract tests](access-a1-review/contract_probe.py) are DOCUMENTATION PROBES, not
product adapters, packaged schema, actual approval UI or credential/transport security.
The URI check is deliberately limited to fixture values. A caller boolean models
local activation; it is not a product authorization mechanism. The WAL test is real
SQLite I/O in a disposable directory, not P7 power-loss/recovery acceptance.

The [mutation experiment](access-a1-review/mutation_probe.py) deliberately removes
selected protections. Five invariant failures and one remaining-FK rejection are
expected; arbitrary setup errors do not count as detection. The first run classified
that FK rejection separately (5/6 assertion detections), not as a product defect;
its receipt is retained. The revised receipt names the redundant FK defense.

Read [review evidence](access-a1-review/README.md) for exact file hashes, runtime,
counts and unexecuted work. No independent subagent was available for invocation;
the review here is author-performed static analysis and executable counterexamples,
not independent approval. A handoff procedure is included for an actual independent
reviewer. No src/, existing product DDL, main, deployment or runtime was changed.

## Primary technical references

- [SQLite composite FK requirements](https://www.sqlite.org/foreignkeys.html):
  match a real primary/unique parent key and enable enforcement per connection.
- [SQLite conflict handling](https://www.sqlite.org/lang_conflict.html): REPLACE's
  implicit delete needs deliberate protection; recursive triggers are required.
- [SQLite backup API](https://www.sqlite.org/backup.html): coherent live snapshots.
- [ADR 0017](../adr/0017-domain-keys-without-storage-surrogates.md),
  [ADR 0028](../adr/0028-classified-times-and-sha256-exchange.md),
  [ADR operating policy](../adr/policy.md).
