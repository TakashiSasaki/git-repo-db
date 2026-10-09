-- Authoritative catalog3 runtime and offline-import schema.
-- Named surrogate keys use <entity>_id; documents use their natural composite key.
-- Service namespaces explicitly use service_instance_uuidv4; neutral FKs match.
-- Role FKs use <role>_<entity>_id. Git oid BLOBs are not catalog IDs.
-- Absolute timestamps use signed 64-bit Unix epoch microseconds and an _us suffix.
-- Every connection enables foreign_keys and recursive_triggers.
PRAGMA foreign_keys=ON;
PRAGMA recursive_triggers=ON;
CREATE TABLE database_identity(
singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    format_id TEXT NOT NULL CHECK(format_id='repo-catalog/catalog3'),
    schema_version INTEGER NOT NULL CHECK(schema_version=13),
    db_instance_id TEXT NOT NULL,
    publication_seq INTEGER NOT NULL CHECK(publication_seq>=0),
    ddl_sha256 BLOB NOT NULL CHECK(length(ddl_sha256)=32), lifecycle TEXT NOT NULL CHECK(lifecycle IN ('building','validated','rejected'))
) STRICT;
CREATE TABLE service_instances(
service_instance_uuidv4 TEXT PRIMARY KEY CHECK(
    length(service_instance_uuidv4)=36 AND length(CAST(service_instance_uuidv4 AS BLOB))=36
    AND substr(service_instance_uuidv4,9,1)='-' AND substr(service_instance_uuidv4,14,1)='-'
    AND substr(service_instance_uuidv4,19,1)='-' AND substr(service_instance_uuidv4,24,1)='-'
    AND length(replace(service_instance_uuidv4,'-',''))=32
    AND replace(service_instance_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*'
    AND substr(service_instance_uuidv4,15,1)='4' AND substr(service_instance_uuidv4,20,1) IN ('8','9','a','b')
), service_kind TEXT NOT NULL CHECK(service_kind IN ('github','gitlab','gitea','forgejo','gitolite','git','other')),
    name TEXT NOT NULL,
    web_base_url TEXT, api_base_url TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    created_at_us INTEGER
) STRICT;
CREATE TABLE sources(

source_id TEXT PRIMARY KEY, source_registration_uuidv4 TEXT NOT NULL UNIQUE CHECK(length(source_registration_uuidv4)=36 AND length(CAST(source_registration_uuidv4 AS BLOB))=36 AND substr(source_registration_uuidv4,9,1)='-' AND substr(source_registration_uuidv4,14,1)='-' AND substr(source_registration_uuidv4,19,1)='-' AND substr(source_registration_uuidv4,24,1)='-' AND length(replace(source_registration_uuidv4,'-',''))=32 AND replace(source_registration_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(source_registration_uuidv4,15,1)='4' AND substr(source_registration_uuidv4,20,1) IN ('8','9','a','b')), service_instance_uuidv4 TEXT REFERENCES service_instances(service_instance_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
    discovery_kind TEXT NOT NULL CHECK(discovery_kind IN ('manual_git','github_inventory')),
    name TEXT NOT NULL,
    settings TEXT CHECK(settings IS NULL OR (json_valid(settings) AND json_type(settings)='object')),
UNIQUE(source_id,source_registration_uuidv4)
) STRICT;
CREATE TABLE repositories(
repository_uuidv4 TEXT PRIMARY KEY, name TEXT NOT NULL,
    preferred_repository_endpoint_id TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    FOREIGN KEY(preferred_repository_endpoint_id,repository_uuidv4) REFERENCES repository_endpoints(repository_endpoint_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE repository_bindings(
repository_binding_id TEXT PRIMARY KEY,
    repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
    service_instance_uuidv4 TEXT NOT NULL REFERENCES service_instances(service_instance_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
    provider_repository_id TEXT CHECK(provider_repository_id IS NULL OR length(provider_repository_id)>0),
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), created_at_us INTEGER,
    UNIQUE(repository_uuidv4,service_instance_uuidv4), UNIQUE(service_instance_uuidv4,provider_repository_id), UNIQUE(repository_binding_id,repository_uuidv4)
) STRICT;
CREATE TABLE repository_endpoints(
repository_endpoint_id TEXT PRIMARY KEY,
    repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
    url TEXT NOT NULL CHECK(length(url)>0),
    transport TEXT NOT NULL CHECK(transport IN ('file','https','ssh','other')),
    label TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), created_at_us INTEGER,
    UNIQUE(repository_uuidv4,url), UNIQUE(repository_endpoint_id,repository_uuidv4)
) STRICT;
CREATE TABLE git_acquisitions(
git_acquisition_id TEXT PRIMARY KEY,
    repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
    repository_endpoint_id TEXT, endpoint_url TEXT,
    object_format TEXT CHECK(object_format IN ('sha1','sha256')),
    refs_observed_at_us INTEGER,
    source_id TEXT REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, kind TEXT NOT NULL CHECK(kind IN ('git','pr','legacy')), started_at_us INTEGER, observed_at_us INTEGER, request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'), roots_manifest TEXT CHECK(roots_manifest IS NULL OR (json_valid(roots_manifest) AND json_type(roots_manifest)='array')),
    UNIQUE(git_acquisition_id,repository_uuidv4),
    FOREIGN KEY(repository_endpoint_id,repository_uuidv4) REFERENCES repository_endpoints(repository_endpoint_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE snapshots(
parsed_result_uuidv4 TEXT NOT NULL,
snapshot_id TEXT PRIMARY KEY, git_acquisition_id TEXT NOT NULL,
    repository_uuidv4 TEXT NOT NULL, published INTEGER NOT NULL CHECK(published IN (0,1)),
    generation INTEGER NOT NULL CHECK(generation>=0), created_at_us INTEGER,
    UNIQUE(snapshot_id,repository_uuidv4),
    FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
UNIQUE(snapshot_id,repository_uuidv4,parsed_result_uuidv4), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4)
) STRICT;
CREATE TABLE change_requests(
change_request_id TEXT PRIMARY KEY, repository_uuidv4 TEXT NOT NULL, repository_binding_id TEXT NOT NULL,
    change_request_kind TEXT NOT NULL CHECK(change_request_kind IN ('pull_request','merge_request')),
    provider_change_request_number INTEGER NOT NULL CHECK(provider_change_request_number>0),
    UNIQUE(repository_binding_id,change_request_kind,provider_change_request_number), UNIQUE(change_request_id,repository_uuidv4),
    FOREIGN KEY(repository_binding_id,repository_uuidv4) REFERENCES repository_bindings(repository_binding_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE change_request_observations(
change_request_observation_uuidv4 TEXT NOT NULL UNIQUE, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL,

change_request_observation_id INTEGER PRIMARY KEY,
    change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    observed_at_us INTEGER, published INTEGER NOT NULL CHECK(published IN (0,1)),
    payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'),
    origin_key TEXT, parsed_at_us INTEGER NOT NULL, origin_fetch_occurrence_id INTEGER REFERENCES fetch_occurrences(fetch_occurrence_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    UNIQUE(change_request_observation_id,change_request_id),
FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4),
UNIQUE(parsed_result_uuidv4,change_request_id)
) STRICT;
CREATE TABLE text_bodies(
text_body_id INTEGER PRIMARY KEY, body TEXT NOT NULL,
    byte_length INTEGER NOT NULL CHECK(byte_length>=0 AND byte_length=length(CAST(body AS BLOB))),
    sha256 BLOB NOT NULL CHECK(length(sha256)=32), UNIQUE(sha256)
) STRICT;
CREATE TABLE documents(
 change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id),
 kind TEXT NOT NULL CHECK(length(kind)>0),
 provider_change_request_document_id TEXT NOT NULL CHECK(length(provider_change_request_document_id)>0),
 PRIMARY KEY(change_request_id,kind,provider_change_request_document_id)
) STRICT;

CREATE TABLE document_observations(author TEXT, url TEXT, deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1)), review_thread_provider_resource_id TEXT,
document_observation_uuidv4 TEXT NOT NULL UNIQUE, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL,

    document_observation_id INTEGER PRIMARY KEY,
    change_request_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    provider_change_request_document_id TEXT NOT NULL,
    text_body_sha256 BLOB NOT NULL REFERENCES text_bodies(sha256) ON UPDATE RESTRICT ON DELETE RESTRICT,
    observed_at_us INTEGER, parsed_at_us INTEGER NOT NULL,
    origin_key TEXT,
    fetch_occurrence_id INTEGER REFERENCES fetch_occurrences(fetch_occurrence_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    UNIQUE(document_observation_id,change_request_id,kind,provider_change_request_document_id),
    FOREIGN KEY(change_request_id,kind,provider_change_request_document_id) REFERENCES documents(change_request_id,kind,provider_change_request_document_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4),
UNIQUE(parsed_result_uuidv4,change_request_id,kind,provider_change_request_document_id), FOREIGN KEY(change_request_id,review_thread_provider_resource_id) REFERENCES review_threads(change_request_id,provider_resource_id)
) STRICT;
CREATE TABLE review_threads(
 change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id),
 provider_resource_id TEXT NOT NULL CHECK(length(provider_resource_id)>0),
 PRIMARY KEY(change_request_id,provider_resource_id)
) STRICT;
CREATE TABLE review_comments(
 change_request_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind='review-comment'),
 provider_change_request_document_id TEXT NOT NULL,
 PRIMARY KEY(change_request_id,kind,provider_change_request_document_id),
 FOREIGN KEY(change_request_id,kind,provider_change_request_document_id) REFERENCES documents(change_request_id,kind,provider_change_request_document_id)
) STRICT;
CREATE TABLE fetch_collections(

fetch_collection_id TEXT PRIMARY KEY, repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, change_request_id TEXT,
    source_id TEXT REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, kind TEXT NOT NULL, resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, observed_at_us INTEGER,
    UNIQUE(fetch_collection_id,change_request_id),
    FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
UNIQUE(fetch_collection_id,repository_uuidv4)
) STRICT;
CREATE TABLE code_listings(
code_listing_id TEXT PRIMARY KEY, change_request_id TEXT NOT NULL,
    fetch_collection_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('commits','files')),
    resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, object_format TEXT CHECK(object_format IN ('sha1','sha256')), head_oid BLOB, base_oid BLOB, CHECK((head_oid IS NULL AND base_oid IS NULL) OR (object_format IS NOT NULL AND object_format='sha1' AND (head_oid IS NULL OR length(head_oid)=20) AND (base_oid IS NULL OR length(base_oid)=20)) OR (object_format IS NOT NULL AND object_format='sha256' AND (head_oid IS NULL OR length(head_oid)=32) AND (base_oid IS NULL OR length(base_oid)=32))),
    UNIQUE(fetch_collection_id,kind), UNIQUE(code_listing_id,change_request_id),
    FOREIGN KEY(fetch_collection_id,change_request_id) REFERENCES fetch_collections(fetch_collection_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE code_observations(code_observation_uuidv4 TEXT NOT NULL UNIQUE, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL,

code_observation_id INTEGER PRIMARY KEY, change_request_id TEXT NOT NULL, change_request_observation_id INTEGER NOT NULL,
    commit_code_listing_id TEXT, file_code_listing_id TEXT,
    state TEXT NOT NULL CHECK(state IN ('pending','partial','complete','unknown')),
    object_format TEXT CHECK(object_format IN ('sha1','sha256')), head_oid BLOB, base_oid BLOB, details TEXT NOT NULL CHECK(json_valid(details) AND json_type(details)='object'), CHECK((head_oid IS NULL AND base_oid IS NULL) OR (object_format IS NOT NULL AND object_format='sha1' AND (head_oid IS NULL OR length(head_oid)=20) AND (base_oid IS NULL OR length(base_oid)=20)) OR (object_format IS NOT NULL AND object_format='sha256' AND (head_oid IS NULL OR length(head_oid)=32) AND (base_oid IS NULL OR length(base_oid)=32))),
    CHECK(state!='complete' OR (commit_code_listing_id IS NOT NULL AND file_code_listing_id IS NOT NULL)),
    FOREIGN KEY(change_request_observation_id,change_request_id) REFERENCES change_request_observations(change_request_observation_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(commit_code_listing_id,change_request_id) REFERENCES code_listings(code_listing_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(file_code_listing_id,change_request_id) REFERENCES code_listings(code_listing_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4)
) STRICT;
CREATE TABLE acquisition_roots(
acquisition_root_id INTEGER PRIMARY KEY, git_acquisition_id TEXT NOT NULL REFERENCES git_acquisitions(git_acquisition_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
    oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)),
    role TEXT NOT NULL,
    repository_uuidv4 TEXT NOT NULL, expected_oid BLOB, published INTEGER NOT NULL CHECK(published IN (0,1)), FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, CHECK(expected_oid IS NULL OR length(expected_oid)=length(oid)), UNIQUE(acquisition_root_id,repository_uuidv4),
    UNIQUE(git_acquisition_id,object_format,oid,role)
) STRICT;
CREATE TABLE root_origins(
root_origin_id INTEGER PRIMARY KEY, acquisition_root_id INTEGER NOT NULL REFERENCES acquisition_roots(acquisition_root_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    origin_kind TEXT NOT NULL CHECK(origin_kind IN ('ref','pr_role','legacy_unknown')),
    raw_ref_name BLOB, source_ordinal INTEGER NOT NULL CHECK(source_ordinal>=0),
    snapshot_id TEXT, change_request_id TEXT, change_request_observation_id INTEGER, repository_uuidv4 TEXT NOT NULL, FOREIGN KEY(acquisition_root_id,repository_uuidv4) REFERENCES acquisition_roots(acquisition_root_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(snapshot_id,repository_uuidv4) REFERENCES snapshots(snapshot_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(change_request_observation_id,change_request_id) REFERENCES change_request_observations(change_request_observation_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT, CHECK((origin_kind='ref' AND snapshot_id IS NOT NULL AND change_request_id IS NULL AND change_request_observation_id IS NULL) OR (origin_kind='pr_role' AND snapshot_id IS NULL AND change_request_id IS NOT NULL AND change_request_observation_id IS NOT NULL) OR (origin_kind='legacy_unknown' AND snapshot_id IS NULL AND change_request_id IS NULL AND change_request_observation_id IS NULL)),
    UNIQUE(acquisition_root_id,origin_kind,source_ordinal),
    CHECK(origin_kind!='ref' OR (raw_ref_name IS NOT NULL AND length(raw_ref_name)>0))
) STRICT;
CREATE TABLE job_attempts(
job_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>=1),
    state TEXT NOT NULL CHECK(state IN ('queued','running','waiting','complete','failed','interrupted','cancelled','unknown')),
    created_at_us INTEGER, updated_at_us INTEGER, not_before_us INTEGER, checkpoint TEXT NOT NULL CHECK(json_valid(checkpoint) AND json_type(checkpoint)='object'), reason TEXT, FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    PRIMARY KEY(job_id,attempt)
) STRICT;
CREATE TABLE source_repositories(
source_id TEXT NOT NULL REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, first_seen_us INTEGER, last_seen_us INTEGER, PRIMARY KEY(source_id,repository_uuidv4),
    CHECK(first_seen_us IS NULL OR last_seen_us IS NULL OR first_seen_us<=last_seen_us)
) STRICT;
CREATE TABLE inventory_observations(parsed_result_uuidv4 TEXT NOT NULL, source_registration_uuidv4 TEXT NOT NULL,

inventory_observation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, asserted_state TEXT NOT NULL CHECK(asserted_state IN ('complete','partial','unknown')), scope TEXT NOT NULL CHECK(json_valid(scope) AND json_type(scope)='object'), observed_at_us INTEGER, reason TEXT,
FOREIGN KEY(parsed_result_uuidv4,source_registration_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,source_registration_uuidv4), FOREIGN KEY(source_id,source_registration_uuidv4) REFERENCES sources(source_id,source_registration_uuidv4)
) STRICT;
CREATE TABLE jobs(
job_id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('discover','sync','hydrate','index','legacy')), request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'), current_attempt INTEGER, created_at_us INTEGER, FOREIGN KEY(job_id,current_attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE acquisition_progress(
git_acquisition_id TEXT PRIMARY KEY REFERENCES git_acquisitions(git_acquisition_id) ON UPDATE RESTRICT ON DELETE RESTRICT, job_id TEXT NOT NULL, attempt INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('planned','fetching','refs_captured','published','failed','interrupted','unknown')), generation INTEGER NOT NULL CHECK(generation>=0), ended_at_us INTEGER, active_cache_entry_id TEXT REFERENCES active_cache_entries(active_cache_entry_id) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE collection_progress(
fetch_collection_id TEXT PRIMARY KEY REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, job_id TEXT NOT NULL, attempt INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('running','partial','complete','failed','interrupted','unknown')), cursor TEXT, reason TEXT, FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE resume_scopes(
resume_scope_id TEXT PRIMARY KEY, repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, repository_binding_id TEXT, source_id TEXT REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, principal_ref TEXT, api_version TEXT, endpoint TEXT, request_context TEXT NOT NULL CHECK(json_valid(request_context) AND json_type(request_context)='object'), parser_version TEXT NOT NULL, profile_version TEXT NOT NULL, confidence TEXT NOT NULL CHECK(confidence IN ('proven','legacy_unknown')), UNIQUE(resume_scope_id,repository_uuidv4), FOREIGN KEY(repository_binding_id,repository_uuidv4) REFERENCES repository_bindings(repository_binding_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE stored_bytes(
sha256 BLOB PRIMARY KEY CHECK(length(sha256)=32), body BLOB NOT NULL,
    byte_length INTEGER NOT NULL CHECK(byte_length>=0 AND byte_length=length(body))
) STRICT;
CREATE TABLE payloads(
representation TEXT NOT NULL CHECK(representation IN ('decoded_api','legacy_normalized','git-object-raw-v1')),
    sha256 BLOB NOT NULL REFERENCES stored_bytes(sha256) ON UPDATE RESTRICT ON DELETE RESTRICT,
    PRIMARY KEY(representation,sha256)
) STRICT;
CREATE TABLE fetch_occurrences(fetch_occurrence_uuidv4 TEXT NOT NULL UNIQUE, repository_uuidv4 TEXT NOT NULL,

fetch_occurrence_id INTEGER PRIMARY KEY, fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, ordinal INTEGER NOT NULL CHECK(ordinal>=0), payload_representation TEXT NOT NULL, payload_sha256 BLOB NOT NULL, request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'), next_cursor TEXT, observed_at_us INTEGER, parsed_at_us INTEGER NOT NULL, UNIQUE(fetch_occurrence_id,fetch_collection_id),
    FOREIGN KEY(payload_representation,payload_sha256) REFERENCES payloads(representation,sha256) ON UPDATE RESTRICT ON DELETE RESTRICT,
UNIQUE(fetch_occurrence_uuidv4,repository_uuidv4), UNIQUE(fetch_occurrence_id,repository_uuidv4), FOREIGN KEY(fetch_collection_id,repository_uuidv4) REFERENCES fetch_collections(fetch_collection_id,repository_uuidv4)
) STRICT;
CREATE TABLE collection_memberships(
    fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    change_request_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    provider_change_request_document_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    PRIMARY KEY(fetch_collection_id,change_request_id,kind,provider_change_request_document_id),
    FOREIGN KEY(change_request_id,kind,provider_change_request_document_id) REFERENCES documents(change_request_id,kind,provider_change_request_document_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE unresolved_payloads(stored_sha256 BLOB REFERENCES stored_bytes(sha256), detected_at_us INTEGER, diagnostic_json TEXT CHECK(diagnostic_json IS NULL OR (json_valid(diagnostic_json) AND json_type(diagnostic_json)='object')),

unresolved_payload_id INTEGER PRIMARY KEY, payload_representation TEXT, payload_sha256 BLOB, reason TEXT NOT NULL CHECK(length(reason)>0),
    CHECK((payload_representation IS NULL)=(payload_sha256 IS NULL)),
    FOREIGN KEY(payload_representation,payload_sha256) REFERENCES payloads(representation,sha256) ON UPDATE RESTRICT ON DELETE RESTRICT,
CHECK((stored_sha256 IS NULL AND detected_at_us IS NULL AND diagnostic_json IS NULL) OR (stored_sha256 IS NOT NULL AND payload_representation IS NULL AND payload_sha256 IS NULL AND reason='physical_corruption' AND detected_at_us IS NOT NULL AND diagnostic_json IS NOT NULL))
) STRICT;
CREATE TABLE validators(
resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, validator_key TEXT NOT NULL, etag TEXT NOT NULL, payload_representation TEXT NOT NULL, payload_sha256 BLOB NOT NULL, validated_at_us INTEGER, PRIMARY KEY(resume_scope_id,validator_key),
    FOREIGN KEY(payload_representation,payload_sha256) REFERENCES payloads(representation,sha256) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE incremental_scans(
incremental_scan_id TEXT PRIMARY KEY, resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, scan_started_at_us INTEGER, safe_watermark_us INTEGER, evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object'), UNIQUE(incremental_scan_id,resume_scope_id)
) STRICT;
CREATE TABLE resume_cursors(
resume_scope_id TEXT PRIMARY KEY REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, incremental_scan_id TEXT, next_cursor TEXT, reusable INTEGER NOT NULL CHECK(reusable IN (0,1)), FOREIGN KEY(incremental_scan_id,resume_scope_id) REFERENCES incremental_scans(incremental_scan_id,resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE completion_markers(
completion_marker_uuidv4 TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',(random() & 3)+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
completion_marker_id INTEGER PRIMARY KEY, resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, asserted_state TEXT NOT NULL CHECK(asserted_state IN ('complete','partial','unknown')), evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object'), observed_at_us INTEGER
) STRICT;
CREATE TABLE coverage_scopes(
coverage_scope_id TEXT PRIMARY KEY,
    repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
    change_request_id TEXT, kind TEXT NOT NULL,
    FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE UNIQUE INDEX coverage_scope_repository_kind ON coverage_scopes(repository_uuidv4,kind) WHERE change_request_id IS NULL;
CREATE UNIQUE INDEX coverage_scope_change_request_kind ON coverage_scopes(change_request_id,kind) WHERE change_request_id IS NOT NULL;
CREATE TABLE coverage_claims(
coverage_claim_id INTEGER PRIMARY KEY,
    coverage_scope_id TEXT NOT NULL REFERENCES coverage_scopes(coverage_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    coverage_state TEXT NOT NULL CHECK(coverage_state IN ('complete','partial','unknown','not_applicable')),
    observed_at_us INTEGER NOT NULL,
    details_json TEXT CHECK(details_json IS NULL OR (json_valid(details_json) AND json_type(details_json)='object')),
    UNIQUE(coverage_scope_id,observed_at_us,coverage_state)
) STRICT;
-- Pick the latest observation first, including unknown. Older facts never provide
-- fallback from a latest unknown/conflict. Empty scopes have no invented claim.
CREATE VIEW current_coverage AS
SELECT s.coverage_scope_id,s.repository_uuidv4,s.change_request_id,s.kind,
       max(c.observed_at_us) AS observed_at_us,
       CASE WHEN count(b.coverage_claim_id)>0 THEN 'conflict'
            WHEN count(DISTINCT CASE WHEN c.coverage_state!='unknown' THEN c.coverage_state END)>1 THEN 'conflict'
            ELSE coalesce(max(CASE WHEN c.coverage_state!='unknown' THEN c.coverage_state END),'unknown') END AS coverage_state,
       count(c.coverage_claim_id) AS claim_count
FROM coverage_scopes s
LEFT JOIN coverage_claims c ON c.coverage_scope_id=s.coverage_scope_id
 AND c.observed_at_us=(SELECT max(latest.observed_at_us) FROM coverage_claims latest WHERE latest.coverage_scope_id=s.coverage_scope_id)
LEFT JOIN exchange_blocked_coverage_claims b ON b.coverage_claim_id=c.coverage_claim_id
GROUP BY s.coverage_scope_id;
CREATE TABLE reviews(
 change_request_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind='review'),
 provider_change_request_document_id TEXT NOT NULL,
 PRIMARY KEY(change_request_id,kind,provider_change_request_document_id),
 FOREIGN KEY(change_request_id,kind,provider_change_request_document_id) REFERENCES documents(change_request_id,kind,provider_change_request_document_id)
) STRICT;
CREATE TABLE change_request_events(
origin_fetch_occurrence_uuidv4 TEXT,change_request_event_uuidv4 TEXT NOT NULL UNIQUE, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL,

change_request_event_id INTEGER PRIMARY KEY, change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT, origin_key TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal>=0), provider_event_id TEXT, payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), observed_at_us INTEGER,
FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4),
FOREIGN KEY(origin_fetch_occurrence_uuidv4,repository_uuidv4) REFERENCES fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4)
) STRICT;
CREATE TABLE code_listing_progress(
code_listing_id TEXT PRIMARY KEY REFERENCES code_listings(code_listing_id) ON UPDATE RESTRICT ON DELETE RESTRICT, state TEXT NOT NULL CHECK(state IN ('partial','complete','unknown')), terminal INTEGER NOT NULL CHECK(terminal IN (0,1)), page_count INTEGER NOT NULL CHECK(page_count>=0), context_proven INTEGER NOT NULL CHECK(context_proven IN (0,1)), CHECK(state!='complete' OR (terminal=1 AND context_proven=1))
) STRICT;
CREATE TABLE code_commits(parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL,

code_listing_id TEXT NOT NULL REFERENCES code_listings(code_listing_id) ON UPDATE RESTRICT ON DELETE RESTRICT, fetch_occurrence_id INTEGER NOT NULL REFERENCES fetch_occurrences(fetch_occurrence_id) ON UPDATE RESTRICT ON DELETE RESTRICT, position INTEGER NOT NULL CHECK(position>=0), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), PRIMARY KEY(code_listing_id,fetch_occurrence_id,position,parsed_result_uuidv4),
FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4), FOREIGN KEY(fetch_occurrence_id,repository_uuidv4) REFERENCES fetch_occurrences(fetch_occurrence_id,repository_uuidv4)
) STRICT;
CREATE TABLE code_file_changes(parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL,

code_listing_id TEXT NOT NULL REFERENCES code_listings(code_listing_id) ON UPDATE RESTRICT ON DELETE RESTRICT, fetch_occurrence_id INTEGER NOT NULL REFERENCES fetch_occurrences(fetch_occurrence_id) ON UPDATE RESTRICT ON DELETE RESTRICT, position INTEGER NOT NULL CHECK(position>=0), raw_path BLOB NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), PRIMARY KEY(code_listing_id,fetch_occurrence_id,position,parsed_result_uuidv4),
FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4), FOREIGN KEY(fetch_occurrence_id,repository_uuidv4) REFERENCES fetch_occurrences(fetch_occurrence_id,repository_uuidv4)
) STRICT;
CREATE TABLE code_acquisitions(
code_observation_id INTEGER NOT NULL REFERENCES code_observations(code_observation_id) ON UPDATE RESTRICT ON DELETE RESTRICT, role TEXT NOT NULL CHECK(length(role)>0), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), acquisition_root_id INTEGER REFERENCES acquisition_roots(acquisition_root_id) ON UPDATE RESTRICT ON DELETE RESTRICT, PRIMARY KEY(code_observation_id,role)
) STRICT;
CREATE TABLE git_objects(
git_object_id INTEGER PRIMARY KEY, object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), type TEXT NOT NULL CHECK(type IN ('commit','tree','blob','tag')), size INTEGER NOT NULL CHECK(size>=0), verified INTEGER NOT NULL CHECK(verified IN (0,1)), UNIQUE(object_format,oid)
) STRICT;
CREATE TABLE commits(
git_fact_uuidv4 TEXT PRIMARY KEY NOT NULL, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL, git_acquisition_id TEXT NOT NULL,
git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id), tree_git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id), raw_headers BLOB NOT NULL, raw_message BLOB NOT NULL, message_text TEXT NOT NULL, metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), UNIQUE(parsed_result_uuidv4,git_object_id), UNIQUE(parsed_result_uuidv4,repository_uuidv4,git_object_id), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4), FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4), FOREIGN KEY(repository_uuidv4,git_object_id,git_acquisition_id) REFERENCES repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id), FOREIGN KEY(repository_uuidv4,tree_git_object_id,git_acquisition_id) REFERENCES repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id)
) STRICT;
CREATE TABLE commit_parents(
git_fact_uuidv4 TEXT PRIMARY KEY NOT NULL, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL, git_acquisition_id TEXT NOT NULL,
commit_git_object_id INTEGER NOT NULL, parent_ordinal INTEGER NOT NULL CHECK(parent_ordinal>=0), parent_git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id), UNIQUE(parsed_result_uuidv4,commit_git_object_id,parent_ordinal), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4), FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4,commit_git_object_id) REFERENCES commits(parsed_result_uuidv4,repository_uuidv4,git_object_id), FOREIGN KEY(repository_uuidv4,parent_git_object_id,git_acquisition_id) REFERENCES repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id)
) STRICT;
CREATE TABLE tree_entries(
git_fact_uuidv4 TEXT PRIMARY KEY NOT NULL, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL, git_acquisition_id TEXT NOT NULL,
tree_git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id), raw_name BLOB NOT NULL CHECK(length(raw_name)>0), decoded_name TEXT NOT NULL, mode INTEGER NOT NULL CHECK(mode IN (16384,33188,33261,40960,57344)), child_format TEXT NOT NULL CHECK(child_format IN ('sha1','sha256')), child_oid BLOB NOT NULL CHECK((child_format='sha1' AND length(child_oid)=20) OR (child_format='sha256' AND length(child_oid)=32)), child_git_object_id INTEGER REFERENCES git_objects(git_object_id), UNIQUE(parsed_result_uuidv4,tree_git_object_id,raw_name), CHECK((mode=57344 AND child_git_object_id IS NULL) OR (mode!=57344 AND child_git_object_id IS NOT NULL)), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4), FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4), FOREIGN KEY(repository_uuidv4,tree_git_object_id,git_acquisition_id) REFERENCES repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id), FOREIGN KEY(repository_uuidv4,child_git_object_id,git_acquisition_id) REFERENCES repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id)
) STRICT;
CREATE TABLE tag_objects(
git_fact_uuidv4 TEXT PRIMARY KEY NOT NULL, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL, git_acquisition_id TEXT NOT NULL,
git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id), target_git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id), raw_payload BLOB NOT NULL, UNIQUE(parsed_result_uuidv4,git_object_id), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4), FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4), FOREIGN KEY(repository_uuidv4,git_object_id,git_acquisition_id) REFERENCES repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id), FOREIGN KEY(repository_uuidv4,target_git_object_id,git_acquisition_id) REFERENCES repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id)
) STRICT;
CREATE TABLE contents(
content_id INTEGER PRIMARY KEY, byte_length INTEGER NOT NULL CHECK(byte_length>=0), created_at_us INTEGER
) STRICT;
CREATE TABLE content_digests(
content_id INTEGER NOT NULL REFERENCES contents(content_id) ON UPDATE RESTRICT ON DELETE RESTRICT, representation TEXT NOT NULL CHECK(representation='raw-content-v1'), algorithm TEXT NOT NULL CHECK(algorithm IN ('md5','sha1','sha256')), digest BLOB NOT NULL CHECK((algorithm='md5' AND length(digest)=16) OR (algorithm='sha1' AND length(digest)=20) OR (algorithm='sha256' AND length(digest)=32)), verified_at_us INTEGER, pipeline_version TEXT NOT NULL, PRIMARY KEY(content_id,representation,algorithm)
) STRICT;
CREATE TABLE blob_content_map(
git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, content_id INTEGER NOT NULL REFERENCES contents(content_id) ON UPDATE RESTRICT ON DELETE RESTRICT, git_acquisition_id TEXT NOT NULL REFERENCES git_acquisitions(git_acquisition_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE repository_object_sources(
repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, git_acquisition_id TEXT NOT NULL, PRIMARY KEY(repository_uuidv4,git_object_id,git_acquisition_id), FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE ref_observations(
parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL,
snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_ref_name BLOB NOT NULL CHECK(length(raw_ref_name)>0), kind TEXT NOT NULL CHECK(kind IN ('head','tag','other')), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), target_oid BLOB NOT NULL CHECK((object_format='sha1' AND length(target_oid)=20) OR (object_format='sha256' AND length(target_oid)=32)), peeled_oid BLOB, target_type TEXT CHECK(target_type IN ('commit','tree','blob','tag')), PRIMARY KEY(snapshot_id,raw_ref_name), CHECK(peeled_oid IS NULL OR length(peeled_oid)=length(target_oid)),
FOREIGN KEY(snapshot_id,repository_uuidv4,parsed_result_uuidv4) REFERENCES snapshots(snapshot_id,repository_uuidv4,parsed_result_uuidv4), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4)
) STRICT;
CREATE TABLE root_manifests(
git_fact_uuidv4 TEXT PRIMARY KEY NOT NULL, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL, git_acquisition_id TEXT NOT NULL,
tree_git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id), complete INTEGER NOT NULL CHECK(complete IN (0,1)), UNIQUE(parsed_result_uuidv4,tree_git_object_id), UNIQUE(parsed_result_uuidv4,repository_uuidv4,tree_git_object_id), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4), FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4), FOREIGN KEY(repository_uuidv4,tree_git_object_id,git_acquisition_id) REFERENCES repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id)
) STRICT;
CREATE TABLE root_manifest_entries(
git_fact_uuidv4 TEXT PRIMARY KEY NOT NULL, parsed_result_uuidv4 TEXT NOT NULL, repository_uuidv4 TEXT NOT NULL, git_acquisition_id TEXT NOT NULL,
tree_git_object_id INTEGER NOT NULL, raw_path BLOB NOT NULL, decoded_path TEXT NOT NULL, mode INTEGER NOT NULL CHECK(mode IN (33188,33261,40960,57344)), git_object_id INTEGER REFERENCES git_objects(git_object_id), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), UNIQUE(parsed_result_uuidv4,tree_git_object_id,raw_path), CHECK((mode=57344 AND git_object_id IS NULL) OR (mode!=57344 AND git_object_id IS NOT NULL)), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4), FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4), FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4,tree_git_object_id) REFERENCES root_manifests(parsed_result_uuidv4,repository_uuidv4,tree_git_object_id), FOREIGN KEY(repository_uuidv4,git_object_id,git_acquisition_id) REFERENCES repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id)
) STRICT;
CREATE TABLE cache_locators(
cache_locator_id TEXT PRIMARY KEY, repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, path TEXT NOT NULL, access TEXT NOT NULL CHECK(access IN ('source_readonly','target_active')), state TEXT NOT NULL CHECK(state IN ('available','missing','unknown')), UNIQUE(cache_locator_id,repository_uuidv4)
) STRICT;
CREATE TABLE content_locations(
content_id INTEGER NOT NULL REFERENCES contents(content_id) ON UPDATE RESTRICT ON DELETE RESTRICT, kind TEXT NOT NULL CHECK(kind IN ('durable-content','cache','legacy')), locator TEXT NOT NULL, cache_locator_id TEXT REFERENCES cache_locators(cache_locator_id) ON UPDATE RESTRICT ON DELETE RESTRICT, state TEXT NOT NULL CHECK(state IN ('available','unavailable','unknown')), PRIMARY KEY(content_id,kind,locator)
) STRICT;
CREATE TABLE active_cache_entries(
active_cache_entry_id TEXT PRIMARY KEY, cache_locator_id TEXT NOT NULL REFERENCES cache_locators(cache_locator_id) ON UPDATE RESTRICT ON DELETE RESTRICT, generation INTEGER NOT NULL CHECK(generation>=0), state TEXT NOT NULL CHECK(state IN ('active','evicting','evicted')), last_used_us INTEGER NOT NULL, bytes INTEGER NOT NULL CHECK(bytes>=0)
) STRICT;
CREATE TABLE cache_leases(
active_cache_entry_id TEXT NOT NULL REFERENCES active_cache_entries(active_cache_entry_id) ON UPDATE RESTRICT ON DELETE RESTRICT, job_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>=1), acquired_at_us INTEGER NOT NULL, PRIMARY KEY(active_cache_entry_id,job_id,attempt), FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE space_reservations(
job_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>=1), reserved INTEGER NOT NULL CHECK(reserved>=0), consumed INTEGER NOT NULL CHECK(consumed>=0), PRIMARY KEY(job_id,attempt), FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE preservation_obligations(
git_acquisition_id TEXT PRIMARY KEY REFERENCES git_acquisitions(git_acquisition_id) ON UPDATE RESTRICT ON DELETE RESTRICT, cache_locator_id TEXT REFERENCES cache_locators(cache_locator_id) ON UPDATE RESTRICT ON DELETE RESTRICT, roots_fixed INTEGER NOT NULL CHECK(roots_fixed IN (0,1)), structure_done INTEGER NOT NULL CHECK(structure_done IN (0,1)), digest_done INTEGER NOT NULL CHECK(digest_done IN (0,1)), text_done INTEGER NOT NULL CHECK(text_done IN (0,1)), published INTEGER NOT NULL CHECK(published IN (0,1))
) STRICT;
CREATE TABLE search_documents(
search_document_id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('code','pr','commits')), source_key TEXT NOT NULL, body TEXT NOT NULL, metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), UNIQUE(kind,source_key)
) STRICT;
CREATE TABLE index_generations(
index_generation_id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('code','pr','commits')), state TEXT NOT NULL CHECK(state IN ('building','ready','retired','removed','unavailable','failed')), table_name TEXT NOT NULL CHECK(length(table_name)>0 AND table_name NOT GLOB '*[^a-z0-9_]*'), target_max_search_document_id INTEGER NOT NULL CHECK(target_max_search_document_id>=0), created_at_us INTEGER
) STRICT;
CREATE TABLE index_membership(
index_generation_id INTEGER NOT NULL REFERENCES index_generations(index_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT, search_document_id INTEGER NOT NULL REFERENCES search_documents(search_document_id) ON UPDATE RESTRICT ON DELETE RESTRICT, input_version TEXT NOT NULL, PRIMARY KEY(index_generation_id,search_document_id)
) STRICT;
CREATE TRIGGER acquisition_progress_immutable BEFORE UPDATE ON acquisition_progress WHEN NEW.git_acquisition_id IS NOT OLD.git_acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER acquisition_progress_no_replace BEFORE INSERT ON acquisition_progress WHEN EXISTS(SELECT 1 FROM acquisition_progress WHERE (git_acquisition_id=NEW.git_acquisition_id) OR (git_acquisition_id=NEW.git_acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX acquisition_progress_fk_0 ON acquisition_progress(job_id,attempt);
CREATE TRIGGER acquisition_roots_immutable BEFORE UPDATE ON acquisition_roots WHEN NEW.acquisition_root_id IS NOT OLD.acquisition_root_id OR NEW.git_acquisition_id IS NOT OLD.git_acquisition_id OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.role IS NOT OLD.role OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.expected_oid IS NOT OLD.expected_oid OR (OLD.published=1 AND NEW.published!=1) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER acquisition_roots_no_replace BEFORE INSERT ON acquisition_roots WHEN EXISTS(SELECT 1 FROM acquisition_roots WHERE (acquisition_root_id=NEW.acquisition_root_id) OR (git_acquisition_id=NEW.git_acquisition_id AND object_format=NEW.object_format AND oid=NEW.oid AND role=NEW.role) OR (acquisition_root_id=NEW.acquisition_root_id AND repository_uuidv4=NEW.repository_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER acquisition_roots_retain BEFORE DELETE ON acquisition_roots BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX acquisition_roots_fk_0 ON acquisition_roots(git_acquisition_id,repository_uuidv4);
CREATE TRIGGER active_cache_entries_immutable BEFORE UPDATE ON active_cache_entries WHEN NEW.active_cache_entry_id IS NOT OLD.active_cache_entry_id OR NEW.cache_locator_id IS NOT OLD.cache_locator_id OR NEW.generation IS NOT OLD.generation BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER active_cache_entries_no_replace BEFORE INSERT ON active_cache_entries WHEN EXISTS(SELECT 1 FROM active_cache_entries WHERE (active_cache_entry_id=NEW.active_cache_entry_id) OR (active_cache_entry_id=NEW.active_cache_entry_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX active_cache_entries_fk_0 ON active_cache_entries(cache_locator_id);
CREATE TRIGGER blob_content_map_immutable BEFORE UPDATE ON blob_content_map WHEN NEW.git_object_id IS NOT OLD.git_object_id OR NEW.content_id IS NOT OLD.content_id OR NEW.git_acquisition_id IS NOT OLD.git_acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER blob_content_map_no_replace BEFORE INSERT ON blob_content_map WHEN EXISTS(SELECT 1 FROM blob_content_map WHERE (git_object_id=NEW.git_object_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER blob_content_map_retain BEFORE DELETE ON blob_content_map BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX blob_content_map_fk_0 ON blob_content_map(git_acquisition_id);
CREATE INDEX blob_content_map_fk_1 ON blob_content_map(content_id);
CREATE TRIGGER cache_leases_immutable BEFORE UPDATE ON cache_leases WHEN NEW.active_cache_entry_id IS NOT OLD.active_cache_entry_id OR NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER cache_leases_no_replace BEFORE INSERT ON cache_leases WHEN EXISTS(SELECT 1 FROM cache_leases WHERE (active_cache_entry_id=NEW.active_cache_entry_id AND job_id=NEW.job_id AND attempt=NEW.attempt) OR (active_cache_entry_id=NEW.active_cache_entry_id AND job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX cache_leases_fk_0 ON cache_leases(job_id,attempt);
CREATE TRIGGER cache_locators_immutable BEFORE UPDATE ON cache_locators WHEN NEW.cache_locator_id IS NOT OLD.cache_locator_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.access IS NOT OLD.access BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER cache_locators_no_replace BEFORE INSERT ON cache_locators WHEN EXISTS(SELECT 1 FROM cache_locators WHERE (cache_locator_id=NEW.cache_locator_id) OR (cache_locator_id=NEW.cache_locator_id AND repository_uuidv4=NEW.repository_uuidv4) OR (cache_locator_id=NEW.cache_locator_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX cache_locators_fk_0 ON cache_locators(repository_uuidv4);
CREATE TRIGGER change_request_events_no_replace BEFORE INSERT ON change_request_events WHEN EXISTS(SELECT 1 FROM change_request_events WHERE (change_request_event_id=NEW.change_request_event_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER change_request_events_retain BEFORE DELETE ON change_request_events BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX change_request_events_fk_0 ON change_request_events(change_request_id);
CREATE TRIGGER change_request_observations_no_replace BEFORE INSERT ON change_request_observations WHEN EXISTS(SELECT 1 FROM change_request_observations WHERE (change_request_observation_id=NEW.change_request_observation_id) OR (change_request_observation_id=NEW.change_request_observation_id AND change_request_id=NEW.change_request_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER change_request_observations_retain BEFORE DELETE ON change_request_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX change_request_observations_fk_0 ON change_request_observations(origin_fetch_occurrence_id);
CREATE INDEX change_request_observations_fk_1 ON change_request_observations(change_request_id);
CREATE TRIGGER change_requests_immutable BEFORE UPDATE ON change_requests WHEN NEW.change_request_id IS NOT OLD.change_request_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.repository_binding_id IS NOT OLD.repository_binding_id OR NEW.change_request_kind IS NOT OLD.change_request_kind OR NEW.provider_change_request_number IS NOT OLD.provider_change_request_number BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER change_requests_no_replace BEFORE INSERT ON change_requests WHEN EXISTS(SELECT 1 FROM change_requests WHERE (change_request_id=NEW.change_request_id) OR (change_request_id=NEW.change_request_id AND repository_uuidv4=NEW.repository_uuidv4) OR (repository_binding_id=NEW.repository_binding_id AND change_request_kind=NEW.change_request_kind AND provider_change_request_number=NEW.provider_change_request_number) OR (change_request_id=NEW.change_request_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX change_requests_fk_1 ON change_requests(repository_binding_id,repository_uuidv4);
CREATE TRIGGER code_acquisitions_immutable BEFORE UPDATE ON code_acquisitions WHEN NEW.code_observation_id IS NOT OLD.code_observation_id OR NEW.role IS NOT OLD.role OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.acquisition_root_id IS NOT OLD.acquisition_root_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_acquisitions_no_replace BEFORE INSERT ON code_acquisitions WHEN EXISTS(SELECT 1 FROM code_acquisitions WHERE (code_observation_id=NEW.code_observation_id AND role=NEW.role) OR (code_observation_id=NEW.code_observation_id AND role=NEW.role)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_acquisitions_retain BEFORE DELETE ON code_acquisitions BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_acquisitions_fk_0 ON code_acquisitions(acquisition_root_id);
CREATE TRIGGER code_commits_no_replace BEFORE INSERT ON code_commits WHEN EXISTS(SELECT 1 FROM code_commits WHERE code_listing_id=NEW.code_listing_id AND fetch_occurrence_id=NEW.fetch_occurrence_id AND position=NEW.position AND parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable fact duplicate'); END;
CREATE TRIGGER code_commits_retain BEFORE DELETE ON code_commits BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_commits_fk_0 ON code_commits(fetch_occurrence_id);
CREATE TRIGGER code_file_changes_no_replace BEFORE INSERT ON code_file_changes WHEN EXISTS(SELECT 1 FROM code_file_changes WHERE code_listing_id=NEW.code_listing_id AND fetch_occurrence_id=NEW.fetch_occurrence_id AND position=NEW.position AND parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable fact duplicate'); END;
CREATE TRIGGER code_file_changes_retain BEFORE DELETE ON code_file_changes BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_file_changes_fk_0 ON code_file_changes(fetch_occurrence_id);
CREATE TRIGGER code_listing_progress_immutable BEFORE UPDATE ON code_listing_progress WHEN NEW.code_listing_id IS NOT OLD.code_listing_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_listing_progress_no_replace BEFORE INSERT ON code_listing_progress WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE (code_listing_id=NEW.code_listing_id) OR (code_listing_id=NEW.code_listing_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_listings_immutable BEFORE UPDATE ON code_listings WHEN NEW.code_listing_id IS NOT OLD.code_listing_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.kind IS NOT OLD.kind OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.object_format IS NOT OLD.object_format OR NEW.head_oid IS NOT OLD.head_oid OR NEW.base_oid IS NOT OLD.base_oid BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_listings_no_replace BEFORE INSERT ON code_listings WHEN EXISTS(SELECT 1 FROM code_listings WHERE (code_listing_id=NEW.code_listing_id) OR (code_listing_id=NEW.code_listing_id AND change_request_id=NEW.change_request_id) OR (fetch_collection_id=NEW.fetch_collection_id AND kind=NEW.kind) OR (code_listing_id=NEW.code_listing_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_listings_retain BEFORE DELETE ON code_listings BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_listings_fk_0 ON code_listings(fetch_collection_id,change_request_id);
CREATE INDEX code_listings_fk_1 ON code_listings(resume_scope_id);
CREATE TRIGGER code_observations_no_replace BEFORE INSERT ON code_observations WHEN EXISTS(SELECT 1 FROM code_observations WHERE (code_observation_id=NEW.code_observation_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_observations_retain BEFORE DELETE ON code_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_observations_fk_0 ON code_observations(file_code_listing_id,change_request_id);
CREATE INDEX code_observations_fk_1 ON code_observations(commit_code_listing_id,change_request_id);
CREATE INDEX code_observations_fk_2 ON code_observations(change_request_observation_id,change_request_id);
CREATE TRIGGER collection_progress_immutable BEFORE UPDATE ON collection_progress WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER collection_progress_no_replace BEFORE INSERT ON collection_progress WHEN EXISTS(SELECT 1 FROM collection_progress WHERE (fetch_collection_id=NEW.fetch_collection_id) OR (fetch_collection_id=NEW.fetch_collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX collection_progress_fk_0 ON collection_progress(job_id,attempt);
CREATE INDEX commit_parents_fk_0 ON commit_parents(parent_git_object_id);
CREATE INDEX commits_fk_0 ON commits(tree_git_object_id);
CREATE TRIGGER completion_markers_immutable BEFORE UPDATE ON completion_markers WHEN NEW.completion_marker_uuidv4 IS NOT OLD.completion_marker_uuidv4 OR NEW.completion_marker_id IS NOT OLD.completion_marker_id OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.asserted_state IS NOT OLD.asserted_state OR NEW.evidence IS NOT OLD.evidence OR NEW.observed_at_us IS NOT OLD.observed_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER completion_markers_no_replace BEFORE INSERT ON completion_markers WHEN EXISTS(SELECT 1 FROM completion_markers WHERE (completion_marker_id=NEW.completion_marker_id OR completion_marker_uuidv4=NEW.completion_marker_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER completion_markers_retain BEFORE DELETE ON completion_markers BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX completion_markers_fk_0 ON completion_markers(fetch_collection_id);
CREATE INDEX completion_markers_fk_1 ON completion_markers(resume_scope_id);
CREATE TRIGGER content_digests_immutable BEFORE UPDATE ON content_digests WHEN NEW.content_id IS NOT OLD.content_id OR NEW.representation IS NOT OLD.representation OR NEW.algorithm IS NOT OLD.algorithm OR NEW.digest IS NOT OLD.digest OR NEW.verified_at_us IS NOT OLD.verified_at_us OR NEW.pipeline_version IS NOT OLD.pipeline_version BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER content_digests_no_replace BEFORE INSERT ON content_digests WHEN EXISTS(SELECT 1 FROM content_digests WHERE (content_id=NEW.content_id AND representation=NEW.representation AND algorithm=NEW.algorithm) OR (content_id=NEW.content_id AND representation=NEW.representation AND algorithm=NEW.algorithm)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER content_digests_retain BEFORE DELETE ON content_digests BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER content_locations_immutable BEFORE UPDATE ON content_locations WHEN NEW.content_id IS NOT OLD.content_id OR NEW.kind IS NOT OLD.kind OR NEW.locator IS NOT OLD.locator BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER content_locations_no_replace BEFORE INSERT ON content_locations WHEN EXISTS(SELECT 1 FROM content_locations WHERE (content_id=NEW.content_id AND kind=NEW.kind AND locator=NEW.locator) OR (content_id=NEW.content_id AND kind=NEW.kind AND locator=NEW.locator)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX content_locations_fk_0 ON content_locations(cache_locator_id);
-- Only missing eligible text may be filled. The admission must hash supplied local
-- bytes against all saved raw-content-v1 digests before this UPDATE; SQL checks
-- the SHA-256 anchor exists, byte length (CHECK), NUL policy and write-once shape.
CREATE TRIGGER coverage_claims_immutable BEFORE UPDATE ON coverage_claims BEGIN SELECT RAISE(ABORT,'Immutable coverage claim'); END;
-- An unassigned INTEGER PRIMARY KEY can appear as -1 in BEFORE INSERT, so only
-- the semantic key is tested here. SQLite enforces explicit ID uniqueness;
-- retain rejects REPLACE's delete with required recursive_triggers enabled, and
-- immutable rejects every UPDATE, including a no-op ON CONFLICT DO UPDATE.
CREATE TRIGGER coverage_claims_no_replace BEFORE INSERT ON coverage_claims WHEN EXISTS(SELECT 1 FROM coverage_claims WHERE coverage_scope_id=NEW.coverage_scope_id AND observed_at_us=NEW.observed_at_us AND coverage_state=NEW.coverage_state) BEGIN SELECT RAISE(ABORT,'Duplicate coverage claim; use admission'); END;
CREATE TRIGGER coverage_claims_retain BEFORE DELETE ON coverage_claims BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX coverage_claims_fk_0 ON coverage_claims(coverage_scope_id);
CREATE TRIGGER coverage_scopes_immutable BEFORE UPDATE ON coverage_scopes WHEN NEW.coverage_scope_id IS NOT OLD.coverage_scope_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER coverage_scopes_no_replace BEFORE INSERT ON coverage_scopes WHEN EXISTS(SELECT 1 FROM coverage_scopes WHERE coverage_scope_id=NEW.coverage_scope_id OR (repository_uuidv4=NEW.repository_uuidv4 AND change_request_id IS NEW.change_request_id AND kind=NEW.kind)) BEGIN SELECT RAISE(ABORT,'Duplicate coverage scope'); END;
CREATE INDEX coverage_scopes_fk_1 ON coverage_scopes(change_request_id,repository_uuidv4);
CREATE INDEX coverage_scopes_fk_2 ON coverage_scopes(repository_uuidv4);
CREATE TRIGGER database_identity_immutable BEFORE UPDATE ON database_identity WHEN NEW.singleton IS NOT OLD.singleton OR NEW.format_id IS NOT OLD.format_id OR NEW.schema_version IS NOT OLD.schema_version OR NEW.ddl_sha256 IS NOT OLD.ddl_sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER database_identity_no_replace BEFORE INSERT ON database_identity WHEN EXISTS(SELECT 1 FROM database_identity WHERE (singleton=NEW.singleton)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
-- Remote observation replay and provider-resource relationships are hot per-comment
-- lookups. Keep them indexed as collections/history grow.
CREATE TRIGGER fetch_collections_immutable BEFORE UPDATE ON fetch_collections WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.source_id IS NOT OLD.source_id OR NEW.kind IS NOT OLD.kind OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.observed_at_us IS NOT OLD.observed_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER fetch_collections_no_replace BEFORE INSERT ON fetch_collections WHEN EXISTS(SELECT 1 FROM fetch_collections WHERE (fetch_collection_id=NEW.fetch_collection_id) OR (fetch_collection_id=NEW.fetch_collection_id AND change_request_id=NEW.change_request_id) OR (fetch_collection_id=NEW.fetch_collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER fetch_collections_retain BEFORE DELETE ON fetch_collections BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX fetch_collections_fk_0 ON fetch_collections(change_request_id,repository_uuidv4);
CREATE INDEX fetch_collections_fk_1 ON fetch_collections(resume_scope_id);
CREATE INDEX fetch_collections_fk_2 ON fetch_collections(source_id);
CREATE INDEX fetch_collections_fk_3 ON fetch_collections(repository_uuidv4);
CREATE TRIGGER fetch_occurrences_no_replace BEFORE INSERT ON fetch_occurrences WHEN EXISTS(SELECT 1 FROM fetch_occurrences WHERE (fetch_occurrence_id=NEW.fetch_occurrence_id) OR (fetch_occurrence_id=NEW.fetch_occurrence_id AND fetch_collection_id=NEW.fetch_collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER fetch_occurrences_retain BEFORE DELETE ON fetch_occurrences BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX fetch_occurrences_fk_0 ON fetch_occurrences(payload_representation,payload_sha256);
CREATE INDEX fetch_occurrences_fk_1 ON fetch_occurrences(fetch_collection_id);
CREATE TRIGGER git_acquisitions_immutable BEFORE UPDATE ON git_acquisitions WHEN NEW.git_acquisition_id IS NOT OLD.git_acquisition_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.repository_endpoint_id IS NOT OLD.repository_endpoint_id OR NEW.endpoint_url IS NOT OLD.endpoint_url OR (OLD.object_format IS NOT NULL AND NEW.object_format IS NOT OLD.object_format) OR (OLD.refs_observed_at_us IS NOT NULL AND NEW.refs_observed_at_us IS NOT OLD.refs_observed_at_us) OR NEW.source_id IS NOT OLD.source_id OR NEW.kind IS NOT OLD.kind OR NEW.started_at_us IS NOT OLD.started_at_us OR (OLD.observed_at_us IS NOT NULL AND NEW.observed_at_us IS NOT OLD.observed_at_us) OR NEW.request IS NOT OLD.request OR (OLD.roots_manifest IS NOT NULL AND NEW.roots_manifest IS NOT OLD.roots_manifest) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER git_acquisitions_no_replace BEFORE INSERT ON git_acquisitions WHEN EXISTS(SELECT 1 FROM git_acquisitions WHERE (git_acquisition_id=NEW.git_acquisition_id) OR (git_acquisition_id=NEW.git_acquisition_id AND repository_uuidv4=NEW.repository_uuidv4) OR (git_acquisition_id=NEW.git_acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER git_acquisitions_retain BEFORE DELETE ON git_acquisitions BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX git_acquisitions_fk_0 ON git_acquisitions(repository_endpoint_id,repository_uuidv4);
CREATE INDEX git_acquisitions_fk_1 ON git_acquisitions(source_id);
CREATE INDEX git_acquisitions_fk_2 ON git_acquisitions(repository_uuidv4);
-- verified is a monotonic result projection, not an immutable legacy assertion.
-- Setting 0 -> 1 requires admission to verify the local raw Git object bytes.
CREATE TRIGGER git_objects_immutable BEFORE UPDATE ON git_objects WHEN NEW.git_object_id IS NOT OLD.git_object_id OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.type IS NOT OLD.type OR NEW.size IS NOT OLD.size OR NEW.verified<OLD.verified BEGIN SELECT RAISE(ABORT,'Immutable Git identity or verification downgrade'); END;
CREATE TRIGGER git_objects_no_replace BEFORE INSERT ON git_objects WHEN EXISTS(SELECT 1 FROM git_objects WHERE (git_object_id=NEW.git_object_id) OR (object_format=NEW.object_format AND oid=NEW.oid)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER git_objects_retain BEFORE DELETE ON git_objects BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER incremental_scans_immutable BEFORE UPDATE ON incremental_scans WHEN NEW.incremental_scan_id IS NOT OLD.incremental_scan_id OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.scan_started_at_us IS NOT OLD.scan_started_at_us OR NEW.safe_watermark_us IS NOT OLD.safe_watermark_us OR NEW.evidence IS NOT OLD.evidence BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER incremental_scans_no_replace BEFORE INSERT ON incremental_scans WHEN EXISTS(SELECT 1 FROM incremental_scans WHERE (incremental_scan_id=NEW.incremental_scan_id) OR (incremental_scan_id=NEW.incremental_scan_id AND resume_scope_id=NEW.resume_scope_id) OR (incremental_scan_id=NEW.incremental_scan_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER incremental_scans_retain BEFORE DELETE ON incremental_scans BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX incremental_scans_fk_0 ON incremental_scans(fetch_collection_id);
CREATE INDEX incremental_scans_fk_1 ON incremental_scans(resume_scope_id);
CREATE TRIGGER index_generations_immutable BEFORE UPDATE ON index_generations WHEN NEW.index_generation_id IS NOT OLD.index_generation_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER index_generations_no_replace BEFORE INSERT ON index_generations WHEN EXISTS(SELECT 1 FROM index_generations WHERE (index_generation_id=NEW.index_generation_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER index_membership_immutable BEFORE UPDATE ON index_membership WHEN NEW.index_generation_id IS NOT OLD.index_generation_id OR NEW.search_document_id IS NOT OLD.search_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER index_membership_no_replace BEFORE INSERT ON index_membership WHEN EXISTS(SELECT 1 FROM index_membership WHERE (index_generation_id=NEW.index_generation_id AND search_document_id=NEW.search_document_id) OR (index_generation_id=NEW.index_generation_id AND search_document_id=NEW.search_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX index_membership_fk_0 ON index_membership(search_document_id);
CREATE TRIGGER inventory_observations_no_replace BEFORE INSERT ON inventory_observations WHEN EXISTS(SELECT 1 FROM inventory_observations WHERE (inventory_observation_id=NEW.inventory_observation_id) OR (inventory_observation_id=NEW.inventory_observation_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER inventory_observations_retain BEFORE DELETE ON inventory_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX inventory_observations_fk_0 ON inventory_observations(source_id);
CREATE TRIGGER job_attempts_immutable BEFORE UPDATE ON job_attempts WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER job_attempts_no_replace BEFORE INSERT ON job_attempts WHEN EXISTS(SELECT 1 FROM job_attempts WHERE (job_id=NEW.job_id AND attempt=NEW.attempt) OR (job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER jobs_immutable BEFORE UPDATE ON jobs WHEN NEW.job_id IS NOT OLD.job_id OR NEW.kind IS NOT OLD.kind OR NEW.request IS NOT OLD.request OR NEW.created_at_us IS NOT OLD.created_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER jobs_no_replace BEFORE INSERT ON jobs WHEN EXISTS(SELECT 1 FROM jobs WHERE (job_id=NEW.job_id) OR (job_id=NEW.job_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX jobs_fk_0 ON jobs(job_id,current_attempt);
CREATE TRIGGER stored_bytes_immutable BEFORE UPDATE ON stored_bytes BEGIN SELECT RAISE(ABORT,'Immutable stored bytes'); END;
CREATE TRIGGER stored_bytes_no_replace BEFORE INSERT ON stored_bytes WHEN EXISTS(SELECT 1 FROM stored_bytes WHERE sha256=NEW.sha256) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited'); END;
CREATE TRIGGER stored_bytes_retain BEFORE DELETE ON stored_bytes BEGIN SELECT RAISE(ABORT,'Retain acquired bytes'); END;
CREATE TRIGGER payloads_immutable BEFORE UPDATE ON payloads BEGIN SELECT RAISE(ABORT,'Immutable payload identity'); END;
CREATE TRIGGER payloads_no_replace BEFORE INSERT ON payloads WHEN EXISTS(SELECT 1 FROM payloads WHERE representation=NEW.representation AND sha256=NEW.sha256) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited'); END;
CREATE TRIGGER payloads_retain BEFORE DELETE ON payloads BEGIN SELECT RAISE(ABORT,'Retain acquired payloads'); END;
CREATE INDEX payloads_stored_bytes_fk ON payloads(sha256);
CREATE TRIGGER preservation_obligations_immutable BEFORE UPDATE ON preservation_obligations WHEN NEW.git_acquisition_id IS NOT OLD.git_acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER preservation_obligations_no_replace BEFORE INSERT ON preservation_obligations WHEN EXISTS(SELECT 1 FROM preservation_obligations WHERE (git_acquisition_id=NEW.git_acquisition_id) OR (git_acquisition_id=NEW.git_acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX preservation_obligations_fk_0 ON preservation_obligations(cache_locator_id);
CREATE TRIGGER ref_observations_immutable BEFORE UPDATE ON ref_observations WHEN NEW.snapshot_id IS NOT OLD.snapshot_id OR NEW.raw_ref_name IS NOT OLD.raw_ref_name OR NEW.kind IS NOT OLD.kind OR NEW.object_format IS NOT OLD.object_format OR NEW.target_oid IS NOT OLD.target_oid OR NEW.peeled_oid IS NOT OLD.peeled_oid OR NEW.target_type IS NOT OLD.target_type BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER ref_observations_no_replace BEFORE INSERT ON ref_observations WHEN EXISTS(SELECT 1 FROM ref_observations WHERE (snapshot_id=NEW.snapshot_id AND raw_ref_name=NEW.raw_ref_name) OR (snapshot_id=NEW.snapshot_id AND raw_ref_name=NEW.raw_ref_name)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER ref_observations_retain BEFORE DELETE ON ref_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER repositories_immutable BEFORE UPDATE ON repositories WHEN NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repositories_no_replace BEFORE INSERT ON repositories WHEN EXISTS(SELECT 1 FROM repositories WHERE (repository_uuidv4=NEW.repository_uuidv4) OR (repository_uuidv4=NEW.repository_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX repositories_fk_1 ON repositories(preferred_repository_endpoint_id,repository_uuidv4);
CREATE TRIGGER repository_bindings_immutable BEFORE UPDATE ON repository_bindings WHEN NEW.repository_binding_id IS NOT OLD.repository_binding_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.service_instance_uuidv4 IS NOT OLD.service_instance_uuidv4 OR (OLD.provider_repository_id IS NOT NULL AND NEW.provider_repository_id IS NOT OLD.provider_repository_id) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_bindings_no_replace BEFORE INSERT ON repository_bindings WHEN EXISTS(SELECT 1 FROM repository_bindings WHERE (repository_binding_id=NEW.repository_binding_id) OR (repository_binding_id=NEW.repository_binding_id AND repository_uuidv4=NEW.repository_uuidv4) OR (service_instance_uuidv4=NEW.service_instance_uuidv4 AND provider_repository_id=NEW.provider_repository_id) OR (repository_uuidv4=NEW.repository_uuidv4 AND service_instance_uuidv4=NEW.service_instance_uuidv4) OR (repository_binding_id=NEW.repository_binding_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_endpoints_immutable BEFORE UPDATE ON repository_endpoints WHEN NEW.repository_endpoint_id IS NOT OLD.repository_endpoint_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_endpoints_no_replace BEFORE INSERT ON repository_endpoints WHEN EXISTS(SELECT 1 FROM repository_endpoints WHERE (repository_endpoint_id=NEW.repository_endpoint_id) OR (repository_endpoint_id=NEW.repository_endpoint_id AND repository_uuidv4=NEW.repository_uuidv4) OR (repository_uuidv4=NEW.repository_uuidv4 AND url=NEW.url) OR (repository_endpoint_id=NEW.repository_endpoint_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_object_sources_immutable BEFORE UPDATE ON repository_object_sources WHEN NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.git_object_id IS NOT OLD.git_object_id OR NEW.git_acquisition_id IS NOT OLD.git_acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_object_sources_no_replace BEFORE INSERT ON repository_object_sources WHEN EXISTS(SELECT 1 FROM repository_object_sources WHERE (repository_uuidv4=NEW.repository_uuidv4 AND git_object_id=NEW.git_object_id AND git_acquisition_id=NEW.git_acquisition_id) OR (repository_uuidv4=NEW.repository_uuidv4 AND git_object_id=NEW.git_object_id AND git_acquisition_id=NEW.git_acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_object_sources_retain BEFORE DELETE ON repository_object_sources BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX repository_object_sources_fk_0 ON repository_object_sources(git_acquisition_id,repository_uuidv4);
CREATE INDEX repository_object_sources_fk_1 ON repository_object_sources(git_object_id);
CREATE TRIGGER resume_cursors_immutable BEFORE UPDATE ON resume_cursors WHEN NEW.resume_scope_id IS NOT OLD.resume_scope_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER resume_cursors_no_replace BEFORE INSERT ON resume_cursors WHEN EXISTS(SELECT 1 FROM resume_cursors WHERE (resume_scope_id=NEW.resume_scope_id) OR (resume_scope_id=NEW.resume_scope_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX resume_cursors_fk_0 ON resume_cursors(incremental_scan_id,resume_scope_id);
CREATE TRIGGER resume_scopes_immutable BEFORE UPDATE ON resume_scopes WHEN NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.repository_binding_id IS NOT OLD.repository_binding_id OR NEW.source_id IS NOT OLD.source_id OR NEW.principal_ref IS NOT OLD.principal_ref OR NEW.api_version IS NOT OLD.api_version OR NEW.endpoint IS NOT OLD.endpoint OR NEW.request_context IS NOT OLD.request_context OR NEW.parser_version IS NOT OLD.parser_version OR NEW.profile_version IS NOT OLD.profile_version OR NEW.confidence IS NOT OLD.confidence BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER resume_scopes_no_replace BEFORE INSERT ON resume_scopes WHEN EXISTS(SELECT 1 FROM resume_scopes WHERE (resume_scope_id=NEW.resume_scope_id) OR (resume_scope_id=NEW.resume_scope_id AND repository_uuidv4=NEW.repository_uuidv4) OR (resume_scope_id=NEW.resume_scope_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER resume_scopes_retain BEFORE DELETE ON resume_scopes BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX resume_scopes_fk_0 ON resume_scopes(repository_binding_id,repository_uuidv4);
CREATE INDEX resume_scopes_fk_1 ON resume_scopes(source_id);
CREATE INDEX resume_scopes_fk_2 ON resume_scopes(repository_uuidv4);
CREATE TRIGGER review_threads_no_replace BEFORE INSERT ON review_threads WHEN EXISTS(SELECT 1 FROM review_threads WHERE change_request_id=NEW.change_request_id AND provider_resource_id=NEW.provider_resource_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX review_threads_fk_0 ON review_threads(change_request_id);
CREATE INDEX root_manifest_entries_fk_0 ON root_manifest_entries(git_object_id);
CREATE TRIGGER root_origins_immutable BEFORE UPDATE ON root_origins WHEN NEW.root_origin_id IS NOT OLD.root_origin_id OR NEW.acquisition_root_id IS NOT OLD.acquisition_root_id OR NEW.origin_kind IS NOT OLD.origin_kind OR NEW.raw_ref_name IS NOT OLD.raw_ref_name OR NEW.source_ordinal IS NOT OLD.source_ordinal OR NEW.snapshot_id IS NOT OLD.snapshot_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.change_request_observation_id IS NOT OLD.change_request_observation_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER root_origins_no_replace BEFORE INSERT ON root_origins WHEN EXISTS(SELECT 1 FROM root_origins WHERE (root_origin_id=NEW.root_origin_id) OR (acquisition_root_id=NEW.acquisition_root_id AND origin_kind=NEW.origin_kind AND source_ordinal=NEW.source_ordinal)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER root_origins_retain BEFORE DELETE ON root_origins BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX root_origins_fk_0 ON root_origins(change_request_observation_id,change_request_id);
CREATE INDEX root_origins_fk_1 ON root_origins(change_request_id,repository_uuidv4);
CREATE INDEX root_origins_fk_2 ON root_origins(snapshot_id,repository_uuidv4);
CREATE INDEX root_origins_fk_3 ON root_origins(acquisition_root_id,repository_uuidv4);
CREATE TRIGGER search_documents_immutable BEFORE UPDATE ON search_documents WHEN NEW.search_document_id IS NOT OLD.search_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER search_documents_no_replace BEFORE INSERT ON search_documents WHEN EXISTS(SELECT 1 FROM search_documents WHERE (search_document_id=NEW.search_document_id) OR (kind=NEW.kind AND source_key=NEW.source_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER service_instances_immutable BEFORE UPDATE ON service_instances WHEN NEW.service_instance_uuidv4 IS NOT OLD.service_instance_uuidv4 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER service_instances_no_replace BEFORE INSERT ON service_instances WHEN EXISTS(SELECT 1 FROM service_instances WHERE (service_instance_uuidv4=NEW.service_instance_uuidv4) OR (service_instance_uuidv4=NEW.service_instance_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER snapshots_immutable BEFORE UPDATE ON snapshots WHEN NEW.snapshot_id IS NOT OLD.snapshot_id OR NEW.git_acquisition_id IS NOT OLD.git_acquisition_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.generation IS NOT OLD.generation OR NEW.created_at_us IS NOT OLD.created_at_us OR (OLD.published=1 AND NEW.published!=1) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER snapshots_no_replace BEFORE INSERT ON snapshots WHEN EXISTS(SELECT 1 FROM snapshots WHERE (snapshot_id=NEW.snapshot_id) OR (snapshot_id=NEW.snapshot_id AND repository_uuidv4=NEW.repository_uuidv4) OR (snapshot_id=NEW.snapshot_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER snapshots_retain BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX snapshots_fk_0 ON snapshots(git_acquisition_id,repository_uuidv4);
-- Pair membership is retained; times are aggregate known min/max, not event rows.
-- NULL may become known, never the reverse. Integer microseconds preserve exact
-- temporal ordering, including observations within the same millisecond.
CREATE TRIGGER source_repositories_immutable BEFORE UPDATE ON source_repositories WHEN NEW.source_id IS NOT OLD.source_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR (OLD.first_seen_us IS NOT NULL AND (NEW.first_seen_us IS NULL OR NEW.first_seen_us>OLD.first_seen_us)) OR (OLD.last_seen_us IS NOT NULL AND (NEW.last_seen_us IS NULL OR NEW.last_seen_us<OLD.last_seen_us)) BEGIN SELECT RAISE(ABORT,'Immutable source pair or aggregate time regression'); END;
CREATE TRIGGER source_repositories_no_replace BEFORE INSERT ON source_repositories WHEN EXISTS(SELECT 1 FROM source_repositories WHERE (source_id=NEW.source_id AND repository_uuidv4=NEW.repository_uuidv4) OR (source_id=NEW.source_id AND repository_uuidv4=NEW.repository_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER source_repositories_retain BEFORE DELETE ON source_repositories BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX source_repositories_fk_0 ON source_repositories(repository_uuidv4);
CREATE TRIGGER sources_immutable BEFORE UPDATE ON sources WHEN NEW.source_id IS NOT OLD.source_id OR NEW.source_registration_uuidv4 IS NOT OLD.source_registration_uuidv4 OR NEW.service_instance_uuidv4 IS NOT OLD.service_instance_uuidv4 OR NEW.discovery_kind IS NOT OLD.discovery_kind BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER sources_no_replace BEFORE INSERT ON sources WHEN EXISTS(SELECT 1 FROM sources WHERE (source_id=NEW.source_id) OR (source_registration_uuidv4=NEW.source_registration_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX sources_fk_0 ON sources(service_instance_uuidv4);
CREATE TRIGGER space_reservations_immutable BEFORE UPDATE ON space_reservations WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER space_reservations_no_replace BEFORE INSERT ON space_reservations WHEN EXISTS(SELECT 1 FROM space_reservations WHERE (job_id=NEW.job_id AND attempt=NEW.attempt) OR (job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX tag_objects_fk_0 ON tag_objects(target_git_object_id);
CREATE TRIGGER text_bodies_immutable BEFORE UPDATE ON text_bodies WHEN NEW.text_body_id IS NOT OLD.text_body_id OR NEW.body IS NOT OLD.body OR NEW.byte_length IS NOT OLD.byte_length OR NEW.sha256 IS NOT OLD.sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER text_bodies_no_replace BEFORE INSERT ON text_bodies WHEN EXISTS(SELECT 1 FROM text_bodies WHERE (text_body_id=NEW.text_body_id) OR (sha256=NEW.sha256)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER text_bodies_retain BEFORE DELETE ON text_bodies BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX tree_entries_fk_0 ON tree_entries(child_git_object_id);
CREATE TRIGGER unresolved_payloads_no_replace BEFORE INSERT ON unresolved_payloads WHEN EXISTS(SELECT 1 FROM unresolved_payloads WHERE (unresolved_payload_id=NEW.unresolved_payload_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER unresolved_payloads_retain BEFORE DELETE ON unresolved_payloads BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX unresolved_payloads_fk_1 ON unresolved_payloads(payload_representation,payload_sha256);
CREATE TRIGGER validators_immutable BEFORE UPDATE ON validators WHEN NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.validator_key IS NOT OLD.validator_key BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER validators_no_replace BEFORE INSERT ON validators WHEN EXISTS(SELECT 1 FROM validators WHERE (resume_scope_id=NEW.resume_scope_id AND validator_key=NEW.validator_key) OR (resume_scope_id=NEW.resume_scope_id AND validator_key=NEW.validator_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX validators_fk_0 ON validators(payload_representation,payload_sha256);
CREATE TRIGGER listing_scope_insert BEFORE INSERT ON code_listings WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id AND f.resume_scope_id=NEW.resume_scope_id) BEGIN SELECT RAISE(ABORT,'Listing collection, CR and scope mismatch'); END;
CREATE TRIGGER listing_scope_update BEFORE UPDATE ON code_listings WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id AND f.resume_scope_id=NEW.resume_scope_id) BEGIN SELECT RAISE(ABORT,'Listing collection, CR and scope mismatch'); END;
CREATE TRIGGER fetch_scope_insert BEFORE INSERT ON fetch_collections WHEN NOT EXISTS(SELECT 1 FROM resume_scopes s WHERE s.resume_scope_id=NEW.resume_scope_id AND s.repository_uuidv4=NEW.repository_uuidv4 AND s.source_id IS NEW.source_id) BEGIN SELECT RAISE(ABORT,'Collection scope mismatch'); END;
CREATE TRIGGER fetch_scope_update BEFORE UPDATE ON fetch_collections WHEN NOT EXISTS(SELECT 1 FROM resume_scopes s WHERE s.resume_scope_id=NEW.resume_scope_id AND s.repository_uuidv4=NEW.repository_uuidv4 AND s.source_id IS NEW.source_id) BEGIN SELECT RAISE(ABORT,'Collection scope mismatch'); END;
CREATE TRIGGER code_commits_insert BEFORE INSERT ON code_observations WHEN NEW.commit_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.commit_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_commits_update BEFORE UPDATE ON code_observations WHEN NEW.commit_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.commit_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_files_insert BEFORE INSERT ON code_observations WHEN NEW.file_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.file_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='files' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_files_update BEFORE UPDATE ON code_observations WHEN NEW.file_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.file_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='files' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_complete_insert BEFORE INSERT ON code_observations
WHEN NEW.state='complete' AND EXISTS(
 SELECT 1 FROM code_listings l WHERE l.code_listing_id IN (NEW.commit_code_listing_id,NEW.file_code_listing_id)
 AND NOT EXISTS(SELECT 1 FROM code_listing_progress p WHERE p.code_listing_id=l.code_listing_id AND p.state='complete')
 AND NOT EXISTS(
  SELECT 1 FROM completion_markers m WHERE m.fetch_collection_id=l.fetch_collection_id AND m.resume_scope_id=l.resume_scope_id
  AND m.asserted_state='complete' AND json_extract(m.evidence,'$.terminal')=1
  AND json_type(m.evidence,'$.fetch_occurrence_uuidv4s')='array'
  AND json_array_length(m.evidence,'$.fetch_occurrence_uuidv4s')>0
  AND m.observed_at_us IS NOT NULL AND m.observed_at_us=(SELECT max(f.observed_at_us) FROM fetch_occurrences f WHERE f.fetch_collection_id=l.fetch_collection_id)
  AND json_array_length(m.evidence,'$.fetch_occurrence_uuidv4s')=(SELECT count(DISTINCT item.value) FROM json_each(m.evidence,'$.fetch_occurrence_uuidv4s') item)
  AND json_array_length(m.evidence,'$.fetch_occurrence_uuidv4s')=(SELECT count(*) FROM fetch_occurrences f WHERE f.fetch_collection_id=l.fetch_collection_id)
  AND NOT EXISTS(SELECT 1 FROM json_each(m.evidence,'$.fetch_occurrence_uuidv4s') item WHERE NOT EXISTS(SELECT 1 FROM fetch_occurrences f WHERE f.fetch_collection_id=l.fetch_collection_id AND f.fetch_occurrence_uuidv4=item.value))
 ))
BEGIN SELECT RAISE(ABORT,'Complete code requires exact complete listing evidence'); END;
CREATE TRIGGER code_complete_update BEFORE UPDATE ON code_observations
WHEN NEW.state='complete' AND EXISTS(
 SELECT 1 FROM code_listings l WHERE l.code_listing_id IN (NEW.commit_code_listing_id,NEW.file_code_listing_id)
 AND NOT EXISTS(SELECT 1 FROM code_listing_progress p WHERE p.code_listing_id=l.code_listing_id AND p.state='complete')
 AND NOT EXISTS(
  SELECT 1 FROM completion_markers m WHERE m.fetch_collection_id=l.fetch_collection_id AND m.resume_scope_id=l.resume_scope_id
  AND m.asserted_state='complete' AND json_extract(m.evidence,'$.terminal')=1
  AND json_type(m.evidence,'$.fetch_occurrence_uuidv4s')='array'
  AND json_array_length(m.evidence,'$.fetch_occurrence_uuidv4s')>0
  AND m.observed_at_us IS NOT NULL AND m.observed_at_us=(SELECT max(f.observed_at_us) FROM fetch_occurrences f WHERE f.fetch_collection_id=l.fetch_collection_id)
  AND json_array_length(m.evidence,'$.fetch_occurrence_uuidv4s')=(SELECT count(DISTINCT item.value) FROM json_each(m.evidence,'$.fetch_occurrence_uuidv4s') item)
  AND json_array_length(m.evidence,'$.fetch_occurrence_uuidv4s')=(SELECT count(*) FROM fetch_occurrences f WHERE f.fetch_collection_id=l.fetch_collection_id)
  AND NOT EXISTS(SELECT 1 FROM json_each(m.evidence,'$.fetch_occurrence_uuidv4s') item WHERE NOT EXISTS(SELECT 1 FROM fetch_occurrences f WHERE f.fetch_collection_id=l.fetch_collection_id AND f.fetch_occurrence_uuidv4=item.value))
 ))
BEGIN SELECT RAISE(ABORT,'Complete code requires exact complete listing evidence'); END;

CREATE TRIGGER listing_no_downgrade BEFORE UPDATE ON code_listing_progress WHEN OLD.state='complete' AND (NEW.state IS NOT OLD.state OR NEW.terminal IS NOT OLD.terminal OR NEW.page_count IS NOT OLD.page_count OR NEW.context_proven IS NOT OLD.context_proven) BEGIN SELECT RAISE(ABORT,'Completed listing is immutable'); END;
-- Completion seals even an unreferenced listing. Deleting and recreating its
-- marker must not reopen it; conflict INSERT/REPLACE is separately prohibited.
CREATE TRIGGER listing_complete_retain BEFORE DELETE ON code_listing_progress WHEN OLD.state='complete' BEGIN SELECT RAISE(ABORT,'Complete listing marker cannot be deleted'); END;
CREATE TRIGGER code_commits_context_insert BEFORE INSERT ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.fetch_collection_id=l.fetch_collection_id WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='commits' AND o.fetch_occurrence_id=NEW.fetch_occurrence_id AND l.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_commits_context_update BEFORE UPDATE ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.fetch_collection_id=l.fetch_collection_id WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='commits' AND o.fetch_occurrence_id=NEW.fetch_occurrence_id AND l.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_commits_sealed_insert BEFORE INSERT ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id) BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_commits_sealed_update BEFORE UPDATE ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id) BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_file_changes_context_insert BEFORE INSERT ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.fetch_collection_id=l.fetch_collection_id WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='files' AND o.fetch_occurrence_id=NEW.fetch_occurrence_id) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_file_changes_context_update BEFORE UPDATE ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.fetch_collection_id=l.fetch_collection_id WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='files' AND o.fetch_occurrence_id=NEW.fetch_occurrence_id) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_file_changes_sealed_insert BEFORE INSERT ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id) BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_file_changes_sealed_update BEFORE UPDATE ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id) BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_acquisition_owner_insert BEFORE INSERT ON code_acquisitions WHEN NEW.acquisition_root_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_observations o ON o.code_observation_id=NEW.code_observation_id JOIN change_requests c ON c.change_request_id=o.change_request_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND r.repository_uuidv4=c.repository_uuidv4 AND (r.role=NEW.role OR (r.role='traversal' AND EXISTS(SELECT 1 FROM git_acquisitions g,json_each(g.roots_manifest) j WHERE g.git_acquisition_id=r.git_acquisition_id AND json_extract(j.value,'$.role')=NEW.role AND lower(json_extract(j.value,'$.expected'))=lower(hex(NEW.oid))))) AND r.object_format=NEW.object_format AND r.oid=NEW.oid AND (r.expected_oid IS NULL OR r.expected_oid=NEW.oid)) BEGIN SELECT RAISE(ABORT,'Code acquisition owner, role or OID mismatch'); END;
CREATE TRIGGER code_acquisition_owner_update BEFORE UPDATE ON code_acquisitions WHEN NEW.acquisition_root_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_observations o ON o.code_observation_id=NEW.code_observation_id JOIN change_requests c ON c.change_request_id=o.change_request_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND r.repository_uuidv4=c.repository_uuidv4 AND (r.role=NEW.role OR (r.role='traversal' AND EXISTS(SELECT 1 FROM git_acquisitions g,json_each(g.roots_manifest) j WHERE g.git_acquisition_id=r.git_acquisition_id AND json_extract(j.value,'$.role')=NEW.role AND lower(json_extract(j.value,'$.expected'))=lower(hex(NEW.oid))))) AND r.object_format=NEW.object_format AND r.oid=NEW.oid AND (r.expected_oid IS NULL OR r.expected_oid=NEW.oid)) BEGIN SELECT RAISE(ABORT,'Code acquisition owner, role or OID mismatch'); END;
CREATE TRIGGER origin_ref_insert BEFORE INSERT ON root_origins WHEN NEW.origin_kind='ref' AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN snapshots s ON s.git_acquisition_id=r.git_acquisition_id JOIN ref_observations f ON f.snapshot_id=s.snapshot_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND s.snapshot_id=NEW.snapshot_id AND f.raw_ref_name=NEW.raw_ref_name AND f.object_format=r.object_format AND COALESCE(f.peeled_oid,f.target_oid)=r.oid) BEGIN SELECT RAISE(ABORT,'Ref origin must match acquisition and OID'); END;
CREATE TRIGGER origin_ref_update BEFORE UPDATE ON root_origins WHEN NEW.origin_kind='ref' AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN snapshots s ON s.git_acquisition_id=r.git_acquisition_id JOIN ref_observations f ON f.snapshot_id=s.snapshot_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND s.snapshot_id=NEW.snapshot_id AND f.raw_ref_name=NEW.raw_ref_name AND f.object_format=r.object_format AND COALESCE(f.peeled_oid,f.target_oid)=r.oid) BEGIN SELECT RAISE(ABORT,'Ref origin must match acquisition and OID'); END;
CREATE TRIGGER origin_pr_insert BEFORE INSERT ON root_origins WHEN NEW.origin_kind='pr_role' AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_acquisitions a ON a.acquisition_root_id=r.acquisition_root_id JOIN code_observations o ON o.code_observation_id=a.code_observation_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND o.change_request_id=NEW.change_request_id AND o.change_request_observation_id=NEW.change_request_observation_id) BEGIN SELECT RAISE(ABORT,'PR origin must match code acquisition'); END;
CREATE TRIGGER origin_pr_update BEFORE UPDATE ON root_origins WHEN NEW.origin_kind='pr_role' AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_acquisitions a ON a.acquisition_root_id=r.acquisition_root_id JOIN code_observations o ON o.code_observation_id=a.code_observation_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND o.change_request_id=NEW.change_request_id AND o.change_request_observation_id=NEW.change_request_observation_id) BEGIN SELECT RAISE(ABORT,'PR origin must match code acquisition'); END;
CREATE TRIGGER root_format_insert BEFORE INSERT ON acquisition_roots WHEN NOT EXISTS(SELECT 1 FROM git_acquisitions a WHERE a.git_acquisition_id=NEW.git_acquisition_id AND a.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Root format must match acquisition'); END;
CREATE TRIGGER root_format_update BEFORE UPDATE ON acquisition_roots WHEN NOT EXISTS(SELECT 1 FROM git_acquisitions a WHERE a.git_acquisition_id=NEW.git_acquisition_id AND a.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Root format must match acquisition'); END;
CREATE TRIGGER scan_scope_insert BEFORE INSERT ON incremental_scans WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.resume_scope_id=NEW.resume_scope_id) BEGIN SELECT RAISE(ABORT,'Scan scope mismatch'); END;
CREATE TRIGGER scan_scope_update BEFORE UPDATE ON incremental_scans WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.resume_scope_id=NEW.resume_scope_id) BEGIN SELECT RAISE(ABORT,'Scan scope mismatch'); END;
CREATE TRIGGER completion_scope_insert BEFORE INSERT ON completion_markers WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.resume_scope_id=NEW.resume_scope_id) BEGIN SELECT RAISE(ABORT,'Completion scope mismatch'); END;
CREATE TRIGGER completion_scope_update BEFORE UPDATE ON completion_markers WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.resume_scope_id=NEW.resume_scope_id) BEGIN SELECT RAISE(ABORT,'Completion scope mismatch'); END;
CREATE TRIGGER active_locator_insert BEFORE INSERT ON active_cache_entries WHEN NOT EXISTS(SELECT 1 FROM cache_locators WHERE cache_locator_id=NEW.cache_locator_id AND access='target_active') BEGIN SELECT RAISE(ABORT,'Readonly source cache cannot become active'); END;
CREATE TRIGGER active_locator_update BEFORE UPDATE ON active_cache_entries WHEN NOT EXISTS(SELECT 1 FROM cache_locators WHERE cache_locator_id=NEW.cache_locator_id AND access='target_active') BEGIN SELECT RAISE(ABORT,'Readonly source cache cannot become active'); END;
CREATE TRIGGER blob_type_insert BEFORE INSERT ON blob_content_map WHEN NOT EXISTS(SELECT 1 FROM git_objects o JOIN contents c ON c.content_id=NEW.content_id WHERE o.git_object_id=NEW.git_object_id AND o.type='blob' AND o.size=c.byte_length) BEGIN SELECT RAISE(ABORT,'Blob content type/length mismatch'); END;
CREATE TRIGGER blob_type_update BEFORE UPDATE ON blob_content_map WHEN NOT EXISTS(SELECT 1 FROM git_objects o JOIN contents c ON c.content_id=NEW.content_id WHERE o.git_object_id=NEW.git_object_id AND o.type='blob' AND o.size=c.byte_length) BEGIN SELECT RAISE(ABORT,'Blob content type/length mismatch'); END;


CREATE TRIGGER acquisition_cache_owner_insert BEFORE INSERT ON acquisition_progress WHEN NEW.active_cache_entry_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN active_cache_entries a ON a.active_cache_entry_id=NEW.active_cache_entry_id JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_uuidv4=l.repository_uuidv4 AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Acquisition cache owner mismatch'); END;
CREATE TRIGGER obligation_cache_owner_insert BEFORE INSERT ON preservation_obligations WHEN NEW.cache_locator_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN cache_locators l ON l.cache_locator_id=NEW.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_uuidv4=l.repository_uuidv4 AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Preservation cache owner mismatch'); END;

CREATE TRIGGER acquisition_cache_owner_update BEFORE UPDATE ON acquisition_progress WHEN NEW.active_cache_entry_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN active_cache_entries a ON a.active_cache_entry_id=NEW.active_cache_entry_id JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_uuidv4=l.repository_uuidv4 AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Acquisition cache owner mismatch'); END;
CREATE TRIGGER obligation_cache_owner_update BEFORE UPDATE ON preservation_obligations WHEN NEW.cache_locator_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN cache_locators l ON l.cache_locator_id=NEW.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_uuidv4=l.repository_uuidv4 AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Preservation cache owner mismatch'); END;

-- Natural-key documents, immutable observations and direct content identity.
CREATE TRIGGER documents_no_replace BEFORE INSERT ON documents WHEN EXISTS(SELECT 1 FROM documents WHERE (change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER documents_retain BEFORE DELETE ON documents BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER reviews_no_replace BEFORE INSERT ON reviews WHEN EXISTS(SELECT 1 FROM reviews WHERE (change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER reviews_retain BEFORE DELETE ON reviews BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER review_comments_no_replace BEFORE INSERT ON review_comments WHEN EXISTS(SELECT 1 FROM review_comments WHERE (change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER review_comments_retain BEFORE DELETE ON review_comments BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER collection_memberships_immutable BEFORE UPDATE ON collection_memberships WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_change_request_document_id IS NOT OLD.provider_change_request_document_id OR NEW.ordinal IS NOT OLD.ordinal BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER collection_memberships_no_replace BEFORE INSERT ON collection_memberships WHEN EXISTS(SELECT 1 FROM collection_memberships WHERE (fetch_collection_id=NEW.fetch_collection_id AND change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER collection_memberships_retain BEFORE DELETE ON collection_memberships BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER document_observations_no_replace BEFORE INSERT ON document_observations WHEN EXISTS(SELECT 1 FROM document_observations WHERE (document_observation_id=NEW.document_observation_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER document_observations_retain BEFORE DELETE ON document_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX document_observations_document_fk ON document_observations(change_request_id,kind,provider_change_request_document_id);
CREATE INDEX document_observations_origin_lookup ON document_observations(change_request_id,kind,provider_change_request_document_id,origin_key);
CREATE INDEX document_observations_body_fk ON document_observations(text_body_sha256);
CREATE INDEX document_observations_occurrence_fk ON document_observations(fetch_occurrence_id);
CREATE INDEX collection_memberships_document_fk ON collection_memberships(change_request_id,kind,provider_change_request_document_id);
CREATE TRIGGER membership_owner_insert BEFORE INSERT ON collection_memberships WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Membership must belong to same CR'); END;
CREATE TRIGGER document_origin_insert BEFORE INSERT ON document_observations WHEN NEW.fetch_occurrence_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE o.fetch_occurrence_id=NEW.fetch_occurrence_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Document occurrence belongs to another CR'); END;
CREATE TRIGGER membership_owner_update BEFORE UPDATE ON collection_memberships WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Membership must belong to same CR'); END;
CREATE TRIGGER document_origin_update BEFORE UPDATE ON document_observations WHEN NEW.fetch_occurrence_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE o.fetch_occurrence_id=NEW.fetch_occurrence_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Document occurrence belongs to another CR'); END;
CREATE TRIGGER change_request_observations_immutable BEFORE UPDATE ON change_request_observations BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER document_observations_immutable BEFORE UPDATE ON document_observations BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER code_observations_immutable BEFORE UPDATE ON code_observations BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER change_request_events_immutable BEFORE UPDATE ON change_request_events BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER code_commits_immutable BEFORE UPDATE ON code_commits BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER code_file_changes_immutable BEFORE UPDATE ON code_file_changes BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER inventory_observations_immutable BEFORE UPDATE ON inventory_observations BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER fetch_occurrences_immutable BEFORE UPDATE ON fetch_occurrences BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER documents_immutable BEFORE UPDATE ON documents BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER review_threads_immutable BEFORE UPDATE ON review_threads BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER reviews_immutable BEFORE UPDATE ON reviews BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER review_comments_immutable BEFORE UPDATE ON review_comments BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER unresolved_payloads_immutable BEFORE UPDATE ON unresolved_payloads BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;

CREATE TABLE parser_profile_selection_publications(
 selection_decision_uuidv4 TEXT PRIMARY KEY REFERENCES parser_profile_selection_decisions(selection_decision_uuidv4)
) STRICT;
CREATE TABLE source_input_observations (
 source_input_uuidv4 TEXT PRIMARY KEY,
 source_registration_uuidv4 TEXT NOT NULL
   REFERENCES sources(source_registration_uuidv4),
 payload_representation TEXT,
 payload_sha256 BLOB,
 request_context_json TEXT NOT NULL
   CHECK(json_valid(request_context_json) AND json_type(request_context_json)='object'),
 observed_at_us INTEGER,
 UNIQUE(source_input_uuidv4,source_registration_uuidv4),
 CHECK ((payload_representation IS NULL) = (payload_sha256 IS NULL)),
 FOREIGN KEY(payload_representation,payload_sha256)
   REFERENCES payloads(representation,sha256)
) STRICT;

-- D27 A, D35 B. "definition_json" includes all declared capabilities,
-- implementation fingerprint and output schema. UUID is identity, NOT digest.
CREATE TABLE parser_profiles (
 parser_profile_uuidv4 TEXT PRIMARY KEY,
 parser_version TEXT NOT NULL,
 profile_version TEXT NOT NULL,
 definition_json TEXT NOT NULL CHECK(
    json_valid(definition_json)
    AND json_type(definition_json)='object'
    AND coalesce(json_type(definition_json,'$.capabilities'),'')='array' AND json_array_length(definition_json,'$.capabilities')>0
 AND coalesce(json_type(definition_json,'$.implementation'),'')='object' AND coalesce(json_type(definition_json,'$.settings'),'')='object' AND coalesce(json_type(definition_json,'$.output_schema'),'')='object'
 )
) STRICT;

-- This is the *declared* supported scope, not a partial-verification table.
-- Admission must check it exactly matches the immutable definition_json list.
CREATE TABLE parser_profile_capabilities (
 parser_profile_uuidv4 TEXT NOT NULL REFERENCES parser_profiles(parser_profile_uuidv4),
 owner_kind TEXT NOT NULL CHECK(owner_kind IN ('repository','source')),
 fact_kind TEXT NOT NULL CHECK(length(fact_kind)>0),
 PRIMARY KEY(parser_profile_uuidv4,owner_kind,fact_kind)
) STRICT;

-- Each normalized capability must occur in the profile's immutable manifest.
CREATE TRIGGER parser_profile_capability_must_be_declared
 BEFORE INSERT ON parser_profile_capabilities
 WHEN NOT EXISTS (
  SELECT 1 FROM parser_profiles p, json_each(p.definition_json,'$.capabilities') c
   WHERE p.parser_profile_uuidv4=NEW.parser_profile_uuidv4
     AND json_extract(c.value,'$.owner_kind')=NEW.owner_kind
     AND json_extract(c.value,'$.fact_kind')=NEW.fact_kind
 )
 BEGIN SELECT RAISE(ABORT,'capability not in immutable profile definition'); END;

-- D33 A/D35 B: verification is for THE ENTIRE declared profile definition.
CREATE TABLE parser_profile_verifications (
 parser_profile_verification_uuidv4 TEXT PRIMARY KEY,
 parser_profile_uuidv4 TEXT NOT NULL REFERENCES parser_profiles(parser_profile_uuidv4),
 outcome TEXT NOT NULL CHECK(outcome IN ('passed','failed','incomplete')),
 criteria_json TEXT NOT NULL CHECK(json_valid(criteria_json) AND json_type(criteria_json)='object'),
 evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json) AND json_type(evidence_json)='object'),
 verified_at_us INTEGER,
 UNIQUE(parser_profile_verification_uuidv4,parser_profile_uuidv4,outcome)
) STRICT;
-- Full-definition verification requires a complete capability manifest.
-- Whether tests actually cover every declared capability is a verifier admission check.
CREATE TRIGGER parser_profile_verification_requires_full_manifest
 BEFORE INSERT ON parser_profile_verifications
 WHEN NEW.outcome='passed' AND EXISTS (
    SELECT 1 FROM parser_profiles p
     WHERE p.parser_profile_uuidv4=NEW.parser_profile_uuidv4
       AND (SELECT COUNT(*) FROM json_each(p.definition_json,'$.capabilities'))
           <> (SELECT COUNT(*) FROM parser_profile_capabilities c
                WHERE c.parser_profile_uuidv4=NEW.parser_profile_uuidv4)
 )
 BEGIN SELECT RAISE(ABORT,'profile definition capabilities not fully declared'); END;

CREATE TABLE parser_profile_verification_invalidations (
 invalidation_uuidv4 TEXT PRIMARY KEY,
 parser_profile_verification_uuidv4 TEXT NOT NULL
   REFERENCES parser_profile_verifications(parser_profile_verification_uuidv4),
 reason TEXT NOT NULL CHECK(length(reason)>0),
 invalidated_at_us INTEGER
) STRICT;

-- Local policy, intentionally NOT exchanged as portable verification truth.
-- This is operational *trust*, not mutable verification evidence.
CREATE TABLE local_parser_profile_verification_trust (
 parser_profile_verification_uuidv4 TEXT PRIMARY KEY
   REFERENCES parser_profile_verifications(parser_profile_verification_uuidv4),
 trusted INTEGER NOT NULL CHECK(trusted IN (0,1)),
 adjudicated_at_us INTEGER,
 rationale_json TEXT NOT NULL CHECK(json_valid(rationale_json) AND json_type(rationale_json)='object')
) STRICT;

-- D25 A/D27 A/D31 A/D36 A. Exact one owner.
CREATE TABLE parsed_results (
 parsed_result_uuidv4 TEXT PRIMARY KEY,
 parser_profile_uuidv4 TEXT NOT NULL REFERENCES parser_profiles(parser_profile_uuidv4),
 owner_kind TEXT NOT NULL CHECK(owner_kind IN ('repository','source')),
 repository_uuidv4 TEXT REFERENCES repositories(repository_uuidv4),
 source_registration_uuidv4 TEXT REFERENCES sources(source_registration_uuidv4),
 parsed_at_us INTEGER,
 input_manifest_json TEXT NOT NULL CHECK(json_valid(input_manifest_json) AND json_type(input_manifest_json)='array' AND json_array_length(input_manifest_json)>0),
 derivation_json TEXT NOT NULL CHECK(json_valid(derivation_json) AND json_type(derivation_json)='object'),
 CHECK (
    (owner_kind='repository' AND repository_uuidv4 IS NOT NULL AND source_registration_uuidv4 IS NULL)
    OR (owner_kind='source' AND repository_uuidv4 IS NULL AND source_registration_uuidv4 IS NOT NULL)
 ),
 UNIQUE(parsed_result_uuidv4,repository_uuidv4),
 UNIQUE(parsed_result_uuidv4,source_registration_uuidv4)
) STRICT;

-- D28 A/D36 A. Composite FK prevents both result/input owner mismatch
-- and references to an input of another repository/source.
-- Three types here: repository HTTP fetch, repository Git acquisition,
-- and source-wide raw input. Other input kinds need explicit typed FKs.
CREATE TABLE parsed_result_inputs (
 parsed_result_uuidv4 TEXT NOT NULL,
 input_ordinal INTEGER NOT NULL CHECK(input_ordinal>=0),
 owner_kind TEXT NOT NULL CHECK(owner_kind IN ('repository','source')),
 repository_uuidv4 TEXT,
 source_registration_uuidv4 TEXT,
 fetch_occurrence_uuidv4 TEXT,
 git_acquisition_id TEXT,
 source_input_uuidv4 TEXT,
 PRIMARY KEY(parsed_result_uuidv4,input_ordinal),
 CHECK (
    (owner_kind='repository' AND repository_uuidv4 IS NOT NULL
      AND source_registration_uuidv4 IS NULL AND source_input_uuidv4 IS NULL
      AND ((fetch_occurrence_uuidv4 IS NOT NULL AND git_acquisition_id IS NULL)
        OR (fetch_occurrence_uuidv4 IS NULL AND git_acquisition_id IS NOT NULL)))
    OR
    (owner_kind='source' AND source_registration_uuidv4 IS NOT NULL
      AND repository_uuidv4 IS NULL AND source_input_uuidv4 IS NOT NULL
      AND fetch_occurrence_uuidv4 IS NULL AND git_acquisition_id IS NULL)
 ),
 FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4)
    REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4),
 FOREIGN KEY(parsed_result_uuidv4,source_registration_uuidv4)
    REFERENCES parsed_results(parsed_result_uuidv4,source_registration_uuidv4),
 FOREIGN KEY(fetch_occurrence_uuidv4,repository_uuidv4)
    REFERENCES fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4),
 FOREIGN KEY(git_acquisition_id,repository_uuidv4)
    REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4),
 FOREIGN KEY(source_input_uuidv4,source_registration_uuidv4)
    REFERENCES source_input_observations(source_input_uuidv4,source_registration_uuidv4)
) STRICT;
CREATE UNIQUE INDEX parsed_input_fetch_once
 ON parsed_result_inputs(parsed_result_uuidv4,fetch_occurrence_uuidv4)
 WHERE fetch_occurrence_uuidv4 IS NOT NULL;
CREATE UNIQUE INDEX parsed_input_git_once
 ON parsed_result_inputs(parsed_result_uuidv4,git_acquisition_id)
 WHERE git_acquisition_id IS NOT NULL;
CREATE UNIQUE INDEX parsed_input_source_once
 ON parsed_result_inputs(parsed_result_uuidv4,source_input_uuidv4)
 WHERE source_input_uuidv4 IS NOT NULL;

-- D29 A/D36 A: generated fact observations have direct FK to result.
-- Shared identity documents and shared text bodies have no parsed-result FK.
-- Production rebuild preserves existing non-parser fact metadata and keys.





-- Publication of a parsed result is distinct from a semantic complete claim.
-- Admission verifies the declared input manifest outside SQL. SQL enforces
-- at least one fully admitted input and the declared count at publication.
CREATE TABLE parsed_result_publications (
 parsed_result_uuidv4 TEXT PRIMARY KEY REFERENCES parsed_results(parsed_result_uuidv4),
 declared_input_count INTEGER NOT NULL CHECK(declared_input_count>0),
 fact_manifest_json TEXT NOT NULL CHECK(json_valid(fact_manifest_json) AND json_type(fact_manifest_json)='array'),
 published_at_us INTEGER
) STRICT;
CREATE TRIGGER parsed_result_input_sealed_on_publication
 BEFORE INSERT ON parsed_result_inputs
 WHEN EXISTS (SELECT 1 FROM parsed_result_publications
               WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4)
 BEGIN SELECT RAISE(ABORT,'published parsed input set is sealed'); END;

CREATE TRIGGER parsed_result_publish_requires_inputs
 BEFORE INSERT ON parsed_result_publications
 WHEN (SELECT COUNT(*) FROM parsed_result_inputs
       WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4)
      <> NEW.declared_input_count
 BEGIN SELECT RAISE(ABORT,'parsed input manifest is not complete'); END;

-- A parsed fact must be of a kind declared by its parser profile.
-- This is additional to composite ownership FKs (D36 A).
CREATE TRIGGER parsed_document_fact_capability
 BEFORE INSERT ON document_observations
 WHEN NOT EXISTS (
   SELECT 1 FROM parsed_results p JOIN parser_profile_capabilities c
     ON c.parser_profile_uuidv4=p.parser_profile_uuidv4
    AND c.owner_kind='repository' AND c.fact_kind=NEW.kind
    WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4
 ) BEGIN SELECT RAISE(ABORT,'parser profile cannot emit this document kind'); END;
CREATE TRIGGER parsed_change_request_fact_capability
 BEFORE INSERT ON change_request_observations
 WHEN NOT EXISTS (
   SELECT 1 FROM parsed_results p JOIN parser_profile_capabilities c
     ON c.parser_profile_uuidv4=p.parser_profile_uuidv4
    AND c.owner_kind='repository' AND c.fact_kind='change-request'
    WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4
 ) BEGIN SELECT RAISE(ABORT,'parser profile cannot emit change-request facts'); END;
CREATE TRIGGER parsed_code_fact_capability
 BEFORE INSERT ON code_observations
 WHEN NOT EXISTS (
   SELECT 1 FROM parsed_results p JOIN parser_profile_capabilities c
     ON c.parser_profile_uuidv4=p.parser_profile_uuidv4
    AND c.owner_kind='repository' AND c.fact_kind='code'
    WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4
 ) BEGIN SELECT RAISE(ABORT,'parser profile cannot emit code facts'); END;
CREATE TRIGGER parsed_inventory_fact_capability
 BEFORE INSERT ON inventory_observations
 WHEN NOT EXISTS (
   SELECT 1 FROM parsed_results p JOIN parser_profile_capabilities c
     ON c.parser_profile_uuidv4=p.parser_profile_uuidv4
    AND c.owner_kind='source' AND c.fact_kind='inventory'
    WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4
 ) BEGIN SELECT RAISE(ABORT,'parser profile cannot emit source inventory facts'); END;

-- D30 A/D32 A/D38 A: profile selection scopes for repository, CR, source.
CREATE TABLE parser_profile_selection_scopes (
 selection_scope_uuidv4 TEXT PRIMARY KEY,
 owner_kind TEXT NOT NULL CHECK(owner_kind IN ('repository','source')),
 repository_uuidv4 TEXT REFERENCES repositories(repository_uuidv4),
 source_registration_uuidv4 TEXT REFERENCES sources(source_registration_uuidv4),
 change_request_id TEXT,
 fact_kind TEXT NOT NULL CHECK(length(fact_kind)>0),
 CHECK (
   (owner_kind='repository' AND repository_uuidv4 IS NOT NULL AND source_registration_uuidv4 IS NULL)
   OR (owner_kind='source' AND repository_uuidv4 IS NULL AND source_registration_uuidv4 IS NOT NULL AND change_request_id IS NULL)
 ),
 UNIQUE(selection_scope_uuidv4,owner_kind,fact_kind),
 FOREIGN KEY(change_request_id,repository_uuidv4)
   REFERENCES change_requests(change_request_id,repository_uuidv4)
) STRICT;
CREATE UNIQUE INDEX parser_scope_repository_unique
 ON parser_profile_selection_scopes(repository_uuidv4,fact_kind)
 WHERE owner_kind='repository' AND change_request_id IS NULL;
CREATE UNIQUE INDEX parser_scope_change_request_unique
 ON parser_profile_selection_scopes(change_request_id,fact_kind)
 WHERE owner_kind='repository' AND change_request_id IS NOT NULL;
CREATE UNIQUE INDEX parser_scope_source_unique
 ON parser_profile_selection_scopes(source_registration_uuidv4,fact_kind)
 WHERE owner_kind='source';

-- D34 A: selection references exact V1, not whatever later V2 passes.
-- outcome constant makes FK enforce that recorded verification is passed;
-- trust and non-invalidation are checked separately by views.
CREATE TABLE parser_profile_selection_decisions (
 selection_decision_uuidv4 TEXT PRIMARY KEY,
 selection_scope_uuidv4 TEXT NOT NULL,
 owner_kind TEXT NOT NULL,
 fact_kind TEXT NOT NULL,
 parser_profile_uuidv4 TEXT NOT NULL,
 parser_profile_verification_uuidv4 TEXT NOT NULL,
 required_verification_outcome TEXT NOT NULL DEFAULT 'passed'
   CHECK(required_verification_outcome='passed'),
 predecessor_manifest_json TEXT NOT NULL CHECK(json_valid(predecessor_manifest_json) AND json_type(predecessor_manifest_json)='array'),
 issuer TEXT NOT NULL CHECK(length(issuer)>0),
 decided_at_us INTEGER,
 UNIQUE(selection_decision_uuidv4,selection_scope_uuidv4),
 FOREIGN KEY(selection_scope_uuidv4,owner_kind,fact_kind)
   REFERENCES parser_profile_selection_scopes(selection_scope_uuidv4,owner_kind,fact_kind),
 FOREIGN KEY(parser_profile_uuidv4,owner_kind,fact_kind)
   REFERENCES parser_profile_capabilities(parser_profile_uuidv4,owner_kind,fact_kind),
 FOREIGN KEY(parser_profile_verification_uuidv4,parser_profile_uuidv4,required_verification_outcome)
   REFERENCES parser_profile_verifications(parser_profile_verification_uuidv4,parser_profile_uuidv4,outcome)
) STRICT;
CREATE TABLE parser_profile_selection_predecessors (
 selection_decision_uuidv4 TEXT NOT NULL,
 predecessor_decision_uuidv4 TEXT NOT NULL,
 selection_scope_uuidv4 TEXT NOT NULL,
 PRIMARY KEY(selection_decision_uuidv4,predecessor_decision_uuidv4),
 CHECK(selection_decision_uuidv4<>predecessor_decision_uuidv4),
 FOREIGN KEY(selection_decision_uuidv4,selection_scope_uuidv4)
  REFERENCES parser_profile_selection_decisions(selection_decision_uuidv4,selection_scope_uuidv4),
 FOREIGN KEY(predecessor_decision_uuidv4,selection_scope_uuidv4)
  REFERENCES parser_profile_selection_decisions(selection_decision_uuidv4,selection_scope_uuidv4)
) STRICT;
CREATE TRIGGER parser_profile_predecessor_no_cycle
 BEFORE INSERT ON parser_profile_selection_predecessors
 BEGIN
   SELECT RAISE(ABORT,'parser profile selection DAG cycle')
   WHERE EXISTS (
     WITH RECURSIVE ancestors(uid) AS (
       SELECT NEW.predecessor_decision_uuidv4
       UNION
       SELECT p.predecessor_decision_uuidv4
         FROM parser_profile_selection_predecessors p
         JOIN ancestors a ON p.selection_decision_uuidv4=a.uid
     )
     SELECT 1 FROM ancestors WHERE uid=NEW.selection_decision_uuidv4
   );
 END;

-- D8/D9: missing dependency is durable, but not promoted as valid FK row.
-- Writers validate/publish from this staging table atomically after arrival.
CREATE TABLE parser_profile_selection_staging (
 selection_decision_uuidv4 TEXT PRIMARY KEY,
 selection_scope_uuidv4 TEXT NOT NULL,
 record_json TEXT NOT NULL CHECK(json_valid(record_json) AND json_type(record_json)='object'),
 unresolved_reason TEXT NOT NULL,
 received_at_us INTEGER
) STRICT;

-- A unique DAG head is necessary but not enough: trust/invalidation count.
CREATE VIEW active_parser_profile_selections AS
WITH heads AS (
 SELECT d.*
   FROM parser_profile_selection_decisions d
   JOIN parser_profile_selection_publications pub USING(selection_decision_uuidv4)
  WHERE NOT EXISTS (
     SELECT 1 FROM parser_profile_selection_predecessors p JOIN parser_profile_selection_publications ppub ON ppub.selection_decision_uuidv4=p.selection_decision_uuidv4
      WHERE p.predecessor_decision_uuidv4=d.selection_decision_uuidv4
  )
), counts AS (
 SELECT selection_scope_uuidv4,COUNT(*) AS head_count
   FROM heads GROUP BY selection_scope_uuidv4
)
SELECT h.selection_scope_uuidv4,h.selection_decision_uuidv4,
       h.parser_profile_uuidv4,h.parser_profile_verification_uuidv4
  FROM heads h JOIN counts c USING(selection_scope_uuidv4)
  JOIN local_parser_profile_verification_trust t
    ON t.parser_profile_verification_uuidv4=h.parser_profile_verification_uuidv4
 WHERE c.head_count=1 AND t.trusted=1
   AND NOT EXISTS(SELECT 1 FROM exchange_selection_blocks b WHERE b.scope_kind='profile' AND b.scope_uuidv4=h.selection_scope_uuidv4)
   AND NOT EXISTS (
     SELECT 1 FROM parser_profile_verification_invalidations i
      WHERE i.parser_profile_verification_uuidv4=h.parser_profile_verification_uuidv4
   )
   AND NOT EXISTS(SELECT 1 FROM parser_profile_selection_decisions ud WHERE ud.selection_scope_uuidv4=h.selection_scope_uuidv4 AND NOT EXISTS(SELECT 1 FROM parser_profile_selection_publications up WHERE up.selection_decision_uuidv4=ud.selection_decision_uuidv4))
   AND NOT EXISTS (
     SELECT 1 FROM parser_profile_selection_staging st
      WHERE st.selection_scope_uuidv4=h.selection_scope_uuidv4
   );

-- D32 A: a present but unresolved CR-specific scope BLOCKS repository fallback.
CREATE VIEW effective_change_request_parser_profiles AS
WITH keys AS (
 SELECT cr.change_request_id,rs.fact_kind
 FROM change_requests cr
 JOIN parser_profile_selection_scopes rs
   ON rs.repository_uuidv4=cr.repository_uuidv4
  AND rs.owner_kind='repository' AND rs.change_request_id IS NULL
 UNION
 SELECT cs.change_request_id,cs.fact_kind
 FROM parser_profile_selection_scopes cs
 WHERE cs.owner_kind='repository' AND cs.change_request_id IS NOT NULL
)
SELECT k.change_request_id,k.fact_kind,
       CASE WHEN cs.selection_scope_uuidv4 IS NOT NULL
            THEN ca.parser_profile_uuidv4 ELSE ra.parser_profile_uuidv4 END AS parser_profile_uuidv4,
       CASE WHEN cs.selection_scope_uuidv4 IS NOT NULL
            THEN ca.selection_decision_uuidv4 ELSE ra.selection_decision_uuidv4 END AS selection_decision_uuidv4,
       CASE WHEN cs.selection_scope_uuidv4 IS NOT NULL THEN 'change_request'
            ELSE 'repository' END AS chosen_scope_kind
  FROM keys k
  JOIN change_requests cr ON cr.change_request_id=k.change_request_id
  LEFT JOIN parser_profile_selection_scopes rs
    ON rs.repository_uuidv4=cr.repository_uuidv4
   AND rs.fact_kind=k.fact_kind AND rs.owner_kind='repository' AND rs.change_request_id IS NULL
  LEFT JOIN active_parser_profile_selections ra
    ON ra.selection_scope_uuidv4=rs.selection_scope_uuidv4
  LEFT JOIN parser_profile_selection_scopes cs
    ON cs.change_request_id=k.change_request_id
   AND cs.fact_kind=k.fact_kind AND cs.owner_kind='repository'
  LEFT JOIN active_parser_profile_selections ca
    ON ca.selection_scope_uuidv4=cs.selection_scope_uuidv4;

CREATE VIEW effective_source_parser_profiles AS
SELECT ss.source_registration_uuidv4,ss.fact_kind,
       a.parser_profile_uuidv4,a.selection_decision_uuidv4
  FROM parser_profile_selection_scopes ss
  LEFT JOIN active_parser_profile_selections a
    ON a.selection_scope_uuidv4=ss.selection_scope_uuidv4
 WHERE ss.owner_kind='source';

-- Candidate filtering ONLY: fact-current DAG resolution remains independent.
CREATE VIEW eligible_document_observations AS
SELECT d.document_observation_id,d.document_observation_uuidv4,
       d.change_request_id,d.repository_uuidv4,d.kind,
       d.provider_change_request_document_id,d.parsed_result_uuidv4
 FROM document_observations d
 JOIN parsed_result_publications pub ON pub.parsed_result_uuidv4=d.parsed_result_uuidv4
 JOIN parsed_results p ON p.parsed_result_uuidv4=d.parsed_result_uuidv4
 JOIN effective_change_request_parser_profiles e
   ON e.change_request_id=d.change_request_id
  AND e.fact_kind=d.kind
  AND e.parser_profile_uuidv4=p.parser_profile_uuidv4;

-- A published result must use a profile that declares its owner type.
CREATE TRIGGER parsed_result_publication_owner_capability
 BEFORE INSERT ON parsed_result_publications
 WHEN NOT EXISTS (
    SELECT 1 FROM parsed_results p JOIN parser_profile_capabilities c
      ON c.parser_profile_uuidv4=p.parser_profile_uuidv4
     AND c.owner_kind=p.owner_kind
     WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4
 ) BEGIN SELECT RAISE(ABORT,'parser profile does not support parsed result owner type'); END;

-- FK indexes for frequent ownership joins and DAG head/verification resolution.
CREATE INDEX parsed_results_repository_owner_idx
 ON parsed_results(repository_uuidv4) WHERE repository_uuidv4 IS NOT NULL;
CREATE INDEX parsed_results_source_owner_idx
 ON parsed_results(source_registration_uuidv4) WHERE source_registration_uuidv4 IS NOT NULL;
CREATE INDEX parsed_results_profile_idx ON parsed_results(parser_profile_uuidv4);
CREATE INDEX parsed_inputs_fetch_idx ON parsed_result_inputs(fetch_occurrence_uuidv4);
CREATE INDEX parsed_inputs_source_idx ON parsed_result_inputs(source_input_uuidv4);
CREATE INDEX parsed_inputs_git_idx ON parsed_result_inputs(git_acquisition_id);
CREATE INDEX verification_profile_idx ON parser_profile_verifications(parser_profile_uuidv4);
CREATE INDEX verification_invalidation_idx ON parser_profile_verification_invalidations(parser_profile_verification_uuidv4);
CREATE INDEX selection_decision_scope_idx ON parser_profile_selection_decisions(selection_scope_uuidv4);
CREATE INDEX selection_predecessor_reverse_idx ON parser_profile_selection_predecessors(predecessor_decision_uuidv4);
CREATE INDEX document_parsed_result_idx ON document_observations(parsed_result_uuidv4);

-- Protect independent, immutable evidence/decisions against mutation/deletion.
-- Existing catalog retention guards remain in force for its existing entities.
CREATE TRIGGER source_input_observations_reject_update BEFORE UPDATE ON source_input_observations
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER source_input_observations_reject_delete BEFORE DELETE ON source_input_observations
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;
CREATE TRIGGER parser_profiles_reject_update BEFORE UPDATE ON parser_profiles
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER parser_profiles_reject_delete BEFORE DELETE ON parser_profiles
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;
CREATE TRIGGER parser_profile_capabilities_reject_update BEFORE UPDATE ON parser_profile_capabilities
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER parser_profile_capabilities_reject_delete BEFORE DELETE ON parser_profile_capabilities
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;
CREATE TRIGGER parser_profile_verifications_reject_update BEFORE UPDATE ON parser_profile_verifications
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER parser_profile_verifications_reject_delete BEFORE DELETE ON parser_profile_verifications
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;
CREATE TRIGGER parser_profile_verification_invalidations_reject_update BEFORE UPDATE ON parser_profile_verification_invalidations
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER parser_profile_verification_invalidations_reject_delete BEFORE DELETE ON parser_profile_verification_invalidations
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;
CREATE TRIGGER parsed_results_reject_update BEFORE UPDATE ON parsed_results
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER parsed_results_reject_delete BEFORE DELETE ON parsed_results
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;
CREATE TRIGGER parsed_result_inputs_reject_update BEFORE UPDATE ON parsed_result_inputs
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER parsed_result_inputs_reject_delete BEFORE DELETE ON parsed_result_inputs
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;








CREATE TRIGGER parser_profile_selection_scopes_reject_update BEFORE UPDATE ON parser_profile_selection_scopes
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER parser_profile_selection_scopes_reject_delete BEFORE DELETE ON parser_profile_selection_scopes
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;
CREATE TRIGGER parser_profile_selection_decisions_reject_update BEFORE UPDATE ON parser_profile_selection_decisions
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER parser_profile_selection_decisions_reject_delete BEFORE DELETE ON parser_profile_selection_decisions
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;
CREATE TRIGGER parser_profile_selection_predecessors_reject_update BEFORE UPDATE ON parser_profile_selection_predecessors
BEGIN SELECT RAISE(ABORT,'immutable evidence/decision'); END;
CREATE TRIGGER parser_profile_selection_predecessors_reject_delete BEFORE DELETE ON parser_profile_selection_predecessors
BEGIN SELECT RAISE(ABORT,'retained evidence/decision'); END;
CREATE TRIGGER parsed_result_publications_reject_update BEFORE UPDATE ON parsed_result_publications BEGIN SELECT RAISE(ABORT,'immutable publication'); END;
CREATE TRIGGER parsed_result_publications_reject_delete BEFORE DELETE ON parsed_result_publications BEGIN SELECT RAISE(ABORT,'retained publication'); END;
CREATE TRIGGER source_input_observations_uuid4_validate BEFORE INSERT ON source_input_observations WHEN NOT (length(NEW.source_input_uuidv4)=36 AND length(CAST(NEW.source_input_uuidv4 AS BLOB))=36 AND substr(NEW.source_input_uuidv4,9,1)='-' AND substr(NEW.source_input_uuidv4,14,1)='-' AND substr(NEW.source_input_uuidv4,19,1)='-' AND substr(NEW.source_input_uuidv4,24,1)='-' AND length(replace(NEW.source_input_uuidv4,'-',''))=32 AND replace(NEW.source_input_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.source_input_uuidv4,15,1)='4' AND substr(NEW.source_input_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER parser_profiles_uuid4_validate BEFORE INSERT ON parser_profiles WHEN NOT (length(NEW.parser_profile_uuidv4)=36 AND length(CAST(NEW.parser_profile_uuidv4 AS BLOB))=36 AND substr(NEW.parser_profile_uuidv4,9,1)='-' AND substr(NEW.parser_profile_uuidv4,14,1)='-' AND substr(NEW.parser_profile_uuidv4,19,1)='-' AND substr(NEW.parser_profile_uuidv4,24,1)='-' AND length(replace(NEW.parser_profile_uuidv4,'-',''))=32 AND replace(NEW.parser_profile_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.parser_profile_uuidv4,15,1)='4' AND substr(NEW.parser_profile_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER parser_profile_verifications_uuid4_validate BEFORE INSERT ON parser_profile_verifications WHEN NOT (length(NEW.parser_profile_verification_uuidv4)=36 AND length(CAST(NEW.parser_profile_verification_uuidv4 AS BLOB))=36 AND substr(NEW.parser_profile_verification_uuidv4,9,1)='-' AND substr(NEW.parser_profile_verification_uuidv4,14,1)='-' AND substr(NEW.parser_profile_verification_uuidv4,19,1)='-' AND substr(NEW.parser_profile_verification_uuidv4,24,1)='-' AND length(replace(NEW.parser_profile_verification_uuidv4,'-',''))=32 AND replace(NEW.parser_profile_verification_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.parser_profile_verification_uuidv4,15,1)='4' AND substr(NEW.parser_profile_verification_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER parser_profile_verification_invalidations_uuid4_validate BEFORE INSERT ON parser_profile_verification_invalidations WHEN NOT (length(NEW.invalidation_uuidv4)=36 AND length(CAST(NEW.invalidation_uuidv4 AS BLOB))=36 AND substr(NEW.invalidation_uuidv4,9,1)='-' AND substr(NEW.invalidation_uuidv4,14,1)='-' AND substr(NEW.invalidation_uuidv4,19,1)='-' AND substr(NEW.invalidation_uuidv4,24,1)='-' AND length(replace(NEW.invalidation_uuidv4,'-',''))=32 AND replace(NEW.invalidation_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.invalidation_uuidv4,15,1)='4' AND substr(NEW.invalidation_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER parsed_results_uuid4_validate BEFORE INSERT ON parsed_results WHEN NOT (length(NEW.parsed_result_uuidv4)=36 AND length(CAST(NEW.parsed_result_uuidv4 AS BLOB))=36 AND substr(NEW.parsed_result_uuidv4,9,1)='-' AND substr(NEW.parsed_result_uuidv4,14,1)='-' AND substr(NEW.parsed_result_uuidv4,19,1)='-' AND substr(NEW.parsed_result_uuidv4,24,1)='-' AND length(replace(NEW.parsed_result_uuidv4,'-',''))=32 AND replace(NEW.parsed_result_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.parsed_result_uuidv4,15,1)='4' AND substr(NEW.parsed_result_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;



CREATE TRIGGER parser_profile_selection_scopes_uuid4_validate BEFORE INSERT ON parser_profile_selection_scopes WHEN NOT (length(NEW.selection_scope_uuidv4)=36 AND length(CAST(NEW.selection_scope_uuidv4 AS BLOB))=36 AND substr(NEW.selection_scope_uuidv4,9,1)='-' AND substr(NEW.selection_scope_uuidv4,14,1)='-' AND substr(NEW.selection_scope_uuidv4,19,1)='-' AND substr(NEW.selection_scope_uuidv4,24,1)='-' AND length(replace(NEW.selection_scope_uuidv4,'-',''))=32 AND replace(NEW.selection_scope_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.selection_scope_uuidv4,15,1)='4' AND substr(NEW.selection_scope_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER parser_profile_selection_decisions_uuid4_validate BEFORE INSERT ON parser_profile_selection_decisions WHEN NOT (length(NEW.selection_decision_uuidv4)=36 AND length(CAST(NEW.selection_decision_uuidv4 AS BLOB))=36 AND substr(NEW.selection_decision_uuidv4,9,1)='-' AND substr(NEW.selection_decision_uuidv4,14,1)='-' AND substr(NEW.selection_decision_uuidv4,19,1)='-' AND substr(NEW.selection_decision_uuidv4,24,1)='-' AND length(replace(NEW.selection_decision_uuidv4,'-',''))=32 AND replace(NEW.selection_decision_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.selection_decision_uuidv4,15,1)='4' AND substr(NEW.selection_decision_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER parser_profile_selection_staging_uuid4_validate BEFORE INSERT ON parser_profile_selection_staging WHEN NOT (length(NEW.selection_decision_uuidv4)=36 AND length(CAST(NEW.selection_decision_uuidv4 AS BLOB))=36 AND substr(NEW.selection_decision_uuidv4,9,1)='-' AND substr(NEW.selection_decision_uuidv4,14,1)='-' AND substr(NEW.selection_decision_uuidv4,19,1)='-' AND substr(NEW.selection_decision_uuidv4,24,1)='-' AND length(replace(NEW.selection_decision_uuidv4,'-',''))=32 AND replace(NEW.selection_decision_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.selection_decision_uuidv4,15,1)='4' AND substr(NEW.selection_decision_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER repositories_portable_uuid4 BEFORE INSERT ON repositories WHEN NOT (length(NEW.repository_uuidv4)=36 AND length(CAST(NEW.repository_uuidv4 AS BLOB))=36 AND substr(NEW.repository_uuidv4,9,1)='-' AND substr(NEW.repository_uuidv4,14,1)='-' AND substr(NEW.repository_uuidv4,19,1)='-' AND substr(NEW.repository_uuidv4,24,1)='-' AND length(replace(NEW.repository_uuidv4,'-',''))=32 AND replace(NEW.repository_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.repository_uuidv4,15,1)='4' AND substr(NEW.repository_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER fetch_occurrences_portable_uuid4 BEFORE INSERT ON fetch_occurrences WHEN NOT (length(NEW.fetch_occurrence_uuidv4)=36 AND length(CAST(NEW.fetch_occurrence_uuidv4 AS BLOB))=36 AND substr(NEW.fetch_occurrence_uuidv4,9,1)='-' AND substr(NEW.fetch_occurrence_uuidv4,14,1)='-' AND substr(NEW.fetch_occurrence_uuidv4,19,1)='-' AND substr(NEW.fetch_occurrence_uuidv4,24,1)='-' AND length(replace(NEW.fetch_occurrence_uuidv4,'-',''))=32 AND replace(NEW.fetch_occurrence_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.fetch_occurrence_uuidv4,15,1)='4' AND substr(NEW.fetch_occurrence_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER change_request_observations_portable_uuid4 BEFORE INSERT ON change_request_observations WHEN NOT (length(NEW.change_request_observation_uuidv4)=36 AND length(CAST(NEW.change_request_observation_uuidv4 AS BLOB))=36 AND substr(NEW.change_request_observation_uuidv4,9,1)='-' AND substr(NEW.change_request_observation_uuidv4,14,1)='-' AND substr(NEW.change_request_observation_uuidv4,19,1)='-' AND substr(NEW.change_request_observation_uuidv4,24,1)='-' AND length(replace(NEW.change_request_observation_uuidv4,'-',''))=32 AND replace(NEW.change_request_observation_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.change_request_observation_uuidv4,15,1)='4' AND substr(NEW.change_request_observation_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER document_observations_portable_uuid4 BEFORE INSERT ON document_observations WHEN NOT (length(NEW.document_observation_uuidv4)=36 AND length(CAST(NEW.document_observation_uuidv4 AS BLOB))=36 AND substr(NEW.document_observation_uuidv4,9,1)='-' AND substr(NEW.document_observation_uuidv4,14,1)='-' AND substr(NEW.document_observation_uuidv4,19,1)='-' AND substr(NEW.document_observation_uuidv4,24,1)='-' AND length(replace(NEW.document_observation_uuidv4,'-',''))=32 AND replace(NEW.document_observation_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.document_observation_uuidv4,15,1)='4' AND substr(NEW.document_observation_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER code_observations_portable_uuid4 BEFORE INSERT ON code_observations WHEN NOT (length(NEW.code_observation_uuidv4)=36 AND length(CAST(NEW.code_observation_uuidv4 AS BLOB))=36 AND substr(NEW.code_observation_uuidv4,9,1)='-' AND substr(NEW.code_observation_uuidv4,14,1)='-' AND substr(NEW.code_observation_uuidv4,19,1)='-' AND substr(NEW.code_observation_uuidv4,24,1)='-' AND length(replace(NEW.code_observation_uuidv4,'-',''))=32 AND replace(NEW.code_observation_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.code_observation_uuidv4,15,1)='4' AND substr(NEW.code_observation_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER change_request_events_portable_uuid4 BEFORE INSERT ON change_request_events WHEN NOT (length(NEW.change_request_event_uuidv4)=36 AND length(CAST(NEW.change_request_event_uuidv4 AS BLOB))=36 AND substr(NEW.change_request_event_uuidv4,9,1)='-' AND substr(NEW.change_request_event_uuidv4,14,1)='-' AND substr(NEW.change_request_event_uuidv4,19,1)='-' AND substr(NEW.change_request_event_uuidv4,24,1)='-' AND length(replace(NEW.change_request_event_uuidv4,'-',''))=32 AND replace(NEW.change_request_event_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.change_request_event_uuidv4,15,1)='4' AND substr(NEW.change_request_event_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER inventory_observations_portable_uuid4 BEFORE INSERT ON inventory_observations WHEN NOT (length(NEW.inventory_observation_id)=36 AND length(CAST(NEW.inventory_observation_id AS BLOB))=36 AND substr(NEW.inventory_observation_id,9,1)='-' AND substr(NEW.inventory_observation_id,14,1)='-' AND substr(NEW.inventory_observation_id,19,1)='-' AND substr(NEW.inventory_observation_id,24,1)='-' AND length(replace(NEW.inventory_observation_id,'-',''))=32 AND replace(NEW.inventory_observation_id,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.inventory_observation_id,15,1)='4' AND substr(NEW.inventory_observation_id,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;

-- Immutable manifests close late edge/input/fact additions at their admission boundary.
CREATE TRIGGER parsed_input_manifest_match BEFORE INSERT ON parsed_result_inputs
WHEN NOT EXISTS (
 SELECT 1 FROM parsed_results p, json_each(p.input_manifest_json) m
 WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND CAST(m.key AS INTEGER)=NEW.input_ordinal
 AND json_extract(m.value,'$.fetch_occurrence_uuidv4') IS NEW.fetch_occurrence_uuidv4
 AND json_extract(m.value,'$.git_acquisition_id') IS NEW.git_acquisition_id
 AND json_extract(m.value,'$.source_input_uuidv4') IS NEW.source_input_uuidv4
) BEGIN SELECT RAISE(ABORT,'input differs from immutable manifest'); END;
CREATE TRIGGER parsed_publication_manifest_count BEFORE INSERT ON parsed_result_publications
WHEN NEW.declared_input_count<>(SELECT json_array_length(input_manifest_json) FROM parsed_results WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4)
BEGIN SELECT RAISE(ABORT,'publication differs from immutable input manifest'); END;
CREATE TRIGGER parser_profile_capability_sealed BEFORE INSERT ON parser_profile_capabilities
WHEN EXISTS(SELECT 1 FROM parser_profile_verifications WHERE parser_profile_uuidv4=NEW.parser_profile_uuidv4)
BEGIN SELECT RAISE(ABORT,'verified profile capabilities sealed'); END;
CREATE TRIGGER parser_verification_evidence_complete BEFORE INSERT ON parser_profile_verifications
WHEN NEW.outcome='passed' AND (
 coalesce(json_type(NEW.evidence_json,'$.capabilities'),'')<>'array'
 OR coalesce(json_type(NEW.evidence_json,'$.definition'),'')<>'object'
 OR json_extract(NEW.evidence_json,'$.definition') <> (SELECT json(definition_json) FROM parser_profiles WHERE parser_profile_uuidv4=NEW.parser_profile_uuidv4)
 OR (SELECT count(*) FROM json_each(NEW.evidence_json,'$.capabilities'))<>(SELECT count(*) FROM parser_profile_capabilities WHERE parser_profile_uuidv4=NEW.parser_profile_uuidv4)
 OR EXISTS(SELECT 1 FROM parser_profile_capabilities c WHERE c.parser_profile_uuidv4=NEW.parser_profile_uuidv4 AND NOT EXISTS(SELECT 1 FROM json_each(NEW.evidence_json,'$.capabilities') e WHERE json_extract(e.value,'$.owner_kind')=c.owner_kind AND json_extract(e.value,'$.fact_kind')=c.fact_kind AND json_extract(e.value,'$.outcome')='passed' AND coalesce(json_type(e.value,'$.checks'),'')='array' AND json_array_length(e.value,'$.checks')>0))
) BEGIN SELECT RAISE(ABORT,'passed verification requires evidence for entire definition'); END;
CREATE TRIGGER parser_selection_edge_manifest BEFORE INSERT ON parser_profile_selection_predecessors
WHEN EXISTS(SELECT 1 FROM parser_profile_selection_publications WHERE selection_decision_uuidv4=NEW.selection_decision_uuidv4)
 OR NOT EXISTS(SELECT 1 FROM parser_profile_selection_decisions d,json_each(d.predecessor_manifest_json) m WHERE d.selection_decision_uuidv4=NEW.selection_decision_uuidv4 AND m.value=NEW.predecessor_decision_uuidv4)
BEGIN SELECT RAISE(ABORT,'selection predecessor manifest is sealed or inconsistent'); END;
CREATE TRIGGER parser_selection_publish_manifest BEFORE INSERT ON parser_profile_selection_publications
WHEN (SELECT count(*) FROM parser_profile_selection_predecessors WHERE selection_decision_uuidv4=NEW.selection_decision_uuidv4)<>(SELECT json_array_length(predecessor_manifest_json) FROM parser_profile_selection_decisions WHERE selection_decision_uuidv4=NEW.selection_decision_uuidv4)
 OR EXISTS(SELECT 1 FROM parser_profile_selection_predecessors e WHERE e.selection_decision_uuidv4=NEW.selection_decision_uuidv4 AND NOT EXISTS(SELECT 1 FROM parser_profile_selection_publications p WHERE p.selection_decision_uuidv4=e.predecessor_decision_uuidv4))
BEGIN SELECT RAISE(ABORT,'selection dependencies are not fully sealed'); END;
CREATE TRIGGER parser_selection_publication_immutable BEFORE UPDATE ON parser_profile_selection_publications BEGIN SELECT RAISE(ABORT,'immutable selection publication'); END;
CREATE TRIGGER parser_selection_publication_retained BEFORE DELETE ON parser_profile_selection_publications BEGIN SELECT RAISE(ABORT,'retained selection publication'); END;

CREATE TABLE review_thread_observations(
 thread_observation_uuidv4 TEXT PRIMARY KEY,
 repository_uuidv4 TEXT NOT NULL,
 change_request_id TEXT NOT NULL,
 provider_resource_id TEXT NOT NULL,
 parsed_result_uuidv4 TEXT NOT NULL,
 observed_at_us INTEGER,
 payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'),
 UNIQUE(parsed_result_uuidv4,change_request_id,provider_resource_id),
 FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4),
 FOREIGN KEY(change_request_id,provider_resource_id) REFERENCES review_threads(change_request_id,provider_resource_id),
 FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4)
) STRICT;

CREATE TABLE fact_selection_scopes(
 fact_selection_scope_uuidv4 TEXT PRIMARY KEY,
 owner_kind TEXT NOT NULL CHECK(owner_kind IN ('repository','source')),
 repository_uuidv4 TEXT REFERENCES repositories(repository_uuidv4),
 source_registration_uuidv4 TEXT REFERENCES sources(source_registration_uuidv4),
 change_request_id TEXT,
 fact_kind TEXT NOT NULL CHECK(length(fact_kind)>0),
 kind TEXT,
 provider_change_request_document_id TEXT,
 provider_resource_id TEXT,
 fetch_occurrence_uuidv4 TEXT,
 git_acquisition_id TEXT,
 CHECK((owner_kind='repository' AND repository_uuidv4 IS NOT NULL AND source_registration_uuidv4 IS NULL) OR (owner_kind='source' AND repository_uuidv4 IS NULL AND source_registration_uuidv4 IS NOT NULL AND change_request_id IS NULL)),
 CHECK((kind IS NULL AND provider_change_request_document_id IS NULL) OR (kind IS NOT NULL AND provider_change_request_document_id IS NOT NULL AND change_request_id IS NOT NULL AND fact_kind=kind)),
 CHECK(provider_resource_id IS NULL OR (change_request_id IS NOT NULL AND fact_kind='review-thread' AND kind IS NULL)),
 CHECK(fetch_occurrence_uuidv4 IS NULL OR (repository_uuidv4 IS NOT NULL AND change_request_id IS NOT NULL AND fact_kind IN ('events','code') AND kind IS NULL AND provider_resource_id IS NULL)),
 CHECK(git_acquisition_id IS NULL OR (repository_uuidv4 IS NOT NULL AND change_request_id IS NULL AND fact_kind='git' AND kind IS NULL AND provider_resource_id IS NULL AND fetch_occurrence_uuidv4 IS NULL)),
 FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4),
 FOREIGN KEY(fetch_occurrence_uuidv4,repository_uuidv4) REFERENCES fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4),
 UNIQUE(fact_selection_scope_uuidv4,repository_uuidv4),
 UNIQUE(fact_selection_scope_uuidv4,source_registration_uuidv4),
 FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4),
 FOREIGN KEY(change_request_id,kind,provider_change_request_document_id) REFERENCES documents(change_request_id,kind,provider_change_request_document_id),
 FOREIGN KEY(change_request_id,provider_resource_id) REFERENCES review_threads(change_request_id,provider_resource_id)
) STRICT;
CREATE UNIQUE INDEX fact_selection_scope_identity ON fact_selection_scopes(owner_kind,coalesce(repository_uuidv4,''),coalesce(source_registration_uuidv4,''),coalesce(change_request_id,''),fact_kind,coalesce(kind,''),coalesce(provider_change_request_document_id,''),coalesce(provider_resource_id,''),coalesce(fetch_occurrence_uuidv4,''),coalesce(git_acquisition_id,''));
CREATE TABLE fact_selection_decisions(
 fact_selection_decision_uuidv4 TEXT PRIMARY KEY,
 fact_selection_scope_uuidv4 TEXT NOT NULL REFERENCES fact_selection_scopes(fact_selection_scope_uuidv4),
 parsed_result_uuidv4 TEXT NOT NULL REFERENCES parsed_result_publications(parsed_result_uuidv4),
 repository_uuidv4 TEXT, source_registration_uuidv4 TEXT,
 predecessor_manifest_json TEXT NOT NULL CHECK(json_valid(predecessor_manifest_json) AND json_type(predecessor_manifest_json)='array'),
 issuer TEXT NOT NULL CHECK(length(issuer)>0), decided_at_us INTEGER,
 CHECK((repository_uuidv4 IS NOT NULL AND source_registration_uuidv4 IS NULL) OR (repository_uuidv4 IS NULL AND source_registration_uuidv4 IS NOT NULL)),
 UNIQUE(fact_selection_decision_uuidv4,fact_selection_scope_uuidv4),
 FOREIGN KEY(fact_selection_scope_uuidv4,repository_uuidv4) REFERENCES fact_selection_scopes(fact_selection_scope_uuidv4,repository_uuidv4),
 FOREIGN KEY(fact_selection_scope_uuidv4,source_registration_uuidv4) REFERENCES fact_selection_scopes(fact_selection_scope_uuidv4,source_registration_uuidv4),
 FOREIGN KEY(parsed_result_uuidv4,repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4),
 FOREIGN KEY(parsed_result_uuidv4,source_registration_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,source_registration_uuidv4)
) STRICT;
CREATE TABLE fact_selection_predecessors(
 fact_selection_decision_uuidv4 TEXT NOT NULL,
 predecessor_decision_uuidv4 TEXT NOT NULL,
 fact_selection_scope_uuidv4 TEXT NOT NULL,
 PRIMARY KEY(fact_selection_decision_uuidv4,predecessor_decision_uuidv4),
 CHECK(fact_selection_decision_uuidv4<>predecessor_decision_uuidv4),
 FOREIGN KEY(fact_selection_decision_uuidv4,fact_selection_scope_uuidv4) REFERENCES fact_selection_decisions(fact_selection_decision_uuidv4,fact_selection_scope_uuidv4),
 FOREIGN KEY(predecessor_decision_uuidv4,fact_selection_scope_uuidv4) REFERENCES fact_selection_decisions(fact_selection_decision_uuidv4,fact_selection_scope_uuidv4)
) STRICT;
CREATE TABLE fact_selection_publications(
 fact_selection_decision_uuidv4 TEXT PRIMARY KEY REFERENCES fact_selection_decisions(fact_selection_decision_uuidv4)
) STRICT;
CREATE INDEX fact_selection_decision_scope_idx ON fact_selection_decisions(fact_selection_scope_uuidv4);
CREATE INDEX fact_selection_predecessor_reverse_idx ON fact_selection_predecessors(predecessor_decision_uuidv4);
CREATE TABLE fact_selection_staging(
 fact_selection_decision_uuidv4 TEXT PRIMARY KEY,
 fact_selection_scope_uuidv4 TEXT NOT NULL,
 record_json TEXT NOT NULL CHECK(json_valid(record_json) AND json_type(record_json)='object'),
 unresolved_reason TEXT NOT NULL,
 received_at_us INTEGER
) STRICT;
CREATE TRIGGER fact_selection_edge_manifest BEFORE INSERT ON fact_selection_predecessors
WHEN EXISTS(SELECT 1 FROM fact_selection_publications WHERE fact_selection_decision_uuidv4=NEW.fact_selection_decision_uuidv4)
 OR NOT EXISTS(SELECT 1 FROM fact_selection_decisions d,json_each(d.predecessor_manifest_json) m WHERE d.fact_selection_decision_uuidv4=NEW.fact_selection_decision_uuidv4 AND m.value=NEW.predecessor_decision_uuidv4)
BEGIN SELECT RAISE(ABORT,'fact predecessor manifest is sealed or inconsistent'); END;
CREATE TRIGGER fact_selection_edge_cycle BEFORE INSERT ON fact_selection_predecessors BEGIN
 SELECT RAISE(ABORT,'fact selection DAG cycle') WHERE EXISTS(WITH RECURSIVE ancestors(uid) AS (SELECT NEW.predecessor_decision_uuidv4 UNION SELECT e.predecessor_decision_uuidv4 FROM fact_selection_predecessors e JOIN ancestors a ON e.fact_selection_decision_uuidv4=a.uid) SELECT 1 FROM ancestors WHERE uid=NEW.fact_selection_decision_uuidv4);
END;
CREATE TRIGGER fact_selection_publish_manifest BEFORE INSERT ON fact_selection_publications
WHEN (SELECT count(*) FROM fact_selection_predecessors WHERE fact_selection_decision_uuidv4=NEW.fact_selection_decision_uuidv4)<>(SELECT json_array_length(predecessor_manifest_json) FROM fact_selection_decisions WHERE fact_selection_decision_uuidv4=NEW.fact_selection_decision_uuidv4)
 OR EXISTS(SELECT 1 FROM fact_selection_predecessors e WHERE e.fact_selection_decision_uuidv4=NEW.fact_selection_decision_uuidv4 AND NOT EXISTS(SELECT 1 FROM fact_selection_publications p WHERE p.fact_selection_decision_uuidv4=e.predecessor_decision_uuidv4))
BEGIN SELECT RAISE(ABORT,'fact decision dependencies are not fully sealed'); END;

-- No digest recomputation on reads: local quarantine propagates along typed inputs.
CREATE VIEW usable_parsed_results AS
SELECT r.* FROM parsed_results r JOIN parsed_result_publications p USING(parsed_result_uuidv4)
WHERE NOT EXISTS(SELECT 1 FROM exchange_blocked_results b WHERE b.parsed_result_uuidv4=r.parsed_result_uuidv4)
AND NOT EXISTS(SELECT 1 FROM parsed_result_inputs i JOIN fetch_occurrences f ON f.fetch_occurrence_uuidv4=i.fetch_occurrence_uuidv4 JOIN payload_quarantine q ON q.sha256=f.payload_sha256 WHERE i.parsed_result_uuidv4=r.parsed_result_uuidv4)
AND NOT EXISTS(SELECT 1 FROM parsed_result_inputs i JOIN source_input_observations f ON f.source_input_uuidv4=i.source_input_uuidv4 JOIN payload_quarantine q ON q.sha256=f.payload_sha256 WHERE i.parsed_result_uuidv4=r.parsed_result_uuidv4)
AND NOT EXISTS(SELECT 1 FROM parsed_result_inputs i JOIN repository_object_sources o ON o.git_acquisition_id=i.git_acquisition_id AND o.repository_uuidv4=i.repository_uuidv4 JOIN git_object_payloads b ON b.git_object_id=o.git_object_id JOIN payload_quarantine q ON q.sha256=b.payload_sha256 WHERE i.parsed_result_uuidv4=r.parsed_result_uuidv4);
CREATE VIEW effective_repository_parser_profiles AS
SELECT s.repository_uuidv4,s.fact_kind,a.parser_profile_uuidv4,a.selection_decision_uuidv4
FROM parser_profile_selection_scopes s LEFT JOIN active_parser_profile_selections a USING(selection_scope_uuidv4)
WHERE s.owner_kind='repository' AND s.change_request_id IS NULL;
CREATE VIEW active_fact_selections AS
WITH heads AS (
 SELECT d.* FROM fact_selection_decisions d JOIN fact_selection_publications p USING(fact_selection_decision_uuidv4)
 WHERE NOT EXISTS(SELECT 1 FROM fact_selection_predecessors e JOIN fact_selection_publications ep ON ep.fact_selection_decision_uuidv4=e.fact_selection_decision_uuidv4 WHERE e.predecessor_decision_uuidv4=d.fact_selection_decision_uuidv4)
), counts AS (SELECT fact_selection_scope_uuidv4,count(*) n FROM heads GROUP BY fact_selection_scope_uuidv4)
SELECT s.*,h.fact_selection_decision_uuidv4,h.parsed_result_uuidv4
FROM heads h JOIN counts c USING(fact_selection_scope_uuidv4) JOIN fact_selection_scopes s USING(fact_selection_scope_uuidv4)
JOIN usable_parsed_results r USING(parsed_result_uuidv4)
WHERE c.n=1
AND NOT EXISTS(SELECT 1 FROM exchange_selection_blocks b WHERE b.scope_kind='fact' AND b.scope_uuidv4=s.fact_selection_scope_uuidv4)
AND NOT EXISTS(SELECT 1 FROM exchange_blocked_results b WHERE b.parsed_result_uuidv4=h.parsed_result_uuidv4)
AND NOT EXISTS(SELECT 1 FROM fact_selection_staging st WHERE st.fact_selection_scope_uuidv4=s.fact_selection_scope_uuidv4)
AND NOT EXISTS(SELECT 1 FROM fact_selection_decisions d WHERE d.fact_selection_scope_uuidv4=s.fact_selection_scope_uuidv4 AND NOT EXISTS(SELECT 1 FROM fact_selection_publications p WHERE p.fact_selection_decision_uuidv4=d.fact_selection_decision_uuidv4))
AND ((s.change_request_id IS NOT NULL AND EXISTS(SELECT 1 FROM effective_change_request_parser_profiles e WHERE e.change_request_id=s.change_request_id AND e.fact_kind=s.fact_kind AND e.parser_profile_uuidv4=r.parser_profile_uuidv4))
 OR (s.owner_kind='repository' AND s.change_request_id IS NULL AND EXISTS(SELECT 1 FROM effective_repository_parser_profiles e WHERE e.repository_uuidv4=s.repository_uuidv4 AND e.fact_kind=s.fact_kind AND e.parser_profile_uuidv4=r.parser_profile_uuidv4))
 OR (s.owner_kind='source' AND EXISTS(SELECT 1 FROM effective_source_parser_profiles e WHERE e.source_registration_uuidv4=s.source_registration_uuidv4 AND e.fact_kind=s.fact_kind AND e.parser_profile_uuidv4=r.parser_profile_uuidv4)));
DROP VIEW eligible_document_observations;
CREATE VIEW eligible_document_observations AS SELECT d.* FROM document_observations d JOIN usable_parsed_results r USING(parsed_result_uuidv4) JOIN effective_change_request_parser_profiles e ON e.change_request_id=d.change_request_id AND e.fact_kind=d.kind AND e.parser_profile_uuidv4=r.parser_profile_uuidv4;
CREATE VIEW eligible_change_request_observations AS SELECT d.* FROM change_request_observations d JOIN usable_parsed_results r USING(parsed_result_uuidv4) JOIN effective_change_request_parser_profiles e ON e.change_request_id=d.change_request_id AND e.fact_kind='change-request' AND e.parser_profile_uuidv4=r.parser_profile_uuidv4;
CREATE VIEW eligible_code_observations AS SELECT d.* FROM code_observations d JOIN usable_parsed_results r USING(parsed_result_uuidv4) JOIN effective_change_request_parser_profiles e ON e.change_request_id=d.change_request_id AND e.fact_kind='code' AND e.parser_profile_uuidv4=r.parser_profile_uuidv4;
CREATE VIEW eligible_change_request_events AS SELECT d.* FROM change_request_events d JOIN usable_parsed_results r USING(parsed_result_uuidv4) JOIN effective_change_request_parser_profiles e ON e.change_request_id=d.change_request_id AND e.fact_kind='events' AND e.parser_profile_uuidv4=r.parser_profile_uuidv4;
CREATE VIEW eligible_code_commits AS SELECT d.* FROM code_commits d JOIN code_listings l USING(code_listing_id) JOIN usable_parsed_results r USING(parsed_result_uuidv4) JOIN effective_change_request_parser_profiles e ON e.change_request_id=l.change_request_id AND e.fact_kind='code' AND e.parser_profile_uuidv4=r.parser_profile_uuidv4;
CREATE VIEW eligible_code_file_changes AS SELECT d.* FROM code_file_changes d JOIN code_listings l USING(code_listing_id) JOIN usable_parsed_results r USING(parsed_result_uuidv4) JOIN effective_change_request_parser_profiles e ON e.change_request_id=l.change_request_id AND e.fact_kind='code' AND e.parser_profile_uuidv4=r.parser_profile_uuidv4;
CREATE VIEW eligible_review_thread_observations AS SELECT d.* FROM review_thread_observations d JOIN usable_parsed_results r USING(parsed_result_uuidv4) JOIN effective_change_request_parser_profiles e ON e.change_request_id=d.change_request_id AND e.fact_kind='review-thread' AND e.parser_profile_uuidv4=r.parser_profile_uuidv4;
CREATE VIEW eligible_inventory_observations AS SELECT d.* FROM inventory_observations d JOIN usable_parsed_results r USING(parsed_result_uuidv4) JOIN effective_source_parser_profiles e ON e.source_registration_uuidv4=d.source_registration_uuidv4 AND e.fact_kind='inventory' AND e.parser_profile_uuidv4=r.parser_profile_uuidv4;
CREATE VIEW current_document_observations AS SELECT d.* FROM eligible_document_observations d JOIN active_fact_selections f ON f.parsed_result_uuidv4=d.parsed_result_uuidv4 AND f.change_request_id=d.change_request_id AND f.kind=d.kind AND f.provider_change_request_document_id=d.provider_change_request_document_id;
CREATE VIEW current_change_request_observations AS SELECT d.* FROM eligible_change_request_observations d JOIN active_fact_selections f ON f.parsed_result_uuidv4=d.parsed_result_uuidv4 AND f.change_request_id=d.change_request_id AND f.fact_kind='change-request';
CREATE VIEW current_code_observations AS SELECT d.* FROM eligible_code_observations d JOIN active_fact_selections f ON f.parsed_result_uuidv4=d.parsed_result_uuidv4 AND f.change_request_id=d.change_request_id AND f.fact_kind='code' AND f.fetch_occurrence_uuidv4 IS NULL;
CREATE VIEW current_inventory_observations AS SELECT d.* FROM eligible_inventory_observations d JOIN active_fact_selections f ON f.parsed_result_uuidv4=d.parsed_result_uuidv4 AND f.source_registration_uuidv4=d.source_registration_uuidv4 AND f.fact_kind='inventory';
CREATE VIEW current_review_thread_observations AS SELECT d.* FROM eligible_review_thread_observations d JOIN active_fact_selections f ON f.parsed_result_uuidv4=d.parsed_result_uuidv4 AND f.change_request_id=d.change_request_id AND f.provider_resource_id=d.provider_resource_id AND f.fact_kind='review-thread';
CREATE TRIGGER review_thread_observations_reject_update BEFORE UPDATE ON review_thread_observations BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER review_thread_observations_reject_delete BEFORE DELETE ON review_thread_observations BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER fact_selection_scopes_reject_update BEFORE UPDATE ON fact_selection_scopes BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER fact_selection_scopes_reject_delete BEFORE DELETE ON fact_selection_scopes BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER fact_selection_decisions_reject_update BEFORE UPDATE ON fact_selection_decisions BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER fact_selection_decisions_reject_delete BEFORE DELETE ON fact_selection_decisions BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER fact_selection_predecessors_reject_update BEFORE UPDATE ON fact_selection_predecessors BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER fact_selection_predecessors_reject_delete BEFORE DELETE ON fact_selection_predecessors BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER fact_selection_publications_reject_update BEFORE UPDATE ON fact_selection_publications BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER fact_selection_publications_reject_delete BEFORE DELETE ON fact_selection_publications BEGIN SELECT RAISE(ABORT,'immutable retained parser fact'); END;
CREATE TRIGGER review_thread_observations_capability BEFORE INSERT ON review_thread_observations WHEN NOT EXISTS(SELECT 1 FROM parsed_results p JOIN parser_profile_capabilities c USING(parser_profile_uuidv4) WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND c.owner_kind='repository' AND c.fact_kind='review-thread') BEGIN SELECT RAISE(ABORT,'profile cannot emit this fact kind'); END;
CREATE TRIGGER change_request_events_capability BEFORE INSERT ON change_request_events WHEN NOT EXISTS(SELECT 1 FROM parsed_results p JOIN parser_profile_capabilities c USING(parser_profile_uuidv4) WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND c.owner_kind='repository' AND c.fact_kind='events') BEGIN SELECT RAISE(ABORT,'profile cannot emit this fact kind'); END;
CREATE TRIGGER code_commits_capability BEFORE INSERT ON code_commits WHEN NOT EXISTS(SELECT 1 FROM parsed_results p JOIN parser_profile_capabilities c USING(parser_profile_uuidv4) WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND c.owner_kind='repository' AND c.fact_kind='code') BEGIN SELECT RAISE(ABORT,'profile cannot emit this fact kind'); END;
CREATE TRIGGER code_file_changes_capability BEFORE INSERT ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM parsed_results p JOIN parser_profile_capabilities c USING(parser_profile_uuidv4) WHERE p.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND c.owner_kind='repository' AND c.fact_kind='code') BEGIN SELECT RAISE(ABORT,'profile cannot emit this fact kind'); END;
CREATE TRIGGER change_request_observations_result_sealed BEFORE INSERT ON change_request_observations WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE TRIGGER document_observations_result_sealed BEFORE INSERT ON document_observations WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE TRIGGER code_observations_result_sealed BEFORE INSERT ON code_observations WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE TRIGGER change_request_events_result_sealed BEFORE INSERT ON change_request_events WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE TRIGGER code_commits_result_sealed BEFORE INSERT ON code_commits WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE TRIGGER code_file_changes_result_sealed BEFORE INSERT ON code_file_changes WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE TRIGGER inventory_observations_result_sealed BEFORE INSERT ON inventory_observations WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE TRIGGER review_thread_observations_result_sealed BEFORE INSERT ON review_thread_observations WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE TRIGGER review_thread_observations_uuid4 BEFORE INSERT ON review_thread_observations WHEN NOT (length(NEW.thread_observation_uuidv4)=36 AND length(CAST(NEW.thread_observation_uuidv4 AS BLOB))=36 AND substr(NEW.thread_observation_uuidv4,9,1)='-' AND substr(NEW.thread_observation_uuidv4,14,1)='-' AND substr(NEW.thread_observation_uuidv4,19,1)='-' AND substr(NEW.thread_observation_uuidv4,24,1)='-' AND length(replace(NEW.thread_observation_uuidv4,'-',''))=32 AND replace(NEW.thread_observation_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.thread_observation_uuidv4,15,1)='4' AND substr(NEW.thread_observation_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER fact_selection_scopes_uuid4 BEFORE INSERT ON fact_selection_scopes WHEN NOT (length(NEW.fact_selection_scope_uuidv4)=36 AND length(CAST(NEW.fact_selection_scope_uuidv4 AS BLOB))=36 AND substr(NEW.fact_selection_scope_uuidv4,9,1)='-' AND substr(NEW.fact_selection_scope_uuidv4,14,1)='-' AND substr(NEW.fact_selection_scope_uuidv4,19,1)='-' AND substr(NEW.fact_selection_scope_uuidv4,24,1)='-' AND length(replace(NEW.fact_selection_scope_uuidv4,'-',''))=32 AND replace(NEW.fact_selection_scope_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.fact_selection_scope_uuidv4,15,1)='4' AND substr(NEW.fact_selection_scope_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER fact_selection_decisions_uuid4 BEFORE INSERT ON fact_selection_decisions WHEN NOT (length(NEW.fact_selection_decision_uuidv4)=36 AND length(CAST(NEW.fact_selection_decision_uuidv4 AS BLOB))=36 AND substr(NEW.fact_selection_decision_uuidv4,9,1)='-' AND substr(NEW.fact_selection_decision_uuidv4,14,1)='-' AND substr(NEW.fact_selection_decision_uuidv4,19,1)='-' AND substr(NEW.fact_selection_decision_uuidv4,24,1)='-' AND length(replace(NEW.fact_selection_decision_uuidv4,'-',''))=32 AND replace(NEW.fact_selection_decision_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.fact_selection_decision_uuidv4,15,1)='4' AND substr(NEW.fact_selection_decision_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;
CREATE TRIGGER fact_selection_staging_uuid4 BEFORE INSERT ON fact_selection_staging WHEN NOT (length(NEW.fact_selection_decision_uuidv4)=36 AND length(CAST(NEW.fact_selection_decision_uuidv4 AS BLOB))=36 AND substr(NEW.fact_selection_decision_uuidv4,9,1)='-' AND substr(NEW.fact_selection_decision_uuidv4,14,1)='-' AND substr(NEW.fact_selection_decision_uuidv4,19,1)='-' AND substr(NEW.fact_selection_decision_uuidv4,24,1)='-' AND length(replace(NEW.fact_selection_decision_uuidv4,'-',''))=32 AND replace(NEW.fact_selection_decision_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.fact_selection_decision_uuidv4,15,1)='4' AND substr(NEW.fact_selection_decision_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;

CREATE TRIGGER parser_profile_definition_manifest BEFORE INSERT ON parser_profiles WHEN EXISTS(SELECT 1 FROM json_each(NEW.definition_json,'$.capabilities') c WHERE coalesce(json_type(c.value),'')<>'object' OR coalesce(json_extract(c.value,'$.owner_kind'),'') NOT IN ('repository','source') OR coalesce(json_type(c.value,'$.fact_kind'),'')<>'text' OR length(json_extract(c.value,'$.fact_kind'))=0) OR (SELECT count(*) FROM json_each(NEW.definition_json,'$.capabilities'))<>(SELECT count(*) FROM (SELECT DISTINCT json_extract(c.value,'$.owner_kind'),json_extract(c.value,'$.fact_kind') FROM json_each(NEW.definition_json,'$.capabilities') c)) BEGIN SELECT RAISE(ABORT,'invalid duplicate profile capability'); END;

CREATE TRIGGER snapshots_parser_identity BEFORE UPDATE ON snapshots WHEN NEW.parsed_result_uuidv4 IS NOT OLD.parsed_result_uuidv4 BEGIN SELECT RAISE(ABORT,'immutable snapshot parsed identity'); END;
CREATE TRIGGER ref_observations_parser_identity BEFORE UPDATE ON ref_observations WHEN NEW.parsed_result_uuidv4 IS NOT OLD.parsed_result_uuidv4 OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 BEGIN SELECT RAISE(ABORT,'immutable ref parsed identity'); END;
CREATE TRIGGER snapshots_result_sealed BEFORE INSERT ON snapshots WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE TRIGGER ref_observations_result_sealed BEFORE INSERT ON ref_observations WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'published parsed fact set is sealed'); END;
CREATE VIEW current_snapshots AS SELECT s.* FROM snapshots s JOIN active_fact_selections f ON f.parsed_result_uuidv4=s.parsed_result_uuidv4 AND f.repository_uuidv4=s.repository_uuidv4 AND f.fact_kind='git' AND f.git_acquisition_id IS NULL WHERE s.published=1;

CREATE VIEW current_change_request_events AS SELECT d.* FROM eligible_change_request_events d WHERE EXISTS(SELECT 1 FROM active_fact_selections f WHERE f.parsed_result_uuidv4=d.parsed_result_uuidv4 AND f.change_request_id=d.change_request_id AND f.fact_kind='events' AND (f.fetch_occurrence_uuidv4 IS NULL OR f.fetch_occurrence_uuidv4=d.origin_fetch_occurrence_uuidv4));
CREATE VIEW current_code_commits AS SELECT d.* FROM eligible_code_commits d JOIN fetch_occurrences o USING(fetch_occurrence_id) JOIN code_listings l USING(code_listing_id) JOIN active_fact_selections f ON f.parsed_result_uuidv4=d.parsed_result_uuidv4 AND f.change_request_id=l.change_request_id AND f.fact_kind='code' AND f.fetch_occurrence_uuidv4=o.fetch_occurrence_uuidv4;
CREATE VIEW current_code_file_changes AS SELECT d.* FROM eligible_code_file_changes d JOIN fetch_occurrences o USING(fetch_occurrence_id) JOIN code_listings l USING(code_listing_id) JOIN active_fact_selections f ON f.parsed_result_uuidv4=d.parsed_result_uuidv4 AND f.change_request_id=l.change_request_id AND f.fact_kind='code' AND f.fetch_occurrence_uuidv4=o.fetch_occurrence_uuidv4;

CREATE VIEW parsed_fact_members AS
SELECT parsed_result_uuidv4,'change_request_observations' AS table_name,json_array(change_request_observation_uuidv4) AS fact_key_json FROM change_request_observations
UNION ALL SELECT parsed_result_uuidv4,'document_observations',json_array(document_observation_uuidv4) FROM document_observations
UNION ALL SELECT parsed_result_uuidv4,'code_observations',json_array(code_observation_uuidv4) FROM code_observations
UNION ALL SELECT parsed_result_uuidv4,'change_request_events',json_array(change_request_event_uuidv4) FROM change_request_events
UNION ALL SELECT parsed_result_uuidv4,'review_thread_observations',json_array(thread_observation_uuidv4) FROM review_thread_observations
UNION ALL SELECT parsed_result_uuidv4,'inventory_observations',json_array(inventory_observation_id) FROM inventory_observations
UNION ALL SELECT parsed_result_uuidv4,'snapshots',json_array(snapshot_id) FROM snapshots
UNION ALL SELECT parsed_result_uuidv4,'ref_observations',json_array(snapshot_id,hex(raw_ref_name)) FROM ref_observations
UNION ALL SELECT d.parsed_result_uuidv4,'code_commits',json_array(d.code_listing_id,f.fetch_occurrence_uuidv4,d.position) FROM code_commits d JOIN fetch_occurrences f USING(fetch_occurrence_id)
UNION ALL SELECT d.parsed_result_uuidv4,'code_file_changes',json_array(d.code_listing_id,f.fetch_occurrence_uuidv4,d.position) FROM code_file_changes d JOIN fetch_occurrences f USING(fetch_occurrence_id)
UNION ALL SELECT parsed_result_uuidv4,'repository_name_observations',json_array(repository_name_observation_uuidv4) FROM repository_name_observations WHERE parsed_result_uuidv4 IS NOT NULL
UNION ALL SELECT parsed_result_uuidv4,'repository_inventory_observations',json_array(repository_inventory_observation_uuidv4) FROM repository_inventory_observations
UNION ALL SELECT parsed_result_uuidv4,'commits',json_array(git_fact_uuidv4) FROM commits
UNION ALL SELECT parsed_result_uuidv4,'commit_parents',json_array(git_fact_uuidv4) FROM commit_parents
UNION ALL SELECT parsed_result_uuidv4,'tree_entries',json_array(git_fact_uuidv4) FROM tree_entries
UNION ALL SELECT parsed_result_uuidv4,'tag_objects',json_array(git_fact_uuidv4) FROM tag_objects
UNION ALL SELECT parsed_result_uuidv4,'root_manifests',json_array(git_fact_uuidv4) FROM root_manifests
UNION ALL SELECT parsed_result_uuidv4,'root_manifest_entries',json_array(git_fact_uuidv4) FROM root_manifest_entries
UNION ALL SELECT parsed_result_uuidv4,'git_text_facts',json_array(git_fact_uuidv4) FROM git_text_facts;
CREATE TRIGGER parsed_publication_fact_manifest BEFORE INSERT ON parsed_result_publications
WHEN json_array_length(NEW.fact_manifest_json)<>(SELECT count(*) FROM parsed_fact_members WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4)
 OR EXISTS(SELECT json_extract(m.value,'$.table'),json_extract(m.value,'$.key') FROM json_each(NEW.fact_manifest_json) m EXCEPT SELECT f.table_name,f.fact_key_json FROM parsed_fact_members f WHERE f.parsed_result_uuidv4=NEW.parsed_result_uuidv4)
 OR json_array_length(NEW.fact_manifest_json)<>(SELECT count(*) FROM (SELECT DISTINCT json_extract(m.value,'$.table'),json_extract(m.value,'$.key') FROM json_each(NEW.fact_manifest_json) m))
BEGIN SELECT RAISE(ABORT,'parsed output fact manifest incomplete or inconsistent'); END;
CREATE TRIGGER fact_selection_result_contains_target BEFORE INSERT ON fact_selection_decisions
WHEN NOT EXISTS(
 SELECT 1 FROM fact_selection_scopes s WHERE s.fact_selection_scope_uuidv4=NEW.fact_selection_scope_uuidv4 AND (
 (s.kind IS NOT NULL AND EXISTS(SELECT 1 FROM document_observations d WHERE d.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND d.change_request_id=s.change_request_id AND d.kind=s.kind AND d.provider_change_request_document_id=s.provider_change_request_document_id))
 OR (s.fact_kind='change-request' AND EXISTS(SELECT 1 FROM change_request_observations d WHERE d.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND d.change_request_id=s.change_request_id AND d.published=1))
 OR (s.fact_kind='code' AND s.fetch_occurrence_uuidv4 IS NULL AND EXISTS(SELECT 1 FROM code_observations d WHERE d.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND d.change_request_id=s.change_request_id))
 OR (s.fact_kind='events' AND s.fetch_occurrence_uuidv4 IS NULL AND EXISTS(SELECT 1 FROM change_request_events d WHERE d.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND d.change_request_id=s.change_request_id))
 OR (s.fact_kind IN ('code','events') AND s.fetch_occurrence_uuidv4 IS NOT NULL AND EXISTS(SELECT 1 FROM parsed_result_inputs i WHERE i.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND i.fetch_occurrence_uuidv4=s.fetch_occurrence_uuidv4))
 OR (s.fact_kind='review-thread' AND EXISTS(SELECT 1 FROM review_thread_observations d WHERE d.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND d.change_request_id=s.change_request_id AND d.provider_resource_id=s.provider_resource_id))
 OR (s.fact_kind='inventory' AND EXISTS(SELECT 1 FROM inventory_observations d WHERE d.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND d.source_registration_uuidv4=s.source_registration_uuidv4))
 OR (s.fact_kind='git' AND s.git_acquisition_id IS NULL AND EXISTS(SELECT 1 FROM snapshots d WHERE d.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND d.repository_uuidv4=s.repository_uuidv4 AND d.published=1))
 OR (s.fact_kind='git' AND s.git_acquisition_id IS NOT NULL AND EXISTS(SELECT 1 FROM parsed_result_inputs i WHERE i.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND i.git_acquisition_id=s.git_acquisition_id))
 )) BEGIN SELECT RAISE(ABORT,'selected result does not contain scoped fact'); END;
CREATE TRIGGER source_input_observations_no_replace_guard BEFORE INSERT ON source_input_observations WHEN EXISTS(SELECT 1 FROM source_input_observations WHERE source_input_uuidv4=NEW.source_input_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parser_profiles_no_replace_guard BEFORE INSERT ON parser_profiles WHEN EXISTS(SELECT 1 FROM parser_profiles WHERE parser_profile_uuidv4=NEW.parser_profile_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parser_profile_capabilities_no_replace_guard BEFORE INSERT ON parser_profile_capabilities WHEN EXISTS(SELECT 1 FROM parser_profile_capabilities WHERE parser_profile_uuidv4=NEW.parser_profile_uuidv4 AND owner_kind=NEW.owner_kind AND fact_kind=NEW.fact_kind) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parser_profile_verifications_no_replace_guard BEFORE INSERT ON parser_profile_verifications WHEN EXISTS(SELECT 1 FROM parser_profile_verifications WHERE parser_profile_verification_uuidv4=NEW.parser_profile_verification_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parser_profile_verification_invalidations_no_replace_guard BEFORE INSERT ON parser_profile_verification_invalidations WHEN EXISTS(SELECT 1 FROM parser_profile_verification_invalidations WHERE invalidation_uuidv4=NEW.invalidation_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parsed_results_no_replace_guard BEFORE INSERT ON parsed_results WHEN EXISTS(SELECT 1 FROM parsed_results WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parsed_result_inputs_no_replace_guard BEFORE INSERT ON parsed_result_inputs WHEN EXISTS(SELECT 1 FROM parsed_result_inputs WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND input_ordinal=NEW.input_ordinal) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parsed_result_publications_no_replace_guard BEFORE INSERT ON parsed_result_publications WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parser_profile_selection_scopes_no_replace_guard BEFORE INSERT ON parser_profile_selection_scopes WHEN EXISTS(SELECT 1 FROM parser_profile_selection_scopes WHERE selection_scope_uuidv4=NEW.selection_scope_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parser_profile_selection_decisions_no_replace_guard BEFORE INSERT ON parser_profile_selection_decisions WHEN EXISTS(SELECT 1 FROM parser_profile_selection_decisions WHERE selection_decision_uuidv4=NEW.selection_decision_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parser_profile_selection_predecessors_no_replace_guard BEFORE INSERT ON parser_profile_selection_predecessors WHEN EXISTS(SELECT 1 FROM parser_profile_selection_predecessors WHERE selection_decision_uuidv4=NEW.selection_decision_uuidv4 AND predecessor_decision_uuidv4=NEW.predecessor_decision_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER parser_profile_selection_publications_no_replace_guard BEFORE INSERT ON parser_profile_selection_publications WHEN EXISTS(SELECT 1 FROM parser_profile_selection_publications WHERE selection_decision_uuidv4=NEW.selection_decision_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER fact_selection_scopes_no_replace_guard BEFORE INSERT ON fact_selection_scopes WHEN EXISTS(SELECT 1 FROM fact_selection_scopes WHERE fact_selection_scope_uuidv4=NEW.fact_selection_scope_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER fact_selection_decisions_no_replace_guard BEFORE INSERT ON fact_selection_decisions WHEN EXISTS(SELECT 1 FROM fact_selection_decisions WHERE fact_selection_decision_uuidv4=NEW.fact_selection_decision_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER fact_selection_predecessors_no_replace_guard BEFORE INSERT ON fact_selection_predecessors WHEN EXISTS(SELECT 1 FROM fact_selection_predecessors WHERE fact_selection_decision_uuidv4=NEW.fact_selection_decision_uuidv4 AND predecessor_decision_uuidv4=NEW.predecessor_decision_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER fact_selection_publications_no_replace_guard BEFORE INSERT ON fact_selection_publications WHEN EXISTS(SELECT 1 FROM fact_selection_publications WHERE fact_selection_decision_uuidv4=NEW.fact_selection_decision_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER review_thread_observations_no_replace_guard BEFORE INSERT ON review_thread_observations WHEN EXISTS(SELECT 1 FROM review_thread_observations WHERE thread_observation_uuidv4=NEW.thread_observation_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable identity conflict; REPLACE forbidden'); END;
CREATE TRIGGER fetch_occurrences_portable_conflict BEFORE INSERT ON fetch_occurrences WHEN EXISTS(SELECT 1 FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=NEW.fetch_occurrence_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable portable identity conflict'); END;
CREATE TRIGGER change_request_observations_portable_conflict BEFORE INSERT ON change_request_observations WHEN EXISTS(SELECT 1 FROM change_request_observations WHERE change_request_observation_uuidv4=NEW.change_request_observation_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable portable identity conflict'); END;
CREATE TRIGGER document_observations_portable_conflict BEFORE INSERT ON document_observations WHEN EXISTS(SELECT 1 FROM document_observations WHERE document_observation_uuidv4=NEW.document_observation_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable portable identity conflict'); END;
CREATE TRIGGER code_observations_portable_conflict BEFORE INSERT ON code_observations WHEN EXISTS(SELECT 1 FROM code_observations WHERE code_observation_uuidv4=NEW.code_observation_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable portable identity conflict'); END;
CREATE TRIGGER change_request_events_portable_conflict BEFORE INSERT ON change_request_events WHEN EXISTS(SELECT 1 FROM change_request_events WHERE change_request_event_uuidv4=NEW.change_request_event_uuidv4) BEGIN SELECT RAISE(ABORT,'immutable portable identity conflict'); END;

CREATE TRIGGER parsed_results_typed_manifest BEFORE INSERT ON parsed_results
WHEN EXISTS(SELECT 1 FROM json_each(NEW.input_manifest_json) m WHERE coalesce(json_type(m.value),'')<>'object' OR (SELECT count(*) FROM json_each(m.value))<>1 OR EXISTS(SELECT 1 FROM json_each(m.value) v WHERE v.key NOT IN ('fetch_occurrence_uuidv4','git_acquisition_id','source_input_uuidv4') OR v.type<>'text'))
BEGIN SELECT RAISE(ABORT,'input manifest requires exact typed input identities'); END;
CREATE TRIGGER event_origin_in_result BEFORE INSERT ON change_request_events
WHEN NEW.origin_fetch_occurrence_uuidv4 IS NOT NULL AND NOT EXISTS(SELECT 1 FROM parsed_result_inputs i WHERE i.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND i.fetch_occurrence_uuidv4=NEW.origin_fetch_occurrence_uuidv4)
BEGIN SELECT RAISE(ABORT,'event input absent from parsed result'); END;
CREATE TRIGGER document_origin_in_result BEFORE INSERT ON document_observations
WHEN NEW.fetch_occurrence_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM parsed_result_inputs i JOIN fetch_occurrences f USING(fetch_occurrence_uuidv4) WHERE i.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND f.fetch_occurrence_id=NEW.fetch_occurrence_id)
BEGIN SELECT RAISE(ABORT,'document input absent from parsed result'); END;
CREATE TRIGGER change_request_origin_in_result BEFORE INSERT ON change_request_observations
WHEN NEW.origin_fetch_occurrence_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM parsed_result_inputs i JOIN fetch_occurrences f USING(fetch_occurrence_uuidv4) WHERE i.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND f.fetch_occurrence_id=NEW.origin_fetch_occurrence_id)
BEGIN SELECT RAISE(ABORT,'change request input absent from parsed result'); END;
CREATE TRIGGER commit_origin_in_result BEFORE INSERT ON code_commits
WHEN NOT EXISTS(SELECT 1 FROM parsed_result_inputs i JOIN fetch_occurrences f USING(fetch_occurrence_uuidv4) WHERE i.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND f.fetch_occurrence_id=NEW.fetch_occurrence_id)
BEGIN SELECT RAISE(ABORT,'code input absent from parsed result'); END;
CREATE TRIGGER file_origin_in_result BEFORE INSERT ON code_file_changes
WHEN NOT EXISTS(SELECT 1 FROM parsed_result_inputs i JOIN fetch_occurrences f USING(fetch_occurrence_uuidv4) WHERE i.parsed_result_uuidv4=NEW.parsed_result_uuidv4 AND f.fetch_occurrence_id=NEW.fetch_occurrence_id)
BEGIN SELECT RAISE(ABORT,'code input absent from parsed result'); END;
