# I6-B + ADR0033 sdist + C0 integration candidate

This is **Author integration verification**, not independent acceptance, Release acceptance or permission to merge main. The candidate includes the full reviewed 154 + 147 + 144 histories. I6-C/I7/I8 implementation and ordinary Transfer activation remain outside this candidate.

## Frozen inputs and actual ancestry

| Input | HEAD | Tree |
| --- | --- | --- |
| 154 / direct PR base | `91827360c185cbf813277bf32a6627d894b1b20a` | `4db21ecf4267f1f31023fd63ac6de7ebd8d93d3c` |
| 147 / reviewed C0 | `e7762952e18061de8c8235beaeddf42f20ad9f5a` | `9c220c6606703aa36606896eb52d0a8966914a36` |
| 144 / reviewed sdist | `ededcd83eb2d99a602ba18c8fe3c177125c825ac` | `2c721a0e8a58ebe8d1f795da821ea4e317b73e7e` |
| Actual tested executable/test freeze | `fb5d7b5a0c4b92c8a282daac154e66fa6d361e64` | `d2010275a90ae6b6cb728344d5708057a79110cd` |

Live GitHub main was reacquired as `cb532242c7aa86c6af5b6232b71c0906ea38f5c5`, tree `318ad07874ab436206e6a61f231b308a421cfc54`. All open PRs, relevant reviews/comments, input checks and branches were read before integration; no same-purpose integration PR existed. All three specified heads/trees matched. All pairwise input merge-bases remain `f16e5b1713bde9a2f18263a25397c4b450fd5773`; input/main merge-base is `d92377599a50f192f534836fc12402a5fe87ca83`. No changed head was silently substituted.

The independent checkout starts exactly at 154. Actual merge147 `9c3de77475d042bb5e8c465a64e5f4b47d2eda23` has ordered parents154/147 and tree `ab1222093f4fe74ddd55032f28a4ef91dddddb15`. Merge144 `9f005eb2dbd97a5c160872740794143a2bd560f7` has ordered parents merge147/144 and tree `2d69ada6c344d8b361fa49241915e91ac712db96`. The final source/test commit only sorts the merged import union for Ruff. Each reviewed input is a real ancestor, not a copied subset. See `integration-identities.json`, `dag.txt.gz` and `audit/topology-overlap.json`.

PR150 `4fc00b1fbc57f10f6c0c6352dee702e1738f65b7` was read as reference and is not an ancestor. Its old simulated tree `2c61c7d79bf9a95c4f04ccdbda8fae1fe15d5491` is not used as this candidate.

## Conflict resolution and protected contracts

Six paths overlap between154 and144; C0 overlaps neither. Two text conflicts were resolved additively:

- `.agents/skills/ci-final-tree-verification/SKILL.md`: retain all154 admission/import/finite-authority/lease/subtest lessons and all144 bounded physical tar/gzip/PAX/metadata/distribution-input lessons.
- `tests/packaging/test_p1_distribution.py`: retain `stage_support` and `check_sdist`, `compare_wheels`, `save`; preserve pre-extraction validation, independent install authority, full wheel/metadata/RECORD comparison and original behavior assertions. Imports are sorted, with neither contract discarded.

The four automatic merges retain Access selection/failure propagation/always-upload and the three distribution verifiers' independent source/install authority plus hardened sdist checks. `audit/provenance-results.json` records all six source HEAD/tree/blob and final blob/SHA256 identities; `conflicts/` preserves the exact conflicting text and all three Git stages. Actual packaging133, installed lanes and full source results below exercise these contracts; static provenance alone is not called runtime acceptance.

All160 product source blobs equal154, including the exact SQL definitions of `i2_transfer_stage_fence` and `i2_transfer_report_stage_fence`; both exist on the normal composed schema and remain fail closed. All31 numbered Accepted ADR files present in154 are unchanged; ADR0033 is exactly the reviewed144 addition. All historical evidence from154/144/147 remains in Git with unchanged blobs, including FAIL reviews (7,625 / 2,797 / 2,711 overlapping paths, never summed). See `audit/protected-inputs.json` and `runtime-schema-fences.json`.

## Actual local execution

One final ordinary invocation completed **6,497 unique = 6,198 PASS / 279 FAIL / 20 ERROR**, exit1; skip/xfail/xpass0. It collected6,499 total nodes and explicitly omitted the live `tests/live/test_smoke.py::test_selected_repository` and benchmark `tests/e2e/test_github_sync.py::test_nested_pagination_stress_workload`. The independent reconciler verifies19,471 ordinary phase reports plus57 additional passing SubtestReports against the raw controller/worker/journal/JUnit records. The generic reused once-per-phase flags are false because they count subtests as extra calls; these flags are preserved, not relabeled. The separate reconciler proves ordinary phase completeness and preserves every subtest.

Frozen154's baseline is **6,344 = 6,045 PASS /279 FAIL /20 ERROR**, not the old79 comparison. All486 historical execution inputs were checked against actual154 Git blobs. All6,343 common nodes retain outcomes/phases. All299 unsuccessful node/phase keys, actual exception classes, typed refusal codes and actual project-frame function sequences match; **0 resolved cases and0 new integration regressions among common ordinary nodes**. Four actual frame coordinates change only `test_p1_distribution.run` line26→27 for the four retained P5 packaging failures. Raw JUnit messages differ at19 nodes and raw traceback bodies at299; the full pairs remain saved, not claimed byte-identical. See `source/compare154-full/`.

There are154 new passing nodes and one removed **passing** README parameter, replaced by the reviewed144 lightweight-sdist test. `baseline154-node-delta.json` enumerates the exact delta and `node-replacement-map.json` maps original assertion meanings: no full runtime acceptance, no runtime lanes and complete unexecuted coverage remain; obsolete all-preparation-none becomes selected sdist/dependencies plus no wheelhouse. This is not removal of a failure to hide it.

Separate diagnostic **745 =446 PASS /279 FAIL /20 ERROR**, exit1, zero skip/xfail, is never added to the ordinary count. All745 call-phase assertion AST-entry sets and all299 unsuccessful all-phase sets match154. Two passing P6 parameter nodes have a different setup association of the unchanged session-fixture subprocess assertion under worker scheduling; the global statement-entry set matches exactly. `diagnostic-assertion-delta.json` retains those two differences. No new downstream assertion reach is claimed. The trace covers the main worker thread's statement entry only, not subexpressions, other threads or child processes.

Historical labels242 I6-C /14 I7 /43 Transfer-stage remain the owner-provided154 baseline partition; comparison uses actual current nodes/phases/exceptions/refusals/frames/reached assertions instead of forcing labels. The legacy79 checker separately reports79 baseline versus299 current,0 resolved and220 additional: this is stale-scope evidence, not220 new integration defects. Raw failures remain preserved.

Separate source lanes completed with zero fail/error/skip/xfail and exit0: M01 **38**, raw-dictionary/strict wire M02 **61**, retained admission **13**, normal **208**, attributed Author **34**, saved counterexamples **33**, and current originals/admission/fence/OID controls **202**. These overlapping invocations are not added to the ordinary total. Exact collection, JUnit, starts, report classes and ordinary phases reconcile. See `i6/REPORT.md` and indexed raw receipts.

The I6 probes preserve full Parent and endpoint originals, service-issued current policy/selection, foreign service/policy/forged-principal refusal, first/replay/revocation and leases through the actual outer commit. Actual second endpoint INSERT, revocation after that INSERT, SAVEPOINT RELEASE denial and deferred COMMIT failure roll back the unit without damaging original Parent/Event evidence. Normal Provider/Exchange routes retain their refusal. v5 seven-column Resource rows, strict/canonical recursive identities, raw received-dictionary digest before normalization, cumulative pre-work reservation, atomic omissions and original terminal/Source/Coverage are exercised. The fresh1001-row budgets0/1/17/prior17 perform0 embedded parses/0 characters and charge1/2/18/18;81 further scanner observations pass. These are operation/allocation observations, not comparative timing benchmarks.

Policy, callsite index, schema audit, all four P1 fingerprints, architecture boundary, Ruff lint/format and report validation pass. Python3.12.14 actually loads SQLite3.53.1/source ID `c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`; compile options, PRAGMAs, interpreter hash and strict/JSON/product capability evidence are recorded. No SQLite or Python replacement/version matrix was prepared. Preliminary harness mistakes remain separate in `static/` and runtime probe attempts: default uv cache was read-only, one guessed CLI command exited2, built-in `_sqlite3` has no `__file__`, and Row objects needed explicit metadata conversion. These did not suppress or alter product results.

## Distribution measurements and installed behavior

Fresh current inventory is **160 product files / 6,025,551 bytes**:137 Python,19SQL,2JSON,2GraphQL. Every required product and builder input survives. The product sdist excludes historical evidence/docs/tests/scripts while preserving those files in Git; it is not claimed to be a standalone developer/test archive.

| Measure | Actual | Preserved finite bound |
| --- | ---: | ---: |
| Compressed sdist | 702,494 | 2,097,152 |
| Regular-file bytes | 6,041,897 | 8,388,608 |
| Logical members / physical headers | 164 / 164 | 512 |
| Whole tar-stream bytes | 6,174,720 | 8,922,624 |

sdist SHA256 `9d228f889f9507cdc5a166b9658e80873fcbd48255c6c958eb90e33954014b54`; source inventory SHA256 `38592a0e30468a80e442ee35d514673beace31eb98daf5cfda1109ac1675d4ed`. Focused packaging **133 PASS**, exit0, includes CRC/ISIZE/trailer/EOF/extra-stream, PAX/abnormal extension/hidden data/tar padding, strict PKG-INFO identity and all size/completeness gates.

The direct wheel is built explicitly; the derived wheel is rebuilt independently from a validated extracted sdist outside Git/source checkout. All164 member names and uncompressed bytes, ZIP metadata, package metadata, entry points and every RECORD entry match. Both wheels are791,300 bytes/SHA256 `2452e419e06eea774805fc89358130538c50fdd313fdb0fb9b82b230e99a39d8`. The actual archives, exhaustive member manifests and RECORD files are retained in `distribution/`.

Each artifact's separate fresh installed environment passes safety626,wire212,attributed review204,resolved-wire4,saved33,Author34,new regressions56, plus I2/I3 probes and CLI doctor. All ordinary phase/node/import checks pass and imports resolve to external site-packages, including child CLI. These overlapping lanes cover894 unique ordinary source nodes; **5,603 source nodes /215 files are not executed in these installed lanes**, with exact lists saved. Full installed-suite acceptance is not claimed.

The unchanged original minimal Access smoke is separately **FAIL1/exit1 in each distribution**, `AdmissionRefused/PERMISSION_DENIED` at the unconnected I6-C boundary. Each trace enters26 original assertion statements;28 subsequent statements remain unreached, including the historical v4 tail. No excessive grant, assertion removal or skip hides it.

## C0 real compressed-ZIP boundaries

Fresh real CLOSED ZIPs of2,097,151 and2,097,152 bytes pass;2,097,153 and2,323,560 bytes refuse exit1 with **zero stdout bytes** and the uploaded-artifact stderr fallback. A6,120,583-byte expanded receipt compressed to18,794 bytes passes. ZIP CRC, receipt-index payload hashes/bytes, binding, BEGIN/DATA/END SHA256/length/base64 and unchanged source artifacts are verified. Ten before/fixed observations and a separate uninstrumented overflow control pass; five exact ZIPs are retained. No mocked length or raw payload size substitutes for the real ZIP measurement. See `c0/`.

## Actual initial hosted CI and routing

All three initial PR155 runs reached terminal outcomes on published executable freeze `fb5d7b5a`, actual checkout `c915fc731bd60339e681a6af8f86a470058a5e06`, ordered parents154/feature and effective tree `d2010275a90ae6b6cb728344d5708057a79110cd`:

- [Development40002761103](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40002761103) **SUCCESS**, `development_checks_passed`, `full_acceptance=false`, **0 product pytest**,232 required/unexecuted files. Its actual hardened sdist gate matches the measured inventory above. Separate infrastructure unittests31+4 pass.
- [Access40002761153](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40002761153) **FAILURE**. Main2786=2487PASS/279FAIL/20ERROR is wholly inside broad3148=2849/279/20. Their actual union is**3148 unique ordinary product nodes**;**3349 source nodes /143 files and all154 newly added nodes are omitted**. Both installed I4/I5 cohorts217/29 pass on each wheel; they are overlapping additional invocations, not summed into the ordinary union. Original Access refusals remain failures.
- [Pages40002761106](https://github.com/TakashiSasaki/git-repo-db/actions/runs/40002761106) **SUCCESS**;8 documentation tests pass and deployment is skipped.

Actual Development receipt89,520 bytes/SHA256 `666e08b3818cd465b3e64cc2c70db6e5be86dfb23b1018fc9f512cc1c4017d29` verifies all24 indexed payloads. Access receipt1,992,791 bytes/SHA256 `65ab48ba62dad77faa806632c268fb642064e08ad59edf27d0bfd6c6b94c017d` verifies all123 indexed payloads. BEGIN/DATA/END, ZIP CRC, complete indexes and actual run/feature/checkout/tree binding are checked. A line-leading BOM initially omitted one DATA record and caused a real hash failure; raw failure and twelve strict parser controls are retained. The existing CI skill now records only the verified prefix-only adjustment; no payload repair or authorization fallback is introduced.

Fresh source-to-hosted comparison for both Access lanes finds exactly299 same identities/phases/outcomes/first-line messages/refusal-token sets. Full messages match280/299; rendered project-frame projections135/299; raw traceback bodies0/299. Hosted actual ExceptionInfo/assertion sidecars were not emitted, so their equality/reach cannot be inferred. See `source/compare-hosted-initial/`, with raw pairs and exact omissions.

Actual uploaded artifact metadata/logs were read, but downloads for artifact IDs12521924254,12522818279,12522517787 returned Azure **Forbidden /0 bytes**, with no retries. Access upload metadata reports795,331,408 bytes and its digest; that full archive was not downloaded or independently byte-hashed. The verified in-log receipts supply the available payload evidence. **No actual hosted overflow was exercised on this tree**: its real Access receipt is below2MiB. Normal upload completed; direct download remains denied. Prior/local overflow success is not substituted for hosted overflow.

The renewed150 routing audit records the existing missing direct Access paths for some I6-A/B modules/tests as a coverage limitation. No actual CI contract violation was reproduced, so no extra duplicate full suite or CI correction was added. Actual candidate planning and exact path predicates were rerun; Release was planned only, never dispatched. Final evidence-HEAD started-CI identities/outcomes are bound externally in PR155 and the final handoff. CI's `acceptance_input_hash` may change when unclassified raw evidence files enter Git even though all493 execution/distribution inputs remain identical; its actual final manifest hash is recorded separately, never substituted for the execution-input or sdist-inventory hashes.

## Remaining boundaries and reviewer handoff

The candidate is fixed154+147+144 only. It neither tracks nor imports parallel taskA's working/unreviewed I6-C changes. Independent non-Author review of this actual integration candidate remains required. Future reviewed I6-C integration must re-freeze its head/tree and rerun service/selection/lease/transaction composition in Provider/Exchange/coordinators, original Parent/endpoints and Source/Coverage/terminal atomicity, v5 strict/raw-digest/work controls, both fences, Access/P5/P7 and original installed smoke. Reconcile all299 failures at actual reached assertions: an old refusal disappearing can expose a downstream failure, which is not automatically a resolution. `audit/CONTRACTS-AND-HANDOFF.md` names the exact files/tests/dependencies and distribution/CI revalidation.

A later cross-task handoff reports that taskA found a new budget test where queue allocation could occur after remaining work was exhausted. **Applicability to this frozen154/144/147 tree is provisional and has not been reproduced here.** No taskA changes or new test were pulled/imported. The passed38/81 scanner probes establish their measured cases, not absence of this possible inherited limitation. A finding already present in154 would be distinct from an integration-induced regression; no verified defect in this fixed tree is claimed without reproduction. Independent review and the next integration checkpoint must obtain the exact reviewed counterexample, reproduce it on frozen154 and this candidate, then revalidate the scanner path and resulting I6-C composition separately.

Development success is not Release acceptance. No Release workflow, main merge, existing-PR-branch modification, rebase/force-push, release/deployment, real catalog or real user data was used. This task publishes a Draft integration candidate only. Scope-excluded I7/I8/ordinary Transfer and subsequent integrated/runtime/independent-review/explicit Release gates remain.

The existing CI-final-tree, three-store and lessons-to-skills procedures were applied. The resolved skill retains both reviewed sets of verified lessons. The existing CI-final-tree skill adds the verified line-leading BOM receipt lesson, supported by the preserved hash failure and12 strict positive/negative controls; no new overlapping or speculative skill is created.

## Evidence integrity and publication identity

`ARTIFACTS.json` binds all delivered payloads; `TRANSPORT.json` records lossless compression/renaming of external raw evidence. Nested ORIGINAL indexes remain historical pre-transport snapshots, with current paths verified by the root index; the I6 delivery's own verified transport/index is also retained. Probe Python is stored as `.py.txt` to avoid accidental collection. Synthetic databases, venvs, caches and tokens are excluded.

Published executable freeze and its actual GitHub test-merge/tree are recorded above. A later evidence-only commit changes this new directory plus that verified skill prose and verifies all493 source/test/build/workflow/README/distribution inputs against the tested freeze. Its final HEAD/tree and final started-CI identities are bound externally in PR155's body and the final handoff, avoiding an impossible committed self-hash. No unexecuted rerun is claimed.

The first unpublished evidence commit retained raw Git graph alignment whitespace. Its staged whitespace preflight failed, but a shell chain continued to commit; `PUBLICATION-CORRECTION.json` and the failed log preserve this publication-harness mistake. A normal additional commit losslessly compresses the graph, updates references/index and rechecks all493 execution inputs. The earlier commit remains in history; no product test is relabeled or rerun claim made.
