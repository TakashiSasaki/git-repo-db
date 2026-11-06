---
status: accepted
date: 2026-11-06
replaces: []
refines:
  - 0014-history-and-notes-catalog-without-file-archive.md
  - 0017-domain-keys-without-storage-surrogates.md
  - 0028-classified-times-and-sha256-exchange.md
  - 0029-independent-access-store.md
  - 0037-operation-scoped-module-independence.md
---

# ADR 0039: Independent filesystem and worktree catalogs

## Decision

The owner selected two independent databases, ordinary directory support, historical
scans, fresh SHA-256 calculation for every regular file, native Windows and POSIX
operation, and automatic scanning of registered sibling worktrees. The owner then
accepted the complete proposed implementation plan with **“Implement the proposed
plan.”** on 2026-11-06. That instruction authorizes this implementation; it does not
authorize merging, publishing, changing existing user catalogs, or release work.

The filesystem authority owns directory locations, scan occurrences, entries,
native attributes and digest observations in `filesystem.sqlite3`. The worktree
authority owns observed Git topology and explicitly attributed external Repository
references in `worktrees.sqlite3`. A separate optional composition package discovers
worktrees, requests filesystem scans and enriches exports; it owns no database.

Each authority can initialize, read, verify, back up and restore independently.
Filesystem operation needs neither Git nor any existing catalog implementation.
Worktree topology does not require the filesystem package. Package installation
creates no databases. Cross-store references are qualified domain references, not
SQLite foreign keys, validity prerequisites or paired backup requirements.

Root identity includes a source namespace, path dialect and lossless native path.
An actual scan/topology observation has an occurrence identity; file rows use the
scan and relative path. Paths, identical hashes, matching HEADs or remote URLs do
not establish a permanent Core Repository UUID. Explicit associations can remain
unresolved when their external catalog is unavailable. No storage-only file UUID
is introduced merely to shorten references.

Scans preserve history and errors, including interrupted work. Directory enumeration
and hashing have separate completeness. They observe an interval, not an atomic
filesystem snapshot. A newer partial scan never silently borrows older entries or
hashes. Ordinary file bytes are read for SHA-256 and immediately discarded.

EFU-compatible UTF-8 CSV export consumes retained observations only. Standard
Everything columns retain their documented meanings; SHA256 and optional qualified
metadata columns extend them. Lossy filename replacement and silently colliding
mapped filenames are prohibited because they change identity.

## Constraints / Do NOT

- Do not add these stores to the P1 factory or Core–Context pair. Existing pair,
  stop, typed admission and recovery guarantees remain in their existing scope.
- Do not retain ordinary file bodies in either new DB, hidden CAS, staging area or
  Search. This additively permits filesystem metadata/digest cataloging under ADR
  0014; it does not relax the ordinary file archival exclusion.
- Do not infer hashes from Git OIDs, the index, filenames or stat equality. Hash
  actual regular-file bytes on each scan. Unreadable or unstable input has no
  successful digest. Symlink/junction targets and special devices are not read.
- Do not modify the inspected Git repository, acquire objects, initialize
  submodules, hydrate missing data or execute configured filters/hooks.
- Do not extend sibling discovery recursively through newly encountered unrelated
  repositories. Explicitly selected repositories expand their registered sibling
  worktrees; nested repositories have separate topology and present file contents.
- Do not use the existing POSIX-only runtime as a transitive dependency of the new
  packages. SQLite transactions own each new DB's locking. Catalog DB storage is
  local; filesystem input may include Windows UNC paths.
- Do not claim Windows execution from mocked path tests. Native focused Windows
  validation is distinct from Linux evidence and from release qualification.

## Context & Reason

This is a Level 3 decision: it introduces authoritative data boundaries and public
package/operation contracts. At investigation base `c0fadd6e`, existing independent
Core/Context/Access distributions already implement part of ADR 0037. Remaining
coupling is primarily Python ownership and composition, not cross-file SQLite
`ATTACH` joins. The P1 factory's required Repository/catalog pair is unsuitable
for generic filesystem roots. Existing approved local Git acquisition intentionally
rejects linked worktrees and therefore is not reused as a topology detector.

One new DB would separate the feature from Core but still couple filesystem
history to Git topology migrations, failures and retention. Two stores retain
independent utility; typed optional associations supply the desired relationship.
The accepted cost is separately reportable partial outcomes without distributed
transactions. The operation contract records the behavior in detail.

Native filesystem times retain their signed native precision, separately from
positive microsecond observation times under ADR 0028. FILETIME conversion is an
export representation; POSIX change time is never relabeled creation time.

## Consequences

The new feature does not switch normal Schema 21, migrate old data, complete every
ADR 0037 installation combination, or add file-body search. Existing Git acquisition
and Search storage dependencies are separated within their current composition,
preserving accounting, authority validation and fallback behavior. Pending remote
PRs #248–250 cover wider distribution work; integration with those branches must
reconcile the overlapping ownership rather than install duplicate definitions.

Acceptance, implementation and executed verification remain distinct. The source
and tests implement the contract; execution evidence belongs to this task's actual
validation results. No release or hosted Windows success follows from this ADR.

## References

- [Local catalog operation contract](../architecture/local-catalog-contract.md)
- [Module independence](0037-operation-scoped-module-independence.md)
- [File archival boundary](0014-history-and-notes-catalog-without-file-archive.md)
- [ADR policy](policy.md)
- [Everything EFU specification](https://www.voidtools.com/support/everything/file_lists/#format)
- Owner selections and implementation instruction in the 2026-11-06 task conversation.
