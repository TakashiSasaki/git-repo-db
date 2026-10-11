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
    schema_version INTEGER NOT NULL CHECK(schema_version=20),
    db_instance_id TEXT NOT NULL,
    local_revision INTEGER NOT NULL CHECK(local_revision>=0),
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
CREATE TABLE change_requests(
change_request_id TEXT PRIMARY KEY, repository_uuidv4 TEXT NOT NULL, repository_binding_id TEXT NOT NULL,
    change_request_kind TEXT NOT NULL CHECK(change_request_kind IN ('pull_request','merge_request')),
    provider_change_request_number INTEGER NOT NULL CHECK(provider_change_request_number>0),
    UNIQUE(repository_binding_id,change_request_kind,provider_change_request_number), UNIQUE(change_request_id,repository_uuidv4),
    FOREIGN KEY(repository_binding_id,repository_uuidv4) REFERENCES repository_bindings(repository_binding_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE text_bodies(
text_body_id INTEGER PRIMARY KEY, body TEXT NOT NULL,
    byte_length INTEGER NOT NULL CHECK(byte_length>=0 AND byte_length=length(CAST(body AS BLOB))),
    sha256 BLOB NOT NULL CHECK(length(sha256)=32), UNIQUE(sha256)
) STRICT;
CREATE TABLE documents(
 change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id),
 kind TEXT NOT NULL CHECK(length(kind)>0 AND kind NOT IN ('review','review-comment')),
 provider_change_request_document_id TEXT NOT NULL CHECK(length(provider_change_request_document_id)>0),
 PRIMARY KEY(change_request_id,kind,provider_change_request_document_id)
) STRICT;
CREATE TABLE review_threads(
 change_request_id TEXT NOT NULL REFERENCES change_requests(change_request_id),
 provider_resource_id TEXT NOT NULL CHECK(length(provider_resource_id)>0),
 PRIMARY KEY(change_request_id,provider_resource_id)
) STRICT;
CREATE TABLE fetch_collections(

fetch_collection_id TEXT PRIMARY KEY, repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, change_request_id TEXT,
    source_id TEXT REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, kind TEXT NOT NULL, resume_scope_id TEXT, observed_at_us INTEGER, scope_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(scope_json) AND json_type(scope_json)='object'),
    UNIQUE(fetch_collection_id,change_request_id),
    FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT,
UNIQUE(fetch_collection_id,repository_uuidv4)
) STRICT;
CREATE TABLE code_listings(
code_listing_id TEXT PRIMARY KEY, change_request_id TEXT NOT NULL,
    fetch_collection_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('commits','files')),
    resume_scope_id TEXT, object_format TEXT CHECK(object_format IN ('sha1','sha256')), head_oid BLOB, base_oid BLOB, CHECK((head_oid IS NULL AND base_oid IS NULL) OR (object_format IS NOT NULL AND object_format='sha1' AND (head_oid IS NULL OR length(head_oid)=20) AND (base_oid IS NULL OR length(base_oid)=20)) OR (object_format IS NOT NULL AND object_format='sha256' AND (head_oid IS NULL OR length(head_oid)=32) AND (base_oid IS NULL OR length(base_oid)=32))),
    UNIQUE(fetch_collection_id,kind), UNIQUE(code_listing_id,change_request_id),
    FOREIGN KEY(fetch_collection_id,change_request_id) REFERENCES fetch_collections(fetch_collection_id,change_request_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE job_attempts(
job_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>=1),
    state TEXT NOT NULL CHECK(state IN ('queued','running','waiting','complete','failed','interrupted','cancelled','unknown')),
    created_at_us INTEGER, updated_at_us INTEGER, not_before_us INTEGER, checkpoint TEXT NOT NULL CHECK(json_valid(checkpoint) AND json_type(checkpoint)='object'), reason TEXT, FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    PRIMARY KEY(job_id,attempt)
) STRICT;
CREATE TABLE source_repositories(
source_id TEXT NOT NULL REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, first_seen_us INTEGER, last_seen_us INTEGER, name TEXT, metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json) AND json_type(metadata_json)='object'), scope_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(scope_json) AND json_type(scope_json)='object'), parser_module TEXT, parser_version TEXT, field_evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(field_evidence_json) AND json_type(field_evidence_json)='object'), PRIMARY KEY(source_id,repository_uuidv4),
    CHECK(first_seen_us IS NULL OR last_seen_us IS NULL OR first_seen_us<=last_seen_us)
) STRICT;
CREATE TABLE jobs(
job_id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('discover','sync','hydrate','index','legacy')), request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'), current_attempt INTEGER, created_at_us INTEGER, FOREIGN KEY(job_id,current_attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE acquisition_progress(
git_acquisition_id TEXT PRIMARY KEY REFERENCES git_acquisitions(git_acquisition_id) ON UPDATE RESTRICT ON DELETE RESTRICT, job_id TEXT NOT NULL, attempt INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('planned','fetching','refs_captured','complete','failed','interrupted','unknown')), generation INTEGER NOT NULL CHECK(generation>=0), ended_at_us INTEGER, active_cache_entry_id TEXT REFERENCES active_cache_entries(active_cache_entry_id) ON UPDATE RESTRICT ON DELETE RESTRICT, FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE collection_progress(
fetch_collection_id TEXT PRIMARY KEY REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, job_id TEXT NOT NULL, attempt INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('running','partial','complete','failed','interrupted','unknown')), cursor TEXT, reason TEXT, FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE resume_scopes(
resume_scope_id TEXT PRIMARY KEY, repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT, repository_binding_id TEXT, source_id TEXT REFERENCES sources(source_id) ON UPDATE RESTRICT ON DELETE RESTRICT, principal_ref TEXT, api_version TEXT, endpoint TEXT, request_context TEXT NOT NULL CHECK(json_valid(request_context) AND json_type(request_context)='object'), parser_version TEXT NOT NULL,  confidence TEXT NOT NULL CHECK(confidence IN ('proven','legacy_unknown')), UNIQUE(resume_scope_id,repository_uuidv4), FOREIGN KEY(repository_binding_id,repository_uuidv4) REFERENCES repository_bindings(repository_binding_id,repository_uuidv4) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE stored_bytes(
sha256 BLOB PRIMARY KEY CHECK(length(sha256)=32), body BLOB NOT NULL,
    byte_length INTEGER NOT NULL CHECK(byte_length>=0 AND byte_length=length(body))
) STRICT;
CREATE TABLE payloads(
representation TEXT NOT NULL CHECK(representation IN ('git-object-raw-v1')),
    sha256 BLOB NOT NULL REFERENCES stored_bytes(sha256) ON UPDATE RESTRICT ON DELETE RESTRICT,
    PRIMARY KEY(representation,sha256)
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
    stored_sha256 BLOB NOT NULL REFERENCES stored_bytes(sha256),
    detected_at_us INTEGER NOT NULL,
    diagnostic_json TEXT NOT NULL CHECK(json_valid(diagnostic_json) AND json_type(diagnostic_json)='object'),
    unresolved_payload_id INTEGER PRIMARY KEY,
    reason TEXT NOT NULL CHECK(reason='physical_corruption')
) STRICT;
CREATE TABLE incremental_scans(
incremental_scan_id TEXT PRIMARY KEY, resume_scope_id TEXT, fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, scan_started_at_us INTEGER, safe_watermark_us INTEGER, evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object'), UNIQUE(incremental_scan_id,resume_scope_id)
) STRICT;
CREATE TABLE resume_cursors(
resume_scope_id TEXT PRIMARY KEY REFERENCES resume_scopes(resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT, incremental_scan_id TEXT, next_cursor TEXT, reusable INTEGER NOT NULL CHECK(reusable IN (0,1)), FOREIGN KEY(incremental_scan_id,resume_scope_id) REFERENCES incremental_scans(incremental_scan_id,resume_scope_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TABLE completion_markers(
completion_marker_uuidv4 TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',(random() & 3)+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
completion_marker_id INTEGER PRIMARY KEY, resume_scope_id TEXT, fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id) ON UPDATE RESTRICT ON DELETE RESTRICT, asserted_state TEXT NOT NULL CHECK(asserted_state IN ('complete','partial','unknown')), evidence TEXT NOT NULL CHECK(json_valid(evidence) AND json_type(evidence)='object'), observed_at_us INTEGER
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
CREATE TABLE code_listing_progress(
code_listing_id TEXT PRIMARY KEY REFERENCES code_listings(code_listing_id) ON UPDATE RESTRICT ON DELETE RESTRICT, state TEXT NOT NULL CHECK(state IN ('partial','complete','unknown')), terminal INTEGER NOT NULL CHECK(terminal IN (0,1)), page_count INTEGER NOT NULL CHECK(page_count>=0), context_proven INTEGER NOT NULL CHECK(context_proven IN (0,1)), CHECK(state!='complete' OR (terminal=1 AND context_proven=1))
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
git_acquisition_id TEXT PRIMARY KEY REFERENCES git_acquisitions(git_acquisition_id) ON UPDATE RESTRICT ON DELETE RESTRICT, cache_locator_id TEXT REFERENCES cache_locators(cache_locator_id) ON UPDATE RESTRICT ON DELETE RESTRICT, roots_fixed INTEGER NOT NULL CHECK(roots_fixed IN (0,1)), structure_done INTEGER NOT NULL CHECK(structure_done IN (0,1)), digest_done INTEGER NOT NULL CHECK(digest_done IN (0,1)), text_done INTEGER NOT NULL CHECK(text_done IN (0,1)), complete INTEGER NOT NULL CHECK(complete IN (0,1))
) STRICT;
CREATE TABLE search_documents(
search_document_id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('code','pr','commits','issue')), source_key TEXT NOT NULL, body TEXT NOT NULL, metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'), UNIQUE(kind,source_key)
) STRICT;
CREATE TABLE index_generations(
index_generation_id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('code','pr','commits','issue')), state TEXT NOT NULL CHECK(state IN ('building','ready','retired','removed','unavailable','failed')), table_name TEXT NOT NULL CHECK(length(table_name)>0 AND table_name NOT GLOB '*[^a-z0-9_]*'), target_max_search_document_id INTEGER NOT NULL CHECK(target_max_search_document_id>=0), created_at_us INTEGER
) STRICT;
CREATE TABLE index_membership(
index_generation_id INTEGER NOT NULL REFERENCES index_generations(index_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT, search_document_id INTEGER NOT NULL REFERENCES search_documents(search_document_id) ON UPDATE RESTRICT ON DELETE RESTRICT, input_version TEXT NOT NULL, PRIMARY KEY(index_generation_id,search_document_id)
) STRICT;
CREATE TRIGGER acquisition_progress_immutable BEFORE UPDATE ON acquisition_progress WHEN NEW.git_acquisition_id IS NOT OLD.git_acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER acquisition_progress_no_replace BEFORE INSERT ON acquisition_progress WHEN EXISTS(SELECT 1 FROM acquisition_progress WHERE (git_acquisition_id=NEW.git_acquisition_id) OR (git_acquisition_id=NEW.git_acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX acquisition_progress_fk_0 ON acquisition_progress(job_id,attempt);
CREATE TRIGGER active_cache_entries_immutable BEFORE UPDATE ON active_cache_entries WHEN NEW.active_cache_entry_id IS NOT OLD.active_cache_entry_id OR NEW.cache_locator_id IS NOT OLD.cache_locator_id OR NEW.generation IS NOT OLD.generation BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER active_cache_entries_no_replace BEFORE INSERT ON active_cache_entries WHEN EXISTS(SELECT 1 FROM active_cache_entries WHERE (active_cache_entry_id=NEW.active_cache_entry_id) OR (active_cache_entry_id=NEW.active_cache_entry_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX active_cache_entries_fk_0 ON active_cache_entries(cache_locator_id);
CREATE TRIGGER cache_leases_immutable BEFORE UPDATE ON cache_leases WHEN NEW.active_cache_entry_id IS NOT OLD.active_cache_entry_id OR NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER cache_leases_no_replace BEFORE INSERT ON cache_leases WHEN EXISTS(SELECT 1 FROM cache_leases WHERE (active_cache_entry_id=NEW.active_cache_entry_id AND job_id=NEW.job_id AND attempt=NEW.attempt) OR (active_cache_entry_id=NEW.active_cache_entry_id AND job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX cache_leases_fk_0 ON cache_leases(job_id,attempt);
CREATE TRIGGER cache_locators_immutable BEFORE UPDATE ON cache_locators WHEN NEW.cache_locator_id IS NOT OLD.cache_locator_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.access IS NOT OLD.access BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER cache_locators_no_replace BEFORE INSERT ON cache_locators WHEN EXISTS(SELECT 1 FROM cache_locators WHERE (cache_locator_id=NEW.cache_locator_id) OR (cache_locator_id=NEW.cache_locator_id AND repository_uuidv4=NEW.repository_uuidv4) OR (cache_locator_id=NEW.cache_locator_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX cache_locators_fk_0 ON cache_locators(repository_uuidv4);
CREATE TRIGGER change_requests_immutable BEFORE UPDATE ON change_requests WHEN NEW.change_request_id IS NOT OLD.change_request_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.repository_binding_id IS NOT OLD.repository_binding_id OR NEW.change_request_kind IS NOT OLD.change_request_kind OR NEW.provider_change_request_number IS NOT OLD.provider_change_request_number BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER change_requests_no_replace BEFORE INSERT ON change_requests WHEN EXISTS(SELECT 1 FROM change_requests WHERE (change_request_id=NEW.change_request_id) OR (change_request_id=NEW.change_request_id AND repository_uuidv4=NEW.repository_uuidv4) OR (repository_binding_id=NEW.repository_binding_id AND change_request_kind=NEW.change_request_kind AND provider_change_request_number=NEW.provider_change_request_number) OR (change_request_id=NEW.change_request_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX change_requests_fk_1 ON change_requests(repository_binding_id,repository_uuidv4);
CREATE TRIGGER code_listing_progress_immutable BEFORE UPDATE ON code_listing_progress WHEN NEW.code_listing_id IS NOT OLD.code_listing_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER code_listing_progress_no_replace BEFORE INSERT ON code_listing_progress WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE (code_listing_id=NEW.code_listing_id) OR (code_listing_id=NEW.code_listing_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_listings_immutable BEFORE UPDATE ON code_listings WHEN NEW.code_listing_id IS NOT OLD.code_listing_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.kind IS NOT OLD.kind OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.object_format IS NOT OLD.object_format OR NEW.head_oid IS NOT OLD.head_oid OR NEW.base_oid IS NOT OLD.base_oid BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER code_listings_no_replace BEFORE INSERT ON code_listings WHEN EXISTS(SELECT 1 FROM code_listings WHERE (code_listing_id=NEW.code_listing_id) OR (code_listing_id=NEW.code_listing_id AND change_request_id=NEW.change_request_id) OR (fetch_collection_id=NEW.fetch_collection_id AND kind=NEW.kind) OR (code_listing_id=NEW.code_listing_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER code_listings_retain BEFORE DELETE ON code_listings BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX code_listings_fk_0 ON code_listings(fetch_collection_id,change_request_id);
CREATE INDEX code_listings_fk_1 ON code_listings(resume_scope_id);
CREATE TRIGGER collection_progress_immutable BEFORE UPDATE ON collection_progress WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER collection_progress_no_replace BEFORE INSERT ON collection_progress WHEN EXISTS(SELECT 1 FROM collection_progress WHERE (fetch_collection_id=NEW.fetch_collection_id) OR (fetch_collection_id=NEW.fetch_collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX collection_progress_fk_0 ON collection_progress(job_id,attempt);
CREATE TRIGGER completion_markers_immutable BEFORE UPDATE ON completion_markers WHEN NEW.completion_marker_uuidv4 IS NOT OLD.completion_marker_uuidv4 OR NEW.completion_marker_id IS NOT OLD.completion_marker_id OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.asserted_state IS NOT OLD.asserted_state OR NEW.evidence IS NOT OLD.evidence OR NEW.observed_at_us IS NOT OLD.observed_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER completion_markers_no_replace BEFORE INSERT ON completion_markers WHEN EXISTS(SELECT 1 FROM completion_markers WHERE (completion_marker_id=NEW.completion_marker_id OR completion_marker_uuidv4=NEW.completion_marker_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER completion_markers_retain BEFORE DELETE ON completion_markers BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX completion_markers_fk_0 ON completion_markers(fetch_collection_id);
CREATE INDEX completion_markers_fk_1 ON completion_markers(resume_scope_id);
CREATE TRIGGER content_locations_immutable BEFORE UPDATE ON content_locations WHEN NEW.content_id IS NOT OLD.content_id OR NEW.kind IS NOT OLD.kind OR NEW.locator IS NOT OLD.locator BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
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
CREATE TRIGGER coverage_scopes_immutable BEFORE UPDATE ON coverage_scopes WHEN NEW.coverage_scope_id IS NOT OLD.coverage_scope_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER coverage_scopes_no_replace BEFORE INSERT ON coverage_scopes WHEN EXISTS(SELECT 1 FROM coverage_scopes WHERE coverage_scope_id=NEW.coverage_scope_id OR (repository_uuidv4=NEW.repository_uuidv4 AND change_request_id IS NEW.change_request_id AND kind=NEW.kind)) BEGIN SELECT RAISE(ABORT,'Duplicate coverage scope'); END;
CREATE INDEX coverage_scopes_fk_1 ON coverage_scopes(change_request_id,repository_uuidv4);
CREATE INDEX coverage_scopes_fk_2 ON coverage_scopes(repository_uuidv4);
CREATE TRIGGER database_identity_immutable BEFORE UPDATE ON database_identity WHEN NEW.singleton IS NOT OLD.singleton OR NEW.format_id IS NOT OLD.format_id OR NEW.schema_version IS NOT OLD.schema_version OR NEW.ddl_sha256 IS NOT OLD.ddl_sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER database_identity_no_replace BEFORE INSERT ON database_identity WHEN EXISTS(SELECT 1 FROM database_identity WHERE (singleton=NEW.singleton)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
-- Remote observation replay and provider-resource relationships are hot per-comment
-- lookups. Keep them indexed as collections/history grow.
CREATE TRIGGER fetch_collections_immutable BEFORE UPDATE ON fetch_collections WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.source_id IS NOT OLD.source_id OR NEW.kind IS NOT OLD.kind OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.observed_at_us IS NOT OLD.observed_at_us OR NEW.scope_json IS NOT OLD.scope_json BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER fetch_collections_no_replace BEFORE INSERT ON fetch_collections WHEN EXISTS(SELECT 1 FROM fetch_collections WHERE (fetch_collection_id=NEW.fetch_collection_id) OR (fetch_collection_id=NEW.fetch_collection_id AND change_request_id=NEW.change_request_id) OR (fetch_collection_id=NEW.fetch_collection_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER fetch_collections_retain BEFORE DELETE ON fetch_collections BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX fetch_collections_fk_0 ON fetch_collections(change_request_id,repository_uuidv4);
CREATE INDEX fetch_collections_fk_1 ON fetch_collections(resume_scope_id);
CREATE INDEX fetch_collections_fk_2 ON fetch_collections(source_id);
CREATE INDEX fetch_collections_fk_3 ON fetch_collections(repository_uuidv4);
CREATE TRIGGER incremental_scans_immutable BEFORE UPDATE ON incremental_scans WHEN NEW.incremental_scan_id IS NOT OLD.incremental_scan_id OR NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.scan_started_at_us IS NOT OLD.scan_started_at_us OR NEW.safe_watermark_us IS NOT OLD.safe_watermark_us OR NEW.evidence IS NOT OLD.evidence BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER incremental_scans_no_replace BEFORE INSERT ON incremental_scans WHEN EXISTS(SELECT 1 FROM incremental_scans WHERE (incremental_scan_id=NEW.incremental_scan_id) OR (incremental_scan_id=NEW.incremental_scan_id AND resume_scope_id=NEW.resume_scope_id) OR (incremental_scan_id=NEW.incremental_scan_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER incremental_scans_retain BEFORE DELETE ON incremental_scans BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX incremental_scans_fk_0 ON incremental_scans(fetch_collection_id);
CREATE INDEX incremental_scans_fk_1 ON incremental_scans(resume_scope_id);
CREATE TRIGGER index_generations_immutable BEFORE UPDATE ON index_generations WHEN NEW.index_generation_id IS NOT OLD.index_generation_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER index_generations_no_replace BEFORE INSERT ON index_generations WHEN EXISTS(SELECT 1 FROM index_generations WHERE (index_generation_id=NEW.index_generation_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER index_membership_immutable BEFORE UPDATE ON index_membership WHEN NEW.index_generation_id IS NOT OLD.index_generation_id OR NEW.search_document_id IS NOT OLD.search_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER index_membership_no_replace BEFORE INSERT ON index_membership WHEN EXISTS(SELECT 1 FROM index_membership WHERE (index_generation_id=NEW.index_generation_id AND search_document_id=NEW.search_document_id) OR (index_generation_id=NEW.index_generation_id AND search_document_id=NEW.search_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX index_membership_fk_0 ON index_membership(search_document_id);
CREATE TRIGGER job_attempts_immutable BEFORE UPDATE ON job_attempts WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER job_attempts_no_replace BEFORE INSERT ON job_attempts WHEN EXISTS(SELECT 1 FROM job_attempts WHERE (job_id=NEW.job_id AND attempt=NEW.attempt) OR (job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER jobs_immutable BEFORE UPDATE ON jobs WHEN NEW.job_id IS NOT OLD.job_id OR NEW.kind IS NOT OLD.kind OR NEW.request IS NOT OLD.request OR NEW.created_at_us IS NOT OLD.created_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER jobs_no_replace BEFORE INSERT ON jobs WHEN EXISTS(SELECT 1 FROM jobs WHERE (job_id=NEW.job_id) OR (job_id=NEW.job_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX jobs_fk_0 ON jobs(job_id,current_attempt);
CREATE TRIGGER stored_bytes_immutable BEFORE UPDATE ON stored_bytes BEGIN SELECT RAISE(ABORT,'Immutable stored bytes'); END;
CREATE TRIGGER stored_bytes_no_replace BEFORE INSERT ON stored_bytes WHEN EXISTS(SELECT 1 FROM stored_bytes WHERE sha256=NEW.sha256) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited'); END;
CREATE TRIGGER stored_bytes_retain BEFORE DELETE ON stored_bytes BEGIN SELECT RAISE(ABORT,'Retain acquired bytes'); END;
CREATE TRIGGER payloads_immutable BEFORE UPDATE ON payloads BEGIN SELECT RAISE(ABORT,'Immutable payload identity'); END;
CREATE TRIGGER payloads_no_replace BEFORE INSERT ON payloads WHEN EXISTS(SELECT 1 FROM payloads WHERE representation=NEW.representation AND sha256=NEW.sha256) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited'); END;
CREATE TRIGGER payloads_retain BEFORE DELETE ON payloads BEGIN SELECT RAISE(ABORT,'Retain acquired payloads'); END;
CREATE INDEX payloads_stored_bytes_fk ON payloads(sha256);
CREATE TRIGGER preservation_obligations_immutable BEFORE UPDATE ON preservation_obligations WHEN NEW.git_acquisition_id IS NOT OLD.git_acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER preservation_obligations_no_replace BEFORE INSERT ON preservation_obligations WHEN EXISTS(SELECT 1 FROM preservation_obligations WHERE (git_acquisition_id=NEW.git_acquisition_id) OR (git_acquisition_id=NEW.git_acquisition_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX preservation_obligations_fk_0 ON preservation_obligations(cache_locator_id);
CREATE TRIGGER repositories_immutable BEFORE UPDATE ON repositories WHEN NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER repositories_no_replace BEFORE INSERT ON repositories WHEN EXISTS(SELECT 1 FROM repositories WHERE (repository_uuidv4=NEW.repository_uuidv4) OR (repository_uuidv4=NEW.repository_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX repositories_fk_1 ON repositories(preferred_repository_endpoint_id,repository_uuidv4);
CREATE TRIGGER repository_bindings_immutable BEFORE UPDATE ON repository_bindings WHEN NEW.repository_binding_id IS NOT OLD.repository_binding_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.service_instance_uuidv4 IS NOT OLD.service_instance_uuidv4 OR (OLD.provider_repository_id IS NOT NULL AND NEW.provider_repository_id IS NOT OLD.provider_repository_id) BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER repository_bindings_no_replace BEFORE INSERT ON repository_bindings WHEN EXISTS(SELECT 1 FROM repository_bindings WHERE (repository_binding_id=NEW.repository_binding_id) OR (repository_binding_id=NEW.repository_binding_id AND repository_uuidv4=NEW.repository_uuidv4) OR (service_instance_uuidv4=NEW.service_instance_uuidv4 AND provider_repository_id=NEW.provider_repository_id) OR (repository_uuidv4=NEW.repository_uuidv4 AND service_instance_uuidv4=NEW.service_instance_uuidv4) OR (repository_binding_id=NEW.repository_binding_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER repository_endpoints_immutable BEFORE UPDATE ON repository_endpoints WHEN NEW.repository_endpoint_id IS NOT OLD.repository_endpoint_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER repository_endpoints_no_replace BEFORE INSERT ON repository_endpoints WHEN EXISTS(SELECT 1 FROM repository_endpoints WHERE (repository_endpoint_id=NEW.repository_endpoint_id) OR (repository_endpoint_id=NEW.repository_endpoint_id AND repository_uuidv4=NEW.repository_uuidv4) OR (repository_uuidv4=NEW.repository_uuidv4 AND url=NEW.url) OR (repository_endpoint_id=NEW.repository_endpoint_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER resume_cursors_immutable BEFORE UPDATE ON resume_cursors WHEN NEW.resume_scope_id IS NOT OLD.resume_scope_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER resume_cursors_no_replace BEFORE INSERT ON resume_cursors WHEN EXISTS(SELECT 1 FROM resume_cursors WHERE (resume_scope_id=NEW.resume_scope_id) OR (resume_scope_id=NEW.resume_scope_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX resume_cursors_fk_0 ON resume_cursors(incremental_scan_id,resume_scope_id);
CREATE TRIGGER resume_scopes_immutable BEFORE UPDATE ON resume_scopes WHEN NEW.resume_scope_id IS NOT OLD.resume_scope_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.repository_binding_id IS NOT OLD.repository_binding_id OR NEW.source_id IS NOT OLD.source_id OR NEW.principal_ref IS NOT OLD.principal_ref OR NEW.api_version IS NOT OLD.api_version OR NEW.endpoint IS NOT OLD.endpoint OR NEW.request_context IS NOT OLD.request_context OR NEW.parser_version IS NOT OLD.parser_version OR NEW.confidence IS NOT OLD.confidence BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER resume_scopes_no_replace BEFORE INSERT ON resume_scopes WHEN EXISTS(SELECT 1 FROM resume_scopes WHERE (resume_scope_id=NEW.resume_scope_id) OR (resume_scope_id=NEW.resume_scope_id AND repository_uuidv4=NEW.repository_uuidv4) OR (resume_scope_id=NEW.resume_scope_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX resume_scopes_fk_0 ON resume_scopes(repository_binding_id,repository_uuidv4);
CREATE INDEX resume_scopes_fk_1 ON resume_scopes(source_id);
CREATE INDEX resume_scopes_fk_2 ON resume_scopes(repository_uuidv4);
CREATE TRIGGER review_threads_no_replace BEFORE INSERT ON review_threads WHEN EXISTS(SELECT 1 FROM review_threads WHERE change_request_id=NEW.change_request_id AND provider_resource_id=NEW.provider_resource_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX review_threads_fk_0 ON review_threads(change_request_id);
CREATE TRIGGER search_documents_immutable BEFORE UPDATE ON search_documents WHEN NEW.search_document_id IS NOT OLD.search_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER search_documents_no_replace BEFORE INSERT ON search_documents WHEN EXISTS(SELECT 1 FROM search_documents WHERE (search_document_id=NEW.search_document_id) OR (kind=NEW.kind AND source_key=NEW.source_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER service_instances_immutable BEFORE UPDATE ON service_instances WHEN NEW.service_instance_uuidv4 IS NOT OLD.service_instance_uuidv4 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER service_instances_no_replace BEFORE INSERT ON service_instances WHEN EXISTS(SELECT 1 FROM service_instances WHERE (service_instance_uuidv4=NEW.service_instance_uuidv4) OR (service_instance_uuidv4=NEW.service_instance_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
-- Pair membership is retained; times are aggregate known min/max, not event rows.
-- NULL may become known, never the reverse. Integer microseconds preserve exact
-- temporal ordering, including observations within the same millisecond.
CREATE TRIGGER source_repositories_immutable BEFORE UPDATE ON source_repositories WHEN NEW.source_id IS NOT OLD.source_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR (OLD.first_seen_us IS NOT NULL AND (NEW.first_seen_us IS NULL OR NEW.first_seen_us>OLD.first_seen_us)) OR (OLD.last_seen_us IS NOT NULL AND (NEW.last_seen_us IS NULL OR NEW.last_seen_us<OLD.last_seen_us)) BEGIN SELECT RAISE(ABORT,'Immutable source pair or aggregate time regression'); END;
CREATE TRIGGER source_repositories_no_replace BEFORE INSERT ON source_repositories WHEN EXISTS(SELECT 1 FROM source_repositories WHERE (source_id=NEW.source_id AND repository_uuidv4=NEW.repository_uuidv4) OR (source_id=NEW.source_id AND repository_uuidv4=NEW.repository_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER source_repositories_retain BEFORE DELETE ON source_repositories BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX source_repositories_fk_0 ON source_repositories(repository_uuidv4);
CREATE TRIGGER sources_immutable BEFORE UPDATE ON sources WHEN NEW.source_id IS NOT OLD.source_id OR NEW.source_registration_uuidv4 IS NOT OLD.source_registration_uuidv4 OR NEW.service_instance_uuidv4 IS NOT OLD.service_instance_uuidv4 OR NEW.discovery_kind IS NOT OLD.discovery_kind BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER sources_no_replace BEFORE INSERT ON sources WHEN EXISTS(SELECT 1 FROM sources WHERE (source_id=NEW.source_id) OR (source_registration_uuidv4=NEW.source_registration_uuidv4)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX sources_fk_0 ON sources(service_instance_uuidv4);
CREATE TRIGGER space_reservations_immutable BEFORE UPDATE ON space_reservations WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER space_reservations_no_replace BEFORE INSERT ON space_reservations WHEN EXISTS(SELECT 1 FROM space_reservations WHERE (job_id=NEW.job_id AND attempt=NEW.attempt) OR (job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER text_bodies_immutable BEFORE UPDATE ON text_bodies WHEN NEW.text_body_id IS NOT OLD.text_body_id OR NEW.body IS NOT OLD.body OR NEW.byte_length IS NOT OLD.byte_length OR NEW.sha256 IS NOT OLD.sha256 BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER text_bodies_no_replace BEFORE INSERT ON text_bodies WHEN EXISTS(SELECT 1 FROM text_bodies WHERE (text_body_id=NEW.text_body_id) OR (sha256=NEW.sha256)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER text_bodies_retain BEFORE DELETE ON text_bodies BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER unresolved_payloads_no_replace BEFORE INSERT ON unresolved_payloads WHEN EXISTS(SELECT 1 FROM unresolved_payloads WHERE (unresolved_payload_id=NEW.unresolved_payload_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER unresolved_payloads_retain BEFORE DELETE ON unresolved_payloads BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER listing_scope_insert BEFORE INSERT ON code_listings WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Listing collection, CR and scope mismatch'); END;
CREATE TRIGGER listing_scope_update BEFORE UPDATE ON code_listings WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Listing collection, CR and scope mismatch'); END;

CREATE TRIGGER listing_no_downgrade BEFORE UPDATE ON code_listing_progress WHEN OLD.state='complete' AND (NEW.state IS NOT OLD.state OR NEW.terminal IS NOT OLD.terminal OR NEW.page_count IS NOT OLD.page_count OR NEW.context_proven IS NOT OLD.context_proven) BEGIN SELECT RAISE(ABORT,'Completed listing is immutable'); END;
-- Completion seals even an unreferenced listing. Deleting and recreating its
-- marker must not reopen it; conflict INSERT/REPLACE is separately prohibited.
CREATE TRIGGER listing_complete_retain BEFORE DELETE ON code_listing_progress WHEN OLD.state='complete' BEGIN SELECT RAISE(ABORT,'Complete listing marker cannot be deleted'); END;
CREATE TRIGGER scan_scope_insert BEFORE INSERT ON incremental_scans WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id) BEGIN SELECT RAISE(ABORT,'Scan scope mismatch'); END;
CREATE TRIGGER scan_scope_update BEFORE UPDATE ON incremental_scans WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id) BEGIN SELECT RAISE(ABORT,'Scan scope mismatch'); END;
CREATE TRIGGER completion_scope_insert BEFORE INSERT ON completion_markers WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id) BEGIN SELECT RAISE(ABORT,'Completion scope mismatch'); END;
CREATE TRIGGER completion_scope_update BEFORE UPDATE ON completion_markers WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id) BEGIN SELECT RAISE(ABORT,'Completion scope mismatch'); END;
CREATE TRIGGER active_locator_insert BEFORE INSERT ON active_cache_entries WHEN NOT EXISTS(SELECT 1 FROM cache_locators WHERE cache_locator_id=NEW.cache_locator_id AND access='target_active') BEGIN SELECT RAISE(ABORT,'Readonly source cache cannot become active'); END;
CREATE TRIGGER active_locator_update BEFORE UPDATE ON active_cache_entries WHEN NOT EXISTS(SELECT 1 FROM cache_locators WHERE cache_locator_id=NEW.cache_locator_id AND access='target_active') BEGIN SELECT RAISE(ABORT,'Readonly source cache cannot become active'); END;


CREATE TRIGGER acquisition_cache_owner_insert BEFORE INSERT ON acquisition_progress WHEN NEW.active_cache_entry_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN active_cache_entries a ON a.active_cache_entry_id=NEW.active_cache_entry_id JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_uuidv4=l.repository_uuidv4 AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Acquisition cache owner mismatch'); END;
CREATE TRIGGER obligation_cache_owner_insert BEFORE INSERT ON preservation_obligations WHEN NEW.cache_locator_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN cache_locators l ON l.cache_locator_id=NEW.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_uuidv4=l.repository_uuidv4 AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Preservation cache owner mismatch'); END;

CREATE TRIGGER acquisition_cache_owner_update BEFORE UPDATE ON acquisition_progress WHEN NEW.active_cache_entry_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN active_cache_entries a ON a.active_cache_entry_id=NEW.active_cache_entry_id JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_uuidv4=l.repository_uuidv4 AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Acquisition cache owner mismatch'); END;
CREATE TRIGGER obligation_cache_owner_update BEFORE UPDATE ON preservation_obligations WHEN NEW.cache_locator_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_acquisitions g JOIN cache_locators l ON l.cache_locator_id=NEW.cache_locator_id WHERE g.git_acquisition_id=NEW.git_acquisition_id AND g.repository_uuidv4=l.repository_uuidv4 AND l.access='target_active') BEGIN SELECT RAISE(ABORT,'Preservation cache owner mismatch'); END;

-- Natural-key documents, immutable observations and direct content identity.
CREATE TRIGGER documents_no_replace BEFORE INSERT ON documents WHEN EXISTS(SELECT 1 FROM documents WHERE (change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER documents_retain BEFORE DELETE ON documents BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE TRIGGER collection_memberships_immutable BEFORE UPDATE ON collection_memberships WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_change_request_document_id IS NOT OLD.provider_change_request_document_id OR NEW.ordinal IS NOT OLD.ordinal BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER collection_memberships_no_replace BEFORE INSERT ON collection_memberships WHEN EXISTS(SELECT 1 FROM collection_memberships WHERE (fetch_collection_id=NEW.fetch_collection_id AND change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_change_request_document_id=NEW.provider_change_request_document_id)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE TRIGGER collection_memberships_retain BEFORE DELETE ON collection_memberships BEGIN SELECT RAISE(ABORT,'Retain acquired and conversion facts'); END;
CREATE INDEX collection_memberships_document_fk ON collection_memberships(change_request_id,kind,provider_change_request_document_id);
CREATE TRIGGER membership_owner_insert BEFORE INSERT ON collection_memberships WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Membership must belong to same CR'); END;
CREATE TRIGGER membership_owner_update BEFORE UPDATE ON collection_memberships WHEN NOT EXISTS(SELECT 1 FROM fetch_collections f WHERE f.fetch_collection_id=NEW.fetch_collection_id AND f.change_request_id=NEW.change_request_id) BEGIN SELECT RAISE(ABORT,'Membership must belong to same CR'); END;
CREATE TRIGGER documents_immutable BEFORE UPDATE ON documents BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER review_threads_immutable BEFORE UPDATE ON review_threads BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER unresolved_payloads_immutable BEFORE UPDATE ON unresolved_payloads BEGIN SELECT RAISE(ABORT,'immutable evidence or identity'); END;
CREATE TRIGGER repositories_portable_uuid4 BEFORE INSERT ON repositories WHEN NOT (length(NEW.repository_uuidv4)=36 AND length(CAST(NEW.repository_uuidv4 AS BLOB))=36 AND substr(NEW.repository_uuidv4,9,1)='-' AND substr(NEW.repository_uuidv4,14,1)='-' AND substr(NEW.repository_uuidv4,19,1)='-' AND substr(NEW.repository_uuidv4,24,1)='-' AND length(replace(NEW.repository_uuidv4,'-',''))=32 AND replace(NEW.repository_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.repository_uuidv4,15,1)='4' AND substr(NEW.repository_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;

CREATE TRIGGER fetch_scope_insert BEFORE INSERT ON fetch_collections
WHEN json_extract(NEW.scope_json,'$.repository_uuidv4') IS NOT NEW.repository_uuidv4 OR json_extract(NEW.scope_json,'$.change_request_id') IS NOT NEW.change_request_id OR coalesce(json_type(NEW.scope_json,'$.endpoint'),'')<>'text'
BEGIN SELECT RAISE(ABORT,'Collection domain scope mismatch'); END;
CREATE TRIGGER fetch_scope_update BEFORE UPDATE ON fetch_collections
WHEN json_extract(NEW.scope_json,'$.repository_uuidv4') IS NOT NEW.repository_uuidv4 OR json_extract(NEW.scope_json,'$.change_request_id') IS NOT NEW.change_request_id OR coalesce(json_type(NEW.scope_json,'$.endpoint'),'')<>'text'
BEGIN SELECT RAISE(ABORT,'Collection domain scope mismatch'); END;

CREATE TRIGGER completion_marker_uuid_insert BEFORE INSERT ON completion_markers
WHEN NOT(length(NEW.completion_marker_uuidv4)=36 AND length(CAST(NEW.completion_marker_uuidv4 AS BLOB))=36 AND NEW.completion_marker_uuidv4=lower(NEW.completion_marker_uuidv4) AND NEW.completion_marker_uuidv4 GLOB '????????-????-4???-[89ab]???-????????????' AND replace(NEW.completion_marker_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*')
BEGIN SELECT RAISE(ABORT,'Completion marker requires canonical UUIDv4'); END;
