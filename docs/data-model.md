# Catalog3 data model

The active DDL is [the packaged catalog3 schema](../src/repo_catalog/resources/catalog3.sql). [Runtime identity](../src/repo_catalog/adapters/sqlite/schema.py) is `repo-catalog/catalog3`, schema version **4**, with a SHA-256 of that DDL. Fresh catalogs initialize directly from it. Earlier catalog3 development databases are rejected; there is no migration or compatibility view. The packaged v2 schema describes salvage input only.

## Identifier convention

Entity primary keys use `<entity>_id`. A neutral foreign key uses exactly the referenced identifier's name, including every owner component of a composite FK. Roles use `<role>_<entity>_id`, for example `current_snapshot_id`, `preferred_repository_endpoint_id`, `current_change_request_observation_id`, `current_document_version_id`, and `parent_git_object_id`.

```sql
SELECT r.repository_id, b.repository_binding_id, cr.change_request_id,
       d.document_id, v.document_version_id, body.body
FROM repositories r
JOIN repository_bindings b ON b.repository_id = r.repository_id
JOIN change_requests cr ON cr.repository_binding_id = b.repository_binding_id
JOIN documents d ON d.change_request_id = cr.change_request_id
JOIN document_versions v ON v.document_id = d.document_id
JOIN text_bodies body ON body.text_body_id = v.text_body_id;
```

Namespaces stay distinct: `source_id` identifies acquisition/discovery sources; `conversion_source_id` identifies archived import provenance. `resume_scope_id` describes request/restart context; `coverage_scope_id` describes completeness. `cache_locator_id` identifies a storage location; `active_cache_entry_id` identifies a managed runtime generation. `document_id` identifies a PR document; `search_document_id` identifies a disposable search input.

`database_identity.singleton` selects the one identity row, not an entity. Composite association/progress keys retain entity IDs plus scalar ordinals, roles or names. `job_attempts.attempt` and `jobs.current_attempt` are attempt ordinals. `number` is a provider request number scoped by binding and request kind. `index_generations.target_max_search_document_id` is a fixed build cutoff, not a foreign key. `search_documents.source_key` is a derived text key interpreted by search kind (content, Git object or document version).

## Identity and acquisition

| Tables | Meaning and relationships |
| --- | --- |
| `service_instances`, `sources` | Service identity and explicit discovery configuration; sources reference `service_instance_id`. |
| `repositories`, `repository_bindings`, `repository_endpoints` | Repository identity is independent of provider IDs and URLs. Bindings uniquely scope `provider_repository_id` by `service_instance_id`; endpoints belong to a `repository_id`. |
| `source_repositories`, `repository_name_assertions`, `inventory_observations` | Source membership, observed names and inventory coverage/history. |
| `git_acquisitions`, `snapshots`, `acquisition_roots`, `root_origins`, `ref_observations` | Acquisition records endpoint/source/context. Published snapshots and roots share the same repository owner. Shared traversal roots retain separate raw ref and PR-role origins. |
| `jobs`, `job_attempts`, `acquisition_progress`, `collection_progress`, `space_reservations` | Runtime work, attempt fencing, atomic progress and capacity reservations. |

Current pointers and composite FKs enforce same-owner relationships. Publication checks require suitable facts; current selection also respects justified observation ordering. Repository IDs are internal UUIDs for fresh registrations; imported source identifiers remain preserved. Native `provider_repository_id`, `provider_document_id`, `provider_event_id` and `provider_node_id` are service identifiers, not catalog row IDs. Raw provider payload keys remain unchanged.

## Git structure and content

`git_objects.git_object_id` is a catalog integer. `(object_format, oid)` identifies a Git object: `oid` is full-length BLOB bytes (20 for SHA-1, 32 for SHA-256). Role OIDs such as `head_oid`, `base_oid`, `target_oid` and `child_oid` also contain Git bytes, never catalog IDs.

`commits.git_object_id`, `tag_objects.git_object_id` and `blob_content_map.git_object_id` reuse their owning object's identifier. `commits.tree_git_object_id`, `commit_parents.commit_git_object_id` / `parent_git_object_id`, `tree_entries.tree_git_object_id` / `child_git_object_id` and `tag_objects.target_git_object_id` make target roles explicit. Ordered parents, raw headers/messages, raw tree names, paths and refs survive acquisition/import. Gitlinks may retain only external OID bytes without a local child object.

`repository_object_sources` attributes shared objects to repository acquisitions. `contents.content_id` identifies content independently; `blob_content_map` associates it with Git blobs. `content_digests` records representation/algorithm-specific raw-content digests. A Git OID hashes a typed/length-prefixed payload; raw-content MD5/SHA-1/SHA-256 hash payload bytes alone. Candidate digest indexes do not imply identity or erase collisions.

`root_manifests` and `root_manifest_entries` share `tree_git_object_id`. Completed manifests are sealed. Historical paths are reconstructed from stored trees without materializing every commit × path. Missing bytes remain distinct from empty bytes; policy exclusions and missing bodies report partial coverage.

## Change requests, documents and API history

`change_requests` belongs to a `repository_binding_id` and `repository_id`. Published `change_request_observations` retain exact payloads, observation times and `origin_fetch_occurrence_id`. `code_observations` connects a `change_request_observation_id` to `commit_code_listing_id` and `file_code_listing_id`; `code_acquisitions` links role OIDs to `acquisition_root_id`.

`documents` owns `document_versions`; each version references `text_body_id`. `document_observations` records distinct occurrences of a `document_version_id`. Shared bodies/versions preserve A→B→A observations. `reviews`, `review_threads`, `review_comments` and `change_request_events` retain provider history and same-request relationships; comments use `review_thread_id`.

`payloads` deduplicates saved API bytes, while `fetch_collections`, `fetch_occurrences` and `collection_memberships` preserve separate requests/pages/membership. `resume_scopes`, `validators`, `incremental_scans`, `resume_cursors` and `completion_markers` retain request context and safe restart boundaries. `code_listings`, `code_listing_progress`, `code_commits` and `code_file_changes` use `code_listing_id`, `fetch_collection_id` and `fetch_occurrence_id`; completion seals membership. `unresolved_payloads` retains attributable parsing gaps. Resume/replay does not create new remote observations or advance watermarks.

`coverage_scopes` and `coverage_claims` keep asserted/evaluated completeness separate from acquisition facts, with `current_coverage_claim_id` selecting the evaluated claim. Partial optional evidence remains queryable; critical identity corruption blocks finalization.

## Preservation, search and salvage

`cache_locators` distinguishes read-only source evidence from target-active storage. `active_cache_entries` owns managed generations; `cache_leases` references `active_cache_entry_id`. `content_locations` and `preservation_obligations` reference `cache_locator_id`. Recovery/GC obey preservation obligations and OS locks.

`search_documents`, `index_generations` and `index_membership` are derived search data. Membership joins on `index_generation_id` and `search_document_id`. FTS candidates are checked against literal original text; missing indexes fall back to scans. Rebuilding derived data does not change catalog identity/publication sequence.

The one-time guarded v2 importer reads unchanged source column names and writes only the current target schema. `conversion_sources`, `conversion_runs`, `conversion_batches`, `legacy_records`, `legacy_values`, `id_mappings`, `validation_results` and `reanalysis_runs` retain exact typed source values, stable mappings, attributable diagnostics and atomic batch proofs. Source bytes/IDs/history remain archived when normalized target names or request-context keys change. Finalization restores only explicit suitable same-owner source selections; legacy jobs, leases and reservations never become active.

Reads use normal SQLite transaction snapshots with foreign keys and recursive triggers enabled. `publication_seq` fences paginated results; restore issues a new database instance and clears operational state. Backup preserves the catalog and its evidence, excluding Git cache contents. See [operations](operations.md) and [runtime handoff](schema-hardening/runtime-handoff.md). Historical files under `docs/schema-hardening/` describe earlier design/evidence states and are not the active DDL.
