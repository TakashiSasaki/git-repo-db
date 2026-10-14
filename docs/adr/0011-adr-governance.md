---
status: proposed
date: null
replaces: []
refines: []
---

# ADR-0011: Shared ADR policy with an optional procedural skill

- **Decision & Context:** Propose the shared developer/agent [ADR policy](policy.md),
  discovered through the [single index](README.md), with repository-resident full
  and Mini-ADR templates and an optional ADR workflow skill. The owner requested
  repository placement on 2026-10-15 and supplied three guidelines. Their common
  principles are the source basis; the repository-specific reconciliations in
  policy section 10 are explicitly proposed for review, not assumed approved.
  This is a Level 2 repository development-workflow decision, not a product
  architecture change. Existing ADRs 0001-0010 and GCTX-M01-M07 retain their exact
  decision scope; legacy migration is separately bounded in policy section 9.
- **Constraints / Do NOT:** Do not make a skill, a vendor-specific instruction
  file or an external Issue the only policy authority. Do not duplicate the policy
  or templates in the skill, promote a proposal by silence, reuse an issued ID,
  discard still-binding clauses during retirement, or convert an unchosen option
  into a blanket prohibition. Do not infer implementation, merge or deployment
  permission from adopting this documentation workflow. Do not silently expand
  the legacy exception or claim the existing tree has already been migrated.
- **Reason & Ref:** A normal Markdown policy serves humans and every agent;
  a thin, optional procedure aids discoverability without tool lock-in or another
  source of truth. The cost is keeping the index and lifecycle metadata synchronized
  and performing a scoped follow-up migration instead of unsafe bulk deletion.
  Source identification, differences and rationale are in policy section 10.
  The documentation base is PR #51, commit
  `a79924f36ddb03c2f5472f14f0233531bd7788a2`, above PRs #44-#50.
  No approval of these adaptations, implementation, runtime test execution,
  legacy ADR removal, merge or website publication is asserted by this record.
