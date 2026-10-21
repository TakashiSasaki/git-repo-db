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

-- G3=A: native identification metadata is a typed FK target, not Parent authority.
CREATE UNIQUE INDEX resources_native_event_fk ON resources(
 service_instance_uuidv4,resource_kind,provider_resource_id,reference_document_kind,
 identifier_namespace_kind,identifier_namespace_id);
