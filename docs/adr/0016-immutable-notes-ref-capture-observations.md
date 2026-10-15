---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0015-automatic-git-notes-ref-discovery.md
  - 0014-history-and-notes-catalog-without-file-archive.md
  - 0006-field-claims-and-observation-scoped-relations.md
---

# ADR 0016: Immutable capture-scoped identity for Git notes-ref observations

**Current post-corruption override:** [ADR 0026 / GCTX-M10](0026-stop-salvage-restore-merge-after-corruption.md) requires stopping ordinary catalog operation, preserving the suspect source read-only, serializing salvage candidates, restoring a verified backup into a fresh destination and merging only revalidated admissible data. Prior post-fault metadata service, same-DB failover, known-corrupt normal backup/restore and references to M10 as pending are historical in that scope. Ordinary sound-catalog rules and unrelated open work remain. No implementation or merge is authorized.

**Current refinement:** [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md) accepts direct semantic composite claim/group keys using the actual Capture UUIDv4 pair, typed slot, asserted value and genuine provenance, without surrogates. B02-R01 structural role-evidence strength is fixed by [ADR 0022](0022-receiver-verified-notes-role-admission.md); B02-R02 configurable finite budget policy is fixed by [ADR 0023](0023-configurable-finite-notes-resource-budgets.md); B02-R03 actual-work accounting is fixed by [ADR 0024](0024-actual-notes-resource-work-accounting.md); [ADR 0025 / B02-R04 A](0025-cumulative-request-budgets-and-scoped-blockers.md) fixes cumulative work within one explicit acquisition request across continuation/resume/retry. Counter units, defaults and resume mechanics are agent-owned engineering work, not further owner blockers. Other proof/completeness/trust/DDL work remains separately scoped; GCTX-M10 recovery is fixed by ADR 0026; detailed implementation remains work under that policy. Earlier alternatives below retain their historical scope.

- **Decision ID:** B01-R02 (second part of B01: durable notes-ref observation identity).
- **Owner selection:** **Option B** — every genuine notes-ref observation is a distinct, immutable, capture-scoped subject with a portable capture identity; notes mapping/relation groups attach to that particular observation. Repeat delivery of that **same** capture must be idempotent, but a new observation of the same ref/root must not be silently merged with the old one.
- **Owner acceptance:** 2026-10-15. This is the owner-accepted target architecture, not a claim that the deployed/implemented schema is changed.
- **Stack base:** [PR #56 / ADR 0015 / B01-R01](https://github.com/TakashiSasaki/git-repo-db/pull/56), unmerged HEAD `d230f3951924e47395c52326670bfd56adb97e2f`, above PR #55 (ADR 0014) and the accepted GCTX-M01–M09 design stack. Sibling [PR #52](https://github.com/TakashiSasaki/git-repo-db/pull/52), proposed ADR 0011 governance, is not a predecessor or accepted authority.
- **Implementation baseline:** Three-Store Core Schema 21. This PR changes design Markdown only; final tables, key encoding, replay algorithms and production code are pending.

## 1. Binding distinction: Git identity, notes ref, and observed capture

Persist distinct concepts with explicit links, not a single composite note record:

1. **Common Git object nominal identity:** `(object_format, full_oid)`, globally nominal across observed repositories (GCTX-M02). This alone says nothing about verified bytes, type, a note role, repo membership or complete observations.
2. **Notes namespace/ref subject:** repository UUIDv4 plus the **exact full ref name**, with actual originating source/ref namespace provenance. `refs/notes/review` is neither the identity of an annotation nor a snapshot of its current root. The automatic/explicit selection policy is fixed separately by B01-R01 / ADR 0015.
3. **Notes-ref observation (capture-scoped identity):** a **portable, stable and immutable capture identity** for one genuine observation of an exact notes ref in a particular repository/source/capture scope, with the observed root OID and kind **when actually known**, and the applicable source and evidence.
4. **Notes mapping groups and member claims:** attach to the **specific capture** in whose source/scope the target-to-note relationships were observed, with the typed target OID, note OID and actual note-tree path when known, and independent membership/order and complete/partial/unknown evidence (GCTX-M03). A group cannot borrow other captures' members to declare itself complete.
5. **Note-content bytes and physical evidence:** separate optional role-authorized Git `blob` representation/metadata with exact receiver-local checks and CAS facts only where actually acquired. An observation ref/root or target OID does not grant raw ordinary-file blob retention (ADR 0014).

**Identity choice:** different genuine capture occurrences MUST remain distinguishable, even if `(repository, notes_ref, observed_root_oid)` and members happen to match. The same exact capture delivered again via retry, Exchange or another permitted transfer route MUST NOT be mistaken for a new historical observation. A capture ID's **portable referential role** is decided here. [ADR 0017 / KEY-P01](0017-domain-keys-without-storage-surrogates.md) subsequently **rules out a separate receiver-local storage surrogate**; the direct **`(capture_origin_uuidv4,capture_uuidv4)`** composite primary/foreign key and D-1 issuance semantics are now **accepted by [ADR 0018 / B01-R03](0018-notes-capture-uuidv4-composite-identity.md)**. [ADR 0019 / B01-R04](0019-monotonic-notes-capture-fact-admission.md) fixes compatible incremental facts and idempotent exact replay without mutating an atomic relation group. ADR 0020 / B01-R05 fixes competing member reports as immutable alternatives; direct semantic claim/group keys are fixed by ADR 0021 / B01-R06 A; issuer-trust details remain separately open.

A capture is the accepted observation fact, **not** a retry Job, page-request attempt, polling heartbeat, generic source revision event, or universal Publication-like batch admission authority. Operational can retry work without multiplying Core capture facts.

## 2. Identity-independent data and truth requirements

For a notes-ref observation, preserve the following when genuinely available:

| Field/evidence kind | Binding requirement |
| --- | --- |
| Portable capture identity | Stable for the **same accepted capture**, not derived solely from the current root or target OIDs; two UUIDv4 components fixed by ADR 0018 / B01-R03; exact producer registry and verification mapping remain further design |
| Repository | Permanent `repository_uuidv4`; do not merge unrelated repositories by ref name |
| Ref | Full, exact notes-ref name and source scope, including explicit extra refs outside `refs/notes/*`; no implicit display-ref winner |
| Ref root | Full typed OID and actual root kind if known (`commit` or direct `tree`), with separate reported/locally verified qualifications. Unknown root must not be invented as a commit |
| Observation provenance | Actual source/capture origin, observation boundaries, supplied/checked evidence and genuinely available acquisition timing (`_us` for stored absolute times). No conflation of observed source event time and receiver receipt time |
| Membership evidence | Capture-scoped note-target/note-OID associations and actual observed raw tree names/paths, with complete/partial/known-empty/unknown contract left to B03 |
| Admission/byte authority | Core-owned typed notes facts with Context-independent interpretation; Context Provider evaluation may reference a capture but is not mandatory for Core validity. Raw note body requires ADR 0022 receiver-verified structural notes-role evidence and GCTX-M05–M09 byte checks |

The identity does **not** certify that a reported ref root was actually resolved at the sender's claimed time, that all the notes members were listed, or that the notes blob is presently physically healthy. The receiver does not authenticate a sender's `verified` bit or infer missing membership from a capture identifier.

The receiver MUST support metadata-only Core operation, including a notes-root observation with no raw commit/tree/notes bytes, with no Provider/Context database, and with honest unknown or unverified status.

## 3. Four observations of one notes ref: counterexample

| Genuine capture | Notes ref | Observed root | Evidence/scope | Correct durable meaning |
| --- | --- | --- | --- | --- |
| `K1` at T1 | `refs/notes/review` | A | Only C1→N1 reported; list partial | Preserve K1, its qualified member and partial claim |
| `K2` at T2 | `refs/notes/review` | A | C1→N1 and C2→N2; complete if supported by real B03 evidence | Distinct observation K2, not a silent mutation/upgrade of K1 |
| `K3` at T3 | `refs/notes/review` | B | C1→N3 reported; completeness unknown | Distinct observation K3, not overwrite of K1/K2 |
| `K4` at T4 | `refs/notes/review` | A | Root A reappears, members may match K1/K2 | Distinct observation K4, not a duplicate of K1/K2 despite same root |

Receiving **K2 again** under a stable, validated capture identity is a replay of K2 and must not create a spurious K5. Receiving the same current root A from *another* independent source/capture does not prove it is K2 either. ADR 0018 / B01-R03 fixes origin UUIDv4 and capture UUIDv4 as the direct portable key. Monotonic compatible-fact admission and exact replay are fixed by ADR 0019 / B01-R04; incompatible member reports are retained as attributed alternatives under ADR 0020 / B01-R05; direct semantic keys are fixed by ADR 0021 / B01-R06 A.

**Important:** even when root A and every member are identical in K1, K2 and K4, the capture identity preserves the fact that the state was separately observed. GCTX-M04's query precedence/conflict policy and future completeness-scope design determine what a query can conclude, not the last inserted capture ID.

## 4. Append-only admission and Exchange/backup constraints

- Each accepted capture identity and its attribution are immutable Git Core facts. When the ref changes, goes missing, or returns to a prior root, do not `UPDATE`/`DELETE` or rewrite older capture/root evidence. A source's later report is additional evidence, never the same capture solely because OIDs match.
- Replaying the **same** capture is idempotent using the D-1 two-UUIDv4 origin/capture key from ADR 0018, with ADR 0019 / B01-R04 monotonic fact-level replay and ADR 0020 / B01-R05 attributed conflicting report preservation; direct semantic claim/group keys are fixed by ADR 0021 / B01-R06 A. An allegedly reused capture identity whose repository/ref/root/provenance conflicts with previously admitted immutable facts must **not** overwrite, silently merge, or validate itself by sender assertion. Fail closed or expose a typed conflict under the future admission protocol.
- A capture may have a **partial** member group or unknown completeness without inventing synthetic empty sets, ordering or raw-object offsets. Any later genuinely distinct observation gets its own ID; the exact incremental delivery of more facts within a single already identified capture, consistent retries and complete-claim promotion rules are constrained by ADR 0019 / B01-R04 to new immutable coherent facts/groups under the original capture; B01-R05 competing member report preservation is fixed by ADR 0020, while ADR 0021 / B01-R06 A fixes direct semantic keys and B03 completeness remains open, never a license to mutate old facts.
- A single producer's multi-ref enumeration may encompass **several ref observations**. B01-R02's authoritative identity is per **ref observation**, while the encompassing inventory snapshot/evidence can be represented separately under B03. Do not elevate a generic source run, poll, batch or Publication into an authority required by every Git Core fact.
- For Exchange, a capture's portable identity/provenance must survive forward and repeated transfer sufficiently to distinguish replay from independently made observations. Receiver-local row IDs must not be mistaken for portable identity, and provenance from external systems must not impose a required Core→Context FK. The identity's two-UUIDv4 key is fixed by ADR 0018, compatible partial-member admission by ADR 0019 / B01-R04 and contradictory member report preservation by ADR 0020 / B01-R05; direct semantic claim/group keys are fixed by ADR 0021 / B01-R06 A; origin trust and Exchange wire consistency B07 remain open.
- Metadata-only Core backup/restore preserves accepted capture identities, sources, ref/root claims and observation-scoped groups without fetching raw bytes or constructing a Context DB. Full Context-containing backup still requires the paired authoritative-store contract. Rebuildable Operational/Search loss cannot erase notes capture identity.
- Notes ref discovery under ADR 0015 includes all **actually observable** `refs/notes/*` and explicit additional ref names; it does not establish any globally complete remote notes inventory. A ref pointing directly to a tree is valid. Captured notes OIDs and annotation targets have one common nominal Git identity (GCTX-M02).
- No new general file blob archival permission follows from attaching a blob OID as an annotation target or from a sender-provided `is_note` flag. Retained note bodies require separately established typed notes-role and byte-verification evidence; current CAS health is not established by a metadata observation.
- An absolute recorded timestamp uses Unix epoch microseconds and `_us`; neither source timestamp, receiver arrival, UUID order, higher Git root OID nor decoder choice selects a current authoritative ref or a canonical metadata winner.

## 5. Alignment with owner-accepted design

| Contract | B01-R02 Option B preservation |
| --- | --- |
| **ADR 0014 / GCTX-S01** | No ordinary file content archive; purpose-bound notes body exception remains. Explicit notes refs, roots, targets and paths are properly scoped |
| **ADR 0015 / B01-R01** | All observable `refs/notes/*` auto-discovered, explicitly nominated additional notes refs supported; each observed selected ref has a distinct capture-scope observation |
| **GCTX-M01** | Source-attributed notes/ref metadata import and Core-only reads require no raw bodies, mandatory rehash or Context |
| **GCTX-M02** | One nominal `(object_format,oid)` per object, independent of ref/notes role, source and number of captures; object possession not implied |
| **GCTX-M03** | Observed note associations are typed, coherent capture-scoped relation groups; never combine incompatible partial groups into a fictitious complete list |
| **GCTX-M04** | Historical source reports remain independent of byte-checked canonical interpretation; conflicts and unverified facts are queryable without arbitrary winner selection |
| **GCTX-M05** | Core owns Git-intrinsic observations and required verification evidence; Context owns Provider-specific mutable assessments; Operational owns retry execution |
| **GCTX-M06–M07** | Accepted exact note/commit/tree/tag bytes have immutable local-admission proof and operation-scoped integrity checks; note capture identity alone proves neither |
| **GCTX-M08–M09** | Valid physical note-body copies, diagnostics, immutable recovery and deterministic eligible-set selection remain a separate domain from notes observations |
| **ADR 0003 / CAS-41** | Strict Core `INSERT`-only (no UPDATE/DELETE/REPLACE/GC), no independent Publication, accurate physical quarantine counts; never classify absent never-fetched bodies as corruption |
| **Other fixed rules** | Permanent repository UUIDv4; Q01-B/Q02-B/Q03-B; unaffected PF-P01–PF-P17; known-positive Source; five-column latest-observation Coverage; Unix `_us`; two-authoritative-store backup; ADR 0001 |
| **GCTX-M10** | Physical quarantine retirement/count predicate remains entirely unresolved and is not implicitly decided by B01 |

These are scoped refinements, not a new generic event store, mutable notes-current ref table, overall verification seal, full Provider API history or byte-retention expansion.

## 6. Future adversarial acceptance counterexamples (NOT executed)

1. Ingest K1 and K2 for same repository/ref/root A with different legitimate partial and complete scopes. Both immutable capture observations remain separate.
2. Later observe B as K3 and a return to A as K4. A newer or older root does not erase or combine captures and does not automatically become universally current.
3. Replay K2 identically via the same origin, an import retry or reverse/repeat Exchange. No new purported independent observation is created, without suppressing genuine separate capture K4.
4. Accept independent capture K5 from a different source reporting same root/members as K2. Preserve K5 and distinct attribution; shared Git nominal OIDs remain one per format.
5. Present an existing K2 ID with inconsistent ref, root, repository or source. Do not mutate the original record, silently overwrite or pretend sender claims authenticate the conflict.
6. Admit a capture reporting a root OID with unknown type, without body or Context. Do not fabricate a notes commit or a validated Git object.
7. Admit a verified notes ref pointing directly at a tree, preserve exact root type and notes-tree path; do not invent a commit root.
8. Capture incomplete note members, known empty list with supported evidence, and no notes observed; do not infer one state's completeness from another capture.
9. Ingest refs with both automatic and explicit selectors within one capture; do not invent duplicate namespace observations solely from selection mechanism.
10. Associate different notes under two namespaces with the same annotated target OID; do not collapse namespaces or merge member groups.
11. Reference an ordinary file blob as annotation target: metadata persists, target file bytes remain excluded. Note-body admission only under real typed notes proof.
12. Import binary, empty and missing note bodies with truthful type/availability labels; do not invent UTF-8, body hashes or size for unobserved bytes.
13. Exchange/backup/re-import a capture with the same origin/capture domain composite (without receiver-local row surrogate IDs) and verify portable identity/provenance without a mandatory Context FK.
14. Restart Operational and rebuild Search while Git Core retains accepted capture/ref/source facts and historical relation alternatives unchanged.
15. Verify failure in a byte-dependent note export does not rewrite prior capture, mark a report verified or bypass CAS-41; GCTX-M07 exact-output integrity remains independent.
16. Ensure no `capture per retry` generic log, no provider-state history substitution, no mutable current-notes-ref pointer and no Git Core GC/REPLACE path is introduced.

## 7. Subsequent owner decisions: B01-R03 D-1, B01-R04 A, B01-R05 A and B01-R06 A accepted; B02-R04 A accepted by ADR 0025

[ADR 0020 / B01-R05](0020-immutable-competing-notes-member-claims.md) now preserves separate genuinely attributed conflicting notes member reports under one stable Capture as immutable Core alternatives and derives explicit conflict without rewriting any existing GCTX-M03 group. Direct report/group semantic PKs and replay equality are fixed by [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md). Original A/B/C/D B01-R03 alternatives below remain historical.

[ADR 0018 / B01-R03](0018-notes-capture-uuidv4-composite-identity.md) adopts **D-1**: capture origin UUIDv4 and capture UUIDv4 directly form the composite domain PK/FK, with no storage-only receiver-local surrogate. ADR 0019 / B01-R04 fixes compatible incremental same-capture facts and exact replay; issuer authenticity remains a separate protocol requirement, while ADR 0020 / B01-R05 fixes immutable competing notes-member alternatives; direct semantic claim/group keys are fixed by **B01-R06 A / ADR 0021**. The A/B/C/D comparison below is historical context, not an open identity-allocation choice.

**How is the accepted immutable capture identity allocated and recognized across local capture, different sources, repeated/partial Exchange delivery and receiver-local database IDs?**

- **A — Producer-issued portable capture ID as the direct key.** The origin issues one globally portable capture ID; receiver stores it directly and deduplicates exact repeated IDs, scoped to verified origin where needed. Simple, but issuer collisions/spoofing, imported sender trust and provenance aliases must be dealt with. Same-root independent captures require fresh IDs.
- **B — Receiver-local immutable identity plus origin-scoped portable mapping (historical option, disallowed by ADR 0017).** This would create a storage-only surrogate despite an available portable domain composite. The new owner's key policy supersedes this unselected suggestion.
- **C — Content-derived capture fingerprint from ref, root and observed mapping/evidence.** Deterministic transport deduplication without producer IDs, but distinct genuine observations of identical state can collapse, and partially delivered captures can get different IDs when members arrive. This risks contradicting B01-R02's captured-event identity.
- **D — Direct origin/capture composite domain key (now accepted as D-1 under ADR 0018).** Use `(capture_origin_uuidv4,capture_uuidv4)` directly as PK and composite FKs, both version-4 UUIDs, with no local surrogate. Genuine capture issuance is fixed; same-capture compatible-fact admission is fixed by ADR 0019 / B01-R04; member-level competing reports are preserved by ADR 0020 / B01-R05; direct semantic claim/group keys are fixed by ADR 0021 / B01-R06 A.

ADR 0017 excludes storage-only local surrogates and ADR 0018 accepts the D-1 **two-UUIDv4 direct composite**. [ADR 0019 / B01-R04](0019-monotonic-notes-capture-fact-admission.md) subsequently accepts monotonic immutable compatible facts/groups and idempotent exact replay under the same capture; ADR 0020 / B01-R05 accepts immutable competing member reports; direct semantic claim/group keys are fixed by ADR 0021 / B01-R06 A. A repeated capture token with conflicting content MUST NOT silently rewrite prior Core truth. ADR 0019 already fixes compatible partial facts and exact fact replay; ADR 0020 / B01-R05 fixes contradictory member report preservation as immutable alternatives; ADR 0021 / B01-R06 A fixes direct semantic member/group keys and exact equality, with issuer authentication separately open. A genuinely new observation still requires a new capture UUIDv4. B02-R01 role-evidence strength is fixed by ADR 0022; B02-R02 finite configurable budget policy is fixed by ADR 0023; exact proof grammar and B03 completeness/scope evidence remain unresolved.

## 8. Scope, references and authorization

- Current owner explicitly chose B01-R02 **B**, after B01-R01 B / ADR 0015 and product scope ADR 0014, maintaining GCTX-M01–M09.
- Git notes primary reference: https://git-scm.com/docs/git-notes (notes ref namespaces, history vs direct-tree roots, annotations stored as blobs).
- Base design stack: ADR 0014 PR #55 → ADR 0015 PR #56 → this design-only ADR 0016.
- Sibling proposed governance PR #52 / ADR 0011 is **not adopted** and does not alter numbering/status or authorize merging.
- Future unresolved work: B01-R03 UUIDv4 composite identity fixed by ADR 0018; B01-R04 compatible-fact admission fixed by ADR 0019; B01-R05 competing member reports fixed by ADR 0020; B01-R06 direct semantic keys fixed by ADR 0021; B02-R01 role-evidence strength fixed by ADR 0022; B02-R02 finite configurable budget policy fixed by ADR 0023; proof grammar open; B03 group and enumeration completeness; GCTX-M10 quarantine retirement/count; exact Core/Context DDL, revision/read fences, Exchange wire, backup pairing and Context GC-03/04.

No Python/SQL/DDL, tests of application runtime, release, deployment, source acquisition, live-catalog migration, merge or authenticated import are authorized. The sixteen counterexamples above are future requirements, **not** executed test evidence.
