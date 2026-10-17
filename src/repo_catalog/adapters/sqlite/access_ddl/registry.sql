-- Opt-in Access registry foundation, not a replacement for any P1 store.
CREATE TABLE access_identity (
 store_role TEXT PRIMARY KEY CHECK(store_role='access'),
 format_id TEXT NOT NULL CHECK(format_id='repo-catalog/access-registry-1'),
 schema_version INTEGER NOT NULL CHECK(schema_version=1),
 ddl_sha256 TEXT NOT NULL CHECK(length(ddl_sha256)=64 AND ddl_sha256 NOT GLOB '*[^0-9a-f]*')
) STRICT, WITHOUT ROWID;
CREATE TABLE access_scopes (
 scope_uuidv4 TEXT PRIMARY KEY CHECK(access_uuid4(scope_uuidv4)),
 display_name TEXT NOT NULL CHECK(access_label(display_name))
) STRICT, WITHOUT ROWID;
CREATE TABLE scope_locators (
 scope_uuidv4 TEXT NOT NULL REFERENCES access_scopes,
 registered_at_us INTEGER NOT NULL CHECK(registered_at_us>0),
 scope_locator_uri TEXT NOT NULL CHECK(access_scope_uri(scope_locator_uri)),
 PRIMARY KEY(scope_uuidv4,registered_at_us,scope_locator_uri)
) STRICT, WITHOUT ROWID;
-- These are current controls, not copied historical/current locator authority.
CREATE TABLE scope_locator_controls (
 scope_uuidv4 TEXT NOT NULL,
 registered_at_us INTEGER NOT NULL,
 scope_locator_uri TEXT NOT NULL,
 enabled INTEGER NOT NULL CHECK(enabled IN(0,1)),
 PRIMARY KEY(scope_uuidv4,registered_at_us,scope_locator_uri),
 FOREIGN KEY(scope_uuidv4,registered_at_us,scope_locator_uri) REFERENCES scope_locators
) STRICT, WITHOUT ROWID;
CREATE VIEW scope_first_choices AS
SELECT l.scope_uuidv4,l.registered_at_us,l.scope_locator_uri FROM scope_locators l
WHERE l.registered_at_us=(SELECT MAX(m.registered_at_us) FROM scope_locators m WHERE m.scope_uuidv4=l.scope_uuidv4);
CREATE TRIGGER access_identity_no_update BEFORE UPDATE ON access_identity
BEGIN SELECT RAISE(ABORT,'immutable Access format'); END;
CREATE TRIGGER access_identity_no_delete BEFORE DELETE ON access_identity
BEGIN SELECT RAISE(ABORT,'immutable Access format'); END;
CREATE TRIGGER access_identity_no_replace BEFORE INSERT ON access_identity
WHEN EXISTS(SELECT 1 FROM access_identity)
BEGIN SELECT RAISE(ABORT,'Access identity already exists'); END;
CREATE TRIGGER scope_identity_no_update BEFORE UPDATE ON access_scopes
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4
BEGIN SELECT RAISE(ABORT,'immutable Scope identity'); END;
CREATE TRIGGER scope_identity_no_delete BEFORE DELETE ON access_scopes
BEGIN SELECT RAISE(ABORT,'Scope retirement not implemented'); END;
CREATE TRIGGER scope_identity_no_replace BEFORE INSERT ON access_scopes
WHEN EXISTS(SELECT 1 FROM access_scopes WHERE scope_uuidv4=NEW.scope_uuidv4)
BEGIN SELECT RAISE(ABORT,'explicit Scope update required'); END;
CREATE TRIGGER scope_registration_no_update BEFORE UPDATE ON scope_locators
BEGIN SELECT RAISE(ABORT,'immutable Scope registration'); END;
CREATE TRIGGER scope_registration_no_delete BEFORE DELETE ON scope_locators
BEGIN SELECT RAISE(ABORT,'immutable Scope registration'); END;
CREATE TRIGGER scope_registration_no_replace BEFORE INSERT ON scope_locators
WHEN EXISTS(SELECT 1 FROM scope_locators WHERE scope_uuidv4=NEW.scope_uuidv4
 AND registered_at_us=NEW.registered_at_us AND scope_locator_uri=NEW.scope_locator_uri)
BEGIN SELECT RAISE(ABORT,'compare replay before insertion'); END;
CREATE TRIGGER scope_control_no_rekey BEFORE UPDATE ON scope_locator_controls
WHEN NEW.scope_uuidv4 IS NOT OLD.scope_uuidv4 OR NEW.registered_at_us IS NOT OLD.registered_at_us
 OR NEW.scope_locator_uri IS NOT OLD.scope_locator_uri
BEGIN SELECT RAISE(ABORT,'immutable control subject'); END;
CREATE TRIGGER scope_control_no_replace BEFORE INSERT ON scope_locator_controls
WHEN EXISTS(SELECT 1 FROM scope_locator_controls WHERE scope_uuidv4=NEW.scope_uuidv4
 AND registered_at_us=NEW.registered_at_us AND scope_locator_uri=NEW.scope_locator_uri)
BEGIN SELECT RAISE(ABORT,'explicit control update required'); END;
