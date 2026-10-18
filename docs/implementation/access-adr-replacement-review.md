# ADR 0003 -> 0029 replacement review ledger

**Independent follow-up:** the [A6 independent review](access-a6-independent-review.md)
includes a 43-row source-clause map and current/historical reference classification.
Whole-record replacement still needs explicit human acceptance; 0003 remains in
HEAD and 0029 remains proposed with no fabricated acceptance date.

Status: author-performed source review on 2026-10-17; no retirement, complete ADR
acceptance, main merge or independent-agent approval is claimed. Owner-confirmed
Scope/Access choices are binding. This is the concrete A0 lifecycle follow-up and
handoff for [ADR 0029](../adr/0029-independent-access-store.md), not another ADR or
an archive copy of retired decision text.

## Exact source and comparison

Read ADR 0003 from `cf90c093089911acbfd3c8c2c7778a9ff8904bc6`; its Git blob is
`ca3bf22068294fe0b78ecfa8028fa8f27e5106cb`. Main is still
`b2a87cfc6562413d9ecde7f4329e90c434ae9aad`. Compare its complete source clauses,
including the final six acceptance criteria, with ADR 0029's existing carry-forward
map and the following explicit disposition. The no-quarantine/retained-body/time
refinements are existing accepted rules, not Access changes.

| Source clause family | Disposition / successor requirement |
| --- | --- |
| Motivation and domain partition | Preserve: partition by meaning, not mutable versus immutable row; Access registration history remains Access |
| Core responsibility / strict INSERT-only | Preserve in 0029 Decision/Constraints; no mutable Core revision, UPDATE/DELETE/REPLACE or evidence relabeling |
| Context responsibility / independent durability | Preserve in 0029 Decision/ACC-05; current Provider evidence and text are not caches |
| Operational responsibility | Preserve in Decision/ACC-08; requests and cumulative costs stay reconstructible with loss semantics |
| Search responsibility | Preserve correct-source reconstruction/fallback; Access does not become a new search authority |
| Exactly four stores | Replace with five responsibility classes; no implication that every mode creates five DB files |
| Git-only availability without Context | Preserve and extend to no required Access for offline facts and explicit one-shot inputs |
| Core rule 1: metadata-only / checked-byte distinction | Preserve with ADRs 0004, 0005, 0014; nominal unknowns are not verified closure |
| Core rule 2: actual capture/ref/provenance | Preserve; Scope URI changes cannot reconstruct or alter a prior Git observation |
| Core rule 3: retention after ref removal | Preserve no Core GC; excluded/unacquired ordinary files are distinct from admitted data loss |
| Core rule 4: all application-visible Core rows immutable | Preserve explicit replay/conflict semantics, technical-row scope and no DDL workaround |
| Core rule 5: mutable baseline remodel | Preserve auditing of old current/completion/verification pointers; not permission to weaken guards |
| Core rule 6: decoder evidence and integrity | Preserve scoped verifiers/no generic winner; ADR 0026 replaces old quarantine/in-place recovery language |
| Core rule 7: permanent repo and minimum provenance | Preserve UUID and Context independence; add no Access FK dependence |
| Context rule 1: provider current-state semantics | Preserve Q01-Q04, field clocks, missing/null, alternatives and actual child/head/base evidence |
| Context rule 2: PR-to-Git dependency direction | Preserve independent Core facts and typed portable references; no reverse required Access/Context row |
| Context rule 3: mixed tables | Preserve key-level split; no whole-table or blanket configuration-JSON move |
| Context rule 4: exact Provider text | Preserve Context UTF-8/SHA-256 ownership and separate GC policy |
| Context rule 5: no Publication/API history reinvention | Preserve; per-assignment Access permission is local execution control, not domain eligibility/Publication |
| Isolation: Git-only paths | Preserve init/local input/query/qualified export/backup; no mandatory credential/network discovery |
| Isolation: cross-store references | Preserve application validation, no cross-file SQLite FK and no fabricated verification |
| Isolation: independent writes | Preserve Core-first factual success if Context later fails; Access plans do not create a three-authority COMMIT |
| Isolation: snapshots | Preserve coherent Core/paired snapshots and truthful absent/stale/conflicting dependencies |
| Isolation: retention/cascade | Preserve no deletion of Git facts due to Context/Source/Access changes |
| Isolation: backup | Preserve truthful git_only/paired scopes, pairing/format/actual-domain checks and fresh activation; add separate Access history backup |
| Isolation: Search/Operational loss | Preserve exact-source fallback, explicit rebuild, and unavailable old continuation rather than zero-cost resume |
| PF-P06/P08 mapping | Change placement only; paired domain backups remain valid without Access |
| PF-P05 mapping | Preserve no present domain-text GC; GC-01/02 remain constraints on future Context GC, GC-03/04 stay unselected |
| PF-P14/P15/P07 mapping | Preserve appropriate Search sources and relaxed disposable atomicity without weakening Core/Context consistency |
| Not-reopened paragraph | Preserve UUID, Q01-Q04, Coverage, trust, real captures, PF retained clauses and ADR 0001; apply existing 0014/0026/0028 scoped overrides |
| Non-goals / deferred work | Preserve no implicit real extraction/GC/merge; no exact table count from baseline; DS-R01/R03-R08 remain deferred in their own scopes |
| Acceptance 1 | Preserve Core-only round trip and metadata-only zero-body operation |
| Acceptance 2 | Preserve append-only attacks and force-push observation retention |
| Acceptance 3 | Preserve Provider/current text outside Core and no false full restore |
| Acceptance 4 | Preserve independent PR-triggered Core facts and honest partial cross-store outcomes |
| Acceptance 5 | Preserve retained-byte and semantic validation, original identity and correct-store fallback under 0026/0028 |
| Acceptance 6 | Preserve exact effective tree, independent review and ADR 0001 development versus release evidence |

The five-store addition and owner-confirmed Scope rules need no re-vote here.
A1 direct-key/local-permission details are in the [engineering contract](access-a1-contract.md).
The whole-record acceptance reference and coherent inbound-link replacement must
still be completed before removing ADR 0003. A successful SQL prototype does not
establish semantic preservation or independently approve the replacement.

## Inbound reference inventory and retirement procedure

A live exact-filename code search returned 24 default-branch file hits at S1. Search
is an index, not a complete checkout walk; this list is a lower-bound inventory,
not certification that these are the only references. PR-only links/mentions in
0029 and the Access design are additionally known. AGENTS contains named four-store
summaries even where the complete filename is absent.

| Handling on actual retirement | Observed paths / families |
| --- | --- |
| Current entry points: retarget to successor and correct scope wording | `README.md`, `docs/architecture.md`, `docs/implementation-status.md`, `docs/adr/README.md` |
| Active ADR references: distinguish current authority from historical baseline | ADRs 0002, 0004-0010, 0012-0014, 0026, 0028 |
| Historical documents with current guidance banners | `docs/phase2/decision-register.md`, `docs/phase2/documentation-status-audit.md` |
| Historical integration narrative | `docs/integration/design-stack-main-review-2026-10-15.md`; preserve facts, pin old-source references rather than rewriting outcomes |
| Procedural guide | `.agents/skills/three-store-invariants/SKILL.md`; preserve its baseline recipes and retarget current-target guidance |
| Immutable distribution evidence | `docs/implementation/evidence/seven-pr-combined-20261016/reviews/d/sdist-members.json`, `docs/implementation/evidence/p5-correction/distribution-clean/distribution-manifest.json`, `docs/implementation/evidence/schema21-baseline-20261016/independent-d/distribution-source-manifest.json`; do not edit old membership evidence |
| Not exhausted by exact-filename search | AGENTS, MkDocs navigation, symbolic ADR 0003/"four stores" mentions, current design and P7 references; inspect full checkout |

After explicit whole-replacement acceptance, one coherent lifecycle change must:

1. Record the real approval reference and date, move 0029 from Proposed to Accepted.
2. Verify every preserved source family above has operative successor wording;
   do not rely solely on a link to a file about to be removed.
3. Update active authority links, retaining historical baselines as pinned Git URLs
   or plain provenance identifiers. Fix wording, not merely link destinations.
4. `git rm` only the replaced ADR 0003; do not copy its obsolete text to an archive.
5. Update the index/governance migration-debt entry for this completed case only;
   do not silently expand the pre-adoption exception or claim unrelated cleanup.
6. Walk the exact final checkout for live links and navigation, run relevant Markdown
   validation, and review the parent diff. Leave archived execution hashes intact.

This review prepares those operations; it intentionally does not delete the file
before approval or claim full-checkout link closure after clone failed DNS.

## Independent review work packet

An independent coding/review agent may read the PR branch and use subagents, with
disjoint ownership. Start by recording `git rev-parse HEAD` and checking the PR's
actual parent. Read the current ADR index/policy, 0029, this ledger and A1 contract.
Do not reopen Q-S1-Q-S4 A or the history/MAX-time decision.

Reviewer K: audit the registration-fact triple, same-time alternatives, replay and
ADR 0017/0028 semantics. Reviewer G: attack full grant FKs, profile/binding/context
ABA, route disable/reenable, restored grants and rank-before-permission. Reviewer D:
check every old clause's retained meaning and classify exact-checkout inbound links.
Run the two supplied probes plus independently authored counterexamples on the
product-supported SQLite binding; inspect rather than trusting their PASS receipts.
Return severity, precise file/line, minimal reproduction, affected invariant,
reviewed commit/tree and executed/unexecuted evidence. Review-only: do not merge,
activate P8, operate on real catalogs or alter accepted decisions.

No independent agent was started in this session: the exposed Browser interface
was read-only and discovery found no directly invokable review subagent. This packet
is ready for delegation, not a claim that delegation or independent review occurred.
