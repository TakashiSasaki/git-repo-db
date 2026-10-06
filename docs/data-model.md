# Catalog3 data model

The active DDL is [the packaged catalog3 schema](../src/repo_catalog/resources/catalog3.sql). [Runtime identity](../src/repo_catalog/adapters/sqlite/schema.py) is `repo-catalog/catalog3`, schema version **5**, with a SHA-256 of that DDL. Fresh catalogs initialize directly from it. Earlier catalog3 development databases are rejected; there is no migration or compatibility view. The packaged v2 schema describes salvage input only.

## Identifier convention

Named surrogate primary keys use `<entity>_id`; this is not a requirement to introduce a surrogate for every entity. Documents have a composite natural key, and service namespaces explicitly use `service_instance_uuidv4`. A neutral foreign key uses exactly the referenced identifier's name, including every owner component of a composite FK. Roles use `<role>_<entity>_id`, for example `current_snapshot_id`, `preferred_repository_endpoint_id`, `current_change_request_observation_id`, `current_document_observation_id`, and `parent_git_object_id`.

```sql
SELECT d.change_request_id, d.kind, d.provider_change_request_document_id,
       o.document_observation_id, lower(hex(o.text_body_sha256)) AS text_body_sha256,
       body.body, o.observed_at
FROM documents d
JOIN document_observations o
  ON o.document_observation_id = d.current_document_observation_id
 AND o.change_request_id = d.change_request_id
 AND o.kind = d.kind
 AND o.provider_change_request_document_id = d.provider_change_request_document_id
JOIN text_bodies body ON body.sha256 = o.text_body_sha256;
```

Namespaces stay distinct: `source_id` identifies acquisition/discovery sources; `conversion_source_id` identifies archived import provenance. `resume_scope_id` describes request/restart context; `coverage_scope_id` describes completeness. `cache_locator_id` identifies a storage location; `active_cache_entry_id` identifies a managed runtime generation. `documents` has no catalog-local document ID or serialized replacement ID. `search_document_id` identifies a disposable search input, not a document entity.

`database_identity.singleton` selects the one identity row, not an entity. Composite association/progress keys retain entity IDs plus scalar ordinals, roles or names. `job_attempts.attempt` and `jobs.current_attempt` are attempt ordinals. `number` is a provider request number scoped by binding and request kind. `index_generations.target_max_search_document_id` is a fixed build cutoff, not a foreign key. `search_documents.source_key` is a derived text key interpreted by search kind (content row, Git object row or text-body SHA-256).

## Identity and acquisition

| Tables | Meaning and relationships |
| --- | --- |
| `service_instances`, `sources` | Service identity and explicit discovery configuration; sources reference `service_instance_uuidv4`. |
| `repositories`, `repository_bindings`, `repository_endpoints` | Repository identity is independent of provider IDs and URLs. Bindings uniquely scope `provider_repository_id` by `service_instance_uuidv4`; endpoints belong to a `repository_id`. |
| `source_repositories`, `repository_name_assertions`, `inventory_observations` | Source membership, observed names and inventory coverage/history. |
| `git_acquisitions`, `snapshots`, `acquisition_roots`, `root_origins`, `ref_observations` | Acquisition records endpoint/source/context. Published snapshots and roots share the same repository owner. Shared traversal roots retain separate raw ref and PR-role origins. |
| `jobs`, `job_attempts`, `acquisition_progress`, `collection_progress`, `space_reservations` | Runtime work, attempt fencing, atomic progress and capacity reservations. |

Current pointers and composite FKs enforce same-owner relationships. Publication checks require suitable facts; current selection also respects justified observation ordering. Repository IDs are internal UUIDs for fresh registrations; imported source identifiers remain preserved. Native `provider_repository_id`, `provider_change_request_document_id`, `provider_event_id` and `provider_node_id` are service identifiers, not catalog row IDs. Raw provider payload keys remain unchanged.

## Portable identity decisions

`service_instance_uuidv4` is a portable namespace generated with `uuid.uuid4()` from a cryptographically secure random source. The DDL accepts canonical lowercase RFC UUIDv4 text with the RFC variant; UUIDv5, other versions and arbitrary strings are rejected. Validation can establish representation/version/variant, not prove the entropy source of an imported UUID. Salvage preserves valid source UUIDv4 values and archives/rejects invalid service identity rather than fabricating a replacement.

A repository with a native provider ID has portable identity `(service_instance_uuidv4, provider_repository_id)`. Distinct namespaces are never merged merely because web/API URLs match. URLs remain locators/attributes, not identity keys. Independently registered copies of the same real service may deliberately remain distinct. Conflicting assertions under a reused identity require diagnostics, not silent replacement. A binding without a provider ID has no such portable repository key.

`service_kind` retains the existing closed enumeration (`github`, `gitlab`, `gitea`, `forgejo`, `gitolite`, `git`, `other`). Open-ended provider types and additional collectors remain deferred. Provider-originated ID values and raw payload keys are preserved; a value is not necessarily a globally unique identity by itself. In particular, the same PR's title/body reuse a provider ID and are separated by document `kind`.

These decisions constrain the current model and future exchange. A multi-catalog export/import protocol, cross-catalog reconciliation and a separate portable schema are **not implemented**. Backup/restore continues to copy local row IDs; it is not semantic import/remapping.

## Git structure and content

`git_objects.git_object_id` is a catalog integer. `(object_format, oid)` identifies a Git object: `oid` is full-length BLOB bytes (20 for SHA-1, 32 for SHA-256). Role OIDs such as `head_oid`, `base_oid`, `target_oid` and `child_oid` also contain Git bytes, never catalog IDs.

`commits.git_object_id`, `tag_objects.git_object_id` and `blob_content_map.git_object_id` reuse their owning object's identifier. `commits.tree_git_object_id`, `commit_parents.commit_git_object_id` / `parent_git_object_id`, `tree_entries.tree_git_object_id` / `child_git_object_id` and `tag_objects.target_git_object_id` make target roles explicit. Ordered parents, raw headers/messages, raw tree names, paths and refs survive acquisition/import. Gitlinks may retain only external OID bytes without a local child object.

`repository_object_sources` attributes shared objects to repository acquisitions. `contents.content_id` identifies content independently; `blob_content_map` associates it with Git blobs. `content_digests` records representation/algorithm-specific raw-content digests. A Git OID hashes a typed/length-prefixed payload; raw-content MD5/SHA-1/SHA-256 hash payload bytes alone. Candidate digest indexes do not imply identity or erase collisions.

`root_manifests` and `root_manifest_entries` share `tree_git_object_id`. Completed manifests are sealed. Historical paths are reconstructed from stored trees without materializing every commit × path. Missing bytes remain distinct from empty bytes; policy exclusions and missing bodies report partial coverage.

## Change requests, documents and API history

`change_requests` belongs to a `repository_binding_id` and `repository_id`. Published `change_request_observations` retain exact payloads, observation times and `origin_fetch_occurrence_id`. `code_observations` connects a `change_request_observation_id` to `commit_code_listing_id` and `file_code_listing_id`; `code_acquisitions` links role OIDs to `acquisition_root_id`.

`documents` is identified directly by `(change_request_id, kind, provider_change_request_document_id)`. There is no `document_id`, `change_request_document_id` or `document_versions` table. The parent change request must be resolved when interpreting the composite key across catalogs; no independent document-ID allocation is required. `reviews`, `review_comments` and `collection_memberships` use the same document key. The former `reviews.review_id` was another name for the synthetic document ID and is removed, not retained as a hidden substitute. Review threads retain their own separate `review_thread_id`.

`text_bodies.sha256` is the unique content identity: SHA-256 of exact UTF-8 bytes of `body`, with no Unicode, whitespace or newline normalization. Empty text is a valid body, not missing content. `text_body_id` remains a local integer; it is not the portable/content key. Admission computes/verifies the digest, looks up by digest and checks an existing body's exact text and byte length before reuse. Inconsistent input or same-hash/different-body is an integrity error, never a second body under that identity. SQL enforces digest uniqueness and byte length; application admission and explicit DB checks verify the hash. This rule is specific to text bodies and does not change raw `contents`/`content_digests` collision handling.

Each `document_observations` row directly references `text_body_sha256 -> text_bodies.sha256`. A→A→B→A yields four observations and two shared bodies; no version entity or inferred interval is materialized. Replaying an already-admitted source occurrence produces no additional observation and does not move current backward. Observations retain metadata and acquisition provenance. This records observed states, not edits that happened between acquisitions.

`documents.current_document_observation_id` selects a same-document observed fact, enforced by the composite FK and ownership trigger. It is not recomputed as the largest ID. If selection is unresolved, current queries report partial coverage rather than silently choosing a candidate; all stored observations remain accessible. Provider-node aliases are only resolved within the same change request and document kind, retaining the admitted natural key and original payload evidence.

`payloads` deduplicates saved API bytes, while `fetch_collections`, `fetch_occurrences` and `collection_memberships` preserve separate requests/pages/membership. `resume_scopes`, `validators`, `incremental_scans`, `resume_cursors` and `completion_markers` retain request context and safe restart boundaries. `code_listings`, `code_listing_progress`, `code_commits` and `code_file_changes` use `code_listing_id`, `fetch_collection_id` and `fetch_occurrence_id`; completion seals membership. `unresolved_payloads` retains attributable parsing gaps. Resume/replay does not create new remote observations or advance watermarks.

`coverage_scopes` and `coverage_claims` keep asserted/evaluated completeness separate from acquisition facts, with `current_coverage_claim_id` selecting the evaluated claim. Partial optional evidence remains queryable; critical identity corruption blocks finalization.

## Preservation, search and salvage

`cache_locators` distinguishes read-only source evidence from target-active storage. `active_cache_entries` owns managed generations; `cache_leases` references `active_cache_entry_id`. `content_locations` and `preservation_obligations` reference `cache_locator_id`. Recovery/GC obey preservation obligations and OS locks.

`search_documents`, `index_generations` and `index_membership` are derived search data. Membership joins on `index_generation_id` and `search_document_id`. PR search inputs use lowercase text-body SHA-256 as `source_key`, one input per body; query results still distinguish each matching observation. FTS candidates are checked against literal original text; missing indexes fall back to scans. Rebuilding derived data does not change catalog identity/publication sequence.

The one-time guarded v2 importer reads unchanged source column names and writes only the current target schema. `conversion_sources`, `conversion_runs`, `conversion_batches`, `legacy_records`, `legacy_values`, `id_mappings`, `validation_results` and `reanalysis_runs` retain exact typed source values, stable mappings, attributable diagnostics and atomic batch proofs. Source bytes/IDs/history remain archived when normalized target names or request-context keys change. Legacy document/version IDs and source body hashes remain in the typed archive. Transient legacy parser tuples never create replacement runtime document/version IDs. Target mappings use the document composite key. Legacy versions without actual observations contribute body/evidence only. A saved current-version assertion can select only a real same-document source observation of that version; the latest unambiguous recorded observation is used, timestamp ties remain unresolved, and import time/ID ordering never decide. Finalization restores only explicit suitable same-owner source selections; legacy jobs, leases and reservations never become active.

Reads use normal SQLite transaction snapshots with foreign keys and recursive triggers enabled. `publication_seq` fences paginated results; restore issues a new database instance and clears operational state. Backup preserves the catalog and its evidence, excluding Git cache contents. See [operations](operations.md) and [runtime handoff](schema-hardening/runtime-handoff.md). Historical files under `docs/schema-hardening/` describe earlier design/evidence states and are not the active DDL.
