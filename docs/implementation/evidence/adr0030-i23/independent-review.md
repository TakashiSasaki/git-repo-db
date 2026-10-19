# Independent read-only I2 + I3 review

Reviewer: `/root/independent_i23_review`, separate from the implementing agent. No repository source, tests, branches, commits or remotes were modified by the reviewer. Executable counterexamples and archived trees live outside the repository.

## Reviewed pushed source

- HEAD: `c20d41cba4f229a93cd750b2f5fe1b1e986f45e9`
- tree: `9316c83fcde284cf44f8586ad4b36e6a32ce6f97`
- remote branch: `impl/adr-0030-i23-integration-20261019`, independently confirmed with `git ls-remote`
- Draft integration PR: [#110](https://github.com/TakashiSasaki/git-repo-db/pull/110), base `impl/adr-0030-i2-provider-intake-20261019`
- two-parent merge: `6dccd3c3bc4919975117a9cea80818936f2b9a5e`
- I2 parent: `9b8a6ad9b761bf23b45eda9f84d639569cee56ef`
- I3 parent: `5c5b816998f7051703ca400e8cfeab377254c435`
- actual merge-base / I1: `9390c9f3b54a033e5f07e1cb05d7c4b263c38fb7`

Independent GitHub reads confirmed #107/#108/#109 remain open Drafts at the pinned heads and retain their original bases; this review performed no merge/retarget/write operation. The source was independently extracted with `git archive c20d41c...` for testing rather than relying on a moving working tree.

## Verdict

**PASS within the I2 + I3 integration scope; R1–R3 are corrected, with no unresolved blocking finding in the reviewed source.** This does not approve I4, merge, deployment, public-runtime activation or release qualification. CI/full-regression evidence remains separately qualified below.

Read AGENTS, the accepted ADR 0029/0030 ledgers, I1/I2/I3/I23 handoffs, Context and selective-Exchange architecture contracts, design evidence handoff, changed integration/workflow/distribution files, inherited I2/I3 implementation and relevant repository skills. The reviewed fixes introduce no Core DDL/mutation, Access authority, hidden Mapping Witness, v3 compatibility, skip/xfail or CI target reduction.

Current affiliations come from original Provider scopes through `provider_repository_roles()`. The integration test explicitly preserves a newer unresolved owner while retaining the older Core-target evidence, so the latter is not promoted to current truth. Original Provider namespaces, exact ClaimKeys, original clocks/provenance, Disposition re-evaluation and complete Transfer EventReportKeys remain intact. Independent R/O/C selection and explicit Repository permissions preserve receiver identity; permission cuts withhold units without adding unauthorized Repository registrations. Existing I3 tests exercise Operational binding/loss, SQL binding immutability, actual subprocess crash boundaries, cumulative work limits including empty packages, Notes/Capture integrity, whole Coverage/Transfer units, Access exclusion and persistent P7 Stop.

## Closed independently reproduced findings

The initial pushed source `6b595ca69d2bcadb7a4643ec7c14191512b20086`, tree `25613415f2a96edaa07138492d795003d20ddf58`, passed its 173-node focused suite but failed twelve additional reviewer controls. See `initial-review.md` and the original repro scripts/logs/JUnit for unchanged failed-tree evidence.

1. **R1, High — typed Provider role preflight.** Three malformed real-I2 `provider_repository_roles` packages bound PackageKey and committed Core before Context rejected role/time/member inconsistency. The corrected preflight calls the same `validate_provider_repository_scope()` as admission, before selection/binding.
2. **R2, High — writer-only subtypes and primitive affinity.** Empty/bad-OID/empty-role reported Core references and empty Provider kind failed after binding/Core commit; numeric Provider/relation kinds were accepted as coerced text. The corrected preflight shares the reported-reference validator with the writer and rejects non-text Context primitives in v4 decoding.
3. **R3, High — complete Coverage owner dependencies/order.** A legitimate collection-owned Coverage scope failed because its FK target was admitted later. Missing collection and permission-cut Source/Repository scopes aborted independent Context facts. The corrected importer orders collections before scopes and checks full original collection keys and Source/Repository positive pairs, including receiver-existing dependencies.

The updated reusable skill correctly records these verified failure modes, exact validation/dependency obligations and positive controls. It does not add policy or claim an issuer-authentication guarantee.

## Independent executed validation

Reviewer runtime: Python **3.13.5**, actual SQLite **3.51.3**, source ID:

```
2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618
```

The interpreter was launched with `LD_LIBRARY_PATH=/workspace/i23-sqlite`; test imports were bound by PYTHONPATH to the independently archived exact source. Version/source ID were queried, not overridden.

```
python -m pytest -q tests/integration/i2 tests/integration/i3 tests/integration/i23 tests/integration/p5
```

**196 passed, 0 failed, 0 errors, 0 skipped**: I2 **48**, I3 **66**, I23 **34**, P5 **48**. All five original P5 Exchange behavior nodes reached their final assertions and passed. Artifacts: `corrected-focused-min.xml`, `corrected-focused-min.log`.

Separately authored external controls on this exact tree and minimum SQLite: **22 passed, 0 failed/errors/skips**, covering nine malformed units under normal and Context-disabled receiver selection (18), genuine/missing/receiver-existing collection owner dependencies (3), and a permission-cut Source coverage scope preserving independent facts (1). Artifacts: `test_corrected_independent.py`, `corrected-counterexamples-min.xml/log`.

An additional genuine **complete collection-owned Coverage proof roundtrip passed (1)**. Exact collection/terminal/proof rows survived and receiver Coverage remained complete (`corrected-complete-proof-min.xml/log`). Thus independent external corrected controls total **23 passed**. These overlap production regressions and must not be added to the product registry count.

A first external harness attempt produced four failures because package construction now correctly rejects numeric kinds before the import assertion was entered. That harness output is preserved as `corrected-constructor-harness.xml/log`. The corrected harness uses raw dictionary wire input and a valid recomputed checksum, and all eighteen invalid-input controls then prove receiver-side rejection before Package Binding/domain mutation. Those harness failures are not product failures and are not hidden as passing executions.

Independent read-only schema generation/fingerprint, Context registration, callsite and implementation-boundary audits all exited zero. Full Ruff lint and format checks exited zero (**385 files already formatted**). Artifacts: `corrected-schema-build.log`, `corrected-schema-audit.log`, `corrected-context-registration.log`, `corrected-callsite.log`, `corrected-implementation.log`, `corrected-ruff.log`.

## Evidence and remaining scope

The implementing agent owns broad regression, direct wheel/sdist-derived independent installation and hosted CI execution. This reviewer will reconcile their final exact-source receipts separately, without claiming to have independently rerun the full extension registry or packaging. The known 27 P6 legacy `Context.admit_repository()` failures remain I4 work; passing focused tests do not hide or fix those failures.

I4 must preserve the fixed qualified Provider read, exact ClaimKey/Disposition/EventReportKey/clock/provenance interfaces, immutable Core and independent Access boundary. It must implement Query/Search/Backup against this integrated source and retain full request/binding/Recovery Stop semantics. Recommended merge dependency remains I1 #107 → I2 #109 → integration #110, whose merge history already includes I3 #108; separate I3 merging requires fresh effective-tree verification.

## Broad local and packaging evidence reconciliation

Independently inspected the implementer's clean-source packaging verifier, execution output and `distribution.json`. Both direct-wheel and sdist-derived-wheel smoke runs use their separate prefix-local imports outside checkout under `-I`, no Provider HTTP dependency, actual SQLite 3.51.3/source ID above, Context table count 19 and fingerprint `fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`. Both installed I2→I3 cross-seed checks passed. Recorded wheel SHA-256 (both builds) is `bee593057a73ca669756e68c09a9516c0721295a512fd179bb593144a215f9da`; sdist SHA-256 is `b74e811d4235538678e35105ab4dfd3cd5f49d65af2d481b0d3522fadbde8ea0`. Temporary built binaries were deleted by the verifier; this review inspected their run receipts and script and does not claim to have rehashed or rerun those deleted artifacts.

Independently recomputed the completed broad local run's collection/start/JUnit multiset equality, exactly-once setup/call/teardown phases, absence of skips, and exact failure-node equality against I2's historical 27-node P6 set. Result: **2069 selected/executed = 2042 passed + 27 failed, 0 errors/skips**. Every failure contains the retired `Context.admit_repository` dependency; no additional or resolved P6 node was hidden. The run's actual runtime is Python 3.12.14 / SQLite 3.53.1, its process exit remains 1, and `full_acceptance` is false. Groups: unit 456; Access 483; I2 48; I23 34; selected P1 150; P3 80; P5 48; I3 66; P2 197; P4 202; P6 23 passed/27 failed; P7 255. This is receipt verification of the author's execution, separate from the reviewer's own 196+23 minimum-SQLite checks.

The completed broad **actual SQLite 3.51.3** run was subsequently independently reconciled from its raw collection, journal and JUnit as well: **2069 selected/executed, 2042 passed, 27 known P6 failures, 0 errors/skips**. Every selected node has exactly one start/setup/call/teardown/JUnit occurrence, one failed finish/process exit 1, and every failed node exactly matches the historical P6 set with the retired API in its failure detail. This source binding is c20d41c; runtime Python 3.13.5 / SQLite 3.51.3/source737ae4. `reconcile_parent.py` and `broad-reconciliation.log` record this reviewer-side evidence check. Hosted CI remains separate from this local minimum-runtime result.

## Supplemental fixture-only follow-up

Independently confirmed remote HEAD `6d50ba22f4b3092516bce004de4611a1a5bd566d`, tree `476ee24311a78efa3048b301ea598f22fb13bc45`. Its diff against c20d41c removes exactly three obsolete I2 UUID arguments across two supplementary compatibility test files and adds eight handoff lines. Original assertions remain; no Provider ownership is invented. Production source, build scripts/configuration, workflow and the 2069-node registry cohort are unchanged. SHA-256 comparison of all 420 entries in the prior source manifest found exactly those two expected supplementary test-file changes, with all other 418 entries identical; the complete 420-entry manifest is therefore not described as unchanged.

Reviewer independently ran the compatibility suite from a read-only archive of 6d50ba2 on actual SQLite 3.51.3: **29 passed, 0 failed/errors/skips** (`supplement-compat-min.xml/log`). Independently reconciled the author's exact-6d supplementary raw collection/journal/JUnit: **234 selected/executed/passed, 0 failed/errors/skips**, exactly-once phases, disjoint from the main registry cohort (**205 complementary P1 + 29 compatibility**). Combined applicable minimum-runtime product selections therefore cover **2303 unique nodes: 2276 passed, 27 known P6 failed, 0 errors/skips**. Reviewer external controls overlap these cohorts and are not added to that count.

## Actual hosted execution and stale status metadata

The earlier queued-status / HTTP-404 log-download limitation was resolved using the authorized GitHub connector's real job log and artifact retrieval. The previous 138-byte HTTP-404 bodies are preserved as failed retrieval attempts; they are not execution logs. Cached run/check metadata still reported queued while the genuine execution log and uploaded artifact showed completed work. This review derives execution results from their bound contents, not from that stale status or a predicted outcome.

Independently inspected [registry run 39278827565](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39278827565), job `118149248529`, and verified its real artifact ZIP SHA-256 `b42f08114e516ad72fd2d8347b88e857db5ac810d848def70303866b7905ad35` matches the upload-log digest. The artifact's checked-out/test merge is `de31bd8d5338be6509150b1261864a6d5bf4ca11`; its effective tree is exactly reviewed c20d41c's `9316c83fcde284cf44f8586ad4b36e6a32ce6f97`. All **420** source-archive code/test/script/build/workflow files were independently hash-compared to the reviewer's archive and matched.

Actual hosted runtime is Python **3.12.15**, SQLite **3.51.3**, source ID `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`. The log verifies official sqlite3.c SHA3-256, shows actual runtime at 15:33:31 UTC, **27 failed / 2042 passed** at 15:39:17, and cleanup at 15:39:35. Independently reconciled artifact collection/JUnit multisets: **2069 unique selected/executed, 2042 passed, exact same 27 known P6 failures, 0 errors/skips**. Hosted artifact has no journal phase stream, so this review claims exactly-once selected/JUnit equality rather than independent hosted setup/call/teardown verification. `reconcile_hosted.py` and `hosted-reconciliation.log` preserve reviewer checks.

Both hosted direct-wheel and sdist-derived-wheel isolated smokes passed on actual SQLite 3.51.3 with the installed I2→I3 cross-seed control. Their recorded wheel/sdist hashes equal the prior c20d41c local receipts. The five implementation audits passed. The Access acceptance audit correctly failed because its input contains 27 failed nodes; the registry execution is **not green/full acceptance** and no node was excluded to hide that result.

Independently decoded [offline run 39278827630](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39278827630), job `118149249333`: bounded receipt length **69179 bytes**, SHA-256 `57d49b3602b697d096501db0ec2c9f553ff354ff24bae4a99980c4bde7642330`, matching BEGIN/END and all **21** indexed members verified. Feature c20d41c/test merge de31bd8/tree9316c83 match. Its manifest is `development_checks_passed`, `full_acceptance=false`, runtime SQLite **3.45.1**, and `coverage.executed=0`: it is development/static evidence, not the minimum-runtime test result above.

The subsequent 6d50ba2 supplementary-fixture commit retains identical production and registry test inputs; its separate minimum-SQLite supplementary run covers the changed fixtures. No executed c20d41c receipt is relabeled as an executed later commit.

## Latest source 6d50ba2 hosted verification

The later source itself now also has real hosted execution evidence, superseding the need to rely solely on unchanged c20d41c cohort inputs. Independently verified [registry run 39280209622](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39280209622), job `118152806024`, artifact `12201120483`. ZIP SHA-256 `7a26ea0bb6487472b1e6e069a5a88dd0a86bfb0f810ae4866a1e10df205ecc38` matches the real upload log. Checkout/test merge `02804e9359ab8e1e0d0f496b76e573e4d97c327d` has effective tree **`476ee24311a78efa3048b301ea598f22fb13bc45`**, exactly the reviewed 6d50ba2 tree. Independently hash-compared all **420** archive code/test/script/build/workflow files to the reviewer's 6d archive: all equal. Artifact collection/JUnit multisets again give **2069 unique nodes, 2042 passed, exact known 27 P6 failures, 0 errors/skips**. Actual hosted Python 3.12.15/SQLite 3.51.3/source737ae4 was printed at 15:44:40 UTC; pytest ended at 15:50:55. The Access acceptance audit again correctly rejected the 27 failed nodes. Neither this registry run nor the integrated source has full acceptance.

Both latest-source hosted isolated wheel and sdist-derived wheel checks passed, with original cross-seed I2→I3 smoke and Context fingerprint/table-count checks. The unchanged wheel SHA-256 is `bee593057a73ca669756e68c09a9516c0721295a512fd179bb593144a215f9da`; this source's updated sdist SHA-256 is **`68b9b933d35480a922b3ee8041465dcc6aa2ef221bd9e2b624808005c0e3062c`**, distinct from c20d41c's sdist because supplementary tests/docs changed. Reviewer script/results: `reconcile_hosted_final.py`, `hosted-final-reconciliation.log`.

Independently decoded latest-source [offline run 39280209580](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39280209580), job `118152806076`: **68951 bytes**, receipt SHA-256 `fd58a5b451ecdbfc875e5515ce8362498ee68ab5e2b581f71be3f1926f1b92b4`, matching BEGIN/END and all **21** indexed members. Feature6d50ba2/test merge02804e9/tree476ee243 are exact. This remains passed **development checks**, `full_acceptance=false`, `coverage.executed=0`, SQLite3.45.1. Receipt ZIP/binding/manifest and parser/results are preserved under `offline-final-*` and `reconcile_offline_final.py`; it is not minimum-runtime evidence.

Final source verdict remains **PASS for the bounded I2 + I3 integration and reviewed fixture corrections**, with R1–R3 closed and no new blocking finding. The known 27 P6/I4 failures are visible in local and hosted executions and remain a real limitation, so no release/full-runtime completion, merge or I4 completion is approved.
