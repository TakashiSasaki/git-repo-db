-- Isolated P1 target. Identity table and INSERT-only triggers are composed centrally.
CREATE TABLE repositories (
 repository_uuidv4 TEXT PRIMARY KEY CHECK(p1_uuid4(repository_uuidv4))
) STRICT, WITHOUT ROWID;
CREATE TABLE git_objects (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 CHECK(p1_oid(object_format,full_oid)),
 PRIMARY KEY(object_format,full_oid)
) STRICT, WITHOUT ROWID;
CREATE TABLE repository_claims (
 repository_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(repository_uuidv4)),
 field TEXT NOT NULL CHECK(field IN ('name','git_path','object_format','endpoint','observation_us','identity_assertion','identity_cancellation')),
 value TEXT NOT NULL CHECK(p1_json(value)),
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance)),
 CHECK(p1_repository_claim(repository_uuidv4,field,value,provenance)),
 PRIMARY KEY(repository_uuidv4,field,value,provenance),
 UNIQUE(repository_uuidv4,field,provenance),
 FOREIGN KEY(repository_uuidv4) REFERENCES repositories
) STRICT, WITHOUT ROWID;
CREATE TABLE git_observations (
 capture_origin_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(capture_origin_uuidv4)),
 capture_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(capture_uuidv4)),
 repository_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(repository_uuidv4)),
 kind TEXT NOT NULL CHECK(kind IN ('acquisition','ref','root','snapshot','membership','manifest')),
 scope TEXT NOT NULL CHECK(p1_json(scope)),
 value TEXT NOT NULL CHECK(p1_json(value)),
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance)),
 CHECK(p1_git_observation(capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,kind,scope,value,provenance)),
 PRIMARY KEY(capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,kind,scope,value,provenance),
 UNIQUE(capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,kind,scope,provenance),
 FOREIGN KEY(repository_uuidv4) REFERENCES repositories
) STRICT, WITHOUT ROWID;
CREATE TABLE scalar_claims (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 field TEXT NOT NULL, value TEXT NOT NULL CHECK(p1_claim(field,value)),
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance)),
 PRIMARY KEY(object_format,full_oid,field,value,provenance),
 UNIQUE(object_format,full_oid,field,provenance),
 FOREIGN KEY(object_format,full_oid) REFERENCES git_objects
) STRICT, WITHOUT ROWID;
CREATE TABLE relation_groups (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 relation TEXT NOT NULL, scope TEXT NOT NULL CHECK(length(scope)>0),
 status TEXT NOT NULL, membership TEXT NOT NULL,
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance)),
 CHECK(p1_group(object_format,relation,status,membership)),
 PRIMARY KEY(object_format,full_oid,relation,scope,status,membership,provenance),
 UNIQUE(object_format,full_oid,relation,scope,provenance),
 FOREIGN KEY(object_format,full_oid) REFERENCES git_objects
) STRICT, WITHOUT ROWID;
CREATE TRIGGER relation_targets BEFORE INSERT ON relation_groups
WHEN EXISTS(SELECT 1 FROM json_each(NEW.membership) j WHERE NOT EXISTS(
 SELECT 1 FROM git_objects o WHERE o.object_format=json_extract(j.value,'$[1]')
 AND o.full_oid=json_extract(j.value,'$[2]')))
BEGIN SELECT RAISE(ABORT,'missing nominal relation target'); END;
CREATE TABLE captures (
 capture_origin_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(capture_origin_uuidv4)),
 capture_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(capture_uuidv4)),
 repository_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(repository_uuidv4)),
 source TEXT NOT NULL CHECK(length(source)>0),
 ref TEXT NOT NULL CHECK(p1_ref(ref)),
 object_format TEXT NOT NULL, root TEXT NOT NULL,
 PRIMARY KEY(capture_origin_uuidv4,capture_uuidv4),
 UNIQUE(capture_origin_uuidv4,capture_uuidv4,object_format,root),
 FOREIGN KEY(repository_uuidv4) REFERENCES repositories,
 FOREIGN KEY(object_format,root) REFERENCES git_objects
) STRICT, WITHOUT ROWID;
CREATE TABLE notes_claims (
 capture_origin_uuidv4 TEXT NOT NULL, capture_uuidv4 TEXT NOT NULL,
 object_format TEXT NOT NULL, target TEXT NOT NULL, note TEXT NOT NULL,
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance)),
 PRIMARY KEY(capture_origin_uuidv4,capture_uuidv4,object_format,target,note,provenance),
 UNIQUE(capture_origin_uuidv4,capture_uuidv4,object_format,target,provenance),
 FOREIGN KEY(capture_origin_uuidv4,capture_uuidv4) REFERENCES captures,
 FOREIGN KEY(object_format,target) REFERENCES git_objects,
 FOREIGN KEY(object_format,note) REFERENCES git_objects
) STRICT, WITHOUT ROWID;
CREATE TABLE notes_groups (
 capture_origin_uuidv4 TEXT NOT NULL, capture_uuidv4 TEXT NOT NULL,
 object_format TEXT NOT NULL, scope TEXT NOT NULL CHECK(length(scope)>0),
 status TEXT NOT NULL, membership TEXT NOT NULL,
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance)),
 CHECK(p1_notes_group(object_format,status,membership)),
 PRIMARY KEY(capture_origin_uuidv4,capture_uuidv4,object_format,scope,status,membership,provenance),
 UNIQUE(capture_origin_uuidv4,capture_uuidv4,object_format,scope,provenance),
 FOREIGN KEY(capture_origin_uuidv4,capture_uuidv4) REFERENCES captures
) STRICT, WITHOUT ROWID;
CREATE TRIGGER notes_group_targets BEFORE INSERT ON notes_groups
WHEN EXISTS(SELECT 1 FROM json_each(NEW.membership) j WHERE NOT EXISTS(
 SELECT 1 FROM git_objects WHERE object_format=NEW.object_format AND full_oid=json_extract(j.value,'$[0]'))
 OR NOT EXISTS(SELECT 1 FROM git_objects WHERE object_format=NEW.object_format AND full_oid=json_extract(j.value,'$[1]')))
BEGIN SELECT RAISE(ABORT,'missing nominal notes group target'); END;
-- Qualified receiver evidence must carry checked native structure even through
-- the supported coordinator callback SQL boundary. This grants no source/ref
-- authenticity: the function proves only this exact Capture/root inventory.
CREATE TRIGGER notes_inventory_guard BEFORE INSERT ON notes_groups
WHEN json_extract(NEW.provenance,'$[5]')='receiver_intrinsic' AND NOT EXISTS(
 SELECT 1 FROM captures c WHERE c.capture_origin_uuidv4=NEW.capture_origin_uuidv4
 AND c.capture_uuidv4=NEW.capture_uuidv4 AND c.object_format=NEW.object_format
 AND p4_notes_inventory(p1_array(c.capture_origin_uuidv4,c.capture_uuidv4,
 c.repository_uuidv4,c.source,c.ref,c.object_format,c.root),
 NEW.scope,NEW.status,NEW.membership,NEW.provenance))
BEGIN SELECT RAISE(ABORT,'receiver Notes inventory requires checked structural evidence'); END;
CREATE TABLE retained_metadata (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 physical_copy_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(physical_copy_uuidv4)),
 native_type TEXT NOT NULL CHECK(native_type IN ('commit','tree','tag')),
 body BLOB NOT NULL, size INTEGER NOT NULL, digest_sha256 TEXT NOT NULL,
 CHECK(p1_native(object_format,full_oid,native_type,body,size,digest_sha256)),
 PRIMARY KEY(object_format,full_oid,physical_copy_uuidv4),
 FOREIGN KEY(object_format,full_oid) REFERENCES git_objects
) STRICT, WITHOUT ROWID;
CREATE TRIGGER metadata_same_representation BEFORE INSERT ON retained_metadata
WHEN EXISTS(SELECT 1 FROM retained_metadata WHERE object_format=NEW.object_format
 AND full_oid=NEW.full_oid AND (native_type<>NEW.native_type OR body<>NEW.body))
BEGIN SELECT RAISE(ABORT,'conflicting exact metadata representation'); END;
CREATE TABLE intrinsic_claims (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 field TEXT NOT NULL, value TEXT NOT NULL, provenance TEXT NOT NULL,
 physical_copy_uuidv4 TEXT NOT NULL,
 PRIMARY KEY(object_format,full_oid,field,value,provenance,physical_copy_uuidv4),
 FOREIGN KEY(object_format,full_oid,field,value,provenance) REFERENCES scalar_claims,
 FOREIGN KEY(object_format,full_oid,physical_copy_uuidv4) REFERENCES retained_metadata
) STRICT, WITHOUT ROWID;
CREATE TRIGGER intrinsic_claim_guard BEFORE INSERT ON intrinsic_claims
WHEN json_extract(NEW.provenance,'$[5]') IS NOT 'receiver_intrinsic'
 OR NOT EXISTS(SELECT 1 FROM retained_metadata r WHERE r.object_format=NEW.object_format AND r.full_oid=NEW.full_oid
 AND r.physical_copy_uuidv4=NEW.physical_copy_uuidv4 AND p1_intrinsic_claim(NEW.field,NEW.value,r.native_type,r.body))
BEGIN SELECT RAISE(ABORT,'field outside checked intrinsic scope'); END;
CREATE TABLE intrinsic_groups (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 relation TEXT NOT NULL, scope TEXT NOT NULL, status TEXT NOT NULL,
 membership TEXT NOT NULL, provenance TEXT NOT NULL, physical_copy_uuidv4 TEXT NOT NULL,
 PRIMARY KEY(object_format,full_oid,relation,scope,status,membership,provenance,physical_copy_uuidv4),
 FOREIGN KEY(object_format,full_oid,relation,scope,status,membership,provenance) REFERENCES relation_groups,
 FOREIGN KEY(object_format,full_oid,physical_copy_uuidv4) REFERENCES retained_metadata
) STRICT, WITHOUT ROWID;
CREATE TRIGGER intrinsic_group_guard BEFORE INSERT ON intrinsic_groups
WHEN json_extract(NEW.provenance,'$[5]') IS NOT 'receiver_intrinsic'
 OR NOT EXISTS(SELECT 1 FROM retained_metadata r WHERE r.object_format=NEW.object_format AND r.full_oid=NEW.full_oid
 AND r.physical_copy_uuidv4=NEW.physical_copy_uuidv4 AND p1_intrinsic_group(NEW.object_format,NEW.relation,NEW.status,NEW.membership,r.native_type,r.body))
BEGIN SELECT RAISE(ABORT,'relation outside checked intrinsic scope'); END;
CREATE TABLE note_roles (
 capture_origin_uuidv4 TEXT NOT NULL, capture_uuidv4 TEXT NOT NULL,
 object_format TEXT NOT NULL, root TEXT NOT NULL, target TEXT NOT NULL, note TEXT NOT NULL,
 path TEXT NOT NULL, proof_bundle TEXT NOT NULL,
 CHECK(p1_note_role(object_format,root,target,note,path,proof_bundle)),
 PRIMARY KEY(capture_origin_uuidv4,capture_uuidv4,object_format,root,target,note,path,proof_bundle),
 FOREIGN KEY(capture_origin_uuidv4,capture_uuidv4,object_format,root) REFERENCES captures(capture_origin_uuidv4,capture_uuidv4,object_format,root),
 FOREIGN KEY(object_format,target) REFERENCES git_objects,
 FOREIGN KEY(object_format,note) REFERENCES git_objects
) STRICT, WITHOUT ROWID;
CREATE TABLE retained_notes (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 physical_copy_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(physical_copy_uuidv4)),
 body BLOB NOT NULL, size INTEGER NOT NULL, digest_sha256 TEXT NOT NULL,
 capture_origin_uuidv4 TEXT NOT NULL, capture_uuidv4 TEXT NOT NULL,
 root TEXT NOT NULL, target TEXT NOT NULL, path TEXT NOT NULL, proof_bundle TEXT NOT NULL,
 CHECK(p1_native(object_format,full_oid,'blob',body,size,digest_sha256)),
 PRIMARY KEY(object_format,full_oid,physical_copy_uuidv4),
 FOREIGN KEY(capture_origin_uuidv4,capture_uuidv4,object_format,root,target,full_oid,path,proof_bundle)
 REFERENCES note_roles(capture_origin_uuidv4,capture_uuidv4,object_format,root,target,note,path,proof_bundle)
) STRICT, WITHOUT ROWID;
CREATE TRIGGER notes_same_representation BEFORE INSERT ON retained_notes
WHEN EXISTS(SELECT 1 FROM retained_notes WHERE object_format=NEW.object_format
 AND full_oid=NEW.full_oid AND body<>NEW.body)
BEGIN SELECT RAISE(ABORT,'conflicting exact note representation'); END;
CREATE TABLE coverage_scopes (
 owner_kind TEXT NOT NULL CHECK(owner_kind IN ('repository','capture','ref_observation','object','field')),
 owner_coordinates_json TEXT NOT NULL CHECK(p1_json(owner_coordinates_json)),
 repository_uuidv4 TEXT,
 capture_origin_uuidv4 TEXT, capture_uuidv4 TEXT,
 observation_origin_uuidv4 TEXT, ref_observation_uuidv7 TEXT,
 object_format TEXT, full_oid TEXT, field TEXT,
 coverage_kind TEXT NOT NULL CHECK(length(coverage_kind)>0),
 CHECK(
 (owner_kind='repository' AND observation_origin_uuidv4 IS NULL AND ref_observation_uuidv7 IS NULL AND repository_uuidv4 IS NOT NULL AND p1_uuid4(repository_uuidv4) AND capture_origin_uuidv4 IS NULL AND capture_uuidv4 IS NULL AND object_format IS NULL AND full_oid IS NULL AND field IS NULL AND owner_coordinates_json=p1_array(repository_uuidv4,coverage_kind)) OR
 (owner_kind='capture' AND observation_origin_uuidv4 IS NULL AND ref_observation_uuidv7 IS NULL AND repository_uuidv4 IS NULL AND capture_origin_uuidv4 IS NOT NULL AND capture_uuidv4 IS NOT NULL AND object_format IS NULL AND full_oid IS NULL AND field IS NULL AND owner_coordinates_json=p1_array(capture_origin_uuidv4,capture_uuidv4,coverage_kind)) OR
 (owner_kind='ref_observation' AND repository_uuidv4 IS NULL AND capture_origin_uuidv4 IS NULL AND capture_uuidv4 IS NULL AND observation_origin_uuidv4 IS NOT NULL AND ref_observation_uuidv7 IS NOT NULL AND object_format IS NULL AND full_oid IS NULL AND field IS NULL AND owner_coordinates_json=p1_array(observation_origin_uuidv4,ref_observation_uuidv7,coverage_kind)) OR
 (owner_kind='object' AND observation_origin_uuidv4 IS NULL AND ref_observation_uuidv7 IS NULL AND repository_uuidv4 IS NULL AND capture_origin_uuidv4 IS NULL AND capture_uuidv4 IS NULL AND object_format IS NOT NULL AND full_oid IS NOT NULL AND field IS NULL AND owner_coordinates_json=p1_array(object_format,full_oid,coverage_kind)) OR
 (owner_kind='field' AND observation_origin_uuidv4 IS NULL AND ref_observation_uuidv7 IS NULL AND repository_uuidv4 IS NULL AND capture_origin_uuidv4 IS NULL AND capture_uuidv4 IS NULL AND object_format IS NOT NULL AND full_oid IS NOT NULL AND field IS NOT NULL AND length(field)>0 AND owner_coordinates_json=p1_array(object_format,full_oid,field,coverage_kind))),
 PRIMARY KEY(owner_kind,owner_coordinates_json),
 FOREIGN KEY(capture_origin_uuidv4,capture_uuidv4) REFERENCES captures,
 FOREIGN KEY(observation_origin_uuidv4,ref_observation_uuidv7) REFERENCES ref_observations,
 FOREIGN KEY(repository_uuidv4) REFERENCES repositories,
 FOREIGN KEY(object_format,full_oid) REFERENCES git_objects
) STRICT, WITHOUT ROWID;
CREATE TRIGGER notes_claim_format BEFORE INSERT ON notes_claims
WHEN NOT EXISTS(SELECT 1 FROM captures WHERE capture_origin_uuidv4=NEW.capture_origin_uuidv4 AND capture_uuidv4=NEW.capture_uuidv4 AND object_format=NEW.object_format)
BEGIN SELECT RAISE(ABORT,'Capture object-format mismatch'); END;
CREATE TRIGGER notes_group_format BEFORE INSERT ON notes_groups
WHEN NOT EXISTS(SELECT 1 FROM captures WHERE capture_origin_uuidv4=NEW.capture_origin_uuidv4 AND capture_uuidv4=NEW.capture_uuidv4 AND object_format=NEW.object_format)
BEGIN SELECT RAISE(ABORT,'Capture object-format mismatch'); END;
CREATE TABLE core_coverage_proofs (
 owner_kind TEXT NOT NULL, owner_coordinates_json TEXT NOT NULL,
 observed_at_us INTEGER NOT NULL CHECK(typeof(observed_at_us)='integer' AND observed_at_us>0), coverage_state TEXT NOT NULL,
 members_json TEXT NOT NULL CHECK(p1_coverage_members(members_json)),
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance)),
 PRIMARY KEY(owner_kind,owner_coordinates_json,observed_at_us,coverage_state,members_json,provenance),
 FOREIGN KEY(owner_kind,owner_coordinates_json,observed_at_us,coverage_state)
 REFERENCES coverage_claims(owner_kind,owner_coordinates_json,observed_at_us,coverage_state)
) STRICT, WITHOUT ROWID;

CREATE TRIGGER core_coverage_members BEFORE INSERT ON core_coverage_proofs
WHEN p1_coverage_members(NEW.members_json) AND EXISTS(SELECT 1 FROM json_each(NEW.members_json) j WHERE NOT EXISTS(
 SELECT 1 FROM git_objects o WHERE o.object_format=json_extract(j.value,'$[0]') AND o.full_oid=json_extract(j.value,'$[1]')))
BEGIN SELECT RAISE(ABORT,'missing nominal Core Coverage member'); END;

-- ADR 0036 target data. Legacy Capture rows remain readable during the I1→I3
-- stack; they are never used as proof for the new observation/claim path.
CREATE TABLE ref_observations (
 observation_origin_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(observation_origin_uuidv4)),
 ref_observation_uuidv7 TEXT NOT NULL CHECK(p1_uuid7(ref_observation_uuidv7)),
 repository_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(repository_uuidv4)),
 ref_name_bytes BLOB NOT NULL CHECK(substr(ref_name_bytes,1,5)=X'726566732F' AND instr(ref_name_bytes,X'00')=0),
 source_attribution TEXT NOT NULL CHECK(length(source_attribution)>0),
 visibility_scope TEXT NOT NULL CHECK(length(visibility_scope)>0),
 observed_at_us INTEGER CHECK(observed_at_us IS NULL OR (typeof(observed_at_us)='integer' AND observed_at_us>0)),
 PRIMARY KEY(observation_origin_uuidv4,ref_observation_uuidv7),
 FOREIGN KEY(repository_uuidv4) REFERENCES repositories
) STRICT, WITHOUT ROWID;
CREATE TABLE ref_observation_claims (
 observation_origin_uuidv4 TEXT NOT NULL, ref_observation_uuidv7 TEXT NOT NULL,
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance) AND json_extract(provenance,'$[5]')='reported'),
 presence_state TEXT NOT NULL CHECK(presence_state IN ('present','absent')),
 ref_form TEXT CHECK(ref_form IS NULL OR ref_form IN ('direct','symbolic')),
 direct_format TEXT, direct_target_oid TEXT, symbolic_target_ref_name BLOB,
 resolved_format TEXT, resolved_target_oid TEXT, peeled_format TEXT, peeled_target_oid TEXT,
 root_format TEXT, root_oid TEXT, absence_evidence TEXT,
 CHECK((direct_format IS NULL AND direct_target_oid IS NULL) OR (direct_format IS NOT NULL AND direct_target_oid IS NOT NULL AND p1_oid(direct_format,direct_target_oid))),
 CHECK((resolved_format IS NULL AND resolved_target_oid IS NULL) OR (resolved_format IS NOT NULL AND resolved_target_oid IS NOT NULL AND p1_oid(resolved_format,resolved_target_oid))),
 CHECK((peeled_format IS NULL AND peeled_target_oid IS NULL) OR (peeled_format IS NOT NULL AND peeled_target_oid IS NOT NULL AND p1_oid(peeled_format,peeled_target_oid))),
 CHECK((root_format IS NULL AND root_oid IS NULL) OR (root_format IS NOT NULL AND root_oid IS NOT NULL AND p1_oid(root_format,root_oid))),
 CHECK(symbolic_target_ref_name IS NULL OR (substr(symbolic_target_ref_name,1,5)=X'726566732F' AND instr(symbolic_target_ref_name,X'00')=0)),
 CHECK(direct_target_oid IS NULL OR ref_form IS 'direct'),
 CHECK(symbolic_target_ref_name IS NULL OR ref_form IS 'symbolic'),
 CHECK(p1_ref_result_formats(direct_format,resolved_format,peeled_format,root_format)),
 CHECK((presence_state='present' AND absence_evidence IS NULL) OR
       (presence_state='absent' AND p1_ref_absence(absence_evidence) AND ref_form IS NULL AND direct_target_oid IS NULL AND symbolic_target_ref_name IS NULL AND resolved_target_oid IS NULL AND peeled_target_oid IS NULL AND root_oid IS NULL)),
 PRIMARY KEY(observation_origin_uuidv4,ref_observation_uuidv7,provenance),
 UNIQUE(observation_origin_uuidv4,ref_observation_uuidv7,provenance,root_format,root_oid),
 FOREIGN KEY(observation_origin_uuidv4,ref_observation_uuidv7) REFERENCES ref_observations,
 FOREIGN KEY(direct_format,direct_target_oid) REFERENCES git_objects,
 FOREIGN KEY(resolved_format,resolved_target_oid) REFERENCES git_objects,
 FOREIGN KEY(peeled_format,peeled_target_oid) REFERENCES git_objects,
 FOREIGN KEY(root_format,root_oid) REFERENCES git_objects
) STRICT, WITHOUT ROWID;
CREATE UNIQUE INDEX ref_claim_coordinate ON ref_observation_claims(
 observation_origin_uuidv4,ref_observation_uuidv7,
 json_extract(provenance,'$[0]'),json_extract(provenance,'$[1]'),json_extract(provenance,'$[2]'));
CREATE TRIGGER ref_absence_subject BEFORE INSERT ON ref_observation_claims
WHEN NEW.presence_state='absent' AND NOT EXISTS(
 SELECT 1 FROM ref_observations o WHERE o.observation_origin_uuidv4=NEW.observation_origin_uuidv4
 AND o.ref_observation_uuidv7=NEW.ref_observation_uuidv7
 AND json_extract(NEW.absence_evidence,'$[0]')=o.source_attribution
 AND json_extract(NEW.absence_evidence,'$[1]')=o.visibility_scope
 AND json_extract(NEW.absence_evidence,'$[2]')=lower(hex(o.ref_name_bytes)))
BEGIN SELECT RAISE(ABORT,'absence evidence must match observed source, visibility and ref'); END;
CREATE TABLE ref_enumeration_observations (
 observation_origin_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(observation_origin_uuidv4)),
 enumeration_uuidv7 TEXT NOT NULL CHECK(p1_uuid7(enumeration_uuidv7)),
 repository_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(repository_uuidv4)),
 source_attribution TEXT NOT NULL CHECK(length(source_attribution)>0),
 visibility_scope TEXT NOT NULL CHECK(length(visibility_scope)>0),
 enumeration_scope_json TEXT NOT NULL CHECK(p1_json(enumeration_scope_json)),
 enumeration_state TEXT NOT NULL CHECK(enumeration_state IN ('complete','partial','unknown')),
 completion_coordinate TEXT,
 observed_at_us INTEGER CHECK(observed_at_us IS NULL OR (typeof(observed_at_us)='integer' AND observed_at_us>0)),
 byte_limit INTEGER NOT NULL CHECK(byte_limit>0),
 ref_limit INTEGER NOT NULL CHECK(ref_limit>0),
 link_count INTEGER NOT NULL CHECK(link_count>=0),
 CHECK((enumeration_state='complete' AND completion_coordinate IS NOT NULL AND length(completion_coordinate)>0)
    OR (enumeration_state IN ('partial','unknown') AND completion_coordinate IS NULL)),
 PRIMARY KEY(observation_origin_uuidv4,enumeration_uuidv7),
 FOREIGN KEY(repository_uuidv4) REFERENCES repositories
) STRICT, WITHOUT ROWID;
CREATE TABLE ref_enumeration_links (
 enumeration_origin_uuidv4 TEXT NOT NULL, enumeration_uuidv7 TEXT NOT NULL,
 observation_origin_uuidv4 TEXT NOT NULL, ref_observation_uuidv7 TEXT NOT NULL,
 claim_provenance TEXT NOT NULL, derivation TEXT NOT NULL CHECK(derivation IN ('item','absence')),
 position INTEGER NOT NULL CHECK(position>=0),
 PRIMARY KEY(enumeration_origin_uuidv4,enumeration_uuidv7,observation_origin_uuidv4,ref_observation_uuidv7,claim_provenance),
 UNIQUE(enumeration_origin_uuidv4,enumeration_uuidv7,position),
 FOREIGN KEY(enumeration_origin_uuidv4,enumeration_uuidv7) REFERENCES ref_enumeration_observations,
 FOREIGN KEY(observation_origin_uuidv4,ref_observation_uuidv7,claim_provenance) REFERENCES ref_observation_claims
) STRICT, WITHOUT ROWID;
CREATE TABLE notes_mappings (
 object_format TEXT NOT NULL, root_oid TEXT NOT NULL,
 interpretation_kind TEXT NOT NULL CHECK(length(interpretation_kind)>0),
 interpretation_version TEXT NOT NULL CHECK(length(interpretation_version)>0),
 interpretation_scope TEXT NOT NULL CHECK(length(interpretation_scope)>0),
 annotated_object_oid TEXT NOT NULL, note_oid TEXT NOT NULL,
 mapping_path_json TEXT NOT NULL CHECK(p1_mapping_path(mapping_path_json)),
 PRIMARY KEY(object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,note_oid,mapping_path_json),
 FOREIGN KEY(object_format,root_oid) REFERENCES git_objects,
 FOREIGN KEY(object_format,annotated_object_oid) REFERENCES git_objects,
 FOREIGN KEY(object_format,note_oid) REFERENCES git_objects
) STRICT, WITHOUT ROWID;
CREATE TABLE notes_mapping_claims (
 observation_origin_uuidv4 TEXT NOT NULL, ref_observation_uuidv7 TEXT NOT NULL, ref_claim_provenance TEXT NOT NULL,
 object_format TEXT NOT NULL, root_oid TEXT NOT NULL, interpretation_kind TEXT NOT NULL,
 interpretation_version TEXT NOT NULL, interpretation_scope TEXT NOT NULL,
 annotated_object_oid TEXT NOT NULL, note_oid TEXT NOT NULL, mapping_path_json TEXT NOT NULL,
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance) AND json_extract(provenance,'$[5]')='reported'),
 PRIMARY KEY(observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,note_oid,mapping_path_json,provenance),
 UNIQUE(observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,provenance),
 FOREIGN KEY(observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,object_format,root_oid) REFERENCES ref_observation_claims(observation_origin_uuidv4,ref_observation_uuidv7,provenance,root_format,root_oid),
 FOREIGN KEY(object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,note_oid,mapping_path_json) REFERENCES notes_mappings
) STRICT, WITHOUT ROWID;
CREATE TABLE notes_mapping_groups (
 observation_origin_uuidv4 TEXT NOT NULL, ref_observation_uuidv7 TEXT NOT NULL, ref_claim_provenance TEXT NOT NULL,
 object_format TEXT NOT NULL, root_oid TEXT NOT NULL,
 interpretation_kind TEXT NOT NULL CHECK(length(interpretation_kind)>0), interpretation_version TEXT NOT NULL CHECK(length(interpretation_version)>0),
 interpretation_scope TEXT NOT NULL CHECK(length(interpretation_scope)>0), group_scope TEXT NOT NULL CHECK(length(group_scope)>0),
 status TEXT NOT NULL, membership TEXT NOT NULL CHECK(p1_notes_group(object_format,status,membership)),
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance) AND json_extract(provenance,'$[5]')='reported'),
 PRIMARY KEY(observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,group_scope,status,membership,provenance),
 UNIQUE(observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,group_scope,provenance),
 FOREIGN KEY(observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,object_format,root_oid) REFERENCES ref_observation_claims(observation_origin_uuidv4,ref_observation_uuidv7,provenance,root_format,root_oid)
) STRICT, WITHOUT ROWID;
CREATE TRIGGER notes_mapping_group_targets BEFORE INSERT ON notes_mapping_groups
WHEN EXISTS(SELECT 1 FROM json_each(NEW.membership) j WHERE NOT EXISTS(
 SELECT 1 FROM git_objects WHERE object_format=NEW.object_format AND full_oid=json_extract(j.value,'$[0]'))
 OR NOT EXISTS(SELECT 1 FROM git_objects WHERE object_format=NEW.object_format AND full_oid=json_extract(j.value,'$[1]')))
BEGIN SELECT RAISE(ABORT,'missing nominal notes group target'); END;
-- Each receiver evidence row is also role evidence: its whole semantic key
-- includes the actual claim, root, mapping, decoder, scope and checked proof.
CREATE TABLE notes_mapping_evidence (
 observation_origin_uuidv4 TEXT NOT NULL, ref_observation_uuidv7 TEXT NOT NULL, ref_claim_provenance TEXT NOT NULL,
 object_format TEXT NOT NULL, root_oid TEXT NOT NULL, interpretation_kind TEXT NOT NULL,
 interpretation_version TEXT NOT NULL, interpretation_scope TEXT NOT NULL,
 annotated_object_oid TEXT NOT NULL, note_oid TEXT NOT NULL, mapping_path_json TEXT NOT NULL,
 verification_scope TEXT NOT NULL CHECK(length(verification_scope)>0),
 provenance TEXT NOT NULL CHECK(p1_provenance(provenance) AND json_extract(provenance,'$[5]')='receiver_intrinsic'),
 proof_bundle TEXT NOT NULL,
 CHECK(interpretation_kind='git-notes' AND interpretation_version='1' AND verification_scope='single-path' AND json_extract(provenance,'$[3]')='native-notes' AND json_extract(provenance,'$[4]')='1'),
 CHECK(json_type(mapping_path_json)='text' AND p1_note_role(object_format,root_oid,annotated_object_oid,note_oid,json_extract(mapping_path_json,'$'),proof_bundle)),
 PRIMARY KEY(observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,note_oid,mapping_path_json,verification_scope,provenance,proof_bundle),
 FOREIGN KEY(observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,object_format,root_oid) REFERENCES ref_observation_claims(observation_origin_uuidv4,ref_observation_uuidv7,provenance,root_format,root_oid),
 FOREIGN KEY(object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,note_oid,mapping_path_json) REFERENCES notes_mappings
) STRICT, WITHOUT ROWID;
CREATE TABLE ref_retained_notes (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 physical_copy_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(physical_copy_uuidv4)),
 body BLOB NOT NULL, size INTEGER NOT NULL, digest_sha256 TEXT NOT NULL,
 observation_origin_uuidv4 TEXT NOT NULL, ref_observation_uuidv7 TEXT NOT NULL, ref_claim_provenance TEXT NOT NULL,
 role_format TEXT NOT NULL, root_oid TEXT NOT NULL, interpretation_kind TEXT NOT NULL,
 interpretation_version TEXT NOT NULL, interpretation_scope TEXT NOT NULL,
 annotated_object_oid TEXT NOT NULL, note_oid TEXT NOT NULL, mapping_path_json TEXT NOT NULL,
 verification_scope TEXT NOT NULL, role_provenance TEXT NOT NULL, proof_bundle TEXT NOT NULL,
 CHECK(object_format=role_format AND full_oid=note_oid),
 CHECK(p1_native(object_format,full_oid,'blob',body,size,digest_sha256)),
 PRIMARY KEY(object_format,full_oid,physical_copy_uuidv4),
 FOREIGN KEY(observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,role_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,note_oid,mapping_path_json,verification_scope,role_provenance,proof_bundle) REFERENCES notes_mapping_evidence
) STRICT, WITHOUT ROWID;
-- A scoped read can choose one physical copy without scanning or fetching the
-- bodies of copies attached to other observations or proofs.
CREATE INDEX ref_retained_notes_role_lookup ON ref_retained_notes(
 observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,
 role_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,
 annotated_object_oid,note_oid,mapping_path_json,physical_copy_uuidv4);
CREATE TRIGGER ref_notes_same_representation BEFORE INSERT ON ref_retained_notes
WHEN EXISTS(SELECT 1 FROM ref_retained_notes WHERE object_format=NEW.object_format AND full_oid=NEW.full_oid AND body<>NEW.body)
 OR EXISTS(SELECT 1 FROM retained_notes WHERE object_format=NEW.object_format AND full_oid=NEW.full_oid AND (body<>NEW.body OR physical_copy_uuidv4=NEW.physical_copy_uuidv4))
BEGIN SELECT RAISE(ABORT,'conflicting exact note representation'); END;
CREATE TRIGGER old_notes_same_representation BEFORE INSERT ON retained_notes
WHEN EXISTS(SELECT 1 FROM ref_retained_notes WHERE object_format=NEW.object_format AND full_oid=NEW.full_oid AND (body<>NEW.body OR physical_copy_uuidv4=NEW.physical_copy_uuidv4))
BEGIN SELECT RAISE(ABORT,'conflicting exact note representation'); END;

-- A decoder label cannot turn a reused original evidence coordinate into an
-- independently attributable report for the same actual semantic slot.
CREATE UNIQUE INDEX notes_mapping_claim_coordinate ON notes_mapping_claims(
 observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,
 object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,
 json_extract(provenance,'$[0]'),json_extract(provenance,'$[1]'),json_extract(provenance,'$[2]'));
CREATE UNIQUE INDEX notes_mapping_group_coordinate ON notes_mapping_groups(
 observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,
 object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,group_scope,
 json_extract(provenance,'$[0]'),json_extract(provenance,'$[1]'),json_extract(provenance,'$[2]'));
CREATE UNIQUE INDEX notes_mapping_evidence_coordinate ON notes_mapping_evidence(
 observation_origin_uuidv4,ref_observation_uuidv7,ref_claim_provenance,
 object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,
 json_extract(provenance,'$[0]'),json_extract(provenance,'$[1]'),json_extract(provenance,'$[2]'));
-- I1 has no enumeration/group-completeness verifier. Do not let generic OID
-- membership be mistaken for a verified complete ref-observation scope; I2
-- supplies an explicitly scoped evidence producer before this guard is removed.
CREATE TRIGGER ref_coverage_proof_requires_typed_evidence BEFORE INSERT ON core_coverage_proofs
WHEN NEW.owner_kind='ref_observation'
BEGIN SELECT RAISE(ABORT,'ref-observation Coverage proof requires I2 typed evidence'); END;
