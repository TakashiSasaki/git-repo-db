# Git object OID naming contract

The owner selected `object_oid` and authorized the coordinated implementation on
2026-10-31. This is a spelling refinement of [ADR 0005 §1](../adr/0005-common-oid-identity-with-attributed-metadata.md#1-binding-identity-contract),
[ADR 0017](../adr/0017-domain-keys-without-storage-surrogates.md) and
[ADR 0036](../adr/0036-ref-observations-and-shared-notes-mappings.md), with no new
identity, authority or retention meaning. Code, canonical sources and machine
contracts are updated in the same implementation PR. A separate design PR is
not needed for this already selected naming decision.

## Current spelling and scope

The common typed key is `(object_format, object_oid)`. `OID.object_oid` retains
its existing full lowercase hexadecimal value (40 SHA-1 or 64 SHA-256 digits).
Typed object holders in NativeObject, CoreReference and object Query views also
use `object_oid`. Role-qualified OID fields use `<role>_object_oid`, including
root, note and direct/resolved/peeled ref targets; `annotated_object_oid` already
has this form. Plural selection fields use `object_oids` with their role prefix.
The opt-in Query and Access acquisition CLI use `--object-oid`.

The opt-in Core/Context DDL, composite PK/FK and generated expressions, Python
values/ports, SQL adapters, UDF predicates, acquisition intent, Query/Search
JSON, Exchange selectors/wire, backup and typed salvage all use these current
names. The same full tuple values, member order, exact bytes, UUIDs, provenance,
uncertainty and actual-work accounting remain unchanged. No aliases, fallback
parsers, dual-write fields or permanent spelling conversion registry are added.
The implementation checklist is temporary working material, not product data.

Normal Catalog3 Core Schema 21, its BLOB OID columns, legacy runtime and generated
normal-schema views remain a separate implemented format. This change neither
replaces that startup with P1 nor activates the five-store target. Provider wire
keys (including GitHub GraphQL `oid`) and native Git grammar retain their actual
external spelling. Historical audits, frozen evidence, baseline schema inventory
and historical examples remain bound to their original sources; their names are
not old-name compatibility interfaces. General refs gain no Notes-only prefix.
Resource coordinates, acquisition/observation UUIDs, `object_format`, SHA-256 body
digests, Context parent coordinates and `text_bodies.sha256` are unchanged.

## Fresh formats and preserved boundaries

The incompatible opt-in DDL uses `repo-catalog/p1-isolated-3`, Exchange uses
`git-repo-db/adr0036-exchange-v8`, and backup manifests use version 3. Regenerated
DDL fingerprints and the existing P1 physical audit bind the current schemas.
Previous formats and old field shapes are rejected, even with a recomputed
checksum. There is no retained-catalog migration or old-name auto-conversion.

Original RefObservation, immutable Claims, shared Mapping content, receiver
proof and physical copies remain separate. Rootless/unknown/absence metadata
needs no invented OID; a shared root does not lend another Claim body authority.
Core remains INSERT-only. Corruption still stops the catalog and preserves the
suspect DB/WAL; salvage is untrusted, restore uses a fresh validated destination,
and revalidation/merge precedes activation under ADR 0026. This PR authorizes no
real data operation, ordinary-runtime cutover, release, deployment or merge.
