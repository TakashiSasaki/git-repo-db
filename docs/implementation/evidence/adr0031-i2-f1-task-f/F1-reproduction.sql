-- Install exact candidate SQL and register functions before this script.
-- Expected: stage fence rejects final INSERT. Actual: accepted, typed report readable.
INSERT INTO providers VALUES('11111111-1111-4111-8111-111111111111','synthetic','{}');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('11111111-1111-4111-8111-111111111111','comment','["issue","\"I7\"","timeline_event","event"]','issue','"I7"','timeline_event','"event"');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('11111111-1111-4111-8111-111111111111','repository','"unresolved-R"',NULL,NULL,NULL,NULL);
INSERT INTO resource_relations VALUES('11111111-1111-4111-8111-111111111111','comment','["issue","\"I7\"","timeline_event","event"]','transfer_event_report','[["11111111-1111-4111-8111-111111111111","repository","\"unresolved-R\""]]','{"evidence":"native-observation","source":"task-d"}','{"clock":{"at_us":17,"domain":"provider"},"event_type":"transferred","from_provider_repository_id":"\"unresolved-R\"","provided_roles":["transfer_from_repository"],"to_provider_repository_id":null}',17);
SELECT count(*) AS i7_rows FROM resources WHERE resource_kind='issue'; -- 0
SELECT count(*) AS endpoint_rows FROM resource_repository_relations; -- 0
SELECT relation_kind,scope_json FROM resource_relations; -- transfer_event_report returned
PRAGMA foreign_key_check; -- empty
PRAGMA integrity_check; -- ok
