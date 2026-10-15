# Independent integration readiness: PR #71 → #70 → #72

**Current final assessment: READY FOR OWNER MERGE APPROVAL for the reviewed four-step sequence #71 → #70 → #72 → #73**, with exact heads/trees and current checks below. Explicit owner authorization of all four merge commits and resulting Pages workflows is still required. Final #73 at `06a4ccd432476af15ee942e8cfcd9fbdf42357c7` offline and Pages builds now pass. Expected final effective tree is `819178212290bc8473bbc31e4a78e95bf125ebc0`; the stop-validation final-extension section supersedes earlier #73 revisions. Original #72 alone remains CHANGES REQUIRED. The final-extension section supersedes historical pending-correction statements below.

Historical three-PR verdict: **CHANGES REQUIRED** for the three-PR sequence. #71 and #70 are individually READY FOR OWNER MERGE APPROVAL with the baseline/environment limits below. #72 has a newly independently demonstrated High integrity defect and must receive the coordinated shared-contract correction and revalidation before readiness. Clean merges and green development checks do not close that finding. No merge, auto-merge, retarget, main update, deployment, release or real-data operation was executed. This is not full release acceptance. Owner authorization must explicitly include merging these three PRs and the resulting existing Pages workflow.

## Verified remote and dependency state

Read-only GitHub queries and fetched refs on 2026-10-15:

| Ref / PR | Actual HEAD | Actual tree | State / base |
| --- | --- | --- | --- |
| main | `57de60b65c2ef29420a885b0c2102dc90e11fa75` | `20d4b5bc6137a66e026748f8aa2eef2afced18d5` | Unchanged |
| #71 | `155645c03417905fcb1a6485e916c10aef371318` | `e0ff950e755bc5b9fed18cecc83f26625434ffcc` | OPEN, CLEAN, MERGEABLE; main |
| #70 | `eb84be9b2061b026ad82b780cc95e062928f838a` | `b8f3b666a6a477d8f8bd50fb77c165a0878b0fba` | OPEN, CLEAN, MERGEABLE; main |
| #72 | `67e8be65c3061b494c2c7373e2fd151398435f62` | `1d9b73e363e5b8a2bfe252fdcb87c7571d012e37` | OPEN, CLEAN, MERGEABLE; feat/implementation-boundary-spikes |

`merge-base(main,#71)` and `merge-base(main,#70)` are current main; `merge-base(#70,#72)` is exact #70 HEAD. #71 is independent of both. #72 contains #70's original history. After simulated #71 integration, merge-base with #70 remains original main. After simulated #70 integration, merge-base with #72 remains exact #70 HEAD. No historical SHA mismatch or unexpected retarget/closure/merge was found.

GitHub temporary merge refs were fetched independently:

| PR merge ref | SHA | Effective tree |
| --- | --- | --- |
| refs/pull/71/merge | `4d93b105ba322b78fa890e53adc88647b1239687` | `e0ff950e755bc5b9fed18cecc83f26625434ffcc` |
| refs/pull/70/merge | `0e9db0f512bfd95bfd9ac9660128997346866034` | `b8f3b666a6a477d8f8bd50fb77c165a0878b0fba` |
| refs/pull/72/merge | `abfc41adbf381653adcd4f5b98efcb4014aa0145` | `1d9b73e363e5b8a2bfe252fdcb87c7571d012e37` |

Those individual PR merge trees do not include the independent #71 correction in #70/#72. They must not be substituted for the ordered final integration tree.

## Effective ordered integration

A disposable detached worktree `/workspace/preflight-effective` was created from exact main. Three real local `git merge --no-ff --no-edit` operations preserved every original commit without cherry-picking, squashing or rebasing. None was pushed.

| Step | Local simulated merge commit | Effective tree | Original feature parent |
| --- | --- | --- | --- |
| main + #71 | `cb7b12391162bc826ef36ef55d24041e1948d399` | `e0ff950e755bc5b9fed18cecc83f26625434ffcc` | `155645c03417905fcb1a6485e916c10aef371318` |
| previous + #70 | `bb86795c55142729db70d73b7b3be184793b225d` | `e3bf1f0aeb3e0f0f16c445ced9f2ef7c6896f5c9` | `eb84be9b2061b026ad82b780cc95e062928f838a` |
| previous + #72 | `759e8cd8abe2d775e9d82da0207be1a5c37b7f1b` | `aea20a9aa4ff178b54119936a121fde761bcd001` | `67e8be65c3061b494c2c7373e2fd151398435f62` |

All merges were conflict free. Actual GitHub merge commit hashes will differ because commit metadata/messages differ; their expected effective trees are exact if these heads and baseline remain unchanged. The final candidate is committed and clean, not an uncommitted synthetic combination.

## Scope, review evidence and boundaries

#71 changes one existing assertion only: the Core-only fixture must show physical absence of Operational `jobs`; it must not query it. Resource-eligibility and completion-marker assertions remain. No skip, xfail or removed test was introduced. Neither #70 nor #72 changes that test, so no test collision exists.

#70 changes 34 files: audit/prototype tests, two audit tools, implementation reports/inventories and repository skill/agent guidance. Its four commits preserve the independently reviewed source and later evidence/skill updates. Recorded independent review closed two Major and six Minor findings, including closed-parent negative knowledge and paired-backup validation order. The independent source report binds `db5775f...`, with later evidence-only binding and executable inputs described in its receipt. The large JSON inventories are intended complete schema/call-site evidence, not unexpected runtime files.

#72 changes 41 files relative to #70: isolated four-store DDL/contracts/reference adapters, tests, audits, implementation handoffs and one existing invariant skill. Recorded three-reviewer independent review contains R1–R12 and executable counterexamples, all resolved through `18bb00e`, `924fb20`, and `f56cf3f`; the last feature commit is evidence/documentation. Material corrections include tree-name slots, unknown parent positions, cross-observation contradictions, verified native negative closure, local snapshot reads, persistent corruption-stop fencing, exact Coverage ownership/latest terminals, null detach and actual retained-text search. The new independent preflight reran all 250 P1 contract tests and 128 architecture-spike regressions against the effective final tree.

There are no GitHub formal review submissions, issue comments or inline review comments on any of the three PRs. In-repository independent-review reports are evidence of task-specific reviewers; they are not invented GitHub approvals. Owner review remains required by the current task.

No file under accepted `docs/adr/` changes in the complete integration. No public CLI/application path, existing initializer/schema/resources, dependencies, workflow, docs builder, MkDocs configuration or publication allowlist changes. Every changed `src/` file is a new isolated `p1_*` module or `p1_ddl` resource. Schema 21 remains the active runtime. The existing runtime's prior test problems below are not introduced by this integration. No real catalog or backup was opened or modified.

## Hosted checks and required-check knowledge

| PR | Latest tests run | Actual boundary |
| --- | --- | --- |
| #71 | [38801923418](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38801923418), success | Static/smoke/schema checks passed; pytest collection/runtime/package steps skipped |
| #70 | [38761861468](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38761861468), success | Latest evidence/skill update: report validation; static/smoke/runtime/package steps skipped |
| #72 | [38805032414](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38805032414), success | Static/smoke/schema checks passed; pytest collection/runtime/package steps skipped |

#70 Pages [38761861630](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38761861630) and #72 Pages [38805032310](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38805032310) passed build-and-validate; deploy-to-pages was skipped. Pages build includes its documentation unit tests, but these success statuses do not claim a local browser build or full application acceptance.

The branch endpoint reports `protected:false`, protection disabled and required_status_checks enforcement off with empty contexts/checks; the repository rulesets endpoint returned `[]`. Repository settings allow merge commits (and also squash/rebase, which this integration must not use). The dedicated branch-protection endpoint returned HTTP403 Resource not accessible by integration; do not infer undisclosed settings from that endpoint alone. Reinspect settings/checks immediately before authorized execution. No `--admin` override is justified. `gh run view --log` returned empty files; following the job log API redirect returned a forbidden blob endpoint. No hosted receipt ZIP contents, acceptance hash or exact hosted test counts were fabricated from these inaccessible logs. Authoritative run/job metadata explicitly identifies runtime/package steps as skipped.

## Independent executable verification

Environment: Python **3.12.14**, SQLite **3.53.1**, Git **2.52.0**, uv **0.12.19**, pytest **9.1.1**, Ruff **0.16.10**. Dependencies prepared in a private worktree venv with `uv sync --locked --group dev`; locked wheelhouse preparation passed. No lock edits. Direct pytest was used once through conftest registration, without the known duplicate `-p scripts.ci_journal` wrapper path. This task makes no successful profiling-wrapper claim and creates no release receipt.

All exact commands, selected/executed node identities, JUnit/journal hashes and phase reconciliation are in `verification-receipt.json`. Separate `*-selected.txt` collection manifests cover effective targets and baseline targets. No missing/duplicate execution or incomplete setup/call/teardown was found.

| Invocation / category | Selected | Executed | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| unchanged main: original documented Core-only failure | 1 | 1 | 0 | 1 | 0 |
| exact #71: entire repaired schema file | 16 | 16 | 16 | 0 | 0 |
| effective: P1 contracts | 250 | 250 | 250 | 0 | 0 |
| effective: architecture spikes/audit | 128 | 128 | 128 | 0 | 0 |
| effective: isolated P1 wheel and sdist-wheel | 2 | 2 | 2 | 0 | 0 |
| effective: existing Schema 21 schema file | 16 | 16 | 16 | 0 | 0 |
| effective: extra unchanged runtime/CLI/schema visualization sample | 54 | 54 | 52 | 2 | 0 |
| effective: documentation unit tests, first attempt | 6 | 6 | 5 | 1 | 0 |
| effective: documentation unit tests, managed Chromium retry | 6 | 6 | 5 | 1 | 0 |
| unchanged main: two additional runtime failures and managed Chromium case | 3 | 3 | 0 | 3 | 0 |

The four effective P1/spike/packaging/schema categories ran together in the initial 402-node invocation (with six docs tests): 401 passed, one docs environment failure. They then ran together again as a clean focused 396-node command: **396 passed, zero failed/skipped**. Repeated invocations above must not be summed as unique coverage. The first six-test docs invocation and initial 402 invocation are the same execution, not two independent first attempts.

Known baseline: unchanged main fails `test_committed_resource_does_not_need_collection_or_operation_success` with `no such table: jobs`. Exact #71 passes all 16 tests. Two additional sampled failures were independently reproduced unchanged on main:

- `test_catalog3_git_runtime.py::test_interrupted_fixed_refs_resume_without_new_remote_observation`: Core-only Store query of Operational `cache_leases`.
- `test_catalog3_model_cli.py::test_cli_retires_http_reparse_without_mutation_or_remote_observation`: helper queries Operational `jobs` through Core-only Store.

These remain real failed tests; they were not skipped, fixed or hidden in this task. #71 repairs only its advertised case, not these additional unrelated baseline tests. Record separate follow-up test repairs if desired.

Local documentation staging first failed because Puppeteer expected unavailable chrome-headless-shell155. With `PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium`, the managed system browser rejected Mermaid's file:// navigation with `ERR_BLOCKED_BY_ADMINISTRATOR`. The latter failure was independently reproduced on unchanged main. No browser policy was bypassed. Current hosted PR Pages builds pass; full local Pages build remains unexecuted/limited by this managed-browser policy.

Checks passed at committed effective SHA/tree:

```sh
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync python scripts/build_p1_schema.py --check
uv run --no-sync python scripts/audit_p1_schema.py --check
uv run --no-sync python scripts/audit_implementation_boundary.py --check
uv run --no-sync python scripts/audit_callsite_dependencies.py --check
uv run --no-sync python scripts/schema_viz.py --check
uv run --no-sync python scripts/audit_publication_free.py > /workspace/evidence/preflight/schema-map.json
cmp /workspace/evidence/preflight/schema-map.json docs/phase2/publication-free-schema-map.json
uv run --no-sync repo-catalog --state-dir /workspace/evidence/preflight/disposable-doctor --format json doctor
```

247 Python files formatted. P1 reconciliation confirms 84 baseline tables /625 columns →46 target tables with no unclassified entries. Public schema visualization remains unchanged and fresh. Doctor confirms STRICT/FTS5 trigram/Python/SQLite/Git capabilities. One earlier doctor invocation omitted explicit state-dir and performed an uninitialized capability read only; the explicit disposable invocation above is retained, and no real catalog initialization occurred.

Not executed: full application acceptance suite; full released CLI wheel/sdist suite; live provider/network acceptance; power-loss/P7/P8 activation; full independent hosted runtime suite; complete local documentation build; any release receipt/reconciliation. Green development CI is not release acceptance.

## Pages implications

#71 changes only a test and does not match Pages push path filters. #70 and #72 change `docs/**`, so their eventual authorized merge commits to main each trigger the existing build and deploy workflow. The unchanged allowlist stages approved site pages, ADR0001/0002, architecture/schema assets and build revision metadata; it does not expose `docs/implementation/**` or new P1 DDL automatically. The published build metadata will change. Main deployments are serialized without cancel-in-progress; PR builds lack deployment permissions and deploy remains skipped. Owner authorization for the merges must acknowledge these automatic Pages publications. Do not dispatch Pages or alter its allowlist/workflow to avoid or expand these effects.

## Newly demonstrated material #72 finding

**High — reported scalar claim can be promoted to receiver-checked authority through a supported transaction callback.** Independent P2 review executed `/workspace/evidence/p2-review/promote_report.py` against exact original P1 HEAD `67e8be65c3061b494c2c7373e2fd151398435f62`, tree `1d9b73e363e5b8a2bfe252fdcb87c7571d012e37`; receipt `promote-report-p1-exact.json` records exit0 and before/after alternatives. Admit an attributed reported tree-type claim, retain matching verified native empty-tree bytes, then insert `intrinsic_claims` linking that original report through supported `AdmissionTransaction.execute`. Its original provenance remains `reported`, but its projection changes `checked:false` to `checked:true`. This violates the frozen contract that local receiver evidence is separate and matching bytes do not promote earlier reports. The prior 250 green P1 tests did not cover this path.

The coordinator is isolating one shared correction (Core DDL provenance qualification guard and corresponding fingerprints), with both consumers tested and independent review. Neither P2 nor P3 should independently create a competing fix. This reviewer did not edit shared source. Until the correction is committed, reviewed and rebound to exact heads/effective trees, #72 is CHANGES REQUIRED. Any changed integration inputs invalidate the original tree expectations below and require recalculation.

## Executable owner-authorized integration mechanics (NOT EXECUTED; BLOCKED on correction)

First close the High #72 finding with the coordinated correction, then recompute this plan against its exact reviewed dependency heads/effective trees. The current script deliberately exits while that finding is unresolved. Subsequently proceed only after explicit owner approval of #71/#70/#72 merge commits and resulting Pages workflow. Freeze concurrent main updates for this sequence. Re-fetch all refs and inspect actual bases/heads/checks. If any head/base/main differs, recompute effective trees and relevant verification instead of using these receipts blindly. A branch-protection/merge-queue change is a reason to stop and reassess; `gh pr merge` can otherwise enqueue or enable auto-merge under queue rules, which is outside this plan. No `--auto`, `--admin`, squash/rebase or branch deletion.

```sh
gh repo set-default TakashiSasaki/git-repo-db
git fetch origin main feat/implementation-boundary-spikes feat/p1-four-store-schema-contracts fix/core-only-schema-test
gh api repos/TakashiSasaki/git-repo-db/branches/main
gh api repos/TakashiSasaki/git-repo-db/rulesets
gh pr view 71 --json state,headRefOid,baseRefName,mergeable,statusCheckRollup
gh pr view 70 --json state,headRefOid,baseRefName,mergeable,statusCheckRollup
gh pr view 72 --json state,headRefOid,baseRefName,mergeable,statusCheckRollup
# Require main=57de60b..., the exact heads above, intended bases and passing current checks.
gh pr merge 71 --merge --match-head-commit 155645c03417905fcb1a6485e916c10aef371318
git fetch origin main
# Require tree=e0ff950e... and original #71 HEAD an ancestor of new main.
git merge-base --is-ancestor 155645c03417905fcb1a6485e916c10aef371318 origin/main
git rev-parse origin/main^{tree}
gh pr checks 70
gh pr merge 70 --merge --match-head-commit eb84be9b2061b026ad82b780cc95e062928f838a
git fetch origin main
# Require tree=e3bf1f0a...; original #70 and #71 both ancestors; inspect resulting tests/Pages.
git merge-base --is-ancestor eb84be9b2061b026ad82b780cc95e062928f838a origin/main
git rev-parse origin/main^{tree}
# Only after authorized #70 main integration: inspect whether GitHub auto-retargeted #72.
gh pr view 72 --json baseRefName,headRefOid,state
# If still based on feat/implementation-boundary-spikes, this related dependency retarget is required:
gh pr edit 72 --base main
# Reinspect exact head, new mergeability/checks and effective tree after retarget; wait for checks.
gh pr checks 72 --watch
gh pr merge 72 --merge --match-head-commit 67e8be65c3061b494c2c7373e2fd151398435f62
git fetch origin main
# Require tree=aea20a9a... and all original heads ancestral; inspect resulting tests/Pages.
git merge-base --is-ancestor 67e8be65c3061b494c2c7373e2fd151398435f62 origin/main
git merge-base --is-ancestor eb84be9b2061b026ad82b780cc95e062928f838a origin/main
git merge-base --is-ancestor 155645c03417905fcb1a6485e916c10aef371318 origin/main
git rev-parse origin/main^{tree}
```

The companion `integration-owner-authorized.sh` is syntax-checked plan code with explicit head/base/tree/parent/protection assertions, an authorization environment guard and an unconditional stop for the unresolved High #72 finding. It was not executed and must be regenerated after the correction; removing the stop alone is insufficient. The inline comments below denote hard assertions, not optional observations. A future executor should implement explicit equality checks or inspect and stop on mismatch before issuing the next mutation. Match-head protects feature identity; it does not lock concurrent main changes. The coordinator must revalidate actual main at every step. Merge commit parents must include each original head; descendant reachability preserves every earlier reviewed commit.

## Handoff

P2 and P3 may proceed as siblings from exact unmerged P1 HEAD67e8be65..., both targeting `feat/p1-four-store-schema-contracts`. Neither depends on #71 or the other's implementation commits. The demonstrated defect is an implementation defect, not a contradiction in accepted architecture. Owner architectural blockers remain **0**. The repeated CI evidence/browser limitations reinforce existing skills' separation of source identity, actual execution and hosted development checks. No new verified technique requires a read-only reviewer to mutate a skill; preserve existing direct-pytest/receipt guidance and report inaccessible log artifacts honestly.

## Shared-correction extension: 2026-10-15

Original #72 exact HEAD remains **CHANGES REQUIRED** on its own. The narrow coordinated correction now exists on `fix/p1-intrinsic-provenance` at commit `2e8618428bea482ececef580045066cd49552455`, tree `9f50e3be6bdf92cfc33ccb490b04a369f74e1609`, directly parented by #72 HEAD. Its separate PR/review was pending when this extension was written. The corrected **four-step integration is conditionally ready subject to independent correction review, current hosted checks, exact-tree rebinding and owner authorization of all merges plus resulting Pages publication**. No permission is implied by this conditional assessment.

Updated integration dependency/order:

```text
#71 ──► main
#70 ──► main
  └── #72 ──► main after #70
        └── shared intrinsic-provenance correction ──► main after #72
              ├── P2 production Git Core
              └── P3 production Context
```

P2 and P3 remain sibling PRs. Both initially target the **same shared correction branch**, `fix/p1-intrinsic-provenance`, rather than duplicating this correction or introducing a serial P2→P3/P3→P2 dependency. The correction is one separately reviewed common dependency on top of P1.

Narrow independent source inspection found exactly four changed files: Core DDL, its corresponding fingerprints, generated disposition evidence, and four new adversarial tests. The scalar and whole-group intrinsic guards now require provenance qualifier `receiver_intrinsic` in addition to their existing actual retained-native-byte semantic checks. An original `reported` alternative cannot gain the checked-link association merely because its value matches checked bytes. Separate genuine receiver intrinsic evidence remains admissible and exact replay remains unchanged. This enforces an existing accepted meaning; it changes no identity, table ownership, five-column Coverage schema, coordination signature, Context DDL, public initializer or accepted ADR. No ordinary-file body retention is added.

The original ordered committed candidate was extended by a real disposable local `git merge --no-ff --no-edit 2e8618428bea482ececef580045066cd49552455`, preserving all original commits:

| Step | Actual local merge SHA | Effective tree | Parents |
| --- | --- | --- | --- |
| previous #71/#70/#72 candidate + shared correction | `54ade6d2e9dab93f1fc90baa3da72a791fd299ee` | `ce5331f1eed5a5621164740e6fd74eed3707c425` | `759e8cd8abe2d775e9d82da0207be1a5c37b7f1b`, `2e8618428bea482ececef580045066cd49552455` |

The merge was conflict free. The corrected effective tree contains the independent #71 repair and exact shared correction, so it differs from the correction feature's own tree. All earlier effective trees remain valid historical evidence. The existing `verification-receipt.json` was preserved unchanged; it must not be rebound to the new worktree HEAD. New execution binding is separate in `correction-verification-receipt.json`.

Independent extension execution at corrected effective SHA/tree: **108 selected/executed/passed, 0 failed/skipped**, comprising four actual callback promotion cases (scalar/group × SHA-1/SHA-256), plus all104 existing Core/notes tests. Collection IDs, journal starts and complete setup/call/teardown phases reconcile exactly once. The four new cases assert atomic rejection, unchanged earlier report/canonical projection, no erroneous corruption stop and successful genuine receiver evidence replay. Build fingerprints, full disposition audit, Ruff lint and Ruff formatting pass (248 formatted Python files). No previous broad runtime or managed-Chromium failures were rerun, and no broader test execution is claimed by this extension.

Future owner-authorized merge sequence is **#71 → #70 → #72 → separate shared correction PR**, preserving merge commits. After #72 reaches main, retarget the correction PR from the P1 feature branch to main only if necessary, re-fetch its GitHub effective merge ref and require tree `ce5331f1eed5a5621164740e6fd74eed3707c425`, its exact reviewed head, passing checks and proper parents. The correction modifies `docs/implementation/p1-disposition.json`, so its eventual main merge also matches existing Pages workflow path filters. Owner approval must include that additional automatic Pages run. The executable plan remains deliberately stopped because the correction PR number/final reviewed head and independent review completion are not yet frozen; those must be inserted and all assertions regenerated before execution. No retarget/merge/push/deployment occurred in this read-only extension.

Owner architectural blockers remain **0**; this was a verified integrity implementation defect with a scoped correction, not an architectural contradiction.


## Final reviewed four-PR integration preflight

This section supersedes the earlier provisional correction SHA and pending-review state. The separate shared correction is now [PR #73](https://github.com/TakashiSasaki/git-repo-db/pull/73), branch `fix/p1-intrinsic-provenance`, final HEAD **`c37916edebb142459c63455c1d13e08db5ded086`**, tree **`de0ab1a4507821bc497abd9df8d6ebeb2917fd56`**, base `feat/p1-four-store-schema-contracts`. It is OPEN and MERGEABLE. Its merge-base is exact #72 HEAD `67e8be65c3061b494c2c7373e2fd151398435f62`. Original #71/#70/#72 and main were independently re-fetched/requeried and retain their original heads/bases/states recorded above. No existing history was rewritten. Main remains `57de60b65c2ef29420a885b0c2102dc90e11fa75`.

Shared independent reviews are closed. The final source includes the original intrinsic guard correction `2e861842`, baseline/isolated production audit correction `fe925cc`, and final Context extension-port/import-guard follow-up `bc6c2c18e05b0c77c0d928626f28518727318a52`. Its final commit is documentation/evidence only. Independent narrow inspection of the later audit diff confirms six explicitly named optional P2/P3 modules are excluded from the historical Schema21 lexical inventory while absolute, relative and from-import forms of those isolated modules are rejected at the public-runtime boundary. The seventh adversarial import case includes the P3 extension port. This does not hide a public runtime activation or exclude arbitrary unknown source files, change accepted ADRs, alter P1 semantic identities or create incompatible sibling interfaces. The four provenance guard tests remain unchanged and pass.

A new clean detached worktree `/workspace/preflight-final` started at original main and performed all **four** real local `--no-ff` merges in order. This produces a committed, independently verified final tree rather than an uncommitted combination:

| Step | Actual disposable merge commit | Expected effective tree | Original PR HEAD preserved as second parent |
| --- | --- | --- | --- |
| #71 | `cbd4a49288570fe191acd9081e5064f8a2a15c90` | `e0ff950e755bc5b9fed18cecc83f26625434ffcc` | `155645c03417905fcb1a6485e916c10aef371318` |
| #70 | `4c3c50024808632486060dbf1f46f47a654c8159` | `e3bf1f0aeb3e0f0f16c445ced9f2ef7c6896f5c9` | `eb84be9b2061b026ad82b780cc95e062928f838a` |
| #72 | `25416059d351c8f1583037ec3094c10eea2a7a1b` | `aea20a9aa4ff178b54119936a121fde761bcd001` | `67e8be65c3061b494c2c7373e2fd151398435f62` |
| #73 | **`a7c820f2cd7b1d5487290dc6177b3f4c2b6634a9`** | **`002c4d10874b32e6e0fbbe0fffeccc5a2450b10b`** | **`c37916edebb142459c63455c1d13e08db5ded086`** |

Every merge was conflict free, and each actual prior merge is its successor's first parent. Expected trees for the first three integrations are unchanged. The prior provisional fourth tree `ce5331f1...` is historical and must not be used for final #73. GitHub merge commit SHAs will differ; compare trees and actual parents. No existing accepted ADR, public runtime/initializer, workflow, docs builder or allowlist changes in this final effective tree. Working tree was clean.

Final independent focused execution on `a7c820f...` / `002c4d10...`: **21 selected, 21 executed, 21 passed, zero failed/skipped**: 17 disposition/audit/import-boundary tests plus four intrinsic provenance guard cases. Exact collection IDs, complete journal phases, JUnit results and artifact hashes are in `final-correction-verification-receipt.json`. The explicit command is:

```sh
PYTHONPATH=src /workspace/preflight-effective/.venv/bin/python -m pytest tests/integration/p1/test_disposition.py tests/integration/p1/test_intrinsic_provenance.py -q -o junit_family=xunit1 --junitxml=/workspace/evidence/preflight/final-correction.xml --journal=/workspace/evidence/preflight/final-correction.jsonl
```

Direct source execution used the independent preflight interpreter and local `src`, in `/workspace/preflight-final`. Call-site audit, P1 composed fingerprint check and full schema/disposition audit also pass. This final narrow extension did not repeat broad runtime, browser, 390-node dependency or production tests; their previous receipts stay bound to their original sources, including recorded baseline/environment failures. Python3.12.14/SQLite3.53.1/Git2.52.0/uv0.12.19 remain unchanged.

Final PR73 hosted checks at exact head:

- [tests run38816113218](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38816113218): completed **success**; static/smoke/schema/report checks passed; pytest collection/runtime/isolated packaging steps skipped under development policy.
- [Pages run38816113288](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38816113288): initially in progress when queried, then independently requeried **completed success**; build-and-validate passed and deploy skipped for the PR. This is not full release acceptance.

The final regenerated `integration-owner-authorized.sh` is syntax-checked and **not executed**. It has an explicit owner-authorization environment guard covering all four merges and Pages, exact initial state/head/base checks, protection/queue-change refusal, current-check waits, expected-main/merge-ref/tree/parent assertions at each step and only `gh pr merge --merge --match-head-commit` mutations. It retargets only related #72 after #70 and related #73 after #72, if necessary. Its exact merge heads are:

```sh
gh pr merge 71 -R TakashiSasaki/git-repo-db --merge --match-head-commit 155645c03417905fcb1a6485e916c10aef371318
gh pr merge 70 -R TakashiSasaki/git-repo-db --merge --match-head-commit eb84be9b2061b026ad82b780cc95e062928f838a
# Retarget #72 to main only after #70 integrates, then inspect refreshed checks/tree.
gh pr merge 72 -R TakashiSasaki/git-repo-db --merge --match-head-commit 67e8be65c3061b494c2c7373e2fd151398435f62
# Retarget #73 to main only after #72 integrates, then inspect refreshed checks/tree.
gh pr merge 73 -R TakashiSasaki/git-repo-db --merge --match-head-commit c37916edebb142459c63455c1d13e08db5ded086
```

Do not execute isolated lines without the script's assertions and separate owner authorization. Main must remain frozen against concurrent updates throughout; head matching does not lock main. Any changed main, feature head, policy, check outcome or merge tree requires a fresh preflight. A temporary UNKNOWN mergeability state after retarget is a stop/recheck condition, never justification to bypass. No auto-merge, admin override, squash/rebase, branch deletion or workflow dispatch occurs in the plan.

The additional #73 docs changes mean its eventual main merge triggers the existing Pages workflow too. Owner authorization must cover #70/#72/#73 automatic Pages publications (and all four merges); #71 alone does not match Pages path filters. The allowlist remains unchanged. P2/P3 remain siblings on the common corrected dependency branch and should consume the exact same final shared contract. Original #72 **alone** is CHANGES REQUIRED; the **reviewed four-step corrected integration is READY FOR OWNER MERGE APPROVAL**, subject to rechecking current CI and obtaining explicit authorization. All recorded final checks currently pass. Owner architectural blockers remain **0**.


## Stop-validation final extension — authoritative final #73 revision

This is the current final preflight and supersedes earlier #73 heads/trees only; every earlier test receipt remains unchanged and bound to its actual source. [PR #73](https://github.com/TakashiSasaki/git-repo-db/pull/73) final HEAD is **`06a4ccd432476af15ee942e8cfcd9fbdf42357c7`**, feature tree **`58f627ff6acc5171d8620f606e366543eb3c7d02`**. Its executable validation correction is `7ac94a9183eb18f54273fcaeb0a561b01d25048c`; the last commit records evidence and review. The separate shared independent reviews are closed.

The latest narrow correction extends `validate_pair` to distinguish failed validation of already persisted authority from rejected incoming work. Semantic CHECK-UDF exceptions, invalid stored UTF8 and authoritative storage errors translate to typed corruption failures. The persistent stop is recorded before the coordinator's gate unwinds; already active `ReadSnapshot` capabilities notify their owners immediately even if a caller catches the validation error internally. Cancellation, locking, resource exhaustion and denied capabilities do not become false corruption diagnoses. The four invalid-UTF8 provider/field × raw/pinned validation cases verify stop persistence across Operational/Search deletion; the fifth cancellation case checks that healthy authority is not falsely stopped. This tightens the accepted corruption-stop boundary without introducing quarantine, ordinary-file retention, changed identities or new authority. Context DDL, five-column Coverage, public initializer and accepted ADRs remain unchanged.

Authenticated refetch initially failed with transient missing Git credentials/GraphQL401. After the session credentials were refreshed, this reviewer successfully re-fetched exact remote heads and read current PR/check metadata via GitHub REST. No inaccessible status was inferred. All four PRs are currently OPEN/MERGEABLE/CLEAN. #71/#70/#72 remain at their original heads/bases. Main remains `57de60b65c2ef29420a885b0c2102dc90e11fa75`; #73 remains based on `feat/p1-four-store-schema-contracts`. Main protection/rulesets retain their prior unprotected/empty state. The safe future retarget commands use the supported REST PATCH endpoint because the installed `gh pr edit` path attempts obsolete projectCards GraphQL fields; this is a future authorized action only, not an executed retarget.

A fresh clean detached worktree `/workspace/preflight-stop-final` performed the complete preserved-history sequence starting from original main:

| Integration step | Actual disposable merge SHA | Expected effective tree |
| --- | --- | --- |
| #71 | `874c586e03e647a76af7d3fd30744bd20d987863` | `e0ff950e755bc5b9fed18cecc83f26625434ffcc` |
| #70 | `81aac30f78920bc549cb04c485dd0cf281348b25` | `e3bf1f0aeb3e0f0f16c445ced9f2ef7c6896f5c9` |
| #72 | `22b81cc47088f5fde293993c970f706605119ff2` | `aea20a9aa4ff178b54119936a121fde761bcd001` |
| final #73 | **`0d16aa746c444f6c8c17d3092144612b6237df90`** | **`819178212290bc8473bbc31e4a78e95bf125ebc0`** |

All four merges were conflict free. The last merge's exact parents are `22b81cc47088f5fde293993c970f706605119ff2` and **`06a4ccd432476af15ee942e8cfcd9fbdf42357c7`**. Each earlier merge likewise retains the previous integration as first parent and original PR HEAD as second parent. This commits the effective tree independently; it was never pushed or merged remotely.

Final narrow independent execution at `0d16aa74...` / `81917821...`: **26 selected, 26 executed, 26 passed, zero failed/skipped**. This comprises 17 disposition/import-boundary tests, four provenance guard cases and five persisted-validation-stop cases. Exact collected IDs, complete setup/call/teardown phases and JUnit/journal hashes are in `stop-final-correction-verification-receipt.json`. Command:

```sh
PYTHONPATH=src /workspace/preflight-effective/.venv/bin/python -m pytest tests/integration/p1/test_disposition.py tests/integration/p1/test_intrinsic_provenance.py tests/integration/p1/test_validation_stop.py -q -o junit_family=xunit1 --junitxml=/workspace/evidence/preflight/stop-final-correction.xml --journal=/workspace/evidence/preflight/stop-final-correction.jsonl
```

Call-site audit, P1 schema fingerprints and full disposition reconciliation also pass on this exact final tree. Environment versions remain Python3.12.14/SQLite3.53.1/Git2.52.0/uv0.12.19. No prior broad runtime, packaging or managed-browser failures were rerun or relabeled; the broader dependency/production verification retains its separate exact-source receipts. No accepted ADR, public runtime/initializer, workflow, docs builder or allowlist difference exists in this final effective integration.

Current hosted checks were inspected authoritatively on exact **06a4ccd**:

- [tests run38817542233](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38817542233): completed **success**; static/smoke/report/schema checks pass, runtime collection and pytest/packaging execution skipped under development policy.
- [Pages run38817542357](https://github.com/TakashiSasaki/git-repo-db/actions/runs/38817542357): completed **success**; build-and-validate and documentation unit tests pass; deploy-to-pages skipped for PR context.

The regenerated `integration-owner-authorized.sh` has been syntax-checked only. It requires explicit authorization of **all four merges plus resulting Pages** before any mutation, verifies current CI again, checks the exact final #73 head06a4ccd and final tree81917821, and uses only merge commits with match-head protection. Related #72/#73 retargets occur only after their dependencies integrate; the script uses REST PATCH for those retargets. Main must remain frozen against independent updates. The final merge command is:

```sh
gh pr merge 73 -R TakashiSasaki/git-repo-db --merge --match-head-commit 06a4ccd432476af15ee942e8cfcd9fbdf42357c7
```

Use it only within the complete gated four-step script and fresh exact-tree checks. Current checks pass, but a later owner executor must recheck them. #73's docs changes trigger Pages when it eventually reaches main, as do #70/#72; owner authorization must include those existing workflow effects. Both production siblings consume the exact same final **06a4ccd** common dependency.

**Final verdict: corrected #71 → #70 → #72 → #73 sequence READY FOR OWNER MERGE APPROVAL. Original #72 alone remains CHANGES REQUIRED.** No merges, auto-merge, main updates, remote retargets, deployments, migrations or real-data modifications were performed. Owner architectural blockers remain **0**.
