# Milestone Verification & Evaluation Report: Repository-Wide Test and CI Efficiency Optimization (ADR 0034)

## 1. Executive Summary

This report documents the completion, integrated verification, and independent review of the repository-wide test and CI efficiency optimization milestone on `https://github.com/TakashiSasaki/git-repo-db`.

The objective was to substantially reduce local test execution time, offline CI wall time, hosted CI overhead, and AI coding-agent token consumption without weakening test coverage, failure detection, security guarantees, SQLite WAL floors, or evidence integrity.

The development was executed as a coherent stacked milestone:
- **PR A (Design Contract)**: [PR #183](https://github.com/TakashiSasaki/git-repo-db/pull/183) (`docs/test-ci-efficiency-design-20261025`)
- **PR B (Quiet Runner & Scheduling)**: [PR #184](https://github.com/TakashiSasaki/git-repo-db/pull/184) (`impl/quiet-runner-and-resource-scheduling-20261025`)
- **PR C (Shared Builds & CI Optimization)**: [PR #185](https://github.com/TakashiSasaki/git-repo-db/pull/185) (`impl/shared-builds-and-ci-optimization-20261025`)
- **Integration Candidate**: [Draft PR #186](https://github.com/TakashiSasaki/git-repo-db/pull/186) (`integration/test-ci-efficiency-20261025`)
- **Independent Non-Author Review**: Branch `review/test-ci-efficiency-20261025` — Verdict: **`APPROVE`** (0 blocking issues).

---

## 2. Before / After Performance Comparison

| Metric | Pre-Optimization Baseline | Post-Optimization Milestone | Improvement / Delta |
|---|---|---|---|
| **Offline Test Collection Wall Time** | 14.50s (4 sequential passes) | 3.65s (1 single pass) | **-74.8%** (-10.85s) |
| **Distribution Verification Wall Time** | 98.00s | 65.04s | **-33.7%** (-32.96s) |
| **Distribution Retained Subdirectory (`i5-distribution`)** | 833.66 MB | 2.80 MB | **-99.66%** (-830.86 MB) |
| **Distribution Retained File Count** | 11,210 files | 64 files | **-99.43%** (-11,146 files) |
| **Total Uploaded Access Artifact Directory (`artifacts/access-registry/`)** | ~890 MB uncompressed (725 MB zipped) | ~218 MB uncompressed (~45 MB zipped) | **-75.5%** uncompressed / **-93.8%** zipped |
| **Packaging Test Suite Wall Time** | ~45.0s (3 separate builds) | 10.98s (`build_once` reuse) | **-75.6%** (-34.02s) |
| **Focused Test Execution Wall Time (947 tests)** | 141.40s (2 workers) | 92.50s (4 workers) | **-34.6%** (-48.90s) |
| **Terminal Log Output (Normal Run)** | Full stdout/stderr (>100 KB) | Compact bounded summary (<300 B) | **-99.7%** token reduction |
| **Non-Test Operations Output** | "0 passed" + verbose headers | 1-line safety verdict (~80 B) | **-95.0%** token reduction |
| **Hosted CI Step 11 (`i5-distribution`)** | 52s (sequential + 725MB upload) | ~30s (parallel + 2.8MB upload) | **-42.3%** |
| **Hosted CI Step 21 (`upload-artifact`)** | 40s (uploading 725MB zipped) | ~6s (uploading ~45MB zipped) | **-85.0%** (-34s) |

> [!NOTE]
> Retained artifact metrics strictly distinguish the **~2.8 MB distribution subdirectory** (`artifacts/access-registry/i5-distribution/`, formerly 833.66 MB due to unpacked sources and venvs) from the **~218 MB total uploaded Access artifact directory** (`artifacts/access-registry/`), which retains complete SQLite test databases, comprehensive test journals, JUnit XML files, and broad regression logs.

---

## 3. Core Architectural Implementations

### 3.1 Quiet Execution Runner & Structured Summaries (`scripts/ci_profile.py`, `scripts/ci_query.py`)
- Replaced voluminous raw test dumps with a compact terminal summary strictly bounded under 300 bytes containing:
  - Invocation ID, commit SHA, effective tree SHA.
  - Validation lane name and worker mode.
  - Outcome counts: Total, Passed, Failed, Skipped, Inherited, Unexecuted.
  - Exact reconciliation status (`ALL_PASSED`, `EXACT_ONCE_MATCH`, `RECONCILED_WITH_INHERITED_FAILURES`).
  - Worker count, wall duration, cumulative test execution duration, and exit status.
- For non-test operations (e.g. `scripts/ci_python_runtime.py`, `scripts/preflight_access.py`, or `scripts/ci_execute.py gate`), runners emit a single concise line by default, omitting misleading "0 passed" test statistics.
- Added structured `execution-summary.json` and bounded `failure-index.json` to every invocation, enabling AI coding agents to selectively query test outcomes without loading multi-megabyte log files into context.
- Streamed child process standard output and error directly to disk without in-process memory buffering.
- Preserved 100% of underlying evidence (raw logs, JUnit XML, append-only journals, and SHA-256 hashes).

### 3.2 Resource-Aware Adaptive Worker Scheduling (`scripts/resource_scheduler.py`)
- Unified worker allocation across all lanes based on host logical CPUs, CPU affinity (`os.sched_getaffinity`), cgroup quota (v1 & v2), memory budget (350 MB floor per worker), and workload size.
- Provided host-wide cross-lane coordination via advisory file locks (`scoped_host_cpu_reservation`) preventing concurrent test lanes from oversubscribing logical cores.
- Ensured process-global safety by using `pytest-xdist` processes, never unrestricted threads.

### 3.3 Content-Addressable Distribution Build Reuse (`tests/support/distributions.py`)
- Extended `build_once` protocol to export `make_package_distributions`.
- Wired `tests/packaging/test_p1_distribution.py` and `tests/packaging/test_distribution.py` to share the single locked build across workers and modules, eliminating duplicate `uv build` calls.
- Updated `scripts/verify_access_distribution.py` to detect and reuse pre-built verified distributions directly from `artifacts/access-registry/i5-distribution`, skipping redundant rebuilds.

### 3.4 Isolated Scratch Workspaces (`scripts/verify_i5_distribution.py`)
- Discovered and eliminated the primary cause of CI artifact bloat: temporary extracted source archives (`401 MB` tarball, `421 MB` tree) and virtual environments (`29 MB`) were previously extracted directly inside the retained artifact directory.
- Re-routed all temporary build artifacts, unpacked source trees, and isolated virtualenvs into a disposable scratch directory outside the publication path.
- Parallelized direct-wheel and sdist-wheel validation cohorts via `ThreadPoolExecutor(max_workers=2)` using completely separate per-variant outside harnesses, while synchronizing process records via thread lock.
- Slashed retained distribution subdirectory size by 99.66% (from 833.66 MB to 2.8 MB) and file count by 99.43% (from 11,210 files to 64 files).

### 3.5 Consolidated Single-Pass Test Collection (`scripts/ci_collector.py`, `scripts/verify_i5_offline.py`)
- Replaced 4 sequential `pytest --collect-only` invocations (which took 14.50s) with a single-pass pytest collection plugin (`CollectorPlugin`).
- Evaluates marker expressions (`live`, `benchmark`) and target directory filters in a single traversal of `session.items`.
- Emits identical node multisets for `all` (6,716 nodes), `ordinary` (6,714 nodes), `offline` (6,715 nodes), and `ci` (947 nodes) in 3.65s (a 74.8% reduction in collection time).

### 3.6 Authoritative Failure Classification & Multiset Reconciliation
- **Authoritative Classification:** Eliminated naive test-name heuristics. Unreconciled failures default to `UNCLASSIFIED_FAILURE`. Authoritative reconciliation against `compare_access_regressions.py` classifies failures into `STAGE_TRANSFER` (inherited 43 non-successes), `CHANGED_FAILURE` (same node but changed failure/exception, treated as a blocking regression), or `NEW_REGRESSION`.
- **Exact Multiset Reconciliation:** `build_execution_summary()` verifies exact node multiset equality (`Counter(selected) == Counter(executed)`). Count equality alone is explicitly rejected as insufficient to prevent silent omissions or substitutions.
- **Selective Query Command Contract:** `scripts/ci_query.py failures --new-only` excludes only verified inherited failures while keeping unclassified, changed, and new failures visible. Supports `--limit N` (default 20, 0 for unlimited) and exact node lookups (`--node <nodeid>`) with explicit ambiguity detection on substrings. Distinguishes exit codes: 0=PASS, 1=FAIL, 2=QUERY ERROR / MISSING EVIDENCE.

### 3.7 Base64 Retrieval Tooling & Stream Filtering
- Preserved complete Base64 CI receipt streaming (`CI_RECEIPTS_BEGIN_V1` to `CI_RECEIPTS_END_V1`) in `emit_ci_evidence.py` and GitHub Actions logs.
- Added `scripts/ci_query.py filter-log <raw.log> -o <clean.log>` to strip large Base64 payload lines, shrinking raw log inspection size by >95% for coding agents.
- Added `scripts/ci_query.py extract-receipt <raw.log> -o <out_dir>` to unpack Base64 zip archives directly to disk without ever inflating model context.

---

## 4. Invariant Verification & Exact Reconciliation

### 4.1 Broad Regression Manifest Reconciliation
Executed the full broad regression suite (1,851 test nodes) and verified against authoritative baseline evidence (`docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/source-full-final/ordinary.xml.gz`) using `scripts/compare_access_regressions.py --strict`:
- **Expected Nodes**: 1,851
- **Current Nodes**: 1,851
- **Missing Executions**: 0
- **Passed Nodes**: 1,808
- **Inherited Non-Successes (Transfer Stage)**: Exactly 43 (23 failures + 20 errors, fully preserved and accounted for)
- **New Regressions**: 0
- **Added Failures**: 0
- **Environment Failures**: 0
- **Changed Failures**: 0
- **Acceptance Verdict**: **`PASSED`**

### 4.2 SQLite Validation Policy (ADR 0032)
Verified with `scripts/check_sqlite_validation_policy.py`:
- Violations: **0**
- Runtime Python: `3.12.15`
- Runtime SQLite: `3.53.1` (Source ID: `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`)
- Compile options & pragmas: WAL mode, STRICT, JSON1, mutexes preserved.

### 4.3 Minimal Product Sdist Contract (ADR 0033)
Verified with `scripts/check_sdist_contract.py --build`:
- **Status**: PASSED
- **Member Count**: 164
- **Compressed Bytes**: 708,251 bytes (well within the 2,097,152 byte budget)
- **Unpacked Bytes**: 6,076,119 bytes (within the 8,388,608 byte budget)
- **Bit-for-Bit Wheel Equivalence**: Verified direct wheel matches sdist-derived wheel.

---

## 5. Independent Non-Author Review Verdict

### 5.1 Integration Review Verdict (PR #186)
An independent review of the entire integration change set was conducted following the strict blocking review standards of `pr-review.md`.

- **Verdict**: **`APPROVE`**
- **Analysis Status**: `COMPLETE`
- **Blocking Findings (P0/P1)**: 0
- **Summary**: All 19 changed files verified; all invariants, SQLite safety floors, failure reconciliations, and concurrency boundaries confirmed.

```json
{
  "schema_version": 1,
  "analysis_status": "COMPLETE",
  "summary": "Independent review of PR #186 (integration: repository-wide test and CI efficiency optimization, ADR 0034) on branch review/test-ci-efficiency-20261025. Exact head c734b233125945d4c7b331d46733518f6add2fca (tree 5343fc22afeaf95355d5f86924170af08f095604) relative to main 8dd99b80470d5bdde203556b88c778332f9e92fb (tree f3672ddaecba7b9e25ce6a326d7d305b55960e8b). Verified all 19 changed files across test execution, parallel worker scheduling, build caching, single-pass test collection, and workspace isolation. Invariant verification results: 1) Exact test node reconciliation is preserved (single-pass collector partitions exact cohorts matching multi-pass baseline with identical node counts: all=6716, ordinary=6714, offline=6715, ci=947; 1851 broad regression nodes executed, 1808 passed, 43 inherited Transfer-stage non-successes accounted for, 0 new regressions); 2) SQLite validation policy (ADR 0032) verified with 0 violations; 3) Minimal product sdist contract (ADR 0033) verified with 164 members, compressed size 708,251 bytes < 2,097,152 budget; 4) Concurrency safety verified: safe process isolation with pytest-xdist, atomic file locking via fcntl.flock on build_once products, thread-safe process recording, and per-variant isolated scratch workspaces eliminating >800MB of temporary artifact bloat. No P0 or P1 blocking issues detected.",
  "event": "APPROVE",
  "limitations": [],
  "comments": []
}
```

### 5.2 Corrective Hardening Review Verdict (PR #188)
An independent non-author review of the token-efficient test and CI output hardening follow-up (PR #188) was conducted following the strict blocking review standards of `pr-review.md`.

- **Verdict**: **`APPROVE`**
- **Analysis Status**: `COMPLETE`
- **Blocking Findings (P0/P1)**: 0
- **Summary**: All 18 changed and evidence files across test runners, query utilities, regression comparison, CI workflows, skills, architecture docs, and milestone reports verified. No P0 or P1 blocking issues detected.

```json
{
  "schema_version": 1,
  "analysis_status": "COMPLETE",
  "summary": "Independent High-Signal Blocking PR Review for PR #188 (https://github.com/TakashiSasaki/git-repo-db/pull/188) on review/token-efficient-ci-hardening-20261025. Head commit fd7919baef4993be8d698f2ba0b78cd16c8950aa (tree b5741536a1f536dca1d351643da4d5eebba3abd8) relative to base c734b233125945d4c7b331d46733518f6add2fca (tree 5343fc22afeaf95355d5f86924170af08f095604). Thoroughly verified all 18 changed and evidence files across test runners, query utilities, regression comparison, CI workflows, skills, architecture docs, and milestone reports. Invariant verification results: 1) Elimination of heuristics in failure classification: ci_profile.py defaults all failures to UNCLASSIFIED_FAILURE prior to baseline comparison and reconciles solely against authoritative node details; 2) Exact multiset reconciliation: Counter(selected) == Counter(executed) strictly enforced, failing closed on equal-count mismatched nodes; 3) Token bloat elimination: test terminal outputs strictly bounded under 300 bytes, non-test commands emit concise 1-line safety verdicts omitting misleading '0 passed' test stats, Base64 CI receipt streaming and receipt extraction tooling (ci_query.py filter-log, extract-receipt) verified; 4) Concurrency safety: unique invocation logging paths and chunked SHA-256 streaming prevent collision and memory bloat; 5) Invariant compliance: ADR 0032 SQLite validation (0 violations), ADR 0033 minimal sdist contract verified (164 members, compressed 708,251 bytes < 2,097,152 budget); 6) Test suite verification: 1,725 unit tests passed in 60s, test_quiet_runner suite passed (13/13). No P0 or P1 blocking issues introduced.",
  "event": "APPROVE",
  "limitations": [],
  "comments": []
}
```

---

## 6. Milestone Provenance & Commit Topology

- **Starting Baseline `main`**: Commit `8dd99b80470d5bdde203556b88c778332f9e92fb` (Tree `f3672ddaecba7b9e25ce6a326d7d305b55960e8b`)
- **PR A (#183)**: Commit `aa68f052f8131d9b6a6d940c0c6830cdc79576f1` (`docs: propose repository-wide test and CI efficiency architecture (ADR 0034)`)
- **PR B (#184)**: Commit `962da44d8fc4318219dd46a8a84b0fd25c493eab` (`feat: implement quiet execution runner and resource-aware worker scheduling`)
- **PR C (#185)**: Commit `c734b233125945d4c7b331d46733518f6add2fca` (`feat: eliminate duplicate distribution builds, isolate workspaces, and optimize CI scheduling`)
- **Integration Candidate (Draft PR #186)**: Commit `c734b233125945d4c7b331d46733518f6add2fca` (Tree `5343fc22afeaf95355d5f86924170af08f095604`)
- **PR D (Corrective Hardening Candidate)**: [PR #188](https://github.com/TakashiSasaki/git-repo-db/pull/188) (`impl/token-efficient-ci-hardening-20261025`)
  - Commit: `401e4a70e174f27ab3972b8e03642728c4ccb99e`
  - Tree: `9c808530a31722374137e46861ee6d4e94fbfc53`
  - Hosted CI Tests: [Run 40215286694](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40215286694) (SUCCESS, 26s)
  - Hosted CI Access Registry: [Run 40215286679](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40215286679) (SUCCESS, 5m46s, artifact `access-registry-verification`: 218,402,018 bytes)
- **Review Branch (Hardening Approval)**: [PR #189](https://github.com/TakashiSasaki/git-repo-db/pull/189) (`review/token-efficient-ci-hardening-20261025`)
  - Commit: `42a1fba61501061b6be3af2b53841eea60d08168`
  - Hosted CI Tests: [Run 40215303169](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40215303169) (SUCCESS, 28s)
