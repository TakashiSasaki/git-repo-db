# Reproduce this Author integration verification

Use the full published history; freeze executable/test input commit
`fb5d7b5a0c4b92c8a282daac154e66fa6d361e64` before running. The final evidence/prose
commit has separately checked input invariance and is not a new product run.
Use an independent checkout, fresh disposable DB/build/output directories, the
environment's selected Python and its actually loaded SQLite. Do not obtain or
swap another SQLite or dispatch Release.

Dependency preparation used `UV_PYTHON_DOWNLOADS=never`, a writable workspace
`UV_CACHE_DIR`, `uv sync --locked --group dev --group docs`, followed by
`scripts/prepare_wheelhouse.py --output /workspace/task-b-wheelhouse`. All48
selected wheel hashes are bound to `uv.lock`. Preparation is distinct from
offline product execution.

`source/tools/` contains lossless `.py.txt` transport of the executed driver,
observers and postprocessor. `tools-transport-and-adaptations.json` records their
historical hashes and exact workspace-binding changes. Restore `.py` suffixes
outside the checkout; adapt only venv/root/temp/cache/wheelhouse/output bindings
for a new environment and record new helper hashes. The full invocation was:

```sh
.venv/bin/python /workspace/task-b-run/tools/run_source.py \
  --root /workspace/task-b-integration \
  --out /workspace/task-b-run/source-full --mode full --workers 4
```

The separate diagnostic uses `--mode diagnostic` and a different empty output
and basetemp. Full and diagnostic totals are never added. The retained
`independent_compare.py.txt` verifies the historical154 execution hashes against
actual154 Git blobs before comparing node/phase/outcome/actual exceptions/refusals
and frames. It checks assertion-statement AST entries only for the diagnostic;
this is not thread/child/subexpression coverage. Read each execution JSON and
raw journal/JUnit rather than interpreting exit1 as an interrupted or passing run.

The source observer files are byte-identical historical probes; the full driver
loads `broad_receipt`, while diagnostic additionally loads `statement_trace`.
The comparator is postprocessing only. Its historical blob target/summary label
was adjusted152→154 during the full run; it was never loaded by that execution.
Before/after helper inventories preserve this difference, while actual driver,
observers and product/test inputs stay unchanged.

`i6/REPORT.md` and its transport manifest cover fresh38/61/13/208/34/33 and202
source lanes. `distribution/` retains exact build/install commands, all member
manifests, metadata and RECORD, archives, separate site-packages origins,
Journals/JUnit and omitted source nodes/files. `c0/` retains the real closed ZIP
calibrator, five exact ZIPs and independent direct overflow control. All probe
code remains attributed; rerunning it does not become independent test design.

`ci-initial/` records exact published feature/test-merge/tree and terminal
GitHub run outcomes. Its receipt verifier uses supported actual job logs and
strict hashes/index/binding; all artifact-download Forbidden responses and
parser failures remain separately recorded. Twelve BOM parser controls exercise
the documented prefix-only adjustment. Final evidence-HEAD CI is externally
bound in the PR body/final handoff to avoid a committed self-hash.

Check the root `ARTIFACTS.json` against delivered bytes, then restore compressed
raw artifacts according to `TRANSPORT.json`. ORIGINAL nested indexes describe
pre-transport paths and are preserved as provenance; the current root index is
authoritative for this delivery. Never execute a received archive or blindly
extract an unvalidated tar/ZIP. No synthetic DB, cache, venv or authenticated
traffic is included.
