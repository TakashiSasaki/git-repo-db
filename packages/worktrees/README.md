# Worktree topology catalog

`repo-catalog-worktrees` independently records local Git worktree observations in
its own SQLite database. It reads Git topology only: it never fetches, checks out,
repairs, prunes, or archives file contents. Filesystem scans and Git Core/Access
databases are optional external references, not installation dependencies.

```sh
repo-catalog-worktrees --database worktrees.sqlite3 init
repo-catalog-worktrees --database worktrees.sqlite3 discover /path/to/checkout
repo-catalog-worktrees --database worktrees.sqlite3 list
repo-catalog-worktrees --database worktrees.sqlite3 verify
repo-catalog-worktrees --database worktrees.sqlite3 backup /new/backup-directory
repo-catalog-worktrees --database restored.sqlite3 restore /new/backup-directory
```

Discovery supports ordinary and linked worktrees, separate Git directories,
submodules, and distant bare repositories. Registered inaccessible worktrees stay
visible. `--no-expand` observes only the nominated checkout. Paths are preserved
as native filesystem bytes; JSON includes hexadecimal values for lossless use.
Repository UUID mappings are explicit assertions and never inferred from URLs,
paths, HEAD, or matching content. Backup/restore uses a fresh destination and
validates the database plus its SHA-256 manifest.

Git registration and per-checkout inspections are observations made over an
interval, not an atomic filesystem snapshot. An interrupted or bounded discovery
reports partial scope while preserving the topology already observed.
