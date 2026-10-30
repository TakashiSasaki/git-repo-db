# ADR 0036 Notes consumer transition contract

This contract scopes the opt-in transition after the merged typed-salvage
implementation. [ADR 0036](../adr/0036-ref-observations-and-shared-notes-mappings.md)
and [ADR 0026](../adr/0026-stop-salvage-restore-merge-after-corruption.md)
remain authoritative. The fixed baseline for this transition is main
`3d3776c61e48cbd1e2009d9a167e101c664af02d` (tree
`1b28a48b51a2da35beec20444458791b42d5f2a6`). This is an engineering contract,
not a new owner decision, public Schema 21 change, migration or release.

## Baseline remaining-work assessment and input boundary

This is the original assessment. Completed stacked units and the current
retirement boundary are recorded below; this table is not a new execution plan.

Rechecked against main `2ff4aab59dcdbada264d9a6a978c07b6ac4ad0d2` in the
cloud `git-repo-db` project. The dated six-PR proposal is an assessment input,
not an execution order. Neither six PRs nor a standalone D0 merge is required.

| Proposed work | Current disposition |
| --- | --- |
| D0 contract | The adopted ADR and this contract already establish the trust and retirement rules. Concretize input/projection boundaries with the first implementation; no new owner choice or standalone design PR is needed. |
| I1 acquisition | Still needed: the old explicit/external inputs cannot express rootless observations or multiple Claims. Add the typed original-report input below. Existing native/discovery enumeration, Claim-aware inventory verification and typed salvage are already implemented; do not recreate them. |
| I2 Query/CLI | Still needed for generic Git-object `notes_targets`, paired resource projections and their CLI consumers. Reuse the existing `get_ref_observation`, `get_ref_enumeration`, `get_notes_mapping`, `list_ref_notes_inventories` and `read_ref_note_bytes` boundaries. |
| I3 Search | Still needed: extraction and document identity use Capture/legacy claims, groups, roles and retained Notes. Preserve observation, result Claim and Mapping identities, alternatives and checked-body authority. |
| I4 old public API | Retire after producer/Query/Search callers have moved. No compatibility promise requires keeping an unused API, but it is still used now. |
| I5 physical/wire/recovery cut | Still needed after consumer migration: P1 DDL and Exchange/backup/salvage retain both families and collision guards. Do not delete these in the input PR. |

The first input implementation adds `NotesAcquisitionSpec.ref_inputs`, a bounded
tuple of `RefNotesInput`. Each contains the original `RefObservation` subject,
all supplied `RefObservationClaim` results, and optional reported
`NotesMappingClaim`/`NotesMappingGroup` units. A Mapping report references an
exact supplied Claim. Subject-only inputs are permitted. The subject's repository
must match the acquisition repository; its original issuer, source, visibility,
lossless raw ref name and nullable original time remain independent of the
current request/source. No Capture conversion, UUID allocation or sender proof
promotion occurs. Enumeration input continues through the existing scanner and
Exchange routes; this carrier does not fabricate an enumeration link.

Request intent binds every subject/result/report coordinate and encodes raw ref
and symbolic-target bytes as hex. Replaying that request preserves original
identities and reported alternatives; changing any intent requires a separate
explicit request. Admission still rejects subject/coordinate rebinding, while
independently attributed contradictory results remain inspectable as conflict.
The carrier is not a new atomic bundle owner: independently admissible units
can survive a later failure, and each whole Group remains atomic.

With an actual Notes source, requested inventory and target operations run for
each rootful supplied Claim through the existing root-specific receiver checks.
Reported Groups alone create neither Coverage proof nor body permission.
Inventory proofs retain the existing after-commit boundary for paired admission,
caller-owned transactions and callback failures. Original unauthenticated reports
are not claims of remote authenticity/freshness even when their structure can
be checked locally. Actual work, including replay and failure, uses the same
cumulative request budget. Rootless Claims and source-unavailable requested work
remain in `GitAcquisitionReport.deferred_ref_claims`, with partial/unknown status;
no fake root, empty inventory or complete Coverage is invented.

Projection consumers must use the existing Claim-aware APIs, exposing every
result and reported Group independently from current receiver evidence. Generic
Query and paired resources must stop deriving new-model results from Capture;
Search must then consume those explicit distinctions. Original evidence, local
proof and physical-copy read authority remain separate even for shared Mapping
content. Unsupported grammar/Coverage stays unknown/deferred. Query precedes
Search, then the old API/family cut; exact PR count follows coherent diffs.

This additive input PR preserves legacy input and discovery production because
actual downstream consumers still depend on it. Its explicit new-input route
produces no legacy Capture/Notes fact. It does not activate public Schema 21,
change the physical/wire format, migrate a catalog, or repeat PR #221/#223's
completed callback repair. Recovery remains corruption stop, read-only
preservation, typed salvage, fresh restore, revalidation/merge, validation and
activation under ADR 0026. Existing Recovery and collision tests remain required
at the eventual physical cut. No remaining owner-policy blocker was identified
for this first input boundary; B03/exact grammar and later activation/release
remain separately scoped.

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

Reported-Group admission uses the same protected callback boundary as receiver
proof admission, including its metadata preflight and its writer transaction.
Callbacks cannot insert unrelated facts, control the Core transaction, reenter
Core APIs or read protected proof columns. Callback failures roll back the
current atomic unit and retain the original exception; a corruption-shaped
caller exception does not diagnose the catalog. This applies to independent and
coordinator-owned Core capabilities. The optional no-budget path has no caller
work callback. These controls, finite-budget refusal, retry and genuine stored
subject corruption are covered by
[`test_ref_group_callbacks.py`](../../tests/integration/p4/test_ref_group_callbacks.py).

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

## R226 input-preparation correction

R226-01 requires revalidating supplied nested Mapping values and every supported
OID at the application input boundary. Frozen dataclass construction alone does
not establish that a supplied object's fields remain valid; SQLite affinity is
not an input-type validator. Reject malformed incoming metadata without diagnosing
a healthy catalog or removing previously admitted reports.

R226-02 places new-carrier processing inside the original request budget. A
shallow legacy preflight excludes carrier contents. Once the existing request
budget is open, a bounded shape walk reserves metadata visits before scheduling
children, using only exact allowed types and constant-time lengths. Before text
scanning, set/hash comparison, deep copy, semantic keys or JSON, reserve a finite
conservative input/output bound. Successful stages settle actual scalar UTF-8
input plus encoded carrier output; failed stages retain the reservation when
performed work is uncertain. The shape/text/depth limits are engineering bounds,
not new completeness or trust semantics. Value-only intent helpers also enforce
the same hard bounds, but confer no request or receiver authority.

Native and metadata acquisition meter initial intent, replay comparison and the
subsequent explicit-input admission preparation independently because each stage
performs work. The former post-encoding charge is removed. Paired preparation
passes its existing work/progress into these stages without creating another
request or resetting accumulated work. For a new carrier via Access, require an
existing approved grant before metered request copying/display preparation;
executor activation still requires review. That preparation and the later Git
acquisition reuse the same work/progress and attempt. Declining activation after
new-carrier preparation does not erase work already performed. The legacy
no-carrier approval flow is unchanged. No extra budget, sender authority or
unbounded pre-intent serialization supplies a shortcut around the original
request. Original FAIL evidence and independent re-review remain distinct from
the author's regression results.

## First Query projection unit (stacked on PR 226)

Git-object results add `ref_notes_targets` alongside the transitional legacy
`notes_targets`. Each entry contains the full original observation projection
(all result Claims, including unknown/competing results) and an exact-Claim,
explicit-interpretation Mapping projection read through the existing checked
Core API. Shared root content alone is not an association: require an original
Mapping Claim, relevant Group member or exact Claim's local evidence. Paired
Core resolutions reuse the same object projection inside the paired snapshot.
No global latest/root/note winner is selected.

These new associations are metadata/evidence projections. They do not infer
physical body availability or return note-body bytes. The existing
`read_ref_note_bytes` remains the explicit checked-body API; `include_bytes`
continues its implemented metadata/legacy-body behavior in this first unit.
Search, legacy family/API retirement and a new generic byte-output interface
remain separate work.

`list_ref_observations` and the opt-in CLI `ref-observations` enumerate original
subjects with every result Claim, including subject-only and rootless results.
They reuse existing snapshot-fenced pagination and validate the UUIDv4/v7 cursor
position independently of its checksum. Raw ref and symbolic-target bytes are
encoded as `{bytes_hex: ...}` without UTF-8 decoding. A changed Core snapshot
invalidates an old cursor. The existing `notes` command retains its explicitly
legacy Capture meaning. A finite 10,000-subject/association scan bound refuses
larger scope with QUERY_BUDGET rather than returning a falsely complete result;
checked projections also retain their finite work/byte/proof limits.

## R227 Query repair boundary

Association discovery includes bounded interpretation headers from Group-only
reports, which need not create standalone Mapping rows. Membership JSON is read
and validated only by the existing exact-Claim/root projection reader, then
matched against the requested target. Header count/bytes and checked projection
work stay finite; shared content, another Claim and an unrelated target cannot
acquire an invented Mapping report, canonical note or receiver proof.

The new ref-observation listing wraps caller work with the existing
`_QueryWorkBoundary` before entering Core/paired/application snapshots. Callback
exceptions cross all corruption classifiers in that wrapper and are restored to
the original exception object outside the application snapshot. Actual stored
corruption retains the existing stop behavior; no classifier or stop condition
is weakened.

## First Search migration unit

The common pinned-snapshot extraction used by Search rebuild and authority
fallback adds new-model Notes documents alongside the transitional legacy
Capture documents. A new document key includes an explicit ref-notes namespace,
the observation origin/v7 pair, exact result-Claim provenance and the full typed
Mapping value, including interpretation and nullable path. All alternatives
are considered; no representative Claim/root/note is chosen. Mapping-only,
Group-only and partial/historical reported Groups remain discoverable metadata.
Their source provenance and reported state stay separate from current inventory
Coverage and receiver-local role evidence.

Only the existing exact-Claim `read_ref_note` may supply text, from a locally
eligible checked physical copy. Another Claim sharing a root/Mapping lends no
body permission. A corrupted selected copy stops the catalog; a missing eligible
copy leaves metadata searchable. An old complete report does not override newer
partial Coverage, while independently admitted path/body evidence retains its
own meaning. Binary refs retain hex identity in summaries. Rootless observations
with no Mapping do not acquire invented Mapping search documents.

New-model extraction shares finite work across Claims and Maps in an invocation;
a supplied work handle can also accumulate across invocations. Search and
rebuild use `_QueryWorkBoundary` across all snapshot/classifier layers. Variable
key/summary/text processing is reserved before processing. Checked Core readers,
finite header/document/summary limits and existing Search candidate revalidation
remain authoritative. Large scopes may honestly refuse with a resource limit;
no truncation is presented as complete. Search remains disposable. Old API,
physical family, schema/wire retirement and normal Schema 21 activation are not
part of this unit.


## Producer and public API retirement unit (stacked on PR 228)

PRs 226–228 supply the adopted original-report input, Claim-specific Query/CLI
and Search boundaries. The next unit disables legacy production in normal
native, metadata-only, Core-only, paired and Access acquisition. Discovery keeps
the unrelated GitObservation/discovery UUIDv4 snapshot and the actual Ref
enumerations, with their original IDs on replay. It allocates no Capture UUIDs
and admits no legacy Capture/Notes rows. Inventory and body acquisition use the
existing exact-Claim reader and receiver checks, with the same request budget.

`NotesAcquisitionSpec.explicit_captures`, `external_claims`, `external_groups`,
Capture-owned acquisition Coverage, legacy report fields `notes_inventories` /
`note_acquisitions`, discovery `captures`, generic/paired `notes_targets`,
`get_git_object(note_captures=...)`, the Capture Query methods and CLI `notes`
command are retired public interfaces. Use `ref_inputs`, `ref_*` report fields,
`ref_notes_targets`, existing RefObservation/Mapping/inventory/body Query APIs
and CLI `ref-observations`. Normal Search extraction now uses only the checked
new model. Its dead legacy extractor is removed. Old physical rows are neither
converted into new Claims nor made searchable by inventing receiver evidence.
Existing cached legacy Notes documents fail authority comparison and fall back
to the new authoritative extraction before a rebuild replaces that derivative.

The deferred physical family still has private `_legacy_*` diagnostic acquisition
and Query methods and private diagnostic DTOs. They keep old-family preservation
and integrity behavior executable while Core DDL, Core family APIs, Exchange,
backup/recovery/salvage, and cross-family copy-collision guards await one coordinated
cut. No schema/wire, live catalog migration, ordinary Schema 21, shared grammar,
general GitObservation or unrelated discovery UUID is removed here. These private
methods are not public compatibility aliases and no normal producer calls them.

Behavior mapping for retired mechanisms:

| Previous mechanism assertion | Replacement / retained safety check |
| --- | --- |
| Dual legacy/new acquisition report and Capture discovery | `p5/test_legacy_retirement_e2e.py::test_new_only_acquisition_query_cli_search_replay`: no old rows, verified inventories/body, original-ID replay with cumulative work, native/metadata × Core/paired × both formats/layouts; existing `p5/test_git_acquisition.py` keeps metadata-only and ordinary-body exclusion checks using the Ref outputs. |
| Legacy public carriers and Query/CLI names | `test_retired_public_carriers_are_rejected`, `test_retired_public_query_and_producer_names`, `test_retired_cli_command_is_rejected`; foreign supplied subjects/Claims/Groups still reject before admission in Access regressions. Their input preflight is charged. |
| Capture-owned metadata Coverage acceptance | `access/test_review_corrections.py::test_metadata_capture_coverage_resolves_the_actual_capture_owner` rejects every retired input, preserving all existing rows and a healthy catalog. |
| Capture binding immutability / damaged old-family reads | Explicit private-family tests `test_legacy_physical_capture_binding_remains_immutable` and `test_legacy_physical_capture_corruption_stops_diagnostic_query`; both preserve original rows and corruption stop. Original P4 role/inventory tests remain private diagnostic tests without weaker body/proof assertions. |
| Paired legacy Notes projection / CLI listing / binary Search | P6 `test_queries.py`, `test_cli.py`, `test_corrections.py::test_binary_notes_rebuild_and_scan_equivalence` use independently admitted typed Ref evidence. P6 fixture legacy facts remain only for diagnostic/physical support tests. |
| Legacy Exchange fixture built via public acquisition | P5/I3 fixture setup uses explicit private diagnostics after new-only native acquisition. Original roundtrip, forged-root refusal and preservation assertions remain, pending the coordinated Exchange cut. |

The modified installed-distribution and P5/P6 compatibility scenarios use the
new reader rather than a public Capture API. They are not claimed executed
unless listed in the implementation report. No test is deleted or skipped to
retire a mechanism.


## R229 public caller and port correction

Independent review of `5270e011eb590b451d387d132973dad6c8dfc76e`
reported scoped FAIL (14/16 passing in 10.34s, plus a separate port import failure).
R229-01 (P1) was a retained Access CLI consumer of removed
`report.note_acquisitions`, causing an AttributeError after successful acquisition.
The CLI now counts unique retained note OIDs solely from `ref_note_acquisitions`.
Its interactive real-Git regression covers both Notes-enabled and Notes-disabled
requests in sha1/sha256, including successful JSON/exit status and no old rows.
R229-02 (P2) was stale DTO imports and Capture methods in `ProductionQueryPort`.
The port now declares the current Ref pagination and exact-Claim APIs, no Capture
methods/parameter, and the existing optional Search/rebuild work handle. An import
and annotation-resolution smoke regression preserves the public contract. No
private DTO alias or retired report field is restored. The original independent
FAIL remains historical evidence; no independent re-review is claimed here.


## Final coordinated physical cut (stacked on PR 229)

This unit supersedes the deferred physical-family boundary above. PRs 226–229
remain fixed. The five old opt-in physical tables (`captures`, `notes_claims`,
`notes_groups`, `note_roles`, `retained_notes`), their immutable/admission guards,
Capture-owned Coverage columns/owner, Core methods/ports/domain values, private
legacy producer/Query DTOs/readers, and legacy Exchange/backup/salvage admission
are removed together. `notes_inventories` was an additional wire section, not a
sixth table. The retired families are not renamed into the new tables and no
actual catalog is migrated. The machine disposition contract and introspected
physical schema are synchronized. Ordinary Schema 21 and unrelated observation,
provider recording and discovery UUIDv4 meanings remain unchanged.

The opt-in factory format is `repo-catalog/p1-isolated-2`; its Core factory now
has 23 tables. Its other factory stores' physical DDL/fingerprints are unchanged
(Context 19, Operational 8, Search 3). These are factory table counts, not a count
of responsibility stores or open files. Core fingerprint is derived from the
packaged DDL. Exchange accepts only `git-repo-db/adr0036-exchange-v7` with the exact
current section/row envelopes; v6 and the six old sections are rejected. New
backup manifests use version 2 and restore refuses version 1; actual manifest
hashes, packaged schema fingerprints, identities/pairing and retained data are
still revalidated. Unknown salvage types remain qualified/deferred/rejected;
they cannot restore an old Notes family or confer body authority. No unreleased
old-format compatibility or migration is promised.

Shared `_notes_group`, `valid_note_role`, native Notes traversal and verification
accounting remain in use by Ref Mapping/Group/evidence and copy validation.
Same-family exact-body/copy collision checks, bounded comparison accounting,
callback exception boundaries and unsupported Ref Coverage behavior remain.
`legacy_source_vm_steps` is the retained generic metadata/Context extraction
budget, not a surviving Capture Notes path. Ref subjects, Claims, alternatives,
Group-only/partial reports, Mapping content, receiver evidence and each physical
copy retain their separate original identities and qualifications.

The ADR 0026 sequence is preserved: corruption stops ordinary service/backup;
source DB/WAL bytes are preserved while typed salvage emits untrusted candidates;
a checked healthy backup restores into a fresh destination; candidate merge
rechecks dependencies, original identity, structural proof and actual bytes;
final validation precedes activation. The new composite E2E
[`test_physical_cut_e2e.py`](../../tests/integration/p7/test_physical_cut_e2e.py)
combines real acquisition, two same-root Claims/Group-only reports, one eligible
Claim's body, Query/CLI/Search, explicit Git-only Exchange, Core-only/paired
backup/restore, damaged-copy stop, byte-preserving salvage, post-backup subject
merge and activation. Git-only transport does not claim Context interchange.
Existing paired Context and metadata-only regressions remain independent.

Retired mechanism tests and their typed-behavior replacements are indexed in
[`adr0036_retired_test_map.json`](../../tests/support/adr0036_retired_test_map.json).
The map preserves original node IDs; old binary/empty-note behavior is exercised
by a new direct Ref role test and real installed wheel/sdist-wheel scenario.
Unrelated metadata/Context/recovery tests stay active. Cross-family copy tests
are superseded by exact same-family replay/conflict/corruption tests; there is
only one Notes-copy family now. No absent-name assertion alone establishes
acceptance. The implementation report distinguishes exploratory failures,
fixed-source tests, packaging execution and CI selection/skips from full release
acceptance. No live recovery, merge or deployment is authorized by this contract.

## R230 salvage classification and preservation-test correction

Independent review of `ffeea444677b8d8bd8ae4615349bfe6769fbac1a` was
scoped FAIL: 12/16 succeeded in 11.75s, with four post-backup metadata recovery
failures (sha1/sha256 × Core-only/paired). Source DB/WAL preservation and the
independent real COMMIT-denial probes succeeded. Those failures remain historical
evidence; they are not replaced by an author PASS declaration.

R230-01 (P1) changes the Context test following `retained_metadata` to `elif`:
retained commit/tree/tag, Context document and generic candidates now have
mutually exclusive classification. Valid native bytes/copy identity are not
reclassified as generic untyped BLOBs. The new post-backup regression checks all
three native types, exact original copy IDs, a damaged sibling withheld without
staging its body, nominal metadata-only rows, Context text, fresh restore/merge
and byte-for-byte source DB/WAL preservation in both formats and topologies.

R230-02 (P2) replaces the old keyword-based retired-test matches with explicit
behavioral invariants and appropriate negative/preservation tests. In particular,
real SQLite COMMIT denial and SIGKILL immediately after the new Ref body INSERT
have dedicated acquisition regressions: rollback, independently admitted prefix,
existing checked copy preservation, original copy/Claim identity and cumulative
retry work are asserted. A Group INSERT failure separately proves rollback of
new nominal objects while retaining an original Group. Narrow-path, unsupported
mode/ambiguous path and bad incoming-body regressions keep the corresponding
refusal/preservation behavior executable. Current typed Group/Claim/proof and
retired-interface differences are stated in the mapping; this is not a claim
that every old parameter matrix was rerun. The first map's target-existence
check did not establish behavioral equivalence. All 78 entries were reviewed;
the implementation report lists the small executed scope and remaining gaps.
No schema/wire change, legacy alias, runtime permission change or new recovery
policy is part of these corrections.
