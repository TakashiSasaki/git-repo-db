# Catalog3 data model

The active DDL is [the packaged catalog3 schema](../src/repo_catalog/resources/catalog3.sql). [Runtime identity](../src/repo_catalog/adapters/sqlite/schema.py) is `repo-catalog/catalog3`, schema version **8**, with a SHA-256 of that DDL. Fresh catalogs initialize directly from it. Earlier catalog3 development databases are rejected; there is no migration or compatibility view. The packaged v2 schema describes salvage input only.

## Absolute timestamps and durations

All normalized persisted absolute times use signed 64-bit `INTEGER` microseconds since `1970-01-01T00:00:00Z`. Every such column has an `_us` suffix, including `observed_at_us`, `parsed_at_us`, `created_at_us`, `first_seen_us`, `last_seen_us`, `safe_watermark_us`, `not_before_us` and `last_used_us`. The ordinary catalog and the import workspace (schema 2) share this convention. Normalized CLI fields and durable operational JSON use the same names and integer units. `0` and negative timestamps are valid; `NULL` represents unknown time where the entity permits it.

The [time boundary helpers](../src/repo_catalog/domain/time.py) obtain current time with `time_ns() // 1000` and convert aware datetimes with integer arithmetic. Dates without a timezone are rejected. ISO inputs with nonzero sub-microsecond digits are rejected instead of silently collapsing distinct instants; extra zero digits in the timestamp fraction are accepted. Fractional-second UTC offsets are rejected because the Python parser can collapse some such offsets to UTC. External Unix seconds convert using decimal arithmetic, flooring sub-microsecond parts. Internal integer inputs reject booleans, floats and strings and must fit signed 64-bit range. SQLite STRICT tables ensure integer storage; application admission validates external input types.

Comparisons, min/max aggregates, retry deadlines and cache age calculations operate on integer microseconds. Provider requests that require dates, such as GitHub `since`, explicitly format the integer boundary as UTC ISO 8601. The full int64 storage range is supported; optional calendar formatting is limited to Python datetime's year range. For example, `2026-10-07T09:00:00.123456Z` is `1791363600123456` µs.

Durations retain explicit unit names such as `timeout_seconds`, `ttl_seconds` and `busy_timeout_ms`. Process-local elapsed-time measurement continues to use a monotonic clock. These durations and monotonic values are not epoch timestamps.

Provider payloads, raw Git objects and archived v2 records preserve their original time strings, units and field names as source evidence. The v2 importer converts valid source times only when projecting normalized facts. An absent or malformed source observation does not acquire the conversion time: nullable facts retain `NULL` with conversion diagnostics where appropriate. Replay retains the original observation instant and does not advance a watermark merely because parsing ran again.

## Identifier convention

Named surrogate primary keys use `<entity>_id`; this is not a requirement to introduce a surrogate for every entity. Documents have a composite natural key, and service namespaces explicitly use `service_instance_uuidv4`. A neutral foreign key uses exactly the referenced identifier's name, including every owner component of a composite FK. Roles use `<role>_<entity>_id`, for example `current_snapshot_id`, `preferred_repository_endpoint_id`, `current_change_request_observation_id`, `current_document_observation_id`, and `parent_git_object_id`.

```sql
SELECT d.change_request_id, d.kind, d.provider_change_request_document_id,
       o.document_observation_id, lower(hex(o.text_body_sha256)) AS text_body_sha256,
       body.body, o.observed_at_us
FROM documents d
JOIN document_observations o
  ON o.document_observation_id = d.current_document_observation_id
 AND o.change_request_id = d.change_request_id
 AND o.kind = d.kind
 AND o.provider_change_request_document_id = d.provider_change_request_document_id
JOIN text_bodies body ON body.sha256 = o.text_body_sha256;
```

Namespaces stay distinct: `source_id` identifies acquisition/discovery sources; `conversion_source_id` identifies import provenance only inside the separate workspace. `resume_scope_id` describes request/restart context; `coverage_scope_id` describes completeness. `cache_locator_id` identifies a storage location; `active_cache_entry_id` identifies a managed runtime generation. `documents` has no catalog-local document ID or serialized replacement ID. `search_document_id` identifies a disposable search input, not a document entity.

`database_identity.singleton` selects the one identity row, not an entity. Composite association/progress keys retain entity IDs plus scalar ordinals, roles or names. `job_attempts.attempt` and `jobs.current_attempt` are attempt ordinals. `provider_change_request_number` is a provider request number scoped by binding and `change_request_kind`. `index_generations.target_max_search_document_id` is a fixed build cutoff, not a foreign key. `search_documents.source_key` is a derived text key interpreted by search kind (content row, Git object row or text-body SHA-256).

## Identity and acquisition

| Tables | Meaning and relationships |
| --- | --- |
| `service_instances`, `sources` | Service identity and explicit discovery configuration; sources reference `service_instance_uuidv4`. |
| `repositories`, `repository_bindings`, `repository_endpoints` | Repository identity is independent of provider IDs and URLs. Bindings uniquely scope `provider_repository_id` by `service_instance_uuidv4`; endpoints belong to a `repository_id`. |
| `source_repositories`, `repository_name_assertions`, `inventory_observations` | Source membership, observed names and inventory coverage/history. |
| `git_acquisitions`, `snapshots`, `acquisition_roots`, `root_origins`, `ref_observations` | Acquisition records endpoint/source/context. Published snapshots and roots share the same repository owner. Shared traversal roots retain separate raw ref and PR-role origins. |
| `jobs`, `job_attempts`, `acquisition_progress`, `collection_progress`, `space_reservations` | Runtime work, attempt fencing, atomic progress and capacity reservations. |

Current pointers and composite FKs enforce same-owner relationships. Publication checks require suitable facts; current selection also respects justified observation ordering. Repository IDs are internal UUIDs for fresh registrations; imported source identifiers remain preserved. Native `provider_repository_id`, `provider_change_request_document_id`, `provider_resource_id` and `provider_event_id` are provider-originated identifiers, not catalog row IDs. Provider-specific Node IDs remain in raw payload evidence but are not modeled as a generic normalized `provider_node_id` column.

## Portable identity decisions

`service_instance_uuidv4` is a portable namespace generated with `uuid.uuid4()` from a cryptographically secure random source. The DDL accepts canonical lowercase RFC UUIDv4 text with the RFC variant; UUIDv5, other versions and arbitrary strings are rejected. Validation can establish representation/version/variant, not prove the entropy source of an imported UUID. Salvage preserves valid source UUIDv4 values and archives/rejects invalid service identity rather than fabricating a replacement.

A repository with a native provider ID has portable identity `(service_instance_uuidv4, provider_repository_id)`. Distinct namespaces are never merged merely because web/API URLs match. URLs remain locators/attributes, not identity keys. Independently registered copies of the same real service may deliberately remain distinct. Conflicting assertions under a reused identity require diagnostics, not silent replacement. A binding without a provider ID has no such portable repository key.

`service_kind` retains the existing closed enumeration (`github`, `gitlab`, `gitea`, `forgejo`, `gitolite`, `git`, `other`). Open-ended provider types and additional collectors remain deferred. Provider-originated ID values and raw payload keys are preserved; a value is not necessarily globally unique by itself. `provider_resource_id` therefore means an opaque provider-native identifier whose required uniqueness scope is defined by the owning resource. GitHub review threads use the GraphQL node `id` as this value, but the common schema does not require every provider to offer a service-wide global ID. The same PR's title/body reuse a provider ID and are separated by document `kind`.

These decisions constrain the current model and future exchange. A multi-catalog export/import protocol, cross-catalog reconciliation and a separate portable schema are **not implemented**. Backup/restore continues to copy local row IDs; it is not semantic import/remapping.

## Git structure and content

`git_objects.git_object_id` is a catalog integer. `(object_format, oid)` identifies a Git object: `oid` is full-length BLOB bytes (20 for SHA-1, 32 for SHA-256). Role OIDs such as `head_oid`, `base_oid`, `target_oid` and `child_oid` also contain Git bytes, never catalog IDs.

`commits.git_object_id`, `tag_objects.git_object_id` and `blob_content_map.git_object_id` reuse their owning object's identifier. `commits.tree_git_object_id`, `commit_parents.commit_git_object_id` / `parent_git_object_id`, `tree_entries.tree_git_object_id` / `child_git_object_id` and `tag_objects.target_git_object_id` make target roles explicit. Ordered parents, raw headers/messages, raw tree names, paths and refs survive acquisition/import. Gitlinks may retain only external OID bytes without a local child object.

`repository_object_sources` attributes shared objects to repository acquisitions. `contents.content_id` identifies content independently; `blob_content_map` associates it with Git blobs. `content_digests` records representation/algorithm-specific raw-content digests. A Git OID hashes a typed/length-prefixed payload; raw-content MD5/SHA-1/SHA-256 hash payload bytes alone. Candidate digest indexes do not imply identity or erase collisions.

`root_manifests` and `root_manifest_entries` share `tree_git_object_id`. Completed manifests are sealed. Historical paths are reconstructed from stored trees without materializing every commit × path. Missing bytes remain distinct from empty bytes; policy exclusions and missing bodies report partial coverage.

## Change requests, documents and API history

`change_requests` belongs to a `repository_binding_id` and `repository_id`. Its portable identity is the repository portable identity plus `(change_request_kind, provider_change_request_number)`. Published `change_request_observations` retain exact payloads, observation times and `origin_fetch_occurrence_id`. `code_observations` connects a `change_request_observation_id` to `commit_code_listing_id` and `file_code_listing_id`; `code_acquisitions` links role OIDs to `acquisition_root_id`.

`documents` is identified directly by `(change_request_id, kind, provider_change_request_document_id)`. There is no `document_id`, `change_request_document_id` or `document_versions` table. The parent change request must be resolved when interpreting the composite key across catalogs; no independent document-ID allocation is required. `reviews`, `review_comments` and `collection_memberships` use the same document key. The former `reviews.review_id` was another name for the synthetic document ID and is removed, not retained as a hidden substitute. `review_threads` likewise has no synthetic `review_thread_id`; its natural key is `(change_request_id, provider_resource_id)`, and review comments reference that scoped key.

`text_bodies.sha256` is the unique content identity: SHA-256 of exact UTF-8 bytes of `body`, with no Unicode, whitespace or newline normalization. Empty text is a valid body, not missing content. `text_body_id` remains a local integer; it is not the portable/content key. Admission computes/verifies the digest, looks up by digest and checks an existing body's exact text and byte length before reuse. Inconsistent input or same-hash/different-body is an integrity error, never a second body under that identity. SQL enforces digest uniqueness and byte length; application admission and explicit DB checks verify the hash. This rule is specific to text bodies and does not change raw `contents`/`content_digests` collision handling.

Each `document_observations` row directly references `text_body_sha256 -> text_bodies.sha256`. A→A→B→A yields four observations and two shared bodies; no version entity or inferred interval is materialized. Replaying an already-admitted source occurrence produces no additional observation and does not move current backward. Observations retain metadata and acquisition provenance. This records observed states, not edits that happened between acquisitions.

`documents.current_document_observation_id` selects a same-document observed fact, enforced by the composite FK and ownership trigger. It is not recomputed as the largest ID. If selection is unresolved, current queries report partial coverage rather than silently choosing a candidate; all stored observations remain accessible. Normalized document identity does not use a secondary provider Node-ID alias; any such provider value remains in the raw payload evidence.

`payloads` deduplicates saved API bytes, while `fetch_collections`, `fetch_occurrences` and `collection_memberships` preserve separate requests/pages/membership. `resume_scopes`, `validators`, `incremental_scans`, `resume_cursors` and `completion_markers` retain request context and safe restart boundaries. `code_listings`, `code_listing_progress`, `code_commits` and `code_file_changes` use `code_listing_id`, `fetch_collection_id` and `fetch_occurrence_id`; completion seals membership. `unresolved_payloads` retains attributable parsing gaps. Resume/replay does not create new remote observations or advance watermarks.

`coverage_scopes` and `coverage_claims` keep asserted/evaluated completeness separate from acquisition facts, with `current_coverage_claim_id` selecting the evaluated claim. Partial optional evidence remains queryable; critical identity corruption blocks finalization.

## Preservation, search and salvage

`cache_locators` distinguishes read-only source evidence from target-active storage. `active_cache_entries` owns managed generations; `cache_leases` references `active_cache_entry_id`. `content_locations` and `preservation_obligations` reference `cache_locator_id`. Recovery/GC obey preservation obligations and OS locks.

`search_documents`, `index_generations` and `index_membership` are derived search data. Membership joins on `index_generation_id` and `search_document_id`. PR search inputs use lowercase text-body SHA-256 as `source_key`, one input per body; query results still distinguish each matching observation. FTS candidates are checked against literal original text; missing indexes fall back to scans. Rebuilding derived data does not change catalog identity/publication sequence.

The one-time guarded v2 importer reads unchanged source column names and writes normalized facts to the ordinary catalog. `conversion_sources`, `conversion_runs`, `conversion_batches`, `legacy_records`, `legacy_values`, `id_mappings`, `validation_results` and `reanalysis_runs` live only in the separate `import-v2/workspace.sqlite3`. Its packaged [workspace DDL](../src/repo_catalog/resources/import_v2/workspace.sql) is not a second copy of catalog DDL: each table is defined in exactly one of the two schemas. An additional workspace identity row binds scratch to the target database instance and both schema hashes.

The workspace is durable working state, not a SQLite TEMP table or an automatically disappearing OS temporary file. It retains typed source values, mappings, diagnostics and atomic batch proofs through import and finalization. A single SQLite connection attaches exactly the fixed checked workspace with both files using on-disk DELETE journals and synchronous=EXTRA. Each batch commits target rows and workspace receipts together. Cross-file foreign keys are not used: workspace-internal relations retain their own FKs, and mappings to target rows are verified by the importer within the transaction and on resume. Missing, foreign, aliased, altered or WAL workspaces fail closed.

Finalization reads workspace source assertions, restores only suitable same-owner selections, and commits catalog readiness and its workspace receipt together. Missing source observations do not invent observations; timestamp ties and unknown ordering remain unresolved. After successful finalization, ordinary reads, checks and backup/restore work without attaching or retaining workspace. The workspace may then be discarded, but the application does not automatically delete it or any original source. Failed/interrupted/unfinalized workspaces must be retained to resume. `unresolved_payloads` keeps normalized gap reasons and optional payload references but no `legacy_record_id` FK into scratch; record-level conversion attribution stays in workspace `id_mappings` and `validation_results`.

Reads use normal SQLite transaction snapshots with foreign keys and recursive triggers enabled. `publication_seq` fences paginated results; restore issues a new database instance and clears operational state. Backup preserves the ordinary catalog, excluding the import workspace and Git cache contents. A building import is not an ordinary backup: retain the paired catalog/workspace and sealed source until finalization. See [operations](operations.md) and [runtime handoff](schema-hardening/runtime-handoff.md). Historical files under `docs/schema-hardening/` describe earlier design/evidence states and are not the active DDL.

### Provider resource admission

GitHub document identities use REST `id` or GraphQL `fullDatabaseId`, represented as positive decimal text. GraphQL `id`/REST `node_id` are not a fallback document key or an alternate normalized identity. When a canonical database ID is missing, retain the raw response and an attributable partial diagnostic without admitting a Node-keyed document or advancing the page as complete. Retry the failed page on resume. Retained-v2 Node-only document identities remain archived, not fabricated into database IDs.

Review-thread `provider_resource_id` remains opaque, unparsed provider text. The common constraint is exactly `PRIMARY KEY(change_request_id, provider_resource_id)`; different change requests may contain the same resource value, even within one service namespace. `review_comments.review_thread_provider_resource_id` references that key together with its own `change_request_id`; NULL denotes an unresolved thread association. The provider value, not a synthetic parent-prefixed string, is passed to the GitHub GraphQL node query.

CLI and normalized query results use `provider_change_request_number` and `change_request_kind`. Selectors are `--provider-change-request-number` and `--change-request-kind`. Raw provider response keys (`number`, `id`, `node_id`, `fullDatabaseId`) are unchanged.
