Independent Task B evidence, 2026-10-21 UTC

Read REPORT.md first. artifact-index.json hashes the selected review artifacts.
The evidence bundle intentionally excludes venvs, cloned Git object databases,
disposable catalogs and extracted historical receipts. Original public receipts
are in the exact commits named in REPORT.md; their verified hashes are retained.

Execution layout:
  repo/        detached 32e5d4de67c0d436f7583d04e1cfd349b64b2bbd
  remediation/ detached 9ea69ba8804a368802457950601a5a4027174c52
  runtime3513/ independently downloaded and built SQLite
  venv3513-dynamic/ new /usr/bin/python3.13 venv, actual SQLite 3.51.3
  venv3531/ new Python 3.12.14 venv, actual embedded SQLite 3.53.1

provenance.json records the compiler/build and official source checksums.
Dependencies were installed into both venvs from:
  uv export --frozen --all-groups --no-emit-project -o locked-requirements.txt
  uv pip install --python VENV/bin/python -r locked-requirements.txt -e ./repo

The initial uv-managed 3.13.5 venv was NOT used for any test: it embedded 3.49.1.
Use the dynamic /usr/bin interpreter and verify actual SQL source IDs first.

Reproduce own probes with the relevant venv Python:
  counterexamples.py CHECKOUT OUTPUT.json
  exchange_probes.py CHECKOUT OUTPUT.json
For minimum runtime prepend LD_LIBRARY_PATH=.../runtime3513.

run_review.py contains exact lane commands and environment selections.
It references remediation-author-receipts/cohort.json, extracted from the
published #118 receipt bundle and independently verified before execution.
It records subprocess exit codes; its own successful orchestration exit does
not turn nonzero pytest/smoke exits into passes. Expected product failures are
fully retained in runs/*/output.log, JUnit, journal and receipt files.

reconcile.py independently compares selected/start/finish/JUnit multisets and
all three phases, retaining literal :: inside parameter suffixes. Collection
lanes intentionally execute zero tests. ordinary-not-executed-*.txt lists the
2,541 ordinary nodes per runtime not executed on the remediation tree.

exchange_probes.initial-row-serializer.py.txt is a preserved work-only harness
snapshot: its final JSON serializer rejected sqlite3.Row. The corrected external
probe converted rows to tuples and reran; no product source was changed.
