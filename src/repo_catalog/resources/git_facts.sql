-- Required raw bytes and decoded values have direct Git object owners.
CREATE TABLE git_object_payloads(git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id),payload_representation TEXT NOT NULL CHECK(payload_representation='git-object-raw-v1'),payload_sha256 BLOB NOT NULL CHECK(length(payload_sha256)=32),FOREIGN KEY(payload_representation,payload_sha256) REFERENCES payloads(representation,sha256)) STRICT;
CREATE TABLE git_commit_facts(
 git_fact_uuidv4 TEXT PRIMARY KEY NOT NULL,git_object_id INTEGER NOT NULL REFERENCES commits(git_object_id),
 decoder_key TEXT NOT NULL CHECK(length(decoder_key)=64),parser_module TEXT NOT NULL CHECK(length(parser_module)>0),parser_version TEXT NOT NULL CHECK(length(parser_version)>0),
 metadata_encoding TEXT NOT NULL CHECK(metadata_encoding IN ('utf-8','latin-1')),metadata_errors TEXT NOT NULL CHECK(metadata_errors IN ('strict','replace','backslashreplace')),
 text_encoding TEXT NOT NULL CHECK(text_encoding IN ('utf-8','latin-1')),max_text_blob_bytes INTEGER NOT NULL CHECK(max_text_blob_bytes>=0),
 message_text TEXT NOT NULL,metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),UNIQUE(git_object_id,decoder_key)
) STRICT;
CREATE TABLE git_text_facts(
 git_fact_uuidv4 TEXT PRIMARY KEY NOT NULL,git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id),content_id INTEGER NOT NULL REFERENCES contents(content_id),
 decoder_key TEXT NOT NULL CHECK(length(decoder_key)=64),parser_module TEXT NOT NULL CHECK(length(parser_module)>0),parser_version TEXT NOT NULL CHECK(length(parser_version)>0),
 text_encoding TEXT NOT NULL CHECK(text_encoding IN ('utf-8','latin-1')),max_text_blob_bytes INTEGER NOT NULL CHECK(max_text_blob_bytes>=0),
 metadata_encoding TEXT NOT NULL CHECK(metadata_encoding IN ('utf-8','latin-1')),metadata_errors TEXT NOT NULL CHECK(metadata_errors IN ('strict','replace','backslashreplace')),
 text_state TEXT NOT NULL CHECK(text_state IN ('eligible','nul','non_utf8','oversize','unknown')),raw_text TEXT,UNIQUE(git_object_id,decoder_key),
 CHECK((text_state='eligible' AND raw_text IS NOT NULL) OR (text_state<>'eligible' AND raw_text IS NULL))
) STRICT;
CREATE TABLE git_name_facts(
 tree_git_object_id INTEGER NOT NULL,raw_name BLOB NOT NULL,decoder_key TEXT NOT NULL CHECK(length(decoder_key)=64),
 parser_module TEXT NOT NULL CHECK(length(parser_module)>0),parser_version TEXT NOT NULL CHECK(length(parser_version)>0),
 metadata_encoding TEXT NOT NULL CHECK(metadata_encoding IN ('utf-8','latin-1')),metadata_errors TEXT NOT NULL CHECK(metadata_errors IN ('strict','replace','backslashreplace')),
 text_encoding TEXT NOT NULL CHECK(text_encoding IN ('utf-8','latin-1')),max_text_blob_bytes INTEGER NOT NULL CHECK(max_text_blob_bytes>=0),
 decoded_name TEXT NOT NULL,PRIMARY KEY(tree_git_object_id,raw_name,decoder_key),
 FOREIGN KEY(tree_git_object_id,raw_name) REFERENCES tree_entries(tree_git_object_id,raw_name)
) STRICT;
CREATE TRIGGER git_object_payloads_length BEFORE INSERT ON git_object_payloads WHEN NOT EXISTS(SELECT 1 FROM git_objects g JOIN stored_bytes b ON b.sha256=NEW.payload_sha256 WHERE g.git_object_id=NEW.git_object_id AND g.size=b.byte_length) BEGIN SELECT RAISE(ABORT,'Git raw payload length mismatch'); END;
CREATE TRIGGER git_object_payloads_identity BEFORE INSERT ON git_object_payloads WHEN NOT EXISTS(
 SELECT 1 FROM git_objects g JOIN stored_bytes b ON b.sha256=NEW.payload_sha256 WHERE g.git_object_id=NEW.git_object_id
 AND repo_catalog_git_object_identity_valid(g.object_format,hex(g.oid),g.type,g.size,b.body,NEW.payload_sha256)=1
) BEGIN SELECT RAISE(ABORT,'Git raw payload identity mismatch'); END;
CREATE TRIGGER git_text_facts_content BEFORE INSERT ON git_text_facts WHEN NOT EXISTS(SELECT 1 FROM blob_content_map b JOIN git_objects g USING(git_object_id) WHERE b.git_object_id=NEW.git_object_id AND b.content_id=NEW.content_id AND g.type='blob') BEGIN SELECT RAISE(ABORT,'Git text requires matching raw blob identity'); END;
CREATE TRIGGER commits_object_type BEFORE INSERT ON commits WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.git_object_id AND type='commit' AND object_format=NEW.tree_format) BEGIN SELECT RAISE(ABORT,'commit object identity mismatch'); END;
CREATE TRIGGER tree_objects_object_type BEFORE INSERT ON tree_objects WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.git_object_id AND type='tree') BEGIN SELECT RAISE(ABORT,'tree object identity mismatch'); END;
CREATE TRIGGER tag_objects_object_type BEFORE INSERT ON tag_objects WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.git_object_id AND type='tag' AND object_format=NEW.target_format) BEGIN SELECT RAISE(ABORT,'tag object identity mismatch'); END;
CREATE TRIGGER tree_entries_format BEFORE INSERT ON tree_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.tree_git_object_id AND object_format=NEW.child_format) BEGIN SELECT RAISE(ABORT,'tree child format mismatch'); END;
CREATE TRIGGER commit_parents_format BEFORE INSERT ON commit_parents WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.commit_git_object_id AND object_format=NEW.parent_format) BEGIN SELECT RAISE(ABORT,'parent format mismatch'); END;
CREATE TRIGGER commit_parents_ordinal BEFORE INSERT ON commit_parents WHEN NOT EXISTS(SELECT 1 FROM commits WHERE git_object_id=NEW.commit_git_object_id AND parent_count>NEW.parent_ordinal) BEGIN SELECT RAISE(ABORT,'parent ordinal outside canonical sequence'); END;
CREATE TRIGGER root_manifest_entries_format BEFORE INSERT ON root_manifest_entries WHEN NOT EXISTS(SELECT 1 FROM git_objects WHERE git_object_id=NEW.tree_git_object_id AND object_format=NEW.object_format) BEGIN SELECT RAISE(ABORT,'manifest child format mismatch'); END;
-- Decoded candidates are computed from the actual byte subject and explicit settings.
CREATE TRIGGER git_text_facts_bytes BEFORE INSERT ON git_text_facts WHEN NOT EXISTS(
 SELECT 1 FROM git_objects g JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 WHERE g.git_object_id=NEW.git_object_id AND g.type='blob'
 AND NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=p.payload_sha256)
 AND repo_catalog_git_object_identity_valid(g.object_format,hex(g.oid),g.type,g.size,b.body,p.payload_sha256)=1 AND repo_catalog_git_decoded_value_valid('text',g.object_format,b.body,NEW.decoder_key,json_object('parser_module',NEW.parser_module,'parser_version',NEW.parser_version,'text_encoding',NEW.text_encoding,'metadata_encoding',NEW.metadata_encoding,'metadata_errors',NEW.metadata_errors,'max_text_blob_bytes',NEW.max_text_blob_bytes),NEW.text_state,NEW.raw_text,NULL)=1
) BEGIN SELECT RAISE(ABORT,'Git decoder value contradicts raw bytes or settings'); END;
CREATE VIEW valid_git_text_facts AS
 SELECT f.* FROM git_text_facts f JOIN available_git_objects g ON g.git_object_id=f.git_object_id JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 JOIN blob_content_map m ON m.git_object_id=g.git_object_id AND m.content_id=f.content_id
 WHERE g.type='blob' AND repo_catalog_git_decoded_value_valid('text',g.object_format,b.body,f.decoder_key,json_object('parser_module',f.parser_module,'parser_version',f.parser_version,'text_encoding',f.text_encoding,'metadata_encoding',f.metadata_encoding,'metadata_errors',f.metadata_errors,'max_text_blob_bytes',f.max_text_blob_bytes),f.text_state,f.raw_text,NULL)=1;
CREATE TRIGGER git_commit_facts_bytes BEFORE INSERT ON git_commit_facts WHEN NOT EXISTS(
 SELECT 1 FROM git_objects g JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 WHERE g.git_object_id=NEW.git_object_id AND g.type='commit'
 AND NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=p.payload_sha256)
 AND repo_catalog_git_object_identity_valid(g.object_format,hex(g.oid),g.type,g.size,b.body,p.payload_sha256)=1 AND repo_catalog_git_decoded_value_valid('commit',g.object_format,b.body,NEW.decoder_key,json_object('parser_module',NEW.parser_module,'parser_version',NEW.parser_version,'text_encoding',NEW.text_encoding,'metadata_encoding',NEW.metadata_encoding,'metadata_errors',NEW.metadata_errors,'max_text_blob_bytes',NEW.max_text_blob_bytes),NULL,NEW.message_text,NEW.metadata)=1
) BEGIN SELECT RAISE(ABORT,'Git decoder value contradicts raw bytes or settings'); END;
CREATE VIEW valid_git_commit_facts AS
 SELECT f.* FROM git_commit_facts f JOIN available_git_objects g ON g.git_object_id=f.git_object_id JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256
 WHERE g.type='commit' AND repo_catalog_git_decoded_value_valid('commit',g.object_format,b.body,f.decoder_key,json_object('parser_module',f.parser_module,'parser_version',f.parser_version,'text_encoding',f.text_encoding,'metadata_encoding',f.metadata_encoding,'metadata_errors',f.metadata_errors,'max_text_blob_bytes',f.max_text_blob_bytes),NULL,f.message_text,f.metadata)=1;
CREATE TRIGGER git_name_facts_bytes BEFORE INSERT ON git_name_facts WHEN NOT EXISTS(
 SELECT 1 FROM git_objects g JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 JOIN tree_entries e ON e.tree_git_object_id=g.git_object_id AND e.raw_name=NEW.raw_name WHERE g.git_object_id=NEW.tree_git_object_id AND g.type='tree'
 AND NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=p.payload_sha256)
 AND repo_catalog_git_name_subject_valid(g.object_format,substr(b.body,e.entry_offset+1,e.entry_length),e.raw_name,0,e.entry_length,e.mode,e.child_oid)=1 AND repo_catalog_git_decoded_value_valid('name',g.object_format,NULL,NEW.decoder_key,json_object('parser_module',NEW.parser_module,'parser_version',NEW.parser_version,'text_encoding',NEW.text_encoding,'metadata_encoding',NEW.metadata_encoding,'metadata_errors',NEW.metadata_errors,'max_text_blob_bytes',NEW.max_text_blob_bytes),NEW.raw_name,NEW.decoded_name,NULL)=1
) BEGIN SELECT RAISE(ABORT,'Git decoder value contradicts raw bytes or settings'); END;
CREATE VIEW valid_git_name_facts AS
 SELECT f.* FROM available_git_objects g CROSS JOIN git_name_facts f ON g.git_object_id=f.tree_git_object_id JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 JOIN tree_entries e ON e.tree_git_object_id=g.git_object_id AND e.raw_name=f.raw_name
 WHERE g.type='tree' AND repo_catalog_git_decoded_value_valid('name',g.object_format,NULL,f.decoder_key,json_object('parser_module',f.parser_module,'parser_version',f.parser_version,'text_encoding',f.text_encoding,'metadata_encoding',f.metadata_encoding,'metadata_errors',f.metadata_errors,'max_text_blob_bytes',f.max_text_blob_bytes),f.raw_name,f.decoded_name,NULL)=1;
-- Availability checks raw bytes and the intrinsic sequence, never parser authority.
CREATE VIEW available_git_objects AS
 SELECT g.* FROM git_objects g JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256
 WHERE g.verified=1 AND g.size=b.byte_length AND NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=p.payload_sha256)
 AND repo_catalog_git_object_identity_valid(g.object_format,hex(g.oid),g.type,g.size,b.body,p.payload_sha256)=1
 AND NOT EXISTS(SELECT 1 FROM commits c WHERE c.git_object_id=g.git_object_id AND g.type<>'commit')
 AND NOT EXISTS(SELECT 1 FROM commit_parents c WHERE c.commit_git_object_id=g.git_object_id AND g.type<>'commit')
 AND NOT EXISTS(SELECT 1 FROM tree_objects t WHERE t.git_object_id=g.git_object_id AND g.type<>'tree')
 AND NOT EXISTS(SELECT 1 FROM tree_entries t WHERE t.tree_git_object_id=g.git_object_id AND g.type<>'tree')
 AND NOT EXISTS(SELECT 1 FROM tag_objects t WHERE t.git_object_id=g.git_object_id AND g.type<>'tag')
 AND NOT EXISTS(SELECT 1 FROM blob_content_map m WHERE m.git_object_id=g.git_object_id AND g.type<>'blob')
 AND ((g.type='blob' AND EXISTS(SELECT 1 FROM blob_content_map m JOIN contents c USING(content_id) WHERE m.git_object_id=g.git_object_id AND c.byte_length=g.size
 AND NOT EXISTS(SELECT 1 FROM content_digests d WHERE d.content_id=m.content_id AND repo_catalog_git_content_digest_valid(b.body,d.algorithm,d.digest)<>1)))
 OR (g.type='commit' AND EXISTS(SELECT 1 FROM commits c WHERE c.git_object_id=g.git_object_id AND c.tree_format=g.object_format
 AND repo_catalog_git_commit_shape_valid(g.object_format,b.body,c.tree_oid,c.tree_header_offset,c.parent_count,c.raw_headers,c.raw_message)=1
 AND c.parent_count=(SELECT count(*) FROM commit_parents p WHERE p.commit_git_object_id=c.git_object_id)
 AND (c.tree_git_object_id IS NULL OR EXISTS(SELECT 1 FROM git_objects target WHERE target.git_object_id=c.tree_git_object_id AND target.verified=1 AND EXISTS(SELECT 1 FROM git_object_payloads raw WHERE raw.git_object_id=target.git_object_id) AND target.object_format=c.tree_format AND target.oid=c.tree_oid AND target.type='tree'))
 AND NOT EXISTS(SELECT 1 FROM commit_parents p WHERE p.commit_git_object_id=c.git_object_id AND (
  p.parent_format<>g.object_format OR p.parent_ordinal>=c.parent_count
  OR substr(c.raw_headers,p.parent_header_offset+1,7)<>CAST('parent ' AS BLOB)
  OR lower(CAST(substr(c.raw_headers,p.parent_header_offset+8,length(p.parent_oid)*2) AS TEXT))<>lower(hex(p.parent_oid))
  OR (p.parent_header_offset<>0 AND substr(c.raw_headers,p.parent_header_offset,1)<>X'0a')
  OR (length(c.raw_headers)<>p.parent_header_offset+7+length(p.parent_oid)*2 AND substr(c.raw_headers,p.parent_header_offset+8+length(p.parent_oid)*2,1)<>X'0a')
  OR EXISTS(SELECT 1 FROM commit_parents prior WHERE prior.commit_git_object_id=p.commit_git_object_id AND prior.parent_ordinal=p.parent_ordinal-1 AND prior.parent_header_offset>=p.parent_header_offset)
  OR (p.parent_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects target WHERE target.git_object_id=p.parent_git_object_id AND target.verified=1 AND EXISTS(SELECT 1 FROM git_object_payloads raw WHERE raw.git_object_id=target.git_object_id) AND target.object_format=p.parent_format AND target.oid=p.parent_oid AND target.type='commit'))
 ))))
 OR (g.type='tree' AND repo_catalog_git_tree_shape_valid(g.object_format,b.body)=1 AND EXISTS(SELECT 1 FROM tree_objects t WHERE t.git_object_id=g.git_object_id AND t.entry_count=(SELECT count(*) FROM tree_entries e WHERE e.tree_git_object_id=g.git_object_id) AND g.size=(SELECT coalesce(sum(e.entry_length),0) FROM tree_entries e WHERE e.tree_git_object_id=g.git_object_id) AND NOT EXISTS(SELECT 1 FROM (SELECT entry_offset,lag(entry_offset+entry_length,1,0) OVER (ORDER BY entry_offset) AS expected_offset FROM tree_entries e WHERE e.tree_git_object_id=g.git_object_id) WHERE entry_offset<>expected_offset)
 AND NOT EXISTS(SELECT 1 FROM tree_entries e WHERE e.tree_git_object_id=g.git_object_id AND (
  e.child_format<>g.object_format OR instr(e.raw_name,X'00')<>0
  OR ltrim(CAST(substr(b.body,e.entry_offset+1,e.entry_length-length(e.raw_name)-length(e.child_oid)-2) AS TEXT),'0')<>CASE e.mode WHEN 16384 THEN '40000' WHEN 33188 THEN '100644' WHEN 33261 THEN '100755' WHEN 40960 THEN '120000' WHEN 57344 THEN '160000' END
  OR substr(b.body,e.entry_offset+1,e.entry_length)<>CAST(substr(b.body,e.entry_offset+1,e.entry_length-length(e.raw_name)-length(e.child_oid)-2)||' '||e.raw_name||char(0)||e.child_oid AS BLOB)
  OR (e.child_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects target WHERE target.git_object_id=e.child_git_object_id AND target.verified=1 AND EXISTS(SELECT 1 FROM git_object_payloads raw WHERE raw.git_object_id=target.git_object_id) AND target.object_format=e.child_format AND target.oid=e.child_oid AND target.type=CASE e.mode WHEN 16384 THEN 'tree' ELSE 'blob' END))
 ))))
 OR (g.type='tag' AND EXISTS(SELECT 1 FROM tag_objects t WHERE t.git_object_id=g.git_object_id AND t.target_format=g.object_format AND t.raw_payload=b.body
 AND repo_catalog_git_tag_shape_valid(g.object_format,b.body,t.target_oid,t.target_type)=1
 AND (t.target_git_object_id IS NULL OR EXISTS(SELECT 1 FROM git_objects target WHERE target.git_object_id=t.target_git_object_id AND target.verified=1 AND EXISTS(SELECT 1 FROM git_object_payloads raw WHERE raw.git_object_id=target.git_object_id) AND target.object_format=t.target_format AND target.oid=t.target_oid AND target.type=t.target_type))
 )));
CREATE VIEW available_git_acquisitions AS
 SELECT a.* FROM git_acquisitions a WHERE a.roots_manifest IS NOT NULL
 -- This establishes availability once per exact source object. All remaining
 -- closure checks use indexed identities/membership, avoiding repeated decoding.
 AND NOT EXISTS(SELECT 1 FROM repository_object_sources r WHERE r.git_acquisition_id=a.git_acquisition_id AND NOT EXISTS(SELECT 1 FROM available_git_objects g WHERE g.git_object_id=r.git_object_id))
 AND NOT EXISTS(SELECT 1 FROM json_each(a.roots_manifest) ref WHERE NOT EXISTS(SELECT 1 FROM git_objects g JOIN repository_object_sources r USING(git_object_id) WHERE r.git_acquisition_id=a.git_acquisition_id AND g.object_format=a.object_format AND g.oid=repo_catalog_git_oid_bytes(a.object_format,json_extract(ref.value,'$.oid')) AND g.type=json_extract(ref.value,'$.type')))
 AND NOT EXISTS(SELECT 1 FROM json_each(a.roots_manifest) ref WHERE json_extract(ref.value,'$.peeled') IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g JOIN repository_object_sources r USING(git_object_id) WHERE r.git_acquisition_id=a.git_acquisition_id AND g.object_format=a.object_format AND g.oid=repo_catalog_git_oid_bytes(a.object_format,json_extract(ref.value,'$.peeled'))))
 AND NOT EXISTS(SELECT 1 FROM acquisition_roots root WHERE root.git_acquisition_id=a.git_acquisition_id AND NOT EXISTS(SELECT 1 FROM git_objects g JOIN repository_object_sources r USING(git_object_id) WHERE r.git_acquisition_id=a.git_acquisition_id AND g.object_format=root.object_format AND g.oid=root.oid))
 AND NOT EXISTS(SELECT 1 FROM repository_object_sources source JOIN commits c ON c.git_object_id=source.git_object_id WHERE source.git_acquisition_id=a.git_acquisition_id AND NOT EXISTS(SELECT 1 FROM git_objects g JOIN repository_object_sources r USING(git_object_id) WHERE r.git_acquisition_id=a.git_acquisition_id AND g.object_format=c.tree_format AND g.oid=c.tree_oid AND g.type='tree'))
 AND NOT EXISTS(SELECT 1 FROM repository_object_sources source JOIN commit_parents p ON p.commit_git_object_id=source.git_object_id WHERE source.git_acquisition_id=a.git_acquisition_id AND NOT EXISTS(SELECT 1 FROM git_objects g JOIN repository_object_sources r USING(git_object_id) WHERE r.git_acquisition_id=a.git_acquisition_id AND g.object_format=p.parent_format AND g.oid=p.parent_oid AND g.type='commit'))
 AND NOT EXISTS(SELECT 1 FROM repository_object_sources source JOIN tree_entries e ON e.tree_git_object_id=source.git_object_id WHERE source.git_acquisition_id=a.git_acquisition_id AND e.mode<>57344 AND NOT EXISTS(SELECT 1 FROM git_objects g JOIN repository_object_sources r USING(git_object_id) WHERE r.git_acquisition_id=a.git_acquisition_id AND g.object_format=e.child_format AND g.oid=e.child_oid AND g.type=CASE e.mode WHEN 16384 THEN 'tree' ELSE 'blob' END))
 AND NOT EXISTS(SELECT 1 FROM repository_object_sources source JOIN tag_objects t ON t.git_object_id=source.git_object_id WHERE source.git_acquisition_id=a.git_acquisition_id AND NOT EXISTS(SELECT 1 FROM git_objects g JOIN repository_object_sources r USING(git_object_id) WHERE r.git_acquisition_id=a.git_acquisition_id AND g.object_format=t.target_format AND g.oid=t.target_oid AND g.type=t.target_type));
-- The same exact ref and closure predicate governs readers and completion.
CREATE VIEW valid_ref_captures AS
 SELECT s.* FROM snapshots s JOIN available_git_acquisitions a USING(git_acquisition_id)
 WHERE repo_catalog_git_ref_capture_valid(a.object_format,a.roots_manifest,coalesce((
  SELECT json_group_array(json_object('name_hex',hex(f.raw_ref_name),'object_format',f.object_format,'oid_hex',hex(f.target_oid),'peeled_hex',CASE WHEN f.peeled_oid IS NULL THEN NULL ELSE hex(f.peeled_oid) END,'type',f.target_type)) FROM ref_observations f WHERE f.snapshot_id=s.snapshot_id
 ),'[]'))=1
 AND NOT EXISTS(SELECT 1 FROM acquisition_roots r WHERE r.git_acquisition_id=s.git_acquisition_id AND r.complete=0);
CREATE VIEW available_snapshots AS SELECT s.* FROM valid_ref_captures s WHERE s.complete=1;
-- Frozen ref-capture predecessors preserve divergent heads, without a time winner.
CREATE VIEW current_snapshots AS
 WITH heads AS (SELECT s.* FROM snapshots s WHERE s.complete=1 AND NOT EXISTS(SELECT 1 FROM snapshots n WHERE n.predecessor_snapshot_id=s.snapshot_id AND n.complete=1))
 SELECT a.* FROM available_snapshots a JOIN heads h USING(snapshot_id)
 WHERE (SELECT count(*) FROM heads x WHERE x.repository_uuidv4=a.repository_uuidv4)=1;
CREATE TRIGGER snapshots_complete_insert BEFORE INSERT ON snapshots WHEN NEW.complete=1 BEGIN SELECT RAISE(ABORT,'capture complete only after exact closure validation'); END;
CREATE TRIGGER snapshots_complete_update BEFORE UPDATE ON snapshots WHEN NEW.complete=1 AND OLD.complete=0 AND NOT EXISTS(SELECT 1 FROM valid_ref_captures s WHERE s.snapshot_id=NEW.snapshot_id)
 BEGIN SELECT RAISE(ABORT,'ref capture closure incomplete'); END;
CREATE TRIGGER snapshots_immutable BEFORE UPDATE ON snapshots WHEN NEW.snapshot_id IS NOT OLD.snapshot_id OR NEW.git_acquisition_id IS NOT OLD.git_acquisition_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.predecessor_snapshot_id IS NOT OLD.predecessor_snapshot_id OR NEW.generation IS NOT OLD.generation OR NEW.created_at_us IS NOT OLD.created_at_us OR NEW.complete<OLD.complete BEGIN SELECT RAISE(ABORT,'immutable ref capture'); END;
CREATE TRIGGER acquisition_roots_immutable BEFORE UPDATE ON acquisition_roots WHEN NEW.acquisition_root_id IS NOT OLD.acquisition_root_id OR NEW.git_acquisition_id IS NOT OLD.git_acquisition_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.role IS NOT OLD.role OR NEW.expected_oid IS NOT OLD.expected_oid OR NEW.complete<OLD.complete BEGIN SELECT RAISE(ABORT,'immutable acquired root'); END;
CREATE TRIGGER git_acquisitions_immutable BEFORE UPDATE ON git_acquisitions WHEN NEW.git_acquisition_id IS NOT OLD.git_acquisition_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.repository_endpoint_id IS NOT OLD.repository_endpoint_id OR NEW.endpoint_url IS NOT OLD.endpoint_url OR NEW.source_id IS NOT OLD.source_id OR NEW.kind IS NOT OLD.kind OR NEW.started_at_us IS NOT OLD.started_at_us OR NEW.request IS NOT OLD.request OR (OLD.object_format IS NOT NULL AND NEW.object_format IS NOT OLD.object_format) OR (OLD.roots_manifest IS NOT NULL AND NEW.roots_manifest IS NOT OLD.roots_manifest) OR (OLD.refs_observed_at_us IS NOT NULL AND NEW.refs_observed_at_us IS NOT OLD.refs_observed_at_us) OR (OLD.observed_at_us IS NOT NULL AND NEW.observed_at_us IS NOT OLD.observed_at_us) BEGIN SELECT RAISE(ABORT,'immutable Git capture'); END;
CREATE TRIGGER git_object_payloads_immutable BEFORE UPDATE ON git_object_payloads BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER git_commit_facts_immutable BEFORE UPDATE ON git_commit_facts BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER git_text_facts_immutable BEFORE UPDATE ON git_text_facts BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER tree_objects_immutable BEFORE UPDATE ON tree_objects BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER contents_immutable BEFORE UPDATE ON contents BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER content_digests_immutable BEFORE UPDATE ON content_digests BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER blob_content_map_immutable BEFORE UPDATE ON blob_content_map BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER repository_object_sources_immutable BEFORE UPDATE ON repository_object_sources BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER ref_observations_immutable BEFORE UPDATE ON ref_observations BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER root_origins_immutable BEFORE UPDATE ON root_origins BEGIN SELECT RAISE(ABORT,'immutable Git domain fact'); END;
CREATE TRIGGER git_object_payloads_no_replace BEFORE INSERT ON git_object_payloads WHEN EXISTS(SELECT 1 FROM git_object_payloads WHERE git_object_id=NEW.git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER git_object_payloads_retain BEFORE DELETE ON git_object_payloads BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER git_commit_facts_no_replace BEFORE INSERT ON git_commit_facts WHEN EXISTS(SELECT 1 FROM git_commit_facts WHERE git_object_id=NEW.git_object_id AND decoder_key=NEW.decoder_key) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER git_commit_facts_retain BEFORE DELETE ON git_commit_facts BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER git_text_facts_no_replace BEFORE INSERT ON git_text_facts WHEN EXISTS(SELECT 1 FROM git_text_facts WHERE git_object_id=NEW.git_object_id AND decoder_key=NEW.decoder_key) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER git_text_facts_retain BEFORE DELETE ON git_text_facts BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER tree_objects_no_replace BEFORE INSERT ON tree_objects WHEN EXISTS(SELECT 1 FROM tree_objects WHERE git_object_id=NEW.git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER tree_objects_retain BEFORE DELETE ON tree_objects BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER contents_no_replace BEFORE INSERT ON contents WHEN EXISTS(SELECT 1 FROM contents WHERE content_id=NEW.content_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER contents_retain BEFORE DELETE ON contents BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER content_digests_no_replace BEFORE INSERT ON content_digests WHEN EXISTS(SELECT 1 FROM content_digests WHERE content_id=NEW.content_id AND representation=NEW.representation AND algorithm=NEW.algorithm) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER content_digests_retain BEFORE DELETE ON content_digests BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER blob_content_map_no_replace BEFORE INSERT ON blob_content_map WHEN EXISTS(SELECT 1 FROM blob_content_map WHERE git_object_id=NEW.git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER blob_content_map_retain BEFORE DELETE ON blob_content_map BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER repository_object_sources_no_replace BEFORE INSERT ON repository_object_sources WHEN EXISTS(SELECT 1 FROM repository_object_sources WHERE repository_uuidv4=NEW.repository_uuidv4 AND git_object_id=NEW.git_object_id AND git_acquisition_id=NEW.git_acquisition_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER repository_object_sources_retain BEFORE DELETE ON repository_object_sources BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER ref_observations_no_replace BEFORE INSERT ON ref_observations WHEN EXISTS(SELECT 1 FROM ref_observations WHERE snapshot_id=NEW.snapshot_id AND raw_ref_name=NEW.raw_ref_name) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER ref_observations_retain BEFORE DELETE ON ref_observations BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER root_origins_no_replace BEFORE INSERT ON root_origins WHEN EXISTS(SELECT 1 FROM root_origins WHERE root_origin_id=NEW.root_origin_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER root_origins_retain BEFORE DELETE ON root_origins BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER commits_no_replace BEFORE INSERT ON commits WHEN EXISTS(SELECT 1 FROM commits WHERE git_object_id=NEW.git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER commits_retain BEFORE DELETE ON commits BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER commit_parents_no_replace BEFORE INSERT ON commit_parents WHEN EXISTS(SELECT 1 FROM commit_parents WHERE commit_git_object_id=NEW.commit_git_object_id AND parent_ordinal=NEW.parent_ordinal) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER commit_parents_retain BEFORE DELETE ON commit_parents BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER tree_entries_no_replace BEFORE INSERT ON tree_entries WHEN EXISTS(SELECT 1 FROM tree_entries WHERE tree_git_object_id=NEW.tree_git_object_id AND raw_name=NEW.raw_name) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER tree_entries_retain BEFORE DELETE ON tree_entries BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER tag_objects_no_replace BEFORE INSERT ON tag_objects WHEN EXISTS(SELECT 1 FROM tag_objects WHERE git_object_id=NEW.git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER tag_objects_retain BEFORE DELETE ON tag_objects BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER root_manifests_no_replace BEFORE INSERT ON root_manifests WHEN EXISTS(SELECT 1 FROM root_manifests WHERE tree_git_object_id=NEW.tree_git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER root_manifests_retain BEFORE DELETE ON root_manifests BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER root_manifest_entries_no_replace BEFORE INSERT ON root_manifest_entries WHEN EXISTS(SELECT 1 FROM root_manifest_entries WHERE tree_git_object_id=NEW.tree_git_object_id AND raw_path=NEW.raw_path) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER root_manifest_entries_retain BEFORE DELETE ON root_manifest_entries BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER git_acquisitions_no_replace BEFORE INSERT ON git_acquisitions WHEN EXISTS(SELECT 1 FROM git_acquisitions WHERE git_acquisition_id=NEW.git_acquisition_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER git_acquisitions_retain BEFORE DELETE ON git_acquisitions BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER snapshots_no_replace BEFORE INSERT ON snapshots WHEN EXISTS(SELECT 1 FROM snapshots WHERE snapshot_id=NEW.snapshot_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER snapshots_retain BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER acquisition_roots_no_replace BEFORE INSERT ON acquisition_roots WHEN EXISTS(SELECT 1 FROM acquisition_roots WHERE acquisition_root_id=NEW.acquisition_root_id) BEGIN SELECT RAISE(ABORT,'immutable Git domain identity conflict'); END;
CREATE TRIGGER acquisition_roots_retain BEFORE DELETE ON acquisition_roots BEGIN SELECT RAISE(ABORT,'retain Git domain fact'); END;
CREATE TRIGGER commits_target_insert BEFORE INSERT ON commits WHEN NEW.tree_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.tree_git_object_id AND g.object_format=NEW.tree_format AND g.oid=NEW.tree_oid AND g.type='tree') BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER commits_target_update BEFORE UPDATE ON commits WHEN NEW.tree_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.tree_git_object_id AND g.object_format=NEW.tree_format AND g.oid=NEW.tree_oid AND g.type='tree') BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER commits_immutable BEFORE UPDATE ON commits WHEN NEW.git_object_id IS NOT OLD.git_object_id OR NEW.tree_format IS NOT OLD.tree_format OR NEW.tree_oid IS NOT OLD.tree_oid OR NEW.tree_header_offset IS NOT OLD.tree_header_offset OR NEW.parent_count IS NOT OLD.parent_count OR NEW.raw_headers IS NOT OLD.raw_headers OR NEW.raw_message IS NOT OLD.raw_message OR (OLD.tree_git_object_id IS NOT NULL AND NEW.tree_git_object_id IS NOT OLD.tree_git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git intrinsic fact'); END;
CREATE TRIGGER commit_parents_target_insert BEFORE INSERT ON commit_parents WHEN NEW.parent_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.parent_git_object_id AND g.object_format=NEW.parent_format AND g.oid=NEW.parent_oid AND g.type='commit') BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER commit_parents_target_update BEFORE UPDATE ON commit_parents WHEN NEW.parent_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.parent_git_object_id AND g.object_format=NEW.parent_format AND g.oid=NEW.parent_oid AND g.type='commit') BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER commit_parents_immutable BEFORE UPDATE ON commit_parents WHEN NEW.commit_git_object_id IS NOT OLD.commit_git_object_id OR NEW.parent_ordinal IS NOT OLD.parent_ordinal OR NEW.parent_header_offset IS NOT OLD.parent_header_offset OR NEW.parent_format IS NOT OLD.parent_format OR NEW.parent_oid IS NOT OLD.parent_oid OR (OLD.parent_git_object_id IS NOT NULL AND NEW.parent_git_object_id IS NOT OLD.parent_git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git intrinsic fact'); END;
CREATE TRIGGER tree_entries_target_insert BEFORE INSERT ON tree_entries WHEN NEW.child_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.child_git_object_id AND g.object_format=NEW.child_format AND g.oid=NEW.child_oid AND g.type=CASE NEW.mode WHEN 16384 THEN 'tree' ELSE 'blob' END) BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER tree_entries_target_update BEFORE UPDATE ON tree_entries WHEN NEW.child_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.child_git_object_id AND g.object_format=NEW.child_format AND g.oid=NEW.child_oid AND g.type=CASE NEW.mode WHEN 16384 THEN 'tree' ELSE 'blob' END) BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER tree_entries_immutable BEFORE UPDATE ON tree_entries WHEN NEW.tree_git_object_id IS NOT OLD.tree_git_object_id OR NEW.raw_name IS NOT OLD.raw_name OR NEW.entry_offset IS NOT OLD.entry_offset OR NEW.entry_length IS NOT OLD.entry_length OR NEW.mode IS NOT OLD.mode OR NEW.child_format IS NOT OLD.child_format OR NEW.child_oid IS NOT OLD.child_oid OR (OLD.child_git_object_id IS NOT NULL AND NEW.child_git_object_id IS NOT OLD.child_git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git intrinsic fact'); END;
CREATE TRIGGER tag_objects_target_insert BEFORE INSERT ON tag_objects WHEN NEW.target_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.target_git_object_id AND g.object_format=NEW.target_format AND g.oid=NEW.target_oid AND g.type=NEW.target_type) BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER tag_objects_target_update BEFORE UPDATE ON tag_objects WHEN NEW.target_git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.target_git_object_id AND g.object_format=NEW.target_format AND g.oid=NEW.target_oid AND g.type=NEW.target_type) BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER tag_objects_immutable BEFORE UPDATE ON tag_objects WHEN NEW.git_object_id IS NOT OLD.git_object_id OR NEW.target_format IS NOT OLD.target_format OR NEW.target_oid IS NOT OLD.target_oid OR NEW.target_type IS NOT OLD.target_type OR NEW.raw_payload IS NOT OLD.raw_payload OR (OLD.target_git_object_id IS NOT NULL AND NEW.target_git_object_id IS NOT OLD.target_git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git intrinsic fact'); END;
CREATE TRIGGER root_manifest_entries_target_insert BEFORE INSERT ON root_manifest_entries WHEN NEW.git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.git_object_id AND g.object_format=NEW.object_format AND g.oid=NEW.oid AND g.type='blob') BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER root_manifest_entries_target_update BEFORE UPDATE ON root_manifest_entries WHEN NEW.git_object_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM git_objects g WHERE g.git_object_id=NEW.git_object_id AND g.object_format=NEW.object_format AND g.oid=NEW.oid AND g.type='blob') BEGIN SELECT RAISE(ABORT,'Git target identity mismatch'); END;
CREATE TRIGGER root_manifest_entries_immutable BEFORE UPDATE ON root_manifest_entries WHEN NEW.tree_git_object_id IS NOT OLD.tree_git_object_id OR NEW.raw_path IS NOT OLD.raw_path OR NEW.mode IS NOT OLD.mode OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR (OLD.git_object_id IS NOT NULL AND NEW.git_object_id IS NOT OLD.git_object_id) BEGIN SELECT RAISE(ABORT,'immutable Git intrinsic fact'); END;
CREATE TRIGGER root_manifests_immutable BEFORE UPDATE ON root_manifests WHEN NEW.tree_git_object_id IS NOT OLD.tree_git_object_id OR NEW.entry_count IS NOT OLD.entry_count OR NEW.complete<OLD.complete BEGIN SELECT RAISE(ABORT,'immutable flattened tree manifest'); END;


CREATE INDEX repository_object_sources_acquisition ON repository_object_sources(git_acquisition_id,git_object_id);
CREATE INDEX snapshots_predecessor ON snapshots(predecessor_snapshot_id,complete);
CREATE INDEX snapshots_repository ON snapshots(repository_uuidv4,complete);
CREATE INDEX blob_content_map_content ON blob_content_map(content_id);

CREATE TRIGGER git_objects_immutable BEFORE UPDATE ON git_objects WHEN NEW.git_object_id IS NOT OLD.git_object_id OR NEW.object_format IS NOT OLD.object_format OR NEW.oid IS NOT OLD.oid OR NEW.type IS NOT OLD.type OR NEW.size IS NOT OLD.size OR NEW.verified<OLD.verified BEGIN SELECT RAISE(ABORT,'immutable canonical Git identity'); END;
CREATE TRIGGER git_objects_no_replace BEFORE INSERT ON git_objects WHEN EXISTS(SELECT 1 FROM git_objects WHERE object_format=NEW.object_format AND oid=NEW.oid) BEGIN SELECT RAISE(ABORT,'canonical Git identity conflict'); END;
CREATE TRIGGER git_objects_retain BEFORE DELETE ON git_objects BEGIN SELECT RAISE(ABORT,'retain canonical Git object'); END;
CREATE TRIGGER git_name_facts_immutable BEFORE UPDATE ON git_name_facts BEGIN SELECT RAISE(ABORT,'immutable Git name decoding'); END;
CREATE TRIGGER git_name_facts_retain BEFORE DELETE ON git_name_facts BEGIN SELECT RAISE(ABORT,'retain Git name decoding'); END;
CREATE TRIGGER git_name_facts_no_replace BEFORE INSERT ON git_name_facts WHEN EXISTS(SELECT 1 FROM git_name_facts WHERE tree_git_object_id=NEW.tree_git_object_id AND raw_name=NEW.raw_name AND decoder_key=NEW.decoder_key) BEGIN SELECT RAISE(ABORT,'Git name decoding identity conflict'); END;

CREATE TRIGGER acquisition_roots_complete BEFORE UPDATE ON acquisition_roots WHEN NEW.complete=1 AND OLD.complete=0 AND NOT EXISTS(SELECT 1 FROM available_git_acquisitions a WHERE a.git_acquisition_id=NEW.git_acquisition_id) BEGIN SELECT RAISE(ABORT,'acquired root closure incomplete'); END;

CREATE TRIGGER root_origins_ref_insert BEFORE INSERT ON root_origins WHEN NEW.origin_kind='ref' AND NOT EXISTS(
 SELECT 1 FROM acquisition_roots r JOIN snapshots s ON s.git_acquisition_id=r.git_acquisition_id
 JOIN ref_observations f ON f.snapshot_id=s.snapshot_id AND f.repository_uuidv4=r.repository_uuidv4
 WHERE r.acquisition_root_id=NEW.acquisition_root_id AND r.repository_uuidv4=NEW.repository_uuidv4
 AND s.snapshot_id=NEW.snapshot_id AND f.raw_ref_name=NEW.raw_ref_name
 AND f.object_format=r.object_format AND coalesce(f.peeled_oid,f.target_oid)=r.oid
) BEGIN SELECT RAISE(ABORT,'Ref origin must match exact captured snapshot and target'); END;

CREATE TRIGGER root_origins_ref_update BEFORE UPDATE ON root_origins WHEN NEW.origin_kind='ref' AND NOT EXISTS(
 SELECT 1 FROM acquisition_roots r JOIN snapshots s ON s.git_acquisition_id=r.git_acquisition_id
 JOIN ref_observations f ON f.snapshot_id=s.snapshot_id AND f.repository_uuidv4=r.repository_uuidv4
 WHERE r.acquisition_root_id=NEW.acquisition_root_id AND r.repository_uuidv4=NEW.repository_uuidv4
 AND s.snapshot_id=NEW.snapshot_id AND f.raw_ref_name=NEW.raw_ref_name
 AND f.object_format=r.object_format AND coalesce(f.peeled_oid,f.target_oid)=r.oid
) BEGIN SELECT RAISE(ABORT,'Ref origin must match exact captured snapshot and target'); END;
