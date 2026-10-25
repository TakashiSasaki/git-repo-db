# Independent publication distribution verification

**Installed verification reproduces two contract-blocking Medium findings.** The
packaging/source/installed-byte checks themselves pass. The honest original Access
smoke still fails at the unconnected Exchange export; its downstream assertions
remain unexecuted. These results are scoped independent review evidence, not
Release acceptance or Transfer activation.

## Frozen inputs and actual environment

All three artifacts were built from a new `git archive` of publication HEAD
`ef787a5ff8b13f118d6bf5107c7338f43fde56dc`, tree
`a3ed2628a98db134bdc65d13da905f5ddf25e972`. This is the actual publication,
not the Author's earlier `a354348` build snapshot. The new review evidence and
parallel work never entered this frozen build source. `execution-binding.json`,
`git-archive-hash.json`, `full-build-source-inventory.json` and
`git-tree-and-metadata-audit.json` bind every one of its 6,349 Git file paths and
content hashes. All are regular/executable blobs; no source path is omitted.
No #144/#147 or other sibling branch was imported.

The already selected CPython 3.12.14 interpreter created separate direct and
derived virtual environments, plus separate minimal no-HTTPX smoke environments.
Every invocation measured its own actual Python, `_sqlite3` origin, SQLite
version/source ID, compile options, STRICT/JSON functionality and connection
PRAGMAs. All load SQLite 3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
No SQLite was downloaded, built, swapped or selected by exact-version assertion.
The 48 locked dependency wheels were hash-verified against publication `uv.lock`
and installed offline by direct URLs with `--no-index --no-deps --require-hashes`.
Preparation is distinct from tests. See `wheelhouse-preparation.log`,
`wheelhouse-manifest.json` and each exact requirements/install receipt.

## Artifact and installation results

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Direct wheel | 790,488 | `6b3a865b90673b9626ad120ecf106064d2211657d2d78a68fb6568a52a8aba71` |
| Publication sdist | 137,096,882 | `1f83f0ad52deedadde5a43b0ad066e61147df371ee31177564916409108c0422` |
| Sdist-derived wheel | 790,488 | `6b3a865b90673b9626ad120ecf106064d2211657d2d78a68fb6568a52a8aba71` |

`artifacts.json` records actual cloud paths; artifacts remain outside the Git
checkout under `/workspace/i6b-distribution-work/`. The sdist is intentionally not
committed as a >100 MB Git blob. Its complete member hashes/bytes/modes are in
`sdist-all-members.json`. All 6,349 original files retain exact content in the
6,350-file sdist; the sole additional file is `PKG-INFO`.

Both wheels have exactly the same 164 members, including every byte of metadata,
entry points and RECORD. All 160 product files / 6,022,477 bytes equal the frozen
source, with no product-file filtering by extension. Complete member inventories,
raw METADATA/WHEEL/entry-points/RECORD and package metadata checks are saved.
Archive RECORD has duplicate-free exact member coverage and every declared
SHA-256/size recomputed. Installed RECORD independently checks all 169 installed
rows, including generated launcher/installation metadata; every declared digest
and size verifies. Raw installed rows and actual paths are included in each
runtime receipt. This verifies the current packaging policy without importing
unintegrated #144 behavior.

Each pytest collection and execution checks actual product imports at start and
finish, every loaded product module inside that invocation's site-packages,
all product bytes, an explicit external pytest config and harness root. The
harness is outside both source checkout and frozen source. Tests/scripts/support
were copied from the frozen source, retaining the original offline fixture and
network guard. Child smoke runs also install the same explicit offline guard.
Before/after runtime measurements verify unchanged products and RECORD.

## Actual executed lanes

The following are **separate invocations in each form**. Counts overlap; no sum is
a complete-suite result. Every lane saves collection, selected IDs, JUnit,
append-only phase journal, command/cwd/process exit and actual import receipts.
Reconciliation confirms exact selected/JUnit/journal-start identity, unique
setup/call/teardown phases and a completed process; all rows below have zero
skips, xfails, xpasses and collection errors.

| Lane | Direct wheel | Derived wheel |
| --- | --- | --- |
| Inherited safety (including I4 217 and I5 29) | 626 PASS, exit 0 | 626 PASS, exit 0 |
| Author ordinary v5/planner tests | 212 PASS, exit 0 | 212 PASS, exit 0 |
| New independent probes (wire 157 / planner 28 / admission 19) | 204 PASS, exit 0 | 204 PASS, exit 0 |
| Unchanged Author external probes, separately attributed | 34 PASS, exit 0 | 34 PASS, exit 0 |
| Separate independent V07 MappingSupport alternatives | 4 PASS, exit 0 | 4 PASS, exit 0 |
| New expected-refusal counterexamples (digest 30 / work 3) | 33 FAIL, exit 1 | 33 FAIL, exit 1 |
| Unchanged original Access smoke, corrected trace harness | 1 FAIL, pytest exit 1 / child exit 1 | 1 FAIL, pytest exit 1 / child exit 1 |
| Installed `repo-catalog doctor` | exit 0 | exit 0 |

The exact safety roster includes 217 nodes in `test_transfer_sql.py`, 29 in
`test_transfer_admission.py`, and the remaining 380 nodes listed in each
`*-safety-selected.txt`. `targets.json` records all target paths.

The independent probe scripts are copied byte-for-byte from the wire/planner/
admission review agents, without importing Author test helpers for the wire and
planner cases. Admission reuses attributed disposable synthetic setup while
executing real authority/transaction boundaries. Probe input hashes are retained
in `independent-probe-inputs.json` and `counterexample-probe-inputs.json`.
A further **separate source invocation** executes the unchanged Author external
34: 34 PASS, exit 0, with exact selected/JUnit/journal reconciliation, original
offline fixture and explicit source import/config assertions. All 160 actual source
product files equal the publication product inventory before and after the run.
See `source-author-extra-{execution,inputs,imports,processes}.json`, its original
collection/JUnit/journal and `run_source_author_extra.py.txt`. This is not inferred
from the installed runs.

The additional four V07 probes independently preserve two distinct MappingSupport
claim/target alternatives and reject target substitution, missing or extra support
fields. They run unchanged in each form; their hashes, isolated imports and
separate receipts are in `resolved-wire-*` / `*-resolved-wire-*`. They do not alter
the earlier 204-node roster.

The external Author 34 reuse frozen publication vectors, independently validating
saved input hashes and byte results. They retain Author authorship and do not
replace the new independent probes.

## Reproduced Medium findings

1. **M01, planner work budget:** after already-valid input is independently
   established, each `max_work` 0, 1 and 17 invocation still parses 1,501 embedded
   JSON strings / 314,392 characters and reports 26,041 work units over 1,001
   input rows before refusing. All three bound assertions fail on both wheels.
   Raw observation values occur in the counterexample log/JUnit failure payloads.
   This reproduces the planner review's R04 budget finding. Finite eventual
   termination does not establish the configured operation-work boundary.
2. **M02, received-data digest:** duplicating or permuting selection coordinates
   changes the actual received canonical-dictionary SHA-256, yet all three
   dict/string/UTF-8 carriers are accepted with the unchanged earlier digest.
   Thirty expected `DIGEST_MISMATCH` assertions fail on each wheel across five
   selection coordinate categories. This reproduces the wire review's R03
   finding; no sender-authentication claim is needed for the content-consistency
   violation. The independent positive 157 wire tests remain separate PASSes.

No product fix is included. Acceptance requires correcting those contracts and
independently rerunning the exact counterexamples, positive lanes and relevant
wide regression comparisons. They prevent declaring all I6-B target conditions
satisfied. Root's combined review owns final severity/ID consolidation and I6-C
readiness.

## Original Access smoke and honest unsuccessful attempts

The smoke literal is extracted through AST from the frozen
`scripts/verify_access_distribution.py`; its literal hash and exact unchanged
text, fixture authority, launcher, wrapper and guard hashes are saved. Minimal
venvs contain product + pytest/jsonschema dependencies and **no HTTPX**. Collection
therefore succeeds; there was no jsonschema bootstrap error in these runs.

Both corrected v2 smoke children reach original line 187:
`ExchangeService(producer).export_package(...)`, then raise
`AdmissionRefused: PERMISSION_DENIED` from installed
`application/exchange.py:397`. The unchanged downstream format-v4, import,
receiver and Provider assertions are unexecuted. Source-line traces and the reach
status of all 54 literal `assert` syntax nodes are retained in each
`*-original-smoke-v2-assertion-reach.json`; 26 have line events, with later
assertions unreached. Unexecuted conditional branches are also explicitly visible.
This is the expected retained fail-closed state, not a passed Access smoke.

Two review-harness issues remain preserved:

- The initial independent inventory driver used `Counter(mapping)` where it
  meant `Counter(mapping.keys())`. It stopped with exit 1 after successful
  builds, before installation/collection. `initial-driver-failure.log` and
  `harness-correction.json` explain the correction; v2 resumes with unchanged
  artifact bytes. It is not a product failure or test PASS.
- The initial direct smoke tracer did `Path.resolve()` on every Python event,
  consuming CPU before reaching the product boundary. The reviewer interrupted
  that child with SIGINT: child exit -2, pytest wrapper exit 1, exception
  KeyboardInterrupt. Its log, partial line trace, JUnit/journal and import/byte
  measurements remain. The corrected tracer returns immediately for unrelated
  frames and compares the exact known filename. It changes no smoke literal,
  product, permission or assertion. The initial derived smoke and both clearly
  separate v2 smoke runs reach the real PERMISSION_DENIED failure (child exit 1).

`additional-summary.json` retains that interrupted initial direct attempt;
`smoke-v2-summary.json` is the completed actual-smoke evidence. Driver process
completion is bookkeeping: individual pytest/child failures above remain failures.
No unsuccessful assertion was inverted, skipped, xfailed or removed.

## Reproduction and limits

The exact executed drivers are saved as `.py.txt` files. On a fresh cloud work
area, run the frozen-source build procedure in `review_distribution.py.txt` with
its Counter correction from `review_distribution_v2.py.txt`, then the separate
`run_independent_and_smoke.py.txt`, `run_author_extra.py.txt`,
`run_counterexamples.py.txt`, `run_resolved_wire.py.txt`,
`run_source_author_extra.py.txt` and corrected `run_original_smoke_v2.py.txt` procedures.
Use a new work/output directory instead of overwriting these receipts. Their
recorded argv/cwd/requirements/input manifests bind the actual executions; source
and installed artifacts use the same selected Python. Counterexamples remain
expected-to-refuse assertions and should currently exit 1.

No full installed ordinary suite, live test, benchmark, release validation,
I6-C/I7/I8 implementation, real catalog operation, merge, fence activation or
SQLite-engine matrix was performed here. Root runs the independent broad source
comparison and final CI qualification separately. No permission/network action
was denied or pending in this packaging task, and all artifact installations and
measured subprocess outcomes are known.
