 -- Full reference to the preexisting coherent transfer_event_report relation.
 event_report_members_json TEXT,
 event_report_scope_json TEXT,
 event_report_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN 'transfer_event_report' END) VIRTUAL,
 event_parent_resource_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN 'issue' END) VIRTUAL,
 support_relation_kind TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN 'parent' END) VIRTUAL,
 support_members_json TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN cp_get(event_report_scope_json,'parent_members_json') END) VIRTUAL,
 support_scope_json TEXT GENERATED ALWAYS AS(CASE WHEN relation_kind IN('transfer_from_repository','transfer_to_repository') THEN cp_get(event_report_scope_json,'parent_scope_json') END) VIRTUAL,
