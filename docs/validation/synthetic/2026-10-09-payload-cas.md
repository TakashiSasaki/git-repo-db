# Payload CAS admission validation

Base: identity foundation `e94c767`, branch `refactor/payload-cas`.
Schema advances from 10 to 11 with 66 ordinary tables. Workspace remains schema 2.

## Scope

Physical byte deduplication, representation-scoped payload identity, composite
FKs, atomic admission, digest verification, exact-byte comparison, immutable
storage and canonical JSON references. REST/GraphQL saved pages, validators,
normalization diagnostics and guarded v2 salvage use the new references.

This is an intermediate implementation. Durable staging, quarantine, explicit
repair, full hash scans and exchange ownership validation remain future work.
The old backup/restore integrity checks are unchanged and do not yet implement
payload hash verification. All exercised data is synthetic and disposable.

## Development checks

The first focused run passed 223 tests and failed one obsolete table-count
expectation (65 instead of 66). The expectation was corrected. The subsequent
payload/import-workspace check passed 29 tests. The corrected target-schema and payload contract check passed 95 tests.
Final clean acceptance is attributed below to its exact tested revision. No original design
attachments are included in these commits.

## Clean acceptance

Tested commit: `de22363585419cba4817bc5d1a8e41cd7f837cb2`.
Tested tree: `c5556d5194bc3f7876edd4297baeb9c8c6a7dc29`.

- Ordinary acceptance: 854 passed in 96.66 s.
- Installed wheel and sdist acceptance: 2 passed in 4.83 s.
- Final reconciliation: 856 executed across 50 selected files, with zero
  unexecuted or excluded files.
- Lint, formatting, prose, locked dependency/wheel preparation, SQLite doctor
  and FTS probes passed.
- The new CAS contract file contains 17 tests. It checks physical deduplication,
  distinct logical representations, separate acquisitions with equal bytes,
  canonical references, composite FKs, mismatch/collision/corruption admission,
  immutable storage and rollback on logical-registration failure.

Environment: Python 3.12.14, SQLite 3.53.1, Git 2.51.1, uv 0.12.19,
pytest 9.1.1, Ruff 0.16.10. Commands follow the packaged CI workflow:
`ci_plan.py --full`, `ci_execute.py collect`, ordinary and packaging lanes,
then `ci_execute.py gate`. Preparation/static commands are profiled separately.

These local results do not claim hosted CI, real-source acquisition or completion
of the whole redesign. GitHub publication is pending: an earlier push containing
original user attachments was rejected; a clean-history push excluding them did
not complete network approval. No PR has been created for these strides. The
current publication history contains implementation, tests and concise evidence,
without copied source attachments.

## Continuation

Next integrate portable acquisition IDs and separate parsed results with typed,
owner-matched inputs and generated-fact FKs. Then add whole-profile verification,
immutable selection/predecessor manifests and staged dependency resolution before
switching ordinary queries. Keep the previous verified identity/CAS checkpoints.
Durable exchange, local quarantine/repair and frozen Job inputs follow the planned
integration. No unresolved design choice is filled in by this stride.
