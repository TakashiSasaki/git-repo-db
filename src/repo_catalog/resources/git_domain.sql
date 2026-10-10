-- Git identities and captures have domain subjects independent of parsing runs.
CREATE TABLE git_acquisitions(
 git_acquisition_id TEXT PRIMARY KEY NOT NULL,
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4),
 repository_endpoint_id TEXT, endpoint_url TEXT,
 object_format TEXT CHECK(object_format IN ('sha1','sha256')),
 refs_observed_at_us INTEGER, source_id TEXT REFERENCES sources(source_id),
 kind TEXT NOT NULL CHECK(kind IN ('git','pr','legacy')),
 started_at_us INTEGER, observed_at_us INTEGER,
 request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'),
 roots_manifest TEXT CHECK(roots_manifest IS NULL OR (json_valid(roots_manifest) AND json_type(roots_manifest)='array')),
 UNIQUE(git_acquisition_id,repository_uuidv4),
 FOREIGN KEY(repository_endpoint_id,repository_uuidv4) REFERENCES repository_endpoints(repository_endpoint_id,repository_uuidv4)
) STRICT;
CREATE TABLE snapshots(
 snapshot_id TEXT PRIMARY KEY NOT NULL, git_acquisition_id TEXT NOT NULL,
 repository_uuidv4 TEXT NOT NULL, predecessor_snapshot_id TEXT,
 complete INTEGER NOT NULL CHECK(complete IN (0,1)),
 generation INTEGER NOT NULL CHECK(generation>=0), created_at_us INTEGER,
 UNIQUE(snapshot_id,repository_uuidv4),
 FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4),
 FOREIGN KEY(predecessor_snapshot_id,repository_uuidv4) REFERENCES snapshots(snapshot_id,repository_uuidv4),
 CHECK(predecessor_snapshot_id IS NULL OR predecessor_snapshot_id<>snapshot_id)
) STRICT;
CREATE TABLE acquisition_roots(
 acquisition_root_id INTEGER PRIMARY KEY, git_acquisition_id TEXT NOT NULL,
 repository_uuidv4 TEXT NOT NULL, object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
 oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)),
 role TEXT NOT NULL CHECK(length(role)>0), expected_oid BLOB,
 complete INTEGER NOT NULL CHECK(complete IN (0,1)),
 UNIQUE(acquisition_root_id,repository_uuidv4), UNIQUE(git_acquisition_id,object_format,oid,role),
 FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4),
 CHECK(expected_oid IS NULL OR length(expected_oid)=length(oid))
) STRICT;
CREATE TABLE root_origins(
 root_origin_id INTEGER PRIMARY KEY, acquisition_root_id INTEGER NOT NULL,
 repository_uuidv4 TEXT NOT NULL, origin_kind TEXT NOT NULL CHECK(origin_kind IN ('ref','pr_role','legacy_unknown')),
 raw_ref_name BLOB, source_ordinal INTEGER NOT NULL CHECK(source_ordinal>=0),
 snapshot_id TEXT, change_request_id TEXT, code_assessment_id TEXT,
 UNIQUE(acquisition_root_id,origin_kind,source_ordinal),
 FOREIGN KEY(acquisition_root_id,repository_uuidv4) REFERENCES acquisition_roots(acquisition_root_id,repository_uuidv4),
 FOREIGN KEY(snapshot_id,repository_uuidv4) REFERENCES snapshots(snapshot_id,repository_uuidv4),
 FOREIGN KEY(change_request_id,repository_uuidv4) REFERENCES change_requests(change_request_id,repository_uuidv4),
 FOREIGN KEY(code_assessment_id,change_request_id) REFERENCES code_assessments(code_assessment_id,change_request_id),
 CHECK((origin_kind='ref' AND snapshot_id IS NOT NULL AND change_request_id IS NULL AND code_assessment_id IS NULL AND raw_ref_name IS NOT NULL AND length(raw_ref_name)>0)
 OR (origin_kind='pr_role' AND snapshot_id IS NULL AND change_request_id IS NOT NULL AND code_assessment_id IS NOT NULL)
 OR (origin_kind='legacy_unknown' AND snapshot_id IS NULL AND change_request_id IS NULL AND code_assessment_id IS NULL))
) STRICT;
CREATE TABLE git_objects(
 git_object_id INTEGER PRIMARY KEY, object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
 oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)),
 type TEXT NOT NULL CHECK(type IN ('commit','tree','blob','tag')), size INTEGER NOT NULL CHECK(size>=0),
 verified INTEGER NOT NULL CHECK(verified IN (0,1)), UNIQUE(object_format,oid)
) STRICT;
CREATE TABLE commits(
 git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id),
 tree_format TEXT NOT NULL CHECK(tree_format IN ('sha1','sha256')),
 tree_oid BLOB NOT NULL CHECK((tree_format='sha1' AND length(tree_oid)=20) OR (tree_format='sha256' AND length(tree_oid)=32)),
 tree_git_object_id INTEGER REFERENCES git_objects(git_object_id),
 tree_header_offset INTEGER NOT NULL CHECK(tree_header_offset>=0), parent_count INTEGER NOT NULL CHECK(parent_count>=0), raw_headers BLOB NOT NULL, raw_message BLOB NOT NULL
) STRICT;
CREATE TABLE commit_parents(
 commit_git_object_id INTEGER NOT NULL REFERENCES commits(git_object_id),
 parent_ordinal INTEGER NOT NULL CHECK(parent_ordinal>=0), parent_header_offset INTEGER NOT NULL CHECK(parent_header_offset>=0),
 parent_format TEXT NOT NULL CHECK(parent_format IN ('sha1','sha256')),
 parent_oid BLOB NOT NULL CHECK((parent_format='sha1' AND length(parent_oid)=20) OR (parent_format='sha256' AND length(parent_oid)=32)),
 parent_git_object_id INTEGER REFERENCES git_objects(git_object_id), PRIMARY KEY(commit_git_object_id,parent_ordinal), UNIQUE(commit_git_object_id,parent_header_offset)
) STRICT;
CREATE TABLE tree_objects(
 git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id), entry_count INTEGER NOT NULL CHECK(entry_count>=0)
) STRICT;
CREATE TABLE tree_entries(
 tree_git_object_id INTEGER NOT NULL REFERENCES tree_objects(git_object_id),
 raw_name BLOB NOT NULL CHECK(length(raw_name)>0 AND instr(raw_name,X'00')=0),
 entry_offset INTEGER NOT NULL CHECK(entry_offset>=0), entry_length INTEGER NOT NULL CHECK(entry_length>0),
 mode INTEGER NOT NULL CHECK(mode IN (16384,33188,33261,40960,57344)),
 child_format TEXT NOT NULL CHECK(child_format IN ('sha1','sha256')),
 child_oid BLOB NOT NULL CHECK((child_format='sha1' AND length(child_oid)=20) OR (child_format='sha256' AND length(child_oid)=32)),
 child_git_object_id INTEGER REFERENCES git_objects(git_object_id),
 PRIMARY KEY(tree_git_object_id,raw_name), UNIQUE(tree_git_object_id,entry_offset),
 CHECK(mode<>57344 OR child_git_object_id IS NULL)
) STRICT;
CREATE TABLE tag_objects(
 git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id),
 target_format TEXT NOT NULL CHECK(target_format IN ('sha1','sha256')),
 target_oid BLOB NOT NULL CHECK((target_format='sha1' AND length(target_oid)=20) OR (target_format='sha256' AND length(target_oid)=32)),
 target_type TEXT NOT NULL CHECK(target_type IN ('commit','tree','blob','tag')),
 target_git_object_id INTEGER REFERENCES git_objects(git_object_id), raw_payload BLOB NOT NULL
) STRICT;
CREATE TABLE contents(content_id INTEGER PRIMARY KEY, byte_length INTEGER NOT NULL CHECK(byte_length>=0), created_at_us INTEGER) STRICT;
CREATE TABLE content_digests(
 content_id INTEGER NOT NULL REFERENCES contents(content_id), representation TEXT NOT NULL CHECK(representation='raw-content-v1'),
 algorithm TEXT NOT NULL CHECK(algorithm IN ('md5','sha1','sha256')),
 digest BLOB NOT NULL CHECK((algorithm='md5' AND length(digest)=16) OR (algorithm='sha1' AND length(digest)=20) OR (algorithm='sha256' AND length(digest)=32)),
 verified_at_us INTEGER, pipeline_version TEXT NOT NULL, PRIMARY KEY(content_id,representation,algorithm)
) STRICT;
CREATE TABLE blob_content_map(git_object_id INTEGER PRIMARY KEY REFERENCES git_objects(git_object_id),content_id INTEGER NOT NULL REFERENCES contents(content_id)) STRICT;
CREATE TABLE repository_object_sources(
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4), git_object_id INTEGER NOT NULL REFERENCES git_objects(git_object_id), git_acquisition_id TEXT NOT NULL,
 PRIMARY KEY(repository_uuidv4,git_object_id,git_acquisition_id),
 FOREIGN KEY(git_acquisition_id,repository_uuidv4) REFERENCES git_acquisitions(git_acquisition_id,repository_uuidv4)
) STRICT;
CREATE TABLE ref_observations(
 repository_uuidv4 TEXT NOT NULL, snapshot_id TEXT NOT NULL, raw_ref_name BLOB NOT NULL CHECK(length(raw_ref_name)>0),
 kind TEXT NOT NULL CHECK(kind IN ('head','tag','other')), object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
 target_oid BLOB NOT NULL CHECK((object_format='sha1' AND length(target_oid)=20) OR (object_format='sha256' AND length(target_oid)=32)),
 peeled_oid BLOB, target_type TEXT CHECK(target_type IN ('commit','tree','blob','tag')),
 PRIMARY KEY(snapshot_id,raw_ref_name), FOREIGN KEY(snapshot_id,repository_uuidv4) REFERENCES snapshots(snapshot_id,repository_uuidv4),
 CHECK(peeled_oid IS NULL OR length(peeled_oid)=length(target_oid))
) STRICT;
CREATE TABLE root_manifests(
 tree_git_object_id INTEGER PRIMARY KEY REFERENCES tree_objects(git_object_id),
 complete INTEGER NOT NULL CHECK(complete IN (0,1)), entry_count INTEGER NOT NULL CHECK(entry_count>=0)
) STRICT;
CREATE TABLE root_manifest_entries(
 tree_git_object_id INTEGER NOT NULL REFERENCES root_manifests(tree_git_object_id), raw_path BLOB NOT NULL CHECK(length(raw_path)>0),
 mode INTEGER NOT NULL CHECK(mode IN (33188,33261,40960,57344)), git_object_id INTEGER REFERENCES git_objects(git_object_id),
 object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
 oid BLOB NOT NULL CHECK((object_format='sha1' AND length(oid)=20) OR (object_format='sha256' AND length(oid)=32)),
 PRIMARY KEY(tree_git_object_id,raw_path), CHECK(mode<>57344 OR git_object_id IS NULL)
) STRICT;
