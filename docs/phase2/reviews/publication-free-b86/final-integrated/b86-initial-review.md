# Independent final integrated verifier: b86 checkpoint (NOT accepted)

Reviewer task `/root/final_integrated_verifier` is fresh and did not author any production source changes. Model and effort: not exposed. User-authorized scope 4 from `docs/phase2/publication-free-implementation-prompt.md`. No release, main merge, retained catalog mutation or authenticated collection was performed. All catalog/HTTP/Git work is synthetic disposable state.

Binding: commit `b86ff2c96d7558379b2230489e1494630b073ef7`, tree `085be492d5fbd8cfbcaa7eb4be3d1db27af84fee`, Schema 20, composed DDL SHA256 `f1ec742a1d9778dab4ed7950bef0f257d0d368ee8c3d89f945cba61ed23ebd04`, Python 3.12.14, SQLite 3.53.1. Actual import asserted `/workspace/reviews/publication-free-final-verifier/src/repo_catalog/__init__.py` through shared `/workspace/git-repo-db/.venv`. `binding.json` and `schema-map-recomputed.json` record actual values. Recomputed schema map exactly equals the checked-in map; 84 tables, 17 views, 367 triggers, 54 indexes. Fresh view/FK/integrity/generated JSON checks ran through map recomputation; they do not establish populated runtime correctness.

Full baseline #25-to-b86 binary diff and changed-path/hunk inventories are preserved in `integrated.patch`, `integrated-name-status.txt`, `source-hunk-inventory.txt`. Governing AGENTS files, owner implementation prompt/design/ADR/decision register/implementation handoff were read. Detailed current-value, collection proof, typed Exchange, Git canonical availability/decoding, query/index, transaction and CAS/maintenance interactions were inspected. This scope does not pretend that the full ordinary suite, every HTTP branch, every historical test assertion or every changed source line was independently executed or exhaustively reviewed; corrected independent scopes 1–3 and actual full test receipts remain separate gates.

## Executed independent probes

The frozen copy `test_final_integrated.b86-frozen.py` is the source of the final b86 14-node run. `b86-own-counterexamples.txt/xml` records 11 passing nodes and 3 mandatory failing nodes, no skips. Earlier harness exploration receipts are retained separately and are not correctness findings or final acceptance. The harness adjustments corrected unsupported initialization profile, a fixture's unknown provider clock, per-field equal-clock comparison, exact-length corruption, shared bodies in different PRs, and a required positive Source association.

Passing probes cover incomplete larger scopes with valid independent current resource/Exchange, negative/zero/sparse/null clocks and stale live fences, Source partial scans preserving positive pairs, both SHA-1/SHA-256 canonical intrinsic atomic installation and missing targets, both SHA-1/SHA-256 decoder ambiguity with false decoder arriving before canonical subject and then valid sibling, Coverage complete100/partial200/stale175/complete300/equal-time unknown/conflict/recovery, COMMIT failure rolling back current value/evidence/text/revision, shared digest quarantine/real canonical repair/CAS-41 backup copied count/restore/no overwrite, and detached Issue transfer with reverse/repeated/onward import. The normal HTTP acquisition -> current drift -> proof -> reverse Exchange -> receiver index/query -> operational loss flow passes until original replay after alias receipt loss (FIV-3).

## Mandatory findings

### FIV-1: local false Git decoding becomes ordinary query data

Production DDL accepts a new `git_text_facts` row under a genuine canonical blob, real content identity and supported decoder settings/key, with a false `raw_text`. No trigger is dropped. `validate_git_fact` rejects it as contradicting canonical bytes, but `decoded_fact(..., decoder_key=...)` returns it. A real normal Git acquisition followed by this insertion passes `check_catalog(full=True)` with `[]` and `QueryService('search code', explicit supported key)` returns the fabricated snippet. This also creates a false default decoder conflict against the valid interpretation.

Reproduce: `PYTHONPATH=/workspace/reviews/publication-free-final-verifier/src:/workspace/reviews/publication-free-final-verifier:/workspace/review-artifacts/final-integrated /workspace/git-repo-db/.venv/bin/python /workspace/review-artifacts/final-integrated/decoder_sql_repro.py`. Actual evidence: `b86-decoder-sql-query.json`, `b86-decoder-sql.txt/xml`, full independent test node `test_sql_decoder_value_must_not_become_ordinary_fact_without_byte_validation`. This requires canonical validation across the local admission/catalog/ordinary reader boundary; Exchange-only checking is insufficient. No profile ranking/certificate is requested.

### FIV-2: late exact captured ref cannot promote genuine root origin

Export a normal real Git capture, omit only `ref_observations`, deliver the remainder, then deliver the exact omitted ref. `root_origins` hits the exact ref trigger while the genuine dependency is absent and is staged `invalid:domain_constraint`. Late arrival promotes snapshot and Git Coverage; `current_snapshots=1`, `root_origins=0`, and the origin remains staged forever, even after full original-unit replay. Missing trigger-only dependency was incorrectly classified invalid.

Reproduce with the same environment above and `late_ref_repro.py`. Actual evidence `b86-late-ref.json` preserves early/late/replay records and outcomes. Full test node `test_ref_capture_type_and_peeled_tuple_cannot_gain_current_scope_from_real_object_bytes` separately confirms incorrect type and peeled tuple cannot make a current scope, and fails on the genuine late-ref promotion. Fix must distinguish genuine absent dependency from wrong existing ref tuple; blanket invalid-row retry is not justified.

### FIV-3: discarded Exchange alias receipts prevent safe original replay

After successful normal GitHub sync and reverse Exchange, delete `exchange_admissions`, `exchange_local_identities` and operational job/cursor tables. Current facts, index, query and full validation remain usable. Reopen/onward export regenerates integer aliases, then replaying the original unit stages 20 rows (10 real `acquisition_roots` as invalid natural-key duplicates; 10 `root_origins` missing the deleted aliases). `Graph._existing` tests generated integer keys instead of the available natural UNIQUE identities. Current docs classify both mappings/admissions as discardable operations, and safe repetition after receipt loss is required. This finding concerns replay/promotion rather than a claim that ordinary facts were initially hidden.

Reproduce full independent node `test_normal_acquisition_current_drift_reverse_transfer_index_reopen_and_receipt_loss`. Actual staged records are preserved in `b86-replay-after-receipt-loss.json`. Natural resource deduplication/mapping reconstruction, or an explicit correct retained-identity responsibility consistent with owner constraints, must be resolved; no generic Publication owner may be introduced.

## Other blockers and pending gates

Scope 1 reported a separate mandatory A1 direct current-candidate staging shape/owner hole. Its correction and fresh review are pending.

The actual b86 package run is complete: 2 selected/executed nodes, 2 failures, no skips, exit 1. Both installed wheel/sdist receiver searches return valid data with partial status due `inventory_incomplete` for imported Source registrations; the package command expects success. This is an unresolved failed gate, not a passed test. Ordinary plan selects 2003 ordinary nodes plus 2 package nodes. Checked-in baseline mapping still records 2002 current ordinary nodes, so the additional digest regression requires exact input reconciliation. Complete ordinary and hosted CI records, the final corrected commit/tree, all corrected independent review receipts and final re-execution are still pending.

Acceptance: NOT accepted. No final integrated signoff can be made while mandatory findings or required complete records are unresolved. Source changes require re-verification on the new frozen exact tree.
