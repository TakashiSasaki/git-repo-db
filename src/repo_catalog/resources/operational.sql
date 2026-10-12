PRAGMA foreign_keys=ON;
PRAGMA recursive_triggers=ON;

CREATE TABLE operational_identity(
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    format_id TEXT NOT NULL CHECK(format_id='repo-catalog/operational1'),
    schema_version INTEGER NOT NULL CHECK(schema_version=1),
    operational_instance_id TEXT NOT NULL,
    catalog_db_instance_id TEXT NOT NULL,
    created_at_us INTEGER NOT NULL,
    ddl_sha256 BLOB NOT NULL CHECK(length(ddl_sha256)=32)
) STRICT;

CREATE TABLE jobs(
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('discover','sync','hydrate','index','legacy')),
    request TEXT NOT NULL CHECK(json_valid(request) AND json_type(request)='object'),
    current_attempt INTEGER,
    created_at_us INTEGER,
    FOREIGN KEY(job_id,current_attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE job_attempts(
    job_id TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK(attempt>=1),
    state TEXT NOT NULL CHECK(state IN ('queued','running','waiting','complete','failed','interrupted','cancelled','unknown')),
    created_at_us INTEGER,
    updated_at_us INTEGER,
    not_before_us INTEGER,
    checkpoint TEXT NOT NULL CHECK(json_valid(checkpoint) AND json_type(checkpoint)='object'),
    reason TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    PRIMARY KEY(job_id,attempt)
) STRICT;

CREATE TABLE cache_locators(
    cache_locator_id TEXT PRIMARY KEY,
    repository_uuidv4 TEXT NOT NULL,
    path TEXT NOT NULL,
    access TEXT NOT NULL CHECK(access IN ('source_readonly','target_active')),
    state TEXT NOT NULL CHECK(state IN ('available','missing','unknown')),
    UNIQUE(cache_locator_id,repository_uuidv4)
) STRICT;

CREATE TABLE active_cache_entries(
    active_cache_entry_id TEXT PRIMARY KEY,
    cache_locator_id TEXT NOT NULL REFERENCES cache_locators(cache_locator_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    generation INTEGER NOT NULL CHECK(generation>=0),
    state TEXT NOT NULL CHECK(state IN ('active','evicting','evicted')),
    last_used_us INTEGER NOT NULL,
    bytes INTEGER NOT NULL CHECK(bytes>=0)
) STRICT;

CREATE TABLE cache_leases(
    active_cache_entry_id TEXT NOT NULL REFERENCES active_cache_entries(active_cache_entry_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    job_id TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK(attempt>=1),
    acquired_at_us INTEGER NOT NULL,
    PRIMARY KEY(active_cache_entry_id,job_id,attempt),
    FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;

CREATE TABLE space_reservations(
    job_id TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK(attempt>=1),
    reserved INTEGER NOT NULL CHECK(reserved>=0),
    consumed INTEGER NOT NULL CHECK(consumed>=0),
    PRIMARY KEY(job_id,attempt),
    FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;

CREATE TABLE acquisition_progress(
    git_acquisition_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('planned','fetching','refs_captured','complete','failed','interrupted','unknown')),
    generation INTEGER NOT NULL CHECK(generation>=0),
    ended_at_us INTEGER,
    active_cache_entry_id TEXT REFERENCES active_cache_entries(active_cache_entry_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;

CREATE TABLE collection_progress(
    fetch_collection_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('running','partial','complete','failed','interrupted','unknown')),
    cursor TEXT,
    reason TEXT,
    FOREIGN KEY(job_id,attempt) REFERENCES job_attempts(job_id,attempt) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT;

CREATE TABLE search_rebuild_metrics(
    rebuild_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at_us INTEGER NOT NULL,
    ended_at_us INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    documents_indexed INTEGER NOT NULL,
    bytes_indexed INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('complete','failed'))
) STRICT;

CREATE TRIGGER operational_identity_immutable BEFORE UPDATE ON operational_identity WHEN NEW.singleton IS NOT OLD.singleton OR NEW.format_id IS NOT OLD.format_id OR NEW.schema_version IS NOT OLD.schema_version OR NEW.operational_instance_id IS NOT OLD.operational_instance_id OR NEW.catalog_db_instance_id IS NOT OLD.catalog_db_instance_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER operational_identity_no_replace BEFORE INSERT ON operational_identity WHEN EXISTS(SELECT 1 FROM operational_identity WHERE singleton=NEW.singleton) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;

CREATE TRIGGER jobs_immutable BEFORE UPDATE ON jobs WHEN NEW.job_id IS NOT OLD.job_id OR NEW.kind IS NOT OLD.kind OR NEW.request IS NOT OLD.request OR NEW.created_at_us IS NOT OLD.created_at_us BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER jobs_no_replace BEFORE INSERT ON jobs WHEN EXISTS(SELECT 1 FROM jobs WHERE job_id=NEW.job_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX jobs_fk_0 ON jobs(job_id,current_attempt);

CREATE TRIGGER job_attempts_immutable BEFORE UPDATE ON job_attempts WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER job_attempts_no_replace BEFORE INSERT ON job_attempts WHEN EXISTS(SELECT 1 FROM job_attempts WHERE job_id=NEW.job_id AND attempt=NEW.attempt) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;

CREATE TRIGGER cache_locators_immutable BEFORE UPDATE ON cache_locators WHEN NEW.cache_locator_id IS NOT OLD.cache_locator_id OR NEW.repository_uuidv4 IS NOT OLD.repository_uuidv4 OR NEW.access IS NOT OLD.access BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER cache_locators_no_replace BEFORE INSERT ON cache_locators WHEN EXISTS(SELECT 1 FROM cache_locators WHERE cache_locator_id=NEW.cache_locator_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;

CREATE TRIGGER active_cache_entries_immutable BEFORE UPDATE ON active_cache_entries WHEN NEW.active_cache_entry_id IS NOT OLD.active_cache_entry_id OR NEW.cache_locator_id IS NOT OLD.cache_locator_id OR NEW.generation IS NOT OLD.generation BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER active_cache_entries_no_replace BEFORE INSERT ON active_cache_entries WHEN EXISTS(SELECT 1 FROM active_cache_entries WHERE active_cache_entry_id=NEW.active_cache_entry_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX active_cache_entries_fk_0 ON active_cache_entries(cache_locator_id);
CREATE TRIGGER active_locator_insert BEFORE INSERT ON active_cache_entries WHEN NOT EXISTS(SELECT 1 FROM cache_locators WHERE cache_locator_id=NEW.cache_locator_id AND access='target_active') BEGIN SELECT RAISE(ABORT,'Readonly source cache cannot become active'); END;
CREATE TRIGGER active_locator_update BEFORE UPDATE ON active_cache_entries WHEN NOT EXISTS(SELECT 1 FROM cache_locators WHERE cache_locator_id=NEW.cache_locator_id AND access='target_active') BEGIN SELECT RAISE(ABORT,'Readonly source cache cannot become active'); END;

CREATE TRIGGER cache_leases_immutable BEFORE UPDATE ON cache_leases WHEN NEW.active_cache_entry_id IS NOT OLD.active_cache_entry_id OR NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER cache_leases_no_replace BEFORE INSERT ON cache_leases WHEN EXISTS(SELECT 1 FROM cache_leases WHERE active_cache_entry_id=NEW.active_cache_entry_id AND job_id=NEW.job_id AND attempt=NEW.attempt) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX cache_leases_fk_0 ON cache_leases(job_id,attempt);

CREATE TRIGGER space_reservations_immutable BEFORE UPDATE ON space_reservations WHEN NEW.job_id IS NOT OLD.job_id OR NEW.attempt IS NOT OLD.attempt BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER space_reservations_no_replace BEFORE INSERT ON space_reservations WHEN EXISTS(SELECT 1 FROM space_reservations WHERE job_id=NEW.job_id AND attempt=NEW.attempt) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;

CREATE TRIGGER acquisition_progress_immutable BEFORE UPDATE ON acquisition_progress WHEN NEW.git_acquisition_id IS NOT OLD.git_acquisition_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER acquisition_progress_no_replace BEFORE INSERT ON acquisition_progress WHEN EXISTS(SELECT 1 FROM acquisition_progress WHERE git_acquisition_id=NEW.git_acquisition_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX acquisition_progress_fk_0 ON acquisition_progress(job_id,attempt);

CREATE TRIGGER collection_progress_immutable BEFORE UPDATE ON collection_progress WHEN NEW.fetch_collection_id IS NOT OLD.fetch_collection_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER collection_progress_no_replace BEFORE INSERT ON collection_progress WHEN EXISTS(SELECT 1 FROM collection_progress WHERE fetch_collection_id=NEW.fetch_collection_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX collection_progress_fk_0 ON collection_progress(job_id,attempt);
