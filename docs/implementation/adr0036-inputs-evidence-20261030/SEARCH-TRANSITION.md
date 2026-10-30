# First RefObservation Notes Search unit

Cloud branch `codex/adr0036-search-projections`, parent PR 227 fixed at
`a71fa7f99bf67ed166432a597d4469470863a366` / `b8e9be29f0e75be598260cb40bf305b851628a92`.
PR 226 stays `1e70d1dd...`; fresh main `2ff4aab59dcdbada264d9a6a978c07b6ac4ad0d2`.
Open PR check found only 226/227. Parent reported scoped PASS for 227 (32 cases);
this author does not claim independent approval.

The common pinned Search extraction adds exact observation/Claim/Mapping-keyed
Notes documents, including Group-only/partial reports. Every Mapping alternative
and its original provenance is retained in summaries. Exact-Claim checked Core
readers supply inventory/Coverage, role evidence and eligible-copy bytes; neither
a shared root nor another Claim lends proof. Historical complete reports remain
reported while current partial Coverage stays partial. Missing body permission
leaves metadata searchable; selected corrupt copies stop the catalog. Rebuild
and authority fallback share this extraction. Legacy Capture documents coexist;
rootless observations without Mapping do not acquire invented Mapping documents.

Finite work is shared across new-model extraction, and caller work may accumulate
across search/rebuild calls. `_QueryWorkBoundary` crosses all snapshot/classifier
layers; caller errors keep identity and do not diagnose corruption. Keys, summaries
and output text are bounded/metered; oversized semantic keys refuse rather than
become hashes or invalid cursors. No schema/wire/physical retirement or Schema21
activation. Old public APIs/families remain later work.

Actual verified Python 3.12.15 / SQLite 3.53.1 / x86_64, `scripts/local-run.sh`:

| Profile | Actual result | Wall |
| --- | --- | ---: |
| ref-search-probe | 20 passed / 8 fixture assertions failed: reported `tree` and verifier `native-notes-tree` are distinct interpretations, correctly distinct documents | 7.81s |
| ref-search-scope-fixture | Only those 8 rerun with matching interpretation: 8 passed | 5.85s |
| ref-search-coverage | 4 new later-partial/current-body/cumulative-limit cases passed | 3.39s |
| ref-search-final | 41 passed, no failures/skips; frozen coherent implementation plus minimum legacy Search/Core-only import regression | 15.55s |
| ref-search-limit | 4 new document-limit/noncorruption cases passed | 2.42s |
| ref-search-key-limit | 4 new cursor-key-limit cases passed | 2.63s |

The 41-case clean execution is `f8f2d8b8dbd4d3f118578f7a4eb415cd13b10d51` /
`a46d097c6ef1cbe00d8d8d04cb7508549fa8f1b7`. Shared preprocessing reservations changed
after initial probes, justifying the frozen minimal cohort. Later changes only
classify local hard limits and bound cursor keys; only their new 4+4 cases ran.
Latest tested code is `051eb6088fe8d72b4af9e7f88cc3f080d6c5e6a0` /
`ea2547dbd04019fcd824a7006829a50a86f18705`; earlier successes are not relabeled as
fresh execution there. Ruff/format and whitespace checks passed. Full release,
installed behavior and broad independent cohorts were not repeated.

Existing complete logs/JUnit/journals/source receipts remain in
`artifacts/ref-search-{probe,scope-fixture,coverage,final,limit,key-limit}` in the
author environment. No new archive or custom phase audit was created. Evidence-only
commits do not cause local product retesting. Final HEAD/tree and CI are given in
the Draft PR/handoff; independent review remains pending. No merge/deploy, formal
APPROVED or old403 artifact access/retry. Requested Sol/high is not runtime-attested.
