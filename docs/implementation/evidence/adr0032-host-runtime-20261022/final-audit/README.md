# PR #133 final audit supplement

Audited at 2026-10-22T22:36:23.760837+00:00. This supplement records a new independent re-audit of the existing completed executions, not a new hosted execution. Source HEAD remains `f16e5b1713bde9a2f18263a25397c4b450fd5773`, tree `6bfa580baafa9f6a117b7a0b610c4e65cd031b86`. No source fix or source commit was necessary. The original evidence commit `14b7901c95b01b1ad2fc162f76e0210abc049a96` and every pre-existing evidence file are preserved.

The final source's environment/CI change is qualified for continued engineering development. It is not complete product/release acceptance: Access CI remains failed on inherited unfinished functionality. No PR was merged, no new PR was created, no I6 implementation was started, and PR #129–#132 were not modified.

## Results

| Scope | Final result |
| --- | --- |
| Access run 39799299209, attempt 1 | completed / failure; registry-runtime failure |
| Tests run 39799299296, attempt 1 | completed / success; offline and sqlite-policy success |
| Original hosted pytest | 2,696 passed, 59 failures, 20 setup errors, no skips; exit 1 |
| Broad hosted offline regression | 3,058 passed, 59 failures, 20 setup errors, no skips; exit 1 |
| Bounded source I4 / I5 | 217 / 29 pass; exit 0; strict selected/JUnit/journal reconciliation |
| Direct and sdist-derived wheels, each | 153 installed .py/.sql/.json hashes exactly match the pinned source; runtime/safety, I2/I3 probes, I4 217 and I5 29 pass; original Access smoke retains Transfer refusal / exit 1 |
| Policy | hosted 0 violations; 31 detector + 4 runtime tests pass. This audit reran all 35 stdlib tests and static policy successfully |
| Independent non-implementer audit | PASS; no unresolved material source finding; [report](independent-audit.md) |

Product Python is **3.12.15**, with built-in **SQLite 3.53.1**, source ID:

`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.

All eight Access runtime receipts retain the same resolved selected Python and binary SHA-256 `0a97d28d3635c7dfd143de6d00b09c0cb382249c020b28ee33fb4002db1efb9c`, compile options, built-in module and null loader overrides. Real Access/P1 safety factories and STRICT/JSON/FTS5/WAL checks pass, including both actual installed venvs. Only a complete checksum-bound Python distribution is selected. No SQLite component download, build, additional installation or replacement, version matrix, or exact-release acceptance requirement was reintroduced. Same-invocation runtime equality is receipt binding.

The stdlib policy job uses setup-python's own Python/SQLite and does not execute product acceptance. The new local tool-only check used Python 3.12.14 and its actual SQLite 3.53.1; its identity is recorded separately and is not substituted for hosted or installed-product evidence.

## Failure attribution and differences

The frozen PR #132 regression XML, historical I4 evidence and final raw JUnit agree on **79 non-success nodes; 0 added, 0 resolved**. Node IDs, phases, refusal conditions and recorded frame paths/functions/line numbers match PR #132. The groups by stage refusal are 45 call failures + 20 setup errors at `I2_TRANSFER_UNSUPPORTED`, and 14 call failures at `I2_IDENTIFICATION_WIRE_UNSUPPORTED`. Wrapping exception types are retained in JUnit: these include direct domain exceptions, SQLite stage-fence errors and subprocess/assertion wrappers.

Four packaging assertion messages differ from the frozen baseline by pytest temporary venv paths and an observed CompletedProcess repr truncation boundary. The exception type, traceback body/lines and refusal are unchanged after those narrowly specified normalizations; the full unmodified deltas are in [message-differences.json](message-differences.json). The original-versus-broad run's four temporary-path deltas are separately retained. No skip, xfail or assertion deletion was used to hide unfinished functionality.

The bounded I4/I5 fixtures deliberately remove two named I2 stage fences in disposable databases. Their successful lower-level checks do not prove end-to-end production Transfer. Both unchanged installed Access smokes still fail in `ProviderAcquisition._preflight_units` at the Transfer fence. Access ledger reconciliation correctly fails closed on failed/error nodes. No final acceptance JSON is fabricated. The intermediate d0 bootstrap-fixture failure and its f16 fixture-only correction remain documented in the original evidence; no additional source change was made by this audit.

## Distribution identity and offline checks

Direct wheel and sdist-derived wheel SHA-256 are both `22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842` (762,725 bytes each). Source sdist SHA-256 is `ad39dce879527cab459a6b23789c03f21190fab688a44e888de2c2bb05ab10df` (83,939,983 bytes). These are the I5 installed-lane artifacts; the original standalone Access verifier is an additional lane and retains its own original result.

The two separate venvs install from local artifact URIs with `--offline --no-index --no-deps --require-hashes` and verified locked wheelhouse dependencies. Imports and real factories resolve inside each venv's site-packages. All 153 installed source/DDL/JSON file hashes match both each other and the fixed source tree. The environment's selected Python supplies both venvs' actual SQLite. Network guards and original outside-checkout origin/schema checks remain. Artifact binary hashes are existing build/install receipts; this re-audit did not download the original wheel/sdist binaries again or claim a new installation run.

## Evidence verification and remaining scope

Fresh GitHub connector job logs were obtained for all three jobs. CLI direct blob redirects returned HTTP 403; the supported connector succeeded. Access and tests receipts decoded from the fresh logs equal the published receipts byte-for-byte. The Access receipt SHA-256 is `511732209c4fda5c84a61b470ea4f56f271a6bbcb3c5e1842680dd0c6c1ff4b6`; tests receipt SHA-256 is `36eddda2b07aa7a70e1022849e3b02526ec8ffb5b1ddc8faf0c5d4437ba38add`. All 150 indexed outer payload members and all three inner receipt indices verify. The independent auditor recomputed the 456 frozen input hashes in all three input sets and strict source node/journal reconciliation. [audit-results.json](audit-results.json) records the root checks; the independent report supplies independent coverage/input/journal recomputation.

The tests workflow is ordinary development mode: its pytest and packaging lanes were deliberately unselected. It passed static/lint/format, schema/capability/doctor and reconciliation checks, with `full_acceptance=false`. Access executed all substantive later lanes after failures; only setup-uv post cleanup was skipped. Additional offline cohorts were inventoried without execution.

Of 5,742 ordinary nodes, 2,570 remain unexecuted on the host. Combining the final frozen hosted execution with the existing disjoint local 289-tool cohort leaves 2,316 ordinary nodes, one live and one benchmark node unexecuted. The new 35-tool rerun overlaps prior coverage and adds no coverage credit. The mutable-input local broad trial remains excluded; the existing local unittest-subTest phase limitation remains explicit.

**I6+ judgment:** engineering development may begin with this qualified environment and explicit inherited failure baseline. General I6 relations/Collections/Exchange depend on I1–I3; its Transfer portion depends on bounded I4/I5, with production Transfer and identification wire still unfinished. I7 depends on persistent I1–I6 and retains its separate validation/recovery review. This is not full release readiness or permission to merge. New work must bind new evidence to its own final HEAD/tree; no I6 work was performed here.

Skills applied: cloud-environment-runtime, repository ci-final-tree-verification and lessons-to-skills. No new skill was needed because the verified retrieval/identity procedures already exist. The audit helper's initial whole-message assertion and action-code heuristic were corrected and independently reviewed outside the source tree; no product rerun or defect fix is implied.

## Complete step conclusions and numerical exit evidence

GitHub REST exposes job/step conclusions, not a numeric job/action process exit code. In the table, `1 (log)` is an explicit `Process completed with exit code 1` record; `0 (inferred)` means a successful workflow shell step; `—` means no numerical code is exposed or no process ran. Skipped steps are not assigned exit 0. Composite/action success and failed job conclusion must not be presented as direct numerical process measurements. Full API snapshots and [steps.json](steps.json) retain observed states.

| Run / job | Step | Conclusion | Exit code evidence |
| --- | --- | --- | --- |
| 39799299209 / registry-runtime | 1: Set up job | success | — |
| 39799299209 / registry-runtime | 2: Run actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 | success | — |
| 39799299209 / registry-runtime | 3: Run ./.github/actions/product-python | success | — |
| 39799299209 / registry-runtime | 4: Run astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 | success | — |
| 39799299209 / registry-runtime | 5: Install locked development dependencies | success | 0 (inferred) |
| 39799299209 / registry-runtime | 6: Prepare locked wheels before offline installed acceptance | success | 0 (inferred) |
| 39799299209 / registry-runtime | 7: Verify runtime and focused tests without overrides | failure | 1 (log) |
| 39799299209 / registry-runtime | 8: I4 I5 bounded and broad offline regression evidence | failure | 1 (log) |
| 39799299209 / registry-runtime | 9: Compare all 79 inherited non-successes | success | 0 (inferred) |
| 39799299209 / registry-runtime | 10: Installed I2 I3 I4 I5 on both distribution artifacts offline | failure | 1 (log) |
| 39799299209 / registry-runtime | 11: Inventory offline and unexecuted coverage | success | 0 (inferred) |
| 39799299209 / registry-runtime | 12: Verify wheel and sdist-derived wheel outside checkout | failure | 1 (log) |
| 39799299209 / registry-runtime | 13: Check isolated module ownership and baseline evidence | success | 0 (inferred) |
| 39799299209 / registry-runtime | 14: Reconcile Access acceptance ledger and exact test nodes | failure | 1 (log) |
| 39799299209 / registry-runtime | 15: Build allowlisted MkDocs sources with placeholder diagrams, no deployment | success | 0 (inferred) |
| 39799299209 / registry-runtime | 16: Check formatting of the exact committed files | success | 0 (inferred) |
| 39799299209 / registry-runtime | 17: Save exact source and locked formatter for offline reproduction | success | 0 (inferred) |
| 39799299209 / registry-runtime | 18: Audit final dependency runtime identity | success | 0 (inferred) |
| 39799299209 / registry-runtime | 19: Emit indexed verification receipts to job log | success | 0 (inferred) |
| 39799299209 / registry-runtime | 20: Save focused verification evidence | success | — |
| 39799299209 / registry-runtime | 39: Post Run astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 | skipped | — |
| 39799299209 / registry-runtime | 40: Post Run actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 | success | — |
| 39799299209 / registry-runtime | 41: Complete job | success | — |
| 39799299296 / offline | 1: Set up job | success | — |
| 39799299296 / offline | 2: Run actions/checkout@v7 | success | — |
| 39799299296 / offline | 3: Run ./.github/actions/product-python | success | — |
| 39799299296 / offline | 4: Run astral-sh/setup-uv@v10.2.0 | success | — |
| 39799299296 / offline | 5: Plan checks from changed files | success | 0 (inferred) |
| 39799299296 / offline | 6: Validate prose | success | 0 (inferred) |
| 39799299296 / offline | 7: Prepare dependencies (online preparation) | success | 0 (inferred) |
| 39799299296 / offline | 8: Confirm dependency environment identity | success | 0 (inferred) |
| 39799299296 / offline | 9: Prepare locked wheels (online preparation) | skipped | — |
| 39799299296 / offline | 10: Ruff lint and formatting | success | 0 (inferred) |
| 39799299296 / offline | 11: Inspect SQLite capabilities and doctor | success | 0 (inferred) |
| 39799299296 / offline | 12: Verify composed schema and generated guards | success | 0 (inferred) |
| 39799299296 / offline | 13: Collect selected tests before execution | skipped | — |
| 39799299296 / offline | 14: Current catalog3 checks (offline) | skipped | — |
| 39799299296 / offline | 15: Installed wheel and sdist checks (offline, isolated parallel workers) | skipped | — |
| 39799299296 / offline | 16: Reconcile selected checks and report unexecuted coverage | success | 0 (inferred) |
| 39799299296 / offline | 17: Emit bounded verification receipts to job log | success | 0 (inferred) |
| 39799299296 / offline | 18: Retain timing and selection evidence | success | — |
| 39799299296 / offline | 35: Post Run astral-sh/setup-uv@v10.2.0 | success | — |
| 39799299296 / offline | 36: Post Run actions/checkout@v7 | success | — |
| 39799299296 / offline | 37: Complete job | success | — |
| 39799299296 / sqlite-policy | 1: Set up job | success | — |
| 39799299296 / sqlite-policy | 2: Run actions/checkout@v7 | success | — |
| 39799299296 / sqlite-policy | 3: Run actions/setup-python@v7 | success | — |
| 39799299296 / sqlite-policy | 4: Check current SQLite validation policy | success | 0 (inferred) |
| 39799299296 / sqlite-policy | 5: Test policy detector against prohibited and permitted configurations | success | 0 (inferred) |
| 39799299296 / sqlite-policy | 6: Test product Python integrity and runtime binding with stdlib only | success | 0 (inferred) |
| 39799299296 / sqlite-policy | 11: Post Run actions/setup-python@v7 | success | — |
| 39799299296 / sqlite-policy | 12: Post Run actions/checkout@v7 | success | — |
| 39799299296 / sqlite-policy | 13: Complete job | success | — |

## Reproduction

Use the pinned source and original evidence worktrees, including the hosted merge Git object. This directory contains the API snapshots used by the helper. Recover `hosted-f16e5b1/access-job.log` and `hosted-f16e5b1/offline-job.log` from the original indexed payload as `access.log` and `offline.log` in a disposable input directory, and copy this directory's JSON snapshots there. Those original receipt bytes have been independently verified identical to the newly fetched logs. Do not blindly extract an archive or execute its members. Then run:

```sh
python audit.py --source /path/to/pinned-source --evidence /path/to/original-evidence --inputs /path/to/disposable-inputs
```

The helper audits raw receipt indices, bindings, JUnit/failure differences, runtime and installed file identities. It copies the already independently recomputed coverage summary; it does not replace the independent journal/input/coverage audit, launch product tests or provide full-release acceptance. Original frozen bytes and new publication remain distinct.
