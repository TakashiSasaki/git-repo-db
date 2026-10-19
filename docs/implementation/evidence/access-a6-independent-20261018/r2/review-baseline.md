# R2 independent read-only Access review

- Reviewer: R2 independent agent; no reviewed production/test/documentation edits.
- Start: 2026-10-18 12:35:44 JST. Baseline findings checkpoint: 2026-10-18 12:41:10 JST.
- Reviewed HEAD: `f4d0d448fca5925bfbe4f8cb8345c3bd0df7de60`.
- Reviewed tree: `a7b4521fb7fa6562c8e0bf67e2766743e0b82c5b`.
- Read-only worktree: `/workspace/access-review-ro`.
- Scope: cumulative Access approval/workflow/descriptor-bound native Git code and invoked P4/P5 acquisition/accounting paths, rather than PR #102's ten changed files alone.
- Runtime for all retained JSON probes: Python 3.13 + actual SQLite 3.51.3, official source ID `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`, trusted system Git 2.52.0. One initial Git-only/in-memory-budget BOM run used Python 3.12/SQLite 3.53.1 before minimum runtime was available; it is not counted as minimum-version evidence. No SQLite database was used in that initial run.

## Confirmed findings before remediation

### R2-H01 — Medium: BOM-prefixed include/includeIf bypasses indirect-configuration rejection

- Source: `src/repo_catalog/adapters/git/access_native.py:191`, especially lines 209–212.
- Contract: local adapter explicitly rejects indirect include/includeIf and freezes the complete physical-source/configuration meaning before launching Git. Representation of stored configurations does not imply support for reading arbitrary external settings.
- Cause: the byte-regex starts at `^\s*\[`. Git permits a UTF-8 BOM at the beginning of its config file, while the regular expression does not treat the BOM as whitespace. An initial BOM-prefixed `[include]` or `[includeIf "gitdir:/**"]` escapes the rejection.
- Minimal reproduction: initialize a synthetic bare repository; replace its config with BOM + include section naming a synthetic sibling `outside.cfg` + its original config. Construct `AccessGitSource` with an opened repo descriptor, an in-memory finite budget and no-op guard. Use both unconditional and matching conditional include.
- Expected: reject `EXECUTOR_UNSUPPORTED` before launching Git and before following the external configuration.
- Observed: valid outside configuration is accepted and creates the source. An invalid outside configuration starts one Git command then raises `GIT_INPUT`. Changing only the external file after source construction leaves `_config_token()` unchanged, yet a subsequent Git command reads the changed external file and fails `GIT_INPUT`.
- Controls: identical non-BOM include/includeIf inputs reject before zero Git commands. Actual Git stderr independently names the malformed external file. No real configuration, credentials or user data were used.
- Evidence: `probe_config_bom.py`, `config-bom-initial.json`, `probe_config_bom_extended.py`, `config-bom-extended.json` (eight extended cases).
- Suggested correction: parse or explicitly account for Git's BOM before the indirect-config checks; retain the rejection and add both valid/malformed unconditional/conditional regressions. Do not disable Git's source checks or treat successful parsing as permission to follow includes.

### R2-H02 — Medium: final command preparation can outlive the cancellation/consent check

- Source: `src/repo_catalog/adapters/git/access_native.py:116` (`_verify`), lines 119–173 and `_process_options` at 232–234; bootstrap launch at 259–266. The inherited P4 `GitNotesSource._output` also obtains `_process_options` immediately before launch.
- Contract: check local approval/disablement before each newly initiated operation; document in-flight cancellation rather than admitting a new command on state observed before blocking final preparation. This is the same placement issue narrowed by A6-H01 at the application callback boundary.
- Cause: `_verify` calls the external guard first, then performs environment, path, directory, configuration and final alternate-file checks. It returns to `Popen` without checking guard again.
- Minimal reproduction: inject cancellation during the final actual `os.stat('http-alternates', dir_fd=...)` performed from `_process_options`. Record real `subprocess.Popen` launches and the cancellation value at launch; use a real synthetic bare repo, real Git and no input/DB substitution.
- Expected: final-preparation cancellation prevents the not-yet-launched command.
- Observed: bootstrap Git starts while cancellation is already true; its read loop later detects `CANCELLED` and kills/cleans it up. The descriptor set returns to baseline. This does not prove a global atomicity or instantaneous in-flight-cancellation guarantee; it is a deterministic placement gap before a newly launched command.
- Evidence: `probe_git_command_guard.py`, `git-command-guard.json`.
- Suggested correction: recheck the supplied guard after final potentially blocking filesystem preparation, immediately before returning process options/starting the command; retain early checks and descriptor cleanup.

### R2-H03 — Medium: cancellation during final grant transaction still admits a generic callback

- Source: `src/repo_catalog/application/access_workflow.py:290`, specifically guard at 295, potentially blocking `_grant` at 298, and only session/time rechecks at 302–304.
- Contract: the final callback boundary should reject cancellation detected during validation, just as it rejects expiry after the DB read. Existing operations already started remain a distinct boundary.
- Cause: the A6 callback wrapper rechecks the guard after executor preparation, but the final DB grant read follows it. A cancellation that occurs during that DB transaction is not checked again before invoking the user callback.
- Minimal reproduction: use a real Access DB and `LocalDirectoryExecutor`. At `_plan` inside the final handoff's real `current_grant` transaction, set the cancellation flag (asserting `store._db.in_transaction` is true). Dispatch through each public API with a guard that raises `CANCELLED` whenever that flag is set.
- Expected: neither application callback starts; cancellation is rejected, activation consumed and executor released.
- Observed: both descriptor-only and reviewed-plan callbacks start, returning normally despite cancellation already true before the grant call returns.
- Scope qualification: this directly affects generic `AccessWorkflow` dispatch. `AccessGitAcquisition` has additional callback/source guards and checks catalog cancellation after its own grant read, so this reproduction does not show native Git input after that cancellation.
- Evidence: `probe_handoff_db_cancel.py`, `handoff-db-cancel.json` (two cases on actual SQLite 3.51.3).
- Suggested correction: recheck the external guard after final grant validation and before callback admission, while keeping lifetime/session and exact-grant checks.

## Independently verified existing A6-H01 correction

`probe_handoff_independent.py` uses a new setup, the real local executor and an OS-evidence checkpoint; it imports no repository test fixture and replaces neither `bound.invoke` nor `bound.evidence`. A helper thread opens a genuinely separate SQLite handle for committed revocation/new-latest registration changes. Expiry and cancellation are synchronized at the same final OS checkpoint. Each of the two public dispatch APIs is exercised with four changes.

- A5 parent module extracted unchanged from commit `444dcecf38f5db3cccdb4716c7c8c6b584543475`: all eight cases reproduce callback admission after expiry/revocation/new default/cancellation.
- Reviewed A6 HEAD: all eight cases reject before callback (`EXPIRED`, `APPROVAL_REQUIRED`, `DISABLED`, `CANCELLED`). Each bound executor and both held descriptors close; every activation re-use is `TOKEN`.
- Evidence: `a5_access_workflow.py`, `probe_handoff_independent.py`, `handoff-independent.json`. Parent extraction is evidence outside checkout, not a modification of reviewed source or a source-overlay installation claim.
- This confirms the specific final-executor-preparation correction. It does not convert R2-H03's later DB-validation gap into PASS.

## Static confirmations and limits

Read repository `AGENTS.md`, ADR index/policy, relevant three-store/CI/lessons-to-skills guidance and Access-specific expiry/final-handoff/native-acquisition references; Access design/A1 contract and A1a/A1b/A2a/A4/A6 reports; ADR 0025/0026/0028/0029 clauses relevant to execution. Reviewed Access selection/approval/invalidation flow, local directory executor, native request intent, Access acquisition, descriptor-bound Git source, invoked native/Notes subprocess/accounting paths and regression assertions.

No additional defect was confirmed in the static reading of exact activation ownership/single-use/expiry, source-path/descriptor identity, original request/plan and physical-source freeze, additional-target versus physical-seed pairing, accumulated work charging or the completion guard. Existing tests cover revocation/configuration replacement after bootstrap, source replacement before resume, Operational loss, real P7 stop and retained committed prefixes. Reading those assertions is not a claim to have independently executed them; root owns the serialized full-cohort execution and receipts.

The scripts use synthetic temporary owned local repositories/Access DBs, finite in-memory budgets where no durable budget is under test, real system Git and no network operations. These probes do not run through pytest's fixture setup, are reported separately from root's pytest node counts, and did not alter or disable the repository network guard. No real data, backups, credentials, deployment, runtime activation, release, merge or push was performed by R2.

Unexecuted by R2 at this checkpoint: full Access/P4/P5/P7 pytest suites; PTY interaction; durable-budget interruption/finite-increase or cross-process source replacement experiments beyond the selected probes; real power loss or hostile privileged filesystem replacement; remote/container execution (not implemented); installed wheel/sdist verification; hosted CI; whole ADR replacement approval. These remain root/other-reviewer evidence or explicitly outside scope, not R2 PASS.

## Reusable lesson recommendation

Update the existing final-executor-handoff/native-acquisition skill references after the fix is verified: recheck external guard as well as deadline after every potentially blocking final validation stage (filesystem preparation and grant DB transaction); test actual transition points rather than only the original fixture. Add Git BOM-aware indirect-config rejection and the conditional-include control to the native-acquisition guidance. A read-only reviewer recommends these changes; the root implementer owns the authorized skill edit and validation.

## Reproduction commands

Run from the frozen worktree with the verified minimum runtime (adapt absolute paths to the environment):

```sh
LD_LIBRARY_PATH=/workspace/access-review-sqlite PYTHONDONTWRITEBYTECODE=1 /workspace/access-review-ro/.venv-minimum/bin/python /workspace/access-review-evidence/r2/probe_handoff_independent.py /workspace/access-review-evidence/r2/a5_access_workflow.py
LD_LIBRARY_PATH=/workspace/access-review-sqlite PYTHONDONTWRITEBYTECODE=1 /workspace/access-review-ro/.venv-minimum/bin/python /workspace/access-review-evidence/r2/probe_config_bom_extended.py
LD_LIBRARY_PATH=/workspace/access-review-sqlite PYTHONDONTWRITEBYTECODE=1 /workspace/access-review-ro/.venv-minimum/bin/python /workspace/access-review-evidence/r2/probe_git_command_guard.py
LD_LIBRARY_PATH=/workspace/access-review-sqlite PYTHONDONTWRITEBYTECODE=1 /workspace/access-review-ro/.venv-minimum/bin/python /workspace/access-review-evidence/r2/probe_handoff_db_cancel.py
```
