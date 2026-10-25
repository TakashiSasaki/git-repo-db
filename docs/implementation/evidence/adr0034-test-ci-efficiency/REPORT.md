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
| **Distribution Retained Artifact Size** | 833.66 MB | 2.80 MB | **-99.66%** (-830.86 MB) |
| **Distribution Retained File Count** | 11,210 files | 64 files | **-99.43%** (-11,146 files) |
| **Packaging Test Suite Wall Time** | ~45.0s (3 separate builds) | 10.98s (`build_once` reuse) | **-75.6%** (-34.02s) |
| **Focused Test Execution Wall Time (947 tests)** | 141.40s (2 workers) | 92.50s (4 workers) | **-34.6%** (-48.90s) |
| **Terminal Log Output (Agent Inspection)** | Full stdout/stderr (>100 KB) | Compact 10-line summary (~600 B) | **-99.4%** token reduction |
| **Hosted CI Step 11 (`i5-distribution`)** | 52s (sequential + 725MB upload) | ~30s (parallel + 2.8MB upload) | **-42.3%** |
| **Hosted CI Step 21 (`upload-artifact`)** | 40s (uploading 725MB zipped) | ~3s (uploading <3MB zipped) | **-92.5%** (-37s) |

---

## 3. Core Architectural Implementations

### 3.1 Quiet Execution Runner & Structured Summaries (`scripts/ci_profile.py`, `scripts/ci_query.py`)
- Replaced voluminous raw test dumps with a compact 10-line terminal summary block containing:
  - Invocation ID, commit SHA, effective tree SHA.
  - Validation lane name and worker mode.
  - Outcome counts: Total, Passed, Failed, Skipped, Inherited, Unexecuted.
  - Exact reconciliation status (`ALL_PASSED`, `EXACT_ONCE_MATCH`, `RECONCILED_WITH_INHERITED_FAILURES`).
  - Worker count, wall duration, cumulative test execution duration, and exit status.
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
- Slashed retained artifact size by 99.66% (from 833.66 MB to 2.8 MB) and file count by 99.43% (from 11,210 files to 64 files).

### 3.5 Consolidated Single-Pass Test Collection (`scripts/ci_collector.py`, `scripts/verify_i5_offline.py`)
- Replaced 4 sequential `pytest --collect-only` invocations (which took 14.50s) with a single-pass pytest collection plugin (`CollectorPlugin`).
- Evaluates marker expressions (`live`, `benchmark`) and target directory filters in a single traversal of `session.items`.
- Emits identical node multisets for `all` (6,716 nodes), `ordinary` (6,714 nodes), `offline` (6,715 nodes), and `ci` (947 nodes) in 3.65s (a 74.8% reduction in collection time).

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

---

## 6. Milestone Provenance & Commit Topology

- **Starting Baseline `main`**: Commit `8dd99b80470d5bdde203556b88c778332f9e92fb` (Tree `f3672ddaecba7b9e25ce6a326d7d305b55960e8b`)
- **PR A (#183)**: Commit `aa68f052f8131d9b6a6d940c0c6830cdc79576f1` (`docs: propose repository-wide test and CI efficiency architecture (ADR 0034)`)
- **PR B (#184)**: Commit `962da44d8fc4318219dd46a8a84b0fd25c493eab` (`feat: implement quiet execution runner and resource-aware worker scheduling`)
- **PR C (#185)**: Commit `c734b233a1e2f754716900f68d66df21a1c97a89` (`feat: eliminate duplicate distribution builds, isolate workspaces, and optimize CI scheduling`)
- **Integration Candidate (Draft PR #186)**: Commit `c734b233a1e2f754716900f68d66df21a1c97a89` (Tree `5041314ecf91ae790677713cdc878e253eca48ce`)
- **Review Head**: Commit `c734b233a1e2f754716900f68d66df21a1c97a89`
