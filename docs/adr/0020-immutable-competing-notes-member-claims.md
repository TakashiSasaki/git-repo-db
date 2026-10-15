---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0019-monotonic-notes-capture-fact-admission.md
  - 0016-immutable-notes-ref-capture-observations.md
  - 0006-field-claims-and-observation-scoped-relations.md
  - 0007-verification-aware-git-metadata-reads.md
---

# ADR 0020: Preserve conflicting Git notes member reports as immutable attributed alternatives

**Subsequent accepted refinement:** [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md) fixes direct semantic composite claim/group PKs and matching FKs using the actual Capture UUIDv4 pair, typed slot, asserted value and genuine provenance. Whole-group membership/scope is part of group identity; no surrogate or digest replaces it. B02-R01 role-evidence strength is fixed by [ADR 0022](0022-receiver-verified-notes-role-admission.md); B02-R02 configurable finite budget policy is fixed by ADR 0023; B02-R03 resource measurement/charging is next; B03 and GCTX-M10 remain open.

- **Decision ID:** B01-R05; **owner choice: Option A**, accepted 2026-10-15.
- **Direct base:** [PR #60 / ADR 0019](https://github.com/TakashiSasaki/git-repo-db/pull/60), HEAD `c1c5bf580bdb0383ed9b5df613b73c70753f73d9`; design-only, no implementation/merge. Inherits ADR 0014–0019, KEY-P01 and GCTX-M01–M09.
- **Concurrent sibling:** Proposed ADR 0011 governance PR #52 remains **unadopted**.
- **Implemented baseline:** Three-Store Core Schema 21 / Operational 1 / Search 1; not yet redesigned.

## 1. Binding decision: competing reports, not competing verified note values

For an existing immutable notes-ref Capture identified directly by `(capture_origin_uuidv4,capture_uuidv4)`, an eligible source-attributed report `C1→N1` and an independently attributable, contradictory report `C1→N9` for the **same genuine logical notes member slot** may coexist as **separately typed immutable reported claims** in Git Core.

**MUST:**
1. Keep each eligible reported assertion with its **actual** source/provenance, Capture/ref/root, member-position/path/target where genuinely known, assertion content, group/evidence scope and verification qualification. Preserve both even if one is later contradicted.
2. Store contradictory reported members in **different immutable coherent observation groups/typed claims**, *not* by modifying an already accepted group. Each coherent group and its members remain atomic under GCTX-M03.
3. Derive an explicit **unresolved conflict plus accessible alternatives** on ordinary note reads when no relevant locally verified intrinsic evidence justifies a canonical answer. Never choose by arrival, issuer ID, source popularity, decoder, unverified timestamp or count of agreeing reports.
4. If the receiver locally checks the **actual relevant Git notes root/tree relationship** for precisely this requested mapping/scope, GCTX-M04 permits its checked intrinsic interpretation to be preferred **for that field/group** with all earlier reports still queryable. Checking the purported note blob's bytes alone does **not** verify its relationship to annotated target C1 or that the notes ref/root/list is complete.
5. Preserve B01-R04 fact-level exact-replay idempotency and monotonic compatible new facts; a competing *reported alternative* is not a compatible extension of the original group and must not silently be treated as two true canonical notes.

**MUST NOT:** use this member-claim policy to redefine a Capture's immutable origin UUID, repository, exact notes-ref name, original root identity or source attribution. A sender reusing a Capture key with a different repository/ref/root/origin is an **identity or provenance violation**, which must fail closed under capture admission rules. A UUID alone neither authenticates the sender nor turns a claim into byte-verified Git truth.

**No other permission implied:** neither a reported note OID nor a conflict grants access to ordinary repository-file raw blob storage. Notes-content body admission still requires receiver-verified structural role evidence (ADR 0022 / B02-R01) and actual CAS/OID checks (GCTX-M05–M09). Metadata disagreement is **not** physical CAS corruption and does not increase CAS-41 quarantine counts.

## 2. GCTX-M03/GCTX-M04/GCTX-M01 and KEY-P01 reconciliation

- **GCTX-M01:** Git Core-only metadata queries, attribute/notes relations and conflicts work with zero bytes, no Context and no hidden fetch.
- **GCTX-M02:** the common `(object_format,full_oid)` nominal Git object identity is not duplicated for conflicting notes.
- **GCTX-M03:** competing notes reports are **distinct typed attributed evidence units or distinct coherent immutable groups**. Do not append N9 into an earlier atomically accepted N1 group or silently union two partial groups into one complete notes listing.
- **GCTX-M04:** canonical read preference is **local field/group-specific intrinsic byte verification**; when absent, expose an unresolved conflict and every alternative. A verified N9 blob alone is insufficient to verify `C1→N9`. The read projection never changes old claims.
- **GCTX-M05–M09:** Core owns Git-intrinsic verification and immutable facts; Context owns Provider assessments; Operational owns jobs; retained note/metadata body admission, physical health, multiple immutable copies and candidate selection remain separate.
- **KEY-P01 / ADR 0017:** no storage-only `claim_id`, `conflict_id` or extra fragment UUID is authorized. [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md) now fixes direct semantic composite claim/group identity and replay equality; concrete lossless encodings and DDL must preserve that choice.
- **ADR 0014–0019:** no ordinary file-content archive; all observable `refs/notes/*` plus explicitly nominated notes refs; genuinely distinct immutable captures; direct version-4 `(capture_origin_uuidv4,capture_uuidv4)`; compatible facts under the same capture with idempotent replay and separately atomic groups.
- **Other fixed decisions:** permanent repository UUIDv4, Source known-positive, Unix epoch microsecond `_us`, Coverage exactly five columns/latest-observation semantics, NO_INDEPENDENT_PUBLICATION, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, full Core+Context paired backup, Git-only metadata backup, ADR 0001 and strictly INSERT-only Core (no UPDATE/DELETE/REPLACE/GC) all remain binding.
- **GCTX-M10:** precise active physical quarantine count and retirement remain open. A metadata conflict neither quarantines bytes nor changes CAS-41 physical instance accounting.

Do not create a mutable conflict-resolution flag, winner-ID pointer, generic Publication, fifth authoritative dispute store, or a required per-scan success-event ledger. Conflict is a **derived projection** from eligible immutable reported alternatives and actually relevant checked evidence.

## 3. Worked four-message example

| Arrival | Information with original provenance, Capture K | Result |
| --- | --- | --- |
| T1 | Partial coherent group G1 reports `C1→N1` | Keep attributed immutable G1 |
| T2 | Compatible, distinct group G2 reports `C2→N2` | Admit new immutable G2 under **same** K (B01-R04); leave G1 intact |
| T3 | Exact replay of G1 including its source/semantic fact identity | Idempotent, no spurious G3 or new Capture |
| T4 | Separately attributable report `C1→N9` in same member slot | **B01-R05 A:** preserve as another immutable attributed claim/coherent group G4; project `conflict(C1)={N1,N9}`, **not** two verified canonical members |

After T4 the catalog says **there are conflicting reports**, not that both associations are valid. If a local check of the exact relevant Git notes tree/root establishes `C1→N9`, ordinary queries may prefer that specific checked relationship, still exposing the G1 alternative. The mere fact that blob N9 is byte-verified does not prove it is the note attached to C1.

A packet with K but a different immutable repository/ref/root is **not** a T4 notes report: do not use this ADR to legitimize a forged/reused Capture identity.

Two notes for C1 in **different notes refs** or genuinely different Captures are different observation scopes, not automatically a conflict.

## 4. Claim provenance, replay and accepted uncertainty

Exact replay of the same source-attributed assertion must remain idempotent. A distinct value/evidenced assertion for the same member slot is not an exact replay merely because the capture, root and target match. Independently observed identical-value claims can have different genuine evidence; neither arrival order nor equal hashes should erase that meaningful provenance.

**Accepted B01-R06 A / ADR 0021:** use the actual Capture UUIDv4 pair, real typed relation/member slot, asserted value and genuine original provenance directly as composite PK/FK components. Coherent group identity includes its entire immutable typed membership and scope. Exact source-attributed replay deduplicates; different genuine evidence remains distinct. Missing information uses truthful typed states, never fabricated ordinals/offsets. A same-coordinate inconsistent input without sufficient genuine identity fails closed rather than acquiring invented evidence. Hash-only keys and new per-claim occurrence IDs are not selected.

The required structural role-evidence strength for retaining **note body bytes** is fixed by **ADR 0022 / B02-R01 A**; resource policy and exact proof grammar remain further **B02** work, list/ref-inventory completeness remains **B03**, issuer-authentication/Exchange/backup fences and concrete DDL remain future contracts.

## 5. Required future adversarial tests (NOT executed)

1. T1 `C1→N1` and T4 `C1→N9` with real separate report evidence are both queryable as unverified alternatives with a derived conflict.
2. Reverse T1/T4 arrival order: same eligible competing evidence and unresolved read result, never last-writer-wins.
3. Replay either exact provenance-bound claim: no duplicate record or new Capture.
4. GCTX-M03 atomic coherent groups G1 and G4 remain distinct; no UPDATE or silent union makes a false complete list.
5. Locally check the *exact notes tree/root mapping*; only relevant checked field/group may be preferred while reported alternatives remain.
6. Verify only note blob N9 bytes; association C1→N9 must **not** automatically become canonical.
7. Different notes ref or independent Capture reporting the same C1 is not forced into a within-Capture conflict.
8. Reuse Capture K with different repository/ref/immutable root: fail closed as identity misuse, not a legitimate alternative note-member claim.
9. Untrusted sender `verified=true` and apparently valid UUIDv4 pair never prove notes-membership authenticity.
10. No normal file blob bytes admitted because they are a note target, an alternative note OID, or an Exchange message containing alleged annotations.
11. A metadata claim conflict does not create/destroy a damaged CAS physical instance or increment CAS-41 quarantine count.
12. Core-only offline metadata query/Exchange/backup preserves alternatives without Context or original Git bytes; recreate Operational/Search and retain the facts.
13. Partial and known-empty mappings remain separate from invented closure and from conflicting data under B03.
14. No synthetic per-claim/fragment surrogate or per-conflict state-owner table merely to simplify composite FKs.
15. Concurrent insertion and crash/retry cannot discard an eligible competing report, mutate G1, report success for half an atomic group or fabricate a preferred winner.

## 6. Historical B01-R06 comparison; Option A now accepted by ADR 0021

**How should the separate immutable report/group be directly keyed and deduplicated without storage-only surrogates?**

- **A — Direct semantic composite key (recommended):** original Capture pair plus typed relation/member slot (real raw path/ordinal where evidenced), asserted value and genuine source/evidence coordinates. Pros: portable meaning, different values coexist, exact replay idempotent; cons: wide keys, strict typed-value normalization and sometimes unavailable provenance/positions.
- **B — Canonical typed assertion hash:** derive a fixed digest of the full source-attributed typed statement and scope. Pros: compact and deterministic; cons: canonical encoding/version, collision rules, false collapsing of distinct evidence with equal content, and hash alone proves no origin.
- **C — Separate genuinely issued assertion-occurrence UUID:** only if source actually identifies a claim occurrence; pros: straightforward replay/Exchange, cons: another issuer/trust protocol, IDs unavailable in normal Git reads, and serious risk of disguising a forbidden surrogate under KEY-P01.

The owner subsequently selected **B01-R06 Option A**, fixed by [ADR 0021](0021-direct-semantic-notes-claim-group-keys.md). The comparison above is historical, not an open choice. The accepted key/equality contract preserves B01-R04's compatible monotonic facts, B01-R05's competing alternatives and GCTX-M03 atomic groups. **B02-R01 role-evidence strength** is fixed by ADR 0022; **B02-R02 finite budget policy** is fixed by ADR 0023; **B02-R03 measurement/charging** is the next owner blocker; B03/GCTX-M10 remain separately open.

## 7. Design-only authorization

Owner accepted **B01-R05 A** after B01-R01 B, R02 B, R03 D-1 and R04 A. This ADR is **documentation only**. No Python, SQL/DDL, source acquisition, migrations, live-catalog mutation, code test, PR merge, deployment or release is authorized. Future test cases above are not executed evidence.
