# Independent local catalog operation contract

This contract implements [ADR 0039](../adr/0039-independent-filesystem-and-worktree-catalogs.md).
It describes independently usable authorities, not new mandatory P1 stores.

## Ownership and operation scope

| Operation | Required implementation/data | Absent implementations permitted |
| --- | --- | --- |
| Filesystem init/scan/query/EFU/verify/backup/restore | Filesystem package and selected DB; live root only for scan | Git, worktrees, Core, Context, Access, Operational, Search |
| Git topology discovery/query/association/verify/backup/restore | Worktree package and selected DB; Git executable/source only for discovery | Filesystem and all existing catalog implementations |
| Related-worktree file scan | Optional local composition, worktree and filesystem packages/explicit DBs | All existing catalog implementations |
| Enriched EFU | Local composition and selected retained filesystem/topology observations | Live filesystem, Git, Core and other existing catalogs |

Initialization is explicit. Read-only opens do not create, migrate or repair DBs.
Each store owns schema validation and a verified standalone backup/restore to a
fresh destination. Neither restores or certifies the other. Failed cross-module
work leaves independent valid observations available, with unresolved links
reported. No cross-DB transaction, foreign key, `ATTACH`, paired migration, shared
catalog identity requirement or third progress authority is introduced.

## Observation and filesystem semantics

- Namespace plus exact native location identifies the source root. Preserve native
  path bytes/spelling and dialect; do not universally case-fold, normalize Unicode
  or use resolved symlink targets as path identity. Windows drive-relative forms
  are rejected; ordinary relative paths resolve against the invocation directory.
- A scan is a real occurrence. Its start, bounded batches of entries/errors and
  terminal status remain historical. Interruptions do not imply completion; the
  next scan is a new occurrence, not a relabeling of prior evidence.
- Enumeration and hashing completeness are independent. Default query/export
  selects one scan per root; a newer incomplete/partial attempt is visible and
  requires explicit partial export. No union of old/new rows or deletion claim
  follows from an incomplete enumeration.
- Hash every regular file's exact bytes with bounded memory. Compare opened handle
  identity/attributes and path identity around the read. Detectable changes or
  read failures leave a reason and no successful SHA256. This is race detection,
  not an atomic snapshot or a guarantee against adversarial undetectable changes.
- Record empty directories, links and special entries. Do not follow symlinks,
  junctions or reparse targets; never open FIFO/socket/device entries for hashing.
  Hard links keep distinct path observations. No ordinary file body is retained.
- Generic filesystem scans have no Git dependency. Worktree composition injects
  actual Git administration exclusions. Include ignored/untracked/hidden files;
  permit explicit administration inclusion. Exclude the active catalog DBs and
  their journals/temp artifacts and preserve exclusion scope in the scan.
- Keep native file times, birth time when available and change time distinct.
  Missing information stays missing; observation timestamps use Unix microseconds.

## Git topology and sibling scanning

Use read-only plumbing (`rev-parse`, `worktree list --porcelain -z`) with controlled
environment, bounded output/time and no network/object acquisition. Retain root,
per-worktree git-dir, common-dir, object format, HEAD/branch, bare/locked/prunable
status and errors. The common directory may be a distant bare repository. A `.git`
pointer, separate git-dir, detached/unborn HEAD or present submodule is supported.

Each explicitly selected repository expands all its registered non-bare siblings.
Scan each observed physical root once per request while preserving topology path
aliases. Missing/prunable/inaccessible roots produce separate outcomes; locked roots
can be read. Bare input discovers siblings but is not an empty worktree. Ordinary
directories scan normally. Nested repositories/submodules retain distinct topology;
they do not automatically initiate further sibling expansion. No checkout, prune,
repair, fetch or submodule initialization occurs.

After a filesystem scan, composition may append its qualified scan reference to
the topology store. A crash before attaching it does not invalidate the filesystem
scan. Explicit Repository UUID associations are claims about external identity,
not evidence that Core is installed or has verified the current files.

## EFU contract

Export is a streaming read of retained facts; it does not rehash files or invoke
Git. Emit UTF-8 CSV with CRLF, standard quoting, and the five standard columns
`Filename,Size,Date Modified,Date Created,Attributes`, followed by `SHA256` and
selected metadata. Empty/unknown values are blank. Directory and Windows attributes
follow EFU meanings; POSIX mode is a separate optional field. Dates use integer
FILETIME, with only its 100 ns export precision; preserve finer source precision
in the catalog. Never substitute POSIX ctime for creation time.

Additional metadata can include entry/hash status, scan, observation time, original
path, link target, root and Git/Repository associations. Extra columns do not change
the baseline contract; arbitrary properties are not promised searchable in every
Everything version. Explicit root mapping can change output paths, but collisions
are rejected. Non-UTF-8 names are refused by default; explicit skipping reports
omissions. Never use replacement characters to alter identity silently. Write the
output atomically so a failed export does not leave a plausible complete EFU.

## Validation scope

Use synthetic file/Git fixtures and real SQLite with the environment's verified
Python. Exercise linked/distant-bare/separate-git-dir cases, missing siblings,
unborn/detached heads, untracked/ignored files, history interruption, hash races,
special files, EFU encoding/collisions, and isolated direct/sdist-built installs.
Native Windows tests cover path/attribute/reparse and concurrent access behavior;
Linux results alone do not prove Windows execution. Missing capability, malformed
input, partial observation and stored corruption remain distinct diagnoses.

Existing Git acquisition preserves durable cumulative work and stop checks after
its import-ownership refactor. Search stores accept bounded projections from
authority-specific extractors and retain content/completeness validation plus scan
fallback. These edits do not claim every pending optional installation complete.
