# Independent Review Report: Local Python and SQLite Standardization

**Date:** 2026-10-25  
**Reviewer:** Independent Non-Author Software Engineer & Security Auditor  
**Target Branch:** `impl/local-python-standardization-20261025`  
**Target PR:** [#179](https://github.com/TakashiSasaki/git-repo-db/pull/179)  
**Base Commit:** `f3f468f4a15d277e984e4a581c8707ab90205397` (Tree: `8665259196010bc0d95ee785d22e5a4b1c79f111`)  
**Tested Commit:** `307878c66cd7a0b0baa02d16eb01d23aa32ce2c5` (Tree: `81dd8d0f4320c6b320fbf0b4be3f27afebcded65`)  
**Review Branch:** `review/local-python-standardization-20261025`  
**Review Surface:** `pull-request.require-independent-exact-head-review`  
**Verdict:** **NON-AUTHOR INDEPENDENT ACCEPTANCE (APPROVE)**  
**Blocking Findings (P0/P1):** **0**  

---

## 1. Executive Summary

This independent audit evaluated Pull Request #179 (`impl/local-python-standardization-20261025`), which standardizes the local Python development and validation environment in strict accordance with [ADR 0032](../../../../docs/adr/0032-environment-sqlite-validation.md) (single Python-loaded SQLite per environment; no test SQLite substitution, external download, or version matrix).

The audit verified:
1. **Installer Security and Confinement**: Extraction mechanics enforce member counts (`MAX_MEMBERS`), unpacked byte thresholds (`MAX_UNPACKED_BYTES`), path normalization, link containment within the distribution root, copy-on-hardlink semantics, rejection of device/special members, post-extraction symlink containment checks, user directory ownership enforcement (`require_private`), read-only permission stamping (`make_read_only`), and atomic publication under advisory locks (`InstallLock`).
2. **Distribution Integrity**: Cryptographic digest binding for both `x86_64-unknown-linux-gnu` and `aarch64-unknown-linux-gnu` distributions from the official `astral-sh/python-build-standalone` release `20261021`, verified directly against upstream release assets and SHA256SUMS.
3. **End-to-End Local Bootstrap**: Executed clean bootstrap `./scripts/setup-local-python.sh` on native Linux aarch64, verifying generation of `artifacts/local-python/receipt.json` with status `"passed"` across all 10 pipeline steps.
4. **Runtime and SQLite Identity**: Verified Python 3.12.15, SQLite 3.53.1 (satisfying the >= 3.51.3 floor), `sqlite_threadsafety == 3` (mutexes enabled), STRICT tables, JSON functions, FTS5 trigram tokenization, WAL journal mode, and verified execution of Access/P1 schema runtime factories.
5. **Adversarial and Negative Testing**: Validated fail-closed defense against dynamic loader overrides (`LD_PRELOAD`, `LD_LIBRARY_PATH`), lockfile tampering (`uv.lock`), foreign virtual environments, unverified environments, and verified safe preservation via `--migrate-venv`.
6. **Preservation of Hosted CI Workflows**: Confirmed unperturbed hosted GitHub Actions CI configuration (`action.yml` exports, `sqlite-policy` and `offline` jobs in `tests.yml`, and green CI runs across all jobs on PR #179).

---

## 2. Baseline and Commit Lineage Verification

- **Target Base (`main`):** `f3f468f4a15d277e984e4a581c8707ab90205397` (Tree: `8665259196010bc0d95ee785d22e5a4b1c79f111`)
- **Tested Input Commit:** `307878c66cd7a0b0baa02d16eb01d23aa32ce2c5` (Tree: `81dd8d0f4320c6b320fbf0b4be3f27afebcded65`)
- **Integration Diff:** 15 files changed, 2577 insertions(+), 49 deletions(-)

---

## 3. Installer Security & Safe Extraction Architecture

### 3.1 Path Confinement and Link Safety
In `scripts/ci_python_runtime.py`:
- `_contained(name, link=None)` validates every archive member path:
  - Rejects empty strings, NUL bytes (`\x00`), backslashes (`\\`), and absolute paths (leading `/`).
  - Resolves symlink and hardlink targets relative to the member's parent directory and normalizes via `posixpath.normpath`.
  - Rejects any path containing `..` components or failing to start with `python/` (`DISTRIBUTION_DIRECTORY`).
- `safe_extract(archive_path, destination)` executes strict two-pass validation:
  - Validates total member count (`len(members) <= 100_000`) and unpacked volume (`sum(m.size) <= 1 GB`).
  - Pre-extraction scan: rejects devices, FIFOs, duplicate members, and any member positioned beneath an archive-defined symlink.
  - Symlink extraction: links are created with relative targets verified to remain inside the distribution tree.
  - Hard link extraction: hard links are copied via `shutil.copyfile` and permissions mirrored, eliminating hard-link escape or inode poisoning risks.
  - Regular file extraction: files are opened with `os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW` and stamped with `0o755` or `0o644`.
  - Post-extraction audit (`verify_contained`): walks the entire extracted tree and verifies `os.path.realpath(path).is_relative_to(root)` for all symbolic links.

### 3.2 Access Control and Immutability
- `require_private(path, what)`:
  - Verifies directory is owned by the current user (`status.st_uid == os.getuid()`).
  - Rejects directories with group-writable or world-writable bits (`status.st_mode & 0o022 != 0`).
- `make_read_only(root)`:
  - Recursively removes write permissions (`~0o222`) from all regular files and directories in the tree.
- Advisory lock (`InstallLock`):
  - Uses `fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)` to ensure concurrent bootstrap invocations serialize and never publish partial or conflicting trees.
- Atomic publication:
  - Staging occurs in `.staging-<sha256>-<pid>-<uuid>`.
  - The staged tree's digest (`tree_sha256`) and interpreter identity are verified, `ready.json` written, and read-only flags set before `os.rename(staging, final)`.
  - Stale staging directories from interrupted processes are pruned only under the advisory lock.
  - Existing installations are never overwritten or replaced.

---

## 4. Python Distribution Integrity

The distribution manifest `scripts/ci_python_runtime.json` pins distributions from the official `astral-sh/python-build-standalone` release `20261021`:
- **x86_64-unknown-linux-gnu**:
  - URL: `https://github.com/astral-sh/python-build-standalone/releases/download/20261021/cpython-3.12.15%2B20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz`
  - SHA-256: `6d7521138fd33afddc1ccd08abb007d9a2829e38117c2576f9efdc0ec73ce772`
- **aarch64-unknown-linux-gnu**:
  - URL: `https://github.com/astral-sh/python-build-standalone/releases/download/20261021/cpython-3.12.15%2B20261021-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz`
  - SHA-256: `b4567aa5a11f51b540c4dfd9e082ebf23e554f8ac17b85caa6cea23e83693394`

Both checksums were independently verified against the published `SHA256SUMS` file from the `astral-sh/python-build-standalone` release `20261021` via GitHub API and curl. The digests match upstream bit-for-bit.

---

## 5. End-to-End Local Bootstrap Execution

Local bootstrap was executed from scratch in `/home/ubuntu/github/git-repo-db/review/local-python-standardization-20261025`:

```bash
./scripts/setup-local-python.sh
```

**Output:**
```json
{
  "status": "passed",
  "python": "/home/ubuntu/.local/share/git-repo-db/python/b4567aa5a11f51b540c4dfd9e082ebf23e554f8ac17b85caa6cea23e83693394/python/bin/python3",
  "sqlite": "3.53.1",
  "receipt": "/home/ubuntu/github/git-repo-db/review/local-python-standardization-20261025/artifacts/local-python/receipt.json"
}
```

The bootstrap recorded complete structured evidence in `artifacts/local-python/receipt.json`:
- `schema`: `git-repo-db-local-python-receipt/1`
- `status`: `passed`
- `repository`: Commit `307878c66cd7a0b0baa02d16eb01d23aa32ce2c5`, Tree `81dd8d0f4320c6b320fbf0b4be3f27afebcded65`, `dirty: false`
- `steps`: All 10 steps passed:
  1. `host`: passed (platform: `aarch64-unknown-linux-gnu`)
  2. `tools`: passed (`uv 0.11.28`, `git 2.43.0`)
  3. `repository`: passed (clean git checkout)
  4. `provision`: passed (content-addressed directory verified)
  5. `identity_before_dependencies`: passed (verified runtime identity prior to package sync)
  6. `virtual_environment`: passed (`action: create`)
  7. `dependency_sync`: passed (`inputs_unchanged: true`)
  8. `identity_after_dependencies`: passed (verified identical SQLite runtime after dependency installation)
  9. `product_preflight`: passed (`scripts/preflight_access.py` PASSED)
  10. `final_verification`: passed (`local_env.verify_environment(deep=True)` PASSED)

---

## 6. Runtime Identity and SQLite Verification

The provisioned runtime was directly queried via `./scripts/local-run.sh python`:
- **Python version**: `3.12.15 (main, Oct 21 2026, 17:46:20) [Clang 23.1.3 ]`
- **SQLite version**: `3.53.1` (exceeds the product floor of 3.51.3)
- **SQLite source ID**: `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`
- **SQLite module origin**: `built-in`
- **SQLite process mappings**: `[]` (no host system dynamic SQLite library mapped)
- **SQLite threadsafety**: `3` (mutexes enabled; satisfies `threadsafety != 0`)
- **STRICT table support**: `passed` (mistyped inserts rejected with `sqlite3.IntegrityError`)
- **JSON support**: `passed` (`json_extract` functional)
- **FTS5 trigram tokenizer**: `passed` (trigram substring query matched correctly)
- **WAL journal mode**: `passed` (`PRAGMA journal_mode=WAL` returned `wal`)
- **Product factories**: `access_schema.require_runtime()` and `p1_schema._open(":memory:", fresh=True)` passed without substitution.

---

## 7. Adversarial & Negative Testing

Failure behavior under mismatched or unsafe conditions was verified:

### 7.1 Dynamic Loader Overrides
- **Command:** `LD_PRELOAD=/unexpected.so ./scripts/local-run.sh python -V`
- **Result:** Exit code 3, output:
  `Refusing to use this environment: Unset these interpreter or dynamic-loader overrides first: LD_PRELOAD`
- **Command:** `LD_LIBRARY_PATH=/tmp ./scripts/local-run.sh python -V`
- **Result:** Exit code 3, output:
  `Refusing to use this environment: Unset these interpreter or dynamic-loader overrides first: LD_LIBRARY_PATH`
- **Command:** `LD_PRELOAD=/unexpected.so ./scripts/setup-local-python.sh`
- **Result:** Exit code 1, failed at `host` step, receipt status recorded as `"failed"`.
- Subsequent `local-run.sh` invocations cleanly refused to proceed until repaired via `setup-local-python.sh`.

### 7.2 Lockfile Tampering
- Appended comment to `uv.lock`.
- **Command:** `./scripts/local-run.sh python -V`
- **Result:** Exit code 3, output:
  `Refusing to use this environment: uv.lock changed after the environment was synchronized`
- Restored `uv.lock` via `git checkout uv.lock`.

### 7.3 Foreign Virtual Environment Rejection & Migration
- Replaced `.venv` with a virtual environment created with system `/usr/bin/python3`.
- **Command:** `./scripts/local-run.sh python -V`
- **Result:** Exit code 3, output:
  `Refusing to use this environment: .../.venv/bin/python resolves to /usr/bin/python3.12, not the selected ...`
- **Command:** `./scripts/setup-local-python.sh` (without `--migrate-venv`)
- **Result:** Exit code 1, failed at `virtual_environment` step, foreign `.venv` left untouched and uncorrupted, with instructions to use `--migrate-venv`.
- **Command:** `./scripts/setup-local-python.sh --migrate-venv`
- **Result:** Exit code 0, foreign `.venv` preserved as `.venv.migrated-<timestamp>`, and a clean, verified project `.venv` established.

---

## 8. Hosted GitHub Actions CI Workflow Preservation

1. **Composite Action**: `.github/actions/product-python/action.yml` is unchanged and executes `scripts/ci_python_runtime.py install "$RUNNER_TEMP/product-python"`, using the shared download and safe extractor.
2. **Hosted Manifest Entry**: `scripts/ci_python_runtime.json` preserves the exact `x86_64-unknown-linux-gnu` configuration and SHA-256 for GitHub-hosted runners.
3. **Workflow Integrity**:
   - `sqlite-policy` in `.github/workflows/tests.yml` tests distribution integrity and SQLite policy with stdlib only.
   - `offline` in `.github/workflows/tests.yml` uses the composite action to provision Python, run `ci_plan.py`, and execute offline tests.
4. **Live GitHub Actions CI Results for Commit `307878c66cd7a0b0baa02d16eb01d23aa32ce2c5`**:
   - `tests` (run `40189104434`):
     - `sqlite-policy`: SUCCESS (15s)
     - `offline`: SUCCESS (29s)
   - `pages` (run `40189104452`):
     - `pages/build-and-validate`: SUCCESS (57s)
   - `Access registry focused verification` (run `40189104435`):
     - All 24 steps completed successfully: SUCCESS (8m5s)

---

## 9. Automated Test Execution Evidence

All automated test suites were executed through `./scripts/local-run.sh`:

1. **Runtime & Safe Extraction Suite:**
   - **Command:** `./scripts/local-run.sh python -m pytest tests/unit/test_ci_python_runtime.py -v`
   - **Result:** `41 passed, 19 subtests passed in 2.43s` (100% PASS)
2. **Local Setup & Launcher Verification Suite:**
   - **Command:** `./scripts/local-run.sh python -m pytest tests/unit/test_local_python_setup.py -v`
   - **Result:** `38 passed, 12 subtests passed in 0.46s` (100% PASS)
3. **Product Preflight Suite:**
   - **Command:** `./scripts/local-run.sh python scripts/preflight_access.py`
   - **Result:** `status: "PASS"`, all locked packages verified against `uv.lock`.
4. **Code Quality & Formatting:**
   - **Command:** `./scripts/local-run.sh ruff check scripts tests` -> All checks passed!
   - **Command:** `./scripts/local-run.sh ruff format --check scripts tests` -> 328 files already formatted.

---

## 10. Review Conclusion & Verdict

The implementation in PR #179 is high-quality, defensively architected, and fully compliant with repository invariants, ADR 0032, and the pr-review rules. It introduces no regressions, security vulnerabilities, or operational risks.

**Final Verdict:** **NON-AUTHOR INDEPENDENT ACCEPTANCE (APPROVE)**  
**Blocking Findings (P0/P1):** **0**
