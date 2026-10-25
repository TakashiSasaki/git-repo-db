# Hosted product Python selection

ADR 0032 uses the selected Python's actual SQLite. The default Ubuntu 24.04
`setup-python` CPython 3.12.15 loaded SQLite 3.45.1 in PR #132; Access correctly
refused its unsafe product runtime before pytest. A newer Python version alone
does not establish compatibility.

Both runtime workflows use `.github/actions/product-python/action.yml`. Its
`scripts/ci_python_runtime.json` selects the complete upstream
[python-build-standalone](https://github.com/astral-sh/python-build-standalone/releases/tag/20261021)
CPython 3.12.15 Linux x86_64 distribution by immutable release URL and SHA-256.
The archive contains the whole interpreter, standard library and its built-in
SQLite extension. No SQLite component is separately obtained, built or replaced.
The Python manifest has no SQLite equality gate. Update the complete distribution
deliberately, verify its published digest and rerun hosted probes and review.

Before dependencies, the action records actual Python/executable/base executable,
SQLite version/source ID, extension origin and digest, compile options, loader
environment and process mappings. A built-in `_sqlite3` has no `__file__`; its
identity is bound to the complete Python executable digest. Real Access and P1
factory guards and STRICT/JSON/FTS5/WAL probes must pass. Runtime receipts are
written before refusal. This does not alter product support or WAL predicates.

The action exports an absolute `CI_PRODUCT_PYTHON`, `UV_PYTHON` and
`UV_PYTHON_DOWNLOADS=never`. Both development and docs dependency preparations
explicitly use that interpreter; subsequent `uv run --no-sync` commands retain it.
Same-invocation comparisons after dependencies and in the actual installed wheel
and sdist-derived-wheel venvs reject executable/library drift. Those comparisons
bind one execution's receipts; local and hosted SQLite versions may differ.
Installed origin, wheel/file hashes, outside-checkout domain smoke assertions and
offline network guards remain separate checks.

The stdlib-only `sqlite-policy` job requires no dependency preparation and does
not run product tests on its bootstrap Python. It checks active workflows,
composite actions and tooling for prohibited SQLite configuration. Access CI
retains every original pytest target, both installed smokes, audits and ledger
reconciliation. Additional I4/I5 bounded tests, broad regression comparison,
offline inventory and installed I2–I5 probes run even after an inherited failure.
The extended timeout accommodates these sequential checks. Failing checks stay
failing; the historical 79 non-successes are compared by node/phase/refusal/frame.
Inventory-only cohorts are explicitly unexecuted, and development CI is not full
release acceptance.

The same script also installs the distribution locally (`provision`) with the same
SHA-256 download and a stricter safe extractor, for the [local environment](local-python.md).
Its manifest additionally pins the aarch64 archive from the same release; the hosted
x86_64 entry and the action are unchanged. Probes now also reject an `_sqlite3` extension
or library outside the selected distribution and record per-capability results.

Artifacts retain the full evidence. Access also emits a bounded indexed ZIP of
runtime/results/JUnit/journals/logs to the normal job log, because artifact blob
downloads returned HTTP 403 in this environment. Decode only actual timestamped
`CI_RECEIPTS_*_V1` output records; verify outer size/SHA-256, END marker and every
indexed member before using results. Source archives, venvs and build trees are
excluded from this fallback. Uploaded artifacts still retain the original files.
