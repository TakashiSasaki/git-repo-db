# ADR 0033 sdist independent review — FAIL

Independent Task A review of [PR #138](https://github.com/TakashiSasaki/git-repo-db/pull/138),
completed on 2026-10-23 UTC. **Two Medium archive-validation defects require
follow-up before accepting the implementation's complete archive contract.**
There are zero Critical/High findings and two Low advisories. The real built
artifacts reproduce the claimed size reduction and complete wheel equivalence;
the adversarial gate is nevertheless incomplete. No product implementation,
accepted ADR, original Author evidence or ancestor PR was modified.

This fresh review agent owns the review and publication. Separate archive and CI
review agents contributed the named subreports. None authored the reviewed
implementation. This is agent independence, not a claim that a different GitHub
account approved the PR. No GitHub approval review, merge, release or deployment
was performed. PR #137 remains preparation evidence, not completed review.

## Frozen identities and provenance

| Role | Commit | Tree |
| --- | --- | --- |
| Accepted design / PR #135 | `18ba867d1c2f33c7d17939b2722d22a67139363a` | `57475b6fe473bc0cb691d9b7165414eb498b3893` |
| Reviewed PR #138 HEAD | `8cd89a3d25c811ee32d117ec32fe76a6022e6d94` | `0f42e9d0e498e249bc2cc02f6b96df9ef87106a0` |
| GitHub test merge | `18f1a890c18a8aee5b4b52238b520d7444c5776f` | `0f42e9d0e498e249bc2cc02f6b96df9ef87106a0` |
| Main, inspected unchanged | `cb532242c7aa86c6af5b6232b71c0906ea38f5c5` | `318ad07874ab436206e6a61f231b308a421cfc54` |

PR #138 base is `docs/adr0033-minimal-sdist-20261022`; its base SHA and actual
merge-base are the accepted-design SHA above. Test merge parents are that base
and reviewed HEAD, in that order. Startup REST reviews were `[]`, and the refreshed
PR list contained no completed independent sdist review. HEAD had not changed
from the supplied target. This new review's base is
`impl/adr0033-minimal-sdist-20261022`. Its containing commit/tree are recorded in
the submitted Draft PR and final handoff rather than embedded self-referentially.

Read AGENTS.md, ADR index, accepted ADRs 0001/0032/0033, implementation design,
complete Author evidence index/report, checker, packaging tests/cache, builders,
CI planner/dependencies/workflows and current testing procedures. Used the local
`efficient-repository-investigation`, `ci-final-tree-verification` and
`lessons-to-skills` skills. The last skill assessment produced a small verified
parser-inspection lesson in the existing CI skill, without changing policy.

Product source tree `84ebc206dce96520df17b7efab01bc1255ab76ea` is identical at
accepted base and reviewed HEAD. Only the new Author evidence directory was
added under historical evidence; existing evidence paths were not changed.
The Author archive SHA-256 `2364944e48508628894e8548db6bd538fce09144df4ea013410d52e75e81fc0c`
and all 107 indexed payloads were independently verified. Review input hashes
are in [reviewed-input-hashes.json](reviewed-input-hashes.json).

## Findings and acceptance conditions

The authoritative full records are [findings.json](findings.json), including
contracts, file/line locations, minimal counterexamples, observations, expected
results, root causes, commands/exits and acceptance conditions.

| ID | Severity | Observed defect / required follow-up |
| --- | --- | --- |
| AR-001 | Medium | `check_sdist_contract.py:109-139`: unknown 10 MiB PAX value is accepted before logical-member accounting. Review actual backend extension keys, allow only justified metadata, and bound decompressed header parsing. Keep regular-file logical byte accounting distinct. |
| AR-002 | Medium | `check_sdist_contract.py:109-151`: a second gzip/tar carrying a hidden log, corrupt/missing gzip trailer and malformed second gzip member are accepted. Validate the complete bounded gzip stream and reject additional uninspected archive payloads. |
| AR-003 | Low | `check_sdist_contract.py:145-151`: malformed Metadata-Version and duplicate Name pass standalone checks. Validate singleton metadata fields/version syntax. Integrated PKG-INFO/METADATA equality already adds protection. |
| A-CI-01 | Low, advisory | `ci_plan.py:461` and dependency rules: README is shipped/source-hashed and triggers the gate, while the runtime acceptance hash deliberately excludes prose. Clarify these distinct identities. Exact commit/tree checks prevent any demonstrated stale-acceptance bypass. Preserve ADR 0001's prose policy. |

The independent [archive probe](archive/README.md) completed 38 cases: 31 expected
behaviors and seven unexpected acceptances, **diagnostic exit 1**. Four standalone
attack CLI invocations returned 0/passed receipts; the unsafe-path control returned
1/failed receipt before extraction. Exact 2 MiB, 8 MiB and 512 boundaries passed;
one-unit excesses failed. Invalid/absolute/traversal paths, duplicates/multiple
roots, links/special files, unexpected ZIP/log/executable paths, missing
SQL/JSON/GraphQL/root metadata and changed source hashes were rejected.

Small actual synthetic archive specimens and their source fixture are preserved
under [archive/counterexamples](archive/counterexamples/). They are test inputs,
never product files. None of these defects alleges a malicious current backend
artifact. The PAX defect concerns unchecked extension data and parsing work;
its reported regular-file byte total is not itself arithmetically wrong.

## Independent distribution measurements

| Measurement | Accepted base | Reviewed implementation |
| --- | ---: | ---: |
| Compressed bytes | 83,949,291 | 677,902 |
| Regular-file unpacked bytes | 137,661,254 | 5,921,698 |
| Members | 3,875 | 159 |
| Direct wheel bytes | 762,725 | 762,725 |

Reduction: **99.19248633082559%**. Reviewed product inputs are exactly **132 Python,
19 SQL, 2 JSON, 2 GraphQL**. Reviewed budgets remain 2 MiB compressed, 8 MiB
regular-file bytes and 512 logical members. All source inputs, root files and
backend metadata are inventoried; `.gitignore` is exact source-hashed.

The independently rebuilt artifacts match the Author hashes exactly:

- Before sdist: `2fa5d627c506370e792ee5fac7cbdec3ae952fc2468273c61aa2d73bc296b4cf`.
- After sdist: `c72f86709f360b306daa1d39e2854e910f773e6acfce9f4bec7dae3396012e21`.
- Before/after direct wheels and derived wheel: `22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842`.

The independent driver explicitly built each direct wheel and each sdist from
frozen sources, checked before extraction, then rebuilt outside Git from the
reduced source. All **159 wheel member paths and uncompressed bytes**, including
all `.dist-info`, METADATA, entry points and complete RECORD hashes/sizes, are
identical. PKG-INFO equals wheel METADATA. All 155 product bytes match frozen
source and separate installed copies. Installer-created bytecode/bookkeeping is
outside that product-input comparison.

An additional backend-only venv had no product installed (`find_spec` returned
None), no Git on PATH, only locked Hatchling dependencies and a copied network
guard. It rebuilt the extracted sdist to the same complete wheel without Git,
lockfile, tests, scripts or docs in the sdist. Full-runtime installs used separate
fresh venvs, outside-source CWD, site-packages origin assertions, hash-required
locked offline dependencies and external-network refusal. Both passed console
CLI doctor, `python -m`, generated JSON guard equality, all P1 store initialization,
DDL fingerprints, integrity/foreign-key checks and actual runtime safety gates.
See [measurements.json](measurements.json) and the independent scripts under
[reproduce/](reproduce/).

## Actual executions and known failures

Counts overlap and must not be added as distinct coverage. Complete commands,
stdout/stderr, JUnit, journals and individual process exits are indexed in the raw
bundle. The broad/source driver and installed orchestrator are unmodified
repository helpers with historically hardcoded `author_verification: true`
labels; their independent invocations are recorded by this review's outer process
receipts. Such labels do not independently attest authorship or release acceptance.

| Execution | Actual outcomes | Exit |
| --- | --- | ---: |
| Packaging, including Author archive regressions | 57 passed, 4 failed | 1 |
| Focused CI planner/execution/cache/efficiency | 235 passed | 0 |
| Broad selected I5 cohort | 3,058 passed, 59 failed, 20 setup errors; no skip/xfail | 1 |
| Bounded source I4 / I5 (overlap broad) | 217 / 29 passed | 0 / 0 |
| Installed I4 / I5, each wheel | 217 / 29 passed | 0 / 0 |
| Additional installed collection/JUnit/journal reconciliation | 246 passed per wheel, exact duplicate-free identities/phases/finish | 0 / 0 |
| Installed I2 / I3 probes, each wheel | passed | 0 / 0 |
| Original installed Access smoke, each wheel | `I2_TRANSFER_UNSUPPORTED: Provider Transfer intake requires reviewed I3-I5 support` | 1 / 1 |
| Installed distribution orchestrator | failed because original Access smoke failed | 1 |
| Independent all-resource/CLI/schema probes | 155 inputs matched on each wheel; passed | 0 / 0 |
| Docs units / allowlisted checkout build | 8 passed / successful `--no-mermaid` placeholder build | 0 / 0 |
| Source lint, format, SQLite-policy | passed / 422 files formatted / 0 policy violations | 0 / 0 / 0 |
| Independent archive counterexamples | 31 expected, 7 unexpected among 38 | 1 |
| Failure comparison / backend-only rebuild | passed / passed | 0 / 0 |

All completed source cohorts reconcile selected nodes, JUnit and journal starts,
phase multiplicity and finish/process status, including failed runs. The additional
installed runs close the original orchestrator's absent-journal limitation. Bounded
I4/I5 tests use their existing explicitly disposable fixture stage fences; passing
those tests does not establish production Transfer/Identification support.

Compared against #133's frozen evidence at commit
`4cd083b0f7295a2bbaa2597ef483af46e77f5463`, archive SHA-256
`e38171c16b5e58cfa222f281ea87406645ae85876cc05aa9f34f055749a76176`,
member `local-i5/regressions.xml`: **79 baseline and 79 current non-successes;
0 additional, 0 resolved**. Every node, failure phase, stage refusal and trace
path/function sequence matches. Four P5 messages differ in disposable paths and
pytest's truncated CompletedProcess rendering; four frame coordinates differ in
the edited distribution fixture. Raw differences are retained, not normalized
into an assertion of exact trace/message equality. The four packaging FAILs are
those same inherited Identification-wire refusals. Matching failures remain FAIL.

## Environment, CI and limits

Selected Python **3.12.14**, environment-loaded SQLite **3.53.1**, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`;
locked Hatchling **1.32.4**, uv **0.12.19**. Runtime options/PRAGMAs, executable and
origins are retained in broad and installed receipts. Network dependency preparation
preceded offline builds/tests. No SQLite acquisition/build/rebinding, version
matrix, live data, real catalogs or safety-guard relaxation occurred.

The [CI subreport](ci/REPORT.md) verifies authoritative run/job metadata, receipts,
all payload hashes and exact test-merge/source bindings:

- Latest tests [39873626172](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39873626172): success, development pytest **0**; the evidence-only update correctly leaves sdist gate not applicable.
- Actual implementation sdist gate [39872269754](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39872269754): selected/passed on frozen `03e1192` with the same measured product archive; no full acceptance.
- Latest Access [39873626305](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39873626305): failure; inherited 79 non-successes and both original installed Transfer refusals preserved; distribution membership/equivalence passed.
- Latest Pages [39873626245](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39873626245): allowlisted checkout build and 8 docs units passed; deploy skipped. Workflow, docs builder and MkDocs config remain identical to accepted base.

Executed **3,419 unique ordinary nodes of 5,787**; **2,368 ordinary**, one live and
one benchmark node remain unexecuted. The exact ordinary remainder is in the raw
bundle. Installed runs overlap source coverage. No complete local or hosted release
validation was requested, dispatched or claimed.

Reviewer harness attempts are preserved: two pytest commands named nonexistent
files (exit 4; zero tests); an initial installed assertion compared sqlite.Row
objects with tuples (exit 1, corrected by reading actual row values); two custom
local docs staging/output overrides disagreed with fixed MkDocs paths (exit 1),
followed by the successful default-path build. Initial uv cache access used a
read-only home (exit 2), corrected with a workspace cache. The archive subreport
also records its initial import-path harness correction. None is silently counted
as a passed test or a product regression.

## Evidence and reproduction

[raw-evidence-index.json](raw-evidence-index.json) binds 171 payloads plus the
internal index in [raw-evidence.zip](raw-evidence.zip). It retains full failures,
commands, manifests, measurement attempts, baseline XML, input hashes, journals,
JUnit and reconciliation. [local-execution-summary.json](local-execution-summary.json),
[baseline-comparison-confirmed.json](baseline-comparison-confirmed.json) and
[installed-journal-reconciliation.json](installed-journal-reconciliation.json) are
convenience copies. CI subreceipts and archive specimens have their own indexed
files, covered by the review-wide evidence index. CI convenience log views are
ZIP-contained to preserve their original whitespace bytes; base64 receipt lines
were omitted by the subreview generator, with decoded receipts retained separately.

Use fresh output directories. Checkout reviewed HEAD for product execution; copy
review-only probe scripts from this review branch separately. Prepare with the
same existing interpreter, then execute offline:

```sh
UV_CACHE_DIR=/absolute/writable/cache uv sync --locked --group dev --group docs --python /existing/python
.venv/bin/python scripts/prepare_wheelhouse.py --output /absolute/new-wheelhouse
REPO_CATALOG_WHEELHOUSE=/absolute/new-wheelhouse .venv/bin/python -m pytest tests/packaging -q --junitxml=/absolute/new-packaging.xml --journal=/absolute/new-packaging.jsonl
REPO_CATALOG_WHEELHOUSE=/absolute/new-wheelhouse .venv/bin/python scripts/verify_i5.py --output /absolute/new-broad --workers 2
REPO_CATALOG_WHEELHOUSE=/absolute/new-wheelhouse .venv/bin/python scripts/verify_i5_distribution.py --output /absolute/new-installed
.venv/bin/python /review/reproduce/measure_distributions.py /frozen/reviewed-source /frozen/accepted-design /absolute/new-measurement /absolute/new-wheelhouse
.venv/bin/python /review/reproduce/check_backend_isolation.py /frozen/reviewed-source /absolute/new-measurement /absolute/new-wheelhouse /absolute/new-backend-proof
```

Archive probes resolve the reviewed validator relative to the review checkout;
use a fresh existing output parent, since specimen directories must be new.
The raw runner scripts preserve the exact actual paths/commands for adaptation.
No action is denied, pending approval or uncertain in this review. Remaining
acceptance blockers are AR-001/AR-002 remediation and independent re-review;
inherited 79 failures, P5 packaging failures and Access smoke remain separate
unresolved product-stage work. Publication is a new evidence-only Draft PR.
