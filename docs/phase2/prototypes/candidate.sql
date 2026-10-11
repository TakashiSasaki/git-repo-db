-- DISPOSABLE PROPOSAL ONLY. Never composed by production schema.py.
-- Tags: [A] accepted semantic responsibility, [P] Proposed/Pending Owner Decision,
-- [I] implementation-dependent physical layout, [ALT] alternative described in ADR.
-- No UUID is an HTTP acquisition, parser execution, or resource identity by implication.
PRAGMA foreign_keys=ON;
PRAGMA recursive_triggers=ON;

-- [A/I] Permanent independent portable identities; UUID syntax validated by writer.
CREATE TABLE service_instances(service_uuid TEXT PRIMARY KEY, kind TEXT NOT NULL) STRICT;
CREATE TABLE repositories(repository_uuid TEXT PRIMARY KEY) STRICT;
CREATE TABLE sources(source_uuid TEXT PRIMARY KEY, service_uuid TEXT,
  FOREIGN KEY(service_uuid) REFERENCES service_instances(service_uuid),
  UNIQUE(source_uuid,service_uuid)) STRICT;
CREATE TABLE repository_bindings(binding_uuid TEXT PRIMARY KEY,
  repository_uuid TEXT NOT NULL,service_uuid TEXT NOT NULL,provider_repository_id TEXT,
  FOREIGN KEY(repository_uuid) REFERENCES repositories(repository_uuid),
  FOREIGN KEY(service_uuid) REFERENCES service_instances(service_uuid),
  UNIQUE(binding_uuid,repository_uuid,service_uuid),
  UNIQUE(repository_uuid,service_uuid),UNIQUE(service_uuid,provider_repository_id)) STRICT;
CREATE TABLE repository_endpoints(endpoint_uuid TEXT PRIMARY KEY,
  repository_uuid TEXT NOT NULL,url TEXT NOT NULL,
  FOREIGN KEY(repository_uuid) REFERENCES repositories(repository_uuid),
  UNIQUE(endpoint_uuid,repository_uuid)) STRICT;
CREATE TABLE source_repositories(source_uuid TEXT NOT NULL,repository_uuid TEXT NOT NULL,
  PRIMARY KEY(source_uuid,repository_uuid),
  FOREIGN KEY(source_uuid) REFERENCES sources(source_uuid),
  FOREIGN KEY(repository_uuid) REFERENCES repositories(repository_uuid)) STRICT;
CREATE TABLE identity_relations(relation_uuid TEXT PRIMARY KEY,
  left_repository_uuid TEXT NOT NULL,right_repository_uuid TEXT NOT NULL,
  assertion TEXT NOT NULL,observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(left_repository_uuid) REFERENCES repositories(repository_uuid),
  FOREIGN KEY(right_repository_uuid) REFERENCES repositories(repository_uuid)) STRICT;
CREATE TABLE identity_relation_cancellations(relation_uuid TEXT NOT NULL,
  cancellation_uuid TEXT PRIMARY KEY,observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(relation_uuid) REFERENCES identity_relations(relation_uuid)) STRICT;

-- [A/I] Exact retained bytes. No decoded_api representation or mandatory archive.
-- Physical layout is illustrative; reuse of existing stored_bytes is feasible.
CREATE TABLE domain_bytes(sha256 BLOB PRIMARY KEY CHECK(length(sha256)=32),
  body BLOB NOT NULL,byte_length INTEGER NOT NULL CHECK(byte_length=length(body))) STRICT;
CREATE TRIGGER domain_bytes_identity BEFORE INSERT ON domain_bytes BEGIN
  SELECT CASE WHEN sha256(NEW.body)<>NEW.sha256 THEN RAISE(ABORT,'content digest') END;
END;
CREATE TABLE text_bodies(sha256 BLOB PRIMARY KEY,
  FOREIGN KEY(sha256) REFERENCES domain_bytes(sha256)) STRICT;
CREATE TRIGGER text_utf8 BEFORE INSERT ON text_bodies BEGIN
  SELECT CASE WHEN valid_utf8((SELECT body FROM domain_bytes WHERE sha256=NEW.sha256))<>1
    THEN RAISE(ABORT,'UTF-8') END;
END;
CREATE TABLE git_objects(object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
  oid BLOB NOT NULL,type TEXT NOT NULL CHECK(type IN ('blob','tree','commit','tag')),
  size INTEGER NOT NULL CHECK(size>=0),sha256 BLOB NOT NULL,
  PRIMARY KEY(object_format,oid),FOREIGN KEY(sha256) REFERENCES domain_bytes(sha256),
  CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32))) STRICT;
CREATE TRIGGER git_object_identity BEFORE INSERT ON git_objects BEGIN
  SELECT CASE WHEN valid_git(NEW.object_format,NEW.oid,NEW.type,NEW.size,
    (SELECT body FROM domain_bytes WHERE sha256=NEW.sha256))<>1
    THEN RAISE(ABORT,'Git identity') END;
END;
-- [A/I] CAS-41 physical quarantine and diagnostics survive. No deletion/GC policy.
CREATE TABLE unresolved_content(diagnostic_uuid TEXT PRIMARY KEY,sha256 BLOB NOT NULL,
  reason TEXT NOT NULL,diagnosed_at_us INTEGER NOT NULL,
  FOREIGN KEY(sha256) REFERENCES domain_bytes(sha256),UNIQUE(diagnostic_uuid,sha256)) STRICT;
CREATE TABLE payload_quarantine(sha256 BLOB PRIMARY KEY,diagnostic_uuid TEXT NOT NULL,
  FOREIGN KEY(diagnostic_uuid,sha256) REFERENCES unresolved_content(diagnostic_uuid,sha256)) STRICT;

-- [P Q04] Separate owner kinds make nullable XOR foreign-key bypass impossible.
-- Publication is a domain bundle; seal does not imply collection completeness.
CREATE TABLE repository_publications(publication_uuid TEXT PRIMARY KEY,
  repository_uuid TEXT NOT NULL,source_uuid TEXT,
  observed_at_us INTEGER NOT NULL,module TEXT NOT NULL,version TEXT NOT NULL,
  FOREIGN KEY(repository_uuid) REFERENCES repositories(repository_uuid),
  FOREIGN KEY(source_uuid,repository_uuid) REFERENCES source_repositories(source_uuid,repository_uuid),
  UNIQUE(publication_uuid,repository_uuid)) STRICT;
CREATE TABLE source_publications(publication_uuid TEXT PRIMARY KEY,source_uuid TEXT NOT NULL,
  observed_at_us INTEGER NOT NULL,module TEXT NOT NULL,version TEXT NOT NULL,
  FOREIGN KEY(source_uuid) REFERENCES sources(source_uuid),UNIQUE(publication_uuid,source_uuid)) STRICT;
CREATE TABLE repository_publication_seals(publication_uuid TEXT PRIMARY KEY,
  repository_uuid TEXT NOT NULL,member_count INTEGER NOT NULL CHECK(member_count>=0),
  member_digest BLOB NOT NULL CHECK(length(member_digest)=32),sealed_at_us INTEGER NOT NULL,
  FOREIGN KEY(publication_uuid,repository_uuid) REFERENCES repository_publications(publication_uuid,repository_uuid)) STRICT;
CREATE TABLE source_publication_seals(publication_uuid TEXT PRIMARY KEY,
  source_uuid TEXT NOT NULL,member_count INTEGER NOT NULL CHECK(member_count>=0),
  member_digest BLOB NOT NULL CHECK(length(member_digest)=32),sealed_at_us INTEGER NOT NULL,
  FOREIGN KEY(publication_uuid,source_uuid) REFERENCES source_publications(publication_uuid,source_uuid)) STRICT;

-- [A/I] Resource identity. [P Q01/Q09] Explicit historical retained fields.
CREATE TABLE change_requests(change_request_id TEXT PRIMARY KEY,
  repository_uuid TEXT NOT NULL,binding_uuid TEXT NOT NULL,service_uuid TEXT NOT NULL,
  provider_number INTEGER NOT NULL,kind TEXT NOT NULL,
  FOREIGN KEY(binding_uuid,repository_uuid,service_uuid)
    REFERENCES repository_bindings(binding_uuid,repository_uuid,service_uuid),
  UNIQUE(change_request_id,repository_uuid),UNIQUE(binding_uuid,kind,provider_number)) STRICT;
CREATE TABLE change_request_observations(observation_uuid TEXT PRIMARY KEY,
  change_request_id TEXT NOT NULL,repository_uuid TEXT NOT NULL,publication_uuid TEXT NOT NULL,
  observed_at_us INTEGER NOT NULL,clock_scope TEXT,provider_clock_us INTEGER,
  module TEXT NOT NULL,version TEXT NOT NULL,state_digest BLOB NOT NULL CHECK(length(state_digest)=32),
  title TEXT,state TEXT,draft INTEGER CHECK(draft IN (0,1)),head_oid BLOB,base_oid BLOB,
  FOREIGN KEY(change_request_id,repository_uuid) REFERENCES change_requests(change_request_id,repository_uuid),
  FOREIGN KEY(publication_uuid,repository_uuid) REFERENCES repository_publications(publication_uuid,repository_uuid),
  CHECK((clock_scope IS NULL)=(provider_clock_us IS NULL)),
  UNIQUE(observation_uuid,repository_uuid),UNIQUE(observation_uuid,change_request_id,repository_uuid)) STRICT;
CREATE INDEX pr_comparable_clock ON change_request_observations(change_request_id,clock_scope,provider_clock_us);
-- [A] Compound natural document identity, no document surrogate/version identity.
CREATE TABLE documents(change_request_id TEXT NOT NULL,kind TEXT NOT NULL,
  provider_document_id TEXT NOT NULL,repository_uuid TEXT NOT NULL,
  PRIMARY KEY(change_request_id,kind,provider_document_id),
  FOREIGN KEY(change_request_id,repository_uuid) REFERENCES change_requests(change_request_id,repository_uuid),
  UNIQUE(change_request_id,kind,provider_document_id,repository_uuid)) STRICT;
-- [P Q02/Q09] Domain observation is distinct from document identity.
CREATE TABLE document_observations(observation_uuid TEXT PRIMARY KEY,
  change_request_id TEXT NOT NULL,kind TEXT NOT NULL,provider_document_id TEXT NOT NULL,
  repository_uuid TEXT NOT NULL,publication_uuid TEXT NOT NULL,body_sha256 BLOB,
  body_state TEXT NOT NULL CHECK(body_state IN ('present','null','missing','inaccessible')),
  observed_at_us INTEGER NOT NULL,clock_scope TEXT,provider_clock_us INTEGER,
  author_provider_id TEXT,module TEXT NOT NULL,version TEXT NOT NULL,
  state_digest BLOB NOT NULL CHECK(length(state_digest)=32),
  FOREIGN KEY(change_request_id,kind,provider_document_id,repository_uuid)
    REFERENCES documents(change_request_id,kind,provider_document_id,repository_uuid),
  FOREIGN KEY(publication_uuid,repository_uuid) REFERENCES repository_publications(publication_uuid,repository_uuid),
  FOREIGN KEY(body_sha256) REFERENCES text_bodies(sha256),
  CHECK((body_state='present' AND body_sha256 IS NOT NULL) OR (body_state<>'present' AND body_sha256 IS NULL)),
  CHECK((clock_scope IS NULL)=(provider_clock_us IS NULL)),UNIQUE(observation_uuid,repository_uuid)) STRICT;
CREATE TABLE change_request_events(event_uuid TEXT PRIMARY KEY,change_request_id TEXT NOT NULL,
  repository_uuid TEXT NOT NULL,publication_uuid TEXT NOT NULL,provider_event_id TEXT,
  event_kind TEXT NOT NULL,occurred_at_us INTEGER,observed_at_us INTEGER NOT NULL,
  module TEXT NOT NULL,version TEXT NOT NULL,
  FOREIGN KEY(change_request_id,repository_uuid) REFERENCES change_requests(change_request_id,repository_uuid),
  FOREIGN KEY(publication_uuid,repository_uuid) REFERENCES repository_publications(publication_uuid,repository_uuid)) STRICT;
CREATE TABLE review_threads(thread_id TEXT PRIMARY KEY,change_request_id TEXT NOT NULL,
  repository_uuid TEXT NOT NULL,provider_thread_id TEXT NOT NULL,
  FOREIGN KEY(change_request_id,repository_uuid) REFERENCES change_requests(change_request_id,repository_uuid),
  UNIQUE(thread_id,repository_uuid),UNIQUE(change_request_id,provider_thread_id)) STRICT;
CREATE TABLE review_thread_observations(observation_uuid TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,repository_uuid TEXT NOT NULL,publication_uuid TEXT NOT NULL,
  observed_at_us INTEGER NOT NULL,resolved INTEGER CHECK(resolved IN (0,1)),
  module TEXT NOT NULL,version TEXT NOT NULL,state_digest BLOB NOT NULL CHECK(length(state_digest)=32),
  FOREIGN KEY(thread_id,repository_uuid) REFERENCES review_threads(thread_id,repository_uuid),
  FOREIGN KEY(publication_uuid,repository_uuid) REFERENCES repository_publications(publication_uuid,repository_uuid),
  UNIQUE(observation_uuid,repository_uuid)) STRICT;
-- [P Q03/Q09] Source-owned facts can concern a repository without changing owner.
CREATE TABLE repository_inventory_observations(observation_uuid TEXT PRIMARY KEY,
  source_uuid TEXT NOT NULL,publication_uuid TEXT NOT NULL,service_uuid TEXT NOT NULL,
  provider_repository_id TEXT NOT NULL,observed_at_us INTEGER NOT NULL,
  provider_name TEXT,clone_url TEXT,is_private INTEGER CHECK(is_private IN (0,1)),
  module TEXT NOT NULL,version TEXT NOT NULL,state_digest BLOB NOT NULL CHECK(length(state_digest)=32),
  FOREIGN KEY(source_uuid,service_uuid) REFERENCES sources(source_uuid,service_uuid),
  FOREIGN KEY(publication_uuid,source_uuid) REFERENCES source_publications(publication_uuid,source_uuid),
  UNIQUE(observation_uuid,source_uuid)) STRICT;
CREATE TABLE repository_name_observations(observation_uuid TEXT PRIMARY KEY,
  source_uuid TEXT NOT NULL,inventory_observation_uuid TEXT NOT NULL,provider_name TEXT NOT NULL,
  FOREIGN KEY(inventory_observation_uuid,source_uuid) REFERENCES repository_inventory_observations(observation_uuid,source_uuid)) STRICT;

-- [P Q09/I] Field cells model missing/null/empty distinctly; absence means missing.
-- value_json is ONE modeled typed domain value, never an original response.
-- unchanged never stored as a replacement; writer preserves the original cell.
-- Prototype field registry is deliberately only title/head_oid/body. Approval of
-- F01-F19 would generate closed path/type contracts for every retained family.
CREATE TABLE pr_observation_fields(observation_uuid TEXT NOT NULL,
  path TEXT NOT NULL CHECK(path IN ('title','head_oid','body')),
  state TEXT NOT NULL CHECK(state IN ('null','value')),value_json TEXT,
  origin_observation_uuid TEXT NOT NULL,module TEXT NOT NULL,version TEXT NOT NULL,
  PRIMARY KEY(observation_uuid,path),
  FOREIGN KEY(observation_uuid) REFERENCES change_request_observations(observation_uuid),
  FOREIGN KEY(origin_observation_uuid) REFERENCES change_request_observations(observation_uuid),
  CHECK((state='null' AND value_json IS NULL) OR
    (state='value' AND value_json IS NOT NULL AND json_valid(value_json) AND json_type(value_json)='text'))) STRICT;

-- [P Q05/Q06] Collection scope, observation, fragment, members, terminal and seal
-- are separate. No HTTP cursor/header/request/response hashes in these tables.
CREATE TABLE repository_collection_scopes(scope_uuid TEXT PRIMARY KEY,
  repository_uuid TEXT NOT NULL,kind TEXT NOT NULL,change_request_id TEXT,thread_id TEXT,
  FOREIGN KEY(repository_uuid) REFERENCES repositories(repository_uuid),
  FOREIGN KEY(change_request_id,repository_uuid) REFERENCES change_requests(change_request_id,repository_uuid),
  FOREIGN KEY(thread_id,repository_uuid) REFERENCES review_threads(thread_id,repository_uuid),
  UNIQUE(scope_uuid,repository_uuid)) STRICT;
CREATE TABLE repository_collection_observations(collection_uuid TEXT PRIMARY KEY,
  scope_uuid TEXT NOT NULL,repository_uuid TEXT NOT NULL,publication_uuid TEXT NOT NULL,
  observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(scope_uuid,repository_uuid) REFERENCES repository_collection_scopes(scope_uuid,repository_uuid),
  FOREIGN KEY(publication_uuid,repository_uuid) REFERENCES repository_publications(publication_uuid,repository_uuid),
  UNIQUE(collection_uuid,repository_uuid)) STRICT;
CREATE TABLE repository_collection_fragments(collection_uuid TEXT NOT NULL,
  repository_uuid TEXT NOT NULL,ordinal INTEGER NOT NULL CHECK(ordinal>=0),
  observed_at_us INTEGER NOT NULL,module TEXT NOT NULL,version TEXT NOT NULL,
  member_count INTEGER NOT NULL CHECK(member_count>=0),member_digest BLOB NOT NULL CHECK(length(member_digest)=32),
  PRIMARY KEY(collection_uuid,ordinal),
  FOREIGN KEY(collection_uuid,repository_uuid) REFERENCES repository_collection_observations(collection_uuid,repository_uuid),
  UNIQUE(collection_uuid,ordinal,repository_uuid)) STRICT;
-- Membership tables are typed; a generic target_table/target_id is excluded.
CREATE TABLE pr_collection_members(collection_uuid TEXT NOT NULL,ordinal INTEGER NOT NULL,
  position INTEGER NOT NULL CHECK(position>=0),repository_uuid TEXT NOT NULL,
  observation_uuid TEXT NOT NULL,state_digest BLOB NOT NULL CHECK(length(state_digest)=32),
  PRIMARY KEY(collection_uuid,ordinal,position),UNIQUE(collection_uuid,observation_uuid),
  FOREIGN KEY(collection_uuid,ordinal,repository_uuid) REFERENCES repository_collection_fragments(collection_uuid,ordinal,repository_uuid),
  FOREIGN KEY(observation_uuid,repository_uuid) REFERENCES change_request_observations(observation_uuid,repository_uuid)) STRICT;
CREATE TABLE document_collection_members(collection_uuid TEXT NOT NULL,ordinal INTEGER NOT NULL,
  position INTEGER NOT NULL CHECK(position>=0),repository_uuid TEXT NOT NULL,
  observation_uuid TEXT NOT NULL,state_digest BLOB NOT NULL CHECK(length(state_digest)=32),
  PRIMARY KEY(collection_uuid,ordinal,position),UNIQUE(collection_uuid,observation_uuid),
  FOREIGN KEY(collection_uuid,ordinal,repository_uuid) REFERENCES repository_collection_fragments(collection_uuid,ordinal,repository_uuid),
  FOREIGN KEY(observation_uuid,repository_uuid) REFERENCES document_observations(observation_uuid,repository_uuid)) STRICT;
-- [A/P Q05/I] Current review receipt attests observed digest and stable identity.
-- It does not retain an edit history or require today's value to match old digest.
CREATE TABLE review_receipt_members(collection_uuid TEXT NOT NULL,ordinal INTEGER NOT NULL,
  position INTEGER NOT NULL CHECK(position>=0),repository_uuid TEXT NOT NULL,
  change_request_id TEXT NOT NULL,kind TEXT NOT NULL,provider_document_id TEXT NOT NULL,
  captured_thread_id TEXT NOT NULL,
  observed_state_digest BLOB NOT NULL CHECK(length(observed_state_digest)=32),
  PRIMARY KEY(collection_uuid,ordinal,position),
  FOREIGN KEY(collection_uuid,ordinal,repository_uuid) REFERENCES repository_collection_fragments(collection_uuid,ordinal,repository_uuid),
  FOREIGN KEY(captured_thread_id,repository_uuid) REFERENCES review_threads(thread_id,repository_uuid),
  FOREIGN KEY(change_request_id,kind,provider_document_id) REFERENCES review_resources(change_request_id,kind,provider_document_id)) STRICT;
CREATE TABLE thread_collection_members(collection_uuid TEXT NOT NULL,ordinal INTEGER NOT NULL,
  position INTEGER NOT NULL CHECK(position>=0),repository_uuid TEXT NOT NULL,
  observation_uuid TEXT NOT NULL,state_digest BLOB NOT NULL CHECK(length(state_digest)=32),
  PRIMARY KEY(collection_uuid,ordinal,position),UNIQUE(collection_uuid,observation_uuid),
  FOREIGN KEY(collection_uuid,ordinal,repository_uuid) REFERENCES repository_collection_fragments(collection_uuid,ordinal,repository_uuid),
  FOREIGN KEY(observation_uuid,repository_uuid) REFERENCES review_thread_observations(observation_uuid,repository_uuid)) STRICT;
CREATE TABLE repository_collection_terminals(collection_uuid TEXT PRIMARY KEY,
  repository_uuid TEXT NOT NULL,last_ordinal INTEGER NOT NULL CHECK(last_ordinal>=0),
  observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(collection_uuid,last_ordinal,repository_uuid) REFERENCES repository_collection_fragments(collection_uuid,ordinal,repository_uuid)) STRICT;
CREATE TABLE collection_child_obligations(parent_collection_uuid TEXT NOT NULL,
  parent_ordinal INTEGER NOT NULL,parent_position INTEGER NOT NULL,repository_uuid TEXT NOT NULL,
  child_collection_uuid TEXT NOT NULL,required_role TEXT NOT NULL,
  PRIMARY KEY(parent_collection_uuid,parent_ordinal,parent_position,required_role),
  FOREIGN KEY(parent_collection_uuid,parent_ordinal,parent_position) REFERENCES thread_collection_members(collection_uuid,ordinal,position),
  FOREIGN KEY(parent_collection_uuid,repository_uuid) REFERENCES repository_collection_observations(collection_uuid,repository_uuid),
  FOREIGN KEY(child_collection_uuid,repository_uuid) REFERENCES repository_collection_observations(collection_uuid,repository_uuid),
  CHECK(parent_collection_uuid<>child_collection_uuid)) STRICT;
CREATE TABLE repository_collection_seals(collection_uuid TEXT PRIMARY KEY,
  repository_uuid TEXT NOT NULL,member_count INTEGER NOT NULL CHECK(member_count>=0),
  member_digest BLOB NOT NULL CHECK(length(member_digest)=32),
  required_child_count INTEGER NOT NULL CHECK(required_child_count>=0),
  required_child_digest BLOB NOT NULL CHECK(length(required_child_digest)=32),observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(collection_uuid,repository_uuid) REFERENCES repository_collection_observations(collection_uuid,repository_uuid),
  FOREIGN KEY(collection_uuid) REFERENCES repository_collection_terminals(collection_uuid)) STRICT;
CREATE INDEX required_children ON collection_child_obligations(child_collection_uuid);
-- SQL handles local shape. Manifest digests, exact required-child set, cycles,
-- observation immutability, scope-kind and semantic validation belong to executable
-- validator below; a seal cannot be admitted merely because these FKs pass.

-- [P Q03/Q05] Source completeness follows same concepts with independently typed scope.
CREATE TABLE source_collection_scopes(scope_uuid TEXT PRIMARY KEY,source_uuid TEXT NOT NULL,kind TEXT NOT NULL,
  principal_scope TEXT NOT NULL,visibility_scope TEXT NOT NULL,query_contract TEXT NOT NULL,
  -- Named, nonsecret captured scope attributes. Their vocabulary/comparability
  -- remains Q03/Q09; never compare scans solely because they share a Source.
  FOREIGN KEY(source_uuid) REFERENCES sources(source_uuid),UNIQUE(scope_uuid,source_uuid)) STRICT;
CREATE TABLE source_collection_observations(collection_uuid TEXT PRIMARY KEY,
  scope_uuid TEXT NOT NULL,source_uuid TEXT NOT NULL,publication_uuid TEXT NOT NULL,observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(scope_uuid,source_uuid) REFERENCES source_collection_scopes(scope_uuid,source_uuid),
  FOREIGN KEY(publication_uuid,source_uuid) REFERENCES source_publications(publication_uuid,source_uuid),UNIQUE(collection_uuid,source_uuid)) STRICT;
CREATE TABLE source_collection_fragments(collection_uuid TEXT NOT NULL,ordinal INTEGER NOT NULL CHECK(ordinal>=0),
  source_uuid TEXT NOT NULL,member_count INTEGER NOT NULL CHECK(member_count>=0),member_digest BLOB NOT NULL CHECK(length(member_digest)=32),
  PRIMARY KEY(collection_uuid,ordinal),FOREIGN KEY(collection_uuid,source_uuid) REFERENCES source_collection_observations(collection_uuid,source_uuid),
  UNIQUE(collection_uuid,ordinal,source_uuid)) STRICT;
CREATE TABLE inventory_collection_members(collection_uuid TEXT NOT NULL,ordinal INTEGER NOT NULL,position INTEGER NOT NULL CHECK(position>=0),
  source_uuid TEXT NOT NULL,observation_uuid TEXT NOT NULL,state_digest BLOB NOT NULL CHECK(length(state_digest)=32),
  PRIMARY KEY(collection_uuid,ordinal,position),UNIQUE(collection_uuid,observation_uuid),
  FOREIGN KEY(collection_uuid,ordinal,source_uuid) REFERENCES source_collection_fragments(collection_uuid,ordinal,source_uuid),
  FOREIGN KEY(observation_uuid,source_uuid) REFERENCES repository_inventory_observations(observation_uuid,source_uuid)) STRICT;
CREATE TABLE source_collection_terminals(collection_uuid TEXT PRIMARY KEY,source_uuid TEXT NOT NULL,last_ordinal INTEGER NOT NULL,
  FOREIGN KEY(collection_uuid,last_ordinal,source_uuid) REFERENCES source_collection_fragments(collection_uuid,ordinal,source_uuid)) STRICT;
CREATE TABLE source_collection_seals(collection_uuid TEXT PRIMARY KEY,source_uuid TEXT NOT NULL,
  member_count INTEGER NOT NULL,member_digest BLOB NOT NULL CHECK(length(member_digest)=32),observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(collection_uuid,source_uuid) REFERENCES source_collection_observations(collection_uuid,source_uuid),
  FOREIGN KEY(collection_uuid) REFERENCES source_collection_terminals(collection_uuid)) STRICT;

-- [A/P Q08] Git content retained; immutable decoded facts/publication selection proposed.
CREATE TABLE git_acquisitions(acquisition_uuid TEXT PRIMARY KEY,repository_uuid TEXT NOT NULL,
  source_uuid TEXT,endpoint_uuid TEXT,observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(repository_uuid) REFERENCES repositories(repository_uuid),
  FOREIGN KEY(source_uuid,repository_uuid) REFERENCES source_repositories(source_uuid,repository_uuid),
  FOREIGN KEY(endpoint_uuid,repository_uuid) REFERENCES repository_endpoints(endpoint_uuid,repository_uuid),UNIQUE(acquisition_uuid,repository_uuid)) STRICT;
CREATE TABLE git_acquisition_objects(acquisition_uuid TEXT NOT NULL,object_format TEXT NOT NULL,oid BLOB NOT NULL,
  PRIMARY KEY(acquisition_uuid,object_format,oid),FOREIGN KEY(acquisition_uuid) REFERENCES git_acquisitions(acquisition_uuid),
  FOREIGN KEY(object_format,oid) REFERENCES git_objects(object_format,oid)) STRICT;
CREATE TABLE git_interpretations(interpretation_uuid TEXT PRIMARY KEY,
  acquisition_uuid TEXT NOT NULL,repository_uuid TEXT NOT NULL,publication_uuid TEXT NOT NULL,
  module TEXT NOT NULL,version TEXT NOT NULL,
  FOREIGN KEY(acquisition_uuid,repository_uuid) REFERENCES git_acquisitions(acquisition_uuid,repository_uuid),
  FOREIGN KEY(publication_uuid,repository_uuid) REFERENCES repository_publications(publication_uuid,repository_uuid),
  UNIQUE(interpretation_uuid,repository_uuid)) STRICT;
CREATE TABLE commits(interpretation_uuid TEXT NOT NULL,object_format TEXT NOT NULL,oid BLOB NOT NULL,
  tree_oid BLOB NOT NULL,authored_at_us INTEGER,committed_at_us INTEGER,
  message_sha256 BLOB,PRIMARY KEY(interpretation_uuid,object_format,oid),
  FOREIGN KEY(interpretation_uuid) REFERENCES git_interpretations(interpretation_uuid),
  FOREIGN KEY(object_format,oid) REFERENCES git_objects(object_format,oid),FOREIGN KEY(message_sha256) REFERENCES text_bodies(sha256)) STRICT;
CREATE TABLE commit_parents(interpretation_uuid TEXT NOT NULL,object_format TEXT NOT NULL,oid BLOB NOT NULL,
  ordinal INTEGER NOT NULL,parent_oid BLOB NOT NULL,PRIMARY KEY(interpretation_uuid,object_format,oid,ordinal),
  FOREIGN KEY(interpretation_uuid,object_format,oid) REFERENCES commits(interpretation_uuid,object_format,oid),
  FOREIGN KEY(object_format,parent_oid) REFERENCES git_objects(object_format,oid)) STRICT;
CREATE TABLE tree_entries(interpretation_uuid TEXT NOT NULL,object_format TEXT NOT NULL,tree_oid BLOB NOT NULL,
  raw_name BLOB NOT NULL,mode INTEGER NOT NULL,child_oid BLOB NOT NULL,retained_child_oid BLOB,
  PRIMARY KEY(interpretation_uuid,object_format,tree_oid,raw_name),
  FOREIGN KEY(interpretation_uuid) REFERENCES git_interpretations(interpretation_uuid),
  FOREIGN KEY(object_format,tree_oid) REFERENCES git_objects(object_format,oid),
  FOREIGN KEY(object_format,retained_child_oid) REFERENCES git_objects(object_format,oid),
  CHECK(retained_child_oid IS NULL OR retained_child_oid=child_oid)) STRICT;
CREATE TABLE tag_objects(interpretation_uuid TEXT NOT NULL,object_format TEXT NOT NULL,oid BLOB NOT NULL,
  target_oid BLOB NOT NULL,raw_name BLOB NOT NULL,tagged_at_us INTEGER,
  PRIMARY KEY(interpretation_uuid,object_format,oid),FOREIGN KEY(interpretation_uuid) REFERENCES git_interpretations(interpretation_uuid),
  FOREIGN KEY(object_format,oid) REFERENCES git_objects(object_format,oid),FOREIGN KEY(object_format,target_oid) REFERENCES git_objects(object_format,oid)) STRICT;
CREATE TABLE snapshots(snapshot_uuid TEXT PRIMARY KEY,interpretation_uuid TEXT NOT NULL,
  repository_uuid TEXT NOT NULL,observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(interpretation_uuid,repository_uuid) REFERENCES git_interpretations(interpretation_uuid,repository_uuid)) STRICT;
CREATE TABLE ref_observations(snapshot_uuid TEXT NOT NULL,raw_ref_name BLOB NOT NULL,
  object_format TEXT NOT NULL,oid BLOB NOT NULL,PRIMARY KEY(snapshot_uuid,raw_ref_name),
  FOREIGN KEY(snapshot_uuid) REFERENCES snapshots(snapshot_uuid),FOREIGN KEY(object_format,oid) REFERENCES git_objects(object_format,oid)) STRICT;
CREATE TABLE root_manifests(snapshot_uuid TEXT PRIMARY KEY,root_count INTEGER NOT NULL,root_digest BLOB NOT NULL,
  FOREIGN KEY(snapshot_uuid) REFERENCES snapshots(snapshot_uuid)) STRICT;
CREATE TABLE root_manifest_entries(snapshot_uuid TEXT NOT NULL,ordinal INTEGER NOT NULL,object_format TEXT NOT NULL,oid BLOB NOT NULL,
  PRIMARY KEY(snapshot_uuid,ordinal),FOREIGN KEY(snapshot_uuid) REFERENCES root_manifests(snapshot_uuid),FOREIGN KEY(object_format,oid) REFERENCES git_objects(object_format,oid)) STRICT;
CREATE TABLE git_text_facts(interpretation_uuid TEXT NOT NULL,object_format TEXT NOT NULL,oid BLOB NOT NULL,
  text_sha256 BLOB NOT NULL,PRIMARY KEY(interpretation_uuid,object_format,oid),
  FOREIGN KEY(interpretation_uuid) REFERENCES git_interpretations(interpretation_uuid),FOREIGN KEY(object_format,oid) REFERENCES git_objects(object_format,oid),
  FOREIGN KEY(text_sha256) REFERENCES text_bodies(sha256)) STRICT;

-- [P Q06/Q08/Q09] Code belongs to the exact observed head/base, never current PR.
CREATE TABLE code_targets(target_uuid TEXT PRIMARY KEY,repository_uuid TEXT NOT NULL,
  change_request_id TEXT NOT NULL,pr_observation_uuid TEXT NOT NULL,role TEXT NOT NULL,
  target_state TEXT NOT NULL CHECK(target_state IN ('missing','null','oid')),
  object_format TEXT,oid BLOB,
  FOREIGN KEY(pr_observation_uuid,change_request_id,repository_uuid) REFERENCES change_request_observations(observation_uuid,change_request_id,repository_uuid),
  CHECK((target_state='oid' AND object_format IS NOT NULL AND oid IS NOT NULL) OR
    (target_state<>'oid' AND object_format IS NULL AND oid IS NULL)),
  UNIQUE(target_uuid,repository_uuid)) STRICT;
CREATE TABLE code_observations(code_uuid TEXT PRIMARY KEY,target_uuid TEXT NOT NULL,
  repository_uuid TEXT NOT NULL,publication_uuid TEXT NOT NULL,observed_at_us INTEGER NOT NULL,
  FOREIGN KEY(target_uuid,repository_uuid) REFERENCES code_targets(target_uuid,repository_uuid),
  FOREIGN KEY(publication_uuid,repository_uuid) REFERENCES repository_publications(publication_uuid,repository_uuid),UNIQUE(code_uuid,repository_uuid)) STRICT;
CREATE TABLE code_git_inputs(code_uuid TEXT NOT NULL,repository_uuid TEXT NOT NULL,acquisition_uuid TEXT NOT NULL,
  PRIMARY KEY(code_uuid,acquisition_uuid),FOREIGN KEY(code_uuid,repository_uuid) REFERENCES code_observations(code_uuid,repository_uuid),
  FOREIGN KEY(acquisition_uuid,repository_uuid) REFERENCES git_acquisitions(acquisition_uuid,repository_uuid)) STRICT;
CREATE TABLE code_listings(listing_uuid TEXT PRIMARY KEY,code_uuid TEXT NOT NULL,repository_uuid TEXT NOT NULL,
  kind TEXT NOT NULL,collection_uuid TEXT NOT NULL,
  FOREIGN KEY(code_uuid,repository_uuid) REFERENCES code_observations(code_uuid,repository_uuid),
  FOREIGN KEY(collection_uuid,repository_uuid) REFERENCES repository_collection_observations(collection_uuid,repository_uuid)) STRICT;
CREATE TABLE code_commits(listing_uuid TEXT NOT NULL,position INTEGER NOT NULL,object_format TEXT NOT NULL,oid BLOB NOT NULL,
  message_sha256 BLOB,PRIMARY KEY(listing_uuid,position),FOREIGN KEY(listing_uuid) REFERENCES code_listings(listing_uuid),
  FOREIGN KEY(message_sha256) REFERENCES text_bodies(sha256)) STRICT;
CREATE TABLE code_file_changes(listing_uuid TEXT NOT NULL,position INTEGER NOT NULL,
  raw_path BLOB NOT NULL,previous_raw_path BLOB,status TEXT NOT NULL,additions INTEGER,deletions INTEGER,
  patch_sha256 BLOB,PRIMARY KEY(listing_uuid,position),FOREIGN KEY(listing_uuid) REFERENCES code_listings(listing_uuid),
  FOREIGN KEY(patch_sha256) REFERENCES text_bodies(sha256)) STRICT;

-- [A/P Q09/I] Current resources preserve existing latest-state semantics/field evidence.
-- This sketch is not the production column inventory. Existing capture snapshots
-- may be detached after transfer; scope relationships validated when present.
CREATE TABLE issue_resources(service_uuid TEXT NOT NULL,provider_issue_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('issue','issue-comment')),repository_uuid TEXT NOT NULL,provider_parent_issue_id TEXT,
  parent_kind TEXT GENERATED ALWAYS AS (CASE WHEN kind='issue-comment' THEN 'issue' END) VIRTUAL,
  body_sha256 BLOB,title TEXT,field_evidence_json TEXT NOT NULL CHECK(json_valid(field_evidence_json)),
  captured_source_uuid TEXT,captured_repository_uuid TEXT NOT NULL,
  last_checked_at_us INTEGER,PRIMARY KEY(service_uuid,kind,provider_issue_id),
  FOREIGN KEY(service_uuid) REFERENCES service_instances(service_uuid),FOREIGN KEY(repository_uuid) REFERENCES repositories(repository_uuid),
  FOREIGN KEY(service_uuid,parent_kind,provider_parent_issue_id) REFERENCES issue_resources(service_uuid,kind,provider_issue_id),
  CHECK((kind='issue' AND provider_parent_issue_id IS NULL) OR (kind='issue-comment' AND provider_parent_issue_id IS NOT NULL)),
  FOREIGN KEY(body_sha256) REFERENCES text_bodies(sha256)) STRICT;
CREATE TABLE review_resources(change_request_id TEXT NOT NULL,kind TEXT NOT NULL,provider_document_id TEXT NOT NULL,
  repository_uuid TEXT NOT NULL,body_sha256 BLOB,field_evidence_json TEXT NOT NULL CHECK(json_valid(field_evidence_json)),
  last_checked_at_us INTEGER,PRIMARY KEY(change_request_id,kind,provider_document_id),
  FOREIGN KEY(change_request_id,repository_uuid) REFERENCES change_requests(change_request_id,repository_uuid),
  FOREIGN KEY(body_sha256) REFERENCES text_bodies(sha256)) STRICT;
-- [A] Existing current-resource receipts attest past digests; not stored edit history.
-- [P Q03/Q05] Source-owned scope extension is an option, not accepted Coverage.
-- [A] Exact five-column Coverage claims/view semantics remain unchanged.
CREATE TABLE coverage_scopes(coverage_scope_id TEXT PRIMARY KEY,repository_uuid TEXT,
  source_uuid TEXT,kind TEXT NOT NULL,scope_identity TEXT NOT NULL,
  CHECK((repository_uuid IS NULL)<>(source_uuid IS NULL)),
  FOREIGN KEY(repository_uuid) REFERENCES repositories(repository_uuid),FOREIGN KEY(source_uuid) REFERENCES sources(source_uuid)) STRICT;
CREATE TABLE coverage_claims(coverage_claim_id INTEGER PRIMARY KEY,coverage_scope_id TEXT NOT NULL,
  coverage_state TEXT NOT NULL CHECK(coverage_state IN ('complete','partial','unknown','not_applicable')),
  observed_at_us INTEGER NOT NULL,
  details_json TEXT CHECK(details_json IS NULL OR (json_valid(details_json) AND json_type(details_json)='object')),
  UNIQUE(coverage_scope_id,observed_at_us,coverage_state),FOREIGN KEY(coverage_scope_id) REFERENCES coverage_scopes(coverage_scope_id)) STRICT;
CREATE TABLE exchange_blocked_coverage_claims(coverage_claim_id INTEGER PRIMARY KEY,
  FOREIGN KEY(coverage_claim_id) REFERENCES coverage_claims(coverage_claim_id)) STRICT;
CREATE VIEW current_coverage AS
  SELECT s.coverage_scope_id,max(c.observed_at_us) AS observed_at_us,
    CASE WHEN count(b.coverage_claim_id)>0 THEN 'conflict'
      WHEN count(DISTINCT CASE WHEN c.coverage_state<>'unknown' THEN c.coverage_state END)>1 THEN 'conflict'
      ELSE coalesce(max(CASE WHEN c.coverage_state<>'unknown' THEN c.coverage_state END),'unknown') END AS coverage_state,
    count(c.coverage_claim_id) AS claim_count
  FROM coverage_scopes s LEFT JOIN coverage_claims c ON c.coverage_scope_id=s.coverage_scope_id
    AND c.observed_at_us=(SELECT max(latest.observed_at_us) FROM coverage_claims latest WHERE latest.coverage_scope_id=s.coverage_scope_id)
  LEFT JOIN exchange_blocked_coverage_claims b ON b.coverage_claim_id=c.coverage_claim_id
  GROUP BY s.coverage_scope_id;
-- [P Q08] Candidate set, not a final current-winner policy. Incomparable clocks
-- leave both observations. Provider timestamp comparability requires domain contract.
CREATE VIEW pr_maximal_candidates AS
 SELECT a.* FROM change_request_observations a
 JOIN repository_publication_seals p ON p.publication_uuid=a.publication_uuid
 WHERE NOT EXISTS(SELECT 1 FROM change_request_observations b
 JOIN repository_publication_seals s ON s.publication_uuid=b.publication_uuid
 WHERE b.change_request_id=a.change_request_id AND b.clock_scope=a.clock_scope
 AND b.provider_clock_us>a.provider_clock_us);

-- [P Q10/I] Operational staging is not a public domain input or proof root.
-- Envelope schema/version/trust validation remains pending; this is only shape.
CREATE TABLE exchange_staging(record_digest BLOB PRIMARY KEY,record_kind TEXT NOT NULL,
  portable_key TEXT NOT NULL,normalized_record_json TEXT NOT NULL CHECK(json_valid(normalized_record_json)),
  reason TEXT NOT NULL) STRICT;
CREATE TABLE exchange_missing_dependencies(record_digest BLOB NOT NULL,dependency_kind TEXT NOT NULL,dependency_key TEXT NOT NULL,
  PRIMARY KEY(record_digest,dependency_kind,dependency_key),FOREIGN KEY(record_digest) REFERENCES exchange_staging(record_digest)) STRICT;
CREATE INDEX exchange_waiters ON exchange_missing_dependencies(dependency_kind,dependency_key);
-- [P Q12/ALT] Same-catalog checkpoint alternative for atomic accepted-prefix writes.
-- Cursor may be erased; it is not a completeness assertion or exported domain FK.
CREATE TABLE acquisition_checkpoints(checkpoint_uuid TEXT PRIMARY KEY,
  collection_uuid TEXT NOT NULL,repository_uuid TEXT NOT NULL,job_uuid TEXT NOT NULL,
  attempt_generation INTEGER NOT NULL,next_ordinal INTEGER NOT NULL,continuation_token TEXT,
  FOREIGN KEY(collection_uuid,repository_uuid) REFERENCES repository_collection_observations(collection_uuid,repository_uuid)) STRICT;
