# Implementation status — implemented Three-Store baseline

> **Current navigation:** This document is a dated historical snapshot; its
> present-tense statements describe that snapshot. For the implemented Schema 21
> runtime and the distinction from opt-in and accepted target design, see
> [Current runtime reference](current-runtime-reference.md). Original body and
> historical evidence remain unchanged.

**Accepted successor target (not a claim of default activation):** [ADR 0029](adr/0029-independent-access-store.md), approved 2026-10-19 as the replacement for historical ADR 0003, preserves strictly INSERT-only Git Core, independent **durable Context**, disposable Operational and rebuildable Search, and adds independent durable **Access** for Scope/Locator/Connection Configuration/local approvals. The [transition plan](architecture/git-core-context-transition-plan.md) and [Access design](architecture/access-store-design.md) inventory the remaining product changes. The earlier `main` three-store/84-table baseline remains historical implementation evidence; accepting the five-store architecture alone does **not** certify any new runtime implementation, P8 activation or release verification.

**Status audited at:** `fb3b1fb4d5e1436c58677d2e867708502fbbc64b`.

Publication removal and the Three-Store implementation are integrated in `main`.
[PR #38](https://github.com/TakashiSasaki/git-repo-db/pull/38) records the accepted
PF-P01–PF-P17 architecture; [PR #39](https://github.com/TakashiSasaki/git-repo-db/pull/39)
implements the split. The inspected [packaged schema composition](../src/repo_catalog/adapters/sqlite/schema.py)
defines Core Schema 21, Operational Schema 1 and Search Schema 1.

This is an implementation/integration observation, **not full release acceptance**.
Use exact-revision execution/review receipts to assess verification. A local test
report, hosted development check, independent review and explicit release
qualification are different evidence. This documentation-only audit runs no
application or release test and invents no reviewer approval.

[ADR 0002](adr/0002-three-store-boundary-architecture.md) remains the policy
register; the [Phase 2 register](phase2/decision-register.md) maps old questions to
accepted scope and residual boundaries. The [status audit](phase2/documentation-status-audit.md)
explains the dated documents. [ADR 0001](adr/0001-validation-lifecycle-architecture.md)
and root [AGENTS.md](../AGENTS.md) govern present validation: dependency-aware
local checks and lightweight development CI, with full independent local/hosted
qualification only for an explicit release-validation task.

Older references to a mandatory four-reviewer reconstruction and full suites
belong to that large change's checkpoint. They are not a new requirement for
every later PR. Retention/GC, trust and Git interpretation are not all undecided:
apply the scoped accepted decisions before considering remaining extensions.

## Preserved Schema 20 checkpoint

The text below is retained verbatim from this file at the audit baseline. It
records the earlier implementation stage, not the current storage version or a
current task authorization. Its links may point to subsequently updated files;
use the baseline commit for exact historical contents.

<details>
<summary>Historical Schema 20 status text (not current instructions)</summary>

# Implementation status — Schema 20

The active feature implements the owner-approved Publication-independent redesign across composed DDL, current PR/document/thread/Source acquisition, Issue/review preservation, atomic Git structures/decoders, queries/search/index, normalized Exchange, revision fencing and CAS/maintenance. It removes parser profiles/results/selection/certificates and required API originals instead of retaining compatibility authority.

Implementation status and acceptance status are distinct. The [handoff](phase2/publication-free-implementation.md) records dependencies, each durable subject's responsibility, removed/reexpressed paths and unresolved policy boundaries. The [complete schema map](phase2/publication-free-schema-map.json) and [test disposition](phase2/publication-free-test-disposition.json) support independent inspection. Final exact-revision review/test/CI receipts determine review-complete status; an exploratory passing subset is insufficient.

Four fresh independent post-implementation reviewers must execute counterexamples against frozen trees. Findings require root-cause correction, a regression, affected verification and reviewer recheck. Complete ordinary and isolated installed wheel/sdist suites, DDL/FK/integrity/JSON, lint/format and controlled selected-scale evidence must bind to the corrected source/tree and submitted PR. No merge/release/deployment authorization is included.

Prior Phase 1/Schema 19 and model-integration reports remain historical evidence. Their retained historical-publication boundaries and certificates are superseded only by the current accepted reconstruction and its actual implemented replacements. No new retention/deletion/cache/trust or Git interpretation policy is claimed.

</details>
