-- Explicit equivalence never rewrites entity identities, facts or coverage.
CREATE TABLE identity_relations(
 relation_uuidv4 TEXT PRIMARY KEY,
 entity_kind TEXT NOT NULL CHECK(entity_kind IN ('repository','service')),
 left_repository_uuidv4 TEXT REFERENCES repositories(repository_uuidv4),
 right_repository_uuidv4 TEXT REFERENCES repositories(repository_uuidv4),
 left_service_instance_uuidv4 TEXT REFERENCES service_instances(service_instance_uuidv4),
 right_service_instance_uuidv4 TEXT REFERENCES service_instances(service_instance_uuidv4),
 evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json) AND json_type(evidence_json)='object'),
 asserted_at_us INTEGER,
 CHECK((entity_kind='repository' AND left_repository_uuidv4 IS NOT NULL AND right_repository_uuidv4 IS NOT NULL AND left_service_instance_uuidv4 IS NULL AND right_service_instance_uuidv4 IS NULL AND left_repository_uuidv4<>right_repository_uuidv4)
 OR (entity_kind='service' AND left_service_instance_uuidv4 IS NOT NULL AND right_service_instance_uuidv4 IS NOT NULL AND left_repository_uuidv4 IS NULL AND right_repository_uuidv4 IS NULL AND left_service_instance_uuidv4<>right_service_instance_uuidv4))
) STRICT;
CREATE TABLE identity_relation_cancellations(
 cancellation_uuidv4 TEXT PRIMARY KEY,
 relation_uuidv4 TEXT NOT NULL REFERENCES identity_relations(relation_uuidv4),
 evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json) AND json_type(evidence_json)='object'),
 asserted_at_us INTEGER
) STRICT;
CREATE TABLE identity_relation_staging(
 record_uuidv4 TEXT NOT NULL,
 content_sha256 BLOB NOT NULL CHECK(length(content_sha256)=32),
 kind TEXT NOT NULL CHECK(kind IN ('relation','cancellation')),
 record_json TEXT NOT NULL CHECK(json_valid(record_json) AND json_type(record_json)='object'),
 reason TEXT NOT NULL,
 PRIMARY KEY(record_uuidv4,content_sha256)
) STRICT;
-- Explicit local naming is identity evidence, not provider edit history.
CREATE TABLE repository_names(
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4),
 name TEXT NOT NULL CHECK(length(name)>0),
 observed_at_us INTEGER,
 provenance_json TEXT NOT NULL CHECK(json_valid(provenance_json) AND json_type(provenance_json)='object'),
 PRIMARY KEY(repository_uuidv4,name)
) STRICT;
CREATE VIEW repository_observed_names AS
 SELECT repository_uuidv4,name FROM repository_names
 UNION SELECT repository_uuidv4,name FROM eligible_source_repositories WHERE name IS NOT NULL;
CREATE VIEW active_identity_relations AS SELECT r.* FROM identity_relations r WHERE NOT EXISTS(SELECT 1 FROM identity_relation_cancellations c WHERE c.relation_uuidv4=r.relation_uuidv4) AND NOT EXISTS(SELECT 1 FROM identity_relation_staging s WHERE s.record_uuidv4=r.relation_uuidv4 OR (s.kind='cancellation' AND json_extract(s.record_json,'$.relation_uuidv4')=r.relation_uuidv4));
CREATE VIEW repository_equivalence_closure AS WITH RECURSIVE edges(a,b) AS (
 SELECT left_repository_uuidv4,right_repository_uuidv4 FROM active_identity_relations WHERE entity_kind='repository'
 UNION SELECT right_repository_uuidv4,left_repository_uuidv4 FROM active_identity_relations WHERE entity_kind='repository'
), closure(a,b) AS (SELECT a,b FROM edges UNION SELECT c.a,e.b FROM closure c JOIN edges e ON e.a=c.b)
SELECT a AS repository_uuidv4,b AS equivalent_repository_uuidv4 FROM closure WHERE a<>b;
CREATE VIEW service_equivalence_closure AS WITH RECURSIVE edges(a,b) AS (
 SELECT left_service_instance_uuidv4,right_service_instance_uuidv4 FROM active_identity_relations WHERE entity_kind='service'
 UNION SELECT right_service_instance_uuidv4,left_service_instance_uuidv4 FROM active_identity_relations WHERE entity_kind='service'
), closure(a,b) AS (SELECT a,b FROM edges UNION SELECT c.a,e.b FROM closure c JOIN edges e ON e.a=c.b)
SELECT a AS service_instance_uuidv4,b AS equivalent_service_instance_uuidv4 FROM closure WHERE a<>b;
CREATE TRIGGER identity_relations_no_update BEFORE UPDATE ON identity_relations BEGIN SELECT RAISE(ABORT,'Immutable identity evidence'); END;
CREATE TRIGGER identity_relations_no_delete BEFORE DELETE ON identity_relations BEGIN SELECT RAISE(ABORT,'Retain identity evidence'); END;
CREATE TRIGGER identity_relations_uuid BEFORE INSERT ON identity_relations WHEN NOT (length(CAST(NEW.relation_uuidv4 AS BLOB))=36 AND substr(NEW.relation_uuidv4,9,1)='-' AND substr(NEW.relation_uuidv4,14,1)='-' AND substr(NEW.relation_uuidv4,19,1)='-' AND substr(NEW.relation_uuidv4,24,1)='-' AND length(replace(NEW.relation_uuidv4,'-',''))=32 AND replace(NEW.relation_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.relation_uuidv4,15,1)='4' AND substr(NEW.relation_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'Invalid UUIDv4'); END;
CREATE TRIGGER identity_relation_cancellations_no_update BEFORE UPDATE ON identity_relation_cancellations BEGIN SELECT RAISE(ABORT,'Immutable identity evidence'); END;
CREATE TRIGGER identity_relation_cancellations_no_delete BEFORE DELETE ON identity_relation_cancellations BEGIN SELECT RAISE(ABORT,'Retain identity evidence'); END;
CREATE TRIGGER identity_relation_cancellations_uuid BEFORE INSERT ON identity_relation_cancellations WHEN NOT (length(CAST(NEW.cancellation_uuidv4 AS BLOB))=36 AND substr(NEW.cancellation_uuidv4,9,1)='-' AND substr(NEW.cancellation_uuidv4,14,1)='-' AND substr(NEW.cancellation_uuidv4,19,1)='-' AND substr(NEW.cancellation_uuidv4,24,1)='-' AND length(replace(NEW.cancellation_uuidv4,'-',''))=32 AND replace(NEW.cancellation_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.cancellation_uuidv4,15,1)='4' AND substr(NEW.cancellation_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'Invalid UUIDv4'); END;
