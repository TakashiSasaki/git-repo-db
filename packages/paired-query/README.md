# Paired authoritative Query

Opt-in Core + Context reads with explicit pairing and snapshots. Install
`repo-catalog-paired-query` and use
`repo_catalog.application.paired_query.PairedQueryService` or the existing
`python -m repo_catalog.cli.production_query` commands. Both existing authorities
are required for paired mode. Installation and reads create no authority,
Access, Operational or Search database.

Search, acquisition, Exchange, and paired backup/recovery orchestration remain
in the composed product. Core retains its existing Git-only recovery minimum. Nominal Core reference availability is distinct from verified
retained bytes and does not authenticate Provider reports. The ordinary Schema21
CLI and catalog format are unchanged.
