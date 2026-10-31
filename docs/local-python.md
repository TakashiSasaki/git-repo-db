# Local Python and SQLite environment

Local development, tests, reviews and agents use one verified project environment:
the manifest-pinned **complete** Python distribution
(`scripts/ci_python_runtime.json`, the same upstream
[python-build-standalone](https://github.com/astral-sh/python-build-standalone)
release hosted CI uses) plus a project `.venv` created on exactly that interpreter.
Per [ADR 0032](adr/0032-environment-sqlite-validation.md) the SQLite is the one that
Python actually loads. It is built into the distribution; no SQLite is downloaded,
built, replaced, overridden or substituted, and `pysqlite3` is not used. The
product floor (SQLite >= 3.51.3, mutexes, WAL, STRICT, JSON, FTS5/trigram) is
enforced by the unchanged product factories, not by a version string.

Do not use the operating system's Python or SQLite for product validation when this
environment exists. Ubuntu 24.04's SQLite 3.45.1 is below the product floor.

## Prerequisites

- Linux `x86_64` or `aarch64` (glibc). Other hosts are refused with a clear message;
  no other Python or SQLite is substituted. Adding a platform means adding its
  SHA-256 to the manifest through review.
- `python3` >= 3.9 (only to start the bootstrap; it never runs product code), `git`
  and [`uv`](https://docs.astral.sh/uv/getting-started/installation/). The bootstrap
  never installs `uv`.
- Network for the first run only (about 30 MB archive, then locked wheels).
  No elevated privileges are used.

**CPU architecture validation scope:** x86_64 and aarch64 are currently
available bootstrap platforms, **not declared release targets**. During ordinary
development, testing one available CPU architecture is sufficient; the presence
of an x86_64 GitHub Actions runner does not require a separate x86_64 local
bootstrap run after a successful aarch64 validation. Supported architectures
for any future release will be selected explicitly at release planning.
See [testing and release validation](testing.md). Existing SQLite product
safety requirements apply on every architecture used.

## First-time setup

```bash
./scripts/setup-local-python.sh            # add --offline to forbid downloads
```

It inspects the host and tools, resolves or installs the verified distribution,
checks its Python/SQLite identity and the real product guards **before** any
dependency, creates or verifies `.venv` on that interpreter, runs
`uv sync --locked --group dev` with `UV_PYTHON` and
`UV_PYTHON_DOWNLOADS=never`, confirms `uv.lock`, root `pyproject.toml` and every workspace project metadata file are unchanged,
re-probes the runtime against the pre-dependency identity, runs
`scripts/preflight_access.py` and writes `artifacts/local-python/receipt.json`.
Any failed mandatory verification exits nonzero and the receipt says
`"status": "failed"` with the failing step; steps not reached are `not_run`.

## Normal use

```bash
scripts/local-run.sh pytest tests/unit/test_ci_plan.py -q
scripts/local-run.sh ruff check src tests scripts
scripts/local-run.sh python scripts/ci_profile.py profile tests/unit/test_ci_plan.py
scripts/local-run.sh python scripts/ci_execute.py current --lane tests
scripts/local-run.sh uv run --no-sync repo-catalog --format json doctor
eval "$(.venv/bin/python scripts/local_env.py env)"   # or export into this shell
```

`local-run.sh` first re-verifies the receipt, the selected interpreter's digest,
`.venv`'s base interpreter and the locked inputs, refuses `LD_*`/`PYTHONHOME`-style
overrides, then puts `.venv/bin` first on `PATH` and exports `UV_PYTHON`,
`UV_PYTHON_DOWNLOADS=never`, `CI_PRODUCT_PYTHON` and `CI_RUNTIME_REFERENCE`. Child
processes and installed wheel/sdist verification therefore select the same Python.
A command named `python*` that would resolve elsewhere is refused. After a lock, workspace metadata or
dependency change, rerun the setup command (it is idempotent) to resynchronize.

## Verification

```bash
.venv/bin/python scripts/local_env.py verify --deep     # re-hash the installed tree
.venv/bin/python scripts/preflight_access.py
.venv/bin/python scripts/ci_python_runtime.py probe artifacts/runtime/now.json \
    --reference artifacts/runtime/selected.json
```

The receipt records commit and effective tree, distribution manifest entry and
SHA-256, `sys.executable`, `sys._base_executable`, Python and SQLite versions and
source ID, `_sqlite3` origin and digest, library mappings, compile options, PRAGMAs,
every capability result, the dependency synchronization outcome and preflight.
Before/after comparisons bind one bootstrap invocation; they do not require the
same SQLite on different machines. This is development validation, not release
acceptance (ADR 0001).

## Offline use and reuse

After the first run, `./scripts/setup-local-python.sh --offline` and
`scripts/local-run.sh ...` need no network when `uv`'s cache holds the locked
wheels. Several checkouts and agents share one installation, found by archive
SHA-256 under `${GIT_REPO_DB_PYTHON_HOME:-${XDG_DATA_HOME:-~/.local/share}/git-repo-db/python}`.
A published installation is read-only and never modified or replaced; its whole
tree is re-verified on every setup run. Concurrent bootstraps are serialized by a
lock and publish only by an atomic rename of a verified staging directory.

## Diagnosing a wrong Python or SQLite

- `scripts/local-run.sh python -c 'import sys,sqlite3; print(sys.executable, sys._base_executable, sqlite3.sqlite_version)'`
  must show `.venv/bin/python`, a base under the installation directory and a
  version >= 3.51.3.
- `local_env.py verify` names the first drift: modified interpreter, repointed
  `.venv`, lock change, failed receipt, or a copied receipt.
- A `probe` failure naming a system SQLite mapping, an `_sqlite3` outside the
  distribution, or a loader override means something replaced the runtime. Unset
  `LD_PRELOAD`, `LD_LIBRARY_PATH`, `PYTHONHOME` etc.; do not work around the check.
- A refused installation (incomplete, edited, wrong version) is reported and left
  untouched. Remove it deliberately (`chmod -R u+w DIR && rm -rf DIR`) and rerun.

## Incompatible existing `.venv`

The bootstrap never deletes or rewrites a `.venv` on another interpreter or one it
cannot verify; it stops with instructions. To keep the old environment and create a
fresh one, run `./scripts/setup-local-python.sh --migrate-venv` (the old directory is
renamed `.venv.migrated-<UTC timestamp>`; remove it yourself when no longer needed).

## Relation to hosted CI

Hosted workflows are unchanged: `.github/actions/product-python` still runs
`scripts/ci_python_runtime.py install "$RUNNER_TEMP/product-python"` and the same
`probe`, sharing the SHA-256 download and safe extractor with the local installer.
See [hosted product Python selection](ci-python-runtime.md). Local and hosted
SQLite versions may differ.

## Temporary and cached locations

| Location | Contents | Safe to delete |
| --- | --- | --- |
| `.venv/`, `.venv.migrated-*` | project environment | yes, then rerun setup |
| `artifacts/local-python/`, `artifacts/runtime/` | receipts, preflight, probes (git-ignored, host paths) | yes |
| `<python home>/<sha256>/` | read-only verified distribution | only if no process uses it |
| `<python home>/.staging-*`, `.lock-*` | private staging, lock files | stale staging is removed automatically |
| `~/.cache/uv` | `uv` wheel cache | yes (needs network next time) |

Documentation uses its independent `documentation/.venv` and lock; product setup does not install rendering dependencies. See [workspace guide](../documentation/README.md).
