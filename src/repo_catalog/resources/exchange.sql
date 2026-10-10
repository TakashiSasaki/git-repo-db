-- Discardable intake/deduplication indexes, never resource owners.
CREATE TABLE exchange_local_identities(
 table_name TEXT NOT NULL,
 local_key_json TEXT NOT NULL CHECK(json_valid(local_key_json)),
 record_key TEXT NOT NULL UNIQUE,
 PRIMARY KEY(table_name,local_key_json)
) STRICT;
CREATE TABLE exchange_admissions(
 record_key TEXT PRIMARY KEY,
 table_name TEXT NOT NULL,
 local_key_json TEXT NOT NULL CHECK(json_valid(local_key_json)),
 content_sha256 BLOB NOT NULL CHECK(length(content_sha256)=32)
) STRICT;
CREATE TABLE exchange_staging(
 record_key TEXT NOT NULL,
 content_sha256 BLOB NOT NULL CHECK(length(content_sha256)=32),
 table_name TEXT NOT NULL,
 repository_uuidv4 TEXT NOT NULL,
 origin_catalog_uuidv4 TEXT NOT NULL,
 record_json TEXT NOT NULL CHECK(json_valid(record_json) AND json_type(record_json)='object'),
 reason TEXT NOT NULL,
 PRIMARY KEY(record_key,content_sha256)
) STRICT;
CREATE INDEX exchange_staging_owner ON exchange_staging(repository_uuidv4,table_name,reason);
CREATE INDEX exchange_staging_reason ON exchange_staging(reason,table_name);
CREATE INDEX exchange_staging_table ON exchange_staging(table_name,record_key);
CREATE INDEX exchange_staging_record_owner ON exchange_staging(record_key,repository_uuidv4);
-- Qualification barriers describe contested domain claims, not admission seals.
CREATE TABLE exchange_blocked_coverage_claims(
 coverage_claim_id INTEGER PRIMARY KEY REFERENCES coverage_claims(coverage_claim_id)
) STRICT;
-- Indexed direct proof subjects. The relation mirrors the immutable claim's
-- declared terminal markers; it does not qualify a claim or replace validation
-- of the actual collection pages, children, owners, and observation times.
CREATE TABLE coverage_claim_markers(
 coverage_claim_id INTEGER NOT NULL REFERENCES coverage_claims(coverage_claim_id),
 completion_marker_uuidv4 TEXT NOT NULL REFERENCES completion_markers(completion_marker_uuidv4),
 PRIMARY KEY(coverage_claim_id,completion_marker_uuidv4)
) STRICT;
CREATE INDEX coverage_claim_markers_marker ON coverage_claim_markers(completion_marker_uuidv4,coverage_claim_id);
CREATE TRIGGER coverage_claim_markers_insert AFTER INSERT ON coverage_claims
BEGIN
 INSERT INTO coverage_claim_markers(coverage_claim_id,completion_marker_uuidv4)
 SELECT NEW.coverage_claim_id,value FROM json_each(NEW.details_json,'$.completion_marker_uuidv4s');
END;
CREATE TRIGGER coverage_claim_markers_subject BEFORE INSERT ON coverage_claim_markers
WHEN NOT EXISTS(SELECT 1 FROM coverage_claims c JOIN json_each(c.details_json,'$.completion_marker_uuidv4s') m
 WHERE c.coverage_claim_id=NEW.coverage_claim_id AND m.value=NEW.completion_marker_uuidv4)
BEGIN SELECT RAISE(ABORT,'Marker is not a declared coverage proof subject'); END;
CREATE TRIGGER coverage_claim_markers_immutable BEFORE UPDATE ON coverage_claim_markers
BEGIN SELECT RAISE(ABORT,'Immutable coverage proof subject'); END;
CREATE TRIGGER coverage_claim_markers_no_delete BEFORE DELETE ON coverage_claim_markers
BEGIN SELECT RAISE(ABORT,'Immutable coverage proof subject'); END;
