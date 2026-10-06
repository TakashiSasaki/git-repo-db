# Retained real v2 catalog discovery — N/A

Application `bdc6a6eb9044f316cd9ebea9e70dd484b49ff406`, 2026-10-06 UTC. Python 3.12.14, SQLite 3.53.1. [JSON summary](2026-10-06-retained-v2-discovery-bdc6a6e.json) records exact paths, format identity, sizes, fingerprints, scope, commands and explicit criteria.

XDG_STATE_HOME is unset; default `/home/agent/.local/state/repo-catalog` does not exist. Only known application catalog/config filenames under `/workspace/git-repo-db` and prior `/tmp/repo-catalog-real-world-adij66vr` were inspected. The current API trial is newly created catalog3 and excluded. No unrelated home, attachment or library contents were searched.

Six identified databases explicitly have format `repo-catalog/catalog3`, schema version 3, lifecycle validated. Three belong to the documented synthetic installed-wheel trial and three to the accepted public Git trial:

- `/workspace/git-repo-db/artifacts/operational-trial-20261006/restored-state/catalog.sqlite3`
- `/workspace/git-repo-db/artifacts/operational-trial-20261006/fresh-state/catalog.sqlite3`
- `/tmp/repo-catalog-real-world-adij66vr/restored/catalog.sqlite3`
- `/tmp/repo-catalog-real-world-adij66vr/backup/catalog.sqlite3`
- `/tmp/repo-catalog-real-world-adij66vr/catalog/catalog.sqlite3`
- `/workspace/git-repo-db/artifacts/operational-trial-20261006/synthetic-backup.sqlite3`

**N/A:** no genuine retained pre-catalog3/v2 source found. Import/finalization/imported queries/backup/restore were not run; a newly collected or synthetic source does not substitute.

**PASS, preservation:** only URI mode=ro database reads; all six SHA-256 fingerprints unchanged. Caches were neither opened nor changed. No source was migrated, moved, renamed, repaired, vacuumed, overwritten or deleted. Only temporary measurements and repository summaries were written. HTTP/API requests: zero. This is scoped absence, not an assertion about unrelated storage; there is no ambiguity among these known catalog3 artifacts.
