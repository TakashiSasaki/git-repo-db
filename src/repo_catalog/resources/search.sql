PRAGMA foreign_keys=ON;
PRAGMA recursive_triggers=ON;

CREATE TABLE search_identity(
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    format_id TEXT NOT NULL CHECK(format_id='repo-catalog/search1'),
    schema_version INTEGER NOT NULL CHECK(schema_version=1),
    search_instance_id TEXT NOT NULL,
    catalog_db_instance_id TEXT NOT NULL,
    created_at_us INTEGER NOT NULL,
    last_rebuilt_at_us INTEGER,
    ddl_sha256 BLOB NOT NULL CHECK(length(ddl_sha256)=32)
) STRICT;

CREATE TABLE search_documents(
    search_document_id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('code','pr','commits','issue')),
    source_key TEXT NOT NULL,
    body TEXT NOT NULL,
    metadata TEXT NOT NULL CHECK(json_valid(metadata) AND json_type(metadata)='object'),
    UNIQUE(kind,source_key)
) STRICT;

CREATE TABLE index_generations(
    index_generation_id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('code','pr','commits','issue')),
    state TEXT NOT NULL CHECK(state IN ('building','ready','retired','removed','unavailable','failed')),
    table_name TEXT NOT NULL CHECK(length(table_name)>0 AND table_name NOT GLOB '*[^a-z0-9_]*'),
    target_max_search_document_id INTEGER NOT NULL CHECK(target_max_search_document_id>=0),
    created_at_us INTEGER
) STRICT;

CREATE TABLE index_membership(
    index_generation_id INTEGER NOT NULL REFERENCES index_generations(index_generation_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    search_document_id INTEGER NOT NULL REFERENCES search_documents(search_document_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    input_version TEXT NOT NULL,
    PRIMARY KEY(index_generation_id,search_document_id)
) STRICT;

CREATE TRIGGER search_identity_immutable BEFORE UPDATE ON search_identity WHEN NEW.singleton IS NOT OLD.singleton OR NEW.format_id IS NOT OLD.format_id OR NEW.schema_version IS NOT OLD.schema_version OR NEW.search_instance_id IS NOT OLD.search_instance_id OR NEW.catalog_db_instance_id IS NOT OLD.catalog_db_instance_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER search_identity_no_replace BEFORE INSERT ON search_identity WHEN EXISTS(SELECT 1 FROM search_identity WHERE singleton=NEW.singleton) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;

CREATE TRIGGER search_documents_immutable BEFORE UPDATE ON search_documents WHEN NEW.search_document_id IS NOT OLD.search_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER search_documents_no_replace BEFORE INSERT ON search_documents WHEN EXISTS(SELECT 1 FROM search_documents WHERE search_document_id=NEW.search_document_id OR (kind=NEW.kind AND source_key=NEW.source_key)) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;

CREATE TRIGGER index_generations_immutable BEFORE UPDATE ON index_generations WHEN NEW.index_generation_id IS NOT OLD.index_generation_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER index_generations_no_replace BEFORE INSERT ON index_generations WHEN EXISTS(SELECT 1 FROM index_generations WHERE index_generation_id=NEW.index_generation_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;

CREATE TRIGGER index_membership_immutable BEFORE UPDATE ON index_membership WHEN NEW.index_generation_id IS NOT OLD.index_generation_id OR NEW.search_document_id IS NOT OLD.search_document_id BEGIN SELECT RAISE(ABORT,'Immutable identity, owner, fact'); END;
CREATE TRIGGER index_membership_no_replace BEFORE INSERT ON index_membership WHEN EXISTS(SELECT 1 FROM index_membership WHERE index_generation_id=NEW.index_generation_id AND search_document_id=NEW.search_document_id) BEGIN SELECT RAISE(ABORT,'Conflict insert/UPSERT/REPLACE prohibited; use explicit UPDATE'); END;
CREATE INDEX index_membership_fk_0 ON index_membership(search_document_id);
