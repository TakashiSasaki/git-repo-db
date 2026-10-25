# Installed test-harness remediation

The mandatory installed I4/I5 collection regression is fixed and independently
reproduced on both distribution forms. This is supporting Author remediation
verification, not non-Author acceptance, release qualification, or a green
whole-suite/whole-workflow claim.

## Frozen inputs and observed failure

The clean baseline is #143 `f5dc409429cdb69955b55e3c27a7ef3c163762fb`,
tree `3ef434120202c6fa4cfaa1152802784a1671d3ed`. The corrected executable
freeze is `423e34504b2a9686c94f971f37c164449a28fe31`, tree
`cd93e1e226042e45b145b9c5eab605f9aa4d2d9d`. Later added evidence files do not
claim a new runtime execution. Both clean installed drivers built a direct wheel
and an independently rebuilt sdist wheel, installed into separate new venvs, and
ran from outside their checkout.

The actual baseline CI-equivalent `verify_i5_distribution.py` run returns 1.
Both direct-wheel and sdist-wheel I4 and I5 invocations return pytest exit 2:
`ModuleNotFoundError: No module named 'tests'` while importing
`tests.support.context_admission`. No required test body executes. Product imports
already resolve to the individual venv's installed `site-packages`; the failure
is omission of the **external test package**, not a missing product dependency.
The historical hosted #143 [Access run](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39895402410)
has the same independently inspected symptom; this local reproduction is a
separate execution.

The old runners copied each test into `test_installed_i4.py` /
`test_installed_i5.py` but omitted `tests/__init__.py`,
`tests/support/__init__.py`, `context_admission.py`, and `i6a.py`. Adding the
product checkout to `PYTHONPATH` or packaging tests in the wheel would conceal
that root cause. Neither was used.

## Correction and isolation

`scripts/installed_test_harness.py` stages those explicit support files as an
external `tests` package, records their hashes, and supplies a standalone journal
plugin. Both I4 and I5 drivers use an external temporary directory even when
the requested receipt directory is inside checkout `artifacts/`. Explicit
`pytest.ini`, `-c`, and `--rootdir` prevent inheritance of the source checkout's
`pythonpath = ['src']` configuration. The retained `PYTHONPATH` contains only the
copied offline `sitecustomize.py` guard, with no product code. Product code is
installed only from the relevant wheel; wheels are checked to contain no
`tests/` or `scripts/` tree.

Inside **each actual pytest process**, session-start and session-finish hooks
check the real product module origin against that venv's prefix, every loaded
product module path, the complete installed Python/SQL/JSON file-hash map against
the wheel, the effective pytest config/root, and loaded test-support origins.
The separately measured source-to-wheel and wheel-to-installed maps also agree.
This guards against a measurement subprocess importing the wheel while pytest
silently imports the source tree.

Collection, JUnit identities and journal starts/phases must reconcile exactly,
with the required 217 I4 / 29 I5 nodes, no duplicate nodes or phases, and no
skip/xfail/xpass. A successful collection or process exit alone cannot pass the
installed obligation. Tests reproduce the missing-support failure before staging,
verify corrected collection, reject staging under source, and reject a shadow
product imported from outside the installed venv.

The I2/I3 smoke scripts also had unbound direct mutations. They now issue finite
fixture authority for their declared Resource/provider sets and use the real
owned transaction. The I3 replay denial uses current policy in its own transaction
so revocation cannot invalidate an earlier transaction's successful leases. The
original child-first, SQL rebind, original Parent, duplicate, replay denial,
foreign-key and integrity assertions remain reached. P1's packaging fixture
copies the same external support package. The Access smoke's initial
provider/repository fixture similarly receives explicit finite authority through
an exact copied test-helper file, including under `python -I`; product import
paths are unchanged.

## Actual results

| Execution | Direct wheel | Sdist-derived wheel | Meaning |
| --- | --- | --- | --- |
| Baseline installed I4 | Collection exit 2 | Collection exit 2 | Missing `tests` package; required bodies unexecuted |
| Baseline installed I5 | Collection exit 2 | Collection exit 2 | Missing `tests` package; required bodies unexecuted |
| Corrected CI-equivalent I4 | 217 PASS | 217 PASS | Exact collection/JUnit/journal/phase reconciliation and in-process import binding |
| Corrected CI-equivalent I5 | 29 PASS | 29 PASS | Same independent checks |
| Corrected I2 and I3 smoke drivers | Both PASS | Both PASS | Original local authority/SQL/Parent assertions reached |
| Corrected original Access smoke | Exit 1 at I6-C export refusal | Exit 1 at I6-C export refusal | `application/exchange.py:397`, `PERMISSION_DENIED` |
| Complete historical installed safety cohort | 551 PASS | 551 PASS | Exact historical 551-node set, no missing/additional nodes or skips/xfails |

The 551-node cohort includes I4/I5 and overlaps the separate 217/29 runs; these
counts must not be added. Source harness/tool regressions pass 33 nodes on the
corrected freeze. A separate pre-freeze P1 packaging check passes both artifact
nodes (2 PASS); it is supporting evidence, not a replacement for the final
frozen artifact executions. The standalone `verify_i4_distribution.py` CLI was
not separately executed; the I5 driver actually executes all required I4 tests
on both artifacts through the shared corrected harness.

The original Access smoke is still unsuccessful, honestly reflected in the
CI-equivalent driver's overall exit 1. Its first failing location changed from
unbound Context fixture setup to the intentional I6-C `ExchangeService.export_package`
guard. Its later receiver round-trip, Provider intake, query/Search and recovery
assertions are retained but unexecuted. No permissive fallback, synthesized
Provider declaration, SQL fence removal, I6-B/C implementation, skip/xfail,
assertion deletion, or exception suppression was introduced. The separate
551-node successful cohort does not turn this Access failure into PASS.

Both final wheels have SHA-256
`53f628499da0f47f72d8236e433bd0f02093202a638dbb1f657e3301891ec359`
(777887 bytes). The sdist is 92581810 bytes, SHA-256
`798853b16eabd25ba59e84dab3e37e9a8f9a32cf8b68df93105efe10b8d07928`.
The large inherited sdist is recorded without integrating the independent ADR
0033/#142 packaging series. Complete frozen build-source and sdist-member
inventories are in the installed safety receipts.

Both safety lanes measure CPython 3.12.14 and the environment's actual SQLite
3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
No SQLite download, replacement, or version matrix was used. Exact Context schema
and fingerprint, both original SQL Transfer fence definitions, empty
`foreign_key_check`, and `integrity_check = ok` pass on both installed artifacts.
No normal Transfer route is enabled. Concurrent parent ordinary-suite execution
means these timings are not a sequential performance comparison.

## Evidence and remaining acceptance

- `before/`: unchanged failed baseline logs, runtime/build bindings, process exits,
  requirements, wheelhouse lock binding, and JUnit.
- `after/`: frozen corrected CI-equivalent raw logs, full product import/hash
  receipts, exact collected IDs/JUnit/journals, and actual smoke failures.
- `../installed-safety/after/`: frozen 551-node direct/sdist executions, complete
  source/sdist inventories, source/wheel/installed hash maps, SQLite/schema/fence
  measurements, and exact historical-node comparisons.
- `source-tests/`: actual source harness/tool 33-node logs/JUnit/journal and the
  separately labeled pre-freeze packaging 2-node run.
- `diagnostic/`: intermediate pre-freeze harness probes against the unchanged
  baseline product, including an I2 `ADMISSION_TRANSACTION_REQUIRED` diagnostic
  before its transaction-owner correction. These are explicitly diagnostic and
  not final frozen-harness acceptance.

Every compressed directory has an original/gzip SHA-256 and byte-count index.
The adapted safety driver and diagnostic/archiving helpers are retained as
`.py.txt`; product artifacts, venvs and build trees remain external. Earlier
frozen Author evidence is unchanged. Corrected hosted workflow execution and
independent non-Author review remain the parent's publication/handoff work; no
hosted corrected PASS is asserted here.
