# Reviewer D — final P7 tests, distributions and evidence

Verdict: no outstanding Reviewer D implementation or verification defect in the tested P7 scope. Final independent functional acceptance below is bound to commit **178ddbaa8fa06f52aff4993730205c5a38da91f4**, tree **9740ad1a91f367192bb31ce9777d039c2bb4729b**. Reviewer D did not edit P7 production code or tests.

## Installed executable verification

Built a wheel and sdist from the clean frozen source; independently built a wheel from that sdist. Every one of the 124 package/runtime/resource files equals the final committed `src/repo_catalog` file byte-for-byte. Both wheels have SHA-256 **dfab687567d3b3202c1ac4de0e2d1485835eb42f3a962242c05c762b5ac2e414**, also identical to the earlier a93d870 package. The only a93d870→178ddbaa source change is the reviewed two-line audit classification of the isolated recovery budget/validation helpers. Both are imported only by already isolated P7 recovery; the correction does not hide a public-runtime caller.

Each wheel was installed normally into its own new virtual environment, outside the source checkout. Locked third-party runtime/test dependencies were installed with `uv sync --locked --offline --group dev --no-install-project --active`; the project wheel was installed with `uv pip install --offline --no-deps`. Parent and independent child interpreter probes report only site-packages runtime imports. Pytest's configured source pythonpath was explicitly disabled; installed environments' bin directories lead PATH. The source checkout supplied tests and test helpers, not the imported runtime package.

Actual final executions:

| Installed variant | Collected | Passed | Failures/errors/skips | Pytest elapsed |
|---|---:|---:|---:|---:|
| Wheel | 255 | 255 | 0 / 0 / 0 | 61.12s |
| Wheel built from sdist | 255 | 255 | 0 / 0 / 0 | 52.80s |

Both commands executed **all** `tests/integration/p7` nodes, with no selected-test exclusions. Each collected-node list exactly reconciles with 255 unique JUnit cases, 255 journal starts and 765 passed setup/call/teardown phases. Each journal completes once with exit 0. This covers the suite's process SIGKILL/resume/concurrency, genuine WAL, persistent stop, replay/Capture, bounded input, restore/activation and corruption/environment distinctions from the installed distributions. Root's broader application/legacy/schema/CLI acceptance is separate; no assertion is made here that the inherited Schema 21 fixture failures disappeared.

Full argv, cwd, exit code and elapsed time for every archive/build/install/identity/collection/test/probe command are in `commands.json`. Both full test commands use the respective installed interpreter:

```
<variant-venv>/bin/python -m pytest tests/integration/p7 -q -o pythonpath= -o junit_family=xunit1 --junitxml <variant>-junit.xml --journal <variant>-journal.jsonl
```

The external runner is retained as `run_installed_acceptance.py`; it asserts clean exact HEAD at start/end, archives that commit, hashes executable inputs, checks wheel contents, creates isolated environments, then executes the actual commands. `binding.json`, `executable-inputs.json`, `environment.json`, `node-reconciliation.json`, JUnit, journals and raw logs provide the underlying evidence. Frozen source archive and distribution bytes remain in this evidence directory; hashes identify them.

## Independent counterexample and review

A separately constructed Notes candidate changes **both** original Capture UUIDs while retaining an already bound physical copy and valid original proof bytes. In both installed variants, the receiver rejects it as inconsistent immutable evidence, reports no replay/admission, and leaves captures, roles and retained Notes counts unchanged. The original hypothesis that a retained-row presence shortcut could falsely classify this change as replay was refuted by execution. `probe_new_role_replay.py` and both `*-independent-replay.log` files preserve the concrete experiment.

Reviewed original Case 3's `Size mismatch` assertion: it updates manifest file-size/hash fields, so the observed mismatch is the native object's declared size versus retained bytes, not a stale outer file-size check. Original weak Case 10/16/23 assertions are supplemented by real P1 WAL, process writer-cut, actual P5/P6 entry-point and genuine unresolved-reference nodes. New corruption tests distinguish damaged stored authority from invalid incoming claims and budget refusal; no source mutation was used to manufacture a passing admission assertion.

Reviewed PR #87 reconciliation commit c058af3: phantom artifact files, unsafe read-only-URI preservation claim, nonempty Context assumption, full Search rebuild claim and unsupported Context-field admission claim were corrected. The parent corrected D's observed stop error-code wording and writer-gate-duration wording before committing. No accepted ADR decision was altered.

## Hosted CI identity and authority

Independently retrieved actual logs for Development run **38922059845** and strictly decoded its timestamped bounded receipt ZIP. SHA-256 **5a85672b47be48e544abe1b58c9618e77277f9a60050f7264ddd6fc123e2bd27**, 67,599 bytes; all 21 indexed archive members match their declared size/SHA-256.

Receipt binding: feature `178ddbaa8fa06f52aff4993730205c5a38da91f4`; GitHub test merge `d9fc2feb8ea6fed433a78646a51cb89cf32106a2`; tree `9740ad1a91f367192bb31ce9777d039c2bb4729b`, equal to the frozen feature tree. Actual status is **development_checks_passed**, **full_acceptance=false**, and actual runtime pytest execution count **0**. A green Development run is not hosted P7 execution. `hosted-receipt-verification.json` records the checks and actual binding.

## Limits and retained unsuccessful experiments

Environment: Python 3.12.14, SQLite 3.53.1, Linux 6.18.44 x86_64, overlay filesystem. Separate processes and SIGKILL are exercised; physical host power loss, NFS/network filesystem behavior, Windows, privileged hostile namespace mutation and production catalog recovery are not established. Root tests ran concurrently, so these elapsed times are not a benchmark comparison. All catalogs were disposable synthetic catalogs.

Before final acceptance, an exploratory a93d870 build completed but offline installation of unconstrained pytest failed because UV registry index metadata was not cached. No product tests ran in that failed bootstrap. Original argv, exit 1 and logs remain under sibling `final/`. The locked/no-project-install procedure then succeeded, and both a93d870 installed suites passed 255 before being superseded by the complete final178 reruns above. Earlier exploratory 5ed92975 source/packaging run passed 165. Initial probe bootstrap/import and incorrect-hypothesis assertion failures are retained separately; they are not P7 product failures or passing acceptance evidence.

No PR was merged, no release/tag was created, no production catalog was touched and no Pages deployment was performed by Reviewer D. PR #89's separate reviewed implementation/evidence is documented in its own branch and report.

## Broader-suite failures: separate independent diagnosis

After the installed P7 acceptance, root's broader suite exposed substantially more failures than the originally reported five. Reviewer D independently reran two exact examples on both this final P7 commit and a new clean main b86c467 worktree, each with its own correctly bound environment. Both revisions fail `test_operational_failure_retains_resumable_job` (`no such table: jobs`) and the selected GraphQL rate-limit retry node (`no such table: collection_progress`). Read-only fixture inspection confirms these tables live in Operational while the assertions query Core; the relevant test/runtime files are identical across revisions. Evidence is in sibling `schema21-counterexamples/REPORT.md` and its binding, traces, JUnit, journals and import probes.

These two failures are independently confirmed inherited stale store-routing assertions. This does not classify every broader-suite failure or establish whole-project acceptance. Do not present the full project as green, silently restrict the inherited-failure count to five, or treat the failed baseline runs as successes.
