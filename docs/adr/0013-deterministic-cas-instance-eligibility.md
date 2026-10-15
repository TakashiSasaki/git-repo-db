# ADR 0013: Evidence-derived eligible CAS instances and deterministic byte selection

**Current post-corruption override:** [ADR 0026 / GCTX-M10](0026-stop-salvage-restore-merge-after-corruption.md) requires stopping ordinary catalog operation, preserving the suspect source read-only, serializing salvage candidates, restoring a verified backup into a fresh destination and merging only revalidated admissible data. Prior post-fault metadata service, same-DB failover, known-corrupt normal backup/restore and references to M10 as pending are historical in that scope. The owner clarification removes quarantine flags, active sets/counts and release/retirement from the new target; earlier CAS-41 count/order requirements below are historical. Ordinary sound-catalog rules and unrelated open work remain. No implementation or merge is authorized.

- **Status:** Accepted candidate-selection design in sound operation; post-corruption continuation superseded by ADR 0026 / GCTX-M10. Exact DDL and implementation pending.
- **Decision date:** 2026-10-15.
- **Decision ID:** GCTX-M09.
- **Owner selection:** Option A — derive a physical-instance eligibility set from immutable Git Core evidence, and choose a candidate for byte access by a stable, explicitly non-authoritative deterministic ordering; revalidate the bytes actually used under GCTX-M07.
- **Direct predecessor:** [ADR 0012 / GCTX-M08](0012-append-only-multiple-cas-physical-instances.md), unmerged design-only PR #53 HEAD `df0689b3a06bb1a46233737f444eb64527ec5db5`.
- **Earlier decisions:** [ADR 0003](0003-append-only-git-core-and-context-store.md) (strictly append-only Git Core + Context), [ADR 0004 / GCTX-M01](0004-metadata-only-git-core.md), [ADR 0005 / GCTX-M02](0005-common-oid-identity-with-attributed-metadata.md), [ADR 0006 / GCTX-M03](0006-field-claims-and-observation-scoped-relations.md), [ADR 0007 / GCTX-M04](0007-verification-aware-git-metadata-reads.md), [ADR 0008 / GCTX-M05](0008-domain-split-git-verification-ownership.md), [ADR 0009 / GCTX-M06](0009-bounded-byte-admission-and-physical-health.md), [ADR 0010 / GCTX-M07](0010-operation-scoped-cas-physical-integrity.md).
- **Concurrent ID reservation:** ADR 0011 belongs to sibling proposed governance PR #52 and is NOT adopted here; ADR 0012 remains the accepted GCTX-M08 design. This accepted GCTX-M09 decision uses ADR 0013.
- **Implementation baseline:** Three-Store Core Schema 21 remains implemented. This is a target-only, design-document decision.

## 1. Binding selection and trust rule

In each coherent Git Core read snapshot S, the reader MUST derive a **candidate-eligible set for the requested logical CAS payload** using immutable, instance-specific evidence. The physical instance is an application-addressable persisted byte copy, NOT a disk block, an assumed separate machine, or the logical payload identity itself.

A candidate may enter the eligible set only when all applicable conditions are met:

1. Its immutable identity identifies a real physical byte copy associated with the **requested** logical payload/representation and expected digest; it has the locally verified byte-admission/recovery evidence required by GCTX-M05/M06/M08. It cannot be merely a nominal OID, unverified third-party claim, sender-provided digest, absent byte body or incomplete staging placeholder.
2. The snapshot contains **no effective known disqualifying evidence** for that specific instance: e.g., an applicable unresolved corruption/quarantine/physical absence, unresolved identity collision or another confirmed integrity block. Evidence about I1 does not automatically disqualify sibling I2, and the availability of I2 does not erase a known I1 fault.
3. The instance is not presented as **currently healthy** simply because it passed historical admission, lacks a failure row, or passed a scan at an earlier time. Eligibility means **permitted to attempt current validation**, not **already proven currently valid**.
4. The group of immutable records and relevant blocking evidence are read coherently, without taking a mutable `active_instance_id`, last-success status, timestamp, parser version or Provider preference as authoritative.

Among eligible candidates, a stable deterministic order using immutable, catalog-local instance identity (or an equally stable non-authoritative key) determines **which candidate to try first**. This physical-access tie-break is not a canonical Git-object winner policy. No semantic priority or trusted source selection is implied, and Exchange need not reproduce the same local instance IDs or try-order on a different receiver.

The final logical payload bytes must still be the correct validated content regardless of which valid instance supplied them. A proven physical/hash collision, conflicting actual body, or ambiguous logical identity is an integrity failure requiring fail-closed diagnosis; it is NOT solved by tie-breaking between unequal alleged contents.

## 2. Selected read and failover behavior

**Current limit:** ADR 0026 supersedes the failure-to-sibling continuation below once authoritative corruption is detected. Stop ordinary service and perform read-only salvage/fresh restore/validated merge. Candidate ordering and actual-byte checks still apply in ordinary sound operation; there is no per-instance quarantine state/count/release in the new target.

For a byte-dependent operation:

1. Resolve nominal Git identity and exact requested CAS payload as necessary. Derive eligible physical instances and their evidence from a **coherent** Git Core snapshot.
2. Consider the first eligible candidate according to the stable non-authoritative ordering. Before marking a verified byte-returning operation successful, check the **same actual output bytes** against the stored CAS SHA-256 and relevant Git format/OID/type/size, and use the GCTX-M07 coherent checked-output/snapshot protocol.
3. If an instance is found to be corrupt, inconsistent, missing or otherwise unsafe at check time, **do not publish it as a successful verified result**. Preserve the required physical-instance-scoped diagnosis/quarantine fact in authoritative Git Core. Do not replace the instance body, delete or rewrite the old diagnosis, or turn it into metadata-only “not fetched”.
4. Once the disqualifying evidence has been durably accounted for and the operation has a valid refreshed/coherent view, a **different** eligible instance may be attempted and independently checked. This is failover, not mutation of a canonical pointer. If the necessary fault cannot be durably accounted for, do not silently continue and report a clean result; fail closed under the eventual precise transaction protocol.
5. If no candidate survives the required checks, report **physical byte unavailable / not currently verified** for that operation, without erasing nominal object identity, historical admission, or attributed source metadata. An actual integrity fault must remain distinguishable from deliberate never-fetched metadata-only state.

No candidate's old successfully checked result permanently certifies present health. Verification work/progress may be held in Operational, but required physical corruption evidence and durable eligibility inputs remain Core-owned and survive Operational/Search recreation and Context omission.

For pure metadata-only or historical canonical-structure reads, **do not require any physical instance** or start implicit hydration. Preserve GCTX-M01 and M04's reported-unverified, conflict, unknown and historical-canonical qualifications, and do not claim live raw-byte possession based only on old proof.

## 3. Worked counterexample: three instances, one logical payload

Suppose a payload identified by representation R and SHA-256 H has:

| Instance | Evidence at snapshot S | Candidate status under this decision |
| --- | --- | --- |
| `I1` | Previously admitted, but an applicable immutable corruption/quarantine diagnosis is recorded | **Excluded** from eligible set; fault remains independently durable |
| `I2` | Byte-verified at admission, with no known effective blocker in S | **Eligible to be checked**; historical success does not prove healthy-now |
| `I3` | Independently re-acquired and byte-verified at admission, with no known effective blocker in S | **Eligible to be checked**; no automatic source/time preference |

The reader deterministically tries an eligible copy (say I2 under an agreed immutable local key order). If I2's actual bytes now hash incorrectly, no successful verified export occurs from I2. The failure must be retained as physical-instance-specific evidence; the reader may then attempt I3 using an appropriate refreshed/coherent view. If I3 checks successfully, the logical payload may be served. Both I1 and I2 remain recorded as damaged; successful use of I3 does not retroactively repair or clear either fault.

If I3 is unavailable, the logical payload is unavailable for **currently verified bytes**, even while a source-reported commit parent or previously locally byte-derived intrinsic metadata remains queryable under the distinct metadata/historical-evidence contracts.

If correct I2 and I3 have identical expected real bytes, the deterministic try-order is a physical optimization and not an evidence ranking or arbitration of competing Git histories.

## 4. Quarantine and CAS-41: what M09 fixes and leaves for M10

**Historical scope:** GCTX-M10 is resolved by ADR 0026's immediate recovery mode, without quarantine states/counts/release/retirement. Earlier CAS-41 predicate/count/order and disposition text below is historical, not a new-format requirement. Actual database/manifest/domain/pairing validation remains. The heading is retained for existing links.

GCTX-M09 fixes that **per-instance disqualification is derived from immutable physical evidence**, never from a mutable `verified` or `preferred_instance` row or from the count of logical payloads. It also fixes that logical availability via a healthy candidate is separate from damage, known quarantine, and the **active physical quarantine count** on retained old instances.

The **exact active-quarantine predicate remains an explicit next decision (GCTX-M10)**:

- An existing `I1` fault is NEVER cleared, forgotten or made eligible merely because `I2` or `I3` supplies the correct logical bytes.
- Whether a permanently damaged and retained `I1` can be **formally retired from active isolation** without deleting its bytes/fault evidence is not settled. No automatic retirement from an alternate instance's arrival is authorized.
- At a coherent count snapshot, CAS-41's active quarantine count is about distinct **physical instance identities satisfying the eventually selected active-quarantine predicate**, NOT the number of historical fault/diagnosis events and NOT the number of unavailable logical payloads. That predicate and any formally allowed disposition states must be fixed before implementing changed backup/restore manifests.
- CAS-41's backup ordering stays: verify the archived count against the copied/verified database's count **before** introducing restore-time diagnoses, with accurate scope and identity. A different eligible instance being available is never grounds to reduce the old instance's active count without an independently accepted disposition rule.
- If the active-count predicate cannot be evaluated reliably from the copied database/manifest, restore **fails closed**; the operation must not silently default an unknown count to zero or conflate the old digest-level quarantine with the new instance-level design.

A physically corrupted instance remains durably retained under the no-Git-Core-GC rule. Different treatment of the **ongoing quarantine obligation** versus the **permanently recorded incident** may be proposed in M10, but no currently healthy fact or cryptographic correction for the broken I1 can ever be inferred merely from its disposition.

## 5. Reconciliation with every accepted boundary

| Accepted decision | GCTX-M09 effect |
| --- | --- |
| **GCTX-M01** | Core-only metadata and Git relations work with zero bytes/physical instances, no Context or hidden fetch |
| **GCTX-M02** | One common typed full OID; nominal Git identity is separate from logical CAS and physical instance identities |
| **GCTX-M03** | Attributed fields and observation-scoped relation groups are untouched; instance selection does not combine incompatible metadata |
| **GCTX-M04** | Precisely checked canonical intrinsic Git facts are preferred for ordinary reads with alternatives retained. Selecting a physical candidate does not validate arbitrary source claims |
| **GCTX-M05** | Git checks, recovery links and physical diagnoses are Core-owned; Provider-specific assessments remain Context; retry progress remains Operational |
| **GCTX-M06** | Immutable per-representation admission proof remains historic; eligibility is computed, no repeated full-scan success ledger or mutation of prior proof |
| **GCTX-M07** | Byte operations revalidate the actual chosen/emitted bytes with coherent checked output; an earlier full scan is not a guarantee at read time |
| **GCTX-M08** | I1 remains an immutable damaged physical instance; new I2/I3 copies and typed recovery evidence coexist. No repaired-in-place bytes or Core UPDATE/DELETE/REPLACE/GC |
| **ADR 0003** | Strict append-only Core and Context independence; no mutable active pointer, in-Core repair override, new fifth authoritative store or independent Publication |
| **Fixed invariants** | Permanent `repository_uuidv4`; Q01-B/Q02-B/Q03-B; unaffected PF-P01–PF-P17; Source known-positive; Coverage five-column/latest-observation semantics; Unix epoch microsecond `_us`; exact Git/CAS checks, CAS-41; no independent Publication; ADR 0001 |
| **Exchange/backup/Search** | Receiver-local bytes/instance IDs and verification authority are not imported by sender claims. Full Context-inclusive backups remain paired; Core-only backups are scope-labeled; Search remains derivative and direct Core reads respect snapshot/eligibility facts |

GCTX-M09 fixes an eligibility/selection **algorithmic contract**, not a production table, immutable per-instance key type, CAS-41 active-count predicate, fresh-check lock implementation, physical retirement policy, or data migration.

## 6. Future acceptance counterexamples (not executed)

1. Zero-byte metadata-only Core remains readable without Context or an eligible instance, and fails truthful byte-only requests without implicit fetching.
2. With I1 quarantined and I2/I3 separately admitted for one payload, eligibility includes I2 and I3 but excludes I1. No mutable preferred pointer exists.
3. Repeat identical read inputs against the same evidence snapshot: the candidate try-order is stable. It may differ on an Exchange receiver without changing canonical content.
4. Inject a newer, but known corrupt I4: it cannot win by recency, physical ID or report count. Select only from eligible evidence.
5. Corrupt I2 after an earlier successful full scan; verified export detects I2's actual mismatch and does not publish its bytes as checked success. A correctly validated I3 may be retried only after proper fault accounting.
6. Make durable fault recording fail after detection of I2 damage. The operation cannot silently present a clean result that omits the essential newly detected physical defect.
7. Ensure no cross-snapshot selection/fault/byte mismatches and no unchecked streamed partial bytes masquerading as a successful verified artifact.
8. Admission of correctly re-acquired I2 makes the logical payload potentially usable, but does not clear I1's recorded fault or automatically decrement a CAS-41 count.
9. Distinguish a previously damaged but formally retired instance (if later permitted under M10) from a healthy candidate; retirement never makes damaged bytes eligible.
10. A full audit reports the checked instance set and time/snapshot, not “all objects physically healthy forever”. Loss of Operational cannot remove required diagnoses.
11. Back up and restore with active physical quarantine counted by instance under the future M10 predicate; archive-count validation precedes restore-time diagnosis.
12. Reject mismatched CAS digest and Git OID/type/size for any candidate byte output. A claimed digest or sender-verified flag cannot bypass receiver validation.
13. Keep two copies in the same SQLite database without promising hardware-fault isolation or recovery from an unreadable database file.
14. Re-creating Search/Operational or omitting Context does not change the authoritative eligible-set evidence.
15. Ensure no generic eligibility/Publication gate, timestamp winner, mutable local Core revision, physical byte UPDATE/DELETE or unauthorized Git Core GC is introduced.

## 7. Historical GCTX-M10 alternatives, superseded by ADR 0026

**Subsequent owner decision:** ADR 0026 replaces this A/B/C question with stop/read-only salvage/fresh restore/validated merge; none of A/B/C was selected.

**When a permanently damaged physical instance remains retained, what is its relationship to “active quarantine” and the CAS-41 active physical quarantine count?**

Compare:

- **A — Perpetually active quarantine for every known-damaged retained instance.** No retirement of a damaged instance; the active count retains I1 even after alternate verified I2 restores logical payload availability. Simple and conservative but active quarantines can accumulate forever.
- **B — Explicit immutable disposition/retirement evidence (recommended candidate).** Require a narrow audited action/evidence declaring damaged I1 *permanently excluded from service*, after which the **active outstanding quarantine** projection may exclude I1 while the immutable damaged-instance history remains retained and verifiable. This is NOT an on-disk repair, eligibility restoration, incident erasure or automatically justified by I2. Precise CAS-41 count/manifest integrity must be specified before permitting this.
- **C — Automatically derived retirement from independently qualifying terminal evidence.** Predetermine an evidence predicate that retires a damaged I1 from active obligations without separate admin choice (but never solely from the presence of sibling I2); lower operator burden but risks opaque count changes and must preserve full diagnosis and no-GC constraints.

None of A/B/C is accepted by this ADR. All candidates must keep “known damaged forever” separate from “active remediation outstanding”, and define the exact counted physical-instance set in a coherent snapshot, not an event count, before changing CAS-41 behavior.

Other unresolved work: physical-instance keys/tables/DDL; exact fault and recovery fact schema; GCTX-M10 disposition/count predicate; reader locking and checked-output atomicity; metadata relation-group completeness evidence; append-only revision/fences, cross-store transaction and backup-pair consistency; Exchange format; GC-03/GC-04. The proposed ADR 0011 governance policy in sibling PR #52 remains **unadopted**.

## 8. Design-only scope and authorization

Stack this accepted owner decision on **unmerged PR #53** (GCTX-M08 / ADR 0012), which depends on PR #51 and preceding design PRs #44–#50. Independent proposed governance PR #52 is a sibling off #51, not a prerequisite. Keep all unmerged; there is no implementation, merge, release, deployment, schema/migration change or retained-catalog mutation authorization. Counterexamples are proposed future tests, not executed results.
