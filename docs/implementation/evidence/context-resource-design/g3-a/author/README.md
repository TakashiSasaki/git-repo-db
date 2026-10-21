# Author execution on frozen G3=A inputs

Both runtimes executed the exact inputs at commit
`4c07cb8ecc4d744ddfb8c3908deb91d8ad72f6f9`, tree
`e171de9f2459b0ade409bebb40787b850d88ff5e`, sequentially.
The [summary](summary.json) records the command, all actual runtime details,
input/SQL hashes and compressed receipt file hashes. Each runtime passed
**11 focused groups / 292 recorded steps** with 0 failed groups. Counts overlap
between runtimes and are not summed as distinct cases. The composed Context
schema measured 19 tables. Both actual I8 direct-SQL attempts raised
`SQLITE_CONSTRAINT_FOREIGNKEY` extended code **787** before a rollback.

Raw `results.json.gz` contains every recorded statement's pre/post rowsets,
transaction state, SQL trace, actual SQLite error name/extended code and
BEGIN/COMMIT/ROLLBACK steps. `inventory.json.gz` contains actual schema,
columns/indexes/FKs. `candidate.sql.gz` is the exact composed DDL. Compression
is lossless; raw and compressed hashes/lengths are both recorded.

SQL structural enforcement and typed Admission limits are distinguished in the
[current experiment contract](../README.md). GA06 proves whole-unit Admission
rollback; GA10 explicitly permits a raw caller's partial multi-statement commit.
A passing experiment is not acceptance of product I6/I7/I8 or packaging/runtime
integration, and is not acceptance or merge of the proposed ADR.

Publication losslessly compresses stdout logs as `.log.gz` to preserve raw
whitespace while keeping `git diff --check` clean. Pre-transport summary/manifest
snapshots are retained; raw log hashes/bytes and all execution results are unchanged.
