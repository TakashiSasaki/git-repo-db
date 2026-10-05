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
    UNIQUE(document_id,body_id), UNIQUE(id,document_id)
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
