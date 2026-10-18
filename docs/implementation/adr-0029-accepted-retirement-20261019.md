# ADR 0029 acceptance and ADR 0003 retirement: closure record

**Decision status:** Accepted by the owner on **2026-10-19**.
The owner replied to the whole-record replacement question:
「はい、ADR0003を原稿から削除することも含めて承認します。」
This is explicit permission for **ADR documentation acceptance/retirement**;
it is not permission to implement an Access store, change Schema 21, enable P8,
change real catalog contents or merge any stacked PR.

This document records the acceptance implementation, not a new domain ADR.
The accepted replacement is
[ADR 0029](../adr/0029-independent-access-store.md).
The old ADR is retired from current HEAD; its exact historical bytes remain
at the [last pre-retirement revision](https://github.com/TakashiSasaki/git-repo-db/blob/bb878eda47cf17268dd821c74343bac64d769ea7/docs/adr/0003-append-only-git-core-and-context-store.md).
No archive copy is added under a new tracked path.

## 1. Decision meaning

The new accepted responsibility boundary comprises Git Core, Context, Access,
Operational and Search. Git Core retains strictly INSERT-only Git identity,
metadata and immutable observations. Context remains independent durable
Provider/Source/PR/Issue authority; Access separately owns durable Scope UUIDs,
Scope/Repository Locators, local connection configurations and approvals.
Operational is reconstructible execution state and Search is rebuildable.
Standalone Core still works without Context or Access.

The Access Scope choices accepted on 2026-10-17 remain fixed: the continuing
logical Scope UUIDv4 (separate from names/URIs and from a repository UUID), Scope
continuity versus independent fork, destination-local reapproval, timestamped
Scope Locator registrations in one table, and the complete maximal-original-time
first-choice set without tie-breaking or automatic authorization.

**The whole-record ADR acceptance is not acceptance of every former design
sketch.** In particular, exact seven-relation Access physical schema/table count,
proposed keys for registrations/assignments, installation sharing, adapter
vocabulary, typed option allowlists, detailed approval revocation and optional
Access bundle are future engineering contracts under the fixed constraints.
They remain visibly conditional in
[the Access physical design](../architecture/access-store-design.md).
No new UUID or surrogate may be introduced for storage convenience.

## 2. Binding ADR 0003 preservation

The original independent R4 review mapped **43 clauses** of ADR 0003, including
its **six implementation acceptance criteria**, to proposed ADR 0029 and
already-accepted refinements ADRs 0004, 0014, 0026, 0028. It found no material
loss. This remains the original R4's evidence, not a new independently executed
review. Use the [full clause map](evidence/access-a6-independent-20261018/r4/adr-clause-map.md)
for every original clause; ADR 0029 carries the binding family-level table
as operative text.

| Domain | Retained normative rule |
| --- | --- |
| Git Core | Permanent repository UUID; qualified metadata-only admission; actual immutable captures/ref history; no UPDATE/DELETE/REPLACE or admitted-Git-fact GC; exact original Git bytes and intrinsic structure when checked |
| Context | Independently durable mutable-current-state authority; Provider/Source/PR/Issue/review text; actual clocks/provenance; missing vs explicit NULL; conflicts and Source known-positive membership |
| Typed references | No cross-file SQLite FK assumption; real portable Core/Context subjects; independently admissible Core data even after Context failure |
| Coverage | Five-column authoritative claim meaning, explicit proof and scope; no inferred complete/known-empty inventory |
| Backup/recovery | Git-only backup does not claim Context; full paired domain snapshot keeps Core+Context consistent, verified and non-overwriting; apply ADR 0026 recovery stop, not obsolete quarantine/count |
| Operational/Search | Original cumulative-work/failure truth, correct-source search fallback, explicit rebuild and no domain truth in disposable state |
| Product boundary | Historical/notes-only permitted bodies; no ordinary file archive, no independent Publication, no generic capture-less edits |
| Implementation validation | Preserve all six future acceptance families, exact-tree independent review and dev/release qualification distinction |

**Subsequent ADR 0030** is also owner-accepted: its six role-aware Context
Repository relations, immutable mapping Dispositions (without Witness table),
bounded selective cross-seed Exchange and retained original provenance are
compatible with Access separation. An Access locator/approval is not a
Provider-to-Core identity claim or a domain Exchange payload. Current
[ADR 0030](../adr/0030-context-repository-relations-and-selective-exchange.md)
has its original 2026-10-18 historical `refines` metadata retained as such.

## 3. Link/identity retirement policy

This acceptance/retirement change removes exactly
`docs/adr/0003-append-only-git-core-and-context-store.md` from tracked HEAD.
A Markdown link to the deleted current path cannot remain a current live link.
Update current authority banners/index and skill directions to ADR 0029.
Older ADRs that directly cite ADR 0003 **as their historical predecessor**
should instead link to the fixed pre-retirement Git revision above, keeping
the original historical decision context.

Do **not** rewrite genuine historical hashes, package-member manifests, old
source receipts or timestamped reports. Do **not** change the preexisting
`replaces`/`refines` metadata referencing the retired filename as a historical
identifier; such frontmatter is not a live Markdown file link. Do not alter
older decisions by globally replacing the string 'ADR 0003' with 'ADR 0029'.
Preserve content of accepted older ADRs except the navigational link target
or an explicit current-authority banner if genuinely outdated.

The previous [readiness audit](adr-0029-replacement-readiness-20261019.md)
recorded the gate while still pending. That source is preserved as an
at-the-time review, now annotated with this successor closure. The
[governance migration policy](../adr/policy.md) closes only the ADR 0003
entry; other pre-policy migration cases remain open.

## 4. Exact branch and check boundary

Stack: #103 -> #104 (ADR 0030) -> #105 (readiness) -> this acceptance/retirement
documentation change. The **pre-retirement parent commit**
`bb878eda47cf17268dd821c74343bac64d769ea7` contains the exact
original ADR 0003, 0029/0030 and R4 evidence. Future reviewers must inspect
the actual PR head and base, not assume the current main branch has adopted
the stacked design.

This change is documentation only. Required checks: exact single-parent diff,
ADR 0029 accepted/status/date/replaces; old ADR removed; ADR index current and
watermark; full current Markdown/agent incoming references; pinned historical
predecessor links; accepted legacy clauses; relative links; no frozen
distribution/CI/manifest rewrites; no code/SQL/product schema change. Record
what actually ran in the PR body and do not claim product or independent
acceptance from an offline prose check.

The future Access implementation/independent review, runtime/default switches,
and merges remain separately authorized operations. ADR 0029 acceptance makes
them *eligible for separately instructed implementation*, not executed.
