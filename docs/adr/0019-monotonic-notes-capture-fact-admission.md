---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0018-notes-capture-uuidv4-composite-identity.md
  - 0016-immutable-notes-ref-capture-observations.md
  - 0006-field-claims-and-observation-scoped-relations.md
---

# ADR 0019: Monotonic, idempotent notes-capture fact admission

**Current refinement:** [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md) accepts direct semantic composite claim/group keys using the actual Capture UUIDv4 pair, typed slot, asserted value and genuine provenance, without surrogates. B02-R01 structural role-evidence strength is fixed by [ADR 0022](0022-receiver-verified-notes-role-admission.md); B02-R02 configurable finite budget policy is fixed by [ADR 0023](0023-configurable-finite-notes-resource-budgets.md); B02-R03 actual-work accounting is fixed by [ADR 0024](0024-actual-notes-resource-work-accounting.md); [ADR 0025 / B02-R04 A](0025-cumulative-request-budgets-and-scoped-blockers.md) fixes cumulative work within one explicit acquisition request across continuation/resume/retry. Counter units, defaults and resume mechanics are agent-owned engineering work, not further owner blockers. Other proof/completeness/trust/DDL work remains separately scoped; GCTX-M10 blocks the affected disposition/count/backup-manifest contract. Earlier alternatives below retain their historical scope.

- **Decision ID:** B01-R04.
- **Owner choice:** **Option A** — admit new compatible immutable notes-member/observation evidence under the **same genuine capture**, treat exact repeats as idempotent, and never mutate previously accepted facts. Contradictory facts must not silently overwrite, be chosen by arrival order, or acquire unearned verification; their immutable attributed alternative preservation is fixed by [ADR 0020 / B01-R05](0020-immutable-competing-notes-member-claims.md); direct semantic keys are fixed by [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md).
- **Accepted date:** 2026-10-15.
- **Stacking base:** Unmerged [PR #59 / ADR 0018 / B01-R03](https://github.com/TakashiSasaki/git-repo-db/pull/59), HEAD `799f1052ece4b02d0ed2d8ace70c2deddc6ddcbf`. Inherited design: ADRs 0014–0018 / KEY-P01, GCTX-M01–M09, and ADR 0003 strictly append-only Git Core. Sibling [PR #52](https://github.com/TakashiSasaki/git-repo-db/pull/52) / proposed ADR 0011 governance remains unaccepted and is not a prerequisite.
- **Implementation baseline:** Three-Store Catalog3 Core Schema 21, Operational 1, Search 1. No production schema, application code, migrations, tests, real catalog or GitHub merge is changed by this ADR.

## 1. Binding monotonic admission contract

**Within one admitted immutable notes-ref Capture identity** `(capture_origin_uuidv4,capture_uuidv4)`:

1. **Accept genuinely new, compatible typed member/evidence facts** using the original capture key, actual ref/root observation scope, source attribution and supported typed note-target/notes-blob/path evidence. New data may arrive in later transactions, in any order, via local acquisition or Exchange, without changing the capture key or retroactively rewriting earlier facts.
2. **Make replay of the identical accepted fact idempotent.** Equality is about the **same capture-scoped typed assertion with its actual provenance and meaning**, not merely matching text, Git object OID, ref root or a digest of concatenated received messages. Do not add another authoritative fact or fabricated independent capture solely for retry, exchange loop, re-import or rearranged transport.
3. **Retain prior accepted facts unchanged** under strict application-level Git Core `INSERT`-only. No `UPDATE`, `DELETE`, `REPLACE`, upsert-mutating a fact, late FK backfill, mutable `complete` flag, per-scan success ledger, generic Publication, local row surrogate or implicit ref-current pointer.
4. **Do not treat contradictory input as a compatible extension.** At minimum, an existing immutable capture identity associated with repository/ref/root/source evidence cannot be silently rebound. Overlapping same-slot notes assertions with different values require a truthful non-success/qualified conflict decision and must not result in a falsely verified or complete notes view. ADR 0020 / B01-R05 now accepts genuinely attributable competing *member reports* as separate immutable alternatives with a derived conflict, never as compatible additions to an old coherent group. Direct semantic claim/group identity is fixed by ADR 0021 / B01-R06 A. Capture issuer spoofing/UUID replay with incompatible identity is an identity/provenance failure, not evidence that two captures are automatically one.
5. **Do not infer completeness from accumulation.** A growing collection of successfully accepted partial members is not automatically a complete mapping for the notes ref, notes root, annotated target, or remote inventory. B03 controls exact complete/partial/known-empty/unknown claims and any accepted closure evidence.

This is a **fact-admission policy under an already fixed capture**, not a mandate that every member has its own random UUID, not a normalized all-scan history and not a general-purpose event-store/Publication layer.

## 2. Preserve GCTX-M03 atomic group boundaries

ADR 0006 / GCTX-M03 fixes **typed observation-scoped ordered relation groups**. It explicitly requires **each coherent relation group and its members to become visible atomically as one admissible unit**, with later partial fragments/corrections represented as **new immutable groups**, not by extending or mutating the old group.

B01-R04 Option A applies to the **capture as an umbrella identity**, not to arbitrary mutation or implicit union of an already accepted group.

- For a later compatible partial message, append appropriately scoped **new immutable field/member facts or a new coherent typed relation group** referencing the **same** capture pair. A group containing multiple interdependent members becomes visible as a single transactionally consistent unit.
- **Never** append a member into a previously frozen group and reinterpret that group as if it had originally contained the member. Preserve the original reported group scope, including partial fragment, known-empty, order and provenance.
- The capture can own multiple groups/evidence units. A read may expose their **separate** facts with source/scope qualifications, but MUST NOT silently union them into one authoritatively complete notes mapping, infer missing ordinals, pick a latest decoder/source or back-date verification.
- Where an incremental message expressly references an **already known group**, its precise well-formed continuation/provenance must be assessed. If the group was atomically accepted as complete or its immutable member set is otherwise fixed, a purported extra member cannot mutate it. ADR 0021 / B01-R06 A fixes direct semantic group identity/equality; concrete fragment grammar, completeness proof and physical schema remain B03/schema work under KEY-P01, not permission to add storage-only IDs.
- Intrinsic facts proven by verified raw note/tree/commit bytes and independent receiver checks are **field/group-specific**; their presence does not upgrade unverified conflicting reports, later-received unrelated groups or logical closure.

Thus, **same capture** does not imply **same immutable relation group**, and **multiple partial groups under one capture** do not imply **one complete snapshot**. This reconciliation is essential to preserve GCTX-M03 as accepted, not silently supersede it.

## 3. Source identity, content and replay constraints

**Capture key stays exact:** `(capture_origin_uuidv4,capture_uuidv4)` from ADR 0018; each component is UUIDv4. The receiver directly uses that domain composite as PK/FK without a local integer/UUID surrogate (ADR 0017). A different genuine observation of identical root A must have a **fresh** capture UUIDv4; replay does not.

**Provenance matters:** The producer/source and the original observation scope belong to the immutable admitted evidence. Replayed packets from another transfer route retain the original capture identity; they are not new independently observed source facts. Two truly independent source reports are not implicitly identical just because values and raw SHA-256 match. Reuse of a capture key is only an idempotent assertion **when its identity, actual origin and meaningful facts are consistent**; an adversary's untrusted sender label cannot establish authenticity or verification.

**No value-based winner:** Two messages reporting `C1→N1` and `C1→N9` under the **same capture and same claimed logical relation slot** are not two versions of a mutable field and not a valid append-as-if-both-true canonical mapping. Their conflict must be recognized, and the previously accepted fact preserved. A note about the same target in a **different notes namespace** or in a genuinely different capture is a separately scoped observation, not automatically a within-capture conflict.

**No implicit typed note-body admission:** `refs/notes/*` discovery or a stable capture UUID does not prove a raw `blob` is note content. The retained note body exception requires purpose/evidence and exact Git/CAS byte validation under ADR 0014 and GCTX-M05–M09. Ordinary file-blob bodies stay excluded; a note targeting a file blob does not authorize retaining the file body.

**Atomic/crash behavior:** Publication of each accepted immutable fact/group must be atomic with its required capture FK and actual evidence. Failed transaction retries cannot produce a partially visible **complete** group, duplicate a successful fact, manufacture a new capture, discard a previously admitted fact or make an incomplete transfer “complete”. A reader uses a consistent visibility snapshot and qualifying provenance; the exact lock/fence and Exchange wire implementation remain open.

**Identity collisions:** A repeated captured pair with a different repository/ref or incompatible immutable observed root/source evidence must **fail closed** rather than be relabeled or overwritten. ADR 0020 / B01-R05 fixes separately attributed immutable alternative member reports; credential/origin authentication and fork/copy issuer protocols remain separate implementation decisions.

## 4. Four message sequence

Let `P/K100` be one genuine notes-ref observation of `refs/notes/review` whose original root is A.

| Arrival | Payload | B01-R04 accepted result |
| --- | --- | --- |
| T1 | Source-attributed partial `C1→N1` | Preserve K100; admit one qualified atomic partial group/fact G1 |
| T2 | Same capture; independent compatible partial `C2→N2` | Keep K100 and G1 unchanged; admit **new** qualified immutable group/fact G2 |
| T3 | Repeat the **same G1 assertion and provenance** (`C1→N1`) through Exchange | Idempotent no duplicate G1; do **not** invent capture K101 |
| T4 | Same K100, same claimed C1 notes mapping slot, `C1→N9` | **Not** an ordinary compatible append. Report/handle contradiction honestly; no overwrite, winner or fabricated canonical/complete group. ADR 0020 / B01-R05 preserves immutable alternative claims and derives conflict; direct semantic member/group keys fixed by ADR 0021 / B01-R06 A |

G1 and G2 can be queried with their actual partial-scope qualifications. **The display set `{C1→N1,C2→N2}` alone is not evidence that all note entries were enumerated.** A supported full list, terminal/empty inventory and completeness acknowledgment require separately scoped B03 proof, not a generic status flag attached to K100.

A new observation made later of the same root A uses **P/K101**, not K100, even if all observable entries match K100's groups.

## 5. Accepted-decision matrix

| Accepted baseline | Consistency |
| --- | --- |
| **ADR 0014 / GCTX-S01** | Git history/structure/notes catalog; preserve notes text/bytes when allowed, never archive ordinary file contents or turn a note target into an acquired file body |
| **ADR 0015 / B01-R01** | Discover actually observable `refs/notes/*` incl. nested namespaces plus explicitly nominated additional refs; enumeration availability is not capture content/closure |
| **ADR 0016 / B01-R02** | Distinct genuine capture occurrences even with same ref/root; original capture retained, no mutable pointer, retry does not become an independent observation |
| **ADR 0017 / KEY-P01** | No storage-only surrogate PKs or incidental fragment-ID table; real capture composite FK and meaningful typed group/member identity only |
| **ADR 0018 / B01-R03** | Both origin and capture UUID are version-4; preserve original pair across Exchange and partial transactions; no sender trust/validated body from UUID equality |
| **GCTX-M01** | Metadata-only Git Core works with zero raw bytes, absent Context and with partial observations |
| **GCTX-M02** | Shared nominal `(object_format,oid)` identity unaffected; one Git object can be referenced under many captures |
| **GCTX-M03** | Each typed coherent group is atomic and immutable; later partial contributions are new groups/facts under same capture, **not** mutation or unauthorized union |
| **GCTX-M04** | Field/group verification-qualified canonical projections and explicit conflicts; no newest/most frequent/source-order winner |
| **GCTX-M05** | Git observation and intrinsic verification evidence remain Core-owned, Provider assessments Context, transient fetch/retry Jobs Operational |
| **GCTX-M06–M07** | Bounded historical locally verified admitted note/metadata bytes plus actual-operation physical integrity checks are separate from capture identity |
| **GCTX-M08–M09** | Immutable alternate physical copies and evidence-derived eligible-set selection remain only for actually retained bytes, not missing ordinary file blobs |
| **ADR 0003 / CAS-41** | Git Core INSERT-only, no UPDATE/DELETE/REPLACE/GC; actual retained-byte quarantine/count backup protection unchanged |
| **Fixed invariants** | Permanent `repository_uuidv4`, Source known-positive, Coverage exactly five columns/latest-observation semantics, Q01-B/Q02-B/Q03-B, no independent Publication, Unix epoch microsecond `_us`, paired Context-containing backup, Core-only metadata backup, ADR 0001 |
| **GCTX-M10** | Quarantine retirement/active count remains explicitly undecided, unrelated to notes capture fact admission |

## 6. Future adversarial acceptance counterexamples (not executed)

1. Receive T1 G1 then T2 G2 with the **same** origin/capture UUIDv4 pair: preserve G1 and make G2 independently, immutably queryable without a new capture.
2. Receive T2 before T1: compatible facts must not force false empty/list closure or arbitrary winner. Correct identity and qualification survive reordering.
3. Replay G1 verbatim with identical attributable assertion identity via different Exchange path: no duplicate authoritative G1 and no new capture.
4. Report same note C1→N1 under a truly different origin's independent capture: do not collapse actual separate observation evidence.
5. Send same K100 with C1→N9 as T4: no overwriting, silent first/last winner, false verified complete map; ADR 0020 / B01-R05 fixes competing member reports and derived conflict; direct semantic claim/group key fixed by ADR 0021 / B01-R06 A.
6. Send same capture UUID but a different repository/ref or falsely rebound root: fail closed on immutable capture identity/provenance violation.
7. Attempt to add member to an already admitted **complete frozen relation group**: no in-place extension or silently changed original group. Later facts use legitimately new groups as permitted by source/scope.
8. Show two compatible partial groups at K100. The interface must not label their aggregate **complete** absent B03-specified proof.
9. Include a genuinely evidenced complete-empty group and a separate partial observed group. Do not infer that empty means unknown or silently change the prior complete group.
10. Crash between capture/group/member writes: rollback the coherent unit; a subset is never an authoritative supposedly complete group.
11. Retry after COMMIT result lost: deduplicate the previously accepted exact fact/group, not a fake new event.
12. A caller supplies a random `member_row_id`/fragment UUID solely for storage convenience. Reject the proposed identity as inconsistent with KEY-P01; use real field/group/membership semantics.
13. Core-only metadata/notes import works without any Context, remote fetch or canonical blob bytes; unverified note mappings retain correct qualification.
14. A note capture references an ordinary file blob: exclude its body. A demonstrated actual note body is separately subject to ADR 0014 retention and GCTX-M05–M09 integrity/CAS-41.
15. Receiver-local approval, UUID equality or a sender-supplied `verified` bit cannot authenticate an issuer or promote unverified claims to byte-checked facts.
16. Recreate Operational/Search, Exchange the capture out and back and restore a Core-only backup; same capture IDs and immutable facts remain authoritative with no hidden mutable deduplication ledger.
17. Concurrent inserts of the same member identity cannot create duplicate accepted facts or corrupt the capture; concurrent compatible new facts remain independently qualified.
18. Do not treat a notes-ref name, root OID, member digest or decoder version as a universal completeness proof or a chronological capture winner.

## 7. Subsequent owner decisions: B01-R05 A and B01-R06 A accepted; B02-R04 A accepted by ADR 0025

[ADR 0020 / B01-R05](0020-immutable-competing-notes-member-claims.md) selects **Option A**: preserve eligible contradictory notes member reports as separately attributed immutable Git Core alternatives and derive explicit unresolved conflict for ordinary reads. Only precisely relevant receiver-checked Git notes mapping evidence can support a canonical value; historical reports remain queryable. Capture origin/repository/ref/root identity misuse still fails closed, not as a member alternative. [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md) fixes direct semantic claim/group identity and replay equality; B02-R01 role-evidence strength is fixed by ADR 0022; B02-R02 configurable finite budget policy is fixed by ADR 0023; B02-R03 actual-work accounting is fixed by ADR 0024; B02-R04 cumulative request scope is fixed by ADR 0025; remaining budget details are engineering work. The following A/B/C alternatives are *historical*, not an open B01-R05 choice.

**How should a contradictory *member-level report* for the same logical note association inside one immutable capture be persisted/represented after B01-R04 has recognized it as incompatible?**

- **A — Preserve typed competing claims as immutable Core alternatives; derive an explicit conflict (recommended candidate).** Accept individually attributed conflicting *reports* under the same capture with separate provenance/scope, never as two verified canonical members or one complete group. Ordinary query shows unresolved conflict/alternatives until actual relevant locally checked evidence supports a specific field; keep both historical reports. Advantages: forensic trace, Exchange reversibility, GCTX-M03/M04 alignment. Costs: fact-key/claim-type grammar, conflict read projection and malicious-untrusted provenance checks.
- **B — Reject the contradictory later report from admission.** Keep the already admitted fact and return a bounded typed input error (possibly retain a separately scoped security/audit diagnosis only where required), with no second member report stored in Core. Advantages: simpler stored membership and strict fail-closed behavior. Costs: audit evidence lost, depends on arrival order, and a previously erroneous first claim cannot be balanced by later alternative evidence.
- **C — Retain disputed report in a distinct immutable Core dispute set and withhold the affected capture/member from ordinary note-map reads until independently resolved.** Advantages: stronger isolation while retaining contradictory input. Costs: additional domain status/set complexity, reduced metadata availability, and risk of creating a generic authoritative quarantine/Publication layer. This is **not** physical CAS quarantine; a metadata contradiction does not indicate a corrupted stored body.

All alternatives must keep **capture identity/ref/root immutability** and reject forged/mismatched capture-origin identity independently of ordinary member conflict. No option allows UPDATE/DELETE/REPLACE, trusted sender “verified”, time-based winner or retroactive completeness. Direct semantic claim/group keys and replay equality are fixed by ADR 0021 / B01-R06 A. Exact admission proof, concrete grammar/DDL, full-member completeness (B03), remaining B02 resource/proof grammar contracts after ADR 0022 role-evidence policy, and physical CAS quarantine (GCTX-M10) remain separate.

## 8. Authorization

Owner accepted **B01-R04 Option A** following B01-R03 D-1, B01-R02 B and B01-R01 B; ADR 0014–0018 / KEY-P01 and GCTX-M01–M09 are preserved within accepted scope. No code, SQL/DDL, live catalog, schema version, tests, authenticated source acquisition, release, deployment or merge is authorized. Future examples above are **planned test cases, not executed evidence**.
