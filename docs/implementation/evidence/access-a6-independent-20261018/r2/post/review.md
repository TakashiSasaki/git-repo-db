# R2 independent post-fix review

R2 independently confirms closure of R2-H01, R2-H02 and R2-H03 on the root-authored correction below. No material residual defect was reproduced in the reviewed approval/executor/Git scope. This is a bounded implementation review, not whole-ADR approval, merge permission, release qualification or an assertion of instantaneous cross-process revocation.

- Actual start: 2026-10-18 12:51:15 JST. Actual finish is recorded in `environment.json`.
- Correction HEAD: `f81a3992ac85542e015cb8f37a5ae9fc31f265b5`.
- Correction tree: `666dfaaa38dbe1f8163d5d196253b0715d98a78e`.
- Read-only detached worktree: `/workspace/access-review-post`; clean when reviewed.
- Python: `/workspace/access-review-post/.venv/bin/python`, CPython 3.13.5.
- Actual imported package: `/workspace/access-review-post/src/repo_catalog/__init__.py`; individual relevant module paths are recorded in `environment.json`.
- Actual loaded SQLite: 3.51.3, source ID `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
- Independence: root implemented the correction; R2 authored baseline reproducers and this post-fix review. R2 changed no file in the reviewed worktree and ran no heavy pytest suite.

## Defect closure and independent positive controls

| Finding or control | Corrected source | Actual independent result |
| --- | --- | --- |
| R2-H01 indirect config | `src/repo_catalog/adapters/git/access_native.py:213` | All eight BOM/non-BOM × include/includeIf × valid/malformed synthetic outside-config cases reject `EXECUTOR_UNSUPPORTED` before any Git command or source-identity binding. |
| Safe BOM positive | Same lexical inspection | Ordinary BOM-prefixed safe configs remain usable in real SHA-1 and SHA-256 repositories. Bootstrap and streamed refs work; original bytes and bound config token remain unchanged; descriptors return to baseline. |
| R2-H02 final Git preparation | `src/repo_catalog/adapters/git/access_native.py:174` | Cancellation injected at the last real `http-alternates` stat prevents the bootstrap `Popen` entirely. Additional independent SHA-1/SHA-256 streamed-ref cases likewise launch zero commands, raise `CANCELLED` and release descriptors. |
| R2-H03 final grant transaction | `src/repo_catalog/application/access_workflow.py:302` | Cancellation while the real final grant transaction is active prevents both public dispatch callbacks. Both return `CANCELLED`, consume the token (`TOKEN` on replay) and close the bound executor and both actual held FDs. |
| Original A6-H01 | Final executor OS checkpoint | The independently authored eight corrected-tree controls still refuse callback admission for expiry/revocation/new latest registration/cancellation across both APIs. Tokens remain single-use and actual FDs close. The unchanged A5-parent module still starts callbacks in all eight negative controls, establishing that the reproducer exercises the original defect rather than merely succeeding during setup. |

The retained post-fix JSON covers 23 scenarios on the corrected tree plus eight unchanged A5 control scenarios. `audit_probe_results.py` verifies each expected semantic outcome and reports PASS in `verification-summary.json`. These are independent probe scenarios, not additional pytest nodes or hosted/installed-distribution test counts. All probe processes completed successfully; no failed or timed-out post-fix probe is omitted. The original pre-fix reports/results remain separate and unchanged.

## Static review of the complete changes in R2 scope

Read the full correction diff for `application/access_workflow.py`, `adapters/git/access_native.py`, `application/acquisition.py`, `domain/native_acquisition.py`, the new `tests/integration/access/test_review_corrections.py`, and all changed skill references. Also inspected the root integration report's treatment of baseline results, remaining Exchange contract and approval gates.

The BOM correction removes one initial UTF-8 BOM only from the in-memory lexical inspection value; it does not rewrite the source file, config token or source identity. The early guards remain, and a final guard follows filesystem validation. The callback's new guard follows the real grant read, followed by session and deadline checks. Cleanup remains in `finally`; no DB transaction spans the application callback or external Git work. The changes narrow demonstrated admission gaps and do not claim a global lock across filesystem, Access and catalog state.

The new regression assertions check behavior: zero Git starts for both include classes and command boundaries, safe-BOM acceptance, no callback starts, token consumption and descriptor cleanup. The callback regression uses a counted fourth `_plan` call to identify the final DB transaction and asserts all four calls were inside transactions. That is an implementation-sensitive checkpoint but it cannot silently claim the earlier-read case passed: the call-count/transaction assertion fails if the assumed path changes. R2's separate stack-detected final-transaction reproducer avoids that specific counter dependency and confirms the result independently.

The additional metadata changes were reviewed statically for R2's original-request/budget and physical-pairing concerns. They retain physical Core/Operational seed+instance checks, distinguish a selected target Repository UUID, freeze a bounded semantic input without body staging, and check selected ownership for repository/observation/Notes/Coverage coordinates. Global OIDs retain independent meaning; a new explicit request can add compatible same-Capture facts. R2 did not independently execute the broad metadata matrix; R3/root own its runtime evidence. The existing Exchange mismatch guard remains and is explicitly documented as a still-incomplete repository-set contract.

The updated existing skills preserve the tested lesson: check the guard as well as the clock after final blocking validation, exercise callback and Git-command boundaries, and account for Git's actual BOM grammar while preserving original bytes. They retain the absence of a global instantaneous-revocation guarantee and do not invent execution permissions. Minimum-SQLite guidance correctly distinguishes an embedded newer binding from the actual dynamically loaded minimum.

## Execution and remaining limits

Commands were run from `/workspace/access-review-post` with `LD_LIBRARY_PATH=/workspace/access-review-sqlite PYTHONDONTWRITEBYTECODE=1 .venv/bin/python`:

- Baseline-authored `probe_handoff_independent.py` with the unchanged extracted A5 module.
- Baseline-authored `probe_config_bom_extended.py` and `probe_git_command_guard.py`.
- `post/probe_handoff_db_cancel_cleanup.py`, extending R2's original DB-cancellation reproducer with replay and actual-FD assertions.
- Independently authored `post/probe_positive_and_streamed.py` for safe-BOM and streamed-command controls in both object formats.
- `post/audit_probe_results.py` to check the retained outcomes.

Synthetic temporary local repositories/configuration/Access databases only. No real catalog, backup, credentials, network transport, deployment, default-runtime/P8 activation, Git push or merge was performed. No network guard was removed or altered. These plain-Python probes are separately identified from pytest fixture execution and are not called installed-distribution tests.

Unexecuted by R2 after this fix: the workflow's complete pytest node set, hosted CI, installed wheel/sdist validation, PTY interaction, broad durable-budget interruption/source-replacement/P7 recovery matrix, real hardware power loss or adversarial privileged filesystem races. Root and other reviewers provide separate evidence for their executed portions. Remote/HTTPS/SSH/container execution is not implemented by this adapter. Whole ADR replacement acceptance and merge/release authorization remain separate human gates.
