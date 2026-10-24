# ADR 0033 archive hardening — Author verification

Task A corrects the archive-checker findings from [review PR #140](https://github.com/TakashiSasaki/git-repo-db/pull/140).
The new [Draft PR #142](https://github.com/TakashiSasaki/git-repo-db/pull/142)
preserves that review branch as its direct parent. **Author remediation and
verification are complete; independent non-Author re-review remains required.**
This report grants no independent review PASS or release acceptance.

## Frozen source and conflict checks

| Role | Commit | Tree |
| --- | --- | --- |
| Required parent, #140 | `ef3ca118d4ab5e52dc2d1c7de384c3557509add2` | `ded7bd39fd86dd0d738404abf667beaf44fb06d0` |
| Tested implementation | `aaee34d31d2511cfec95d0bfa41a3a9733ac43e4` | `6552c028771f957a6e81c31b9f67b9016bf5b569` |
| Actual initial GitHub test merge | `b54faad4fe8af65a3021e1ba50115fe90342688b` | `6552c028771f957a6e81c31b9f67b9016bf5b569` |

The test merge has exactly the parent and implementation commits above, in that
order. Startup live GitHub reads confirmed #138 at
`8cd89a3d25c811ee32d117ec32fe76a6022e6d94`, tree
`0f42e9d0e498e249bc2cc02f6b96df9ef87106a0`, and #140 at the required parent.
Their bases, reviews and checks were saved. All 76 remote branches and the latest
100 PR records were inspected; no competing archive repair existed. No prior
review was repeated or prior evidence modified.

Neither #139's receipt-limit fix nor #141/I6-A is an ancestor of this branch.
They were not merged or cherry-picked. Integration must preserve the assigned
#140 stack; any eventual combination with the independent I6-A stack needs
separate effective-tree verification. The inherited C0 receipt behavior is not
repaired here. No existing PR head, accepted ADR, product source, DDL, UDF or
SQLite safety predicate changed. The `src` tree remains
`ec0e0b9ebc8c9117453c0cace607626803e90c8e`.

Read AGENTS.md, ADR index, accepted ADRs 0001/0032/0033, design, #140's report,
findings and archive/CI/reproduction evidence, checker, packaging fixtures/cache,
distribution builders, planner/dependencies and workflows. Used the repository
investigation, final-tree verification and lessons-to-skills procedures. The
existing final-tree skill now records the verified bounded-archive procedure.
Implementation/test/CI-documentation delegates used GPT-6.1 Sol with High effort.
Those contributions are Author work, not independent acceptance.

## Finding disposition

| Finding | Correction and executable evidence |
| --- | --- |
| AR-001, Medium | Stream gzip inflation with a finite output limit before any tar parser. Inspect fixed-size raw headers before logical iteration. Actual locked Hatchling 1.32.4 emitted **zero PAX records/keys**; the justified extension allowlist is empty. Reject local/global PAX, GNU extensions, unknown/giant values and malformed extension lengths without parsing extension bodies. Regression cases forbid even `TarInfo.frombuf`/`TarFile.next` before the inflation limit. |
| AR-002, Medium | Validate exactly one gzip member through CRC, ISIZE, trailer and EOF; reject every trailing byte or second stream. Require aligned tar records, two end blocks and exclusively zero end/member padding. Reject hidden archives, nonzero tails, cuts, bad checksums and inconsistent raw sizes. |
| AR-003, Low | Require exactly one case-insensitive Metadata-Version/Name/Version header, no email-parser defects, supported metadata versions and valid Name/PEP 440 Version syntax with exact project identity. Duplicate headers fail regardless of order. Full PKG-INFO/wheel METADATA equality remains mandatory. |
| A-CI-01, Low | Document that `acceptance_input_hash` deliberately excludes README prose, while `source_inventory_sha256` includes README path, byte count and digest. Planner regressions preserve lightweight README sdist selection and cover checker, builders, packaging tests, shared fixture and workflow changes. No runtime hash or CI policy semantics changed. |

The original limits remain **2,097,152 compressed bytes**, **8,388,608 regular-file
logical bytes**, and **512 members**. The separate whole-tar limit is
`8,388,608 + 512 * (512 + 511) + 10,240 = 8,922,624 bytes`. It covers each
permitted header/alignment and a tar record of terminal padding. Output is read
in at most 64 KiB increments into finite storage; no unbounded full inflation is
used. Real tar size is **6,051,840**, raw headers **159**, terminal zero padding
**5,632 bytes**. Receipts separately report compressed bytes, regular-file bytes,
whole-stream bytes and physical/logical header counts. A future legitimate
extension or long path requires fresh calibration and reviewed bounded policy.

## Before/after and actual local execution

All seven stored #140 attack archives were accepted by the frozen old checker;
all seven now reject. Every attack CLI exits 1 and retains a failed receipt.
The new regression module has **94 cases**: the same tests against the frozen
old checker yield **72 FAIL / 22 PASS**, exit 1; against the repair all **94 PASS**.
They include valid exact 2 MiB gzip framing (empty DEFLATE blocks, no appended
garbage), exact 8 MiB and 512-member cases and overflows, physical-stream limits,
new PAX/framing/metadata/header cases, resources and refusal before extraction,
rebuild or installation. The existing 37 checker tests also pass, including real
Hatchling builds. Test generators and named JUnit outcomes preserve the new
counterexamples; historical specimens stay untouched.

| Execution | Actual result | Exit |
| --- | --- | ---: |
| Complete packaging directory, includes old/new checker cases | **151 PASS / 4 FAIL**, zero skips/xfails | 1 |
| Broad selected I5 regression cohort | **3,058 PASS / 59 FAIL / 20 ERROR**, zero skips/xfails | 1 |
| Overlapping source I4 / I5 | **217 / 29 PASS** | 0 / 0 |
| CI planner/profile/execution/efficiency | **253 PASS** | 0 |
| Docs units / checkout allowlist build | **8 PASS** / successful `--no-mermaid` placeholder build | 0 / 0 |
| Ruff lint / format / SQLite policy detector | PASS / 423 files formatted / zero violations | 0 / 0 / 0 |
| Direct / sdist-derived installed I4+I5 | **246 PASS each**, collection equals JUnit exactly | 0 / 0 |
| Installed I2 / I3 on each wheel | PASS | 0 |
| Original installed Access smoke, each wheel | `I2_TRANSFER_UNSUPPORTED` | 1 / 1 |
| Installed orchestrator | FAIL because original Access smoke fails | 1 |
| Independent distribution measurement / backend-only rebuild | PASS / PASS | 0 / 0 |

The four packaging failures are the inherited P5 Identification-wire refusal
nodes. Broad comparison uses the #133 baseline XML retained and hash-indexed in
#140: **79 baseline / 79 current**, **0 added / 0 resolved**. Every node, phase,
stage refusal and trace path/function sequence matches. Four messages differ in
disposable paths/pytest's truncated subprocess rendering; full XML and comparison
details are retained. Matching failures remain failures. No skip, xfail, reduced
cohort or weakened guard hides them.

All source cohorts reconcile exact node multisets, JUnit, journal phases and
finish/process exits, including failed runs. **3,531 unique ordinary nodes out
of 5,888** executed; **2,357 ordinary**, one live and one benchmark node remain
unexecuted. Installed cases overlap source coverage. The unchanged installed
orchestrator produces JUnit/process receipts without a journal; a separate
collection matches all 246 nodes per artifact. This limitation is explicit, not
a claim of a missing journal's success. The preliminary hardened 94-case stdout
was not persisted; its JUnit/journal and the later complete packaging log exist.

## Distribution measurements and identities

Frozen accepted-design source and repaired source were explicitly built with the
same backend, each direct wheel separately from its sdist. The validated reduced
sdist rebuilt outside Git. All **159 wheel members and RECORD rows** are exactly
equal, including PKG-INFO/METADATA. Separate fresh runtime venvs outside both
sources verify CLI/module entry points, all stores' DDL/integrity/foreign keys,
generated guards, resources, actual runtime safety and installed import origins.
All **155 product inputs** match: 132 Python, 19 SQL, 2 JSON and 2 GraphQL.

An additional backend-only venv has no installed product or Git on PATH and only
hash-verified locked Hatchling dependencies. It rebuilds the same wheel without
Git, lockfile, tests, scripts or docs in the sdist. Dependency preparation occurs
before offline builds and guarded execution. No SQLite library was downloaded,
built, replaced or rebound, and no version matrix was introduced.

| Measurement | Accepted design | Repaired source |
| --- | ---: | ---: |
| Compressed sdist bytes | 83,949,291 | **677,902** |
| Regular-file bytes | 137,661,254 | **5,921,698** |
| Members | 3,875 | **159** |
| Direct / rebuilt wheel bytes | 762,725 | **762,725** |

Reduction is **99.19248633082559%**. These are newly measured results, not hashes
forced to match history. Product inputs did not change, so deterministic bytes
also reproduce the historical measurements.

- Sdist SHA-256: `c72f86709f360b306daa1d39e2854e910f773e6acfce9f4bec7dae3396012e21`.
- Both wheels: `22809cb1f468d5c57f18e8aea66e218ca261134cf3307043cd988f1ff436f842`.
- Sdist source-inventory hash: `7d93a7c4b2d3d6a7411f0fc98a42901a83b508a63d2e15e44c2f6f2674f21934`.
- Tested runtime acceptance hash: `508261ad3a6a2a95d55bbe5af95394f6db64fa9a0b2e823316b8853f81d3d1ec`.
- Tested byte-inventory hash for source/tests/scripts/workflows and lock inputs:
  `c0742237299a23851496ed83d87f0f64ba75e41e1b64fa7f0e507861003d73f7`.

Complete per-file input hashes, the distinct sdist source-inventory hash and
artifact hashes are in the receipts. The later evidence commit is explicitly
bound to unchanged execution inputs, not represented as a test rerun. Conservative
CI hashing can include new unclassified evidence JSON/ZIPs; its final hash can
therefore differ from the tested runtime hash. Exact candidate hashes and trees
are recorded in the PR and final hosted receipt, without redefining the hash.

Local Python is **3.12.14**, actual SQLite **3.53.1**, source ID
`2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`;
Hatchling **1.32.4**, uv **0.12.19**. Actual PRAGMAs, compile options, UDFs and
origins are retained. Hosted development uses Python **3.12.15** and its actual
SQLite **3.53.1**. Agreement was observed, not imposed as an acceptance gate.

## Hosted development verification and handoff

Initial [tests run 39890829950](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39890829950)
passed. The actual log receipt verifies **24 indexed payloads** against SHA-256,
the exact feature/test-merge/tree above and the tested acceptance hash. Sdist
gate selected/passed with the same measured archive and whole-tar size.
`acceptance_status=development_checks_passed`, `full_acceptance=false`, hosted
runtime pytest executed **0**. Receipt ZIP SHA-256:
`c2563f673743e54fba464c49359149e8ce202455784ee211b79bb49e02774c2e`.

[Access run 39890829878](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39890829878)
completed **FAIL**. Actual focused results are **2,696 PASS / 59 FAIL / 20 ERROR**;
its broad results are **3,058 PASS / 59 FAIL / 20 ERROR**, exit 1. Both source
and hosted comparisons preserve the same 79 inherited non-successes; the hosted
XML also matches the #133 baseline's nodes/phases/refusals/trace paths/functions.
Installed I4/I5 pass **246 cases per wheel** and both original Access probes
fail, making their orchestrator fail. Access-ledger reconciliation fails on
the unpassed required nodes. Both distribution receipts pass with the measured
archive and complete wheel equivalence. Audits, runtime binding, formatting and
allowlisted docs build succeed; no deploy step is involved. Actual hosted
receipt SHA-256 is
`6002bc141f804f35d0b52fb2a6a852440a2714eba7b493432b26eb0729ed42cd`:
**102 indexed payloads** verify against the same exact test-merge/tree. Its
1,677,217 compressed bytes are below both 2 MiB and the inherited emitter's
4 MiB bound; this does not integrate or claim remediation of #139.

The [raw evidence index](raw-evidence-index.json) binds all payloads in
[raw-evidence.zip](raw-evidence.zip). Convenience copies include
[verification-summary.json](verification-summary.json),
[measurements.json](measurements.json), [PAX calibration](pax-calibration.json)
and [baseline comparison](baseline-comparison.json). Reproduce with the same
existing interpreter and fresh output paths using the recorded commands;
`scripts/verify_i5.py`, `scripts/verify_i5_distribution.py`, and the preserved
#140 measurement/backend-isolation drivers remain unchanged.

Two setup/harness failures are retained separately: the initial uv cache path
was read-only (exit 2; fixed with a writable cache), and a summary script outside
the checkout initially lacked the repository import path (exit 1; corrected
without product changes). An old `gh pr checks --json` flag was unsupported;
plain checks plus raw API metadata supplied the same read-only evidence. None
is counted as a test PASS or a product regression.

Independent reviewer: inspect all AR-001/002/003 boundaries and A-CI-01, reproduce
retained and new counterexamples, review the finite stream/extension policy and
complete artifact/install evidence against the published effective tree. Keep
the original 79 failures and Access smoke refusal visible. Full ordinary and
dual-environment release acceptance remain unexecuted. No merge, release, deploy,
real catalog operation or automation modification occurred. No action is denied,
pending approval or uncertain; remaining gates are independent re-review and the
separate inherited product-stage failures.
