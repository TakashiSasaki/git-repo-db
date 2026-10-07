# Catalog3 data model

The active DDL is [the packaged catalog3 schema](../src/repo_catalog/resources/catalog3.sql). [Runtime identity](../src/repo_catalog/adapters/sqlite/schema.py) is `repo-catalog/catalog3`, schema version **9**, with a SHA-256 of that DDL. Fresh catalogs initialize directly from it. Earlier catalog3 development databases are rejected; there is no migration or compatibility view. The packaged v2 schema describes salvage input only.

## Absolute timestamps and durations

All normalized persisted absolute times use signed 64-bit `INTEGER` microseconds since `1970-01-01T00:00:00Z`. Every such column has an `_us` suffix, including `observed_at_us`, `parsed_at_us`, `created_at_us`, `first_seen_us`, `last_seen_us`, `safe_watermark_us`, `not_before_us` and `last_used_us`. The ordinary catalog and the import workspace (schema 2) share this convention. Normalized CLI fields and durable operational JSON use the same names and integer units. `0` and negative timestamps are valid; `NULL` represents unknown time where the entity permits it.

The [time boundary helpers](../src/repo_catalog/domain/time.py) obtain current time with `time_ns() // 1000` and convert aware datetimes with integer arithmetic. Dates without a timezone are rejected. ISO inputs with nonzero sub-microsecond digits are rejected instead of silently collapsing distinct instants; extra zero digits in the timestamp fraction are accepted. Fractional-second UTC offsets are rejected in hour-only, compact and colon-separated forms because the Python parser can collapse some such offsets to UTC. NUL characters are invalid anywhere in a timestamp. External Unix seconds convert using decimal arithmetic, flooring sub-microsecond parts. Internal integer inputs reject booleans, floats and strings and must fit signed 64-bit range. SQLite STRICT tables ensure integer storage; application admission validates external input types.

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

## Coverage claims and current state

`coverage_scopes` identifies one repository or change-request component by its owner and `kind`. Partial unique indexes enforce one scope per `(repository_id, kind)` for repository scopes and per `(change_request_id, kind)` for change-request scopes; the latter retains same-repository ownership. A scope has no current-claim pointer.

Writer calls identify the repository explicitly and optionally name a change request belonging to it. A local repository ID may equal another repository's change-request ID; ID equality never selects an owner type. Claim IDs may be negative. Automatic allocation after an explicit negative ID retains the same immutable admission rules.

`coverage_claims` contains exactly these fields:

| Field | Contract |
| --- | --- |
| `coverage_claim_id` | Catalog-local integer primary key. |
| `coverage_scope_id` | Required reference to the evaluated scope. |
| `coverage_state` | One of `complete`, `partial`, `unknown`, `not_applicable`. |
| `observed_at_us` | Required signed 64-bit integer Unix microseconds. Epoch 0 and negative instants are valid. |
| `details_json` | Optional JSON object stored as text; `NULL` means no advisory details. |

Claim identity is `(coverage_scope_id, observed_at_us, coverage_state)`, with a matching `UNIQUE` constraint. Advisory details do not affect identity, admission, ordering or state derivation. A claim does not need a provider payload, evidence row or details object to be valid. The coverage model has no separate asserted/effective states, evaluation timestamp, correction, retraction or invalidation operation. Other acquisition/progress entities retain their own state fields.

The `current_coverage` view first selects **all claims at the maximum observation time for each scope**, including `unknown`. It then derives one state from that set:

| States at the latest observation time | Derived state |
| --- | --- |
| `unknown` only | `unknown` |
| One distinct state other than `unknown`, optionally with `unknown` | That state |
| Two or more distinct states other than `unknown`, optionally with `unknown` | `conflict` |
| No claims in the scope | `unknown`, with `observed_at_us = NULL` and no synthetic claim |

`not_applicable` participates as a determinate state. `conflict` is derived and cannot be stored as a claim. A newer `unknown` therefore supersedes an older `complete`; a latest conflict never falls back to an older unambiguous result. The view also exposes `claim_count`. It selects no arbitrary winning row and combines no details.

[Domain helpers](../src/repo_catalog/domain/coverage.py) express latest selection, derivation and admission. [SQLite admission](../src/repo_catalog/adapters/sqlite/coverage.py) performs the stale/duplicate checks and insertion in one atomic statement. An incoming observation older than the existing maximum is a NO-OP. The same time and state is also a NO-OP, preserving the original details exactly. A different state at the same time is retained alongside existing claims; a newer observation is appended without deleting history. Scope creation shares the writer transaction. Constraints and retention triggers reject direct replacement, mutation or deletion of existing claims.

`export_current_claims` returns the whole maximum-time set, retaining `unknown`, conflict constituents and each claim's separate raw `details_json` or `NULL`. This implements selection policy only: local IDs still require explicit destination scope resolution, and a multi-catalog wire format and import workflow remain deferred. CLI `coverage`, `status` and snapshot results expose the derived scope and its `claims` list using one SQLite snapshot. PR queries use the same current view so historical incomplete claims do not poison a newer complete result.

Runtime producers use the original observation being evaluated. Git repository-wide claims use the fixed refs observation and are emitted only by repository Git collection, not PR-only roots. REST claims use actual saved page times; thread completion includes nested GraphQL page times. Replaying a committed terminal page or resuming an older fixed root does not acquire the resume time. A job start, local failure or failure before any response does not itself create a coverage claim; incomplete observed prefixes can produce `partial`. Job/collection progress remains separately queryable. Partial optional evidence remains queryable, while critical identity corruption blocks finalization.

PR code observations are finalized after acquisition, with their exact required role links and coverage claim published atomically. Complete code requires stable API head/base, complete context-proven lists, resolved target enumeration and preserved matching Git roots. Partial GraphQL responses retain any valid merge targets without treating an incomplete target set as complete. A failed refresh may reuse previously preserved exact roots; an unobserved transport failure alone does not create a new partial claim. Rechecking the same saved PR observation without new incomplete evidence does not append a partial code observation over matching complete code; new observations and actual Git/API races still require their own assessment.

Query completeness also accounts for structural gaps in the requested saved data. A new current PR observation without its required code observation, or a purportedly complete code observation lacking required published role links, is reported as incomplete without modifying claims. PR queries evaluate these gaps and semantic coverage for the requested identity scope within one read transaction, before pagination. Document-only queries exclude code-only collection/claim kinds; commit or path constraints require code coverage. Page size, byte cutoff and cursor position do not change this assessment. Content filters remain conservative where missing saved information could itself match the filter.

Imported listing reuse records the original authenticated detail/304 boundary, including its marker, PR observation and time. Reusing the same boundary does not append another completion marker. A 304 replay resolves its saved authorized observation even after the current PR pointer advances. GraphQL connection completion requires explicit nodes and valid pagination fields; malformed root or nested pages retain their response and retry boundary and remain partial. Error-only rate-limit responses retain raw evidence and the retry cursor as operational state; they do not advance semantic observation times or create new incomplete content claims. Saved prefixes retain their original times, and jobs honor the recorded retry deadline.

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
