---
name: lessons-to-skills
description: Capture verified reusable procedures as repo-local Agent Skills after repeated trial-and-error, recurring successful workflows, non-obvious review corrections, or difficult investigations. Use at stable checkpoints and before handoff, including repeated design-only ADR stack updates; prefer improving an existing skill.
---

# Turn debugging lessons into reusable skills

Use this procedure when repeated trial-and-error, a recurring successful workflow, a difficult investigation, or an independently discovered defect produced a **verified and generalizable** technique other agents could reuse. At stable checkpoints, actively assess and record that technique within the task's authorized scope instead of only proposing that someone remember it. Do not create a new skill for every test failure, private incident, speculative workaround, or ordinary one-off change.

1. Search existing `.agents/skills/*/SKILL.md` descriptions and the current docs for the same procedure. Improve a matching skill instead of creating a near-duplicate.
2. Establish evidence: exact observed symptom, root cause, successful correction or reliable diagnosis, verified commands and tests, affected environments, and a counterexample or exclusion. Attribute old results to their actual commit/tree; distinguish development checks from full release acceptance.
3. Write concise, imperative guidance in `.agents/skills/<descriptive-name>/SKILL.md`. Include YAML `name` and `description`; make the description clear about **when** to use it. Put optional lengthy examples in `references/` and deterministic repeatable checks in `scripts/`.
4. Include failure symptoms, safe diagnostic sequence, fix or decision boundary, verification command, and cases where the method is inappropriate. Avoid volatile absolute workspace paths and old SHA/count assumptions.
5. Do not invent design or trust policy, override active owner decisions, grant new execution permissions, relax security gates, or reintroduce superseded Publication machinery.
6. Remove secrets, private repository contents, raw authenticated API payloads, retained databases, and misleading claims from the skill. Keep only minimal sanitized examples.
7. Validate frontmatter, referenced files, commands, and any scripts. Review the skill diff. Include the change in an authorized task PR, or record the exact suggested skill update in the handoff if edits are not allowed.
8. At handoff, list which existing skills were used or updated and any new skill path, plus the reproducible lesson that motivated it. If nothing generalizes, explicitly skip skill creation.

Reviewers inspecting a frozen read-only tree can recommend lessons but should not alter that tree. The implementing agent owns the subsequent skill edit and revalidation.

The goal is to help the next agent avoid repeating the same failed investigation, **not** to store an exhaustive transcript.

For repeated design-only ADR stack work, read [the verified stack-update procedure](references/design-only-adr-stack-updates.md). It covers live parent pinning, current-versus-historical decision reconciliation, avoiding stale patches after broad replacements, and binding documentation checks to the published feature tree. Use it when that workflow recurs; it is not ADR governance adoption or implementation/merge permission.

## Status-reconciliation lessons are scope-sensitive

**Observed failure pattern:** a decision register's overview says a whole group
is resolved while individual sections still say selection is paused. Old
implementation handoffs can also be mistaken for current pending work. The root
cause is updating only an umbrella label without mapping the scope and evidence
of each superseding decision.

When capturing a correction of this kind:

1. Pin the source revision. Map each old question to the explicit later decision,
   retained implementation guarantee and residual policy separately. A newer date
   alone is not supersession, and implementation existence is not owner approval
   of its permanent retention or a broader guarantee.
2. Update the current register, overview and applicable agent instructions
   together. Under the accepted [ADR 0011](../../../docs/adr/0011-adr-governance.md)
   and [ADR policy](../../../docs/adr/policy.md), retire superseded ADR decision
   text only after a reviewed carry-forward of all still-binding clauses; use
   Git history for retired text rather than copying it into another active file.
   Historical execution receipts are distinct evidence and must keep their exact
   original meanings; never relabel an old failed execution as PASS.
3. Separate accepted policy, implementation/integration and actually executed
   verification. Keep source-unclear IDs unresolved rather than guessing their
   meaning. A preserved word such as "paused" is not itself a current defect.
4. Check links, unchanged decision text and the final diff. Verify a copied
   snapshot with `git rev-parse BASE:path/to/original.md` against
   `git rev-parse HEAD:path/to/snapshot.md`; verify documentation scope with
   `git diff --name-only BASE...HEAD` and whitespace with `git diff --check`.
   Replace BASE/HEAD and paths with the inspected revisions and files.

Do not apply this procedure to silently settle a genuine new policy conflict,
rewrite immutable evidence, or claim runtime acceptance from prose checks. The
[status audit](../../../docs/phase2/documentation-status-audit.md) records the
concrete diagnosis and source map; keep run-specific checks in the PR evidence.
