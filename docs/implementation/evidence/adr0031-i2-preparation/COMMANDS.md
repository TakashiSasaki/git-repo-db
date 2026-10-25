# Task C commands and observed process outcomes

All paths/state are disposable. No branch or PR mutation was issued.

## Live inspection

```sh
git ls-remote https://github.com/TakashiSasaki/git-repo-db.git refs/heads/main refs/pull/116/head refs/pull/117/head refs/pull/118/head
gh api repos/TakashiSasaki/git-repo-db/pulls/116
gh api repos/TakashiSasaki/git-repo-db/pulls/117
gh api repos/TakashiSasaki/git-repo-db/pulls/118
git clone --no-hardlinks --no-checkout /workspace/git-repo-db /workspace/i2-preparation-20261021/repo
git -C /workspace/i2-preparation-20261021/repo remote set-url origin https://github.com/TakashiSasaki/git-repo-db.git
git -C /workspace/i2-preparation-20261021/repo fetch origin main pull/117/head pull/118/head
git -C /workspace/i2-preparation-20261021/repo checkout --detach 9ea69ba8804a368802457950601a5a4027174c52
```

Exit 0. API/ref snapshots are retained. Clone object reuse is not reuse of prior
test environments or results; fresh fetch confirms the exact remote objects.

## Runtime construction

Read-only copy of the independently fetched Task B amalgamation was compiled anew:

```sh
cc -O0 -fPIC -shared -DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_COLUMN_METADATA -DSQLITE_ENABLE_RTREE /workspace/i2-preparation-20261021/runtime3513/sqlite3.c -o /workspace/i2-preparation-20261021/runtime3513/libsqlite3.so.0 -lpthread -ldl -lm
/usr/bin/python3.13 -m venv --without-pip /workspace/i2-preparation-20261021/venv3513
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv --without-pip /workspace/i2-preparation-20261021/venv3531
```

Completed successfully; actual SQL source IDs and independently fetched official
release-page comparisons are retained. No dependencies or product package were
installed or changed for these stdlib-only SQL probes.

## Final proposal execution

```sh
python /workspace/i2-preparation-20261021/run.py
```

Both child commands exit 0; 133/133 diagnostic cases per runtime. Exact child argv,
cwd, permitted environment overrides, stdout/stderr and exit code are retained in
`minimum-command.json` and `newer-command.json`.

```sh
LD_LIBRARY_PATH=/workspace/i2-preparation-20261021/runtime3513 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace/i2-preparation-20261021/repo/src /workspace/i2-preparation-20261021/venv3513/bin/python /workspace/i2-preparation-20261021/baseline_controls.py baseline-minimum.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace/i2-preparation-20261021/repo/src /workspace/i2-preparation-20261021/venv3531/bin/python /workspace/i2-preparation-20261021/baseline_controls.py baseline-newer.json
LD_LIBRARY_PATH=/workspace/i2-preparation-20261021/runtime3513 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace/i2-preparation-20261021/repo/src /workspace/i2-preparation-20261021/venv3513/bin/python /workspace/i2-preparation-20261021/transaction_controls.py transaction-minimum.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace/i2-preparation-20261021/repo/src /workspace/i2-preparation-20261021/venv3531/bin/python /workspace/i2-preparation-20261021/transaction_controls.py transaction-newer.json
```

Each exits 0. SQL refusals are expected observations, not hidden process failures.
The original initial duplicate-trigger prototype exits 1 before SQL test cases;
its failed composed schema is retained. Final source hashes prove no source edit.

No product pytest, wheel/sdist build, installed product smoke or release validation
was executed during this preparation. Their exact future requirements are in the
implementation plan.
