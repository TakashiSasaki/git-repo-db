# Design stack integration review and merge plan — 2026-10-15

This is a documentation-only Integration Lead report. It prepares a main-target integration PR for a separate owner decision; **no merge, auto-merge, main update, deployment, implementation or catalog operation is authorized or executed**. The original design commits are preserved, including the independently reviewed latest design HEAD. Only documentary applicability corrections and this report are added on the new integration branch.

The final integration HEAD/tree, temporary merge tree and completed CI run URLs are recorded in the containing integration PR's verification section. Keeping those external exact-head receipts avoids claiming that a document can contain its own commit/tree hash. Read that final verification section together with this source review before approval; a predecessor PR's green status is not final integration evidence.

## 1. Live baseline and actual dependency graph

Initial metadata snapshot: **2026-10-15 13:16:47 UTC**. GitHub branch/PR metadata and fetched full Git history agreed:

| Item | Verified value |
| --- | --- |
| Repository | `TakashiSasaki/git-repo-db` |
| main HEAD / latest-design merge-base | `b329efacafe612404848dfd26424eec219680e4c` |
| Latest design | [PR #68 / ADR 0027](https://github.com/TakashiSasaki/git-repo-db/pull/68) |
| Latest design HEAD | `6e2554263a19ae9d9eb59e00b5baf416f935cba3` |
| Latest design tree | `f5c3970a45eaf137b5f5fad9a2f1c525c42af47e` |
| Original cumulative history | 28 commits ahead / 0 behind main; linear single-parent history |
| Original cumulative diff | 36 Markdown files, 3,074 additions / 52 deletions |
| Integration branch | `codex/design-stack-main-integration` |
| Applicability correction | `df4ac35d50079be961e648dd6c368a840baf5a26`, tree `ccb5f29abb816dccc28aa705f54ad8d641ea59bf`, sole parent the original design HEAD |
| Other work | No main-only commits; all older PR heads #1–#43 are main ancestors; no other open PR outside this stack and excluded #52 at the snapshot |

The following sequence was derived by matching each actual base SHA to the preceding head and by checking **every commit parent** inside each PR range, not from consecutive PR numbers. All 24 target PRs were open, unmerged and mergeable against their own bases. The extra commits belong to #44 (2), #53 (3) and #67 (2); all others have one. Every historical stack commit changes Markdown only.

| PR | Head branch | Full head SHA | Base branch | Full base SHA | Commits | Observed state |
| --- | --- | --- | --- | --- | --- | --- |
| [#44](https://github.com/TakashiSasaki/git-repo-db/pull/44) | `docs/adr-0003-append-only-git-core-context` | `2dc0e438c3d029866b847f4e3404a3b7dbaa2b26` | `main` | `b329efacafe612404848dfd26424eec219680e4c` | 2 | open / mergeable |
| [#45](https://github.com/TakashiSasaki/git-repo-db/pull/45) | `docs/adr-0004-metadata-only-git-core` | `936ca68c3743749dfc0eb2ad90b8cbd5ba7327ec` | `docs/adr-0003-append-only-git-core-context` | `2dc0e438c3d029866b847f4e3404a3b7dbaa2b26` | 1 | open / mergeable |
| [#46](https://github.com/TakashiSasaki/git-repo-db/pull/46) | `docs/adr-0005-common-oid-identity` | `c3002e8894a228c31a892ad54aa7e6815d33889e` | `docs/adr-0004-metadata-only-git-core` | `936ca68c3743749dfc0eb2ad90b8cbd5ba7327ec` | 1 | open / mergeable |
| [#47](https://github.com/TakashiSasaki/git-repo-db/pull/47) | `docs/adr-0006-field-claims-relation-groups` | `65b2344a8c96b9f3c83381572847cbe9f0c6dae1` | `docs/adr-0005-common-oid-identity` | `c3002e8894a228c31a892ad54aa7e6815d33889e` | 1 | open / mergeable |
| [#48](https://github.com/TakashiSasaki/git-repo-db/pull/48) | `docs/adr-0007-verification-aware-git-reads` | `5963f28229bc7798634d549855a08db06d12b3a6` | `docs/adr-0006-field-claims-relation-groups` | `65b2344a8c96b9f3c83381572847cbe9f0c6dae1` | 1 | open / mergeable |
| [#49](https://github.com/TakashiSasaki/git-repo-db/pull/49) | `docs/adr-0008-domain-split-git-verification` | `607c91e4a1254c57ca8e22733541c2e4a6ebce2c` | `docs/adr-0007-verification-aware-git-reads` | `5963f28229bc7798634d549855a08db06d12b3a6` | 1 | open / mergeable |
| [#50](https://github.com/TakashiSasaki/git-repo-db/pull/50) | `docs/adr-0009-bounded-byte-admission` | `29dd530a4245a62c7b9c0dbf2cd07a2ad62cb84e` | `docs/adr-0008-domain-split-git-verification` | `607c91e4a1254c57ca8e22733541c2e4a6ebce2c` | 1 | open / mergeable |
| [#51](https://github.com/TakashiSasaki/git-repo-db/pull/51) | `docs/adr-0010-operation-scoped-cas-integrity` | `a79924f36ddb03c2f5472f14f0233531bd7788a2` | `docs/adr-0009-bounded-byte-admission` | `29dd530a4245a62c7b9c0dbf2cd07a2ad62cb84e` | 1 | open / mergeable |
| [#53](https://github.com/TakashiSasaki/git-repo-db/pull/53) | `docs/adr-0011-append-only-cas-instance-recovery` | `df0689b3a06bb1a46233737f444eb64527ec5db5` | `docs/adr-0010-operation-scoped-cas-integrity` | `a79924f36ddb03c2f5472f14f0233531bd7788a2` | 3 | open / mergeable |
| [#54](https://github.com/TakashiSasaki/git-repo-db/pull/54) | `docs/adr-0013-evidence-derived-cas-selection` | `0301fcc8aeef427e2b9e2a3197a4ed993dcdf657` | `docs/adr-0011-append-only-cas-instance-recovery` | `df0689b3a06bb1a46233737f444eb64527ec5db5` | 1 | open / mergeable |
| [#55](https://github.com/TakashiSasaki/git-repo-db/pull/55) | `docs/adr-0014-history-notes-no-file-archive` | `4a45a137ee22ec1c87fb616bc94aef5587918737` | `docs/adr-0013-evidence-derived-cas-selection` | `0301fcc8aeef427e2b9e2a3197a4ed993dcdf657` | 1 | open / mergeable |
| [#56](https://github.com/TakashiSasaki/git-repo-db/pull/56) | `docs/adr-0015-notes-ref-discovery` | `d230f3951924e47395c52326670bfd56adb97e2f` | `docs/adr-0014-history-notes-no-file-archive` | `4a45a137ee22ec1c87fb616bc94aef5587918737` | 1 | open / mergeable |
| [#57](https://github.com/TakashiSasaki/git-repo-db/pull/57) | `docs/adr-0016-notes-capture-identity` | `896fbee08ed186897069558bc70d7f49a59325bb` | `docs/adr-0015-notes-ref-discovery` | `d230f3951924e47395c52326670bfd56adb97e2f` | 1 | open / mergeable |
| [#58](https://github.com/TakashiSasaki/git-repo-db/pull/58) | `docs/adr-0017-domain-keys-no-storage-surrogates` | `c3cb94b367777b4a31d9dcf9644e253a69eef74a` | `docs/adr-0016-notes-capture-identity` | `896fbee08ed186897069558bc70d7f49a59325bb` | 1 | open / mergeable |
| [#59](https://github.com/TakashiSasaki/git-repo-db/pull/59) | `docs/adr-0018-notes-capture-uuidv4-key` | `799f1052ece4b02d0ed2d8ace70c2deddc6ddcbf` | `docs/adr-0017-domain-keys-no-storage-surrogates` | `c3cb94b367777b4a31d9dcf9644e253a69eef74a` | 1 | open / mergeable |
| [#60](https://github.com/TakashiSasaki/git-repo-db/pull/60) | `docs/adr-0019-monotonic-notes-capture-facts` | `c1c5bf580bdb0383ed9b5df613b73c70753f73d9` | `docs/adr-0018-notes-capture-uuidv4-key` | `799f1052ece4b02d0ed2d8ace70c2deddc6ddcbf` | 1 | open / mergeable |
| [#61](https://github.com/TakashiSasaki/git-repo-db/pull/61) | `docs/adr-0020-competing-notes-member-claims` | `d12e54b114b48167898ee6e9789d0ec9d63b60fe` | `docs/adr-0019-monotonic-notes-capture-facts` | `c1c5bf580bdb0383ed9b5df613b73c70753f73d9` | 1 | open / mergeable |
| [#62](https://github.com/TakashiSasaki/git-repo-db/pull/62) | `codex/adr-0021-semantic-notes-claim-keys` | `51093022b50d773b0620fb5bec9b0a7b4a7e1544` | `docs/adr-0020-competing-notes-member-claims` | `d12e54b114b48167898ee6e9789d0ec9d63b60fe` | 1 | open / mergeable |
| [#63](https://github.com/TakashiSasaki/git-repo-db/pull/63) | `codex/adr-0022-verified-notes-role-admission` | `8bf737152033902063eac7513840a210c06bbfbb` | `codex/adr-0021-semantic-notes-claim-keys` | `51093022b50d773b0620fb5bec9b0a7b4a7e1544` | 1 | open / mergeable |
| [#64](https://github.com/TakashiSasaki/git-repo-db/pull/64) | `codex/adr-0023-configurable-notes-resource-budgets` | `6975fbda577323291b922ddc6a89369dcdab0bbb` | `codex/adr-0022-verified-notes-role-admission` | `8bf737152033902063eac7513840a210c06bbfbb` | 1 | open / mergeable |
| [#65](https://github.com/TakashiSasaki/git-repo-db/pull/65) | `codex/adr-0024-actual-notes-resource-accounting` | `45f7da24924caa8d4da7a00107e32dc03c6bb416` | `codex/adr-0023-configurable-notes-resource-budgets` | `6975fbda577323291b922ddc6a89369dcdab0bbb` | 1 | open / mergeable |
| [#66](https://github.com/TakashiSasaki/git-repo-db/pull/66) | `codex/adr-0025-budget-scope-blocker-triage` | `8cb70cd2c9a4ef2abbf6052ad9e5541a6c20c4ce` | `codex/adr-0024-actual-notes-resource-accounting` | `45f7da24924caa8d4da7a00107e32dc03c6bb416` | 1 | open / mergeable |
| [#67](https://github.com/TakashiSasaki/git-repo-db/pull/67) | `codex/adr-0026-stop-salvage-restore-merge` | `1a9fc10894d097d4af68f040155d85f8fe5b684d` | `codex/adr-0025-budget-scope-blocker-triage` | `8cb70cd2c9a4ef2abbf6052ad9e5541a6c20c4ce` | 2 | open / mergeable |
| [#68](https://github.com/TakashiSasaki/git-repo-db/pull/68) | `codex/adr-0027-unauthenticated-capture-origin` | `6e2554263a19ae9d9eb59e00b5baf416f935cba3` | `codex/adr-0026-stop-salvage-restore-merge` | `1a9fc10894d097d4af68f040155d85f8fe5b684d` | 1 | open / mergeable |

An in-memory `git merge-tree --write-tree` preview of the pinned main/latest-design inputs returned the latest-design tree, without conflicts or changing any branch. Main is already its ancestor. The final integration PR must repeat the effective-tree comparison after the documentary follow-ups; no actual merge is performed here.

### Excluded governance and parallel allocation

[PR #52](https://github.com/TakashiSasaki/git-repo-db/pull/52) remains a separate open, unmerged, unadopted proposal at `8337cef911e664b1a2c267c837a05ddaa0c762f9`, based on `a79924f36ddb03c2f5472f14f0233531bd7788a2`. Its unique commit is not an ancestor of the design/integration history. Its exclusive files are absent: `.agents/skills/adr-workflow/SKILL.md`, `docs/adr/0011-adr-governance.md`, `docs/adr/policy.md`, `docs/adr/template.md`, `docs/adr/template-mini.md`. Shared guides were inspected for accidental policy adoption.

There are **26 numbered accepted ADR files and 26 matching unique numeric index rows**: 0001–0027 except reserved 0011. PR #53's branch name contains `0011`, but its final accepted document is ADR 0012; that branch name is not governance inclusion. #52 overlaps shared guides/index and needs separate reconciliation if later adopted. No other open parallel ADR allocation was observed. Existing PR states, bases and branches are not changed by this integration preparation.

## 2. Independent review and findings

Three fresh delegated reviewers received the frozen SHA/tree with no author conversation history and explicit read-only instructions. The Integration Lead authored the latest design work and is **not** counted as independent review. Reviewers reported no file/ref/PR changes and performed no GitHub approval or merge. All reviewed the original `6e2554263a19ae9d9eb59e00b5baf416f935cba3` / `f5c3970a45eaf137b5f5fad9a2f1c525c42af47e`:

| Reviewer | Scope | Result and evidence boundary |
| --- | --- | --- |
| `integration_architecture_review` (B1) | All 24 accepted ADRs 0003–0010/0012–0027, precedence/supersession, Core/Context, recovery/trust, current guides/register/status | No actionable finding. Exact SHA/tree, all 36 changed Markdown, UTF-8, whitespace and 346 relative file links checked; no runtime/hosted/release execution |
| `integration_persistence_review` (B2) | Immutable facts/groups/keys, notes and file-retention boundary, local verification, Source/Coverage/time, backup/recovery, relevant baseline identity traces | No Blocking/Major/Minor; PR-01 below is an implementation constraint, not a new owner choice. No executable/DDL/recovery/runtime or release tests |
| `integration_documents_pages_review` (B3) | Current/historical entrypoints, index/refinement/frontmatter, all five skills, source links and Pages staging/workflow | Two Minor applicability defects, no Blocking/Major. 41 Markdown files, 362 non-fenced relative links, fences, 26 unique ADR/index rows, 14 YAML ADRs and five skill frontmatters checked. Build/deploy not run by reviewer |

Severity criteria: **Blocking** requires resolution of an unsafe/contradictory target or a genuine owner choice; **Major** is a material current-contract/instruction defect preventing merge; **Minor** is a clear editorial/applicability defect within settled policy; **Informational** records an engineering constraint or verification/delivery limit. Execution authorization is separate from architectural blockers.

| ID | Severity | Target at original review | Problem | Impact | Recommended correction / disposition | Merge blocking |
| --- | --- | --- | --- | --- | --- | --- |
| DR-31 | Minor | `.agents/skills/three-store-invariants/SKILL.md:65–67,158–159` | Unqualified Core-only/quarantine-count recipe and historical test count could be reused as current target | Old implemented mechanisms could be copied despite ADR 0003/0026 | **Fixed by Lead** in `df4ac35d50079be961e648dd6c368a840baf5a26`: baseline-only applicability, scoped current-target guidance, preserved historical recipe/counts with source revision | No; resolved |
| DR-32 | Minor | `docs/phase2/README.md:13–21,43–47`; `docs/phase2/AGENTS.md:40` | Entry guidance foregrounded old canonical placement/CAS-41/mutable revision mechanisms without current scope | Incomplete target map for an agent entering through Phase 2 | **Fixed by Lead** in the same commit: current index/transition map and clear baseline/target boundaries, no new policy | No; resolved |
| PR-01 | Informational | `docs/adr/0017-domain-keys-without-storage-surrogates.md:25–27,48–50,78,85–96`; `AGENTS.md:62`; `docs/data-model.md:27`; baseline `catalog3.sql:136–150`, `store.py:315–326`, `coverage.py:76–89` | Legacy Coverage scope UUID and claim integer have no established surrogate exception | Required key audit must satisfy both actual semantic PK/FKs and the exact five-column/latest-observation contract | Keep as implementation audit requirement. Do not invent a genuine event identity, grandfather a surrogate or silently reinterpret the contract as merely a view. No impossible pair of final target requirements was established | No |
| DR-33 | Informational | `.github/workflows/pages.yml:3–17,87–111` | Main document push starts the existing publication path | Merge can update the allowlisted site after build; PR event deploy is skipped | Obtain separate explicit merge/Pages delivery authorization; see section 4 | No source defect; delivery approval required |
| DR-34 | Informational | `scripts/build_docs_site.py:243–365,374–420`; `mkdocs.yml:7,73–76` | ADR 0003–0027 and this report are outside the publication allowlist | A green Pages build does not render or publish these new design ADRs | Validate their source separately. Any publication expansion is separate work/approval | No |
| IL-01 | Informational | Unchanged historical files listed below | Whole-repository link scan found five inherited dangling source/test links | Historical navigation limitation, with no new missing path in the integration changes | Disclose unchanged evidence; do not rewrite old checkpoints or claim all repository links pass | No |

**Independent correction revalidation:** B1 reviewer `integration_architecture_review`, who did not raise DR-31/32 and did not author their correction, inspected `df4ac35d50079be961e648dd6c368a840baf5a26` / tree `ccb5f29abb816dccc28aa705f54ad8d641ea59bf`. It verified the four-Markdown-only diff, exact parent, no ADR/policy/code change, 28 relative file links, UTF-8, frontmatter and whitespace. It confirmed the historical skill at `f5c92d0509284cb559c882e61c9703542c78257d` is byte-identical to the frozen predecessor skill. **DR-31/32 fixed; no new finding.** The finding author did not provide final approval of its own correction.

Counts: **0 Blocking, 0 Major; 2 Minor found and fixed, 0 Minor remaining**. Four Informational items remain as disclosed limits/constraints. No accepted owner decision was changed. **Estimated remaining architectural owner blockers: 0 in the current Git Core/Context migration scope.** Exact DDL, proof/wire/clone/fencing/pairing/recovery mechanics remain engineering work; deferred extensions and missing implementation permission are not new architectural questions. Escalate a concrete incompatible proposal if one is later demonstrated.

## 3. Verification scope and reproducible commands

The following checks were actually used, substituting the recorded literal SHAs for BASE/DESIGN/HEAD where shown. Commands are inspection/validation; merge execution is only a future plan.

```powershell
git fetch origin 'refs/heads/*:refs/remotes/origin/*'
git log --graph --oneline --decorate BASE..DESIGN
git merge-base BASE DESIGN
git rev-list --left-right --count BASE...DESIGN
git rev-list --reverse --parents PR_BASE..PR_HEAD
git diff-tree --no-commit-id --name-only -r COMMIT
git diff --name-status BASE HEAD
git diff --check BASE HEAD
git merge-base --is-ancestor GOVERNANCE_HEAD DESIGN
git merge-tree --write-tree BASE DESIGN
git log -1 --format='%H%n%T%n%P'
git rev-parse 'HEAD^{tree}'
git status --porcelain=v1
```

API reads covered `branches/main`, all 68 PR metadata records, detailed metadata for #44–#68, repository merge settings and the `github-pages` environment/branch policies. Main permits merge commits; auto-merge is disabled; automatic branch deletion is disabled. The environment allows only branch `main` and has a branch-policy rule, with no required-reviewer rule observed. These are observations, not a promise that settings stay unchanged.

Lead static scan at the corrected commit parsed **all 174 tracked Markdown files**, strict UTF-8 and **978 local file/image/HTML-link occurrences**. All **370 occurrences in the 38 changed files** resolve; 40 additional source links refer to explicitly generated staged-site routes and are checked by the site build. All 26 ADR index entries are unique and exactly cover numeric ADR files. All 14 YAML-bearing ADRs parse as accepted with existing refinement/replacement targets; earlier Markdown-style accepted-status records retain their existing convention, without adopting #52 templates. All five skills have valid matching name/description frontmatter. Official skill validation passed for the two touched skills in UTF-8 mode.

The final report-only commit adds one Markdown document. Repeat the complete path/link/status/whitespace check for its exact final SHA; final counts and any changed facts belong to the PR's verification table. No executable helper or raw API payload is committed. Validation helpers and snapshots remain outside the repository worktrees.

The five inherited missing links are:

| Source | Missing target | Baseline evidence |
| --- | --- | --- |
| `docs/phase2/no-independent-publication-adr.md:100` | `src/repo_catalog/adapters/sqlite/parser_model.py` | Source blob `55678e4aa6c6501ca8b15a780eccdc245a9483e9` unchanged from main |
| `docs/phase2/workstreams/publication.md:30` | Same deleted parser file, `#L332` | Source blob `280418b08c4d0c23ae0c0be53182fb9729cae78e` unchanged from main |
| `docs/schema-hardening/p3a-handoff.md:84` | `tests/integration/test_conversion_source_admission.py`, `tests/unit/test_conversion_phase.py`, `tests/integration/test_p3a_operational_flow.py` | Source blob `a80e82a7f82f49338b8d7494d61e9bb67e0709f1` unchanged from main |

Validation distinctions required for the final integration PR:

| Check | Required interpretation |
| --- | --- |
| Development CI | Run/read the final integration PR event; verify the planned prose checks and gate for the exact feature SHA and checkout tree |
| Document site build/unit tests | Validate the unchanged explicit public-site staging/build and its safety/link checks; deployment must be skipped on the PR |
| New design ADRs | Independently reviewed and source-validated; outside site allowlist, so a Pages success alone does not validate/render them |
| Product tests | Report selected/executed/unexecuted files from the actual final plan. Do not demand or invent full runtime execution for this Markdown-only integration |
| Release validation | Not requested or performed. No local/hosted full release, packaging, recovery/Exchange simulation or release acceptance is claimed |

No application, SQL/DDL, test, dependency, workflow, build source, MkDocs config or public-site source differs from main. The accepted implementation remains the old baseline; no running catalog or authenticated upstream collection was used. A local full site build is not claimed if the final site validation is hosted. Previous #68 CI is historical evidence only and is not reused for this integration PR.

## 4. Pages publication impact and separate approval

The unchanged workflows are `tests` and `pages`. Both run on the main push; `pages` path filters match `docs/**`. Pages build performs locked dependency setup, schema-visualization freshness checking, site build, site unit tests and a preview artifact. Configure/upload/deploy conditions are `github.ref == 'refs/heads/main' && github.event_name != 'pull_request'`. PR execution skips publication, including when Draft. Manual dispatch on main also satisfies the publication condition; it is not a safe way to request build-only validation there.

The live `github-pages` environment is restricted to main, with no required-reviewer gate observed. Thus a future approved main merge is eligible to publish automatically after successful build; do not rely on an unconfigured manual hold.

The actual publication staging allowlist contains:

- Named `docs/site/` homepage, architecture, ADR index, development and schema DBML/Mermaid index documents; named PWA files/icons.
- Explicitly copied ADR **0001 and 0002** only, with ADR 0001 repository-link adjustments.
- Schema README, standalone schema viewer, DBML exports and ten named Mermaid documents rendered to SVG, plus configured MkDocs/theme assets.

It excludes **ADR 0003–0027**, root/nested agent guides, the new transition plan and this integration report. There is no directory-wide ADR glob. ADR 0002's new baseline/supersession annotation **is already allowlisted and will update**, and home build commit/tree metadata changes. Implemented schema visualization and other unchanged pages keep their existing source meaning; this is not publication of a newly implemented four-store schema. Public-source GitHub links can resolve newly merged repository files, independently of Pages staging.

Owner execution choices, separate from architectural blocker count:

1. **Approve source integration and the existing allowlisted Pages deployment together.** Approve the exact final HEAD/tree and the current publication scope explicitly; the later main push uses the existing workflow. Observe the new main run and deployed source metadata afterward. No allowlist expansion or additional manual main dispatch is needed.
2. **Approve source integration but hold Pages publication.** Separately authorize and validate a concrete deployment pause/settings or workflow change **before** the main push. No such change is made here. Retest/review affected inputs and require owner approval of the resulting merge/publication plan; merely saying "merge only" cannot suppress the existing deployment condition.
3. **Publish the new design ADRs/report on Pages.** This requires separate owner-approved allowlist/navigation/source-label changes and validation. It is not included in either the present PR or an approval of the existing allowlist.

This task performs none of these main/publication actions. Final readiness means **READY FOR OWNER APPROVAL**, not permission to merge or deploy. Extra delivery authorization is expected at the user's final decision and does not inflate the current architectural owner-blocker estimate.

## 5. Main merge execution plan — not executed

1. Recommend merging only the **new main-target integration PR**, after its final exact-head verification and owner authorization. It incorporates #44–#51 and #53–#68 by ancestry; #52 is excluded. Do not merge each old PR separately or reproduce commits by cherry-pick.
2. Prefer a **merge commit**, permitted by current repository settings. Preserve all 28 original design SHAs and the integration-only documentary follow-ups. No squash, rebase, amend or force push.
3. Immediately before execution, re-read main, the integration PR head, latest design #68 and every original target PR state/head. Require exact approved SHAs/base/merge-base and intended diff. If main or a target head moved, stop and recompute dependencies, review, effective tree and CI before seeking renewed approval.
4. Require no unresolved Blocking/Major finding, validated Minor dispositions, correct Markdown-only scope, #52 exclusion, local link/frontmatter/index/skill/whitespace checks, successful final development and site runs with actual selections disclosed, matching temporary merge/feature trees, and a clean checkout. No release qualification is implied or newly required for this design-only delivery.
5. Obtain explicit **merge authorization** and a distinct decision on **existing allowlisted Pages publication or an approved prior pause**. Keep auto-merge disabled. New ADR Pages publication remains separate work.
6. After an authorized merge, fetch the actual merge commit M. Verify its first parent is the approved pre-merge main and second parent is the approved integration HEAD H; verify H and all 24 design heads are ancestors of M/main. Require `M^{tree}` to equal the verified final integration tree when base is unchanged. Re-read GitHub's actual PR merge result, not only its UI label.
7. Observe main CI and, only as authorized, Pages deploy/result/source commit/tree metadata. A deployment failure is not solved by changing the allowlist or hiding stale build metadata. The product runtime remains unimplemented target work.
8. Re-query original PR states after integration; do not assume which GitHub marks indirectly merged. Preserve all old PRs and branches during this task. For any remaining open PR, show its head is included and it has no unincorporated work before separately authorized close/cleanup; link the integration result. Keep #52 outside cleanup. Automatic branch deletion is currently off; retain branches until their owners/dependents and explicit cleanup permission are checked.
9. On a moved ref, conflict, unexpected code/governance inclusion, unresolved substantive issue, failed required CI or missing publication authorization, keep the PR Draft and stop execution. Before merge, preserve evidence and prepare a normal follow-up or report the owner choice; do not rewrite old SHAs. After a later authorized merge, stop further merges/deployments, preserve actual commit/run evidence and seek an approved fix-forward/revert PR or publication pause/recovery plan. Never reset/force-push main, modify catalogs or silently redeploy/revert under this preparatory authorization.

## 6. Complete integration file inventory

This includes the original 36 files, the corrected baseline skill and Phase 2 README newly entering the main diff, and this report. All **39 paths are Markdown**. Existing changed guides/reference also contain the small correction. No original design commit was rewritten; final GitHub comparison must confirm this inventory.

| Change | Path | Type |
| --- | --- | --- |
| M | `.agents/skills/lessons-to-skills/SKILL.md` | Markdown |
| A | `.agents/skills/lessons-to-skills/references/design-only-adr-stack-updates.md` | Markdown |
| M | `.agents/skills/three-store-invariants/SKILL.md` | Markdown |
| M | `AGENTS.md` | Markdown |
| M | `README.md` | Markdown |
| M | `docs/adr/0002-three-store-boundary-architecture.md` | Markdown |
| A | `docs/adr/0003-append-only-git-core-and-context-store.md` | Markdown |
| A | `docs/adr/0004-metadata-only-git-core.md` | Markdown |
| A | `docs/adr/0005-common-oid-identity-with-attributed-metadata.md` | Markdown |
| A | `docs/adr/0006-field-claims-and-observation-scoped-relations.md` | Markdown |
| A | `docs/adr/0007-verification-aware-git-metadata-reads.md` | Markdown |
| A | `docs/adr/0008-domain-split-git-verification-ownership.md` | Markdown |
| A | `docs/adr/0009-bounded-byte-admission-and-physical-health.md` | Markdown |
| A | `docs/adr/0010-operation-scoped-cas-physical-integrity.md` | Markdown |
| A | `docs/adr/0012-append-only-multiple-cas-physical-instances.md` | Markdown |
| A | `docs/adr/0013-deterministic-cas-instance-eligibility.md` | Markdown |
| A | `docs/adr/0014-history-and-notes-catalog-without-file-archive.md` | Markdown |
| A | `docs/adr/0015-automatic-git-notes-ref-discovery.md` | Markdown |
| A | `docs/adr/0016-immutable-notes-ref-capture-observations.md` | Markdown |
| A | `docs/adr/0017-domain-keys-without-storage-surrogates.md` | Markdown |
| A | `docs/adr/0018-notes-capture-uuidv4-composite-identity.md` | Markdown |
| A | `docs/adr/0019-monotonic-notes-capture-fact-admission.md` | Markdown |
| A | `docs/adr/0020-immutable-competing-notes-member-claims.md` | Markdown |
| A | `docs/adr/0021-direct-semantic-notes-claim-group-keys.md` | Markdown |
| A | `docs/adr/0022-receiver-verified-notes-role-admission.md` | Markdown |
| A | `docs/adr/0023-configurable-finite-notes-resource-budgets.md` | Markdown |
| A | `docs/adr/0024-actual-notes-resource-work-accounting.md` | Markdown |
| A | `docs/adr/0025-cumulative-request-budgets-and-scoped-blockers.md` | Markdown |
| A | `docs/adr/0026-stop-salvage-restore-merge-after-corruption.md` | Markdown |
| A | `docs/adr/0027-unauthenticated-external-capture-origin-reports.md` | Markdown |
| M | `docs/adr/README.md` | Markdown |
| M | `docs/architecture.md` | Markdown |
| A | `docs/architecture/git-core-context-transition-plan.md` | Markdown |
| M | `docs/implementation-status.md` | Markdown |
| A | `docs/integration/design-stack-main-review-2026-10-15.md` | Markdown |
| M | `docs/phase2/AGENTS.md` | Markdown |
| M | `docs/phase2/README.md` | Markdown |
| M | `docs/phase2/decision-register.md` | Markdown |
| M | `docs/phase2/documentation-status-audit.md` | Markdown |

## 7. Handoff boundary

Used `ci-final-tree-verification` for exact feature/effective-tree and test-scope evidence, `lessons-to-skills` for the correction discipline, and `skill-creator` validation for edited skills. Updated the existing workflow reference with the verified lesson that nested guides and old implementation-facing skills need applicability reconciliation even when the latest ADR/index is correct. No new standalone skill or product policy was invented.

The final PR verification section must state the actual HEAD/tree/base/counts, temporary merge/tree binding, independent final report recheck, final CI URLs/selections and any deviations. The owner evaluates that concrete evidence before separately authorizing merge and publication. **This report grants no execution permission.**
