# A4a: approved local Git acquisition and repository-scoped native requests

Status: opt-in implementation stacked directly on A3 PR #99, parent
`c82fe24454926e2213a476f7bdfd7650519b12b6`, tree
`0b64d6a8e9eb2d88795eff6c3ce78f25840fcdd1`. The owner requested continuation on
2026-10-18. Main-agent work started 02:08:20 JST. Read the [Access design](../architecture/access-store-design.md),
[A1 contract](access-a1-contract.md), [A2a workflow](access-a2a-workflow.md) and
[A3 boundary](access-a3-registration-boundary.md). This does not retire ADR 0003,
merge an ADR/PR, switch P8/default Schema 21, migrate user data or alter backups.

## 1. Scope and unmodified persistence

Connect an explicitly approved Linux local Access route to existing P5 native Git
acquisition, including P4 Notes. Both SHA-1 and SHA-256 are exercised with real local
Git repositories. There is no clone/fetch, SSH/HTTPS/container executor, credential
lookup, arbitrary helper command or ordinary file-body archival interface.

The ten-table Access DDL, Core/Context/Operational/Search DDL and fingerprints are
unchanged. Scope UUID identity, same-table registration history, max-original-time
candidate sets, ties, per-assignment consent, and transactional invalidation remain.
Domain Exchange stays v3. A4a never imports/activates Access from domain packages.

Repository UUID and catalog-seed UUID have different roles. A native request may
explicitly target a registered or newly admitted Repository UUID different from the
catalog seed. Core/Operational pairing is STILL checked against the actual seed and
catalog-instance pair. NotesProgress receives both the target repository and the
physical catalog seed; it checks the physical pair AND original target/source request
scope. A4a does not treat every Core repository as the seed or discard pairing checks.

This native/Notes correction also works in P5's prepared Core-first/Context-second
path. General `GitMetadataInput` admission and domain Exchange repository-selection
rules retain their existing constraints; this is not a claim of unrestricted
multi-repository behavior for every API. The Access driver itself performs local
Git/Core acquisition, not an Access-controlled Provider/Context intake.

## 2. Modules and flow

- `domain/native_acquisition.py`: complete bounded semantic native-request intent,
  including target UUID, original occurrence/time, OIDs, flags, all attributed claims,
  copy coordinates and complete Notes specifications. Validate nested identities and
  repository-owned claims before admission; no second occurrence identifier.
- `application/access_acquisition.py`: AccessGitAcquisition composes existing local
  review/activation, persistent Operational accounting, GitCore stop checks and P5.
- `adapters/git/access_native.py`: trusted Linux descriptor-bound Git source.
- `cli/access_acquisition.py`: separately invoked, interactive local acquisition CLI.
- Existing native/Notes subprocess adapters expose a trusted `_process_options`
  hook for fd inheritance; ordinary GitNativeSource supplies no extra parameters.
- Existing AccessWorkflow adds `dispatch_reviewed_once` so the operation receives
  the exact activated plan and a binding recheck, not a newly resolved default.

Acquisition order:

1. Validate target/selection, full typed request and finite limits. Require existing
   Core and Operational stores; never initialize a missing budget ledger here.
2. Check the existing domain stop and request cancellation before activation.
3. Select/verify stored consent, inspect the permitted local directories, display
   the actual request/catalog/object-format intent and require local confirmation.
   A mutable display copy cannot change the retained request.
4. Consume the one-use A2 activation. Capture its exact grant/plan. Recheck domain
   availability, actual executor binding and consent before source input.
5. Open Operational under the physical catalog identity, explicitly issue or resume
   the original finite request, and bind its complete Access plan and native intent.
6. Pin repository/Git storage directories, inspect bounded local configuration under
   the work budget, bind stable physical source coordinates, then run the first Git
   storage-format probe. Incorrect format or storage fails without fabricated input.
7. Stream selected native metadata/Notes through existing budgeted P4/P5 validation.
   Preserve nominal missing objects and allowed-body roles. Admit an original,
   self-contained actual-path repository claim under the genuine capture/provenance.
8. Check availability/consent/binding again before returning the report. A later
   failure preserves independently committed Core prefixes; it does not retroactively
   erase facts or report success after a detected stop.

No database write transaction spans Git input. Operational charges persist across
retry and input failure. Loss of the original ledger/witness refuses continuation,
not a zero-cost restart. A new request is an explicit operation.

## 3. Fixed source and retry identity

Every attempt needs fresh local activation, even when persisted consent is unchanged.
Operational stores a non-secret frozen review plan plus complete original native
request. It also records source path, expected object format, pinned directory
identities, local user/group/mount view and configuration-file change token.

File descriptor numbers and process IDs are NOT durable identity coordinates: a
retry in another process may use different descriptor numbers. The actual path in
original Core provenance is not `/proc/self/fd/N`. Directory/configuration stat
values are execution-consistency tokens, not invented observation timestamps.

Changed Access registration, profile, target repository, OIDs/claims/Notes intent or
physical source cannot silently reuse the old request. Configuration/source changes
fail before another Git command; already consumed inspection work is not refunded.
A new latest Scope Locator never retargets an in-flight request. After dispatch the
original explicitly selected grant is rechecked, not a replacement default.

The previous native replay intent omitted several request-defining fields. The
full semantic intent prevents explicit in-memory progress or shared captures being
replayed under another target/claim/specification. Old unreleased continuations with
another scope shape are not transparently reinterpreted; no compatibility promise.

## 4. Local Git adapter boundary

The approved directory descriptor is duplicated and `.git` (ordinary worktree) or
the repository itself (bare) is opened without following links. The top-level Git
storage, objects and refs directories are pinned. Before each command, verify their
identities, owner/permissions, original configured path, local environment and
configuration token. Linked worktree pointer files, commondir, external object
alternates, indirect include/includeIf configuration and worktree extensions are
outside this first adapter's support and fail explicitly.

The executable comes from the trusted system search path. Subprocess arguments and
environment are authored by the adapter, never caller-provided shell/config strings.
Git selection/config/trace/SSH environment variables are not inherited. Explicit
protocol deny, no-lazy-fetch, no-replacement, no optional locks and disabled hooks /
fsmonitor prevent unrequested transport/operation paths. Only the internal metadata,
refs and storage-format plumbing commands are available.

The storage-format bootstrap has bounded output and timeout, with source-byte/work
charges before reading. Metadata/Notes reuse existing streamed limits and role checks.
The adapter's config inspection is finite and does not retain config bytes or secrets.

This is NOT a sandbox against the filesystem owner, an adversarial Git binary or
privileged replacement during a syscall race. It does not recursively certify every
Git internal file or offer an atomic snapshot of mutable refs. Git-managed internal
storage and the local executor are trusted within the declared owned-local-filesystem
boundary. Supported input is not a promise that every Git repository layout works.

Checks occur before each newly launched Git command and on result completion. The
callback cancellation/consent checks do not claim instantaneous revocation of an
already-running command; P4's finite subprocess timeout remains. A detected P7 stop
always prevents further normal admission/output. Native bytes already accepted before
a later failure remain legitimate committed facts.

## 5. Opt-in local CLI

```sh
python -m repo_catalog.cli.access_acquisition \
  --access-db /path/to/access.sqlite3 --catalog /path/to/catalog \
  --repository REPOSITORY_UUID --scope SCOPE_UUID \
  --capture-origin ORIGINAL_ORIGIN_UUID --capture ORIGINAL_CAPTURE_UUID \
  --source-attribution actual-local-source --observed-at-us ORIGINAL_TIME_US \
  --object-format sha256 --oid FULL_COMMIT_OID --new-request
```

The UUID/time/path placeholders are operator inputs, not generated evidence. Both
standard input and diagnostic output must be interactive terminals. Confirm the
shown `acquire-local-git SCOPE_UUID REPOSITORY_UUID` phrase. No `--yes` or imported
approval flag. This checks terminal interaction, not proof of a living human.

`--notes` discovers/inventories observable Notes; `--note-target` selects explicit
note targets. `--metadata-only` suppresses raw representation retention, not native
metadata acquisition (it is NOT the separate GitMetadataInput API). Per-unit work
limits and maximum object bytes are explicit finite options. Repeat an original
request without `--new-request`; never generate replacement capture/time merely to
resume. Optional explicit request identity must supply its full original pair.

The summary distinguishes acquisition status/partial failure and returns identifiers,
not raw repository bodies. An intentionally missing ordinary blob is not corruption.

## 6. Verification record

Local development uses Python 3.13.5, Git 2.47.3 and actual SQLite 3.51.3 from the
SHA-256-verified A3 artifact, with the official SQLite source ID checked. The isolated
source-overlay virtualenv enables child-process imports; it is NOT an installed-wheel
test. Hosted direct-wheel/sdist-derived-wheel executions are reported separately.

The new suite includes real SHA-1/SHA-256 bare and ordinary worktree input, non-seed
metadata and Notes, paired native/Notes, no-Context Access acquisition, real PTY CLI
confirmation, exact replay/cumulative work, wrong physical pairing, lost Operational,
source replacement, changed intent, poisoned Git environment, alternates/config
rejection, revoked consent, P7 stop and post-commit completion checks. Pure request
validation separately covers invalid nested types and previously omitted fields.

Six deliberate mutations remove frozen-plan binding, physical-source binding, full
native intent, isolated Git environment, configuration recheck and per-command
consent checks. Every corrected experiment yields a test assertion failure, no
setup errors. These are targeted author-run counterexamples, not independent review
or an exhaustive security score. All mutated files are restored before final tests.

Retain failures: initial broad foreground runs hit tool execution limits; a completed
312-case run had four child-process import failures before source-overlay correction;
the corrected same cohort passed. New test expansion initially omitted five imports
(14 failures), and a paired assertion compared sqlite3.Row directly with a tuple
(two failures); both fixture mistakes were corrected without weakening product checks.
No independent subagent was launched. Final exact-HEAD counts, audits and hosted
results are recorded in the PR body and downloadable execution evidence.

Final local risk run (02:38:42–02:42:01 JST): **1,655 passed, zero failures/errors/
skips**. This includes 107 new cases (84 integration + 23 pure request validation),
the prior 1,149-case A3 risk cohort, and 399 additional existing P2/P4 cases. Four
existing Python-3.13 multiprocessing-fork warnings remain recorded. The same source
also passed all five baseline/routing audits, Ruff and whitespace checks. The source
smoke exercised the extended distribution script against the checkout; it does not
establish installed-package isolation. Actual wheel/sdist results remain a hosted
verification step and must be bound to its final effective tree.

## 7. Remaining scope

A5 still owns Access backup/restore/fork and restoring without executable consent.
A6 owns independent integrated review and coherent ADR 0003 replacement closure.
Remote/container transports, unrestricted multi-repository metadata-only/Exchange
selection, real-data extraction and default runtime activation are not implemented
or authorized by this work. No repeated questions reopen the accepted Scope design.

## References

- [Git environment/configuration and security](https://git-scm.com/docs/git).
- [Python subprocess cwd/pass_fds contract](https://docs.python.org/3.12/library/subprocess.html).
- [Verified review procedure](../../.agents/skills/three-store-invariants/references/access-native-acquisition.md).
