-- A1b current settings and local grants. No transport execution or import authority.
CREATE TABLE scope_execution_contexts (
 scope_uuidv4 TEXT PRIMARY KEY REFERENCES access_scopes,
 execution_context_json TEXT NOT NULL CHECK(access_execution_context(execution_context_json)),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1))
) STRICT, WITHOUT ROWID;
CREATE TABLE repository_locators (
 scope_uuidv4 TEXT NOT NULL REFERENCES access_scopes,
 locator_text TEXT NOT NULL CHECK(access_repository_locator(locator_text)),
 repository_uuidv4 TEXT NOT NULL CHECK(access_uuid4(repository_uuidv4)),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 PRIMARY KEY(scope_uuidv4,locator_text),
 UNIQUE(scope_uuidv4,locator_text,repository_uuidv4)
) STRICT, WITHOUT ROWID;
CREATE TABLE connection_configurations (
 scope_uuidv4 TEXT NOT NULL REFERENCES access_scopes,
 configuration_name TEXT NOT NULL CHECK(access_name(configuration_name)),
 options_json TEXT NOT NULL CHECK(access_options(options_json)),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 PRIMARY KEY(scope_uuidv4,configuration_name)
) STRICT, WITHOUT ROWID;
CREATE TABLE locator_connections (
 scope_uuidv4 TEXT NOT NULL,
 locator_text TEXT NOT NULL,
 configuration_name TEXT NOT NULL,
 purpose TEXT NOT NULL CHECK(purpose='git-read'),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
 PRIMARY KEY(scope_uuidv4,locator_text,configuration_name,purpose),
 FOREIGN KEY(scope_uuidv4,locator_text) REFERENCES repository_locators,
 FOREIGN KEY(scope_uuidv4,configuration_name) REFERENCES connection_configurations
) STRICT, WITHOUT ROWID;
CREATE TABLE repository_access_preferences (
 repository_uuidv4 TEXT NOT NULL,
 scope_uuidv4 TEXT NOT NULL,
 purpose TEXT NOT NULL,
 locator_text TEXT NOT NULL,
 configuration_name TEXT NOT NULL,
 PRIMARY KEY(repository_uuidv4,scope_uuidv4,purpose),
 FOREIGN KEY(scope_uuidv4,locator_text,configuration_name,purpose) REFERENCES locator_connections,
 FOREIGN KEY(scope_uuidv4,locator_text,repository_uuidv4)
 REFERENCES repository_locators(scope_uuidv4,locator_text,repository_uuidv4)
) STRICT, WITHOUT ROWID;
CREATE TABLE local_access_grants (
 scope_uuidv4 TEXT NOT NULL,
 locator_text TEXT NOT NULL,
 configuration_name TEXT NOT NULL,
 purpose TEXT NOT NULL,
 repository_uuidv4 TEXT NOT NULL,
 registered_at_us INTEGER NOT NULL,
 scope_locator_uri TEXT NOT NULL,
 reviewed_options_json TEXT NOT NULL CHECK(access_options(reviewed_options_json)),
 reviewed_context_json TEXT NOT NULL CHECK(access_execution_context(reviewed_context_json)),
 approved_at_us INTEGER NOT NULL CHECK(approved_at_us>0),
 PRIMARY KEY(scope_uuidv4,locator_text,configuration_name,purpose),
 FOREIGN KEY(scope_uuidv4,locator_text,configuration_name,purpose) REFERENCES locator_connections ON DELETE CASCADE,
 FOREIGN KEY(scope_uuidv4,locator_text,repository_uuidv4)
 REFERENCES repository_locators(scope_uuidv4,locator_text,repository_uuidv4),
 FOREIGN KEY(scope_uuidv4,registered_at_us,scope_locator_uri) REFERENCES scope_locators
) STRICT, WITHOUT ROWID;
CREATE INDEX grants_profile ON local_access_grants(scope_uuidv4,configuration_name);
CREATE INDEX grants_registration ON local_access_grants(scope_uuidv4,registered_at_us,scope_locator_uri);
CREATE TRIGGER scope_execution_contexts_no_replace BEFORE INSERT ON scope_execution_contexts
WHEN EXISTS(SELECT 1 FROM scope_execution_contexts WHERE scope_uuidv4=NEW.scope_uuidv4)
BEGIN SELECT RAISE(ABORT,'explicit Access change required'); END;
CREATE TRIGGER scope_execution_contexts_no_rekey BEFORE UPDATE ON scope_execution_contexts
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4
BEGIN SELECT RAISE(ABORT,'immutable Access coordinates'); END;
CREATE TRIGGER repository_locators_no_replace BEFORE INSERT ON repository_locators
WHEN EXISTS(SELECT 1 FROM repository_locators WHERE scope_uuidv4=NEW.scope_uuidv4 AND locator_text=NEW.locator_text)
BEGIN SELECT RAISE(ABORT,'explicit Access change required'); END;
CREATE TRIGGER repository_locators_no_rekey BEFORE UPDATE ON repository_locators
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4 OR NEW.locator_text IS NOT OLD.locator_text
BEGIN SELECT RAISE(ABORT,'immutable Access coordinates'); END;
CREATE TRIGGER connection_configurations_no_replace BEFORE INSERT ON connection_configurations
WHEN EXISTS(SELECT 1 FROM connection_configurations WHERE scope_uuidv4=NEW.scope_uuidv4 AND configuration_name=NEW.configuration_name)
BEGIN SELECT RAISE(ABORT,'explicit Access change required'); END;
CREATE TRIGGER connection_configurations_no_rekey BEFORE UPDATE ON connection_configurations
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4 OR NEW.configuration_name IS NOT OLD.configuration_name
BEGIN SELECT RAISE(ABORT,'immutable Access coordinates'); END;
CREATE TRIGGER locator_connections_no_replace BEFORE INSERT ON locator_connections
WHEN EXISTS(SELECT 1 FROM locator_connections WHERE scope_uuidv4=NEW.scope_uuidv4 AND locator_text=NEW.locator_text AND configuration_name=NEW.configuration_name AND purpose=NEW.purpose)
BEGIN SELECT RAISE(ABORT,'explicit Access change required'); END;
CREATE TRIGGER locator_connections_no_rekey BEFORE UPDATE ON locator_connections
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4 OR NEW.locator_text IS NOT OLD.locator_text OR NEW.configuration_name IS NOT OLD.configuration_name OR NEW.purpose IS NOT OLD.purpose
BEGIN SELECT RAISE(ABORT,'immutable Access coordinates'); END;
CREATE TRIGGER repository_access_preferences_no_replace BEFORE INSERT ON repository_access_preferences
WHEN EXISTS(SELECT 1 FROM repository_access_preferences WHERE repository_uuidv4=NEW.repository_uuidv4 AND scope_uuidv4=NEW.scope_uuidv4 AND purpose=NEW.purpose)
BEGIN SELECT RAISE(ABORT,'explicit Access change required'); END;
CREATE TRIGGER repository_access_preferences_no_rekey BEFORE UPDATE ON repository_access_preferences
WHEN NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4 OR NEW.purpose IS NOT OLD.purpose
BEGIN SELECT RAISE(ABORT,'immutable Access coordinates'); END;
CREATE TRIGGER local_access_grants_no_replace BEFORE INSERT ON local_access_grants
WHEN EXISTS(SELECT 1 FROM local_access_grants WHERE scope_uuidv4=NEW.scope_uuidv4 AND locator_text=NEW.locator_text AND configuration_name=NEW.configuration_name AND purpose=NEW.purpose)
BEGIN SELECT RAISE(ABORT,'explicit Access change required'); END;
CREATE TRIGGER local_access_grants_no_rekey BEFORE UPDATE ON local_access_grants
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4 OR NEW.locator_text IS NOT OLD.locator_text OR NEW.configuration_name IS NOT OLD.configuration_name OR NEW.purpose IS NOT OLD.purpose
BEGIN SELECT RAISE(ABORT,'immutable Access coordinates'); END;
CREATE TRIGGER scope_execution_contexts_revoke_update BEFORE UPDATE ON scope_execution_contexts
WHEN NEW.execution_context_json IS NOT OLD.execution_context_json OR NEW.enabled IS NOT OLD.enabled
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4; END;
CREATE TRIGGER scope_execution_contexts_revoke_delete BEFORE DELETE ON scope_execution_contexts
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4; END;
CREATE TRIGGER repository_locators_revoke_update BEFORE UPDATE ON repository_locators
WHEN NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.enabled IS NOT OLD.enabled
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND locator_text=OLD.locator_text; END;
CREATE TRIGGER repository_locators_revoke_delete BEFORE DELETE ON repository_locators
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND locator_text=OLD.locator_text; END;
CREATE TRIGGER connection_configurations_revoke_update BEFORE UPDATE ON connection_configurations
WHEN NEW.options_json IS NOT OLD.options_json OR NEW.enabled IS NOT OLD.enabled
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND configuration_name=OLD.configuration_name; END;
CREATE TRIGGER connection_configurations_revoke_delete BEFORE DELETE ON connection_configurations
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND configuration_name=OLD.configuration_name; END;
CREATE TRIGGER locator_connections_revoke_update BEFORE UPDATE ON locator_connections
WHEN NEW.enabled IS NOT OLD.enabled
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND locator_text=OLD.locator_text AND configuration_name=OLD.configuration_name AND purpose=OLD.purpose; END;
CREATE TRIGGER locator_connections_revoke_delete BEFORE DELETE ON locator_connections
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND locator_text=OLD.locator_text AND configuration_name=OLD.configuration_name AND purpose=OLD.purpose; END;
CREATE TRIGGER scope_locator_controls_revoke_update BEFORE UPDATE ON scope_locator_controls
WHEN NEW.enabled IS NOT OLD.enabled
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND registered_at_us=OLD.registered_at_us AND scope_locator_uri=OLD.scope_locator_uri; END;
CREATE TRIGGER scope_locator_controls_revoke_delete BEFORE DELETE ON scope_locator_controls
BEGIN DELETE FROM local_access_grants WHERE scope_uuidv4=OLD.scope_uuidv4 AND registered_at_us=OLD.registered_at_us AND scope_locator_uri=OLD.scope_locator_uri; END;
CREATE TRIGGER assignment_transport_insert BEFORE INSERT ON locator_connections
WHEN EXISTS(SELECT 1 FROM connection_configurations p WHERE p.scope_uuidv4=NEW.scope_uuidv4
 AND p.configuration_name=NEW.configuration_name
 AND json_extract(p.options_json,'$.transport')<>access_repository_transport(NEW.locator_text))
BEGIN SELECT RAISE(ABORT,'transport mismatch'); END;
CREATE TRIGGER profile_transport_update BEFORE UPDATE ON connection_configurations
WHEN EXISTS(SELECT 1 FROM locator_connections a WHERE a.scope_uuidv4=NEW.scope_uuidv4
 AND a.configuration_name=NEW.configuration_name
 AND access_repository_transport(a.locator_text)<>json_extract(NEW.options_json,'$.transport'))
BEGIN SELECT RAISE(ABORT,'transport mismatch'); END;
CREATE TRIGGER grant_no_update BEFORE UPDATE ON local_access_grants
BEGIN SELECT RAISE(ABORT,'explicit local reapproval required'); END;
CREATE TRIGGER grant_checked BEFORE INSERT ON local_access_grants
WHEN NOT EXISTS(SELECT 1 FROM scope_execution_contexts s
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
