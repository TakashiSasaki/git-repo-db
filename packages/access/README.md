# repo-catalog-access

Independent opt-in Access configuration, local approvals and coherent Access-only
backup/inspection/fresh inactive restore. Requires Python >=3.12, POSIX/Linux for
the existing local adapters, and the SQLite capabilities checked by Access
(SQLite >=3.51.3). There are no Python runtime dependencies.

Install explicitly; installation opens no catalog and initializes no database.
`repo_catalog.adapters.sqlite.access_schema.initialize(path)` explicitly creates
only `access.sqlite3`. Use `AccessConnections`, `AccessWorkflow` and
`AccessMaintenance` through their existing public APIs. A Repository UUID is a
logical reference; no Core registration is required.

Existing CLI modules remain available:

```
python -m repo_catalog.cli.access_workflow --help
python -m repo_catalog.cli.access_maintenance --help
```

Approval and local execution preflight require a local terminal. A synthetic
review callback is a trusted test/admin mechanism, not proof of human approval.
Restore removes grants and disables routes; destination-local reapproval is
required. A backup preserves Access configuration only. It is not domain recovery.

Core, Context, Operational, Search, Git acquisition, Exchange and paired Recovery
are absent. Access-approved acquisition remains part of the composed `repo-catalog`
product. No normal Schema 21 startup behavior changes.
