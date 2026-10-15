# ADR operating policy for developers and coding agents

**Status: owner-accepted on 2026-10-15 in [ADR 0011](0011-adr-governance.md).**
This is the single normative ADR governance policy; the [ADR index](README.md) is the common entry point.
Adoption includes the section 10 repository-specific adaptations, but changes no accepted product-domain contract and grants no general implementation, merge or release permission.

## 1. Purpose and principles

Record the decision, its scope, reasons and consequences so a developer or coding agent can discover the current constraints without reconstructing a conversation. Apply three principles from the supplied guidelines:

1. **Anti-ADR fatigue:** triage decisions into full ADR, Mini-ADR, or a short implementation rationale.
2. **Context hygiene:** keep current accepted decision text in the active decision set; retire superseded decision files from the current tracked tree and retain their history in Git.
3. **Tool independence:** ordinary Markdown files and Git are sufficient. Neither a particular agent, a skill loader, an IDE ignore file nor access to GitHub discussions is required to understand a binding decision.

In this policy, MUST / MUST NOT state requirements, SHOULD a recommendation requiring a reason to depart, and MAY a permission within the current owner's task. No policy or skill grants execution permissions beyond that task.

## 2. Scope, authority and states

The current owner's explicit decisions take precedence over accepted ADRs and their explicit scoped replacements, then unsuperseded production contracts, then historical evidence. A later date, larger ADR number, agent recommendation, implementation, merge or green check is not by itself a new decision.

Keep **decision acceptance**, **branch integration**, **implementation**, and **executed verification** separate. An owner-accepted target may be in an unmerged design stack and unimplemented. A proposed ADR is not binding. Record an actual approval reference before changing `status` to `accepted`; do not pre-accept a template or infer approval from silence.

The active index applies to the checked-out branch and its recorded accepted design dependencies, not automatically to every branch or to the deployed software. Read the relevant ADRs after scanning the index. Never infer that an omitted legacy contract is repealed. Report conflicting rules or missing dependencies rather than guessing.

Except for the enumerated migration cases in section 9, the accepted snapshot MUST contain accepted, currently applicable decision files only. An unmerged review branch MAY contain clearly marked `proposed` ADRs, listed separately from Active Decisions. Before integration, accept them explicitly or remove them from the proposed integrated tree. Templates, this operating policy, and short migration metadata are not individual accepted product decisions. These distinctions make the supplied HEAD-only rule usable with design-first Stacked PRs.

## 3. Triage

| Level | Nature and indicative cost | Scope | Record |
| --- | --- | --- | --- |
| 3: Full ADR | Type 1 / architectural foundation; at least a week to replace, data migration, or substantial cost | System-wide, cross-repository/team, long-lived operation | `docs/adr/NNNN-slug.md`, using [the full template](template.md) |
| 2: Mini-ADR | Important reversible choice or shared convention; days to about a week | Repository-wide rules or development workflow | The same directory and ID space, using [the Mini-ADR template](template-mini.md) |
| 1: No ADR | Local reversible implementation choice; hours or one small PR | Function, class or module | One or two sentences in a PR description, commit message or relevant code comment |

Use the supplied five-question checklist:

1. Would replacement require at least one week of work or data migration?
2. Does it affect multiple services, repositories, or another team's interface?
3. Does it introduce paid SaaS, a managed cloud service, or a licensing decision?
4. Does it create a direct security, performance, availability or compliance tradeoff?
5. Did alternatives cause over 30 minutes of discussion or ten chat exchanges, or would the reason otherwise be difficult to recover later?

Any Yes to 1-4 requires Level 3. If 1-4 are No but 5 is Yes, use Level 2. If all are No, Level 1 is sufficient. Estimate cost in this project's actual **unreleased, single-developer, no-backward-compatibility-required** setting; do not invent migration obligations merely to increase the level. A mandatory explicit owner decision is still recorded even when discussion was short.

Mini-ADRs MUST be in the repository, not only in an Issue. External discussions MAY provide supporting detail; the essential decision and reason MUST remain understandable from a checkout. Concrete scope examples: changing Git Core admission or the authoritative-store boundary needs a full ADR; adopting an ADR maintenance workflow can use a Mini-ADR; correcting a spelling error needs no new ADR.

## 4. Files, index and numbering

Use `docs/adr/README.md` as the single discovery index, `policy.md` for this policy, `template.md` and `template-mini.md` for authoring. Root README and agent instructions link to the index rather than maintaining another ADR registry. Keep the index short enough to scan, then load only relevant decision files. Do not copy the entire policy or decision catalog into a skill.

Active Decisions MUST identify the record, scope, one-line decision, Do NOT constraints and applicable status/override. The authoritative meaning stays in the individual decision, not an oversimplified index row. Synchronize the index whenever a decision is added, replaced, retired or changes approval status.

Allocate a four-digit, zero-padded, monotonically increasing ID and descriptive lowercase hyphenated slug. Full and Mini-ADRs share the same sequence. IDs and existing external decision identifiers such as `GCTX-M07` have different roles; do not renumber or reinterpret the latter.

The index maintains a **highest allocated number**, including retired and publicly proposed IDs. Never decrement it or reuse a gap. Before allocating, inspect that watermark, reachable Git history including deletions, current remote branches and open design PRs. The highest filename in the working directory alone is insufficient. Coordinate concurrent allocations; on a collision or incomplete history, resolve the allocation before publication instead of assuming an ID is free. Retain the watermark when closing a rejected proposal. Recheck the current base before opening or updating a PR. If the four-digit namespace is exhausted, propose a naming change; do not wrap around.

## 5. Content and metadata

Put **Decision** and **Constraints / Do NOT** first, followed by **Context & Reason**, **Consequences**, and **References**. A full ADR describes benefits and accepted disadvantages, scope and preserved invariants. A Mini-ADR uses three substantive items: Decision & Context, Constraints / Do NOT, Reason & Ref; it is not limited to three physical lines at the expense of meaning.

New full and Mini-ADRs share YAML metadata: `status`, `date`, `replaces`, and `refines`. Use `status: proposed` and `date: null` until accepted; fill `date` with the actual acceptance date as `YYYY-MM-DD`. Empty replacement/refinement lists are `[]`, not an ambiguous string. `replaces` lists fully retired files; `refines` lists still-valid decisions extended without contradiction. Explain the exact affected and preserved clauses in the text. Legacy header formats remain readable until the scoped migration in section 9.

For replaced files outside this directory, record their repository-relative paths. For files inside this directory, a filename is sufficient. These are history identifiers, not live Markdown links to deleted files. When an exact pre-retirement commit is already known, record it as additional provenance. Do not require the hash of the commit being authored inside its own contents.

A Do NOT rule MUST state its actual scope and short reason. Preserve relevant lessons from rejected alternatives and retired approaches, but **not selected** does not automatically mean **universally prohibited**. For example, rejecting a technology for one subsystem does not prohibit it for every unrelated tool. Where appropriate, prohibit substituting it within the decided scope without a new accepted ADR. Do not invent a prohibition merely to fill the template; write `None identified` when accurate. Avoid long rejected implementations or ambiguous alternative code in active ADRs; retain a short reason and a history/discussion reference instead.

Keep unsettled questions explicitly unsettled. A later ADR resolving a previously open question can be an additive refinement; that is different from reversing an accepted clause. Updating a link, spelling, an approval/status field, or an already-resolved question's reference without changing decision meaning is an editorial change and MAY use the existing file. A substantive reversal MUST NOT be disguised as editorial cleanup.

## 6. Lifecycle and PR boundaries

### Create and accept

Triage, identify affected accepted decisions, allocate an ID, and write from the appropriate template. Record the exact proposed scope and unresolved boundaries. Add a Proposed entry, request owner review, and move the entry to Active Decisions only with explicit acceptance.

This project's default is **design first, then implementation in dependent Stacked PRs**. A Level 3 architectural decision MUST be settled before implementing that change. Level 2 co-location with implementation is allowed only when the current owner task explicitly permits that workflow and no accepted decision is reopened. This qualifies the general source documents' more permissive same-PR examples; it does not weaken the project's existing authorization boundary. Each PR names its actual base/dependencies, changed scope and validation limits. Acceptance does not authorize merge, release, deployment or retained-data operations.

### Replace, including partial replacement

A reversal requires a new accepted ADR and ID. Document what changes, what survives, and the applicable scoped Do NOT lessons. Add `replaces`, remove the old file with `git rm`, and update the index and affected current links **in one coherent commit** after the new decision is accepted. Do not leave both contradictory decisions in the active tree or add an archive copy of the superseded ADR elsewhere in HEAD.

If only part of the old ADR is replaced, **do not discard the still-binding remainder**. Carry its still-valid clauses and rationale into the replacement, or split them into separately indexed accepted records, with an explicit clause-to-successor map. Obtain review that this is preservation, not a new decision. Only then retire the entire old file. If that mapping cannot be established, report the blocker; do not guess, silently weaken a rule, or delete the old ADR for cosmetic compliance. The pre-existing cases in section 9 are a migration debt, not a precedent for new indefinite partial-supersession chains.

An additive, nonconflicting refinement MAY keep both files with `refines`, updating genuinely stale unresolved-status annotations editorially. Never call a contradictory replacement an additive refinement merely to avoid retirement.

### Retire without replacement or reject

When the entire subject no longer exists and no still-binding invariant is lost, remove the ADR and its active entry in the authorized removal PR; state the reason in the commit. Fix current links. A rejected proposal is not an active decision: preserve its discussion/history, remove its integrated proposal file, and keep its allocated ID retired. A binding decision *not to introduce* something is different: it requires explicit acceptance and an ordinary active ADR.

### Investigate history

Git history is the audit source for retired ADR text, not a second active Markdown archive. Read history only when the task requires it and label recovered material as historical. Example read-only commands, with the actual file and known pre-retirement commit substituted:

```sh
git log --all --full-history -m --no-renames --diff-filter=D --summary -- docs/adr/
git log --all --follow -- docs/adr/0002-three-store-boundary-architecture.md
git show PRE_RETIREMENT_COMMIT:docs/adr/0002-three-store-boundary-architecture.md
```

`git log -p` displays a patch, not necessarily an exact standalone prior file; use `git show COMMIT:path` for the latter. Inspect the relevant parent explicitly when a deletion is in a merge. These paths are examples, not claims that ADR 0002 has been deleted. Recovery needs the relevant reachable commits/objects: a shallow clone, history rewrite or missing refs may make evidence unavailable. Report that rather than asserting unconditional recoverability. Removing a tracked file does not purge old clones or external search indexes; it reduces stale text in the current checkout, not every possible source of context contamination.

## 7. Skills and human access

The policy is a normal repository document and remains usable without skill support. The optional [ADR workflow skill](../../.agents/skills/adr-workflow/SKILL.md) provides procedural discovery, review and handoff steps. It MUST link to this policy and the index, not become an alternative policy text, duplicate templates, or silently resolve undecided architecture. It must not grant tool, merge or deployment permissions. Its existence is not a claim that every agent automatically discovers it.

Use the existing lessons-to-skills procedure for verified reusable learning. For ADR history, follow this policy's retirement rule rather than copying superseded decisions into a current snapshot. Actual execution receipts are a different category: preserve their exact meaning and never rewrite failure as success. The policy does not order deletion of every historical report, code example or design document in the repository.

## 8. Review and evidence

Before submission, verify approval versus proposal status, triage, scope, new/reused IDs, preserved clauses, replacement/refinement semantics, index synchronization, frontmatter, relative links, removed-file references and task permissions. Check the diff against the **actual stack parent**, not only main. Read accepted decisions relevant to the task; a table cannot replace that review.

For documentation-only changes, perform appropriate static/diff/link checks and report what ran, failed or was not executable. Follow ADR 0001: do not demand a full runtime suite or duplicate local work in development CI merely for prose. Future acceptance examples are specifications, not test results. Preserve exact commit/tree references for executed evidence. Do not claim this policy installs a CI linter or proves product acceptance.

## 9. Existing-repository migration: explicit, not completed here

The proposal was originally authored against PR #51 at `a79924f36ddb03c2f5472f14f0233531bd7788a2` before [PR #69](https://github.com/TakashiSasaki/git-repo-db/pull/69) integrated the accepted Git Core/Context design stack through ADR 0027. At adoption, ADRs 0001–0010 and 0012–0027 plus older accepted external-path decisions already exist. This governance policy **does not rewrite, renumber, delete, re-accept or reverse** any of their settled substantive clauses. The accepted source/identity/notes/retained-byte and GCTX-M01–M09 contracts remain intact; ADR 0026's recovery-without-quarantine and ADR 0027's unauthenticated-origin policy govern their affected scope. Existing pre-policy decisions may contain historical alternatives and partial scoped supersessions. These are enumerated migration exceptions, **not** instructions to remove still-binding requirements or reopen completed choices.

| Existing material | Known mismatch with the target policy | Required follow-up before retiring or relocating it |
| --- | --- | --- |
| ADR 0002 | Contains the implemented Three-Store baseline and clauses partially superseded by ADR 0003 | Map each retained PF clause and implementation-only statement to its correct successor/reference; do not erase still-binding semantics |
| ADR 0003 | Verified-only metadata admission was narrowly replaced by ADR 0004; append-only and four-store boundaries remain binding | Preserve the valid boundary/backup rules and map only the replaced admission clauses |
| ADR 0004-0010 | Pre-policy format and refinement chains; some records contain old pending-status text and discussed alternatives | Audit current versus historical statements without changing chosen GCTX options or claiming pending implementations passed |
| ADR 0012–0013 | Earlier physical-instance and active-quarantine/count material partially superseded by accepted ADR 0026 | Carry forward still-valid immutable copy identity and byte-validation rules; treat old quarantine/count or same-suspect-DB continuation as historical, not current authority |
| ADR 0014–0025 | Existing scope/notes/capture/claim/budget ADRs contain choice alternatives, old unresolved-status text and successive scoped refinements | Audit current versus historical statements against actual accepted successors through ADR 0027; retain binding clauses until separately reviewed carry-forward; do not mass delete |
| ADR 0026–0027 | Current accepted recovery and origin-report ADRs include historical evidence, examples and supersession explanations | Preserve current binding meaning, including the no-quarantine rule and no-PKI external-origin acceptance; any optional active-only cleanup needs an independent scoped review |
| Transport-independent Core and No Independent Publication decisions | Accepted records outside `docs/adr/`, with historical baseline/status text | Keep them discoverable from the common index until an explicit semantics-preserving relocation/replacement updates inbound links |
| Root/nested agent guides, handoffs and skills | Existing repeated summaries and historical-snapshot advice | Remove duplication incrementally after checking authoritative coverage; ADR decision snapshots must not become a new archive in HEAD |

This expressly updated pre-adoption exception covers the existing ADRs through 0027 and MUST NOT be expanded silently for later design work. Close entries through separately scoped, reviewed documentation work, preserving original history and approvals. A reviewer must not certify the repository as fully migrated or free of stale context after this bootstrap PR. No product implementation, four-store migration, website-publication expansion or mass historical cleanup is included.

## 10. Source basis and repository-specific adaptations

The owner supplied three DOCX guidelines on 2026-10-15. Similar filenames do not establish revision precedence; no one attachment is assumed to supersede the others. The policy preserves their shared framing and identifies adjustments rather than silently merging inconsistent details.

| Source identification | Basis used |
| --- | --- |
| S1: `Architecture Decision Record (ADR) 運用規範`, subtitle containing `共生` and `コンテキスト汚染防止` | Three principles; sections 2-6 on triage, lazy loading, templates, retirement and agent workflow |
| S2: `ADR運用規範（人間・コーディングエージェント共通ガイドライン）`, subtitle containing `協調開発` | Non-reused IDs, repository-resident Mini-ADRs, related-link maintenance and lifecycle guidance |
| S3: `Architecture Decision Record (ADR) 運用規範`, subtitle containing `双方に最適化` | Same core rules; explicit Level 3 design-first versus Level 2 same-PR distinction |

**Repository-specific adaptations accepted with ADR 0011, not direct quotations or new product-domain decisions:**

- Mini-ADRs are repository files (S2/S3), not Issue-only records permitted by S1. Shared frontmatter normalizes the differing Mini-ADR examples.
- The five-question threshold uses one week, consistent with all checklists; S1's full-ADR matrix says several weeks. The checklist governs the overlap.
- The detailed policy is separated from the scan-friendly index, while retaining one entry point and no second rule authority.
- Proposed versus accepted branch states and explicit design-stack authorization qualify the generic HEAD and same-PR wording.
- The allocation watermark/history/concurrency checks close the gap in S3's working-directory maximum rule when the highest ADR is deleted.
- Scoped Do NOT rules preserve rejection lessons without inventing universal bans; partial-replacement carry-forward prevents loss of valid decisions.
- Read-only `git show` recovery and reachable-history caveats qualify the source examples' stronger recovery wording.
- Section 9 is a bounded migration plan for the actual repository, not a claim present in the supplied generic documents.

The DOCX attachments and their illustrative ECS/ORM/date-library choices are not copied into the repository as competing policies or product decisions. Essential content is carried here so the policy does not depend on attachment access. Operational command/format references: [Git log](https://git-scm.com/docs/git-log), [Git show](https://git-scm.com/docs/git-show), and [Agent Skills specification](https://agentskills.io/specification). These references explain mechanisms; they do not override owner decisions.
