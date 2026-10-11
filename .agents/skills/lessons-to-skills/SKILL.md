---
name: lessons-to-skills
description: Capture reusable, verified engineering lessons as repo-local Agent Skills after repeated failed attempts, non-obvious review corrections, or difficult investigations. Use during debugging retrospectives and before handoff; prefer improving an existing skill.
---

# Turn debugging lessons into reusable skills

Use this procedure when a repeated failure, difficult investigation, or independently discovered defect produced a **verified and generalizable** technique other agents could reuse. Do not create a new skill for every test failure, private incident, speculative workaround, or ordinary one-off change.

1. Search existing `.agents/skills/*/SKILL.md` descriptions and the current docs for the same procedure. Improve a matching skill instead of creating a near-duplicate.
2. Establish evidence: exact observed symptom, root cause, successful correction or reliable diagnosis, verified commands and tests, affected environments, and a counterexample or exclusion. Attribute old results to their actual commit/tree; distinguish scoped from full acceptance.
3. Write concise, imperative guidance in `.agents/skills/<descriptive-name>/SKILL.md`. Include YAML `name` and `description`; make the description clear about **when** to use it. Put optional lengthy examples in `references/` and deterministic repeatable checks in `scripts/`.
4. Include failure symptoms, safe diagnostic sequence, fix or decision boundary, verification command, and cases where the method is inappropriate. Avoid volatile absolute workspace paths and old SHA/count assumptions.
5. Do not invent design or trust policy, override active owner decisions, grant new execution permissions, relax security gates, or reintroduce superseded Publication machinery.
6. Remove secrets, private repository contents, raw authenticated API payloads, retained databases, and misleading claims from the skill. Keep only minimal sanitized examples.
7. Validate frontmatter, referenced files, commands, and any scripts. Review the skill diff. Include the change in an authorized task PR, or record the exact suggested skill update in the handoff if edits are not allowed.
8. At handoff, list which existing skills were used or updated and any new skill path, plus the reproducible lesson that motivated it. If nothing generalizes, explicitly skip skill creation.

Reviewers inspecting a frozen read-only tree can recommend lessons but should not alter that tree. The implementing agent owns the subsequent skill edit and revalidation.

The goal is to help the next agent avoid repeating the same failed investigation, **not** to store an exhaustive transcript.
