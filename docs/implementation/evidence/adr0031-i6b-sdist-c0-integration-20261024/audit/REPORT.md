# Task B supporting audit

Read-only Author integration support; no independent acceptance, product execution or Release claim. Audited integration HEAD `fb5d7b5a0c4b92c8a282daac154e66fa6d361e64`, tree `d2010275a90ae6b6cb728344d5708057a79110cd`. Input HEAD/tree pairs and every original/final shared-file blob are in `topology-overlap.json` and `provenance-results.json`.

## Exact topology

- 154: `91827360c185cbf813277bf32a6627d894b1b20a`, tree `4db21ecf4267f1f31023fd63ac6de7ebd8d93d3c`.
- 147: `e7762952e18061de8c8235beaeddf42f20ad9f5a`, tree `9c220c6606703aa36606896eb52d0a8966914a36`.
- 144: `ededcd83eb2d99a602ba18c8fe3c177125c825ac`, tree `2c721a0e8a58ebe8d1f795da821ea4e317b73e7e`.
- All three pairwise merge bases: `f16e5b1713bde9a2f18263a25397c4b450fd5773`.
- Live main: `cb532242c7aa86c6af5b6232b71c0906ea38f5c5`, tree `318ad07874ab436206e6a61f231b308a421cfc54`; each input/main merge-base `d92377599a50f192f534836fc12402a5fe87ca83`.

Exactly six shared paths, all 154–144; C0 shares none. Final blobs:

| Path | Effective Git blob |
|---|---|
| `.agents/skills/ci-final-tree-verification/SKILL.md` | `f40f5d481d2792993f9960d715c5df53282874a2` |
| `.github/workflows/access-registry.yml` | `e3dea46eca394211418458f8fc9ea82c8256e183` |
| `scripts/verify_access_distribution.py` | `f40dd64e475dd69f0042f23efb986316491f3d3b` |
| `scripts/verify_i4_distribution.py` | `c57585929278e02005bdce4f4a6fca54d15dd33e` |
| `scripts/verify_i5_distribution.py` | `4d1260da4507522f30ce2a191f0bc6d040b78a3f` |
| `tests/packaging/test_p1_distribution.py` | `8eb6ebbccd3f4ae46f01bdd21c06b0195ddd58d5` |

## Retained contracts

`src` equals all 160 product blobs from154. All31 numbered ADR files from154 and the ADR0033 addition from144 retain exact blobs. Every historical evidence file from each input is retained unchanged: 7,625/2,797/2,711 respectively (overlapping, never summed). `protected-inputs.json` records individual ADR blobs and complete evidence-set checks. The source equality preserves exact Transfer-fence SQL; behavior still requires actual tests.

The skill retains both installed-harness/authority/lease/subtest lessons and bounded sdist lessons. P1 packaging retains `stage_support` plus `check_sdist`/`compare_wheels`/`save`, with validation before extraction and complete-wheel/metadata/RECORD comparison. All three distribution verifiers retain sdist checks and explicit independent installed authority/import binding; original smoke and nonzero propagation remain. Access workflow retains both series' selection paths, frozen runtime, actual pytest exit propagation and `always()` receipt/upload. The gate/planner/executor/dependency-policy equal144; C0 emitter/tests equal147.

Exact executable regression recommendations for all six paths appear in `CONTRACTS-AND-HANDOFF.md`. Run real P1 packaging, installed-harness, sdist hardening/contract, CI planner/emitter tests and all three distribution drivers; report original Access refusal honestly. This subaudit executed no product tests.

## Re-executed routing audit

Actual clean-tree `ci_plan.make_plan` runs exited0. Development selects static+smoke+sdist preparation, **0 runtime files**, **232 required/unexecuted files**. A **plan only** for Release selects all232 (222+10 packaging), excluded0; no Release execution/dispatch. Acceptance input hash `106d274117017ca99caafb07b20c36eed6a9995dfa752f6bebfcfbe047618a67`. All24 final path probes exist. Direct Access filters still omit new I6 admission/wire/dependency modules and I6-A/B tests; existing Exchange/shared-helper paths match. Both upload steps retain `always()`. No CI contract violation was reproduced and no CI correction is justified.

This reruns actual candidate planning and strict pattern inspection, not PR150's synthetic single-file commit probes. Preserved preparatory mistakes: two guessed nonexistent module paths corrected to actual files; a Git empty-pathspec failure corrected to `.`. Neither changed source or ran product tests. See retained initial helpers/results and the detailed report for limits.

## Future reviewed I6-C handoff

Re-freeze reviewed I6-C and rerun actual service/selection/current-policy/lease/transaction composition in application Exchange/Provider/coordinators plus domain and SQLite admission. Rerun full I6-A originals/foreign-principal/revocation/second-INSERT/deferred-COMMIT/fence controls, v5 wire/raw-dictionary digest/strict identity/cumulative scanner-work tests, Source/Coverage/terminal/atomic-unit tests, and Access/P5/P7 composition.

Compare all299 current154 non-successes at node/phase/exception/refusal/actual frame/reached assertions, retaining historical242 I6-C/14 I7/43 Transfer-stage distinctions and separate old79 baseline. Reaching downstream assertions is not by itself resolution. Rebuild current product inventory, both independent distributions and full member/byte/metadata/RECORD/import checks, real closed-ZIP C0 boundaries, final CI routing and actual hosted receipt/tree binding. Preserve both fences and I7/I8 scope. Report missing hosted overflow/upload/download; Development is not Release acceptance.

All writes are confined to external audit evidence. No checkout/remote/source/test/ADR mutation, workflow dispatch or product acceptance was performed by this support agent.
