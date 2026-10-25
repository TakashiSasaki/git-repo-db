---
status: proposed
date: 2026-10-25
replaces: []
refines: [0001-validation-lifecycle-architecture.md, 0032-environment-sqlite-validation.md, 0033-minimal-product-sdist.md]
---

# ADR 0034: Repository-wide test and CI efficiency architecture

- **Decision & Context:** Adopt a repository-wide **Level 2 Mini-ADR** defining a
  unified, token-efficient, resource-aware test runner and CI scheduling convention
  that substantially reduces local test wall time, CI overhead, and AI coding-agent
  token consumption without weakening test coverage, failure detection, security
  guarantees, or evidence integrity.

  1. **Quiet execution and machine-readable indexing:** By default, test execution
     runners (`scripts/ci_execute.py`, `scripts/ci_profile.py`, and test harnesses)
     output a compact, deterministic terminal summary containing invocation ID,
     commit and effective tree, validation lane, test counts (total, passed, failed,
     skipped, inherited, unexecuted), reconciliation status, exit code, worker count,
     wall time, and evidence paths. Complete raw stdout/stderr, JUnit XML, append-only
     JSONL journals, and exact test-node inventories are preserved in output files
     via direct file streaming rather than retained in process memory. A structured
     `execution-summary.json` and selective `failure-index.json` allow AI coding agents
     and CI tools to inspect execution status and retrieve targeted error diagnostics
     without reading multi-megabyte raw logs.
  2. **Adaptive, safe pytest parallelization:** Unify previously divergent worker
     selection policies across all validation lanes into a shared, resource-aware
     budgeting model. Calculate worker counts from available logical CPUs, CPU
     affinity masks, cgroup CPU quotas, available memory limits, and selected test-node
     counts. Run tests exclusively in isolated `pytest-xdist` processes; never use
     unrestricted multithreading that violates repository process-global state invariants
     (such as environment variables and SQLite file handles). Deterministic worker bounds
     prevent concurrent lanes from oversubscribing host resources.
  3. **Shared immutable build outputs:** Reuse and extend the atomic, hash-bound
     `build_once` distribution mechanism (`tests/support/distributions.py`) across all
     packaging fixtures and distribution verifiers (`scripts/verify_i5_distribution.py`,
     `tests/packaging/test_p1_distribution.py`, and Access distribution checks).
     Artifacts (direct wheel, sdist, sdist-derived wheel, and locked wheelhouse) are
     built exactly once per unique input tree fingerprint and sealed with SHA-256
     receipts protected by file locking.
  4. **Strict workspace and concurrent isolation:** Separate all mutable per-variant
     test state. Direct-wheel and sdist-wheel verifications use completely distinct
     installation virtual environments, isolated outside-checkout test harnesses,
     per-variant logs, and separate database destinations. Never share mutable
     databases, HOME directories, virtual environments, or test fixtures.
  5. **CI task scheduling and consolidated collection:** Consolidate repeated, redundant
     pytest collection passes (such as the four sequential passes in `verify_i5_offline.py`)
     into a single collection pass with structured marker/cohort evaluation while
     preserving exact test-node multiset reconciliation. Execute independent CI tasks
     (static validation, documentation checking, and artifact preparation) concurrently
     where dependency graphs permit.
  6. **Safe artifact retention and temporary workspace exclusion:** Restrict CI artifact
     uploads (e.g. `artifacts/access-registry/`) to essential verification evidence
     (raw test logs, JUnit XML, JSONL journals, failure comparisons, runtime identities,
     packaging contracts, hashes, and minimal reproduction archives) using an explicit
     allowlist. Exclude disposable expanded source trees, temporary wheel build
     workspaces, and disposable virtual environments, reducing artifact bloat by
     hundreds of megabytes per run.

- **Constraints / Do NOT:** Do not replace the existing validation infrastructure
  with an unrelated test framework or disable `pytest-xdist`. Do not run tests in
  threads instead of processes. Do not share mutable databases, writable catalogs,
  virtual environments, or mutable conftest/fixture state across workers or variants.
  Do not delete or truncate underlying raw logs, JUnit files, or journals: quiet
  presentation governs terminal/model consumption only, never evidence durability.
  Do not remove or weaken `os.fsync` durability in `ci_journal.py` without proven
  equivalent crash-tolerance. Do not hide known inherited non-successes (the 43
  Transfer-stage non-successes remain visible and explicitly reconciled). Do not
  report development check success as complete release acceptance. Do not weaken
  product SQLite safety floors (SQLite >= 3.51.3, WAL, STRICT, JSON, mutexes) or
  substitute an unverified SQLite library. Do not add cross-architecture requirements
  or an x86_64 local bootstrap test to ordinary development. Do not infer test nodes
  from filenames or skip required test-node reconciliation.

  Preserve [ADR 0001](0001-validation-lifecycle-architecture.md)'s two validation
  modes (development vs release), exact input binding (`acceptance_input_hash`),
  and clean-tree requirements. Preserve [ADR 0032](0032-environment-sqlite-validation.md)'s
  environment-loaded SQLite convention and [ADR 0033](0033-minimal-product-sdist.md)'s
  minimal product sdist contracts.

- **Reason & Ref:** Baseline profiling revealed significant efficiency bottlenecks:
  repetitive collection passes in `verify_i5_offline.py` consumed ~14.5 seconds of pure
  overhead; uncoordinated 2-worker defaults in Access CI underutilized available 4-core
  hosts, extending suite wall time by 34–50%; packaging and distribution scripts
  repeatedly rebuilt identical wheels and sdists from scratch; `verify_i5_distribution.py`
  stored entire 401 MB `source.tar` archives, 421 MB unpacked sources, and 29 MB
  virtualenvs directly inside `artifacts/access-registry/`, resulting in a massive
  725 MB zipped artifact upload taking 40 seconds in CI; and full pytest terminal
  outputs flooded console logs with tens of thousands of tokens. This decision
  formalizes the engineering contracts for high-performance, token-efficient,
  and safe validation infrastructure.

  Accompanied by the detailed architectural specification in
  [docs/architecture/verification-efficiency-architecture.md](../architecture/verification-efficiency-architecture.md).
  Allocation on 2026-10-25 UTC checked remote heads, reachable ADR history, and the
  prior 0033 watermark. Stacked on `main` HEAD `8dd99b80470d5bdde203556b88c778332f9e92fb`.
