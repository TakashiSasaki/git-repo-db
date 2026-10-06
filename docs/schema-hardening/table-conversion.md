# v2テーブル変換対応（機械契約から生成）

正本: conversion-contract.json。全旧値はlegacy_records/legacy_valuesにも型・key・exact bytes付きで保持する。P2/P3B基盤に保存済みGit/API/PRの統合変換と明示的なreadonly target queryを実装した。実行recipeと各旧tableのdispositionはp3_integratedを参照する。通常runtime切替・実データ移行は後続範囲。

| v2 table | target producers | columns without direct output (archive / recipe inputs) |
|---|---|---|
| acquisition_roots | acquisition_roots, root_origins | pr_number, observation_id |
| api_responses | payloads, unresolved_payloads | none |
| blob_content_map | blob_content_map | none |
| cache_entries | cache_locators | generation, last_used, bytes |
| cache_leases | legacy_records / legacy_values | cache_id, job_id, attempt, acquired_at |
| catalog_meta | legacy_records / legacy_values | id, db_instance_id, publication_seq, schema_version |
| collection_memberships | collection_memberships | none |
| collection_pages | fetch_occurrences | none |
| collection_runs | acquisition_progress, git_acquisitions | cache_id |
| collections | collection_progress, completion_markers, fetch_collections, resume_scopes | none |
| commit_parents | commit_parents | none |
| commits | commits | none |
| content_digests | content_digests | none |
| content_locations | content_locations | none |
| contents | contents | none |
| coverage_components | coverage_claims, coverage_scopes | none |
| document_versions | document_versions, text_bodies | none |
| git_objects | git_objects | verified |
| index_generations | legacy_records / legacy_values | id, kind, state, table_name, target_max_id, created_at |
| index_membership | legacy_records / legacy_values | generation_id, document_id, input_version |
| inventory_runs | inventory_observations | none |
| jobs | job_attempts, jobs | none |
| pr_code_observations | code_listings, code_observations | state |
| pr_commits | code_commits | ordinal |
| pr_documents | documents | none |
| pr_events | change_request_events | run_id |
| pr_file_changes | code_file_changes | ordinal |
| pr_git_links | code_acquisitions | none |
| pr_observations | change_request_observations | job_id |
| pr_reviews | reviews | none |
| preservation_obligations | preservation_obligations | none |
| pull_requests | change_requests | none |
| ref_observations | ref_observations | none |
| repositories | repositories | source_id, provider_host, provider_repo_id, url |
| repository_bindings | repository_bindings | none |
| repository_endpoints | repository_endpoints | is_preferred |
| repository_names | repository_name_assertions | none |
| repository_object_sources | repository_object_sources | none |
| resource_observations | document_observations | none |
| review_comments | review_comments | none |
| review_threads | review_threads | none |
| root_manifest_entries | root_manifest_entries | none |
| root_manifests | root_manifests | none |
| schema_migrations | legacy_records / legacy_values | version, checksum, applied_at |
| search_documents | legacy_records / legacy_values | id, kind, source_key, body, metadata |
| service_instances | service_instances | none |
| snapshots | snapshots | none |
| source_repositories | source_repositories | none |
| sources | sources | none |
| space_reservations | legacy_records / legacy_values | job_id, reserved, consumed |
| sync_checkpoints | legacy_records / legacy_values | scope, value, updated_at |
| tag_objects | tag_objects | none |
| tree_entries | tree_entries | none |

## Integrated input buffer bounds

Raw source-record byte budget: 8388608 bytes. Size: source_key bytes + row_sha256 bytes + typed column value_bytes; Python object overhead excluded.
Record limit: receipt batch_size, capped at one for single_record_recipes. Single-record recipes: saved_document_repair, saved_listing_repair, saved_pr_document_repair, sync_checkpoints.
Oversized source record: preserve in its own one-record batch; pending raw input is bounded by budget plus the largest individual source record.
Saved replay input limit: 33554432 bytes; per decoded saved page/checkpoint object; derived operation count and Python object memory are not bounded by this input limit.

## Integrated executable source dispositions

| v2 table | implemented recipes | disposition |
|---|---|---|
| acquisition_roots | acquisition_roots, unknown_root_origins | normalized; invalid/unsupported records stay attributed in the typed archive |
| api_responses | payloads | normalized; invalid/unsupported records stay attributed in the typed archive |
| blob_content_map | blob_content_map | normalized; invalid/unsupported records stay attributed in the typed archive |
| cache_entries | parent/archive | deferred operational state; exact typed archive and sealed cache evidence retained |
| cache_leases | parent/archive | deferred operational state; exact typed archive and sealed cache evidence retained |
| catalog_meta | parent/archive | archive preserved; source format/migration identity already authenticated |
| collection_memberships | collection_memberships | normalized; invalid/unsupported records stay attributed in the typed archive |
| collection_pages | fetch_occurrences, saved_document_repair, saved_listing_repair | normalized; invalid/unsupported records stay attributed in the typed archive |
| collection_runs | git_acquisitions | normalized; invalid/unsupported records stay attributed in the typed archive |
| collections | resume_scopes, fetch_collections | normalized; invalid/unsupported records stay attributed in the typed archive |
| commit_parents | commit_parents | normalized; invalid/unsupported records stay attributed in the typed archive |
| commits | commits | normalized; invalid/unsupported records stay attributed in the typed archive |
| content_digests | content_digests | normalized; invalid/unsupported records stay attributed in the typed archive |
| content_locations | parent/archive | deferred operational state; exact typed archive and sealed cache evidence retained |
| contents | contents | normalized; invalid/unsupported records stay attributed in the typed archive |
| coverage_components | parent/archive | deferred operational state; exact typed archive and sealed cache evidence retained |
| document_versions | document_versions | normalized; invalid/unsupported records stay attributed in the typed archive |
| git_objects | git_objects | normalized; invalid/unsupported records stay attributed in the typed archive |
| index_generations | parent/archive | deferred operational state; exact typed archive and sealed cache evidence retained |
| index_membership | parent/archive | deferred operational state; exact typed archive and sealed cache evidence retained |
| inventory_runs | inventory_observations | normalized; invalid/unsupported records stay attributed in the typed archive |
| jobs | jobs | normalized; invalid/unsupported records stay attributed in the typed archive |
| pr_code_observations | code_listings, code_listing_completion, code_observations | normalized; invalid/unsupported records stay attributed in the typed archive |
| pr_commits | code_commits | normalized; invalid/unsupported records stay attributed in the typed archive |
| pr_documents | documents | normalized; invalid/unsupported records stay attributed in the typed archive |
| pr_events | change_request_events | normalized; invalid/unsupported records stay attributed in the typed archive |
| pr_file_changes | code_file_changes | normalized; invalid/unsupported records stay attributed in the typed archive |
| pr_git_links | code_acquisitions, pr_root_origins | normalized; invalid/unsupported records stay attributed in the typed archive |
| pr_observations | change_request_observations, saved_pr_document_repair | normalized; invalid/unsupported records stay attributed in the typed archive |
| pr_reviews | reviews | normalized; invalid/unsupported records stay attributed in the typed archive |
| preservation_obligations | parent/archive | deferred operational state; exact typed archive and sealed cache evidence retained |
| pull_requests | change_requests | normalized; invalid/unsupported records stay attributed in the typed archive |
| ref_observations | ref_observations, ref_root_origins | normalized; invalid/unsupported records stay attributed in the typed archive |
| repositories | parent/archive | normalized; invalid/unsupported records stay attributed in the typed archive |
| repository_bindings | parent/archive | normalized; invalid/unsupported records stay attributed in the typed archive |
| repository_endpoints | parent/archive | normalized; invalid/unsupported records stay attributed in the typed archive |
| repository_names | parent/archive | normalized; invalid/unsupported records stay attributed in the typed archive |
| repository_object_sources | repository_object_sources | normalized; invalid/unsupported records stay attributed in the typed archive |
| resource_observations | document_observations | normalized; invalid/unsupported records stay attributed in the typed archive |
| review_comments | review_comments | normalized; invalid/unsupported records stay attributed in the typed archive |
| review_threads | review_threads | normalized; invalid/unsupported records stay attributed in the typed archive |
| root_manifest_entries | root_manifest_entries | normalized; invalid/unsupported records stay attributed in the typed archive |
| root_manifests | root_manifests | normalized; invalid/unsupported records stay attributed in the typed archive |
| schema_migrations | parent/archive | archive preserved; source format/migration identity already authenticated |
| search_documents | parent/archive | archive preserved; derived search is replaced by original-text scan |
| service_instances | parent/archive | normalized; invalid/unsupported records stay attributed in the typed archive |
| snapshots | snapshots | normalized; invalid/unsupported records stay attributed in the typed archive |
| source_repositories | parent/archive | normalized; invalid/unsupported records stay attributed in the typed archive |
| sources | parent/archive | normalized; invalid/unsupported records stay attributed in the typed archive |
| space_reservations | parent/archive | deferred operational state; exact typed archive and sealed cache evidence retained |
| sync_checkpoints | sync_checkpoints | normalized; invalid/unsupported records stay attributed in the typed archive |
| tag_objects | tag_objects | normalized; invalid/unsupported records stay attributed in the typed archive |
| tree_entries | tree_entries | normalized; invalid/unsupported records stay attributed in the typed archive |
