# Independent review of the ADR 0031 evidence integration

**Documentation revision: no blocking finding. Complete owner design acceptance:
NOT YET READY.** The revision faithfully incorporates the demonstrated C′ subset
and corrected G1/G2 while retaining G3 as an explicit owner decision. This review
is not owner acceptance, product implementation approval or a new SQLite run.

## Reviewed inputs and independence

The reviewer is a separate agent that authored none of the seven revised design
files. Review used a detached, read-only worktree of commit
`060da07e0412e2d93dd4132332ab3bf908e3d8db`, tree
`26fdd521faffce4ef458b3ad762ef02c98ea1eea`. The update baseline is
`5244b98a9a302f082a07a526480faf438fc91838`; the actual #113 stack base is
`24f593861327328fa00dab0b83f956cec330a0ac`. This receipt and its JSON checks are
subsequent review artifacts, not contents of that reviewed freeze.

The review applied root AGENTS.md and the repository ADR workflow, read ADR
governance, accepted ADRs 0017/0028/0029/0030, the revised ADR/schema/handoff,
compatibility and eight-obligation matrices, original experiment final review,
follow-up semantic source/final reviews, runtime receipts and F2 source mechanisms.
No reviewed file or remote branch was edited by the reviewer.

Evidence inspected through exact Git objects:

- F1 executable `e9aba86f4530b2e683c77e23a4fe58bdf02192c5`; original final review
  publication `22b58ce7ff59478f1a4c8c8ef89b17d2f0068590`.
- F2 executable `9eeacb28f7e4a426114a9ce40e2324b4da302817`, tree
  `8f78de68058582327beddbb656207659507d43c6`.
- R2 publication `8ab57eb74068f5ba303b5985a335f0f76be4fdd2`, including the independent
  semantic review, final review, 75-case and 39-case receipts on both runtimes,
  and author-rerun summary.

The [integration map](cprime-integration.md) contains verified commit-pinned links.
F2 is the corrected executable freeze; R2 is the later publication. Neither a
later report HEAD nor this design commit is misrepresented as an executed input.

## Semantic and evidence findings

| Review area | Finding |
| --- | --- |
| Owner ledger | A3, B3, U3=C′, U4=B, U5=A, U1=B, U2=A and U2-E2 remain explicit and intact. No selected choice is reopened by the review gate. |
| ADR 0017 and identity | ResourceKey triple, genuine PR/document coordinates, permanent Repository and issued observation identities remain. Independent Documents retain kind `document`; shape does not establish their native contract. No surrogate or new identity discriminator is introduced. |
| ADR 0028 | Original strict timestamp validation remains distinct from SQL affinity; missing/NULL and positive versus Git-native signed times survive. Canonical identity validation does not replace outer digest comparison or authenticate origin. |
| ADR 0029 | Five-store authority, Context mapping/text/evidence, Content/Resource/Observation separation, Source positives, five Coverage columns and paired-backup boundary remain. No Access authority is inferred from Resource reports. |
| ADR 0030 | Six Repository roles, EventReportKey pairing, attributed alternatives, exact support references, no Witness/header table and qualification limits survive. Q-S10 is marked unresolved at its newly exposed semantic boundary. |
| G1 | **CLOSED — corrected and independently verified**, within the isolated native-contract declarations. `cp_resource`, explicit `document_input`, required native-ID repetition, non-key absence projection and real source/target FKs agree with the stated forms. Malformed PR input has no fallback. SQL is not claimed to authenticate the Provider identification contract. |
| G2 | **CLOSED — corrected and independently verified.** The specified namespace-TEXT encoding matches F2. The two separate encodings are reversible/injective; their union can alias different native Parents. The revision selects one profile without dropping semantic coordinates or retroactively rewriting old receipts. |
| G3 | **OWNER DECISION REQUIRED.** The I8 report may be retained and exact typed support passes SQL, while supported admission withholds the unresolved mismatch. The revision does not call that Python guard an FK or silently select universal equality. The I7-contract versus separately qualified I8 alternatives are stated precisely. |
| Acceptance state | ADR 0031 remains `status: proposed`, `date: null`, `replaces: []`, and separately indexed. No accepted body is changed or retired. |

The eight acceptance obligations map accurately to the inspected mechanisms:

1. Parent authority remains existing `resource_relations`; row-local identity
   metadata and generated projections do not become a second Parent authority.
2. Resource admission has no semantic Parent existence FK; actual relationship
   referents and dependent support do. Later arrival requires original re-supply.
3. Timeline subtype and Issue report support use actual composite SQL FKs;
   normalized event semantics and temporary G3 withholding are separate layers.
4. Full supplied support keys are enforced; rejecting I8 relative to native I7
   is expressly unresolved, rather than reported as demonstrated SQL behavior.
5. Full event-report support, clock/time triggers and immutable group rules are
   mapped separately from application whole-endpoint handling and qualification.
6. CHECK predicates and deterministic projections bind row-local fields and
   close typed NULL bypasses. Arbitrary JSON members have no individual FKs.
7. Existing mutation guards and pre-conflict rebind triggers are identified;
   recursive-trigger configuration and unsupported enforcement disablement are
   explicit. Immediate FKs are not described as deferred COMMIT machinery.
8. Whole-unit savepoint handling includes original timestamp types, declared
   Provider-member existence and complete supplied endpoints. The independently
   observed second-endpoint FK rollback is application atomicity evidence, not
   an SQL guarantee that every stored declared endpoint set is complete.

No FK, trigger or canonical encoding is claimed to authenticate a Provider.
The original F1 verdict is retained in its bounded scope; old I8 diagnostics
remain structural, and G1/G2 add coverage without proving the whole ADR contract.

## Checks and future handoff

The [independent check receipt](cprime-independent-checks.json) records:

- Both update-baseline and stack-parent `git diff --check` passed. The seven-file
  update is documentation only. The stack also contains one inherited skill
  reference change already in #114; it is unchanged by this update. No source,
  packaged DDL, dependencies, workflows, product tests or accepted ADR body changes.
- Strict UTF-8, valid JSON, balanced Markdown fences, eight ledger labels and
  proposed/null metadata passed. 100 local target/anchor occurrences and 28 full
  commit-pinned Git blob targets resolved. These counts describe this review's
  scanner and are not additive to author counts or an HTTP availability claim.
- All 18 manifest input hashes match F2 and remain unchanged in R2. Manifest
  SHA-256 is `30e0e1b75f476f0813bd410b5726fe952511125adbd2e1f0bc2fbf980d3605a3`.
- Independently reconstructed SQL text hashes match F1
  `c2c325532279f35ba51b36aacbeea30ceda4040e80b5d31512cbb9e19d564dee` and F2
  `2892a5fb0bcef8a0e0ea916fc1b71687a0a2afe545849e27dec4f7fd3600171f`.
  This evaluated only frozen pure text-composition functions with Git-backed
  inputs; it opened no SQLite database and executed no experiment suite.
- Existing receipts identify actual SQLite 3.51.3/Python 3.13.5 and SQLite
  3.53.1/Python 3.12.14 with source IDs and enabled enforcement. Their grouped
  author, focused and independent counts match the integration map; overlapping
  counts are not added.

The handoff separates owner resolution, shared encoding, Resources, Parent
reports, Transfer SQL, admission, scoped Exchange, stored integrity/recovery,
query/Search, genuine minimum/newer runtimes, wheel/sdist and final effective-tree
verification. Dependencies and non-author review gates are explicit. Product
integration, Exchange/backup implementation, packaging and release checks remain
future work and are not claimed by this documentation review.

The documentation update is suitable to publish for owner review. Complete ADR
0031 design acceptance remains **NOT YET READY** until the owner resolves G3's
Q-S10 Issue eligibility and any required accepted-contract carry-forward is
explicitly reviewed. No additional engineering defect or owner-choice blocker
was identified in this bounded documentation review.
