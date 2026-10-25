-- Independently executed Task F examples. Install reviewed after.sql and UDFs first.
-- Each block uses a savepoint and rolls back to a fresh empty candidate.
-- Expected SQL failures must not terminate your diagnostic driver early.

-- report/ignore/dependencies-0
-- Expected extended SQL code 1811
SAVEPOINT independent_example;
INSERT INTO providers VALUES('22222222-2222-4222-8222-222222222222','task-f','{}');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','issue','["project-f","I7"]','timeline_event','["evt","91"]');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','repository','"provider-repo-F"',NULL,NULL,NULL,NULL);
INSERT OR IGNORE INTO resource_relations VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','transfer_event_report','[["22222222-2222-4222-8222-222222222222","repository","\"provider-repo-F\""]]','{"evidence":["observed",53],"source":"task-f-independent"}','{"clock":{"at_us":53,"domain":"provider-f"},"event_type":"transferred","from_provider_repository_id":"\"provider-repo-F\"","provided_roles":["transfer_from_repository"],"to_provider_repository_id":null}',53);
ROLLBACK TO independent_example;
RELEASE independent_example;

-- correct-I7-parent/report/upsert_noop
-- Expected extended SQL code 1811
SAVEPOINT independent_example;
INSERT INTO providers VALUES('22222222-2222-4222-8222-222222222222','task-f','{}');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','issue','["project-f","I7"]','timeline_event','["evt","91"]');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','issue','["project-f","I7"]',NULL,NULL,NULL,NULL);
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','repository','"provider-repo-F"',NULL,NULL,NULL,NULL);
INSERT INTO resource_relations VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','parent','[["22222222-2222-4222-8222-222222222222","issue","[\"project-f\",\"I7\"]"]]','{"evidence":["observed",53],"source":"task-f-independent"}','{}',53);
INSERT INTO resource_relations VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','transfer_event_report','[["22222222-2222-4222-8222-222222222222","repository","\"provider-repo-F\""]]','{"evidence":["observed",53],"source":"task-f-independent"}','{"clock":{"at_us":53,"domain":"provider-f"},"event_type":"transferred","from_provider_repository_id":"\"provider-repo-F\"","provided_roles":["transfer_from_repository"],"to_provider_repository_id":null}',53) ON CONFLICT DO UPDATE SET observed_at_us=observed_at_us WHERE 0;
ROLLBACK TO independent_example;
RELEASE independent_example;

-- generic-upsert-update/report
-- Expected extended SQL code 1811
SAVEPOINT independent_example;
INSERT INTO providers VALUES('22222222-2222-4222-8222-222222222222','task-f','{}');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','issue','["project-f","I7"]','timeline_event','["evt","91"]');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','repository','"provider-repo-F"',NULL,NULL,NULL,NULL);
INSERT INTO resource_relations VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','f_relation','[]','{"evidence":["observed",53],"source":"task-f-independent"}','{}',53);
INSERT INTO resource_relations VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','f_relation','[]','{"evidence":["observed",53],"source":"task-f-independent"}','{}',53) ON CONFLICT DO UPDATE SET relation_kind='transfer_event_report';
ROLLBACK TO independent_example;
RELEASE independent_example;

-- multirow/INSERT OR FAIL
-- Expected extended SQL code 1811
SAVEPOINT independent_example;
INSERT INTO providers VALUES('22222222-2222-4222-8222-222222222222','task-f','{}');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','issue','["project-f","I7"]','timeline_event','["evt","91"]');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','repository','"provider-repo-F"',NULL,NULL,NULL,NULL);
INSERT OR FAIL INTO resource_relations VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','f_relation','[]','{"evidence":["observed",53],"source":"task-f-independent"}','{}',53), ('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','transfer_event_report','[["22222222-2222-4222-8222-222222222222","repository","\"provider-repo-F\""]]','{"evidence":["observed",53],"source":"task-f-independent"}','{"clock":{"at_us":53,"domain":"provider-f"},"event_type":"transferred","from_provider_repository_id":"\"provider-repo-F\"","provided_roles":["transfer_from_repository"],"to_provider_repository_id":null}',53) RETURNING relation_kind;
ROLLBACK TO independent_example;
RELEASE independent_example;

-- insert-select-returning/INSERT OR IGNORE
-- Expected extended SQL code 1811
SAVEPOINT independent_example;
INSERT INTO providers VALUES('22222222-2222-4222-8222-222222222222','task-f','{}');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','issue','["project-f","I7"]','timeline_event','["evt","91"]');
INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES('22222222-2222-4222-8222-222222222222','repository','"provider-repo-F"',NULL,NULL,NULL,NULL);
INSERT OR IGNORE INTO resource_relations SELECT '22222222-2222-4222-8222-222222222222','comment','["issue","[\"project-f\",\"I7\"]","timeline_event",["evt","91"]]','transfer_event_report' COLLATE NOCASE,'[["22222222-2222-4222-8222-222222222222","repository","\"provider-repo-F\""]]','{"evidence":["observed",53],"source":"task-f-independent"}','{"clock":{"at_us":53,"domain":"provider-f"},"event_type":"transferred","from_provider_repository_id":"\"provider-repo-F\"","provided_roles":["transfer_from_repository"],"to_provider_repository_id":null}',53 RETURNING relation_kind;
ROLLBACK TO independent_example;
RELEASE independent_example;
