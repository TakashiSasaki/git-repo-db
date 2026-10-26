# Same-source Access retry over the independently reviewed repair

Source `55759a2ac02512a17f4ed637c49caccf34ff4763`, effective tree
`7a28c0626a5b9ca0da613d224b4f939051f24d3d`.

[Run 40282065961 attempt 1](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40282065961/attempts/1)
**failed** while preparing a locked wheel: TLS UNEXPECTED_EOF_WHILE_READING.
No wheelhouse manifest was published; preflight/scoped Access suite were skipped
and dependent acceptance failed. Its independently verified broad reconciliation
was useful partial evidence, not a successful CI run. The exact wheel URL was not
logged. Prior reviewer failure statements remain unchanged.

The owner-authorized same-source failed-job rerun,
[attempt 2](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40282065961/attempts/2),
**succeeded**. Job `121440185145` completed every required step successfully.
Actual temporary merge `c1394bb494a678fce1da41d86ea6149afb87a4ba` has parents
PR186 base `049cc13b129223239cf987590a70c1394e035524` and the repair HEAD, and
its tree exactly equals the reviewed repair tree (GitHub commit API checked).

- Scoped: 947 selected/executed, all passed, exact Counter match.
- Broad: 1,851 selected/executed, exact Counter match; 1,808 passed, 23 failure
  plus 20 error outcomes. All 43 are inherited Transfer refusals; strict comparison
  has zero new/changed/added failures, missing/unexpected nodes or unexpected skips.
  Actual pytest exit is 1 (`RECONCILED_FAILURES`), not all tests passing.
- Both wheel/sdist-wheel installed smoke checks passed; 29/29 I2-I5 processes
  exited zero; sdist membership/budgets and wheel equivalence passed. Offline
  inventory is collection evidence, not an extra full-cohort execution.
- Runtime preflight and final identity audit passed on Python 3.12.15 / actual
  loaded SQLite 3.53.1. No source, TLS validation, route, timeout or SQLite change.

Summaries retain binding and raw-log/index hashes. The compressed filtered logs
preserve diagnostic evidence; originals and checksum-verified receipt sets remain
under ignored `artifacts/pr192-access-ci/`. `counts-and-history.json` distinguishes
105 indexed payload members plus the index from the 106 extracted files in
attempt 2 (attempt 1: 38 plus index = 39). No historical FAIL is rewritten.

This records scoped repair-source CI, not full release acceptance or approval of
an untested final PR186 integration. Final integration CI/review are separate gates.
