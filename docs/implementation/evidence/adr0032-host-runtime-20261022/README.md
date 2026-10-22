# ADR 0032 hosted product runtime establishment

PR [#133](https://github.com/TakashiSasaki/git-repo-db/pull/133) is stacked on
PR #132 at `a022dd3efb9c8116cf9dc0abc13ab1d5bbc88e37`.
Final source HEAD: `f16e5b1713bde9a2f18263a25397c4b450fd5773`;
tree: `6bfa580baafa9f6a117b7a0b610c4e65cd031b86`.
Hosted merge `b5f5026b07826b551cbd35ec39ac0ef3ca214a99` has the same tree,
with parents PR #132 and this feature HEAD. This separate evidence branch is
publication only; it does not claim another execution or update the source PR.
No merge, prior-PR mutation or frozen-evidence modification was performed.

## Result and actual environment

The host environment incompatibility is removed. Both product-runtime jobs use
the complete checksum-bound python-build-standalone CPython **3.12.15**, release
**20261021**, on Linux x86_64. Actual loaded SQLite is **3.53.1**:

```text
2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9
```

Selected executable: `/home/runner/work/_temp/product-python/python/bin/python`;
resolved base: `/home/runner/work/_temp/product-python/python/bin/python3.12`.
Dependency execution uses the checkout's `.venv/bin/python`; distribution checks
use their separate venv executables. All eight Access runtime-binding receipts
retain that same resolved base, source ID, compile options and binary digest:

```text
0a97d28d3635c7dfd143de6d00b09c0cb382249c020b28ee33fb4002db1efb9c
```

`_sqlite3` is built into this interpreter. No separate SQLite library is mapped;
loader override variables are null in the product jobs. Whole-Python archive
SHA-256: `6d7521138fd33afddc1ccd08abb007d9a2829e38117c2576f9efdc0ec73ce772`.
The manifest selects a complete Python distribution, with no chosen-SQLite
equality gate. No SQLite component was separately downloaded, built, installed,
replaced or loaded by an override. Product source, WAL predicates, DDL,
fingerprints and domain assertions are byte-unchanged from PR #132.

Original Access and P1 runtime factories pass, as do STRICT, JSON, FTS5 trigram
and WAL probes. Probes run before dependencies, after initial and docs sync,
after execution, and inside both actual direct/sdist artifact venvs. The latter
invoke installed `site-packages` factories. Outside-checkout origin, installed
file hashes, domain smokes and offline network guards remain independent checks.

## Hosted final results

| Check | Result |
| --- | --- |
| [tests run 39799299296](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39799299296) | **success**, both jobs complete |
| Independent stdlib-only SQLite policy job | 0 violations; 31 detector tests and 4 Python-selection tests pass; no dependency preparation |
| `offline` development job | static/lint/format, FTS/doctor, schema and reconciliation pass; `development_checks_passed`, `full_acceptance=false`; pytest/packaging lanes are not selected |
| [Access run 39799299209](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39799299209) | **failure**, inherited domain failures retained |
| Original Access pytest targets | 2,696 passed / 59 failed / 20 setup errors; 2,775 nodes; exit 1; no skips |
| Broad offline regression cohort | 3,058 passed / 59 failed / 20 setup errors; 3,137 nodes; exit 1; inputs unchanged; exact JUnit/journal reconciliation passes |
| Bounded source I4 / I5 | **217 / 29 passed**; exact selected/JUnit/journal phase reconciliation passes |
| Direct wheel | build/install, runtime binding, installed file hashes, I2/I3 probes, I4 217 and I5 29 pass; original Access smoke fails at inherited Transfer fence; exit 1 retained |
| sdist-derived wheel | same independent successful checks and inherited Access smoke failure; exit 1 retained |
| Original distribution verifier | both direct and sdist-derived wheel attempted; both pass runtime checks and fail inherited `I2_TRANSFER_UNSUPPORTED`; exit 1 retained |
| Ownership/schema/boundary/registration audits, docs build, formatting, final runtime identity | pass |
| Access ledger reconciliation | fails closed because JUnit contains failed/error nodes; no acceptance JSON or success is fabricated |

The lightweight policy job's bootstrap setup-python is Python 3.12.15 with its
actual SQLite 3.45.1 and setup-python's own loader path. It runs stdlib
configuration and negative-fixture tests only. It is not a product runtime test;
both jobs that execute product checks use the selected 3.53.1 environment.

## Baseline and failure attribution

PR #132 final [tests run 39795283604](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39795283604)
was successful development static/smoke CI on Python 3.12.15 / SQLite 3.45.1.
It executed zero pytest nodes and no packaging lane, so its green result never
established product runtime compatibility. Its independent policy job passed.

PR #132 [Access run 39795283696](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39795283696)
correctly failed `access_schema.require_runtime()` with `SQLITE_RUNTIME` before
pytest collection or execution. Both installed artifact smokes also refused
SQLite 3.45.1. Ledger reconciliation then failed for missing pytest evidence,
and docs were skipped. Ownership audits and formatting passed. These are runtime
environment refusals and consequent unexecuted work, not evidence of 79 executed
functional failures. No product guard was weakened to remove them.

The new hosted broad run preserves all **79** frozen functional non-successes:
**0 added, 0 resolved**, same nodes, phases and stage refusals. Historical I4
comparison retains frame paths/functions; 27 historical line-number shifts had
already occurred by PR #132. A separate exact comparison with PR #132's frozen
`payload.zip` member `run-3594f47/i5/regressions.xml` verifies all full frame
records, **including line numbers**, unchanged. Transfer/identification-wire
support and downstream I6/I7 work remain unfinished. Installed original Access
smokes fail in `ProviderAcquisition._preflight_units` with
`I2_TRANSFER_UNSUPPORTED`, not in a SQLite guard.

One new infrastructure-test failure occurred at intermediate `d0b1192`, tests run
39798601683: its source-ID negative fixture inherited the bootstrap loader path
and reached the separate loader refusal first. Final `f16e5b1` isolates that
mocked fixture; all original assertions and the real loader rejection remain.
The final hosted four tests pass. Its failed raw log is preserved. No unresolved
new SQLite-policy/environment regression was found.

## Coverage, local validation and independent review

Final local CI/tool verification passes **289 nodes and 57 subtests**, exit 0,
with JUnit, journal starts and successful finish retained. This repeats the prior
285-node cohort and adds the four environment tests. Its existing unittest
subtest call-event representation is not claimed to pass strict one-call-per-node
phase reconciliation. Hosted broad/bounded cohorts do pass that reconciliation.
Local final direct/sdist distribution checks independently reproduce the hosted
outcomes. Whole-tree Ruff lint and formatting pass; policy reports 0 violations.

Of **5,742 ordinary nodes**, final hosted source plus policy checks cover 3,172
unique nodes; 2,570 ordinary nodes remain unexecuted on the host. Combining the
frozen final hosted source run with the disjoint final local 289-node tool run
covers 3,426 unique nodes; **2,316 ordinary nodes remain unexecuted** across this
task. One live and one benchmark node also remain unexecuted. The exact remaining
list is `unexecuted-ordinary.txt` in the payload. Installed copies overlap source
tests and do not count as additional ordinary-suite coverage. The offline helper
ran inventory only; its full disjoint `--execute` cohorts and full release
acceptance were not requested or claimed.

A local broad development trial began at `c83a783` while tooling follow-up was
still being edited. It retained the same 79 failures, but reports
`inputs_unchanged=false` and is **excluded from final frozen acceptance**. Its
raw receipts are preserved. Final source claims use the unchanged-input hosted
`f16e5b1` execution instead.

The separate non-author agent's [independent review](independent-review.md) and
[machine report](independent-review.json) cover source guards, complete-Python
selection, child/actual artifact venv identity, offline protections, no reduced
targets/assertions, raw hosted receipts, failure comparison and omissions.
The source implementation has no unresolved material review finding. Evidence
publication is separately bound to the reviewed source commit; it is not a test
rerun. Repository skills used include `ci-final-tree-verification`,
`efficient-repository-investigation` and `lessons-to-skills`; the first records
the verified whole-Python selection and built-in-extension identity procedure.
Environment inspection used the cloud-environment-runtime skill; Firecrawl
research reinforced that a newer Python version alone does not establish SQLite
support. The manifest release/digest and actual hosted measurements are decisive.

## Evidence and reproduction

[results.json](results.json) is the machine summary.
[payload.zip](payload.zip) preserves raw baseline logs, final hosted receipt ZIPs
and job logs, local tests/distributions/inventory, exact comparisons, source/tree
binding and independent-review evidence. [artifact-index.json](artifact-index.json)
binds every outer member by bytes/SHA-256. Each hosted receipt ZIP also has its
own index and execution binding; validate both levels before using results.
The final Access receipt contains 101 indexed members, 1,632,586 bytes, SHA-256
`511732209c4fda5c84a61b470ea4f56f271a6bbcb3c5e1842680dd0c6c1ff4b6`.

Artifact blob download returned HTTP 403; authenticated job-log retrieval and
the indexed log receipt fallback supplied verified raw evidence. Transient
signed download URLs are excluded. Earlier API status snapshots are labeled as
such; `final-workflow-runs.json` and completed check results establish final
workflow conclusions. No protection/ruleset change, merge, release or deployment
was performed. Existing PR #129–#132 heads and frozen evidence remain unchanged.

The final source's workflows reproduce hosted selection and all executed checks.
For local evidence, use the environment's explicitly selected compatible Python,
prepare locked dev/docs dependencies and wheels, then execute:

```sh
uv sync --locked --group dev --group docs --python "$CI_PRODUCT_PYTHON"
uv run --no-sync python scripts/prepare_wheelhouse.py
uv run --no-sync python scripts/verify_i5.py --output NEW_EMPTY_DIRECTORY --workers 2
uv run --no-sync python scripts/verify_i5_distribution.py --output ANOTHER_NEW_DIRECTORY
uv run --no-sync python scripts/verify_i5_offline.py --output INVENTORY_DIRECTORY
```

Preserve expected nonzero domain outcomes. These commands do not install a
separate SQLite, authorize live acquisition or constitute release acceptance.
