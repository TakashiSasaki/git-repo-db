# ADR 0005: Common OID identity with attributed Git metadata

- **Status:** Accepted owner design decision; DDL and implementation pending.
- **Decision date:** 2026-10-14.
- **Decision ID:** GCTX-M02.
- **Owner selection:** Option A — a common OID identity plus separately attributed metadata.
- **Dependency:** [ADR 0004 / GCTX-M01](0004-metadata-only-git-core.md) (mandatory byte-free Git Core), stacked on [ADR 0003](0003-append-only-git-core-and-context-store.md) (append-only Git Core and durable Context).
- **Baseline:** Unmerged PR #45 HEAD `936ca68c3743749dfc0eb2ad90b8cbd5ba7327ec`. The implemented format remains Three-Store Core Schema 21; this ADR changes no executable schema.

## 1. Binding identity contract

Within a Git Core catalog, each **nominal full Git OID** has one common logical identity keyed by the tuple:

```text
(object_format, oid)
```

- `object_format` discriminates Git SHA-1 from Git SHA-256; the full binary OID is 20 or 32 bytes accordingly. A shortened/ambiguous OID is not silently promoted to a nominal full identity.
- The nominal identity is **repository-independent**. Multiple repositories or acquisitions can refer to the same key without creating duplicate nominal identities. Repository membership, retrieval and ref observations remain distinct, attributed facts; sharing the key does not assert acquisition from either repository.
- A nominal identity means **the catalog has a subject for assertions about the claimed OID**. It does **not** itself prove a real Git object exists, that bytes are available, that the object is a specific type or size, or that a purported parent/tree relationship is canonical.
- `type`, `size`, author, timestamp, message, tree target, ordered parent relationships, tree entries, blob attributes and other reported metadata are **not globally fixed truth on the nominal identity** merely because a source supplied them.
- Attributes and relationships must preserve attribution to their actual source/observation and their epistemic status. Independent reports and byte-derived facts can coexist against the same nominal identity. A later report or verified byte representation must not UPDATE, DELETE or REPLACE earlier admitted reports.
- A reference to an OID without retained bytes may use the common nominal identity, but the presence of that identity never satisfies a requirement for verified object bytes, verified intrinsic structure, source membership or complete graph closure.

This establishes **logical identity** and **domain separation**, not a mandatory physical table name. Using the existing `git_objects` name as a nominal registry, introducing a separate registry, surrogate key choices and concrete foreign-key layouts are *not decided here*.

## 2. Metadata and optional verification

Consider an OID `C`:

1. Source S1 reports `C` has parent `P`; neither object body is present.
2. Independent source S2 reports `C` has parent `Q`; still no raw body.
3. Actual raw bytes for `C` are later acquired, pass exact Git object format/type/size/OID checks, and contain parent `P`.

There is **one common nominal identity** for `C`. Preserve the S1 and S2 reports as independently attributed assertions and add the byte-verified representation/structure without rewriting prior assertions. A successful byte identity check for `C` does not make the unrelated S1 or S2 claims verified, even when a value happens to match. Resolving conflicting metadata for ordinary queries remains a subsequent explicit design decision.

The same principles apply to `tree` entries, claimed object types and sizes, and reported `blob` attributes. A first false report cannot poison nominal identity to block later correct bytes. Differences between metadata reports are not by themselves cryptographic hash collisions. Genuine object-identity or physical-CAS conflicts continue to require the existing strict integrity handling and must not be silently ranked or merged.

Full OIDs in different `object_format` namespaces are **not** the same nominal key even when hex values or underlying payloads appear related. Raw Git byte admission, when requested, still requires exact verification and atomic installation of the intrinsic structure. Physical availability, current health, assertion conformance and scope completeness are separate concepts.

## 3. Domain and persistence boundary

- Git Core alone owns common nominal OID identities and the modeled Git attributes/relationships necessary for metadata-only operation, regardless of whether their contents have been rehashed. Necessary attribution is retained in a Context-independent form.
- Provider/source registration, credentials and mutable Provider/PR/Issue/review data remain Context-owned. Provider-specific associations to Git facts remain Context-owned; they cannot be mandatory parents or FKs of Git Core truth.
- Ordinary metadata queries/traversal and metadata Exchange/backup must function with zero raw Git bytes and no Context. Byte-dependent operations remain explicitly qualified.
- Core is strictly INSERT-only at the application-visible level; no metadata hydration, late-FK backfill, verification promotion, revision update, exceptional CAS repair or GC grants Core UPDATE/DELETE/REPLACE.
- Neither receiver-local object IDs nor bare OIDs without their format may serve as an assumed globally portable identity. Where repository/capture membership is material, the OID alone is insufficient.
- No generalized event store, independent Publication, universal eligibility seal, decoder winner or automatic trusted-source precedence is authorized by the common OID identity.

## 4. Scoped alignment with previous decisions

| Decision / rule | GCTX-M02 effect |
| --- | --- |
| ADR 0003: Git Core append-only, Context-independent | Preserved; nominal identities and reported relations can be installed without modifying existing Core rows |
| ADR 0004 / GCTX-M01: useful metadata-only Git Core | Preserved and made concrete at the identity level: bytes are unnecessary for nominal identity and attributed Git claims |
| Permanent `repository_uuidv4` | Preserved; repo identity and per-repo observations are distinct from shared OID identity |
| Git exact verification and CAS-41 | Preserved for claims of byte identity, retained bytes and recovery; nominal OID presence is not verification |
| Q01-B / Q02-B / Q03-B, NO_INDEPENDENT_PUBLICATION | Preserved; common OID identity is not a Publication or a Provider-history register |
| Source known-positive, Coverage five-column/latest-observation contracts | Preserved; no source membership, actual fetch or completeness is inferred from an OID row |
| Unix epoch microseconds and `_us` naming | Preserved; no timestamp ordering is used to choose a winning report |
| ADR 0001 validation policy | Preserved; these are future counterexamples, not runtime tests completed by this design PR |

This ADR answers **identity strategy only**; it does not settle the semantics of contradictory report visibility or which reports constitute a complete or partial ordered list.

## 5. Consequences and acceptance counterexamples

The following are *future implementation tests*, not executed by this design-only PR.

1. Register full SHA-1 OID `C` from repository R1 and later R2. Both map to one nominal key while their source membership/ref/acquisition facts remain distinct.
2. Register the same nominal OID in metadata-only mode with no type, size or bytes. Ordinary Git metadata queries and traversal remain available without Context.
3. Record differing source-attributed types, sizes, parents or tree entries for one OID. Nothing is overwritten; neither report is silently promoted to a canonical fact or rejected merely because the earlier one exists.
4. Admit later verified bytes for that OID, matching one report and contradicting another. The verified representation is not blocked by earlier metadata; original assertions remain, and their discrepancy can be reported.
5. A nominal parent/tree child key with no materialized bytes does not satisfy verified closure, byte availability, CAS integrity or repository membership requirements.
6. Repeated and reversed Exchange, backup/restore and re-ingestion preserve nominal identity and distinct attributed reports; sender-local surrogate IDs and sender's verification declarations do not grant receiver-local authority.
7. SHA-1 and SHA-256 OID namespaces remain separate, including in foreign references; malformed, shortened and mixed-format identifiers do not enter the nominal full-OID registry.

## 6. Deliberately unresolved: next design question GCTX-M03

**How should reported scalar attributes and multi-valued ordered Git relationships be grouped and attributed, especially for incomplete or conflicting observations?**

Compare source/capture-bounded object reports, individually attributed properties/edges, and a typed hybrid (scalar field claims plus observation-scoped ordered-list groups). No option is accepted until the owner decides. In particular, an independently reported parent edge is not evidence of a complete parent list, and a partial tree page is not a complete tree manifest. Mere arrival order, source preference and parser version do not establish authoritative truth.

Still unresolved: table names/counts/DDL; physical registry layout; provenance record details; conflict and ordinary-read policy; verification execution/result placement (including the prior Context suggestion); metadata/byte/completeness scope semantics; append-only-safe CAS recovery; cross-store transactions, revisions/fences, backup pairing; exact Exchange format; GC-03/GC-04.

## 7. Design-only scope

Stack this ADR on the still-unmerged ADR 0004 PR #45, which is stacked on ADR 0003 PR #44. Do not merge either PR without explicit owner authorization. No application code, DDL, schema version, CLI, mutation of real catalogs, deployment, release or runtime acceptance is authorized by this change.