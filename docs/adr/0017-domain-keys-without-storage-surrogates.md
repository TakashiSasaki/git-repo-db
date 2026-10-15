---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0005-common-oid-identity-with-attributed-metadata.md
  - 0016-immutable-notes-ref-capture-observations.md
  - 0012-append-only-multiple-cas-physical-instances.md
---

# ADR 0017: Prefer domain primary keys; prohibit storage-only surrogates

**Current refinement:** [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md) accepts direct semantic composite claim/group keys using the actual Capture UUIDv4 pair, typed slot, asserted value and genuine provenance, without surrogates. B02-R01 structural role-evidence strength is fixed by [ADR 0022](0022-receiver-verified-notes-role-admission.md); B02-R02 configurable finite budget policy is fixed by [ADR 0023](0023-configurable-finite-notes-resource-budgets.md); B02-R03 actual-work accounting is fixed by [ADR 0024](0024-actual-notes-resource-work-accounting.md); [ADR 0025 / B02-R04 A](0025-cumulative-request-budgets-and-scoped-blockers.md) fixes cumulative work within one explicit acquisition request across continuation/resume/retry. Counter units, defaults and resume mechanics are agent-owned engineering work, not further owner blockers. Other proof/completeness/trust/DDL work remains separately scoped; GCTX-M10 blocks the affected disposition/count/backup-manifest contract. Earlier alternatives below retain their historical scope.

- **Decision ID:** KEY-P01 (repository-wide primary/foreign-key policy).
- **Owner directive:** For the entire future design, do not introduce surrogate keys. Prefer real natural/domain identities and their composite keys over extra row identifiers.
- **Status:** Accepted owner design policy on 2026-10-15. Final physical DDL and code are not implemented. The semantics of established domain identities must not be silently changed by choosing a primary-key shape.
- **Direct parent:** Unmerged [PR #57 / ADR 0016](https://github.com/TakashiSasaki/git-repo-db/pull/57) HEAD `896fbee08ed186897069558bc70d7f49a59325bb`, on the B01 notes design stack. Proposed governance PR #52 / ADR 0011 is a sibling and remains unapproved.
- **Baseline:** Current Three-Store Core Schema 21 includes many surrogate-ID columns, which are an implementation baseline to redesign, not binding final-format choices.

## 1. Binding repository-wide key policy

**Do not add a column whose only purpose is to replace the actual domain identity with a shorter/local database row ID.** The primary key of a durable domain entity/relationship must directly express its established semantic identity, including all genuinely needed namespace/source/observation components. Use matching composite foreign keys rather than inventing another PK merely for FK convenience.

Apply this rule across **Git Core, Context, Operational and derived Search integrations**. Changing stores does not create a license for database-only surrogate IDs.

Examples of prohibited final-target patterns when the actual domain key is known:

- `git_object_id INTEGER PRIMARY KEY` plus `UNIQUE(object_format,oid)`, rather than the actual composite Git identity.
- `notes_ref_capture_row_id INTEGER PRIMARY KEY` plus `UNIQUE(capture_origin_identity,capture_identity)`.
- `association_id UUID PRIMARY KEY` for one unambiguously identified relationship with a meaningful composite key.
- A mutable `current_*_id` pointer, a receiver-only mapping ID, or SQL auto-number used as stable authority in Exchange, merely because its owner/domain key spans multiple columns.

**Preferred conceptual keys** (exact DDL/types still require follow-up):

| Subject | Domain identity for PK/FK |
| --- | --- |
| Git nominal object | `(object_format, full_oid)` |
| Notes namespace/ref | Permanent `repository_uuidv4` with full exact ref name and real source scope where necessary |
| Notes ref capture | **Now fixed by [ADR 0018 / B01-R03](0018-notes-capture-uuidv4-composite-identity.md)**: direct `(capture_origin_uuidv4, capture_uuidv4)` composite PK/FK; compatible same-capture fact admission fixed by [ADR 0019 / B01-R04](0019-monotonic-notes-capture-fact-admission.md); B01-R05 competing member report preservation fixed by ADR 0020; B01-R06 direct semantic keys fixed by ADR 0021 |
| PR document | Existing accepted `(change_request_id, kind, provider_change_request_document_id)` |
| Source ↔ repository membership | Meaningful Source and repository identifiers in a composite key |
| Notes mapping/member | Capture composite key, relation kind and genuinely evidenced member identity/order/path/fragment as applicable |
| Retained physical CAS copy | The actual distinguishing **physical-instance domain identity**, not a second storage-only ID of the same copy |

Composite FK width is an accepted cost. A `WITHOUT ROWID` table may suit some SQLite composites, but is not a universal mandate. Internal SQLite/FTS row numbering or a disposable implementation index is not a **durable domain identity** and must never leak into authoritative PK/FK, Exchange or backup meaning.

No arbitrary ordinal, missing root, placeholder, unstable URL/name, first-seen clock or incoming sender-local SQLite key may be fabricated as a semantic PK component. If the domain identity is unknown, admit a truthful typed partial observation under its actual identity-bearing capture or leave the record unadmitted until adequate identity is available; do not cure the lack of identity with a new local auto-increment.

## 2. Explicitly preserve genuine issued domain identities; report their tension

**Terminology matters:** a producer-generated UUID or event token can itself be called a surrogate key in database theory, even if it is globally stable. Calling it a `domain ID` does not magically make a synthetic identifier a natural key.

However, previously accepted architecture requires **distinct entities that cannot be identified by content alone**:

- Owner-fixed permanent `repository_uuidv4` distinguishes the same repository across names/URLs/provider changes. The no-extra-surrogate policy must not reopen or replace this settled identity.
- B01-R02 / ADR 0016 requires different genuine observations K1 and K2 of the **same ref and root** to remain distinct, while a replay of K1 is idempotent. A content/root hash or `(repository,ref,root)` cannot distinguish them. Some genuine capture-occurrence identity (or independently evidenced source event coordinate) is essential.
- GCTX-M08 / ADR 0012 requires separate I1 and I2 physical copies **of identical CAS content**, independently diagnosable/quarantinable. The shared SHA-256 digest cannot identify each physical copy.
- Stable external Provider IDs, already approved domain UUIDs, real source event coordinates and physically distinct instance identifiers can be meaningful **entity identities**. They are not permission to add a **second** local DB row surrogate just for convenient joins.

This ADR fixes the owner's default prohibition on **additional storage-only surrogate keys**, without claiming that all issued domain identities are mathematically natural keys or granting unlimited new generated IDs. Each new opaque capture/instance identity must be justified by the accepted domain distinction, its true issuer, uniqueness, portability and trust; its exact issuance is not decided here.

If the owner's intended prohibition also literally forbids **all newly generated/issued occurrence IDs**, that stronger reading conflicts with the owner-fixed permanent repository UUID and the B01-R02/M08 distinct-observation/copy requirements. Such a conflict MUST be surfaced and explicitly resolved before implementing dependent schemas; do not conceal it by relabeling arbitrary UUIDs as natural.

## 3. Reconciliation with current owner decisions

| Decision | Preserved/changed detail |
| --- | --- |
| ADR 0014 and B01-R01 / ADR 0015 | History/tree/tag/notes catalog, no ordinary file blob archival; auto-discover observable `refs/notes/*` and explicitly nominated notes refs |
| B01-R02 / ADR 0016 | Preserve immutable, separate genuine captures and idempotent replay of the *same* capture. [ADR 0018 / B01-R03](0018-notes-capture-uuidv4-composite-identity.md) now fixes D-1: direct origin UUIDv4 plus capture UUIDv4 as PK/FK with no receiver-local surrogate; B01-R04 monotonic compatible-fact admission fixed by ADR 0019; ADR 0020 / B01-R05 now preserves attributed competing member reports; direct claim/group keys fixed by ADR 0021 / B01-R06 A |
| GCTX-M01/M02 | Metadata-only Core without Context/bytes and common Git full `(object_format,oid)`, not local `git_object_id` |
| GCTX-M03/M04 | Preserve independently attributed typed field claims, observation-scoped ordered relation groups, unknown/partial/known-empty, and truthful verification-aware reads |
| GCTX-M05–M07 | Exact local byte/representation verification, immutable admission proof and byte-dependent physical checks remain for permitted retained bodies |
| GCTX-M08/M09 | Distinct immutable physical instances with evidence-derived eligible-set selection. A real per-copy domain identity is required; its format is still open, with no extra storage-only surrogate |
| ADR 0003 | Strictly append-only Git Core and Context independence. No UPDATE, DELETE, REPLACE, Core GC or generic Publication |
| Other accepted rules | Permanent repository UUIDv4, Source known-positive, five-column/latest-observation Coverage, Unix epoch `_us`, NO_INDEPENDENT_PUBLICATION, CAS-41, ADR 0001, durable Context and derived Operational/Search |
| Still open | B01-R04 compatible monotonic fact admission fixed by ADR 0019; B01-R05 competing immutable member reports fixed by ADR 0020; B01-R06 direct semantic keys fixed by ADR 0021; origin authentication and clone/fork identity lifecycle detail, B02-R01 role-evidence strength fixed by ADR 0022; B02-R02 finite configurable budget policy fixed by ADR 0023; proof grammar open, B03 completeness, GCTX-M10 quarantine, exact DDL, cross-store fences/backups and Exchange |

A key policy is not a substitute for provenance/trust, verification, integrity, exact source attribution or Exchange idempotency.

## 4. Impact and handoff to coding agents

The implemented Schema 21 explicitly states that named surrogate keys follow the `<entity>_id` convention. Its tables include integer primary keys, some domain UUIDs, existing natural/composite keys and local FKs. The new final design **must audit and redesign** the storage-only ID cases instead of inheriting them for unreleased-data compatibility.

For every table in both authoritative and disposable stores, produce a precise inventory:

1. What is the real domain entity, fact, observation or physical instance?
2. What information makes two instances genuinely different, including repository/source/capture scopes?
3. Which semantic PK components are known? Which are unknown or generated by an actual domain occurrence?
4. Does any extra integer/UUID row-ID merely duplicate that identity? If yes, **remove it from the final model**.
5. Can children, Exchange and backups use composite foreign/reference keys without converting to a receiver-local authority?
6. Where a unique occurrence/copy truly needs an issued identity, is its origin/namespace and idempotency contract separately supported? If not, **report the unresolved domain-identity decision**, do not invent a surrogate.

No compatibility shim or temporary promise to keep old surrogate columns is necessary before release. Do not erroneously flatten independent observations/copies just to avoid an ID. No literal `*_id` naming ban: a true immutable domain ID and a storage-only row ID are different, and must be distinguished by evidence rather than column spelling.

## 5. Future counterexamples (NOT executed)

1. Nominal Git object keys are direct `(object_format,oid)` composites, not integer PKs with unique OID side constraints.
2. Child notes mappings and FK references can use the same origin/capture composite without receiver-only `notes_capture_row_id`.
3. Two independent notes captures at identical root remain separate; replay of the *same* capture is idempotent.
4. Reusing the same capture key for contradictory ref/root/source data cannot overwrite immutable Core truth.
5. Two independent physical I1/I2 copies of identical bytes have distinct real instance identities, while `sha256` is shared.
6. Missing note root/type/path must not be replaced with fake ordinals or dummy values to satisfy a composite PK.
7. Source/repository and document relations use actual supported domain composites without a second opaque membership/document row ID.
8. Native Git object and Context references survive Export/Import without sender-local SQL row IDs as authority.
9. Query/FTS/Search implementations may use internal ephemeral indexes but never export them as stable identity.
10. The existing `repository_uuidv4` remains permanent, even if classified as artificial/generated by strict relational terminology.
11. An entity that cannot be distinguished using an actual domain contract triggers design review, not a silent auto-increment.
12. Core and Context stay separate, physical integrity/CAS-41 checks remain and omitted ordinary file bytes are not corruption.

## 6. Subsequent B01-R03 D-1, B01-R04 A, B01-R05 A, B01-R06 A accepted; B02-R04 A accepted by ADR 0025; implementation and merge forbidden

[ADR 0018 / B01-R03](0018-notes-capture-uuidv4-composite-identity.md) accepts **D-1**: direct **`(capture_origin_uuidv4,capture_uuidv4)`** composite PK/FK, both UUID version 4. Each genuine origin/capture occurrence has its semantic identity; exact retransmission retains the pair, and no receiver-local row surrogate is permitted. The earlier B01-R03 B proposal (receiver-local surrogate) stays disallowed. [ADR 0019 / B01-R04](0019-monotonic-notes-capture-fact-admission.md) now fixes append-only admission of compatible new facts/groups and exact replay under the same capture. [ADR 0020 / B01-R05](0020-immutable-competing-notes-member-claims.md) accepts immutable competing reported member alternatives and derived conflicts; [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md) fixes direct semantic claim/group keys and replay equality. No generic UUID-as-natural-key exception is implied for unrelated domain tables.

No code/SQL/DDL, tests, migration, live-catalog mutation, release, deployment or merge is authorized. This decision must appear in the repository and agent instructions before dependent coding work. The tests above are future specifications, not executed results.
