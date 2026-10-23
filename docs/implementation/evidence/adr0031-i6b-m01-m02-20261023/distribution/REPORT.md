# Author verification of the corrected installed distributions

This is Author validation of the M01/M02 correction, not independent re-review or
Release acceptance. All final artifacts use frozen product commit
`fe9e48bfac750a276b2622da2c50d3d4559de338`, tree
`8ef254ff060f44f02370a695743c7a581e7b9b5c`. Its immediately preceding correction is
`d68dc43bff1eb949b071ebf1652e3d70a5a52ed9`; the correction chain starts at
`a3185cde585a3dbf4dec7d491ecd20e43c285a19`, whose sole parent is review #152
`8521158f2996f125d2fcaac36ea79ac1296a7cf7`. Final evidence is under
`final-root-guard/`. Completed superseded d68 evidence remains unchanged under
`final/`, with exact original report `REPORT-d68dc43.md`; interrupted a318 evidence
is under `nonfinal-a3185cd/`. No earlier result is combined with this freeze.

## Artifacts and actual product set

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Direct wheel | 791,300 | `2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8` |
| Sdist | 151,931,750 | `96134d412faf97119c50e98845c494f6a4554ea67d22d328da0a314049f8fbd7` |
| Independently built sdist-derived wheel | 791,300 | `2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8` |

The direct wheel and sdist were built by Hatchling from one fresh Git archive;
the derived wheel was independently built from its extracted sdist. All 164 wheel
members are byte-equal, including metadata, entry points and RECORD. Archive
RECORD has exact duplicate-free member coverage and recomputed SHA-256/lengths.
The measured product set is 160 files / 6,025,551 bytes; every product file equals
the frozen source, including packaged SQL and fingerprints. Counts were measured,
not used as a compatibility gate. Each installed RECORD is independently checked,
including generated installation metadata and launcher. Complete member inventories,
raw metadata/RECORD, actual site-packages origins and before/after product hashes
are retained. `final-root-guard/all-member-installed-agreement.json` additionally compares
all 163 non-RECORD archive inputs (product plus metadata) against every one of
18 before/after installed measurements; installed RECORD has 169 validated rows.

There is a packaging limitation outside M01/M02: of the 7,127 frozen Git files,
7,007 survive exactly in the sdist, with `PKG-INFO` as the only added file (7,008
members). Existing `.gitignore` rule `artifacts/` excludes 120 historical #152
files under `docs/implementation/evidence/adr0031-i6b-independent-20261023/ci/author-access/artifacts/`.
Every omitted file and `.gitignore` are byte-equal to #152. The complete omitted
path list is retained in `final-root-guard/sdist-source-retention.json`. All product, test,
script, workflow and dependency inputs are retained. Retained file bytes and Git
modes agree exactly. No packaging rule was changed and no #144 behavior imported.
It would be incorrect to claim that all publication evidence files survive.

Artifacts remain outside Git under `/workspace/i6b-fix-distribution-root-guard/`;
large source tar, sdist, venvs and disposable catalogs are not committed. Evidence
contains exact inventories and hashes. The 48 dependency wheels were hash-checked
against unchanged `uv.lock`, then installed offline into separate direct/derived
venvs. Separate minimal smoke venvs omit HTTPX. Every measured Python is the
existing CPython 3.12.14 and loads SQLite 3.53.1, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`.
Actual executable, module origin, compile options, STRICT/JSON and PRAGMAs are saved.
No SQLite installation, build, replacement, matrix or safety-floor relaxation occurred.

## Executed scopes

Each row below is a separate invocation in **each** installed form. Counts overlap
and are never summed into a complete suite. Each saves original collection,
selected IDs, JUnit, journal, command/cwd/process exit, source/input hashes and
actual product origins. Exact selected/JUnit/journal-start identities and normal
phases are reconciled, including failure status for the original smoke.

| Scope | Direct | Derived |
| --- | --- | --- |
| Retained safety (I4 217 / I5 29 included) | 626 PASS, exit 0 | 626 PASS, exit 0 |
| Existing Author wire/planner | 212 PASS, exit 0 | 212 PASS, exit 0 |
| Retained independent normal wire/planner/admission | 204 PASS, exit 0 | 204 PASS, exit 0 |
| Separate independent V07 alternatives | 4 PASS, exit 0 | 4 PASS, exit 0 |
| Retained Author external probes | 34 PASS, exit 0 | 34 PASS, exit 0 |
| Unchanged independent M01/M02 probes | 33 PASS, exit 0 | 33 PASS, exit 0 |
| New correction regressions | 56 PASS, exit 0 | 56 PASS, exit 0 |
| Unchanged original minimal Access smoke | 1 FAIL, pytest/child exit 1 | 1 FAIL, pytest/child exit 1 |
| Installed doctor | exit 0 | exit 0 |

The existing offline fixture/network guard remains active. Tests and support
files are copied from the frozen archive to a separate harness outside checkout;
pytest uses its explicit external configuration. Session start/finish verifies
all imported product modules originate in the actual selected site-packages,
with the entire measured product set unchanged. New test files are also compared
to their frozen bytes. Durations are process observations under concurrent Author
verification, not sequential benchmark comparisons.

The three unchanged M01 probes each use 1,001 already codec-validated rows. Both
installed forms now observe:

| max_work | Charged work | Embedded JSON calls / characters |
| ---: | ---: | ---: |
| 0 | 1 | 0 / 0 |
| 1 | 2 | 0 / 0 |
| 17 | 18 | 0 / 0 |

The single extra unit is the documented failed reservation, with no refused
operation run. Historical observations at #152 were 1,501 parses / 314,392
characters / 26,041 charged work for each budget. The new 16 planner tests include a huge malformed root-key dictionary checked
with `len` before allocating `set(data)`, in addition to exercising
zero/small/exhausted budgets, scanner/parse reservations and boundaries, strict
hard caps and retention of whole semantic units; the existing 212 and independent
normal lanes retain depth/byte/work/cycle/Source/Coverage/originals contracts.

The unchanged 30 digest probes now refuse stale digests as `DIGEST_MISMATCH` in
all five dimensions and three carriers. A separate measurement replays the **actual
30 saved raw JSON vector files**, checking each source hash: all stale cases
refuse `DIGEST_MISMATCH`; all correctly rehashed changed noncanonical selections
refuse `INVALID_SELECTION`; all 30 canonical originals decode unchanged. These
measurements overlap the probe nodes and are not added to any test total.
`*-saved-vector-replay.json` retains carriers, actual/declared digests and exact
codes. The paired wrapper retains sanitized environment and exact subprocess receipts. No input is silently repaired.

Both original smoke children execute the exact AST-extracted smoke literal and
reach original line 187 `ExchangeService.export_package`, refusing with
`AdmissionRefused: PERMISSION_DENIED`. Actual child and pytest exits are 1;
subsequent import/receiver/Provider assertions remain unexecuted. All 54 original
assert syntax nodes have explicit line-reach records. No assertion, grant or
Transfer fence is changed to make the smoke succeed.

## Preserved superseded attempts and limitations

At nonfinal `a3185cd`, both build artifacts and full member inventories completed.
An overly broad all-source sdist retention assertion failed on the historical
120 `artifacts/` exclusions. The failed driver and exact observation are retained;
a continuation reports the actual omissions without changing packaging. Its first
setup-only attempt omitted its local `env` variable and exited 1 before derived
build; the corrected continuation completed the derived build and inventory.
Those setup/audit failures are not passing product tests.

After the parent found a zero-budget hard-limit refusal-precedence regression,
the nonfinal verification was deliberately stopped. The driver received SIGTERM
(exit 143); its direct safety child received SIGINT and wrote journal finish
exitstatus 2 after 455 passing nodes. This is an interrupted partial execution,
not a completed 626-node lane. Remaining nonfinal lanes were unexecuted. Final
artifacts and all final lanes above were independently rebuilt/re-executed on
`fe9e48b`, and none uses those partial results.

The completed d68 distribution run was superseded after a final source read found
that the planner root-shape `set(data)` allocation preceded its constant-size
length check. That earlier run and its artifacts remain intact; the correction
reorders the length guard and adds one allocation-boundary regression. All final
artifacts and requested lanes here were rebuilt/re-executed from `fe9e48b`; the
d68 results are not reused as current-freeze executions.

The first third-freeze postprocessing attempt exited 1 before producing a summary:
a copied relative `F=OUT/final` path selected superseded d68 receipts, and an
extra check expected the journal label `passed` instead of its actual success
label `completed`. No test execution was repeated and no current or old raw
receipt was changed. The corrected postprocessor checks the explicit root-guard
directory and expected source HEAD/tree before reading lanes, then requires exact
`completed`/exit 0 or `failed`/exit 1 journal/process agreement. Its failed script
and structured observation remain in `final-root-guard/summary-harness-failure.json`
and `summarize-initial.py.txt`. Only correctly bound current-freeze receipts enter
the final summary.

No full installed ordinary suite, live Provider acquisition, benchmark, Release
qualification, I6-C/I7/I8 implementation, Transfer activation, PR integration or
release/deployment is claimed. Source full-suite comparison and hosted final-HEAD
CI are separate parent-owned evidence. No distribution operation remains denied, pending or uncertain.

`final-root-guard/verification-summary.json` contains the reconciled machine summary;
`final-root-guard/raw-compression-index.json` binds every retained gzip to its original raw bytes.
