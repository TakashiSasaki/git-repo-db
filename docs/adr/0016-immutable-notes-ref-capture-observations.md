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

**Identity choice:** different genuine capture occurrences MUST remain distinguishable, even if `(repository, notes_ref, observed_root_oid)` and members happen to match. The same exact capture delivered again via retry, Exchange or another permitted transfer route MUST NOT be mistaken for a new historical observation. A capture ID's **portable referential role** is decided here; its issuer namespace, UUID/allocation mechanism, imported-origin mapping, receiver-local surrogate, collision protocol and exact idempotency predicate are the focused **B01-R03** question, not preselected by this ADR.

A capture is the accepted observation fact, **not** a retry Job, page-request attempt, polling heartbeat, generic source revision event, or universal Publication-like batch admission authority. Operational can retry work without multiplying Core capture facts.

## 2. Identity-independent data and truth requirements

For a notes-ref observation, preserve the following when genuinely available:

| Field/evidence kind | Binding requirement |
| --- | --- |
| Portable capture identity | Stable for the **same accepted capture**, not derived solely from the current root or target OIDs; exact ID format/open producer mapping remains B01-R03 |
| Repository | Permanent `repository_uuidv4`; do not merge unrelated repositories by ref name |
| Ref | Full, exact notes-ref name and source scope, including explicit extra refs outside `refs/notes/*`; no implicit display-ref winner |
| Ref root | Full typed OID and actual root kind if known (`commit` or direct `tree`), with separate reported/locally verified qualifications. Unknown root must not be invented as a commit |
| Observation provenance | Actual source/capture origin, observation boundaries, supplied/checked evidence and genuinely available acquisition timing (`_us` for stored absolute times). No conflation of observed source event time and receiver receipt time |
| Membership evidence | Capture-scoped note-target/note-OID associations and actual observed raw tree names/paths, with complete/partial/known-empty/unknown contract left to B03 |
| Admission/byte authority | Core-owned typed notes facts with Context-independent interpretation; Context Provider evaluation may reference a capture but is not mandatory for Core validity. Raw note body must have the separate ADR 0014 role proof and GCTX-M05–M09 byte checks |

The identity does **not** certify that a reported ref root was actually resolved at the sender's claimed time, that all the notes members were listed, or that the notes blob is presently physically healthy. The receiver does not authenticate a sender's `verified` bit or infer missing membership from a capture identifier.

The receiver MUST support metadata-only Core operation, including a notes-root observation with no raw commit/tree/notes bytes, with no Provider/Context database, and with honest unknown or unverified status.

## 3. Four observations of one notes ref: counterexample

| Genuine capture | Notes ref | Observed root | Evidence/scope | Correct durable meaning |
| --- | --- | --- | --- | --- |
| `K1` at T1 | `refs/notes/review` | A | Only C1→N1 reported; list partial | Preserve K1, its qualified member and partial claim |
| `K2` at T2 | `refs/notes/review` | A | C1→N1 and C2→N2; complete if supported by real B03 evidence | Distinct observation K2, not a silent mutation/upgrade of K1 |
| `K3` at T3 | `refs/notes/review` | B | C1→N3 reported; completeness unknown | Distinct observation K3, not overwrite of K1/K2 |
| `K4` at T4 | `refs/notes/review` | A | Root A reappears, members may match K1/K2 | Distinct observation K4, not a duplicate of K1/K2 despite same root |

Receiving **K2 again** under a stable, validated capture identity is a replay of K2 and must not create a spurious K5. Receiving the same current root A from *another* independent source/capture does not prove it is K2 either. Exact source-origin idempotency and forwarded replay detection are reserved for B01-R03.

**Important:** even when root A and every member are identical in K1, K2 and K4, the capture identity preserves the fact that the state was separately observed. GCTX-M04's query precedence/conflict policy and future completeness-scope design determine what a query can conclude, not the last inserted capture ID.

## 4. Append-only admission and Exchange/backup constraints

- Each accepted capture identity and its attribution are immutable Git Core facts. When the ref changes, goes missing, or returns to a prior root, do not `UPDATE`/`DELETE` or rewrite older capture/root evidence. A source's later report is additional evidence, never the same capture solely because OIDs match.
- Replaying the **same** capture is idempotent under the future exact B01-R03 origin/key and content-consistency rules. An allegedly reused capture identity whose repository/ref/root/provenance conflicts with previously admitted immutable facts must **not** overwrite, silently merge, or validate itself by sender assertion. Fail closed or expose a typed conflict under the future admission protocol.
- A capture may have a **partial** member group or unknown completeness without inventing synthetic empty sets, ordering or raw-object offsets. Any later genuinely distinct observation gets its own ID; the exact incremental delivery of more facts within a single already identified capture, consistent retries and complete-claim promotion rules are still B01-R03/B03 design, not a license to mutate old facts.
- A single producer's multi-ref enumeration may encompass **several ref observations**. B01-R02's authoritative identity is per **ref observation**, while the encompassing inventory snapshot/evidence can be represented separately under B03. Do not elevate a generic source run, poll, batch or Publication into an authority required by every Git Core fact.
- For Exchange, a capture's portable identity/provenance must survive forward and repeated transfer sufficiently to distinguish replay from independently made observations. Receiver-local row IDs must not be mistaken for portable identity, and provenance from external systems must not impose a required Core→Context FK. The actual mapping/wire contract remains B01-R03/B07.
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
13. Exchange/backup/re-import a capture through unrelated receiver-local surrogate IDs and verify that portable capture identity/provenance are preserved without a mandatory Context FK.
14. Restart Operational and rebuild Search while Git Core retains accepted capture/ref/source facts and historical relation alternatives unchanged.
15. Verify failure in a byte-dependent note export does not rewrite prior capture, mark a report verified or bypass CAS-41; GCTX-M07 exact-output integrity remains independent.
16. Ensure no `capture per retry` generic log, no provider-state history substitution, no mutable current-notes-ref pointer and no Git Core GC/REPLACE path is introduced.

## 7. Next unresolved identity/idempotency decision: B01-R03

**How is the accepted immutable capture identity allocated and recognized across local capture, different sources, repeated/partial Exchange delivery and receiver-local database IDs?**

- **A — Producer-issued portable capture ID as the direct key.** The origin issues one globally portable capture ID; receiver stores it directly and deduplicates exact repeated IDs, scoped to verified origin where needed. Simple, but issuer collisions/spoofing, imported sender trust and provenance aliases must be dealt with. Same-root independent captures require fresh IDs.
- **B — Receiver-local immutable identity plus an origin-scoped portable capture key/mapping (recommended candidate).** Each receiving Core has its own immutable row ID; the supplied/minted origin-scoped capture key and provenance are preserved separately for replay, forwarding and collision checks. A true local observation can mint portable origin identity without Context. Extra tables/mappings and precise replay/conflict validation are necessary; never trust a sender `verified` flag merely because its key matches.
- **C — Content-derived capture fingerprint from ref, root and observed mapping/evidence.** Deterministic transport deduplication without producer IDs, but distinct genuine observations of identical state can collapse, and partially delivered captures can get different IDs when members arrive. This risks contradicting B01-R02's captured-event identity.

Do not select a B01-R03 choice by implication here. A repeated capture token with conflicting content MUST NOT silently rewrite prior Core truth, but the exact origin-key, replay-content grammar, repeated observations and partial-member update/extension protocol are left for the next owner decision. Separate B02 source note-body admission/resources and B03 completeness/scope evidence remain unresolved.

## 8. Scope, references and authorization

- Current owner explicitly chose B01-R02 **B**, after B01-R01 B / ADR 0015 and product scope ADR 0014, maintaining GCTX-M01–M09.
- Git notes primary reference: https://git-scm.com/docs/git-notes (notes ref namespaces, history vs direct-tree roots, annotations stored as blobs).
- Base design stack: ADR 0014 PR #55 → ADR 0015 PR #56 → this design-only ADR 0016.
- Sibling proposed governance PR #52 / ADR 0011 is **not adopted** and does not alter numbering/status or authorize merging.
- Future unresolved work: B01-R03 origin/local capture key and idempotency; B02 provenance-based note-body admission/limits; B03 group and enumeration completeness; GCTX-M10 quarantine retirement/count; exact Core/Context DDL, revision/read fences, Exchange wire, backup pairing and Context GC-03/04.

No Python/SQL/DDL, tests of application runtime, release, deployment, source acquisition, live-catalog migration, merge or authenticated import are authorized. The sixteen counterexamples above are future requirements, **not** executed test evidence.
