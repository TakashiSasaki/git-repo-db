# Task E evidence and non-author review handoff

Read [REPORT.md](REPORT.md) first. This is **Author verification** with explicit
remaining stage failures, not independent product acceptance or merge approval.

The indexed `task-e-evidence.zip` retains final raw collection/execution logs,
JUnit/phase journals, full source/runtime bindings, SQL statements/errors/full
rowsets, installed artifact receipts/hashes and the original failed attempts.
`artifact-index.json` binds every archived member by size and SHA-256, and binds
the archive itself. No database, runtime library, credential, venv or full
distribution binary is published. Built artifacts remain identifiable by their
recorded hashes and exact source commit.

Final execution folders inside the archive are `publication-3513` and
`publication-3531`, both at `cb1df83afc543d74df8b16327bfb2c418786b3b2`, tree
`9d0130aa3324ff36e4bcda0cfc89258e951a747a`. `summary.json` records the actual
nonzero broad/distribution results alongside successful bounded I2 checks.
`freeze1-3513` and `final-3513` are superseded development freezes, not final
acceptance. Their original labels are retained to preserve raw receipts.

## Reproduce

Use the repository's unchanged `uv.lock` and declared dev/docs groups. Build
actual SQLite 3.51.3 / 3.53.1 from the sqlite.org URLs, hashes and exact compiler
argv in `runtime/provenance.json`; use a dynamically linked interpreter and
measure `SELECT sqlite_version(),sqlite_source_id()` before testing. The source
archive hashes are `acb1e6f5d832484bf6d32b681e858c38add8b2acdfd42ac5df24b8afb46552b4`
and `36ad6e7f38540a3b21a2ac36340833f0a9e426bc1c752751c3ba669466827eae`.
Never relabel a static interpreter's SQLite version.

For each measured runtime, using fresh output paths:

```sh
python scripts/verify_i2.py --sqlite 3.51.3 --output /absolute/new-test-evidence
python scripts/verify_i2_sql_counterexamples.py /absolute/repository 3.51.3 /absolute/new-sql-evidence
python scripts/build_p1_schema.py --check
python scripts/audit_p1_schema.py --check
python scripts/audit_callsite_dependencies.py --check
```

Repeat with actual 3.53.1. The broad exit is currently **1**, with retained
stage-dependent assertions/setup failures. All original Task A 2,740 nodes are
included; no pass is manufactured from deselection/skip/xfail.

The archived `reproduction/distributions.py` builds a clean Git archive and both
artifact variants, installs each outside checkout for both runtimes and runs the
new I2 probe plus the **unmodified** original Access smoke. Invoke with repository,
executed commit, fresh output directory and `--runtime-root` containing the two
version-named library directories. Original command arrays/process results and
all four installed-file manifests are archived. This orchestrator exits **1**
while the original Access Transfer smoke remains unsupported. The installed I2
driver is also exercised by `tests/packaging/test_p1_distribution.py`.

## Review scope

Inspect actual product DDL/functions/connection registration, BINARY PK/FK/index
inventories, all global/scoped replay verbs and local reconstruction. Independently
rerun SQL refusals and lawful positives, real selected imports/primed replay,
poisoned-store recovery stops across consumers and installed artifacts. Review
the exact new skill guidance and test mechanism mapping in the implementation
record. Do not treat the inherited Task F design verdict as product acceptance.

I3–I5 and matching routing must replace both fences coherently before Transfer
is supported. I6 generalized wire and full I7/I8 validation/backup/Search remain
separate. The final Draft PR supplies publication HEAD/tree plus an unchanged
predecessor-file comparison; historical evidence and accepted ADRs are untouched.
