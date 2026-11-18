"""Execute retained P1 adversaries against the actual production Repository subclass.

Imported functions retain their actual pytest parameterization. The local repository
fixture binds every call to GitRepository, rather than rerunning only the reference.
"""

from tests.integration.p1.test_notes import (  # noqa: F401
    test_new_role_exact_binary_body_and_git_hash,
)
from tests.integration.p1.test_repository import (  # noqa: F401
    test_cached_statement_authorization_does_not_leak,
    test_checked_native_full_parent_group_excludes_across_observation_scopes,
    test_closed_group_does_not_exclude_unrelated_scope,
    test_closed_group_excludes_later_positive_slot_in_same_scope,
    test_cross_observation_compatible_positive_slots_do_not_conflict,
    test_exact_claim_replay_monotonic_later_evidence_conflicts_and_bad_replay,
    test_explicit_intrinsic_slot_conflicts_across_observation_scopes,
    test_explicit_tree_mode_conflicts_across_observation_scopes,
    test_nullable_positive_epoch_microseconds_and_observations,
    test_ordered_groups_are_whole_atomic_and_never_union,
    test_parent_group_transport_reorder_is_exact_replay_not_new_claim,
    test_repository_coverage_five_columns_semantic_fk_latest_unknown_and_empty,
    test_supported_connection_rejects_arbitrary_operations,
    test_tree_entry_conflicts_use_name_slot_and_mode_target_values,
    test_triggers_reject_mutation_on_infrastructure_connection,
    test_unknown_parent_position_compares_membership_without_fake_slot,
    test_unknown_position_and_out_of_order_parents_preserve_actual_evidence,
    test_untrusted_report_cannot_assert_local_verification,
)
