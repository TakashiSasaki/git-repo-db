# Owner-executable merge plan

No merge in this plan has been executed. Obtain explicit owner authorization first.
Do not use auto-merge, squash, rebase, force push, branch deletion, release/tag or a
workflow dispatch that intentionally deploys Pages. Preserve reviewed stacked history.

## Pin the review

Starting main: `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`.
The final PR #92 evidence HEAD is pinned in its PR body and the final task report;
its tested runtime source is `74f90adae40ae60076dca33629fa2edbf5763474`.
Any changed HEAD requires a new diff/input check, not blind acceptance of the latest ref.

Expected feature heads:

- #89 `660178ff1a881e4482b7a3cde02b51dc50cf2603`
- #87 `c058af3a1be9ba3e9a1b0ba649c789f5bdcd1d75`
- #88 `e956cd50b1f25bd95427301cced4741bb68e24f8`
- #93 `7dc31256907aff4412170bc3f3ce3069b2ad89f2`
- #91 `1700ed37e82a6028cfa40c86b35db7621dd50404`
- #92 **the final owner-reviewed evidence HEAD in the PR body**, not merely74f90ada
- #90 `7cbade2928467f3c3ab2350bdc84e275d7057622`

Read-only preflight: fetch origin/main and each `refs/pull/N/head` plus the current
temporary merge refs. Query PR state/head/base, commit checks/run metadata, main
branch metadata, GraphQL branchProtectionRule and repository rulesets. The admin
protection endpoint returned403; ordinary branch metadata affirmatively reported
unprotected/no enforced required checks, GraphQL rule null and rulesets empty.
Recheck current policy instead of interpreting403 alone as an unknown blocker.

## Execute each authorized merge separately

Order: **89 →87 →88 →93 →91 →92 →90**. #90 now deliberately bases on #88 so its
Skill conflict is already resolved and independently reviewed; it can be last.

For each next PR:

1. Require its expected feature HEAD and OPEN state; require current necessary
   checks for that HEAD. Distinguish hosted Development `development_checks_passed`
   from full runtime execution. Inspect actual checkout/effective-tree binding,
   not just the status name. No missing required checks may be waived.
2. After the parent merges, inspect GitHub's actual base. If #88, #91, #92 or #90
   still targets the parent feature branch, retarget to `main` explicitly. Do not
   assume GitHub always retargets it. Verify unchanged feature HEAD, intended
   parent ancestry, final diff and current checks again after retargeting.
3. In a disposable clone/worktree compute `git merge-base origin/main FEATURE`
   and `git merge-tree --write-tree origin/main FEATURE`. Stop on conflict or
   unexpected paths. Compare the resulting tree's production/test/config inputs
   with the reviewed source/evidence, accounting for already merged independent
   Pages and P7 changes. Run the current schema/boundary/dependency/publication
   checks if those effective inputs differ. Do not edit the original P7 PRs.
4. Only after owner authorization and those checks, use the explicit equivalent
   of `gh pr merge N --merge --match-head-commit EXPECTED_HEAD`. Do not pass
   `--auto`, `--squash`, `--rebase` or `--delete-branch`.
5. Fetch main again. Verify the new commit has first parent equal to the prior
   main and second parent equal to the expected reviewed feature HEAD, and its
   tree equals the just-computed merge tree. Preserve the actual merge SHA/tree
   before moving to the next PR. A merge authorization never authorizes release,
   activation, recovery, real-catalog mutation or a manual Pages deployment.

The exact reviewed ancestry before merges is #87 HEAD→#88; #93 final HEAD→#91
final HEAD→#92. #90's ordinary merge parents are its prior9f56345 evidence HEAD
and #88e956cd50. Its no-production-change comparison is the **resulting merge
tree versus then-current main**, not the old feature tree versus newer main.

## Frozen-tree reference values

These are verified Git trees, not predicted GitHub merge commit IDs. They assume
starting main above and the reviewed heads. Synthetic local commits are evidence
objects only; actual merge timestamps/messages will give different commit IDs.

| Sequence | Expected tree |
| --- | --- |
| main +#89 | `ed80623514a5e574d1e24e908b95504f60b815db` |
| +#87 | `6ebd07cf4d6846e7d964c1be571c8507c037b9be` |
| +#88 | `e250fe0ad801013fb9c59e929cfc7f875fabb5b8` |
| tested public74f90ada +#88 | `8dcc1f022c50977ad10530b6e2baa24941b15e2f` |
| #89→#87→#88→#93→#91→tested#92 source74f90ada | `5795e1ed9d0224d74600c7e9988229ebb39a20ba` |
| preceding frozen runtime tree +resolved#90 | `d1f83a722e8fcd1b88b7c8b96cf3b5ecd00155ba` |

The last three values refer to the tested74f runtime source. Final #92 evidence
commits add artifacts/procedure prose, so their full trees differ and must be
recomputed from the final evidence HEAD. The PR body records a final current-head
preflight after that commit; do not compare a later evidence tree blindly with
these historical reference trees. No production/test/config delta is permitted
to be hidden as an evidence follow-up. CI acceptance hashes may conservatively
change for new evidence files; file-level runtime binding is a separate claim,
and no complete release receipt is asserted.

All original three merges and the six-runtime-PR sequence were conflict-free.
The optional #90 Skill conflict was found, concretely resolved by an ordinary
merge, verified to retain both sets of instructions, independently approved by A,
and checked green against its new base. It is not left as owner implementation work.

If main policy later requires the path-filtered Pages workflow for every PR,
out-of-filter changes may never emit that required status. Confirm an appropriate
always-emitted gate or a non-deadlocking policy before proceeding; do not weaken
required checks to work around it. No such deadlock was configured at review time.
