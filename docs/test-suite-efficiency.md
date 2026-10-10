# Test suite efficiency

This corrective PR is stacked on the Schema 19 evidence-integrity implementation.
It changes test execution and synthetic fixture preparation, without changing
production sources, domain decisions, parser definitions or the packaged DDL.
Phase 2 architecture recommendations remain pending owner decisions.

## Parallelism and isolation

Ordinary acceptance was already running with four xdist processes. It now uses
`worksteal` so idle workers can take queued cases from busy workers. Small selected
ordinary sets keep their sequential default. `--workers N` overrides the count;
one disables xdist, and selected execution caps the count at the selected case
count. Different CPU quotas may favor different counts; four is not a claim of
optimality on every machine.

The installed wheel and sdist-derived-wheel cases now run with two isolated
processes. Each keeps its own venv, working directory, HOME/configuration,
catalog, Git repositories and local HTTP server. Real credentials and checkout
PYTHONPATH/bootstrap state do not enter their captured child environments.
Their existing installed-origin, schema, acquisition, search, reparse, retirement,
Exchange and maintenance assertions remain intact.

Parallel workers would normally repeat a module-scoped distribution build. The
new test-only helper instead builds both artifacts and locked requirements once
inside this pytest invocation. A blocking OS lock excludes competing builders;
only a complete hash-bound product set receives an atomically published success
receipt. Failed or killed prefixes can be rebuilt; changed sealed products fail.
Sequential and xdist invocation roots are handled separately, so no result is
reused across pytest invocations. Installation environments and mutable catalogs
are never shared.

## Removed redundant preparation

Git fixture trees reuse identical blobs that native Git already wrote in that
same repository. Native Git still creates every tree/commit and establishes all
object IDs. Another repository or object format writes its own objects. Missing
loose objects, including packed objects, fall back to native writes. Direct
`blob()` calls retain native execution, and byteslike input is normalized only
for cache keys. No initialized-catalog template or cross-test mutable fixture is
introduced.

Existing schema/FK/integrity and domain checks are retained. CLI schema validation
was already compiled once per process, and HTTP fixture shutdown already used a
short polling interval; neither is counted as a new improvement. Twenty added
ordinary cases cover scheduling/overrides, competing builders, incomplete/corrupt
products and Git repository/format/content isolation.

## Actual measurement

The [machine receipt](validation/synthetic/test-suite-efficiency-20261010.json)
records raw-profile/JUnit hashes, exact source SHAs/trees, commands and CPU times.
The local binding was Python 3.12.14 / SQLite 3.53.1, uv 0.12.19, with a four-CPU
cgroup quota. Whole-suite samples ran sequentially, without concurrent tests or
benchmarks. These are one-pair observations, not performance guarantees.

| Lane | Before | After | Cases before / after |
| --- | ---: | ---: | ---: |
| Ordinary, four workers | 253.81 s | 241.70 s | 1,921 / 1,941 |
| Installed packages | 58.55 s | 31.57 s | 2 / 2 |
| Combined | 312.36 s | 273.27 s | 1,923 / 1,943 |

Combined measured wall time fell 12.5%, despite the added regression cases.
Package wall time fell 46.1%; package CPU work did not fall, since parallelism
overlaps the two checks and adds worker startup. The ordinary change combines
scheduling and fixture deduplication; this measurement does not isolate their
individual causal contributions.

The original `/usr/bin/time` attempt could not execute because that program was
absent. Successful samples use Python `perf_counter` and `getrusage`; the failed
setup is not included as a timing sample.

## Reproduction and final acceptance

Prepare the locked environment and wheelhouse, then use the current runner:

```sh
uv sync --locked --group dev
uv run --no-sync python scripts/prepare_wheelhouse.py
uv run --no-sync python scripts/ci_execute.py current --lane tests --workers 4
uv run --no-sync python scripts/ci_execute.py current --lane packaging --workers 2
```

Use separate profile output directories for comparisons and wait for each run
to finish. `current` profiles are raw execution evidence; they do not fabricate a
selected/executed acceptance gate. The final hosted workflow collects selections
before execution and reconciles every unique node ID against JUnit. Final source
SHA/tree, hosted run, full acceptance and independent review are recorded in the
submitted PR body. No merge or release is authorized.
