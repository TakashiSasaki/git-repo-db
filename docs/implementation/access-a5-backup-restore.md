# A5a independent Access backup, inactive restore and Scope fork

Status: opt-in implementation, owner-requested continuation on 2026-10-18.
Exact parent: PR #100, `2ab6a59dd91c46ebbc9a9d14a0078f2b16235b4f`, tree
`6ea8778ff721c64a86a6cb86f085e1ad8c94da81`. Read the
[A1 contract](access-a1-contract.md), [ADR 0029](../adr/0029-independent-access-store.md)
and [A4 implementation](access-a4-local-acquisition.md). This stage changes no
accepted identity, time, approval or retention decision and does not retire ADR
0003, merge branches, activate P8 or operate on a real user catalog.

## 1. Scope and responsibilities

An explicit single Access store is independent of Core/Context pairing. Add
`AccessMaintenance`, its maintenance port, and a Linux local-filesystem SQLite
adapter. The existing ten Access tables and all five store DDL fingerprints are
unchanged. No new backup UUID, history table, source-event surrogate, latest-row
pointer or Core foreign key is needed. The normal CLI remains untouched.

Four opt-in commands are provided by `python -m repo_catalog.cli.access_maintenance`:

```sh
python -m repo_catalog.cli.access_maintenance backup --access-db /private/access.sqlite3 --destination /private/access-backup
python -m repo_catalog.cli.access_maintenance inspect --bundle /private/access-backup
python -m repo_catalog.cli.access_maintenance restore --bundle /private/access-backup --destination /private/restored-access
python -m repo_catalog.cli.access_maintenance fork --access-db /private/restored-access/access.sqlite3 --source-scope SOURCE_UUID --scope-uri file:///new-environment --display-name fork
```

Backup/restore require a nonexistent destination directory and an existing owned
private-write parent. Explicit maintenance may be noninteractive: it never probes
credentials, contacts a host, runs Git or grants execution authority. Existing A2
operator approval and independently checked executor activation remain required.
Limits are positive finite `--max-bytes`, `--max-rows`, `--timeout-seconds` options
before the command; defaults are 256 MiB, 100,000 rows and 60 seconds. These are
engineering bounds, not owner-selected performance requirements.

## 2. Coherent backup and exact artifact

The source is opened read-only, checked for stop/path/format/domain corruption,
and pinned by an explicit read transaction. SQLite Backup API copies this same
snapshot, including its committed WAL state. Concurrent later registrations are
not mixed into the protected snapshot. A normal backup is refused for stopped or
known corrupt Access, without writing the damaged DB; only a separate Access stop
may be recorded. Core/Context stop files and domain data are never touched.

A private, unexposed copy is validated before removing local_access_grants. The
copy is VACUUMed, validated again, and converted into a standalone DELETE-journal
SQLite file. Only the private copy is changed; Scope registrations and source
settings/grants remain intact. Removing consent at backup time also avoids treating
a transported raw approval row as valid. Enablement intent in other settings is
preserved in this artifact, but it is not executable live-format Access.

The artifact contains exactly three private regular files:

```text
access-backup/
    access.sqlite3
    manifest.json
    manifest.sha256
```

The canonical, bounded `git-repo-db/access-backup-v1` manifest records actual snapshot
bytes/SHA-256, compiled Access format/version/DDL hash, all table counts, actual
creation time and source grant omission count. It explicitly declares no grants,
required local reapproval and exclusion of domain catalogs. SHA-256 detects changed
bytes; a party replacing data and hashes is not authenticated. Exact member/key
allowlists, stored-domain/schema/FK verification and zero-grant requirements still
apply after a digest matches. This is not general secret/prose DLP.

## 3. Restore means continuation, not imported consent

Before any input SQLite is opened, fixed manifest/digest names and the single fixed
`access.sqlite3` member are opened without following symlinks, checked for regular
single-link private files, and bounded. The store is streamed into a new private
stage while verifying its hash/length; only that sidecar-free copy reaches SQLite.
Unknown fields, paths, extra files/WAL/SHM, unsupported formats, invalid UTF-8,
corrupt stored values and grants supplied with recomputed hashes are rejected.
The backup input and pre-existing destination are never repaired or rewritten.

Preserve every Scope UUID, original registration triple, same-time candidate and
Repository UUID. No restored timestamp is replaced by receipt time. Current
configuration and preferences survive, but all route controls are disabled and
local grants are absent before exposure. Other enablement intent is preserved;
reenabling a route alone cannot restore consent. Missing control rows stay missing,
not reconstructed by replay. The output is a freshly validated WAL Access database
plus a non-authoritative `restore.json` receipt, not a new backup format or an
activation token. Rebackup through the explicit backup API.

A restored copy with the original Scope UUID is a requested logical continuation.
Moving a Scope does not automatically prove that its new environment interprets
locators identically. The operator must ensure the old and new environments do not
become independent active copies with one identity. This is not distributed fencing.

## 4. Independent fork is a new operation

`fork` operates transactionally within one selected sound writable Access DB. It
allocates (or explicitly receives) a new Scope UUID and requires an explicit new
Scope Locator. Its registration time is measured by the local application as a NEW
operation. The adapter receives the typed original operation triple for testing/
explicit administration, not an imported old timestamp. A target UUID already in
that database is a conflict, not an upsert or automatic merge.

Copy only current execution context, repository bindings, named profiles,
assignments and preferences from the source Scope. All copied executable settings
are disabled; no grant is copied. Retain Repository UUIDs. Exactly one explicitly
requested new Scope registration is inserted. S1/T1 history is neither rewritten
nor copied as S2/T1, and all original S1 history/settings/grants stay unchanged.
The receipt reports source/target UUIDs and per-table additions; no ancestry table
or independently generated historical event ID is introduced.

For a separate installation, restore a full inactive backup, then fork the selected
Scope there. Original S1 history remains attributable to S1 in that restored DB;
S2 has its own new registration. Scope retirement/deletion, selective extraction,
a settings merge into existing destinations and multiwriter synchronization are
not implemented. Fork failures before commit roll back all new rows; an uncertain
client retry with an explicit target observes the existing target rather than
silently issuing another identity. Separate new fork requests may issue new UUIDs.

## 5. Filesystem, resource and failure boundaries

Linux local filesystems must support atomic `renameat2(RENAME_NOREPLACE)`. The stage
is a private sibling directory; every output file and the stage are fsynced before
publication relative to a pinned parent. An existing target, including an empty
directory raced into place, is not overwritten. Parent directory fsync follows
rename. If it fails, report PUBLICATION_UNCERTAIN and preserve the complete target;
do not delete it or report success. No replacing-rename fallback is provided.

Timeout/cancellation is checked in SQLite progress/backup callbacks, streaming
loops and before commits/publication. No claim of instantaneous cancellation or
hard real-time termination of a filesystem syscall. File/row/time limits fail
without falsely labeling a sound source corrupt. Scope fork validates read-only
before a writable open, then revalidates under BEGIN IMMEDIATE with synchronous
EXTRA. Snapshot reads plus expected source identity/stop checks prevent accidental
alias replacement during the supported operation.

A process exit before rename leaves an unpromoted private stage and no completed
named destination. Normal exceptions remove only the owned unchanged stage. An
abandoned stage is never automatically adopted as a completed backup/restore. No
automatic cleanup of unknown stages or source evidence is provided. User-owned
malicious concurrent filesystem/DDL changes, recursive sandboxing, NFS semantics,
hardware power-loss qualification and global cross-process completion fencing are
outside this adapter. Tests do not promote these limits into proven guarantees.

## 6. Existing architecture preserved

P7 `git_only` and `paired` domain backups remain unchanged and valid without Access.
An Access backup includes all location history but no Core/Context bodies; do not
call it a full domain backup. Optional aggregate environment-bundle packaging and
cross-component atomicity are not implied or implemented. Operational/Search remain
reconstructible. No domain Exchange import opens Access or creates local consent.

The five new Python modules are individually listed in the isolated callsite audit:
`domain/access_backup.py`, `domain/ports/access_backup.py`,
`adapters/sqlite/access_backup.py`, `application/access_maintenance.py`, and
`cli/access_maintenance.py`. No prefix-wide exclusion or baseline inventory rewrite.

## 7. Verification status

Results are separately tied to exact source/PR trees. New tests cover all-history
round trips, ties, committed WAL and concurrent writers, source preservation,
rechecksummed invalid payloads, no-overwrite races, process exits, post-rename fsync
failure, fork rollback/content preservation and reapproval through the A2 workflow.
The focused hosted workflow includes these tests and installed-wheel/sdist-derived
wheel backup/restore/fork smoke checks outside the checkout. No independent reviewer
or subagent execution is claimed. See the PR's exact run IDs, JUnit, source hashes,
failures and unexecuted scope rather than interpreting this document as a PASS.

References: [SQLite backup API](https://www.sqlite.org/backup.html),
[SQLite snapshot isolation](https://www.sqlite.org/isolation.html),
[Linux renameat2 semantics](https://man7.org/linux/man-pages/man2/rename.2.html),
[backup/fork review lessons](../../.agents/skills/three-store-invariants/references/access-backup-continuity.md).
