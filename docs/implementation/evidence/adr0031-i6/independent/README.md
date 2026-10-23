# Independent I6 design review evidence

Read [REPORT.md](REPORT.md), [all requirements](MATRIX.md), and
[findings.json](findings.json). Review target is #134 at Author commit
`418ee68046fdfd03a0e84cc840e5d52fce176b81`, tree
`476d32923c9be5e3b60e4e17c8828e3646611c43`. Only this new evidence directory is
added by the review. Source, tests, DDL, accepted ADRs, historical evidence and
Author branches are unchanged.

Use the selected environment's existing Python 3.12+ and actual SQLite, following
ADR 0032. Do not install an additional SQLite engine or bypass a safety check.
The recorded run used CPython 3.12.14 / SQLite 3.53.1. In this environment the venv
is `/tmp/task-b-venv`; this path is an execution location, not a required runtime.
From repository root, dependency preparation was:

```sh
UV_CACHE_DIR=/tmp/task-b-uv-cache UV_PROJECT_ENVIRONMENT=/tmp/task-b-venv uv sync --locked --group dev --group docs --python /opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python
```

The exact preexisting interpreter was selected explicitly; no Python or SQLite
replacement was prepared. Dependency setup is separate from product execution.
To reproduce in a new environment, select that environment's Python explicitly
and record its own identities. Keep new receipts outside the historical `raw`
directory. Commands below abbreviate the venv Python as `python`:

```sh
python -m pytest tests/integration/p3/test_transfer_admission.py tests/integration/p3/test_transfer_sql.py -q -o junit_family=xunit1 --junitxml=/tmp/review-focused.xml --journal=/tmp/review-focused.jsonl
python -m pytest tests/integration/p3/test_transfer_admission.py tests/integration/p3/test_transfer_sql.py --collect-only -q > /tmp/review-focused-nodes.txt
PYTHONPATH=src python docs/implementation/evidence/adr0031-i6/independent/review_probes.py
PYTHONPATH=src python docs/implementation/evidence/adr0031-i6/independent/wire_probe.py
PYTHONPATH=src python docs/implementation/evidence/adr0031-i6/independent/sql_probe.py
python docs/implementation/evidence/adr0031-i6/independent/verify_evidence.py
```

The three independent probe scripts only mutate disposable in-memory SQLite
connections. They verify the exact composed schema first; any positive Transfer
fixture then removes exactly the two fences on that disposable connection.
No product SQL file, persisted catalog or normal fence is changed. The normal
refusal probe retains both. SQL trace payloads are synthetic fixture values.

| Artifact | Meaning |
| --- | --- |
| `raw/focused.log`, `.xml`, `.jsonl`, `focused-nodes.txt`, `.exit` | Actual one-run 246 pytest cases; 29 I5 + 217 I4, both inherited fixture parameters |
| `raw/focused.execution.json`, `focused-summary.json` | Source/runtime/process binding and exact node/phase reconciliation |
| `raw/review-probes.json` | 5 independently authored scenarios; includes current A1/B1/C1 behavior and true SQL rollback |
| `raw/wire-probes.json` | 15 existing domain/codec checks; not v5 execution |
| `raw/sql-probes.json` | 5 schema/fence states plus deferred COMMIT/ROLLBACK diagnostic, full trace |
| `raw/environment.json`, `input-manifest.json` | Measured interpreter/SQLite/options/PRAGMAs/UDFs/fingerprint and exact runtime/test/build input hashes |
| `raw/author-*`, `parent-pr133.json`, `task-b-*`, `remote-refs.txt`, `duplicate-pr-search.json` | Live API/commit/CI/comment/ref and initial duplicate-query snapshots |
| `raw/harness-corrections.txt` | Reviewer fixture/setup errors, separate from product outcomes |
| `raw/validation.json`, `artifact-index.json` | Evidence checks and SHA-256/length inventory; index excludes itself and generated validation receipt |

Probe sources were formatted/linted before the retained successful final runs.
The retained focused suite ran before evidence prose creation; unchanged product,
test and build input hashes bind it to the Author source. Evidence additions
change the review publication tree and full sdist inputs; **no new distribution
build/test is claimed**. Node collection is collection only; JUnit/journal/exit
prove actual execution independently. No wrapper profile or release receipt is
claimed. The scripts are evidence utilities outside normal `tests/` selection.

Unexecuted: future v5/AdmissionContext/lease/route tests T01–T27 as a completed
implementation suite, broad/all-79 regression reconciliation, installed wheels,
sdist-derived wheel, actual Provider traffic, real catalog operations, Recovery,
Search and normal Transfer end-to-end. The Author's positive design vectors and
historical #130 two-engine/distribution receipts remain specifications/history.
They are not this review's execution results.
