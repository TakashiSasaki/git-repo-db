-- Portable exchange bookkeeping is catalog-local and never re-exported.
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
 content_sha256 BLOB NOT NULL CHECK(length(content_sha256)=32),
 record_json TEXT NOT NULL CHECK(json_valid(record_json) AND json_type(record_json)='object')
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
CREATE TABLE exchange_source_provenance(
 source_registration_uuidv4 TEXT NOT NULL REFERENCES sources(source_registration_uuidv4),
 origin_catalog_uuidv4 TEXT NOT NULL,
 definition_sha256 BLOB NOT NULL CHECK(length(definition_sha256)=32),
 definition_json TEXT NOT NULL CHECK(json_valid(definition_json) AND json_type(definition_json)='object'),
 PRIMARY KEY(source_registration_uuidv4,origin_catalog_uuidv4,definition_sha256)
) STRICT;
CREATE TRIGGER exchange_admissions_immutable BEFORE UPDATE ON exchange_admissions BEGIN SELECT RAISE(ABORT,'Exchange admission is immutable'); END;
CREATE TRIGGER exchange_admissions_retain BEFORE DELETE ON exchange_admissions BEGIN SELECT RAISE(ABORT,'Exchange admission must be retained'); END;
CREATE TRIGGER exchange_local_identities_immutable BEFORE UPDATE ON exchange_local_identities BEGIN SELECT RAISE(ABORT,'Portable exchange identity is immutable'); END;
CREATE TRIGGER exchange_local_identities_retain BEFORE DELETE ON exchange_local_identities BEGIN SELECT RAISE(ABORT,'Portable exchange identity must be retained'); END;
CREATE TRIGGER exchange_source_provenance_immutable BEFORE UPDATE ON exchange_source_provenance BEGIN SELECT RAISE(ABORT,'Source provenance is immutable'); END;
CREATE TRIGGER exchange_source_provenance_retain BEFORE DELETE ON exchange_source_provenance BEGIN SELECT RAISE(ABORT,'Source provenance must be retained'); END;
-- Derived local resolution barriers. Recomputed atomically after each intake;
-- they prevent a retained first-arriving immutable variant becoming a winner.
CREATE TABLE exchange_blocked_results(
 parsed_result_uuidv4 TEXT PRIMARY KEY REFERENCES parsed_results(parsed_result_uuidv4)
) STRICT;
CREATE TABLE exchange_selection_blocks(
 scope_kind TEXT NOT NULL CHECK(scope_kind IN ('profile','fact')),
 scope_uuidv4 TEXT NOT NULL,
 record_key TEXT NOT NULL,
 PRIMARY KEY(scope_kind,scope_uuidv4,record_key)
) STRICT;
