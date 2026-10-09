# Latest-state table and schema-object inventory

Baseline: PR #12 (`a3a4cb7482d42709f79d137b802f1789e3aa45cb`), schema 13. Current fresh schema 14. This is structural inventory, not behavioral acceptance.

Composed DDL SHA-256: `13d835b5b141c9d8647f0318c8b2bd1d1590df341baa28f98f755f274753a531`. Current objects: 103 tables, 48 views, 496 triggers, 108 indexs.

Every production table follows. The JSON companion records every column and FK, along with actual added, removed and changed object names. Current resource rows are excluded from immutable parser publications.

| Table | Change | Key | Owner | Lifecycle | Reason |
|---|---|---|---|---|---|
| acquisition_progress | retained | git_acquisition_id | git_acquisition_id | Catalog-local operational state | Resume/repair coordination for retained Git acquisitions |
| acquisition_roots | retained | acquisition_root_id | repository_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Captured immutable traversal roots of retained Git acquisition |
| active_cache_entries | retained | active_cache_entry_id | Via cache_locators | Catalog-local operational state | Replaceable cache materialization separate from durable content identity |
| blob_content_map | retained | git_object_id | git_acquisition_id | Retained immutable evidence / relation | Retained blob-to-content relation for captured Git object bytes |
| cache_leases | retained | active_cache_entry_id, job_id, attempt | Via active_cache_entries, job_attempts | Catalog-local operational state | Prevents concurrent cache eviction during active operations |
| cache_locators | retained | cache_locator_id | repository_uuidv4 | Catalog-local operational state | Local cache destinations; no portable identity or current resource history |
| change_request_events | retained | change_request_event_id | repository_uuidv4, change_request_id, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained result-owned PR timeline events |
| change_request_observations | retained | change_request_observation_id | repository_uuidv4, change_request_id, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained PR metadata interpretations and code target capture |
| change_requests | retained | change_request_id | repository_uuidv4, change_request_id | Typed identity / context | Typed PR identity and acquisition binding used by reviews and code |
| code_acquisitions | retained | code_observation_id, role | Via acquisition_roots, code_observations | Retained immutable evidence / relation | Links each frozen PR code role to its exact Git acquisition |
| code_commits | retained | code_listing_id, fetch_occurrence_id, position, parsed_result_uuidv4 | repository_uuidv4, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained PR commit-list page interpretations |
| code_file_changes | retained | code_listing_id, fetch_occurrence_id, position, parsed_result_uuidv4 | repository_uuidv4, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained PR file-list page interpretations |
| code_listing_progress | retained | code_listing_id | Via code_listings | Catalog-local operational state | Local incremental status for retained PR code lists |
| code_listings | retained | code_listing_id | change_request_id, fetch_collection_id | Retained immutable evidence / relation | Frozen PR list scope, contextual head/base and exact collection |
| code_observations | retained | code_observation_id | repository_uuidv4, change_request_id, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained PR code capture and eligibility boundary |
| collection_memberships | retained | fetch_collection_id, change_request_id, kind, provider_change_request_document_id | change_request_id, fetch_collection_id | Retained immutable evidence / relation | Exact membership of retained historical document collections; excludes current reviews |
| collection_progress | retained | fetch_collection_id | fetch_collection_id | Catalog-local operational state | Local collection resume/partial/complete status; not a body transcript |
| commit_parents | retained | git_fact_uuidv4 | repository_uuidv4, parsed_result_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Result-owned retained Git commit structure |
| commits | retained | git_fact_uuidv4 | repository_uuidv4, parsed_result_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Result-owned retained Git commit interpretation |
| completion_markers | retained | completion_marker_id | fetch_collection_id | Retained immutable evidence / relation | Immutable terminal proof binds exact fetch/current page sets; never mutable bodies |
| content_digests | retained | content_id, representation, algorithm | Via contents | Immutable durable identity/bytes | Durable representation-specific shared content digests |
| content_locations | retained | content_id, kind, locator | Via cache_locators, contents | Catalog-local operational state | Replaceable local materialization locations |
| contents | retained | content_id | Catalog-local / shared natural identity | Immutable durable identity/bytes | Durable shared content identity and length |
| coverage_claims | retained | coverage_claim_id | Via coverage_scopes | Retained immutable evidence / relation | Immutable five-column observation claims with latest-time set derivation |
| coverage_scopes | retained | coverage_scope_id | repository_uuidv4, change_request_id | Typed identity / context | Exact typed coverage owner/kind/context |
| current_collection_pages | added | fetch_collection_id, ordinal | fetch_collection_id | Immutable collection receipt | Minimum typed current-resource membership and page/terminal proof, without message bodies |
| database_identity | changed | singleton | Catalog-local / shared natural identity | Catalog-local operational state | Fresh schema/DDL/catalog lifecycle identity |
| document_observations | changed | document_observation_id | repository_uuidv4, change_request_id, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained PR title/body/conversation interpretations; review families prohibited |
| documents | changed | change_request_id, kind, provider_change_request_document_id | change_request_id | Typed identity / context | Natural identity of retained PR title/body/conversation documents; review families prohibited |
| exchange_admissions | retained | record_key | Catalog-local / shared natural identity | Retained immutable evidence / relation | Admission receipts for immutable exchange records; current states use separate admission |
| exchange_blocked_coverage_claims | retained | coverage_claim_id | Via coverage_claims | Catalog-local operational state | Receiver-local unresolved immutable proof conflict barriers |
| exchange_blocked_results | retained | parsed_result_uuidv4 | parsed_result_uuidv4 | Catalog-local operational state | Receiver-local unresolved immutable result conflict barriers |
| exchange_local_identities | retained | table_name, local_key_json | Catalog-local / shared natural identity | Typed identity / context | Remaps immutable portable exchange identities to receiver-local keys |
| exchange_selection_blocks | retained | scope_kind, scope_uuidv4, record_key | Catalog-local / shared natural identity | Catalog-local operational state | Receiver-local unresolved scope conflict barriers |
| exchange_source_provenance | retained | source_registration_uuidv4, origin_catalog_uuidv4, definition_sha256 | source_registration_uuidv4 | Immutable received provenance / local configuration boundary | Historical source definitions kept separate from receiver operational configuration |
| exchange_staging | retained | record_key, content_sha256 | repository_uuidv4 | Bounded pending intake | Existing durable pending intake reused for bounded current conflicts/dependencies |
| fact_selection_decisions | retained | fact_selection_decision_uuidv4 | repository_uuidv4, source_registration_uuidv4, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained explicit fact-selection decision history |
| fact_selection_predecessors | retained | fact_selection_decision_uuidv4, predecessor_decision_uuidv4 | Via fact_selection_decisions | Retained immutable evidence / relation | Exact immutable predecessor relations for fact selection |
| fact_selection_publications | retained | fact_selection_decision_uuidv4 | Via fact_selection_decisions | Retained immutable evidence / relation | Seals exact fact-selection predecessor membership |
| fact_selection_scopes | retained | fact_selection_scope_uuidv4 | repository_uuidv4, change_request_id, source_registration_uuidv4, git_acquisition_id | Typed identity / context | Typed fact-selection owner/context without implicit fallback |
| fact_selection_staging | retained | fact_selection_decision_uuidv4 | Catalog-local / shared natural identity | Bounded pending intake | Existing pending missing-dependency fact decisions |
| fetch_collections | retained | fetch_collection_id | repository_uuidv4, change_request_id, fetch_collection_id | Retained immutable evidence / relation | Acquisition scope/provenance for retained history and minimal current collections |
| fetch_occurrences | retained | fetch_occurrence_id | repository_uuidv4, fetch_collection_id | Retained immutable evidence / relation | Original still-required historical HTTP input observations; pure current pages do not require these |
| git_acquisition_publications | retained | git_acquisition_id | repository_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Seals exact retained raw Git object and traversal-root membership |
| git_acquisitions | retained | git_acquisition_id | repository_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Immutable retained Git acquisition context and observation time |
| git_object_payloads | retained | git_object_id | Via git_objects, payloads | Immutable durable identity/bytes | Verified retained original Git bytes by object identity |
| git_objects | retained | git_object_id | Catalog-local / shared natural identity | Immutable durable identity/bytes | Immutable Git object format/OID identity |
| git_text_facts | retained | git_fact_uuidv4 | repository_uuidv4, parsed_result_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Retained result-owned Git text interpretation |
| identity_relation_cancellations | retained | cancellation_uuidv4 | Via identity_relations | Retained immutable evidence / relation | Immutable explicit identity-relation cancellation evidence |
| identity_relation_staging | retained | record_uuidv4, content_sha256 | Catalog-local / shared natural identity | Bounded pending intake | Existing pending missing identity relation dependencies |
| identity_relations | retained | relation_uuidv4 | Via repositories, service_instances | Retained immutable evidence / relation | Explicit equivalence evidence without row merging |
| incremental_scans | retained | incremental_scan_id | fetch_collection_id | Retained immutable evidence / relation | Frozen collection scan boundary and safe watermark evidence |
| index_generations | changed | index_generation_id | Catalog-local / shared natural identity | Rebuildable derived data | Replaceable search generation metadata including issue family |
| index_membership | retained | index_generation_id, search_document_id | Via index_generations, search_documents | Rebuildable derived data | Replaceable generation membership |
| inventory_observations | retained | inventory_observation_id | source_registration_uuidv4, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained source acquisition inventory diagnostics, separate from repository current resources |
| issue_resources | added | service_instance_uuidv4, kind, provider_resource_id | repository_uuidv4, service_instance_uuidv4 | Mutable accepted state | One accepted mutable row per service/kind/provider ID; repository is membership not identity |
| job_attempts | retained | job_id, attempt | Via jobs | Catalog-local operational state | Local execution/resume attempts and checkpoints |
| jobs | retained | job_id | Via job_attempts | Catalog-local operational state | Local frozen work plans and execution status |
| local_parser_profile_verification_trust | retained | parser_profile_verification_uuidv4 | Via parser_profile_verifications | Catalog-local operational state | Explicit receiver-local trust; excluded from exchange |
| parsed_result_inputs | retained | parsed_result_uuidv4, input_ordinal | repository_uuidv4, source_registration_uuidv4, parsed_result_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Exact original-input references for retained immutable interpretations |
| parsed_result_publications | retained | parsed_result_uuidv4 | parsed_result_uuidv4 | Retained immutable evidence / relation | Seals retained immutable outputs; current resources excluded |
| parsed_results | retained | parsed_result_uuidv4 | repository_uuidv4, source_registration_uuidv4, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained immutable interpretations of unaffected domain input families |
| parser_profile_capabilities | retained | parser_profile_uuidv4, owner_kind, fact_kind | Via parser_profiles | Retained immutable evidence / relation | Exact immutable declared capability manifest including current resource kinds |
| parser_profile_selection_decisions | retained | selection_decision_uuidv4 | Via parser_profile_capabilities, parser_profile_selection_scopes, parser_profile_verifications | Retained immutable evidence / relation | Retained explicit profile selection decision history |
| parser_profile_selection_predecessors | retained | selection_decision_uuidv4, predecessor_decision_uuidv4 | Via parser_profile_selection_decisions | Retained immutable evidence / relation | Exact immutable profile decision predecessor relations |
| parser_profile_selection_publications | retained | selection_decision_uuidv4 | Via parser_profile_selection_decisions | Retained immutable evidence / relation | Seals exact profile decision predecessors |
| parser_profile_selection_scopes | retained | selection_scope_uuidv4 | repository_uuidv4, change_request_id, source_registration_uuidv4 | Typed identity / context | Typed owner/fact-kind profile scopes and inheritance barriers |
| parser_profile_selection_staging | retained | selection_decision_uuidv4 | Catalog-local / shared natural identity | Bounded pending intake | Existing pending missing profile decision dependencies |
| parser_profile_verification_invalidations | retained | invalidation_uuidv4 | Via parser_profile_verifications | Retained immutable evidence / relation | Immutable revocation of exact verification run |
| parser_profile_verifications | retained | parser_profile_verification_uuidv4 | Via parser_profiles | Retained immutable evidence / relation | Immutable full-profile evidence bound to exact definition |
| parser_profiles | retained | parser_profile_uuidv4 | Catalog-local / shared natural identity | Retained immutable evidence / relation | Immutable implementation/settings/schema/capability definition |
| payload_admission_staging | retained | stage_uuidv4 | Catalog-local / shared natural identity | Bounded pending intake | Existing pending exact payload admission dependencies |
| payload_quarantine | retained | sha256 | Via stored_bytes, unresolved_payloads | Catalog-local operational state | Active physical byte quarantine; required verified-copy CAS-41 count |
| payloads | retained | representation, sha256 | Via stored_bytes | Immutable durable identity/bytes | Representation-specific retained exact input identity |
| preservation_obligations | retained | git_acquisition_id | git_acquisition_id | Catalog-local operational state | Local policy state protecting still-required durable bytes |
| ref_observations | retained | snapshot_id, raw_ref_name | repository_uuidv4, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained captured Git ref name/OID observations |
| repositories | retained | repository_uuidv4 | repository_uuidv4 | Typed identity / context | Stable repository identity and local registration |
| repository_bindings | retained | repository_binding_id | repository_uuidv4, service_instance_uuidv4 | Typed identity / context | Typed repository-to-provider identity mapping |
| repository_endpoints | retained | repository_endpoint_id | repository_uuidv4 | Typed identity / context | Retained/local endpoint identity for acquisition and context |
| repository_inventory_observations | retained | repository_inventory_observation_uuidv4 | repository_uuidv4, source_registration_uuidv4, parsed_result_uuidv4 | Retained immutable evidence / relation | Source-owned repository inventory interpretation |
| repository_name_observations | retained | repository_name_observation_uuidv4 | repository_uuidv4, parsed_result_uuidv4 | Retained immutable evidence / relation | Immutable source-derived names without repository row merging |
| repository_object_sources | retained | repository_uuidv4, git_object_id, git_acquisition_id | repository_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Exact retained Git object acquisition membership |
| resume_cursors | retained | resume_scope_id | Via incremental_scans, resume_scopes | Catalog-local operational state | Local safe retry cursor and checkpoint |
| resume_scopes | retained | resume_scope_id | repository_uuidv4 | Typed identity / context | Typed source/binding/principal/API/parser/preservation request scope |
| review_comments | removed | change_request_id, kind, provider_change_request_document_id | change_request_id | Removed type marker | Removed redundant marker; typed review_resources row replaces marker and review history |
| review_resources | added | change_request_id, kind, provider_change_request_document_id | repository_uuidv4, change_request_id, service_instance_uuidv4 | Mutable accepted state | One accepted mutable row per CR/kind/provider document ID with typed thread/review/reply/code links |
| review_thread_observations | retained | thread_observation_uuidv4 | repository_uuidv4, change_request_id, parsed_result_uuidv4 | Retained immutable evidence / relation | Retained immutable thread state, root original input and contextual code linkage |
| review_threads | retained | change_request_id, provider_resource_id | change_request_id | Typed identity / context | Retained typed review thread identity and parent CR |
| reviews | removed | change_request_id, kind, provider_change_request_document_id | change_request_id | Removed type marker | Removed redundant marker; typed review_resources row replaces marker and review history |
| root_manifest_entries | retained | git_fact_uuidv4 | repository_uuidv4, parsed_result_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Retained result-owned Git root traversal entries |
| root_manifests | retained | git_fact_uuidv4 | repository_uuidv4, parsed_result_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Retained result-owned Git root interpretation |
| root_origins | retained | root_origin_id | repository_uuidv4, change_request_id | Retained immutable evidence / relation | Captured Git traversal provenance from ref or frozen PR code context |
| search_documents | changed | search_document_id | Catalog-local / shared natural identity | Rebuildable derived data | Replaceable text search projection; superseded current bodies removed from index |
| service_instances | retained | service_instance_uuidv4 | service_instance_uuidv4 | Typed identity / context | Stable provider service identity shared by resource natural keys |
| snapshots | retained | snapshot_id | repository_uuidv4, parsed_result_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Retained Git ref snapshot publication |
| source_input_observations | retained | source_input_uuidv4 | source_registration_uuidv4 | Retained immutable evidence / relation | Immutable source original input acquisition context |
| source_repositories | retained | source_id, repository_uuidv4 | repository_uuidv4 | Typed identity / context | Source-to-repository registration membership |
| sources | retained | source_id | service_instance_uuidv4, source_registration_uuidv4 | Typed identity / context | Stable Source registration and local operational settings |
| space_reservations | retained | job_id, attempt | Via job_attempts | Catalog-local operational state | Local bounded space coordination |
| stored_bytes | retained | sha256 | Catalog-local / shared natural identity | Immutable durable identity/bytes | Verified physical exact byte store; no optional archive content dependency |
| tag_objects | retained | git_fact_uuidv4 | repository_uuidv4, parsed_result_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Retained result-owned annotated tag interpretation |
| text_bodies | retained | text_body_id | Catalog-local / shared natural identity | Immutable durable identity/bytes | Shared exact UTF-8 text identity; resource state ownership separate from sharing |
| tree_entries | retained | git_fact_uuidv4 | repository_uuidv4, parsed_result_uuidv4, git_acquisition_id | Retained immutable evidence / relation | Retained result-owned Git tree structure |
| unresolved_payloads | retained | unresolved_payload_id | Via payloads, stored_bytes | Retained immutable evidence / relation | Diagnostics for still-required historical original input interpretation failures |
| validators | retained | resume_scope_id, validator_key | Via payloads, resume_scopes | Catalog-local operational state | Local conditional HTTP validators; not portable completeness proof |

## Table changes

Added: `current_collection_pages`, `issue_resources`, `review_resources`.
Removed: `review_comments`, `reviews`.
Changed: `database_identity`, `document_observations`, `documents`, `index_generations`, `search_documents`.

## View changes

Added: `current_resource_diagnostics`, `eligible_issue_resources`, `eligible_review_resources`.
Removed: none.
Changed: none.

## Trigger changes

Added: `current_collection_completion_valid`, `current_collection_pages_immutable`, `current_collection_pages_no_replace`, `current_collection_pages_not_after_terminal`, `current_collection_pages_profile_capability`, `current_collection_pages_retain`, `issue_resources_identity`, `issue_resources_no_replace`, `issue_resources_owner_insert`, `issue_resources_owner_update`, `issue_resources_profile_update`, `issue_resources_retain`, `issue_resources_scope_insert`, `issue_resources_scope_update`, `issue_resources_transfer_children`, `json_current_collection_pages_members_insert`, `json_current_collection_pages_members_update`, `json_issue_resources_acquisition_scope_json_insert`, `json_issue_resources_acquisition_scope_json_update`, `json_review_resources_acquisition_scope_json_insert`, `json_review_resources_acquisition_scope_json_update`, `review_resources_child_thread_update`, `review_resources_identity`, `review_resources_no_replace`, `review_resources_owner_insert`, `review_resources_owner_update`, `review_resources_profile_update`, `review_resources_reply_cycle_insert`, `review_resources_reply_cycle_update`, `review_resources_retain`, `review_resources_scope_insert`, `review_resources_scope_update`.
Removed: `review_comments_immutable`, `review_comments_no_replace`, `review_comments_retain`, `reviews_immutable`, `reviews_no_replace`, `reviews_retain`.
Changed: `json_completion_markers_evidence_insert`, `json_completion_markers_evidence_update`.

## Index changes

Added: `current_collection_pages_profile`, `issue_resources_current_number`, `issue_resources_parent`, `issue_resources_repository`, `review_resources_reply`, `review_resources_repository`, `review_resources_review`, `review_resources_thread`.
Removed: none.
Changed: none.
