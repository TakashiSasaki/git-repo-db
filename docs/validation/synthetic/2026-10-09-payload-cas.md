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
payload/import-workspace check passed 29 tests. Final clean acceptance results
will be attributed below to their exact tested revision. No original design
attachments are included in these commits.
