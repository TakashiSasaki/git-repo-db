CREATE TABLE store_identity(
    store_role TEXT PRIMARY KEY CHECK(store_role='context'),
    repository_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(repository_uuidv4)),
    catalog_instance_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(catalog_instance_uuidv4))
) STRICT, WITHOUT ROWID;

-- Context authority. Current field candidates are mutable; no complete edit history.
CREATE TABLE providers(
 service_instance_uuidv4 TEXT PRIMARY KEY CHECK(p1_uuid4(service_instance_uuidv4)),
 provider_kind TEXT NOT NULL CHECK(length(provider_kind)>0),
 configuration_json TEXT NOT NULL CHECK(p1_json(configuration_json) AND p1_registration_json('provider',configuration_json))
) STRICT, WITHOUT ROWID;
CREATE TABLE repository_context(
 repository_uuidv4 TEXT PRIMARY KEY CHECK(p1_uuid4(repository_uuidv4)),
 configuration_json TEXT NOT NULL CHECK(p1_json(configuration_json) AND p1_registration_json('repository',configuration_json))
) STRICT, WITHOUT ROWID;
CREATE TABLE sources(
 source_registration_uuidv4 TEXT PRIMARY KEY CHECK(p1_uuid4(source_registration_uuidv4)),
 service_instance_uuidv4 TEXT NOT NULL REFERENCES providers,
 configuration_json TEXT NOT NULL CHECK(p1_json(configuration_json) AND p1_registration_json('source',configuration_json))
) STRICT, WITHOUT ROWID;
CREATE TABLE source_repositories(
 source_registration_uuidv4 TEXT NOT NULL REFERENCES sources,
 repository_uuidv4 TEXT NOT NULL REFERENCES repository_context,
 attributes_json TEXT NOT NULL CHECK(p1_json(attributes_json) AND p1_registration_json('membership',attributes_json)),
 PRIMARY KEY(source_registration_uuidv4,repository_uuidv4)
) STRICT, WITHOUT ROWID;
-- Known-positive membership cannot be removed by a partial/empty inventory.
CREATE TRIGGER source_positive_no_delete BEFORE DELETE ON source_repositories BEGIN
 SELECT RAISE(ABORT,'known-positive Source membership is durable'); END;
-- Identification coordinates are not semantic Parent reports or references.
CREATE TABLE resources(
 service_instance_uuidv4 TEXT NOT NULL REFERENCES providers,
 resource_kind TEXT NOT NULL CHECK(length(resource_kind)>0),
 provider_resource_id TEXT NOT NULL CHECK(cp_identity(provider_resource_id)=1),
 identifier_namespace_kind TEXT,
 identifier_namespace_id TEXT,
 document_kind TEXT,
 provider_document_id TEXT,
 -- Non-key typed absence projection, never a native identity coordinate.
 reference_document_kind TEXT GENERATED ALWAYS AS(coalesce(document_kind,'')) VIRTUAL,
 CHECK(cp_resource(resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id)=1),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id)
) STRICT, WITHOUT ROWID;
CREATE UNIQUE INDEX resources_typed_event_fk
 ON resources(service_instance_uuidv4,resource_kind,provider_resource_id,reference_document_kind);

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
   AND COALESCE(json_type(clock_json,'$.at_us') IN('integer','null'),0) AND typeof(json_extract(clock_json,'$.at_us')) IN('integer','null') AND (json_type(clock_json,'$.at_us')='null' OR json_extract(clock_json,'$.at_us')>0) AND json_remove(clock_json,'$.domain','$.at_us')='{}'),
 provenance_json TEXT NOT NULL CHECK(p1_json(provenance_json) AND json_type(provenance_json)='object' AND COALESCE(json_type(provenance_json,'$.source')='text',0) AND length(json_extract(provenance_json,'$.source'))>0 AND json_type(provenance_json,'$.evidence') IS NOT NULL AND json_type(provenance_json,'$.evidence')!='null'),
 observed_at_us INTEGER CHECK(observed_at_us IS NULL OR (typeof(observed_at_us)='integer' AND observed_at_us>0)),
 clock_domain TEXT GENERATED ALWAYS AS(json_extract(clock_json,'$.domain')) VIRTUAL,
 source_clock_us INTEGER GENERATED ALWAYS AS(json_extract(clock_json,'$.at_us')) VIRTUAL,
 text_body_sha256 TEXT GENERATED ALWAYS AS(CASE WHEN field_name='text_body_sha256' THEN json_extract(value_json,'$') END) VIRTUAL REFERENCES text_bodies(sha256),
 CHECK(field_name!='text_body_sha256' OR json_type(value_json)='null' OR (json_type(value_json)='text' AND length(json_extract(value_json,'$'))=64 AND json_extract(value_json,'$') NOT GLOB '*[^0-9a-f]*')),
 CHECK(field_name!='repository_uuidv4'),
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
 observed_at_us INTEGER CHECK(observed_at_us IS NULL OR (typeof(observed_at_us)='integer' AND observed_at_us>0)),
 parent_service TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind='parent' THEN cp_get(members_json,0,0) END) VIRTUAL,
 parent_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind='parent' THEN cp_get(members_json,0,1) END) VIRTUAL,
 parent_id TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind='parent' THEN cp_get(members_json,0,2) END) VIRTUAL,
 source_document_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind='parent' THEN coalesce(cp_get(scope_json,'document_kind'),'') WHEN relation_kind='transfer_event_report' THEN 'timeline_event' END) VIRTUAL,
 report_clock_json TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('parent','transfer_event_report') THEN cp_get(scope_json,'clock') END) VIRTUAL,
 support_relation_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind='transfer_event_report' THEN 'parent' END) VIRTUAL,
 support_members_json TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind='transfer_event_report' THEN cp_get(scope_json,'parent_members_json') END) VIRTUAL,
 support_provenance_json TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind='transfer_event_report' THEN cp_get(scope_json,'parent_provenance_json') END) VIRTUAL,
 support_scope_json TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind='transfer_event_report' THEN cp_get(scope_json,'parent_scope_json') END) VIRTUAL,
 support_parent_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind='transfer_event_report' THEN 'issue' END) VIRTUAL,
 CHECK(cp_relation(relation_kind,service_instance_uuidv4,resource_kind,members_json,scope_json)=1),
 CHECK(relation_kind!='parent' OR (parent_service IS NOT NULL AND parent_kind IS NOT NULL AND parent_id IS NOT NULL AND source_document_kind IS NOT NULL)),
 CHECK(relation_kind!='transfer_event_report' OR (support_members_json IS NOT NULL AND support_scope_json IS NOT NULL AND support_provenance_json IS NOT NULL)),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id) REFERENCES resources,
 FOREIGN KEY(parent_service,parent_kind,parent_id) REFERENCES resources,
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,source_document_kind) REFERENCES resources(service_instance_uuidv4,resource_kind,provider_resource_id,reference_document_kind),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,support_relation_kind,support_members_json,support_provenance_json,support_scope_json,source_document_kind,support_parent_kind)
 REFERENCES resource_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,source_document_kind,parent_kind)
) STRICT, WITHOUT ROWID;
CREATE UNIQUE INDEX parent_report_typed_fk ON resource_relations(
 service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,source_document_kind,parent_kind);

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
 observed_at_us INTEGER NOT NULL CHECK(typeof(observed_at_us)='integer' AND observed_at_us>0),
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
 observed_at_us INTEGER NOT NULL CHECK(typeof(observed_at_us)='integer' AND observed_at_us>0),
 coverage_state TEXT NOT NULL,
 service_instance_uuidv4 TEXT NOT NULL,
 resource_kind TEXT NOT NULL,
 provider_resource_id TEXT NOT NULL,
 collection_kind TEXT NOT NULL,
 provenance_json TEXT NOT NULL,
 terminal_observed_at_us INTEGER NOT NULL CHECK(typeof(terminal_observed_at_us)='integer' AND terminal_observed_at_us>0),
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
 observed_at_us INTEGER NOT NULL CHECK(typeof(observed_at_us)='integer' AND observed_at_us>0),
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
 WHEN 'repository' THEN json_extract(c.scope_json,'$.repository_uuidv4')=s.repository_uuidv4 AND s.coverage_kind=COALESCE(json_extract(c.scope_json,'$.coverage_kind'),NEW.collection_kind)
 WHEN 'source' THEN s.coverage_kind=COALESCE(json_extract(c.scope_json,'$.coverage_kind'),NEW.collection_kind) AND json_extract(c.scope_json,'$.repository_uuidv4')=s.repository_uuidv4 AND json_extract(c.scope_json,'$.source_registration_uuidv4')=s.source_registration_uuidv4 AND EXISTS(SELECT 1 FROM sources src WHERE src.source_registration_uuidv4=s.source_registration_uuidv4 AND src.service_instance_uuidv4=NEW.service_instance_uuidv4)
 WHEN 'resource' THEN s.service_instance_uuidv4=NEW.service_instance_uuidv4 AND s.resource_kind=NEW.resource_kind AND s.provider_resource_id=NEW.provider_resource_id AND s.coverage_kind=COALESCE(json_extract(c.scope_json,'$.coverage_kind'),NEW.collection_kind)
 WHEN 'field' THEN s.coverage_kind=COALESCE(json_extract(c.scope_json,'$.coverage_kind'),NEW.collection_kind) AND s.service_instance_uuidv4=NEW.service_instance_uuidv4 AND s.resource_kind=NEW.resource_kind AND s.provider_resource_id=NEW.provider_resource_id AND json_extract(c.scope_json,'$.field_name')=s.field_name
 WHEN 'collection' THEN s.coverage_kind=COALESCE(json_extract(c.scope_json,'$.coverage_kind'),NEW.collection_kind) AND s.service_instance_uuidv4=NEW.service_instance_uuidv4 AND s.resource_kind=NEW.resource_kind AND s.provider_resource_id=NEW.provider_resource_id AND s.collection_kind=NEW.collection_kind AND s.collection_provenance_json=NEW.provenance_json
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
 observed_at_us INTEGER NOT NULL CHECK(typeof(observed_at_us)='integer' AND observed_at_us>0),
 coverage_state TEXT NOT NULL,
 source_registration_uuidv4 TEXT NOT NULL,
 scope_json TEXT NOT NULL,
 inventory_observed_at_us INTEGER NOT NULL CHECK(typeof(inventory_observed_at_us)='integer' AND inventory_observed_at_us>0),
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
 AND source_registration_uuidv4=NEW.source_registration_uuidv4 AND source_scope_json=NEW.scope_json AND json_extract(NEW.scope_json,'$.coverage_kind')=coverage_kind)
 BEGIN SELECT RAISE(ABORT,'Source Coverage proof owner mismatch'); END;
CREATE TRIGGER source_coverage_no_update BEFORE UPDATE ON source_coverage_proofs BEGIN SELECT RAISE(ABORT,'immutable Source Coverage proof'); END;
CREATE TRIGGER source_coverage_no_delete BEFORE DELETE ON source_coverage_proofs BEGIN SELECT RAISE(ABORT,'immutable Source Coverage proof'); END;
CREATE TRIGGER repository_context_identity BEFORE UPDATE ON repository_context WHEN NEW.repository_uuidv4!=OLD.repository_uuidv4
BEGIN SELECT RAISE(ABORT,'permanent repository identity'); END;
CREATE TRIGGER provider_identity BEFORE UPDATE ON providers WHEN NEW.service_instance_uuidv4!=OLD.service_instance_uuidv4 OR NEW.provider_kind!=OLD.provider_kind
BEGIN SELECT RAISE(ABORT,'registered Provider identity'); END;
CREATE TRIGGER source_identity BEFORE UPDATE ON sources WHEN NEW.source_registration_uuidv4!=OLD.source_registration_uuidv4 OR NEW.service_instance_uuidv4!=OLD.service_instance_uuidv4
BEGIN SELECT RAISE(ABORT,'registered Source identity'); END;

-- Dependent completeness may only cite the current genuine terminal candidate
-- set. Later terminals preserve old reports; readers recheck them dynamically.
CREATE TRIGGER coverage_proof_current_terminal BEFORE INSERT ON coverage_proofs
WHEN NEW.terminal_observed_at_us!=(SELECT MAX(t.observed_at_us) FROM collection_terminals t
 WHERE t.service_instance_uuidv4=NEW.service_instance_uuidv4 AND t.resource_kind=NEW.resource_kind AND t.provider_resource_id=NEW.provider_resource_id AND t.collection_kind=NEW.collection_kind AND t.provenance_json=NEW.provenance_json)
 OR EXISTS(SELECT 1 FROM collection_terminals t WHERE t.service_instance_uuidv4=NEW.service_instance_uuidv4 AND t.resource_kind=NEW.resource_kind AND t.provider_resource_id=NEW.provider_resource_id AND t.collection_kind=NEW.collection_kind AND t.provenance_json=NEW.provenance_json AND t.observed_at_us=NEW.terminal_observed_at_us AND t.terminal_state!='unknown' AND (t.terminal_state!=NEW.terminal_state OR t.members_json!=NEW.members_json))
BEGIN SELECT RAISE(ABORT,'Coverage proof terminal is superseded or conflicting'); END;
CREATE TRIGGER source_coverage_current_terminal BEFORE INSERT ON source_coverage_proofs
WHEN NEW.inventory_observed_at_us!=(SELECT MAX(i.observed_at_us) FROM source_inventory_evidence i WHERE i.source_registration_uuidv4=NEW.source_registration_uuidv4 AND i.scope_json=NEW.scope_json)
 OR EXISTS(SELECT 1 FROM source_inventory_evidence i WHERE i.source_registration_uuidv4=NEW.source_registration_uuidv4 AND i.scope_json=NEW.scope_json AND i.observed_at_us=NEW.inventory_observed_at_us AND i.coverage_state!='unknown' AND (i.coverage_state!=NEW.inventory_state OR i.members_json!=NEW.members_json OR i.terminal!=NEW.terminal))
BEGIN SELECT RAISE(ABORT,'Source Coverage terminal is superseded or conflicting'); END;

CREATE TABLE resource_repository_relations(
 service_instance_uuidv4 TEXT NOT NULL,
 resource_kind TEXT NOT NULL,
 provider_resource_id TEXT NOT NULL,
 relation_kind TEXT NOT NULL,
 target_json TEXT NOT NULL CHECK(p1_mapping_target(target_json)=1),
 clock_json TEXT NOT NULL CHECK(p1_mapping_clock(clock_json)=1),
 provenance_json TEXT NOT NULL CHECK(p1_mapping_provenance(provenance_json)=1),
 observed_at_us INTEGER CHECK(observed_at_us IS NULL OR (typeof(observed_at_us)='integer' AND observed_at_us>0)),
 repository_uuidv4 TEXT GENERATED ALWAYS AS(CASE WHEN json_type(target_json)='text' THEN json_extract(target_json,'$') END) VIRTUAL REFERENCES repository_context(repository_uuidv4),
 clock_domain TEXT GENERATED ALWAYS AS(json_extract(clock_json,'$.domain')) VIRTUAL,
 source_clock_us INTEGER GENERATED ALWAYS AS(json_extract(clock_json,'$.at_us')) VIRTUAL,
 event_document_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN 'timeline_event' END) VIRTUAL,
 -- Full reference to the preexisting coherent transfer_event_report relation.
 event_report_members_json TEXT,
 event_report_scope_json TEXT,
 event_report_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN 'transfer_event_report' END) VIRTUAL,
 event_parent_resource_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN 'issue' END) VIRTUAL,
 support_relation_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN 'parent' END) VIRTUAL,
 support_members_json TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN cp_get(event_report_scope_json,'parent_members_json') END) VIRTUAL,
 support_provenance_json TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN cp_get(event_report_scope_json,'parent_provenance_json') END) VIRTUAL,
 support_scope_json TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN cp_get(event_report_scope_json,'parent_scope_json') END) VIRTUAL,
 CHECK(typeof(source_clock_us) IN('integer','null')),
 CHECK((relation_kind='represents_repository' AND resource_kind='repository') OR (relation_kind='owning_repository' AND resource_kind='issue') OR (relation_kind IN('base_repository','head_repository') AND resource_kind='pull_request') OR (relation_kind IN('transfer_from_repository','transfer_to_repository') AND resource_kind='comment')),
 CHECK(relation_kind!='represents_repository' OR json_type(target_json)='text'),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,clock_json,target_json,provenance_json),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id) REFERENCES resources(service_instance_uuidv4,resource_kind,provider_resource_id),
 CHECK(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN
 event_report_members_json IS NOT NULL AND event_report_scope_json IS NOT NULL
 AND support_members_json IS NOT NULL AND support_scope_json IS NOT NULL AND support_provenance_json IS NOT NULL
 AND cp_endpoint(relation_kind,target_json,event_report_scope_json,clock_json)=1
 ELSE event_report_members_json IS NULL AND event_report_scope_json IS NULL END),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,event_document_kind) REFERENCES resources(service_instance_uuidv4,resource_kind,provider_resource_id,reference_document_kind),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,support_relation_kind,support_members_json,support_provenance_json,support_scope_json,event_document_kind,event_parent_resource_kind)
 REFERENCES resource_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,source_document_kind,parent_kind),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,event_report_kind,event_report_members_json,provenance_json,event_report_scope_json)
 REFERENCES resource_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json)
) STRICT, WITHOUT ROWID;
CREATE INDEX rrr_by_repository ON resource_repository_relations(
 repository_uuidv4,relation_kind,service_instance_uuidv4,resource_kind,provider_resource_id
) WHERE repository_uuidv4 IS NOT NULL;
CREATE INDEX rrr_current_clock ON resource_repository_relations(
 service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,clock_domain,source_clock_us DESC
) WHERE relation_kind IN('owning_repository','base_repository','head_repository') AND source_clock_us IS NOT NULL;
CREATE INDEX rrr_event_report ON resource_repository_relations(
 service_instance_uuidv4,resource_kind,provider_resource_id,clock_json,provenance_json,relation_kind
) WHERE relation_kind IN('transfer_from_repository','transfer_to_repository');
CREATE TRIGGER rrr_no_update BEFORE UPDATE ON resource_repository_relations
BEGIN SELECT RAISE(ABORT,'immutable repository relation'); END;
CREATE TRIGGER rrr_event_report_time BEFORE INSERT ON resource_repository_relations
WHEN NEW.relation_kind IN('transfer_from_repository','transfer_to_repository')
 AND EXISTS(
  SELECT 1 FROM resource_repository_relations peer
  WHERE peer.service_instance_uuidv4=NEW.service_instance_uuidv4
    AND peer.resource_kind=NEW.resource_kind
    AND peer.provider_resource_id=NEW.provider_resource_id
    AND peer.clock_json=NEW.clock_json
    AND peer.provenance_json=NEW.provenance_json
    AND peer.relation_kind IN('transfer_from_repository','transfer_to_repository')
    AND NOT (peer.relation_kind=NEW.relation_kind AND peer.target_json=NEW.target_json)
    AND peer.observed_at_us IS NOT NEW.observed_at_us
 )
BEGIN SELECT RAISE(ABORT,'transfer event report observed_at_us mismatch'); END;
CREATE TRIGGER rrr_no_rebind BEFORE INSERT ON resource_repository_relations
WHEN EXISTS(
 SELECT 1 FROM resource_repository_relations existing
 WHERE existing.service_instance_uuidv4=NEW.service_instance_uuidv4
   AND existing.resource_kind=NEW.resource_kind
   AND existing.provider_resource_id=NEW.provider_resource_id
   AND existing.relation_kind=NEW.relation_kind
   AND existing.clock_json=NEW.clock_json
   AND existing.target_json=NEW.target_json
   AND existing.provenance_json=NEW.provenance_json
   AND existing.observed_at_us IS NOT NEW.observed_at_us
) OR (
 NEW.relation_kind IN('owning_repository','base_repository','head_repository')
 AND NEW.source_clock_us IS NOT NULL
 AND EXISTS(
  SELECT 1 FROM resource_repository_relations later
  WHERE later.service_instance_uuidv4=NEW.service_instance_uuidv4
    AND later.resource_kind=NEW.resource_kind
    AND later.provider_resource_id=NEW.provider_resource_id
    AND later.relation_kind=NEW.relation_kind
    AND later.clock_domain=NEW.clock_domain
    AND later.source_clock_us>NEW.source_clock_us
 )
)
BEGIN
 SELECT CASE
  WHEN EXISTS(
   SELECT 1 FROM resource_repository_relations existing
   WHERE existing.service_instance_uuidv4=NEW.service_instance_uuidv4
     AND existing.resource_kind=NEW.resource_kind
     AND existing.provider_resource_id=NEW.provider_resource_id
     AND existing.relation_kind=NEW.relation_kind
     AND existing.clock_json=NEW.clock_json
     AND existing.target_json=NEW.target_json
     AND existing.provenance_json=NEW.provenance_json
     AND existing.observed_at_us IS NOT NEW.observed_at_us
  ) THEN RAISE(ABORT,'resource_repository_relations observed_at_us rebind')
  ELSE RAISE(ABORT,'stale current repository relation candidate')
 END;
END;
CREATE TRIGGER rrr_delete_guard BEFORE DELETE ON resource_repository_relations
WHEN OLD.relation_kind NOT IN('owning_repository','base_repository','head_repository')
  OR OLD.source_clock_us IS NULL
  OR NOT EXISTS(
   SELECT 1 FROM resource_repository_relations later
   WHERE later.service_instance_uuidv4=OLD.service_instance_uuidv4
     AND later.resource_kind=OLD.resource_kind
     AND later.provider_resource_id=OLD.provider_resource_id
     AND later.relation_kind=OLD.relation_kind
     AND later.clock_domain=OLD.clock_domain
     AND later.source_clock_us>OLD.source_clock_us
  )
BEGIN SELECT RAISE(ABORT,'only dominated current candidates may be deleted'); END;
CREATE TRIGGER rrr_prune_dominated AFTER INSERT ON resource_repository_relations
WHEN NEW.relation_kind IN('owning_repository','base_repository','head_repository')
  AND NEW.source_clock_us IS NOT NULL
BEGIN
 DELETE FROM resource_repository_relations
 WHERE service_instance_uuidv4=NEW.service_instance_uuidv4
   AND resource_kind=NEW.resource_kind
   AND provider_resource_id=NEW.provider_resource_id
   AND relation_kind=NEW.relation_kind
   AND clock_domain=NEW.clock_domain
   AND source_clock_us IS NOT NULL
   AND source_clock_us<NEW.source_clock_us;
END;
CREATE TABLE repository_mapping_dispositions(
 service_instance_uuidv4 TEXT NOT NULL,
 resource_kind TEXT NOT NULL CHECK(resource_kind='repository'),
 provider_resource_id TEXT NOT NULL,
 relation_kind TEXT NOT NULL CHECK(relation_kind='represents_repository'),
 claim_clock_json TEXT NOT NULL CHECK(p1_mapping_clock(claim_clock_json)=1),
 claim_target_json TEXT NOT NULL CHECK(p1_mapping_target(claim_target_json)=1 AND json_type(claim_target_json)='text'),
 claim_provenance_json TEXT NOT NULL CHECK(p1_mapping_provenance(claim_provenance_json)=1),
 disposition_kind TEXT NOT NULL CHECK(disposition_kind IN('withdraw','correct','dispute')),
 disposition_clock_json TEXT NOT NULL CHECK(p1_mapping_clock(disposition_clock_json)=1),
 disposition_provenance_json TEXT NOT NULL CHECK(p1_mapping_provenance(disposition_provenance_json)=1),
 observed_at_us INTEGER CHECK(observed_at_us IS NULL OR (typeof(observed_at_us)='integer' AND observed_at_us>0)),
 replacement_clock_json TEXT CHECK(replacement_clock_json IS NULL OR p1_mapping_clock(replacement_clock_json)=1),
 replacement_target_json TEXT CHECK(replacement_target_json IS NULL OR (p1_mapping_target(replacement_target_json)=1 AND json_type(replacement_target_json)='text')),
 replacement_provenance_json TEXT CHECK(replacement_provenance_json IS NULL OR p1_mapping_provenance(replacement_provenance_json)=1),
 CHECK((disposition_kind='correct' AND replacement_clock_json IS NOT NULL AND replacement_target_json IS NOT NULL AND replacement_provenance_json IS NOT NULL) OR (disposition_kind!='correct' AND replacement_clock_json IS NULL AND replacement_target_json IS NULL AND replacement_provenance_json IS NULL)),
 CHECK(disposition_kind!='correct' OR replacement_clock_json!=claim_clock_json OR replacement_target_json!=claim_target_json OR replacement_provenance_json!=claim_provenance_json),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,claim_clock_json,claim_target_json,claim_provenance_json,disposition_kind,disposition_clock_json,disposition_provenance_json),
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,claim_clock_json,claim_target_json,claim_provenance_json) REFERENCES resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,clock_json,target_json,provenance_json) ON DELETE RESTRICT,
 FOREIGN KEY(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,replacement_clock_json,replacement_target_json,replacement_provenance_json) REFERENCES resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,clock_json,target_json,provenance_json) ON DELETE RESTRICT
) STRICT, WITHOUT ROWID;
CREATE INDEX rmd_by_provider_target ON repository_mapping_dispositions(
 service_instance_uuidv4,resource_kind,provider_resource_id,claim_target_json,disposition_kind
);
CREATE INDEX rmd_by_replacement ON repository_mapping_dispositions(
 service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,replacement_clock_json,replacement_target_json,replacement_provenance_json
) WHERE replacement_target_json IS NOT NULL;
CREATE TRIGGER rmd_no_rebind BEFORE INSERT ON repository_mapping_dispositions
WHEN EXISTS(
 SELECT 1 FROM repository_mapping_dispositions existing
 WHERE existing.service_instance_uuidv4=NEW.service_instance_uuidv4
   AND existing.resource_kind=NEW.resource_kind
   AND existing.provider_resource_id=NEW.provider_resource_id
   AND existing.relation_kind=NEW.relation_kind
   AND existing.claim_clock_json=NEW.claim_clock_json
   AND existing.claim_target_json=NEW.claim_target_json
   AND existing.claim_provenance_json=NEW.claim_provenance_json
   AND existing.disposition_kind=NEW.disposition_kind
   AND existing.disposition_clock_json=NEW.disposition_clock_json
   AND existing.disposition_provenance_json=NEW.disposition_provenance_json
   AND (
    existing.observed_at_us IS NOT NEW.observed_at_us
    OR existing.replacement_clock_json IS NOT NEW.replacement_clock_json
    OR existing.replacement_target_json IS NOT NEW.replacement_target_json
    OR existing.replacement_provenance_json IS NOT NEW.replacement_provenance_json
   )
)
BEGIN SELECT RAISE(ABORT,'repository_mapping_dispositions payload rebind'); END;
CREATE TRIGGER rmd_no_update BEFORE UPDATE ON repository_mapping_dispositions
BEGIN SELECT RAISE(ABORT,'immutable mapping disposition'); END;
CREATE TRIGGER rmd_no_delete BEFORE DELETE ON repository_mapping_dispositions
BEGIN SELECT RAISE(ABORT,'immutable mapping disposition'); END;



-- Exactly FIVE physical authoritative claim columns, no rowid or hidden alias.
CREATE TABLE coverage_claims(
 owner_kind TEXT NOT NULL,
 owner_coordinates_json TEXT NOT NULL,
 observed_at_us INTEGER NOT NULL CHECK(typeof(observed_at_us)='integer' AND observed_at_us>0),
 coverage_state TEXT NOT NULL CHECK(coverage_state IN('complete','partial','unknown','not_applicable')),
 details_json TEXT CHECK(details_json IS NULL OR p1_json(details_json)),
 PRIMARY KEY(owner_kind,owner_coordinates_json,observed_at_us,coverage_state),
 FOREIGN KEY(owner_kind,owner_coordinates_json) REFERENCES coverage_scopes
) STRICT, WITHOUT ROWID;
CREATE TRIGGER coverage_claim_no_update BEFORE UPDATE ON coverage_claims BEGIN SELECT RAISE(ABORT,'immutable Coverage claim'); END;
CREATE TRIGGER coverage_claim_no_delete BEFORE DELETE ON coverage_claims BEGIN SELECT RAISE(ABORT,'immutable Coverage claim'); END;
CREATE TRIGGER coverage_claim_no_replace BEFORE INSERT ON coverage_claims WHEN EXISTS(
 SELECT 1 FROM coverage_claims WHERE owner_kind=NEW.owner_kind AND owner_coordinates_json=NEW.owner_coordinates_json AND observed_at_us=NEW.observed_at_us AND coverage_state=NEW.coverage_state)
 BEGIN SELECT RAISE(ABORT,'Coverage exact replay must be compared before insert'); END;

CREATE TRIGGER p1_immutable_store_identity_update BEFORE UPDATE ON store_identity BEGIN SELECT RAISE(ABORT,'immutable context fact'); END;

CREATE TRIGGER p1_immutable_store_identity_delete BEFORE DELETE ON store_identity BEGIN SELECT RAISE(ABORT,'immutable context fact'); END;

-- A replay cannot silently bind the same semantic report key to a new clock.
CREATE TRIGGER cp_relation_no_rebind BEFORE INSERT ON resource_relations
WHEN EXISTS(SELECT 1 FROM resource_relations old WHERE
 old.service_instance_uuidv4=NEW.service_instance_uuidv4 AND old.resource_kind=NEW.resource_kind
 AND old.provider_resource_id=NEW.provider_resource_id AND old.relation_kind=NEW.relation_kind
 AND old.members_json=NEW.members_json AND old.provenance_json=NEW.provenance_json
 AND old.scope_json=NEW.scope_json AND old.observed_at_us IS NOT NEW.observed_at_us)
BEGIN SELECT RAISE(ABORT,'relation original observation rebind'); END;
-- Exact EventReportKey owns one immutable whole group, as in typed admission.
CREATE TRIGGER cp_event_report_no_rebind BEFORE INSERT ON resource_relations
WHEN NEW.relation_kind='transfer_event_report' AND EXISTS(
 SELECT 1 FROM resource_relations old WHERE old.relation_kind='transfer_event_report'
 AND old.service_instance_uuidv4=NEW.service_instance_uuidv4 AND old.resource_kind=NEW.resource_kind
 AND old.provider_resource_id=NEW.provider_resource_id AND old.report_clock_json=NEW.report_clock_json
 AND old.provenance_json=NEW.provenance_json
 AND (old.members_json!=NEW.members_json OR old.scope_json!=NEW.scope_json OR old.observed_at_us IS NOT NEW.observed_at_us))
BEGIN SELECT RAISE(ABORT,'immutable whole event report rebind'); END;
CREATE TRIGGER cp_endpoint_report_time BEFORE INSERT ON resource_repository_relations
WHEN NEW.relation_kind IN('transfer_from_repository','transfer_to_repository') AND EXISTS(
 SELECT 1 FROM resource_relations report WHERE report.service_instance_uuidv4=NEW.service_instance_uuidv4
 AND report.resource_kind=NEW.resource_kind AND report.provider_resource_id=NEW.provider_resource_id
 AND report.relation_kind='transfer_event_report' AND report.members_json=NEW.event_report_members_json
 AND report.scope_json=NEW.event_report_scope_json AND report.provenance_json=NEW.provenance_json
 AND report.observed_at_us IS NOT NEW.observed_at_us)
BEGIN SELECT RAISE(ABORT,'endpoint/report observation mismatch'); END;
-- The newly introduced complete report reference is immutable non-key payload.
-- BEFORE INSERT is essential: conflict-ignore skips later CHECK/FK evaluation.
CREATE TRIGGER cp_endpoint_no_rebind BEFORE INSERT ON resource_repository_relations
WHEN EXISTS(SELECT 1 FROM resource_repository_relations old WHERE
 old.service_instance_uuidv4=NEW.service_instance_uuidv4 AND old.resource_kind=NEW.resource_kind
 AND old.provider_resource_id=NEW.provider_resource_id AND old.relation_kind=NEW.relation_kind
 AND old.clock_json=NEW.clock_json AND old.target_json=NEW.target_json AND old.provenance_json=NEW.provenance_json
 AND (old.event_report_members_json IS NOT NEW.event_report_members_json OR old.event_report_scope_json IS NOT NEW.event_report_scope_json))
BEGIN SELECT RAISE(ABORT,'endpoint support payload rebind'); END;

-- Resource identification metadata is deterministic, but conflict-ignore can skip
-- its consistency CHECK. Reject an inadmissible purported replay before that path.
CREATE TRIGGER cp_resource_no_rebind BEFORE INSERT ON resources
WHEN EXISTS(SELECT 1 FROM resources old WHERE
 old.service_instance_uuidv4=NEW.service_instance_uuidv4 AND old.resource_kind=NEW.resource_kind
 AND old.provider_resource_id=NEW.provider_resource_id
 AND (old.identifier_namespace_kind IS NOT NEW.identifier_namespace_kind
 OR old.identifier_namespace_id IS NOT NEW.identifier_namespace_id
 OR old.document_kind IS NOT NEW.document_kind
 OR old.provider_document_id IS NOT NEW.provider_document_id))
BEGIN SELECT RAISE(ABORT,'Resource identification payload rebind'); END;
