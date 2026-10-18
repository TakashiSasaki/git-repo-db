# ADR 0007: Verification-aware canonical Git metadata reads

**Current post-corruption override:** [ADR 0026 / GCTX-M10](0026-stop-salvage-restore-merge-after-corruption.md) requires stopping ordinary catalog operation, preserving the suspect source read-only, serializing salvage candidates, restoring a verified backup into a fresh destination and merging only revalidated admissible data. Prior post-fault metadata service, same-DB failover, known-corrupt normal backup/restore and references to M10 as pending are historical in that scope. Ordinary sound-catalog rules and unrelated open work remain. No implementation or merge is authorized.

- **Status:** Accepted owner design decision; implementation and concrete storage schema pending.
- **Decision date:** 2026-10-14.
- **Decision ID:** GCTX-M04.
- **Owner selection:** Option B — prefer receiver-verified canonical Git bytes and confirmed intrinsic values in ordinary queries; explicitly surface unresolved or conflicting unverified reports.
- **Dependencies:** [ADR 0003](https://github.com/TakashiSasaki/git-repo-db/blob/bb878eda47cf17268dd821c74343bac64d769ea7/docs/adr/0003-append-only-git-core-and-context-store.md) (append-only Git Core + Context), [ADR 0004 / GCTX-M01](0004-metadata-only-git-core.md) (metadata without bytes), [ADR 0005 / GCTX-M02](0005-common-oid-identity-with-attributed-metadata.md) (common nominal OID identity), and [ADR 0006 / GCTX-M03](0006-field-claims-and-observation-scoped-relations.md) (field claims and typed relation groups).
- **Baseline:** Unmerged PR #47 HEAD `65b2344a8c96b9f3c83381572847cbe9f0c6dae1`, stacked on PR #46 → #45 → #44. The implemented Three-Store Core Schema 21 is not changed by this decision.

## 1. Binding decision and precise scope

Ordinary Git metadata readers MUST distinguish a **nominal OID subject**, **attributed reported values**, **receiver-verified original bytes and checked intrinsic interpretations**, **current physical byte availability**, and **evidence for the completeness of a requested relation/graph scope**. These are not interchangeable states.

For an actual Git object OID and a requested typed metadata field or relationship, ordinary reads prefer a value justified by **locally validated canonical Git object bytes and field/relationship conformance**, while preserving all contradictory reports as separately retrievable, immutable evidence. Where such byte-backed justification is unavailable, do **not** select a conflicting value by source preference, receipt order, commit clock, parser version or the number of agreeing providers.

This is a **read-time selection / query projection rule**, not an UPDATE of admitted Core facts, a promotion of a source assertion, a new winning-decoder policy, a generic certification system or an authorization to fetch raw objects.

## 2. Required normal-query behavior

| Case | Required query semantics |
| --- | --- |
| Receiver-validated original Git bytes and the requested field/relationship have been checked against those bytes | Return the **byte-backed canonical interpretation** for the supported field/relationship, identify its evidence basis and keep separately accessible all original source reports, including conflicting ones |
| No byte-backed answer and supported reports agree for an individual typed scalar value or an exactly supported complete relationship group | Return the reported value with an explicit **unverified** qualification and underlying provenance. Agreement is not cryptographic verification or a proof of full scope |
| No byte-backed answer and reports contradict on a field or on overlapping required relation positions/members | Return an explicit **conflict** and available alternatives/provenance; do not invent a winning value or a union of incompatible groups |
| Available reports cover only a partial relation/list scope | Expose the known portion with **partial/unknown** qualification; never claim a complete parent list, complete tree inventory, or verified closure |
| No applicable metadata claim | Explicit **unknown / absent evidence**, not a known-empty list, null, zero, empty string or fabricated default |
| A canonical byte-backed interpretation disagrees with a prior claim | Prefer the canonical value in ordinary reads, while retaining the earlier claim and making the disagreement queryable. Do not rewrite, downgrade or falsely mark the earlier claim as locally byte-verified |
| A previously admitted verified byte representation is currently quarantined, inaccessible or damaged | Clearly separate historical verified-admission evidence from **present physical availability**. Byte-dependent operations fail closed. Do not silently substitute a claimed value for a current byte check or conceal actual CAS loss/corruption |

The labels above are **logical result categories**, not approved enum names, columns or JSON/API layout. Result structure and read-profile surfaces are implementation design work.

**Crucial qualification:** a correct object hash authenticates the *exact Git object bytes*, not automatically a particular Unicode normalization, parser output, external attribution, signature, or every third-party field claim. Intrinsic `parent` and `tree` structure can be checked against the exact bytes. For an `author` value, distinguish raw header content from decoding into a display string; any normalized or decoded interpretation must identify its explicit decoder/settings and must not silently install a globally preferred parser profile. Fields unsupported by the verified representation remain reported/unverified or unknown as appropriate.

The existence of one locally verified representation does not imply that all referenced children, trees or blobs are obtained or verified. Hash collision/inconsistent raw identities must be rejected or isolated under existing integrity rules; never select one purported 'canonical' body by arbitrary order.

## 3. Partial relationship sets and provenance

Keep GCTX-M03's typed group boundaries. For one commit `C`, suppose observations are:

| Evidence | Claimed values | Scope |
| --- | --- | --- |
| S1 | `parent[0] = P` | Partial observation |
| S2 | `parents = [P, Q]` | Supported complete-list report, unverified |
| S3 | `parents = [R]` | Supported complete-list report, unverified |
| S4 | `author = Alice` | Independent scalar field, unverified |

Without raw bytes, S2 and S3 are **conflicting complete-list reports**. Neither S1 plus S2 nor S2 plus S3 becomes a newly certified group. An explicit compatible partial report may support a compatible field, but it does not independently certify the completeness of S2's list. S4's missing parent field is **not** an empty parent list.

If raw bytes for `C` are later locally validated and decode to parents `[P,Q]`, ordinary parent-list reads use the verified intrinsic structure `[P,Q]` with a canonical-byte evidence qualifier; S3 `[R]` remains accessible as a historical conflicting report. It must still be possible to read all sources without the preferred projection, e.g. via explicit alternatives/diagnostic query mode. Canonical selection is per requested field/relation under suitable checked evidence; it does not fabricate a coherent all-fields object by combining incompatible claims.

Where a report covers only a fragment, its compatibility with a complete report requires a real shared index/key/scope semantics, not mere set overlap. A group labeled `complete` based solely on source assertion remains **reported complete**, not byte-validated closure or Coverage `complete`. The exact admission proof grammar for group completeness remains unresolved; GCTX-M04 does not weaken Coverage's existing 5-column/latest-observation contract.

## 4. Physical health and snapshot guarantees

- A successful earlier local byte admission and a healthy present physical payload are distinct. If retained CAS bytes become unavailable or quarantined, metadata-only queries can still display independent reports and historical admission evidence, but must accurately report degraded current byte availability and must not claim successful current raw export or verified closure. The append-only-compatible repair design is a separate decision.
- The query's answer and its supporting evidence must be derived from one coherent Git Core read snapshot. Current Context data, if requested, needs the separately designed two-authoritative-store fence; a missing Context cannot cause Git Core metadata reads to fail.
- Search is only a rebuildable derivative. Its missing/stale state must fall back to the correct Git Core metadata authority and preserve reported/unverified/conflict/canonical distinctions. Search must not create an unverified 'winner'.
- Exact claims of receiver-local byte verification require real receiver-held input and checks, not the sender's `verified` flag or provider consensus. Exchange cannot import a sender's verification conclusion as local authority.

This ADR makes no final choice about whether a historical byte-backed projection can be served without contemporaneous rehash, or about the precise current-byte-availability freshness protocol. Those must be consistent with the physical integrity and backup/CAS-41 decisions; never silently misrepresent a corrupt payload as verified currently available.

## 5. Consistency with earlier decisions

| Binding decision | Effect of GCTX-M04 |
| --- | --- |
| GCTX-M01 metadata-only Git Core | Ordinary metadata remains queryable with no Context and no raw object bytes, with truthful epistemic qualification |
| GCTX-M02 common OID identity | A single `(object_format, oid)` subject can have many independent claims and optional verified evidence; no metadata report can poison the nominal OID key |
| GCTX-M03 scalar claims + observation-scoped relation groups | Select a canonical value only when independently checked, preserve alternative groups and their partial/full scopes; never union unrelated edges |
| ADR 0003 strictly append-only Git Core | Query selection is derived; no UPDATE, DELETE, REPLACE, in-place repair, GC or hidden mutable 'preferred value' row |
| Context / Operational / Search boundaries | Context holds Provider/PR/Issue domain and any associated assessments under later design, Operational remains disposable, Search rebuildable; Core's essential interpretation does not require Context |
| Exact Git verification, CAS and CAS-41 | Local verification remains strict when asserted; raw identity verification, field decoding, physical health and closure are distinct; no sender-laundered verification |
| Coverage, Source, repository identity, time | No relabeling of `complete`, no inferred repository membership, no implicit latest-report winner; preserve `repository_uuidv4`, known-positive Source, Unix epoch `_us`, five-column Coverage contract |
| NO_INDEPENDENT_PUBLICATION / ADR 0001 | No universal seal or generic version-winner. This is a design decision with future tests, not a release-qualified implementation |

## 6. Future implementation counterexamples (NOT executed here)

1. With no bytes and no Context, matching independent scalar claims remain queryable with `reported_unverified`; contradictory claims yield alternatives and no chosen `canonical` value.
2. Incompatible complete parent groups `[P,Q]` and `[R]` yield an explicit conflict; no union, no preferred newest/source/decoder and no falsely complete DAG.
3. A genuine partial `[P]` with an independently supported complete `[P,Q]` does not create a merged group, yet read APIs can present original compatible observations and the full *reported* list with exact provenance.
4. A supported complete empty list, an unknown group, and the absence of a group remain distinguishable without creating fake edges or raw bytes.
5. Later receiver-verified bytes confirming `[P,Q]` select canonical `[P,Q]` while retaining a contradictory `[R]` report; no admitted row is mutated and no external claim is marked validated merely by OID coincidence.
6. A verified raw commit header with multiple possible display decoders does not select an unspecified authoritative Unicode string, alter decoder provenance or canonize a provider-normalized author/message.
7. Child bytes are absent: the parent's locally verified parent edge can be canonical without claiming that the parent child object bytes or full closure exist.
8. After loss/quarantine of retained verified bytes, current availability and byte-only reads fail closed; old reports/evidence remain, CAS-41 accounting and append-only constraints hold; intentional metadata-only absence is not diagnosed as corruption.
9. Exchange reversed/repeated or a sender-asserted verification cannot create receiver-local verified status or update old claims. Git-only/Context-absent backup and Search direct-read fallback still return appropriately qualified metadata.
10. Query results, alternatives and their proofs use consistent read snapshots and cannot splice incompatible group versions or unrelated provider scopes.

## 7. Subsequent owner decision: GCTX-M05 accepted; next GCTX-M06

[ADR 0008 / GCTX-M05](0008-domain-split-git-verification-ownership.md) fixes Git-intrinsic verification and necessary durable evidence in Core, Provider-specific assessments in Context, and execution/Jobs in Operational. A shared verification library does not make Context the Core admission authority. [ADR 0009 / GCTX-M06](0009-bounded-byte-admission-and-physical-health.md) fixes bounded immutable admission evidence, separate from current physical health. [ADR 0010 / GCTX-M07](0010-operation-scoped-cas-physical-integrity.md) fixes operation-scoped assurance, leaving low-level snapshot/locking and GCTX-M08 physical repair open.

Other open decisions include: exact physical schemas, metadata types and relation-group identity; GCTX-M05 verifier domain ownership fixed by ADR 0008 while exact evidence record layout is still open; completeness proofs; health/recheck policy and append-only CAS repair; local revision/read fences; two-DB transactions/backup pairing; Exchange wire identity; GC-03/GC-04. This ADR does not select any of those.

## 8. Work scope

This ADR is a design-only change stacked on the still-unmerged PR #47. PRs #44 → #45 → #46 → #47 must remain unmerged without explicit authorization. No production code, DDL, schema version, migration, runtime process, real catalog, GC, deployment, release or merge is authorized. Follow ADR 0001 for future implementation validation; the acceptance examples above are requirements, not executed results.
