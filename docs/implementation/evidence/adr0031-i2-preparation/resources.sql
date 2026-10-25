-- PROPOSED I2 Resources fragment, executed only in disposable databases.
-- namespace_* identifies native scope and has NO referent-existence FK.
CREATE TABLE resources(
 service_instance_uuidv4 TEXT COLLATE BINARY NOT NULL REFERENCES providers
   CHECK(p1_uuid4(service_instance_uuidv4)=1),
 resource_kind TEXT COLLATE BINARY NOT NULL CHECK(resource_kind!=''),
 provider_resource_id TEXT COLLATE BINARY NOT NULL
   CHECK(typeof(provider_resource_id)='text' AND p1_resource_identity_v1(provider_resource_id)=1),
 identifier_namespace_kind TEXT COLLATE BINARY,
 identifier_namespace_id TEXT COLLATE BINARY,
 document_kind TEXT COLLATE BINARY,
 provider_document_id TEXT COLLATE BINARY,
 reference_document_kind TEXT COLLATE BINARY
   GENERATED ALWAYS AS(coalesce(document_kind,'')) VIRTUAL,
 CHECK(p1_resource_identification_v1(resource_kind,provider_resource_id,
   identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id)=1),
 PRIMARY KEY(service_instance_uuidv4,resource_kind,provider_resource_id)
) STRICT, WITHOUT ROWID;
-- Preserve the existing five-column endpoint type target during staging.
CREATE UNIQUE INDEX resources_typed_event_fk ON resources(
 service_instance_uuidv4,resource_kind,provider_resource_id,
 reference_document_kind,identifier_namespace_kind);
-- I3 can reference global Documents through the non-NULL typed absence marker.
CREATE UNIQUE INDEX resources_document_contract_fk ON resources(
 service_instance_uuidv4,resource_kind,provider_resource_id,reference_document_kind);
-- Exact I4 target; this index alone does NOT enforce native-I7 support.
CREATE UNIQUE INDEX resources_native_event_fk ON resources(
 service_instance_uuidv4,resource_kind,provider_resource_id,
 reference_document_kind,identifier_namespace_kind,identifier_namespace_id);
CREATE TRIGGER resources_admit BEFORE INSERT ON resources BEGIN
 SELECT CASE WHEN p1_uuid4(NEW.service_instance_uuidv4)!=1
   OR typeof(NEW.resource_kind)!='text' OR NEW.resource_kind=''
   OR p1_resource_identification_v1(NEW.resource_kind,NEW.provider_resource_id,
       NEW.identifier_namespace_kind,NEW.identifier_namespace_id,
       NEW.document_kind,NEW.provider_document_id)!=1
   THEN RAISE(ABORT,'invalid Resource identification') END;
 -- Deliberately pre-conflict: IGNORE / DO NOTHING cannot hide a contradiction.
 SELECT CASE WHEN EXISTS(SELECT 1 FROM resources r
   WHERE r.service_instance_uuidv4=NEW.service_instance_uuidv4
     AND r.resource_kind=NEW.resource_kind
     AND r.provider_resource_id=NEW.provider_resource_id
     AND (r.identifier_namespace_kind IS NOT NEW.identifier_namespace_kind
       OR r.identifier_namespace_id IS NOT NEW.identifier_namespace_id
       OR r.document_kind IS NOT NEW.document_kind
       OR r.provider_document_id IS NOT NEW.provider_document_id))
   THEN RAISE(ABORT,'Resource identification rebind') END;
END;
-- Existing resources_no_update/resources_no_delete later in context.sql remain.
