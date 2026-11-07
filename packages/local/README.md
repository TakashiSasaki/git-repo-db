# Local catalog composition

`repo-catalog-local` composes the independently usable filesystem and worktree
catalogs. It has no database of its own and does not load Core, Context, Access,
Operational, Search, or the older POSIX catalog runtime.

```sh
repo-catalog-local init --filesystem-db files.sqlite3 --worktrees-db worktrees.sqlite3
repo-catalog-local scan --filesystem-db files.sqlite3 --worktrees-db worktrees.sqlite3 /path/to/checkout
repo-catalog-local export --filesystem-db files.sqlite3 --worktrees-db worktrees.sqlite3 --scan SCAN_UUID --output files.efu
```

An explicit root expands all registered sibling worktrees of that local Git
repository. A bare repository supplies topology but no file scan. Nested
repositories and submodules are inspected without recursively expanding their
sibling worktrees. Ordinary directories are also scanned. Filesystem errors and
missing worktrees remain separate outcomes, and successful scans survive other
failures. Scans hash regular files, including untracked and ignored files. Git
administration directories are excluded unless `--include-git-admin` is selected.

The composition performs a metadata walk to find nested Git administration
locations before the filesystem scan. It reads file content only in the latter.
Catalog databases and their SQLite sidecars are always excluded from their own
scans. No file bodies are retained.

Cross-store references are appended only after a filesystem scan is committed.
They do not require paired backup, foreign keys, shared transactions, or a live
Git checkout. Export reads saved observations only. Omit `--worktrees-db` to
export filesystem data without Git enrichment; `repo-catalog-filesystem` also
works with this entire composition distribution uninstalled.

The default export refuses partial scans. `--allow-partial` selects their
actually observed entries explicitly. Exports replace their selected destination
atomically only after all selected entries serialize successfully.
