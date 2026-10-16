# Owner-executable seven-PR merge gate

Engineering verification is recorded separately from owner authorization. No merge in this plan has been executed. The supplementary evidence PR #94 is not a runtime dependency and is not inserted into the seven-PR order.

Frozen starting main: `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`. Tested synthetic source: `388b824d1b3abe41c902759bf37a52c6ee5bcd2f`; tree: `ea006924152d2fc508c7eb21697ad3c376e373f6`. Synthetic commit IDs are reproducible evidence objects; actual GitHub merge commit IDs are unknown.

| Order | PR | Reviewed feature HEAD | Expected cumulative tree | Current target |
| --- | --- | --- | --- | --- |
| 1 | [#89](https://github.com/TakashiSasaki/git-repo-db/pull/89) | `660178ff1a881e4482b7a3cde02b51dc50cf2603` | `ed80623514a5e574d1e24e908b95504f60b815db` | `main` |
| 2 | [#87](https://github.com/TakashiSasaki/git-repo-db/pull/87) | `c058af3a1be9ba3e9a1b0ba649c789f5bdcd1d75` | `6ebd07cf4d6846e7d964c1be571c8507c037b9be` | `main` |
| 3 | [#88](https://github.com/TakashiSasaki/git-repo-db/pull/88) | `e956cd50b1f25bd95427301cced4741bb68e24f8` | `e250fe0ad801013fb9c59e929cfc7f875fabb5b8` | `docs/p7-backup-recovery-technical-design` |
| 4 | [#93](https://github.com/TakashiSasaki/git-repo-db/pull/93) | `7dc31256907aff4412170bc3f3ce3069b2ad89f2` | `d4bf2253eed2ea7df26336c681c5a5241dd36bf6` | `main` |
| 5 | [#91](https://github.com/TakashiSasaki/git-repo-db/pull/91) | `1700ed37e82a6028cfa40c86b35db7621dd50404` | `f749d63fb1162520b21512a0690bf2015441ba91` | `fix/schema21-collection-contract` |
| 6 | [#92](https://github.com/TakashiSasaki/git-repo-db/pull/92) | `94488cf4e7fa15f747ece7a4e3d57e0bc213966a` | `1e5b150613d1ccf15285c5724498744fb4d883fa` | `fix/schema21-job-search-runtime` |
| 7 | [#90](https://github.com/TakashiSasaki/git-repo-db/pull/90) | `7cbade2928467f3c3ab2350bdc84e275d7057622` | `ea006924152d2fc508c7eb21697ad3c376e373f6` | `feat/p7-production-recovery` |

## Required owner action

Explicitly authorize merge commits for **#89 → #87 → #88 → #93 → #91 → #92 → #90**, subject to a fresh per-step preflight. Do not run the commands below before that separate authorization. No squash, rebase, force push, auto-merge, branch deletion, release, tag, migration or production activation.

## Before each step

1. Fetch all branches and the specific PR head; require unchanged reviewed feature SHA, OPEN state, and the actual previous authorized main. For the first step it must be the frozen main above. For later steps use the actual prior merge SHA just recorded, never a predicted synthetic SHA. Require earlier PRs merged and their feature heads ancestors of main.
2. Read current policy and statuses. Initial inspection found branch `protected=false`, enforcement `off`, no contexts, GraphQL branchProtectionRule `null`, rulesets `[]`, merge commits allowed. That is an observation, not a waiver. Repeat it; inspect applicable rulesets including inherited policy and commit status contexts, check names and exact source/effective-tree receipts. Stop on unknown, pending, failing or missing required checks. Historical duplicate CANCELLED jobs on #90 are retained; newer same-context runs succeeded. Deployment skips on pull requests are expected. Development success does not mean hosted full acceptance.

```sh
gh api repos/TakashiSasaki/git-repo-db/branches/main
gh api repos/TakashiSasaki/git-repo-db/rules/branches/main
gh api repos/TakashiSasaki/git-repo-db/rulesets --paginate
gh pr checks N --required
gh api repos/TakashiSasaki/git-repo-db/commits/FEATURE_SHA/status
```

3. After each parent merge, verify the child target. #88 after #87, #91 after #93, #92 after #91, and #90 after #88 may still target the parent branch. Retarget only then; no branch history rewrite is needed. The exact REST equivalent avoids a legacy `gh pr edit` Projects query issue:

```sh
gh api --method PATCH repos/TakashiSasaki/git-repo-db/pulls/N -f base=main
gh api repos/TakashiSasaki/git-repo-db/pulls/N --jq '{state,head:.head.sha,base:.base.ref,mergeable,mergeable_state}'
```

4. Require the same feature SHA after retarget. Wait for current relevant checks without bypassing policy. Recompute merge base and effective tree from actual main with `git merge-tree --write-tree MAIN FEATURE`. Require no conflict and exact cumulative tree from the table. Compare actual diff paths with `chain.json`; any new executable input, unexpected path/tree, remote main update or feature change invalidates this preflight. Re-review/retest changed inputs rather than silently accepting them. `owner-preflight.py.txt` is a read-only helper; copy to `.py` next to `chain.json` and run from a clone with origin pointing at this repository:

```sh
python owner-preflight.py N --expected-current-main ACTUAL_PRIOR_MAIN_SHA
```

5. After authorization and every check above, arrange an owner-coordinated single-merger window. Immediately re-read remote main and require ACTUAL_PRIOR_MAIN_SHA again. `--match-head-commit` fences the feature HEAD only; it does not atomically fence the base against another merger. This procedure does not claim atomic main fencing. If concurrent main updates cannot be excluded, stop and coordinate before merging. Execute one merge commit only:

```sh
gh pr merge N --repo TakashiSasaki/git-repo-db --merge --match-head-commit FEATURE_SHA
```

Do not add `--auto`, `--squash`, `--rebase`, `--admin`, or `--delete-branch`. Repository-supported squash/rebase availability is irrelevant; this plan requires merge commits.

6. Fetch and inspect the actual resulting commit before the next merge:

```sh
git fetch origin main
git show -s --format='%H%n%P%n%T' origin/main
gh api repos/TakashiSasaki/git-repo-db/pulls/N --jq '{state,merged,merge_commit_sha,head:.head.sha}'
```

Require actual main to equal the PR merge_commit_sha, exactly two parents, first parent equal to ACTUAL_PRIOR_MAIN_SHA and second parent equal to FEATURE_SHA, and tree equal to the table. Preserve that actual SHA/parents/tree and recheck remote state. Abort on any mismatch; do not reset, overwrite, revert or continue automatically. Re-evaluate required checks after each base change. A path-filtered Pages check must not be made an unsatisfiable requirement; resolve actual policy without weakening checks.

## End boundary

No PR is merged by this evidence work. Main and the seven feature heads are rechecked in `raw/pr-final.json` and final policy artifacts. Actual Release Acceptance (independent complete hosted release run and release reconciliation), physical power-loss validation, unsupported platform/filesystem qualification, opt-in P8 public-runtime wiring and owner merge authorization remain separate.
