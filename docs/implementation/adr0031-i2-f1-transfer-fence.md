# ADR 0031 I2 Transfer fence correction — C-F1

The design correction for the High F1 finding in [independent review #121](https://github.com/TakashiSasaki/git-repo-db/pull/121)
is ready for independent re-review. It adds a Direct SQL refusal for the reserved
`resource_relations.relation_kind='transfer_event_report'`, preserving the
existing fence on both Transfer endpoint roles and the entire Resources design.

Read the [before/after contract and implementation-plan addendum](evidence/adr0031-i2-f1/I2-F1-ADDENDUM.md),
[author verification](evidence/adr0031-i2-f1/AUTHOR-VERIFICATION.md), and
[reproduction/re-review handoff](evidence/adr0031-i2-f1/README.md).

On each actual SQLite 3.51.3 and 3.53.1 runtime, 119 bounded author case groups
pass, with zero failed cases and actual process exit 0. The unchanged Task D
minimal SQL succeeds before the correction and raises trigger refusal 1811
afterward. General I8 Parent reporting still succeeds without the native I7
Resource. The schema changes by one trigger only.

The addendum also requires unsupported-stage behavior for future typed APIs,
Exchange/import, readers/export and Search integration. Its executable normalized
routing model is not product code or real Exchange implementation. The SQL
proposal and stage contract need independent Task D review on their final inputs.
I3 Parent constraints, I4 native-I7 SQL and I5 whole-unit Admission remain pending.

This work adds design/evidence files on exact #121 HEAD
`03ff484eca32bf6ed76b4b9fd472c99052f7d8b6`. It changes no predecessor evidence,
Accepted ADR, product source, product DDL/fingerprint, tests, dependency or
workflow. No merge, release, deployment or live-catalog operation is supplied.
