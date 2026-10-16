# Crash recovery inventory — 2026-10-16

Phase 0 completed before source modification. The only original worktree was
`/workspace/git-repo-db`, ordinary non-bare `.git`, branch `work`, HEAD
`b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`. No linked or detached worktrees,
uncommitted tracked/untracked files, stashes, merge/rebase/cherry-pick state,
unique unpushed commits, or former-agent validation files were present.
`git fsck --full --no-reflogs --unreachable` found only the empty tree.
No repository-modifying Git process was running. The environment-created
`codex-index-refresh.lock` was retained; no lock was deleted.

The complete original Git directory, binary diffs, untracked inventory, reflogs,
process inventory and SHA-256 file index are preserved outside the checkout at
`/workspace/recovery-evidence-20261016`. Every one of the 16 distinct reflog
commits was anchored as `refs/recovery/20261016/pre-fetch/<full SHA>` before fetch.
The old P7 agent workspace is unavailable here: no unique unfinished code or
forensic evidence from that workspace could be recovered. This inventory cannot
establish whether unavailable artifacts existed elsewhere.

Fresh remote inspection confirmed main `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`,
#87 `290e9831ff1d0504f7ba755e41a3e899b1ac540c`,
#88 `e0c6fd85bc233412c0b4dbfb32d63d69ffd26893`,
#89 `7cbe97f0be9b19127948c56bf1b7c0b4f6fcaae7`.
All recovered historical commits already belong to main history. No unknown work
was stashed, reset, cleaned, cherry-picked or merged. Dedicated new worktrees
start from the exact remote feature heads. #88 contains #87 through existing
merge `711a9cd234d489916236a15ad2e5acc6029bd7d8`; no repeat merge was needed.

Baseline independent P7 integration run: **46 passed**, exit 0, 2.48 seconds
pytest time (3.309 seconds command wall time), against #88 e0c6fd85 and tree
`4b984207d7dd0d1f39b8a4a97dcdcb4648aa9a7c`. Raw JUnit, journal, output and
command binding are retained beside this file. This is baseline evidence,
not acceptance of subsequent corrections or hosted runtime execution.
