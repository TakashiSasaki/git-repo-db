# ADR 0036 typed salvage contract

Current opt-in OID spelling and fresh-format versions follow the
[OID naming contract](object-oid-naming-contract.md). Pinned baseline examples
below retain their historical spelling and do not provide compatibility APIs.

This contract specifies the opt-in RefObservation recovery work on the merged
I1–I3 stack. The authoritative design is [ADR 0026](../adr/0026-stop-salvage-restore-merge-after-corruption.md),
with the identity and origin override in [ADR 0036](../adr/0036-ref-observations-and-shared-notes-mappings.md).
It does not activate the ordinary Schema 21 path, migrate a real catalog, retire
legacy Capture/Notes, or establish issuer authenticity. Implementation and
independent review evidence must name the actual source tree.

## Recovery sequence and boundary

Drain cooperating writers and preserve the suspect database and its WAL, SHM,
or rollback journal. Open only a bounded working copy; neither execute recovered
schema/triggers nor call the ordinary exporter on a stopped catalog. A candidate
is untrusted source-attributed material, not a backup or proof of origin. Restore
a suitable independently revalidated backup to a fresh, distinct destination,
revalidate candidates through receiver domain admission, validate the resulting
authority and its Core/Context scope, and activate only after validation. The
original remains preserved and stopped. No suitable backup means no restored
service claim.

The bounded serialization retains each original origin UUIDv4, observation or
enumeration UUIDv7, raw ref bytes, immutable subject, semantic coordinates and
original provenance. Extraction coordinates describe recovery and cannot
replace that provenance. A digest or readable row proves neither issuer nor
receiver authority. Physical Notes bytes may be serialized only with the exact
Claim, root, structural path and copy identity needed for revalidation; this
does not permit staging the annotated ordinary file body.

## Domain-unit and dependency matrix

| Unit | Dependencies and receiver treatment | Atomicity and incomplete scope |
| --- | --- | --- |
| Ref subject | Original repository, key, ref bytes, source, visibility and optional observation time | One immutable subject; exact replay only; changed subject is rejected |
| Result Claim | Original subject and full provenance/result, including scoped absence evidence | One original coordinate; separately attributed conflicts remain alternatives, while coordinate rebinding is rejected. Unknown and absence have no invented OID |
| Enumeration | Original event plus every ordered link and its exact subject and Claim | Admit the original event only as a whole, including a genuinely empty event. Missing, duplicate or reordered membership is omitted or rejected, never called complete; independent subjects and Claims remain eligible |
| Shared Mapping content | Typed root, interpretation, target, note and exact path | Preserve standalone content without creating a Claim, receiver proof or body permission |
| Mapping Claim | Exact result Claim/root and original mapping/provenance | One reported semantic unit; shared Mapping content does not merge Claims |
| Mapping Group | Exact result Claim/root, scope, status, original provenance and whole membership | Preserve each ordered group unchanged, including known empty. Do not union partial groups or infer missing members |
| Notes evidence | Exact result Claim/root, mapping, original evidence coordinate and native structural proof | Recompute the supported single-path proof locally; a sender flag or another Claim's proof does not authorize it |
| Physical Notes copy | Exact Claim/root/mapping evidence, copy UUIDv4, blob bytes, type, size, Git OID and SHA-256 | Recheck proof and each actual copy; independent good copies remain eligible. Direct-tree roots require no fabricated commit |
| Ref Coverage Claim | Exact owner and original observation time/state/details | Preserve metadata and latest/stale/conflict behavior; unsupported completeness stays unknown |
| Notes inventory proof | Exact complete or known-empty Group, Coverage Claim, original verification coordinate and full structures | Rewalk the supported inventory locally; no sender flag, partial group or older complete claim establishes current completeness |

Dependencies may be present in the restored baseline or supplied as complete
input units. A missing or invalid dependency is reported as deferred/rejected;
it cannot be silently invented. Candidate order must not change which complete,
independently admissible units can be recovered. Every visible group or event
is a whole transaction; a failure rolls back that unit, without erasing work
already charged or independently admitted units. Actual corruption already
present in the destination invokes catalog-wide stop; malformed incoming
candidates, genuine conflicts, exhausted limits and caller callback exceptions
are not themselves proof of target corruption.

When the original link rows are all present but their subject or result Claim
is unreadable, extraction may retain the complete link coordinates as an
untrusted pending event, while reporting the missing source dependency. The
receiver resolves only the same immutable subject and original Claim coordinate
from its validated baseline or another input unit. A bounded fixed-point retry
after the input stream resolves transitive later dependencies; a pass without
progress defers the remainder, and each retry consumes the same durable budget.
An independently readable Claim whose subject is missing can likewise wait for
that exact subject; the receiver checks their original scope before admission.
If a link itself is missing, duplicated or malformed, no whole-event candidate
is asserted. None of these cases constructs a missing member or chooses among
conflicting Claims.

Notes and supported inventory candidates may also retain their original full
Mapping, Group, evidence and Claim coordinates when a referenced source row is
unreadable. The exact copied native structure and any physical Notes body are
checked before output; the receiver still resolves the precise original Claim,
checks its root and revalidates the entire applicable proof. A proof row can
supply its complete original Group coordinates, but cannot combine partial
Groups or supply a missing Coverage Claim's advisory details. The receiver may
resolve that Claim from the baseline or input. If any required coordinate is
still missing, all writes for that candidate roll back and it stays deferred.

## Bounded work and dispositions

Reserve variable-length fields, proof structures and bodies before Python
materialization. Bound individual units, aggregate input/output, row counts,
JSON depth, proof traversal and receiver work. Charge work actually repeated on
replay, rejection or rollback. A durable request and reservation checkpoint
outside reconstructible Operational/Search preserve cumulative expenditure
across retries, process crashes and cooperating concurrent continuations; lost
state fails closed. Work callbacks must not borrow the adapter's checked-byte
capability, and their own exceptions retain their original identity.

For extraction, the request ledger is a separate coordination sidecar in the
stopped source directory, bound to that directory's identity and the explicit
request ID. It never writes the source database or its SQLite sidecars; moving
the output file does not create a new allowance. The default request is bound
to the absolute output path, so callers continuing to a different output must
supply the same explicit request ID. Output candidates have a finite nesting
and element limit; a whole event or Group that exceeds it is omitted and the
receipt is partial rather than silently shrinking the unit. Decoder traversal
has its own cumulative byte-work budget in addition to the read-byte budget.
Forensic readers inspect column descriptors before projecting source values;
typed Core tables with generated or hidden columns are omitted. Existing
Context tables may contain auxiliary generated columns: those are excluded
from the projection, with direct table scans and an authorizer that disallows
views, triggers and unapproved functions. Each forensic connection has finite
SQLite size and VM limits, and its VM reservation is
persisted before execution and settled to measured work after a clean return.
The independent reader allowances are cumulative across an extraction request.
Draft extraction ledgers created before these VM dimensions cannot silently
resume with fresh allowances: mismatched accounting fails closed. Existing
merge-request ledgers do not acquire these extraction-only dimensions.

The restored-baseline receipt is a local workflow record written only after
backup validation and fresh restore. It does not authenticate an issuer, sign a
backup or protect against an actor with arbitrary write access to recovery
sidecars. Activation still validates the resulting databases and scope; the
receipt cannot make an unchecked candidate or corrupted target healthy.

Receipts distinguish admitted, exact replay, qualified observation, rejected,
deferred and unprocessed units. Unreadable or uninspected scope, a missing
dependency and an exhausted limit remain explicit; none implies empty or
complete data. A successful activation validates the restored authority and
reported scope, not that all suspect facts were recovered.

## Verification obligations

Use only disposable synthetic catalogs. Exercise metadata-only absence/unknown
and non-UTF-8 refs; shared roots, replay, competing Claims and rebinding; empty,
malformed, missing and reordered events/groups; shuffled and missing dependencies;
proof/body forgeries and damaged sibling copies; complete/empty and unsupported
Coverage; source and filesystem preservation; bounded work, rollback, crash and
concurrency; stored corruption versus invalid input and callback errors; and
fresh backup restore, merge, validation and both successful and failed activation.
Exercise SHA-1 and SHA-256 without claiming untested platforms or live catalogs.

## Supported scope and executable mapping

| Unit or boundary | Current supported treatment | Regression examples |
| --- | --- | --- |
| Subject and result Claims | Typed metadata-only extraction and atomic admission with original IDs, bytes and provenance; distinct Claims stay distinct | `test_empty_event_and_rootless_claims_survive_without_context`, `test_lossless_ref_and_competing_claims_survive_shuffled_replay` |
| Enumeration | Whole event with all original ordered links, including empty events; resolve missing link dependencies from the baseline or later input, otherwise defer; independent Claims may survive an omitted event | `test_transitive_pending_dependencies_are_order_independent`, `test_missing_event_dependency_resolves_from_baseline_or_later_input`, `test_missing_event_link_does_not_discard_independent_claim`, `test_existing_whole_event_rejects_reordered_membership` |
| Mapping content, Claims and Groups | Content may stand alone; Claims and each whole reported Group retain their own scope, order and provenance | `test_standalone_mapping_never_creates_evidence_or_body`, `test_partial_groups_are_not_unioned_into_complete_coverage` |
| Notes evidence and physical copies | Locally recheck exact Claim/root/path/physical bytes, including missing dependencies; preserve original evidence and add distinct receiver evidence | `test_notes_dependencies_resolve_without_rebinding_original_evidence`, `test_pending_note_cannot_rebind_existing_claim_to_another_root`, `test_damaged_note_copy_is_omitted_without_losing_valid_sibling`, `test_invalid_candidate_rolls_back_and_actual_target_damage_stops` |
| Coverage | Preserve supported Claim history; verify whole Notes inventory only, including resolved dependencies. Unsupported completeness Claims remain exchangeable metadata with unknown derived completeness | `test_inventory_dependencies_resolve_from_baseline_or_later_input`, `test_whole_inventory_rejects_changed_group_membership`, `test_older_salvaged_complete_cannot_replace_newer_partial` |
| Fresh baseline, coexistence and activation | Restore revalidated Git-only or paired backup, check the scope and identities, merge, then validate and activate | `test_full_fresh_restore_salvage_and_activation`, `test_ref_merge_checks_paired_context_identity`, `test_missing_verified_baseline_cannot_merge_or_activate`, `test_corrupt_fresh_target_is_stopped_and_not_activated` |
| Bounds and preservation | Source copy, bounded typed candidates, generated-column exclusion, durable cumulative requests and no callback borrowing | `test_generated_source_columns_are_never_evaluated_and_other_rows_survive`, `test_context_generated_columns_are_not_selected_or_executed`, `test_extract_vm_expenditure_survives_a_continuing_request`, `test_crashed_vm_reservation_is_not_refunded_on_resume`, `test_extract_crash_retains_reservation_and_preserves_source`, `test_parallel_extractions_share_one_cumulative_budget`, `test_candidate_decode_limit_stops_before_admission_and_survives_retry`, `test_receiver_work_callback_cannot_borrow_body_access` |
| Untyped and legacy data | Omit unrecognized source tables, ordinary blob bodies and untyped binary fields. Preserve legacy Capture/Notes recovery only when the exact source role and bytes revalidate; do not use it as a different ref Claim's evidence | `test_unknown_binary_is_not_staged_by_generic_extraction`, `test_legacy_note_bytes_are_staged_only_with_valid_original_proof`, `test_ordinary_blob_cannot_be_staged_as_structural_metadata` |

These named examples are in `tests/integration/p7/test_ref_typed_salvage.py`;
the P7 and I1–I3 regression suites remain separate obligations. The supported
inventory verifier does not verify arbitrary Coverage kinds, provider origin,
the current truth of an old report, or the completeness of unreadable source
scope. No real catalog conversion, automatic migration, Context Transfer
expansion, ordinary file-body archive or release acceptance follows from these
synthetic tests. Durable reservations assume cooperating local processes and
the filesystem guarantees documented by the recovery accounting module; they
are not a host power-loss proof.
