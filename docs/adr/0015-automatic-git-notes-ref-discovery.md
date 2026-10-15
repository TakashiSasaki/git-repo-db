---
status: accepted
date: 2026-10-15
replaces: []
refines:
  - 0014-history-and-notes-catalog-without-file-archive.md
---

# ADR 0015: Automatically discover Git notes refs and allow explicit additional namespaces

**Current refinement:** [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md) accepts direct semantic composite claim/group keys using the actual Capture UUIDv4 pair, typed slot, asserted value and genuine provenance, without surrogates. B02-R01 structural role-evidence strength is fixed by [ADR 0022](0022-receiver-verified-notes-role-admission.md); B02-R02 resource policy, exact proof grammar, B03 completeness, GCTX-M10 and concrete DDL/trust remain open; earlier choices below retain their historical scope.

- **Decision ID:** B01-R01 (B01 notes-ref discovery-scope decision; capture/observation identity is subsequently fixed by ADR 0016/0018).
- **Owner choice:** **Option B** — discover all observable refs under `refs/notes/*`, and permit additional explicitly designated notes refs.
- **Decision status:** Accepted owner instruction on 2026-10-15; capture identity is subsequently fixed by ADR 0016/0018 and direct semantic claim/group keys by ADR 0021; B02-R01 role-evidence strength is fixed by ADR 0022; exact supported proof grammar, resource budgets and DDL remain unresolved.
- **Stacking base:** Unmerged [PR #55](https://github.com/TakashiSasaki/git-repo-db/pull/55), HEAD `4a45a137ee22ec1c87fb616bc94aef5587918737`, itself above PR #54 and ancestors #44–#51/#53. Proposed ADR 0011 governance [PR #52](https://github.com/TakashiSasaki/git-repo-db/pull/52) is a sibling off PR #51, not yet accepted; no governance-policy adoption occurs here.
- **Scope:** Design documentation only. Implemented Catalog3 Three-Store Core Schema 21 is unchanged.

## 1. Binding choice: enumerate notes namespaces, not just the default

For each explicitly bounded Git repository/ref-source observation, the **default discovery selector** includes **every actual ref whose full, validated name is under the `refs/notes/` prefix**. This includes `refs/notes/commits` as well as e.g. `refs/notes/review`, `refs/notes/build-results` and nested `refs/notes/team/review`. The `*` in this decision means the **notes subtree**, including nested slash-separated suffixes, not just one shell-glob path segment.

The product ALSO supports additional notes-ref names explicitly nominated by a caller/configuration for that repository and observation source. A nominated ref need not be lexically under `refs/notes/`, but its name and source must be unambiguously recorded, validated and treated as a *candidate notes namespace*. The nominated role is not by itself cryptographic or structural proof that a ref contains Git notes. Additional refs must meet the same capture/evidence and **role-based admission** rules as automatically discovered refs.

Auto-discovery is based on the ref inventory **actually observable in the selected source/snapshot**. It is not permission to assume unadvertised or unfetched remote notes refs exist or do not exist, to fetch all remote refs without a bounded acquisition contract, or to treat a remote-tracking alias as the same authoritative ref merely because it has a similar suffix. The exact Git/transport commands, remote fetchspecs, snapshot fencing and requested providers remain implementation details. Explicit configured names and automatically found refs are combined into one **identity-preserving set** for that observation; a matching name discovered twice must not create two independent notes namespaces by policy alone. Discovery provenance, original ref name and selector basis (automatic, explicit or both) remain queryable.

**Do not use** `core.notesRef`, `GIT_NOTES_REF`, `notes.displayRef` or the default notes display settings as an exclusive discovery allowlist. Git's default notes ref and display configuration are not a declaration that all other `refs/notes/*` do not exist. These settings can inform evidence about a selected view but cannot silently narrow the accepted automatic discovery scope.

## 2. Four separate evidence/availability boundaries

The product must distinguish:

1. **Ref enumeration**: did an authoritative enough ref inventory for the *requested source/scope* actually occur, and which names were observed? A failed/partial/not-attempted listing is not an authoritative empty set and cannot establish global absence.
2. **Ref-root observation**: for each discovered or explicitly nominated ref, what exact full ref name, observed root OID, declared/checked root kind, repository and source/capture evidence are available? The root may be a notes-history **commit** or directly a **tree**. Unknown root kind must not be fabricated as a commit.
3. **Notes mapping observation**: which note-target OID, note blob OID and observed notes-tree entry/path are actually supported by the selected root and capture? One ref's members/completeness cannot be united with a different ref or capture to fabricate one complete mapping.
4. **Note body retention**: actual binary note bytes may be admitted under [ADR 0014](0014-history-and-notes-catalog-without-file-archive.md) **only when their notes-content role is supported by the required typed evidence**. A ref name prefix or caller `is_note=true` does not, by itself, authorize accepting arbitrary file bytes as an annotation.

These are **separate** from ordinary repository-file body retention, native Git object OID identity, Provider context and whole-repository closure. A discovered notes namespace can be cataloged without acquiring every root/tree or note body. Do not silently equate “found ref” with “complete note listing” or “all note bodies retained”.

This decision establishes a *discovery policy*, not a concrete portable observation/capture primary key, source identity grammar, a particular notion of complete enumeration, a minimum/full root proof, or permission to turn malformed/unsupported note-tree entries into canonical notes. Capture/claim identity is subsequently fixed by ADR 0016/0018/0021 and required role-evidence strength by ADR 0022. Exact proof grammar, source trust and B02-R02/B03 acquisition/coverage contracts remain open.

## 3. Example: multiple namespaces and observations

Suppose an observed repository R exposes:

| Observed ref | Discovery selector | Observed root | Mapping from this specific source/capture |
| --- | --- | --- | --- |
| `refs/notes/commits` | Automatic | Notes commit `NC1` | Target C1 → note N1 |
| `refs/notes/review` | Automatic | Notes commit `NR1` | Target C1 → note N2; C2 → N3 |
| `refs/notes/team/audit` | Automatic (nested) | Notes tree `NT1` directly | Target C3 → note N4, if proven by actual mapping |
| `refs/company/annotations` | Explicit nomination | Reported root `NX` | No locally verified note mapping yet |

Ref names and root OIDs are **observations**, not one globally eternal ref state or a per-target note's unique identity. The same target C1 can legitimately have notes N1/N2 from distinct namespaces. A later `refs/notes/review → NR2` does not UPDATE/DELETE the earlier observation for NR1. A later return to NR1 also does not erase an independently evidenced earlier capture.

For `refs/company/annotations`, explicit nomination allows observation and possible notes-specific parsing; it does **not** authorize persisting every reachable blob merely because the root has tree entries. The source may report only the root or names, and the database must retain partial or unknown qualification.

If an attempted inventory yields no names, that supports **known empty** only when the defined requested enumeration scope was actually covered by appropriate evidence. “No inventory attempted” and “not fetched on this clone” are **unknown**, not equivalent to a verified absence of remote notes.

## 4. Preserved invariants and scoped compatibility

| Prior contract | Consequence of B01-R01 |
| --- | --- |
| **ADR 0014 / GCTX-S01** | Ordinary file bodies remain excluded. Notes are a role of Git `blob`, not a fifth native object type. Namespaces discover candidates; role-backed content is retained only with correct notes association. Commit/tree/tag representations remain permitted |
| **GCTX-M01 / ADR 0004** | Git Core-only metadata import/query/traversal works without any original bytes, without Context or hidden fetch. Ref discovery can be partial |
| **GCTX-M02 / ADR 0005** | Same `(object_format, oid)` across repositories for a nominal Git object; note file role and file-content role never create two nominal OID identities |
| **GCTX-M03 / ADR 0006** | Relation members require typed observation-scoped groups, preserved capture/provenance and partial/known-empty/unknown distinction. Unrelated ref/root observations are never silently merged into complete groups |
| **GCTX-M04 / ADR 0007** | An unverified note/ref mapping remains reported/unverified even if several sources agree. Only receiver-checked intrinsic evidence supports byte-backed canonical claims; contradictory captures remain visible |
| **GCTX-M05 / ADR 0008** | Git ref/notes facts and required local validation remain Git Core-owned; Provider-specific assessments Context-owned; retry/fetch progress Operational-owned |
| **GCTX-M06/M07 / ADRs 0009/0010** | Historical byte admission is bounded and immutable; actual note bytes require proper local Git OID/type/size and physical CAS checks, with verified output of the actual emitted bytes; a ref listing does not prove body health |
| **GCTX-M08/M09 / ADRs 0012/0013** | Multiple immutable physical instances, diagnosis/recovery and evidence-derived candidate selection apply to actual retained note/metadata bytes; discovered but unacquired blob bodies have no physical instance to quarantine |
| **ADR 0003 / fixed contracts** | Strict append-only Git Core, durable Context, disposable Operational/Search; no independent Publication, no Core GC, permanent `repository_uuidv4`, known-positive Source, Unix epoch `_us` and exact five-column Coverage/latest-observation semantics |
| **CAS-41 / GCTX-M10** | Actual retained physical faults remain subject to CAS-41; the active quarantine/disposition predicate **remains open** and is not changed by B01 discovery |
| **Exchange/backups** | Transfer notes-ref selection/capture provenance and partial evidence without accepting sender `verified` as local truth or admitting ordinary file bodies. Core-only Git metadata backups stay useful; Context-containing full backups remain paired |

Git notes namespace enumeration neither implies all notes bodies were preserved nor promises a full repository mirror or a complete canonical note graph.

## 5. Required future acceptance counterexamples (not executed)

1. Discover `refs/notes/commits` and two other `refs/notes/*` namespaces, including a nested suffix; treat all as independently named notes scopes rather than displaying only the default.
2. Add a valid explicitly designated ref outside the notes subtree, preserving its exact name and source. A duplicated explicit+automatic name does not fork a new namespace identity.
3. A selected ref points directly to a tree rather than a commit. Preserve root kind accurately and do not invent a notes commit.
4. Two notes refs attach different notes to the same commit/blob target. Keep separate namespace and capture provenance and retain only evidenced note bodies, not target file bodies.
5. Report a notes ref/root from an API but supply no body. Catalog it as a qualified observation without fabricating locally verified root or note bytes.
6. A local clone lacks fetched remote notes refs. Do not conclude that the remote has no notes or claim a complete remote note inventory from local silence.
7. Record one complete empty inventory (with real scoped evidence), one partial enumeration and one not-attempted enumeration. These yield distinct outcomes under the future B03 completeness policy.
8. Notes ref changes root and subsequently returns to an earlier root. Preserve all actually distinct evidenced observations without UPDATE/DELETE or a fabricated current-state winner.
9. Supply a malformed note-tree entry or an arbitrary tree under an explicitly nominated ref. A matching refname or `is_note` flag must not authorize a generic file-body upload or full descendant hydration.
10. Preserve empty and binary notes in an allowed, proven note-body role without false UTF-8 normalization, destructive decoding or invented payloads. B02 limits remain separately unsettled.
11. Exchange captures in reverse/repeated order and recreate Operational/Search: logical notes scopes, provenance, alternatives and Core facts survive.
12. Confirm no Core-to-Context mandatory FK, Generic Publication, winner-by-time, file-body archived as `git_text_facts` or unrelated Content CAS retention arises from automatic ref discovery.
13. Scan a ref inventory concurrently with ref movement or force-push: do not claim a coherent complete snapshot or mix note members from different roots without explicit evidence/fence.
14. Validate actual retained note bytes independently of sender success flags; retain CAS-41 fault evidence, allowing zero-byte metadata-only catalogs.
15. Validate exact ref-name matching, nested notes prefixes and explicit names without leaking remote credentials into Core or relying on a global Git notes display configuration.

## 6. Subsequent owner decisions: B01-R02–R06 accepted; next B02-R02

[ADR 0020 / B01-R05](0020-immutable-competing-notes-member-claims.md) accepts immutable competing notes member reports and derived conflict while preserving B01-R01 ref discovery, capture-scope identity, atomic groups and no ordinary file-body archival. Direct semantic claim/group keys and replay equality are fixed by [ADR 0021 / B01-R06 A](0021-direct-semantic-notes-claim-group-keys.md).

[ADR 0016 / B01-R02](0016-immutable-notes-ref-capture-observations.md) accepts Option B: each genuine notes-ref observation has a separate immutable, portable capture-scoped identity, even when its ref/root matches an earlier observation. Exact replay of the same capture is idempotent; [ADR 0018 / B01-R03](0018-notes-capture-uuidv4-composite-identity.md) now fixes issuer UUIDv4 plus capture UUIDv4 as a direct composite PK; [ADR 0019 / B01-R04](0019-monotonic-notes-capture-fact-admission.md) fixes monotonic compatible-fact admission and exact replay; contradictory member reports are now preserved as immutable attributed alternatives by ADR 0020 / B01-R05; direct semantic claim/group keys are fixed by ADR 0021 / B01-R06 A. The original A/B/C options below document the already answered question, not an open B01-R02 choice.

**What is the durable identity of a notes-ref observation/capture, especially when the same ref+root recurs or is reported by different sources?**

- **A — Ref/root natural-key identity.** Key by e.g. `(repository_uuidv4, full_ref_name, object_format, observed_root_oid, root_kind)`, with distinct separately attached source evidence. Efficient canonical deduplication, but repeated independent observations of the same root become difficult to distinguish.
- **B — Immutable capture-scoped observation identity (recommended candidate).** One genuine capture/observation has a distinct portable ID plus exact ref name, observed root if known, source and capture scope; notes mapping groups attach to that observation. A replay of the **same** capture is idempotent; a distinct observation of an identical root remains representable. More provenance storage and idempotency requirements; not a generic record per background scan attempt.
- **C — Target/note-scoped identity as the primary unit.** Key each note relation by target/note OIDs and ref name, with observation details as annotations. Compact for individual lookup but risks conflating reappearances, incomplete inventory, ref changes and source-level provenance.

ADR 0016 has now fixed B01-R02 Option B while preserving B01-R01. ADR 0018 / B01-R03 fixes the direct two-UUIDv4 capture key; B01-R04 compatible-fact/group replay is fixed by ADR 0019; B01-R05 competing member report preservation is fixed by ADR 0020; B01-R06 semantic claim/group identity is fixed by ADR 0021; final tables/FKs and B03 completeness remain open; the original alternatives above are historical.

## 7. Authorization and references

- Git notes primary reference: https://git-scm.com/docs/git-notes (default `refs/notes/commits`, notes namespaces, alternate notes refs, direct-tree notes roots, binary note blobs).
- Owner-selected scope: B01 Option B in this conversation, after ADR 0014 and GCTX-M01–M09.
- Follow-on blocking topics: B01-R02 capture-scoped identity is fixed by ADR 0016; B01-R03 direct UUIDv4 key fixed by ADR 0018; B01-R04 monotonic fact admission fixed by ADR 0019; B01-R05 competing member report preservation fixed by ADR 0020; B01-R06 direct semantic claim/group keys fixed by ADR 0021; B02-R01 role-evidence strength fixed by ADR 0022; B02-R02 note-body budgets and exact proof grammar open; B03 notes enumeration/list completeness; GCTX-M10 physical quarantine; physical Core/Context schema, Exchange and backup pairing.

Do not implement, change SQL/DDL or schema version, mutate catalogs, merge PRs, run authenticated acquisition, release or deploy as part of this design-only PR. Counterexamples here are future implementation test requirements, not executed tests; no local runtime/CI verification success is implied.
