-- A1 DESIGN PROBE ONLY. Not a packaged product schema or migration.
-- All connections must register a_uuid/a_json and enable FK/recursive triggers.
CREATE TABLE access_scopes(
 scope_uuidv4 TEXT PRIMARY KEY CHECK(a_uuid(scope_uuidv4)),
 display_name TEXT NOT NULL,
 execution_context_json TEXT NOT NULL CHECK(a_json(execution_context_json)),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1))
) STRICT, WITHOUT ROWID;
CREATE TABLE scope_locators(
 scope_uuidv4 TEXT NOT NULL REFERENCES access_scopes,
 registered_at_us INTEGER NOT NULL CHECK(registered_at_us>0),
 scope_locator_uri TEXT NOT NULL CHECK(length(scope_locator_uri)>0),
 PRIMARY KEY(scope_uuidv4,registered_at_us,scope_locator_uri)
) STRICT, WITHOUT ROWID;
CREATE TRIGGER registration_no_update BEFORE UPDATE ON scope_locators
BEGIN SELECT RAISE(ABORT,'immutable registration'); END;
CREATE TRIGGER registration_no_delete BEFORE DELETE ON scope_locators
BEGIN SELECT RAISE(ABORT,'immutable registration'); END;
-- Mutable execution controls, NOT another locator history/current authority.
CREATE TABLE scope_locator_controls(
 scope_uuidv4 TEXT NOT NULL,
 registered_at_us INTEGER NOT NULL,
 scope_locator_uri TEXT NOT NULL,
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 PRIMARY KEY(scope_uuidv4,registered_at_us,scope_locator_uri),
 FOREIGN KEY(scope_uuidv4,registered_at_us,scope_locator_uri) REFERENCES scope_locators
) STRICT, WITHOUT ROWID;
CREATE TABLE repository_locators(
 scope_uuidv4 TEXT NOT NULL REFERENCES access_scopes,
 locator_text TEXT NOT NULL CHECK(length(locator_text)>0),
 repository_uuidv4 TEXT NOT NULL CHECK(a_uuid(repository_uuidv4)),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 PRIMARY KEY(scope_uuidv4,locator_text),
 UNIQUE(scope_uuidv4,locator_text,repository_uuidv4)
) STRICT, WITHOUT ROWID;
CREATE TABLE connection_configurations(
 scope_uuidv4 TEXT NOT NULL REFERENCES access_scopes,
 configuration_name TEXT NOT NULL CHECK(length(configuration_name)>0),
 options_json TEXT NOT NULL CHECK(a_json(options_json)),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 PRIMARY KEY(scope_uuidv4,configuration_name)
) STRICT, WITHOUT ROWID;
CREATE TABLE locator_connections(
 scope_uuidv4 TEXT NOT NULL,
 locator_text TEXT NOT NULL,
 configuration_name TEXT NOT NULL,
 purpose TEXT NOT NULL CHECK(purpose='git-read'),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 PRIMARY KEY(scope_uuidv4,locator_text,configuration_name,purpose),
 FOREIGN KEY(scope_uuidv4,locator_text) REFERENCES repository_locators,
 FOREIGN KEY(scope_uuidv4,configuration_name) REFERENCES connection_configurations
) STRICT, WITHOUT ROWID;
CREATE TABLE repository_access_preferences(
 repository_uuidv4 TEXT NOT NULL,
 scope_uuidv4 TEXT NOT NULL,
 purpose TEXT NOT NULL,
 locator_text TEXT NOT NULL,
 configuration_name TEXT NOT NULL,
 PRIMARY KEY(repository_uuidv4,scope_uuidv4,purpose),
 FOREIGN KEY(scope_uuidv4,locator_text,configuration_name,purpose) REFERENCES locator_connections,
 FOREIGN KEY(scope_uuidv4,locator_text,repository_uuidv4) REFERENCES repository_locators(scope_uuidv4,locator_text,repository_uuidv4)
) STRICT, WITHOUT ROWID;
-- One current locally-issued grant per real assignment; no grant row UUID.
-- The snapshot strings are full reviewed values, NOT hashes or identity aliases.
CREATE TABLE local_access_grants(
 scope_uuidv4 TEXT NOT NULL,
 locator_text TEXT NOT NULL,
 configuration_name TEXT NOT NULL,
 purpose TEXT NOT NULL,
 repository_uuidv4 TEXT NOT NULL,
 registered_at_us INTEGER NOT NULL,
 scope_locator_uri TEXT NOT NULL,
 reviewed_options_json TEXT NOT NULL CHECK(a_json(reviewed_options_json)),
 reviewed_context_json TEXT NOT NULL CHECK(a_json(reviewed_context_json)),
 approved_at_us INTEGER NOT NULL CHECK(approved_at_us>0),
 PRIMARY KEY(scope_uuidv4,locator_text,configuration_name,purpose),
 FOREIGN KEY(scope_uuidv4,locator_text,configuration_name,purpose) REFERENCES locator_connections ON DELETE CASCADE,
 FOREIGN KEY(scope_uuidv4,locator_text,repository_uuidv4) REFERENCES repository_locators(scope_uuidv4,locator_text,repository_uuidv4),
 FOREIGN KEY(scope_uuidv4,registered_at_us,scope_locator_uri) REFERENCES scope_locators
) STRICT, WITHOUT ROWID;
CREATE TRIGGER grant_checked BEFORE INSERT ON local_access_grants
WHEN NOT EXISTS(
 SELECT 1 FROM access_scopes s
 JOIN scope_locator_controls c ON c.scope_uuidv4=s.scope_uuidv4
 JOIN repository_locators r ON r.scope_uuidv4=s.scope_uuidv4
 JOIN connection_configurations p ON p.scope_uuidv4=s.scope_uuidv4
 JOIN locator_connections a ON a.scope_uuidv4=r.scope_uuidv4 AND a.locator_text=r.locator_text AND a.configuration_name=p.configuration_name
 WHERE s.scope_uuidv4=NEW.scope_uuidv4 AND s.enabled=1
 AND s.execution_context_json=NEW.reviewed_context_json
 AND c.registered_at_us=NEW.registered_at_us AND c.scope_locator_uri=NEW.scope_locator_uri AND c.enabled=1
 AND r.locator_text=NEW.locator_text AND r.repository_uuidv4=NEW.repository_uuidv4 AND r.enabled=1
 AND p.configuration_name=NEW.configuration_name AND p.options_json=NEW.reviewed_options_json AND p.enabled=1
 AND a.purpose=NEW.purpose AND a.enabled=1)
BEGIN SELECT RAISE(ABORT,'unreviewed or disabled assignment'); END;
CREATE TRIGGER grant_no_update BEFORE UPDATE ON local_access_grants
BEGIN SELECT RAISE(ABORT,'replace only after explicit local review'); END;
-- Revocation is destructive only for current permissions, never registration facts.
CREATE TRIGGER profile_revoke BEFORE UPDATE ON connection_configurations
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4 OR NEW.configuration_name IS NOT OLD.configuration_name
 OR NEW.options_json IS NOT OLD.options_json OR NEW.enabled IS NOT OLD.enabled
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND configuration_name=OLD.configuration_name; END;
CREATE TRIGGER binding_revoke BEFORE UPDATE ON repository_locators
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4 OR NEW.locator_text IS NOT OLD.locator_text
 OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.enabled IS NOT OLD.enabled
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND locator_text=OLD.locator_text; END;
CREATE TRIGGER assignment_revoke BEFORE UPDATE ON locator_connections
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4 OR NEW.locator_text IS NOT OLD.locator_text
 OR NEW.configuration_name IS NOT OLD.configuration_name OR NEW.purpose IS NOT OLD.purpose OR NEW.enabled IS NOT OLD.enabled
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND locator_text=OLD.locator_text AND configuration_name=OLD.configuration_name AND purpose=OLD.purpose; END;
CREATE TRIGGER context_revoke BEFORE UPDATE ON access_scopes
WHEN NEW.execution_context_json IS NOT OLD.execution_context_json OR NEW.enabled IS NOT OLD.enabled
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4; END;
CREATE TRIGGER scope_no_rekey BEFORE UPDATE ON access_scopes
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4
BEGIN SELECT RAISE(ABORT,'permanent scope identity'); END;
CREATE TRIGGER route_revoke BEFORE UPDATE ON scope_locator_controls
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND registered_at_us=OLD.registered_at_us AND scope_locator_uri=OLD.scope_locator_uri; END;
CREATE TRIGGER route_delete_revoke BEFORE DELETE ON scope_locator_controls
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND registered_at_us=OLD.registered_at_us AND scope_locator_uri=OLD.scope_locator_uri; END;
-- REPLACE must not bypass update/revocation rules for mutable settings.
CREATE TRIGGER scope_no_replace BEFORE INSERT ON access_scopes
WHEN EXISTS(SELECT 1 FROM access_scopes WHERE scope_uuidv4=NEW.scope_uuidv4)
BEGIN SELECT RAISE(ABORT,'explicit update required'); END;
CREATE TRIGGER profile_no_replace BEFORE INSERT ON connection_configurations
WHEN EXISTS(SELECT 1 FROM connection_configurations WHERE scope_uuidv4=NEW.scope_uuidv4 AND configuration_name=NEW.configuration_name)
BEGIN SELECT RAISE(ABORT,'explicit update required'); END;
CREATE TRIGGER binding_no_replace BEFORE INSERT ON repository_locators
WHEN EXISTS(SELECT 1 FROM repository_locators WHERE scope_uuidv4=NEW.scope_uuidv4 AND locator_text=NEW.locator_text)
BEGIN SELECT RAISE(ABORT,'binding conflict or explicit update required'); END;
CREATE TRIGGER assignment_no_replace BEFORE INSERT ON locator_connections
WHEN EXISTS(SELECT 1 FROM locator_connections WHERE scope_uuidv4=NEW.scope_uuidv4 AND locator_text=NEW.locator_text AND configuration_name=NEW.configuration_name AND purpose=NEW.purpose)
BEGIN SELECT RAISE(ABORT,'explicit update required'); END;
CREATE TRIGGER controls_no_replace BEFORE INSERT ON scope_locator_controls
WHEN EXISTS(SELECT 1 FROM scope_locator_controls WHERE scope_uuidv4=NEW.scope_uuidv4 AND registered_at_us=NEW.registered_at_us AND scope_locator_uri=NEW.scope_locator_uri)
BEGIN SELECT RAISE(ABORT,'explicit update required'); END;
CREATE VIEW scope_first_choices AS
SELECT l.scope_uuidv4,l.registered_at_us,l.scope_locator_uri FROM scope_locators l
WHERE l.registered_at_us=(SELECT MAX(m.registered_at_us) FROM scope_locators m WHERE m.scope_uuidv4=l.scope_uuidv4);
