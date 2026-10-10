-- Minimal immutable observations for latest-state resource collection. These
-- receipts attest identities and state digests, never mutable body foreign keys.
-- Acquisition/source/endpoint scope remains owned by fetch_collections.
CREATE TABLE current_collection_pages(
 fetch_collection_id TEXT NOT NULL REFERENCES fetch_collections(fetch_collection_id),
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 observed_at_us INTEGER NOT NULL,
 has_next INTEGER NOT NULL CHECK(has_next IN (0,1)),
 members TEXT NOT NULL CHECK(json_valid(members) AND json_type(members)='array'),
 status INTEGER NOT NULL CHECK(status>=200 AND status<300),
 parser_module TEXT NOT NULL CHECK(length(parser_module)>0 AND instr(parser_module,char(0))=0),
 parser_version TEXT NOT NULL CHECK(length(parser_version)>0 AND instr(parser_version,char(0))=0),
 PRIMARY KEY(fetch_collection_id,ordinal)
) STRICT;
CREATE TRIGGER current_collection_pages_immutable BEFORE UPDATE ON current_collection_pages
BEGIN SELECT RAISE(ABORT,'Current collection page receipt is immutable'); END;
CREATE TRIGGER current_collection_pages_retain BEFORE DELETE ON current_collection_pages
BEGIN SELECT RAISE(ABORT,'Retain current collection completeness receipts'); END;
CREATE TRIGGER current_collection_pages_no_replace BEFORE INSERT ON current_collection_pages
WHEN EXISTS(SELECT 1 FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id AND ordinal=NEW.ordinal)
BEGIN SELECT RAISE(ABORT,'Current collection page receipt already exists'); END;
CREATE TRIGGER current_collection_pages_not_after_terminal BEFORE INSERT ON current_collection_pages
WHEN EXISTS(SELECT 1 FROM completion_markers m WHERE m.fetch_collection_id=NEW.fetch_collection_id AND json_extract(m.evidence,'$.kind') IN ('current-resource-pages-v1','current-resource-tree-v1'))
BEGIN SELECT RAISE(ABORT,'Completed collection evidence is immutable'); END;
CREATE TRIGGER current_collection_completion_kind BEFORE INSERT ON completion_markers
WHEN NEW.asserted_state='complete' AND coalesce(json_extract(NEW.evidence,'$.kind'),'') NOT IN ('current-resource-pages-v1','current-resource-tree-v1')
BEGIN SELECT RAISE(ABORT,'Complete collection requires a typed enumeration proof'); END;
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
 OR EXISTS(SELECT 1 FROM current_collection_pages p WHERE p.fetch_collection_id=NEW.fetch_collection_id AND ((p.ordinal=(SELECT max(ordinal) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id) AND p.has_next=1) OR (p.ordinal<(SELECT max(ordinal) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id) AND p.has_next=0)))
)
BEGIN SELECT RAISE(ABORT,'Invalid current collection completeness proof'); END;

CREATE TRIGGER current_collection_tree_completion_valid BEFORE INSERT ON completion_markers
WHEN json_extract(NEW.evidence,'$.kind')='current-resource-tree-v1' AND (
 NEW.asserted_state<>'complete' OR json_type(NEW.evidence,'$.terminal') IS NOT 'true'
 OR json_type(NEW.evidence,'$.page_ordinals') IS NOT 'array' OR json_type(NEW.evidence,'$.fetch_collection_ids') IS NOT 'array'
 OR (SELECT count(*) FROM json_each(NEW.evidence))<>4
 OR NOT EXISTS(SELECT 1 FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id)
 OR json_array_length(NEW.evidence,'$.page_ordinals')<>(SELECT count(*) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id)
 OR EXISTS(SELECT 1 FROM json_each(NEW.evidence,'$.page_ordinals') e WHERE e.type<>'integer' OR e.value<>CAST(e.key AS INTEGER) OR NOT EXISTS(SELECT 1 FROM current_collection_pages p WHERE p.fetch_collection_id=NEW.fetch_collection_id AND p.ordinal=e.value))
 OR EXISTS(SELECT 1 FROM current_collection_pages p WHERE p.fetch_collection_id=NEW.fetch_collection_id AND ((p.ordinal=(SELECT max(ordinal) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id) AND p.has_next=1) OR (p.ordinal<(SELECT max(ordinal) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id) AND p.has_next=0)))
 OR json_array_length(NEW.evidence,'$.fetch_collection_ids')<>(SELECT count(*) FROM thread_collection_requirements WHERE fetch_collection_id=NEW.fetch_collection_id)
 OR EXISTS(SELECT 1 FROM json_each(NEW.evidence,'$.fetch_collection_ids') e GROUP BY e.value HAVING count(*)>1)
 OR EXISTS(SELECT 1 FROM thread_collection_requirements r WHERE r.fetch_collection_id=NEW.fetch_collection_id AND (r.child_fetch_collection_id IS NULL OR NOT EXISTS(SELECT 1 FROM json_each(NEW.evidence,'$.fetch_collection_ids') e WHERE e.value=r.child_fetch_collection_id) OR NOT EXISTS(SELECT 1 FROM completion_markers m WHERE m.fetch_collection_id=r.child_fetch_collection_id AND m.asserted_state='complete' AND json_extract(m.evidence,'$.kind')='current-resource-pages-v1')))
 OR NEW.observed_at_us IS NOT (SELECT max(observed_at_us) FROM current_collection_pages WHERE fetch_collection_id=NEW.fetch_collection_id OR fetch_collection_id IN (SELECT child_fetch_collection_id FROM thread_collection_requirements WHERE fetch_collection_id=NEW.fetch_collection_id))
)
BEGIN SELECT RAISE(ABORT,'Invalid nested current collection proof'); END;
