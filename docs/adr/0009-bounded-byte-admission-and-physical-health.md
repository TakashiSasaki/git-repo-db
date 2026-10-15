# ADR 0009: Bounded immutable verified-byte admission and independent physical health

- **Status:** Accepted owner design decision; concrete DDL and runtime implementation pending.
- **Decision date:** 2026-10-14.
- **Decision ID:** GCTX-M06.
- **Owner selection:** Option B — bounded immutable evidence for each accepted byte-verified Git representation, distinct from current physical byte health.
- **Depends on:** [ADR 0003](0003-append-only-git-core-and-context-store.md) (four-store append-only boundary), [ADR 0004 / GCTX-M01](0004-metadata-only-git-core.md) (metadata-only requirement), [ADR 0005 / GCTX-M02](0005-common-oid-identity-with-attributed-metadata.md) (nominal OID), [ADR 0006 / GCTX-M03](0006-field-claims-and-observation-scoped-relations.md) (claims/relation groups), [ADR 0007 / GCTX-M04](0007-verification-aware-git-metadata-reads.md) (read policy), and [ADR 0008 / GCTX-M05](0008-domain-split-git-verification-ownership.md) (verifier responsibility).
- **Design baseline:** Unmerged PR #49 HEAD `607c91e4a1254c57ca8e22733541c2e4a6ebce2c`, stacked on PRs #48 → #47 → #46 → #45 → #44.
- **Current implementation:** The old Three-Store Core Schema 21 remains the implemented baseline. This ADR does not alter it.

## 1. Binding decision: the accepted representation is the historical proof

A nominal full `(object_format,oid)` identifies the subject of Git metadata reports without requiring any original bytes. This is unchanged by GCTX-M06. A byte-verified representation is **optional**, and can be admitted only after the receiver has actually obtained the original raw body.

For an optional byte-backed representation, Git Core's admission contract requires:

1. Validate the **actual** Git object body with the declared format, exact OID, object type and size. Compute the appropriate Git SHA-1/SHA-256 over the canonical `type size\0` header followed by the exact raw body. Compare any required retained-byte SHA-256/CAS digest against the physical bytes; never trust a provided digest by declaration alone.
2. Validate and atomically install the canonical object's intrinsic structure (commit/tree/tag or blob). Parent/child OIDs need not themselves have locally retained bytes; do not fabricate referenced objects or claim whole-DAG closure.
3. Commit a **bounded, immutable representation/identity/physical-payload association** and the checked intrinsic structure as one consistent acceptance unit. Failed or interrupted admission cannot publish a partially verified canonical object or structure.
4. An identical re-ingestion is idempotent and does not add a new durable success event for each check/retry. A conflicting byte-backed representation for the same alleged identity must trigger existing exact-identity/collision diagnostics and rejection/staging rules, never silent winner selection. An earlier inaccurate *unverified metadata report* must not block independently correct bytes.
5. The accepted, checked and committed representation plus its precise bytes/identity/structure relation constitutes the **historical local byte-verification evidence**. A separate per-attempt `verification_success` history, an UPDATE to `git_objects.verified`, a generic certificate/Publication ledger or a mutable preferred-result pointer is not required or authorized by this decision.

Here **per representation** concerns one accepted canonical byte-backed domain fact, **not** a prohibition on multiple physical storage instances after a future append-only-safe repair. The physical representation/instance-key schema, exact FK structure and any narrowly necessary evidence attributes remain unselected. Nor may an unguarded direct SQL insertion be accepted as cryptographic proof: the eventual trusted admission API/DDL must enforce the above checks.

## 2. Distinct guarantees and their interpretations

| Subject / property | What the Core may truthfully assert |
| --- | --- |
| Nominal OID plus source-attributed metadata | Only that an identified source/capture reported values about a full typed OID. No original bytes, true type, size or object existence are proved |
| Historical locally verified admission | At a prior admission, **actual** bytes matched the declared Git format/OID/type/size and the accepted intrinsic structure. This remains historical truth if storage later fails |
| Historical byte-derived metadata | The specifically checked intrinsic field or group can be presented as previously canonical, without promoting unrelated source claims or imposing a global decoder winner |
| Present physical byte availability | The needed physical byte instance is present and satisfies **the operation's explicit current-integrity checks and snapshot/fence contract**; prior admission alone is insufficient |
| Retained-byte corruption/quarantine | A real physical defect and its durable diagnosis, distinct both from historical admission success and intentional nonacquisition |
| Complete acquisition/graph/Coverage | Must have its own domain/scope evidence. Neither accepted object bytes nor their OID proves all descendants/reachable objects were retrieved |

The implications are intentionally one-way:

- `nominal_oid_known(C)` does not imply `historically_admitted(C)`.
- `historically_admitted(C)` does not imply `currently_healthy(C)`.
- `verified_parent(C,P)` does not imply `bytes_present(P)` or complete closure.
- `historically_admitted(C)` does not turn every previously reported field/parent/entry concerning `C` into a verified claim.
- An older scan reporting `OK` does not by itself prove **now**; health can be `unknown` or `as_of_snapshot`. [ADR 0010 / GCTX-M07](0010-operation-scoped-cas-physical-integrity.md) now fixes operation-scoped assurance tiers while the precise snapshot/locking implementation remains open.

In particular, **metadata-only queries do not require original bytes or a full rehash**. Historical validated intrinsic metadata may remain useful even if its original bytes are presently inaccessible, as long as its historical/admission provenance and current byte availability are truthfully distinguished under the GCTX-M04 read contract. No current raw export or successful byte-verified checkout may be inferred solely from a historical admission fact.

## 3. Verification attempts and physical integrity lifecycle

- A successful periodic integrity scan or successful on-demand recheck is **not automatically a new permanent successful-verification fact**. Job progress and retry state belong to Operational, but indispensably durable admission facts and actual corruption diagnosis must remain Core-owned.
- Accepted Git original bytes are not garbage-collected. A physical defect must not be hidden by recoding it as `metadata-only`. A metadata-only catalog that never acquired bytes is not corrupt merely for that reason.
- Preserve **CAS-41** precisely: during restore, verify the backed-up **active physical quarantine count** against the copied, verified database before any restore-time diagnosis. Do not use the number of cumulative immutable diagnostic events as a replacement for active quarantine count.
- Restoring availability after physical corruption cannot UPDATE old raw bytes, DELETE quarantine/diagnoses or temporarily disable Core immutability as an exceptional repair. An append-only physical-instance/recovery design must preserve earlier evidence; exact mechanics are **not decided**.
- Exchange cannot promote a sender's `verified` marker or receiver-unverified alleged proof into receiver-local byte-admission authority. The receiver must perform its own exact checks before admitting byte-backed data. Metadata-only Exchange requires no invented CAS payload or proof.
- A successful integrity scan can be reported with its observed scope/time/snapshot, but the specification does not yet choose whether or how its successful result is kept persistently. A universal success ledger or blanket eligibility/Publication owner is not authorized.

## 4. Worked example

| Step | Actual input | Required interpretation |
| --- | --- | --- |
| T1 | Source S1 reports `parent(C)=Q` without raw bytes | Common nominal C and a source-attributed unverified parent group are admitted; no CAS, proof or fake object |
| T2 | Actual commit bytes for `C` arrive, locally hash to C and contain parent `P` | Atomically retain verified representation and intrinsic parent P. S1's contradictory Q remains an immutable historical report |
| T3 | An explicit full-CAS scan succeeds | Scan can report `OK at T3 for its checked snapshot`. No additional per-attempt permanent success entry is mandatory |
| T4 | A storage error corrupts the previously admitted physical bytes | T2 acceptance remains true historically; current physical-byte integrity cannot be claimed from T2/T3 alone |
| T5 | Correct bytes are reacquired | Later append-only-safe restoration will require additional physical/evidence facts; must not rewrite T2 bytes or erase T4 diagnosis |

At T4, a Core-only metadata query may still show P as historical byte-derived canonical structure, qualified by the separate physical availability status. It must not mislabel the currently corrupt bytes as healthy. That operation-scoped assurance policy is fixed by ADR 0010 / GCTX-M07; exact reader snapshots and recovery are still open.

## 5. Reconciliation with all prior constraints

| Prior decision | Consequence |
| --- | --- |
| GCTX-M01 | Metadata-only Core remains fully useful without original bytes/Context/verification Jobs |
| GCTX-M02 | One nominal typed full OID identity; reported type/size cannot poison later correct byte admission |
| GCTX-M03 | Individually attributed fields and typed observation-scoped ordered relations remain immutable; no union of incompatible groups |
| GCTX-M04 | Precisely checked intrinsic bytes may justify canonical values; conflicting reported alternatives remain accessible, with separate live health qualification |
| GCTX-M05 | Byte verification, durable accepted byte evidence and Git integrity diagnostics belong to Core; Provider assessment to Context; Jobs to Operational |
| ADR 0003 | No Core UPDATE, DELETE, REPLACE, in-place CAS repair or Core GC. Bounded immutable representation acceptance is not a new universal publication gate |
| Existing invariants | Preserve `repository_uuidv4` permanence, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, Source known-positive, five-column latest-observation Coverage, Unix epoch `_us`, exact Git OIDs, CAS/collision handling, CAS-41, NO_INDEPENDENT_PUBLICATION and ADR 0001 |
| Backup/Exchange | Git-only metadata backup remains usable without Context; full backup requires consistent Core+Context pairing. Actual retained bytes and necessary physical diagnoses are not disposable or silently absent; sender verification never imports as receiver authority |

## 6. Future acceptance counterexamples (NOT executed by this design PR)

1. Register metadata-only OID/fields/relations without raw bytes or Context; do not synthesize digest, proof, child object or closure.
2. Attempt byte-backed admission with wrong declared type/size/OID, malformed intrinsic structure or mismatching physical CAS digest; reject atomically, exposing no partly verified data.
3. After an incorrect source report, admit correct matching raw bytes without updating or rejecting the earlier report.
4. Repeat correct admission, successful rehash and periodic scan: no uncontrolled append-only success-attempt growth. Retry is idempotent.
5. With byte-backed C admitted, parent P referenced but not fetched: the C→P intrinsic relation may be canonical while full closure remains false/unknown.
6. Corrupt bytes after successful admission and earlier successful scan: preserve historical admission evidence but fail closed for operations asserting current byte integrity unless their checks actually pass.
7. Preserve durable physical corruption evidence and CAS-41 active-quarantine restore ordering, including historical records that remain after future append-only-safe repair.
8. Intentionally omit raw bytes for a valid metadata-only catalog and confirm no false physical-corruption alarm.
9. Receive a sender-verified raw Git representation through Exchange; revalidate locally before establishing local byte-backed authority. Reverse/repeated metadata-only exchange remains valid.
10. Remove/recreate Operational and Search, omit Context, and restore Git-only metadata: required Core facts remain independently queryable.
11. Back up and restore an admitted raw object with a known quarantined physical instance: do not claim healthy/complete by relying on historical admission alone.
12. Confirm no generic Publication/seal, winning decoder, mutable verified flag or unconditional scan success-history table is introduced.

## 7. Subsequent owner decision: GCTX-M07 accepted; next GCTX-M08

[ADR 0010 / GCTX-M07](0010-operation-scoped-cas-physical-integrity.md) selects Option B: explicit operation-specific integrity assurance. Historical metadata/verified structure does not mandate rehash; operations claiming current verified bytes must check the actual emitted bytes in a coherent scope; audits are as-of. The following A/B/C choices document the original question rather than an unresolved owner decision.

**What current physical-integrity assurance level should each read/operation require, and what freshness/snapshot language is truthful?**

Compare **A: rehash on every byte-backed use**, **B: operation-specific assurance tiers (metadata views may use historical proof; actual byte export or `currently verified` claims require matching current checks; explicit scoped/full audit separately)**, and **C: periodic full scans with as-of health snapshots/cached status**. Distinguish performance, stale scan risk, byte output correctness, known quarantine, read consistency and lock/scan time. ADR 0010 selects B. Neither historical admission nor old `scan OK` may masquerade as current physical health; GCTX-M08 physical repair is still open.

Still unresolved: final nominal/claim/group and representation tables/FKs/DDL, source evidence and complete-list proof, physical CAS instance keys and GCTX-M09 active quarantine/selection under ADR 0011's immutable alternate-instance recovery, precise health scan/read fences, cross-store transaction/backup matching, local revision/fence, Exchange wire, GC-03/GC-04.

## 8. Scope, permissions and implementation status

Stack this design-only decision directly on unmerged PR #49. Do not merge any of #44 through #49 or this dependent PR without explicit owner approval. No production SQL/DDL, Python, CLI, migration, actual catalog mutation, release or deployment is authorized. The acceptance counterexamples above are future implementation requirements, **not executed tests**.
