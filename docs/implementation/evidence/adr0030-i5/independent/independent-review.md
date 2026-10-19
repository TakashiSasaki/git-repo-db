# Independent ADR 0030 I5 review

Reviewer: `/root/independent_review`, separate from production and I5 test authors. The reviewer never edited, committed or pushed the repository. Disposable probes, archived source and virtual environments are outside the reviewed checkout.

## Source and runtime

Frozen integrated product HEAD `a54cb218226e3c91c44e979ee0df0543ea459502`, tree `cc2eafaaeb8e3305270c17e74ae69edc42c0a50b`, was independently extracted using `git archive`. The review reads AGENTS, ADR index, accepted ADR 0029/0030, the Context and selective-Exchange contracts, design handoff, I1–I4 handoffs and historical independent reviews, then compares the actual implementations and boundary tests.

The final independent run uses its own locked editable environment inside that archive, Python **3.13.5**, actual SQLite **3.51.3**, source ID:

```
2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618
```

`runtime-source-binding.json` records source file SHA-256s. `session-binding.json` and `review_binding.py` assert the pytest configuration, imported product/schema paths, interpreter path and an isolated child-process import all belong to the archived source. SQLite version/source ID were queried, never replaced. Context fingerprint remains `fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`.

## Verdict

**PASS within this independent I5 implementation and verification-delta review; unresolved material findings: 0.** Reviewed final I5 HEAD `20198151a6af2f8eefa43e85074307e9d77527b7`, tree `74b164f111859c96396ca751a5c90df7e0a5f53a`, base `a54cb218226e3c91c44e979ee0df0543ea459502`. Its five-file delta contains I5 tests, helper, CI, skill and merge planning only; source/DDL, package/dependency configuration and Access acceptance ledger are unchanged (`final-delta-binding.json`). All independent executions below completed normally. The final new E2E test file SHA-256 is `af34964d3c8ea508006dca403b825486d12e2acd74c622faf837c8314a240a26`.

This is approval of the reviewed scope, not an assertion that this reviewer reran every ordinary test, the final I5 hosted job or both installed distributions. Supplementary/full-inventory execution and those separate receipts must remain explicit in the owner's acceptance record. Owner merge approval, release, P8/public activation and real data operations remain separate and unauthorized.

## Independently selected executable boundaries

The reviewer authored 30 external probes in `test_independent_boundaries.py`, using only synthetic Catalogs and genuine existing setup helpers. The completed isolated-environment execution passes **449/449** (419 existing and 30 external), with zero failure/error/skip/xfail/xpass and normal process exit zero. Breakdown: I3 66, I23 34, I4 26, P7 255, P1 Context relation guards 38, external probes 30. An additional exact-final-I5 archive run passes **20/20** new E2E tests, and four additional external backup-scope probes pass **4/4**. Thus independently completed unique pytest controls total **473**, without adding overlapping exploratory reruns. `independent-execution-reconciliation.json` independently verifies duplicate-free selected/JUnit multiset equality for each completed set. Logs: `exact-focused.log`, `final-i5-e2e.log`, `backup-scopes.log`.

- Twelve strict time controls reject bool, float, numeric string, zero, negative and overflow envelope/relation observation times before Package Binding or Core mutation, including disabled Context selection.
- Four malformed provenance controls remain invalid even when the bad unit is unselected; no false P7 Stop occurs.
- A crash immediately after Package Binding, before any domain commit, preserves the binding. A changed valid digest under the same PackageKey and a genuinely new Request is rejected; unchanged retry converges.
- Reconstructed Operational plus a new Request cannot erase or bypass a persistent P7 Stop.
- Four additional Access/configuration/approval wire sections are rejected and cannot create an Access store or domain mutation.
- Eight direct supported-SQL controls reject MappingClaim and Disposition REPLACE, UPSERT, UPDATE and DELETE with identical surviving row sets. FK and recursive-trigger prerequisites are checked. The typed time probes verify pre-affinity rejection; STRICT SQLite storage alone is not represented as proof of original caller type.

The 419 existing independently selected nodes cover I3 (including actual subprocess exits, binding races, budget/retry/empty-package controls), I23 (including real configured Access byte equality), I4, all P7, and P1 Context relation guards. Full node collection is saved in `exact-collection.log`.

Independent read-only schema build/fingerprint, schema audit, Context registration, call-site dependency, implementation-boundary, Ruff lint and Ruff format checks all exited zero against the frozen archive (`audit-results.json` and seven logs).

## Independent reconciliation of other executed receipts

The reviewer separately recomputed #111 hosted selection/JUnit counters and file bindings, without claiming to have rerun that hosted job. Run `39287566981`, artifact `12204800854`, ZIP SHA-256 `baa31d2e9e8edd34af520c5977c6cc58fb1654e2ccb00c7ff13de6352cb0134e`: **2329 unique selected = 2329 executed/passed**, no failure/error/skip. All **422** archived executable-input hashes match Git blobs at the frozen product HEAD. Actual test merge `320fe9aa955a97975affb25713b8cfe32c0a58f6` has the same effective `cc2eaf...` tree. Evidence: `reconcile_hosted_i4.py`, `hosted-i4-independent-reconciliation.json`.

The new author's local base cohort independently reconciles **2329 selected = 2329 JUnit = 2329 starts**, exactly **6987** setup/call/teardown phases, one completed finish, process exit zero and no bad JUnit cases. Its actual runtime is Python 3.13.5/SQLite 3.51.3. The midrun input capture compares all **422** inherited inputs equal to the archive, with two added I5 files outside the base cohort. This does not relabel concurrently developed I5 helper/test inputs as frozen or tested. Evidence: `reconcile_base_ci.py`, `base-ci-independent-reconciliation.json`, `base-ci-midrun-input-comparison.json`.

The reviewer independently executed the final helper collection on a clean read-only archive with its own locked dev+docs environment: **4934 all nodes, 4932 ordinary, 4933 non-live including one benchmark, 2349 focused CI**, no collection errors or duplicate nodes, and unchanged before/after inputs. The 2583 additional ordinary nodes are explicitly enumerated. Only live `tests/live/test_smoke.py::test_selected_repository` is excluded from non-live execution; it requires the prohibited real network/repository selection. `final-helper-collection/` binds this to final HEAD/tree and records empty dirty state. Collection is not execution.

The reviewer also ran **seven** external helper controls: a valid receipt accepted; missing start, missing call, duplicate call, missing finish, substituted JUnit and duplicate selection rejected. These are helper controls, separate from pytest product-node totals (`check_final_helper.py`, `final-helper-controls.json`). Final Ruff lint/format, workflow YAML parse and Git diff whitespace checks pass. The updated workflow retains inherited targets and adds I5 with two isolated xdist workers; full logs remain artifacts while only a bounded tail is printed. No skip/xfail, deleted assertion or failure suppression was introduced.

The reviewer read the final merge plan: the aggregate #111 → I5 route requires separately authorized retargeting, complete aggregate review/current checks and unchanged effective tree; the alternative #107 → #109 → #110 → #111 → I5 omits a second #108 merge and explicitly blocks on failed intermediate-stage checks. Six I3-exclusive commits are already ancestors of #110/#111. Neither route permits squashing away that ancestry or waiving failed checks. The reviewer did not independently execute any merge or retarget.

The remaining 2583-node author's supplementary execution, one benchmark, installed distributions and final I5 hosted execution remain separately attributed. No success is inferred for unexecuted nodes or an unfinished supplementary run. The review found no basis to alter historical Access ledger entries or auto-clear #15; #11's formerly seed-scoped Exchange gap is addressed by the executed cross-seed/selection/pairing controls, while full ledger reclassification requires the explicitly scoped evidence proposal in the owner's record.

## Explicit backup-scope proof

`test_backup_scopes.py` supplies four independent executable controls on final I5 source: (1) `BackupScope.GIT_ONLY` is the Core-only domain scope and creates/restores a metadata-only Core without Context; (2) paired backup with missing Context refuses before publication; (3) a physical Context-only source refuses paired backup because authoritative Core is absent; (4) a checksum-valid manifest declaring `context_only` is rejected before destination creation, without falsely stopping the sound source. The API exposes only `git_only` and `paired`; no standalone Context-only/full-domain restore is claimed.

The final I5 paired scenario independently passed with **all 19 Context tables populated**, exact columns/full primary keys/full row sets, correction/replacement Dispositions, Transfer reports, Coverage, Source membership and OID/Capture/Notes dependencies preserved. It excludes Access/Operational/Search from restoration. Existing P7 `test_consistent_backup.py::test_core_only_backup_and_restore` and all 255 P7 controls also passed in this review. Thus Core-only/Git-only, missing paired authority and Context-only refusal are distinguished explicitly.

## Static boundary conclusions

Accepted 19-table Context, six closed roles, complete direct ClaimKey/DispositionKey, no Mapping Witness and original clocks/provenance remain in place. Query and Search use current Provider-role scopes; older retained Core-target reports do not supply current ownership after a newer unresolved affiliation. Search qualifications are recomputed against authoritative Context. Paired backup/restore validates the new relation/Disposition/EventReport dependencies; Access/Operational/Search remain outside domain backup. Genuine Source membership, OID and Capture semantics remain distinct from Repository execution approval.

SQL guard conclusions assume the supported factory's FK and recursive-trigger settings. Arbitrary privileged DDL/filesystem replacement is outside the application boundary. Digest binding is checksum consistency, not authentication. Operational-only binding history cannot detect arbitrary prior ID replacement after Operational loss, and no hidden durable Witness is added to pretend otherwise.

## Preserved harness history and lessons

The first external run returned 21 passed/1 failed because the reviewer attempted arithmetic on legitimate unknown `exported_at_us=None`. It was corrected to a definite positive changed envelope time; the original log/XML is preserved under `probes-initial-harness-error.*`. Corrected subset 22 and expanded 30 runs overlap and must not be added as distinct product coverage.

A preliminary 419-node run was intentionally interrupted to strengthen subprocess isolation: PYTHONPATH pins the parent import, but the existing network fixture replaces child PYTHONPATH. A shared editable environment could therefore use the live checkout in children. The console recorded 208 passed/exit2; its JUnit includes an extra in-flight testcase and is not complete passing evidence. The final run instead uses the archive's own locked `.venv`, explicit `-c`, and parent/isolated-child import assertions. Original interrupted log/XML remain preserved. Existing `ci-final-tree-verification` and `lessons-to-skills` guidance was applied; no skill was edited by the read-only reviewer. Recommend retaining that already-documented isolation rule; the one-off nullable-time harness mistake needs no new overlapping skill.
