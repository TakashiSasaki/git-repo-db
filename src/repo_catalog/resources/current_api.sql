-- Direct typed current API resources and independent domain scope evidence.
CREATE TABLE change_request_state(
 change_request_id TEXT PRIMARY KEY REFERENCES change_requests(change_request_id),
 kind TEXT NOT NULL CHECK(kind='change-request'), provider_resource_id TEXT,
 state TEXT, draft INTEGER CHECK(draft IN (0,1)), merged INTEGER CHECK(merged IN (0,1)), locked INTEGER CHECK(locked IN (0,1)), author TEXT, url TEXT,
 object_format TEXT CHECK(object_format IN ('sha1','sha256')), head_oid BLOB, base_oid BLOB, merge_oid BLOB,
 head_ref TEXT,base_ref TEXT, head_repository_binding_id TEXT REFERENCES repository_bindings(repository_binding_id),base_repository_binding_id TEXT REFERENCES repository_bindings(repository_binding_id),
 created_at_us INTEGER, closed_at_us INTEGER, merged_at_us INTEGER,
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4),
 repository_binding_id TEXT NOT NULL, service_instance_uuidv4 TEXT NOT NULL REFERENCES service_instances(service_instance_uuidv4),
 provider_updated_at_us INTEGER, provider_clock_scope TEXT,
 observed_at_us INTEGER NOT NULL, last_checked_at_us INTEGER, parsed_at_us INTEGER NOT NULL,
 parser_module TEXT NOT NULL CHECK(length(parser_module)>0 AND instr(parser_module,char(0))=0),
 parser_version TEXT NOT NULL CHECK(length(parser_version)>0 AND instr(parser_version,char(0))=0),
 metadata TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata) AND json_type(metadata)='object'),
 acquisition_scope_json TEXT NOT NULL CHECK(json_valid(acquisition_scope_json) AND json_type(acquisition_scope_json)='object'),
 field_evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(field_evidence_json) AND json_type(field_evidence_json)='object'),
 FOREIGN KEY(repository_binding_id,repository_uuidv4) REFERENCES repository_bindings(repository_binding_id,repository_uuidv4),
 FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4),
 CHECK((head_oid IS NULL AND base_oid IS NULL AND merge_oid IS NULL) OR (object_format IS NOT NULL AND (head_oid IS NULL OR length(head_oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END) AND (base_oid IS NULL OR length(base_oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END) AND (merge_oid IS NULL OR length(merge_oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END)))
) STRICT;
CREATE TABLE document_state(
 change_request_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('pr-title','pr-body','issue-comment')),
 provider_change_request_document_id TEXT NOT NULL,
 body_status TEXT NOT NULL CHECK(body_status IN ('present','provider-null','missing','inaccessible')),
 text_body_sha256 BLOB REFERENCES text_bodies(sha256), author TEXT,url TEXT,deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN (0,1)),
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4),
 repository_binding_id TEXT NOT NULL, service_instance_uuidv4 TEXT NOT NULL REFERENCES service_instances(service_instance_uuidv4),
 provider_updated_at_us INTEGER, provider_clock_scope TEXT,
 observed_at_us INTEGER NOT NULL, last_checked_at_us INTEGER, parsed_at_us INTEGER NOT NULL,
 parser_module TEXT NOT NULL CHECK(length(parser_module)>0 AND instr(parser_module,char(0))=0),
 parser_version TEXT NOT NULL CHECK(length(parser_version)>0 AND instr(parser_version,char(0))=0),
 metadata TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata) AND json_type(metadata)='object'),
 acquisition_scope_json TEXT NOT NULL CHECK(json_valid(acquisition_scope_json) AND json_type(acquisition_scope_json)='object'),
 field_evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(field_evidence_json) AND json_type(field_evidence_json)='object'),
 FOREIGN KEY(repository_binding_id,repository_uuidv4) REFERENCES repository_bindings(repository_binding_id,repository_uuidv4),
 PRIMARY KEY(change_request_id,kind,provider_change_request_document_id),
 FOREIGN KEY(change_request_id,kind,provider_change_request_document_id) REFERENCES documents(change_request_id,kind,provider_change_request_document_id),
 FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4),
 CHECK((body_status='present' AND text_body_sha256 IS NOT NULL) OR (body_status<>'present' AND text_body_sha256 IS NULL))
) STRICT;
CREATE TABLE review_thread_state(
 change_request_id TEXT NOT NULL,provider_resource_id TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind='review-thread'),
 resolved INTEGER CHECK(resolved IN (0,1)),outdated INTEGER CHECK(outdated IN (0,1)),
 raw_path BLOB,line INTEGER,start_line INTEGER,original_line INTEGER,original_start_line INTEGER,side TEXT,start_side TEXT,
 object_format TEXT CHECK(object_format IN ('sha1','sha256')),commit_oid BLOB,original_commit_oid BLOB,diff_hunk TEXT,
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4),
 repository_binding_id TEXT NOT NULL, service_instance_uuidv4 TEXT NOT NULL REFERENCES service_instances(service_instance_uuidv4),
 provider_updated_at_us INTEGER, provider_clock_scope TEXT,
 observed_at_us INTEGER NOT NULL, last_checked_at_us INTEGER, parsed_at_us INTEGER NOT NULL,
 parser_module TEXT NOT NULL CHECK(length(parser_module)>0 AND instr(parser_module,char(0))=0),
 parser_version TEXT NOT NULL CHECK(length(parser_version)>0 AND instr(parser_version,char(0))=0),
 metadata TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata) AND json_type(metadata)='object'),
 acquisition_scope_json TEXT NOT NULL CHECK(json_valid(acquisition_scope_json) AND json_type(acquisition_scope_json)='object'),
 field_evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(field_evidence_json) AND json_type(field_evidence_json)='object'),
 FOREIGN KEY(repository_binding_id,repository_uuidv4) REFERENCES repository_bindings(repository_binding_id,repository_uuidv4),
 PRIMARY KEY(change_request_id,provider_resource_id),
 FOREIGN KEY(change_request_id,provider_resource_id) REFERENCES review_threads(change_request_id,provider_resource_id),
 FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4),
 CHECK((commit_oid IS NULL AND original_commit_oid IS NULL) OR (object_format IS NOT NULL AND (commit_oid IS NULL OR length(commit_oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END) AND (original_commit_oid IS NULL OR length(original_commit_oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END)))
) STRICT;

CREATE TABLE code_assessments(
 code_assessment_id TEXT PRIMARY KEY,change_request_id TEXT NOT NULL,repository_uuidv4 TEXT NOT NULL,
 commit_code_listing_id TEXT,file_code_listing_id TEXT,state TEXT NOT NULL CHECK(state IN ('pending','partial','complete','unknown')),
 object_format TEXT CHECK(object_format IN ('sha1','sha256')),head_oid BLOB,base_oid BLOB,
 observed_at_us INTEGER,parser_module TEXT NOT NULL,parser_version TEXT NOT NULL,
 details_json TEXT NOT NULL CHECK(json_valid(details_json) AND json_type(details_json)='object'),
 UNIQUE(code_assessment_id,change_request_id),
 FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4),
 FOREIGN KEY(commit_code_listing_id,change_request_id) REFERENCES code_listings(code_listing_id,change_request_id),
 FOREIGN KEY(file_code_listing_id,change_request_id) REFERENCES code_listings(code_listing_id,change_request_id),
 CHECK(state<>'complete' OR (commit_code_listing_id IS NOT NULL AND file_code_listing_id IS NOT NULL)),
 CHECK((head_oid IS NULL AND base_oid IS NULL) OR (object_format IS NOT NULL AND (head_oid IS NULL OR length(head_oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END) AND (base_oid IS NULL OR length(base_oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END)))
) STRICT;
CREATE TABLE code_acquisitions(
 code_assessment_id TEXT NOT NULL REFERENCES code_assessments(code_assessment_id),role TEXT NOT NULL,
 object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),oid BLOB NOT NULL,
 acquisition_root_id INTEGER REFERENCES acquisition_roots(acquisition_root_id),
 PRIMARY KEY(code_assessment_id,role),CHECK(length(oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END)
) STRICT;
CREATE TABLE code_commits(
 code_listing_id TEXT NOT NULL REFERENCES code_listings(code_listing_id),position INTEGER NOT NULL CHECK(position>=0),
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4),object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),oid BLOB NOT NULL,
 metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
 PRIMARY KEY(code_listing_id,position),CHECK(length(oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END)
) STRICT;
CREATE TABLE code_file_changes(
 code_listing_id TEXT NOT NULL REFERENCES code_listings(code_listing_id),position INTEGER NOT NULL CHECK(position>=0),
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4),raw_path BLOB NOT NULL,previous_path BLOB,
 status TEXT,object_format TEXT CHECK(object_format IN ('sha1','sha256')),oid BLOB,
 additions INTEGER,deletions INTEGER,changes INTEGER,patch TEXT,patch_status TEXT,
 metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
 PRIMARY KEY(code_listing_id,position),CHECK(oid IS NULL OR (object_format IS NOT NULL AND length(oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END))
) STRICT;
CREATE TABLE change_request_events(
 change_request_event_uuidv4 TEXT PRIMARY KEY,change_request_id TEXT NOT NULL,repository_uuidv4 TEXT NOT NULL,
 provider_event_id TEXT,event_kind TEXT NOT NULL,actor TEXT,created_at_us INTEGER,
 object_format TEXT CHECK(object_format IN ('sha1','sha256')),commit_oid BLOB,
 metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),observed_at_us INTEGER,parser_module TEXT NOT NULL,parser_version TEXT NOT NULL,
 FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4),
 CHECK(commit_oid IS NULL OR (object_format IS NOT NULL AND length(commit_oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END)),
 UNIQUE(change_request_id,provider_event_id)
) STRICT;
CREATE TABLE source_inventory_assessments(
 source_id TEXT NOT NULL REFERENCES sources(source_id),scope_key TEXT NOT NULL,scope_json TEXT NOT NULL CHECK(json_valid(scope_json) AND json_type(scope_json)='object'),
 observed_at_us INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('complete','partial','unknown')),
 terminal INTEGER NOT NULL CHECK(terminal IN (0,1)),members_json TEXT NOT NULL CHECK(json_valid(members_json) AND json_type(members_json)='array'),
 parser_module TEXT NOT NULL,parser_version TEXT NOT NULL,reason TEXT,
 PRIMARY KEY(source_id,scope_key,observed_at_us,state),CHECK(state<>'complete' OR terminal=1)
) STRICT;
CREATE TABLE thread_collection_requirements(
 fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id),provider_resource_id TEXT NOT NULL,
 child_fetch_collection_id TEXT REFERENCES fetch_collections(fetch_collection_id),required_observed_at_us INTEGER NOT NULL,
 object_format TEXT CHECK(object_format IN ('sha1','sha256')),head_oid BLOB,base_oid BLOB,
 PRIMARY KEY(fetch_collection_id,provider_resource_id)
) STRICT;
CREATE TABLE thread_collection_continuations(
 fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id),provider_resource_id TEXT NOT NULL,
 child_cursor TEXT,observed_at_us INTEGER NOT NULL,PRIMARY KEY(fetch_collection_id,provider_resource_id)
) STRICT;
CREATE TABLE thread_collection_targets(
 fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id),role TEXT NOT NULL,
 object_format TEXT CHECK(object_format IN ('sha1','sha256')),oid BLOB,
 observed_at_us INTEGER NOT NULL,PRIMARY KEY(fetch_collection_id,role),CHECK(oid IS NULL OR (object_format IS NOT NULL AND length(oid)=CASE object_format WHEN 'sha1' THEN 20 ELSE 32 END))
) STRICT;
CREATE TRIGGER change_request_state_identity BEFORE UPDATE ON change_request_state WHEN NEW.change_request_id IS NOT OLD.change_request_id BEGIN SELECT RAISE(ABORT,'immutable resource identity'); END;
CREATE VIEW eligible_change_request_state AS SELECT r.* FROM change_request_state r WHERE NOT EXISTS(SELECT 1 FROM exchange_staging d WHERE d.table_name='change_request_state' AND d.reason='current_state:conflict' AND json_extract(d.record_json,'$.change_request_id')=r.change_request_id);
CREATE INDEX change_request_state_repository ON change_request_state(repository_uuidv4);
CREATE TRIGGER document_state_identity BEFORE UPDATE ON document_state WHEN NEW.change_request_id IS NOT OLD.change_request_id OR NEW.kind IS NOT OLD.kind OR NEW.provider_change_request_document_id IS NOT OLD.provider_change_request_document_id BEGIN SELECT RAISE(ABORT,'immutable resource identity'); END;
CREATE VIEW eligible_document_state AS SELECT r.* FROM document_state r WHERE NOT EXISTS(SELECT 1 FROM exchange_staging d WHERE d.table_name='document_state' AND d.reason='current_state:conflict' AND json_extract(d.record_json,'$.change_request_id')=r.change_request_id AND json_extract(d.record_json,'$.kind')=r.kind AND json_extract(d.record_json,'$.provider_change_request_document_id')=r.provider_change_request_document_id);
CREATE INDEX document_state_repository ON document_state(repository_uuidv4);
CREATE TRIGGER review_thread_state_identity BEFORE UPDATE ON review_thread_state WHEN NEW.change_request_id IS NOT OLD.change_request_id OR NEW.provider_resource_id IS NOT OLD.provider_resource_id BEGIN SELECT RAISE(ABORT,'immutable resource identity'); END;
CREATE VIEW eligible_review_thread_state AS SELECT r.* FROM review_thread_state r WHERE NOT EXISTS(SELECT 1 FROM exchange_staging d WHERE d.table_name='review_thread_state' AND d.reason='current_state:conflict' AND json_extract(d.record_json,'$.change_request_id')=r.change_request_id AND json_extract(d.record_json,'$.provider_resource_id')=r.provider_resource_id);
CREATE INDEX review_thread_state_repository ON review_thread_state(repository_uuidv4);

CREATE VIEW eligible_source_repositories AS SELECT r.* FROM source_repositories r WHERE NOT EXISTS(SELECT 1 FROM exchange_staging d WHERE d.table_name='source_repositories' AND d.reason='current_state:conflict' AND json_extract(d.record_json,'$.source_id')=r.source_id AND json_extract(d.record_json,'$.repository_uuidv4')=r.repository_uuidv4);

-- A replies requirement names the exact parent capture and comparison, not
-- merely a provider thread ID whose earlier enumeration might be complete.
CREATE TRIGGER thread_requirement_owner_insert BEFORE INSERT ON thread_collection_requirements
WHEN NOT EXISTS(SELECT 1 FROM fetch_collections p JOIN review_threads t ON t.change_request_id=p.change_request_id AND t.provider_resource_id=NEW.provider_resource_id WHERE p.fetch_collection_id=NEW.fetch_collection_id)
 OR (NEW.child_fetch_collection_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM fetch_collections p JOIN fetch_collections c ON c.change_request_id=p.change_request_id AND c.repository_uuidv4=p.repository_uuidv4
 WHERE p.fetch_collection_id=NEW.fetch_collection_id AND c.fetch_collection_id=NEW.child_fetch_collection_id
 AND json_extract(c.scope_json,'$.request_context.parent_fetch_collection_id')=NEW.fetch_collection_id
 AND json_extract(c.scope_json,'$.request_context.provider_resource_id')=NEW.provider_resource_id
 AND json_extract(c.scope_json,'$.request_context.parent_observed_at_us')=NEW.required_observed_at_us
 AND json_extract(c.scope_json,'$.request_context.object_format') IS NEW.object_format
 AND json_extract(c.scope_json,'$.request_context.head_oid') IS CASE WHEN NEW.head_oid IS NOT NULL THEN lower(hex(NEW.head_oid)) END
 AND json_extract(c.scope_json,'$.request_context.base_oid') IS CASE WHEN NEW.base_oid IS NOT NULL THEN lower(hex(NEW.base_oid)) END
 ))
BEGIN SELECT RAISE(ABORT,'Thread child does not match required parent capture and targets'); END;
CREATE TRIGGER thread_requirement_identity BEFORE UPDATE ON thread_collection_requirements
WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id OR NEW.provider_resource_id IS NOT OLD.provider_resource_id
BEGIN SELECT RAISE(ABORT,'immutable thread requirement capture'); END;
CREATE TRIGGER thread_requirement_child_update BEFORE UPDATE ON thread_collection_requirements
WHEN NEW.child_fetch_collection_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM fetch_collections p JOIN fetch_collections c ON c.change_request_id=p.change_request_id AND c.repository_uuidv4=p.repository_uuidv4
 WHERE p.fetch_collection_id=NEW.fetch_collection_id AND c.fetch_collection_id=NEW.child_fetch_collection_id
 AND json_extract(c.scope_json,'$.request_context.parent_fetch_collection_id')=NEW.fetch_collection_id
 AND json_extract(c.scope_json,'$.request_context.provider_resource_id')=NEW.provider_resource_id
 AND json_extract(c.scope_json,'$.request_context.parent_observed_at_us')=NEW.required_observed_at_us
 AND json_extract(c.scope_json,'$.request_context.object_format') IS NEW.object_format
 AND json_extract(c.scope_json,'$.request_context.head_oid') IS CASE WHEN NEW.head_oid IS NOT NULL THEN lower(hex(NEW.head_oid)) END
 AND json_extract(c.scope_json,'$.request_context.base_oid') IS CASE WHEN NEW.base_oid IS NOT NULL THEN lower(hex(NEW.base_oid)) END)
BEGIN SELECT RAISE(ABORT,'Thread child does not match required parent capture and targets'); END;
CREATE TRIGGER code_commit_owner BEFORE INSERT ON code_commits
WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN change_requests c USING(change_request_id) WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND c.repository_uuidv4=NEW.repository_uuidv4)
BEGIN SELECT RAISE(ABORT,'Code commit belongs to another listing owner'); END;
CREATE TRIGGER code_file_owner BEFORE INSERT ON code_file_changes
WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN change_requests c USING(change_request_id) WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='files' AND c.repository_uuidv4=NEW.repository_uuidv4)
BEGIN SELECT RAISE(ABORT,'Code file belongs to another listing owner'); END;
CREATE TRIGGER code_assessment_targets BEFORE INSERT ON code_assessments
WHEN (NEW.commit_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.commit_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid))
 OR (NEW.file_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.file_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='files' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid))
 OR (NEW.state='complete' AND NOT EXISTS(SELECT 1 FROM code_listing_progress a JOIN code_listing_progress b ON b.code_listing_id=NEW.file_code_listing_id WHERE a.code_listing_id=NEW.commit_code_listing_id AND a.state='complete' AND b.state='complete'))
BEGIN SELECT RAISE(ABORT,'Code assessment target/list completeness mismatch'); END;
CREATE TRIGGER code_acquisition_target BEFORE INSERT ON code_acquisitions
WHEN NEW.acquisition_root_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_assessments c ON c.code_assessment_id=NEW.code_assessment_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND r.repository_uuidv4=c.repository_uuidv4 AND r.object_format=NEW.object_format AND r.oid=NEW.oid AND r.role=NEW.role)
BEGIN SELECT RAISE(ABORT,'Code acquisition root/role mismatch'); END;
CREATE TRIGGER change_request_state_owner_insert BEFORE INSERT ON change_request_state
WHEN NOT EXISTS(SELECT 1 FROM change_requests c JOIN repository_bindings b USING(repository_binding_id) WHERE c.change_request_id=NEW.change_request_id AND c.repository_uuidv4=NEW.repository_uuidv4 AND c.repository_binding_id=NEW.repository_binding_id AND b.service_instance_uuidv4=NEW.service_instance_uuidv4)
BEGIN SELECT RAISE(ABORT,'Current PR owner mismatch'); END;
CREATE TRIGGER change_request_state_owner_update BEFORE UPDATE ON change_request_state
WHEN NOT EXISTS(SELECT 1 FROM change_requests c JOIN repository_bindings b USING(repository_binding_id) WHERE c.change_request_id=NEW.change_request_id AND c.repository_uuidv4=NEW.repository_uuidv4 AND c.repository_binding_id=NEW.repository_binding_id AND b.service_instance_uuidv4=NEW.service_instance_uuidv4)
BEGIN SELECT RAISE(ABORT,'Current PR owner mismatch'); END;
CREATE TRIGGER document_state_owner_insert BEFORE INSERT ON document_state
WHEN NOT EXISTS(SELECT 1 FROM change_requests c JOIN repository_bindings b USING(repository_binding_id) WHERE c.change_request_id=NEW.change_request_id AND c.repository_uuidv4=NEW.repository_uuidv4 AND c.repository_binding_id=NEW.repository_binding_id AND b.service_instance_uuidv4=NEW.service_instance_uuidv4)
BEGIN SELECT RAISE(ABORT,'Current document owner mismatch'); END;
CREATE TRIGGER document_state_owner_update BEFORE UPDATE ON document_state
WHEN NOT EXISTS(SELECT 1 FROM change_requests c JOIN repository_bindings b USING(repository_binding_id) WHERE c.change_request_id=NEW.change_request_id AND c.repository_uuidv4=NEW.repository_uuidv4 AND c.repository_binding_id=NEW.repository_binding_id AND b.service_instance_uuidv4=NEW.service_instance_uuidv4)
BEGIN SELECT RAISE(ABORT,'Current document owner mismatch'); END;
CREATE TRIGGER review_thread_state_owner_insert BEFORE INSERT ON review_thread_state
WHEN NOT EXISTS(SELECT 1 FROM change_requests c JOIN repository_bindings b USING(repository_binding_id) WHERE c.change_request_id=NEW.change_request_id AND c.repository_uuidv4=NEW.repository_uuidv4 AND c.repository_binding_id=NEW.repository_binding_id AND b.service_instance_uuidv4=NEW.service_instance_uuidv4)
BEGIN SELECT RAISE(ABORT,'Current thread owner mismatch'); END;
CREATE TRIGGER review_thread_state_owner_update BEFORE UPDATE ON review_thread_state
WHEN NOT EXISTS(SELECT 1 FROM change_requests c JOIN repository_bindings b USING(repository_binding_id) WHERE c.change_request_id=NEW.change_request_id AND c.repository_uuidv4=NEW.repository_uuidv4 AND c.repository_binding_id=NEW.repository_binding_id AND b.service_instance_uuidv4=NEW.service_instance_uuidv4)
BEGIN SELECT RAISE(ABORT,'Current thread owner mismatch'); END;

CREATE TRIGGER thread_requirements_after_complete BEFORE INSERT ON thread_collection_requirements WHEN EXISTS(SELECT 1 FROM completion_markers WHERE fetch_collection_id=NEW.fetch_collection_id AND asserted_state='complete' AND json_extract(evidence,'$.kind')='current-resource-tree-v1') BEGIN SELECT RAISE(ABORT,'Completed child requirements cannot grow'); END;
CREATE TRIGGER thread_requirements_update_complete BEFORE UPDATE ON thread_collection_requirements WHEN EXISTS(SELECT 1 FROM completion_markers WHERE fetch_collection_id=NEW.fetch_collection_id AND asserted_state='complete' AND json_extract(evidence,'$.kind')='current-resource-tree-v1') BEGIN SELECT RAISE(ABORT,'Completed child requirements cannot change'); END;
CREATE TRIGGER thread_requirements_delete_complete BEFORE DELETE ON thread_collection_requirements WHEN EXISTS(SELECT 1 FROM completion_markers WHERE fetch_collection_id=OLD.fetch_collection_id AND asserted_state='complete' AND json_extract(evidence,'$.kind')='current-resource-tree-v1') BEGIN SELECT RAISE(ABORT,'Completed child requirements cannot disappear'); END;

CREATE TRIGGER code_assessment_targets_update BEFORE UPDATE ON code_assessments
WHEN (NEW.commit_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.commit_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid))
 OR (NEW.file_code_listing_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM code_listings l WHERE l.code_listing_id=NEW.file_code_listing_id AND l.change_request_id=NEW.change_request_id AND l.kind='files' AND l.object_format IS NEW.object_format AND l.head_oid IS NEW.head_oid AND l.base_oid IS NEW.base_oid))
 OR (NEW.state='complete' AND NOT EXISTS(SELECT 1 FROM code_listing_progress a JOIN code_listing_progress b ON b.code_listing_id=NEW.file_code_listing_id WHERE a.code_listing_id=NEW.commit_code_listing_id AND a.state='complete' AND b.state='complete'))
BEGIN SELECT RAISE(ABORT,'Code assessment target/list completeness mismatch'); END;

CREATE TRIGGER code_acquisition_target_update BEFORE UPDATE ON code_acquisitions
WHEN NEW.acquisition_root_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM acquisition_roots r JOIN code_assessments c ON c.code_assessment_id=NEW.code_assessment_id WHERE r.acquisition_root_id=NEW.acquisition_root_id AND r.repository_uuidv4=c.repository_uuidv4 AND r.object_format=NEW.object_format AND r.oid=NEW.oid AND r.role=NEW.role)
BEGIN SELECT RAISE(ABORT,'Code acquisition root/role mismatch'); END;

CREATE TRIGGER code_commit_owner_update BEFORE UPDATE ON code_commits
WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN change_requests c USING(change_request_id) WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='commits' AND l.object_format IS NEW.object_format AND c.repository_uuidv4=NEW.repository_uuidv4)
BEGIN SELECT RAISE(ABORT,'Code commit belongs to another listing owner'); END;

CREATE TRIGGER code_file_owner_update BEFORE UPDATE ON code_file_changes
WHEN NOT EXISTS(SELECT 1 FROM code_listings l JOIN change_requests c USING(change_request_id) WHERE l.code_listing_id=NEW.code_listing_id AND l.kind='files' AND c.repository_uuidv4=NEW.repository_uuidv4)
BEGIN SELECT RAISE(ABORT,'Code file belongs to another listing owner'); END;
-- A completed exact comparison listing has a fixed domain enumeration.
CREATE TRIGGER code_commits_complete_insert BEFORE INSERT ON code_commits
WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id AND state='complete')
BEGIN SELECT RAISE(ABORT,'Completed code listing cannot gain an entry'); END;
CREATE TRIGGER code_commits_complete_update BEFORE UPDATE ON code_commits
WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=OLD.code_listing_id AND state='complete')
BEGIN SELECT RAISE(ABORT,'Completed code listing content cannot change'); END;
CREATE TRIGGER code_commits_complete_delete BEFORE DELETE ON code_commits
WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=OLD.code_listing_id AND state='complete')
BEGIN SELECT RAISE(ABORT,'Completed code listing content cannot disappear'); END;
CREATE TRIGGER code_files_complete_insert BEFORE INSERT ON code_file_changes
WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=NEW.code_listing_id AND state='complete')
BEGIN SELECT RAISE(ABORT,'Completed code listing cannot gain an entry'); END;
CREATE TRIGGER code_files_complete_update BEFORE UPDATE ON code_file_changes
WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=OLD.code_listing_id AND state='complete')
BEGIN SELECT RAISE(ABORT,'Completed code listing content cannot change'); END;
CREATE TRIGGER code_files_complete_delete BEFORE DELETE ON code_file_changes
WHEN EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=OLD.code_listing_id AND state='complete')
BEGIN SELECT RAISE(ABORT,'Completed code listing content cannot disappear'); END;
CREATE TRIGGER code_listing_progress_complete BEFORE UPDATE ON code_listing_progress
WHEN OLD.state='complete' AND (NEW.state IS NOT OLD.state OR NEW.terminal IS NOT OLD.terminal OR NEW.page_count IS NOT OLD.page_count OR NEW.context_proven IS NOT OLD.context_proven)
BEGIN SELECT RAISE(ABORT,'Completed exact code listing assessment cannot change'); END;
