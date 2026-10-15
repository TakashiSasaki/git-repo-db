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
WHEN NOT EXISTS(SELECT 1 FROM retained_metadata r WHERE r.object_format=NEW.object_format AND r.full_oid=NEW.full_oid
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
WHEN NOT EXISTS(SELECT 1 FROM retained_metadata r WHERE r.object_format=NEW.object_format AND r.full_oid=NEW.full_oid
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
 owner_kind TEXT NOT NULL CHECK(owner_kind IN ('repository','capture','object','field')),
 owner_coordinates_json TEXT NOT NULL CHECK(p1_json(owner_coordinates_json)),
 repository_uuidv4 TEXT,
 capture_origin_uuidv4 TEXT, capture_uuidv4 TEXT,
 object_format TEXT, full_oid TEXT, field TEXT,
 coverage_kind TEXT NOT NULL CHECK(length(coverage_kind)>0),
 CHECK(
 (owner_kind='repository' AND repository_uuidv4 IS NOT NULL AND p1_uuid4(repository_uuidv4) AND capture_origin_uuidv4 IS NULL AND capture_uuidv4 IS NULL AND object_format IS NULL AND full_oid IS NULL AND field IS NULL AND owner_coordinates_json=p1_array(repository_uuidv4,coverage_kind)) OR
 (owner_kind='capture' AND repository_uuidv4 IS NULL AND capture_origin_uuidv4 IS NOT NULL AND capture_uuidv4 IS NOT NULL AND object_format IS NULL AND full_oid IS NULL AND field IS NULL AND owner_coordinates_json=p1_array(capture_origin_uuidv4,capture_uuidv4,coverage_kind)) OR
 (owner_kind='object' AND repository_uuidv4 IS NULL AND capture_origin_uuidv4 IS NULL AND capture_uuidv4 IS NULL AND object_format IS NOT NULL AND full_oid IS NOT NULL AND field IS NULL AND owner_coordinates_json=p1_array(object_format,full_oid,coverage_kind)) OR
 (owner_kind='field' AND repository_uuidv4 IS NULL AND capture_origin_uuidv4 IS NULL AND capture_uuidv4 IS NULL AND object_format IS NOT NULL AND full_oid IS NOT NULL AND field IS NOT NULL AND length(field)>0 AND owner_coordinates_json=p1_array(object_format,full_oid,field,coverage_kind))),
 PRIMARY KEY(owner_kind,owner_coordinates_json),
 FOREIGN KEY(capture_origin_uuidv4,capture_uuidv4) REFERENCES captures,
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
 observed_at_us INTEGER NOT NULL, coverage_state TEXT NOT NULL,
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
