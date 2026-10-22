# Task G — Independent review of ADR 0031 I2 / PR #124

Publication note: the owner explicitly authorized this new Draft PR after the review freeze. The [original report and raw evidence](task-g-review-evidence.zip) remain byte-preserved in the ZIP; links to archived evidence below identify its member path. This rendered report changes only publication context and local-link destinations. Product runtime results still bind to the reviewed commit, not this later evidence-only commit.

**Verdict: READY WITH CONDITIONS for the bounded I2 persistence and staged-refusal implementation. Whole ADR 0031 / whole-product acceptance remains NOT READY.**

The required Transfer fences and their supported routing are coherent on both actual SQLite runtimes. No I2 implementation defect explains the retained 59 failures / 20 setup errors. They remain failures/errors, with the downstream assertions unexecuted. A new counterexample, G-R1 below, demonstrates incomplete recovery coverage in the direct field facade. It is recorded as an I7 follow-up, not silently counted as a success or confused with the specifically required I2 Transfer-storage stop.

This reviewer did not author Task E. No subagent was used. Existing author tests and diagnostic scripts were re-executed and examined; their authorship has not become independent merely by running them again. The separately authored 46-case suite and installed counterexample provide additional evidence. Only synthetic, disposable catalogs were used. During the original review execution there were no GitHub writes, product/test/ADR changes, merge, release, deployment, or live Provider/catalog operations.

## Frozen inputs and sources

| Object | Commit | Tree |
| --- | --- | --- |
| Reviewed / actually tested HEAD | `4cb90d35bd9c572239496a24cb0dd62049029235` | `991d588051766ef1b6ba7c1db9309d60caf47fee` |
| Task E executed source | `cb1df83afc543d74df8b16327bfb2c418786b3b2` | `9d0130aa3324ff36e4bcda0cfc89258e951a747a` |
| PR #123 / implementation base | `c1b62d216db2b728a4c8cb1821250335fcafc534` | `9e970f71b27d8d1c8cec3971cbca8690edb27da1` |

The only executed-source-to-HEAD changes are five added files under `docs/implementation/evidence/adr0031-i2-task-e/`. All 3,783 predecessor tracked files are identical. The HEAD inventory contains 3,788 tracked files. Source, tests, scripts, lock and packaging inputs are unchanged between the two commits. The reviewed worktree and original shared checkout retain clean tracked status. The review lives outside the source tree.

Full HEAD input manifest SHA-256: **`40b62bf98099aa538bea1c58b1003b0a5580b2e3f4044bf347191cf0fdaa1e4f`**. See [input audit](task-g-review-evidence.zip) (archive member `evidence/input-audit.json`) and [full manifest](task-g-review-evidence.zip) (archive member `evidence/full-input-manifest.json`). Both broad runs independently recorded identical input hashes before/after execution. Sealed independent receipts bind both reviewer-authored drivers before/after each child process.

Consulted contracts and actual implementation, rather than treating PR descriptions as proof:

- [Accepted ADR 0031](https://github.com/TakashiSasaki/git-repo-db/blob/4cb90d35bd9c572239496a24cb0dd62049029235/docs/adr/0031-generalized-context-resources.md), companion Resource schema and implementation handoff.
- [PR #120](https://github.com/TakashiSasaki/git-repo-db/pull/120): complete native declarations, bounded row-local UDFs, direct BINARY triple, child-first admission, local API/storage closure and explicit later-stage dependencies.
- [PR #122](https://github.com/TakashiSasaki/git-repo-db/pull/122): report fence plus both endpoint fences, pre-conflict rejection, selected-unit preflight and explicit unsupported consumers.
- [PR #123 report](https://github.com/TakashiSasaki/git-repo-db/blob/c1b62d216db2b728a4c8cb1821250335fcafc534/docs/implementation/evidence/adr0031-i2-f1-task-f/REPORT.md): all five mandatory implementation conditions.
- [PR #124](https://github.com/TakashiSasaki/git-repo-db/pull/124): actual 42-file diff, implementation record, Author report, raw evidence and scripts.

Initial/final GitHub metadata snapshots are retained. #120/#122/#123/#124 remained open Drafts at their specified heads/bases. The Author archive SHA-256 `c6ab88560c125005f3b911dc41bbfe9f1b8f4d890d7bcf71928ca29c43a2908e` and all 219 indexed members verified. This establishes binding, not independent acceptance of their results.

## Actual independent runtimes

Official amalgamations were freshly downloaded and separately compiled with GCC 14.2.0. Runtime versions were measured through SQL; no Python/SQLite version constant was changed. Actual test interpreter: dynamically linked CPython **3.13.5**.

| SQLite | `sqlite_source_id()` | Official archive SHA-256 |
| --- | --- | --- |
| 3.51.3 | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` | `acb1e6f5d832484bf6d32b681e858c38add8b2acdfd42ac5df24b8afb46552b4` |
| 3.53.1 | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` | `36ad6e7f38540a3b21a2ac36340833f0a9e426bc1c752751c3ba669466827eae` |

[Build provenance](task-g-review-evidence.zip) (archive member `runtime/provenance.json`) records URLs, compiler argv, elapsed time, successful compiler exits, source/header/library hashes. Per-run receipts record compile options and PRAGMAs. Normal profile: FK=1, recursive triggers=1, ignored CHECKs=0, deferred FKs=0, trusted schema=1, synchronous=3/EXTRA, UTF-8. Initialized product databases use WAL. In-memory SQL diagnostics report memory journaling; they do not demonstrate crash/power-loss durability.

An initial attempt used the preinstalled statically linked CPython 3.12.14. Its measured SQLite remained 3.53.1 despite `LD_LIBRARY_PATH`, so the requested 3.51.3 assertion correctly aborted before collection: exit 1, **zero test cases**. That attempt is preserved separately and excluded from all final counts.

## Executed results and exits

The two runtimes produced identical node outcomes.

| Final lane, per runtime unless stated | Executed | Result | Actual child/process exit |
| --- | ---: | --- | ---: |
| Broad retained regression cohort | 2,826 | 2,747 pass; 59 fail; 20 setup errors; zero skip/xfail/xpass | **1** |
| Dedicated I2 + P1 installed subset, already included above | 86 | 86 pass | Included in broad exit 1 |
| Existing Task F-derived product SQL diagnostics | 301 groups | 301 pass; 300 involve product DDL, one old-composition comparison | **0** |
| Reviewer-authored sealed counterexamples | 46 | 44 pass; 2 fail (G-R1); zero setup errors/skips | **1** |
| Direct-wheel / sdist-wheel installed Author I2 probes, four runtime/artifact combinations total | 4 processes | All complete successfully, installed files match source | **0 each** |
| Unmodified installed Access smoke, four combinations total | 4 processes | All stop at Provider Transfer preflight | **1 each** |
| Reviewer-authored installed metadata/recovery probe, four combinations total | 4 processes | Healthy controls succeed; G-R1 reproduced for Global and Scoped in each process | **1 each** |

The SQL reruns are requirement-overlapping diagnostic groups, not 602 additional unique acceptance tests. Likewise the 86 are not added to 2,826. The preliminary 32-case and expanded unsealed runs are preserved, superseded by the sealed 46-case runs; they are not added to the final count. The sealed recorder exits 0 when it successfully captures all child results, including failures. The separate assessment process exits **1** to preserve the incomplete full-target acceptance result.

Ordinary collection: **5,369 collected, 5,367 selected after two opt-in deselections**; no collection errors, exit 0. **2,541 ordinary selected nodes were not executed**. No full release-suite claim is made. The original Task A final-r2 2,740-node list is included without missing nodes; its selected-list SHA-256 is `a67c1d1bac48a3b22be33c54943acfb67ef3d5b9dd4f4fac8deabd00b8c64fdd` on both original lanes. Duplicate-aware selected/JUnit/start/phase reconciliation passes for both new broad runs. Every setup error has no call phase. See [Task A retention](task-g-review-evidence.zip) (archive member `evidence/task-a-retention.json`), broad summaries, journals and XML.

Schema generation, physical schema audit, callsite dependency audit, implementation-boundary audit and registration audit all exited 0. These static checks do not turn the runtime failures into passes.

## Findings against the mandatory I2 contract

### DDL, identities, references and connections

The implemented Resources table retains `STRICT, WITHOUT ROWID` and the three-column PK. All four declaration columns are non-key; `reference_document_kind` is a generated absence projection. Resource index key slots, including exact 4/5/6-column UNIQUE targets, are BINARY. The Resource FK points only to Provider, with no namespace/Parent-existence FK. Child-reference comparisons remain exact. Wrong-case reference counterexamples fail without changing authority.

The two required UDFs are versioned, deterministic (flag 2048), row-local predicates using the shared bounded I1 codec. SQL accepts canonical String/recursive Array identities and refuses NULL/BLOB, forbidden JSON types, alternate/noncanonical spellings, malformed Unicode and over-limit values. The inclusive byte/depth/node limits and pre-decoder bounds are exercised. Complete scoped metadata reconstructs the exact key; Global metadata repeats the full key ID. No shape-based Global/Scoped dispatch was found.

Actual product composed Context DDL SHA-256: **`2149fb9f37187433e12a47e11e32ccbdac095e6a443ebb0c4e96dabebdda657d`** on both runtimes. Declared DDL/schema fingerprints match. Product Core/Operational/Search DDL and fingerprints, Access schema and public default Schema 21 are unchanged by the diff.

Connection review covered factory initialization/open/connect, expected-schema construction, production Context transaction/snapshot, coordinator read/write capabilities, query/Search use of those capabilities, and recovery schema/Core/Context validation. The normal target paths register the same functions and verify the required profile. Missing-function and unsupported-PRAGMA controls fail closed. Recovery schema/semantic validation now configures the trusted profile before checks. SQLite backup destinations merely copy bytes; untrusted salvage/identity extraction are explicitly read-only candidates, not admission or schema-validation paths. Those distinct paths are not misreported as normal trusted decoders.

Physical inventories, SQL/parameters, extended errors, full pre/post rowsets, PRAGMAs and function flags are preserved in the SQL receipts and installed I2 receipts. Static audits also pass. This is coherent packaged I2 behavior, not a claim of arbitrary raw-connection/DDL-tampering safety.

### Declarations, child-first storage and replay

The independently authored shape-ambiguous example uses the same triple as either a genuine Global Document or a scoped declaration in separate catalogs. Three separate reopen/replay cycles preserve the original declaration and query output. The namespace Resource is absent initially, then arrives, while zero Parent reports are inferred. Global recursive native IDs and scoped recursive local IDs retain their exact distinction.

The existing product diagnostics separately exercise all opposite-declaration replay/conflict verbs: INSERT, IGNORE, DO NOTHING, REPLACE, OR REPLACE, UPSERT and no-op UPSERT; contradictory declarations refuse before duplicate shortcuts. Equal metadata replay and reconstructed keys retain the complete declaration. Typed document omission refuses rather than guessing the key shape. Provider REST and GraphQL non-Transfer paths persist native local/Node coordinates and reopen without the Task A scalar-local storage gate.

Semantic Parent remains in `resource_relations`. A lawful general Parent report to I8 is retained independently of I7; this is generic common storage. It is not a proof of completed I3 typing or eligible Transfer support. Native namespace alone supplies neither a Parent report nor Transfer evidence.

### Transfer staging and real consumers

Both unconditional packaged INSERT fences are present: exact `transfer_event_report`, and both `transfer_from_repository` / `transfer_to_repository`. Existing immutable UPDATE/DELETE guards close generic-to-reserved updates and UPSERT-update paths. Trigger comparison is BINARY; distinct case/whitespace/NUL names remain opaque and gain no Transfer meaning.

The unchanged Task D literal admits the Provider-only report in the historical composition and refuses it with 1811 in product DDL. The 301 groups cover report/from/to, missing/correct/wrong/native dependencies, true collisions, conflict/no-op verbs, UPDATE/UPSERT, multirow ABORT, savepoints and reopen. The new suite adds multirow INSERT SELECT RETURNING with a preceding valid row and caller savepoint work, both endpoint roles with actual stored PK collisions, and a Provider mixed sequence with `transfer_event=False` but a generic reserved report. All of those new refusal cases pass with equal complete authoritative rowsets.

Typed Context, generic relation, Provider `admit_unit(s)` / `admit_batch` and Transfer query/export methods reject explicitly. Real import preflight is after version/digest/domain/receiver-selection validation but before dependency rewriting, package replay/binding and authority admission. Existing product tests run rechecksummed endpoint/report-only packages, mixed order, primed replay and nested-extension parser rejection. Independent Core-only receiver selections remain usable. The nested normalized helper is not credited as a real parser. Current Document/review/comment/thread wire selections refuse explicitly pending I6; no old-wire declaration inference was found.

For an impossible **Transfer** report or either endpoint in a restored exact packaged schema, ordinary Context, query, export and Search enter persistent Recovery Stop before exposure. Unsupported input itself does not cause a false corruption stop. Rows are retained without hiding, deleting or repairing them. Malformed schema is a format refusal. New G-R1 below concerns a different non-Transfer metadata path.

## Classification of the existing 59 failures / 20 errors

Classification uses actual trace locations, affected selected fixtures and the staged contract; an exception name alone is not proof that later semantics passed. Detailed node-by-node [CSV](task-g-review-evidence.zip) (archive member `evidence/broad-3513-dynamic/failures.csv`) / [JSON](task-g-review-evidence.zip) (archive member `evidence/broad-3513-dynamic/failures.json`) are supplied for each runtime. Both outcome maps agree.

| Classification | Call failures | Setup errors | Review conclusion |
| --- | ---: | ---: | --- |
| I2 implementation defect in these 79 nodes | **0 found** | **0 found** | No unexpected exception category or wrong selected-stage refusal found |
| Intended ADR 0031 I3–I5 / matching Transfer consumers | **45** | **20** | `I2_TRANSFER_UNSUPPORTED`; all 20 setup errors share the I5 module fixture boundary |
| Intended I6 identification Wire dependency | **14** | **0** | `I2_IDENTIFICATION_WIRE_UNSUPPORTED`; includes the four P5 packaging cases |

The 14 Wire failures include five selective-Exchange tests, four P5 Exchange tests, one I23 test and four P5 installed cases. For example, collection anti-forgery tests fail during source export of a declared scoped child, **before** mutation/import and their later anti-forgery assertions. They therefore supply no successful coverage of those later checks. The Transfer cohort likewise does not establish completed G3=A SQL support, actual event semantics or successful Transfer roundtrips merely because the earlier scalar-local gate disappeared.

### Task A's four original failure nodes: actual new first positions

| Retained node | First new failure on the reviewed HEAD | Not reached |
| --- | --- | --- |
| `i2/test_provider_intake.py::test_non_transfer_cannot_promote_repository_fields_or_forged_flag[True]` | Test line 376 calls `ctx.transfer_event_reports()`; `production_context.py:987` refuses. The preceding non-Transfer `admit_unit` did complete. | The second conjunct's repository-relations check and later forged-flag promotion check |
| `i2/test_provider_intake.py::test_graphql_transfer_parent_namespace_and_original_type` | Test line 408 → `acquisition.py:1519` → `_preflight_units:1471` | Successful native-Issue Event/report/endpoint and original-type semantics |
| `i2/test_provider_intake.py::test_graphql_event_does_not_infer_destination_from_current_issue_repository` | Test line 745 → same preflight at 1471 | Destination non-inference and one-sided Transfer assertions |
| `i5/test_independent_e2e.py::test_transfer_reports_never_mix_across_observations_or_identifier_namespaces` | **Setup error**, `assembled_template` line 271 → same preflight. The test body never starts. | Event pairing, namespaces, onward Exchange/query/Search/backup; the same fixture blocks 20 bodies |

Full original traces are in [task-a-four.json](task-g-review-evidence.zip) (archive member `evidence/task-a-four.json`).

## New counterexample G-R1 — direct field facade does not check stored identification

**Medium follow-up; classified as remaining I7 recovery coverage.** The bounded I2 Transfer invariant is enforced, but complete stored-identification verification is not universal across low-level production Context consumers. The I2 plan assigns complete recovery integration to I7 (file map entry for recovery; remaining-work section), and Task F condition 4 specifically requires the impossible reserved Transfer representation stop. Therefore this additional stronger probe does not overturn narrow I2 readiness. It must be carried into I7 acceptance; complete recovery coverage must not be claimed now.

Reproduction, on both runtimes and all four isolated installations:

1. Admit a healthy Global or Scoped `document`, with a valid title FieldCandidate. Both declarations deliberately use a key whose array shape is ambiguous.
2. In a disposable diagnostic connection only, temporarily remove Resources triggers and ignore CHECKs; change only `provider_document_id` to canonical `"WRONG"`. Restore all triggers and normal CHECK settings.
3. Verify `sqlite_schema` is exactly the packaged schema, and normal schema validation passes. `validate_stored_context_relations` correctly raises `StoredContextInvariantError` for the invalid declaration. The corruption injector is not a supported write route.
4. Open **production** `Context.snapshot` and call `ctx.candidates(key, "title")`. It returns the retained candidate; `p1-recovery-stop.json` is absent.
5. Call `ctx.identification(key)` in a new snapshot. It raises `AUTHORITATIVE_CORRUPTION` and persists Recovery Stop. All authoritative rowsets remain unchanged.

The sealed independent cases `test_invalid_identification_stops_selected_authority[candidates-global]` and `[candidates-scoped]` fail with DID NOT RAISE. The other eight route/declaration controls (Resource get, Resource list, Search, rebuild) stop correctly. The installed receipts show `ordinary_read_accepted=true`, `stop_after_candidates=false`, `stop_after_identification=true`, `authority_unchanged=true` for both declarations in each combination.

Cause: `production_context.py:809` wraps FieldCandidate decoding; `p1_context.py:704` reconstructs only field rows. `_validate_stage` at 357 checks Transfer representations. Neither path validates the referenced Resource's non-key declaration. `identification()` / `resources()` do validate it. Recommendation for I7: establish the stored-Resource validation boundary before direct field/other resource-owned reads and writes, and audit comparable facade routes. Do not add guessed declarations, silently filter claims or write repairs. This review does not change the product.

Executable repros: [test_independent.py](test_independent.py.txt) and the standalone [installed driver](installed_independent.py.txt). Failing probes are retained as failures. They are not skipped or changed into expected-success checks.

## Distribution binding and execution

Both variants were built anew from a clean Git archive of **the published HEAD**, installed non-editably into separate venvs for each runtime, and run with `-I` outside the checkout. Installed package origins are inside each venv. Complete installed-file hash manifests match source files. Reviewer-authored installed probes also use only the installed package, never the source/tests imports.

- Direct wheel and sdist-derived wheel SHA-256: **`991bd31ed13cafdcf5d452a80f87270f914f24f105ab998a9631021b7f688c47`**. They are byte-identical to each other and the Author's exercised wheel.
- Published-HEAD sdist SHA-256: **`d8ada8450180d02e6a34cee938ac96a0cd925680bd9178dd2ccf4cf5aab20da7`**. This matches the reported published-tree artifact. It is correctly different from Task E's execution-freeze sdist containing five fewer evidence files.
- Original Access smoke SHA-256: `eeca419cb9f1a18123d72eda443a17c338ff7e975f465f41b6ccb2835cc93717`; unmodified in all attempts.

The four ordinary installed I2 probes pass. The four original Access smokes exit 1 at `ProviderAcquisition.admit_batch` → `_preflight_units` / `I2_TRANSFER_UNSUPPORTED`; later assertions are unexecuted. The distribution orchestrator actually exits 1. All four new installed G-R1 processes exit 1 after recording both Global/Scoped exposures and successful positive/detection controls. The initial installed diagnostic had an incorrect exception catch for `StoredContextInvariantError`, failed before the candidate probe, and is preserved separately; it is not credited as reproducing G-R1. The sealed corrected receipts are the final installed evidence.

## Conditions and residual dependencies

1. Keep both packaged SQL fences and explicit consumer/intake/import restrictions until one independently reviewed effective tree contains I3 typed Parent, I4 full-report/native-I7 SQL binding, I5 actual semantics/whole-unit Admission, and matching routes. A lawful I8 Parent report is still permanently ineligible as Transfer support for an I7-native Event; an absent I7 is a different resupply dependency. This review accepts neither guarantee as implemented.
2. I6 must carry complete Global/Scoped declarations and support real selected wire/import/export without inferring them. Re-execute all 14 blocked cases and their currently unexecuted negative assertions. Preserve independent Core-only selections, atomic groups, provenance and original times.
3. I7 must cover G-R1 and full stored validation, paired backup/restore/salvage and stop behavior. I8 must complete generalized query/Search integration. Existing successful basic Search/poison-Transfer controls do not establish those full stages.
4. Re-execute the 45 blocked call cases, the 20 blocked bodies, the original four Task A nodes and all original installed Access smokes after their dependencies are implemented. Do not claim full product/release acceptance from green I2 probes, the 301 groups, static audits or hosted Development checks with zero runtime tests.

No merge/release/deployment approval follows from this verdict. At the original evidence freeze, publication had not yet been approved and no Draft PR had been created. The owner subsequently explicitly requested publication by pull request; this documentation-only Draft PR performs that publication.

## Reproduction and evidence handling

See [README](README.md) for exact commands and artifact layout. Final broad logs/JUnit/journals, SQL rowsets/errors, package receipts, sealed reviewer probes, input hashes, build provenance and node classifications are included in the evidence archive. Runtime libraries, venvs, extracted full source copies and disposable databases are excluded from the portable review archive; reproducible build inputs and hashes are retained.

Procedures used: cloud-environment-runtime, efficient-repository-investigation, and the repository lessons-to-skills assessment. The reviewed `three-store-invariants` addition correctly warns against endpoint-only fencing, replay shortcuts, payload-text interpretation, poisoned-row filtering and nonisolated distribution builds. No skill was edited. Suggested reusable addition: test non-key declaration corruption through direct field facades as well as Resource list/query/Search, and distinguish a completed evidence-capture recorder from its nonzero child acceptance results. This recommendation is based on the sealed G-R1 evidence and does not redefine I2 scope.
