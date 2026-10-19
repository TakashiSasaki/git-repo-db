# ADR 0029 whole-replacement readiness: ADR 0003 carry-forward and post-0030 delta

**Status: preparation and review only; NOT whole-ADR owner acceptance or retirement.**
Reviewed on 2026-10-19 against PR #104 HEAD
`bb54d799d1b749a90fa62de89dbd978ef3bc8055`, itself based on
PR #103 `1134e200eb4ac9ec45bf3fae3be695e2bb786a8d`.
The parent ADR 0029 blob SHA is
`08735e1e7e54deb035377167a6f65538a99defa3`, byte-identical at
`f4d0d448fca5925bfbe4f8cb8345c3bd0df7de60` (#102),
#103 and #104. This audit is a new review of **changes and remaining gates**
after the previous R4 work, not a new ADR or a second authority for accepted clauses.

## 1. Existing independent work: do not redo or overstate

The independently reported R4 review has already traced **43 clauses** of
[ADR 0003](../adr/0003-append-only-git-core-and-context-store.md) to the
operative successor/related ADRs, including all six original acceptance tests.
Consult its exact
[clause map](evidence/access-a6-independent-20261018/r4/adr-clause-map.md)
and [review](access-a6-independent-review.md), not merely the abbreviated
family map in ADR 0029. R4 found no material loss of a still-binding clause
*under already accepted scoped overrides* (ADRs 0004, 0014, 0026, 0028).
It did **not** approve ADR 0029's whole replacement, remove ADR 0003,
run a five-store production implementation, or authorize a merge.

R4 also classified
[25 baseline source files / 26 link or reference occurrences](evidence/access-a6-independent-20261018/r4/adr0003-inbound-classified.json):
nine current guidance/banner files, nine historical accepted-decision
predecessor links, three history-only ADR metadata entries, three immutable
distribution receipts, and one historical integration narrative. The evidence
is revision-scoped: source changes after #102 must be scanned again. In
particular, proposed ADR 0029's `replaces` entry is historical metadata
about what would be retired, not an instruction to delete the file while
`status: proposed` remains in effect.

## 2. What the owner actually fixed versus what remains proposed

| Scope | Current owner-approved content | Not automatically approved |
| --- | --- | --- |
| Scope identity | Permanent canonical Scope UUIDv4, names/URI not a key; Scope is a continuing logical resolution environment | Scope-name uniqueness, URI-derived keys or a new global identity service |
| Continuity/fork | Verified continuity may retain UUID; independent operating fork gets new UUID; historical registration facts are not rekeyed | Automatic continuity inference, distributed single-writer protection |
| Scope Locator | Location and identity separate; immutable dated registrations in the same `scope_locators` table; MAX(original registration time) first-choice **set**, ties unresolved | New current-pointer/history table, lexical/timestamp tie winner, automatic execution |
| Repository Locator/configuration | Independent repository locators and reusable connection configurations; approved Scope/Repository/route separation | Whole seven-relation Access sketch and every physical FK/column as accepted by implication |
| Approval | New local reapproval per scoped locator/configuration/purpose, with effective environment/content checked | Copied authorizations, imported approvals, implied trust from URI or credentials |
| Trust/backup | Core and Context independent; Access has separate durable control; no secrets in ordinary domain Exchange; genuine domain metadata survives | Automatic P8 switch, remote adapter support, environment-bundle implementation, whole-record acceptance |
| ADR lifecycle | Existing ADR 0003 remains operative where unsuperseded; ADR 0029 replacement proposed | Setting `status: accepted`, assigning an acceptance date, or `git rm` of ADR 0003 without explicit whole-replacement authorization |

**Proposed physical decisions to leave conspicuously provisional:** the
`(scope_uuidv4, registered_at_us, scope_locator_uri)` registration-fact PK;
`(scope_uuidv4, locator_text)` repository locator key; shared Access-store
installation model; actual supported SSH/HTTPS/file/UNC/Windows adapters;
full grants/reference shape and control revocation; typed configuration
allowlists; physical Access schema/table count; optional Access environment
backup bundle. Existing ADR 0029 and its companion design label much of
this A1/A2 engineering review. Do not turn those proposals into new
owner decisions simply by performing a status/date edit.

Before a future acceptance commit, classify each prescriptive sentence in
ADR 0029 as (a) confirmed final target, (b) engineering contract constrained
by that target, or (c) still-unselected proposal. Move category (c) detail to
the explicitly proposed companion design or keep it visibly tentative;
do not rewrite categories (a) or their reasons.

## 3. ADR 0003 normative carry-forward checkpoints

The R4 43-row clause map is the **detailed** source of truth for retention.
The following checklist shows the high-impact groups which an acceptance
and retirement commit must preserve.

| Original scope | Still-binding guarantee | Carry-forward location and trap |
| --- | --- | --- |
| Four-store boundary | Core Git facts INSERT-only; independent durable Context; disposable Operational; derivative Search | ADR 0029 five-store table adds Access, **does not reassign** prior authoritative facts |
| Core 1--3 | Metadata without raw bytes, genuine historical Capture/ref observations, retention of admitted Git facts and permitted bytes | ADR 0029 ACC-04, accepted ADRs 0004/0014; no ordinary-file-body archive |
| Core 4--5 | Application-visible Core INSERT-only including technical rows; exact semantic replay; no mutable verified/completion/revision pointers | Explicitly retain no UPDATE/DELETE/REPLACE/UPSERT/bypass, not a vague append-only description |
| Core 6 | Source decoder provenance, scoped verified intrinsic structure, no global winner; no in-place corruption repair | ADRs 0007--0010/0026; do not restore old quarantine/count or same-DB failover |
| Core 7 | Permanent Repository UUID, minimal self-contained provenance and Git-only operation | ADR 0029 ACC-01/04; neither Context nor Access is required to read valid Git facts |
| Context 1--2 | PR/Issue/Review state, original per-field clocks, missing/NULL/conflicts, parent/head/base, portable Git OID links | ADR 0029 ACC-05 plus ADR 0030's **six role-aware repository relations**; don't silently keep old single generic field |
| Context 3--5 | Split mixed ownership by described fact, Context UTF-8/SHA-256 text, no hidden full edit-history or Publication | ADR 0029 ACC-05 and ADR 0030; no Provider-settings laundering |
| Cross-file refs and writes | No cross-file SQLite FK claim; Core facts remain valid if later Context write fails; no false closure from failed stage | ADR 0029 ACC-08; ADR 0030's bounded Exchange/checkpoints do not promise all-store ACID |
| Coherent reads | Pinned consistent Core or paired Core/Context snapshot and conservative qualified dependencies | Access request configuration snapshot is distinct; no new domain authority |
| Retention & GC | No admitted Git Core GC, known-positive Source retention; Context future GC is separately governed | GC-03/04 remain deferred, no new automatic deletion |
| Backup & recovery | Truthful git-only vs mutually consistent Core+Context paired domain backup, verified pairing/hashes, no overwrite | ADRs 0026/0029 ACC-07; optional Access bundle is a **separate** scoped artifact |
| Search & Operational | Correct-authority direct fallback, explicit rebuild; operational loss does not erase domain facts or reset an old request budget | ADR 0029 ACC-07/08 and ADR 0030 Q-E7--Q-E10 |
| Former PF placement | PF-P06/P08/P05/P14/P15/P07 retained only in their compatible meaning | New Access store is not an excuse for weakening Core/Context backup or Work accounting |
| Unchanged prior decisions | UUID permanence, five-column Coverage, Source positives, original capture/clock, trust, no Publication | ADRs 0017,0027,0028,0030 and relevant existing ADRs; no re-opening Q-S or Q-E choices |
| Six ADR 0003 acceptance criteria | Offline Git-only/zero-body roundtrip, Core immutability attacks, Context isolation, partial truth, backups/Exchange, exact-tree review | Retain these as **future executable requirements**, not fulfilled merely by ADR status change |

Notably, ADR 0003's old **four-store count** is a policy conflict with the
five-store target and cannot survive as a current normative claim. The
legacy Three-Store/Schema 21 *implemented baseline* and historical test
receipts remain truthful, date-scoped evidence. Do not replace those old
results with invented five-store PASS claims.

## 4. Post-R4 delta: PR #104 / ADR 0030

The reviewed ADR 0029 file itself is byte-identical at #102, #103 and #104.
However, #104 introduced owner-accepted [ADR 0030](../adr/0030-context-repository-relations-and-selective-exchange.md)
and new design documents. This produces extra **acceptance-time** obligations
beyond R4's frozen incoming-link classification:

| Path | Current state | Eventual retirement action, only after approval |
| --- | --- | --- |
| `docs/adr/0030-context-repository-relations-and-selective-exchange.md` | `refines` metadata names ADR 0003; substantive design keeps Core/Context and Access separation | Reconcile its **current active** refinement base with accepted ADR 0029, while keeping accurate history of the 2026-10-18 decision and not implying retroactive approval |
| `docs/adr/README.md` | ADR 0003 active; ADR 0029 proposed; ADR 0030 active; 0030 allocation watermark | In one accepted replacement commit, move 0029 into Active, retire 0003 from current active index, update 0030's current scope pointers; keep watermark at least 0030 |
| `docs/implementation/context-exchange-design-handoff.md` | Explicitly says ADR 0029 whole acceptance is a separate gate | Update only if the gate actually closes, preserving the handoff's historical source/evidence meaning |
| `docs/architecture/context-repository-relations.md` and `selective-exchange-contract.md` | ADR 0030 design details with Provider/Core and Access separation | Check relative links and retained constraints against accepted five-store classification; **do not** introduce Access grants into domain Exchange |
| `docs/adr/policy.md` section 9 | Pre-policy scoped exception includes ADR 0003 | Record closure of **that one debt item** without expanding exemptions or rewriting older decisions |

A source search on the default branch found legacy live references in
`README.md`, `AGENTS.md`, `docs/architecture.md`,
`docs/implementation-status.md`, `docs/phase2/decision-register.md`,
`docs/adr/0002-*` and `docs/adr/0028-*`, among others.
The R4 JSON gives the earlier exact classification. Do **not** globally
replace all occurrences of the old filename: some are historical ADR
predecessors, plain `replaces/refines` history identifiers, frozen
distribution manifests or independent validation receipts.

Before a removal commit, rescan the **actual final proposed tree**, including
changed branches, markdown link targets and references from agent skills.
For historical Markdown hyperlinks, pin a real pre-retirement Git revision
when a navigable historical link is needed; otherwise retain truthful
non-link historical narrative. Plain ADR `replaces` metadata naming a retired
file may legitimately remain a historical identifier, not a broken link.
No current normative link may point to a deleted tracked file.

## 5. Exact future one-commit acceptance transaction

**These steps are NOT authorized by this preparatory review alone.**

1. Obtain the owner's **explicit acceptance of ADR 0029 as the complete
   successor** to ADR 0003, not just the already approved Scope choices.
   Record the actual approval date and evidence. Do not backdate it to the
   partial 2026-10-17 Scope decision.
2. Resolve only genuinely unselected normative assertions in the proposed
   ADR 0029 text by narrowing/proposing them, not quietly accepting unknown
   physical implementation contracts. Complete the clause-preservation review
   against current documents.
3. In **one coherent reviewed commit**, set ADR 0029 status/date to accepted;
   remove ADR 0003 from the active tracked tree; update
   `docs/adr/README.md` and all current authority/index links, including
   ADR 0030's active successor reference and `docs/adr/policy.md` scoped
   migration note. Do not make an archive ADR file elsewhere in HEAD.
4. Keep ADR 0003's exact accepted historical bytes in reachable Git history;
   do not modify prior test receipts, historical package-member manifests,
   CI claims or old validation logs. Retired paths in `replaces` are history
   metadata, not live Markdown links.
5. Static-review the final diff against the **actual stack parent**:
   frontmatter, no broken active local links, preserved Do NOT rules, exact
   changed-file inventory, parent/HEAD/tree identity and bounded text checks.
   A second independent review must confirm **meaning preservation** rather
   than merely matching filename strings. Ordinary documentation CI does not
   certify runtime.
6. Keep default Schema 21/P8 activation, Git Core/Context/Access implementation,
   real-catalog extraction, backups, release, merges and deployment behind
   their separate explicit owner approvals. ADR acceptance alone is not a merge.

### Approval question for the owner

> Do you explicitly accept ADR 0029 as the **whole-record replacement**
> of ADR 0003, subject to preserving all still-binding clauses and keeping
> unselected physical/adapter details visibly proposed, and authorize a
> subsequent coherent acceptance/retirement documentation change?

Answering this **has not** happened merely by asking us to continue ADR work.
Until it happens, `status: proposed`, `date: null`, the active ADR 0003 file and
its links remain unchanged.

## 6. Actual validation status of this preparatory review

- This audit reuses R4's completed 43-clause and 25-file/26-occurrence work.
  It is **not** a fresh independent R4 review; the source-specific R4 review is
  available at its exact cited files.
- The canonical ADR 0029 blob was re-fetched at the #102, #103 and #104
  revisions and was byte-identical. The #104 base and source pointers were
  inspected before authoring. The #104 new material is explicitly considered.
- Some newer current source references were sampled, not a complete
  final-tree retirement link audit. A full final-tree scan is required after
  the approved replacement changes are actually prepared.
- No new ADR ID is needed for a readiness report; ADR 0030 remains the
  allocation watermark. This document is not a second normative ADR.
- No production DDL, source, runtime tests, schema fingerprints, CI
  workflows, Pages allowlist, real catalog, backup, secrets or Access
  configuration are changed by this preparation PR.
