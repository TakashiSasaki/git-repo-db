# repo-catalog-core

Minimal opt-in Git Core: initialization, typed admission, reads and Git-only Recovery.

This synchronized distribution is part of git-repo-db. It includes the
`CoreRecoveryService` Python entry point for verified backup, persistent stop,
bounded salvage, fresh restore, receiver-validated merge and safe activation.
Git-only activation creates no Context, Operational or Search database. Paired
Recovery requires the composed distribution. Revision-bound OP-01/OP-02
execution evidence is recorded separately from these implementation statements.
