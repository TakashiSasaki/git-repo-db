# Application JSON contract inventory

This active schema **18** contract inventory follows the composed production SQLite schema and explicit `json_contracts.JSON_REGISTRY`; the registry rejects unclassified CHECK-backed JSON columns. The [Phase 1 implementation inventory](phase1-api-original-retirement-implementation.md) records executed before/after schema and JSON dependencies. Earlier [current closure](current-state-schema-closure.md), [column liveness](current-state-schema-liveness.md) and [complete schema inventory](current-state-schema-inventory.md) are historical receipts, separate from schema 18 acceptance.

## Enforceable categories

| Category | Contract |
|---|---|
| `authored` | Recursive typed target/owner/dependency validation; SQL guards; exact payload identities. |
| `current-acquisition` | Issue capture scope with canonical typed identifiers, endpoint and service checks. A transferred comment may retain detached repository/binding/Source identifiers as a validated snapshot; available registrations must agree, but the old registrations are not required exchange dependencies. |
| `current-field-evidence` | One proof per retained mutable scalar/body/metadata path; canonical path, clock/time, actual parser module/version and capture schema, with no absent-field proofs or previous values. Profile/result/transport-original references are rejected; original capture scopes are snapshots. |
| `current-members` | Typed current-page resource identities/digests, unique member keys and collection binding/owner checks; immutable page and terminal evidence. |
| `provider` | Opaque provider projection; object JSON only. Application reference names have no meaning here. |
| `operational` | Receiver-local configuration/checkpoints/diagnostics; object JSON; existing operational writer/registration contracts. Excluded from portable evidence. |
| `decoded-headers` | Result-owned decoded Git strings; JSON object values are header/message text, not catalog references. |
| `definition` | Full immutable parser definition or verification schema; named references validated; SHA-256 fields are canonical definition/test-report digests, not payload aliases. |
| `input-manifest` | Nonempty typed input array; canonical targets, real owner, composite input FKs and sealed membership. |
| `fact-manifest` | Exact generated-fact table/natural-key set checked by publication SQL; immutable after sealing. |
| `predecessor-manifest` | Unique canonical decision UUID array; typed targets, scope FKs and publication DAG guards. |
| `git-roots` | Captured Git refs require structured name/name_b64/oid/type/peeled and optional exact PR role/number/expected fields. Python checks canonical base64 and lossless displayed-name correspondence; SQL checks member types/base64 syntax and canonical OID format. Capture OIDs are declarations before object admission; published roots use exact format/OID/role set guards. |
| `git-object-manifest` | Exact object-format/OID/raw-payload map; typed Git natural keys, owner/acquisition membership, raw mapping and immutable publication guards. |
| `staging-envelope` | Unadmitted retained domain/proof record envelope; dedicated validator before admission and on promotion. Missing dependencies/immutable variants stay durable. Original-only envelope chains cannot authorize API-original admission. |
| `local-key` | Receiver-local table-key map; Graph remapping validates table/key schema; never application evidence. |

## Every JSON CHECK column

| Table and column | Category | Shape / null |
|---|---|---|
| `change_request_events.payload` | `provider` | object; required |
| `change_request_observations.payload` | `provider` | object; required |
| `code_commits.payload` | `provider` | object; required |
| `code_file_changes.payload` | `provider` | object; required |
| `code_observations.details` | `authored` | object; required |
| `commits.metadata` | `decoded-headers` | object; required |
| `completion_markers.evidence` | `authored` | object; required |
| `coverage_claims.details_json` | `authored` | object; NULL allowed |
| `current_collection_pages.members` | `current-members` | array; required |
| `document_observations.metadata` | `provider` | object; required |
| `exchange_admissions.local_key_json` | `local-key` | object; required |
| `exchange_admissions.record_json` | `staging-envelope` | object; required |
| `exchange_local_identities.local_key_json` | `local-key` | object; required |
| `exchange_source_provenance.definition_json` | `operational` | object; required |
| `exchange_staging.record_json` | `staging-envelope` | object; required |
| `fact_selection_decisions.predecessor_manifest_json` | `predecessor-manifest` | array; required |
| `fact_selection_staging.record_json` | `staging-envelope` | object; required |
| `fetch_occurrences.request` | `authored` | object; required |
| `git_acquisition_publications.object_manifest_json` | `git-object-manifest` | array; required |
| `git_acquisition_publications.root_manifest_json` | `git-roots` | array; required |
| `git_acquisitions.request` | `authored` | object; required |
| `git_acquisitions.roots_manifest` | `git-roots` | array; NULL allowed |
| `identity_relation_cancellations.evidence_json` | `authored` | object; required |
| `identity_relation_staging.record_json` | `staging-envelope` | object; required |
| `identity_relations.evidence_json` | `authored` | object; required |
| `incremental_scans.evidence` | `authored` | object; required |
| `inventory_observations.scope` | `operational` | object; required |
| `issue_resources.acquisition_scope_json` | `current-acquisition` | object; required |
| `issue_resources.field_evidence_json` | `current-field-evidence` | object; required |
| `issue_resources.metadata` | `provider` | object; required |
| `job_attempts.checkpoint` | `operational` | object; required |
| `jobs.request` | `operational` | object; required |
| `local_parser_profile_verification_trust.rationale_json` | `operational` | object; required |
| `parsed_result_publications.fact_manifest_json` | `fact-manifest` | array; required |
| `parsed_results.derivation_json` | `authored` | object; required |
| `parsed_results.input_manifest_json` | `input-manifest` | array; required |
| `parser_profile_selection_decisions.predecessor_manifest_json` | `predecessor-manifest` | array; required |
| `parser_profile_selection_staging.record_json` | `staging-envelope` | object; required |
| `parser_profile_verifications.criteria_json` | `definition` | object; required |
| `parser_profile_verifications.evidence_json` | `definition` | object; required |
| `parser_profiles.definition_json` | `definition` | object; required |
| `payload_admission_staging.context_json` | `operational` | object; required |
| `repositories.metadata` | `authored` | object; required |
| `repository_bindings.metadata` | `authored` | object; required |
| `repository_endpoints.metadata` | `authored` | object; required |
| `repository_inventory_observations.metadata_json` | `provider` | object; required |
| `repository_name_observations.provenance_json` | `authored` | object; required |
| `resume_scopes.request_context` | `authored` | object; required |
| `review_resources.acquisition_scope_json` | `authored` | object; required |
| `review_resources.field_evidence_json` | `current-field-evidence` | object; required |
| `review_resources.metadata` | `provider` | object; required |
| `review_thread_observations.payload` | `provider` | object; required |
| `search_documents.metadata` | `operational` | object; required |
| `service_instances.metadata` | `authored` | object; required |
| `source_input_observations.request_context_json` | `authored` | object; required |
| `sources.settings` | `operational` | object; NULL allowed |
| `unresolved_payloads.diagnostic_json` | `operational` | object; required; physical corruption only |

## Meaningful reference vocabulary

| JSON name | Exact target |
|---|---|
| `change_request_id` | `change_requests.change_request_id` |
| `change_request_observation_uuidv4` | `change_request_observations.change_request_observation_uuidv4` |
| `code_observation_uuidv4` | `code_observations.code_observation_uuidv4` |
| `completion_marker_uuidv4` | `completion_markers.completion_marker_uuidv4` |
| `document_observation_uuidv4` | `document_observations.document_observation_uuidv4` |
| `fetch_collection_id` | `fetch_collections.fetch_collection_id` |
| `fetch_occurrence_uuidv4` | `fetch_occurrences.fetch_occurrence_uuidv4` |
| `git_acquisition_id` | `git_acquisitions.git_acquisition_id` |
| `parent_fetch_collection_id` | `fetch_collections.fetch_collection_id` |
| `parsed_result_uuidv4` | `parsed_results.parsed_result_uuidv4` |
| `parser_profile_uuidv4` | `parser_profiles.parser_profile_uuidv4` |
| `parser_profile_verification_uuidv4` | `parser_profile_verifications.parser_profile_verification_uuidv4` |
| `relation_uuidv4` | `identity_relations.relation_uuidv4` |
| `repository_binding_id` | `repository_bindings.repository_binding_id` |
| `repository_endpoint_id` | `repository_endpoints.repository_endpoint_id` |
| `repository_uuidv4` | `repositories.repository_uuidv4` |
| `resume_scope_id` | `resume_scopes.resume_scope_id` |
| `selection_decision_uuidv4` | `fact_selection_decisions.fact_selection_decision_uuidv4` |
| `service_instance_uuidv4` | `service_instances.service_instance_uuidv4` |
| `source_input_uuidv4` | `source_input_observations.source_input_uuidv4` |
| `source_registration_uuidv4` | `sources.source_registration_uuidv4` |
| `stable_scope` | `resume_scopes.resume_scope_id` |
| `change_request_ids` | Array of `change_request_id` targets; exact assessed request set for aggregate coverage proof. |
| `parsed_result_uuidv4s` | Array of `parsed_result_uuidv4` targets; exact complete code interpretations for aggregate coverage proof. |
| `completion_marker_uuidv4s` | Array of `completion_marker_uuidv4` targets; identical references deduplicate during dependency extraction. |
| `fetch_collection_ids` | Array of `fetch_collection_id` targets; identical references deduplicate during dependency extraction. |
| `fetch_occurrence_uuidv4s` | Array of `fetch_occurrence_uuidv4` targets; identical references deduplicate during dependency extraction. |
| `git_acquisition_ids` | Array of `git_acquisition_id` targets; identical references deduplicate during dependency extraction. |
| `selection_predecessors` | Array of `selection_decision_uuidv4` targets; identical references deduplicate during dependency extraction. |

`payload` is exactly `{"representation":...,"sha256":...}` with a supported logical representation and lowercase 64-character SHA-256. SQL canonical hexadecimal checks compare both text and byte widths, rejecting embedded NUL characters that SQLite's text functions otherwise truncate. The physical digest does not substitute for the logical `(representation, sha256)` key. A payload reference also needs an acquisition under the evidence owner. Global physical sharing does not establish ownership. Missing explicit acquisition inputs defer that ownership check until promotion; an existing foreign owner or conflicting authoritative Git byte map is rejected.

Authored evidence recursively reserves registered names, unknown `*_uuidv4`/`*_uuidv4s`/`*_sha256` encodings, payload encodings, and catalog-local surrogate reference names. Other annotation properties have no reference semantics and are never dereferenced. A new semantic property therefore needs an explicit registry entry and consumer contract. UUIDs must be canonical UUIDv4 text; textual portable natural identities remain separate from receiver-local integer IDs. Duplicate authored JSON properties are rejected. Malformed encodings, wrong-kind UUIDs and foreign ownership are contract errors; missing valid targets raise `MissingJsonDependencies` and follow durable exchange staging.

The root `parsed_results.derivation_json.selection_decision_uuidv4` when `kind` is `git` declares a future output decision allocated by the Git planner; it is canonical but is not an already-existing dependency. The same name at any nested location or under another derivation kind is a real typed decision dependency. `selection_predecessors` always contains dependencies.

Application-consumed code detail fields have concrete optional schemas: expected role/OID maps match the declared Git object format, review-target role IDs match their OID, API/code completion flags are booleans, missing roles are typed arrays, provider limits are positive int64 bounds, and merge declarations contain canonical OIDs or null. These OIDs are expectations until actual acquisition links/publications establish ownership and completeness. Retained live request/context GraphQL variables, provider thread identities, query/request strings and consumed terminal/context flags have concrete types. API offline reparse is absent; the failed-response `operational_only` flag and its dedicated guards are removed.

The `head` and `base` members in `resume_scopes.request_context` are unmodified provider excerpts and remain opaque. Other members, including `parent_fetch_collection_id`, use authored reference rules. Provider projection columns remain explicitly opaque throughout export/import and preserve their content, pending the field-inventory decision. Successful historical publication, accepted partial GraphQL roots with error envelopes, live restart/304 and domain-proof paths still retain exact API bytes in CAS. Fully rejected, uncommitted API responses are not archived or staged in the core; optional external transport recording may separately capture them. This boundary does not claim zero transport-shaped JSON everywhere.

Current field proofs use canonical JSON-array path keys, such as `["body"]` or
`["metadata","reactions","total_count"]`. Each entry contains exactly
`provider_updated_at_us`, `provider_clock_scope`, `observed_at_us`,
`parsed_at_us`, `parser_module`, `parser_version` and `acquisition_scope`. The
body and its availability status share one proof. Missing fields keep their prior proof;
explicit NULL and empty text remain known values. An older full projection may
fill an unknown field without overwriting a newer known field. The map holds
current attribution only, with size proportional to retained fields/metadata
paths; it does not grow a version history on each refresh.

Captured identifiers inside current-field proofs, and the detached portion of an
Issue comment's `current-acquisition` scope, are declarations of original capture
context. Canonical identity/service checks and consistency with existing
repository/binding/Source registrations remain enforced. They do not cause a
destination repository export to include the old repository or Source-wide
inventory. This exception is specific to the capture schemas; ordinary authored
references still require their typed dependencies. `last_checked_at_us` is
outside the proof map and remains a receiver-local authoritative-live check.

## JSON without a JSON CHECK column, and non-database envelopes

| Structure | Classification and validation |
|---|---|
| `collection_progress.cursor` JSON variants | Local restart boundary; contains opaque provider cursor/thread ID and receiver-local occurrence. Collector validates the saved boundary and ownership through SQL acquisition context. Excluded from exchange. Ordinary cursor text remains valid. |
| `unresolved_payloads.reason` | Required literal `physical_corruption`; no logical parsing-gap or JSON retry variant. Physical diagnostics remain local and excluded from exchange. |
| `job_attempts.reason` and progress reasons | Diagnostic strings, not a reference envelope, even if their text resembles JSON. |
| `stored_bytes.body` for API JSON | Remaining successful historical publication/live restart/304/domain-proof original bytes; SHA admission and exact equality. Body field names cannot justify standalone distribution or reinterpretation. |
| `parsed_fact_members.fact_key_json` | SQL-generated read-only manifest members derived from actual fact keys; publication checks exact membership. |
| Exchange unit / record `$refs`, `$bytes`, dependency manifests | Explicit `Graph` envelope schema and typed table/FK remapping; canonical hashes, real owners, repository boundary, exact publication and coverage proof checks. Original records require actual retained domain/Git/proof reachability; orphan originals and archive-only scaffolding are rejected on export/import/promotion. Promotion reruns JSON registry admission after remapping. |
| Parser verification package artifact | Exact full definition, capability evidence and report digests; checked by `verify_builtin_parser.py` and runtime full-profile verification. |
| Backup manifest | Local backup file/schema/digest envelope; maintenance validates exact format, retained DB hash and complete DDL before atomic restore. CAS-41 requires the verified copy's active physical `quarantined_payload_count`, strictly checked before restore diagnosis. |
| Source settings input / frozen job plan | Local acquisition configuration. `source_service`, `repository_identity` and `job_plans` validate supported settings, Source registration, saved plan ownership and credential references. Frozen Source registrations/settings are protected by the job plan FK table and checked before execution. |
| Query/page cursor and CLI JSON responses | Output/pagination protocol, not admitted portable evidence. Query cursor decoding checks its existing request identity and catalog revision. |

## Production boundaries and executable evidence

Packaged `resources/json_contracts.sql` is generated by `guard_sql()` and installed last by the single schema composer. It uses standalone SQL, without a connection-specific callback. INSERT/UPDATE guards validate authored shapes, duplicates, canonical references, nested target existence and owner/membership boundaries. Current-acquisition and field-evidence guards additionally enforce capture relationships and actual current-value paths. Existing typed FKs and publication/DAG/Git manifest guards remain authoritative for native manifests.

`ParserModel` validates profile definitions, verification criteria/evidence, result derivation and input/output manifests at application writer boundaries. `ApiFacts.finish` validates exact completion evidence, original 304 observation/result/fetch/payload and named root/child collection membership. Name observation and identity-evidence writers use the same registry. Exchange validates export, includes typed JSON dependency closure, and validates again on import/promotion after local-ID remapping. An explicit full catalog validation audits all admitted authored records; quick validation checks exhaustive schema classification.

`tests/integration/test_catalog3_json_contracts.py` covers canonical/nested/foreign/wrong-kind references, logical payload identity and owner acquisition, duplicate properties/reference set semantics, missing multiple targets, opaque provider data, future declarations, reopened promotion and record permutations. Independent attacks in `test_catalog3_remaining_adversarial.py` cover Source membership arrays, nested verification, delayed Git raw membership and embedded NUL encodings in Git OIDs and parser-definition digests. Current projection/transfer follow-up tests cover inherited clocks, detached snapshots and invalid proof paths. Installed distribution tests check the registry, SQL resource/generator equality and populated catalog audit. Invalid-header and code-role reader fixtures assert early rejection while retaining child-row ownership attacks and valid missing-acquisition diagnostics. Phase 1 schema 18 acceptance is recorded separately in the implementation report; the prior schema 15 receipt remains historical.
