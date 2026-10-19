# ADR 0030 I5: owner merge preparation

This is a read-only preparation plan. No merge, retarget, release, P8 activation,
public-runtime switch or real Catalog operation was performed. Keep every PR
Draft until the owner separately authorizes the next gate. Design acceptance,
implementation acceptance, independent review, branch checks and owner approval
are separate decisions.

## Observed integration history

The 2026-10-19 GitHub snapshot and local Git objects agree:

| PR | HEAD | Current base | Effective tree |
| --- | --- | --- | --- |
| main | `6780088befd33e711230d570bb291edb2ee40cbf` | — | `aa981f3f22dfd42eb2d860618b25548faa62e1a3` |
| #107 I1 | `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7` | main | `14c694218109de1e3dfebc93e7776d48ad79faf3` |
| #108 I3 | `5c5b816998f7051703ca400e8cfeab377254c435` | #107 branch | `a4c0ea69a0cf5f31b6ffcdaba918b52de1ed6c91` |
| #109 I2 | `9b8a6ad9b761bf23b45eda9f84d639569cee56ef` | #107 branch | `7c461c633c137086537158385feb03a1b79d7dfe` |
| #110 I2/I3 | `8519056d5b9484eb0cc4dcf9f693285b4e65518a` | #109 branch | `a77503505127367e9378c57c5ab9ee9ae11767f3` |
| #111 I4 | `a54cb218226e3c91c44e979ee0df0543ea459502` | #110 branch | `cc2eafaaeb8e3305270c17e74ae69edc42c0a50b` |

The I2/I3 merge is `6dccd3c3bc4919975117a9cea80818936f2b9a5e`,
tree `269c3eec3598e8eb1cf63a70b80a67ce2eb26104`, with first parent
`9b8a6ad…` and **second parent `5c5b816…`**. All six I3-exclusive commits
are reachable from #110 and #111. #108 is not an additional dependency to merge
after #110. Shared OIDs and shared Git ancestry have different meanings; this
history proof concerns commits, not Repository identity.

All five fetched GitHub test-merge refs have the same effective tree as their
respective feature HEAD. Local two-parent simulations of
main → #107 → #109 → #110 → #111 have no conflicts and reproduce each feature
tree in turn. These synthetic commits are local unattached objects; no branch
was merged or updated. The I4 executed source `f948cc6…` and submitted #111 have
identical sets and bytes for all 422 executable inputs. Historical evidence-only
changes are not represented as another test execution.

## Recommended future integration route

Prefer promoting the **tested assembled implementation** without placing an
unfinished intermediate stage on main:

1. Obtain separate owner merge authorization and serialize the merge window.
   Fetch main and #107–#111 again; stop if any pinned HEAD/base changes.
   Retarget #111 to main only under that authorization, without rewriting its
   history. Review the resulting complete I1–I4 diff. Recompute the main/#111
   merge tree; it must equal the accepted #111 tree (or require fresh validation).
   Require current applicable checks and protection rules to pass on that exact
   candidate. Preserve the two-parent merge history; do not squash/rebase it.
2. After an owner-authorized #111 merge, verify the actual main merge parents,
   effective tree and reachability of every #107/#108/#109/#110 commit. Retarget
   the I5 child to main without rewriting it. Its diff must contain only the
   reviewed verification/helper/CI/evidence changes, with no repeated I1–I4
   implementation. Recheck its test-merge tree, executable-input binding,
   independent review and applicable checks before any separate I5 merge.
3. Treat #107–#110 as already integrated through ancestry. Do not issue another
   merge or cherry-pick for #108 or the other parents. Any later PR closure or
   metadata update is an owner action, not part of this task.

The intended merge order for this route is **#111 → I5**. Its dependency graph
still preserves **I1 → I2 → I2/I3 integration → I4 → I5**, including I3's second
parent. Retargeting is a proposal, not an action taken by I5, and must not be
used to bypass required checks or broader aggregate review.

If repository policy instead requires individual stage merges, use
**#107 → #109 → #110 → #111 → I5**, retargeting each child only after its
parent is integrated, preserving merge ancestry and verifying the actual target
and effective tree at every step. Omit a separate #108 merge. At this snapshot
#107–#110 each have successful `offline` but failed `registry-sqlite-3513`
checks from stage-owned incomplete integration; #111 has both checks successful.
Thus this individual-stage route is **not ready under a green-check requirement**.
The later assembled success does not rewrite or waive those failures. Resolve
the stage-check/protection plan explicitly before choosing that route; do not
hide tests, mark known failures expected or assume a badge transferred between
trees. Merely rerunning an unchanged unfinished stage cannot repair its failures.

## Preconditions and stop conditions

Recheck actual protection/approval requirements at merge time; this task makes
no claim of protection-rule visibility or a grant to override them. Feature-SHA
matching alone does not atomically fence a changing main. Coordinate one merger,
reread main immediately before each action, and verify actual parents/tree
afterward. Changed refs, tree, input manifest, conflicts, checks, approvals or
review findings stop the sequence and require scope-appropriate revalidation.

No route authorizes release, P8/public activation, legacy extraction or real
Catalog/credential work. Access #15 stays deferred. An accepted I5 record is
evidence for the owner's decision, not that decision itself.

Exact metadata, commit graph, ancestry matrix, all test-merge trees and local
simulation receipts are retained in the I5 evidence `stack/` directory.
