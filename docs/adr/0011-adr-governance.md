---
status: accepted
date: 2026-10-15
replaces: []
refines: []
---

# ADR 0011: Shared ADR policy and an optional procedural skill

- **Decision & owner acceptance:** The owner explicitly adopts the [governance proposal PR #52](https://github.com/TakashiSasaki/git-repo-db/pull/52) on 2026-10-15, including the specific repository adaptations reconciled in [policy section 10](policy.md). This is a repository-wide **Level 2 developer/agent workflow decision**, not a product-data-model change.
- **Single authority:** The [ADR operating policy](policy.md) is the normative text. The [common ADR index](README.md) is the entry point; [full](template.md) and [Mini-ADR](template-mini.md) templates are repository files; the optional [adr-workflow skill](../../.agents/skills/adr-workflow/SKILL.md) is procedural, not another authority. Humans and coding agents without plugin/skill support can use these Markdown files.
- **Existing history:** PR #52's original proposal commit `8337cef911e664b1a2c267c837a05ddaa0c762f9` was based on PR #51 before the owner accepted the additional GCTX and notes design stack. PR #69 subsequently integrated accepted ADRs through 0027 into main. This governance adoption explicitly keeps their original historical Git commits and all still-applicable design authority. Adopted policy section 9 enumerates pre-adoption migration exceptions **through ADR 0027**; it does not perform or authorize blanket ADR file retirement.
- **Constraints / Do NOT:** Do not make an agent-specific skill, external Issue or template the sole norm; infer approval from silence; reuse retired/reserved ADR IDs; replace by newest-number-wins; turn one rejected alternative into a universal prohibition; delete an ADR containing still-binding clauses before reviewed carry-forward; treat old provisional alternatives as reopened owner questions; confuse accepted target with implemented runtime or executed release tests; or adopt an unrelated product redesign through this workflow.
- **Decision process:** Choose full ADR/Mini-ADR/short implementation rationale by actual project impact; keep four-digit allocation monotonic and coordinate active branches; record explicit acceptance, provenance, scoped refinements/replacements and Do NOT reasons; prefer design-first Stacked PRs with independent review as applicable. Separate decision acceptance, branch integration, runtime implementation and executed verification.
- **Consequences and remaining work:** The policy is accessible from a checkout and keeps one source of truth, but requires index/metadata maintenance and a **separate future reviewed, semantics-preserving migration** of historical partial overrides and old formats. Current main is not certified to satisfy every prospective active-only ADR-file lifecycle rule. No automatic product implementation, migration, release, extra publication allowlist, Pages configuration change or future unrestricted merge permission follows this adoption.
