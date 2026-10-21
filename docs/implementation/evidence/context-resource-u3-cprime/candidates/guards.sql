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
