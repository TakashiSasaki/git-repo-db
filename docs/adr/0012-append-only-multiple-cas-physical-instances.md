# ADR 0012: Append-only physical-instance variants and Git CAS recovery

**Current post-corruption override:** [ADR 0038 / GCTX-M10](0038-scoped-recovery-and-optional-initialization.md) requires stopping ordinary catalog operation, preserving the suspect source read-only, serializing salvage candidates, restoring a verified backup into a fresh destination and merging only revalidated admissible data. Prior post-fault metadata service, same-DB failover, known-corrupt normal backup/restore and references to M10 as pending are historical in that scope. The owner clarification removes quarantine flags, active sets/counts and release/retirement from the new target; earlier CAS-41 count/order requirements below are historical. Ordinary sound-catalog rules and unrelated open work remain. No implementation or merge is authorized.

- **Status:** Accepted physical-copy identity/evidence design; post-corruption operation superseded by ADR 0026 / GCTX-M10. Detailed DDL and implementation pending.
- **Decision date:** 2026-10-15.
- **Decision ID:** GCTX-M08.
- **Owner selection:** Option A — retain immutable physical CAS instances, add independently identified verified replacement instance(s), and append narrowly scoped physical-corruption/recovery evidence. Never UPDATE or DELETE admitted Git Core facts or bytes.
- **Number allocation:** ADR 0011 is reserved by the independent proposed ADR governance PR #52 (a sibling design branch); this accepted GCTX-M08 decision uses ADR 0012 to avoid collision. PR #52's proposed policy is not adopted by this decision.
- **Direct predecessor:** [ADR 0010 / GCTX-M07](0010-operation-scoped-cas-physical-integrity.md), unmerged design PR #51, HEAD `a79924f36ddb03c2f5472f14f0233531bd7788a2`.
- **Earlier decisions:** [ADR 0003](https://github.com/TakashiSasaki/git-repo-db/blob/bb878eda47cf17268dd821c74343bac64d769ea7/docs/adr/0003-append-only-git-core-and-context-store.md), [ADR 0004 / GCTX-M01](0004-metadata-only-git-core.md), [ADR 0005 / GCTX-M02](0005-common-oid-identity-with-attributed-metadata.md), [ADR 0006 / GCTX-M03](0006-field-claims-and-observation-scoped-relations.md), [ADR 0007 / GCTX-M04](0007-verification-aware-git-metadata-reads.md), [ADR 0008 / GCTX-M05](0008-domain-split-git-verification-ownership.md), [ADR 0009 / GCTX-M06](0009-bounded-byte-admission-and-physical-health.md).
- **Implementation baseline:** Current Three-Store Core Schema 21 still uses one `stored_bytes` row per SHA-256 and a digest-keyed quarantine/repair path. This ADR is target design only; its physical-instance model is NOT implemented.

## 1. Binding identity boundary

Three separate identity levels MUST remain distinguishable:

1. **Git object nominal identity** `(object_format, oid)`: one common, repository-independent full OID, with optional unverified, attributed metadata (GCTX-M01/M02).
2. **Logical CAS payload identity** `(representation, sha256)`, as applicable: the expected content/representation, independent of its number of stored copies. Identical logical content may be shared by multiple Git references and acquisitions, but its existence is not proof that any original bytes are physically available.
3. **Physical instance identity** (exact key scheme deliberately open): one individually addressable **persisted copy of bytes**, with its own immutable identity and actual storage body or strictly bound immutable physical locator. Different physical instances `I1` and `I2` MAY share a logical payload digest `H` while remaining independently diagnosable, quarantinable and byte-checkable.

A physical instance is an **application-addressable storage entity**, such as a future distinct SQLite BLOB row, **not** a disk sector, SQLite page, host, network replica or proof of hardware fault-domain independence. Separate instances inside one SQLite DB do not by themselves provide storage-device redundancy. GCTX-M08 selects the logical physical-copy model, not a mandatory disk/file layout or extra authoritative store.

This explicitly supersedes the old target-shape assumption that `stored_bytes(sha256 PRIMARY KEY, body)` is sufficient to distinguish all independently retained byte instances, and that `payload_quarantine(sha256 PRIMARY KEY)` can directly encode all per-instance physical faults. Their exact replacement tables/keys/triggers remain pending. [ADR 0017 / KEY-P01](0017-domain-keys-without-storage-surrogates.md) now disallows storage-only surrogate PKs, while preserving the genuine independent physical-instance identities required here; the format and origin of those identities still need domain justification. No backward-compatibility schema retention is required before release.

## 2. Immutable physical diagnosis and recovery

**Scoped successor:** ADR 0026 replaces the post-corruption in-service I1/I2 recovery path below with stop/read-only salvage/fresh restore/validated merge. Copy identity distinctions remain, without a per-copy quarantine state/count/release lifecycle. Never append a replacement into the stopped source or require damaged I1 in the new operational database.

For each actual retained-byte instance:

- After detecting a real physical mismatch, append **instance-specific, durable diagnosis/quarantine evidence** sufficient to distinguish damaged bytes `I1` from all other instances of the same logical payload. The physically corrupted original may have been changed by a fault outside the application's control; the application MUST NOT update, delete, restore-in-place, GC or erase the old instance or its diagnosis.
- Reacquired candidate bytes for the **same expected logical content** MUST receive a **new physical instance identity** `I2`. Validate the actual bytes against the expected CAS SHA-256 and, whenever claiming a verified Git original, the corresponding Git format/type/size/OID and intrinsic structure under GCTX-M05/M06. A mere Provider claim, old success scan, matching expected digest string or sender's verified marker is insufficient.
- Publish an **immutable, narrowly typed association/recovery fact** between the expected payload and independently verified candidate instance(s), with provenance of actual acquisition/recovery and the required evidence. This is not a generic `repair succeeded` ledger for all domains; it is not a replacement for original verified object admission.
- A correction or recovery MUST NOT mutate the originally admitted per-representation proof, replace old physical bytes under the same `physical_instance_id`, delete diagnosis, mark damaged `I1` healthy because `I2` is healthy, or silently select an instance by insertion order or latest timestamp.
- The **logical payload** may regain usable byte availability through a valid candidate even though an older physical instance remains damaged or quarantined. Conversely, a healthy-looking logical payload does not prove every stored physical instance is healthy.
- Diagnoses and optional recovery facts are immutable; their **current/effective projection**, including any active physical quarantine and candidate eligibility, is a derived view over relevant admitted evidence. The physical candidate eligibility and deterministic selection contract is now fixed by [ADR 0013 / GCTX-M09](0013-deterministic-cas-instance-eligibility.md). Isolation/retirement event types, simultaneous-fault disposition and exact active-quarantine predicate remain reserved for **GCTX-M10**.

**Atomicity requirement:** A verified alternate instance and its durable logical association must not become *available for verified reads* until all required bytes and checks are committed consistently. If bodies live outside SQLite, a staged immutable publication/fence protocol must prevent partially published or orphaned physical instances from being accepted; this ADR does NOT authorize an external fifth authoritative store. Crash/retry cases must be fail-closed and idempotent.

The existing implementation's `repair_payload()` path temporarily drops an immutable trigger, UPDATEs `stored_bytes.body`, DELETEs `payload_quarantine` and increments the mutable Core revision. That mechanism directly conflicts with ADR 0003 and MUST be replaced, not exempted from append-only restrictions.

## 3. Detailed adversarial example

| Step | Evidence | Required state |
| --- | --- | --- |
| T1 | Blob `B` has expected CAS SHA-256 `H`, Git OID `O` and admitted body copy `I1` | A bounded historical byte-admission proof refers to the checked actual content; `I1` is an independently identified physical instance |
| T2 | External damage changes actual bytes in `I1` so `SHA256(I1.body) != H` | Append instance-scoped fault/quarantine diagnosis. Keep historical `I1` and its distinct identity; trusted raw output using `I1` fails |
| T3 | Correct original bytes are independently reacquired, validated against `H` and Git OID `O`, and stored as `I2` | Add an immutable `I2` with verified association/evidence; do not rewrite or replace `I1` and do not erase the T2 event |
| T4 | Caller requests `B`'s historical Git metadata | Core may use historical admission evidence and source-attributed metadata with truthful current-byte qualification, no Context or mandatory rehash |
| T5 | Caller requests a *currently verified* raw export of `B` | A candidate may be used only if eligible under the evidence-derived GCTX-M09 projection in ADR 0013 and the **actual emitted bytes** pass GCTX-M07's operation-scope checks |
| T6 | Audit and backup are requested | Report each applicable physical instance, its known diagnoses and the current scoped physical quarantine count; distinguish logical `B` availability from damaged `I1` |

Thus, **logical restoration** through `I2` is not equivalent to **physical repair of I1**. If both copies live in the same SQLite database, low-level database-file/page failure may still make the entire Core unreadable; in that exceptional case external verified-backup restoration remains an independently necessary recovery path. The choice of A does not guarantee self-healing from an unreadable database.

## 4. CAS-41 preservation and backup/restore obligations

**Current scoped successor:** ADR 0026 removes the quarantine state, active predicate/count and pre-diagnosis count comparison from the new target format. Preserve actual database/manifest/domain/pairing validation, and keep known-corrupt artifacts as forensic/salvage evidence. The CAS-41 count/order text below is historical; no continuation or retirement option can bypass immediate recovery mode.

**CAS-41 remains binding.** Before restore-time diagnosis changes any effective diagnosis state, verify the archived **active physical quarantine count** against the count in the *copied and verified source database*, under a coherent matching scope. The accumulated number of immutable fault events is NOT that active count.

GCTX-M08 makes physical-instance scope explicit; it does **not yet fix** whether/how a physically damaged original may ever be formally retired from an active quarantine projection when a healthy alternative is available. ADR 0013 / GCTX-M09 fixes evidence-derived candidate eligibility and deterministic selection; the separate **GCTX-M10** decision must define active quarantine/retirement and exact CAS-41 instance-count rules. Specifically:

- Newly validated `I2` cannot itself delete, erase or implicitly resolve a fault on `I1`. Unless an explicitly defined disposition of `I1` applies, `I1`'s physical fault remains represented as a fault of that retained instance.
- A payload can be logically usable via `I2` while active fault accounting may still include `I1`. Backups/restores and diagnostics must convey both truths and must not reduce the active **physical** quarantine count merely because logical byte availability was recovered.
- Backup formats and restore admission must preserve the immutable physical-instance identities, body integrity evidence, known corrupt instances and repaired candidates as an appropriately consistent set, or truthfully reject unsupported scopes. A copied catalog containing a quarantined byte copy is not thereby a sound verified copy of all its bytes. The detailed restore policy (including how corruption affected copies are represented safely) remains open.
- Receiver-side Exchange must validate any byte-backed candidate independently; it cannot import sender-local `I1/I2` IDs as globally portable identities, nor downgrade a real corruption to intentionally missing metadata.
- Git Core continues to retain all previously admitted Git bytes/facts under the no-GC policy. This carries storage-growth costs, including potential irrecoverably damaged historical copies; GCTX-M08 does not introduce physical deletion or retention exceptions.

**Collision boundary:** Two different byte sequences claiming the same expected digest or Git OID require strict collision/identity handling and must not become two interchangeable healthy alternatives. An unexpected mismatch is a physical corruption, conflicting content, or input error to be diagnosed under actual evidence; it is not resolved by choosing the newest row.

## 5. Reconciliation with accepted decisions

| Accepted decision | GCTX-M08 preservation |
| --- | --- |
| **GCTX-M01** | Fully metadata-only Core remains valid without physical instances or Context. No fake CAS rows and no implicit fetch |
| **GCTX-M02** | Shared full `(object_format,oid)` identity independent from payload and physical instance identity |
| **GCTX-M03** | Source-attributed scalar claims and observation-scoped typed parent/tree groups remain separate; alternate byte instances do not silently merge inconsistent claims |
| **GCTX-M04** | Specifically receiver-validated intrinsic values may be canonical; reported conflicts remain queryable. Historical byte-backed evidence is distinct from current physical health |
| **GCTX-M05** | Git checks, immutable diagnosis and required recovery evidence remain Core-owned; Context owns Provider assessments; Operational owns Jobs |
| **GCTX-M06** | Historical per-representation admission proof remains bounded and immutable; `I2` is a new physical instance, not a rewrite of `I1` or a new proof for every rescan |
| **GCTX-M07** | Verified raw export must validate the actual eligible instance's emitted bytes under a coherent scope; audits are as-of, not eternal health |
| **ADR 0003** | Application-level Git Core INSERT-only; no UPDATE, DELETE, REPLACE, mutable selection/repair, exceptional trigger bypass, physical byte reclamation or GC |
| **CAS/CAS-41** | Exact raw Git OID/type/size checks, CAS SHA-256 and collision safeguards; archive active physical quarantine count is checked against verified copy before restore diagnosis |
| **Other fixed contracts** | Repository UUIDv4 permanence, typed provenance, Source known-positive, existing Coverage 5-column/newest-observation semantics, Unix epoch `_us`, NO_INDEPENDENT_PUBLICATION, independent Git-only backups and Context-inclusive paired backups, ADR 0001 |

This does not fix an automatic canonical physical **winner**, ref-current policy, parser/decoder winner, generic Publication, Provider historic edit log, or status UPDATE. A derived eligible instance is a physical read candidate, not an arbitrary preferred Git truth.

## 6. Future implementation counterexamples (not executed)

1. A nominal OID and source-attributed object/tree/commit metadata are usable with zero physical instances, no Context and no verifier Jobs.
2. One valid logical payload digest `H` admits distinct physical instances `I1` and `I2` with the same correct content; distinct IDs cannot be deduplicated away merely by a unique `sha256` constraint.
3. Introduce real corruption in `I1` after historical admission, retain an immutable instance-scoped diagnosis and reject verified raw export from that copy. Do not UPDATE/DELETE `I1` or its fault facts.
4. Independently acquire correct bytes as `I2` and check CAS digest plus declared Git OID/type/size. New candidate admission succeeds without repairing the old row or declaring old `I1` healthy.
5. Inject an invalid `I2` candidate and a claimed matching digest: reject promotion, quarantine/diagnose actual bad input as appropriate, and preserve no false verified-byte success.
6. Crash between byte staging and logical recovery association: no partial or uncommitted instance is eligible for verified output. Retry is idempotent, and old Core evidence remains readable.
7. Two valid alternatives `I2` and `I3` coexist; ADR 0013 / GCTX-M09 permits stable physical-ID-based try-order **only among evidence-eligible candidates**, never an authoritative semantic winner or newest-first selection. Raw export always rechecks actual chosen bytes under GCTX-M07.
8. Logical payload availability via `I2` can coexist with `I1`'s recorded physical damage. CAS-41 active physical quarantine manifest/count must not silently change to zero just because logical availability is restored.
9. Full/Core-only metadata backup and paired Core+Context backup preserve truthful scopes and required fault/physical instance evidence; restore must reject invented current health, inconsistent counts and fabricated raw-byte completeness.
10. A database file/page is actually unreadable despite multiple BLOB rows; do not promise recovery through intra-DB alternatives. A verified backup/external reacquisition path may be needed, with the same append-only truth requirements for any restored catalog.
11. Recreate Operational/Search or omit Context, and verify immutable Git physical diagnoses and historical admission remain Core-owned without provider dependencies.
12. Sender Exchange payloads and alleged verification/instance identifiers are not automatically trusted. Receiver validates independently and assigns its own per-instance IDs.
13. Assert no repair implementation drops integrity triggers, UPDATEs old bytes, DELETEs quarantine, mutates local Core revision, or introduces a generic success-event ledger.
14. Test unexpected digest/OID collision or conflicting same-digest data; do not silently select, overwrite or certify either under a false identity.
15. Confirm all physical instances remain retained with no new Git Core GC authorization; quantify growth/capacity effects as part of later implementation planning.

## 7. Subsequent owner decision: GCTX-M09 accepted; next GCTX-M10

[ADR 0013 / GCTX-M09](0013-deterministic-cas-instance-eligibility.md) adopts Option A. Eligibility is a Core-snapshot-derived set of locally admitted physical instances without known effective blocks, not a claim of current health. Selection is by stable, non-authoritative physical identity order; validated byte use and failover follow GCTX-M07, and diagnosed faults remain immutable. The following A/B/C alternatives document the original question, not a still-open selection.

**How should current physical-instance eligibility, candidate selection and active quarantine state be *derived* without mutable Core pointers or inaccurate CAS-41 counts?**

Compare:
- **A: Deterministic evidence-based eligible-set projection (recommended candidate).** Derive each instance's known fault/eligibility status from immutable instance-scoped diagnostics and recovery evidence, then choose among fully validated, eligible instances by a stable non-authoritative tie-break (e.g., physical instance ID) for byte access. Recheck the actual emitted bytes per GCTX-M07; never conflate one damaged instance with logical payload unavailability.
- **B: Append-only explicit activation/retirement decisions.** Record narrowly typed immutable, causally linked selection/activation facts and derive an effective chosen instance, without UPDATE. Avoid time-as-truth or an unapproved generic revision log; manage forks/conflicting activations.
- **C: Caller-selected explicit physical instance.** Require explicit instance selection or manual intervention for any payload with multiple copies, even if an alternative passes validation. Avoid an automatic winner at the cost of ergonomics and restored logical availability.

Any option must keep instance-scoped corruption, actual active **physical** quarantine accounting and its CAS-41 backup comparison distinct from derived logical-payload availability. ADR 0013 fixes GCTX-M09 Option A. The exact retirement/active-quarantine count predicate is deliberately **GCTX-M10**, not settled by choosing a healthy alternate instance.

Other open decisions: physical instance IDs/tables/keys and on-disk layout; GCTX-M10 rules for whether a corrupted instance may be retired from active isolation without mutation or GC; exact repair atomicity/revision/fence and backup/restore; typed Git complete-list evidence; Core–Context consistency; Exchange wire; GC-03/GC-04.

## 8. Design-only scope and explicit permissions

This accepted decision is to be fixed as a design-only stacked PR directly above unmerged PR #51. Do not merge it or any predecessor #44–#51 without explicit user authorization. This ADR makes **no** production Python/DDL/SQL, migration, schema-version, CLI, real-catalog, deployment, release or authenticated acquisition changes. Future counterexamples are acceptance requirements, not executed test evidence.
