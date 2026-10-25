# Independent Review Report: Local Python and SQLite Standardization Hardening (Superseding Review)

- **Date:** 2026-10-25
- **Reviewer:** Independent Non-Author Software Engineer & Security Auditor
- **Target Repository:** `/home/ubuntu/github/git-repo-db`
- **Target PR:** [#179](https://github.com/TakashiSasaki/git-repo-db/pull/179)
- **Target Branch:** `impl/local-python-standardization-20261025`
- **Base Commit:** `f3f468f4a15d277e984e4a581c8707ab90205397` (Tree: `8665259196010bc0d95ee785d22e5a4b1c79f111`)
- **Tested Commit (HEAD):** `fe778a9ea8f0f1e405ebc956652bc73cb699e9c6` (Tree: `5e2d5cf81f9cd0e26eaca2b84ec2a64bbe390ccd`)
- **Review Branch:** `review/local-python-standardization-followup-20261025`
- **Review Surface:** `pull-request.require-independent-exact-head-review`
- **Superseded Review PR:** [#180](https://github.com/TakashiSasaki/git-repo-db/pull/180) (Commit: `307878c66cd7a0b0baa02d16eb01d23aa32ce2c5`, Tree: `81dd8d0f4320c6b320fbf0b4be3f27afebcded65`)
- **Verdict:** **NON-AUTHOR INDEPENDENT ACCEPTANCE (APPROVE)**
- **Blocking Findings (P0/P1):** **0**

---

## 1. Supersession Statement

This independent review report formally **supersedes** the historical review PR [#180](https://github.com/TakashiSasaki/git-repo-db/pull/180), which evaluated initial implementation commit `307878c66cd7a0b0baa02d16eb01d23aa32ce2c5`.

Following that earlier review, author hardening commit `fe778a9ea8f0f1e405ebc956652bc73cb699e9c6` was pushed to PR #179 with message:
`fix(env): serialize checkout bootstrap, ignore migrated venvs, and execute local setup tests in hosted CI`.

The follow-up commit introduced four material hardening improvements:
1. **Root Git-Ignore of Migrated Environments:** Added `/.venv.migrated-*/` to `.gitignore` to guarantee that migrated conflicting virtual environments never pollute `git status --porcelain` or effective tree calculations.
2. **Hosted CI Execution of Setup Test Suite:** Wired `test_local_python_setup.py` directly into the stdlib-only `sqlite-policy` job in `.github/workflows/tests.yml`, providing hosted regression coverage across all 47 setup tests on every pull request.
3. **Checkout-Level Concurrency Serialization:** Introduced `CheckoutLock` advisory locking (`root / artifacts/local-python/.bootstrap.lock`) with configurable timeout (`--lock-timeout`), establishing an ordered lock hierarchy (`CheckoutLock` -> `InstallLock`) that serializes concurrent bootstraps within the same checkout and fails closed on contention without receipt corruption.
4. **Comprehensive Concurrency & Git-Ignore Test Suites:** Added `GitIgnoreMigratedVenvTests` (4 tests) and `CheckoutConcurrencyTests` (5 tests) to `tests/unit/test_local_python_setup.py`, increasing total test coverage from 38 to 47 tests.

This re-review rigorously audits the complete integrated tree of commit `fe778a9ea8f0f1e405ebc956652bc73cb699e9c6` across all 9 required verification domains.

---

## 2. Section-by-Section Independent Verification

### 2.1 Git Ignore Behavior (`/.venv.migrated-*/`)
- **Inspection of Root `.gitignore`:** Confirmed `.gitignore` line 3 contains `/.venv.migrated-*/`.
- **Unit Test Execution:** Ran `python3 -m unittest -v tests.unit.test_local_python_setup.GitIgnoreMigratedVenvTests` in the review worktree:
  - `test_migrated_venv_is_excluded_from_git_status`: PASSED
  - `test_effective_tree_calculation_excludes_migrated_environments`: PASSED
  - `test_ordinary_source_changes_remain_discoverable`: PASSED
  - `test_git_check_ignore_root_level_scoping`: PASSED
  - **Result:** `Ran 4 tests in 0.081s - OK`.
- **Live Git Status & Porcelain Verification:**
  - Created temporary directory `.venv.migrated-test-20261025T120000Z` with dummy files in the worktree.
  - Executed `git status --porcelain`: output was completely empty.
  - Executed `git check-ignore -v .venv.migrated-test-20261025T120000Z`: matched `.gitignore:3:/.venv.migrated-*/`.
  - Removed temporary directory cleanly.

### 2.2 Hosted CI Execution
- **Workflow Run Inspection:** Audited GitHub Actions workflow run `40193813875` (Commit `fe778a9ea8f0f1e405ebc956652bc73cb699e9c6`):
  - Workflow Name: `tests`
  - Status: `completed`, Conclusion: `success`.
- **Job `121170246634` (`sqlite-policy`):**
  - Executed command: `python -m unittest discover -s tests/unit -p test_local_python_setup.py`
  - Python Environment: `/opt/hostedtoolcache/Python/3.12.15/x64`
  - Job Log Record:
    ```
    ...............................................
    ----------------------------------------------------------------------
    Ran 47 tests in 0.753s
    OK
    ```
- **Associated Workflow Runs:**
  - Run `40193813875` (`tests`): `sqlite-policy` (16s) and `offline` (44s) both SUCCESS.
  - Run `40193813880` (`Access registry focused verification`): All 24 steps completed, SUCCESS.
  - Run `40193813890` (`pages`): `pages/build-and-validate` completed, SUCCESS.

### 2.3 Checkout-Level Concurrency & Lock Hierarchy
- **Implementation Inspection:**
  - `scripts/setup_local_python.py` implements `CheckoutLock` (lines 50-81) utilizing `fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)`.
  - Checkout lock target: `root / artifacts/local-python/.bootstrap.lock`.
  - Locking scope: Wraps entire bootstrap pipeline (lines 413-441).
  - Lock hierarchy: `CheckoutLock` (checkout-scoped, acquired first) -> `InstallLock` (runtime distribution-scoped, acquired inside `ci_python_runtime.provision()`). This strict unidirectional order guarantees deadlock-free operation across concurrent checkouts and workers.
  - Timeout fail-closed: If lock acquisition exceeds `timeout` (default 600.0s, configurable via `--lock-timeout`), `TimeoutError` is raised and caught, reporting to stderr and returning exit status 1 without mutating existing receipts.
- **Unit Test Execution:** Ran `python3 -m unittest -v tests.unit.test_local_python_setup.CheckoutConcurrencyTests`:
  - `test_competing_receipt_writes_prevented`: PASSED
  - `test_failed_bootstrap_under_lock_records_failure_and_releases_lock`: PASSED
  - `test_held_checkout_lock_blocks_and_times_out`: PASSED
  - `test_independent_checkouts_do_not_block_each_other`: PASSED
  - `test_sequential_bootstrap_under_lock_is_idempotent`: PASSED
  - **Result:** `Ran 5 tests in 0.429s - OK`.

### 2.4 Interpreter and SQLite Safety
- **Runtime Identity:**
  - Python Version: `3.12.15 (main, Oct 21 2026, 17:46:20) [Clang 23.1.3 ]`
  - SQLite Version: `3.53.1` (exceeding product floor >= 3.51.3)
  - SQLite Source ID: `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`
  - Threadsafety: `3` (serialized multi-threading mode enabled)
  - Process Mappings: Empty (`[]`), confirming no external system dynamic SQLite library is loaded.
- **Database Capabilities:**
  - STRICT table support: Verified active (`CREATE TABLE ... STRICT` rejects mistyped inserts with `sqlite3.IntegrityError`).
  - JSON support: Verified active (`json_extract`, `json_valid` operational).
  - WAL journal mode: Verified active (`PRAGMA journal_mode=WAL` returns `wal`).
  - FTS5 Trigram tokenizer: Verified active (`CREATE VIRTUAL TABLE ... USING fts5(..., tokenize='trigram case_sensitive 1')` matches substrings).
  - Preflight verification: Executed `scripts/preflight_access.py` under the synchronized interpreter, reporting `status: "PASS"`.
- **Policy Compliance:** Executed `scripts/check_sqlite_validation_policy.py` and `tests/unit/test_sqlite_validation_policy.py`: 31 tests passed in 0.200s, reporting 0 policy violations.

### 2.5 x86_64 Bootstrap Evidence
- **Distribution Manifest Verification:**
  - Pinned x86_64 distribution in `scripts/ci_python_runtime.json`:
    - Release: `20261021`
    - URL: `https://github.com/astral-sh/python-build-standalone/releases/download/20261021/cpython-3.12.15%2B20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz`
    - SHA-256: `6d7521138fd33afddc1ccd08abb007d9a2829e38117c2576f9efdc0ec73ce772`
  - Pinned aarch64 distribution:
    - URL: `https://github.com/astral-sh/python-build-standalone/releases/download/20261021/cpython-3.12.15%2B20261021-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz`
    - SHA-256: `b4567aa5a11f51b540c4dfd9e082ebf23e554f8ac17b85caa6cea23e83693394`
- **Upstream Cryptographic Integrity Check:**
  - Fetched official `SHA256SUMS` from GitHub release `astral-sh/python-build-standalone` tag `20261021`.
  - Both digests match upstream published checksums bit-for-bit.
  - Confirmed x86_64 GitHub Actions runner execution and receipt generation in hosted run `40193813875`.

### 2.6 Hosted Installation Preservation
- **Action Configuration:** `.github/actions/product-python/action.yml` is byte-identical to `main` (`git diff` reports 0 differences).
- **Workflow Configuration:** `.github/workflows/tests.yml` preserves all existing composite actions, planning steps, offline boundaries, and artifact retention, adding only the stdlib-only local setup test execution in `sqlite-policy`.
- **CI Stability:** All CI jobs across all workflows completed with green success conclusions on commit `fe778a9ea8f0f1e405ebc956652bc73cb699e9c6`.

### 2.7 Installation Integrity & Archive Extraction Boundaries
- **Extraction Hardening in `scripts/ci_python_runtime.py`:**
  - `_contained()` rejects empty paths, NUL bytes, backslashes, absolute paths, `..` directory traversal, and link targets that escape the `python/` directory.
  - `safe_extract()` limits member counts (`MAX_MEMBERS = 100_000`) and total unpacked byte volume (`MAX_UNPACKED_BYTES = 1 GB`).
  - Refuses block devices, character devices, FIFOs, and duplicate members.
  - Rejects archive members placed beneath an archive-defined symlink.
  - Enforces copy-on-hardlink semantics via `shutil.copyfile` to eliminate hardlink escape and inode poisoning risks.
  - Opens regular files with `os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW`.
  - Post-extraction `verify_contained()` scans all extracted symlinks to confirm targets remain within the distribution tree.
- **Filesystem Boundaries:**
  - `require_private()` verifies directory ownership by `os.getuid()` and rejects group-writable or world-writable modes (`st_mode & 0o022`).
  - `make_read_only()` recursively strips write bits (`~0o222`) before atomic publication.
- **Unit Test Execution:** Ran `python3 -m unittest -v tests/unit/test_ci_python_runtime.py`:
  - 41 tests passed, 19 subtests passed in 1.609s (1 expected skip for zero threadsafety test on serialized build).

### 2.8 Failure Receipts and Fail-Closed Behavior
- **Dynamic Loader Overrides:**
  - Executed `LD_PRELOAD=/unexpected.so ./scripts/local-run.sh python -V`.
  - Output: `Refusing to use this environment: Unset these interpreter or dynamic-loader overrides first: LD_PRELOAD`
  - Exit code: `3` (distinct refusal status per `local_env.py`).
- **Incompatible Virtual Environments:**
  - Foreign virtual environment detected without `--migrate-venv` fails bootstrap with exit status `1`, writes `status: "failed"` receipt at step `virtual_environment`, and leaves the foreign `.venv` untouched.
  - Rerunning with `--migrate-venv` cleanly renames the foreign directory to `.venv.migrated-<timestamp>` and creates a fresh verified `.venv`.
- **Timeout and Concurrency Contention:**
  - Bootstrap execution with held lock and expired timeout exits with status `1`, prints failure message, and preserves existing passed receipts intact without modification.

### 2.9 Packaging, Format, and Lint Verification
- **Sdist Packaging Contract:**
  - Executed `scripts/check_sdist_contract.py --build --output artifacts/ci-profile/sdist-members.json` via `./scripts/local-run.sh`:
  - Output: `status: "passed"`, 164 members, compressed size 708,251 bytes (< 2 MiB budget), unpacked size 6,076,119 bytes (< 8 MiB budget).
- **Code Linting and Formatting:**
  - Executed `./scripts/local-run.sh ruff check src tests scripts`: `All checks passed!`.
  - Executed `./scripts/local-run.sh ruff format --check src tests scripts`: `465 files already formatted`.
- **Integrated Test Execution:**
  - Executed `./scripts/local-run.sh pytest -v tests/unit/test_ci_python_runtime.py tests/unit/test_local_python_setup.py tests/unit/test_sqlite_validation_policy.py`:
  - Result: `119 passed, 88 subtests passed in 4.19s` (100% PASS).

---

## 3. PR Review Decision Block

```json
{
  "schema_version": 1,
  "analysis_status": "COMPLETE",
  "summary": "Independent re-review confirms PR #179 hardened commit fe778a9e satisfies all repository invariants, ADR 0032, and security boundaries with 0 blocking findings.",
  "event": "APPROVE",
  "limitations": [],
  "comments": []
}
```

---

## 4. Conclusion & Final Acceptance

Commit `fe778a9ea8f0f1e405ebc956652bc73cb699e9c6` successfully hardens PR #179 against concurrency races, workspace git-status pollution, and hosted CI verification gaps without introducing any regressions, security vulnerabilities, or architecture contract violations.

- **Verdict:** **NON-AUTHOR INDEPENDENT ACCEPTANCE (APPROVE)**
- **Blocking Findings (P0/P1):** **0**

---

## Read Files

The following absolute paths represent all repository files opened and inspected via file viewing tools during this review:

- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/.gitignore`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/tests/unit/test_local_python_setup.py`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/.github/workflows/tests.yml`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/scripts/setup_local_python.py`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/scripts/ci_python_runtime.py`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/scripts/ci_python_runtime.json`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-20261025/docs/implementation/evidence/local-python-standardization-20261025/independent/REPORT.md`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-20261025/docs/implementation/evidence/local-python-standardization-20261025/independent/summary.json`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-20261025/docs/implementation/evidence/local-python-standardization-20261025/independent/provenance.json`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/docs/local-python.md`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/.github/actions/product-python/action.yml`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/scripts/setup-local-python.sh`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/scripts/local-run.sh`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/scripts/local_env.py`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/.agents/skills/ci-final-tree-verification/SKILL.md`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/AGENTS.md`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/README.md`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/docs/ci-python-runtime.md`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/docs/site/development/index.md`
- `/home/ubuntu/github/git-repo-db/review/local-python-standardization-followup-20261025/docs/testing.md`
