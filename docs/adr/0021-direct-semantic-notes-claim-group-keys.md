---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0017-domain-keys-without-storage-surrogates.md
  - 0018-notes-capture-uuidv4-composite-identity.md
  - 0019-monotonic-notes-capture-fact-admission.md
  - 0020-immutable-competing-notes-member-claims.md
  - 0006-field-claims-and-observation-scoped-relations.md
---

# ADR 0021: Direct semantic composite keys for Git notes claims and coherent groups

**Current post-corruption override:** [ADR 0026 / GCTX-M10](0026-stop-salvage-restore-merge-after-corruption.md) requires stopping ordinary catalog operation, preserving the suspect source read-only, serializing salvage candidates, restoring a verified backup into a fresh destination and merging only revalidated admissible data. Prior post-fault metadata service, same-DB failover, known-corrupt normal backup/restore and references to M10 as pending are historical in that scope. Ordinary sound-catalog rules and unrelated open work remain. No implementation or merge is authorized.

**Subsequent accepted refinement:** [ADR 0022 / B02-R01 A](0022-receiver-verified-notes-role-admission.md) requires receiver-verified relevant notes structure plus exact body checks before durable note-body retention. The B02 comparison below is historical; B02-R02 finite configurable budget policy is fixed by ADR 0023; B02-R03 actual-work accounting is fixed by ADR 0024; B02-R04 cumulative request scope is fixed by ADR 0025; remaining budget details are engineering work, while exact proof grammar and B03 completeness remain unfinished; GCTX-M10 recovery is fixed by ADR 0026.

- **Decision ID:** B01-R06; **owner choice: Option A**, accepted 2026-10-15.
- **Direct base:** [PR #61 / ADR 0020](https://github.com/TakashiSasaki/git-repo-db/pull/61), verified HEAD `d12e54b114b48167898ee6e9789d0ec9d63b60fe`, branch `docs/adr-0020-competing-notes-member-claims`. This is its direct documentation-only successor, not a sibling or an implementation PR.
- **Inherited decisions:** ADR 0014–0020, KEY-P01 and GCTX-M01–M09. Proposed [PR #52 / ADR 0011 governance](https://github.com/TakashiSasaki/git-repo-db/pull/52) remains unadopted.
- **Implemented baseline:** Three-Store Catalog3 Core Schema 21 / Operational 1 / Search 1. Acceptance of this design is neither implementation nor merge permission.

## 1. Binding decision

Identify each eligible immutable notes member claim and coherent relation-group assertion **directly by its domain-semantic composite primary key**, and use corresponding full composite foreign/reference keys in SQL, Exchange and backup. The key contains the original **actual Capture UUIDv4 pair**, typed claim/relation slot, the **asserted value**, and **genuine original provenance/evidence coordinates**. For a coherent group, the asserted value includes its entire immutable typed membership and asserted scope.

Do not substitute a `claim_id`, `group_id`, `fragment_id`, `conflict_id`, extra random UUID, local integer, assertion digest, or opaque concatenated row token as the authoritative PK/FK. A hash/index may accelerate a lookup only if full semantic equality remains authoritative and collisions cannot merge claims. The rejected hash-key and extra occurrence-ID alternatives from ADR 0020 do not become acceptable by calling them natural keys.

The existing `(capture_origin_uuidv4,capture_uuidv4)` is preserved, with **both UUIDs version 4**, exactly as accepted by ADR 0018. This ADR does not mint per-claim/group UUIDs or replace permanent `repository_uuidv4`, nominal `(object_format,full_oid)` identity, or separately justified physical-copy identity.

## 2. Semantic key and equality contract

The following is **conceptual typed tuple notation, not SQL/DDL or a selected wire encoding**. Each descriptor denotes its full recoverable domain components, never a hidden surrogate or a hash standing in for them. Relation-specific schemas must expand/use these components directly and preserve their equality.

| Unit | Direct semantic components |
| --- | --- |
| Capture `K` | `(capture_origin_uuidv4,capture_uuidv4)`; immutable repository/ref/root/source binding follows ADR 0018/0020 |
| Individual claim | `(K, typed_subject_and_relation, actual_member_or_field_slot, asserted_typed_value, original_provenance)` |
| Coherent group | `(K, typed_subject_and_relation, actual_group_scope_or_evidence_boundary, asserted_group_value, original_provenance)` |
| Group member reference | Full owning group composite, plus that member's actual typed slot/value and any genuinely distinct member provenance; no shorter authoritative group row ID |

**Slot:** preserve the actual subject/target full typed OID, relation kind, namespace through K, and raw path/name or reported ordinal **only where genuinely evidenced and relevant**. A full target OID may identify a reported target-to-note mapping slot even without a raw path. Different refs/captures are different scopes. Do not invent offsets, positions, filenames, fragment numbers or an absent root to complete a key. Do not interpret a sender-local database ID as an evidence coordinate.

**Value:** include the complete asserted typed value, such as note `(object_format,full_oid)` with its assertion kind. Equal text alone, equal root alone, or equal note OID alone does not identify an attributed claim. Preserve raw byte distinctions for Git paths/names and exact asserted byte/text distinctions; do not trim, Unicode-normalize or lossily decode identity-bearing values. This is not permission to store an ordinary file body as a key component.

**Provenance:** use the actually supported original issuer/source observation and evidence coordinates and, where interpretation produced the assertion, its real decoder/module/version evidence. Keep original attribution on onward Exchange; receiver receipt time, arrival order, transfer route, retry count and forwarding sender are not new assertion provenance. Do not demand a mandatory Context Source registration, original API response, raw Git body, byte offset or new all-attempts ledger. A locally computed index/position is not source evidence. An actual recorded observation time may be evidence, but never a fabricated key salt or canonical winner.

**Missing information:** typed `unknown`, omitted/not-reported, explicit null where meaningful, known-empty and known value are distinct semantic states, not dummy values of the underlying domain. Their lossless tags do not assert a fake path/ordinal. Do not rely on nullable SQL uniqueness behavior to permit duplicate replays or use `0`/empty bytes/a sentinel UUID as an unknown domain value. If genuine available subject/slot/scope/provenance still cannot identify a proposed member/group, leave that keyed assertion unadmitted or retain only an independently identifiable truthful partial observation. Do not manufacture another event ID or collapse unrelated unidentified reports. Protocol/DDL must make this failure explicit without durably staging excluded file bodies.

**Equality:** two assertions are exact replays only when every semantic key component agrees after lossless typed representation, including value, original provenance, group scope and membership where applicable. Equivalent transport packaging does not create another claim. A later genuine independent observation retains its new Capture and/or actual evidence, even if its note OID/text agrees. Source authentication is a separate unresolved contract; putting a claimed coordinate in a PK does not authenticate it.

### 2.1 Coherent groups are immutable complete assertion values

The group value is the whole **asserted** finite typed membership together with the assertion's actual ordering/fragment/scope qualification. It is not proof of full notes inventory. Preserve witnessed order where order belongs to the relation, multiplicity where meaningful, and unknown order without invented contiguous ordinals. Transport reordering of a semantically unordered collection does not change its identity; changing genuinely asserted order does.

For example, `G1={C1→N1}` and `G2={C1→N1,C2→N2}` under K are **different immutable group assertions**, even if their source/evidence boundary overlaps. G2 is not an INSERT of C2 into G1. A group and all its members become visible atomically, and an exact replay deduplicates the whole assertion. A partial group, a supported known-empty group and a claimed full group cannot accidentally share an identical key just because their listed members coincide. Whether a claimed full/empty scope has adequate proof remains **B03**.

Group identity must include the full value and real evidence boundary needed to distinguish those assertions. A unique constraint on `(K,relation,source)` alone is insufficient; a content hash, decoder-generated ordinal, random group UUID or generic group seal is not a shortcut. The final physical representation must demonstrate that it can express the full composite and matching child references without recursive self-identification, partial visibility, mutable group extension or substituting a digest as authority. Concrete bounded encodings, table layout and resource limits remain design/implementation work under this fixed choice; an unsupported representation must be reported rather than silently switching to Option B/C.

## 3. Replay, conflict and identity misuse are different comparisons

The **replay PK** includes asserted value and provenance. The **conflict comparison scope** compares eligible reports for the same actual K/subject/relation/member slot while allowing competing values and independent provenance to differ. Therefore different PKs do not by themselves mean either compatible facts or a conflict. Read projections must examine the actual semantic slots and group qualifications, not merely key inequality.

| Input under K | Required outcome |
| --- | --- |
| `(slot C1, value N1, actual evidence E1)` again, including through another Exchange route | Same full semantic key; idempotent, no new capture/claim/group |
| `(slot C1, value N1, genuinely distinct evidence E2)` | Separate attributed assertion; agreement is not independent verification |
| `(slot C1, value N9, genuinely attributable evidence E3)` | Separate immutable alternative; compare C1 slot and derive explicit unresolved conflict with N1 under ADR 0020 |
| Same supposedly immutable evidence coordinate reports two different values | A different value alone does not establish independent attribution. If the actual evidence cannot genuinely identify both assertions, fail closed with an identity/provenance diagnosis; never forge E2 or mutate E1. Only genuinely identifiable alternatives qualify under ADR 0020 |
| Additional compatible C2→N2 | New immutable fact/coherent group under K under ADR 0019; no mutation/union of G1 |
| Same Capture UUID pair rebound to another immutable repository/ref/root/origin | Fail closed as identity/provenance misuse; adding the new root to a claim key cannot legitimize it |
| Same root, independent genuine Capture K2 | Distinct capture and assertions under ADR 0016/0018, not an exact replay |

An incomplete member without enough actual slot/evidence is **not** automatically a second independently attributable report. Nor may two unrelated unknown slots be declared conflicting solely because their unknown tags match. The admissible partial assertion must retain its honest scope; uncertain comparability remains uncertain. Later unknown-to-known information is a new immutable assertion/group, not a rewrite of the earlier key.

Receiver-local verification is **separate immutable evidence referring to the exact checked assertion/scope**, not a mutable `verified` key component or a re-key of an earlier report. Under GCTX-M04, checking the exact notes root/tree-to-target mapping may support that checked canonical relationship while reports remain accessible. Verifying N1's blob OID alone does not prove C1→N1, notes-role admissibility, inventory completeness or healthy bytes now.

## 4. Consistency with all inherited decisions

| Accepted decision | Preserved constraint |
| --- | --- |
| ADR 0014 / GCTX-S01 | History/structure/notes catalog; no ordinary file-body archive, including in keys, evidence, Exchange staging or Search. ADR 0022 / B02-R01 A fixes required receiver-verified structural role evidence; B02-R02 finite configurable budget policy is fixed by ADR 0023; exact proof grammar remain open |
| ADR 0015 / B01-R01 | All observable `refs/notes/*` plus explicit additional refs; selection alone is not notes proof |
| ADR 0016 / B01-R02 | Genuine repeated observations remain separate; replay preserves original capture |
| ADR 0017 / KEY-P01 | Direct semantic PK and matching full FKs; no storage-only row surrogate across stores |
| ADR 0018 / B01-R03 D-1 | Actual origin UUIDv4/capture UUIDv4 pair; no per-claim ID and no repository/Provider/Context-ID substitution |
| ADR 0019 / B01-R04 A | Compatible facts append under K; exact replays deduplicate; old facts/groups never mutate |
| ADR 0020 / B01-R05 A | Genuinely attributed conflicting reports coexist as alternatives; derived conflict; Capture identity misuse rejected |
| GCTX-M01 / ADR 0004 | Metadata-only, zero-body, Context-independent import/query/Exchange remains valid; no mandatory fetch or byte offset |
| GCTX-M02 / ADR 0005 | One full typed nominal OID; identity alone proves no type/size/bytes/membership |
| GCTX-M03 / ADR 0006 | Scalar claims and typed coherent groups preserve actual order, scope and atomic visibility; no partial-group union |
| GCTX-M04 / ADR 0007 | Relevant local intrinsic verification supports only checked fields/groups; retain reports, no arrival/source/decoder winner |
| GCTX-M05 / ADR 0008 | Core owns Git checks, Context Provider assessment, Operational jobs; key provenance does not create a Core→Context dependency |
| GCTX-M06 / ADR 0009 | Bounded immutable historical admission proof for role-allowed exact bytes; original report key is not a verification receipt |
| GCTX-M07 / ADR 0010 | Byte-dependent outputs check the selected/emitted bytes; metadata equality is not physical health |
| GCTX-M08 / ADR 0012 | Distinct immutable physical copies and diagnoses remain separate from claims; no overwrite/cleanup |
| GCTX-M09 / ADR 0013 | Evidence-derived eligible physical candidates and actual output checking remain; semantic key sorting selects no canonical metadata winner |
| ADR 0003 and other fixed rules | Strict application-level Core INSERT-only, no UPDATE/DELETE/REPLACE/GC; permanent repository UUIDv4, known-positive Source, five-column/latest-observation Coverage, Unix epoch `_us`, NO_INDEPENDENT_PUBLICATION, Q01-B/Q02-B/Q03-B, unaffected PF-P01–PF-P17, durable Context, paired full backup, ADR 0001 |

No contradiction requiring a prior decision reversal was identified. Wide keys and lossless typed equality are accepted costs, not exemptions from KEY-P01. Metadata disagreement does not create physical corruption or alter CAS-41 counts. GCTX-M10 quarantine disposition/count, origin trust, exact DDL/wire/fences/backup pairing and Context GC-03/04 remain unresolved.

## 5. Future adversarial acceptance cases (NOT executed product tests)

1. Exact E1 replay through reverse/repeat/forward Exchange deduplicates with the full original key despite changed transport packaging.
2. Same C1→N1 with real E2 remains independently attributed; a new genuine K2 at the same root is not merged with K.
3. C1→N1/E1 and C1→N9/E3 coexist with explicit conflict in either arrival order, while neither becomes verified by agreement/count.
4. Capture reuse with inconsistent immutable repository/ref/root/origin fails closed before member-key comparison.
5. G1 and expanded G2 have different whole-group keys; partial/full/known-empty scope assertions stay distinct; no UPDATE or silent complete union.
6. Group/member visibility is atomic on error, crash, concurrency and retry; matching full composite references cannot attach a member to another group.
7. Actually reported order and raw path bytes survive Exchange exactly; unknown order/path never creates fabricated ordinals or normalized-name collisions.
8. Unknown, omitted, explicit null, known-empty, zero and empty byte values follow their typed meanings and cannot evade replay uniqueness.
9. Insufficient real identity cannot be repaired with a UUID/hash/receiver clock or falsely described independent source evidence.
10. Two unidentified slots are not declared the same logical conflict just because both lack a path; a genuinely known target slot remains usable without raw bytes.
11. Local checked relationship evidence is separate; receiving `verified=true` or verifying only a note blob cannot verify its target attachment or authorize ordinary file bodies.
12. Same-coordinate inconsistent values retain genuine attribution or fail explicitly when unidentifiable; no source-coordinate fabrication or capture rebinding.
13. Hash/index collisions trigger full component comparison; no digest-only authoritative PK/FK or exported sender-local row key.
14. Core-only metadata backup/restore/Exchange preserves keys and alternatives without Context, Git bodies or mandatory API originals; Operational/Search rebuild loses no authoritative evidence.
15. Same file/note nominal OID stays one identity, but no body is retained by a claim key or generic upload flag. ADR 0022 / B02-R01 structural role evidence and exact body checks remain required.
16. Key design cannot clear a damaged physical instance, reduce CAS-41 quarantine counts or weaken M06–M09 byte checks.

## 6. Historical B02 role-admissibility comparison; Option A now accepted by ADR 0022

**Which evidence is sufficient to retain supplied blob bytes in the Git notes role?** This is separate from accepting source-attributed metadata, checking a blob's own OID, and B03 list completeness. The owner subsequently selected **A**, fixed as **B02-R01 by ADR 0022**. The unselected B/C options below remain historical, not body-admission alternatives still available to implementers.

Example: K reports `refs/notes/review`, target C1 and note N1. N1's own bytes/OID can be checked, but the receiver has not checked a Git notes root/tree path establishing C1→N1. Is the reported association enough for durable retention? Ordinary target file bytes remain excluded under every option.

- **A — Require receiver-local structural notes-role proof (recommended):** retain the body only after locally checking the relevant captured root/tree-to-target-to-note relationship under an explicitly supported notes grammar, plus the body's own exact type/size/OID/digest checks. A commit root needs its relevant commit/tree linkage; a direct-tree root does not require an invented commit. A partial but sufficient path proof need not imply full notes enumeration or target-body possession. Until proof is available, keep eligible attributed metadata without a durable pending blob body. **Pros:** concrete purpose gate, no arbitrary file archive via a report flag, consistent receiver-local evidence boundary. **Cons:** needs relevant Git metadata/proof bytes and grammar; metadata-only API reports cannot alone retain supplied body bytes.
- **B — Accept a sufficiently attributed typed source report as role evidence:** require actual Capture/ref/target/note/provenance and locally validate the supplied blob, retaining the association as reported/unverified. **Pros:** permits notes-body preservation from API/Exchange reports without root/tree proof. **Cons:** a false typed report could admit arbitrary ordinary file data; source authenticity/eligibility must be specified, and metadata attribution is not structural proof. A simple caller `is_note` flag is insufficient even here.
- **C — Two explicitly distinguished evidence tiers:** A by default; separately allow B only for owner-selected authenticated/trusted sources and mark the admitted role basis accurately. **Pros:** supports selected providers while retaining explicit evidence levels. **Cons:** introduces trust configuration, provenance-preserving Exchange and policy-change questions; it cannot make source assertions receiver-verified or delete already admitted Core facts on later distrust.

Accepted **A / ADR 0022** fixes the required strength of role evidence only. It does not fix exact fanout/path/mode grammar, numeric limits, concrete counters, binary decoding, completeness B03, physical GC or retention cancellation. Empty/binary notes, unknown/unavailable targets, same-OID file/note reuse and direct-tree roots must remain expressible. Resource-limit behavior must report honest metadata/availability and never silently truncate or disguise durable file-body staging. **ADR 0023–0025 / B02-R02–R04 A** fix finite configurable limits, actual-work charging and cumulative explicit-request scope; numeric defaults and concrete counters/resume mechanics are engineering work, not owner blockers or lifetime Capture quotas.

## 7. Authorization and verification boundary

Owner accepted **B01-R06 A** after B01-R01 B, R02 B, R03 D-1, R04 A and R05 A. This ADR fixes that design; the owner subsequently selected **B02-R01 A**, fixed separately by ADR 0022. Prior alternatives remain historical; none is implemented.

Only Markdown design/agent/index/transition guidance changes are authorized. No Python/application code, SQL/DDL, schema labels, executable tests, workflows, dependencies, source acquisition, real-catalog mutation or migration, deployment, release, implementation, merge or auto-merge is authorized. Static document checks and independent design review are distinct from the future product cases above; no runtime or hosted-CI success is implied. No reusable procedural skill is added for this one design choice.
