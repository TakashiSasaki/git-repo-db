# Repeated design-only ADR stack updates

Use this procedure when an owner accepts one previously presented design option and the current task authorizes recording it in a direct stacked documentation PR. Preserve the actual task's scope; an option selection is not generic permission for implementation, merge, release, or messaging other chats.

## Why this procedure exists

Successive design PRs exposed two repeatable traps: updating only the newest ADR leaves older entrypoints saying the accepted choice is still open; broadly changing `next QUESTION` also rewrites historical examples, and a later patch using the old text then fails. The verified correction was to pin the live parent, make scoped status updates, reread transformed lines, and validate the final published tree. Repeated completed examples are [PR #62](https://github.com/TakashiSasaki/git-repo-db/pull/62), [PR #63](https://github.com/TakashiSasaki/git-repo-db/pull/63), and [PR #64](https://github.com/TakashiSasaki/git-repo-db/pull/64). Their old counts and heads are evidence of those runs, never defaults for a new task. A later owner correction exposed another failure: repeatedly treating resource defaults/counter mechanics as architectural blockers manufactured an unnecessary decision chain. Classify the residual work before proposing a successor question.

## Pin identity and authority before editing

- Read the live parent PR's state, head branch and full SHA. Compare them with the owner's intended base; use that head as the sole parent of the new branch. If it moved, inspect the new state before continuing. Do not silently stack on `main`, the parent's base branch, or a nearby sibling.
- Inspect the actual checkout, root/applicable agent guidance, ADR index and relevant accepted records. Preserve uncommitted work and read-only synced references. Reuse a suitable authorized checkout or worktree; do not create another merely for this procedure.
- Separate the one accepted option from remaining units, numbers, trust rules, fences and other choices. A recommended option is not accepted. A proposed governance sibling does not become binding through inclusion in a stack or a newer date.
- Before offering lifecycle/status options, trace their actual consumers and state the failure/trust model they assume. Successful queries, a structural check or an isolated corruption test do not prove the rest of a database is sound; another copy in the same database is not independent fault isolation. If the owner challenges that premise, resolve it before comparing counters or retirement states. Show the operational consequences and distinguish preservation evidence, salvage candidates and validated service data. This lesson governs the review method, not a reusable authorization to stop or recover real catalogs.

## Reconcile current state without rewriting history

1. Add the next available ADR using the repository's actual conventions. State the accepted option, direct parent, scoped refinement, residual blockers and authorization boundary; distinguish target design from implemented behavior.
2. Update active decision summaries in the relevant predecessor ADRs, index, agent guide and transition entrypoint. Scope an `open` statement to its real residual question; do not erase an unresolved detail just because its parent policy was accepted.
3. Mark the prior alternatives as historical and identify the accepted successor. Preserve historical receipts and their original meaning; future adversarial cases remain future requirements, not executed test results.
4. Prefer targeted patches against freshly read content. If a mechanical replacement was used, reread its affected lines before applying another patch. In particular, check headings, examples, index rows and `open`/`next` wording; a blanket question-number replacement can change the meaning of a sentence without breaking Markdown.
5. On a missing-context patch error, reread the current file and patch the actual text. Do not rerun a non-idempotent insertion helper blindly: it can duplicate summary paragraphs or index rows.

## Freeze and verify the final tree

For a local checkout, set `$parentSha` from the verified live parent first. These PowerShell-compatible checks have been used successfully:

```powershell
git log -1 --format='%H%n%T%n%P'
git rev-parse 'HEAD^{tree}'
git diff --name-only $parentSha HEAD
git diff --check $parentSha HEAD
git status --porcelain=v1
```

Quote `'HEAD^{tree}'` in PowerShell. An unquoted brace expression can be parsed by the shell rather than reaching Git as the intended revision expression. Check native command exit codes; a later successful command does not prove an earlier command succeeded.

- Include new/untracked files in pre-commit checks; use the full parent-to-feature diff after commit. A Markdown-only task may include a user-authorized skill instruction/reference update, but executable helpers change its validation scope. Do not hide scripts under a prose-only claim.
- Validate strict UTF-8, applicable frontmatter/refinement targets, relative links against the actual tree, unique index entries, code fences, whitespace and current/historical status. Regex checks cannot prove design semantics; review the transformed statements themselves.
- For a skill update, run the skill creator's validator on the actual skill folder, then check its referenced files and scope. On Windows, Python UTF-8 mode avoids locale decoding errors. Prefer an existing available runtime over reinstalling dependencies for a prose check.
- Re-read the live parent before publishing. Read back the resulting PR's base/head, sole commit parent, changed paths and Git tree. Attach the created PR in Codex when that tool is available. Keep commands and run-specific SHAs/counts in PR evidence rather than adding them as future policy.
- Use the repository's [exact-tree CI procedure](../../ci-final-tree-verification/SKILL.md). Verify the temporary merge tree against the feature tree and inspect the planned checks for that exact head. A successful prose/development run with product tests skipped is not runtime or release acceptance. Do not reuse a predecessor PR's success.

## Stop at the authorized result

Present the completed design PR and its actual checks/limits. If the task requests a next blocker, first identify a concrete unresolved domain meaning, trust/admission authority or serialized backup meaning, its conflicting outcomes and the affected dependent stage. Give a genuine owner choice a concrete example, pros/cons and recommendation. Do not label every unfinished item blocking or require another question just to continue a sequence. Tunable defaults, precise counter units, configuration encoding and resume/concurrency mechanics are normally engineering work within accepted policy; escalate only a concrete policy conflict or material ambiguity. Existing policy remains binding, and lack of implementation permission is separate from an unresolved architecture choice. Keep unaffected independent work unblocked.

Reconcile prior entrypoints that called routine details owner gates, while preserving accepted limits and historical alternatives. Keep permissions explicit and unresolved options unselected. Do not merge, implement, expand publication allowlists or write retained catalog data just because the documentation checks passed.

This reference captures the repeatable method, not the current architecture. Read the [ADR index](../../../../docs/adr/README.md) for current decisions. If the task authorizes a different delivery shape or only a read-only review, follow that scope instead of applying this sequence mechanically.
