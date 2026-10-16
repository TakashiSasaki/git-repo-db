# Owner-executable merge plan — no authorization inferred

These are future owner commands, not actions executed by this assignment. Explicit owner authorization is required for each merge. Keep merge commits; do not squash, rebase, force-push, enable auto-merge or bypass a required check. Ordinary main merge events may run the existing Pages deployment; no workflow dispatch/deployment is requested here.

Start only while main is `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`. If another PR merges first, recompute the full sequence and compare its effective tree before requesting/executing owner authorization. Baseline-remediation PRs are independent from P7 and may change this assumption when eventually authorized.

1. Refresh exact refs and inspect current remote heads:

   ```sh
   git fetch origin main refs/pull/89/head:refs/remotes/origin/pr89 refs/pull/87/head:refs/remotes/origin/pr87 refs/pull/88/head:refs/remotes/origin/pr88
   git rev-parse origin/main origin/pr89 origin/pr87 origin/pr88
   gh pr view 89 --json state,headRefOid,baseRefName,mergeable,mergeStateStatus,statusCheckRollup
   gh pr view 87 --json state,headRefOid,baseRefName,mergeable,mergeStateStatus,statusCheckRollup
   gh pr view 88 --json state,headRefOid,baseRefName,mergeable,mergeStateStatus,statusCheckRollup
   git merge-base origin/main origin/pr89
   git merge-base origin/main origin/pr87
   git merge-base origin/pr87 origin/pr88
   ```

   Require the README's exact HEADs and expected bases (`main`, `main`, design branch). First two merge-bases must be original main, third exact PR 87 HEAD. Confirm all current checks are completed successfully for each feature HEAD; PR deployment skip is expected. The GitHub check payload's `head_sha` may be the temporary test merge, so compare its feature/run binding and effective tree. Confirm current repository settings still permit merge commits.

2. Owner inspects main branch protection/rules in GitHub Settings or with credentials that can read protection. The assignment's token receives HTTP 403; visible rulesets alone are insufficient. Resolve any unconditional required Pages context that path filtering would omit. Do not remove/weaken required checks to obtain a merge. This is a policy visibility gate, not an assertion that a deadlock currently exists.

3. After explicit owner authorization for PR 89, preflight:

   ```sh
   git merge-tree --write-tree origin/main origin/pr89
   ```

   Require tree `ed80623514a5e574d1e24e908b95504f60b815db` and exit 0. The reviewed merge action is:

   ```sh
   gh pr merge 89 --merge --match-head-commit 660178ff1a881e4482b7a3cde02b51dc50cf2603
   ```

   Fetch main, record actual merge SHA as `M89`, inspect `git show -s --format='%H %P %T' origin/main`. Require first parent old main, second parent exact PR 89 HEAD and expected tree. Do not proceed if GitHub changes the effective tree.

4. Recheck PR 87 metadata/checks, then after explicit owner authorization:

   ```sh
   git merge-tree --write-tree origin/main origin/pr87
   ```

   Require tree `6ebd07cf4d6846e7d964c1be571c8507c037b9be` and exit 0. Then:

   ```sh
   gh pr merge 87 --merge --match-head-commit c058af3a1be9ba3e9a1b0ba649c789f5bdcd1d75
   ```

   Fetch main; record actual SHA `M87`. Require first parent `M89`, second parent exact design HEAD and expected tree. Keep the design branch until PR 88's base/ancestry is confirmed. Repository currently has delete-branch-on-merge disabled, but do not depend on automatic retargeting.

5. Inspect PR 88's current base after PR 87 merges. If it remains the design branch, retarget to main using the supported REST mutation (only after authorized design merge):

   ```sh
   gh api --method PATCH repos/TakashiSasaki/git-repo-db/pulls/88 -f base=main
   ```

   Re-fetch main/PR 88; require unchanged feature HEAD, `git merge-base --is-ancestor c058af3a1be9ba3e9a1b0ba649c789f5bdcd1d75 origin/main` and the same command against `origin/pr88` both succeed. `git merge-base origin/main origin/pr88` must equal exact design HEAD for this planned sequence. Re-evaluate PR diff after base change; it must contain only the reviewed implementation/evidence/skill changes relative to the new main, accounting for PR 89 already present on main. A changed base can schedule fresh checks: inspect once at the meaningful completion barrier; do not loop with sleeps or infer old checks certify a new merge tree.

6. After exact-HEAD checks, unchanged executable manifest, required-policy confirmation and explicit owner authorization for PR 88:

   ```sh
   git merge-tree --write-tree origin/main origin/pr88
   ```

   Require tree `e250fe0ad801013fb9c59e929cfc7f875fabb5b8`, exit 0 and no conflicts. Then:

   ```sh
   gh pr merge 88 --merge --match-head-commit e956cd50b1f25bd95427301cced4741bb68e24f8
   ```

   Fetch main, record actual `M88`; require first parent `M87`, second parent exact implementation HEAD and expected final tree. Verify main contains the exact PR 87 and PR 88 HEADs as ancestors and that final versus PR 88 changes are precisely PR 89's reviewed paths. Record actual merge SHA/tree/check links. Do not relabel the inherited failing public suite as passing; follow separate baseline-remediation evidence.

No merge command in this file is an instruction to the current agent to execute it. Any remote advance, changed SHA, unexpected parent/tree, conflict, failed mandatory check or policy uncertainty stops dependent merges pending a concrete new preflight/owner decision. No P7 redesign is called for without a reproducible defect.
