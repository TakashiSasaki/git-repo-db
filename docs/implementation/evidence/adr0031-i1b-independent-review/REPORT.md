# Independent ADR 0031 I1b adversarial review

Reviewer: independent non-author agent `/root/independent_i1b_review`, 2026-10-21 UTC. The implementation/validation author supplied the task boundary, but supplied no substantive review guidance or judgments. I independently discovered the live remediation PR. I made no changes to implementation source, tests, accepted ADRs, branches, PR metadata, or GitHub discussions. All execution used new detached trees, new venvs, and disposable state under `/workspace/independent-task-b-20261021`; the author's checkout and venv were never execution baselines.

**Disposition:** no new blocking defect in the bounded I1 codec/shared-key implementation was established. The original #117 tree has active validation-fixture failures; #118 repairs those boundaries. Generalized Resource persistence and complete product/distribution acceptance remain blocked by I2 dependencies. In particular, the in-memory global-Document guard is not preserved by triple/dataclass reconstruction and must not be represented as a durable admission guarantee.

This is a scoped review and evidence report, not merge, release, deployment, P8, or full product approval. All independent lanes completed; results and practical limits follow.

## 1. Verified source coordinates and scope

| Object | Commit | Tree |
| --- | --- | --- |
| Live main; merged I1a effective tree | `cb532242c7aa86c6af5b6232b71c0906ea38f5c5` | `318ad07874ab436206e6a61f231b308a421cfc54` |
| I1a #116 head, now merged | `d92377599a50f192f534836fc12402a5fe87ca83` | `318ad07874ab436206e6a61f231b308a421cfc54` |
| I1b #117, Draft/open | `32e5d4de67c0d436f7583d04e1cfd349b64b2bbd` | `708c860cd4badd4d787d4d8140b9626c80813be6` |
| Discovered validation #118, Draft/open | `9ea69ba8804a368802457950601a5a4027174c52` | `8183f346b3613ea1206b2c0ab3e6428f31614cd8` |
| #118 executable freeze, publication's parent | `d77acad2c2d97538479d7fa5489ecebfd5ad8f67` | `9e6a0d9db602446d4ce7e93d98f12533202e4b5e` |

I reconfirmed main/#116/#117 via live GitHub and `git ls-remote` before reviewing, then fetched exact objects into my own clone. I discovered [#118](https://github.com/TakashiSasaki/git-repo-db/pull/118) through live PR search, inspected its exact 36-path diff, and created a second detached worktree at its published head. Its 25 existing test files, verification script, generated callsite index, and nine report/evidence/skill paths change no `src/`, packaged DDL/fingerprints, dependencies, workflows, accepted ADR, schema contract, or implementation handoff. The publication adds exactly nine report/evidence/skill paths over its executable parent; all 429 frozen executable inputs match. End-of-review live refs are unchanged. I independently fetched published merge `4521ee0165ef5fc7587d87321842b00dc5395cc5`: its parents are exact #117 and #118 heads, and its effective tree is `8183f346b3613ea1206b2c0ab3e6428f31614cd8`. A disposable `git merge-tree --write-tree` against current main yields that same tree. See `final-git-binding.json`.

Read and applied: repository AGENTS; accepted ADR 0031 and relevant ADR 0001 validation distinctions; the generalized Resource schema and I1–I8 handoff; I1 implementation report; author raw receipts; both prior independent reviews (`codec-review/review.md` and `integration-review/review.md`). Their findings were hypotheses to verify. I independently compared all 426 I1 input hashes, all 48 indexed I1 receipt members, and all 123 indexed #118 receipt members with zero mismatches. The archive hashes and comparisons are in `historical-hash-verification.json`.

The independently generated AST inventory has 81 source call expressions: 66 strict constructors, six native factories, one scoped factory and eight scoped-decoder calls. Every location is present in the claimed 88-entry author inventory; its seven extra entries are explicitly labeled references/callbacks, including annotations. I inspected the changed production boundaries and relevant unchanged row/wire callbacks. Neither inventory is a whole-program data-flow proof.

## 2. Independent runtimes and execution

| Runtime | Independent interpreter | Actual SQL source ID |
| --- | --- | --- |
| SQLite 3.51.3 | New venv from `/usr/bin/python3.13`, Python 3.13.5; independently built shared SQLite | `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618` |
| SQLite 3.53.1 | New venv from supplied Python 3.12.14, embedded actual SQLite | `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9` |

I downloaded the minimum amalgamation from sqlite.org, built my own library with GCC 14.2.0, and compared `sqlite3.c` SHA3-256 `32d5424f97e0a7fc5ed2f6335afbb58be4e0298bd7117a34e39d345ff13d859e` and the source ID with the [official 3.51.3 release page](https://www.sqlite.org/releaselog/3_51_3.html). Current downloaded archive SHA-256 is `acb1e6f5d832484bf6d32b681e858c38add8b2acdfd42ac5df24b8afb46552b4`; my library SHA-256 is `525e2857153a83fd38ee160fc59062d723505afd5bddb7f5eeb85c96bb104041`. I also checked the newer source ID against its official release page. Commands, compiler, hashes and actual compile options are retained in `provenance.json` and per-run receipts. No shared author-built SQLite binary was used.

An initial uv-managed Python 3.13.5 was statically bound to SQLite 3.49.1 despite `LD_LIBRARY_PATH`; actual SQL detected this before any test execution. I created a separate dynamic-interpreter venv. No 3.49.1 run is counted as minimum validation. Dependencies were installed from an independent export of the repository's frozen lock.

My external `counterexamples.py` completed 35 observation groups per runtime; `exchange_probes.py` completed five more per runtime. They include 2,000 independently generated reference roundtrips per runtime, canonical/Unicode/limit cases, PR coordinates, GitHub namespace distinctions, nested MappingSupport/Coverage/Collection/selection references, fresh-checksum cursors, actual packaged storage controls and independently authored SQL. Two groups intentionally demonstrate unsupported product/metadata behavior; their successful diagnostic assertions are not successful generalized persistence. Counts overlap pytest and are not summed as unique acceptance tests.

The Exchange probes import actual digest-consistent packages into newly initialized disposable Core/Context/Operational stores. Valid composite references survive. Invalid root IDs, invalid nested Collection IDs, alternate-escape nested IDs and invalid Coverage owners fail before Context Resource writes, with zero rows before and after. An initial work-only receipt serializer tried to encode `sqlite3.Row`; I retained that script snapshot, corrected only the external serializer to tuples, and reran both runtimes. No product input changed.

| Independent lane | SQLite | Selected / executed | Passed / failed / errors / skips | Process exit |
| --- | --- | --- | --- | --- |
| Exact #117 nine-module cohort | 3.51.3 | 564 / 564 | 561 / 3 / 0 / 0 | 1 |
| Exact #117 nine-module cohort | 3.53.1 | 564 / 564 | 561 / 3 / 0 / 0 | 1 |
| #117 full ordinary collection | 3.53.1 | 5,181 / 0 | two collection errors; 2 opt-in deselections | 2 |
| #118 full ordinary collection | 3.51.3 | 5,281 / 0 | zero collection errors; 2 opt-in deselections | 0 |
| #118 full ordinary collection | 3.53.1 | 5,281 / 0 | zero collection errors; 2 opt-in deselections | 0 |
| #118 complete chosen broad cohort | 3.51.3 | 2,740 / 2,740 | 2,736 / 4 / 0 / 0 | 1 |
| #118 complete chosen broad cohort | 3.53.1 | 2,740 / 2,740 | 2,736 / 4 / 0 / 0 | 1 |
| #118 installed direct-wheel + sdist-wheel smoke | 3.51.3 | 2 artifact attempts / 2 | both fail at composite Event gate | each smoke 1; runner 1 |
| #118 installed direct-wheel + sdist-wheel smoke | 3.53.1 | 2 artifact attempts / 2 | both fail at composite Event gate | each smoke 1; runner 1 |

Both broad cohorts include all 22 P1–P7 packaging cases passing. There are zero pytest skips/xfails in these executed cohorts. The 37 authored disposable SQL cases pass on each runtime. All 2,541 ordinary nodes outside the selected broad cohort remain unexecuted and are independently enumerated in `ordinary-not-executed-3513.txt` and `ordinary-not-executed-3531.txt`.

Full commands, output, JUnit and my independent collection/start/phase/finish journal are under `runs/`. `reconcile.py` confirms selected/start/finish/JUnit multiset equality, exactly one setup/call/teardown per executed node and the actual nonzero exits, preserving literal `::` inside parameter IDs. Collection-only lanes correctly have zero execution. Final source comparisons retain all 426 baseline and 429 remediation input hashes with zero mismatches and zero tracked diffs.

## 3. Findings and stage ownership

**Blocking for complete product/distribution acceptance:** four genuinely identified GraphQL Events still cannot enter packaged Context storage, and installed Access smokes cannot pass. Removing the guard, stringifying native arrays, skipping cases or declaring semantic tests obsolete would not resolve this. The first responsible boundary and correction owner are I2 generalized identifying metadata/native-local persistence, followed by the later dependent stages' own checks.

**Closed by reviewed validation remediation:** native fixture literals were still being passed to the now-serialized constructor, including module-level fixtures that prevented collection, SQL references, nested Provider scopes, query/Search predicates, accessor/CLI inputs and installed smoke setup. #118 consistently uses native factories only at native boundaries and retains strict constructors for serialized rows/helper outputs. Its packaging builds explicitly select the prepared interpreter. It does not remove tests, add skips/xfails, change original evidence/clocks or alter Exchange digest rules. The ordinary-comment negative fixture now has a valid scoped key and reaches the intended non-Timeline filter guard. These are actual obsolete representation fixtures, unlike the four remaining native-array cases.

**Deferred I2/I6 limitation, not a demonstrated key-equality defect:** global/scoped identification intent is outside the triple. The present instance guard is useful for direct native calls but loses information on reconstruction. I do not infer that key equality/hash changed, that a Parent report was created, or that a complete global wire contract was implemented. The accepted handoff explicitly assigns generalized identifying metadata to I2 and global wire handling to I6. I therefore do not promote this documented, unsupported roundtrip to a new blocking I1 source finding. Conversely, this review does not accept any blanket claim that a global-shaped Document remains protected after serialization or dataclass reconstruction. It is an explicit prerequisite for generalized admission.

**Deferred SQL enforcement:** raw product SQL still admits a noncanonical top-level Issue ID `731`; strict `ResourceKey` reconstruction then refuses that row. This is independently reproduced. The unchanged product DDL lacks the generalized bounded identity predicate, open-kind support and durable global/scoped metadata. This belongs to I2 and is not closed by a clean FK/integrity check or the comparison harness.

**Nonblocking engineering observations:** the pure codec, strict native/serialized separation, single scoped namespace-TEXT encoding, genuine PR/subtype/local coordinates, exact Unicode sequences, bounded recursion and actual cursor key validation behaved as specified. No generic JSON or outer Exchange serializer change was found. No new accepted-ADR conflict or owner design question was established.

## 4. Counterexamples: expected and actual

| Counterexample | Expected boundary | Independent observation |
| --- | --- | --- |
| Native string `731`, array `["731"]`, JSON-looking string, Node and decimal namespaces | Distinct exact triples | Distinct; reconstruction equality/hash stable |
| Native PR namespace scalar/composite/empty, subtype body/title, local scalar/composite/empty | Preserve all genuine coordinates in `J([kind,J(namespace),subtype,native_local])` | 32 distinct scoped keys; one namespace-TEXT profile, no decoded-nested fallback |
| Lone surrogate, raw non-ASCII serialized TEXT, alternate escapes, forbidden nested type, exact limit plus one | Refuse rather than repair/truncate/coerce | Refused; exact byte/depth/node boundaries pass |
| Freshly checksummed Context/paired cursor with raw `731`, alternate spelling, null-containing ID or lone surrogate | Check identity after checksum | `INVALID_CURSOR`; valid canonical cursor survives |
| Digest-consistent Exchange with bad nested Collection/Coverage/root ID | Digest consistency does not establish inner validity | Domain import refuses before Context writes |
| Global Document native array shaped exactly like a scoped body key | Direct explicit global admission/refusal must not depend on missing referents or duplicate shortcut | With the real PR row present: direct initial admission refused, no Document inserted; direct duplicate replay also refused after equal scoped key exists |
| Same global key through copy/deepcopy/pickle | Preserve live instance guard | All continue to refuse scoped admission |
| Same global key through triple, `asdict` constructor or `dataclasses.replace` | Triple alone carries identity, not lost non-key contract | `_document_contract=None`; scoped decoder returns coordinates and scoped-only storage admits/replays it. Identifying columns become PR/body/local; zero semantic `resource_relations` reports are created |
| Product raw SQL Issue ID `731` | Current product is not yet the generalized SQL contract | SQL admits it, strict reconstruction refuses it: a real I2 gap |

For the global-shaped example, global and scoped factories yield the same triple and hash; no fourth key coordinate exists. The diagnostic does not prove two different real Provider entities are safely identified by that same triple. Native adapter contracts must establish completeness and namespace disjointness. I2 must preserve or explicitly validate non-key identifying metadata, reject contradictory/partial contracts, and never infer global versus scoped solely from array shape, arrival order, which equal instance a set retains, or a private Python flag. A storage-only discriminator added to PK/FK/equality is not an acceptable repair.

My separate minimal SQL comparison harness uses BINARY TEXT keys, a full three-component PK/FK, NOT NULL columns and a deterministic bounded identity predicate. It verifies meaningful empties, nesting, order, NFC/NFD, case, string/array distinctions, wrong service/kind/canonical spelling, NULL and BLOB attempts. Both actual runtimes reject the invalid references and end with clean FK/integrity results. Its receipts retain `foreign_keys=1`, `recursive_triggers=1`, encoding and other pragmas. It is explicitly **not product DDL**; it proves comparison/reference behavior under those harness constraints only. The product's existing scalar/scoped cases are separate controls.

## 5. Three reported I2 classifications

I confirm the first-failure classification of all three cases. This confirms where execution first stops; it does not establish their later semantic assertions.

| Exact Provider-intake test name | Native local Event ID at failure | Classification |
| --- | --- | --- |
| `test_non_transfer_cannot_promote_repository_fields_or_forged_flag[True]` | `["github:node_id","EV_opaque"]` | I2 storage dependency confirmed; non-Transfer promotion assertions remain blocked |
| `test_graphql_transfer_parent_namespace_and_original_type` | `["github:node_id","EV_node"]` | I2 storage dependency confirmed; later original-type/Transfer behavior remains blocked |
| `test_graphql_event_does_not_infer_destination_from_current_issue_repository` | `["github:node_id","EV"]` | I2 storage dependency confirmed; later destination-inference assertions remain blocked |

Each uses canonical Issue namespace TEXT `"7"` in slot two and a genuine native array in slot four. The first exception is at `adapters/sqlite/p1_context.py:89`, reached through `Context.resource`, before SQL insertion of that Event. The I1 GitHub producer correctly preserves the native Node namespace. The old DDL's scalar `provider_document_id` and `p1_array(...)` profile cannot represent it coherently. No I5 event-semantic, I4 native-I7 SQL, I6 Exchange or I8 Search failure is the first responsible boundary.

The fourth #118 case, `tests/integration/i5/test_independent_e2e.py::test_transfer_reports_never_mix_across_observations_or_identifier_namespaces`, reaches the same gate for native `["github:node_id","EV_node"]` under Issue `501`. Its later report-pairing/namespace assertions are unexecuted. The installed `EV_installed` failures have the same ownership.

## 6. Collection and distribution readiness

I inspected the original wider Access collection log: 2,312 collected, one P3 module-level plain-ID error, no execution. My full ordinary baseline collection independently exposes the additional P2/P3 module-level native fixture too: 5,181 selected out of 5,183 reported collected, two collection errors, no test execution, exit 2. These counts describe different scopes and are not contradictory.

The original installed baseline smoke first fails in the strict `ResourceKey` constructor on the scripted plain decimal Repository ID. Its sdist-derived wheel was built, but that script exited on the first wheel smoke before attempting the second smoke. It would be incorrect to label both original smoke variants executed or to call that first exception an I2 storage failure. #118 fixes the setup without double-encoding canonical Node IDs or replacing the Event's native local array. Its revised script attempts both variants and returns nonzero if either fails.

I independently fetched the current published-head Access job log from GitHub, not from the author workspace. Run [39599593172](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39599593172), job `119220408970`, checks out merge `4521ee0165ef5fc7587d87321842b00dc5395cc5` and reports actual SQLite 3.51.3, 2,388 passed/four failed and failed direct-wheel/sdist-wheel smokes. The acceptance ledger fails. The simultaneous Development run [39599593130](https://github.com/TakashiSasaki/git-repo-db/actions/runs/39599593130) succeeds; that success is not full product/distribution acceptance. The live job log is retained as `hosted-access118.log`.

Ordinary collection readiness is established only on the remediation tree. Passing focused P1–P7 packaging checks do not override the installed Access smoke failures. My four independently installed wheels have SHA-256 `47d1f5cc4af32eca2552ebf91bd5fa8641001eeab58dd050ba5aa86f6fc724ff`; their current publication-tree sdist has SHA-256 `3a9ea3db403ec923837cb1aced13d6cc4e16149750cbbc14f30dcf5307aebac6`, distinct from the earlier pre-documentation freeze sdist. Installed origins are outside checkout; Context DDL fingerprint is unchanged at `fa7838f86d9f0ab4b2f26c561ad0721df2d0c7dad45ee97e72ff09cbb89ac434`. The actual source IDs, origins, hashes and first errors are retained in `independent-distribution-summary.json` and each complete output log. Complete release qualification was not requested or performed; the ordinary nodes outside the chosen broad cohort remain unexecuted here.

## 7. Exact prerequisites for integration and I2 development

1. Treat the integration unit as #117 plus the reviewed fixture/script/index closure in #118, or an independently reviewed equivalent. #117 alone retains active collection and smoke-input breakage. Reconfirm current heads, ancestry and final effective merge tree; bind executable hashes and relevant tests to that actual tree. A later material production correction requires a new frozen tree and non-author re-review.
2. Preserve the deliberately partial I1 status: three original and the additional fourth Event case remain failed; complete installed Access smoke remains failed. This report supplies no merge authorization and does not turn deferred failures into passes. Do not advertise generalized Resources, global Document roundtrips, G3=A SQL enforcement or full runtime/distribution readiness from I1.
3. I2 development can use the exact reviewed I1/#118 source as its dependency baseline in disposable environments. Before generalized admission is accepted, implement bounded SQL identity validation, identifying metadata and native scalar/recursive-array local persistence, packaged DDL/composer/UDFs/indexes/fingerprints coherently. All supported connections must register required functions and enable FKs/triggers.
4. Make global/scoped identifying contracts survive the relevant in-memory and durable boundaries or fail closed when that contract is unavailable. Test shaped globals on first admission, equal-key replay, triple/asdict/dataclass reconstruction, store/reopen and Exchange. Keep equality and PK/FK as the same triple; do not add surrogate/storage discriminator keys or infer semantic Parent reports from identity.
5. Re-execute direct SQL canonical/Unicode/finite limits, NULL/omitted/partial metadata, full composite BINARY matching and conflict verbs against **product DDL**, on actual 3.51.3 and 3.53.1. Then rerun all four Event cases and both installed artifact variants on each runtime. Passing intake must unlock and actually execute the later semantic assertions, not simply remove their first exception.
6. Continue I3 sole Parent authority, I4 G3=A native-I7 typed SQL, I5 whole-unit Admission, I6 generic relations/Collections/Exchange, I7 stored validation/paired recovery and I8 query/Search as their own reviewed obligations. A namespace in Identity proves no report, referent, endpoint, original provenance or authenticity; matching I7 remains necessary but insufficient. Do not borrow acceptance from the disposable harness or historical design SQL.

## 8. Reproduction and evidence

Use `run_review.py` for sequential baseline/cohort/collection/remediation/distribution commands, `counterexamples.py` and `exchange_probes.py` for the independently authored probes, and `reconcile.py` for journal/JUnit/source comparison. All are external to the reviewed trees. `provenance.json`, `historical-hash-verification.json`, `live-checks.json`, `reconciliation.json`, individual JSON probe receipts and `runs/*/{receipt.json,output.log,junit.xml,journal.jsonl}` preserve source/runtime/outcome bindings. No source fix or test edit was made during this review.

Finalization: all review lanes completed on 2026-10-21 UTC. No source changes or silent fixes were made. The evidence is scoped local agent execution plus independently fetched hosted logs, not a full release attestation.
