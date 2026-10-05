-- Complete independent target DDL, P1; NOT an application migration.
-- SQLite >= 3.46.1; every target connection must enable foreign_keys and recursive_triggers.
PRAGMA foreign_keys=ON;
PRAGMA recursive_triggers=ON;
CREATE TABLE database_identity(
singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    format_id TEXT NOT NULL CHECK(format_id='repo-catalog/catalog3-p1'),
    schema_version INTEGER NOT NULL CHECK(schema_version=3),
    db_instance_id TEXT NOT NULL,
    publication_seq INTEGER NOT NULL CHECK(publication_seq>=0),
    ddl_sha256 BLOB NOT NULL CHECK(length(ddl_sha256)=32), lifecycle TEXT NOT NULL CHECK(lifecycle IN ('building','validated','rejected'))
) STRICT;
CREATE TABLE service_instances(
id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('github','gitlab','gitea','forgejo','gitolite','git','other')),
    name TEXT NOT NULL UNIQUE,
    web_base_url TEXT, api_base_url TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    created_at TEXT
) STRICT;
CREATE TABLE sources(
id TEXT PRIMARY KEY, instance_id TEXT REFERENCES service_instances(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    discovery_kind TEXT NOT NULL CHECK(discovery_kind IN ('manual_git','github_inventory')),
    name TEXT NOT NULL,
    settings TEXT NOT NULL CHECK(json_valid(settings) AND json_type(settings)='object')
) STRICT;
CREATE TABLE repositories(
id TEXT PRIMARY KEY, name TEXT NOT NULL,
    preferred_endpoint_id TEXT, current_snapshot_id TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    FOREIGN KEY(preferred_endpoint_id,id) REFERENCES repository_endpoints(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(current_snapshot_id,id) REFERENCES snapshots(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE repository_bindings(
id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    instance_id TEXT NOT NULL REFERENCES service_instances(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    provider_repo_id TEXT CHECK(provider_repo_id IS NULL OR length(provider_repo_id)>0),
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), created_at TEXT,
    UNIQUE(repo_id,instance_id), UNIQUE(instance_id,provider_repo_id), UNIQUE(id,repo_id)
) STRICT;
CREATE TABLE repository_endpoints(
id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    url TEXT NOT NULL CHECK(length(url)>0),
    transport TEXT NOT NULL CHECK(transport IN ('file','https','ssh','other')),
    label TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), created_at TEXT,
    UNIQUE(repo_id,url), UNIQUE(id,repo_id)
) STRICT;
CREATE TABLE git_acquisitions(
id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    endpoint_id TEXT, endpoint_url TEXT,
    object_format TEXT CHECK(object_format IN ('sha1','sha256')),
    refs_observed_at TEXT,
    source_id TEXT REFERENCES sources(id) ON UPDATE RESTRICT ON DELETE RESTRICT, kind TEXT NOT NULL CHECK(kind IN ('git','pr','legacy')), started_at TEXT, observed_at TEXT, request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'), roots_manifest TEXT CHECK(roots_manifest IS NULL OR (json_valid(roots_manifest) AND json_type(roots_manifest)='array')),
    UNIQUE(id,repo_id),
    FOREIGN KEY(endpoint_id,repo_id) REFERENCES repository_endpoints(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE snapshots(
id TEXT PRIMARY KEY, acquisition_id TEXT NOT NULL UNIQUE,
    repo_id TEXT NOT NULL, published INTEGER NOT NULL CHECK(published IN (0,1)),
    generation INTEGER NOT NULL CHECK(generation>=0), created_at TEXT,
    UNIQUE(id,repo_id),
    FOREIGN KEY(acquisition_id,repo_id) REFERENCES git_acquisitions(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE change_requests(
id TEXT PRIMARY KEY, repo_id TEXT NOT NULL, binding_id TEXT NOT NULL,
    request_kind TEXT NOT NULL CHECK(request_kind IN ('pull_request','merge_request')),
    number INTEGER NOT NULL CHECK(number>0), current_observation_id INTEGER,
    node_id TEXT,
    UNIQUE(binding_id,request_kind,number), UNIQUE(id,repo_id),
    FOREIGN KEY(binding_id,repo_id) REFERENCES repository_bindings(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(current_observation_id,id) REFERENCES change_request_observations(id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE change_request_observations(
id INTEGER PRIMARY KEY,
    change_request_id TEXT NOT NULL REFERENCES change_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    observed_at TEXT, published INTEGER NOT NULL CHECK(published IN (0,1)),
    payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'),
    origin_key TEXT, parsed_at TEXT NOT NULL, origin_occurrence_id INTEGER REFERENCES fetch_occurrences(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    UNIQUE(id,change_request_id)
) STRICT;
CREATE TABLE text_bodies(
id INTEGER PRIMARY KEY, body TEXT NOT NULL,
    byte_length INTEGER NOT NULL CHECK(byte_length>=0 AND byte_length=length(CAST(body AS BLOB))),
    sha256 BLOB NOT NULL CHECK(length(sha256)=32), UNIQUE(sha256,body)
) STRICT;
CREATE TABLE documents(
id TEXT PRIMARY KEY,
    change_request_id TEXT NOT NULL REFERENCES change_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    kind TEXT NOT NULL, provider_id TEXT NOT NULL, current_version_id INTEGER,
    deleted INTEGER NOT NULL CHECK(deleted IN (0,1)),
    node_id TEXT, author TEXT, url TEXT, metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    UNIQUE(id,change_request_id), UNIQUE(change_request_id,kind,provider_id),
    FOREIGN KEY(current_version_id,id) REFERENCES document_versions(id,document_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE document_versions(
id INTEGER PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    body_id INTEGER NOT NULL REFERENCES text_bodies(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    legacy_body_sha256 BLOB CHECK(legacy_body_sha256 IS NULL OR length(legacy_body_sha256)=32),
    UNIQUE(id,document_id)
) STRICT;
CREATE TABLE document_observations(
id INTEGER PRIMARY KEY, document_id TEXT NOT NULL, version_id INTEGER NOT NULL,
    observed_at TEXT, parsed_at TEXT NOT NULL,
    origin_key TEXT, occurrence_id INTEGER REFERENCES fetch_occurrences(id) ON UPDATE RESTRICT ON DELETE RESTRICT, metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    FOREIGN KEY(version_id,document_id) REFERENCES document_versions(id,document_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE review_threads(
id TEXT PRIMARY KEY,
    change_request_id TEXT NOT NULL REFERENCES change_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), observed_at TEXT,
    UNIQUE(id,change_request_id)
) STRICT;
CREATE TABLE review_comments(
document_id TEXT PRIMARY KEY, change_request_id TEXT NOT NULL, thread_id TEXT,
    payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'),
    FOREIGN KEY(document_id,change_request_id) REFERENCES documents(id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(thread_id,change_request_id) REFERENCES review_threads(id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE fetch_collections(
id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT, change_request_id TEXT,
    source_id TEXT REFERENCES sources(id) ON UPDATE RESTRICT ON DELETE RESTRICT, kind TEXT NOT NULL, scope_id TEXT NOT NULL REFERENCES resume_scopes(id) ON UPDATE RESTRICT ON DELETE RESTRICT, observed_at TEXT,
    UNIQUE(id,change_request_id),
    FOREIGN KEY(change_request_id,repo_id) REFERENCES change_requests(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE code_listings(
id TEXT PRIMARY KEY, change_request_id TEXT NOT NULL,
    collection_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('commits','files')),
    scope_id TEXT NOT NULL REFERENCES resume_scopes(id) ON UPDATE RESTRICT ON DELETE RESTRICT, object_format TEXT CHECK(object_format IN ('sha1','sha256')), head_oid BLOB, base_oid BLOB, CHECK((head_oid IS NULL AND base_oid IS NULL) OR (object_format IS NOT NULL AND object_format='sha1' AND (head_oid IS NULL OR length(head_oid)=20) AND (base_oid IS NULL OR length(base_oid)=20)) OR (object_format IS NOT NULL AND object_format='sha256' AND (head_oid IS NULL OR length(head_oid)=32) AND (base_oid IS NULL OR length(base_oid)=32))),
    UNIQUE(collection_id,kind), UNIQUE(id,change_request_id),
    FOREIGN KEY(collection_id,change_request_id) REFERENCES fetch_collections(id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE code_observations(
id INTEGER PRIMARY KEY, change_request_id TEXT NOT NULL, observation_id INTEGER NOT NULL,
    commit_listing_id TEXT, file_listing_id TEXT,
    state TEXT NOT NULL CHECK(state IN ('pending','partial','complete','unknown')),
    object_format TEXT CHECK(object_format IN ('sha1','sha256')), head_oid BLOB, base_oid BLOB, details TEXT NOT NULL CHECK(json_valid(details) AND json_type(details)='object'), CHECK((head_oid IS NULL AND base_oid IS NULL) OR (object_format IS NOT NULL AND object_format='sha1' AND (head_oid IS NULL OR length(head_oid)=20) AND (base_oid IS NULL OR length(base_oid)=20)) OR (object_format IS NOT NULL AND object_format='sha256' AND (head_oid IS NULL OR length(head_oid)=32) AND (base_oid IS NULL OR length(base_oid)=32))),
    CHECK(state!='complete' OR (commit_listing_id IS NOT NULL AND file_listing_id IS NOT NULL)),
    FOREIGN KEY(observation_id,change_request_id) REFERENCES change_request_observations(id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(commit_listing_id,change_request_id) REFERENCES code_listings(id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(file_listing_id,change_request_id) REFERENCES code_listings(id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE acquisition_roots(
id INTEGER PRIMARY KEY, acquisition_id TEXT NOT NULL REFERENCES git_acquisitions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
    oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)),
    role TEXT NOT NULL,
    repo_id TEXT NOT NULL, expected_oid BLOB, published INTEGER NOT NULL CHECK(published IN (0,1)), FOREIGN KEY(acquisition_id,repo_id) REFERENCES git_acquisitions(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT, CHECK(expected_oid IS NULL OR length(expected_oid)=length(oid)), UNIQUE(id,repo_id),
    UNIQUE(acquisition_id,object_format,oid,role)
) STRICT;
CREATE TABLE root_origins(
id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL REFERENCES acquisition_roots(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    origin_kind TEXT NOT NULL CHECK(origin_kind IN ('ref','pr_role','legacy_unknown')),
    raw_ref_name BLOB, source_ordinal INTEGER NOT NULL CHECK(source_ordinal>=0),
    snapshot_id TEXT, change_request_id TEXT, observation_id INTEGER, repo_id TEXT NOT NULL, FOREIGN KEY(root_id,repo_id) REFERENCES acquisition_roots(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(snapshot_id,repo_id) REFERENCES snapshots(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(change_request_id,repo_id) REFERENCES change_requests(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(observation_id,change_request_id) REFERENCES change_request_observations(id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT, CHECK((origin_kind='ref' AND snapshot_id IS NOT NULL AND change_request_id IS NULL AND observation_id IS NULL) OR (origin_kind='pr_role' AND snapshot_id IS NULL AND change_request_id IS NOT NULL AND observation_id IS NOT NULL) OR (origin_kind='legacy_unknown' AND snapshot_id IS NULL AND change_request_id IS NULL AND observation_id IS NULL)),
    UNIQUE(root_id,origin_kind,source_ordinal),
    CHECK(origin_kind!='ref' OR (raw_ref_name IS NOT NULL AND length(raw_ref_name)>0))
) STRICT;
CREATE TABLE job_attempts(
job_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>=1),
    state TEXT NOT NULL CHECK(state IN ('queued','running','waiting','complete','failed','interrupted','cancelled','unknown')),
    created_at TEXT, updated_at TEXT, not_before REAL CHECK(not_before IS NULL OR (not_before>=0 AND not_before<1.0e308)), checkpoint TEXT NOT NULL CHECK(json_valid(checkpoint) AND json_type(checkpoint)='object'), reason TEXT, FOREIGN KEY(job_id) REFERENCES jobs(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    PRIMARY KEY(job_id,attempt)
) STRICT;
CREATE TABLE conversion_sources(
id TEXT PRIMARY KEY, source_sha256 BLOB NOT NULL CHECK(length(source_sha256)=32), schema_sha256 BLOB NOT NULL CHECK(length(schema_sha256)=32), format_id TEXT NOT NULL, source_db_instance_id TEXT NOT NULL, source_catalog BLOB NOT NULL, source_migrations BLOB NOT NULL
) STRICT;
CREATE TABLE conversion_runs(
id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES conversion_sources(id) ON UPDATE RESTRICT ON DELETE RESTRICT, started_at TEXT NOT NULL, ended_at TEXT, parser_version TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('building','paused','validated','rejected')), manifest TEXT NOT NULL CHECK(json_valid(manifest) AND json_type(manifest)='object')
) STRICT;
CREATE TABLE conversion_batches(
id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES conversion_runs(id) ON UPDATE RESTRICT ON DELETE RESTRICT, source_table TEXT NOT NULL, input_sha256 BLOB NOT NULL CHECK(length(input_sha256)=32), committed_at TEXT NOT NULL, output_manifest TEXT NOT NULL CHECK(json_valid(output_manifest) AND json_type(output_manifest)='object')
) STRICT;
CREATE TABLE legacy_records(
id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES conversion_sources(id) ON UPDATE RESTRICT ON DELETE RESTRICT, source_table TEXT NOT NULL, source_key BLOB NOT NULL, row_sha256 BLOB NOT NULL CHECK(length(row_sha256)=32), UNIQUE(source_id,source_table,source_key)
) STRICT;
CREATE TABLE legacy_values(
record_id INTEGER NOT NULL REFERENCES legacy_records(id) ON UPDATE RESTRICT ON DELETE RESTRICT, column_name TEXT NOT NULL, storage_type TEXT NOT NULL CHECK(storage_type IN ('null','integer','real','text','blob')), value_bytes BLOB NOT NULL, PRIMARY KEY(record_id,column_name), CHECK(storage_type!='null' OR length(value_bytes)=0)
) STRICT;
CREATE TABLE id_mappings(
id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL REFERENCES legacy_records(id) ON UPDATE RESTRICT ON DELETE RESTRICT, target_table TEXT NOT NULL, target_key BLOB NOT NULL, relation TEXT NOT NULL CHECK(relation IN ('identity','split','merge','derived','archive')), reason TEXT NOT NULL
) STRICT;
CREATE TABLE validation_results(
id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES conversion_runs(id) ON UPDATE RESTRICT ON DELETE RESTRICT, invariant_id TEXT NOT NULL, code TEXT NOT NULL, severity TEXT NOT NULL CHECK(severity IN ('blocking','partial','info')), observed_at TEXT NOT NULL, details TEXT NOT NULL CHECK(json_valid(details) AND json_type(details)='object')
) STRICT;
CREATE TABLE source_repositories(
source_id TEXT NOT NULL REFERENCES sources(id) ON UPDATE RESTRICT ON DELETE RESTRICT, repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT, first_seen TEXT, last_seen TEXT, PRIMARY KEY(source_id,repo_id),
    CHECK(first_seen IS NULL OR julianday(first_seen) IS NOT NULL),
    CHECK(last_seen IS NULL OR julianday(last_seen) IS NOT NULL),
    CHECK(first_seen IS NULL OR last_seen IS NULL OR julianday(first_seen)<=julianday(last_seen))
) STRICT;
CREATE TABLE repository_name_assertions(
repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT, name TEXT NOT NULL, observed_at TEXT, PRIMARY KEY(repo_id,name)
) STRICT;
CREATE TABLE inventory_observations(
id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id) ON UPDATE RESTRICT ON DELETE RESTRICT, asserted_state TEXT NOT NULL CHECK(asserted_state IN ('complete','partial','unknown')), scope TEXT NOT NULL CHECK(json_valid(scope) AND json_type(scope)='object'), observed_at TEXT, reason TEXT
) STRICT;
CREATE TABLE jobs(
id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('discover','sync','hydrate','index','legacy')), request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'), current_attempt INTEGER, created_at TEXT, FOREIGN KEY(id,current_attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE acquisition_progress(
acquisition_id TEXT PRIMARY KEY REFERENCES git_acquisitions(id) ON UPDATE RESTRICT ON DELETE RESTRICT, job_id TEXT NOT NULL, attempt INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('planned','fetching','refs_captured','published','failed','interrupted','unknown')), generation INTEGER NOT NULL CHECK(generation>=0), ended_at TEXT, FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE collection_progress(
collection_id TEXT PRIMARY KEY REFERENCES fetch_collections(id) ON UPDATE RESTRICT ON DELETE RESTRICT, job_id TEXT NOT NULL, attempt INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('running','partial','complete','failed','interrupted','unknown')), cursor TEXT, reason TEXT, FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE resume_scopes(
id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT, binding_id TEXT, source_id TEXT REFERENCES sources(id) ON UPDATE RESTRICT ON DELETE RESTRICT, principal_ref TEXT, api_version TEXT, endpoint TEXT, request_context TEXT NOT NULL CHECK(json_valid(request_context) AND json_type(request_context)='object'), parser_version TEXT NOT NULL, profile_version TEXT NOT NULL, confidence TEXT NOT NULL CHECK(confidence IN ('proven','legacy_unknown')), UNIQUE(id,repo_id), FOREIGN KEY(binding_id,repo_id) REFERENCES repository_bindings(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE payloads(
id INTEGER PRIMARY KEY, sha256 BLOB NOT NULL CHECK(length(sha256)=32), body BLOB NOT NULL, byte_length INTEGER NOT NULL CHECK(byte_length=length(body)), representation TEXT NOT NULL CHECK(representation IN ('decoded_api','legacy_normalized'))
) STRICT;
CREATE TABLE fetch_occurrences(
id INTEGER PRIMARY KEY, collection_id TEXT NOT NULL REFERENCES fetch_collections(id) ON UPDATE RESTRICT ON DELETE RESTRICT, ordinal INTEGER NOT NULL CHECK(ordinal>=0), payload_id INTEGER NOT NULL REFERENCES payloads(id) ON UPDATE RESTRICT ON DELETE RESTRICT, request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'), next_cursor TEXT, observed_at TEXT, parsed_at TEXT NOT NULL, UNIQUE(id,collection_id)
) STRICT;
CREATE TABLE collection_memberships(
collection_id TEXT NOT NULL REFERENCES fetch_collections(id) ON UPDATE RESTRICT ON DELETE RESTRICT, document_id TEXT NOT NULL REFERENCES documents(id) ON UPDATE RESTRICT ON DELETE RESTRICT, ordinal INTEGER NOT NULL CHECK(ordinal>=0), PRIMARY KEY(collection_id,document_id)
) STRICT;
CREATE TABLE unresolved_payloads(
id INTEGER PRIMARY KEY, payload_id INTEGER REFERENCES payloads(id) ON UPDATE RESTRICT ON DELETE RESTRICT, legacy_record_id INTEGER REFERENCES legacy_records(id) ON UPDATE RESTRICT ON DELETE RESTRICT, reason TEXT NOT NULL, CHECK(payload_id IS NOT NULL OR legacy_record_id IS NOT NULL)
) STRICT;
CREATE TABLE validators(
scope_id TEXT NOT NULL REFERENCES resume_scopes(id) ON UPDATE RESTRICT ON DELETE RESTRICT, validator_key TEXT NOT NULL, etag TEXT NOT NULL, payload_id INTEGER NOT NULL REFERENCES payloads(id) ON UPDATE RESTRICT ON DELETE RESTRICT, validated_at TEXT, PRIMARY KEY(scope_id,validator_key)
) STRICT;
CREATE TABLE incremental_scans(
id TEXT PRIMARY KEY, scope_id TEXT NOT NULL REFERENCES resume_scopes(id) ON UPDATE RESTRICT ON DELETE RESTRICT, collection_id TEXT NOT NULL REFERENCES fetch_collections(id) ON UPDATE RESTRICT ON DELETE RESTRICT, scan_started_at TEXT, safe_watermark TEXT, evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object'), UNIQUE(id,scope_id)
) STRICT;
CREATE TABLE resume_cursors(
scope_id TEXT PRIMARY KEY REFERENCES resume_scopes(id) ON UPDATE RESTRICT ON DELETE RESTRICT, scan_id TEXT, next_cursor TEXT, reusable INTEGER NOT NULL CHECK(reusable IN (0,1)), FOREIGN KEY(scan_id,scope_id) REFERENCES incremental_scans(id,scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE completion_markers(
id INTEGER PRIMARY KEY, scope_id TEXT NOT NULL REFERENCES resume_scopes(id) ON UPDATE RESTRICT ON DELETE RESTRICT, collection_id TEXT NOT NULL REFERENCES fetch_collections(id) ON UPDATE RESTRICT ON DELETE RESTRICT, asserted_state TEXT NOT NULL CHECK(asserted_state IN ('complete','partial','unknown')), evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object'), observed_at TEXT
) STRICT;
CREATE TABLE coverage_scopes(
id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT, change_request_id TEXT, kind TEXT NOT NULL, current_claim_id INTEGER, FOREIGN KEY(change_request_id,repo_id) REFERENCES change_requests(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(current_claim_id,id) REFERENCES coverage_claims(id,scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE coverage_claims(
id INTEGER PRIMARY KEY, scope_id TEXT NOT NULL REFERENCES coverage_scopes(id) ON UPDATE RESTRICT ON DELETE RESTRICT, asserted_state TEXT NOT NULL CHECK(asserted_state IN ('complete','partial','unknown','not_applicable')), effective_state TEXT NOT NULL CHECK(effective_state IN ('complete','partial','unknown','not_applicable')), details TEXT NOT NULL CHECK(json_valid(details) AND json_type(details)='object'), observed_at TEXT, evaluated_at TEXT NOT NULL, UNIQUE(id,scope_id)
) STRICT;
CREATE TABLE reviews(
id TEXT PRIMARY KEY, change_request_id TEXT NOT NULL, document_id TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), FOREIGN KEY(document_id,change_request_id) REFERENCES documents(id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE change_request_events(
id INTEGER PRIMARY KEY, change_request_id TEXT NOT NULL REFERENCES change_requests(id) ON UPDATE RESTRICT ON DELETE RESTRICT, origin_key TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal>=0), provider_id TEXT, payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), observed_at TEXT
) STRICT;
CREATE TABLE code_listing_progress(
listing_id TEXT PRIMARY KEY REFERENCES code_listings(id) ON UPDATE RESTRICT ON DELETE RESTRICT, state TEXT NOT NULL CHECK(state IN ('partial','complete','unknown')), terminal INTEGER NOT NULL CHECK(terminal IN (0,1)), page_count INTEGER NOT NULL CHECK(page_count>=0), context_proven INTEGER NOT NULL CHECK(context_proven IN (0,1)), CHECK(state!='complete' OR (terminal=1 AND context_proven=1))
) STRICT;
CREATE TABLE code_commits(
listing_id TEXT NOT NULL REFERENCES code_listings(id) ON UPDATE RESTRICT ON DELETE RESTRICT, occurrence_id INTEGER NOT NULL REFERENCES fetch_occurrences(id) ON UPDATE RESTRICT ON DELETE RESTRICT, position INTEGER NOT NULL CHECK(position>=0), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), PRIMARY KEY(listing_id,occurrence_id,position)
) STRICT;
CREATE TABLE code_file_changes(
listing_id TEXT NOT NULL REFERENCES code_listings(id) ON UPDATE RESTRICT ON DELETE RESTRICT, occurrence_id INTEGER NOT NULL REFERENCES fetch_occurrences(id) ON UPDATE RESTRICT ON DELETE RESTRICT, position INTEGER NOT NULL CHECK(position>=0), raw_path BLOB NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'), PRIMARY KEY(listing_id,occurrence_id,position)
) STRICT;
CREATE TABLE code_acquisitions(
code_observation_id INTEGER NOT NULL REFERENCES code_observations(id) ON UPDATE RESTRICT ON DELETE RESTRICT, role TEXT NOT NULL CHECK(role IN ('head','base','merge')), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), root_id INTEGER REFERENCES acquisition_roots(id) ON UPDATE RESTRICT ON DELETE RESTRICT, PRIMARY KEY(code_observation_id,role)
) STRICT;
CREATE TABLE reanalysis_runs(
id TEXT PRIMARY KEY, conversion_run_id TEXT REFERENCES conversion_runs(id) ON UPDATE RESTRICT ON DELETE RESTRICT, parser_version TEXT NOT NULL, parsed_at TEXT NOT NULL, evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object')
) STRICT;
CREATE TABLE git_objects(
id INTEGER PRIMARY KEY, object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), type TEXT NOT NULL CHECK(type IN ('commit','tree','blob','tag')), size INTEGER NOT NULL CHECK(size>=0), verified INTEGER NOT NULL CHECK(verified IN (0,1)), UNIQUE(object_format,oid)
) STRICT;
CREATE TABLE commits(
object_id INTEGER PRIMARY KEY REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, tree_id INTEGER NOT NULL REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_headers BLOB NOT NULL, raw_message BLOB NOT NULL, metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object')
) STRICT;
CREATE TABLE commit_parents(
commit_id INTEGER NOT NULL REFERENCES commits(object_id) ON UPDATE RESTRICT ON DELETE RESTRICT, parent_ordinal INTEGER NOT NULL CHECK(parent_ordinal>=0), parent_id INTEGER NOT NULL REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, PRIMARY KEY(commit_id,parent_ordinal)
) STRICT;
CREATE TABLE tree_entries(
tree_id INTEGER NOT NULL REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_name BLOB NOT NULL CHECK(length(raw_name)>0), mode INTEGER NOT NULL CHECK(mode IN (16384,33188,33261,40960,57344)), child_format TEXT NOT NULL CHECK(child_format IN ('sha1','sha256')), child_oid BLOB NOT NULL CHECK((child_format='sha1' AND length(child_oid)=20) OR (child_format='sha256' AND length(child_oid)=32)), child_id INTEGER REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, PRIMARY KEY(tree_id,raw_name), CHECK((mode=57344 AND child_id IS NULL) OR (mode!=57344 AND child_id IS NOT NULL))
) STRICT;
CREATE TABLE tag_objects(
object_id INTEGER PRIMARY KEY REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, target_id INTEGER NOT NULL REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_payload BLOB NOT NULL
) STRICT;
CREATE TABLE contents(
id INTEGER PRIMARY KEY, byte_length INTEGER NOT NULL CHECK(byte_length>=0), raw_text TEXT, text_state TEXT NOT NULL CHECK(text_state IN ('eligible','nul','non_utf8','oversize','unknown')), created_at TEXT, CHECK(raw_text IS NULL OR length(CAST(raw_text AS BLOB))=byte_length)
) STRICT;
CREATE TABLE content_digests(
content_id INTEGER NOT NULL REFERENCES contents(id) ON UPDATE RESTRICT ON DELETE RESTRICT, representation TEXT NOT NULL CHECK(representation='raw-content-v1'), algorithm TEXT NOT NULL CHECK(algorithm IN ('md5','sha1','sha256')), digest BLOB NOT NULL CHECK((algorithm='md5' AND length(digest)=16) OR (algorithm='sha1' AND length(digest)=20) OR (algorithm='sha256' AND length(digest)=32)), verified_at TEXT, pipeline_version TEXT NOT NULL, PRIMARY KEY(content_id,representation,algorithm)
) STRICT;
CREATE TABLE blob_content_map(
object_id INTEGER PRIMARY KEY REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, content_id INTEGER NOT NULL REFERENCES contents(id) ON UPDATE RESTRICT ON DELETE RESTRICT, acquisition_id TEXT NOT NULL REFERENCES git_acquisitions(id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE repository_object_sources(
repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT, object_id INTEGER NOT NULL REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, acquisition_id TEXT NOT NULL, PRIMARY KEY(repo_id,object_id,acquisition_id), FOREIGN KEY(acquisition_id,repo_id) REFERENCES git_acquisitions(id,repo_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE ref_observations(
snapshot_id TEXT NOT NULL REFERENCES snapshots(id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_ref_name BLOB NOT NULL CHECK(length(raw_ref_name)>0), kind TEXT NOT NULL CHECK(kind IN ('head','tag','other')), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), target_oid BLOB NOT NULL CHECK((object_format='sha1' AND length(target_oid)=20) OR (object_format='sha256' AND length(target_oid)=32)), peeled_oid BLOB, target_type TEXT CHECK(target_type IN ('commit','tree','blob','tag')), PRIMARY KEY(snapshot_id,raw_ref_name), CHECK(peeled_oid IS NULL OR length(peeled_oid)=length(target_oid))
) STRICT;
CREATE TABLE root_manifests(
tree_id INTEGER PRIMARY KEY REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, complete INTEGER NOT NULL CHECK(complete IN (0,1))
) STRICT;
CREATE TABLE root_manifest_entries(
tree_id INTEGER NOT NULL REFERENCES root_manifests(tree_id) ON UPDATE RESTRICT ON DELETE RESTRICT, raw_path BLOB NOT NULL, mode INTEGER NOT NULL CHECK(mode IN (33188,33261,40960,57344)), object_id INTEGER REFERENCES git_objects(id) ON UPDATE RESTRICT ON DELETE RESTRICT, object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')), oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)), PRIMARY KEY(tree_id,raw_path), CHECK((mode=57344 AND object_id IS NULL) OR (mode!=57344 AND object_id IS NOT NULL))
) STRICT;
CREATE TABLE cache_locators(
id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id) ON UPDATE RESTRICT ON DELETE RESTRICT, path TEXT NOT NULL, access TEXT NOT NULL CHECK(access IN ('source_readonly','target_active')), state TEXT NOT NULL CHECK(state IN ('available','missing','unknown')), UNIQUE(id,repo_id)
) STRICT;
CREATE TABLE content_locations(
content_id INTEGER NOT NULL REFERENCES contents(id) ON UPDATE RESTRICT ON DELETE RESTRICT, kind TEXT NOT NULL CHECK(kind IN ('durable-content','cache','legacy')), locator TEXT NOT NULL, cache_id TEXT REFERENCES cache_locators(id) ON UPDATE RESTRICT ON DELETE RESTRICT, state TEXT NOT NULL CHECK(state IN ('available','unavailable','unknown')), PRIMARY KEY(content_id,kind,locator)
) STRICT;
CREATE TABLE active_cache_entries(
id TEXT PRIMARY KEY, locator_id TEXT NOT NULL REFERENCES cache_locators(id) ON UPDATE RESTRICT ON DELETE RESTRICT, generation INTEGER NOT NULL CHECK(generation>=0), state TEXT NOT NULL CHECK(state IN ('active','evicting','evicted')), last_used REAL NOT NULL CHECK(last_used>=0 AND last_used<1.0e308), bytes INTEGER NOT NULL CHECK(bytes>=0)
) STRICT;
CREATE TABLE cache_leases(
cache_id TEXT NOT NULL REFERENCES active_cache_entries(id) ON UPDATE RESTRICT ON DELETE RESTRICT, job_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>=1), acquired_at TEXT NOT NULL, PRIMARY KEY(cache_id,job_id,attempt), FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE space_reservations(
job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON UPDATE RESTRICT ON DELETE RESTRICT, reserved INTEGER NOT NULL CHECK(reserved>=0), consumed INTEGER NOT NULL CHECK(consumed>=0)
) STRICT;
CREATE TABLE preservation_obligations(
acquisition_id TEXT PRIMARY KEY REFERENCES git_acquisitions(id) ON UPDATE RESTRICT ON DELETE RESTRICT, cache_id TEXT REFERENCES cache_locators(id) ON UPDATE RESTRICT ON DELETE RESTRICT, roots_fixed INTEGER NOT NULL CHECK(roots_fixed IN (0,1)), structure_done INTEGER NOT NULL CHECK(structure_done IN (0,1)), digest_done INTEGER NOT NULL CHECK(digest_done IN (0,1)), text_done INTEGER NOT NULL CHECK(text_done IN (0,1)), published INTEGER NOT NULL CHECK(published IN (0,1))
) STRICT;
CREATE TABLE search_documents(
id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('code','pr','commits')), source_key TEXT NOT NULL, body TEXT NOT NULL, metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), UNIQUE(kind,source_key)
) STRICT;
CREATE TABLE index_generations(
id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('code','pr','commits')), state TEXT NOT NULL CHECK(state IN ('building','ready','retired','removed','unavailable','failed')), table_name TEXT NOT NULL CHECK(length(table_name)>0 AND table_name NOT GLOB '*[^a-z0-9_]*'), target_max_id INTEGER NOT NULL CHECK(target_max_id>=0), created_at TEXT
) STRICT;
CREATE TABLE index_membership(
generation_id INTEGER NOT NULL REFERENCES index_generations(id) ON UPDATE RESTRICT ON DELETE RESTRICT, document_id INTEGER NOT NULL REFERENCES search_documents(id) ON UPDATE RESTRICT ON DELETE RESTRICT, input_version TEXT NOT NULL, PRIMARY KEY(generation_id,document_id)
) STRICT;
CREATE TRIGGER acquisition_progress_immutable BEFORE UPDATE ON acquisition_progress WHEN NEW.acquisition_id IS NOT OLD.acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER acquisition_progress_no_replace BEFORE INSERT ON acquisition_progress WHEN EXISTS(SELECT 1 FROM acquisition_progress WHERE (acquisition_id=NEW.acquisition_id) OR (acquisition_id=NEW.acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX acquisition_progress_fk_0 ON acquisition_progress(job_id,attempt);
CREATE TRIGGER acquisition_roots_immutable BEFORE UPDATE ON acquisition_roots WHEN NEW.id IS NOT OLD.id OR NEW.acquisition_id IS NOT OLD.acquisition_id OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.role IS NOT OLD.role OR NEW.repo_id IS NOT OLD.repo_id OR NEW.expected_oid IS NOT OLD.expected_oid OR (OLD.published=1 AND NEW.published!=1) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER acquisition_roots_no_replace BEFORE INSERT ON acquisition_roots WHEN EXISTS(SELECT 1 FROM acquisition_roots WHERE (id=NEW.id) OR (acquisition_id=NEW.acquisition_id AND object_format=NEW.object_format AND oid=NEW.oid AND role=NEW.role) OR (id=NEW.id AND repo_id=NEW.repo_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER acquisition_roots_retain BEFORE DELETE ON acquisition_roots BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX acquisition_roots_fk_0 ON acquisition_roots(acquisition_id,repo_id);
CREATE TRIGGER active_cache_entries_immutable BEFORE UPDATE ON active_cache_entries WHEN NEW.id IS NOT OLD.id OR NEW.locator_id IS NOT OLD.locator_id OR NEW.generation IS NOT OLD.generation BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER active_cache_entries_no_replace BEFORE INSERT ON active_cache_entries WHEN EXISTS(SELECT 1 FROM active_cache_entries WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX active_cache_entries_fk_0 ON active_cache_entries(locator_id);
CREATE TRIGGER blob_content_map_immutable BEFORE UPDATE ON blob_content_map WHEN NEW.object_id IS NOT OLD.object_id OR NEW.content_id IS NOT OLD.content_id OR NEW.acquisition_id IS NOT OLD.acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER blob_content_map_no_replace BEFORE INSERT ON blob_content_map WHEN EXISTS(SELECT 1 FROM blob_content_map WHERE (object_id=NEW.object_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER blob_content_map_retain BEFORE DELETE ON blob_content_map BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX blob_content_map_fk_0 ON blob_content_map(acquisition_id);
CREATE INDEX blob_content_map_fk_1 ON blob_content_map(content_id);
CREATE TRIGGER cache_leases_immutable BEFORE UPDATE ON cache_leases WHEN NEW.cache_id IS NOT OLD.cache_id OR NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER cache_leases_no_replace BEFORE INSERT ON cache_leases WHEN EXISTS(SELECT 1 FROM cache_leases WHERE (cache_id=NEW.cache_id AND job_id=NEW.job_id AND attempt=NEW.attempt) OR (cache_id=NEW.cache_id AND job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX cache_leases_fk_0 ON cache_leases(job_id,attempt);
CREATE TRIGGER cache_locators_immutable BEFORE UPDATE ON cache_locators WHEN NEW.id IS NOT OLD.id OR NEW.repo_id IS NOT OLD.repo_id OR NEW.access IS NOT OLD.access BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER cache_locators_no_replace BEFORE INSERT ON cache_locators WHEN EXISTS(SELECT 1 FROM cache_locators WHERE (id=NEW.id) OR (id=NEW.id AND repo_id=NEW.repo_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX cache_locators_fk_0 ON cache_locators(repo_id);
CREATE TRIGGER change_request_events_immutable BEFORE UPDATE ON change_request_events WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.origin_key IS NOT OLD.origin_key OR NEW.ordinal IS NOT OLD.ordinal OR NEW.provider_id IS NOT OLD.provider_id OR NEW.payload IS NOT OLD.payload OR NEW.observed_at IS NOT OLD.observed_at BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER change_request_events_no_replace BEFORE INSERT ON change_request_events WHEN EXISTS(SELECT 1 FROM change_request_events WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER change_request_events_retain BEFORE DELETE ON change_request_events BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX change_request_events_fk_0 ON change_request_events(change_request_id);
CREATE TRIGGER change_request_observations_immutable BEFORE UPDATE ON change_request_observations WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.observed_at IS NOT OLD.observed_at OR NEW.payload IS NOT OLD.payload OR NEW.origin_key IS NOT OLD.origin_key OR NEW.parsed_at IS NOT OLD.parsed_at OR NEW.origin_occurrence_id IS NOT OLD.origin_occurrence_id OR (OLD.published=1 AND NEW.published!=1) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER change_request_observations_no_replace BEFORE INSERT ON change_request_observations WHEN EXISTS(SELECT 1 FROM change_request_observations WHERE (id=NEW.id) OR (id=NEW.id AND change_request_id=NEW.change_request_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER change_request_observations_retain BEFORE DELETE ON change_request_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX change_request_observations_fk_0 ON change_request_observations(origin_occurrence_id);
CREATE INDEX change_request_observations_fk_1 ON change_request_observations(change_request_id);
CREATE TRIGGER change_requests_immutable BEFORE UPDATE ON change_requests WHEN NEW.id IS NOT OLD.id OR NEW.repo_id IS NOT OLD.repo_id OR NEW.binding_id IS NOT OLD.binding_id OR NEW.request_kind IS NOT OLD.request_kind OR NEW.number IS NOT OLD.number BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER change_requests_no_replace BEFORE INSERT ON change_requests WHEN EXISTS(SELECT 1 FROM change_requests WHERE (id=NEW.id) OR (id=NEW.id AND repo_id=NEW.repo_id) OR (binding_id=NEW.binding_id AND request_kind=NEW.request_kind AND number=NEW.number) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX change_requests_fk_0 ON change_requests(current_observation_id,id);
CREATE INDEX change_requests_fk_1 ON change_requests(binding_id,repo_id);
CREATE TRIGGER code_acquisitions_immutable BEFORE UPDATE ON code_acquisitions WHEN NEW.code_observation_id IS NOT OLD.code_observation_id OR NEW.role IS NOT OLD.role OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.root_id IS NOT OLD.root_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_acquisitions_no_replace BEFORE INSERT ON code_acquisitions WHEN EXISTS(SELECT 1 FROM code_acquisitions WHERE (code_observation_id=NEW.code_observation_id AND role=NEW.role) OR (code_observation_id=NEW.code_observation_id AND role=NEW.role)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_acquisitions_retain BEFORE DELETE ON code_acquisitions BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_acquisitions_fk_0 ON code_acquisitions(root_id);
CREATE TRIGGER code_commits_immutable BEFORE UPDATE ON code_commits WHEN NEW.listing_id IS NOT OLD.listing_id OR NEW.occurrence_id IS NOT OLD.occurrence_id OR NEW.position IS NOT OLD.position OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.payload IS NOT OLD.payload BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_commits_no_replace BEFORE INSERT ON code_commits WHEN EXISTS(SELECT 1 FROM code_commits WHERE (listing_id=NEW.listing_id AND occurrence_id=NEW.occurrence_id AND position=NEW.position) OR (listing_id=NEW.listing_id AND occurrence_id=NEW.occurrence_id AND position=NEW.position)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_commits_retain BEFORE DELETE ON code_commits BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_commits_fk_0 ON code_commits(occurrence_id);
CREATE TRIGGER code_file_changes_immutable BEFORE UPDATE ON code_file_changes WHEN NEW.listing_id IS NOT OLD.listing_id OR NEW.occurrence_id IS NOT OLD.occurrence_id OR NEW.position IS NOT OLD.position OR NEW.raw_path IS NOT OLD.raw_path OR NEW.payload IS NOT OLD.payload BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_file_changes_no_replace BEFORE INSERT ON code_file_changes WHEN EXISTS(SELECT 1 FROM code_file_changes WHERE (listing_id=NEW.listing_id AND occurrence_id=NEW.occurrence_id AND position=NEW.position) OR (listing_id=NEW.listing_id AND occurrence_id=NEW.occurrence_id AND position=NEW.position)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_file_changes_retain BEFORE DELETE ON code_file_changes BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_file_changes_fk_0 ON code_file_changes(occurrence_id);
CREATE TRIGGER code_listing_progress_immutable BEFORE UPDATE ON code_listing_progress WHEN NEW.listing_id IS NOT OLD.listing_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_listing_progress_no_replace BEFORE INSERT ON code_listing_progress WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE (listing_id=NEW.listing_id) OR (listing_id=NEW.listing_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_listings_immutable BEFORE UPDATE ON code_listings WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.collection_id IS NOT OLD.collection_id OR NEW.kind IS NOT OLD.kind OR NEW.scope_id IS NOT OLD.scope_id OR NEW.object_format IS NOT OLD.object_format OR NEW.head_oid IS NOT OLD.head_oid OR NEW.base_oid IS NOT OLD.base_oid BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_listings_no_replace BEFORE INSERT ON code_listings WHEN EXISTS(SELECT 1 FROM code_listings WHERE (id=NEW.id) OR (id=NEW.id AND change_request_id=NEW.change_request_id) OR (collection_id=NEW.collection_id AND kind=NEW.kind) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_listings_retain BEFORE DELETE ON code_listings BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_listings_fk_0 ON code_listings(collection_id,change_request_id);
CREATE INDEX code_listings_fk_1 ON code_listings(scope_id);
CREATE TRIGGER code_observations_immutable BEFORE UPDATE ON code_observations WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.observation_id IS NOT OLD.observation_id OR NEW.commit_listing_id IS NOT OLD.commit_listing_id OR NEW.file_listing_id IS NOT OLD.file_listing_id OR NEW.state IS NOT OLD.state OR NEW.object_format IS NOT OLD.object_format OR NEW.head_oid IS NOT OLD.head_oid OR NEW.base_oid IS NOT OLD.base_oid OR NEW.details IS NOT OLD.details BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER code_observations_no_replace BEFORE INSERT ON code_observations WHEN EXISTS(SELECT 1 FROM code_observations WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_observations_retain BEFORE DELETE ON code_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_observations_fk_0 ON code_observations(file_listing_id,change_request_id);
CREATE INDEX code_observations_fk_1 ON code_observations(commit_listing_id,change_request_id);
CREATE INDEX code_observations_fk_2 ON code_observations(observation_id,change_request_id);
CREATE TRIGGER collection_memberships_immutable BEFORE UPDATE ON collection_memberships WHEN NEW.collection_id IS NOT OLD.collection_id OR NEW.document_id IS NOT OLD.document_id OR NEW.ordinal IS NOT OLD.ordinal BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER collection_memberships_no_replace BEFORE INSERT ON collection_memberships WHEN EXISTS(SELECT 1 FROM collection_memberships WHERE (collection_id=NEW.collection_id AND document_id=NEW.document_id) OR (collection_id=NEW.collection_id AND document_id=NEW.document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER collection_memberships_retain BEFORE DELETE ON collection_memberships BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX collection_memberships_fk_0 ON collection_memberships(document_id);
CREATE TRIGGER collection_progress_immutable BEFORE UPDATE ON collection_progress WHEN NEW.collection_id IS NOT OLD.collection_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER collection_progress_no_replace BEFORE INSERT ON collection_progress WHEN EXISTS(SELECT 1 FROM collection_progress WHERE (collection_id=NEW.collection_id) OR (collection_id=NEW.collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX collection_progress_fk_0 ON collection_progress(job_id,attempt);
CREATE TRIGGER commit_parents_immutable BEFORE UPDATE ON commit_parents WHEN NEW.commit_id IS NOT OLD.commit_id OR NEW.parent_ordinal IS NOT OLD.parent_ordinal OR NEW.parent_id IS NOT OLD.parent_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER commit_parents_no_replace BEFORE INSERT ON commit_parents WHEN EXISTS(SELECT 1 FROM commit_parents WHERE (commit_id=NEW.commit_id AND parent_ordinal=NEW.parent_ordinal) OR (commit_id=NEW.commit_id AND parent_ordinal=NEW.parent_ordinal)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER commit_parents_retain BEFORE DELETE ON commit_parents BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX commit_parents_fk_0 ON commit_parents(parent_id);
CREATE TRIGGER commits_immutable BEFORE UPDATE ON commits WHEN NEW.object_id IS NOT OLD.object_id OR NEW.tree_id IS NOT OLD.tree_id OR NEW.raw_headers IS NOT OLD.raw_headers OR NEW.raw_message IS NOT OLD.raw_message OR NEW.metadata IS NOT OLD.metadata BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER commits_no_replace BEFORE INSERT ON commits WHEN EXISTS(SELECT 1 FROM commits WHERE (object_id=NEW.object_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER commits_retain BEFORE DELETE ON commits BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX commits_fk_0 ON commits(tree_id);
CREATE TRIGGER completion_markers_immutable BEFORE UPDATE ON completion_markers WHEN NEW.id IS NOT OLD.id OR NEW.scope_id IS NOT OLD.scope_id OR NEW.collection_id IS NOT OLD.collection_id OR NEW.asserted_state IS NOT OLD.asserted_state OR NEW.evidence IS NOT OLD.evidence OR NEW.observed_at IS NOT OLD.observed_at BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER completion_markers_no_replace BEFORE INSERT ON completion_markers WHEN EXISTS(SELECT 1 FROM completion_markers WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER completion_markers_retain BEFORE DELETE ON completion_markers BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX completion_markers_fk_0 ON completion_markers(collection_id);
CREATE INDEX completion_markers_fk_1 ON completion_markers(scope_id);
CREATE TRIGGER content_digests_immutable BEFORE UPDATE ON content_digests WHEN NEW.content_id IS NOT OLD.content_id OR NEW.representation IS NOT OLD.representation OR NEW.algorithm IS NOT OLD.algorithm OR NEW.digest IS NOT OLD.digest OR NEW.verified_at IS NOT OLD.verified_at OR NEW.pipeline_version IS NOT OLD.pipeline_version BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER content_digests_no_replace BEFORE INSERT ON content_digests WHEN EXISTS(SELECT 1 FROM content_digests WHERE (content_id=NEW.content_id AND representation=NEW.representation AND algorithm=NEW.algorithm) OR (content_id=NEW.content_id AND representation=NEW.representation AND algorithm=NEW.algorithm)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER content_digests_retain BEFORE DELETE ON content_digests BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER content_locations_immutable BEFORE UPDATE ON content_locations WHEN NEW.content_id IS NOT OLD.content_id OR NEW.kind IS NOT OLD.kind OR NEW.locator IS NOT OLD.locator BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER content_locations_no_replace BEFORE INSERT ON content_locations WHEN EXISTS(SELECT 1 FROM content_locations WHERE (content_id=NEW.content_id AND kind=NEW.kind AND locator=NEW.locator) OR (content_id=NEW.content_id AND kind=NEW.kind AND locator=NEW.locator)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX content_locations_fk_0 ON content_locations(cache_id);
-- Only missing eligible text may be filled. The admission must hash supplied local
-- bytes against all saved raw-content-v1 digests before this UPDATE; SQL checks
-- the SHA-256 anchor exists, byte length (CHECK), NUL policy and write-once shape.
CREATE TRIGGER contents_immutable BEFORE UPDATE ON contents WHEN NEW.id IS NOT OLD.id OR NEW.byte_length IS NOT OLD.byte_length OR NEW.text_state IS NOT OLD.text_state OR NEW.created_at IS NOT OLD.created_at OR (NEW.raw_text IS NOT OLD.raw_text AND NOT (OLD.raw_text IS NULL AND NEW.raw_text IS NOT NULL AND OLD.text_state='eligible' AND instr(NEW.raw_text,char(0))=0 AND EXISTS(SELECT 1 FROM content_digests WHERE content_id=OLD.id AND representation='raw-content-v1' AND algorithm='sha256'))) BEGIN SELECT RAISE(ABORT,'Immutable content or invalid text completion'); END;
CREATE TRIGGER contents_no_replace BEFORE INSERT ON contents WHEN EXISTS(SELECT 1 FROM contents WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER contents_retain BEFORE DELETE ON contents BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER conversion_batches_immutable BEFORE UPDATE ON conversion_batches WHEN NEW.id IS NOT OLD.id OR NEW.run_id IS NOT OLD.run_id OR NEW.source_table IS NOT OLD.source_table OR NEW.input_sha256 IS NOT OLD.input_sha256 OR NEW.committed_at IS NOT OLD.committed_at OR NEW.output_manifest IS NOT OLD.output_manifest BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER conversion_batches_no_replace BEFORE INSERT ON conversion_batches WHEN EXISTS(SELECT 1 FROM conversion_batches WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER conversion_batches_retain BEFORE DELETE ON conversion_batches BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX conversion_batches_fk_0 ON conversion_batches(run_id);
CREATE TRIGGER conversion_runs_immutable BEFORE UPDATE ON conversion_runs WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER conversion_runs_no_replace BEFORE INSERT ON conversion_runs WHEN EXISTS(SELECT 1 FROM conversion_runs WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX conversion_runs_fk_0 ON conversion_runs(source_id);
CREATE TRIGGER conversion_sources_immutable BEFORE UPDATE ON conversion_sources WHEN NEW.id IS NOT OLD.id OR NEW.source_sha256 IS NOT OLD.source_sha256 OR NEW.schema_sha256 IS NOT OLD.schema_sha256 OR NEW.format_id IS NOT OLD.format_id OR NEW.source_db_instance_id IS NOT OLD.source_db_instance_id OR NEW.source_catalog IS NOT OLD.source_catalog OR NEW.source_migrations IS NOT OLD.source_migrations BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER conversion_sources_no_replace BEFORE INSERT ON conversion_sources WHEN EXISTS(SELECT 1 FROM conversion_sources WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER conversion_sources_retain BEFORE DELETE ON conversion_sources BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER coverage_claims_immutable BEFORE UPDATE ON coverage_claims WHEN NEW.id IS NOT OLD.id OR NEW.scope_id IS NOT OLD.scope_id OR NEW.asserted_state IS NOT OLD.asserted_state OR NEW.effective_state IS NOT OLD.effective_state OR NEW.details IS NOT OLD.details OR NEW.observed_at IS NOT OLD.observed_at OR NEW.evaluated_at IS NOT OLD.evaluated_at BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER coverage_claims_no_replace BEFORE INSERT ON coverage_claims WHEN EXISTS(SELECT 1 FROM coverage_claims WHERE (id=NEW.id) OR (id=NEW.id AND scope_id=NEW.scope_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER coverage_claims_retain BEFORE DELETE ON coverage_claims BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX coverage_claims_fk_0 ON coverage_claims(scope_id);
CREATE TRIGGER coverage_scopes_immutable BEFORE UPDATE ON coverage_scopes WHEN NEW.id IS NOT OLD.id OR NEW.repo_id IS NOT OLD.repo_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER coverage_scopes_no_replace BEFORE INSERT ON coverage_scopes WHEN EXISTS(SELECT 1 FROM coverage_scopes WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX coverage_scopes_fk_0 ON coverage_scopes(current_claim_id,id);
CREATE INDEX coverage_scopes_fk_1 ON coverage_scopes(change_request_id,repo_id);
CREATE INDEX coverage_scopes_fk_2 ON coverage_scopes(repo_id);
CREATE TRIGGER database_identity_immutable BEFORE UPDATE ON database_identity WHEN NEW.singleton IS NOT OLD.singleton OR NEW.format_id IS NOT OLD.format_id OR NEW.schema_version IS NOT OLD.schema_version OR NEW.db_instance_id IS NOT OLD.db_instance_id OR NEW.ddl_sha256 IS NOT OLD.ddl_sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER database_identity_no_replace BEFORE INSERT ON database_identity WHEN EXISTS(SELECT 1 FROM database_identity WHERE (singleton=NEW.singleton)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER document_observations_immutable BEFORE UPDATE ON document_observations WHEN NEW.id IS NOT OLD.id OR NEW.document_id IS NOT OLD.document_id OR NEW.version_id IS NOT OLD.version_id OR NEW.observed_at IS NOT OLD.observed_at OR NEW.parsed_at IS NOT OLD.parsed_at OR NEW.origin_key IS NOT OLD.origin_key OR NEW.occurrence_id IS NOT OLD.occurrence_id OR NEW.metadata IS NOT OLD.metadata BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER document_observations_no_replace BEFORE INSERT ON document_observations WHEN EXISTS(SELECT 1 FROM document_observations WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER document_observations_retain BEFORE DELETE ON document_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX document_observations_fk_0 ON document_observations(version_id,document_id);
CREATE INDEX document_observations_fk_1 ON document_observations(occurrence_id);
CREATE TRIGGER document_versions_immutable BEFORE UPDATE ON document_versions WHEN NEW.id IS NOT OLD.id OR NEW.document_id IS NOT OLD.document_id OR NEW.body_id IS NOT OLD.body_id OR NEW.legacy_body_sha256 IS NOT OLD.legacy_body_sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER document_versions_no_replace BEFORE INSERT ON document_versions WHEN EXISTS(SELECT 1 FROM document_versions WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER document_versions_retain BEFORE DELETE ON document_versions BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX document_versions_fk_0 ON document_versions(body_id);
CREATE TRIGGER documents_immutable BEFORE UPDATE ON documents WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_id IS NOT OLD.provider_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER documents_no_replace BEFORE INSERT ON documents WHEN EXISTS(SELECT 1 FROM documents WHERE (id=NEW.id) OR (change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_id=NEW.provider_id) OR (id=NEW.id AND change_request_id=NEW.change_request_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX documents_fk_0 ON documents(current_version_id,id);
CREATE TRIGGER fetch_collections_immutable BEFORE UPDATE ON fetch_collections WHEN NEW.id IS NOT OLD.id OR NEW.repo_id IS NOT OLD.repo_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.source_id IS NOT OLD.source_id OR NEW.kind IS NOT OLD.kind OR NEW.scope_id IS NOT OLD.scope_id OR NEW.observed_at IS NOT OLD.observed_at BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER fetch_collections_no_replace BEFORE INSERT ON fetch_collections WHEN EXISTS(SELECT 1 FROM fetch_collections WHERE (id=NEW.id) OR (id=NEW.id AND change_request_id=NEW.change_request_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER fetch_collections_retain BEFORE DELETE ON fetch_collections BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX fetch_collections_fk_0 ON fetch_collections(change_request_id,repo_id);
CREATE INDEX fetch_collections_fk_1 ON fetch_collections(scope_id);
CREATE INDEX fetch_collections_fk_2 ON fetch_collections(source_id);
CREATE INDEX fetch_collections_fk_3 ON fetch_collections(repo_id);
CREATE TRIGGER fetch_occurrences_immutable BEFORE UPDATE ON fetch_occurrences WHEN NEW.id IS NOT OLD.id OR NEW.collection_id IS NOT OLD.collection_id OR NEW.ordinal IS NOT OLD.ordinal OR NEW.payload_id IS NOT OLD.payload_id OR NEW.request IS NOT OLD.request OR NEW.next_cursor IS NOT OLD.next_cursor OR NEW.observed_at IS NOT OLD.observed_at OR NEW.parsed_at IS NOT OLD.parsed_at BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER fetch_occurrences_no_replace BEFORE INSERT ON fetch_occurrences WHEN EXISTS(SELECT 1 FROM fetch_occurrences WHERE (id=NEW.id) OR (id=NEW.id AND collection_id=NEW.collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER fetch_occurrences_retain BEFORE DELETE ON fetch_occurrences BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX fetch_occurrences_fk_0 ON fetch_occurrences(payload_id);
CREATE INDEX fetch_occurrences_fk_1 ON fetch_occurrences(collection_id);
CREATE TRIGGER git_acquisitions_immutable BEFORE UPDATE ON git_acquisitions WHEN NEW.id IS NOT OLD.id OR NEW.repo_id IS NOT OLD.repo_id OR NEW.endpoint_id IS NOT OLD.endpoint_id OR NEW.endpoint_url IS NOT OLD.endpoint_url OR NEW.object_format IS NOT OLD.object_format OR NEW.refs_observed_at IS NOT OLD.refs_observed_at OR NEW.source_id IS NOT OLD.source_id OR NEW.kind IS NOT OLD.kind OR NEW.started_at IS NOT OLD.started_at OR NEW.observed_at IS NOT OLD.observed_at OR NEW.request IS NOT OLD.request OR NEW.roots_manifest IS NOT OLD.roots_manifest BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER git_acquisitions_no_replace BEFORE INSERT ON git_acquisitions WHEN EXISTS(SELECT 1 FROM git_acquisitions WHERE (id=NEW.id) OR (id=NEW.id AND repo_id=NEW.repo_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER git_acquisitions_retain BEFORE DELETE ON git_acquisitions BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX git_acquisitions_fk_0 ON git_acquisitions(endpoint_id,repo_id);
CREATE INDEX git_acquisitions_fk_1 ON git_acquisitions(source_id);
CREATE INDEX git_acquisitions_fk_2 ON git_acquisitions(repo_id);
-- verified is a monotonic result projection, not an immutable legacy assertion.
-- Setting 0 -> 1 requires admission to verify the local raw Git object bytes.
CREATE TRIGGER git_objects_immutable BEFORE UPDATE ON git_objects WHEN NEW.id IS NOT OLD.id OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.type IS NOT OLD.type OR NEW.size IS NOT OLD.size OR NEW.verified<OLD.verified BEGIN SELECT RAISE(ABORT,'Immutable Git identity or verification downgrade'); END;
CREATE TRIGGER git_objects_no_replace BEFORE INSERT ON git_objects WHEN EXISTS(SELECT 1 FROM git_objects WHERE (id=NEW.id) OR (object_format=NEW.object_format AND oid=NEW.oid)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER git_objects_retain BEFORE DELETE ON git_objects BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER id_mappings_immutable BEFORE UPDATE ON id_mappings WHEN NEW.id IS NOT OLD.id OR NEW.record_id IS NOT OLD.record_id OR NEW.target_table IS NOT OLD.target_table OR NEW.target_key IS NOT OLD.target_key OR NEW.relation IS NOT OLD.relation OR NEW.reason IS NOT OLD.reason BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER id_mappings_no_replace BEFORE INSERT ON id_mappings WHEN EXISTS(SELECT 1 FROM id_mappings WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER id_mappings_retain BEFORE DELETE ON id_mappings BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX id_mappings_fk_0 ON id_mappings(record_id);
CREATE TRIGGER incremental_scans_immutable BEFORE UPDATE ON incremental_scans WHEN NEW.id IS NOT OLD.id OR NEW.scope_id IS NOT OLD.scope_id OR NEW.collection_id IS NOT OLD.collection_id OR NEW.scan_started_at IS NOT OLD.scan_started_at OR NEW.safe_watermark IS NOT OLD.safe_watermark OR NEW.evidence IS NOT OLD.evidence BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER incremental_scans_no_replace BEFORE INSERT ON incremental_scans WHEN EXISTS(SELECT 1 FROM incremental_scans WHERE (id=NEW.id) OR (id=NEW.id AND scope_id=NEW.scope_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER incremental_scans_retain BEFORE DELETE ON incremental_scans BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX incremental_scans_fk_0 ON incremental_scans(collection_id);
CREATE INDEX incremental_scans_fk_1 ON incremental_scans(scope_id);
CREATE TRIGGER index_generations_immutable BEFORE UPDATE ON index_generations WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER index_generations_no_replace BEFORE INSERT ON index_generations WHEN EXISTS(SELECT 1 FROM index_generations WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER index_membership_immutable BEFORE UPDATE ON index_membership WHEN NEW.generation_id IS NOT OLD.generation_id OR NEW.document_id IS NOT OLD.document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER index_membership_no_replace BEFORE INSERT ON index_membership WHEN EXISTS(SELECT 1 FROM index_membership WHERE (generation_id=NEW.generation_id AND document_id=NEW.document_id) OR (generation_id=NEW.generation_id AND document_id=NEW.document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX index_membership_fk_0 ON index_membership(document_id);
CREATE TRIGGER inventory_observations_immutable BEFORE UPDATE ON inventory_observations WHEN NEW.id IS NOT OLD.id OR NEW.source_id IS NOT OLD.source_id OR NEW.asserted_state IS NOT OLD.asserted_state OR NEW.scope IS NOT OLD.scope OR NEW.observed_at IS NOT OLD.observed_at OR NEW.reason IS NOT OLD.reason BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER inventory_observations_no_replace BEFORE INSERT ON inventory_observations WHEN EXISTS(SELECT 1 FROM inventory_observations WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER inventory_observations_retain BEFORE DELETE ON inventory_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX inventory_observations_fk_0 ON inventory_observations(source_id);
CREATE TRIGGER job_attempts_immutable BEFORE UPDATE ON job_attempts WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER job_attempts_no_replace BEFORE INSERT ON job_attempts WHEN EXISTS(SELECT 1 FROM job_attempts WHERE (job_id=NEW.job_id AND attempt=NEW.attempt) OR (job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER jobs_immutable BEFORE UPDATE ON jobs WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER jobs_no_replace BEFORE INSERT ON jobs WHEN EXISTS(SELECT 1 FROM jobs WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX jobs_fk_0 ON jobs(id,current_attempt);
CREATE TRIGGER legacy_records_immutable BEFORE UPDATE ON legacy_records WHEN NEW.id IS NOT OLD.id OR NEW.source_id IS NOT OLD.source_id OR NEW.source_table IS NOT OLD.source_table OR NEW.source_key IS NOT OLD.source_key OR NEW.row_sha256 IS NOT OLD.row_sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER legacy_records_no_replace BEFORE INSERT ON legacy_records WHEN EXISTS(SELECT 1 FROM legacy_records WHERE (id=NEW.id) OR (source_id=NEW.source_id AND source_table=NEW.source_table AND source_key=NEW.source_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER legacy_records_retain BEFORE DELETE ON legacy_records BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER legacy_values_immutable BEFORE UPDATE ON legacy_values WHEN NEW.record_id IS NOT OLD.record_id OR NEW.column_name IS NOT OLD.column_name OR NEW.storage_type IS NOT OLD.storage_type OR NEW.value_bytes IS NOT OLD.value_bytes BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER legacy_values_no_replace BEFORE INSERT ON legacy_values WHEN EXISTS(SELECT 1 FROM legacy_values WHERE (record_id=NEW.record_id AND column_name=NEW.column_name) OR (record_id=NEW.record_id AND column_name=NEW.column_name)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER legacy_values_retain BEFORE DELETE ON legacy_values BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER payloads_immutable BEFORE UPDATE ON payloads WHEN NEW.id IS NOT OLD.id OR NEW.sha256 IS NOT OLD.sha256 OR NEW.body IS NOT OLD.body OR NEW.byte_length IS NOT OLD.byte_length OR NEW.representation IS NOT OLD.representation BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER payloads_no_replace BEFORE INSERT ON payloads WHEN EXISTS(SELECT 1 FROM payloads WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER payloads_retain BEFORE DELETE ON payloads BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER preservation_obligations_immutable BEFORE UPDATE ON preservation_obligations WHEN NEW.acquisition_id IS NOT OLD.acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER preservation_obligations_no_replace BEFORE INSERT ON preservation_obligations WHEN EXISTS(SELECT 1 FROM preservation_obligations WHERE (acquisition_id=NEW.acquisition_id) OR (acquisition_id=NEW.acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX preservation_obligations_fk_0 ON preservation_obligations(cache_id);
CREATE TRIGGER reanalysis_runs_immutable BEFORE UPDATE ON reanalysis_runs WHEN NEW.id IS NOT OLD.id OR NEW.conversion_run_id IS NOT OLD.conversion_run_id OR NEW.parser_version IS NOT OLD.parser_version OR NEW.parsed_at IS NOT OLD.parsed_at OR NEW.evidence IS NOT OLD.evidence BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER reanalysis_runs_no_replace BEFORE INSERT ON reanalysis_runs WHEN EXISTS(SELECT 1 FROM reanalysis_runs WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER reanalysis_runs_retain BEFORE DELETE ON reanalysis_runs BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX reanalysis_runs_fk_0 ON reanalysis_runs(conversion_run_id);
CREATE TRIGGER ref_observations_immutable BEFORE UPDATE ON ref_observations WHEN NEW.snapshot_id IS NOT OLD.snapshot_id OR NEW.raw_ref_name IS NOT OLD.raw_ref_name OR NEW.kind IS NOT OLD.kind OR NEW.object_format IS NOT OLD.object_format OR NEW.target_oid IS NOT OLD.target_oid OR NEW.peeled_oid IS NOT OLD.peeled_oid OR NEW.target_type IS NOT OLD.target_type BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER ref_observations_no_replace BEFORE INSERT ON ref_observations WHEN EXISTS(SELECT 1 FROM ref_observations WHERE (snapshot_id=NEW.snapshot_id AND raw_ref_name=NEW.raw_ref_name) OR (snapshot_id=NEW.snapshot_id AND raw_ref_name=NEW.raw_ref_name)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER ref_observations_retain BEFORE DELETE ON ref_observations BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER repositories_immutable BEFORE UPDATE ON repositories WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repositories_no_replace BEFORE INSERT ON repositories WHEN EXISTS(SELECT 1 FROM repositories WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX repositories_fk_0 ON repositories(current_snapshot_id,id);
CREATE INDEX repositories_fk_1 ON repositories(preferred_endpoint_id,id);
CREATE TRIGGER repository_bindings_immutable BEFORE UPDATE ON repository_bindings WHEN NEW.id IS NOT OLD.id OR NEW.repo_id IS NOT OLD.repo_id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.provider_repo_id IS NOT OLD.provider_repo_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_bindings_no_replace BEFORE INSERT ON repository_bindings WHEN EXISTS(SELECT 1 FROM repository_bindings WHERE (id=NEW.id) OR (id=NEW.id AND repo_id=NEW.repo_id) OR (instance_id=NEW.instance_id AND provider_repo_id=NEW.provider_repo_id) OR (repo_id=NEW.repo_id AND instance_id=NEW.instance_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_endpoints_immutable BEFORE UPDATE ON repository_endpoints WHEN NEW.id IS NOT OLD.id OR NEW.repo_id IS NOT OLD.repo_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_endpoints_no_replace BEFORE INSERT ON repository_endpoints WHEN EXISTS(SELECT 1 FROM repository_endpoints WHERE (id=NEW.id) OR (id=NEW.id AND repo_id=NEW.repo_id) OR (repo_id=NEW.repo_id AND url=NEW.url) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_name_assertions_immutable BEFORE UPDATE ON repository_name_assertions WHEN NEW.repo_id IS NOT OLD.repo_id OR NEW.name IS NOT OLD.name OR NEW.observed_at IS NOT OLD.observed_at BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_name_assertions_no_replace BEFORE INSERT ON repository_name_assertions WHEN EXISTS(SELECT 1 FROM repository_name_assertions WHERE (repo_id=NEW.repo_id AND name=NEW.name) OR (repo_id=NEW.repo_id AND name=NEW.name)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_name_assertions_retain BEFORE DELETE ON repository_name_assertions BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER repository_object_sources_immutable BEFORE UPDATE ON repository_object_sources WHEN NEW.repo_id IS NOT OLD.repo_id OR NEW.object_id IS NOT OLD.object_id OR NEW.acquisition_id IS NOT OLD.acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER repository_object_sources_no_replace BEFORE INSERT ON repository_object_sources WHEN EXISTS(SELECT 1 FROM repository_object_sources WHERE (repo_id=NEW.repo_id AND object_id=NEW.object_id AND acquisition_id=NEW.acquisition_id) OR (repo_id=NEW.repo_id AND object_id=NEW.object_id AND acquisition_id=NEW.acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_object_sources_retain BEFORE DELETE ON repository_object_sources BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX repository_object_sources_fk_0 ON repository_object_sources(acquisition_id,repo_id);
CREATE INDEX repository_object_sources_fk_1 ON repository_object_sources(object_id);
CREATE TRIGGER resume_cursors_immutable BEFORE UPDATE ON resume_cursors WHEN NEW.scope_id IS NOT OLD.scope_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER resume_cursors_no_replace BEFORE INSERT ON resume_cursors WHEN EXISTS(SELECT 1 FROM resume_cursors WHERE (scope_id=NEW.scope_id) OR (scope_id=NEW.scope_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX resume_cursors_fk_0 ON resume_cursors(scan_id,scope_id);
CREATE TRIGGER resume_scopes_immutable BEFORE UPDATE ON resume_scopes WHEN NEW.id IS NOT OLD.id OR NEW.repo_id IS NOT OLD.repo_id OR NEW.binding_id IS NOT OLD.binding_id OR NEW.source_id IS NOT OLD.source_id OR NEW.principal_ref IS NOT OLD.principal_ref OR NEW.api_version IS NOT OLD.api_version OR NEW.endpoint IS NOT OLD.endpoint OR NEW.request_context IS NOT OLD.request_context OR NEW.parser_version IS NOT OLD.parser_version OR NEW.profile_version IS NOT OLD.profile_version OR NEW.confidence IS NOT OLD.confidence BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER resume_scopes_no_replace BEFORE INSERT ON resume_scopes WHEN EXISTS(SELECT 1 FROM resume_scopes WHERE (id=NEW.id) OR (id=NEW.id AND repo_id=NEW.repo_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER resume_scopes_retain BEFORE DELETE ON resume_scopes BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX resume_scopes_fk_0 ON resume_scopes(binding_id,repo_id);
CREATE INDEX resume_scopes_fk_1 ON resume_scopes(source_id);
CREATE INDEX resume_scopes_fk_2 ON resume_scopes(repo_id);
CREATE TRIGGER review_comments_immutable BEFORE UPDATE ON review_comments WHEN NEW.document_id IS NOT OLD.document_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.thread_id IS NOT OLD.thread_id OR NEW.payload IS NOT OLD.payload BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER review_comments_no_replace BEFORE INSERT ON review_comments WHEN EXISTS(SELECT 1 FROM review_comments WHERE (document_id=NEW.document_id) OR (document_id=NEW.document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER review_comments_retain BEFORE DELETE ON review_comments BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX review_comments_fk_0 ON review_comments(thread_id,change_request_id);
CREATE INDEX review_comments_fk_1 ON review_comments(document_id,change_request_id);
CREATE TRIGGER review_threads_immutable BEFORE UPDATE ON review_threads WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER review_threads_no_replace BEFORE INSERT ON review_threads WHEN EXISTS(SELECT 1 FROM review_threads WHERE (id=NEW.id) OR (id=NEW.id AND change_request_id=NEW.change_request_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX review_threads_fk_0 ON review_threads(change_request_id);
CREATE TRIGGER reviews_immutable BEFORE UPDATE ON reviews WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.document_id IS NOT OLD.document_id OR NEW.payload IS NOT OLD.payload BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER reviews_no_replace BEFORE INSERT ON reviews WHEN EXISTS(SELECT 1 FROM reviews WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER reviews_retain BEFORE DELETE ON reviews BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX reviews_fk_0 ON reviews(document_id,change_request_id);
CREATE TRIGGER root_manifest_entries_immutable BEFORE UPDATE ON root_manifest_entries WHEN NEW.tree_id IS NOT OLD.tree_id OR NEW.raw_path IS NOT OLD.raw_path OR NEW.mode IS NOT OLD.mode OR NEW.object_id IS NOT OLD.object_id OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER root_manifest_entries_no_replace BEFORE INSERT ON root_manifest_entries WHEN EXISTS(SELECT 1 FROM root_manifest_entries WHERE (tree_id=NEW.tree_id AND raw_path=NEW.raw_path) OR (tree_id=NEW.tree_id AND raw_path=NEW.raw_path)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER root_manifest_entries_retain BEFORE DELETE ON root_manifest_entries BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX root_manifest_entries_fk_0 ON root_manifest_entries(object_id);
CREATE TRIGGER root_manifests_immutable BEFORE UPDATE ON root_manifests WHEN NEW.tree_id IS NOT OLD.tree_id OR NEW.complete IS NOT OLD.complete BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER root_manifests_no_replace BEFORE INSERT ON root_manifests WHEN EXISTS(SELECT 1 FROM root_manifests WHERE (tree_id=NEW.tree_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER root_manifests_retain BEFORE DELETE ON root_manifests BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER root_origins_immutable BEFORE UPDATE ON root_origins WHEN NEW.id IS NOT OLD.id OR NEW.root_id IS NOT OLD.root_id OR NEW.origin_kind IS NOT OLD.origin_kind OR NEW.raw_ref_name IS NOT OLD.raw_ref_name OR NEW.source_ordinal IS NOT OLD.source_ordinal OR NEW.snapshot_id IS NOT OLD.snapshot_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.observation_id IS NOT OLD.observation_id OR NEW.repo_id IS NOT OLD.repo_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER root_origins_no_replace BEFORE INSERT ON root_origins WHEN EXISTS(SELECT 1 FROM root_origins WHERE (id=NEW.id) OR (root_id=NEW.root_id AND origin_kind=NEW.origin_kind AND source_ordinal=NEW.source_ordinal)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER root_origins_retain BEFORE DELETE ON root_origins BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX root_origins_fk_0 ON root_origins(observation_id,change_request_id);
CREATE INDEX root_origins_fk_1 ON root_origins(change_request_id,repo_id);
CREATE INDEX root_origins_fk_2 ON root_origins(snapshot_id,repo_id);
CREATE INDEX root_origins_fk_3 ON root_origins(root_id,repo_id);
CREATE TRIGGER search_documents_immutable BEFORE UPDATE ON search_documents WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER search_documents_no_replace BEFORE INSERT ON search_documents WHEN EXISTS(SELECT 1 FROM search_documents WHERE (id=NEW.id) OR (kind=NEW.kind AND source_key=NEW.source_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER service_instances_immutable BEFORE UPDATE ON service_instances WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER service_instances_no_replace BEFORE INSERT ON service_instances WHEN EXISTS(SELECT 1 FROM service_instances WHERE (id=NEW.id) OR (name=NEW.name) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER snapshots_immutable BEFORE UPDATE ON snapshots WHEN NEW.id IS NOT OLD.id OR NEW.acquisition_id IS NOT OLD.acquisition_id OR NEW.repo_id IS NOT OLD.repo_id OR NEW.generation IS NOT OLD.generation OR NEW.created_at IS NOT OLD.created_at OR (OLD.published=1 AND NEW.published!=1) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER snapshots_no_replace BEFORE INSERT ON snapshots WHEN EXISTS(SELECT 1 FROM snapshots WHERE (id=NEW.id) OR (id=NEW.id AND repo_id=NEW.repo_id) OR (acquisition_id=NEW.acquisition_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER snapshots_retain BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX snapshots_fk_0 ON snapshots(acquisition_id,repo_id);
-- Pair membership is retained; times are aggregate known min/max, not event rows.
-- NULL may become known, never the reverse. Admission validates timezone and exact
-- temporal ordering; julianday supplies a coarse SQL guard, not microsecond proof.
CREATE TRIGGER source_repositories_immutable BEFORE UPDATE ON source_repositories WHEN NEW.source_id IS NOT OLD.source_id OR NEW.repo_id IS NOT OLD.repo_id OR (OLD.first_seen IS NOT NULL AND (NEW.first_seen IS NULL OR julianday(NEW.first_seen)>julianday(OLD.first_seen))) OR (OLD.last_seen IS NOT NULL AND (NEW.last_seen IS NULL OR julianday(NEW.last_seen)<julianday(OLD.last_seen))) BEGIN SELECT RAISE(ABORT,'Immutable source pair or aggregate time regression'); END;
CREATE TRIGGER source_repositories_no_replace BEFORE INSERT ON source_repositories WHEN EXISTS(SELECT 1 FROM source_repositories WHERE (source_id=NEW.source_id AND repo_id=NEW.repo_id) OR (source_id=NEW.source_id AND repo_id=NEW.repo_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER source_repositories_retain BEFORE DELETE ON source_repositories BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX source_repositories_fk_0 ON source_repositories(repo_id);
CREATE TRIGGER sources_immutable BEFORE UPDATE ON sources WHEN NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.discovery_kind IS NOT OLD.discovery_kind BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER sources_no_replace BEFORE INSERT ON sources WHEN EXISTS(SELECT 1 FROM sources WHERE (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX sources_fk_0 ON sources(instance_id);
CREATE TRIGGER space_reservations_immutable BEFORE UPDATE ON space_reservations WHEN NEW.job_id IS NOT OLD.job_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER space_reservations_no_replace BEFORE INSERT ON space_reservations WHEN EXISTS(SELECT 1 FROM space_reservations WHERE (job_id=NEW.job_id) OR (job_id=NEW.job_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER tag_objects_immutable BEFORE UPDATE ON tag_objects WHEN NEW.object_id IS NOT OLD.object_id OR NEW.target_id IS NOT OLD.target_id OR NEW.raw_payload IS NOT OLD.raw_payload BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER tag_objects_no_replace BEFORE INSERT ON tag_objects WHEN EXISTS(SELECT 1 FROM tag_objects WHERE (object_id=NEW.object_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER tag_objects_retain BEFORE DELETE ON tag_objects BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX tag_objects_fk_0 ON tag_objects(target_id);
CREATE TRIGGER text_bodies_immutable BEFORE UPDATE ON text_bodies WHEN NEW.id IS NOT OLD.id OR NEW.body IS NOT OLD.body OR NEW.byte_length IS NOT OLD.byte_length OR NEW.sha256 IS NOT OLD.sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER text_bodies_no_replace BEFORE INSERT ON text_bodies WHEN EXISTS(SELECT 1 FROM text_bodies WHERE (id=NEW.id) OR (sha256=NEW.sha256 AND body=NEW.body)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER text_bodies_retain BEFORE DELETE ON text_bodies BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER tree_entries_immutable BEFORE UPDATE ON tree_entries WHEN NEW.tree_id IS NOT OLD.tree_id OR NEW.raw_name IS NOT OLD.raw_name OR NEW.mode IS NOT OLD.mode OR NEW.child_format IS NOT OLD.child_format OR NEW.child_oid IS NOT OLD.child_oid OR NEW.child_id IS NOT OLD.child_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER tree_entries_no_replace BEFORE INSERT ON tree_entries WHEN EXISTS(SELECT 1 FROM tree_entries WHERE (tree_id=NEW.tree_id AND raw_name=NEW.raw_name) OR (tree_id=NEW.tree_id AND raw_name=NEW.raw_name)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER tree_entries_retain BEFORE DELETE ON tree_entries BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX tree_entries_fk_0 ON tree_entries(child_id);
CREATE TRIGGER unresolved_payloads_immutable BEFORE UPDATE ON unresolved_payloads WHEN NEW.id IS NOT OLD.id OR NEW.payload_id IS NOT OLD.payload_id OR NEW.legacy_record_id IS NOT OLD.legacy_record_id OR NEW.reason IS NOT OLD.reason BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER unresolved_payloads_no_replace BEFORE INSERT ON unresolved_payloads WHEN EXISTS(SELECT 1 FROM unresolved_payloads WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER unresolved_payloads_retain BEFORE DELETE ON unresolved_payloads BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX unresolved_payloads_fk_0 ON unresolved_payloads(legacy_record_id);
CREATE INDEX unresolved_payloads_fk_1 ON unresolved_payloads(payload_id);
CREATE TRIGGER validation_results_immutable BEFORE UPDATE ON validation_results WHEN NEW.id IS NOT OLD.id OR NEW.run_id IS NOT OLD.run_id OR NEW.invariant_id IS NOT OLD.invariant_id OR NEW.code IS NOT OLD.code OR NEW.severity IS NOT OLD.severity OR NEW.observed_at IS NOT OLD.observed_at OR NEW.details IS NOT OLD.details BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER validation_results_no_replace BEFORE INSERT ON validation_results WHEN EXISTS(SELECT 1 FROM validation_results WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER validation_results_retain BEFORE DELETE ON validation_results BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX validation_results_fk_0 ON validation_results(run_id);
CREATE TRIGGER validators_immutable BEFORE UPDATE ON validators WHEN NEW.scope_id IS NOT OLD.scope_id OR NEW.validator_key IS NOT OLD.validator_key BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact or publication'); END;
CREATE TRIGGER validators_no_replace BEFORE INSERT ON validators WHEN EXISTS(SELECT 1 FROM validators WHERE (scope_id=NEW.scope_id AND validator_key=NEW.validator_key) OR (scope_id=NEW.scope_id AND validator_key=NEW.validator_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX validators_fk_0 ON validators(payload_id);
CREATE TRIGGER snapshot_current_insert BEFORE INSERT ON repositories WHEN NEW.current_snapshot_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM snapshots WHERE id=NEW.current_snapshot_id AND repo_id=NEW.id AND published=1) BEGIN SELECT RAISE(ABORT,'Current snapshot requires published fact'); END;
CREATE TRIGGER snapshot_current_update BEFORE UPDATE ON repositories WHEN NEW.current_snapshot_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM snapshots WHERE id=NEW.current_snapshot_id AND repo_id=NEW.id AND published=1) BEGIN SELECT RAISE(ABORT,'Current snapshot requires published fact'); END;
CREATE TRIGGER cr_current_insert BEFORE INSERT ON change_requests WHEN NEW.current_observation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM change_request_observations WHERE id=NEW.current_observation_id AND change_request_id=NEW.id AND published=1) BEGIN SELECT RAISE(ABORT,'Current observation requires published fact'); END;
CREATE TRIGGER cr_current_update BEFORE UPDATE ON change_requests WHEN NEW.current_observation_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM change_request_observations WHERE id=NEW.current_observation_id AND change_request_id=NEW.id AND published=1) BEGIN SELECT RAISE(ABORT,'Current observation requires published fact'); END;
CREATE TRIGGER listing_scope_insert BEFORE INSERT ON code_listings WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.id=NEW.collection_id AND f.change_request_id=NEW.change_request_id AND f.scope_id=NEW.scope_id) BEGIN SELECT RAISE(ABORT,'Listing collection, CR and scope mismatch'); END;
CREATE TRIGGER listing_scope_update BEFORE UPDATE ON code_listings WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.id=NEW.collection_id AND f.change_request_id=NEW.change_request_id AND f.scope_id=NEW.scope_id) BEGIN SELECT RAISE(ABORT,'Listing collection, CR and scope mismatch'); END;
CREATE TRIGGER fetch_scope_insert BEFORE INSERT ON fetch_collections WHEN NOT EXISTS(SELECT 1 FROM resume_scopes s WHERE s.id=NEW.scope_id AND s.repo_id=NEW.repo_id AND s.source_id IS NEW.source_id) BEGIN SELECT RAISE(ABORT,'Collection scope mismatch'); END;
CREATE TRIGGER fetch_scope_update BEFORE UPDATE ON fetch_collections WHEN NOT EXISTS(SELECT 1 FROM resume_scopes s WHERE s.id=NEW.scope_id AND s.repo_id=NEW.repo_id AND s.source_id IS NEW.source_id) BEGIN SELECT RAISE(ABORT,'Collection scope mismatch'); END;
CREATE TRIGGER code_commits_insert BEFORE INSERT ON code_observations WHEN NEW.commit_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.id=NEW.commit_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_commits_update BEFORE UPDATE ON code_observations WHEN NEW.commit_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.id=NEW.commit_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_files_insert BEFORE INSERT ON code_observations WHEN NEW.file_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.id=NEW.file_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='files' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_files_update BEFORE UPDATE ON code_observations WHEN NEW.file_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.id=NEW.file_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='files' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid) BEGIN SELECT RAISE(ABORT,'Code listing kind or context mismatch'); END;
CREATE TRIGGER code_complete_insert BEFORE INSERT ON code_observations WHEN NEW.state='complete' AND (NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE listing_id=NEW.commit_listing_id AND state='complete') OR NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE listing_id=NEW.file_listing_id AND state='complete')) BEGIN SELECT RAISE(ABORT,'Complete code requires complete listings'); END;
CREATE TRIGGER code_complete_update BEFORE UPDATE ON code_observations WHEN NEW.state='complete' AND (NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE listing_id=NEW.commit_listing_id AND state='complete') OR NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE listing_id=NEW.file_listing_id AND state='complete')) BEGIN SELECT RAISE(ABORT,'Complete code requires complete listings'); END;
CREATE TRIGGER listing_no_downgrade BEFORE UPDATE ON code_listing_progress WHEN OLD.state='complete' AND (NEW.state IS NOT OLD.state OR NEW.terminal IS NOT OLD.terminal OR NEW.page_count IS NOT OLD.page_count OR NEW.context_proven IS NOT OLD.context_proven) BEGIN SELECT RAISE(ABORT,'Completed listing is immutable'); END;
-- Completion seals even an unreferenced listing. Deleting and recreating its
-- marker must not reopen it; conflict INSERT/REPLACE is separately prohibited.
CREATE TRIGGER listing_complete_retain BEFORE DELETE ON code_listing_progress WHEN OLD.state='complete' BEGIN SELECT RAISE(ABORT,'Complete listing marker cannot be deleted'); END;
CREATE TRIGGER code_commits_context_insert BEFORE INSERT ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.collection_id=l.collection_id WHERE l.id=NEW.listing_id AND l.kind='commits' AND o.id=NEW.occurrence_id AND l.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_commits_context_update BEFORE UPDATE ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.collection_id=l.collection_id WHERE l.id=NEW.listing_id AND l.kind='commits' AND o.id=NEW.occurrence_id AND l.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_commits_sealed_insert BEFORE INSERT ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE listing_id=NEW.listing_id AND state='partial') BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_commits_sealed_update BEFORE UPDATE ON code_commits WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE listing_id=NEW.listing_id AND state='partial') BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_file_changes_context_insert BEFORE INSERT ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.collection_id=l.collection_id WHERE l.id=NEW.listing_id AND l.kind='files' AND o.id=NEW.occurrence_id) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_file_changes_context_update BEFORE UPDATE ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN fetch_occurrences o ON o.collection_id=l.collection_id WHERE l.id=NEW.listing_id AND l.kind='files' AND o.id=NEW.occurrence_id) BEGIN SELECT RAISE(ABORT,'Listing item kind or page mismatch'); END;
CREATE TRIGGER code_file_changes_sealed_insert BEFORE INSERT ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE listing_id=NEW.listing_id AND state='partial') BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_file_changes_sealed_update BEFORE UPDATE ON code_file_changes WHEN NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE listing_id=NEW.listing_id AND state='partial') BEGIN SELECT RAISE(ABORT,'Listing items require initialized partial progress'); END;
CREATE TRIGGER code_acquisition_owner_insert BEFORE INSERT ON code_acquisitions WHEN NEW.root_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_observations o ON o.id=NEW.code_observation_id JOIN change_requests c ON c.id=o.change_request_id WHERE r.id=NEW.root_id AND r.repo_id=c.repo_id AND r.role=NEW.role AND r.object_format=NEW.object_format AND r.oid=NEW.oid AND (r.expected_oid IS NULL OR r.expected_oid=NEW.oid)) BEGIN SELECT RAISE(ABORT,'Code acquisition owner, role or OID mismatch'); END;
CREATE TRIGGER code_acquisition_owner_update BEFORE UPDATE ON code_acquisitions WHEN NEW.root_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_observations o ON o.id=NEW.code_observation_id JOIN change_requests c ON c.id=o.change_request_id WHERE r.id=NEW.root_id AND r.repo_id=c.repo_id AND r.role=NEW.role AND r.object_format=NEW.object_format AND r.oid=NEW.oid AND (r.expected_oid IS NULL OR r.expected_oid=NEW.oid)) BEGIN SELECT RAISE(ABORT,'Code acquisition owner, role or OID mismatch'); END;
CREATE TRIGGER origin_ref_insert BEFORE INSERT ON root_origins WHEN NEW.origin_kind='ref' AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN snapshots s ON s.acquisition_id=r.acquisition_id JOIN ref_observations f ON f.snapshot_id=s.id WHERE r.id=NEW.root_id AND s.id=NEW.snapshot_id AND f.raw_ref_name=NEW.raw_ref_name AND f.object_format=r.object_format AND COALESCE(f.peeled_oid,f.target_oid)=r.oid) BEGIN SELECT RAISE(ABORT,'Ref origin must match acquisition and OID'); END;
CREATE TRIGGER origin_ref_update BEFORE UPDATE ON root_origins WHEN NEW.origin_kind='ref' AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN snapshots s ON s.acquisition_id=r.acquisition_id JOIN ref_observations f ON f.snapshot_id=s.id WHERE r.id=NEW.root_id AND s.id=NEW.snapshot_id AND f.raw_ref_name=NEW.raw_ref_name AND f.object_format=r.object_format AND COALESCE(f.peeled_oid,f.target_oid)=r.oid) BEGIN SELECT RAISE(ABORT,'Ref origin must match acquisition and OID'); END;
CREATE TRIGGER origin_pr_insert BEFORE INSERT ON root_origins WHEN NEW.origin_kind='pr_role' AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_acquisitions a ON a.root_id=r.id JOIN code_observations o ON o.id=a.code_observation_id WHERE r.id=NEW.root_id AND o.change_request_id=NEW.change_request_id AND o.observation_id=NEW.observation_id) BEGIN SELECT RAISE(ABORT,'PR origin must match code acquisition'); END;
CREATE TRIGGER origin_pr_update BEFORE UPDATE ON root_origins WHEN NEW.origin_kind='pr_role' AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_acquisitions a ON a.root_id=r.id JOIN code_observations o ON o.id=a.code_observation_id WHERE r.id=NEW.root_id AND o.change_request_id=NEW.change_request_id AND o.observation_id=NEW.observation_id) BEGIN SELECT RAISE(ABORT,'PR origin must match code acquisition'); END;
CREATE TRIGGER root_format_insert BEFORE INSERT ON acquisition_roots WHEN NOT EXISTS(SELECT 1 FROM git_acquisitions a WHERE a.id=NEW.acquisition_id AND a.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Root format must match acquisition'); END;
CREATE TRIGGER root_format_update BEFORE UPDATE ON acquisition_roots WHEN NOT EXISTS(SELECT 1 FROM git_acquisitions a WHERE a.id=NEW.acquisition_id AND a.object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'Root format must match acquisition'); END;
CREATE TRIGGER membership_owner_insert BEFORE INSERT ON collection_memberships WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f JOIN documents d ON d.change_request_id=f.change_request_id WHERE f.id=NEW.collection_id AND d.id=NEW.document_id) BEGIN SELECT RAISE(ABORT,'Membership must belong to same CR'); END;
CREATE TRIGGER membership_owner_update BEFORE UPDATE ON collection_memberships WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f JOIN documents d ON d.change_request_id=f.change_request_id WHERE f.id=NEW.collection_id AND d.id=NEW.document_id) BEGIN SELECT RAISE(ABORT,'Membership must belong to same CR'); END;
CREATE TRIGGER document_origin_insert BEFORE INSERT ON document_observations WHEN NEW.occurrence_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM fetch_occurrences o JOIN fetch_collections f ON f.id=o.collection_id JOIN documents d ON d.change_request_id=f.change_request_id WHERE o.id=NEW.occurrence_id AND d.id=NEW.document_id) BEGIN SELECT RAISE(ABORT,'Document occurrence belongs to another CR'); END;
CREATE TRIGGER document_origin_update BEFORE UPDATE ON document_observations WHEN NEW.occurrence_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM fetch_occurrences o JOIN fetch_collections f ON f.id=o.collection_id JOIN documents d ON d.change_request_id=f.change_request_id WHERE o.id=NEW.occurrence_id AND d.id=NEW.document_id) BEGIN SELECT RAISE(ABORT,'Document occurrence belongs to another CR'); END;
CREATE TRIGGER scan_scope_insert BEFORE INSERT ON incremental_scans WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.id=NEW.collection_id AND f.scope_id=NEW.scope_id) BEGIN SELECT RAISE(ABORT,'Scan scope mismatch'); END;
CREATE TRIGGER scan_scope_update BEFORE UPDATE ON incremental_scans WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.id=NEW.collection_id AND f.scope_id=NEW.scope_id) BEGIN SELECT RAISE(ABORT,'Scan scope mismatch'); END;
CREATE TRIGGER completion_scope_insert BEFORE INSERT ON completion_markers WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.id=NEW.collection_id AND f.scope_id=NEW.scope_id) BEGIN SELECT RAISE(ABORT,'Completion scope mismatch'); END;
CREATE TRIGGER completion_scope_update BEFORE UPDATE ON completion_markers WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.id=NEW.collection_id AND f.scope_id=NEW.scope_id) BEGIN SELECT RAISE(ABORT,'Completion scope mismatch'); END;
CREATE TRIGGER active_locator_insert BEFORE INSERT ON active_cache_entries WHEN NOT EXISTS(SELECT 1 FROM cache_locators WHERE id=NEW.locator_id AND access='target_active') BEGIN SELECT RAISE(ABORT,'Readonly source cache cannot become active'); END;
CREATE TRIGGER active_locator_update BEFORE UPDATE ON active_cache_entries WHEN NOT EXISTS(SELECT 1 FROM cache_locators WHERE id=NEW.locator_id AND access='target_active') BEGIN SELECT RAISE(ABORT,'Readonly source cache cannot become active'); END;
CREATE TRIGGER commit_type_insert BEFORE INSERT ON commits WHEN NOT EXISTS(SELECT 1 FROM git_objects c JOIN git_objects t ON t.id=NEW.tree_id WHERE c.id=NEW.object_id AND c.type='commit' AND t.type='tree' AND c.object_format=t.object_format) BEGIN SELECT RAISE(ABORT,'Commit or tree type/format mismatch'); END;
CREATE TRIGGER commit_type_update BEFORE UPDATE ON commits WHEN NOT EXISTS(SELECT 1 FROM git_objects c JOIN git_objects t ON t.id=NEW.tree_id WHERE c.id=NEW.object_id AND c.type='commit' AND t.type='tree' AND c.object_format=t.object_format) BEGIN SELECT RAISE(ABORT,'Commit or tree type/format mismatch'); END;
CREATE TRIGGER parent_type_insert BEFORE INSERT ON commit_parents WHEN NOT EXISTS(SELECT 1 FROM git_objects c JOIN git_objects p ON p.id=NEW.parent_id WHERE c.id=NEW.commit_id AND p.type='commit' AND c.object_format=p.object_format) BEGIN SELECT RAISE(ABORT,'Parent type/format mismatch'); END;
CREATE TRIGGER parent_type_update BEFORE UPDATE ON commit_parents WHEN NOT EXISTS(SELECT 1 FROM git_objects c JOIN git_objects p ON p.id=NEW.parent_id WHERE c.id=NEW.commit_id AND p.type='commit' AND c.object_format=p.object_format) BEGIN SELECT RAISE(ABORT,'Parent type/format mismatch'); END;
CREATE TRIGGER tree_type_insert BEFORE INSERT ON tree_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects t WHERE t.id=NEW.tree_id AND t.type='tree' AND t.object_format=NEW.child_format) OR (NEW.child_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects c WHERE c.id=NEW.child_id AND c.object_format=NEW.child_format AND c.oid=NEW.child_oid AND c.type=CASE WHEN NEW.mode=16384 THEN 'tree' ELSE 'blob' END)) BEGIN SELECT RAISE(ABORT,'Tree child type/format/OID mismatch'); END;
CREATE TRIGGER tree_type_update BEFORE UPDATE ON tree_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects t WHERE t.id=NEW.tree_id AND t.type='tree' AND t.object_format=NEW.child_format) OR (NEW.child_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects c WHERE c.id=NEW.child_id AND c.object_format=NEW.child_format AND c.oid=NEW.child_oid AND c.type=CASE WHEN NEW.mode=16384 THEN 'tree' ELSE 'blob' END)) BEGIN SELECT RAISE(ABORT,'Tree child type/format/OID mismatch'); END;
CREATE TRIGGER tag_type_insert BEFORE INSERT ON tag_objects WHEN NOT EXISTS(SELECT 1 FROM git_objects t JOIN git_objects c ON c.id=NEW.target_id WHERE t.id=NEW.object_id AND t.type='tag' AND t.object_format=c.object_format) BEGIN SELECT RAISE(ABORT,'Tag type/format mismatch'); END;
CREATE TRIGGER tag_type_update BEFORE UPDATE ON tag_objects WHEN NOT EXISTS(SELECT 1 FROM git_objects t JOIN git_objects c ON c.id=NEW.target_id WHERE t.id=NEW.object_id AND t.type='tag' AND t.object_format=c.object_format) BEGIN SELECT RAISE(ABORT,'Tag type/format mismatch'); END;
CREATE TRIGGER blob_type_insert BEFORE INSERT ON blob_content_map WHEN NOT EXISTS(SELECT 1 FROM git_objects o JOIN contents c ON c.id=NEW.content_id WHERE o.id=NEW.object_id AND o.type='blob' AND o.size=c.byte_length) BEGIN SELECT RAISE(ABORT,'Blob content type/length mismatch'); END;
CREATE TRIGGER blob_type_update BEFORE UPDATE ON blob_content_map WHEN NOT EXISTS(SELECT 1 FROM git_objects o JOIN contents c ON c.id=NEW.content_id WHERE o.id=NEW.object_id AND o.type='blob' AND o.size=c.byte_length) BEGIN SELECT RAISE(ABORT,'Blob content type/length mismatch'); END;
CREATE TRIGGER manifest_type_insert BEFORE INSERT ON root_manifests WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE id=NEW.tree_id AND type='tree') BEGIN SELECT RAISE(ABORT,'Manifest requires tree'); END;
CREATE TRIGGER manifest_type_update BEFORE UPDATE ON root_manifests WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE id=NEW.tree_id AND type='tree') BEGIN SELECT RAISE(ABORT,'Manifest requires tree'); END;
CREATE TRIGGER manifest_entry_type_insert BEFORE INSERT ON root_manifest_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE id=NEW.tree_id AND type='tree' AND object_format=NEW.object_format) OR (NEW.object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects WHERE id=NEW.object_id AND type='blob' AND oid=NEW.oid AND object_format=NEW.object_format)) BEGIN SELECT RAISE(ABORT,'Manifest type/format/OID mismatch'); END;
CREATE TRIGGER manifest_entry_type_update BEFORE UPDATE ON root_manifest_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE id=NEW.tree_id AND type='tree' AND object_format=NEW.object_format) OR (NEW.object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects WHERE id=NEW.object_id AND type='blob' AND oid=NEW.oid AND object_format=NEW.object_format)) BEGIN SELECT RAISE(ABORT,'Manifest type/format/OID mismatch'); END;
