# ADR 0036 Notes consumer transition contract

This contract scopes the opt-in transition after the merged typed-salvage
implementation. [ADR 0036](../adr/0036-ref-observations-and-shared-notes-mappings.md)
and [ADR 0026](../adr/0026-stop-salvage-restore-merge-after-corruption.md)
remain authoritative. The fixed baseline for this transition is main
`3d3776c61e48cbd1e2009d9a167e101c664af02d` (tree
`1b28a48b51a2da35beec20444458791b42d5f2a6`). This is an engineering contract,
not a new owner decision, public Schema 21 change, migration or release.

## Ordered review boundaries

| Boundary | Consumer at the transition baseline and required replacement | Scope of first candidate (#219) |
| --- | --- | --- |
| Whole Notes inventory | [`NotesAcquisition.inventory_ref`](../../src/repo_catalog/application/notes.py) currently records an attributed `NotesMappingGroup` without receiver-verified Coverage. An explicitly invoked receiver verification exhausts the exact Claim/root grammar and rechecks the ordered structures through `RefNotesInventoryCoverageProof`. Preserve reported groups independently and never promote a partial Group or imported status into proof. | Implement and test explicit verification for complete/empty, failed/partial, replay and budget behavior. Automatic paired-plan orchestration follows when the input carriers and coordinated admission are migrated. |
| Inventory Query | [`list_notes_inventories`](../../src/repo_catalog/application/production_query.py) consumes legacy Capture Groups. A Claim-aware listing must expose original Groups and only the current, locally revalidated proof for the exact Claim. Latest/stale/conflict Coverage remains visible; a historical Group is not silently rewritten as unverified. | Add the new typed listing, with finite metadata/proof reads. The legacy listing still serves actual old-format facts during the transition. |
| Note-body source port | [`NotesSource.note_body`](../../src/repo_catalog/domain/ports/notes.py) names only `NotesProof`, although the Git adapter already consumes `NotesMappingEvidence`. | Describe both actually supported evidence types; neither grants the annotated target's body. |
| Acquisition input and orchestration | [`_run_notes_spec`](../../src/repo_catalog/application/acquisition.py) currently invokes both ref-aware and legacy Capture operations; `explicit_captures`, `external_claims`, and `external_groups` are real old-format semantic inputs. | Preserve old inputs and output while this first candidate establishes the new inventory path. A subsequent candidate introduces explicit new-model input carriers, migrates producers and stops duplicate legacy production once dependent consumers are ready. Do not synthesize a new observation from a Capture. |
| Generic Query and paired resource | [`get_git_object` and paired resource projection](../../src/repo_catalog/application/production_query.py) derive `notes_targets` from Capture-scoped projection. | Subsequent candidate: retain each explicit Claim and its alternatives, its root-bound receiver evidence and physical-copy validation; do not choose a latest UUID, root or report as winner. |
| Search | [`extract_notes_documents`](../../src/repo_catalog/adapters/sqlite/production_search.py) consumes Capture, legacy mapping reports, Groups, roles and retained Notes. | Subsequent candidate: index and revalidate actual Claim-specific mappings and eligible bodies, preserving discoverability without borrowing another Claim's authority. Retain unindexed/partial scope honestly. |
| Legacy physical cut | Legacy DDL, Exchange families, recovery, and cross-family collision guards still have consumers and protected evidence. Shared grammar validators are also used by the new path. | A later coordinated schema/wire/Core/recovery cut follows reviewed consumer migration. No old family, cross-family guard, backup or salvage path is removed here. |

The candidates are sequential and may be stacked; each must identify its
parent, its actual implemented scope and independent-review status. Old-format
data are not silently converted or treated as evidence for a new Claim.

## Automatic verification candidate

The next candidate is stacked on the independently reviewed inventory boundary
at `bb4119e3e9051b5f3a634810434198ee002cfabd`. When a Notes request discovers
ref Claims and requests inventories, P5 also invokes the existing receiver
verification for each reported whole Group. Its result is exposed separately
from the original report in `GitAcquisitionReport`, alongside a freshly checked
Claim-specific projection of Coverage. All projections contributing to one
aggregate report share a single Core snapshot; they do not assert that later
concurrent writes are absent. A replayed historical proof remains evidence of
its original check; a later partial/unknown or conflicting
Coverage cannot make the current request report complete. A partial report, a
failed read, a rootless Claim or a conflicting alternative cannot acquire a
fabricated proof. Replays retain the existing request-bound verification pin.
This adds a real structural reread and proof-admission work to inventory
requests; the same finite cumulative request budget applies, including on retry.
An unsuccessful verification has no fabricated current projection in the report.

Ordinary Core acquisition runs verification after the Group is admitted. A
paired acquisition prepares its typed facts before the coordinator transaction,
commits Core and Context, then runs the independent verification using the same
work and progress handles. No proof pin is written before the Core commit. If a
coordinator cut interrupts either commit, the verification has not run and a
retry uses the retained facts and progress. An exception during post-commit
verification propagates unchanged; the committed paired outcome is noted when
the exception permits it. It does not roll back either store. Independently
verified prefixes already admitted remain durable and are revalidated on retry.
A caller-owned external Core
transaction has no post-commit hook, so this candidate explicitly reports
verification as deferred instead of pinning uncommitted evidence. Verification
can be invoked after that transaction commits. The direct verification API also
rejects an externally owned Core transaction before it can save a proof pin.
An already orphaned pin refuses its old continuation; it is not silently
rebound. A distinct explicit request can perform a fresh check if its source is
available, without resetting the old request's work.

This is an orchestration change, not a new authority or source of receiver
proofs. It leaves explicit/external legacy inputs, generic Query, paired resource
projection, Search, and the eventual schema/wire/Core/recovery cut for later
candidates. No legacy producer is disabled while those consumers still need it.
The associated behavior checks are
[`test_ref_inventory_wiring.py`](../../tests/integration/p5/test_ref_inventory_wiring.py):
`test_inventory_wiring_keeps_original_claims_and_receiver_checks` covers native
and metadata input, independent and paired Core, replay and cumulative work;
`test_replay_reports_current_coverage_without_losing_historical_proof` covers
later partial Coverage and a genuine competing Claim;
`test_aggregate_coverage_uses_one_core_snapshot` covers concurrent Coverage writes,
`test_aggregate_snapshot_guards_work_callback` covers callback reentry, and
`test_aggregate_snapshot_honors_finite_limits` covers bounds without a false stop;
`test_completion_refuses_stop_after_aggregate_snapshot` and
`test_completion_without_inventory_also_observes_stop` cover concurrent stops;
`test_inventory_wiring_preserves_exact_source_scope` covers empty, malformed and
non-UTF-8 refs; `test_paired_commit_failure_cannot_pin_a_future_proof` covers
both sides of the Core commit; `test_paired_post_commit_failure_preserves_verified_prefix`
covers failure after one proof; and the source-failure, callback-exception and
caller-owned-transaction commit/rollback tests cover nonterminal outcomes.
`test_direct_verification_rejects_caller_owned_transaction` checks that the
direct API cannot create an Operational pin for a rolled-back proof.
`test_existing_orphaned_pin_refuses_without_fabricating_a_proof` covers the
already-orphaned continuation and a separate fresh request.
`test_wiring_stops_on_corrupted_stored_verification` checks that a real damaged
proof still stops the catalog when acquisition is replayed.
The installed wheel and sdist-wheel check is
`test_p5_installed_acquisition_and_exchange`.

## Inventory and evidence invariants

A complete or known-empty report is one immutable, attributed Group. A
receiver proof binds that exact Group, the original result Claim, typed root,
coverage coordinate, local verification provenance and complete ordered native
structures. It is independently rechecked at admission and on a checked read.
The receiver's actual verification time is recorded with its result; UUID time
and the ref's earlier observation time do not stand in for inventory time. Once
the proof is admitted, a request-local pin permits exact replay with renewed
checks and work charges. Its self-contained local provenance includes the
actual request identity, so a pin cannot select another request's verification.
If a crash loses that pin, a fresh structural reread
is a distinct verification with its own evidence coordinate; it does not rebind
the earlier proof. No source body or proof is stored in Operational. A missing
or stale proof, malformed input, source failure or exhausted budget cannot
become a verified complete inventory.

The Claim-aware inventory listing exposes all reported Groups and indicates
which have proof in the latest Coverage candidate set for that exact Claim.
It also returns the derived Coverage state, including conflict; a Group without
a current proof is not a statement that it was never verified historically.
Rootless presence, unknown and confirmed absence do not acquire invented roots
or inventories. Per-Claim proofs never select among contradictory Claims or
lend body authority to another Claim. Metadata-only operation remains valid.

All materialization and proof work is finitely reserved and cumulatively
charged, including replay, failed admission and callback work. Caller callback
exceptions retain their identity and cannot borrow checked-byte access. Actual
stored corruption stops the catalog; an invalid incoming claim, a missing proof
or a resource limit alone does not. `auto` and `core_only`, coexisting Context,
Exchange v6, backup, typed salvage and the cross-family comparison guards retain
their existing contracts.

## Review examples for this candidate

- A direct tree and a commit/fanout root produce a complete reported Group and
  a separately receiver-verified proof; an empty tree is known empty. Replay
  retains original coordinates, and a real later scan remains separate.
- Partial, malformed or budget-limited scans never prove completion. A valid
  Group without a proof appears as reported, not receiver-verified.
- Two result Claims, including conflicting roots under one observation, keep
  distinct groups/proofs; no evidence or note bytes move across Claims.
- A newer partial/unknown or competing Coverage candidate cannot fall back to
  an older complete one. Historical Groups remain reported.
- Invalid stored UTF-8 or tampered stored proofs stop the catalog; malformed
  input, budget callbacks and normal limits do not. Checked-read callbacks have
  no generic body/proof capability.
- Real Git fixtures cover SHA-1/SHA-256 and bare/non-bare repositories; paired
  and Core-only Query, Exchange, backup/salvage and distribution boundaries are
  checked where affected. No test is a live recovery or release acceptance.

The executable examples in
[`test_ref_inventory_transition.py`](../../tests/integration/p4/test_ref_inventory_transition.py)
cover each listed behavior: `test_inventory_report_and_receiver_proof_remain_claim_specific`,
`test_competing_claims_keep_separate_groups_and_no_winner`,
`test_shared_root_does_not_share_claim_verification`,
`test_later_partial_does_not_fall_back_to_verified_complete`,
`test_partial_group_never_becomes_receiver_verified`,
`test_forged_group_and_source_failure_never_prove_completeness`,
`test_lost_verification_pin_causes_new_check_without_rebinding`,
`test_progress_cannot_rebind_another_requests_verification`,
`test_proof_writer_budget_failure_rolls_back_without_false_completion`,
`test_proof_writer_callback_cannot_reenter_or_fake_corruption`,
`test_noncanonical_unicode_group_is_bounded_before_reencoding`,
`test_group_comparison_accounts_for_non_ascii_bytes`,
`test_provenance_comparison_accounts_for_non_ascii_bytes`,
`test_long_provenance_is_not_scanned_before_budget_reservation`,
`test_variable_json_fields_reserve_character_walk_before_scanning`,
`test_inventory_query_detects_damaged_stored_receiver_proof`, and
`test_receiver_inventory_proof_survives_exchange_and_backup`. The existing
I1–I3 and P7 suites cover the preserved admission, Exchange, Query, backup and
salvage boundaries; the later Search and producer transitions are not claimed
by these tests.
