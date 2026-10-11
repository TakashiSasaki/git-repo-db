# Independent integrated verifier — immutable fafc checkpoint

**The preserved scope-4 repair counterexamples pass on fafc on both SQLite versions. The whole candidate is NOT ACCEPTED.** The complete hosted ordinary result has 126 failures, local ordinary execution is still incomplete, and the complete local package gate fails its receiver partial exit-code expectation. This receipt confirms the stated repair families and actual artifact binding; it is not final integrated sign-off and must not be reused as acceptance of subsequent source changes.

Reviewer `/root/final_integrated_verifier` authored no production or repository test changes. Model and reasoning effort: **not exposed**. No extra subagents were used. Initial b86 and narrow isolated-repair receipts remain preserved outside the root repository.

## Exact source and execution binding

- Feature SHA `fafc1b2d4d2e1986768143cc71a0e55cba943ba3`; Git tree `6f566cb3e91e25facda60671c40108e0a9f8965b`.
- Detached worktree `/workspace/reviews/publication-free-final-verifier-fafc1b2`; actual asserted module `/workspace/reviews/publication-free-final-verifier-fafc1b2/src/repo_catalog/__init__.py`; Git status remains clean.
- Schema 20 actual packaged DDL SHA-256 `bf6deb09471a361918ab9d9e97ca1ba204060ffc78420972775a914357912f26`.
- Primary Python 3.12.14 / linked SQLite 3.53.1: `/workspace/git-repo-db/.venv/bin/python`.
- Native Python 3.13.5 / official SQLite 3.45.1: `/workspace/review-artifacts/schema-a1-b86/native345-venv/bin/python`, with the explicitly recorded native library. This is a separate interpreter, not a claimed change to the statically linked shared venv.
- The FTS5-enabled native library is `/workspace/review-artifacts/final-integrated/sqlite345-fts5/lib/libsqlite3.so.0`, SHA-256 `4f15080736efef7cc00d9080b837a08c5d0362d8cb1acdf8aded4c50098a8f0c`; actual source ID is `2024-01-30 16:01:20 e876e51a0ed5c5b3126f52e532044363a014bc594cfefa87ffb5b82257cc467a`. `binding-345-fts5.json` records actual compile options and a successful native trigram CREATE/INSERT/MATCH. The independent build receipt preserves the exact command and official archive/source hashes.

All catalogs and providers were synthetic/disposable, including local HTTP fixtures with dummy tokens. No retained catalog, authenticated collection, root source/history mutation, PR merge, release or deployment occurred.

## Actual independent executions

`independent-complete-executions.json` binds all actual XML case names/counts/statuses and hashes. Own assertions import production modules and setup helpers, not implementer test assertions.

| Execution | Actual cases | Outcome |
| --- | ---: | --- |
| Original coherent own suite, SQLite 3.53.1 | 23 | 23 passed, no error/skip |
| Strengthened native candidate subset, SQLite 3.53.1 | 4 | 4 passed, no error/skip; these are four repeated logical nodes, not new coverage credit |
| Strongest own suite, SQLite 3.45.1 with FTS5 | 23 | 23 passed, no error/skip |
| Strict decoder preservation script, SQLite 3.53.1 | 4 scenarios | All passed |
| Strict decoder preservation script, SQLite 3.45.1 | 4 scenarios | All passed |
| Existing complete timestamp file, SQLite 3.45.1 | 115 | 115 passed, no error/skip; not independently authored nodes |
| Actual composed schema / all-view preparation, each runtime | Structural audit | Exact map, generated SQL equality, FK and integrity checks passed |

The own pytest set is 14 integrated cases, four native decoder-family cases, and five follow-up cases: **23 distinct logical nodes per runtime**, without adding repeats or standalone scenarios to that node count. The final follow-up strengthens the four direct native candidates to use a valid `current-state:` plus 64-hex key. The two original A1 payload defects still fail on original b86 with valid keys, while all four strengthened final cases reject correctly. `probe-input-reconciliation.json` and `probe-strengthening-reconciliation.json` disclose import-assertion rebinding and that strengthening; no product assertion was weakened.

An earlier native 3.45.1 run is retained: 22 passed, one failed solely at index rebuild with `INDEX_UNAVAILABLE`. That official native library was built without FTS5. The same assertions passed after rebuilding the identical official source with `-DSQLITE_ENABLE_FTS5`. This is disclosed harness capability correction, not a source defect or a hidden skip. Shared-host timings are execution logs, not comparative benchmarks.

## Independently verified repair families and interactions

FIV-1: ordinary native text, commit-message, commit-metadata and tree-name values cannot contradict the actual canonical byte subject and explicit supported decoder settings. Normal Git acquisition, both formats, invalid-first Exchange, legitimate UTF-8/Latin-1 ambiguity, explicit keys, actual queries/index and full check were exercised. The diagnostic follow-up preserves `PARSER_DECODE`, canonical raw/intrinsic rows and local revision, rejects a strict interpretation, and permits later genuine replacement decoding.

FIV-2: genuinely absent exact captured refs remain pending through reversed transfer, reopen and receiver-to-receiver forwarding, then promote on the actual late ref. Present wrong type/target/peeled tuples stay invalid; incomplete/complete closure is not manufactured as two alternatives during forwarding.

FIV-3: normal GitHub acquisition/current drift, direct typed proofs, reversed Exchange, ordinary query/index, reopen, deletion of operational receipts/aliases/progress/jobs, onward export and original replay preserve admitted current facts, natural Git root/origin identity and actual typed proof closure. Discardable receipt state does not become an owner of facts.

Scope-1 A1 residual: minimal and foreign-capture-parent current candidates are rejected natively before missing-parent staging, using valid operational keys. Additional escaped modeled-key opaque nested extensions also reject. Valid independent resources remain usable under incomplete larger scope. Sparse/null/zero/negative clocks, live fences, receiver checks, Source partial-inventory positive pairs, detached Issue transfer capture, stale/current/conflicting Coverage, per-object atomicity and COMMIT rollback are independently exercised.

Shared CAS cases exercise shared-byte quarantine, actual canonical Git repair authorization, domain text preservation, backup/restore and CAS-41/no-overwrite behavior. These are populated cross-module cases, not fresh-DDL-only evidence.

The actual DDL map matches on both runtimes: 84 tables, 617 columns including three generated columns, 190 FK column rows (141 constraints in the matching inventory), 20 views, 556 triggers and 55 indexes. Structural equality does not certify every guard/caller.

## Complete gate audit and open integrated acceptance

The independent raw-collection audit matches SHA `88ce59a32b14839d01f2d7d9363583621d6ced3bb3e1ac8282877fc197d84852`: all 1,950 baseline ordinary nodes are accounted for by 487 explicit mappings plus 1,463 same-ID survivors; 193 removed/renamed functions have collected replacement nodes; 2,128 current ordinary plus two package nodes are selected, with no excluded or unexecuted files in the full plan. Same IDs and collection accounting do not prove behavioral sufficiency.

Actual hosted run `38056834301`, attempt 1, feature fafc, base `0bd5704caca2f6e3723bef22531b065cd4d7bad0`, tested checkout `d889c5335f89574ba9ab1132b0f1fb011f55a68c` has **the identical Git tree** listed above. Python 3.12.15 / SQLite 3.45.1. XML and profile agree on all **2,128 nodes: 2,002 passed, 126 failed, zero errors/skips**, exit 1. The two package nodes were not executed; no matching passed full validation manifest exists. The independent audit recomputes actual Git-map/policy/broad-acceptance hashes, selected IDs, profile/XML statuses and command run/runtime binding. It does not infer success from partial progress or a CI badge.

Local fafc package is complete and failed: two actual installed variants reject the newly written expected exit 2 for global receiver search. Actual installed CLI rechecks show partial exit **3**, only inventory gaps, exactly the same four hits as complete repository-scoped search, and full check exit 0. The isolated one-line expectation repair `0357cc2` has a complete two-passed XML receipt; it is separately source-bound and does not repair or accept the 126 ordinary failures. Its sender backup/restore assertion passed unchanged: the backup uses the original full sender. `package-gate-failure.md` preserves the corrected diagnosis and initial reviewer inference error.

The hosted whole-suite failures include remaining real reader/history/scope behavior and obsolete fixtures; root-cause classification and corrections are ongoing. They are mandatory integrated blockers even though the own repair counterexamples pass. All 43 failing function groups/126 nodes remain in the raw hosted artifact; a bounded function summary and independent whole-artifact audit are preserved here. The incomplete local ordinary run is not assigned a fabricated complete result.

Scopes 1, 2 and 3 final-fafc receipts are read as scoped evidence, not substitutes for complete gates. Scope 2 actual XML reports 50 plus 16 passed cases; Scope 1 reports distinct reviewer programs plus 138/27 selected existing cases and 63 native pending cases; Scope 3 reports 66 independently authored nodes and sequential deterministic VM/authorization work. Their exact source/DDL bindings and limitations remain explicit. Further affected source corrections require fresh affected reviews and reruns on the next coherent frozen candidate.

## Reproduction, preservation and limits

Actual executed commands are reconstructible from the bound paths: use `PYTHONPATH=worktree/src:worktree:probe-directory`, shared venv on PATH, and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Run the three own files in `final-fafc1b2/` with the shared interpreter; run `final-fafc1b2-valid-keys/test_final_followups.py -k 'native_pending_current or decoded_current_candidate'` for the stronger shared-runtime subset; run all three stronger files with the native interpreter and explicit FTS5 `LD_PRELOAD`. The original native non-FTS command substitutes the preserved original library. Scripts `strict_decoder_diagnostic_recheck.py worktree`, `inspect_final_schema.py worktree`, `audit_collection_binding.py` and `audit_completed_results.py` are independent external artifacts with their required arguments retained in logs/reports.

`path-review-manifest.json` enumerates all **253** #25-to-fafc changed paths and **78** b86 correction paths with actual review depth. The complete integrated and correction diffs are retained. This review does not claim every historical/generated line, every authored assertion or every native guard/caller was manually or dynamically covered. Exhaustive collector/restart/state machines, all scale dimensions, full retained-data growth, actual I/O fault injection and every CLI historical/scope interaction are outside the executed scope. Original governing documents were fully read, including accepted Q01B/Q02B/Q03B/NO_INDEPENDENT_PUBLICATION. No new trust, GC/deletion, cache, decoder ranking or generic Publication policy was selected.

Later receipt/document commits must be reconciled against the exact tested source/test inputs. They change Git trees and may change broad acceptance hashes even when production code is identical. No identical-tree or complete-gate reuse claim is authorized by this receipt. All final ordinary/package/hosted results, independent scopes and the actually submitted final checkout must be audited before final acceptance.
