# A2a: local review, executor activation and one-shot pre-dispatch checks

Status: opt-in implementation, exact parent PR #97 at
`8852f4c4db3c5466654be38b16f1ef18eada4a1c`, tree
`63138d2ca173171692df3745d37ae678138eb24d`. The owner requested continuation;
this implements the confirmed A2 boundary from the [A1 contract](access-a1-contract.md),
not a new Scope identity or merge permission. A2a supplies actual local-terminal
review and a finite Linux local-directory adapter. Full remote/Git acquisition and
P7 integration remain separate. Existing ADRs, default CLI and all DDL are unchanged.

## 1. Architecture and engineering contract

- `domain/access_workflow.py` owns typed original request selection and exact review
  display. Explicit choices are retained, rather than silently changing defaults.
- `domain/ports/access_workflow.py` owns the trusted executor integration protocol.
- `application/access_workflow.py` owns local review, grant revalidation, runtime
  activation, session limits and final dispatch checks. It imports no adapters.
- `adapters/filesystem/access_executor.py` implements one bounded Linux filesystem
  context. `cli/access_workflow.py` chooses it explicitly, not from imported JSON.

Scope UUIDv4 and Repository UUIDv4 remain the only relevant entity identities.
Locator history remains the original single table and full registration triple.
No history table, scope revision, grant UUID, activation flag or new stored column
is introduced. A1b Access format 2 and its ten tables are byte-identical.

Session tokens are in-memory object capabilities, not UUIDs or portable identifiers.
They are purpose-bound, single-use, limited to their creating process/thread/session,
and expire using a monotonic clock (default 300 seconds, configurable 1..3600).
There are at most 64 pending handles by default (configurable 1..1024). Expired,
closed and consumed activations close their descriptors. This is not a persistent
retry budget or a replacement for original acquisition/Capture identity.

## 2. Review and approval

`inspect` reads settings only. `begin_review` captures a coherent A1b review plan.
`approve` shows exact non-secret references/options to a TRUSTED local reviewer,
requires an actual True return, and re-resolves the original selection afterward.
The underlying A1b operation rechecks the full shown plan and records consent
transactionally. The token is consumed on decline/failure too. Callbacks and private
Python state are trusted application code, not hostile input or a security sandbox.

A concurrent default change after the application's last read can at most leave
consent for the exact old plan the operator saw: the A1b transaction cannot approve
unseen changed settings. It does not authorize the unseen default. Activation and
dispatch re-resolve the original default selection; explicit old-route requests
remain deliberately explicit. No grant/enablement filter changes MAX-time ranking.

## 3. Independent runtime activation

A stored grant is required BEFORE asking an executor to inspect even the local
filesystem. Binding then measures actual local context, displays those measurements
alongside the plan, and requires a second explicit activation confirmation. Session
activation is never loaded from the database, backup, JSON or a persistent flag.
Same UUID/URI/reference names do not attest a host or authenticate repository identity.

The initial adapter supports ONLY `executor_kind=local`, POSIX file profiles, a
local `file:` Scope Locator naming an allowed directory root, and an absolute
Repository Locator beneath that root in the SAME filesystem namespace. It does not
reinterpret `/repos/x` as `root/repos/x`, chroot, contact a runner API, use SSH, resolve
credentials or execute Git. This is one finite adapter's addressing contract, not
a redefinition of all Scope Locators. Other valid stored routes remain unsupported
for execution and fail explicitly without fallback.

It opens every component with O_DIRECTORY/O_NOFOLLOW, pins the root/repository
file descriptors, requires owned non-group/world-writable final directories, and
records device/inode/permission coordinates plus PID/effective IDs and Linux mount
namespace identity. Before work it reopens the named paths without following
symlinks and compares both names and held descriptors with the reviewed values.
No CWD-dependent relative path, dot traversal, lossy decoding, symlink route,
Windows/UNC, nonlocal file authority, arbitrary mount or container executor is
claimed. Underlying network filesystems and hostile privileged writers are outside
support. This does not prove Git repository identity or inspect Git bodies.

## 4. Final check, revocation and cancellation boundary

`dispatch_once` requires the embedding application's stop/cancellation guard. It
then checks actual bound executor context, the current grant and original selection,
and the token's lifetime. Expiry is checked AFTER potentially slow validation as
well as before it. All SQLite reads have committed before the trusted callback.
The local adapter passes a BORROWED pinned directory FD for the callback duration;
callbacks must not close/retain it or use path-based reopening as a substitute.

The final successful pre-dispatch check admits ONE in-flight operation. A revocation
before the check refuses work; a concurrent change after it is not promised to cancel
already admitted work instantaneously. The callback may continue, and later operations
need a fresh check/activation. Failed callbacks do not automatically retry. Existing
acquisition retries cannot retarget to a new latest locator under the same identity.
A4 must provide the real P7 stop fence, finite work accounting, and a domain-safe
metadata/notes callback; the required guard cannot be inferred from Access settings.

## 5. Explicit opt-in CLI

The normal `repo-catalog` entry point is unchanged. Use this module deliberately:

```sh
python -m repo_catalog.cli.access_workflow review --access-db ACCESS --scope SCOPE_UUID --repository REPO_UUID
python -m repo_catalog.cli.access_workflow approve --access-db ACCESS --scope SCOPE_UUID --repository REPO_UUID
python -m repo_catalog.cli.access_workflow preflight --access-db ACCESS --scope SCOPE_UUID --repository REPO_UUID
```

`--locator` and `--profile` select an explicit repository assignment together.
`--scope-uri` and `--registered-at-us` select an exact Scope registration together.
`review` is read-only and may emit JSON to a pipe. `approve` and `preflight` require
local TTY stdin/stderr and an exact typed confirmation containing BOTH UUIDs; no
`--yes`, piped import or approve flag is accepted. JSON output escapes terminal
controls/Unicode. A PTY can be automated by the local account: this is a deliberate
local-administration boundary, not proof that a biological human typed the response.

`preflight` requires an already stored grant plus runtime confirmation and only
fstats the pinned directory. It explicitly reports `git_acquired=false`; it is NOT
an acquisition endpoint. Its no-catalog guard is limited to that directory check.
Settings may be managed through the A1b typed APIs; this stage adds no implicit
initialization, data migration, backup restore, generic command or credential probe.

## 6. Verification and limitations

Local Python 3.13.5 uses ACTUAL SQLite 3.51.3 from SHA-256-verified A1b CI artifact
12102434632. No version override or lower product minimum was used. The parent tree
was reconstructed from all 2,590 archived source files and matched Git exactly.
The unchanged 219 Access tests passed before work. The new cohort currently adds
63 cases: **282 total passed**, zero failures/errors/skips; 15 existing P1 schema
cases and four baseline audits also passed. The dedicated workflow includes all
new cases, and both installed wheel variants are extended with the workflow and
read-only CLI. Hosted execution must be checked for the actual new PR HEAD.

The initial new cohort passed 53 tests, then 61. Two additional slow-validation
counterexamples FAILED because review/dispatch could exceed the TTL while checking
the database. Lifetime rechecks were added after validation; all 63 now pass.
Retain the two original failures as regression evidence, not passing results.
Eight deliberate defense removals all produced assertion/test failures, zero setup
errors: exact confirmation, single use, post-review selection, final grant read,
directory identity, post-validation expiry, process ownership and domain-stop guard.
These are author-run mutation checks, not an exhaustive score or independent review.

Actual PTY tests exercise approval, decline and local preflight in separate Python
processes against disposable directories. No network, credentials, user repository,
Git contents or real catalog were accessed. Revocation during a trusted callback
confirms no DB transaction spans work and intentionally does not claim instantaneous
cancellation. DDL fingerprints and original Core/Context/Operational/Search checks
are unchanged. No independent subagent was available/launched; main-agent review and
automated CI remain distinct. Local hatchling is unavailable, so installed artifact
claims must come from real hosted verification, not from local import-only smoke.

A3 Context/Exchange separation, A4 Git acquisition/seed reconciliation, A5 restoration
with cleared grants, A6 independent integration and ADR 0003 retirement remain open.
The [expiry review note](../../.agents/skills/three-store-invariants/references/access-review-expiry.md)
records the new executed lesson. No accepted ADR is deleted or reinterpreted here.

## Technical basis

- [Python descriptor-relative OS operations](https://docs.python.org/3/library/os.html).
- [SQLite transaction boundaries](https://www.sqlite.org/lang_transaction.html).
- [A1b storage boundary](access-a1b-connections.md) and [ADR 0029](../adr/0029-independent-access-store.md).
