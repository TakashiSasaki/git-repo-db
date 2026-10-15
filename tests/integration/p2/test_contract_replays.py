"""Execute retained P1 adversaries against the actual production Core subclass.

Imported functions retain their actual pytest parameterization. The local core
fixture binds every call to GitCore, rather than rerunning only the reference.
"""

from tests.integration.p1.test_core import (  # noqa: F401
    test_cached_statement_authorization_does_not_leak,
    test_checked_native_full_parent_group_excludes_across_observation_scopes,
    test_closed_group_does_not_exclude_unrelated_scope,
    test_closed_group_excludes_later_positive_slot_in_same_scope,
    test_core_coverage_five_columns_semantic_fk_latest_unknown_and_empty,
    test_cross_observation_compatible_positive_slots_do_not_conflict,
    test_exact_claim_replay_monotonic_later_evidence_conflicts_and_bad_replay,
    test_explicit_intrinsic_slot_conflicts_across_observation_scopes,
    test_explicit_tree_mode_conflicts_across_observation_scopes,
    test_ordered_groups_are_whole_atomic_and_never_union,
    test_parent_group_transport_reorder_is_exact_replay_not_new_claim,
    test_signed_epoch_microseconds_and_observations,
    test_supported_connection_rejects_arbitrary_operations,
    test_tree_entry_conflicts_use_name_slot_and_mode_target_values,
    test_triggers_reject_mutation_on_infrastructure_connection,
    test_unknown_parent_position_compares_membership_without_fake_slot,
    test_unknown_position_and_out_of_order_parents_preserve_actual_evidence,
    test_untrusted_report_cannot_assert_local_verification,
)
from tests.integration.p1.test_notes import (  # noqa: F401
    test_capture_binding_immutable_no_new_retry_identity,
    test_false_relevant_mode_or_name_rejects_body,
    test_metadata_only_notes_role_obeys_zero_proof_step_budget,
    test_notes_projection_closed_scope_does_not_borrow_other_scope_absence,
    test_same_capture_reports_alternatives_groups_and_replay,
    test_sender_claim_hash_prefix_and_ref_do_not_authorize_retention,
)
