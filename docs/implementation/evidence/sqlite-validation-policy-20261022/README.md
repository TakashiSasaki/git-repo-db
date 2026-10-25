# ADR 0032 implementation validation — 2026-10-22

Development evidence for the SQLite validation policy stack: #130 → [PR A #131](https://github.com/TakashiSasaki/git-repo-db/pull/131) → dependent CI/tooling PR B. No PR was merged. [ADR 0032](../../../adr/0032-environment-sqlite-validation.md) records the already accepted owner decision. Product compatibility, DDL and assertions remain unchanged.

## Execution bindings and outcome

- Broad I5 verification executed clean commit `3594f475731554d3b836f261fce869bc29bff414`.
- Distribution, final focused tests and offline inventory executed clean code commit `cb9dee62077a25560f8ac03cc39c3ca5f97e2cfc`, tree `cb725bb06c0bf3a4ccea9f4f3c2aba51d0c5bd08`.
- Those commits differ only in the policy checker and its regression tests (the additional test detects the exact original V1 instruction). Product code, verification tools and workflow inputs are identical between them. Each execution retains its own binding; the later evidence publication is **not** a new execution or distribution build at its publication HEAD.
- All executions used Python **3.12.14**, actual SQLite **3.53.1**, source ID `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`. Both artifact venvs derive from the selected Python and report the same library. No SQLite download, compilation, additional installation or library substitution occurred.

| Check | Result |
| --- | --- |
| Final changed-tool and existing CI focused tests | 285 passed; 57 subtests passed; exit 0 |
| Standalone stdlib policy tests | 31 passed; current policy violations 0 |
| Whole-tree Ruff check and format | Passed |
| Bounded I5 / I4, separately reconciled | 29 / 217 passed; no skips/xfails |
| Broad selected regression | 3,058 passed, 59 failed, 20 setup errors; exit **1** |
| Comparison with explicit historical I4 XML | Same 79 non-success nodes, phases, stage refusals and trace paths/functions; **0 added, 0 resolved** |
| Direct wheel and sdist-derived wheel | Each: I5 29 and I4 217 passed; I2/I3 probes passed; installed origins/file hashes verified |
| Original Access smoke, both artifact variants | Both fail at inherited `I2_TRANSFER_UNSUPPORTED`; distribution orchestrator exit **1** |
| Offline collection inventory | 5,740 all / 5,738 ordinary / 5,739 offline / 2,775 Access-CI nodes; all collection exits 0; input hashes unchanged |

Broad verification selected 3,137 ordinary nodes and reconciled JUnit/journal execution exactly. The final 285 focused nodes are disjoint from that selection. Of the final 5,738 ordinary nodes, **2,316 were not executed** in this task; one live and one benchmark node were also not executed. The offline helper's complete disjoint `--execute` cohorts and full release qualification were not run. Installed tests overlap bounded source tests and are not additional ordinary-suite coverage. No skips/xfails, removed assertions or guard bypass earn success.

A profiling attempt via the existing `ci_profile.py profile` wrapper failed **before collection** because `--journal` was registered twice (explicit plugin plus the unchanged root conftest). Its failed profile/log are preserved. The equivalent direct pytest invocation passed all 285 selected tests. This wrapper defect was not caused or repaired by the SQLite policy change; only its runtime metadata recording changed.

## Changes and preserved obligations

Access CI no longer provisions a test SQLite or asserts a release/source ID. Both dependency sync operations and subsequent uv invocations retain the action-selected Python. Runtime identity is written before the unchanged product refusal. Existing collection, pytest exit propagation, both distribution variants, ledger/node reconciliation and failure artifacts remain.

I2–I5 tools measure the environment without selecting a release. I4/I5 distributions build both artifact forms and install hash-locked dependencies offline, retain the network guard and all inherited probes, and return nonzero for failures. Failure-comparison CLIs accept one current XML and an explicitly selected historical ZIP member; a member's release-shaped name never selects the current library. Existing same-invocation plan/profile identity checks remain; local/hosted SQLite equality is not required.

Raw DDL diagnostics now probe the existing `p1_schema._open(':memory:', fresh=True)` factory after saving actual environment facts. This retains its existing minimum, JSON and PRAGMA refusal without duplicating or weakening product predicates. Product `p1_schema.py` and `access_schema.py` retain their >=3.51.3 floor for the WAL reset fix and required features; `store.py` retains the WAL predicate including recognized 3.44.6/3.50.7 backports. No product support change was made.

The lightweight `sqlite-policy` job runs without dependency preparation or full pytest. The checker scopes workflows, scripts, agent instructions and explicit live-document entry points. Frozen evidence, negative fixtures and product safety code remain outside that scope. Its bounded syntax/prose patterns supplement independent review; arbitrary dynamic programs or natural language are not proven safe. New live validation entry points must be added to `LIVE_DOCS`.

No existing frozen author/reviewer ZIP, report, receipt or prior evidence file was changed. Only current reproduction instructions in the I2 implementation document were updated. PR #129/#130 branches and commits were not rewritten. Existing I5/I4/Wire failures and the independent review's I6/I7 carryovers remain open; this task neither causes nor resolves them.

## Independent review

A separate non-author agent reviewed policy PR A and final implementation commit `cb9dee6`: **PASS**, no unresolved material findings. The review independently exercised 14 checker snippets (9 prohibited / 5 permitted), the original Access workflow (5 detections), the exact original V1 row (1 detection), 9 failure-comparison scenarios, 3 product-safety refusal paths, both workflow YAMLs and their shell blocks, and the 21 expanded CI target paths.

Detected and fixed during review: generated comma-import probes, unrelated negation masking a positive command, Japanese build wording, the original minimum/SQLite/newer ordering, and the safety-floor gap in raw diagnostic paths after exact-version gate removal. Counterexamples and unit regressions verify these fixes. Safety-negative experiments changed the existing product minimum in isolated processes while retaining the actual SQLite; they did not install or spoof another engine.

Ruleset listing returned no rulesets. Required-status-check branch-protection inspection returned HTTP 403 (`Resource not accessible by integration`); settings were not changed. If an external required check still names the retired `registry-sqlite-3513` job, the owner should review replacing that requirement with `registry-runtime`. No protection update is assumed or authorized here.

## Evidence and reproduction

[results.json](results.json) provides the machine summary. [artifact-index.json](artifact-index.json) identifies all **98** members and their SHA-256/lengths in [payload.zip](payload.zip) (1,513,089 bytes; SHA-256 `dfc126e31477e295e594f5c3ba8dd297ecb1c7fb6ca6304e58034cc80b9b1222`). The payload preserves raw logs, JUnit/journals, collections, before/after input hashes, measured runtimes, build/wheelhouse bindings, failure comparison, and the failed profiling attempt. Built source trees, venvs and wheelhouse bytes are excluded; their bindings and hashes remain.

Prepare locked dev+docs dependencies and the wheelhouse with the selected environment Python as described in [testing](../../../testing.md). Use new output directories and that interpreter, without preparing another SQLite:

```sh
python scripts/check_sqlite_validation_policy.py
python -m unittest discover -s tests/unit -p test_sqlite_validation_policy.py
python -m pytest tests/unit/test_ci_plan.py tests/unit/test_ci_profile.py tests/integration/test_ci_execution.py tests/unit/test_sqlite_validation_policy.py tests/unit/test_sqlite_verification_tools.py -q
python scripts/verify_i5.py --output /absolute/new-i5-evidence --workers 4
python scripts/compare_i5_failures.py --current /absolute/new-i5-evidence/regressions.xml --baseline-entry author-3.53.1/regressions.xml --output /absolute/new-comparison.json
python scripts/verify_i5_distribution.py --output /absolute/new-distribution-evidence
python scripts/verify_i5_offline.py --output /absolute/new-inventory
```

The broad verifier and distribution orchestrator are expected to retain their inherited nonzero outcomes. Passing bounded checks or an exact failure comparison does not establish full product, whole-ADR or release acceptance. Subsequent I6 work should start from PR B's final publication HEAD, retaining both Transfer stage fences until their owning implementation is reviewed.
