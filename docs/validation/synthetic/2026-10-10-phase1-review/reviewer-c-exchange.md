# Reviewer C — Corrected PR #20 Exchange review

## Review identity and scope

This is an independent review of the corrected PR #20 Exchange implementation. I authored no production correction. The independent baseline finding report and exact initial PR #20 source snapshot are preserved in `reviewer-c-original-exchange-findings.md` and `reviewer-c-exchange-f9bff8.py`; the fixes were reviewed read-only in the current implementation. The only tracked change I made is the new deterministic regression file `tests/integration/test_phase1_exchange_scaling.py`.

At review time:

- PR #20 base/integration HEAD: `2b5123e0aee1d5cdf65fd14be0ded3d8e4c31bd9`.
- HEAD tree: `bf6f5e1b037cf18b798086b9ef56abd68e211380`.
- Effective worktree tree snapshot (including current uncommitted integration changes and my new test): `cc38a6f42c7d9c65c692e38203568644aedfa0f4`.
- `src/repo_catalog/adapters/sqlite/exchange.py` SHA-256: `d142d7689272ba869fdb56c33539750efc665bc831c5623ced58a6ee7ddaa103`.
- New `tests/integration/test_phase1_exchange_scaling.py` SHA-256: `534b6b3a0467279314271d073df86140f655d51279101f3d3e302b9f407e38ee`.
- Main Exchange regression file SHA-256: `d02b5ea123a32ef092667f68375d5565351ddb2e11094af318c34bd74abc33a7`.

Environment: Linux 6.18.44 x86_64 / glibc 2.41, Python 3.12.14, SQLite 3.53.1. The scoped run used no `REPO_CATALOG_TEST_BOOTSTRAP` override and no live provider tests.

## Findings and corrections

### High — invalid domain candidates authorized rejected API originals (corrected)

**Affected path:** `Graph.original_root` → `required_original_keys` → `receive` / `_admit` / `_promote`.

I independently reproduced three baseline attacks at initial PR #20 head `f9bff8b2dc17ddffd6b3f7662791022f25175c44`:

1. A `parsed_result_publications.fact_manifest_json` named a nonexistent observation. The publication was later rejected by normal admission, but its input fetch and `stored_bytes` were admitted.
2. A `complete` marker used a terminal-shaped evidence object without a valid terminal proof (including fetch/proof time mismatch). The marker was staged as incomplete, but its input body was retained.
3. A `document_observations` candidate used SQL-invalid `deleted=2`; the observation failed its catalog constraint while its fetch and raw API body were admitted.

The baseline root predicate trusted a `DOMAIN_FACTS` table name and shallow publication/marker shape before successful semantic and SQL admission. This violated R4/R6: rejected input could persist as raw bytes or delayed retry material.

**Correction reviewed:** domain roots now require exact persisted-row verification or deferred-constraint validation; publication roots must be persisted and JSON-complete; completion roots must pass the ordinary `proof_requirements` contract. `_preflight_original_roots` tests the combined available incoming/staged dependency graph through ordinary admission in a savepoint, so valid out-of-order rows can remain pending without letting a rejected candidate retain its bytes. Advisory `requires` and generic JSON references do not grant authorization. Promotion rechecks root authorization before admitting or retaining a staged original envelope.

**Regressions passing:** `test_publication_for_missing_fact_cannot_retain_its_input`, `test_incomplete_terminal_proof_cannot_retain_input_body`, `test_domain_fact_rejected_by_catalog_constraint_cannot_retain_input`, `test_advisory_requires_cannot_attach_unrelated_original_to_valid_proof`, `test_partial_reason_marker_cannot_authorize_originals`, `test_malformed_publication_manifest_cannot_authorize_originals`, and `test_generic_request_payload_reference_cannot_authorize_unrelated_original` (both direct and staged variants).

### Medium — repository export and intake scanned unrelated history (corrected)

**Affected paths:** `local_original_context`, `original_intake_context`, and repeated `_promote` preflight.

The initial implementation materialized every `git_object_payloads` mapping while exporting one repository, then parsed every `exchange_admissions.record_json` during intake. Promotion could repeat context construction. This was O(unrelated Git objects + unrelated receipts) in time and Python memory for a single-repository operation.

**Correction reviewed:** Git byte roots are selected through `repository_object_sources` and `git_acquisitions` for the requested repository (or by the specific digest for corruption diagnosis). The review confirmed every `DOMAIN_FACTS` table and `fetch_collections` has `repository_uuidv4`, so this path can scope its candidate roots. Admitted proof ancestry is loaded by indexed exact `exchange_admissions.record_key=?` lookup only when reached through a required dependency; it no longer parses global receipt JSON. Promotion reads the pending staging snapshot once and groups it by repository before preflight. The lead’s follow-up batching fix removed the per-repository unindexed staging-table query; `test_promotion_groups_staged_candidates_before_preflight_scans` exercises 24 repository groups and asserts there is no per-repository staging scan.

**New deterministic regressions added:**

- `test_export_vm_work_is_scoped_away_from_thousands_of_unrelated_git_objects` inserts 4,096 valid SHA-1 Git blob bodies, correct OIDs, raw payload registrations, and repository/acquisition ownership across two unrelated repositories. With foreign keys and recursive triggers enabled, selected-repository export stays one record and SQLite VM estimate remains exactly 8,000 before and after the unrelated population (delta 0). The assertion allows a 2,000-opcode margin and has no wall-time deadline.
- `test_intake_context_does_not_materialize_unrelated_admission_receipts` inserts 12,000 unrelated receipt-shaped JSON rows, each containing 1 KiB of padding. The selected repository’s intake context is empty and SQL trace confirms no `exchange_admissions` scan lacking a `record_key` predicate.

The same-environment standalone benchmark harness and raw outputs are preserved at `exchange-performance-harness.py`, `exchange-performance-initial-pr20.jsonl`, and `exchange-performance-corrected.jsonl`. Harness SHA-256: `1c05d3c6ca820e51fbfd4c07a8d528b0e8d47cad70af9d301ed1463a175fca80`. Output hashes: initial `9ceb40bf039cae21a76da25cfbd778a60d0a10ecf95bef6add4adf07b8130fcf`; corrected `9b0956623a094581f413baf2a6cb5c21608a207458255c186259838eda111108`.

| Operation | Initial PR #20 | Corrected | Output / interpretation |
|---|---:|---:|---|
| Export with 1,000 unrelated Git objects | 10,224 SQL trace statements; 0.654 s; 9.076 MiB Python peak | 224; 0.0188 s; 0.605 MiB | 1 output record both runs |
| Export with 5,000 unrelated Git objects | 50,224; 3.3088 s; 44.854 MiB | 224; 0.0095 s; 0.221 MiB | 1 output record both runs |
| Intake context with 50,000 unrelated synthetic receipt JSON rows | 21 SQL trace statements; 0.3577 s; 24.167 MiB; 50,000 context records | 20; 0.0006 s; 0.016 MiB; 0 context records | Trace count alone does not show rows consumed; parsed-context count and allocation peak expose the old scan. |

Each table row is an independent run, not a quantity to sum. SQL trace counts and Python allocation peaks are measurements, not acceptance deadlines; timing is a single-run observation. The new VM-step regression separately guards the export complexity without wall-clock dependence.

### Savepoint / preflight side-effect check

The preflight savepoint temporarily supplies a placeholder physical row and synthetic receipt only when missing API bytes are needed to validate an otherwise available domain proof. It restores `ignore_check_constraints` in a `finally` block and rolls the entire savepoint back in its outer `finally`. I checked a valid full-unit preflight by comparing `iterdump()` before/after; the dumps matched, `PRAGMA defer_foreign_keys` and `PRAGMA ignore_check_constraints` were both 0 afterward, `foreign_key_check` was empty, and `integrity_check` returned `ok`. The three malformed-root receive-path regressions above verify no rejected body remains after preflight. The current code’s staging and admission transactions remain independent from the rolled-back probe.

## Mandatory adversarial cases 1–12

| Case | Reproducer / evidence | Corrected result |
|---|---|---|
| 1. Export standalone API originals without domain facts | `test_original_only_units_do_not_enter_storage_or_json_envelopes` builds `stored_bytes`, `payloads`, and fetch rows for `decoded_api`, `legacy_normalized`, and forged `git-object-raw-v1`; `test_original_encoder_and_explicit_fetch_selector_have_no_side_effects` exercises encoder and explicit fetch selector. | Original-only rows are rejected; no raw body, Base64 envelope, staging receipt, or identity is retained. Legitimate full/collection exports omit unreferenced originals (`test_full_and_collection_export_omit_unreferenced_originals`). |
| 2. Import bare `stored_bytes`, `payloads`, or `fetch_occurrences` | Bare rows are imported directly and via pending promotion in the original-only/direct-admission tests. | Rejected as a standalone archive path; no durable bytes or fetch observations. |
| 3. Smuggle API bodies into `exchange_staging`, then promote | Direct SQL staging, multiple failure reasons, malformed/corrupt proof, and later promotion are exercised by `test_direct_admission_and_pending_promotion_do_not_restore_original_intake`, `test_failed_api_original_envelopes_are_not_retry_staging`, and `test_corrupt_api_proof_intake_never_retains_rejected_original_envelope`. | Invalid API envelopes are deleted from retry staging. A valid retained Git body can keep its distinct Git repair/staging use. |
| 4. Use advisory `requires` to authorize unrelated payloads | `test_advisory_requires_cannot_attach_unrelated_original_to_valid_proof`; generic authored JSON references are tested direct and staged. | Advisory/envelope metadata cannot expand the verified proof closure. |
| 5. Forge Git format, type, size, OID, or representation | `test_forged_git_object_cannot_authorize_original_retention`; `test_verified_rejected_git_bytes_require_true_object_identity` exercises SHA-1 and SHA-256, bad format/OID/type/length via Python and SQL; `test_rejected_original_cannot_enter_git_staging_through_python_or_sql`; `test_forged_canonical_git_oid_cannot_authorize_api_original_repair`. | Rejected API labels cannot authorize Git staging or repair. Only exact Git object identity and byte digest pass. |
| 6. Deliver Git bytes before their object descriptor | `test_valid_git_dependencies_can_arrive_in_separate_units` sends a payload/map, then the matching bytes, then the object descriptor. | Legitimate Git dependency pieces can arrive separately; no forged descriptor is needed to authorize API retention. |
| 7. Missing parents and valid out-of-order domain dependencies | `test_missing_dependencies_survive_reopen_and_promote_without_new_ids` stages domain rows before parents, closes/reopens the catalog, then sends the full unit; `test_delayed_required_bytes_satisfy_retained_domain_staging` separates valid proof and required bytes. | Valid dependencies remain durable and promote after arrival, preserving portable IDs. Rejected inputs do not become observations. |
| 8. Same-key competing immutable variants | `test_same_uuid_different_fact_is_staged_original_preserved` and `test_competing_unadmitted_variants_are_both_held`. | Existing admitted fact wins without replacement; unadmitted competing variants are both held, with no arrival-order winner. |
| 9. Wrong Source/Repository ownership or cross-repository leakage | `test_source_wide_local_policy_and_second_repository_are_not_exported`, `test_known_source_wide_parent_cannot_authorize_pending_api_bytes`; manually changed a valid repository-B unit’s top-level repository to A. Also directly staged B-owned records under A’s repository owner. | Source-wide/other-repository data are excluded; the mismatched unit raises `CatalogError INVALID_EXCHANGE` and leaves target unchanged. Owner-mismatched staging admits no B API body, fetch occurrence, or domain observation. Ownerless prerequisites may be admitted. |
| 10. Valid domain records whose transport dependencies are delayed | `test_delayed_required_bytes_satisfy_retained_domain_staging`, plus separate Git-object dependency arrival test above. | Required valid dependencies can be staged and admitted later; successful historical facts/proofs are not deleted. |
| 11. Corrupt incumbent bytes and shared Git consumers | `test_existing_corrupt_bytes_get_diagnosed_without_automatic_repair`, `test_corrupt_api_proof_intake_never_retains_rejected_original_envelope`, `test_shared_git_consumer_preserves_rejected_domain_content_staging` for SHA-1/SHA-256, and CAS repair/quarantine/backup/restore cases in `test_catalog3_cas_integrity.py`. | Incumbent corruption is diagnosed, never silently replaced. A genuine shared Git consumer preserves Git content staging/repair eligibility; rejected API input alone does not. Quarantine and repair are explicit and atomic. |
| 12. Repeated/reverse-order imports, forwarding, and restart | `test_complete_round_trip_remaps_local_ids_and_preserves_portable_ids` imports the same unit twice, exports onward, and compares record keys; `test_missing_dependencies_survive_reopen_and_promote_without_new_ids` reopens a staged catalog; `test_scope_mapping_forwarding_and_independent_dag_heads` forwards exchange data both directions. | Identical re-import is idempotent; local IDs remap while portable identities remain stable; missing records promote after reopen; forwarded repository scope is preserved. |

## Retained proof boundary and remaining findings

Phase 1 removes standalone saved-original archive/replay authority. It does not claim that all historical API body references are gone. A successfully admitted historical domain fact, publication, terminal/304 marker, or other retained proof may still require its exact input closure for publication/restart. The corrected Exchange derives those dependencies from verified facts and proof contracts, while the next architecture ADR must decide the replacement contracts before those shared dependencies can be removed.

I found no remaining high- or medium-severity defect in the reviewed Exchange areas after the corrections above. Specifically, I found no unrelated Git payload scan in repository export, no all-receipt JSON materialization, no per-repository staging scan during batched promotion, no demonstrated API-body staging bypass, and no preflight savepoint residue. This is the scoped Exchange review, not a claim that this report alone is full repository acceptance.

## Focused verification

Exact no-bootstrap command:

```sh
env -u REPO_CATALOG_TEST_BOOTSTRAP uv run --locked --group dev python -m pytest -q \
  tests/integration/test_phase1_exchange_scaling.py \
  tests/integration/test_phase1_exchange_retirement.py \
  tests/integration/test_catalog3_exchange.py \
  tests/integration/test_catalog3_cas_integrity.py
```

Result: **108 passed in 31.63 s; 0 failed, 0 skipped.** The two new scaling regressions alone passed: **2 passed in 0.44 s**. Ruff lint and formatting checks on the new file passed. The selected command includes the retirement/adversarial Exchange, full and selective graph exchange, CAS/quarantine/repair, and backup/restore cases; it does not include live-provider tests. No tests in the selected command were skipped or excluded by markers.

The lead independently regenerated the parser verification certificate from a successful 1,718-test run; that certificate is separate evidence and is not counted in my 108-test focused result.
