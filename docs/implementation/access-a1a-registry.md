# A1a: opt-in Access Scope registry foundation

Status: implementation review, not complete Access or runtime activation.
Design dependency: PR #95, `3cde893f7a16fd7d04021e3be3cbc0d22c765c38`.
The owner requested continued implementation on 2026-10-17 after accepting Scope
UUIDv4 identity, logical continuity/fork semantics, same-table locator history,
original registration-time first-choice sets, and separate local authorization.

This narrowly implements those accepted registry decisions. It does not accept
all proposed ADR 0029 details, retire ADR 0003, authorize merge, or switch P8.
Existing Core/Context/Operational/Search DDL, normal CLI and real catalogs remain
unchanged. The incomplete broader design lifecycle is still a merge dependency.

## Implemented modules and ownership

| Path below `src/repo_catalog/` | Responsibility |
| --- | --- |
| `domain/access_registry.py` | Validated Scope identity/label, registration triple, bounded result values |
| `domain/ports/access_registry.py` | Typed read/write registry contracts; no generic SQL or execution port |
| `adapters/sqlite/access_schema.py` | Independent packaged format, UDFs, read-only preflight, exclusive creation, Access-only diagnostic stop |
| `adapters/sqlite/access_registry.py` | Short transactions, exact replay, controls, first-choice sets and keyset history pages |
| `adapters/sqlite/access_ddl/registry.sql` | Four concrete registry tables, immutable fact guards and derived first-choice view |

The four tables are `access_identity`, `access_scopes`, `scope_locators` and
`scope_locator_controls`. This is a **registry subset**, not the final Access
schema count or an implementation of repository bindings/profiles/grants.
No history table, event UUID, extra row ID or mutable current-locator pointer is
introduced. Controls reference the complete registration triple. Disabled/missing
controls are not a grant; enabling a route cannot initiate any external action.

The exact four new Python paths enter the existing explicit isolated-module list
in `scripts/audit_callsite_dependencies.py`. No prefix exclusion or historic
inventory regeneration is introduced. Tests check both accidental imports from
the normal runtime and domain-to-adapter dependency direction.

## Registration and first-choice semantics

`ScopeLocatorRegistration(scope_uuidv4, registered_at_us, scope_locator_uri)` is
one immutable registration fact. The complete triple is the direct PK/FK. An exact
replay is a duplicate; it never updates time, changes enabled state or recreates a
missing control row. A genuine re-registration uses its actual new time, allowing
A->B->A without overwriting the original A. Independent identical-triple operation
multiplicity is outside this model; no audit event identity is fabricated.

Registration times are genuine positive int64 Unix epoch microseconds. Python
rejects bool/float/string inputs. SQLite STRICT/CHECK validates stored types, not
the original caller's Python type. Earlier-time insertion is retained and returns
`precedes_latest` with the previous maximum; this diagnoses order without claiming
to distinguish clock regression from genuinely older supplied data. No artificial
clock tick or receiver receipt date manufactures freshness.

`first_choices` computes MAX over **all** registrations, before route control or
future approval checks. It returns the complete maximum-time tie set, or a bounded
`CANDIDATE_LIMIT` error rather than truncating to an arbitrary winner. URI ordering
is display stability only. Empty registered Scope yields an empty tuple; an unknown
Scope is `NOT_FOUND`. Future A2 must report ambiguity/approval and must not silently
fall back to a lower timestamp.

History uses descending original time and exact ascending URI keyset pagination.
The cursor is a full existing registration of the same Scope, not an opaque row
ID. Each call is coherent; multiple paginated calls do **not** claim a single
pinned multi-call snapshot if concurrent older registrations are inserted.

## Finite storage grammar, not an execution claim

A1a accepts ASCII absolute `https://`, `ssh://` and local `file://` Scope locator
URIs, retaining validated text exactly. Percent escapes may represent non-ASCII
path bytes. Queries/fragments (including empty delimiters), passwords, HTTPS
userinfo, malformed escapes, controls, literal backslashes, ambiguous authorities,
helpers and relative inputs are rejected. SSH explicit usernames are allowed;
file authority must be empty or localhost. URI strings are at most 8192 bytes,
labels 1024 UTF-8 bytes, result page/tie bounds 1..1000. UUID's `urn:uuid:` spelling
is not an environment location. These are initial adapter-supported storage
limits, not a prohibition on future separately reviewed locator grammars.

Parsing does not resolve DNS, read SSH/key files, fetch URI documents, execute Git,
or authorize a container/remote environment. Repository scp/path grammars are a
different future type. A URI-shaped string is not proof of reachability or Scope
identity. Credentials concealed in an ordinary path cannot be inferred by a
syntax validator; do not call this a universal secret detector. Public exception
messages are generic and suppress lower-level causes containing stored/input text.

## Supported persistence and failure boundary

The actual Python SQLite binding must be >=3.51.3 with mutexes. There is **no
production override**. This reference adapter supports cooperating POSIX processes
on local filesystems, with owned mode-0600 unaliased regular database files and an
owned parent directory not writable by other users. Symlinked parents, database
symlinks/hardlinks, and pre-existing initialization sidecars are refused. No claim
is made for hostile same-owner processes, arbitrary DDL/Python mutation, network
filesystems, Windows, distributed ownership fencing or remote execution.

Initialization is explicit and exclusive. It never implicitly creates Core/Context,
invents a repository seed, migrates, overwrites a target or silently recreates an
incomplete file. Open validates the exact packaged schema, identity, domain values
and FKs in a read-only snapshot before a writable reopen; inode and stop checks
surround it. Foreign keys and recursive triggers remain enabled. Prepared-statement
caching is disabled. Generic SQL on the private connection is denied outside typed
capabilities; factory functions/private Python fields remain trusted infrastructure.

Typed writes own one BEGIN IMMEDIATE transaction and roll back on body/COMMIT
failure. An injected controls-insert failure leaves no half-registered locator.
Readonly operations pin one transaction and eagerly materialize their bounded
results. No transaction spans network or caller callbacks. No shared Core writer
gate or mutable Core revision is introduced.

Detected Access data corruption publishes `<access-file>.access-stop.json` outside
the suspect database and blocks subsequent registry operations. Invalid stored
UTF-8 is recognized even when CPython reports OperationalError without
SQLITE_CORRUPT. An existing Access marker blocks new and open handles; no clearing
or in-place recovery method is exposed. Wrong-format files are rejected without
modification or being mislabeled as a diagnosed damaged Access catalog. A2/A5 must
supply complete dispatch/recovery fencing; this is **not** P7's crash-safe
completion fence or a power-loss-tested activation engine. A concurrent in-flight
SQLite operation is not claimed to be instantaneously revoked by an external
marker. Core/Context corruption and their P7 stop are never bypassed; A1a performs
no Core operations at all.

## Verification and observed limits

New suites: `tests/unit/test_access_registry_values.py` and
`tests/integration/access/`. The focused workflow `access-registry.yml` builds
SQLite 3.51.3 from the official amalgamation, verifies the published SHA3-256 of
`sqlite3.c`, checks actual `sqlite_source_id()`, and runs without a runtime bypass.
It also builds/installs a wheel and an sdist-derived wheel in separate temporary
environments, outside checkout and without HTTP dependencies, via
`scripts/verify_access_distribution.py`. Existing baseline audits run separately.
A green historical docs job is not evidence that these tests ran.

Local environment: Python 3.13.5, SQLite 3.46.1; checkout/network bootstrap was
unavailable. On that environment, 78 pure/ownership/runtime-rejection tests passed
(the ownership scan had only the local patch, not a full checkout). A separate
**uncommitted test-only harness** bypassed the runtime gate for 36 additional
semantic/file tests, which passed. Those 36 are non-qualifying development probes,
not supported-runtime acceptance. The real minimum-runtime rejection test runs
without that override. Hosted results are bound to the eventual exact PR commit
and must be reported separately; none are claimed here before execution.

Self-review found invalid stored UTF-8 initially did not persist Access-stop;
read-only open and already-open read regressions now cover the correction. A
privileged corruption fixture initially hit the still-active FK instead of
creating damage; the fixture now explicitly disables that FK for the synthetic
attack. All production guards remain enabled. A transient URI exception-handler
edit was caught by rerun and fixed before publication. No independent subagent
review has been executed. The requested three review tracks remain in the parent
`access-adr-replacement-review.md`.

## Next dependency and non-goals

A1b must add repository binding, named connection configurations, whole-setting
approval references and ABA-safe invalidation from `access-a1-contract.md`.
A2 owns real resolution/approval/dispatch; A3 owns Context JSON/Exchange separation;
A4 owns acquisition integration and the seed-versus-registry restriction; A5 owns
Access backup/fork/restore and reapproval. A1a's SQLite backup test exercises copying
history only, not an Access backup API. A6 still requires independent exact-tree
review and integrated packaging. Do not treat this subset as complete A1/A2,
retirement of ADR 0003, acceptance of all ADR 0029, or a default-runtime switch.
