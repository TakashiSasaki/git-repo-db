# ADR 0001: Development and Release Validation Lifecycle Architecture

- **Status:** Accepted target design; implementation contract for CI and test infrastructure.
- **Decision date:** 2026-10-12.
- **Baseline:** `main` at `0c42f5fc82b8d5047c9398e9837f46159e8fd306`, tree `4d25427d73df53bb186b8a7ba83bfeb8deb7c2ef`, Catalog3 Schema 20.
- **Scope of this ADR:** Architecture, execution semantics, trust boundaries, evidence contracts, and lifecycle status definitions for local and hosted validation across ordinary development and release qualification.
- **Implementation scope of this PR:** Documentation and architectural specification. Infrastructure code implementation follows in stacked PRs.

---

## 1. Context and Problem Statement

The `git-repo-db` test suite currently contains 2,254 test cases (2,252 ordinary test cases across unit, integration, and e2e, plus 2 packaging test cases), with parallel execution taking 8–12 minutes in hosted GitHub Actions runners.

Prior CI policy attempted a "CI-first complete acceptance" model where any change touching `src/**` automatically expanded the hosted CI plan to execute the entire 2,254-test suite on every pull request push. This produced severe drawbacks:
1. **Redundant execution:** Tests thoroughly executed and verified locally were mechanically repeated in full on GitHub Actions for every minor intermediate change or stacked PR iteration.
2. **Slow feedback loop:** Development velocity slowed because intermediate documentation, skill, or focused code PRs waited for 10-minute full suite runs.
3. **Ambiguous status semantics:** A "green" hosted CI run was frequently conflated with complete release acceptance, even when only a subset of checks had run (`selected_checks_only`), or conversely, developers were forced to treat every development PR as if it were an unalterable production release candidate.
4. **Lack of granular timing and crash resilience:** Test profiling relied on post-facto JUnit XML parsing. If a run timed out, was cancelled by concurrency groups, or crashed, all intermediate timing data was lost.
5. **Trust boundary confusion:** Local validation receipts were either ignored by hosted CI or treated as unverifiable, while hosted CI results were assumed to automatically certify local developer execution.

An explicit owner decision establishes that:
- Ordinary development validation and release acceptance are distinct operations.
- Local testing is the primary mechanism for development validation.
- Unnecessary duplicate execution of locally tested cases in GitHub Actions during development must be eliminated.
- Full dual-environment acceptance (complete local pytest + complete hosted pytest + packaging) is required exclusively for an explicit, user-invoked release-validation operation.

This ADR defines the formal validation lifecycle architecture to enforce these principles.

---

## 2. Terminology and Boundary

| Term | Definition | Primary Environment | Hosted CI Behavior |
| --- | --- | --- | --- |
| **Development Validation** | Focused, dependency-aware verification of changes during editing and stacked PR iteration. | Local developer / agent workstation | Inexpensive static analysis (Ruff check/format), configuration checks, schema/doctor smoke tests, evidence inspection. No automatic full pytest run. |
| **Release Acceptance** | Complete, independent dual qualification of the software against the entire acceptance test suite and packaging requirements. | Dual: Local AND Hosted | Complete pytest suite, isolated wheel/sdist installation testing, DDL/integrity verification, exactly-once test node reconciliation. |
| **Acceptance Test Suite** | All standard test files under `tests/unit`, `tests/integration`, `tests/e2e`, and `tests/packaging` matching `test_*.py` and `*_test.py`. | Both | Collected via `pytest --collect-only -q -m "not live and not benchmark"`. |
| **Opt-in Tests** | Live network collection tests (`tests/live`, `-m live`) and specialized performance benchmarks (`-m benchmark`). | Dedicated environment | Excluded from ordinary development and release acceptance suites unless explicitly opted into with credentials. |
| **Validation Manifest** | Immutable, machine-readable summary record (`validation-manifest.json`) declaring execution identity, input hashes, selected node IDs, executed node IDs, timing, and outcome status. | Output artifact | Created upon completion of planned checks. |
| **Test Execution Journal** | Append-only event stream (`events.jsonl` or per-worker journal) recording test start, phase durations (setup, call, teardown), worker ID, and outcome as they happen. | Both | Preserved incrementally to capture partial progress even on interruption. |

---

## 3. Authoritative Architectural Decisions

### VAL-01: Two Distinct Validation Modes

The validation infrastructure must explicitly support two modes:

1. **Development Mode (`mode=development`)**:
   - The default mode for all pull requests (`pull_request`), branch pushes (`push`), and stacked PR construction.
   - **Local execution:** The developer or coding agent runs relevant focused tests during editing, expanding scope according to dependencies and actual correctness risks.
   - **Hosted CI execution:** Executes lightweight checks:
     - Policy and configuration validation.
     - Report and documentation integrity validation.
     - Static linting and formatting (`ruff check`, `ruff format --check`).
     - Schema audit and CLI doctor smoke checks (`repo-catalog doctor`).
     - Verification of supplied local test execution evidence (if present).
     - Validation gap reporting (identifying unexecuted acceptance tests).
   - **Full suite prohibition:** Development CI must NOT automatically execute the complete hosted test suite merely because source files in `src/**` changed.
   - **Status outcome:** Yields `development_checks_passed` (or `development_checks_failed`). Never yields `complete_release_passed`.

2. **Release Mode (`mode=release`)**:
   - An explicit, user-invoked operation triggered manually via `workflow_dispatch` (with `mode: release`) or an equivalent dedicated release-validation workflow.
   - Requires independent, complete execution in **both** local and hosted environments.
   - **Requirements:**
     - 100% of applicable ordinary acceptance tests executed locally.
     - 100% of applicable ordinary acceptance tests executed in hosted GitHub Actions.
     - Independent installed-wheel and sdist-derived-wheel tests executed in isolated virtual environments.
     - Complete composed schema, view, trigger, foreign-key, generated JSON, and SQLite capability audits.
     - Exact reconciliation of all selected vs executed test node IDs (exactly once, zero skips, zero failures, zero exclusions).
     - Exact input hash and tree SHA binding.
   - **Status outcome:** Yields `complete_release_passed` only when both local and hosted criteria are satisfied; otherwise `release_rejected`.
   - **Authority boundary:** An explicit release-validation operation does NOT authorize release, publication, deployment, package upload, Git tagging, or branch merging.

### VAL-02: Evidence Provenance, Trust Boundaries, and Input Identity

1. **Local Evidence Nature:**
   - A local execution receipt (`local-receipt.json`, `events.jsonl`) is developer-asserted or agent-asserted evidence.
   - It proves that an execution claimed to occur with specific parameters, but it is not independent third-party attestation.
   - Hosted CI must verify the internal consistency, schema conformance, and input binding of local receipts, but must never claim that hosted CI itself independently executed those tests.

2. **Exact Input Binding (`acceptance_input_hash`):**
   - The validation plan computes an SHA-256 fingerprint over all repository entries affecting runtime code, tests, dependencies, and validation policy:
     - `src/**`
     - `tests/**`
     - `pyproject.toml`, `uv.lock`, `.python-version`
     - `scripts/ci_*.py`, `scripts/ci_dependencies.json`, `.github/workflows/**`
   - Pure prose files (`README.md`, `AGENTS.md`, `docs/**/*.md`, `.agents/skills/**/*.md`) and designated read-only reports are classified as documentation/report inputs and excluded from `acceptance_input_hash`.
   - If `acceptance_input_hash` differs between evidence and the evaluated Git tree, all prior execution receipts are invalid for that tree.

3. **Dirty Tree Policy:**
   - Local validation executions on dirty working trees must be recorded with `tracked_changes=true` and include a digest of the uncommitted working-tree diff.
   - Dirty-tree receipts are valid for local iterative development feedback only.
   - A dirty-tree execution receipt can **never** be used as evidence for clean-tree release qualification.

4. **Lower-Stack Changes:**
   - In stacked PRs, if an upstream (lower) PR changes its head or is rebased, the effective merge tree and `acceptance_input_hash` of downstream PRs change.
   - Downstream PRs must reacquire validation against the new effective tree; historical evidence from the prior parent tree cannot be grandfathered.

### VAL-03: Validation State Machine and Status Semantics

The validation system uses distinct, mutually exclusive statuses to prevent conflation between development checks and release qualification:

```
[Trigger / Invocation]
         |
         v
    [PLANNING]
         |
         +---------------------------------------+
         |                                       |
    (Development Mode)                      (Release Mode)
         |                                       |
         v                                       v
[Lightweight Static/Smoke Checks]      [Dual Local & Hosted Full Execution]
         |                                       |
  +------+------+                         +------+------+
  |             |                         |             |
(Pass)        (Fail)                    (Pass)        (Fail)
  |             |                         |             |
  v             v                         v             v
[DEV_PASSED]  [DEV_FAILED]           [Evidence Reconciled] [RELEASE_REJECTED]
  |                                       |
  +--> [Inspect Local Evidence]          (Both Local + Hosted 100% OK?)
         |                                |             |
       +-+-+                            (Yes)          (No)
       |   |                              |             |
 (Supplied)(None/Gaps)                    v             v
       |   |                     [COMPLETE_RELEASE_   [RELEASE_REJECTED]
       v   v                          PASSED]
  [EVIDENCE_ [VALIDATION_GAP_
  VERIFIED]   REPORTED]
```

#### Status Definitions

1. `development_checks_passed`: All planned hosted development checks (lint, format, smoke, config) succeeded. Full runtime acceptance is explicitly unexecuted and unverified.
2. `development_checks_failed`: One or more hosted development checks failed (e.g. Ruff format error, syntax error, smoke test failure).
3. `local_evidence_supplied`: Machine-readable local execution receipts were provided alongside the development commit.
4. `local_evidence_verified`: Supplied local evidence matches the exact `acceptance_input_hash`, has valid node ID structures, and records zero failures for the executed subset.
5. `validation_gap_reported`: The difference between current acceptance test suite files/nodes and locally verified nodes is explicitly enumerated in the summary.
6. `hosted_release_passed`: Hosted CI executed 100% of acceptance test nodes with zero failures, zero errors, zero skips, and completed packaging isolation tests.
7. `complete_release_passed`: Both local and hosted independent executions have completed with 100% node reconciliation on the exact same clean Git tree, satisfying all release criteria.
8. `release_rejected`: Release validation was attempted but failed due to test failures, missing local receipts, node ID mismatches, runtime mismatches, or skips.

Under no circumstances may `development_checks_passed` or a green PR check badge be described as "tests passed" or "release accepted".

### VAL-04: Test Selection, Reconciliation, and Exclusion

1. **Acceptance Directories:**
   - The ordinary acceptance directories are strictly: `tests/unit`, `tests/integration`, `tests/e2e`, `tests/packaging`.
   - All files matching `test_*.py` and `*_test.py` within these directories are acceptance files.

2. **Collection Before Execution:**
   - Prior to test execution in any lane, test node IDs must be collected via `pytest --collect-only -q -m "not live and not benchmark"`.
   - Node IDs must be sorted, unique, and recorded in `selected-tests.txt`.
   - In Release mode, executed node IDs must match collected node IDs with an exact 1:1 set equality:
     $$\text{Executed} = \text{Selected}$$
     $$\text{Missing} = \emptyset, \quad \text{Extra} = \emptyset, \quad \text{Duplicates} = \emptyset$$

3. **Exclusions and Skips:**
   - Any test marked with `@pytest.mark.skip`, `@pytest.mark.skipif`, or dynamically skipped during runtime causes `acceptance_status` to fail in Release mode.
   - Skips are strictly reported as unaccepted in release mode.

### VAL-05: Per-Test and Per-Phase Timing with Crash-Tolerant Journaling

1. **Granular Timing:**
   - Timing records must distinguish:
     - `setup_duration`: Fixture setup time.
     - `call_duration`: Actual test function execution time.
     - `teardown_duration`: Fixture and test teardown time.
     - `total_duration`: Cumulative duration of all three phases.
     - `worker_id`: Identifier of the executing worker process under `pytest-xdist`.
   - Distinct from case duration, execution records must measure:
     - Collection duration.
     - Virtual environment and dependency preparation duration.
     - Command wall-clock elapsed time.

2. **Crash-Tolerant Journaling (`events.jsonl`):**
   - Timing and test outcome data must be recorded incrementally to an append-only JSON Lines file as each test phase finishes, flushed immediately to disk (`flush()`).
   - If a test process terminates abnormally (SIGINT, SIGTERM, runner timeout, uncaught worker crash):
     - All events flushed prior to the crash remain valid and inspectable.
     - The post-processing analyzer recovers the partial event journal.
     - Incomplete runs must be marked `status: interrupted` or `status: failed`; they must NEVER be converted into passing results.
   - JUnit XML remains supported as a secondary summary interchange format, but is not the sole persistence mechanism for timing.

### VAL-06: Handling Interrupted Runs and Failure Propagation

1. **Signals and Interruption:**
   - The execution wrapper must register signal handlers for `SIGINT` and `SIGTERM` where operating system support exists.
   - Upon receiving an interruption signal, the wrapper records an `interrupted` event with timestamp and wall seconds, closes open file handles, and exits with non-zero exit code.
   - Handlers must be fail-safe: if handler execution itself raises an exception, the partially written journal on disk must not be corrupted or overwritten.

2. **No False Positives on Incomplete Execution:**
   - The gating validator (`ci_execute.py gate`) must verify that the recorded profile exit code is `0`, that expected test files completed, and that no incomplete test markers exist.
   - A truncated or unfinalized journal is treated as an execution failure.

### VAL-07: Security, Privacy, and Artifact Limits

1. **No Secret or Sensitive Data in Receipts:**
   - Timing logs, receipts, manifests, and event journals must never contain authorization headers, API tokens, user passwords, or private repository URLs.
   - Standard sanitized placeholders (`[REDACTED]`, `test-provider-key`) must be used in fixtures and captured commands.

2. **Bounded Log Receipts:**
   - To prevent runner log exhaustion and truncation, in-log receipt bundles (`CI_RECEIPTS_DATA_V1`) must be bounded to a maximum compressed size of 2 MiB.
   - If compressed artifacts exceed 2 MiB, the workflow outputs an informative message directing inspection to the uploaded GitHub Actions artifact.

### VAL-08: Migration and Compatibility Disposition

1. **Deprecation of `full=true` Workflow Input:**
   - The workflow input `full: boolean` is deprecated in favor of `mode: string` with allowed values `development` (default) and `release`.
   - Backward compatibility: if `full=true` is supplied, it is translated to `mode=release`.

2. **Retirement of Historical Node ID Bounds:**
   - Fixed historical test counts (e.g. 2,252) and historical node ID lists are retired as gates.
   - The sole authoritative acceptance standard is exact collection against the active tree.

---

## 4. Consequences and Implementation Plan

### Positive Consequences
- Development PRs finish CI in under 60 seconds (static checks + schema audits + evidence checks) rather than 10 minutes.
- Developers can iterate locally with focused tests without incurring 2,250-test CI penalties on every push.
- Release qualification is completely rigorous, verifiable, and cannot be spoofed by development check passes.
- Interrupted or timed-out test runs preserve valuable timing data for bottleneck diagnosis.

### Negative Consequences / Trade-offs
- Developers must take responsibility for local validation and explicitly supply test evidence when seeking comprehensive verification before release.
- A green checkmark on a development PR means "development checks passed", not "all tests passed"; review workflows must educate contributors on this distinction.

---

## 5. References and Applicable Policies

- [Binding Owner Decisions on Test and CI Optimization](../../AGENTS.md)
- [Change-Aware CI Architecture](../change-aware-ci.md)
- [Testing Architecture and Guidelines](../testing.md)
- [CI Dependencies and Classification Policy](../../scripts/ci_dependencies.json)
