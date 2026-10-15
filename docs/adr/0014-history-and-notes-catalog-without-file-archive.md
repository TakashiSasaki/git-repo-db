---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0003-append-only-git-core-and-context-store.md
  - 0004-metadata-only-git-core.md
  - 0013-deterministic-cas-instance-eligibility.md
---

# ADR 0014: A Git history and notes catalog, not a file-content archive

- **Decision ID:** GCTX-S01 (product-scope revision; not the unresolved GCTX-M10 quarantine decision).
- **Owner instruction:** Exclude original-content archival from the product, but continue to store commit/tree/tag/note, and redesign accordingly. Accepted in this conversation on 2026-10-15.
- **Design base:** Unmerged PR #54, commit `0301fcc8aeef427e2b9e2a3197a4ed993dcdf657`. ADR 0011 is reserved by the separate, still-proposed governance PR #52; that proposal is not adopted here.
- **Status:** Accepted product scope and the explicit scope consequences below; concrete schemas, input limits and implementation remain pending. No implementation or merge is authorized.

## Decision

The product catalogs Git history, repository observations, file identities and annotations. It is **not a general-purpose archive or mirror of repository file contents**. Ordinary file-content blob storage is removed as a product capability, not merely disabled by default or retained behind an optional flag.

The phrase "no original-content archival" is applied to repository **file contents**, with the owner's explicit commit/tree/tag/notes preservation exception. It is not interpreted as a ban on storing the bytes needed to preserve those retained metadata entities. In particular, it does not silently reduce notes to a target OID or discard commit/tag messages and signatures.

| Subject | Catalog information retained | Body policy |
| --- | --- | --- |
| Ordinary Git blob used as file contents | Full typed OID, reported type/size and digest claims if actually supplied, source/observation, tree-path relationships | **No ordinary file body archival**, regardless of small size, text/binary classification or compression |
| Commit | Attributes, ordered parents, tree target, authorship/time/message and genuine supplied evidence | Retain exact commit representation when actually acquired and verified; metadata-only observations remain valid without it |
| Tree | Actual entry names/modes/child OIDs, ordering/observation scope and completeness evidence | Retain exact tree representation when acquired; following a tree edge does not authorize storing an ordinary child blob body |
| Annotated tag | Tag object, target type/OID, tagger/message/signature information | Retain its exact representation when acquired; a tag pointing at a blob does not authorize archiving that target body |
| Lightweight tag | Actual tag ref observations and target OID | There is no fabricated tag object or tag body |
| Git note | Notes namespace/ref observation, observed notes root, annotated object OID, note object OID where known, annotation content and provenance | **Retain note content as Git annotation data**, including its actual bytes where available; notes use Git blobs but are an explicit role-based exception |
| PR/Issue/review text | Existing Context-owned state and required evidence | Unchanged; this scope decision does not discard Context text |

Exact representations of retained commit/tree/tag/notes data preserve their existing identity-check and reanalysis guarantees. They are not mandatory prerequisites for first-class metadata-only import under GCTX-M01. When a source supplies only attributes or transformed text, keep those as attributed claims; do not reconstruct and mislabel a canonical raw object.

## Constraints / Do NOT

- Do not keep a generic blob upload, archive, restore-file, mirror, arbitrary raw-object export or full repository checkout capability under a renamed API or optional archive mode. Internal storage is limited by retained domain purpose, not simply by `git_object.type`.
- Do not persist excluded file bodies through `git_text_facts.raw_text`, base64/JSON, compressed/delta payloads, staging, pending Exchange, caches treated as a durable product feature, Search, or Context. Real Provider domain text and required bounded evidence keep their existing meaning; this does not authorize a hidden file replica.
- Do not call intentional file-body exclusion physical corruption, failed preservation, a quarantined instance or an obligation to fetch. There is no physical instance for a never-retained body. Distinguish the absence of a product capability from temporary unavailability of retained metadata.
- Do not infer blob type, size, raw-content SHA-256 or present existence merely from a tree entry or Git OID. Git object OID and `SHA256(raw body)` are different digests. Nominal identity and attributed claims remain separate.
- Do not discard retained metadata bodies, rewrite accepted Core facts, delete old instances, disable integrity triggers, or lower CAS-41 protection on the theory that the application is now a catalog. The no-Core-UPDATE/DELETE/REPLACE/GC rule still applies to data that is actually admitted.
- Do not treat this redesign as permission to purge previously populated catalogs. Fresh-format implementation/rebuild may omit ordinary bodies, but legacy retained data, backups and physical faults need an explicit, separately authorized transition; they cannot silently become "never acquired".
- Do not claim complete Git repository reconstruction, raw file export or source-code full-text search from this catalog. A complete **catalog backup** is not a complete Git mirror.

## Git notes: the essential exception

Git has commit/tree/blob/tag object types; note is a domain role, not a fifth native object type. The Git notes manual states that notes are blobs attached to objects, are obtained through notes refs, can have their own commit history, can use a ref pointing directly to a tree, and can contain binary data. A blanket `type != blob` filter would therefore destroy the requested notes capability. See the primary sources below.

The receiving design must retain an explicit notes association, not just a blob body with a caller-provided `is_note` label. A typed notes capture preserves the source and notes scope: repository UUID, full notes ref name, observed root OID and kind when known, annotated target's full typed OID, note blob OID when known, exact observed entry path and attribution. Actual Git-derived associations and source-reported associations retain their distinct evidence levels. A generic blob upload cannot bypass product scope by setting a flag.

An annotation **target** can be a commit, tree, tag or ordinary blob, and need not itself be present. The note body is retained; an ordinary target blob body is not fetched or archived because it has been annotated. Multiple notes refs may annotate the same OID differently; do not collapse them or attach note text as an intrinsic mutable field of the target commit.

A changing notes ref and later removal/rewrite do not erase previously observed note associations. Record the observed root/scope rather than pretending `(target_oid)` alone is a permanent note identity. An observed notes ref pointing directly to a tree does not require inventing a notes commit. Missing, empty, truncated and partially obtained notes differ.

Notes can contain arbitrary binary bytes, and a single blob OID can be used both as ordinary file content and as a note body. Preserve one nominal OID and separate roles; do not create contradictory duplicate Git identities. Retention in the demonstrated note role does not re-enable a general file archive API. Conversely, it is impossible to guarantee that no retained annotation ever has the same bytes as a repository file. This is a **product-purpose boundary**, not a proof that arbitrary binary data cannot occur in notes.

[ADR 0015 / B01-R01](0015-automatic-git-notes-ref-discovery.md) now fixes **automatic discovery of all observed `refs/notes/*` refs plus explicitly nominated additional ref names**. [ADR 0016 / B01-R02](0016-immutable-notes-ref-capture-observations.md) now fixes **immutable capture-scoped identity for each genuine notes-ref observation**, including distinct repeats of a root and idempotent replay of the same capture. [ADR 0018 / B01-R03](0018-notes-capture-uuidv4-composite-identity.md) fixes a direct `(capture_origin_uuidv4,capture_uuidv4)` composite PK/FK. [ADR 0019 / B01-R04](0019-monotonic-notes-capture-fact-admission.md) fixes monotonic compatible fact/group admission and exact-replay idempotency under a stable capture; B01-R05 contradictory member-report persistence, origin-trust implementation, resource limits and note-body admission proof grammar still require design. Do not invent a maximum size, assume all notes are UTF-8/small, silently truncate an accepted note, or recursively retain every blob reachable from an arbitrary notes-like ref. Preserve the exact captured bytes where claimed; decoded display/search is separately attributed.

## Precise supersession and preserved contracts

| Prior scope | Change in this ADR |
| --- | --- |
| ADR 0003/0004 permit optional archival of any Git object's original bytes | Narrow **new body admission** to retained commit/tree/tag representations and purpose-bound notes content. Ordinary file blob bodies are excluded from product scope |
| GCTX-M01: metadata-only Core must work | Fully preserved, including zero-body commit/tree observations and Context independence; preservation capability does not require every input to supply complete original metadata bytes |
| GCTX-M02/M03 | Preserve one full `(object_format, oid)` registry, attributed scalar claims and observation-scoped relation groups. Add notes associations as a typed Git domain, not a new generic event store |
| GCTX-M04/M05 | Preserve precise receiver-verified canonical values, explicit decoder provenance and conflicting reports. Verification of a commit/tree does not verify a referenced ordinary blob body |
| GCTX-M06/M07 | Preserve immutable byte-admission evidence and actual-output verification **for retained metadata/notes representations**. Remove the ordinary file-body service and whole-repository recovery promise, not integrity checks on remaining data |
| GCTX-M08/M09 | Preserve append-only alternative physical instances, diagnostics and evidence-derived selection **for retained bodies**. These mechanisms are not a new general blob archive |
| GCTX-M10 | Still unresolved. No permanent quarantine, retirement or count-decrement option is selected by this product-scope change |
| CAS-41 | Still applies where retained physical instances exist, including note payloads; intentional excluded blobs contribute no physical instance. Do not relabel existing faults or blindly force the count to zero |
| Coverage/completeness | Separate metadata inventory, retained metadata-body availability, notes coverage and excluded file-content restoration. Existing five-column/latest-observation Coverage semantics are not weakened or reused under a different meaning |
| Search/Exchange/backup | Exchange metadata and allowed retained metadata/notes content only. Back up the actual catalog scope, with both Core and Context for a full Context-containing backup. No general file body reintroduction through transfer or search |

Preserved without reopening: `repository_uuidv4` permanence; Q01-B/Q02-B/Q03-B; NO_INDEPENDENT_PUBLICATION; unaffected PF-P01–PF-P17; known-positive Source associations; Unix epoch microseconds and `_us`; exact OID/byte validation when claimed; append-only Git Core and Context nondependency; Context durability; Operational/Search rebuildability; ADR 0001 development/release policy.

This is a **scoped substantive change**, not a declaration that GCTX-M05–M09 are wholly obsolete. Retaining exact commit/tree/tag/notes content still requires integrity and recovery. Removing their physical-byte protections as well would be a different decision and is not authorized here.

## Consequences and redesign sequence

Ordinary file payload volume, file hydration/retention jobs, file-body Exchange and content-index maintenance can be removed. Remaining work includes history/structure and notes preservation, metadata conflict handling, ref observations, Core/Context separation, retained-metadata integrity, and honest catalog backup/restore. Commit, tree and note data can themselves be large; no unmeasured reduction percentage or final table count is promised.

The [transition plan](../architecture/git-core-context-transition-plan.md) is updated around the new retention boundary. Its first implementation gate is an audited allowlist of domain body admissions and an inventory of ordinary-body dependencies, including indirect staging/search paths. Concrete table/key designs remain proposed until separately fixed. Existing design PRs are not merged or closed by this ADR.

## Validation and open decisions

Future product tests must cover excluded ordinary blob bytes, note-role admission, tag-to-blob and note-to-blob targets, identical file/note OIDs, binary and empty notes, multiple notes namespaces, direct-tree notes refs, ref rewrites, metadata-only input, exact retained-object hashing, malformed/transformed claims, no hidden file text storage, filtered acquisition, Exchange admission, scope-aware backup and retained-metadata corruption/CAS-41. These product tests have not run.

A disposable upstream-Git fixture was run during this design work using Git 2.47.3. It confirmed: commit/tree/annotated-tag native types; note content is `blob`; a notes ref may directly reference a tree; binary note bytes round-trip unchanged; one blob OID may be used as both a file and a note. It did not execute `git-repo-db`, production DDL, migrations, remote collection or any runtime acceptance suite.

Still open: B01-R05 contradictory member-report treatment after ADR 0019 / B01-R04 monotonic compatible-fact admission, exact notes-ref inventory snapshot/fencing and resource limits, detailed attribution/verification grammar, physical table layout and instance keys, GCTX-M10 quarantine lifecycle/count, append-only revision/fences, cross-store transactions and backup pairing, Exchange wire evolution, and GC-03/GC-04 for Context text. Temporary inspection of ordinary file bytes is not required or newly authorized as a product feature; any later verifier-only path must explicitly distinguish observed-and-not-retained evidence from historical retained-byte admission.

## References and work boundary

- [Git notes manual](https://git-scm.com/docs/git-notes), especially DISCUSSION and EXAMPLES: blob representation, namespaces, direct-tree roots and binary notes.
- [Git object model](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects): object identities, tree relations and canonical hashing.
- [git-cat-file](https://git-scm.com/docs/git-cat-file): distinguish object inspection and metadata from body reads.
- Accepted base: PR #54 at `0301fcc8aeef427e2b9e2a3197a4ed993dcdf657`; source tree `d08aea3f977415837ef366236ff9fef721866356`.

This PR changes design Markdown only. It does not implement features, purge data, merge earlier PRs, approve proposed governance PR #52, deploy the documentation site, or authorize authenticated real-source acquisition. No hosted-CI, full-runtime or independent review success is claimed.
