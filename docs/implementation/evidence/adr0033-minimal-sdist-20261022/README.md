# ADR 0033 minimal sdist implementation: Author evidence

This report belongs to implementation [PR B #138](https://github.com/TakashiSasaki/git-repo-db/pull/138),
stacked on owner-accepted design [PR A #135](https://github.com/TakashiSasaki/git-repo-db/pull/135).
It is Author verification, not independent review or complete release acceptance.
No merge, release or deployment was performed.

| Identity | Commit | Tree |
| --- | --- | --- |
| Accepted design / base | `18ba867d1c2f33c7d17939b2722d22a67139363a` | `57475b6fe473bc0cb691d9b7165414eb498b3893` |
| Frozen implementation executed locally and hosted | `03e1192f5228c9a1ca40dcef88271419c6828874` | `b5bdcb3cf5361a339ecdcea496c9ee32d1ab61ce` |
| GitHub temporary test merge for that source | `142f45ceae01603fe4a939399dffcb7ed4c1254c` | `b5bdcb3cf5361a339ecdcea496c9ee32d1ab61ce` |

A later evidence-only commit publishes this report. It is not another product
execution. Final PR HEAD/tree and any subsequent ordinary CI runs are recorded
in the PR description; this document does not invent its own containing SHA.
Main remains `cb532242c7aa86c6af5b6232b71c0906ea38f5c5`; #117–#134 were not changed.
The owner explicitly approved ADR 0033 before implementation. #137 preserves the
historical prerequisite inspection; it is not an independent review of B.

## Measured distribution boundary

| Artifact | Before bytes | After bytes | Result |
| --- | ---: | ---: | --- |
| Product sdist | 83,949,291 | 677,902 | **99.192486% reduction** |
| Unpacked regular-file bytes | 137,661,254 | 5,921,698 | All 155 product source/data files preserved |
| Sdist members | 3,875 | 159 | 3,716 prior non-product members excluded |
| Direct wheel | 762,725 | 762,725 | Complete before/after wheel contents unchanged |
| Sdist-derived wheel | — | 762,725 | Complete equality with direct wheel |

The old artifact was built from the clean accepted-design checkout before edits,
using the same prepared Python/Hatchling as the implementation. Its SHA-256 is
`2fa5d627c506370e792ee5fac7cbdec3ae952fc2468273c61aa2d73bc296b4cf`.
The reduced sdist SHA-256 is
`c72f86709f360b306daa1d39e2854e910f773e6acfce9f4bec7dae3396012e21`.
Both new wheel SHA-256 values are
`22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842`.
The hosted lightweight, Access and I5 builds also produced that same sdist hash;
this observed equality is not a requirement to align independent SQLite versions.

The 159 allowed files are 132 Python, 19 SQL, 2 JSON, 2 GraphQL product files,
`pyproject.toml`, `README.md`, the exact `.gitignore`, and generated `PKG-INFO`.
Hatchling 1.32.4 force-includes `.gitignore` despite the three-entry positive
selection; it is explicitly source-hashed, not an arbitrary generated-file
exemption. `PKG-INFO` must match the wheel's `METADATA`. No license file exists at
this base; no licensing decision or synthetic license was introduced.

Old top-level member counts included **3,396 docs, 253 tests, 43 scripts**, 16
agent-skill files and other developer inputs. The new artifact contains none of
those directories or verification ZIPs/logs. All remain in Git. Full before/after
member lists, member/source hashes, budgets and largest input sizes can be
reconstructed from the indexed receipts; [measurements](measurements.json) give
the compact summary. No timing speedup is claimed.

The fixed, reviewed initial limits are compressed **2 MiB**, unpacked **8 MiB**,
and **512 members**. They provide product-growth headroom, fail closed, and are
not automatically raised with a moving baseline.

## Actual test results and exits

Counts below overlap; do not add them as distinct product coverage.

| Verification | Actual result | Exit |
| --- | --- | ---: |
| Frozen focused archive/CI/cache cohort | **272 passed**, no failures/errors/skips | 0 |
| Related packaging suite | **57 passed, 4 failed**, no errors/skips | 1 |
| Frozen broad I5 cohort | **3,058 passed, 59 failed, 20 setup errors**, zero skips/xfail | 1 |
| Bounded source I4 / I5 | **217 / 29 passed**, exact node/JUnit/journal reconciliation | 0 / 0 |
| Installed I4 / I5, each wheel | **217 / 29 passed** on each artifact | 0 / 0 |
| Installed I2 / I3 probes, each wheel | Passed on each artifact | 0 / 0 |
| Original Access smoke, each wheel | Existing `I2_TRANSFER_UNSUPPORTED` refusal retained | 1 / 1 |
| Installed I5 distribution orchestrator | Nonzero because original Access smoke fails | 1 |
| Two full-dependency installed CLI/resource/schema probes | Both passed; all **155** installed file hashes equal wheel contents | 0 / 0 |
| Documentation unit tests | **8 passed** | 0 |
| Local allowlisted docs build | Passed with `--no-mermaid` placeholder mode | 0 |
| Ruff lint + format / SQLite-policy checker | Passed; policy **0 violations** | 0 |

The packaging suite was an iterative run with working inputs subsequently
committed unchanged; it is not a clean-tree release receipt. The 272-test focused
run, broad cohort and installed I5 driver used the frozen clean source commit.
Selected IDs, JUnit and journals reconcile for the focused and packaging runs,
as well as the source I4/I5/broad cohorts. Raw failures remain preserved.

Adversarial tests reject extra docs/tests/scripts/ZIP and unclassified package
members, missing SQL/JSON/GraphQL/root metadata, wrong source hashes, traversal,
duplicate members, symlinks/hardlinks/special files, exceeded finite budgets,
invalid RECORD entries and divergent wheel content/metadata. Independent builds
from a Git-free sdist succeed. Adding random evidence ZIPs, scripts, tests and an
unclassified root binary leaves the sdist's members **and archive bytes identical**.
These are Author counterexamples; a non-Author must still review independently.

## Known non-success comparison

The latest parent remains #133's source with unchanged product contents. Its
frozen evidence payload at branch commit
`4cd083b0f7295a2bbaa2597ef483af46e77f5463` has SHA-256
`e38171c16b5e58cfa222f281ea87406645ae85876cc05aa9f34f055749a76176`.
The local broad comparison uses its `local-i5/regressions.xml`; hosted comparisons
use its frozen nested hosted Access receipt. In each comparison:

- **79 baseline and 79 current non-successes; 0 additional, 0 resolved**.
- Node identity, phase, stage refusal and trace path/function sequences match.
- Four recorded frame line coordinates change only in the edited P1 distribution
  fixture. Raw line deltas are retained; exact line equality is not claimed.
- The packaging suite's four failing P5 nodes match the baseline Identification
  wire refusals. No product, Transfer, Identification, DDL or behavioral assertion
  was changed to obtain a passing result.

The passing bounded I4/I5 fixtures remove only their existing named fences in
throwaway databases. They do not establish production Transfer/Identification
support. Matching old failures also does not turn an execution into PASS.

## Environment, installation and preserved inputs

Local execution used **Python 3.12.14 / native SQLite 3.53.1**, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Hatchling was the locked **1.32.4**, uv **0.12.19**. Selected Python was retained
through dependency preparation, subprocesses and installed venvs. No separate
SQLite download, build, installation, binding swap or version matrix occurred.
Product WAL/STRICT/JSON/FTS/PRAGMA safety predicates were left intact.

The direct and sdist-derived wheels were installed into separate venvs, and their
import origins resolved under those venvs' `site-packages`, outside both source
checkouts. Full-dependency probes separately exercised console CLI doctor,
`python -m`, all packaged SQL/JSON/GraphQL hashes, generated JSON guard equality,
all P1 store initialization, integrity/foreign-key checks and original runtime
safety. I5's no-HTTP-dependency Access harness remains separate and unchanged in
meaning. Offline installation uses verified locked wheels and hash-required
requirements. Network guards and file-only Git transport remain active.

Product subtree `src/repo_catalog` is byte/object-identical to the base:
`84ebc206dce96520df17b7efab01bc1255ab76ea`. The old historical evidence subtree
was identical at execution (`c04e1ded38846906fa5288063527ca98d070fad1`), and the
Pages workflow blob remains `7d58ad4324976fdf7b23e0c1042f38fd5ad8ce7e`.
This publication adds a new evidence directory without rewriting prior evidence.
The wheel package mapping, all DDL, UDFs and product package data are unchanged.

## Hosted CI on the frozen implementation

| Workflow | Actual outcome | Meaning |
| --- | --- | --- |
| [tests 39872269754](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39872269754) | **success** | Lightweight sdist gate selected/passed; static/smoke/policy checks passed. Product pytest/packaging executions **0**; `development_checks_passed`, `full_acceptance=false`. |
| [Pages 39872269698](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39872269698) | **success** | Actual allowlisted site build/validation; deploy job **skipped**. |
| [Access 39872269603](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39872269603) | **failure** | Original focused 2,696 passed / 59 failed / 20 errors; broad and original installed-smoke failures retained. Source and broad 79-node comparisons show zero added/resolved non-successes. Both distribution-contract checks passed. |

The tests receipt is 81,861 bytes, SHA-256
`6d17db9a9958dc8add6c7921bc6766750fdd0fa5a7be7a36b50762c1a895b341`,
with 24 indexed payload members verified. The Access receipt is 1,662,499 bytes,
SHA-256 `37db5fbfd7d4b382fa616472a696441fbef5844c7b3467dabc00bb538dda2f02`,
with all 102 indexed payload members verified. Run/attempt, merge tree and source
bindings match. Hosted product jobs measured Python 3.12.15 / actual SQLite
3.53.1. No hosted full release acceptance or prior-PR success reuse is claimed.

## Evidence and reproduction

[raw-evidence.zip](raw-evidence.zip) retains 107 indexed payloads plus its internal
index: before/after manifests, complete source/member hashes, wheel bindings,
JUnit, journals, failing logs, comparisons, measured environments, installed
resource/CLI receipts, the measurement scripts and verified hosted receipt ZIPs.
[artifact-index.json](artifact-index.json) binds the complete archive and each
payload. Convenience hosted log views omit duplicate base64 receipt-data lines
and are labeled accordingly; complete decoded receipt bytes are retained.
[executions.json](executions.json) records exits and scope;
[coverage.json](coverage.json) records the unique ordinary-node coverage.

Use the selected existing Python; prepare dependencies online before offline
execution. Example commands for the frozen commit, with new empty output paths:

```sh
uv sync --locked --group dev --group docs --python "$(command -v python)"
uv run --no-sync python scripts/prepare_wheelhouse.py
uv run --no-sync python scripts/check_sdist_contract.py --build --output /absolute/new-contract.json
uv run --no-sync pytest tests/packaging -q --junitxml=/absolute/new-packaging.xml --journal=/absolute/new-packaging.jsonl
uv run --no-sync python scripts/verify_i5.py --output /absolute/new-i5 --workers 2
uv run --no-sync python scripts/verify_i5_distribution.py --output /absolute/new-installed-i5
uv run --no-sync python scripts/compare_i5_failures.py --current /absolute/new-i5/regressions.xml --baseline-archive /absolute/parent133-payload.zip --baseline-entry local-i5/regressions.xml --output /absolute/new-comparison.json
```

The raw measurement scripts contain run-specific workspace paths; adapt those
paths when reproducing. An early comparison attempted before the current XML
existed failed before comparison; the completed comparison returned 0. It was not
a product failure or a test rerun. No failure was overwritten or hidden.

## Remaining work and independent-review handoff

The ordinary inventory has **5,787** nodes. Combining local source, focused,
packaging and docs runs executed **3,419 unique ordinary nodes**; **2,368 ordinary
nodes**, one live and one benchmark node remain unexecuted. Installed copies
exercise overlapping behaviors, not additional source-node coverage. No full
release validation was requested or dispatched.

The 79 source non-successes, four P5 installed packaging failures and original
Access smoke refusal remain unresolved product-stage work. No new non-success
was found in the measured scopes. This does not prove all unexecuted behavior.

A non-Author should pin B's final HEAD/tree, verify this archive/index and
source-input preservation, independently challenge tar/RECORD/source hashes and
budgets, reproduce isolated installs/CLI/schema safety and examine both current
CI and inherited failures. Critical/High/Medium/Low independent findings are
**unassessed**, not zero. Do not use this Author report or #137 as a substitute
for that review. Approval, integration and release remain separate.
