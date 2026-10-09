# Catalog3 data model

The active DDL is the complete schema assembled by [schema.py](../src/repo_catalog/adapters/sqlite/schema.py), including [catalog3.sql](../src/repo_catalog/resources/catalog3.sql) and [current_resources.sql](../src/repo_catalog/resources/current_resources.sql). Runtime identity is `repo-catalog/catalog3`, schema version **16**, with a SHA-256 of that complete DDL. Fresh catalogs initialize directly from it. Earlier development databases are rejected; there is no migration or compatibility view. The v2 importer was retired. Current changes are documented in [boundary corrections](current-state-boundaries.md), [schema 15 closure](current-state-schema-closure.md), [column liveness](current-state-schema-liveness.md) and [complete inventory](current-state-schema-inventory.md); historical receipts do not establish schema 16 acceptance.

## Absolute timestamps and durations

All normalized persisted absolute times use signed 64-bit `INTEGER` microseconds since `1970-01-01T00:00:00Z`. Every such column has an `_us` suffix, including `observed_at_us`, `parsed_at_us`, `created_at_us`, `first_seen_us`, `last_seen_us`, `safe_watermark_us`, `not_before_us` and `last_used_us`. Normalized CLI fields and durable operational JSON use the same names and integer units. `0` and negative timestamps are valid; `NULL` represents unknown time where the entity permits it.

The [time boundary helpers](../src/repo_catalog/domain/time.py) obtain current time with `time_ns() // 1000` and convert aware datetimes with integer arithmetic. Dates without a timezone are rejected. ISO inputs with nonzero sub-microsecond digits are rejected instead of silently collapsing distinct instants; extra zero digits in the timestamp fraction are accepted. Fractional-second UTC offsets are rejected in hour-only, compact and colon-separated forms because the Python parser can collapse some such offsets to UTC. Clock fractions require complete hour/minute/second fields; fractional hours or minutes are rejected. Offset hours must be 0–23 and minutes/seconds 0–59 rather than normalized across components. NUL characters are invalid anywhere in a timestamp. External Unix seconds convert using decimal arithmetic, flooring sub-microsecond parts. Internal integer inputs reject booleans, floats and strings and must fit signed 64-bit range. SQLite STRICT tables ensure integer storage; application admission validates external input types.

Comparisons, min/max aggregates, retry deadlines and cache age calculations operate on integer microseconds. Provider requests that require dates, such as GitHub `since`, explicitly format the integer boundary as UTC ISO 8601. The full int64 storage range is supported; optional calendar formatting is limited to Python datetime's year range. For example, `2026-10-07T09:00:00.123456Z` is `1791363600123456` µs.

Durations retain explicit unit names such as `timeout_seconds`, `ttl_seconds` and `busy_timeout_ms`. Process-local elapsed-time measurement continues to use a monotonic clock. These durations and monotonic values are not epoch timestamps.

Provider evidence and raw Git objects preserve their original time strings, units and field names. Missing provider update times remain unknown and do not become parsing time. Replay retains the original observation instant and does not advance a watermark merely because parsing ran again. Current resources distinguish provider update time, accepted observation time, live confirmation time and parsing time.

## Identifier convention

Named surrogate primary keys use `<entity>_id`; this is not a requirement to introduce a surrogate for every entity. Documents have a composite natural key, and service namespaces explicitly use `service_instance_uuidv4`. A neutral foreign key uses exactly the referenced identifier's name, including every owner component of a composite FK. Roles use `<role>_<entity>_id`, for example `preferred_repository_endpoint_id` and `parent_git_object_id`. Current historical selections come from views and immutable selection DAGs; obsolete current-pointer columns are absent from repository, change-request and document identity tables.

```sql
SELECT d.change_request_id, d.kind, d.provider_change_request_document_id,
       o.document_observation_id, lower(hex(o.text_body_sha256)) AS text_body_sha256,
       body.body, o.observed_at_us
FROM documents d
JOIN current_document_observations o
  ON o.change_request_id = d.change_request_id
 AND o.kind = d.kind
 AND o.provider_change_request_document_id = d.provider_change_request_document_id
JOIN text_bodies body ON body.sha256 = o.text_body_sha256;
```

Namespaces stay distinct: `source_id` is a catalog-local acquisition/discovery handle; `source_registration_uuidv4` is a separate immutable CSPRNG UUIDv4 preserved by backup/restore and exchange. `resume_scope_id` describes request/restart context; `coverage_scope_id` describes completeness. `cache_locator_id` identifies a storage location; `active_cache_entry_id` identifies a managed runtime generation. `documents`, `issue_resources` and `review_resources` have natural keys rather than catalog-local resource/version IDs. `search_document_id` identifies a disposable search input, not a document entity.

`database_identity.singleton` selects the one identity row, not an entity. Composite association/progress keys retain entity IDs plus scalar ordinals, roles or names. `job_attempts.attempt` and `jobs.current_attempt` are attempt ordinals. `provider_change_request_number` is a provider request number scoped by binding and `change_request_kind`. `index_generations.target_max_search_document_id` is a fixed build cutoff, not a foreign key. `search_documents.source_key` is a derived text key interpreted by search kind (content row, Git object row or text-body SHA-256).

## Identity and acquisition

| Tables | Meaning and relationships |
| --- | --- |
| `service_instances`, `sources` | Service identity and explicit discovery configuration; sources reference `service_instance_uuidv4`. |
| `repositories`, `repository_bindings`, `repository_endpoints` | Repository identity is independent of provider IDs and URLs. Bindings uniquely scope `provider_repository_id` by `service_instance_uuidv4`; endpoints belong to a `repository_uuidv4`. |
| `source_repositories`, `repository_name_assertions`, `inventory_observations` | Source membership, observed names and inventory coverage/history. |
| `git_acquisitions`, `snapshots`, `acquisition_roots`, `root_origins`, `ref_observations` | Acquisition records endpoint/source/context. Published snapshots and roots share the same repository owner. Shared traversal roots retain separate raw ref and PR-role origins. |
| `jobs`, `job_attempts`, `acquisition_progress`, `collection_progress`, `space_reservations` | Runtime work, attempt fencing, atomic progress and capacity reservations. |

Composite FKs enforce same-owner relationships. Publication checks require suitable facts; current historical selection derives from eligible published results and immutable selection DAGs. Repository IDs are internal UUIDs for fresh registrations; imported source identifiers remain preserved. Native `provider_repository_id`, `provider_change_request_document_id`, `provider_resource_id` and `provider_event_id` are provider-originated identifiers, not catalog row IDs. Provider-specific Node IDs remain in raw payload evidence but are not modeled as a generic normalized `provider_node_id` column.

## Portable identity decisions

Service display names are not unique. Name selection requires exactly one match; explicit service UUIDs are authoritative. An ambiguous implicit `github.com` selection requires `--instance UUID`. Source selectors accept a local ID or registration UUID, with `local:` and `registration:` prefixes to resolve cross-kind ambiguity. Display names do not select sources. Source service membership, discovery kind and registration UUID are immutable; name and operational settings remain local attributes. `settings=NULL` means unconfigured, while configured settings must be a JSON object and satisfy acquisition-specific checks.

Portable observation identity, verified parser selection, payload CAS and single-repository exchange are integrated. Schema 15 uses scoped current-state stores with field-specific acquisition evidence alongside the immutable PR/Git interpretation model.

`service_instance_uuidv4` is a portable namespace generated with `uuid.uuid4()` from a cryptographically secure random source. The DDL accepts canonical lowercase RFC UUIDv4 text with the RFC variant; UUIDv5, other versions and arbitrary strings are rejected. Validation can establish representation/version/variant, not prove the entropy source of an imported UUID. Received invalid identity is rejected or diagnosed rather than replaced with a fabricated value.

A repository with a native provider ID has portable identity `(service_instance_uuidv4, provider_repository_id)`. Distinct namespaces are never merged merely because web/API URLs match. URLs remain locators/attributes, not identity keys. Independently registered copies of the same real service may deliberately remain distinct. Conflicting assertions under a reused identity require diagnostics, not silent replacement. A binding without a provider ID has no such portable repository key.

`service_kind` retains the existing closed enumeration (`github`, `gitlab`, `gitea`, `forgejo`, `gitolite`, `git`, `other`). Open-ended provider types and additional collectors remain deferred. Provider-originated ID values and raw payload keys are preserved; a value is not necessarily globally unique by itself. `provider_resource_id` therefore means an opaque provider-native identifier whose required uniqueness scope is defined by the owning resource. GitHub review threads use the GraphQL node `id` as this value, but the common schema does not require every provider to offer a service-wide global ID. The same PR's title/body reuse a provider ID and are separated by document `kind`.

Single-repository export/import carries required identity, dependencies and bytes, remapping catalog-local IDs by portable identity. Missing dependencies and immutable collisions remain staged. Current-state updates use their shared admission rules rather than treating every changed row as an immutable collision. Receiver-local trust, quarantine, settings and Source-wide inventory are excluded. Backup/restore copies a database snapshot; it is not semantic import/remapping.

## Git structure and content

`git_objects.git_object_id` is a catalog integer. `(object_format, oid)` identifies a Git object: `oid` is full-length BLOB bytes (20 for SHA-1, 32 for SHA-256). Role OIDs such as `head_oid`, `base_oid`, `target_oid` and `child_oid` also contain Git bytes, never catalog IDs.

`commits.git_object_id`, `tag_objects.git_object_id` and `blob_content_map.git_object_id` reuse their owning object's identifier. `commits.tree_git_object_id`, `commit_parents.commit_git_object_id` / `parent_git_object_id`, `tree_entries.tree_git_object_id` / `child_git_object_id` and `tag_objects.target_git_object_id` make target roles explicit. Ordered parents, raw headers/messages, raw tree names, paths and refs survive acquisition/import. Gitlinks may retain only external OID bytes without a local child object.

`repository_object_sources` attributes shared objects to repository acquisitions. `contents.content_id` identifies content independently; `blob_content_map` associates it with Git blobs. `content_digests` records representation/algorithm-specific raw-content digests. A Git OID hashes a typed/length-prefixed payload; raw-content MD5/SHA-1/SHA-256 hash payload bytes alone. Candidate digest indexes do not imply identity or erase collisions.

`root_manifests` and `root_manifest_entries` share `tree_git_object_id`. Completed manifests are sealed. Historical paths are reconstructed from stored trees without materializing every commit × path. Missing bytes remain distinct from empty bytes; policy exclusions and missing bodies report partial coverage.

## Change requests, documents and API history

`change_requests` belongs to a `repository_binding_id` and `repository_uuidv4`. Its portable identity is the repository portable identity plus `(change_request_kind, provider_change_request_number)`. Published `change_request_observations` retain exact payloads, observation times and `origin_fetch_occurrence_id`. `code_observations` connects a `change_request_observation_id` to `commit_code_listing_id` and `file_code_listing_id`; `code_acquisitions` links role OIDs to `acquisition_root_id`.

`documents` is identified directly by `(change_request_id, kind, provider_change_request_document_id)` and contains PR title, body and PR conversation `issue-comment` kinds. There is no document surrogate/version table. The parent change request must be resolved across catalogs. Review summaries/comments instead use `review_resources` with the same logical resource key; redundant `reviews`/`review_comments` marker tables are removed. `review_threads` retains its independent natural key `(change_request_id, provider_resource_id)` and immutable thread observations.

`text_bodies.sha256` is the unique content identity: SHA-256 of exact UTF-8 bytes of `body`, with no Unicode, whitespace or newline normalization. Empty text is a valid body, not missing content. `text_body_id` remains a local integer; it is not the portable/content key. Admission computes/verifies the digest, looks up by digest and checks an existing body's exact text and byte length before reuse. Inconsistent input or same-hash/different-body is an integrity error, never a second body under that identity. SQL enforces digest uniqueness and byte length; application admission and explicit DB checks verify the hash. This rule is specific to text bodies and does not change raw `contents`/`content_digests` collision handling.

Each historical `document_observations` row directly references `text_body_sha256 -> text_bodies.sha256`. A→A→B→A yields four observations and two shared bodies; no version entity or inferred interval is materialized. Replaying an already-admitted source occurrence produces no additional observation and does not move current backward. This behavior applies to retained PR title/body/conversation history, not the current-state Issue/review families. Observations retain metadata and acquisition provenance; unobserved intervening edits are not reconstructed.

`current_document_observations` selects same-document facts through eligible published results and the explicit fact/profile selection DAGs. The document identity table has no current-observation pointer. If selection is unresolved, current queries report partial coverage; all stored observations remain accessible. Normalized document identity does not use a secondary provider Node-ID alias; any such provider value remains in the raw payload evidence.

`stored_bytes(sha256, body, byte_length)` stores each exact byte sequence once under
its 32-byte SHA-256. `payloads(representation, sha256)` separately registers the
logical representation; neither table has a local integer payload key. Different
representations can share physical bytes. Acquisition, validator and gap records
use composite logical-payload FKs. Writers verify declared hashes and compare
existing bytes before reuse; physical and logical admission is atomic. Existing
bytes are never silently overwritten. Portable payload JSON uses exactly
`representation` and a 64-character lowercase hexadecimal `sha256`; new inventory
and 304 evidence stores that reference. Provider evidence remains unchanged.

Durable conflict staging, local physical quarantine, explicit atomic repair,
full backup/restore hash verification and exchanged-owner validation use this
admission foundation. Supplementary transport archives use separate recording
adapters and are not mandatory catalog payloads for current-state resources.

The tables `fetch_collections`, `fetch_occurrences` and `collection_memberships` preserve separate requests/pages/membership. `resume_scopes`, `validators`, `incremental_scans`, `resume_cursors` and `completion_markers` retain request context and safe restart boundaries. `code_listings`, `code_listing_progress`, `code_commits` and `code_file_changes` use `code_listing_id`, `fetch_collection_id` and `fetch_occurrence_id`; completion seals membership. `unresolved_payloads` retains attributable parsing gaps. Resume/replay does not create new remote observations or advance watermarks.

## Shared latest-state resources

| Physical store | Key | Lifecycle and ownership |
| --- | --- | --- |
| `issue_resources` | `(service_instance_uuidv4, kind, provider_resource_id)` | `issue` and `issue-comment`; one accepted state per provider resource. Current repository/binding/Issue number are attributes; an Issue's permanent identity survives a supported transfer. |
| `review_resources` | `(change_request_id, kind, provider_change_request_document_id)` | `review` and `review-comment`; every distinct review/comment is retained at its latest accepted state, owned by the same PR/repository/binding/service. |

Each current row stores its exact text-body reference, provider attributes, parser/profile UUID, non-secret acquisition scope and the distinct times `provider_updated_at_us`, `observed_at_us`, `last_checked_at_us`, `parsed_at_us`. Body status distinguishes present, provider-null, missing and inaccessible. Absent fields in a partial response do not erase known fields. SQL keys, composite FKs and triggers guard identity, canonical positive decimal provider IDs, typed parents, scope ownership, replies and thread consistency. Review membership, reply membership and thread membership remain separate; unresolved parents are staged rather than fabricated.

`field_evidence_json` keeps one proof for each currently known mutable field or metadata path: provider clock, observation/parse times, exact parser profile and original acquisition scope. It stores no previous values. Omitted fields retain their original evidence instead of inheriting a newer response clock. An older complete response may fill a previously unknown body while a newer known title remains unchanged. Actual same-clock contradictions remain conflicts. Map size follows retained fields/metadata paths, rather than edit count; paths for absent values are rejected. Reviews have no title column or provider update clock.

The common admission service handles live collection, import and replay. Equal content is idempotent, while stronger field evidence can reevaluate staged conflicts. Comparable provider clocks can establish order; an explicit live acquisition fence additionally requires the saved catalog revision and exact acquisition scope. Receipt order, UUID order and parsing time are not ordering evidence. A different state with no proven order is staged as a conflict and suppressed from ordinary eligible-current queries. Missing dependencies can promote after arrival and restart. Current staging is classified by resource type instead of record-key spelling. No normalized edit/observation row is appended for these families. Unreferenced shared text bodies are not automatically garbage collected.

An Issue transfer updates child current repository/binding/number and preserves their original captured endpoint, Source, repository/binding, observation/parse times and field proofs. Export from the destination retains these captured identifiers as a validated provenance snapshot without importing the former repository/Source registrations. Existing captured registrations must agree when present. Current membership still has ordinary typed owner/parent FKs. Live acquisition must match current membership. Updates assign only changed columns, and unchanged membership never cascades child updates.

`last_checked_at_us` is receiver-local: accepted initial, edited and identical authoritative live acquisitions advance it using the local check/response observation time, monotonically. Authoritative means a matching pre-request catalog revision and exact scope. Import/replay ignores sender check times and preserves any existing receiver check. Provider clock and per-field capture evidence remain distinct from this local confirmation.

Current rows are mutable domain state and are not sealed immutable parsed-result output members. Exact selected verified profiles and receiver-local trust still govern eligibility. Immutable PR/Git results, owned inputs/outputs, predecessor DAGs and independent thread observations retain their existing contracts. Stable code-target references preserve earlier code listings when a review comment changes later.

Current-resource collection retains minimal immutable `current_collection_pages`: scoped collection, page ordinal, observation time, next cursor, member identities/state digests and successful status. A completion marker seals contiguous pages and the explicit terminal boundary. These receipts do not point at mutable body state and do not require archived HTTP bytes. They justify collection completeness; a successful response alone does not. Full/selective exchange includes required current rows, parents, bodies and scope/completion evidence while excluding optional message archives. Historical `--fetch`/`--collection` exchange remains available for unaffected acquisitions.

## Coverage claims and current state

`coverage_scopes` identifies one repository or change-request component by its owner and `kind`. Partial unique indexes enforce one scope per `(repository_uuidv4, kind)` for repository scopes and per `(change_request_id, kind)` for change-request scopes; the latter retains same-repository ownership. A scope has no current-claim pointer.

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

`export_current_claims` returns the whole maximum-time set, retaining `unknown`, conflict constituents and each claim's separate raw `details_json` or `NULL`. Exchange resolves destination scope ownership and carries justified proof rather than claiming a selected subset is complete. CLI `coverage`, `status` and snapshot results expose the derived scope and its `claims` list using one SQLite snapshot. PR queries use the same current view so historical incomplete claims do not poison a newer complete result.

Runtime producers use the original observation being evaluated. Git repository-wide claims use the fixed refs observation and are emitted only by repository Git collection, not PR-only roots. REST claims use actual page observation times; thread completion includes nested GraphQL page times. Replaying a committed terminal page or resuming an older fixed root does not acquire the resume time. A job start, local failure or failure before any response does not itself create a coverage claim; incomplete observed prefixes can produce `partial`. Job/collection progress remains separately queryable. Optional recording availability does not change semantic coverage. Required identity/owner corruption remains an integrity failure.

PR code observations are finalized after acquisition, with their exact required role links and coverage claim published atomically. Complete code requires stable API head/base, complete context-proven lists, resolved target enumeration and preserved matching Git roots. Partial GraphQL responses retain any valid merge targets without treating an incomplete target set as complete. Explicitly returned null merge targets remain visible as null in advisory merge metadata; only actual target OIDs enter `expected_roles` and require acquisition. A failed refresh may reuse previously preserved exact roots; an unobserved transport failure alone does not create a new partial claim. Rechecking the same saved PR observation without new incomplete evidence does not append a partial code observation over matching complete code; new observations and actual Git/API races still require their own assessment.

Query completeness also accounts for structural gaps in the requested saved data. A new current PR observation without its required code observation, or a purportedly complete code observation lacking required published role links, is reported as incomplete without modifying claims. PR queries evaluate these gaps and semantic coverage for the requested identity scope within one read transaction, before pagination. Document-only queries exclude code-only collection/claim kinds; commit or path constraints require code coverage. Page size, byte cutoff and cursor position do not change this assessment. Result filters, including state, author and reviewer, do not hide gaps from that identity scope; missing saved information may itself match the filter. Ordinary queries assess the selected current code observation, while diagnostic target queries apply the same role checks to retained code-observation history.

Imported listing reuse records the original authenticated detail/304 boundary, including its marker, PR observation and time. Reusing the same boundary does not append another completion marker. A 304 replay resolves its saved authorized observation even after the current PR selection changes. GraphQL connection completion requires explicit nodes and valid pagination fields; malformed root or nested pages retain their response and retry boundary and remain partial. Error-only rate-limit responses retain raw evidence and the retry cursor as operational state; they do not advance semantic observation times or create new incomplete content claims. Saved prefixes retain their original times, and jobs honor the recorded retry deadline.

## Preservation, search and maintenance

`cache_locators` distinguishes read-only source evidence from target-active storage. `active_cache_entries` owns managed generations; `cache_leases` references `active_cache_entry_id`. `content_locations` and `preservation_obligations` reference `cache_locator_id`. Recovery/GC obey preservation obligations and OS locks.

`search_documents`, `index_generations` and `index_membership` are derived search data. Membership joins on `index_generation_id` and `search_document_id`. Historical PR search still distinguishes matching observations. Current Issue/review search resolves each eligible current row and never returns a stale body merely because a derived index retains a candidate. FTS candidates are checked against literal original text; missing indexes fall back to scans. Rebuilding derived data does not change catalog identity/publication sequence.

The v2 importer and conversion workspace are retired (`D2: not_applicable / retired`). Historical reports and source receipts are retained as evidence. They are not current operations or schema requirements, and their retirement does not permit fabricated identity or observation time.

Reads use normal SQLite transaction snapshots with foreign keys and recursive triggers enabled. `publication_seq` fences paginated results; restore issues a new database instance and resets operational cache/job state. Backup scans source bytes under the writer lock, verifies copied bytes, and records the verified copy's active `payload_quarantine` row count as mandatory `quarantined_payload_count`. Restore checks copied checksum/identity and that count before diagnostic scanning, then verifies all physical bytes. The count is a JSON integer from 0 through `9223372036854775807`, excluding booleans. Positive matching counts retain known quarantined bytes and diagnoses; mismatches and unexplained corruption reject publication while retaining the failed stage. Counts exclude representations, historical diagnoses, staging and cache quarantine directories.

Backup preserves guaranteed catalog data, excluding Git cache and supplementary transport archives. Ordinary restored current-state use does not require the archive. No mandatory multi-store forensic backup is promised. LFS preserves Git pointer bytes; attachments preserve source text and embedded URLs. LFS objects, attachment bodies and automatic external URL fetching are outside scope. See [operations](operations.md), [transport recording](latest-state-transport.md) and [integration handoff](model-integration-handoff.md). Files under `docs/schema-hardening/` are historical snapshots, not the active DDL.

### Provider resource admission

GitHub document/current-resource identities use REST `id` or GraphQL `fullDatabaseId`, represented as positive decimal text. GraphQL `id`/REST `node_id` are not fallback keys or alternate normalized identities. When a canonical database ID is missing, retain an attributable partial diagnostic and required retry context without admitting a Node-keyed resource or advancing the page as complete. Unaffected historical responses remain required catalog evidence; current-state response recording is optional. The Issues API includes PRs, so ordinary Issue admission checks ownership and excludes PR records; PR conversation comments retain their historical policy.

Review-thread `provider_resource_id` remains opaque, unparsed provider text. Its key is `PRIMARY KEY(change_request_id, provider_resource_id)`; different change requests may contain the same value, even within one service namespace. `review_resources.review_thread_provider_resource_id` references that key with the same `change_request_id`; NULL denotes an unresolved thread association. The provider value, not a synthetic parent-prefixed string, is passed to the GitHub GraphQL node query.

CLI and normalized query results use `provider_change_request_number` and `change_request_kind`. Selectors are `--provider-change-request-number` and `--change-request-kind`. Raw provider response keys (`number`, `id`, `node_id`, `fullDatabaseId`) are unchanged.
