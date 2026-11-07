# Independent filesystem catalog

`repo-catalog-filesystem` has no dependencies on Git, Core, Context, Access,
Operational, Search or their databases. It uses Python 3.12+ and the environment's
SQLite 3.51.3+ with WAL and thread safety. Installation creates no database.

```sh
repo-catalog-filesystem --database files.sqlite3 init
repo-catalog-filesystem --database files.sqlite3 scan /path/to/folder
repo-catalog-filesystem --database files.sqlite3 scans
repo-catalog-filesystem --database files.sqlite3 export SCAN_UUID --output files.efu
```

Every scan records a fresh UUIDv7 observation within a permanent UUIDv4 filesystem
namespace. Root and relative paths retain native filesystem bytes, with platform
and encoding recorded in the database. Entries and scan outcomes are append-only;
an interrupted process leaves an explicitly incomplete scan. A later scan never
deletes previous observations. Each regular file is read in full and SHA256 hashes
its exact bytes. File bodies are never retained. Symlinks, junctions, other reparse
points and special files are recorded without following or reading their bodies.
Directory and file changes detected during traversal make the result partial;
this is an observation over an interval, not an atomic filesystem snapshot.
Scan results distinguish `enumeration_complete` from `hashing_complete` for the
observed regular files. An unreadable or changed file can leave enumeration
complete while hashing is incomplete; unfinished traversals never claim complete
enumeration.

The scanner accepts generic `exclude_paths` and records the exclusion scope. It
automatically excludes its own SQLite file and journals. Git administrative
exclusion and worktree relationships belong to the optional local bridge. Generic
folder scans do not interpret `.git` or `.gitignore`.

EFU and CSV use the same UTF-8/CRLF serializer, with `Filename`, `Size`,
`Date Modified`, `Date Created`, `Attributes`, and `SHA256`. Dates are integer
Windows FILETIME; unknown creation time is empty (POSIX ctime is never creation
time). Native nanosecond metadata remains in the catalog; FILETIME rounds down
to its 100 ns resolution. `--column` selects optional metadata fields. Cross-OS
offline export uses the stored path dialect. `--path-map SOURCE DESTINATION`
performs an explicit root mapping; it does not imply that files exist on Windows.
Duplicate emitted filenames are refused; case and spelling are preserved.
Non-UTF-8 names are refused unless `--skip-non-utf8` explicitly permits omission, whose count
is reported. Partial scans require `--allow-partial`. Export reads catalog metadata
only, and publishes the output atomically after complete serialization.

`verify` checks the exact schema, SQLite integrity, relationships and terminal scan
counts. `backup DESTINATION` creates a fresh SQLite backup and SHA256 manifest;
`restore SOURCE` verifies both and restores to the fresh `--database` destination.
Backup/restore need no other catalog. Backup hashes establish consistency, not
sender authenticity. Existing destinations are never overwritten by restore.

Python API: `FilesystemCatalog.initialize(path, namespace_uuid=...)`, `.open(path,
readonly=...)`, `.scan(root, exclude_paths=...)`, `.get_scan(uuid)`,
`.iter_entries(uuid)`, `.export_efu(uuid, destination, allow_partial=False)`,
`.verify()`, `.backup(destination)`, and `.restore(source, destination)`. A catalog
is a context manager. Standalone `export_efu(entries, text_stream, extra_columns=...,
row_enricher=...)` accepts DTO enrichment without importing another catalog.
