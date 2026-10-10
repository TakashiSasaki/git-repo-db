# git-repo-db — Implement the Publication-independent design, then independently review and correct it

## 1. Execute the redesign, not another questionnaire

Repository: https://github.com/TakashiSasaki/git-repo-db

Implement the reconstructed architecture in `docs/phase2/publication-free-design.md`, together with `docs/phase2/no-independent-publication-adr.md`, the active decision register and applicable AGENTS.md files. An attached identical design file may be used if the design PR has not yet reached your checkout; reconcile it with the repository before coding.

The owner accepted:
- P2-Q01-B: latest accepted PR state plus necessary evidence.
- P2-Q02-B: latest PR title/body/conversation comments and independent thread state plus necessary evidence.
- P2-Q03-B: current known Source inventory plus necessary scoped evidence.
- P2-Q04: **NO_INDEPENDENT_PUBLICATION**.
- No retained API transport originals or retrospective API replay; actual parser module/version is sufficient provenance.

Further multiple-choice selections are paused. Do not reopen these choices, revive the 69-table Publication-centered draft, or treat earlier unselected recommendations as approved.

Your deliverable is substantial real implementation across schema, writers, readers, Exchange, maintenance and tests, followed by **actual independent post-implementation subagent review, corrective work and re-review**. A plan, isolated prototype or self-review is not completion.

You may create branches/commits, integrate explicitly identified prerequisite branches into your new branch, push and submit stacked PRs. You are NOT authorized to merge GitHub PRs into main, release, deploy, tag, mutate retained user catalogs, run authenticated live collection or rewrite another agent's history. Prior permissions to merge #19/#20 do not apply here.

## 2. Refresh and reconcile the baseline

Preparation checkpoints, not a stale-checkout mandate:
- main: `20e0f8d78b77c6c8d37826fd6d639819631e166b`, Schema 18.
- #22: `e5f7ff386b77627490a400f0a7e29d3989a9a532`, old Phase 2 investigation.
- #23: `162581dfcfb501311d4993e90cdd160fb64d6e35`, Schema 19 evidence/proof/index corrections.
- #24: `52a36cab26f2287591ff9296cac151fe135cc55a`, isolated test efficiency.
- #25: `0bd5704caca2f6e3723bef22531b065cd4d7bad0`, corrected audit and selected-scale evidence.
- #26: `26c5972d0187c52e4780f55cc9e307b84c71cbee`, no-Publication decision overlay, a sibling based on #22.

Fetch current main, open PRs, exact heads, ancestry and local changes. Discover the PR containing `publication-free-design.md` rather than guessing its number. If prerequisites remain unmerged, use a new integration branch that preserves #23-#25 corrections and incorporates #26 plus the reconstructed design. Prefer ordinary merges with documented parents; do not blindly rebase or force-push. Resolve document conflicts in favor of the owner's latest decisions, without reverting source/test corrections. No prerequisite PR needs to be merged into main just to begin this work.

Record actual source/tree SHAs and the effective dependency graph. Build from the latest coherent reviewed implementation, not merely the old documentation branch. Update the active schema to the next appropriate fresh format only when the real contract changes; no schema-number target or compatibility layer is required.

## 3. Design gate before production edits

Read the reconstruction fully. Build a concise responsibility map from the actual composed production DDL and live callers, including Store.one/all, local SQL forwarders, generated SQL/JSON guards, composite FKs, views, triggers, dynamic dispatch, CLI, failure/restart, Exchange promotion and packaging.

For every proposed durable object, state its domain/operational subject, key, consumer, lifetime responsibility and why it is NOT an independent Publication. Reject generic transaction/batch/bundle/generation/member-seal records that merely reproduce the old abstraction.

Do not repeat the old entire investigation. Reuse verified artifacts as evidence, correct gaps, and establish the no-Publication mapping. Before coding, obtain a design consistency pass from a separate subagent and record concrete issues. This preliminary pass does NOT replace the mandatory review after implementation.

Distinguish implementation mechanics from new owner policy. You may choose coherent columns/indexes/transactions that preserve accepted meanings. Do not invent a new lifecycle, deletion-on-absence rule, total ordering, final collection evidence retention policy, cache architecture, provider trust or Git interpretation policy. An irreducible issue must be isolated with a counterexample and exact affected path; continue independent work. Do not retain generic Publication simply because it would avoid addressing dependencies.

## 4. Mandatory implementation outcomes

### A. Remove independent Publication and parser authority

Retire generic parsed-result input/output publication ownership, Publication IDs/registries/seals, selected-profile/fact DAGs and ordinary-read verification/trust gates. Remove the equivalent proposed repository/source Publication machinery instead of implementing it.

Move retained facts to direct typed resource/object/list/Source owners. Rewrite associated PK/FK/generated capability columns, union member views, eligibility guards, JSON references, CLI/services and tests. No dummy fetch, empty fake input manifest, renamed result, universal admission batch or version-ranked selector is allowed.

Retire parser certificate generators/artifacts and profile CLI where their consumers are removed. Do not recreate verification certificates for simple module/version provenance. Preserve legitimate Git-only content reanalysis and truthful decoder evidence, not API replay.

### B. Implement latest API state and truthful evidence

PR metadata, existing natural-key documents, independent threads and current Source roster must obey the accepted latest-state choices. Preserve existing ordinary Issue/review behavior.

Atomically update values, presence, field clocks/producer/capture, relevant conflicts and local revision. Missing is not explicit null. Inherited values keep their original provenance. Preserve live revision/scope fences, transfer capture, incomparable conflicts and receiver-local checks. Do not append all previous values to an evidence/history table. Do not confuse actual timeline events or required code target anchors with resource edit snapshots.

Retain modeled domain fields with their existing documented consumers and exact null/type semantics. Do not preserve entire provider-shaped responses under metadata/state JSON. If a named field's semantics are genuinely disputed, report it specifically rather than silently dropping it or keeping an opaque response replica.

### C. Separate commit from completeness

Use SQLite transactions/savepoints for coherent local writes. Correctly roll back the whole intended unit on body/constraint/COMMIT failure; a statement ABORT is not a whole-transaction rollback. Do not hold a write transaction over network collection.

Valid committed resources remain independently usable when a later page fails. Individual validity, requested collection completeness and latest Coverage are separate predicates. No Publication completion flag may gate all resources.

Preserve exact domain scope, member/terminal and required-child outcomes without API originals. Current-only historical evidence must not require today's values to match yesterday's digest or require a full edit history. Preserve the five-column Coverage contract and actual time candidate-set behavior; do not make advisory details mandatory publication certificates.

Do not automatically adopt old Q05-A/B layouts. Reexpress the existing required outcomes using justified typed domain evidence, and test the anti-disguised-Publication boundary. Record any truly new evidence-retention choice instead of inventing it.

### D. Git and code

Validate canonical Git format/OID/type/size and physical bytes. Install each object's complete intrinsic relational structure atomically; large imports may commit independently valid objects. A partial tree's entries may not masquerade as a complete object.

Keep actual ref/root/acquisition/snapshot responsibilities and exact code head/base/role bindings. Scope reachability/completeness is domain-specific, not a generic publish layer. Missing Git targets stay missing, not fabricated. Do not retag head A's assessment as belonging to current head B or retain the entire old PR merely to anchor code.

Do not silently select a new Q08 decoding/interpretation/ref-current policy. Preserve the independently supported behavior and flag a concrete conflict if unavoidable. Latest-only API decisions do not authorize deleting all Git captures.

### E. Operations and content

Preserve the single local revision/fencing role of Store.publish/publication_seq, preferably with clear mechanical names such as advance_local_revision/local_revision. Update all readers, paging, live fences, restore and tests. Do not create a revision-history table or import the sender's revision as freshness.

Normalize needed thread continuation and code target facts while responses are in memory. Cursor/checkpoint/job state must not own durable resource validity. Never advance a cursor beyond committed data. Missing/mismatched cache state cannot confirm a domain state; perform a genuine safe live fetch or report reuse unavailable. No new persistent API-original cache, retrospective replay or unapproved checkpoint placement/lifetime policy.

Remove all final API-original storage/reference routes, including errors, accepted-partial response envelopes, pending exchange JSON and hidden encoded copies, as their consumers are reexpressed. Keep Git/text/domain bytes, shared-digest integrity, quarantine/real Git repair and CAS-41. Do not physically clean retained user databases or invent GC policy.

### F. Exchange, queries and maintenance

Exchange selects actual domain dependencies from a consistent snapshot, not sender Publication membership. A delivery envelope/checksum is transport processing, never durable domain ownership or eligibility authority.

Admit coherent typed resources; retain real missing-dependency and conflict candidates. Reverse/repeated/partial arrivals, reopen, promotion and onward export must be correct. Independent valid resources can be used before the whole transfer/list completes. Missing closure cannot establish broad complete coverage. Arbitrary sender hints cannot authorize foreign content.

Preserve the existing evidence/trust boundary. A digest does not prove provider authenticity or reveal a coherently omitted member. Do not accept an unprovable claim merely to eliminate old dependencies.

Rebuild search from current retained API values and legitimate Git/event content. Retire obsolete API-history interfaces rather than fabricate historical values. Backup/restore and physical catalog readiness are not domain Publication; preserve their established protections.

## 5. Large implementation strides

Prefer one integrated implementation PR, or a small number of genuinely coherent stacked PRs. Coordinate parallel workstreams with disjoint worktrees/modules and one integration owner. Intermediate breakage is allowed; the submitted accepted endpoint must be coherent.

Do not stop at a few column renames, leave dead guards, or make table-count reduction a goal. After each major removal, search again for newly dead consumers and surrogate Publication mechanisms. Keep a source/DDL/runtime classification rather than treating every string match as live architecture.

Preserve #23's presence/time/proof fixes, #24's isolation of parallel package tests, and #25's corrected audit and selected-scale findings. Use one controlled workload at a time for comparative performance; parallel code review is separate from benchmark evidence.

## 6. Mandatory independent POST-IMPLEMENTATION subagent review

After producing a coherent integrated candidate, freeze its commit/tree. Start fresh reviewers that did not author their reviewed production changes. Report each subagent's purpose, model and effort when exposed; otherwise say `not exposed`. Do not claim independence from differently named passes in the same implementation context.

Required scopes:
1. **Architecture and DDL:** no independent/renamed Publication, no hidden latest-state history, direct typed ownership, complete removal of retired references and generated artifacts.
2. **Acquisition and completeness:** rollback/COMMIT failures, sparse values and v1/v2 provenance, Source scopes, empty/missing/nested terminal evidence, stale/equal clocks, cancellation/restart/cache loss.
3. **Git, Exchange and CAS:** partial intrinsic object rows, wrong head/base, fake Git labels/OIDs, malformed/foreign/pending records, reverse/duplicate transfer, shared-byte corruption, backup/restore, local revision versus domain freshness, selected-scale performance.
4. **Final integrated verifier:** examine interactions across corrected modules, exact source/test/artifact binding and the actual complete ordinary/package result set.

Give reviewers the owner constraints, full integrated diff, old-to-new map and commands, not only your success summary. Require each to build and execute independent counterexamples against its exact frozen tree, identify reviewed/unreviewed paths and return reproducible findings. Tests authored solely by the implementer and green CI alone do not satisfy this gate.

**Correction loop:** reproduce each finding; fix root cause; add a regression; run affected tests; give the corrected tree back to the reviewer for re-verification. Recheck cross-module interactions after shared changes. Any new source change invalidates affected prior sign-off. Repeat until no unresolved mandatory correctness issue remains; do not stop after reporting findings or after one arbitrary review round.

If actual subagents are unavailable, use a separate executable reviewer environment where available and report the exact limitation. Do not label self-review independent or claim the required gate passed. Complete safe implementation work, leave the PR Draft/not review-complete, and report that unmet gate.

## 7. Acceptance and adversarial tests

Run fresh complete composed DDL checks, FK/integrity, view/trigger behavior, generated JSON equality, lint/format, complete applicable ordinary tests and isolated installed wheel/sdist tests on the FINAL corrected tree without bootstrap overrides. Use current repository tooling, including verified parallel package isolation if integrated. Test counts are evidence, not fixed targets. Retire only mechanism-specific obsolete tests; replace their still-required behavioral assertions.

Required scenarios include:
- Midway value/evidence failure and COMMIT failure: no mismatched committed state/revision.
- No universal publish call/row needed for a valid resource; incomplete larger list does not hide it.
- 10,000 repeated current updates do not create a full normalized API edit history; separately report unreferenced shared bytes rather than claim GC.
- Complete100 -> identified partial200 -> older successful175 -> complete300, same-time conflicts, empty terminal versus no terminal, required-child omission and foreign parent.
- Source R1/R2 then partial R1: no inferred deletion or identity change.
- PR head A code anchor then current B: no borrowed completeness or retained old full PR.
- Crash during large Git ingestion; incomplete single-object structure; missing target; SHA-1/SHA-256 verification.
- Delivery parent missing, late arrival, repeated/reversed import, current-value drift, inconsistent digest/member evidence, fake original authorization and onward export.
- Optional archive/operational-state deletion does not invalidate committed facts; safe retry does not fabricate old observations.
- Shared physical digest corruption, CAS-41 copied quarantine mismatch, atomic no-overwrite restore.
- Same-repository unselected history and selected-volume growth; indexed selected closure and nonquadratic membership checks. Count statements/VM steps/visited records as appropriate; do not misrepresent concurrent timings.

Inspect final schema, serialized records, job/pending JSON, source dispatch and executed failure paths for Publication/original surrogates. Narrow exceptions need a real non-Publication responsibility, not an allowlist chosen to pass a grep test.

Bind final local/hosted CI to feature SHA and effective checkout tree. Reconcile selected/executed node IDs and disclose failures/skips/exclusions/unexecuted tests. Certificates of removed parser machinery must not remain final acceptance gates; surviving transitional mechanisms must be explicitly incomplete scope, not used to claim full redesign success.

## 8. Submit and report

Submit actual implementation PRs with explicit base/head dependencies and the design reference. Do not merge. Preserve original validation receipts; write new exact-revision evidence for this work.

Report: implemented architecture; removed/reexpressed tables, columns, FKs, views, triggers and services; evidence that no disguised Publication/history remains; actual residual API-original/selection dependencies; unresolved policy boundaries; each independent reviewer and findings/corrections/re-review; exact final ordinary/package/CI counts; schema and tree fingerprints; scale results and limits; PR URLs and dependency order.

Do not claim full completion if a supported path still requires an independent Publication or mandatory API original. Isolate unavoidable unfinished work precisely rather than weaken tests, silently choose owner policy or promise later background completion. The target is a working, reviewed integrated implementation, not a proposal to begin one.
