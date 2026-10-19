# I5 final source distribution verification

**PASS.** Independently executed against frozen source
`20198151a6af2f8eefa43e85074307e9d77527b7`, tree
`74b164f111859c96396ca751a5c90df7e0a5f53a`.
`input-binding.json` records all 431 tracked scoped source/test/script/workflow/
lockfile/contract inputs with Git blob IDs and actual SHA-256; scoped diff was
empty. The earlier a54 acceptance runs/artifacts remain separate and unchanged.

Python 3.13.5 loads the actual SQLite 3.51.3 library using
`LD_LIBRARY_PATH=/workspace/i5-runtime`, with source ID
`2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
No runtime-version substitution, live product acquisition, real Catalog or
credential was used. All Git fixtures and Catalogs are synthetic temporary data.

Executed `/workspace/i5-runtime/python run_distribution.py`, `run_static.py`
and `run_dependency_complete.py`. Full argv, working directories and exits are
in `commands.json`, `static-audits.json`, `dependency-complete-commands.json`.
The standalone runners retain their explicit checkout/output path constants for
reproduction; change those paths when reproducing elsewhere.

## Results

Five independent scenario executions passed (counted separately from pytest):

1. Editable source checkout with the locked development dependencies.
2. Direct wheel, fresh venv, outside checkout, `python -I`, `--no-deps` install.
3. Sdist-derived wheel, separate fresh venv, outside checkout, `python -I`,
   `--no-deps` install.
4. Direct wheel, another fresh venv, complete declared dependencies installed
   from the local wheelhouse with `--offline --no-index`, `uv pip check` pass.
5. Sdist-derived wheel, another fresh venv, complete declared dependencies
   installed from that wheelhouse with `--offline --no-index`, `uv pip check` pass.

The two minimal environments prove the offline API surface needs no HTTP client;
the two dependency-complete environments complement those checks and include
httpx 0.28.1, httpcore 1.0.9, anyio 4.15.1, certifi 2026.7.22, h11 0.16.0,
idna 3.20 and typing_extensions 4.16.0. No network was used for these installs.

All environments execute production API assertions for Access history/approval
invalidation, real synthetic local-Git non-seed acquisition, separate Access
backup/reapproval/fork, strict Context registration, typed Exchange v4,
I2 Provider decimal/Node identities and genuine transfer, I3 different-seed
selective import, I4 qualified Dispositions, Query, Search fallback/rebuild, and
fresh paired backup/restore. Domain restore excludes Access/Operational and
Search local-check authority. Actual source/site-packages import origins are
recorded. These scenario probes are not a full installed pytest run and do not
claim live Provider transport or host power-loss coverage.

Source and both minimal installs have equal Core/Context/Operational/Search and
Access DDL fingerprints, 19 Context tables, and all six typed relation constants.
Dependency-complete probes repeat the original full installed behavior smoke.
Both wheel archives have equal member sets and byte-identical payloads; the
entire wheel files are also byte-identical. The final sdist includes the I5 source
additions and intentionally differs from the historical a54 sdist.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| direct wheel | 745869 | `2ec7c49a81734088ef6f15564c548448f7e79b1786ef86d12bf828c1dd3969cc` |
| final-source sdist | 29457395 | `c0bc97b8dde27e06f793ac321210794256ee644ce4948c5a68106e914c886a43` |
| sdist-derived wheel | 745869 | `2ec7c49a81734088ef6f15564c548448f7e79b1786ef86d12bf828c1dd3969cc` |

All eight final static commands passed: full `src tests scripts` Ruff lint and
format (including the I5 runner/tests); schema build check; P1 schema audit;
callsite dependency check; implementation boundary check; Context registration
audit; Access acceptance ledger audit. They ran in a bounded three-worker pool;
concurrent elapsed times are not sequential benchmarks. They did not regenerate
source. Baseline reports retain the exact unchanged DDL hashes, and final
`distribution.json` repeats those hashes.

No new product issue was identified. No pytest cohort was repeated by this final
packaging pass: five scenario executions and eight static commands are separate
from the full-suite and focused test-node totals. Historical Access requirement
11/15 reevaluation remains separate in the baseline distribution evidence.
No merge, release, P8 activation or real-data action is authorized by this receipt.
