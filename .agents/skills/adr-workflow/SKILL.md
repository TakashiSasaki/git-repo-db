---
name: adr-workflow
description: Create, review, refine, replace, or retire Architecture Decision Records in git-repo-db. Use when a task changes design decisions or ADR governance, when reconciling design stacks, or before an ADR handoff. Discover the shared policy and active decisions without duplicating them.
---

# ADR workflow

## Authority and entry point

Read [the common ADR index](../../../docs/adr/README.md), then the relevant accepted
records and [the operating policy](../../../docs/adr/policy.md). Check their actual
adoption state: a proposed policy or ADR does not override an accepted decision.
This skill is an optional procedure, not a second normative document or additional
permission. Humans and agents without skill support can use the same Markdown
sources directly. Do not copy their policy text or templates here.

## Procedure

1. Establish the current owner task, checked-out branch/commit, actual stack base
   and permitted operations. Distinguish accepted target, implemented behavior and
   executed verification. Stop for a real unresolved decision; do not select an
   option from a recommendation or a stale handoff.
2. Read only relevant accepted ADRs after scanning the index. Apply explicit scoped
   replacements, not newest-number-wins. Inspect the documented legacy migration
   cases before changing an older record; omission from a new summary is not repeal.
3. Apply the policy's triage and authoring guidance. Record a short reason for the
   chosen level. Reuse the [full template](../../../docs/adr/template.md) or
   [Mini-ADR template](../../../docs/adr/template-mini.md), not an agent-only copy.
4. Before allocating an ID, inspect the index watermark, reachable history and
   active remote design work. Coordinate collisions or incomplete evidence instead
   of filling a gap. Preserve established domain decision identifiers.
5. Classify the operation as creation, editorial correction, additive refinement,
   substantive replacement, or retirement. For replacement, map changed and
   still-valid clauses to successors before removing anything. Use the policy's
   coherent lifecycle/index/link update; never archive obsolete ADR text in HEAD.
6. Keep proposed and accepted records separate. Record real approval evidence;
   preserve all still-open choices. Follow the owner-authorized design-first/stack
   workflow. A documentation task never independently authorizes implementation,
   a merge, a release or retained-data mutation.
7. Verify the exact-parent diff, metadata, scope, IDs, index, links and retirement
   mapping. Review copied Do NOT rules for accidental scope expansion. Report
   actual checks and limitations; do not report acceptance examples as tests run.
8. Hand off the branch/commit and PR dependencies, decision versus proposal status,
   preserved decisions, unresolved migration work, and checks performed or blocked.
   Use the existing lessons-to-skills procedure only for verified reusable learning.

## Read-only checks

From the repository root, substitute the actual stack parent for `BASE`:

```sh
git status --short
git diff --check BASE...HEAD
git diff --name-status BASE...HEAD
git log --all --full-history --name-only --format= -- docs/adr/
```

These commands do not prove link correctness, approval or complete remote history.
Inspect links separately and report missing refs. For a retired file's exact text,
use the policy's `git show COMMIT:path` procedure, not a patch described as a full
file. Never run a mutating cleanup command merely because a filename looks old.

## Boundaries

Do not use this skill to automatically migrate the existing ADR collection,
reopen GCTX decisions, enforce a universal technology ban, purge execution receipts,
or claim that every agent automatically discovers skills. ADR 0011 and its policy
are now owner-accepted; never treat their adoption as
completion of the bounded pre-adoption migration or permission to retire accepted
clauses or implement unrelated design work.
