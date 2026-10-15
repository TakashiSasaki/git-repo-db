---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0014-history-and-notes-catalog-without-file-archive.md
  - 0015-automatic-git-notes-ref-discovery.md
  - 0021-direct-semantic-notes-claim-group-keys.md
  - 0009-bounded-byte-admission-and-physical-health.md
---

# ADR 0022: Require receiver-verified structural notes-role evidence before retaining note bodies

- **Decision ID:** B02-R01, the first B02 body-admissibility choice; **owner selected Option A**, accepted 2026-10-15. This does not settle all B02 questions.
- **Direct base:** [PR #62 / ADR 0021](https://github.com/TakashiSasaki/git-repo-db/pull/62), verified HEAD `51093022b50d773b0620fb5bec9b0a7b4a7e1544`, branch `codex/adr-0021-semantic-notes-claim-keys`. Documentation-only direct successor; implementation and merge remain forbidden.
- **Inherited decisions:** ADR 0014–0021, KEY-P01, GCTX-M01–M09 and strictly append-only Git Core. Proposed [PR #52 / ADR 0011 governance](https://github.com/TakashiSasaki/git-repo-db/pull/52) remains unadopted.
- **Implemented baseline:** Three-Store Catalog3 Core Schema 21 / Operational 1 / Search 1. No runtime or DDL change is made by this decision.

## 1. Binding choice: structural role proof plus exact body validation

Before admitting supplied blob bytes as durable Git notes content, the receiver MUST establish both:

1. **Receiver-verified structural notes role:** within the actual immutable notes Capture/ref/root scope, locally checked Git structure establishes the relevant root/tree path and the association of the exact annotated target OID with the exact note blob OID under an explicitly supported notes grammar.
2. **Receiver-verified body identity:** the actual exact note bytes pass the applicable Git object-format/OID/type/size and retained-byte digest/CAS checks under GCTX-M05–M09.

Neither condition substitutes for the other. A valid blob OID proves no attachment to C1; a valid tree entry does not establish that the supplied N1 body matches its OID. Body permission is purpose-bound to the demonstrated notes role; it never extends to an ordinary annotated target's file contents or unrelated tree descendants.

For a captured notes **commit** root, check its relevant commit-to-tree linkage and the necessary tree path. A directly captured **tree** root is supported without inventing a commit. Unknown root kind/path or unverified structural reports cannot stand in for checked linkage. A proof of one mapping need not enumerate every note, acquire the annotated target body, traverse commit history or prove whole-repository closure.

The exact fanout/name/mode interpretation and supported proof encoding remain explicit follow-up contracts. This ADR selects the **required evidence strength**, not a permissive parser for arbitrary trees. Unsupported or malformed entries cannot authorize a body merely because their ref/path looks like notes. Until adequate supported proof exists, preserve only admissible metadata and do not durably retain the unproven body.

## 2. Separate structure, capture attribution and present byte health

The receiver checks content-addressed structure **relative to the captured root**. This does not authenticate the origin UUID, prove that a remote ref pointed to that root at the claimed time, establish current ref freshness, or promote every report in that Capture to truth. Preserve the original source/ref-root qualifications. Origin authentication and snapshot/fencing remain separate; no mandatory live fetch or new trust tier is selected here.

Relevant structural facts must derive from the receiver's own actual Git checks, either performed for this admission or already established by its own immutable checked intrinsic facts under GCTX-M04/M06. Attributed metadata alone, a sender's `verified` bit, an assertion hash or an imported success receipt is not that local evidence. The design must preserve the exact scope and links to the checked structures without inventing missing proof bytes or a full-object report.

Historical checked structure is distinct from current physical availability. Reuse of admitted intrinsic facts does not require a full rehash for ordinary metadata queries. Any operation actually consuming or emitting retained bytes follows M07's relevant current-integrity checks. An old role/admission fact does not claim healthy bytes now, and losing/corrupting previously admitted proof/note bytes cannot be relabeled as normal metadata-only omission.

Strict proof establishes a notes role under supported Git semantics; it cannot promise that a note's bytes never equal a repository file. ADR 0014 already permits one nominal OID to serve both file and note roles. Do not create a generic file retrieval/archive feature merely because those bytes are retained as an annotation.

## 3. Metadata remains admissible without note bodies

An API/Exchange source may report K, `refs/notes/review`, C1→N1 and supply a correctly hashed N1 body without the needed checked root/tree relationship. Keep genuinely identifiable source-attributed metadata under ADR 0018–0021, including conflicts and unknown qualifications; **do not admit that body's durable payload on the strength of the report alone**.

- A qualified typed source report, trusted-provider designation, selected ref, `is_note=true`, decoder/module identity or caller assertion is insufficient by itself. Options B and C from ADR 0021 are not adopted.
- No durable unproven-body holding area in Core, Context, Operational jobs, pending Exchange, quarantine, Search, raw-text facts, compressed/base64 fields, retry logs or long-lived caches may bypass the product boundary. Bounded incidental transport buffers remain distinct from durable product retention; their concrete lifetime/resource protocol is not selected here.
- Do not mark withheld/unacquired bodies as physical corruption, quarantine instances or retained-byte loss. Do not infer an empty note, absent remote association or complete inventory from body nonadmission.
- Later sufficient proof may support a new immutable role/admission fact and exact body acceptance. Preserve prior reports and the actual Capture pair; a delivery retry is not a new capture and cannot UPDATE a claim or extend a frozen group.
- Empty and binary notes remain exact binary annotation content. No destructive decoding, trimming, normalization, silent truncation, fabricated raw serialization or UTF-8 prerequisite is allowed.

## 4. Atomic admission, Exchange and historical preservation

The accepted role linkage, exact representation/physical association and required checked intrinsic structure must form a consistent, bounded immutable admission unit under M06. Existing checked dependencies may be referenced; do not expose a role-authorized body while its necessary evidence links are missing, or require all metadata reports for the Capture to be admitted in one generic batch.

Use ADR 0021's **direct semantic composite references** to the actual Capture UUIDv4 pair, typed association slot/value and genuine provenance. Receiver-local checks are separate scoped immutable evidence, not a `verified` update to the source report, new storage-only `role_proof_id`, mutable allow flag, generic Publication or per-success-attempt ledger. Concrete evidence keys/DDL remain follow-up work under KEY-P01.

Exchange preserves the actual Capture/ref/root/target/note and provenance. A receiver must establish its own pertinent structural and body checks before new local body admission; sending historical proof can provide inputs, never imported local authority. Metadata-only Exchange works without bodies, Context or fake payloads. Git-only and paired full backups preserve the respective authoritative role/admission evidence and retained bodies; no new cross-store pairing protocol is selected.

Later ref deletion/rewrite, source distrust, a different resource limit or a competing report does not revoke historical admitted Core facts or authorize deleting note/proof bytes. Preserve ordinary conflict projections, physical diagnoses and immutable alternative copies under M08/M09. This decision authorizes no legacy catalog extraction/purge or Core GC, and does not decide GCTX-M10/CAS-41 count changes.

## 5. Worked examples

| Input/evidence | Required result |
| --- | --- |
| API reports C1→N1; only N1's bytes/OID are checked | Keep eligible attributed report, withhold durable N1 body; no fake quarantine or completeness |
| Relevant captured commit/tree path is locally checked and establishes C1→N1; N1 body checks pass | Role evidence threshold is met for N1; retain exact body only through valid atomic admission and still-unsettled applicable resource rules |
| Captured root is directly a tree; relevant mapping/body checks pass | Same role threshold; no fabricated notes commit |
| Relevant one-note path is checked, other subtrees and C1 body are absent | Do not require whole-list/target-body acquisition; do not infer full inventory or remote absence |
| Source reports C1→N9 but checked structure proves C1→N1 | Preserve attributable alternatives; only the precisely checked association supports structural role proof. Checking N9's blob alone cannot repair its missing mapping proof |
| N1 is both an ordinary file blob and a structurally demonstrated note | One nominal typed OID, purpose-bound note retention; no general file archive/export capability |
| A previously retained note becomes physically corrupt | Preserve historical role/admission and durable diagnosis; M07–M09/CAS-41 apply, never reclassify as intentionally withheld bytes |

## 6. Reconciliation with accepted design

| Decision | Preservation/refinement |
| --- | --- |
| ADR 0014 / GCTX-S01 | Refines its notes exception with mandatory receiver-checked structural role evidence; ordinary file bodies remain excluded |
| ADR 0015 / B01-R01 | All observable notes refs plus explicit additional refs remain discoverable; ref selection never grants body permission |
| ADR 0016/0018 / B01-R02/R03 | Original immutable Capture with actual two-UUIDv4 key and source qualifications, repeated genuine observations distinct; no capture-per-retry |
| ADR 0017 / KEY-P01 | Actual semantic composite PK/FK, no extra body-role/claim/proof surrogate |
| ADR 0019/0020 / B01-R04/R05 | Monotonic compatible facts and separately atomic competing reports remain; no overwrite, group union or report-based byte permission |
| ADR 0021 / B01-R06 A | Full semantic assertion/group keys, exact replay and genuine provenance preserved; identity does not itself prove role |
| GCTX-M01 / ADR 0004 | Metadata-only Core with zero bodies, no Context and no mandatory fetch remains fully supported |
| GCTX-M02 / ADR 0005 | Shared full typed OID, distinct roles/evidence; identity alone implies no bytes/type/size/membership |
| GCTX-M03 / ADR 0006 | Coherent typed groups and actual scope/order remain atomic and immutable; no fabricated completeness |
| GCTX-M04 / ADR 0007 | Locally checked intrinsic mapping supports only that field/scope, retaining historical alternatives; no winning source/decoder |
| GCTX-M05/M06 / ADR 0008/0009 | Core owns Git checks and bounded immutable admission evidence; Context owns Provider assessment, Operational owns work |
| GCTX-M07 / ADR 0010 | Byte-dependent output checks the actual selected/emitted bytes; role proof is not healthy-now evidence |
| GCTX-M08/M09 / ADR 0012/0013 | Immutable copies, durable fault evidence and evidence-derived candidate selection preserved; no repair overwrite/cleanup |
| Other fixed decisions | Strict Core INSERT-only/no UPDATE/DELETE/REPLACE/GC; permanent repository UUIDv4, known-positive Source, five-column/latest-observation Coverage, Unix epoch microseconds, NO_INDEPENDENT_PUBLICATION, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, durable Context, paired full backup and ADR 0001 |

No prior accepted decision needs reversal. Resource policy/numbers, exact supported notes grammar/proof format, source authentication, B03 completeness, GCTX-M10 quarantine/count, physical DDL/wire/fences/backup pairing and Context GC-03/04 remain open. Role proof alone is not a claim that every operational admission prerequisite has been finalized.

## 7. Future adversarial cases (NOT executed product tests)

1. Correct N1 body and an attributed API mapping without checked structure: metadata accepted when eligible, body withheld with no durable hidden staging.
2. Sender `verified=true`, trusted source, notes ref prefix and decoder version each fail to replace local role proof.
3. Correct captured commit-to-tree/path and note checks satisfy the role threshold; direct-tree root works without an invented commit.
4. Unknown/malformed/unsupported path or mode fails role admission without erasing usable metadata or guessing missing structure.
5. A checked one-note path with missing siblings/target body never claims full notes inventory or whole-DAG closure.
6. Wrong note type/size/OID/digest, proof-link mismatch, collision and interrupted admission cannot expose a partly verified body.
7. Empty/binary note bytes remain exact; ordinary annotated target bytes remain excluded.
8. Same file/note OID keeps one nominal identity and explicit purpose; generic file archive remains unavailable.
9. Source report N9 and locally checked N1 retain truthful alternatives; checking N9 body alone proves no attachment.
10. Reverse/repeat Exchange rechecks required local authority and keeps original semantic identity; no new capture/claim/success event solely for retry.
11. Later actual proof permits immutable scoped additions without PK rewrite, old-group mutation or invented source evidence.
12. Historical checked intrinsic evidence is distinct from current byte health; corrupt retained note/proof bytes receive durable physical diagnosis, never a missing-by-policy label.
13. Ref rewrite/deletion or a later lower budget cannot delete admitted Core data or silently decrement CAS-41 counts.
14. Core-only metadata backup/restore remains valid without Context/bodies; full Context backup still requires both authoritative stores.

## 8. Next owner blocker: B02-R02 resource-limit policy (OPEN)

How should body size, total acquisition work and proof traversal be bounded? A structurally valid note can be huge, and many valid notes can exhaust resources even when each is small. This is a **new unaccepted choice**; no limit or default is fixed here.

Illustrative workload only: a valid 20 MiB note, 10,000 smaller notes and a proof traversal exceeding the caller's budget. Illustrative policy values such as 8 MiB per note or 128 MiB per operation are examples, **not adopted defaults**.

- **A — Configurable finite admission/work budgets (recommended):** explicit bounded defaults for individual raw note size, total operation bytes/work and proof traversal; allow a deliberate configuration increase followed by retry. At a limit, keep independently admissible metadata/complete atomic units, withhold the oversize/unproven body or incomplete unit, and report the actual stop/availability. **Pros:** adjustable resource protection without truncation; large notes can later be admitted under a sufficient budget. **Cons:** configuration and reproducible retry accounting must be defined; exact units/defaults and reuse counting need later agreement.
- **B — Fixed product-wide hard caps:** use the same finite limits with no per-operation override. **Pros:** predictable implementation and resource envelope. **Cons:** valid large notes remain permanently outside that format's limits until the product policy changes; a hard cap is not Git invalidity.
- **C — No product-level note-size cap, streaming with operational cancellation/failure:** preserve any proven exact note if the available system resources allow completion. **Pros:** no arbitrary size cutoff for valid notes. **Cons:** weaker predictable storage/work protection, and streaming alone does not bound total traversal or disk exhaustion; failures/retries still need truthful reporting.

Under every option, never silently truncate an exact note, represent a stopped scan as complete/empty, store an unproven body as a retry artifact, delete previously admitted Core bytes, or count deliberate nonadmission as physical corruption. B03 still decides completeness evidence; exact numeric budgets, charging shared/replayed content, proof grammar and acquisition protocol are not chosen by this comparison.

## 9. Authorization and verification boundary

The owner selected **B02 Option A**, recorded as **B02-R01 A** only. Options B/C are historical unselected alternatives; B02-R02 is a separate next decision. This PR changes design Markdown and current agent/index/transition guidance only.

No implementation, Python/application source, SQL/DDL/schema label, executable product test, workflow/dependency, live source acquisition, real-catalog mutation/migration, deployment, release, merge or auto-merge is authorized. Static documentation checks and hosted documentation/development CI are not runtime acceptance of the target. The cases above remain future requirements; no independent review or execution success is implied by listing them. No reusable skill is added for this individual design choice.
