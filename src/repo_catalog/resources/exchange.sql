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
-- Qualification barriers describe contested domain claims, not admission seals.
CREATE TABLE exchange_blocked_coverage_claims(
 coverage_claim_id INTEGER PRIMARY KEY REFERENCES coverage_claims(coverage_claim_id)
) STRICT;
