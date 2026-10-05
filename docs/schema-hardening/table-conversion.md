# v2テーブル変換対応（機械契約から生成）

正本: conversion-contract.json。全旧値はlegacy_records/legacy_valuesにも型・key・exact bytes付きで保持する。converterは未実装。

| v2 table | target producers | archive-only columns |
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
| git_objects | git_objects | none |
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
