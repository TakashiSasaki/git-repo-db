# ADR 0030 I4 verification and I5 handoff

## Frozen source and stack

Draft PR [#111](https://github.com/TakashiSasaki/git-repo-db/pull/111) targets
`impl/adr-0030-i23-integration-20261019` (#110).

| Coordinate | Value |
| --- | --- |
| Base HEAD | `8519056d5b9484eb0cc4dcf9f693285b4e65518a` |
| Base tree | `a77503505127367e9378c57c5ab9ee9ae11767f3` |
| Executed and independently reviewed HEAD | `f948cc6c764689154734f6386a10f97db6923e7a` |
| Executed and independently reviewed tree | `0dd55440469be7bb1a2d341ef9c2bc6419f631b0` |
| SHA-256 of the 422-input source manifest | `2ba3549c28a41825317bbcb65a20717c6541fb89c7b18d37547f83ba97f0a246` |

`raw/source.json`, `raw/inputs.json` and `raw/summary.json` bind the clean pushed
source, runtime/tests/scripts/workflows/locked dependency inputs and the run.
Evidence/skill-only follow-ups do not claim the tests were rerun; verify their
unchanged executable inputs against this manifest. Final Git HEAD/tree are
reported by the PR after publication; the executed source above stays immutable.
Initial and final protected-ref snapshots verify that main and #107–#110 are
unchanged. #110 remains an ancestor. No merge, release, P8 switch, real Catalog
operation, credential acquisition or live Provider collection was performed.

## Changed implementation files

The full source-change inventory is `raw/implementation-files.json`; the evidence
transport inventory is `index.json`. The executable changes are:

- `src/repo_catalog/domain/production_query.py`: typed role/historical projections.
- `src/repo_catalog/application/production_query.py`: qualified reads/filters/cursors.
- `src/repo_catalog/adapters/sqlite/production_search.py`: typed derivative generation.
- `src/repo_catalog/adapters/sqlite/recovery_validation.py`: enduring Provider invariants.
- `src/repo_catalog/adapters/sqlite/recovery.py`: scope notice and proven-corruption Stop.
- `tests/integration/p6/conftest.py`: retired API removal using genuine typed fixtures.
- `tests/integration/i4/__init__.py` and `test_query_search_backup.py`:26 new nodes.
- `scripts/verify_access_distribution.py`: installed I4 chain.
- `.github/workflows/access-registry.yml`: expanded actual-minimum cohort.

The I4 implementation document, this evidence directory and the existing
`.agents/skills/ci-final-tree-verification/SKILL.md` provide handoff and verified
procedures. Accepted ADR text, public runtime and production schema/fingerprints
are unchanged.

## Executed local verification

Actual Python **3.13.5**, SQLite **3.51.3**, source ID
`2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`.
The dynamic Python binding loads the compiled official amalgamation, verified
against official sqlite3.c SHA3-256
`32d5424f97e0a7fc5ed2f6335afbb58be4e0298bd7117a34e39d345ff13d859e`.
See `raw/runtime.json` and `raw/runtime-build.json`; no version override is used.

The expanded workflow-equivalent cohort passed **2,329 / 2,329**, with **0 failed,
0 errors, 0 skipped**. Collected and executed node multisets are identical,
duplicate-free, with no missing/unexpected nodes. All 422 inputs stayed unchanged
through execution. The four-worker run is correctness evidence, not a sequential
benchmark. Four Python 3.13 fork/thread deprecation warnings are preserved in the
raw log. The original baseline remains separate: P6 **23 passed / 27 failed**.

| Cohort | Passed | Failed / errors / skipped |
| --- | ---: | ---: |
| Selected unit values / acceptance | 456 | 0 / 0 / 0 |
| Access | 483 | 0 / 0 / 0 |
| I2 | 48 | 0 / 0 / 0 |
| I3 | 66 | 0 / 0 / 0 |
| I23 | 34 | 0 / 0 / 0 |
| I4 new adversarial tests | 26 | 0 / 0 / 0 |
| P1 | 355 | 0 / 0 / 0 |
| P2 | 197 | 0 / 0 / 0 |
| P3 | 80 | 0 / 0 / 0 |
| P4 | 202 | 0 / 0 / 0 |
| P5 | 48 | 0 / 0 / 0 |
| P6 | 50 | 0 / 0 / 0 |
| P7 | 255 | 0 / 0 / 0 |
| P5/P6 compatibility | 29 | 0 / 0 / 0 |

`raw/p6-resolution.json` names every one of the **27/27 resolved P6 failures**,
verifies retention/success of all 50 original P6 nodes and all **five original P5
Exchange nodes**. The sixth Exchange-module node is the separate I3 typed
relation control; it also passes but is not counted as an original-five node.
An initial receipt-parser assertion mistakenly counted that sixth control as an
original node; correcting the inventory did not rerun or alter test results.

The local Access evidence audit reconciles all 2,329 nodes successfully.
Its existing ledger still has 24 covered / 1 partial / 1 deferred requirement;
its pending governance/review labels are not a new I4 release or merge approval.
See `raw/acceptance.json`. This is evidence consistency, not full release receipt.

Ruff lint/format and DDL/fingerprint generation, schema audit, Context registration,
callsite-dependency and implementation-boundary audits all exit0 (seven checks).
Exact commands/logs are under `raw/commands.json`, `raw/audits.json` and the
compressed collection/JUnit/audit logs. The original CI cohort is retained,
P1 is expanded to all modules without duplicate selection, and I4 plus P5/P6
compatibility are included. No skip, xfail or test deletion hides failures.

## Distribution isolation

Both direct wheel and sdist-derived wheel were built on pushed `f948cc6`, installed
outside the checkout, and loaded from site-packages on actual SQLite3.51.3.
Both pass the expanded installed smoke, including native Git, Access isolation,
I2→I3 cross-seed Exchange, I4 Query/Search/Disposition qualification and fresh
paired backup/restore. Context contains19 tables with fingerprint
`fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`.

| Local artifact | SHA-256 |
| --- | --- |
| Direct wheel and sdist-derived wheel | `2ec7c49a81734088ef6f15564c548448f7e79b1786ef86d12bf828c1dd3969cc` |
| Source sdist at executed HEAD | `8d97536beb5f7ac1fd1208289c0b892a4ee1b8457e77d4aaa28b06e38011cc43` |

See `raw/distribution.json`. Later evidence changes can change complete sdist
bytes; they do not retroactively change these built/tested artifacts. The
independent reviewer separately built and tested both artifact kinds; its
artifact hashes and origin paths are in `independent/distribution.json`.

## Hosted verification

[Development CI run39285853846](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39285853846)
is verified from the actual job log and bounded receipt ZIP as
`development_checks_passed`, `full_acceptance=false`, with zero runtime pytest
execution. Its feature SHA is `f948cc6`; temporary test-merge HEAD
`10a85addb66f95d2fdaf6fcee4bfb55a7478c676` has the same effective tree
`0dd5544…`. This is static/development evidence, not minimum-runtime acceptance.
The SHA-256/length of the emitted ZIP and each receipt-index member were verified.
See `raw/offline-receipt.zip`, `raw/offline-receipt-binding.json`,
`raw/offline-validation-manifest.json` and `raw/offline-receipt-index.json`.

[Actual minimum-SQLite expanded run39285853860](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39285853860)
completed **2,329 passed / 0 failed / 0 errors / 0 skipped** on Python3.12.15 /
SQLite3.51.3 with the same official source ID. Collection/JUnit multisets match
each other and the local cohort exactly, without duplicates. All422 archived
source inputs match tested/reviewed `f948cc6`; the test-merge tree is identical.
Both installed artifact smoke runs, schema/registration/dependency/boundary
checks, formatting and MkDocs allowlist/internal-link checks pass. See
`raw/hosted-reconciliation.json`, runtime, collection, JUnit and actual job log.

The40,096,272-byte artifact ZIP (ID12205115448) has SHA-256
`5b7efc6094cb9cd29e17d519db15aae8fb79909c9d27cecb8b769e6c84202ca8`,
matching the actual upload log. The source tar was read in memory without blind
extraction and all422 input digests were checked. The committed evidence contains
allowlisted text receipts rather than compiled libraries, Ruff binaries or the
large original artifact ZIP. The independent reviewer separately reconciles this
archive/receipt in [the hosted supplement](independent/hosted-supplement.md),
rather than claiming another hosted test execution.

Run/job metadata lagged as `queued` / `in_progress` despite complete job logs and the finalized
artifact. The metadata snapshot and actual executed evidence are both preserved;
no success is inferred from status text. Before completion, log retrieval returned
404/BlobNotFound. Direct `gh` artifact download then failed403; the authorized
GitHub artifact-download connector supplied a readable file. Failed retrievals
are retained without signed temporary URLs. Obsolete own-branch runs were
cancelled where still cancellable. This expanded cohort is I4 verification,
not a full-release acceptance receipt.

## Independent review and corrected failures

The separate read-only reviewer fixed its own exported source, environment and
pytest config and ran **96 passed / 0 failed / 0 errors / 0 skipped** on the exact
corrected pushed HEAD: I4 26, P6 50, P7 source-diagnosis16 and four external
counterexamples. Both isolated distributions and all seven audits also pass.
There is **no remaining material finding** in that scope. A separate
[receipt reconciliation](independent/evidence-supplement.md) independently checks
the full local2,329-node collection/JUnit multiset, all422 original/current input
hashes, all27 P6 resolutions, original P5five, distribution/audit evidence and
Development CI receipt; this is not another2,329-node test execution. The reviewer did not
independently rerun all2,329 broad/hosted nodes; those executions are attributed
separately. Read [the independent report](independent/independent-review.md) and
`independent/review-summary.json`.

Initial pushed `b4caae0` independently reproduced **75 pass / 1 fail**: backup
refused a proven corrupt Provider scope but failed to persist P7 Stop. The trusted
stored-decoder exception was misclassified as an unexpected generic ValueError.
The correction uses an explicit `StoredContextInvariantError` boundary, preserves
its cause and distinguishes proven corruption from arbitrary errors, IO, lock or
budget refusal. The exact corrected-source reviewer confirms all four Stop paths
and all16 P7 diagnosis controls. The implementation's intermediate correction run
had47 pass / 1 fail because its assertion still expected BackupValidationError
rather than the now-correct CorruptionDetectedError; that test was corrected and
the full2,329-node run passed. Original failures remain in the raw evidence.

Precommit I4 harness errors (stale-index FK injection, wrong budget keyword,
order-dependent assertion, missing parameter decorator/import) are preserved
without relabeling them as passing product tests. The independent reviewer also
preserves incorrect initial probe expectations and an external-path pytest-config
mistake that imported old source. Explicit `-c` plus module/config-path assertions
binds its final96-node execution. The verified lesson updates the existing
`ci-final-tree-verification` skill, following `lessons-to-skills`; neither skill
expands domain or execution authority.

## Guarantees and remaining I5 acceptance

Current Provider roles and retained Core-target history remain distinct, with
no old fallback after a newer unresolved observation. Exact original IDs,
ClaimKeys, clock and provenance are preserved. Dispositions remain reports
without genuine caller operation evidence. Search is derivative, validates
against authority, falls back on index inconsistency and rebuilds explicitly;
it cannot supply identity, Mapping qualification or bypass P7 Stop.

Paired snapshots preserve all19 Context tables, Mapping subjects/replacements,
Transfer EventReportKeys and coherent endpoints, Provider relations, Coverage,
Source membership, original observation times and text/provenance. Fresh restore
verifies fingerprint/DDL, FK, stored domain invariants, retained bytes and pair
identity before installation. Checksummed malformed backups are rejected without
stopping a sound source. Proven authoritative source corruption stops Query,
Search, rebuild and normal backup. Access settings/approvals and Operational/
Search authority are excluded. Git-only backup remains independent and neither
scope claims repository-file restoration or complete operational environment
restoration. See [the implementation contract](../../adr0030-i4-query-search-backup.md).

I5 still must freeze the intended assembled integration/merge tree and conduct
independent end-to-end acceptance across mixed Repository/OID/Context selections,
Provider/Disposition qualification, Search loss/rebuild, recovery/Operational loss,
Core/Access separation and installed artifacts. Recheck actual refs/effective
trees before any separately authorized merge. Existing Access partial/deferred
acceptance and P8/public-runtime activation remain outside I4. No complete release
acceptance receipt, merge, release or real Catalog operation is claimed here.

`index.json` verifies compressed and uncompressed evidence bytes. Only text/ZIP
receipts are committed; synthetic catalogs, compiled libraries, venvs, credentials,
raw authenticated traffic and pytest temp trees are excluded.
