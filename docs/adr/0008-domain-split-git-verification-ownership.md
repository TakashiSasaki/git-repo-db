# ADR 0008: Domain-split Git verification ownership

**Current post-corruption override:** [ADR 0026 / GCTX-M10](0026-stop-salvage-restore-merge-after-corruption.md) requires stopping ordinary catalog operation, preserving the suspect source read-only, serializing salvage candidates, restoring a verified backup into a fresh destination and merging only revalidated admissible data. Prior post-fault metadata service, same-DB failover, known-corrupt normal backup/restore and references to M10 as pending are historical in that scope. Ordinary sound-catalog rules and unrelated open work remain. No implementation or merge is authorized.

- **Status:** Accepted owner design decision; evidence representation and implementation pending.
- **Decision date:** 2026-10-14.
- **Decision ID:** GCTX-M05.
- **Owner selection:** Option C: Git intrinsic verification and required durable immutable evidence belong to Git Core; Provider-specific assessments belong to Context; verification execution Jobs/progress belong to Operational.
- **Dependencies:** [ADR 0003](https://github.com/TakashiSasaki/git-repo-db/blob/bb878eda47cf17268dd821c74343bac64d769ea7/docs/adr/0003-append-only-git-core-and-context-store.md), [ADR 0004 / GCTX-M01](0004-metadata-only-git-core.md), [ADR 0005 / GCTX-M02](0005-common-oid-identity-with-attributed-metadata.md), [ADR 0006 / GCTX-M03](0006-field-claims-and-observation-scoped-relations.md), and [ADR 0007 / GCTX-M04](0007-verification-aware-git-metadata-reads.md).
- **Baseline:** Unmerged PR #48 HEAD `5963f28229bc7798634d549855a08db06d12b3a6`, stacked on PRs #47 → #46 → #45 → #44.
- **Implementation status:** Three-Store Core Schema 21 remains the implemented schema. This ADR is design-only.

## 1. Binding responsibility boundary

Separate (a) where the verification algorithm executes, (b) which authoritative store is responsible for the claim and durable evidence, and (c) where retryable Job execution state resides. A pure/shared library may implement cryptographic checks; using that library from Context never makes Context authoritative for Git Core byte admission.

| Responsibility | Owner and binding rule |
| --- | --- |
| Git object format, exact full OID, type/size, and hash of canonical Git header plus actual raw body; SHA-1 or SHA-256 as declared | **Git Core admission boundary.** Mandatory for optional *byte-verified* representation admission; independent of Context |
| Commit/tree/tag intrinsic structure parsed and checked against exact raw Git bytes; atomic object representation and intrinsic installation | **Git Core**, without mutable late-FK backfill or partial representation marked canonical |
| Comparing Core-owned source-attributed scalar claims and typed parent/tree relation groups to already validated bytes | **Git Core domain**, or computation from Core data; independent of Context and scoped to the specifically checked field/relationship |
| Durable evidence needed to establish historical Git byte admission, Core-only canonical interpretation, physical corruption diagnosis and CAS-41 | **Git Core**; precise immutable record granularity is deliberately unresolved |
| Provider/API-specific quality, source assertions and their evaluation, PR-specific context, field status and attribution | **Context**, with current-state UPDATE only where Context's existing domain contract allows |
| Verification Job execution, retries, leases, cancellation and transient scan progress | **Operational**; disposable and not the sole owner of an admitted fact or indispensable integrity diagnosis |
| Search/FTS and cached derived verification-aware views | **Search**, always rebuildable and not a verification authority |
| Git acquisition/graph completeness versus Provider/API Coverage | Separate Git/Core and Provider/Context evidence domains. OID verification proves neither graph closure nor the preexisting five-column Coverage complete state |

Provider data can supply a modeled Git metadata claim to Core if the claim's provenance is independently understandable without Context. Provider registration, credentials, PR state, mutable Provider assessments and associated textual bodies remain Context-owned. The Core may independently compare its own stored claims to its verified object bytes; a Context assessment cannot be the sole validity gate or FK required by Core.

## 2. Different notions of verified and available

1. **Metadata-only:** GCTX-M01 permits Core identity, attributes and relationships with zero original bytes, no rehashing, no Context and no verification Job. Merely recording a full typed OID neither proves the object exists nor certifies its type/size, source membership or closure.
2. **Byte-backed admission:** Actual raw Git bytes must pass receiver-local exact format/OID/type/size checks before Core records them as verified. The verified representation and its intrinsic structure enter atomically. A sender's `verified` bit, consensus among providers, or a Context report is not a substitute.
3. **Per-field conformity:** Hashing a Git object does not automatically verify all earlier Provider/source claims, Unicode-decoded author/message values or every decoder candidate. GCTX-M04 permits canonical reads only for individually justified intrinsic interpretations, while preserving conflicting reports.
4. **Historical admission versus present physical health:** Previously validated raw bytes can subsequently suffer storage corruption. Historical admission evidence, current CAS presence, current byte integrity, quarantine/repair and reachability are distinct. Intentional metadata-only nonacquisition is *not* physical corruption.
5. **Persisted success records:** GCTX-M05 does not require a new row for every successful scan, a historical verification-attempt ledger, mutable `git_objects.verified`, a universal eligibility seal or independent Publication authority. GCTX-M06 will select the evidence granularity and physical-health policy.
6. **Repair:** Strict CAS integrity/collision guarantees and CAS-41 remain. The old trigger-disabling/in-place byte UPDATE repair conflicts with append-only Git Core and must not return. Exact append-only-safe recovery remains undecided.

## 3. Concrete counterexample

At T1, a Provider reports commit C parent Q without object bytes. Core retains the nominal C and a source-attributed parent relation group containing Q, while Context retains Provider/PR-specific metadata and assessments. At T2, the actual raw body of C is acquired. A receiver-local canonical Git hash recomputation matches C, and the raw intrinsic commit structure contains parent P. Core atomically admits the byte-verified representation with parent P; the earlier Q report remains unmodified.

At T3, Context is missing and Operational has been recreated. Core must still answer the checked parent relation with canonical P, expose Q as a conflicting reported alternative, and truthfully distinguish currently available raw bytes from historical admission. It must not infer the actual parent P object has been acquired or the whole DAG is complete.

At T4, Context can evaluate a Provider-specific discrepancy by referring to a coherent Core read snapshot under the still-to-be-designed cross-store fence, without changing Core truth. No Context write can retroactively forge the prior Git observation or become a prerequisite for Core-only use.

## 4. Compatibility with accepted design

- **GCTX-M01 / ADR 0004:** useful byte-free Git Core cataloging without Context, hidden clone or automatic validation remains mandatory.
- **GCTX-M02 / ADR 0005:** one common nominal `(object_format, oid)` identity across repositories. Byte verification does not mutate the nominal identity or assert unreported type/size.
- **GCTX-M03 / ADR 0006:** separate source-attributed field claims and typed observation-scoped parent/tree relation groups stay immutable; no fabricated union or completeness.
- **GCTX-M04 / ADR 0007:** receiver-verified exact bytes justify only the checked intrinsic field/relationship in ordinary reads; agreement among unverified reports is still unverified, contradictory values remain alternatives.
- **ADR 0003:** Core remains strictly application-level INSERT-only and Context-independent. Context is an independently durable authority and can update Provider assessments; Operational/Search remain reconstructible. No Core UPDATE/DELETE/REPLACE, GC, mutable repair or Core→Context mandatory FK.
- **Unchanged decisions:** permanent `repository_uuidv4`; Q01-B/Q02-B/Q03-B; unaffected PF-P01–PF-P17; Source known-positive associations; Unix epoch microseconds with `_us`; original Coverage five-column/current-observation semantics; strict OID and CAS/CAS-41 validation; NO_INDEPENDENT_PUBLICATION; ADR 0001.
- **Backup and transactions:** Context-specific assessments referencing Core need the separately designed cross-store read fence. Full backups containing Context still require a consistent paired Core+Context snapshot, while Git-only Core backups remain independently usable.

This decision fixes **domain ownership**, not DDL/table names, concrete validation receipt format, whether a successful repeated check is durably logged, contemporaneous physical health guarantees, or a cross-store transaction protocol.

## 5. Future acceptance counterexamples (not tests executed here)

1. Import commit/parent/tree/blob metadata and query Core alone without bytes, Context or a verification Job.
2. Verify and admit correct Git bytes in a Context-free Core; reject mismatched OID/type/size without creating byte-verified facts.
3. Keep a false source report beside a correct later byte-verified intrinsic field; no prior claim is rewritten or indiscriminately marked verified.
4. A sender's claimed verification, an imported digest or Context provider verdict alone cannot create receiver-local byte authority.
5. Deleting/recreating Operational and omitting Context cannot invalidate durable Core metadata, admitted bytes or required integrity evidence.
6. Provider assessment UPDATEs in Context cannot rewrite or remove Git Core facts; failure of Context assessment does not destroy Core-only canonical reads.
7. A verified parent edge does not prove that the parent object bytes exist or that graph closure/Source membership is complete.
8. Corruption or quarantine of retained CAS bytes is not the same as initial zero-byte metadata mode; current byte-dependent paths fail closed and CAS-41 counting survives.
9. Reversed/repeated Exchange and Core-only / paired backup restore preserve provenance and receiver-trust boundaries.
10. No generic success-event/Publication ledger, unapproved parser-winner policy or Core mutation bypasses prior decisions.

## 6. Subsequent owner decision: GCTX-M06 accepted; next GCTX-M07

[ADR 0009 / GCTX-M06](0009-bounded-byte-admission-and-physical-health.md) selects Option B: bounded immutable per-representation admission evidence, separate from current physical-byte health. The following alternatives document the original question, not a still-open owner choice. ADR 0010 / GCTX-M07 now fixes operation-scoped assurance tiers, while the exact snapshot/locking implementation remains open. [ADR 0012 / GCTX-M08](0012-append-only-multiple-cas-physical-instances.md) selects append-only alternate-instance recovery; GCTX-M09 selection/active quarantine remain open.

How should Git Core represent immutable admission of verified original bytes and separate it from **current** physical availability?

- **A: On-demand verification.** Keep real bytes and their identity/linkage, recompute type/size/OID and intrinsic checks whenever byte-backed canonical data is requested; no extra persistent success ledger.
- **B: Bounded immutable per-representation admission evidence with separate physical-health evaluation.** Atomically bind verified real bytes, identity and intrinsic structure; that committed binding proves historical admission. Physical instance health and current byte availability require their own truthful validation/diagnostics. Do not log every successful periodic rescan.
- **C: Append-only per-attempt verification history.** Every verification success/failure becomes a separate durable record, independent of bytes, with detailed timing/input; evaluate the storage, stale-result and generic-ledger risks.

**GCTX-M06 is decided by ADR 0009 (Option B).** Do not claim that historical admission proves current healthy bytes. Exact on-read hash frequency/scan freshness, physical-instance identity, quarantine closure, append-only-safe CAS repair and backup integrity are still unresolved.

Other open design work: full 70-table impact/DDL model, typed metadata/provenance and group-completeness evidence, local revision and read fences, Core/Context transaction and backup pairing, Exchange wire format and GC-03/GC-04.

## 7. Scope and authorization

Stack this design-only decision on unmerged PR #48. PRs #44 through #48 are not authorized for merging. No Python/DDL/schema-version/CLI changes, actual catalog migration, release, deployment, raw authenticated collection, retained-data mutation or implementation are authorized. Validate future implementations under ADR 0001; these acceptance scenarios are not executed evidence.
