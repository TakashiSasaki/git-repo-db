# Installed test-harness remediation — final source

Fresh final executions bind to source `93d9927ae801d5402aab0aa0c7c270eeab2809e6`,
tree `0c8a50e7cc23b98c6e7e2d1e6066077cbe8d203a`. The clean baseline remains
#143 `f5dc409429cdb69955b55e3c27a7ef3c163762fb`, tree
`3ef434120202c6fa4cfaa1152802784a1671d3ed`. These are local supporting Author
verification results, not independent acceptance or complete workflow acceptance.

## Root cause and correction

Both baseline direct-wheel and sdist-wheel I4/I5 invocations reproduced pytest
exit 2 with `ModuleNotFoundError: No module named 'tests'`. The runners copied
standalone test files while omitting their absolute-import test package and
support modules. No required test bodies executed in those baseline invocations;
product imports already resolved to installed artifacts.

The corrected runners stage the explicit `tests` support package outside the
checkout, including when receipts are requested under checkout `artifacts/`.
Explicit pytest config/root settings prevent the source `pythonpath=['src']`
setting from entering installed tests. Every pytest process checks its real
product import origins and complete installed Python/SQL/JSON hashes against the
wheel at session start and finish, plus test-support origins and effective
config/root. Only the copied offline network guard is on `PYTHONPATH`; no product
source path is supplied. Neither product wheel contains tests or harness scripts.
Collection, JUnit and journal identities/phases must match exactly, without
skips, xfails, substituted nodes, duplicate nodes or duplicate phases.

I2/I3 smoke setup now issues finite fixture authority and uses product-owned
transactions. Their original child-first registration, SQL declaration rebind,
Parent reports, duplicate/replay denial, FK and integrity assertions execute.
The Access smoke's initial provider/repository setup similarly has explicit
finite local authority; its original later assertions remain intact.

## Fresh final results

| Final-source execution | Direct wheel | Sdist-derived wheel |
| --- | --- | --- |
| CI-equivalent I4 | 217 PASS | 217 PASS |
| CI-equivalent I5 | 29 PASS | 29 PASS |
| I2/I3 installed smoke drivers | Both PASS | Both PASS |
| Historical installed safety cohort | 551 PASS | 551 PASS |
| Original Access smoke | Exit 1, intentional I6-C export refusal | Exit 1, intentional I6-C export refusal |

The complete historical 551-node identity set is preserved exactly in each
fresh safety lane: no missing or additional nodes, errors, skips, xfails or
xpasses, with successful process exit and exact collection/JUnit/journal
reconciliation. I4/I5 are included in that cohort and the counts overlap.
The CI-equivalent driver returns 1 solely for the two original Access smoke
failures at `application/exchange.py:397`, `PERMISSION_DENIED`. Its receiver
round-trip, Provider intake, query/Search and recovery assertions after that
I6-C guard remain unexecuted. No I6-B/C route or ordinary Transfer was enabled.

Both final wheels have SHA-256
`53f628499da0f47f72d8236e433bd0f02093202a638dbb1f657e3301891ec359`
(777887 bytes). The final sdist is 92582574 bytes, SHA-256
`1ab614a13cf92b583050af614c9600740ae6a42c7edd5211595dee906cb774e3`.
Both forms were built, installed and executed afresh on source 93d9927;
equal product bytes with the initial checkpoint do not replace these new runs.
The inherited large sdist remains separate from unintegrated ADR 0033/#142.

Both installed safety lanes use the environment's CPython 3.12.14 and SQLite
3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Source-to-wheel and wheel-to-installed file maps match. Exact normal schema and
fingerprint, both original SQL Transfer fence definitions, empty FK checks and
`integrity_check=ok` pass. No SQLite library was downloaded, installed, replaced
or tested as a second version. Concurrent parent ordinary execution excludes
sequential timing comparisons.

## Evidence and checkpoint separation

- [Final CI-equivalent receipts](final/compression-index.json): fresh final 93d9927
  build/runtime/import bindings, selected IDs, JUnit, journals, smoke failures,
  process exits and locked offline dependency binding.
- [Final installed safety evidence](../installed-safety/final/REPORT.md): fresh
  complete 551-node direct/sdist executions, full source/sdist inventories,
  file hashes, schema, SQL fences and integrity checks.
- [Preserved initial 423e345 report](initial-423e345-REPORT.md): the original report
  bytes are retained. `after/` and `../installed-safety/after/` remain unchanged
  initial-source executions, not final-source evidence. Their sdist hash/size
  belongs to that earlier source.
- `before/` retains the failed baseline. `diagnostic/` remains an explicitly
  intermediate, uncommitted harness probe against baseline product bytes.
- `source-tests/` retains the initial-423 harness/tool 33 PASS and separately
  labeled pre-freeze P1 packaging 2 PASS. They are not relabeled as new final
  source invocations; the parent's full final ordinary run is separate.

All compressed members have verified original/gzip SHA-256 and byte counts.
The standalone I4 CLI entrypoint was not separately invoked; the final I5 driver
actually executed all required I4 and I5 tests on both artifacts. This report
records local runs; hosted results and final PR publication bindings are reported
separately by the parent. No complete release or independent acceptance is claimed.
