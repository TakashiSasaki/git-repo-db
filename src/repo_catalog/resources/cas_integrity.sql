-- Catalog-local physical integrity state. Diagnostics survive explicit repair.
CREATE TABLE payload_quarantine(
    sha256 BLOB PRIMARY KEY REFERENCES stored_bytes(sha256) ON UPDATE RESTRICT ON DELETE RESTRICT,
    unresolved_payload_id INTEGER NOT NULL UNIQUE REFERENCES unresolved_payloads(unresolved_payload_id) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;
CREATE TRIGGER payload_quarantine_diagnostic BEFORE INSERT ON payload_quarantine
WHEN NOT EXISTS(SELECT 1 FROM unresolved_payloads d WHERE d.unresolved_payload_id=NEW.unresolved_payload_id AND d.stored_sha256=NEW.sha256 AND d.reason='physical_corruption')
BEGIN SELECT RAISE(ABORT,'Quarantine requires matching physical corruption diagnostic'); END;
CREATE TRIGGER payload_quarantine_immutable BEFORE UPDATE ON payload_quarantine
BEGIN SELECT RAISE(ABORT,'Quarantine identity is immutable'); END;
CREATE TRIGGER payload_quarantine_no_replace BEFORE INSERT ON payload_quarantine
WHEN EXISTS(SELECT 1 FROM payload_quarantine WHERE sha256=NEW.sha256 OR unresolved_payload_id=NEW.unresolved_payload_id)
BEGIN SELECT RAISE(ABORT,'Existing quarantine cannot be replaced'); END;

-- Rejected raw Git bytes remain separate from admitted immutable physical objects.
-- API transport originals have no pending-admission store.
CREATE TABLE payload_admission_staging(
    stage_uuidv4 TEXT PRIMARY KEY NOT NULL,
    representation TEXT NOT NULL CHECK(representation='git-object-raw-v1'),
    sha256 BLOB NOT NULL CHECK(length(sha256)=32),
    body BLOB NOT NULL,
    context_json TEXT NOT NULL CHECK(
        json_valid(context_json) AND json_type(context_json)='object'
        AND json_extract(context_json,'$.object_format') IN ('sha1','sha256')
        AND json_type(context_json,'$.oid')='text'
        AND json_extract(context_json,'$.object_type') IN ('blob','tree','commit','tag')
        AND json_type(context_json,'$.byte_length')='integer'
        AND json_extract(context_json,'$.byte_length')=length(body)
        AND (
            (json_extract(context_json,'$.object_format')='sha1'
             AND length(json_extract(context_json,'$.oid'))=40)
            OR
            (json_extract(context_json,'$.object_format')='sha256'
             AND length(json_extract(context_json,'$.oid'))=64)
        )
        AND json_extract(context_json,'$.oid') NOT GLOB '*[^0-9a-f]*'
    ),
    reason TEXT NOT NULL CHECK(reason IN ('PAYLOAD_CORRUPTION','PAYLOAD_HASH_COLLISION')),
    received_at_us INTEGER NOT NULL
) STRICT;
CREATE TRIGGER payload_admission_staging_immutable BEFORE UPDATE ON payload_admission_staging
BEGIN SELECT RAISE(ABORT,'Retain rejected immutable acquisition'); END;
CREATE TRIGGER payload_admission_staging_retain BEFORE DELETE ON payload_admission_staging
BEGIN SELECT RAISE(ABORT,'Retain rejected immutable acquisition'); END;
CREATE TRIGGER payload_admission_staging_no_replace BEFORE INSERT ON payload_admission_staging
WHEN EXISTS(SELECT 1 FROM payload_admission_staging WHERE stage_uuidv4=NEW.stage_uuidv4)
BEGIN SELECT RAISE(ABORT,'Staged acquisition identity conflict'); END;

CREATE TRIGGER payload_admission_staging_uuid4 BEFORE INSERT ON payload_admission_staging
WHEN NOT (length(NEW.stage_uuidv4)=36 AND length(CAST(NEW.stage_uuidv4 AS BLOB))=36
 AND substr(NEW.stage_uuidv4,9,1)='-' AND substr(NEW.stage_uuidv4,14,1)='-'
 AND substr(NEW.stage_uuidv4,19,1)='-' AND substr(NEW.stage_uuidv4,24,1)='-'
 AND length(replace(NEW.stage_uuidv4,'-',''))=32
 AND replace(NEW.stage_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*'
 AND substr(NEW.stage_uuidv4,15,1)='4' AND substr(NEW.stage_uuidv4,20,1) IN ('8','9','a','b'))
BEGIN SELECT RAISE(ABORT,'invalid RFC UUIDv4'); END;

-- Writable catalog connections register this predicate; unregistered writers fail closed.
CREATE TRIGGER payload_admission_staging_git_object BEFORE INSERT ON payload_admission_staging
WHEN repo_catalog_git_object_identity_valid(
    json_extract(NEW.context_json,'$.object_format'),
    json_extract(NEW.context_json,'$.oid'),
    json_extract(NEW.context_json,'$.object_type'),
    json_extract(NEW.context_json,'$.byte_length'),
    NEW.body,
    NEW.sha256
) <> 1
BEGIN SELECT RAISE(ABORT,'staged bytes do not match Git object identity'); END;
