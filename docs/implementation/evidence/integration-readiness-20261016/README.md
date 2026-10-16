# Final P7 integration readiness — 2026-10-16

All three reviewed PRs are **READY_FOR_OWNER_MERGE_AUTHORIZATION** in their declared scopes. No reproducible unaddressed P7 safety defect was found. Owner merge authorization remains pending. The administrative branch-protection endpoint returns HTTP 403, but ordinary branch metadata reports `protected=false`, required-status enforcement off with no contexts; GraphQL reports no branch-protection rule and visible rulesets are empty. No current required-check deadlock is observed. Recheck settings immediately before owner merge. No PR was merged or auto-merge enabled, and no deployment was dispatched.

This documentation/evidence PR is based independently on unchanged main. It is not a prerequisite for the three product PRs and changes no public-runtime implementation. Evidence timestamps are those returned by GitHub or recorded in the existing reports. This review revalidates stored execution evidence; it does not claim to rerun P7 or the full suite.

| PR | Exact feature HEAD | Feature tree | Verdict |
| --- | --- | --- | --- |
| [89](https://github.com/TakashiSasaki/git-repo-db/pull/89) | `660178ff1a881e4482b7a3cde02b51dc50cf2603` | `ed80623514a5e574d1e24e908b95504f60b815db` | READY_FOR_OWNER_MERGE_AUTHORIZATION |
| [87](https://github.com/TakashiSasaki/git-repo-db/pull/87) | `c058af3a1be9ba3e9a1b0ba649c789f5bdcd1d75` | `920bc7b61477d3e1d6f7ac2ecaaef74bb188d4dd` | READY_FOR_OWNER_MERGE_AUTHORIZATION |
| [88](https://github.com/TakashiSasaki/git-repo-db/pull/88) | `e956cd50b1f25bd95427301cced4741bb68e24f8` | `87cd5817c5e945b0f29b8501bfa3fda6d2674dc4` | READY_FOR_OWNER_MERGE_AUTHORIZATION |

Main was refreshed as `b86c46761ec0c3f3843a19edd4f3e106ef5ef58c`. Exact PR metadata and check-run records are retained next to this report. All three were OPEN, MERGEABLE and CLEAN. Each exact HEAD has successful `offline` Development and `build-and-validate` Pages checks; `deploy-to-pages` is correctly SKIPPED on PRs.

## PR 89 — publication inputs and hosted validation

The diff contains 24 files: workflow paths, existing builder's explicit no-Mermaid unit-test path, regression tests, one existing skill and internal evidence. The approved staging allowlist and deployment permissions/gates are unchanged. Both push and pull-request filters cover every one of the **74** declared publication/build/schema-check input files. The previously verified executed schema-check import closure, including ten transitive modules, remains represented. Conditional imports on unexecuted future branches remain outside this historical probe's guarantee; modifying the builder requires updating the dependency regression.

All 74 exact byte sizes/SHA-256 values match the independently tested `fbf3c37f6de3522e800a8cc282a332b3fbd1a0fd` source manifest. The subsequent final commit changes only the internal evidence directory. The original independent review is preserved at `docs/implementation/evidence/pages-ci/2026-10-16-independent-review/REPORT.md` on PR 89.

Latest exact-HEAD [Pages run 38918703718](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38918703718) succeeds. Actual run-log ZIP bytes show checkout merge `80cf339`, effective tree `ed80623514a5e574d1e24e908b95504f60b815db`, ten actual Mermaid renders, MkDocs build, publication safety with zero sensitive files, zero broken links and **8 passed in 1.60s**. Narrow verbatim lines are retained in `pr89-pages-excerpt.log`. Development run [38918703695](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38918703695) also succeeds. No new performance benchmark or local browser download/execution was attempted.

Required-check deadlock risk is conditional: GitHub may leave a required `build-and-validate` context pending for a PR excluded by workflow path filtering. The same general risk existed for earlier filters, and narrowing expands the excluded set. The administrative protection endpoint returns **HTTP 403: Resource not accessible by integration**. Additional supported metadata resolves the current state: ordinary `GET /branches/main` reports `protected=false`, `protection.enabled=false`, required-status `checks=[]`, `contexts=[]`, enforcement `off`; GraphQL returns `defaultBranchRef.branchProtectionRule=null` without errors; repository rulesets return `[]`. No configured required-check deadlock is observed. Recheck settings at the actual owner merge barrier. If a new policy makes Pages unconditionally required, resolve the CI design in a focused correction without weakening checks before merging. No policy was changed or bypassed.

## PR 87 — scoped design consistency

The exact diff adds only `docs/implementation/p7-backup-recovery-technical-design.md` (292 lines). No ADR, DDL, production, dependency or workflow file changes. It preserves ADR 0026's immediate persistent stop, read-only suspect preservation, untrusted typed salvage, fresh verified restore and receiver-validated merge. ADR 0022 role evidence and ADR 0027/0028 attribution/checksum boundaries remain intact.

The final design expressly limits supported recovery to Linux/cooperating-process filesystem primitives and process/SIGKILL evidence. It does not promise physical host power-loss durability. Unsupported Context resources/field candidates remain qualified observations; full typed Context salvage is not claimed. Operational/Search are initialized empty; full Search population requires separate P6 reconstruction. The public Schema 21 initializer/runtime is explicitly unchanged. Exact-HEAD Development [38920182337](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38920182337) and Pages [38920182320](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38920182320) both succeed.

## PR 88 — executable and review reconciliation

PR 87's exact final HEAD is an ancestor of PR 88; main is an ancestor of both. Tested source remains `178ddbaa8fa06f52aff4993730205c5a38da91f4`, tree `9740ad1a91f367192bb31ce9777d039c2bb4729b`. **368** executable input hashes match that source byte-for-byte at final PR HEAD. All later changed paths are evidence or existing skills. **443** transported artifacts match their stored SHA-256 and their decompressed original size/SHA-256. This includes the final reconciliation and failed experiments, not merely passing summaries.

Changed production scope is the six opt-in recovery modules plus bounded native-header allocation in the opt-in `domain/git_native.py`. The earlier public decoder and runtime remain separate. Default store/schema, packaged public DDL and CLI paths are byte-identical to main; the exact verified list is in `verification.json`. Audit registration adds explicit isolated P7 modules instead of a broad exclusion. The pre-existing `test_cli_more.py` fencing test was corrected to inject Operational state and release the subprocess hook in `finally`; no public production route was changed to pass it.

Independent stored approvals bind the final tested source: A covers database/domain and independently rechecks B's CHECK/UTF-8 correction; B covers crash/filesystem/stop/activation and excludes own accounting/validation production changes; C independently covers accounting/security/bounded input and all P7 nodes; D authored no P7 production/test changes and covers installed distributions, source identity, domain counterexamples and evidence. A explicitly excludes own input implementation, covered by C/D. Final A supplement and B/C/D receipts identify `178ddbaa` / tree `9740ad1`; post-review executable identity is unchanged. The scopes collectively cover all recorded production corrections without treating a writer's own approval as independent.

This review re-parses installed wheel and wheel-from-sdist evidence: each contains **255 unique JUnit cases, 255 unique journal starts, 765 passed phases and exit 0**, without skips/failures/errors. Both wheels were independently identified as SHA-256 `dfab687567d3b3202c1ac4de0e2d1485835eb42f3a962242c05c762b5ac2e414`; the stored distribution review verifies 124 package/resource files and parent/child site-packages imports. Distribution binaries remain external and were not downloaded or rebuilt here. Their identity relies on the hash-verified independent execution record.

The root full run also reconciles directly: **3748 selected/JUnit/journal nodes**, **11242 phases**, **3517 passed / 229 failed / 2 errors**, exit 1. Its 255 P7 and 937 P1–P6/compatibility successes do not erase **228 inherited public-runtime failures**, the missing local Chrome documentation failure or the two initial wheelhouse setup errors. Later two-package success remains supplementary. Live/stress exclusions and failed capacity/bootstrap/probe experiments remain in the original evidence. This is not a whole-repository release acceptance claim.

Latest exact-HEAD Development [38926458613](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38926458613) is independently decoded from its actual run log. Receipt ZIP SHA-256 `c934ed37d70a2192eaa2d858fc7aaa36000164f27288831b57fe896b0c79405a`, **76,206 bytes**, **21 indexed members** verified. Feature `e956cd50`, checkout merge `80c3f278592e73efc2fd4049b96c17afb3d17257`, effective tree `87cd5817`. Actual status: `development_checks_passed`, `full_acceptance=false`, **0 runtime pytest executions**. Latest Pages [38926458993](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38926458993) also succeeds. Development is not hosted P7 acceptance.

The large diff was inspected by scope and decompressed credential-pattern scan. It retains synthetic test results, UUIDs, temporary/worktree paths, environment/process/history logs and reviewed probe source as text. No retained catalog, real backup or distribution archive binary appears in the changed evidence paths; no private-key/GitHub-token/AWS-key pattern matched. This bounded scan is not a universal disclosure guarantee. No unintended real catalog data or credential was found. Internal evidence remains outside the existing Pages publication allowlist.

## Merge plan and reproducibility

Use the owner-executable plan in [owner-merge-plan.md](owner-merge-plan.md). Local `git merge-tree --write-tree` and temporary two-parent `git commit-tree` objects simulate the full order without changing refs or the remote:

| Step | Expected effective tree |
| --- | --- |
| main + PR 89 | `ed80623514a5e574d1e24e908b95504f60b815db` |
| previous + PR 87 | `6ebd07cf4d6846e7d964c1be571c8507c037b9be` |
| previous + PR 88 | `e250fe0ad801013fb9c59e929cfc7f875fabb5b8` |

All are conflict-free. Final tree differs from PR 88 only by PR 89's 24 changed paths. Synthetic commit IDs in `merge-simulation.json` are local verification artifacts, not predictions of GitHub merge SHA. Merge parents/effective trees, source identity, required checks and possible PR 88 base retargeting must be rechecked immediately before owner execution.

Reproduce the Git-object/evidence checks from a clone containing these exact commits:

```sh
python docs/implementation/evidence/integration-readiness-20261016/verify.py
```

The driver writes `verification.json` and `merge-simulation.json`; it does not execute reviewed production code, contact GitHub, or merge/push refs. It creates unreferenced local synthetic Git objects to model reviewed history. Refresh remote refs separately and compare the frozen SHAs before relying on this report. Ruff lint/format of the driver and staged whitespace checks passed. Independent review is recorded separately after the frozen documentation checkpoint.

Independent review found that the first evidence-driver revision compared installed-distribution counts without explicitly comparing all JUnit identities. The follow-up now enforces duplicate-free collection/XML/journal node-set equality and exactly one passed setup/call/teardown phase per installed node. The original immutable P7 evidence already contained independent per-node reconciliation; this correction strengthens this new review driver and does not change P7 acceptance scope.
