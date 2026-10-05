-- Executable design fragment, NOT a production migration or complete schema.
-- The application never loads this file. Tests use only an isolated in-memory DB.
PRAGMA foreign_keys=ON;
CREATE TABLE database_identity(
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    format_id TEXT NOT NULL CHECK(format_id='repo-catalog/catalog3-draft'),
    schema_version INTEGER NOT NULL CHECK(schema_version=3),
    db_instance_id TEXT NOT NULL,
    publication_seq INTEGER NOT NULL CHECK(publication_seq>=0)
) STRICT;
CREATE TABLE service_instances(
    id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('github','gitlab','gitea','forgejo','gitolite','git','other')),
    name TEXT NOT NULL UNIQUE,
    web_base_url TEXT, api_base_url TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object')
) STRICT;
CREATE TABLE sources(
    id TEXT PRIMARY KEY, instance_id TEXT REFERENCES service_instances(id) ON DELETE RESTRICT,
    discovery_kind TEXT NOT NULL CHECK(discovery_kind IN ('manual_git','github_inventory')),
    name TEXT NOT NULL,
    settings TEXT NOT NULL CHECK(json_valid(settings) AND json_type(settings)='object')
) STRICT;
CREATE TABLE repositories(
    id TEXT PRIMARY KEY, name TEXT NOT NULL,
    preferred_endpoint_id TEXT, current_snapshot_id TEXT,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    FOREIGN KEY(preferred_endpoint_id,id) REFERENCES repository_endpoints(id,repo_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(current_snapshot_id,id) REFERENCES snapshots(id,repo_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE repository_bindings(
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE RESTRICT,
    instance_id TEXT NOT NULL REFERENCES service_instances(id) ON DELETE RESTRICT,
    provider_repo_id TEXT CHECK(provider_repo_id IS NULL OR length(provider_repo_id)>0),
    UNIQUE(repo_id,instance_id), UNIQUE(instance_id,provider_repo_id), UNIQUE(id,repo_id)
) STRICT;
CREATE TABLE repository_endpoints(
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE RESTRICT,
    url TEXT NOT NULL CHECK(length(url)>0),
    transport TEXT NOT NULL CHECK(transport IN ('file','https','ssh','other')),
    label TEXT,
    UNIQUE(repo_id,url), UNIQUE(id,repo_id)
) STRICT;
CREATE TABLE git_acquisitions(
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE RESTRICT,
    endpoint_id TEXT, endpoint_url TEXT,
    object_format TEXT CHECK(object_format IN ('sha1','sha256')),
    refs_observed_at TEXT,
    UNIQUE(id,repo_id),
    FOREIGN KEY(endpoint_id,repo_id) REFERENCES repository_endpoints(id,repo_id) ON DELETE RESTRICT
) STRICT;
CREATE TABLE snapshots(
    id TEXT PRIMARY KEY, acquisition_id TEXT NOT NULL UNIQUE,
    repo_id TEXT NOT NULL, published INTEGER NOT NULL CHECK(published IN (0,1)),
    UNIQUE(id,repo_id),
    FOREIGN KEY(acquisition_id,repo_id) REFERENCES git_acquisitions(id,repo_id) ON DELETE RESTRICT
) STRICT;
CREATE TRIGGER snapshot_pointer_published_insert BEFORE INSERT ON repositories
WHEN NEW.current_snapshot_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM snapshots WHERE id=NEW.current_snapshot_id AND repo_id=NEW.id AND published=1
) BEGIN SELECT RAISE(ABORT,'Current snapshot must be published in this repository'); END;
CREATE TRIGGER snapshot_pointer_published_update BEFORE UPDATE OF current_snapshot_id,id ON repositories
WHEN NEW.current_snapshot_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM snapshots WHERE id=NEW.current_snapshot_id AND repo_id=NEW.id AND published=1
) BEGIN SELECT RAISE(ABORT,'Current snapshot must be published in this repository'); END;
CREATE TRIGGER current_snapshot_no_unpublish BEFORE UPDATE OF published ON snapshots
WHEN NEW.published=0 AND EXISTS(SELECT 1 FROM repositories WHERE current_snapshot_id=OLD.id)
BEGIN SELECT RAISE(ABORT,'Clear current pointer before unpublishing'); END;
CREATE TABLE change_requests(
    id TEXT PRIMARY KEY, repo_id TEXT NOT NULL, binding_id TEXT NOT NULL,
    request_kind TEXT NOT NULL CHECK(request_kind IN ('pull_request','merge_request')),
    number INTEGER NOT NULL CHECK(number>0), current_observation_id INTEGER,
    UNIQUE(binding_id,request_kind,number), UNIQUE(id,repo_id),
    FOREIGN KEY(binding_id,repo_id) REFERENCES repository_bindings(id,repo_id) ON DELETE RESTRICT,
    FOREIGN KEY(current_observation_id,id) REFERENCES change_request_observations(id,change_request_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE change_request_observations(
    id INTEGER PRIMARY KEY,
    change_request_id TEXT NOT NULL REFERENCES change_requests(id) ON DELETE RESTRICT,
    observed_at TEXT, published INTEGER NOT NULL CHECK(published IN (0,1)),
    payload TEXT NOT NULL CHECK(json_valid(payload) AND json_type(payload)='object'),
    UNIQUE(id,change_request_id)
) STRICT;
CREATE TRIGGER cr_pointer_published_insert BEFORE INSERT ON change_requests
WHEN NEW.current_observation_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM change_request_observations WHERE id=NEW.current_observation_id AND change_request_id=NEW.id AND published=1
) BEGIN SELECT RAISE(ABORT,'Current CR observation must be published in this CR'); END;
CREATE TRIGGER cr_pointer_published_update BEFORE UPDATE OF current_observation_id,id ON change_requests
WHEN NEW.current_observation_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM change_request_observations WHERE id=NEW.current_observation_id AND change_request_id=NEW.id AND published=1
) BEGIN SELECT RAISE(ABORT,'Current CR observation must be published in this CR'); END;
CREATE TRIGGER current_cr_no_unpublish BEFORE UPDATE OF published ON change_request_observations
WHEN NEW.published=0 AND EXISTS(SELECT 1 FROM change_requests WHERE current_observation_id=OLD.id)
BEGIN SELECT RAISE(ABORT,'Clear current pointer before unpublishing'); END;
CREATE TABLE text_bodies(
    id INTEGER PRIMARY KEY, body TEXT NOT NULL,
    byte_length INTEGER NOT NULL CHECK(byte_length>=0 AND byte_length=length(CAST(body AS BLOB))),
    sha256 BLOB NOT NULL CHECK(length(sha256)=32), UNIQUE(sha256,body)
) STRICT;
CREATE TABLE documents(
    id TEXT PRIMARY KEY,
    change_request_id TEXT NOT NULL REFERENCES change_requests(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL, provider_id TEXT NOT NULL, current_version_id INTEGER,
    deleted INTEGER NOT NULL CHECK(deleted IN (0,1)),
    UNIQUE(id,change_request_id), UNIQUE(change_request_id,kind,provider_id),
    FOREIGN KEY(current_version_id,id) REFERENCES document_versions(id,document_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE document_versions(
    id INTEGER PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    body_id INTEGER NOT NULL REFERENCES text_bodies(id) ON DELETE RESTRICT,
    UNIQUE(id,document_id)
) STRICT;
CREATE TABLE document_observations(
    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL, version_id INTEGER NOT NULL,
    observed_at TEXT, parsed_at TEXT NOT NULL,
    FOREIGN KEY(version_id,document_id) REFERENCES document_versions(id,document_id) ON DELETE RESTRICT
) STRICT;
CREATE TRIGGER document_version_immutable BEFORE UPDATE ON document_versions
BEGIN SELECT RAISE(ABORT,'Create a new document version instead of changing it'); END;
CREATE TRIGGER text_body_immutable BEFORE UPDATE ON text_bodies
BEGIN SELECT RAISE(ABORT,'Shared body bytes and identity are immutable'); END;
CREATE TABLE review_threads(
    id TEXT PRIMARY KEY,
    change_request_id TEXT NOT NULL REFERENCES change_requests(id) ON DELETE RESTRICT,
    UNIQUE(id,change_request_id)
) STRICT;
CREATE TABLE review_comments(
    document_id TEXT PRIMARY KEY, change_request_id TEXT NOT NULL, thread_id TEXT,
    FOREIGN KEY(document_id,change_request_id) REFERENCES documents(id,change_request_id) ON DELETE RESTRICT,
    FOREIGN KEY(thread_id,change_request_id) REFERENCES review_threads(id,change_request_id) ON DELETE RESTRICT
) STRICT;
CREATE TABLE fetch_collections(
    id TEXT PRIMARY KEY, repo_id TEXT NOT NULL REFERENCES repositories(id), change_request_id TEXT,
    state TEXT NOT NULL CHECK(state IN ('running','partial','complete','unknown')),
    UNIQUE(id,change_request_id),
    FOREIGN KEY(change_request_id,repo_id) REFERENCES change_requests(id,repo_id) ON DELETE RESTRICT
) STRICT;
CREATE TABLE code_listings(
    id TEXT PRIMARY KEY, change_request_id TEXT NOT NULL,
    collection_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('commits','files')),
    UNIQUE(collection_id,kind), UNIQUE(id,change_request_id),
    FOREIGN KEY(collection_id,change_request_id) REFERENCES fetch_collections(id,change_request_id) ON DELETE RESTRICT
) STRICT;
CREATE TABLE code_observations(
    id INTEGER PRIMARY KEY, change_request_id TEXT NOT NULL, observation_id INTEGER NOT NULL,
    commit_listing_id TEXT, file_listing_id TEXT,
    state TEXT NOT NULL CHECK(state IN ('pending','partial','complete','unknown')),
    CHECK(state!='complete' OR (commit_listing_id IS NOT NULL AND file_listing_id IS NOT NULL)),
    FOREIGN KEY(observation_id,change_request_id) REFERENCES change_request_observations(id,change_request_id) ON DELETE RESTRICT,
    FOREIGN KEY(commit_listing_id,change_request_id) REFERENCES code_listings(id,change_request_id) ON DELETE RESTRICT,
    FOREIGN KEY(file_listing_id,change_request_id) REFERENCES code_listings(id,change_request_id) ON DELETE RESTRICT
) STRICT;
CREATE TRIGGER code_listing_kinds_insert BEFORE INSERT ON code_observations
WHEN (NEW.commit_listing_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM code_listings WHERE id=NEW.commit_listing_id AND kind='commits' AND change_request_id=NEW.change_request_id
)) OR (NEW.file_listing_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM code_listings WHERE id=NEW.file_listing_id AND kind='files' AND change_request_id=NEW.change_request_id
)) BEGIN SELECT RAISE(ABORT,'Listing kind and CR must match pointer'); END;
CREATE TRIGGER code_listing_kinds_update BEFORE UPDATE OF commit_listing_id,file_listing_id,change_request_id ON code_observations
WHEN (NEW.commit_listing_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM code_listings WHERE id=NEW.commit_listing_id AND kind='commits' AND change_request_id=NEW.change_request_id
)) OR (NEW.file_listing_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM code_listings WHERE id=NEW.file_listing_id AND kind='files' AND change_request_id=NEW.change_request_id
)) BEGIN SELECT RAISE(ABORT,'Listing kind and CR must match pointer'); END;
CREATE TRIGGER listing_referenced_kind_immutable BEFORE UPDATE OF kind ON code_listings
WHEN NEW.kind!=OLD.kind AND EXISTS(
    SELECT 1 FROM code_observations WHERE commit_listing_id=OLD.id OR file_listing_id=OLD.id
) BEGIN SELECT RAISE(ABORT,'Referenced listing kind is immutable'); END;
CREATE TABLE acquisition_roots(
    id INTEGER PRIMARY KEY, acquisition_id TEXT NOT NULL REFERENCES git_acquisitions(id),
    object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
    oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)),
    role TEXT NOT NULL,
    UNIQUE(acquisition_id,object_format,oid,role)
) STRICT;
CREATE TABLE root_origins(
    id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL REFERENCES acquisition_roots(id),
    origin_kind TEXT NOT NULL CHECK(origin_kind IN ('ref','pr_role','legacy_unknown')),
    raw_ref_name BLOB, source_ordinal INTEGER NOT NULL CHECK(source_ordinal>=0),
    UNIQUE(root_id,origin_kind,source_ordinal),
    CHECK(origin_kind!='ref' OR (raw_ref_name IS NOT NULL AND length(raw_ref_name)>0))
) STRICT;
CREATE TABLE job_attempts(
    job_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>=1),
    state TEXT NOT NULL CHECK(state IN ('queued','running','waiting','complete','failed','interrupted','cancelled','unknown')),
    PRIMARY KEY(job_id,attempt)
) STRICT;
-- Required runtime facts, payload/page tables, provenance, coverage, cache,
-- conversion ledger and FTS modules are specified in schema-proposal.md.
-- This fragment verifies the proposed ownership/pointer/listing/root mechanisms.

-- Identity is immutable even while constructing an unpublished fact.
-- Publication is monotonic. REPLACE must not delete/reinsert facts implicitly.
CREATE TRIGGER database_identity_identity_fixed BEFORE UPDATE ON database_identity WHEN NEW.singleton IS NOT OLD.singleton BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER service_instances_identity_fixed BEFORE UPDATE ON service_instances WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER service_instances_no_replace BEFORE INSERT ON service_instances WHEN EXISTS(SELECT 1 FROM service_instances WHERE (name=NEW.name) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER sources_identity_fixed BEFORE UPDATE ON sources WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER sources_no_replace BEFORE INSERT ON sources WHEN EXISTS(SELECT 1 FROM sources WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER repositories_identity_fixed BEFORE UPDATE ON repositories WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER repositories_no_replace BEFORE INSERT ON repositories WHEN EXISTS(SELECT 1 FROM repositories WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER repository_bindings_identity_fixed BEFORE UPDATE ON repository_bindings WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER repository_bindings_no_replace BEFORE INSERT ON repository_bindings WHEN EXISTS(SELECT 1 FROM repository_bindings WHERE (id=NEW.id AND repo_id=NEW.repo_id) OR (instance_id=NEW.instance_id AND provider_repo_id=NEW.provider_repo_id) OR (repo_id=NEW.repo_id AND instance_id=NEW.instance_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER repository_endpoints_identity_fixed BEFORE UPDATE ON repository_endpoints WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER repository_endpoints_no_replace BEFORE INSERT ON repository_endpoints WHEN EXISTS(SELECT 1 FROM repository_endpoints WHERE (id=NEW.id AND repo_id=NEW.repo_id) OR (repo_id=NEW.repo_id AND url=NEW.url) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER git_acquisitions_identity_fixed BEFORE UPDATE ON git_acquisitions WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER git_acquisitions_no_replace BEFORE INSERT ON git_acquisitions WHEN EXISTS(SELECT 1 FROM git_acquisitions WHERE (id=NEW.id AND repo_id=NEW.repo_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER git_acquisitions_no_delete BEFORE DELETE ON git_acquisitions BEGIN SELECT RAISE(ABORT,'Preserve acquired facts'); END;
CREATE TRIGGER git_acquisitions_fact_fixed BEFORE UPDATE ON git_acquisitions BEGIN SELECT RAISE(ABORT,'Append new facts'); END;
CREATE TRIGGER snapshots_identity_fixed BEFORE UPDATE ON snapshots WHEN NEW.id IS NOT OLD.id OR NEW.acquisition_id IS NOT OLD.acquisition_id OR NEW.repo_id IS NOT OLD.repo_id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER snapshots_no_replace BEFORE INSERT ON snapshots WHEN EXISTS(SELECT 1 FROM snapshots WHERE (id=NEW.id AND repo_id=NEW.repo_id) OR (acquisition_id=NEW.acquisition_id) OR (id=NEW.id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER snapshots_no_delete BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT,'Preserve acquired facts'); END;
CREATE TRIGGER snapshot_publication_monotonic BEFORE UPDATE OF published ON snapshots WHEN OLD.published=1 AND NEW.published!=1 BEGIN SELECT RAISE(ABORT,'Publication is monotonic'); END;
CREATE TRIGGER change_requests_identity_fixed BEFORE UPDATE ON change_requests WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER change_requests_no_replace BEFORE INSERT ON change_requests WHEN EXISTS(SELECT 1 FROM change_requests WHERE (id=NEW.id AND repo_id=NEW.repo_id) OR (binding_id=NEW.binding_id AND request_kind=NEW.request_kind AND number=NEW.number) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER change_request_observations_identity_fixed BEFORE UPDATE ON change_request_observations WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER change_request_observations_no_replace BEFORE INSERT ON change_request_observations WHEN EXISTS(SELECT 1 FROM change_request_observations WHERE (id=NEW.id AND change_request_id=NEW.change_request_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER change_request_observations_no_delete BEFORE DELETE ON change_request_observations BEGIN SELECT RAISE(ABORT,'Preserve acquired facts'); END;
CREATE TRIGGER change_request_observations_fact_fixed BEFORE UPDATE ON change_request_observations
WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.observed_at IS NOT OLD.observed_at OR NEW.payload IS NOT OLD.payload OR (OLD.published=1 AND NEW.published!=1)
BEGIN SELECT RAISE(ABORT,'Append new facts; publication is monotonic'); END;
CREATE TRIGGER text_bodies_identity_fixed BEFORE UPDATE ON text_bodies WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER text_bodies_no_replace BEFORE INSERT ON text_bodies WHEN EXISTS(SELECT 1 FROM text_bodies WHERE (sha256=NEW.sha256 AND body=NEW.body) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER text_bodies_no_delete BEFORE DELETE ON text_bodies BEGIN SELECT RAISE(ABORT,'Preserve acquired facts'); END;
CREATE TRIGGER documents_identity_fixed BEFORE UPDATE ON documents WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_id IS NOT OLD.provider_id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER documents_no_replace BEFORE INSERT ON documents WHEN EXISTS(SELECT 1 FROM documents WHERE (change_request_id=NEW.change_request_id AND kind=NEW.kind AND provider_id=NEW.provider_id) OR (id=NEW.id AND change_request_id=NEW.change_request_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER document_versions_identity_fixed BEFORE UPDATE ON document_versions WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER document_versions_no_replace BEFORE INSERT ON document_versions WHEN EXISTS(SELECT 1 FROM document_versions WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER document_versions_no_delete BEFORE DELETE ON document_versions BEGIN SELECT RAISE(ABORT,'Preserve acquired facts'); END;
CREATE TRIGGER document_observations_identity_fixed BEFORE UPDATE ON document_observations WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER document_observations_no_replace BEFORE INSERT ON document_observations WHEN EXISTS(SELECT 1 FROM document_observations WHERE (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER document_observations_no_delete BEFORE DELETE ON document_observations BEGIN SELECT RAISE(ABORT,'Preserve acquired facts'); END;
CREATE TRIGGER document_observations_fact_fixed BEFORE UPDATE ON document_observations BEGIN SELECT RAISE(ABORT,'Append new facts'); END;
CREATE TRIGGER review_threads_identity_fixed BEFORE UPDATE ON review_threads WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER review_threads_no_replace BEFORE INSERT ON review_threads WHEN EXISTS(SELECT 1 FROM review_threads WHERE (id=NEW.id AND change_request_id=NEW.change_request_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER review_comments_identity_fixed BEFORE UPDATE ON review_comments WHEN NEW.document_id IS NOT OLD.document_id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER review_comments_no_replace BEFORE INSERT ON review_comments WHEN EXISTS(SELECT 1 FROM review_comments WHERE (document_id=NEW.document_id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER fetch_collections_identity_fixed BEFORE UPDATE ON fetch_collections WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER fetch_collections_no_replace BEFORE INSERT ON fetch_collections WHEN EXISTS(SELECT 1 FROM fetch_collections WHERE (id=NEW.id AND change_request_id=NEW.change_request_id) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER code_listings_identity_fixed BEFORE UPDATE ON code_listings WHEN NEW.id IS NOT OLD.id OR NEW.change_request_id IS NOT OLD.change_request_id OR NEW.collection_id IS NOT OLD.collection_id OR NEW.kind IS NOT OLD.kind BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER code_listings_no_replace BEFORE INSERT ON code_listings WHEN EXISTS(SELECT 1 FROM code_listings WHERE (id=NEW.id AND change_request_id=NEW.change_request_id) OR (collection_id=NEW.collection_id AND kind=NEW.kind) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER code_listings_no_delete BEFORE DELETE ON code_listings BEGIN SELECT RAISE(ABORT,'Preserve acquired facts'); END;
CREATE TRIGGER code_listings_fact_fixed BEFORE UPDATE ON code_listings BEGIN SELECT RAISE(ABORT,'Append new facts'); END;
CREATE TRIGGER code_observations_identity_fixed BEFORE UPDATE ON code_observations WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER acquisition_roots_identity_fixed BEFORE UPDATE ON acquisition_roots WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER acquisition_roots_no_replace BEFORE INSERT ON acquisition_roots WHEN EXISTS(SELECT 1 FROM acquisition_roots WHERE (acquisition_id=NEW.acquisition_id AND object_format=NEW.object_format AND oid=NEW.oid AND role=NEW.role) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER acquisition_roots_no_delete BEFORE DELETE ON acquisition_roots BEGIN SELECT RAISE(ABORT,'Preserve acquired facts'); END;
CREATE TRIGGER acquisition_roots_fact_fixed BEFORE UPDATE ON acquisition_roots BEGIN SELECT RAISE(ABORT,'Append new facts'); END;
CREATE TRIGGER root_origins_identity_fixed BEFORE UPDATE ON root_origins WHEN NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER root_origins_no_replace BEFORE INSERT ON root_origins WHEN EXISTS(SELECT 1 FROM root_origins WHERE (root_id=NEW.root_id AND origin_kind=NEW.origin_kind AND source_ordinal=NEW.source_ordinal) OR (id=NEW.id)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
CREATE TRIGGER root_origins_no_delete BEFORE DELETE ON root_origins BEGIN SELECT RAISE(ABORT,'Preserve acquired facts'); END;
CREATE TRIGGER root_origins_fact_fixed BEFORE UPDATE ON root_origins BEGIN SELECT RAISE(ABORT,'Append new facts'); END;
CREATE TRIGGER job_attempts_identity_fixed BEFORE UPDATE ON job_attempts WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity or ownership'); END;
CREATE TRIGGER job_attempts_no_replace BEFORE INSERT ON job_attempts WHEN EXISTS(SELECT 1 FROM job_attempts WHERE (job_id=NEW.job_id AND attempt=NEW.attempt)) BEGIN SELECT RAISE(ABORT,'Use explicit update; REPLACE is prohibited'); END;
