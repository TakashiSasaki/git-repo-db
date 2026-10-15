# ADR 0010: Operation-scoped physical integrity assurance for Git Core CAS

- **Status:** Accepted owner design decision; concrete DDL, reader/locking protocol and implementation pending.
- **Decision date:** 2026-10-15.
- **Decision ID:** GCTX-M07.
- **Owner selection:** Option B — operation-specific assurance tiers: metadata-only/history queries need no rehash, while operations representing or exporting currently verified original Git bytes must check the actual bytes in the operation's coherent scope. Full/scoped audits report as-of results, not eternal health.
- **Direct predecessor:** [ADR 0009 / GCTX-M06](0009-bounded-byte-admission-and-physical-health.md), design-only PR #50 HEAD `29dd530a4245a62c7b9c0dbf2cd07a2ad62cb84e`.
- **Earlier decisions:** [ADR 0003](0003-append-only-git-core-and-context-store.md) and [ADR 0004 / GCTX-M01](0004-metadata-only-git-core.md) through [ADR 0008 / GCTX-M05](0008-domain-split-git-verification-ownership.md). This is a design-only step stacked above still-unmerged PRs #44–#50.
- **Implemented baseline:** The existing Three-Store Core Schema 21 remains unchanged; no GCTX-M07 runtime behavior is implemented by this ADR.

## 1. Binding distinction: historical admission is not live physical health

GCTX-M06 establishes bounded, immutable, receiver-verified original Git representation admission: canonical OID/type/size, actual raw bytes/CAS association and checked intrinsic structure form a historical Git Core fact. It remains true after damage. However, it **does not establish the present integrity or existence** of the physical bytes.

GCTX-M07 fixes that **an operation's required assurance determines the necessary current-byte checks**. The status of a nominal OID, verified historical admission, source-attributed metadata, current physical-instance health, and graph/scope completeness remain distinct and must never be collapsed into one mutable `verified` boolean.

The contract is not “rehash every normal metadata query” and not “trust the last full scan indefinitely”. Query/result types need explicit qualification about the kind of proof, inspected physical subject, scope and time/snapshot where applicable. Exact public JSON/SQL enum names remain a separate implementation decision.

## 2. Selected operation-specific assurance tiers

| Requested operation or assertion | Required guarantee |
| --- | --- |
| **Metadata-only / nominal OID / source-reported scalar and relation-group query** | No raw Git bytes, CAS, hash computation, Context database or implicit fetch required. Return reported/unverified, conflict, partial, unknown and source attribution truthfully |
| **Historical canonical intrinsic metadata query** | May rely on the bounded immutable, locally verified admission evidence and the exact checked intrinsic relation. Do not require full current-body rehash merely to show historical facts. Surface known physical degradation/quarantine and do not present historical admission as healthy-now |
| **Raw object bytes export, checkout/read path presented as verified Git content, or byte-returning Exchange transfer** | Validate the **actual bytes to be delivered** against their physical SHA-256/CAS identity and the claimed Git object format/type/size/OID as appropriate to that representation. A merely historical or prior-scan success is insufficient |
| **Operation explicitly claiming current physical integrity or physical availability** | Check the particular required physical instance(s) using a coherent operation read/snapshot with a defined stable checked scope. Return a result qualified to that checked scope/snapshot; do not guarantee health at arbitrary later times |
| **Explicit bounded or full CAS integrity audit, e.g. `db verify-payloads`** | Inspect actual requested physical instances, report the checked set/interval, observed integrity, failures and necessary persistent fault evidence. A full audit is “as of the checked snapshot”, not a general permanent healthy flag |
| **Restore and backup integrity gates** | Apply existing format, retained physical payload, manifest and CAS-41 checks at the appropriate copied/staged snapshot. Verify the backed-up active physical quarantine count **before** restore-time diagnosis. Git-only metadata backup is separately valid when no original bytes were acquired |

For raw-byte **validated output**, the verification must cover the same byte sequence as the actual emitted artifact. A two-read implementation without a protected/equivalent immutable read snapshot may verify one body and output a different one. Conversely, streaming unverified chunks as already trusted before a trailing digest failure is **not** equivalent to a successful verified export. The detailed solution (bounded spooling, snapshot-pinned read, atomic staged output, or equivalent) is deferred to implementation design; the invariant is fixed. Trusted output must not be successfully published if the bytes fail or are insufficiently validated.

A byte-returning diagnostic/debug API explicitly labeled *unverified* is not by this ADR granted the same guarantee as a verified export; whether to offer such a mode is not decided here.

## 3. Checking scope, time and fault behavior

1. **As-of is not now forever.** A successful verification at T2 may be represented as “checked at T2 against physical instance I in snapshot S”, not unqualified “healthy at T4”. After the check, storage may deteriorate independently of the database.
2. **Known fault fails closed.** A physical instance with known unresolved corruption, quarantine, absent retained bytes or an unresolved collision must not be returned as a currently verified raw object. Existence of metadata or an earlier admission does not negate this.
3. **Unknown differs from healthy.** If a physical instance has not passed the checks demanded by an operation's assurance tier, its current health is not established; do not silently treat absence of a diagnostic as success.
4. **Object identity and storage digest.** When claiming verified *Git bytes* the requested integrity check covers both the physical-byte identity (including CAS digest and exact bytes) and the relevant canonical Git OID/type/size relation, not just a stored checksum string. Typed intrinsic structure must be matched to the validated representation, not to an unrelated object report.
5. **Coherent read/snapshot.** The checked byte instance, OID association, quarantine/integrity evidence and emitted result must refer to a coherent read scope. A concurrent Core append, later quarantine or underlying file corruption cannot be hidden by combining mismatched observations. SQLite snapshots, lock scope and any external physical-instance pinning are not yet selected.
6. **Audit correctness.** An audit claiming “all retained physical instances” must not silently omit newly admitted instances that are within its announced scope. For a long scan, explicitly define the frozen membership or per-instance checked window and the point-in-time limitation; do not pretend that one non-atomic walk provides an instantaneous all-file guarantee without evidence.
7. **No mandated success ledger.** Successful per-use checks/full scans can report to callers and Operational execution status without a durable success event for each. Real corruption diagnostics necessary for faithful Core integrity and CAS-41 cannot be solely Operational and cannot be erased by ephemeral-state recreation.
8. **No automatic fetch.** A metadata query never triggers a clone or byte hydration; unavailable bytes remain unavailable for operations that genuinely require them. No Git Core GC or accepted-byte rewriting is introduced.

This is a **semantic assurance contract**; exact scan cadence, mandatory low-level Git validation entry points, file-handle lifetime, backup fence protocol, cache invalidation and the physical-instance design belong to subsequent implementation decisions. It does not order periodic automatic scans or reinterpret the historical `verified` projection.

## 4. Worked adversarial sequence

| Time | Event | Required result |
| --- | --- | --- |
| T1 | Metadata-only claim `parent(C)=Q` arrives without body | Valid nominal/attributed Git Core metadata; no CAS or integrity failure |
| T2 | Actual commit C body is locally rehashed, validated and immutably admitted; canonical parent is P | Historical byte-backed parent P is usable as canonical per GCTX-M04; earlier unverified Q retained |
| T3 | Explicit full CAS audit passes all physical instances in its checked snapshot | Report T3 as-of scope and success, not a durable promise of future health |
| T4 | Physical instance I storing C suffers an external bit flip (not yet detected) | T2 admission remains true, T3 audit becomes stale for T4; lack of diagnosis is not proof of present health |
| T5a | User requests only C's historical verified parent | Core may return P with historical-canonical qualifier, preserve alternative Q and avoid mandatory rehash; do not claim current raw bytes are healthy |
| T5b | User requests C's original bytes as verified Git object | Verify the exact bytes to be emitted under the operation's consistency contract. If corrupted, deny successful verified export and retain appropriate fault diagnosis |
| T6 | Correct bytes are independently reacquired | Future append-only-safe recovery must not rewrite I or erase its history. Recovery via a new independently validated physical instance is fixed by ADR 0012 / GCTX-M08; candidate eligibility/selection is fixed by ADR 0013 / GCTX-M09, while active quarantine/retirement remains open for GCTX-M10 |

A verified edge C→P does not prove P's raw bytes exist or that whole-graph closure is complete. A metadata-only catalog must remain usable after Operational/Search recreation and Context omission.

## 5. Reconciliation with prior accepted decisions

| Accepted decision | What is preserved under GCTX-M07 |
| --- | --- |
| GCTX-M01 / ADR 0004 | Core-only metadata import/query/search/traversal without raw bodies, Context, mandatory rehash or implicit fetch |
| GCTX-M02 / ADR 0005 | Shared nominal full `(object_format, oid)`; a subject identity has no inherent “currently verified” status |
| GCTX-M03 / ADR 0006 | Attributed scalar claims and typed observation-scoped ordered relation groups; no union, fabricated completeness or lost alternatives |
| GCTX-M04 / ADR 0007 | Locally byte-verified intrinsic fields can be canonical; unverified/conflicting alternatives remain visible. Historical byte-derived value is not a live CAS health statement |
| GCTX-M05 / ADR 0008 | Intrinsic byte checks and required fault evidence remain Core-owned; Provider-specific assessments Context-owned, verification Jobs Operational-owned, Search derivative |
| GCTX-M06 / ADR 0009 | A bounded immutable admitted-representation fact proves historical local admission; current-byte assurance is separate and operation scoped |
| ADR 0003 | No application-level Core UPDATE, DELETE, REPLACE, in-place CAS correction or Git Core GC; no Core dependence on Context or a generic eligibility/Publication gate |
| Fixed invariants | `repository_uuidv4` permanence, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, Source known-positive, Coverage five-column/latest-observation semantics, Unix microseconds `_us`, exact Git identity/CAS and CAS-41, NO_INDEPENDENT_PUBLICATION, ADR 0001 |
| Backup/Exchange | Local receiver verifies sender's bytes independently when claiming local authority; Git-only backups preserve appropriate scope, complete Context-containing backups require paired authoritative snapshots, and faults must not be mislabeled as intentionally absent bytes |

No “last success wins”, no cryptographic certification of Provider authenticity, no global preferred decoder, and no new completion seal follows from these assurance tiers.

## 6. Future executable counterexamples (NOT run by this ADR)

1. Query and traverse metadata-only Git Core with no original bytes and Context absent. No rehash, automatic fetch, fabricated health or accidental `verified=1` occurs.
2. Read historical canonical commit-parent facts from immutable admission evidence without mandatory raw-body load; separate known corrupt/unavailable physical health from the historical fact.
3. Export verified original bytes with a correct CAS digest but wrong Git OID/type/size: reject and avoid publishing an apparently successful verified object.
4. Flip a byte after a successful earlier scan but before verified export: deny success by checking the emitted bytes rather than trusting that older scan.
5. Inject a body-change race between “validate” and “emit”; no checked-A / published-B substitution is accepted as verified output.
6. Inject interruption/failure while spooling/staging verified output; no partially delivered artifact is reported as a successful verified export.
7. Verify an explicit scoped/full set under concurrent new admissions: output makes its snapshot/member boundary explicit, not a falsely instantaneous or limitless whole-CAS guarantee.
8. Recreate Operational/Search; missing transient scan progress does not change Core historical facts or erase necessary durable physical faults.
9. Quarantine a corrupted retained physical instance and test honest metadata-only vs byte-export behavior, independent of Context; preserve CAS-41 active quarantine count ordering during restore.
10. Exchange raw Git bytes from a sender asserting `verified`: receiver rechecks exact bytes before local byte-backed admission; metadata-only exchange needs no payload.
11. Verify Git-only metadata backup/restore with no byte bodies and full paired backup with Core+Context, without confusing physical integrity, metadata completeness or graph closure.
12. Ensure no new universal verification ledger, mutable preferred-result pointer, new decoder winner or arbitrary Core UPDATE/DELETE/REPLACE path is introduced.

## 7. Subsequent owner decision: GCTX-M08 accepted; next GCTX-M09

[ADR 0012 / GCTX-M08](0012-append-only-multiple-cas-physical-instances.md) selects Option A: multiple immutable physical instances per logical CAS payload, with appended instance-specific corruption and recovery evidence; original damaged bytes are not overwritten or garbage-collected. The following A/B/C comparison records the original alternatives, not an open owner choice. GCTX-M09 will settle eligible instance selection and active quarantine derivation.

**How should physical CAS corruption and repair be modeled under an absolutely append-only Git Core while preserving CAS-41?** Compare:

- **A: Immutable physical-instance variants and appended diagnosis/recovery evidence** (recommended candidate): preserve the damaged instance I1, append a separately identified, locally verified replacement instance I2, and derive available byte instances and physical quarantine state from immutable facts. Do not silently mark I1 healthy or select by newest timestamp.
- **B: Verified full backup restore only:** do not perform in-place catalog repair; create a fresh validated restored catalog from a suitable backup. Consider whether correct bytes reacquired after the backup must be re-admitted and how already retained immutable facts remain intact.
- **C: External immutable repair overlay with Core-bound integrity manifest:** keep repair bytes in a distinct append-only byte store and bind them to Core. Must prove portable Core-only backup/restore, durability, no undocumented fifth authority and exact collision/quarantine safety.

For all options, distinguish *logical payload availability* from *physical-instance quarantine* and preserve the CAS-41 manifest's active **physical** quarantine accounting, which cannot be substituted by the count of historical diagnostic rows. Detailed per-instance keys, collision resolution, active-quarantine projection, atomic promotion, alternate-byte validation and crash/restore protocols are **not** accepted yet.

Other open work: final Core/Context tables/FKs, relation-group completeness evidence, append-only revision/fences and cross-authoritative transactions/backups, Exchange wire, GC-03/GC-04. ADR 0012 selects GCTX-M08 Option A; physical-instance eligibility/selection is fixed by ADR 0013 / GCTX-M09; quarantine retirement and active-count details remain open for GCTX-M10.

## 8. Permissions and implementation scope

Stack this design-only decision directly above unmerged PR #50. PRs #44 through #50 and the dependent design PR remain unmerged absent explicit user authorization. No Python, SQL/DDL, schema version, CLI, real catalog mutation, authenticated remote acquisition, deployment or release is authorized. Future implementation acceptance follows ADR 0001; examples above are required tests **not executed** by this PR.
