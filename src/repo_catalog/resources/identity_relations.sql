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
CREATE TABLE repository_name_observations(
 repository_name_observation_uuidv4 TEXT PRIMARY KEY,
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4),
 name TEXT NOT NULL CHECK(length(name)>0),
 observed_at_us INTEGER,
 parsed_result_uuidv4 TEXT REFERENCES parsed_results(parsed_result_uuidv4),
 provenance_json TEXT NOT NULL CHECK(json_valid(provenance_json) AND json_type(provenance_json)='object'),
 owner_repository_uuidv4 TEXT REFERENCES repositories(repository_uuidv4),
 owner_source_registration_uuidv4 TEXT REFERENCES sources(source_registration_uuidv4),
 FOREIGN KEY(parsed_result_uuidv4,owner_repository_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,repository_uuidv4),
 FOREIGN KEY(parsed_result_uuidv4,owner_source_registration_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,source_registration_uuidv4),
 CHECK((parsed_result_uuidv4 IS NULL AND owner_repository_uuidv4 IS NULL AND owner_source_registration_uuidv4 IS NULL)
 OR (parsed_result_uuidv4 IS NOT NULL AND ((owner_repository_uuidv4 IS NOT NULL AND owner_repository_uuidv4=repository_uuidv4 AND owner_source_registration_uuidv4 IS NULL) OR (owner_repository_uuidv4 IS NULL AND owner_source_registration_uuidv4 IS NOT NULL))))
) STRICT;
-- Normal selectors use only eligible parsed names; explicit local naming
-- evidence has no parser dependency and remains independently available.
CREATE VIEW repository_observed_names AS
SELECT DISTINCT n.repository_uuidv4,n.name FROM repository_name_observations n
WHERE n.parsed_result_uuidv4 IS NULL OR EXISTS(
 SELECT 1 FROM usable_parsed_results r
 WHERE r.parsed_result_uuidv4=n.parsed_result_uuidv4 AND (
  (r.owner_kind='source' AND EXISTS(SELECT 1 FROM effective_source_parser_profiles e
   WHERE e.source_registration_uuidv4=r.source_registration_uuidv4 AND e.fact_kind='inventory'
    AND e.parser_profile_uuidv4=r.parser_profile_uuidv4))
  OR (r.owner_kind='repository' AND EXISTS(SELECT 1 FROM effective_repository_parser_profiles e
   WHERE e.repository_uuidv4=r.repository_uuidv4 AND e.fact_kind='repository-name'
    AND e.parser_profile_uuidv4=r.parser_profile_uuidv4))
 ));
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
CREATE TRIGGER repository_name_observations_no_update BEFORE UPDATE ON repository_name_observations BEGIN SELECT RAISE(ABORT,'Immutable identity evidence'); END;
CREATE TRIGGER repository_name_observations_no_delete BEFORE DELETE ON repository_name_observations BEGIN SELECT RAISE(ABORT,'Retain identity evidence'); END;
CREATE TRIGGER repository_name_observations_uuid BEFORE INSERT ON repository_name_observations WHEN NOT (length(CAST(NEW.repository_name_observation_uuidv4 AS BLOB))=36 AND substr(NEW.repository_name_observation_uuidv4,9,1)='-' AND substr(NEW.repository_name_observation_uuidv4,14,1)='-' AND substr(NEW.repository_name_observation_uuidv4,19,1)='-' AND substr(NEW.repository_name_observation_uuidv4,24,1)='-' AND length(replace(NEW.repository_name_observation_uuidv4,'-',''))=32 AND replace(NEW.repository_name_observation_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.repository_name_observation_uuidv4,15,1)='4' AND substr(NEW.repository_name_observation_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'Invalid UUIDv4'); END;

CREATE TRIGGER repository_name_source_owner BEFORE INSERT ON repository_name_observations
WHEN NEW.owner_source_registration_uuidv4 IS NOT NULL AND NOT EXISTS(SELECT 1 FROM source_repositories m JOIN sources s USING(source_id) WHERE s.source_registration_uuidv4=NEW.owner_source_registration_uuidv4 AND m.repository_uuidv4=NEW.repository_uuidv4)
BEGIN SELECT RAISE(ABORT,'Name observation source does not own repository membership'); END;
CREATE TRIGGER repository_name_result_sealed BEFORE INSERT ON repository_name_observations
WHEN NEW.parsed_result_uuidv4 IS NOT NULL AND EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4)
BEGIN SELECT RAISE(ABORT,'Published parsed result is sealed'); END;

-- Inventory interpretations remain Source-owned; multiple sources/profiles never
-- overwrite a repository registration's local display metadata.
CREATE TABLE repository_inventory_observations(
 repository_inventory_observation_uuidv4 TEXT PRIMARY KEY,
 repository_uuidv4 TEXT NOT NULL REFERENCES repositories(repository_uuidv4),
 parsed_result_uuidv4 TEXT NOT NULL,
 source_registration_uuidv4 TEXT NOT NULL REFERENCES sources(source_registration_uuidv4),
 name TEXT NOT NULL,
 metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json) AND json_type(metadata_json)='object'),
 FOREIGN KEY(parsed_result_uuidv4,source_registration_uuidv4) REFERENCES parsed_results(parsed_result_uuidv4,source_registration_uuidv4)
) STRICT;
CREATE TRIGGER repository_inventory_owner BEFORE INSERT ON repository_inventory_observations WHEN NOT EXISTS(SELECT 1 FROM source_repositories m JOIN sources s USING(source_id) WHERE s.source_registration_uuidv4=NEW.source_registration_uuidv4 AND m.repository_uuidv4=NEW.repository_uuidv4) BEGIN SELECT RAISE(ABORT,'Inventory source membership mismatch'); END;
CREATE TRIGGER repository_inventory_sealed BEFORE INSERT ON repository_inventory_observations WHEN EXISTS(SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=NEW.parsed_result_uuidv4) BEGIN SELECT RAISE(ABORT,'Published result is sealed'); END;
CREATE TRIGGER repository_inventory_no_update BEFORE UPDATE ON repository_inventory_observations BEGIN SELECT RAISE(ABORT,'Immutable inventory observation'); END;
CREATE TRIGGER repository_inventory_no_delete BEFORE DELETE ON repository_inventory_observations BEGIN SELECT RAISE(ABORT,'Retain inventory observation'); END;
CREATE TRIGGER repository_inventory_no_replace BEFORE INSERT ON repository_inventory_observations WHEN EXISTS(SELECT 1 FROM repository_inventory_observations WHERE repository_inventory_observation_uuidv4=NEW.repository_inventory_observation_uuidv4) BEGIN SELECT RAISE(ABORT,'Immutable inventory observation'); END;
CREATE VIEW current_repository_inventory_observations AS SELECT r.* FROM repository_inventory_observations r JOIN current_inventory_observations i ON i.parsed_result_uuidv4=r.parsed_result_uuidv4 AND i.source_registration_uuidv4=r.source_registration_uuidv4;
CREATE TRIGGER repository_inventory_uuid BEFORE INSERT ON repository_inventory_observations WHEN NOT (length(CAST(NEW.repository_inventory_observation_uuidv4 AS BLOB))=36 AND substr(NEW.repository_inventory_observation_uuidv4,9,1)='-' AND substr(NEW.repository_inventory_observation_uuidv4,14,1)='-' AND substr(NEW.repository_inventory_observation_uuidv4,19,1)='-' AND substr(NEW.repository_inventory_observation_uuidv4,24,1)='-' AND length(replace(NEW.repository_inventory_observation_uuidv4,'-',''))=32 AND replace(NEW.repository_inventory_observation_uuidv4,'-','') NOT GLOB '*[^0-9a-f]*' AND substr(NEW.repository_inventory_observation_uuidv4,15,1)='4' AND substr(NEW.repository_inventory_observation_uuidv4,20,1) IN ('8','9','a','b')) BEGIN SELECT RAISE(ABORT,'Invalid UUIDv4'); END;
-- A current Source/result pair has one inventory assertion and one interpretation
-- of each member repository; independent interpretations use independent results.
CREATE UNIQUE INDEX inventory_observations_result_identity ON inventory_observations(parsed_result_uuidv4);
CREATE UNIQUE INDEX repository_inventory_result_member ON repository_inventory_observations(parsed_result_uuidv4,repository_uuidv4);
-- Interpreted names participate in exact output seals; local name evidence has
-- no result and should not enlarge their indexed publication membership.
CREATE INDEX repository_names_parsed_result_idx ON repository_name_observations(parsed_result_uuidv4) WHERE parsed_result_uuidv4 IS NOT NULL;
