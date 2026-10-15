-- Context authority. Current field candidates are mutable; no complete edit history.
CREATE TABLE providers(
 service_instance_uuidv4 TEXT PRIMARY KEY CHECK(p1_uuid4(service_instance_uuidv4)),
 provider_kind TEXT NOT NULL CHECK(length(provider_kind)>0),
 configuration_json TEXT NOT NULL CHECK(p1_json(configuration_json))
) STRICT, WITHOUT ROWID;
CREATE TABLE repository_context(
 repository_uuidv4 TEXT PRIMARY KEY CHECK(p1_uuid4(repository_uuidv4)),
 configuration_json TEXT NOT NULL CHECK(p1_json(configuration_json))
) STRICT, WITHOUT ROWID;
CREATE TABLE sources(
 source_registration_uuidv4 TEXT PRIMARY KEY CHECK(p1_uuid4(source_registration_uuidv4)),
 service_instance_uuidv4 TEXT NOT NULL REFERENCES providers,
 configuration_json TEXT NOT NULL CHECK(p1_json(configuration_json))
) STRICT, WITHOUT ROWID;
CREATE TABLE source_repositories(
 source_registration_uuidv4 TEXT NOT NULL REFERENCES sources,
 repository_uuidv4 TEXT NOT NULL REFERENCES repository_context,
 attributes_json TEXT NOT NULL CHECK(p1_json(attributes_json)),
 PRIMARY KEY(source_registration_uuidv4,repository_uuidv4)
) STRICT, WITHOUT ROWID;
-- Known-positive membership cannot be removed by a partial/empty inventory.
CREATE TRIGGER source_positive_no_delete BEFORE DELETE ON source_repositories BEGIN
 SELECT RAISE(ABORT,'known-positive Source membership is durable'); END;
CREATE TABLE resources(
 service_instance_uuidv4 TEXT NOT NULL REFERENCES providers,
 resource_kind TEXT NOT NULL CHECK(resource_kind IN('repository','pull_request','issue','review','comment','thread','document','assessment','identity','endpoint','annotation','lfs')),
 provider_resource_id TEXT NOT NULL CHECK(length(provider_resource_id)>0),
 parent_resource_kind TEXT,
 parent_provider_resource_id TEXT,
 document_kind TEXT,
 provider_document_id TEXT,
 CHECK(resource_kind NOT IN('review','document') OR parent_resource_kind='pull_request'),
 CHECK(resource_kind!='thread' OR parent_resource_kind IN('pull_request','review')),
 CHECK(resource_kind!='comment' OR parent_resource_kind IN('pull_request','issue','review','thread')),
 CHECK(CASE WHEN resource_kind IN('review','comment','thread','document') THEN
 parent_resource_kind IS NOT NULL AND parent_provider_resource_id IS NOT NULL AND document_kind IS NOT NULL AND length(document_kind)>0 AND provider_document_id IS NOT NULL AND length(provider_document_id)>0
 AND provider_resource_id=p1_array(parent_resource_kind,parent_provider_resource_id,document_kind,provider_document_id)
 ELSE parent_resource_kind IS NULL AND parent_provider_resource_id IS NULL AND document_kind IS NULL AND provider_document_id IS NULL END),
 FOREIGN KEY(service_instance_uuidv4,parent_resource_kind,parent_provider_resource_id) REFERENCES resources(service_instance_uuidv4,resource_kind,provider_resource_id),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id)
) STRICT, WITHOUT ROWID;
CREATE TABLE text_bodies(
 sha256 TEXT PRIMARY KEY CHECK(length(sha256)=64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
 text_value TEXT NOT NULL CHECK(p1_text_sha256(text_value)=sha256)
) STRICT, WITHOUT ROWID;
CREATE TABLE field_candidates(
 service_instance_uuidv4 TEXT NOT NULL,
 resource_kind TEXT NOT NULL,
 provider_resource_id TEXT NOT NULL,
 field_name TEXT NOT NULL CHECK(length(field_name)>0),
 value_json TEXT NOT NULL CHECK(p1_json(value_json)),
 clock_json TEXT NOT NULL CHECK(p1_json(clock_json) AND json_type(clock_json)='object'
   AND COALESCE(json_type(clock_json,'$.domain')='text',0) AND length(json_extract(clock_json,'$.domain'))>0
   AND COALESCE(json_type(clock_json,'$.at_us') IN('integer','null'),0) AND json_remove(clock_json,'$.domain','$.at_us')='{}'),
 provenance_json TEXT NOT NULL CHECK(p1_json(provenance_json) AND json_type(provenance_json)='object' AND COALESCE(json_type(provenance_json,'$.source')='text',0) AND length(json_extract(provenance_json,'$.source'))>0 AND json_type(provenance_json,'$.evidence') IS NOT NULL AND json_type(provenance_json,'$.evidence')!='null'),
 observed_at_us INTEGER NOT NULL,
 clock_domain TEXT GENERATED ALWAYS AS(json_extract(clock_json,'$.domain')) VIRTUAL,
 source_clock_us INTEGER GENERATED ALWAYS AS(json_extract(clock_json,'$.at_us')) VIRTUAL,
 repository_uuidv4 TEXT GENERATED ALWAYS AS(CASE WHEN field_name='repository_uuidv4' THEN json_extract(value_json,'$') END) VIRTUAL REFERENCES repository_context,
 CHECK(field_name!='repository_uuidv4' OR (json_type(value_json)='text' AND p1_uuid4(json_extract(value_json,'$')))),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,clock_json,value_json,provenance_json),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id) REFERENCES resources
) STRICT, WITHOUT ROWID;
CREATE TABLE resource_relations(
 service_instance_uuidv4 TEXT NOT NULL,
 resource_kind TEXT NOT NULL,
 provider_resource_id TEXT NOT NULL,
 relation_kind TEXT NOT NULL CHECK(length(relation_kind)>0),
 members_json TEXT NOT NULL CHECK(p1_json(members_json) AND json_type(members_json)='array'),
 provenance_json TEXT NOT NULL CHECK(p1_json(provenance_json) AND json_type(provenance_json)='object' AND COALESCE(json_type(provenance_json,'$.source')='text',0) AND length(json_extract(provenance_json,'$.source'))>0 AND json_type(provenance_json,'$.evidence') IS NOT NULL AND json_type(provenance_json,'$.evidence')!='null'),
 scope_json TEXT NOT NULL CHECK(p1_json(scope_json)),
 observed_at_us INTEGER NOT NULL,
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id) REFERENCES resources
) STRICT, WITHOUT ROWID;
CREATE TABLE collections(
 service_instance_uuidv4 TEXT NOT NULL,
 resource_kind TEXT NOT NULL,
 provider_resource_id TEXT NOT NULL,
 collection_kind TEXT NOT NULL CHECK(length(collection_kind)>0),
 provenance_json TEXT NOT NULL CHECK(p1_json(provenance_json) AND json_type(provenance_json)='object' AND COALESCE(json_type(provenance_json,'$.source')='text',0) AND length(json_extract(provenance_json,'$.source'))>0 AND json_type(provenance_json,'$.evidence') IS NOT NULL AND json_type(provenance_json,'$.evidence')!='null'),
 scope_json TEXT NOT NULL CHECK(p1_json(scope_json)),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,provenance_json),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id) REFERENCES resources
) STRICT, WITHOUT ROWID;
CREATE TABLE collection_terminals(
 service_instance_uuidv4 TEXT NOT NULL,
 resource_kind TEXT NOT NULL,
 provider_resource_id TEXT NOT NULL,
 collection_kind TEXT NOT NULL,
 provenance_json TEXT NOT NULL,
 observed_at_us INTEGER NOT NULL,
 terminal_state TEXT NOT NULL CHECK(terminal_state IN('complete','partial','unknown')),
 members_json TEXT NOT NULL CHECK(p1_json(members_json) AND json_type(members_json)='array'),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,provenance_json,observed_at_us,terminal_state,members_json),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,provenance_json) REFERENCES collections
) STRICT, WITHOUT ROWID;
CREATE TABLE core_references(
 service_instance_uuidv4 TEXT NOT NULL,
 resource_kind TEXT NOT NULL,
 provider_resource_id TEXT NOT NULL,
 role TEXT NOT NULL CHECK(length(role)>0),
 object_format TEXT NOT NULL,
 full_oid TEXT NOT NULL CHECK(p1_oid(object_format,full_oid)),
 provenance_json TEXT NOT NULL CHECK(p1_json(provenance_json) AND json_type(provenance_json)='object' AND COALESCE(json_type(provenance_json,'$.source')='text',0) AND length(json_extract(provenance_json,'$.source'))>0 AND json_type(provenance_json,'$.evidence') IS NOT NULL AND json_type(provenance_json,'$.evidence')!='null'),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id,role,object_format,full_oid,provenance_json),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id) REFERENCES resources
) STRICT, WITHOUT ROWID;
-- Explicit normalized owners constrain the reversible full coordinate encoding.
CREATE TABLE coverage_scopes(
 owner_kind TEXT NOT NULL CHECK(owner_kind IN('repository','source','source_inventory','resource','collection','field')),
 owner_coordinates_json TEXT NOT NULL CHECK(p1_json(owner_coordinates_json)),
 repository_uuidv4 TEXT REFERENCES repository_context,
 source_registration_uuidv4 TEXT REFERENCES sources,
 source_scope_json TEXT CHECK(source_scope_json IS NULL OR p1_json(source_scope_json)),
 service_instance_uuidv4 TEXT,
 resource_kind TEXT,
 provider_resource_id TEXT,
 collection_kind TEXT,
 collection_provenance_json TEXT,
 field_name TEXT,
 coverage_kind TEXT NOT NULL CHECK(length(coverage_kind)>0),
 PRIMARY KEY(owner_kind,owner_coordinates_json),
 FOREIGN KEY(source_registration_uuidv4,repository_uuidv4) REFERENCES source_repositories,
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id) REFERENCES resources,
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,collection_provenance_json) REFERENCES collections,
 CHECK(CASE owner_kind
 WHEN 'repository' THEN source_scope_json IS NULL AND repository_uuidv4 IS NOT NULL AND source_registration_uuidv4 IS NULL AND service_instance_uuidv4 IS NULL AND resource_kind IS NULL AND provider_resource_id IS NULL AND collection_kind IS NULL AND collection_provenance_json IS NULL AND field_name IS NULL AND owner_coordinates_json=p1_array(repository_uuidv4,coverage_kind)
 WHEN 'source' THEN source_scope_json IS NULL AND repository_uuidv4 IS NOT NULL AND source_registration_uuidv4 IS NOT NULL AND service_instance_uuidv4 IS NULL AND resource_kind IS NULL AND provider_resource_id IS NULL AND collection_kind IS NULL AND collection_provenance_json IS NULL AND field_name IS NULL AND owner_coordinates_json=p1_array(source_registration_uuidv4,repository_uuidv4,coverage_kind)
 WHEN 'resource' THEN source_scope_json IS NULL AND repository_uuidv4 IS NULL AND source_registration_uuidv4 IS NULL AND service_instance_uuidv4 IS NOT NULL AND resource_kind IS NOT NULL AND provider_resource_id IS NOT NULL AND collection_kind IS NULL AND collection_provenance_json IS NULL AND field_name IS NULL AND owner_coordinates_json=p1_array(service_instance_uuidv4,resource_kind,provider_resource_id,coverage_kind)
 WHEN 'collection' THEN source_scope_json IS NULL AND repository_uuidv4 IS NULL AND source_registration_uuidv4 IS NULL AND service_instance_uuidv4 IS NOT NULL AND resource_kind IS NOT NULL AND provider_resource_id IS NOT NULL AND collection_kind IS NOT NULL AND collection_provenance_json IS NOT NULL AND field_name IS NULL AND owner_coordinates_json=p1_array(service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,collection_provenance_json,coverage_kind)
 WHEN 'field' THEN source_scope_json IS NULL AND repository_uuidv4 IS NULL AND source_registration_uuidv4 IS NULL AND service_instance_uuidv4 IS NOT NULL AND resource_kind IS NOT NULL AND provider_resource_id IS NOT NULL AND collection_kind IS NULL AND collection_provenance_json IS NULL AND field_name IS NOT NULL AND length(field_name)>0 AND owner_coordinates_json=p1_array(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,coverage_kind)
 WHEN 'source_inventory' THEN repository_uuidv4 IS NULL AND source_registration_uuidv4 IS NOT NULL AND source_scope_json IS NOT NULL AND service_instance_uuidv4 IS NULL AND resource_kind IS NULL AND provider_resource_id IS NULL AND collection_kind IS NULL AND collection_provenance_json IS NULL AND field_name IS NULL AND owner_coordinates_json=p1_array(source_registration_uuidv4,source_scope_json,coverage_kind)
 ELSE 0 END)
) STRICT, WITHOUT ROWID;
CREATE TABLE coverage_proofs(
 owner_kind TEXT NOT NULL,
 owner_coordinates_json TEXT NOT NULL,
 observed_at_us INTEGER NOT NULL,
 coverage_state TEXT NOT NULL,
 service_instance_uuidv4 TEXT NOT NULL,
 resource_kind TEXT NOT NULL,
 provider_resource_id TEXT NOT NULL,
 collection_kind TEXT NOT NULL,
 provenance_json TEXT NOT NULL,
 terminal_observed_at_us INTEGER NOT NULL,
 terminal_state TEXT NOT NULL,
 members_json TEXT NOT NULL,
 PRIMARY KEY(owner_kind,owner_coordinates_json,observed_at_us,coverage_state,service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,provenance_json,terminal_observed_at_us,terminal_state,members_json),
 FOREIGN KEY(owner_kind,owner_coordinates_json,observed_at_us,coverage_state) REFERENCES coverage_claims,
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,provenance_json,terminal_observed_at_us,terminal_state,members_json) REFERENCES collection_terminals,
 CHECK(terminal_observed_at_us<=observed_at_us),
 CHECK(coverage_state!='complete' OR terminal_state='complete')
) STRICT, WITHOUT ROWID;

CREATE TABLE source_inventory_evidence(
 source_registration_uuidv4 TEXT NOT NULL REFERENCES sources,
 scope_json TEXT NOT NULL CHECK(p1_json(scope_json)),
 observed_at_us INTEGER NOT NULL,
 coverage_state TEXT NOT NULL CHECK(coverage_state IN('complete','partial','unknown','not_applicable')),
 terminal INTEGER NOT NULL CHECK(terminal IN(0,1)),
 members_json TEXT NOT NULL CHECK(p1_json(members_json) AND json_type(members_json)='array'),
 provenance_json TEXT NOT NULL CHECK(p1_json(provenance_json) AND json_type(provenance_json)='object' AND COALESCE(json_type(provenance_json,'$.source')='text',0) AND length(json_extract(provenance_json,'$.source'))>0 AND json_type(provenance_json,'$.evidence') IS NOT NULL AND json_type(provenance_json,'$.evidence')!='null'),
 PRIMARY KEY(source_registration_uuidv4,scope_json,observed_at_us,coverage_state,terminal,members_json,provenance_json)
) STRICT, WITHOUT ROWID;
CREATE TRIGGER coverage_proof_owner BEFORE INSERT ON coverage_proofs WHEN NOT EXISTS(
 SELECT 1 FROM coverage_scopes s JOIN collections c ON
 c.service_instance_uuidv4=NEW.service_instance_uuidv4 AND c.resource_kind=NEW.resource_kind AND c.provider_resource_id=NEW.provider_resource_id AND c.collection_kind=NEW.collection_kind AND c.provenance_json=NEW.provenance_json
 WHERE s.owner_kind=NEW.owner_kind AND s.owner_coordinates_json=NEW.owner_coordinates_json
 AND CASE s.owner_kind
 WHEN 'repository' THEN json_extract(c.scope_json,'$.repository_uuidv4')=s.repository_uuidv4 AND (s.coverage_kind=NEW.collection_kind OR json_extract(c.scope_json,'$.coverage_kind')=s.coverage_kind)
 WHEN 'source' THEN json_extract(c.scope_json,'$.repository_uuidv4')=s.repository_uuidv4 AND json_extract(c.scope_json,'$.source_registration_uuidv4')=s.source_registration_uuidv4 AND EXISTS(SELECT 1 FROM sources src WHERE src.source_registration_uuidv4=s.source_registration_uuidv4 AND src.service_instance_uuidv4=NEW.service_instance_uuidv4)
 WHEN 'resource' THEN s.service_instance_uuidv4=NEW.service_instance_uuidv4 AND s.resource_kind=NEW.resource_kind AND s.provider_resource_id=NEW.provider_resource_id AND (s.coverage_kind=NEW.collection_kind OR json_extract(c.scope_json,'$.coverage_kind')=s.coverage_kind)
 WHEN 'field' THEN s.service_instance_uuidv4=NEW.service_instance_uuidv4 AND s.resource_kind=NEW.resource_kind AND s.provider_resource_id=NEW.provider_resource_id AND json_extract(c.scope_json,'$.field_name')=s.field_name
 WHEN 'collection' THEN s.service_instance_uuidv4=NEW.service_instance_uuidv4 AND s.resource_kind=NEW.resource_kind AND s.provider_resource_id=NEW.provider_resource_id AND s.collection_kind=NEW.collection_kind AND s.collection_provenance_json=NEW.provenance_json
 ELSE 0 END)
 BEGIN SELECT RAISE(ABORT,'Coverage proof owner mismatch'); END;
CREATE TRIGGER resources_no_update BEFORE UPDATE ON resources BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER resources_no_delete BEFORE DELETE ON resources BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER text_bodies_no_update BEFORE UPDATE ON text_bodies BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER text_bodies_no_delete BEFORE DELETE ON text_bodies BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER resource_relations_no_update BEFORE UPDATE ON resource_relations BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER resource_relations_no_delete BEFORE DELETE ON resource_relations BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER collections_no_update BEFORE UPDATE ON collections BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER collections_no_delete BEFORE DELETE ON collections BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER collection_terminals_no_update BEFORE UPDATE ON collection_terminals BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER collection_terminals_no_delete BEFORE DELETE ON collection_terminals BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER core_references_no_update BEFORE UPDATE ON core_references BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER core_references_no_delete BEFORE DELETE ON core_references BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER coverage_scopes_no_update BEFORE UPDATE ON coverage_scopes BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER coverage_scopes_no_delete BEFORE DELETE ON coverage_scopes BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER coverage_proofs_no_update BEFORE UPDATE ON coverage_proofs BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER coverage_proofs_no_delete BEFORE DELETE ON coverage_proofs BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER source_inventory_evidence_no_update BEFORE UPDATE ON source_inventory_evidence BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;
CREATE TRIGGER source_inventory_evidence_no_delete BEFORE DELETE ON source_inventory_evidence BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;

CREATE TRIGGER source_positive_identity BEFORE UPDATE ON source_repositories
WHEN NEW.source_registration_uuidv4!=OLD.source_registration_uuidv4 OR NEW.repository_uuidv4!=OLD.repository_uuidv4
BEGIN SELECT RAISE(ABORT,'known-positive Source identity is immutable'); END;
-- Source inventories have genuine Source/scope identity even with zero members.
CREATE TABLE source_coverage_proofs(
 owner_kind TEXT NOT NULL CHECK(owner_kind='source_inventory'),
 owner_coordinates_json TEXT NOT NULL,
 observed_at_us INTEGER NOT NULL,
 coverage_state TEXT NOT NULL,
 source_registration_uuidv4 TEXT NOT NULL,
 scope_json TEXT NOT NULL,
 inventory_observed_at_us INTEGER NOT NULL,
 inventory_state TEXT NOT NULL,
 terminal INTEGER NOT NULL CHECK(terminal=1),
 members_json TEXT NOT NULL,
 provenance_json TEXT NOT NULL,
 PRIMARY KEY(owner_kind,owner_coordinates_json,observed_at_us,coverage_state,source_registration_uuidv4,scope_json,inventory_observed_at_us,inventory_state,terminal,members_json,provenance_json),
 FOREIGN KEY(owner_kind,owner_coordinates_json,observed_at_us,coverage_state) REFERENCES coverage_claims,
 FOREIGN KEY(source_registration_uuidv4,scope_json,inventory_observed_at_us,inventory_state,terminal,members_json,provenance_json) REFERENCES source_inventory_evidence,
 CHECK(inventory_observed_at_us<=observed_at_us),
 CHECK(coverage_state!='complete' OR inventory_state='complete')
) STRICT, WITHOUT ROWID;
CREATE TRIGGER source_coverage_owner BEFORE INSERT ON source_coverage_proofs WHEN NOT EXISTS(
 SELECT 1 FROM coverage_scopes WHERE owner_kind=NEW.owner_kind AND owner_coordinates_json=NEW.owner_coordinates_json
 AND source_registration_uuidv4=NEW.source_registration_uuidv4 AND source_scope_json=NEW.scope_json)
 BEGIN SELECT RAISE(ABORT,'Source Coverage proof owner mismatch'); END;
CREATE TRIGGER source_coverage_no_update BEFORE UPDATE ON source_coverage_proofs BEGIN SELECT RAISE(ABORT,'immutable Source Coverage proof'); END;
CREATE TRIGGER source_coverage_no_delete BEFORE DELETE ON source_coverage_proofs BEGIN SELECT RAISE(ABORT,'immutable Source Coverage proof'); END;
CREATE TRIGGER repository_context_identity BEFORE UPDATE ON repository_context WHEN NEW.repository_uuidv4!=OLD.repository_uuidv4
BEGIN SELECT RAISE(ABORT,'permanent repository identity'); END;
CREATE TRIGGER provider_identity BEFORE UPDATE ON providers WHEN NEW.service_instance_uuidv4!=OLD.service_instance_uuidv4 OR NEW.provider_kind!=OLD.provider_kind
BEGIN SELECT RAISE(ABORT,'registered Provider identity'); END;
CREATE TRIGGER source_identity BEFORE UPDATE ON sources WHEN NEW.source_registration_uuidv4!=OLD.source_registration_uuidv4 OR NEW.service_instance_uuidv4!=OLD.service_instance_uuidv4
BEGIN SELECT RAISE(ABORT,'registered Source identity'); END;
