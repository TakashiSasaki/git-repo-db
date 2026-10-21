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
