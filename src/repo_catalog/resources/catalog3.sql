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
    schema_version INTEGER NOT NULL CHECK(schema_version=9),
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
    name TEXT NOT NULL UNIQUE,
    web_base_url TEXT, api_base_url TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    created_at_us INTEGER
) STRICT;
CREATE TABLE sources(
source_id TEXT PRIMARY KEY, service_instance_uuidv4 TEXT REFERENCES service_instances(service_instance_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
    discovery_kind TEXT NOT NULL CHECK(discovery_kind IN ('manual_git','github_inventory')),
    name TEXT NOT NULL,
    settings TEXT NOT NULL CHECK(json_valid(settings) AND json_type(settings)='object')
) STRICT;
CREATE TABLE repositories(
repository_id TEXT PRIMARY KEY, name TEXT NOT NULL,
    preferred_repository_endpoint_id TEXT, current_snapshot_id TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    FOREIGN KEY(preferred_repository_endpoint_id,repository_id) REFERENCES repository_endpoints(repository_endpoint_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(current_snapshot_id,repository_id) REFERENCES snapshots(snapshot_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE repository_bindings(
repository_binding_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    service_instance_uuidv4 TEXT NOT NULL REFERENCES service_instances(service_instance_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
    provider_repository_id TEXT CHECK(provider_repository_id IS NULL OR length(provider_repository_id)>0),
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), created_at_us INTEGER,
    UNIQUE(repository_id,service_instance_uuidv4), UNIQUE(service_instance_uuidv4,provider_repository_id), UNIQUE(repository_binding_id,repository_id)
) STRICT;
CREATE TABLE repository_endpoints(
repository_endpoint_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    url TEXT NOT NULL CHECK(length(url)>0),
    transport TEXT NOT NULL CHECK(transport IN ('file','https','ssh','other')),
    label TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), created_at_us INTEGER,
    UNIQUE(repository_id,url), UNIQUE(repository_endpoint_id,repository_id)
) STRICT;
CREATE TABLE git_acquisitions(
git_acquisition_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    repository_endpoint_id TEXT, endpoint_url TEXT,
    object_format TEXT CHECK(object_format IN ('sha1','sha256')),
    refs_observed_at_us INTEGER,
    source_id TEXT REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, kind TEXT NOT NULL CHECK(kind IN ('git','pr','legacy')), started_at_us INTEGER, observed_at_us INTEGER, request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'), roots_manifest TEXT CHECK(roots_manifest IS NULL OR (json_valid(roots_manifest) AND json_type(roots_manifest)='array')),
    UNIQUE(git_acquisition_id,repository_id),
    FOREIGN KEY(repository_endpoint_id,repository_id) REFERENCES repository_endpoints(repository_endpoint_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE snapshots(
snapshot_id TEXT PRIMARY KEY, git_acquisition_id TEXT NOT NULL UNIQUE,
    repository_id TEXT NOT NULL, published INTEGER NOT NULL CHECK(published IN (0,1)),
    generation INTEGER NOT NULL CHECK(generation>=0), created_at_us INTEGER,
    UNIQUE(snapshot_id,repository_id),
    FOREIGN KEY(git_acquisition_id,repository_id) REFERENCES git_acquisitions(git_acquisition_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE change_requests(
change_request_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL, repository_binding_id TEXT NOT NULL,
    change_request_kind TEXT NOT NULL CHECK(change_request_kind IN ('pull_request','merge_request')),
    provider_change_request_number INTEGER NOT NULL CHECK(provider_change_request_number>0), current_change_request_observation_id INTEGER,
    UNIQUE(repository_binding_id,change_request_kind,provider_change_request_number), UNIQUE(change_request_id,repository_id),
    FOREIGN KEY(repository_binding_id,repository_id) REFERENCES repository_bindings(repository_binding_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(current_change_request_observation_id,change_request_id) REFERENCES change_request_observations(change_request_observation_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE change_request_observations(
change_request_observation_id INTEGER PRIMARY KEY,
    change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    observed_at_us INTEGER, published INTEGER NOT NULL CHECK(published IN (0,1)),
    payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'),
    origin_key TEXT, parsed_at_us INTEGER NOT NULL, origin_fetch_occurrence_id INTEGER REFERENCES fetch_occurrences(fetch_occurrence_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    UNIQUE(change_request_observation_id,change_request_id)
) STRICT;
CREATE TABLE text_bodies(
text_body_id INTEGER PRIMARY KEY, body TEXT NOT NULL,
    byte_length INTEGER NOT NULL CHECK(byte_length>=0 AND byte_length=length(CAST(body AS BLOB))),
    sha256 BLOB NOT NULL CHECK(length(sha256)=32), UNIQUE(sha256)
) STRICT;
CREATE TABLE documents(
    change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK(length(kind)>0),
    provider_change_request_document_id TEXT NOT NULL CHECK(length(provider_change_request_document_id)>0),
    current_document_observation_id INTEGER,
    deleted INTEGER NOT NULL CHECK(deleted IN (0,1)),
    author TEXT, url TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    PRIMARY KEY(change_request_id,kind,provider_change_request_document_id),
    FOREIGN KEY(current_document_observation_id,change_request_id,kind,provider_change_request_document_id) REFERENCES document_observations(document_observation_id,change_request_id,kind,provider_change_request_document_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE document_observations(
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
    FOREIGN KEY(change_request_id,kind,provider_change_request_document_id) REFERENCES documents(change_request_id,kind,provider_change_request_document_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE review_threads(
    change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    provider_resource_id TEXT NOT NULL CHECK(length(provider_resource_id)>0),
    payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), observed_at_us INTEGER,
    PRIMARY KEY(change_request_id,provider_resource_id)
) STRICT;
CREATE TABLE review_comments(
    change_request_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    provider_change_request_document_id TEXT NOT NULL,
    review_thread_provider_resource_id TEXT,
    payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'),
    PRIMARY KEY(change_request_id,kind,provider_change_request_document_id),
    CHECK(kind='review-comment'),
    FOREIGN KEY(change_request_id,kind,provider_change_request_document_id) REFERENCES documents(change_request_id,kind,provider_change_request_document_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(change_request_id,review_thread_provider_resource_id) REFERENCES review_threads(change_request_id,provider_resource_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE fetch_collections(
fetch_collection_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, change_request_id TEXT,
    source_id TEXT REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, kind TEXT NOT NULL, resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, observed_at_us INTEGER,
    UNIQUE(fetch_collection_id,change_request_id),
    FOREIGN KEY(change_request_id,repository_id) REFERENCES change_requests(change_request_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE code_listings(
code_listing_id TEXT PRIMARY KEY, change_request_id TEXT NOT NULL,
    fetch_collection_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('commits','files')),
    resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, object_format TEXT CHECK(object_format IN ('sha1','sha256')), head_oid BLOB, base_oid BLOB, CHECK((head_oid IS NULL AND base_oid IS NULL) OR (object_format IS NOT NULL AND object_format='sha1' AND (head_oid IS NULL OR length(head_oid)=20) AND (base_oid IS NULL OR length(base_oid)=20)) OR (object_format IS NOT NULL AND object_format='sha256' AND (head_oid IS NULL OR length(head_oid)=32) AND (base_oid IS NULL OR length(base_oid)=32))),
    UNIQUE(fetch_collection_id,kind), UNIQUE(code_listing_id,change_request_id),
    FOREIGN KEY(fetch_collection_id,change_request_id) REFERENCES fetch_collections(fetch_collection_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE code_observations(
code_observation_id INTEGER PRIMARY KEY, change_request_id TEXT NOT NULL, change_request_observation_id INTEGER NOT NULL,
    commit_code_listing_id TEXT, file_code_listing_id TEXT,
    state TEXT NOT NULL CHECK(state IN ('pending','partial','complete','unknown')),
    object_format TEXT CHECK(object_format IN ('sha1','sha256')), head_oid BLOB, base_oid BLOB, details TEXT NOT NULL CHECK(json_valid(details) AND json_type(details)='object'), CHECK((head_oid IS NULL AND base_oid IS NULL) OR (object_format IS NOT NULL AND object_format='sha1' AND (head_oid IS NULL OR length(head_oid)=20) AND (base_oid IS NULL OR length(base_oid)=20)) OR (object_format IS NOT NULL AND object_format='sha256' AND (head_oid IS NULL OR length(head_oid)=32) AND (base_oid IS NULL OR length(base_oid)=32))),
    CHECK(state!='complete' OR (commit_code_listing_id IS NOT NULL AND file_code_listing_id IS NOT NULL)),
    FOREIGN KEY(change_request_observation_id,change_request_id) REFERENCES change_request_observations(change_request_observation_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(commit_code_listing_id,change_request_id) REFERENCES code_listings(code_listing_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(file_code_listing_id,change_request_id) REFERENCES code_listings(code_listing_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE acquisition_roots(
acquisition_root_id INTEGER PRIMARY KEY, git_acquisition_id TEXT NOT NULL REFERENCES git_acquisitions(git_acquisition_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
    oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)),
    role TEXT NOT NULL,
    repository_id TEXT NOT NULL, expected_oid BLOB, published INTEGER NOT NULL CHECK(published IN (0,1)), FOREIGN KEY(git_acquisition_id,repository_id) REFERENCES git_acquisitions(git_acquisition_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, CHECK(expected_oid IS NULL OR length(expected_oid)=length(oid)), UNIQUE(acquisition_root_id,repository_id),
    UNIQUE(git_acquisition_id,object_format,oid,role)
) STRICT;
CREATE TABLE root_origins(
root_origin_id INTEGER PRIMARY KEY, acquisition_root_id INTEGER NOT NULL REFERENCES acquisition_roots(acquisition_root_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    origin_kind TEXT NOT NULL CHECK(origin_kind IN ('ref','pr_role','legacy_unknown')),
    raw_ref_name BLOB, source_ordinal INTEGER NOT NULL CHECK(source_ordinal>=0),
    snapshot_id TEXT, change_request_id TEXT, change_request_observation_id INTEGER, repository_id TEXT NOT NULL, FOREIGN KEY(acquisition_root_id,repository_id) REFERENCES acquisition_roots(acquisition_root_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(snapshot_id,repository_id) REFERENCES snapshots(snapshot_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(change_request_id,repository_id) REFERENCES change_requests(change_request_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(change_request_observation_id,change_request_id) REFERENCES change_request_observations(change_request_observation_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT, CHECK((origin_kind='ref' AND snapshot_id IS NOT NULL AND change_request_id IS NULL AND change_request_observation_id IS NULL) OR (origin_kind='pr_role' AND snapshot_id IS NULL AND change_request_id IS NOT NULL AND change_request_observation_id IS NOT NULL) OR (origin_kind='legacy_unknown' AND snapshot_id IS NULL AND change_request_id IS NULL AND change_request_observation_id IS NULL)),
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
source_id TEXT NOT NULL REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, first_seen_us INTEGER, last_seen_us INTEGER, PRIMARY KEY(source_id,repository_id),
    CHECK(first_seen_us IS NULL OR last_seen_us IS NULL OR first_seen_us<=last_seen_us)
) STRICT;
CREATE TABLE repository_name_assertions(
repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, name TEXT NOT NULL, observed_at_us INTEGER, PRIMARY KEY(repository_id,name)
) STRICT;
CREATE TABLE inventory_observations(
inventory_observation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, asserted_state TEXT NOT NULL CHECK(asserted_state IN ('complete','partial','unknown')), scope TEXT NOT NULL CHECK(json_valid(scope) AND json_type(scope)='object'), observed_at_us INTEGER, reason TEXT
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
resume_scope_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, repository_binding_id TEXT, source_id TEXT REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, principal_ref TEXT, api_version TEXT, endpoint TEXT, request_context TEXT NOT NULL CHECK(json_valid(request_context) AND json_type(request_context)='object'), parser_version TEXT NOT NULL, profile_version TEXT NOT NULL, confidence TEXT NOT NULL CHECK(confidence IN ('proven','legacy_unknown')), UNIQUE(resume_scope_id,repository_id), FOREIGN KEY(repository_binding_id,repository_id) REFERENCES repository_bindings(repository_binding_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE payloads(
payload_id INTEGER PRIMARY KEY, sha256 BLOB NOT NULL CHECK(length(sha256)=32), body BLOB NOT NULL, byte_length INTEGER NOT NULL CHECK(byte_length=length(body)), representation TEXT NOT NULL CHECK(representation IN ('decoded_api','legacy_normalized'))
) STRICT;
CREATE TABLE fetch_occurrences(
fetch_occurrence_id INTEGER PRIMARY KEY, fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, ordinal INTEGER NOT NULL CHECK(ordinal>=0), payload_id INTEGER NOT NULL REFERENCES payloads(payload_id) ON UPDATE RESTRICT ON DELETE RESTRICT, request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'), next_cursor TEXT, observed_at_us INTEGER, parsed_at_us INTEGER NOT NULL, UNIQUE(fetch_occurrence_id,fetch_collection_id)
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
CREATE TABLE unresolved_payloads(
unresolved_payload_id INTEGER PRIMARY KEY, payload_id INTEGER REFERENCES payloads(payload_id) ON UPDATE RESTRICT ON DELETE RESTRICT, reason TEXT NOT NULL CHECK(length(reason)>0)
) STRICT;
CREATE TABLE validators(
resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, validator_key TEXT NOT NULL, etag TEXT NOT NULL, payload_id INTEGER NOT NULL REFERENCES payloads(payload_id) ON UPDATE RESTRICT ON DELETE RESTRICT, validated_at_us INTEGER, PRIMARY KEY(resume_scope_id,validator_key)
) STRICT;
CREATE TABLE incremental_scans(
incremental_scan_id TEXT PRIMARY KEY, resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, scan_started_at_us INTEGER, safe_watermark_us INTEGER, evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object'), UNIQUE(incremental_scan_id,resume_scope_id)
) STRICT;
CREATE TABLE resume_cursors(
resume_scope_id TEXT PRIMARY KEY REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, incremental_scan_id TEXT, next_cursor TEXT, reusable INTEGER NOT NULL CHECK(reusable IN (0,1)), FOREIGN KEY(incremental_scan_id,resume_scope_id) REFERENCES incremental_scans(incremental_scan_id,resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE completion_markers(
completion_marker_id INTEGER PRIMARY KEY, resume_scope_id TEXT NOT NULL REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, asserted_state TEXT NOT NULL CHECK(asserted_state IN ('complete','partial','unknown')), evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object'), observed_at_us INTEGER
) STRICT;
CREATE TABLE coverage_scopes(
coverage_scope_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    change_request_id TEXT, kind TEXT NOT NULL,
    FOREIGN KEY(change_request_id,repository_id) REFERENCES change_requests(change_request_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE UNIQUE INDEX coverage_scope_repository_kind ON coverage_scopes(repository_id,kind) WHERE change_request_id IS NULL;
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
SELECT s.coverage_scope_id,s.repository_id,s.change_request_id,s.kind,
       max(c.observed_at_us) AS observed_at_us,
       CASE WHEN count(DISTINCT CASE WHEN c.coverage_state!='unknown' THEN c.coverage_state END)>1
            THEN 'conflict'
            ELSE coalesce(max(CASE WHEN c.coverage_state!='unknown' THEN c.coverage_state END),'unknown')
       END AS coverage_state,
       count(c.coverage_claim_id) AS claim_count
FROM coverage_scopes s
LEFT JOIN coverage_claims c
  ON c.coverage_scope_id=s.coverage_scope_id
 AND c.observed_at_us=(SELECT max(latest.observed_at_us) FROM coverage_claims latest WHERE latest.coverage_scope_id=s.coverage_scope_id)
GROUP BY s.coverage_scope_id;
CREATE TABLE reviews(
    change_request_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    provider_change_request_document_id TEXT NOT NULL,
    payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'),
    PRIMARY KEY(change_request_id,kind,provider_change_request_document_id),
    CHECK(kind='review'),
    FOREIGN KEY(change_request_id,kind,provider_change_request_document_id) REFERENCES documents(change_request_id,kind,provider_change_request_document_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE change_request_events(
change_request_event_id INTEGER PRIMARY KEY, change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT, origin_key TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal>=0), provider_event_id TEXT, payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), observed_at_us INTEGER
) STRICT;
CREATE TABLE code_listing_progress(
code_listing_id TEXT PRIMARY KEY REFERENCES code_listings(code_listing_id) ON UPDATE RESTRICT ON DELETE RESTRICT, state TEXT NOT NULL CHECK(state IN ('partial','complete','unknown')), terminal INTEGER NOT NULL CHECK(terminal IN (0,1)), page_count INTEGER NOT NULL CHECK(page_count>=0), context_proven INTEGER NOT NULL CHECK(context_proven IN (0,1)), CHECK(state!='complete' OR (terminal=1 AND context_proven=1))
) STRICT;
CREATE TABLE code_commits(
code_listing_id TEXT NOT NULL REFERENCES code_listings(code_listing_id) ON UPDATE RESTRICT ON DELETE RESTRICT, fetch_occurrence_id INTEGER NOT NULL REFERENCES fetch_occurrences(fetch_occurrence_id) ON UPDATE RESTRICT ON DELETE RESTRICT, position INTEGER NOT NULL CHECK(position>=0), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), PRIMARY KEY(code_listing_id,fetch_occurrence_id,position)
) STRICT;
CREATE TABLE code_file_changes(
code_listing_id TEXT NOT NULL REFERENCES code_listings(code_listing_id) ON UPDATE RESTRICT ON DELETE RESTRICT, fetch_occurrence_id INTEGER NOT NULL REFERENCES fetch_occurrences(fetch_occurrence_id) ON UPDATE RESTRICT ON DELETE RESTRICT, position INTEGER NOT NULL CHECK(position>=0), raw_path BLOB NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), PRIMARY KEY(code_listing_id,fetch_occurrence_id,position)
) STRICT;
CREATE TABLE code_acquisitions(
code_observation_id INTEGER NOT NULL REFERENCES code_observations(code_observation_id) ON UPDATE RESTRICT ON DELETE RESTRICT, role TEXT NOT NULL CHECK(length(role)>0), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), acquisition_root_id INTEGER REFERENCES acquisition_roots(acquisition_root_id) ON UPDATE RESTRICT ON DELETE RESTRICT, PRIMARY KEY(code_observation_id,role)
) STRICT;
CREATE TABLE git_objects(
git_object_id INTEGER PRIMARY KEY, object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), type TEXT NOT NULL CHECK(type IN ('commit','tree','blob','tag')), size INTEGER NOT NULL CHECK(size>=0), verified INTEGER NOT NULL CHECK(verified IN (0,1)), UNIQUE(object_format,oid)
) STRICT;
CREATE TABLE commits(
git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, tree_git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_headers BLOB NOT NULL, raw_message BLOB NOT NULL, metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object')
) STRICT;
CREATE TABLE commit_parents(
commit_git_object_id INTEGER NOT NULL REFERENCES commits(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, parent_ordinal INTEGER NOT NULL CHECK(parent_ordinal>=0), parent_git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, PRIMARY KEY(commit_git_object_id,parent_ordinal)
) STRICT;
CREATE TABLE tree_entries(
tree_git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_name BLOB NOT NULL CHECK(length(raw_name)>0), mode INTEGER NOT NULL CHECK(mode IN (16384,33188,33261,40960,57344)), child_format TEXT NOT NULL CHECK(child_format IN ('sha1','sha256')), child_oid BLOB NOT NULL CHECK((child_format='sha1' AND length(child_oid)=20) OR (child_format='sha256' AND length(child_oid)=32)), child_git_object_id INTEGER REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, PRIMARY KEY(tree_git_object_id,raw_name), CHECK((mode=57344 AND child_git_object_id IS NULL) OR (mode!=57344 AND child_git_object_id IS NOT NULL))
) STRICT;
CREATE TABLE tag_objects(
git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, target_git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_payload BLOB NOT NULL
) STRICT;
CREATE TABLE contents(
content_id INTEGER PRIMARY KEY, byte_length INTEGER NOT NULL CHECK(byte_length>=0), raw_text TEXT, text_state TEXT NOT NULL CHECK(text_state IN ('eligible','nul','non_utf8','oversize','unknown')), created_at_us INTEGER, CHECK(raw_text IS NULL OR length(CAST(raw_text AS BLOB))=byte_length)
) STRICT;
CREATE TABLE content_digests(
content_id INTEGER NOT NULL REFERENCES contents(content_id) ON UPDATE RESTRICT ON DELETE RESTRICT, representation TEXT NOT NULL CHECK(representation='raw-content-v1'), algorithm TEXT NOT NULL CHECK(algorithm IN ('md5','sha1','sha256')), digest BLOB NOT NULL CHECK((algorithm='md5' AND length(digest)=16) OR (algorithm='sha1' AND length(digest)=20) OR (algorithm='sha256' AND length(digest)=32)), verified_at_us INTEGER, pipeline_version TEXT NOT NULL, PRIMARY KEY(content_id,representation,algorithm)
) STRICT;
CREATE TABLE blob_content_map(
git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, content_id INTEGER NOT NULL REFERENCES contents(content_id) ON UPDATE RESTRICT ON DELETE RESTRICT, git_acquisition_id TEXT NOT NULL REFERENCES git_acquisitions(git_acquisition_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE repository_object_sources(
repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, git_acquisition_id TEXT NOT NULL, PRIMARY KEY(repository_id,git_object_id,git_acquisition_id), FOREIGN KEY(git_acquisition_id,repository_id) REFERENCES git_acquisitions(git_acquisition_id,repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE ref_observations(
snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_ref_name BLOB NOT NULL CHECK(length(raw_ref_name)>0), kind TEXT NOT NULL CHECK(kind IN ('head','tag','other')), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), target_oid BLOB NOT NULL CHECK((object_format='sha1' AND length(target_oid)=20) OR (object_format='sha256' AND length(target_oid)=32)), peeled_oid BLOB, target_type TEXT CHECK(target_type IN ('commit','tree','blob','tag')), PRIMARY KEY(snapshot_id,raw_ref_name), CHECK(peeled_oid IS NULL OR length(peeled_oid)=length(target_oid))
) STRICT;
CREATE TABLE root_manifests(
tree_git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, complete INTEGER NOT NULL CHECK(complete IN (0,1))
) STRICT;
CREATE TABLE root_manifest_entries(
tree_git_object_id INTEGER NOT NULL REFERENCES root_manifests(tree_git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_path BLOB NOT NULL, mode INTEGER NOT NULL CHECK(mode IN (33188,33261,40960,57344)), git_object_id INTEGER REFERENCES git_objects(git_object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), PRIMARY KEY(tree_git_object_id,raw_path), CHECK((mode=57344 AND git_object_id IS NULL) OR (mode!=57344 AND git_object_id IS NOT NULL))
) STRICT;
CREATE TABLE cache_locators(
cache_locator_id TEXT PRIMARY KEY, repository_id TEXT NOT NULL REFERENCES repositories(repository_id) ON UPDATE RESTRICT ON DELETE RESTRICT, path TEXT NOT NULL, access TEXT NOT NULL CHECK(access IN ('source_readonly','target_active')), state TEXT NOT NULL CHECK(state IN ('available','missing','unknown')), UNIQUE(cache_locator_id,repository_id)
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
CREATE TRIGGER acquisition_roots_immutable BEFORE UPDATE ON acquisition_roots WHEN NEW.acquisition_root_id IS NOT OLD.acquisition_root_id OR NEW.git_acquisition_id IS NOT OLD.git_acquisition_id OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.role IS NOT OLD.role OR NEW.repository_id IS NOT OLD.repository_id OR NEW.expected_oid IS NOT OLD.expected_oid OR (OLD.published=1 AND NEW.published!=1) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER acquisition_roots_no_replace BEFORE INSERT ON acquisition_roots WHEN EXISTS(SELECT 1 FROM acquisition_roots WHERE (acquisition_root_id=NEW.acquisition_root_id) OR (git_acquisition_id=NEW.git_acquisition_id AND object_format=NEW.object_format AND oid=NEW.oid AND role=NEW.role) OR (acquisition_root_id=NEW.acquisition_root_id AND repository_id=NEW.repository_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER acquisition_roots_retain BEFORE DELETE ON acquisition_roots BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX acquisition_roots_fk_0 ON acquisition_roots(git_acquisition_id,repository_id);
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
CREATE TRIGGER cache_locators_immutable BEFORE UPDATE ON cache_locators WHEN NEW.cache_locator_id IS NOT OLD.cache_locator_id OR NEW.repository_id IS NOT OLD.repository_id OR NEW.access IS NOT OLD.access BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER cache_locators_no_replace BEFORE INSERT ON cache_locators WHEN EXISTS(SELECT 1 FROM cache_locators WHERE (cache_locator_id=NEW.cache_locator_id) OR (cache_locator_id=NEW.cache_locator_id AND repository_id=NEW.repository_id) OR (cache_locator_id=NEW.cache_locator_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX cache_locators_fk_0 ON cache_locators(repository_id);
CREATE TRIGGER change_request_events_immutable BEFORE UPDATE ON change_request_events WHEN NEW.change_request_event_id IS NOT OLD.change_request_event_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.origin_key IS NOT OLD.origin_key OR NEW.ordinal IS NOT OLD.ordinal OR NEW.provider_event_id IS NOT OLD.provider_event_id OR NEW.payload IS NOT OLD.payload OR NEW.observed_at_us IS NOT OLD.observed_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER change_request_events_no_replace BEFORE INSERT ON change_request_events WHEN EXISTS(SELECT 1 FROM change_request_events WHERE (change_request_event_id=NEW.change_request_event_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER change_request_events_retain BEFORE DELETE ON change_request_events BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX change_request_events_fk_0 ON change_request_events(change_request_id);
CREATE TRIGGER change_request_observations_immutable BEFORE UPDATE ON change_request_observations WHEN NEW.change_request_observation_id IS NOT OLD.change_request_observation_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.observed_at_us IS NOT OLD.observed_at_us OR NEW.payload IS NOT OLD.payload OR NEW.origin_key IS NOT OLD.origin_key OR NEW.parsed_at_us IS NOT OLD.parsed_at_us OR NEW.origin_fetch_occurrence_id IS NOT OLD.origin_fetch_occurrence_id OR (OLD.published=1 AND NEW.published!=1) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER change_request_observations_no_replace BEFORE INSERT ON change_request_observations WHEN EXISTS(SELECT 1 FROM change_request_observations WHERE (change_request_observation_id=NEW.change_request_observation_id) OR (change_request_observation_id=NEW.change_request_observation_id AND change_request_id=NEW.change_request_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER change_request_observations_retain BEFORE DELETE ON change_request_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX change_request_observations_fk_0 ON change_request_observations(origin_fetch_occurrence_id);
CREATE INDEX change_request_observations_fk_1 ON change_request_observations(change_request_id);
CREATE TRIGGER change_requests_immutable BEFORE UPDATE ON change_requests WHEN NEW.change_request_id IS NOT OLD.change_request_id OR NEW.repository_id IS NOT OLD.repository_id OR NEW.repository_binding_id IS NOT OLD.repository_binding_id OR NEW.change_request_kind IS NOT OLD.change_request_kind OR NEW.provider_change_request_number IS NOT OLD.provider_change_request_number BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER change_requests_no_replace BEFORE INSERT ON change_requests WHEN EXISTS(SELECT 1 FROM change_requests WHERE (change_request_id=NEW.change_request_id) OR (change_request_id=NEW.change_request_id AND repository_id=NEW.repository_id) OR (repository_binding_id=NEW.repository_binding_id AND change_request_kind=NEW.change_request_kind AND provider_change_request_number=NEW.provider_change_request_number) OR (change_request_id=NEW.change_request_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX change_requests_fk_0 ON change_requests(current_change_request_observation_id,change_request_id);
CREATE INDEX change_requests_fk_1 ON change_requests(repository_binding_id,repository_id);
CREATE TRIGGER code_acquisitions_immutable BEFORE UPDATE ON code_acquisitions WHEN NEW.code_observation_id IS NOT OLD.code_observation_id OR NEW.role IS NOT OLD.role OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.acquisition_root_id IS NOT OLD.acquisition_root_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_acquisitions_no_replace BEFORE INSERT ON code_acquisitions WHEN EXISTS(SELECT 1 FROM code_acquisitions WHERE (code_observation_id=NEW.code_observation_id AND role=NEW.role) OR (code_observation_id=NEW.code_observation_id AND role=NEW.role)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_acquisitions_retain BEFORE DELETE ON code_acquisitions BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_acquisitions_fk_0 ON code_acquisitions(acquisition_root_id);
CREATE TRIGGER code_commits_immutable BEFORE UPDATE ON code_commits WHEN NEW.code_listing_id IS NOT OLD.code_listing_id OR NEW.fetch_occurrence_id IS NOT OLD.fetch_occurrence_id OR NEW.position IS NOT OLD.position OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.payload IS NOT OLD.payload BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_commits_no_replace BEFORE INSERT ON code_commits WHEN EXISTS(SELECT 1 FROM code_commits WHERE (code_listing_id=NEW.code_listing_id AND fetch_occurrence_id=NEW.fetch_occurrence_id AND position=NEW.position) OR (code_listing_id=NEW.code_listing_id AND fetch_occurrence_id=NEW.fetch_occurrence_id AND position=NEW.position)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_commits_retain BEFORE DELETE ON code_commits BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_commits_fk_0 ON code_commits(fetch_occurrence_id);
CREATE TRIGGER code_file_changes_immutable BEFORE UPDATE ON code_file_changes WHEN NEW.code_listing_id IS NOT OLD.code_listing_id OR NEW.fetch_occurrence_id IS NOT OLD.fetch_occurrence_id OR NEW.position IS NOT OLD.position OR NEW.raw_path IS NOT OLD.raw_path OR NEW.payload IS NOT OLD.payload BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_file_changes_no_replace BEFORE INSERT ON code_file_changes WHEN EXISTS(SELECT 1 FROM code_file_changes WHERE (code_listing_id=NEW.code_listing_id AND fetch_occurrence_id=NEW.fetch_occurrence_id AND position=NEW.position) OR (code_listing_id=NEW.code_listing_id AND fetch_occurrence_id=NEW.fetch_occurrence_id AND position=NEW.position)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_file_changes_retain BEFORE DELETE ON code_file_changes BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_file_changes_fk_0 ON code_file_changes(fetch_occurrence_id);
CREATE TRIGGER code_listing_progress_immutable BEFORE UPDATE ON code_listing_progress WHEN NEW.code_listing_id IS NOT OLD.code_listing_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_listing_progress_no_replace BEFORE INSERT ON code_listing_progress WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE (code_listing_id=NEW.code_listing_id) OR (code_listing_id=NEW.code_listing_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_listings_immutable BEFORE UPDATE ON code_listings WHEN NEW.code_listing_id IS NOT OLD.code_listing_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.kind IS NOT OLD.kind OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.object_format IS NOT OLD.object_format OR NEW.head_oid IS NOT OLD.head_oid OR NEW.base_oid IS NOT OLD.base_oid BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_listings_no_replace BEFORE INSERT ON code_listings WHEN EXISTS(SELECT 1 FROM code_listings WHERE (code_listing_id=NEW.code_listing_id) OR (code_listing_id=NEW.code_listing_id AND change_request_id=NEW.change_request_id) OR (fetch_collection_id=NEW.fetch_collection_id AND kind=NEW.kind) OR (code_listing_id=NEW.code_listing_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_listings_retain BEFORE DELETE ON code_listings BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_listings_fk_0 ON code_listings(fetch_collection_id,change_request_id);
CREATE INDEX code_listings_fk_1 ON code_listings(resume_scope_id);
CREATE TRIGGER code_observations_immutable BEFORE UPDATE ON code_observations WHEN NEW.code_observation_id IS NOT OLD.code_observation_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.change_request_observation_id IS NOT OLD.change_request_observation_id OR NEW.commit_code_listing_id IS NOT OLD.commit_code_listing_id OR NEW.file_code_listing_id IS NOT OLD.file_code_listing_id OR NEW.state IS NOT OLD.state OR NEW.object_format IS NOT OLD.object_format OR NEW.head_oid IS NOT OLD.head_oid OR NEW.base_oid IS NOT OLD.base_oid OR NEW.details IS NOT OLD.details BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_observations_no_replace BEFORE INSERT ON code_observations WHEN EXISTS(SELECT 1 FROM code_observations WHERE (code_observation_id=NEW.code_observation_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_observations_retain BEFORE DELETE ON code_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_observations_fk_0 ON code_observations(file_code_listing_id,change_request_id);
CREATE INDEX code_observations_fk_1 ON code_observations(commit_code_listing_id,change_request_id);
CREATE INDEX code_observations_fk_2 ON code_observations(change_request_observation_id,change_request_id);
CREATE TRIGGER collection_progress_immutable BEFORE UPDATE ON collection_progress WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER collection_progress_no_replace BEFORE INSERT ON collection_progress WHEN EXISTS(SELECT 1 FROM collection_progress WHERE (fetch_collection_id=NEW.fetch_collection_id) OR (fetch_collection_id=NEW.fetch_collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX collection_progress_fk_0 ON collection_progress(job_id,attempt);
CREATE TRIGGER commit_parents_immutable BEFORE UPDATE ON commit_parents WHEN NEW.commit_git_object_id IS NOT OLD.commit_git_object_id OR NEW.parent_ordinal IS NOT OLD.parent_ordinal OR NEW.parent_git_object_id IS NOT OLD.parent_git_object_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER commit_parents_no_replace BEFORE INSERT ON commit_parents WHEN EXISTS(SELECT 1 FROM commit_parents WHERE (commit_git_object_id=NEW.commit_git_object_id AND parent_ordinal=NEW.parent_ordinal) OR (commit_git_object_id=NEW.commit_git_object_id AND parent_ordinal=NEW.parent_ordinal)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER commit_parents_retain BEFORE DELETE ON commit_parents BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX commit_parents_fk_0 ON commit_parents(parent_git_object_id);
CREATE TRIGGER commits_immutable BEFORE UPDATE ON commits WHEN NEW.git_object_id IS NOT OLD.git_object_id OR NEW.tree_git_object_id IS NOT OLD.tree_git_object_id OR NEW.raw_headers IS NOT OLD.raw_headers OR NEW.raw_message IS NOT OLD.raw_message OR NEW.metadata IS NOT OLD.metadata BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER commits_no_replace BEFORE INSERT ON commits WHEN EXISTS(SELECT 1 FROM commits WHERE (git_object_id=NEW.git_object_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER commits_retain BEFORE DELETE ON commits BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX commits_fk_0 ON commits(tree_git_object_id);
CREATE TRIGGER completion_markers_immutable BEFORE UPDATE ON completion_markers WHEN NEW.completion_marker_id IS NOT OLD.completion_marker_id OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.asserted_state IS NOT OLD.asserted_state OR NEW.evidence IS NOT OLD.evidence OR NEW.observed_at_us IS NOT OLD.observed_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER completion_markers_no_replace BEFORE INSERT ON completion_markers WHEN EXISTS(SELECT 1 FROM completion_markers WHERE (completion_marker_id=NEW.completion_marker_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
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
CREATE TRIGGER contents_immutable BEFORE UPDATE ON contents WHEN NEW.content_id IS NOT OLD.content_id OR NEW.byte_length IS NOT OLD.byte_length OR NEW.text_state IS NOT OLD.text_state OR NEW.created_at_us IS NOT OLD.created_at_us OR (NEW.raw_text IS NOT OLD.raw_text AND NOT (OLD.raw_text IS NULL AND NEW.raw_text IS NOT NULL AND OLD.text_state='eligible' AND instr(NEW.raw_text,char(0))=0 AND EXISTS(SELECT 1 FROM content_digests WHERE content_id=OLD.content_id AND representation='raw-content-v1' AND algorithm='sha256'))) BEGIN SELECT RAISE(ABORT,'Immutable content or invalid text completion'); END;
CREATE TRIGGER contents_no_replace BEFORE INSERT ON contents WHEN EXISTS(SELECT 1 FROM contents WHERE (content_id=NEW.content_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER contents_retain BEFORE DELETE ON contents BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER coverage_claims_immutable BEFORE UPDATE ON coverage_claims BEGIN SELECT RAISE(ABORT,'Immutable coverage claim'); END;
-- An unassigned INTEGER PRIMARY KEY can appear as -1 in BEFORE INSERT, so only
-- the semantic key is tested here. SQLite enforces explicit ID uniqueness;
-- retain rejects REPLACE's delete with required recursive_triggers enabled, and
-- immutable rejects every UPDATE, including a no-op ON CONFLICT DO UPDATE.
CREATE TRIGGER coverage_claims_no_replace BEFORE INSERT ON coverage_claims WHEN EXISTS(SELECT 1 FROM coverage_claims WHERE coverage_scope_id=NEW.coverage_scope_id AND observed_at_us=NEW.observed_at_us AND coverage_state=NEW.coverage_state) BEGIN SELECT RAISE(ABORT,'Duplicate coverage claim; use admission'); END;
CREATE TRIGGER coverage_claims_retain BEFORE DELETE ON coverage_claims BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX coverage_claims_fk_0 ON coverage_claims(coverage_scope_id);
CREATE TRIGGER coverage_scopes_immutable BEFORE UPDATE ON coverage_scopes WHEN NEW.coverage_scope_id IS NOT OLD.coverage_scope_id OR NEW.repository_id IS NOT OLD.repository_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER coverage_scopes_no_replace BEFORE INSERT ON coverage_scopes WHEN EXISTS(SELECT 1 FROM coverage_scopes WHERE coverage_scope_id=NEW.coverage_scope_id OR (repository_id=NEW.repository_id AND change_request_id IS NEW.change_request_id AND kind=NEW.kind)) BEGIN SELECT RAISE(ABORT,'Duplicate coverage scope'); END;
CREATE INDEX coverage_scopes_fk_1 ON coverage_scopes(change_request_id,repository_id);
CREATE INDEX coverage_scopes_fk_2 ON coverage_scopes(repository_id);
CREATE TRIGGER database_identity_immutable BEFORE UPDATE ON database_identity WHEN NEW.singleton IS NOT OLD.singleton OR NEW.format_id IS NOT OLD.format_id OR NEW.schema_version IS NOT OLD.schema_version OR NEW.ddl_sha256 IS NOT OLD.ddl_sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER database_identity_no_replace BEFORE INSERT ON database_identity WHEN EXISTS(SELECT 1 FROM database_identity WHERE (singleton=NEW.singleton)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
-- Remote observation replay and provider-resource relationships are hot per-comment
-- lookups. Keep them indexed as collections/history grow.
CREATE TRIGGER fetch_collections_immutable BEFORE UPDATE ON fetch_collections WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.repository_id IS NOT OLD.repository_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.source_id IS NOT OLD.source_id OR NEW.kind IS NOT OLD.kind OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.observed_at_us IS NOT OLD.observed_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER fetch_collections_no_replace BEFORE INSERT ON fetch_collections WHEN EXISTS(SELECT 1 FROM fetch_collections WHERE (fetch_collection_id=NEW.fetch_collection_id) OR (fetch_collection_id=NEW.fetch_collection_id AND change_request_id=NEW.change_request_id) OR (fetch_collection_id=NEW.fetch_collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER fetch_collections_retain BEFORE DELETE ON fetch_collections BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX fetch_collections_fk_0 ON fetch_collections(change_request_id,repository_id);
CREATE INDEX fetch_collections_fk_1 ON fetch_collections(resume_scope_id);
CREATE INDEX fetch_collections_fk_2 ON fetch_collections(source_id);
CREATE INDEX fetch_collections_fk_3 ON fetch_collections(repository_id);
CREATE TRIGGER fetch_occurrences_immutable BEFORE UPDATE ON fetch_occurrences WHEN NEW.fetch_occurrence_id IS NOT OLD.fetch_occurrence_id OR NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.ordinal IS NOT OLD.ordinal OR NEW.payload_id IS NOT OLD.payload_id OR NEW.request IS NOT OLD.request OR NEW.next_cursor IS NOT OLD.next_cursor OR NEW.observed_at_us IS NOT OLD.observed_at_us OR NEW.parsed_at_us IS NOT OLD.parsed_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER fetch_occurrences_no_replace BEFORE INSERT ON fetch_occurrences WHEN EXISTS(SELECT 1 FROM fetch_occurrences WHERE (fetch_occurrence_id=NEW.fetch_occurrence_id) OR (fetch_occurrence_id=NEW.fetch_occurrence_id AND fetch_collection_id=NEW.fetch_collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER fetch_occurrences_retain BEFORE DELETE ON fetch_occurrences BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX fetch_occurrences_fk_0 ON fetch_occurrences(payload_id);
CREATE INDEX fetch_occurrences_fk_1 ON fetch_occurrences(fetch_collection_id);
CREATE TRIGGER git_acquisitions_immutable BEFORE UPDATE ON git_acquisitions WHEN NEW.git_acquisition_id IS NOT OLD.git_acquisition_id OR NEW.repository_id IS NOT OLD.repository_id OR NEW.repository_endpoint_id IS NOT OLD.repository_endpoint_id OR NEW.endpoint_url IS NOT OLD.endpoint_url OR (OLD.object_format IS NOT NULL AND NEW.object_format IS NOT OLD.object_format) OR (OLD.refs_observed_at_us IS NOT NULL AND NEW.refs_observed_at_us IS NOT OLD.refs_observed_at_us) OR NEW.source_id IS NOT OLD.source_id OR NEW.kind IS NOT OLD.kind OR NEW.started_at_us IS NOT OLD.started_at_us OR (OLD.observed_at_us IS NOT NULL AND NEW.observed_at_us IS NOT OLD.observed_at_us) OR NEW.request IS NOT OLD.request OR (OLD.roots_manifest IS NOT NULL AND NEW.roots_manifest IS NOT OLD.roots_manifest) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER git_acquisitions_no_replace BEFORE INSERT ON git_acquisitions WHEN EXISTS(SELECT 1 FROM git_acquisitions WHERE (git_acquisition_id=NEW.git_acquisition_id) OR (git_acquisition_id=NEW.git_acquisition_id AND repository_id=NEW.repository_id) OR (git_acquisition_id=NEW.git_acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER git_acquisitions_retain BEFORE DELETE ON git_acquisitions BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX git_acquisitions_fk_0 ON git_acquisitions(repository_endpoint_id,repository_id);
CREATE INDEX git_acquisitions_fk_1 ON git_acquisitions(source_id);
CREATE INDEX git_acquisitions_fk_2 ON git_acquisitions(repository_id);
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
CREATE TRIGGER inventory_observations_immutable BEFORE UPDATE ON inventory_observations WHEN NEW.inventory_observation_id IS NOT OLD.inventory_observation_id OR NEW.source_id IS NOT OLD.source_id OR NEW.asserted_state IS NOT OLD.asserted_state OR NEW.scope IS NOT OLD.scope OR NEW.observed_at_us IS NOT OLD.observed_at_us OR NEW.reason IS NOT OLD.reason BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER inventory_observations_no_replace BEFORE INSERT ON inventory_observations WHEN EXISTS(SELECT 1 FROM inventory_observations WHERE (inventory_observation_id=NEW.inventory_observation_id) OR (inventory_observation_id=NEW.inventory_observation_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER inventory_observations_retain BEFORE DELETE ON inventory_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX inventory_observations_fk_0 ON inventory_observations(source_id);
CREATE TRIGGER job_attempts_immutable BEFORE UPDATE ON job_attempts WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER job_attempts_no_replace BEFORE INSERT ON job_attempts WHEN EXISTS(SELECT 1 FROM job_attempts WHERE (job_id=NEW.job_id AND attempt=NEW.attempt) OR (job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER jobs_immutable BEFORE UPDATE ON jobs WHEN NEW.job_id IS NOT OLD.job_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER jobs_no_replace BEFORE INSERT ON jobs WHEN EXISTS(SELECT 1 FROM jobs WHERE (job_id=NEW.job_id) OR (job_id=NEW.job_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX jobs_fk_0 ON jobs(job_id,current_attempt);
CREATE TRIGGER payloads_immutable BEFORE UPDATE ON payloads WHEN NEW.payload_id IS NOT OLD.payload_id OR NEW.sha256 IS NOT OLD.sha256 OR NEW.body IS NOT OLD.body OR NEW.byte_length IS NOT OLD.byte_length OR NEW.representation IS NOT OLD.representation BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER payloads_no_replace BEFORE INSERT ON payloads WHEN EXISTS(SELECT 1 FROM payloads WHERE (payload_id=NEW.payload_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER payloads_retain BEFORE DELETE ON payloads BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER preservation_obligations_immutable BEFORE UPDATE ON preservation_obligations WHEN NEW.git_acquisition_id IS NOT OLD.git_acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER preservation_obligations_no_replace BEFORE INSERT ON preservation_obligations WHEN EXISTS(SELECT 1 FROM preservation_obligations WHERE (git_acquisition_id=NEW.git_acquisition_id) OR (git_acquisition_id=NEW.git_acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX preservation_obligations_fk_0 ON preservation_obligations(cache_locator_id);
CREATE TRIGGER ref_observations_immutable BEFORE UPDATE ON ref_observations WHEN NEW.snapshot_id IS NOT OLD.snapshot_id OR NEW.raw_ref_name IS NOT OLD.raw_ref_name OR NEW.kind IS NOT OLD.kind OR NEW.object_format IS NOT OLD.object_format OR NEW.target_oid IS NOT OLD.target_oid OR NEW.peeled_oid IS NOT OLD.peeled_oid OR NEW.target_type IS NOT OLD.target_type BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER ref_observations_no_replace BEFORE INSERT ON ref_observations WHEN EXISTS(SELECT 1 FROM ref_observations WHERE (snapshot_id=NEW.snapshot_id AND raw_ref_name=NEW.raw_ref_name) OR (snapshot_id=NEW.snapshot_id AND raw_ref_name=NEW.raw_ref_name)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER ref_observations_retain BEFORE DELETE ON ref_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER repositories_immutable BEFORE UPDATE ON repositories WHEN NEW.repository_id IS NOT OLD.repository_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repositories_no_replace BEFORE INSERT ON repositories WHEN EXISTS(SELECT 1 FROM repositories WHERE (repository_id=NEW.repository_id) OR (repository_id=NEW.repository_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX repositories_fk_0 ON repositories(current_snapshot_id,repository_id);
CREATE INDEX repositories_fk_1 ON repositories(preferred_repository_endpoint_id,repository_id);
CREATE TRIGGER repository_bindings_immutable BEFORE UPDATE ON repository_bindings WHEN NEW.repository_binding_id IS NOT OLD.repository_binding_id OR NEW.repository_id IS NOT OLD.repository_id OR NEW.service_instance_uuidv4 IS NOT OLD.service_instance_uuidv4 OR (OLD.provider_repository_id IS NOT NULL AND NEW.provider_repository_id IS NOT OLD.provider_repository_id) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_bindings_no_replace BEFORE INSERT ON repository_bindings WHEN EXISTS(SELECT 1 FROM repository_bindings WHERE (repository_binding_id=NEW.repository_binding_id) OR (repository_binding_id=NEW.repository_binding_id AND repository_id=NEW.repository_id) OR (service_instance_uuidv4=NEW.service_instance_uuidv4 AND provider_repository_id=NEW.provider_repository_id) OR (repository_id=NEW.repository_id AND service_instance_uuidv4=NEW.service_instance_uuidv4) OR (repository_binding_id=NEW.repository_binding_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_endpoints_immutable BEFORE UPDATE ON repository_endpoints WHEN NEW.repository_endpoint_id IS NOT OLD.repository_endpoint_id OR NEW.repository_id IS NOT OLD.repository_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_endpoints_no_replace BEFORE INSERT ON repository_endpoints WHEN EXISTS(SELECT 1 FROM repository_endpoints WHERE (repository_endpoint_id=NEW.repository_endpoint_id) OR (repository_endpoint_id=NEW.repository_endpoint_id AND repository_id=NEW.repository_id) OR (repository_id=NEW.repository_id AND url=NEW.url) OR (repository_endpoint_id=NEW.repository_endpoint_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_name_assertions_immutable BEFORE UPDATE ON repository_name_assertions WHEN NEW.repository_id IS NOT OLD.repository_id OR NEW.name IS NOT OLD.name OR NEW.observed_at_us IS NOT OLD.observed_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_name_assertions_no_replace BEFORE INSERT ON repository_name_assertions WHEN EXISTS(SELECT 1 FROM repository_name_assertions WHERE (repository_id=NEW.repository_id AND name=NEW.name) OR (repository_id=NEW.repository_id AND name=NEW.name)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_name_assertions_retain BEFORE DELETE ON repository_name_assertions BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER repository_object_sources_immutable BEFORE UPDATE ON repository_object_sources WHEN NEW.repository_id IS NOT OLD.repository_id OR NEW.git_object_id IS NOT OLD.git_object_id OR NEW.git_acquisition_id IS NOT OLD.git_acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_object_sources_no_replace BEFORE INSERT ON repository_object_sources WHEN EXISTS(SELECT 1 FROM repository_object_sources WHERE (repository_id=NEW.repository_id AND git_object_id=NEW.git_object_id AND git_acquisition_id=NEW.git_acquisition_id) OR (repository_id=NEW.repository_id AND git_object_id=NEW.git_object_id AND git_acquisition_id=NEW.git_acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_object_sources_retain BEFORE DELETE ON repository_object_sources BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX repository_object_sources_fk_0 ON repository_object_sources(git_acquisition_id,repository_id);
CREATE INDEX repository_object_sources_fk_1 ON repository_object_sources(git_object_id);
CREATE TRIGGER resume_cursors_immutable BEFORE UPDATE ON resume_cursors WHEN NEW.resume_scope_id IS NOT OLD.resume_scope_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER resume_cursors_no_replace BEFORE INSERT ON resume_cursors WHEN EXISTS(SELECT 1 FROM resume_cursors WHERE (resume_scope_id=NEW.resume_scope_id) OR (resume_scope_id=NEW.resume_scope_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX resume_cursors_fk_0 ON resume_cursors(incremental_scan_id,resume_scope_id);
CREATE TRIGGER resume_scopes_immutable BEFORE UPDATE ON resume_scopes WHEN NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.repository_id IS NOT OLD.repository_id OR NEW.repository_binding_id IS NOT OLD.repository_binding_id OR NEW.source_id IS NOT OLD.source_id OR NEW.principal_ref IS NOT OLD.principal_ref OR NEW.api_version IS NOT OLD.api_version OR NEW.endpoint IS NOT OLD.endpoint OR NEW.request_context IS NOT OLD.request_context OR NEW.parser_version IS NOT OLD.parser_version OR NEW.profile_version IS NOT OLD.profile_version OR NEW.confidence IS NOT OLD.confidence BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER resume_scopes_no_replace BEFORE INSERT ON resume_scopes WHEN EXISTS(SELECT 1 FROM resume_scopes WHERE (resume_scope_id=NEW.resume_scope_id) OR (resume_scope_id=NEW.resume_scope_id AND repository_id=NEW.repository_id) OR (resume_scope_id=NEW.resume_scope_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER resume_scopes_retain BEFORE DELETE ON resume_scopes BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX resume_scopes_fk_0 ON resume_scopes(repository_binding_id,repository_id);
CREATE INDEX resume_scopes_fk_1 ON resume_scopes(source_id);
CREATE INDEX resume_scopes_fk_2 ON resume_scopes(repository_id);
CREATE TRIGGER review_threads_immutable BEFORE UPDATE ON review_threads WHEN NEW.change_request_id IS NOT OLD.change_request_id OR NEW.provider_resource_id IS NOT OLD.provider_resource_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER review_threads_no_replace BEFORE INSERT ON review_threads WHEN EXISTS(SELECT 1 FROM review_threads WHERE change_request_id=NEW.change_request_id AND provider_resource_id=NEW.provider_resource_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX review_threads_fk_0 ON review_threads(change_request_id);
CREATE TRIGGER root_manifest_entries_immutable BEFORE UPDATE ON root_manifest_entries WHEN NEW.tree_git_object_id IS NOT OLD.tree_git_object_id OR NEW.raw_path IS NOT OLD.raw_path OR NEW.mode IS NOT OLD.mode OR NEW.git_object_id IS NOT OLD.git_object_id OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER root_manifest_entries_no_replace BEFORE INSERT ON root_manifest_entries WHEN EXISTS(SELECT 1 FROM root_manifest_entries WHERE (tree_git_object_id=NEW.tree_git_object_id AND raw_path=NEW.raw_path) OR (tree_git_object_id=NEW.tree_git_object_id AND raw_path=NEW.raw_path)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER root_manifest_entries_retain BEFORE DELETE ON root_manifest_entries BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX root_manifest_entries_fk_0 ON root_manifest_entries(git_object_id);
CREATE TRIGGER root_manifests_immutable BEFORE UPDATE ON root_manifests WHEN NEW.tree_git_object_id IS NOT OLD.tree_git_object_id OR NEW.complete<OLD.complete BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER root_manifests_no_replace BEFORE INSERT ON root_manifests WHEN EXISTS(SELECT 1 FROM root_manifests WHERE (tree_git_object_id=NEW.tree_git_object_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER root_manifests_retain BEFORE DELETE ON root_manifests BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER root_origins_immutable BEFORE UPDATE ON root_origins WHEN NEW.root_origin_id IS NOT OLD.root_origin_id OR NEW.acquisition_root_id IS NOT OLD.acquisition_root_id OR NEW.origin_kind IS NOT OLD.origin_kind OR NEW.raw_ref_name IS NOT OLD.raw_ref_name OR NEW.source_ordinal IS NOT OLD.source_ordinal OR NEW.snapshot_id IS NOT OLD.snapshot_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.change_request_observation_id IS NOT OLD.change_request_observation_id OR NEW.repository_id IS NOT OLD.repository_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER root_origins_no_replace BEFORE INSERT ON root_origins WHEN EXISTS(SELECT 1 FROM root_origins WHERE (root_origin_id=NEW.root_origin_id) OR (acquisition_root_id=NEW.acquisition_root_id AND origin_kind=NEW.origin_kind AND source_ordinal=NEW.source_ordinal)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER root_origins_retain BEFORE DELETE ON root_origins BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX root_origins_fk_0 ON root_origins(change_request_observation_id,change_request_id);
CREATE INDEX root_origins_fk_1 ON root_origins(change_request_id,repository_id);
CREATE INDEX root_origins_fk_2 ON root_origins(snapshot_id,repository_id);
CREATE INDEX root_origins_fk_3 ON root_origins(acquisition_root_id,repository_id);
CREATE TRIGGER search_documents_immutable BEFORE UPDATE ON search_documents WHEN NEW.search_document_id IS NOT OLD.search_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER search_documents_no_replace BEFORE INSERT ON search_documents WHEN EXISTS(SELECT 1 FROM search_documents WHERE (search_document_id=NEW.search_document_id) OR (kind=NEW.kind AND source_key=NEW.source_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER service_instances_immutable BEFORE UPDATE ON service_instances WHEN NEW.service_instance_uuidv4 IS NOT OLD.service_instance_uuidv4 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER service_instances_no_replace BEFORE INSERT ON service_instances WHEN EXISTS(SELECT 1 FROM service_instances WHERE (service_instance_uuidv4=NEW.service_instance_uuidv4) OR (name=NEW.name) OR (service_instance_uuidv4=NEW.service_instance_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER snapshots_immutable BEFORE UPDATE ON snapshots WHEN NEW.snapshot_id IS NOT OLD.snapshot_id OR NEW.git_acquisition_id IS NOT OLD.git_acquisition_id OR NEW.repository_id IS NOT OLD.repository_id OR NEW.generation IS NOT OLD.generation OR NEW.created_at_us IS NOT OLD.created_at_us OR (OLD.published=1 AND NEW.published!=1) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER snapshots_no_replace BEFORE INSERT ON snapshots WHEN EXISTS(SELECT 1 FROM snapshots WHERE (snapshot_id=NEW.snapshot_id) OR (snapshot_id=NEW.snapshot_id AND repository_id=NEW.repository_id) OR (git_acquisition_id=NEW.git_acquisition_id) OR (snapshot_id=NEW.snapshot_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER snapshots_retain BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX snapshots_fk_0 ON snapshots(git_acquisition_id,repository_id);
-- Pair membership is retained; times are aggregate known min/max, not event rows.
-- NULL may become known, never the reverse. Integer microseconds preserve exact
-- temporal ordering, including observations within the same millisecond.
CREATE TRIGGER source_repositories_immutable BEFORE UPDATE ON source_repositories WHEN NEW.source_id IS NOT OLD.source_id OR NEW.repository_id IS NOT OLD.repository_id OR (OLD.first_seen_us IS NOT NULL AND (NEW.first_seen_us IS NULL OR NEW.first_seen_us>OLD.first_seen_us)) OR (OLD.last_seen_us IS NOT NULL AND (NEW.last_seen_us IS NULL OR NEW.last_seen_us<OLD.last_seen_us)) BEGIN SELECT RAISE(ABORT,'Immutable source pair or aggregate time regression'); END;
CREATE TRIGGER source_repositories_no_replace BEFORE INSERT ON source_repositories WHEN EXISTS(SELECT 1 FROM source_repositories WHERE (source_id=NEW.source_id AND repository_id=NEW.repository_id) OR (source_id=NEW.source_id AND repository_id=NEW.repository_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER source_repositories_retain BEFORE DELETE ON source_repositories BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX source_repositories_fk_0 ON source_repositories(repository_id);
CREATE TRIGGER sources_immutable BEFORE UPDATE ON sources WHEN NEW.source_id IS NOT OLD.source_id OR NEW.service_instance_uuidv4 IS NOT OLD.service_instance_uuidv4 OR NEW.discovery_kind IS NOT OLD.discovery_kind BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER sources_no_replace BEFORE INSERT ON sources WHEN EXISTS(SELECT 1 FROM sources WHERE (source_id=NEW.source_id) OR (source_id=NEW.source_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX sources_fk_0 ON sources(service_instance_uuidv4);
CREATE TRIGGER space_reservations_immutable BEFORE UPDATE ON space_reservations WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER space_reservations_no_replace BEFORE INSERT ON space_reservations WHEN EXISTS(SELECT 1 FROM space_reservations WHERE (job_id=NEW.job_id AND attempt=NEW.attempt) OR (job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER tag_objects_immutable BEFORE UPDATE ON tag_objects WHEN NEW.git_object_id IS NOT OLD.git_object_id OR NEW.target_git_object_id IS NOT OLD.target_git_object_id OR NEW.raw_payload IS NOT OLD.raw_payload BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER tag_objects_no_replace BEFORE INSERT ON tag_objects WHEN EXISTS(SELECT 1 FROM tag_objects WHERE (git_object_id=NEW.git_object_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER tag_objects_retain BEFORE DELETE ON tag_objects BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX tag_objects_fk_0 ON tag_objects(target_git_object_id);
CREATE TRIGGER text_bodies_immutable BEFORE UPDATE ON text_bodies WHEN NEW.text_body_id IS NOT OLD.text_body_id OR NEW.body IS NOT OLD.body OR NEW.byte_length IS NOT OLD.byte_length OR NEW.sha256 IS NOT OLD.sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER text_bodies_no_replace BEFORE INSERT ON text_bodies WHEN EXISTS(SELECT 1 FROM text_bodies WHERE (text_body_id=NEW.text_body_id) OR (sha256=NEW.sha256)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER text_bodies_retain BEFORE DELETE ON text_bodies BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER tree_entries_immutable BEFORE UPDATE ON tree_entries WHEN NEW.tree_git_object_id IS NOT OLD.tree_git_object_id OR NEW.raw_name IS NOT OLD.raw_name OR NEW.mode IS NOT OLD.mode OR NEW.child_format IS NOT OLD.child_format OR NEW.child_oid IS NOT OLD.child_oid OR NEW.child_git_object_id IS NOT OLD.child_git_object_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER tree_entries_no_replace BEFORE INSERT ON tree_entries WHEN EXISTS(SELECT 1 FROM tree_entries WHERE (tree_git_object_id=NEW.tree_git_object_id AND raw_name=NEW.raw_name) OR (tree_git_object_id=NEW.tree_git_object_id AND raw_name=NEW.raw_name)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER tree_entries_retain BEFORE DELETE ON tree_entries BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX tree_entries_fk_0 ON tree_entries(child_git_object_id);
CREATE TRIGGER unresolved_payloads_immutable BEFORE UPDATE ON unresolved_payloads WHEN NEW.unresolved_payload_id IS NOT OLD.unresolved_payload_id OR NEW.payload_id IS NOT OLD.payload_id OR NEW.reason IS NOT OLD.reason BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER unresolved_payloads_no_replace BEFORE INSERT ON unresolved_payloads WHEN EXISTS(SELECT 1 FROM unresolved_payloads WHERE (unresolved_payload_id=NEW.unresolved_payload_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER unresolved_payloads_retain BEFORE DELETE ON unresolved_payloads BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX unresolved_payloads_fk_1 ON unresolved_payloads(payload_id);
CREATE TRIGGER validators_immutable BEFORE UPDATE ON validators WHEN NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.validator_key IS NOT OLD.validator_key BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER validators_no_replace BEFORE INSERT ON validators WHEN EXISTS(SELECT 1 FROM validators WHERE (resume_scope_id=NEW.resume_scope_id AND validator_key=NEW.validator_key) OR (resume_scope_id=NEW.resume_scope_id AND validator_key=NEW.validator_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX validators_fk_0 ON validators(payload_id);
CREATE TRIGGER snapshot_current_insert BEFORE INSERT ON repositories WHEN NEW.current_snapshot_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM snapshots WHERE snapshot_id=NEW.current_snapshot_id AND repository_id=NEW.repository_id AND published=1) BEGIN SELECT RAISE(ABORT,'Current snapshot requires published fact'); END;
CREATE TRIGGER snapshot_current_update BEFORE UPDATE ON repositories WHEN NEW.current_snapshot_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM snapshots WHERE snapshot_id=NEW.current_snapshot_id AND repository_id=NEW.repository_id AND published=1) BEGIN SELECT RAISE(ABORT,'Current snapshot requires published fact'); END;
CREATE TRIGGER cr_current_insert BEFORE INSERT ON change_requests WHEN NEW.current_change_request_observation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM change_request_observations WHERE change_request_observation_id=NEW.current_change_request_observation_id AND change_request_id=NEW.change_request_id AND published=1) BEGIN SELECT RAISE(ABORT,'Current observation requires published fact'); END;
CREATE TRIGGER cr_current_update BEFORE UPDATE ON change_requests WHEN NEW.current_change_request_observation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM change_request_observations WHERE change_request_observation_id=NEW.current_change_request_observation_id AND change_request_id=NEW.change_request_id AND published=1) BEGIN SELECT RAISE(ABORT,'Current observation requires published fact'); END;
CREATE TRIGGER listing_scope_insert BEFORE INSERT ON code_listings WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id AND f.resume_scope_id=NEW.resume_scope_id) BEGIN SELECT RAISE(ABORT,'Listing collection, CR and scope mismatch'); END;
CREATE TRIGGER listing_scope_update BEFORE UPDATE ON code_listings WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id AND f.resume_scope_id=NEW.resume_scope_id) BEGIN SELECT RAISE(ABORT,'Listing collection, CR and scope mismatch'); END;
CREATE TRIGGER fetch_scope_insert BEFORE INSERT ON fetch_collections WHEN NOT EXISTS(SELECT 1 FROM resume_scopes s WHERE s.resume_scope_id=NEW.resume_scope_id AND s.repository_id=NEW.repository_id AND s.source_id IS NEW.source_id) BEGIN SELECT RAISE(ABORT,'Collection scope mismatch'); END;
CREATE TRIGGER fetch_scope_update BEFORE UPDATE ON fetch_collections WHEN NOT EXISTS(SELECT 1 FROM resume_scopes s WHERE s.resume_scope_id=NEW.resume_scope_id AND s.repository_id=NEW.repository_id AND s.source_id IS NEW.source_id) BEGIN SELECT RAISE(ABORT,'Collection scope mismatch'); END;
CREATE TRIGGER code_commits_insert BEFORE INSERT ON code_observations WHEN NEW.commit_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.commit_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_commits_update BEFORE UPDATE ON code_observations WHEN NEW.commit_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.commit_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_files_insert BEFORE INSERT ON code_observations WHEN NEW.file_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.file_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='files' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_files_update BEFORE UPDATE ON code_observations WHEN NEW.file_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.file_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='files' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_complete_insert BEFORE INSERT ON code_observations WHEN NEW.state='complete' AND (NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.commit_code_listing_id AND state='complete') OR NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.file_code_listing_id AND state='complete')) BEGIN SELECT RAISE(ABORT,'Complete code requires complete listings'); END;
CREATE TRIGGER code_complete_update BEFORE UPDATE ON code_observations WHEN NEW.state='complete' AND (NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.commit_code_listing_id AND state='complete') OR NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.file_code_listing_id AND state='complete')) BEGIN SELECT RAISE(ABORT,'Complete code requires complete listings'); END;
CREATE TRIGGER listing_no_downgrade BEFORE UPDATE ON code_listing_progress WHEN OLD.state='complete' AND (NEW.state IS NOT OLD.state OR NEW.terminal IS NOT OLD.terminal OR NEW.page_count IS NOT OLD.page_count OR NEW.context_proven IS NOT OLD.context_proven) BEGIN SELECT RAISE(ABORT,'Completed listing is immutable'); END;
-- Completion seals even an unreferenced listing. Deleting and recreating its
-- marker must not reopen it; conflict INSERT/REPLACE is separately prohibited.
CREATE TRIGGER listing_complete_retain BEFORE DELETE ON code_listing_progress WHEN OLD.state='complete' BEGIN SELECT RAISE(ABORT,'Complete listing marker cannot be deleted'); END;
CREATE TRIGGER code_commits_context_insert BEFORE INSERT ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.fetch_collection_id=l.fetch_collection_id WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='commits' AND o.fetch_occurrence_id=NEW.fetch_occurrence_id AND l.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_commits_context_update BEFORE UPDATE ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.fetch_collection_id=l.fetch_collection_id WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='commits' AND o.fetch_occurrence_id=NEW.fetch_occurrence_id AND l.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_commits_sealed_insert BEFORE INSERT ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id AND state='partial') BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_commits_sealed_update BEFORE UPDATE ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id AND state='partial') BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_file_changes_context_insert BEFORE INSERT ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.fetch_collection_id=l.fetch_collection_id WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='files' AND o.fetch_occurrence_id=NEW.fetch_occurrence_id) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_file_changes_context_update BEFORE UPDATE ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.fetch_collection_id=l.fetch_collection_id WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='files' AND o.fetch_occurrence_id=NEW.fetch_occurrence_id) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_file_changes_sealed_insert BEFORE INSERT ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id AND state='partial') BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_file_changes_sealed_update BEFORE UPDATE ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id AND state='partial') BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_acquisition_owner_insert BEFORE INSERT ON code_acquisitions WHEN NEW.acquisition_root_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_observations o ON o.code_observation_id=NEW.code_observation_id JOIN change_requests c ON c.change_request_id=o.change_request_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND r.repository_id=c.repository_id AND (r.role=NEW.role OR (r.role='traversal' AND EXISTS(SELECT 1 FROM git_acquisitions g,json_each(g.roots_manifest) j WHERE g.git_acquisition_id=r.git_acquisition_id AND json_extract(j.value,'$.role')=NEW.role AND lower(json_extract(j.value,'$.expected'))=lower(hex(NEW.oid))))) AND r.object_format=NEW.object_format AND r.oid=NEW.oid AND (r.expected_oid IS NULL OR r.expected_oid=NEW.oid)) BEGIN SELECT RAISE(ABORT,'Code acquisition owner, role or OID mismatch'); END;
CREATE TRIGGER code_acquisition_owner_update BEFORE UPDATE ON code_acquisitions WHEN NEW.acquisition_root_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_observations o ON o.code_observation_id=NEW.code_observation_id JOIN change_requests c ON c.change_request_id=o.change_request_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND r.repository_id=c.repository_id AND (r.role=NEW.role OR (r.role='traversal' AND EXISTS(SELECT 1 FROM git_acquisitions g,json_each(g.roots_manifest) j WHERE g.git_acquisition_id=r.git_acquisition_id AND json_extract(j.value,'$.role')=NEW.role AND lower(json_extract(j.value,'$.expected'))=lower(hex(NEW.oid))))) AND r.object_format=NEW.object_format AND r.oid=NEW.oid AND (r.expected_oid IS NULL OR r.expected_oid=NEW.oid)) BEGIN SELECT RAISE(ABORT,'Code acquisition owner, role or OID mismatch'); END;
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
CREATE TRIGGER commit_type_insert BEFORE INSERT ON commits WHEN NOT EXISTS(SELECT 1 FROM git_objects c JOIN git_objects t ON t.git_object_id=NEW.tree_git_object_id WHERE c.git_object_id=NEW.git_object_id AND c.type='commit' AND t.type='tree' AND c.object_format=t.object_format) BEGIN SELECT RAISE(ABORT,'Commit or tree type/format mismatch'); END;
CREATE TRIGGER commit_type_update BEFORE UPDATE ON commits WHEN NOT EXISTS(SELECT 1 FROM git_objects c JOIN git_objects t ON t.git_object_id=NEW.tree_git_object_id WHERE c.git_object_id=NEW.git_object_id AND c.type='commit' AND t.type='tree' AND c.object_format=t.object_format) BEGIN SELECT RAISE(ABORT,'Commit or tree type/format mismatch'); END;
CREATE TRIGGER parent_type_insert BEFORE INSERT ON commit_parents WHEN NOT EXISTS(SELECT 1 FROM git_objects c JOIN git_objects p ON p.git_object_id=NEW.parent_git_object_id WHERE c.git_object_id=NEW.commit_git_object_id AND p.type='commit' AND c.object_format=p.object_format) BEGIN SELECT RAISE(ABORT,'Parent type/format mismatch'); END;
CREATE TRIGGER parent_type_update BEFORE UPDATE ON commit_parents WHEN NOT EXISTS(SELECT 1 FROM git_objects c JOIN git_objects p ON p.git_object_id=NEW.parent_git_object_id WHERE c.git_object_id=NEW.commit_git_object_id AND p.type='commit' AND c.object_format=p.object_format) BEGIN SELECT RAISE(ABORT,'Parent type/format mismatch'); END;
CREATE TRIGGER tree_type_insert BEFORE INSERT ON tree_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects t WHERE t.git_object_id=NEW.tree_git_object_id AND t.type='tree' AND t.object_format=NEW.child_format) OR (NEW.child_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects c WHERE c.git_object_id=NEW.child_git_object_id AND c.object_format=NEW.child_format AND c.oid=NEW.child_oid AND c.type=CASE WHEN NEW.mode=16384 THEN 'tree' ELSE 'blob' END)) BEGIN SELECT RAISE(ABORT,'Tree child type/format/OID mismatch'); END;
CREATE TRIGGER tree_type_update BEFORE UPDATE ON tree_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects t WHERE t.git_object_id=NEW.tree_git_object_id AND t.type='tree' AND t.object_format=NEW.child_format) OR (NEW.child_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects c WHERE c.git_object_id=NEW.child_git_object_id AND c.object_format=NEW.child_format AND c.oid=NEW.child_oid AND c.type=CASE WHEN NEW.mode=16384 THEN 'tree' ELSE 'blob' END)) BEGIN SELECT RAISE(ABORT,'Tree child type/format/OID mismatch'); END;
CREATE TRIGGER tag_type_insert BEFORE INSERT ON tag_objects WHEN NOT EXISTS(SELECT 1 FROM git_objects t JOIN git_objects c ON c.git_object_id=NEW.target_git_object_id WHERE t.git_object_id=NEW.git_object_id AND t.type='tag' AND t.object_format=c.object_format) BEGIN SELECT RAISE(ABORT,'Tag type/format mismatch'); END;
CREATE TRIGGER tag_type_update BEFORE UPDATE ON tag_objects WHEN NOT EXISTS(SELECT 1 FROM git_objects t JOIN git_objects c ON c.git_object_id=NEW.target_git_object_id WHERE t.git_object_id=NEW.git_object_id AND t.type='tag' AND t.object_format=c.object_format) BEGIN SELECT RAISE(ABORT,'Tag type/format mismatch'); END;
CREATE TRIGGER blob_type_insert BEFORE INSERT ON blob_content_map WHEN NOT EXISTS(SELECT 1 FROM git_objects o JOIN contents c ON c.content_id=NEW.content_id WHERE o.git_object_id=NEW.git_object_id AND o.type='blob' AND o.size=c.byte_length) BEGIN SELECT RAISE(ABORT,'Blob content type/length mismatch'); END;
CREATE TRIGGER blob_type_update BEFORE UPDATE ON blob_content_map WHEN NOT EXISTS(SELECT 1 FROM git_objects o JOIN contents c ON c.content_id=NEW.content_id WHERE o.git_object_id=NEW.git_object_id AND o.type='blob' AND o.size=c.byte_length) BEGIN SELECT RAISE(ABORT,'Blob content type/length mismatch'); END;
CREATE TRIGGER manifest_type_insert BEFORE INSERT ON root_manifests WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.tree_git_object_id AND type='tree') BEGIN SELECT RAISE(ABORT,'Manifest requires tree'); END;
CREATE TRIGGER manifest_type_update BEFORE UPDATE ON root_manifests WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.tree_git_object_id AND type='tree') BEGIN SELECT RAISE(ABORT,'Manifest requires tree'); END;
CREATE TRIGGER manifest_entry_type_insert BEFORE INSERT ON root_manifest_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.tree_git_object_id AND type='tree' AND object_format=NEW.object_format) OR (NEW.git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.git_object_id AND type='blob' AND oid=NEW.oid AND object_format=NEW.object_format)) BEGIN SELECT RAISE(ABORT,'Manifest type/format/OID mismatch'); END;
CREATE TRIGGER manifest_entry_type_update BEFORE UPDATE ON root_manifest_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.tree_git_object_id AND type='tree' AND object_format=NEW.object_format) OR (NEW.git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.git_object_id AND type='blob' AND oid=NEW.oid AND object_format=NEW.object_format)) BEGIN SELECT RAISE(ABORT,'Manifest type/format/OID mismatch'); END;

CREATE TRIGGER manifest_entries_sealed_insert BEFORE INSERT ON root_manifest_entries WHEN EXISTS(SELECT 1 FROM root_manifests WHERE tree_git_object_id=NEW.tree_git_object_id AND complete=1) BEGIN SELECT RAISE(ABORT,'Completed manifest is sealed'); END;

CREATE TRIGGER acquisition_cache_owner_insert BEFORE INSERT ON acquisition_progress WHEN NEW.active_cache_entry_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN active_cache_entries a ON a.active_cache_entry_id=NEW.active_cache_entry_id JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_id=l.repository_id AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Acquisition cache owner mismatch'); END;
CREATE TRIGGER obligation_cache_owner_insert BEFORE INSERT ON preservation_obligations WHEN NEW.cache_locator_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN cache_locators l ON l.cache_locator_id=NEW.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_id=l.repository_id AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Preservation cache owner mismatch'); END;

CREATE TRIGGER acquisition_cache_owner_update BEFORE UPDATE ON acquisition_progress WHEN NEW.active_cache_entry_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN active_cache_entries a ON a.active_cache_entry_id=NEW.active_cache_entry_id JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_id=l.repository_id AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Acquisition cache owner mismatch'); END;
CREATE TRIGGER obligation_cache_owner_update BEFORE UPDATE ON preservation_obligations WHEN NEW.cache_locator_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN cache_locators l ON l.cache_locator_id=NEW.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_id=l.repository_id AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Preservation cache owner mismatch'); END;

-- Natural-key documents, immutable observations and direct content identity.
CREATE TRIGGER documents_immutable BEFORE UPDATE ON documents WHEN NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_change_request_document_id IS NOT OLD.provider_change_request_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER documents_no_replace BEFORE INSERT ON documents WHEN EXISTS(SELECT 1 FROM documents WHERE (change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER documents_retain BEFORE DELETE ON documents BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER reviews_immutable BEFORE UPDATE ON reviews WHEN NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_change_request_document_id IS NOT OLD.provider_change_request_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER reviews_no_replace BEFORE INSERT ON reviews WHEN EXISTS(SELECT 1 FROM reviews WHERE (change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER reviews_retain BEFORE DELETE ON reviews BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER review_comments_immutable BEFORE UPDATE ON review_comments WHEN NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_change_request_document_id IS NOT OLD.provider_change_request_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER review_comments_no_replace BEFORE INSERT ON review_comments WHEN EXISTS(SELECT 1 FROM review_comments WHERE (change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER review_comments_retain BEFORE DELETE ON review_comments BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER collection_memberships_immutable BEFORE UPDATE ON collection_memberships WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_change_request_document_id IS NOT OLD.provider_change_request_document_id OR NEW.ordinal IS NOT OLD.ordinal BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER collection_memberships_no_replace BEFORE INSERT ON collection_memberships WHEN EXISTS(SELECT 1 FROM collection_memberships WHERE (fetch_collection_id=NEW.fetch_collection_id AND change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER collection_memberships_retain BEFORE DELETE ON collection_memberships BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER document_observations_immutable BEFORE UPDATE ON document_observations WHEN NEW.document_observation_id IS NOT OLD.document_observation_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_change_request_document_id IS NOT OLD.provider_change_request_document_id OR NEW.text_body_sha256 IS NOT OLD.text_body_sha256 OR NEW.observed_at_us IS NOT OLD.observed_at_us OR NEW.parsed_at_us IS NOT OLD.parsed_at_us OR NEW.origin_key IS NOT OLD.origin_key OR NEW.fetch_occurrence_id IS NOT OLD.fetch_occurrence_id OR NEW.metadata IS NOT OLD.metadata BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER document_observations_no_replace BEFORE INSERT ON document_observations WHEN EXISTS(SELECT 1 FROM document_observations WHERE (document_observation_id=NEW.document_observation_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER document_observations_retain BEFORE DELETE ON document_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX documents_current_observation_fk ON documents(current_document_observation_id,change_request_id,kind,provider_change_request_document_id);
CREATE INDEX document_observations_document_fk ON document_observations(change_request_id,kind,provider_change_request_document_id);
CREATE INDEX document_observations_origin_lookup ON document_observations(change_request_id,kind,provider_change_request_document_id,origin_key);
CREATE INDEX document_observations_body_fk ON document_observations(text_body_sha256);
CREATE INDEX document_observations_occurrence_fk ON document_observations(fetch_occurrence_id);
CREATE INDEX review_comments_thread_fk ON review_comments(change_request_id,review_thread_provider_resource_id);
CREATE INDEX collection_memberships_document_fk ON collection_memberships(change_request_id,kind,provider_change_request_document_id);
CREATE TRIGGER document_current_insert BEFORE INSERT ON documents WHEN NEW.current_document_observation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM document_observations o WHERE o.document_observation_id=NEW.current_document_observation_id AND o.change_request_id=NEW.change_request_id AND o.kind=NEW.kind AND o.provider_change_request_document_id=NEW.provider_change_request_document_id AND o.observed_at_us IS NOT NULL) BEGIN SELECT RAISE(ABORT,'Current document requires a same-document observed fact'); END;
CREATE TRIGGER membership_owner_insert BEFORE INSERT ON collection_memberships WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Membership must belong to same CR'); END;
CREATE TRIGGER document_origin_insert BEFORE INSERT ON document_observations WHEN NEW.fetch_occurrence_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE o.fetch_occurrence_id=NEW.fetch_occurrence_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Document occurrence belongs to another CR'); END;
CREATE TRIGGER document_current_update BEFORE UPDATE ON documents WHEN NEW.current_document_observation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM document_observations o WHERE o.document_observation_id=NEW.current_document_observation_id AND o.change_request_id=NEW.change_request_id AND o.kind=NEW.kind AND o.provider_change_request_document_id=NEW.provider_change_request_document_id AND o.observed_at_us IS NOT NULL) BEGIN SELECT RAISE(ABORT,'Current document requires a same-document observed fact'); END;
CREATE TRIGGER membership_owner_update BEFORE UPDATE ON collection_memberships WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Membership must belong to same CR'); END;
CREATE TRIGGER document_origin_update BEFORE UPDATE ON document_observations WHEN NEW.fetch_occurrence_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE o.fetch_occurrence_id=NEW.fetch_occurrence_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Document occurrence belongs to another CR'); END;
