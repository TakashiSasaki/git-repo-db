-- Minimal immutable observations for latest-state resource collection. These
-- receipts seal identities and state digests, never mutable body foreign keys.
-- Acquisition/source/endpoint scope remains owned by fetch_collections.
CREATE TABLE current_collection_pages(
 fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id),
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 observed_at_us INTEGER NOT NULL,
 next_cursor TEXT,
 members TEXT NOT NULL CHECK(json_valid(members) AND json_type(members)='array'),
 status INTEGER NOT NULL CHECK(status>=200 AND status<300),
 parser_profile_uuidv4 TEXT NOT NULL REFERENCES parser_profiles(parser_profile_uuidv4),
 PRIMARY KEY(fetch_collection_id,ordinal)
) STRICT;
CREATE INDEX current_collection_pages_profile ON current_collection_pages(parser_profile_uuidv4);
CREATE TRIGGER current_collection_pages_profile_capability BEFORE INSERT ON current_collection_pages
WHEN NOT EXISTS(SELECT 1 FROM fetch_collections c JOIN parser_profile_capabilities p ON p.parser_profile_uuidv4=NEW.parser_profile_uuidv4 AND p.owner_kind='repository' AND p.fact_kind=CASE c.kind WHEN 'threads' THEN 'review-comment' WHEN 'thread-comments' THEN 'review-comment' WHEN 'review-comment-incremental' THEN 'review-comment' ELSE c.kind END WHERE c.fetch_collection_id=NEW.fetch_collection_id)
 OR EXISTS(SELECT 1 FROM json_each(NEW.members) m WHERE CASE WHEN m.type='object' THEN NOT EXISTS(SELECT 1 FROM parser_profile_capabilities p WHERE p.parser_profile_uuidv4=NEW.parser_profile_uuidv4 AND p.owner_kind='repository' AND p.fact_kind=CASE json_extract(m.value,'$.kind') WHEN 'issue-comment' THEN 'ordinary-issue-comment' ELSE json_extract(m.value,'$.kind') END) ELSE 0 END)
BEGIN SELECT RAISE(ABORT,'Current page parser lacks required capability'); END;
CREATE TRIGGER current_collection_pages_immutable BEFORE UPDATE ON current_collection_pages
BEGIN SELECT RAISE(ABORT,'Current collection page receipt is immutable'); END;
CREATE TRIGGER current_collection_pages_retain BEFORE DELETE ON current_collection_pages
BEGIN SELECT RAISE(ABORT,'Retain current collection completeness receipts'); END;
CREATE TRIGGER current_collection_pages_no_replace BEFORE INSERT ON current_collection_pages
WHEN EXISTS(SELECT 1 FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id AND ordinal=NEW.ordinal)
BEGIN SELECT RAISE(ABORT,'Current collection page receipt already exists'); END;
CREATE TRIGGER current_collection_pages_not_after_terminal BEFORE INSERT ON current_collection_pages
WHEN EXISTS(SELECT 1 FROM completion_markers m WHERE (m.fetch_collection_id=NEW.fetch_collection_id AND json_extract(m.evidence,'$.kind')='current-resource-pages-v1') OR EXISTS(SELECT 1 FROM json_each(m.evidence,'$.current_page_collections') e WHERE json_extract(e.value,'$.fetch_collection_id')=NEW.fetch_collection_id))
BEGIN SELECT RAISE(ABORT,'Current collection is sealed'); END;
CREATE TRIGGER current_collection_completion_valid BEFORE INSERT ON completion_markers
WHEN json_extract(NEW.evidence,'$.kind')='current-resource-pages-v1' AND (
 NEW.asserted_state<>'complete'
 OR json_type(NEW.evidence,'$.terminal') IS NOT 'true'
 OR json_type(NEW.evidence,'$.page_ordinals') IS NOT 'array'
 OR (SELECT count(*) FROM json_each(NEW.evidence))<>3
 OR NOT EXISTS(SELECT 1 FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id)
 OR NEW.observed_at_us IS NOT (SELECT max(observed_at_us) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id)
 OR json_array_length(NEW.evidence,'$.page_ordinals')<>(SELECT count(*) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id)
 OR EXISTS(SELECT 1 FROM json_each(NEW.evidence,'$.page_ordinals') e WHERE e.type<>'integer' OR e.value<>CAST(e.key AS INTEGER) OR NOT EXISTS(SELECT 1 FROM current_collection_pages p WHERE p.fetch_collection_id=NEW.fetch_collection_id AND p.ordinal=e.value))
 OR EXISTS(SELECT 1 FROM current_collection_pages p WHERE p.fetch_collection_id=NEW.fetch_collection_id AND ((p.ordinal=(SELECT max(ordinal) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id) AND p.next_cursor IS NOT NULL) OR (p.ordinal<(SELECT max(ordinal) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id) AND p.next_cursor IS NULL)))
)
BEGIN SELECT RAISE(ABORT,'Invalid current collection completeness proof'); END;
