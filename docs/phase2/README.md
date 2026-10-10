# Phase 2: Publication-independent reconstruction

The owner accepted Q01-B/Q02-B/Q03-B (latest accepted API resource state and current known Source inventory plus necessary evidence) and Q04 **NO_INDEPENDENT_PUBLICATION**. Further option selection is paused. The old Publication-centered 69-table sketch is not the target.

## Current design and implementation instructions

1. [Accepted decision](no-independent-publication-adr.md) and [actual decision register](decision-register.md).
2. [Reconstructed whole architecture](publication-free-design.md): direct domain ownership, current values and field evidence, local transaction atomicity, separate collection/Git completeness, operational fences, normalized Exchange and retained-content maintenance.
3. [Implementation and independent-review prompt](publication-free-implementation-prompt.md): substantial integrated changes, required independent post-implementation subagent reviews, corrective iterations and exact-tree acceptance.

The reconstruction is a logical/implementation contract under the accepted decisions, not an executed complete replacement DDL. It does not mark paused Q05-Q12 recommendations accepted, implement a new retention/cache/trust policy, claim independent subagent approval already happened, or authorize merging/releasing.

## The decisive boundary

No independent Publication ID, generic input/output manifest, member/seal registry, selected interpretation or universal publish transition may own or enable ordinary domain resources. A renamed batch/bundle/generation/receipt with the same role is also excluded.

Identity and ownership belong to the actual resource. A coherent local update commits its values, field evidence and applicable conflict/revision state atomically. Completeness belongs to the exact requested collection, child tree, Git closure or code target. Normalized Exchange validates real typed dependencies, not sender transaction groups. Valid individual resources are not hidden merely because a larger acquisition is incomplete.

Latest-state choices must not become full edit/roster history stored under evidence. Required current origins, genuine unresolved candidates and minimal still-used target/scope evidence remain. Generic raw provider JSON is not an alternative to API-original deletion. Required Git content, exact domain text and CAS-41 remain protected.

The local `Store.publish()` / `publication_seq` role is a revision fence, not an independent domain Publication. Preserve that responsibility with clear naming, without creating a commit-history table. Physical catalog validation and atomic installation are likewise separate.

## Integration baseline

At reconstruction, main was `20e0f8d78b77c6c8d37826fd6d639819631e166b`, Schema 18. The runtime/audit stack is #22 -> #23 -> #24 -> #25; #23 supplies Schema 19 correctness fixes, #24 test efficiency and #25 corrected dependency/selected-scale evidence. #26 is the accepted decision overlay on a sibling of #23 based on #22. The reconstruction is stacked on #26.

Re-fetch actual state and integrate the decision documents without losing the separately submitted runtime/test corrections. No branch is rewritten, retargeted or merged by these design documents. An implementation must not regress to the older source tree merely because the design branch has it.

## Evidence and remaining policy boundaries

The [previous proposal](proposal-before-no-publication.md), [previous questionnaire](decision-register-before-no-publication.md), workstreams, inventories and prototypes remain checkpoint evidence. Static hits, SQL preparation, a synthetic counterexample and production acceptance are different evidence classes. Do not rewrite old validation receipts to claim new behavior.

The reconstruction specifies dependency direction, ownership, atomicity and required observable outcomes. Permanent fragment/final-set representation, stronger Exchange trust, new negative-membership rules, Git decoder/current-selection policy, cache/checkpoint lifetime and GC are not implicitly chosen. Preserve established semantics and report an exact irreducible policy conflict; do not restart the multiple-choice sequence or silently invent a policy.

Implementation may use a fresh incompatible development schema. After the integrated candidate is implemented, independent subagents must test it, the lead must correct findings, and affected reviewers must reverify the corrected tree. Final ordinary/package/hosted checks must identify that exact tree. This document update runs no runtime tests and claims no implementation or merge.
