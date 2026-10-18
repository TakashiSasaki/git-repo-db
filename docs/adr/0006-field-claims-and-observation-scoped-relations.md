# ADR 0006: Field-level claims and observation-scoped Git relation groups

- **Status:** Accepted owner design decision; concrete DDL and implementation pending.
- **Decision date:** 2026-10-14.
- **Decision ID:** GCTX-M03.
- **Owner selection:** Option C: per-field attributed claims for logically single-valued Git metadata; typed, observation-scoped groups for multi-valued Git relationships.
- **Dependencies:** [ADR 0004 / GCTX-M01](0004-metadata-only-git-core.md) and [ADR 0005 / GCTX-M02](0005-common-oid-identity-with-attributed-metadata.md), under [ADR 0003](https://github.com/TakashiSasaki/git-repo-db/blob/bb878eda47cf17268dd821c74343bac64d769ea7/docs/adr/0003-append-only-git-core-and-context-store.md).
- **Baseline:** Unmerged PR #46 HEAD `c3002e8894a228c31a892ad54aa7e6815d33889e`, stacked on PR #45 and PR #44.

## 1. Decision: two different metadata units

Each Git object has the **common nominal identity** `(object_format, oid)` already accepted in GCTX-M02. That common identity does not assert type, size, repository membership, object possession, or cryptographic verification. A usable Git Core metadata catalog must work with no canonical object bytes or Context DB (GCTX-M01).

### 1.1 Single-valued Git attributes: independent, typed claims

- Represent a supplied logically single-valued Git attribute as a **field-specific, attributed claim** against the nominal OID. Examples are a reported object `type`, `size`, commit `author`, authored timestamp, `message`, or a reported single tree-target OID. These are examples of fields, **not** a final column vocabulary.
- Retain the field identity, typed value when known, actual source/capture provenance and relevant observation or evidence information. A field may be absent, unknown, or reported with an explicitly meaningful value; do not invent zero, empty string, `NULL`-as-asserted-null, object type or local timestamp to fill gaps. Where the source explicitly distinguishes null from missing, retain that distinction.
- Different fields may be learned from different observations. No all-fields-together object report is mandatory. Multiple conflicting values for the *same* logical field can coexist under distinct provenance and are not resolved by row arrival order, source popularity, processing time or parser version.
- Grouping subfields into an indivisible typed value when their own meaning requires atomic coherence is a physical/field-contract detail; it does not reinstate a universal report or allow silently mixing incompatible source claims.
- An attributed scalar report is not byte-verified merely because a byte-verified representation later exists for its subject. No update of the prior claim is permitted.

### 1.2 Multi-valued Git relationships: typed, observation-scoped groups

- An ordered parent list and a tree-entry collection are **domain-specific typed relationship groups**, not independent free-floating edges whose union is assumed canonical.
- Anchor each group to one nominal subject OID, relation kind, the actual source/capture/observation scope and its evidence. Retain members together with whichever order, ordinal, raw name, mode, format and child OID are genuinely known. Do not require raw Git headers, original byte offsets or reconstructed complete object bytes merely to admit metadata.
- Model the group **scope** distinctly: an actually supported full list, a partial list/known fragment, and an unknown list are not interchangeable. If the source cannot establish list completeness, a group must not claim completeness. An explicitly supported complete empty list (for example, a root commit with no parents, or an empty tree) differs from a list not observed at all.
- Preserve a reported parent ordinal or entry identity if actually supplied; where the order is unknown, do not manufacture a continuous ordinal or an inferred position. Reported child OIDs can be nominally known while the child bytes, the child's type, or cross-repository membership remain unknown. Gitlink entries must not imply possession of a local blob/tree object.
- Each coherent group and its membership must become visible **atomically as one admissible unit**; a partially written group may not appear as an authoritative complete list. Later corrections, additional fragments or complete observations are **new immutable groups**, not in-place updates to existing group rows.
- Do not implicitly combine parent edges/tree entries across distinct groups into a new canonical list or complete graph. Compatibility, group comparisons, query precedence and any explicitly permitted synthesis are later decisions. This also excludes inferring missing entries from contiguous numbering or treating all individually reported edges as one complete source list.
- A relation group's own claimed completeness is **not** automatic verified Git closure, byte availability, repository reachability, or a general Coverage claim. Preserve the existing five-column Coverage contract and its distinct latest-observation semantics.

These groups describe **specific Git relationships**, not a universal Publication, batch admission owner, generic seal, all-PR edit history, or metadata-wide winner registry. Their schema, portable group identity, list-fragment grammar, verification of a completeness claim, and exact field vocabularies remain undecided.

## 2. Worked counterexample

Suppose the same nominal commit OID `C` receives these independently attributed observations:

| Observation | Supplied information | Reported scope |
| --- | --- | --- |
| S1 | `parent[0] = P` | partial list (only one known entry) |
| S2 | `[P, Q]` | complete ordered parent list |
| S3 | `[R]` | complete ordered parent list |
| S4 | `author = Alice` | individual scalar field only |

Required representation: S4 is one field claim; S1, S2, S3 are three distinct parent groups attached to **one** common nominal OID `C`. Do **not** infer `[P,Q,R]`, mistake S4's lack of parents for an empty list, or silently choose S2 over S3. S1's observed prefix and S2 may be compatible, but their provenance/scope is not collapsed or treated as the same capture. The correct default conflict-read treatment is deliberately reserved for GCTX-M04.

If verified raw bytes for `C` later contain `[P,Q]`, the verified canonical structure may be added under the existing exact byte/type/size/OID validation contract. The historical S3 report `[R]` remains a source-attributed observation, not a canonical byte fact and not an obstacle to byte admission. Stored CAS corruption and metadata-only nonacquisition are still distinct conditions.

## 3. Architectural compatibility

| Existing decision | Consequence of GCTX-M03 |
| --- | --- |
| ADR 0003 append-only Git Core | No UPDATE, DELETE, REPLACE, mutable late-FK backfill or object-body GC; new groups/claims are additional immutable facts |
| ADR 0004 / GCTX-M01 metadata-only | Neither scalar claims nor relation groups require actual Git object bodies, Context, hidden fetch or byte reconstruction |
| ADR 0005 / GCTX-M02 common OID identity | All claims/groups refer to a shared typed full OID; multiple repositories/observations retain independent capture facts |
| Provider/Source and Context separation | Git-domain metadata and minimal independently readable provenance are Core-owned, even if collected via an API; Provider registrations, PR semantics and associated bodies remain Context-owned |
| Exact Git verification and CAS-41 | Optional verified representation admission remains exact; no sender's verification assertions are promoted into local verification, and actual retained physical bytes remain subject to integrity checks |
| Coverage, Source, Unix microsecond times | Coverage's five columns/latest-observation semantics, known-positive Source association, `_us` time naming and unknown/NULL distinctions remain intact |
| NO_INDEPENDENT_PUBLICATION | A group is only a typed Git relationship assertion unit and cannot certify unrelated content or become a universal eligibility owner |

## 4. Future acceptance counterexamples (not yet executed)

1. Import unrelated scalar fields from separate sources for one OID; field-level provenance survives reverse/repeat Exchange, backup/restore and further ingestion without falsely declaring an object-wide coherent report.
2. Import `S1:[P] partial`, `S2:[P,Q] complete`, `S3:[R] complete` for the same commit; retain three bounded groups and do not create `[P,Q,R]` or silently select a preferred group.
3. Distinguish a known complete empty parent/tree group from no group and from an observed incomplete/unknown group, including null-versus-missing scalar attributes.
4. Admit out-of-order parent entries, unknown positions and partial tree entries without invented ordinals, fabricated raw byte offsets, missing child bytes or a false complete enumeration.
5. Write a complete group and all its members atomically; rollback, interruptions and repeated input cannot expose a partially admitted group falsely labeled complete.
6. Import the same OID and observations without Context or raw bytes. Query ordinary metadata, traverse only justified reported relationships, and Exchange/restore offline without hidden fetching.
7. After conflicting metadata arrives, admit exact verified canonical bytes. Keep all previous claims and groups, do not falsely promote their validation, and preserve byte-integrity/CAS-41 safeguards.
8. Retain actual acquisition/ref and repository-membership facts separately; neither a group nor a nominal OID implies that a repository obtained the referenced bytes or completed Git closure.

## 5. Subsequent owner decision: GCTX-M04 accepted; next GCTX-M05

[ADR 0007 / GCTX-M04](0007-verification-aware-git-metadata-reads.md) adopts verification-aware canonical read projections while preserving all source-attributed alternatives. Compatible unverified reports remain reported/unverified; unresolved contradictions return an explicit conflict, never a source/time/decoder-selected winner. Receiver-verified bytes justify only the specifically checked intrinsic field or relation. This is a query policy, not a record mutation, implicit group union, mandatory raw fetch, or determination of verification-result ownership. Next GCTX-M05 addresses the latter.

Still unresolved: concrete DDL and table names/counts; exact field/relationship schemas, group IDs and portable provenance; detailed complete/partial evidence admission; implementation details of ADR 0007 query projections/graph traversal; verification domain ownership fixed by ADR 0008 while exact evidence record layout/current-health policy remain open; append-only-safe CAS repair, read fences, cross-store transactions/backups, Exchange wire shape and GC-03/GC-04.

## 6. Work scope

This design-only ADR is stacked above unmerged PR #46, itself above #45 and #44. No implementation, SQL/DDL/schema-version change, release, deployment, retained-catalog mutation or merge is authorized. Future implementation and independent verification must follow ADR 0001; the counterexamples above are not claimed as executed tests.
