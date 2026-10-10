-- DISPOSABLE PROPOSAL: P2-Q04/Q05/Q06/Q09/Q10 remain pending owner decision.
-- This narrow counterexample fixture is NOT production DDL or a migration.
-- Generic synthetic member keys below stand in for the integrated proposal's
-- separate typed PR/document/thread/inventory membership tables.
PRAGMA foreign_keys=ON;
PRAGMA recursive_triggers=ON;
CREATE TABLE p2_repositories(repository_uuidv4 TEXT PRIMARY KEY) STRICT;
CREATE TABLE p2_sources(source_registration_uuidv4 TEXT PRIMARY KEY) STRICT;
CREATE TABLE p2_collection_scopes(
 scope_id TEXT PRIMARY KEY,
 repository_uuidv4 TEXT REFERENCES p2_repositories,
 source_registration_uuidv4 TEXT REFERENCES p2_sources,
 family TEXT NOT NULL,
 CHECK((repository_uuidv4 IS NOT NULL)+(source_registration_uuidv4 IS NOT NULL)=1)
) STRICT;
CREATE TABLE p2_collection_observations(
 collection_uuidv4 TEXT PRIMARY KEY,
 scope_id TEXT NOT NULL REFERENCES p2_collection_scopes,
 captured_source_registration_uuidv4 TEXT REFERENCES p2_sources,
 UNIQUE(collection_uuidv4,scope_id)
) STRICT;
CREATE TABLE p2_member_observations(
 observation_uuidv4 TEXT PRIMARY KEY,
 repository_uuidv4 TEXT NOT NULL REFERENCES p2_repositories,
 family TEXT NOT NULL CHECK(family IN ('pr','thread','comment')),
 resource_key TEXT NOT NULL,
 title_status TEXT NOT NULL CHECK(title_status IN ('missing','null','value')),
 title TEXT,
 requires_child INTEGER NOT NULL CHECK(requires_child IN (0,1)),
 CHECK((title_status='value' AND title IS NOT NULL)
       OR (title_status IN ('missing','null') AND title IS NULL)),
 UNIQUE(observation_uuidv4,repository_uuidv4,family,resource_key)
) STRICT;
CREATE TABLE p2_collection_fragments(
 collection_uuidv4 TEXT NOT NULL REFERENCES p2_collection_observations,
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 observed_at_us INTEGER NOT NULL,
 is_terminal INTEGER NOT NULL CHECK(is_terminal IN (0,1)),
 members_sha256 BLOB NOT NULL CHECK(length(members_sha256)=32),
 parser_module TEXT NOT NULL CHECK(length(parser_module)>0),
 parser_version TEXT NOT NULL CHECK(length(parser_version)>0),
 PRIMARY KEY(collection_uuidv4,ordinal)
) STRICT;
CREATE TABLE p2_collection_members(
 collection_uuidv4 TEXT NOT NULL,
 fragment_ordinal INTEGER NOT NULL,
 member_ordinal INTEGER NOT NULL CHECK(member_ordinal>=0),
 observation_uuidv4 TEXT NOT NULL,
 repository_uuidv4 TEXT NOT NULL,
 family TEXT NOT NULL,
 resource_key TEXT NOT NULL,
 state_sha256 BLOB NOT NULL CHECK(length(state_sha256)=32),
 PRIMARY KEY(collection_uuidv4,fragment_ordinal,member_ordinal),
 FOREIGN KEY(collection_uuidv4,fragment_ordinal)
   REFERENCES p2_collection_fragments(collection_uuidv4,ordinal),
 FOREIGN KEY(observation_uuidv4,repository_uuidv4,family,resource_key)
   REFERENCES p2_member_observations(observation_uuidv4,repository_uuidv4,family,resource_key)
) STRICT;
CREATE TRIGGER p2_member_scope BEFORE INSERT ON p2_collection_members
WHEN NOT EXISTS(SELECT 1 FROM p2_collection_observations c
 JOIN p2_collection_scopes s USING(scope_id)
 WHERE c.collection_uuidv4=NEW.collection_uuidv4
 AND s.repository_uuidv4=NEW.repository_uuidv4)
BEGIN SELECT RAISE(ABORT,'Collection/member repository mismatch'); END;
CREATE TABLE p2_collection_terminals(
 terminal_uuidv4 TEXT PRIMARY KEY,
 collection_uuidv4 TEXT NOT NULL UNIQUE REFERENCES p2_collection_observations,
 final_ordinal INTEGER NOT NULL CHECK(final_ordinal>=0),
 observed_at_us INTEGER NOT NULL,
 members_sha256 BLOB NOT NULL CHECK(length(members_sha256)=32),
 FOREIGN KEY(collection_uuidv4,final_ordinal)
   REFERENCES p2_collection_fragments(collection_uuidv4,ordinal)
) STRICT;
CREATE TABLE p2_child_obligations(
 parent_collection_uuidv4 TEXT NOT NULL,
 parent_fragment_ordinal INTEGER NOT NULL,
 parent_member_ordinal INTEGER NOT NULL,
 child_collection_uuidv4 TEXT NOT NULL UNIQUE REFERENCES p2_collection_observations,
 PRIMARY KEY(parent_collection_uuidv4,parent_fragment_ordinal,parent_member_ordinal),
 FOREIGN KEY(parent_collection_uuidv4,parent_fragment_ordinal,parent_member_ordinal)
   REFERENCES p2_collection_members(collection_uuidv4,fragment_ordinal,member_ordinal)
) STRICT;
CREATE TRIGGER p2_child_scope BEFORE INSERT ON p2_child_obligations
WHEN NOT EXISTS(SELECT 1 FROM p2_collection_observations p
 JOIN p2_collection_scopes ps ON ps.scope_id=p.scope_id
 JOIN p2_collection_observations c ON c.collection_uuidv4=NEW.child_collection_uuidv4
 JOIN p2_collection_scopes cs ON cs.scope_id=c.scope_id
 WHERE p.collection_uuidv4=NEW.parent_collection_uuidv4
 AND ps.repository_uuidv4 IS cs.repository_uuidv4
 AND ps.source_registration_uuidv4 IS cs.source_registration_uuidv4
 AND p.captured_source_registration_uuidv4 IS c.captured_source_registration_uuidv4)
BEGIN SELECT RAISE(ABORT,'Child/parent owner mismatch'); END;
CREATE INDEX p2_members_observation ON p2_collection_members(observation_uuidv4);
CREATE INDEX p2_children_parent ON p2_child_obligations(parent_collection_uuidv4);
-- Deliberately the accepted exact five-column claim shape, kept unchanged.
CREATE TABLE coverage_claims(
 coverage_claim_id INTEGER PRIMARY KEY,
 coverage_scope_id TEXT NOT NULL REFERENCES p2_collection_scopes,
 coverage_state TEXT NOT NULL CHECK(coverage_state IN ('complete','partial','unknown','not_applicable')),
 observed_at_us INTEGER NOT NULL,
 details_json TEXT,
 UNIQUE(coverage_scope_id,observed_at_us,coverage_state)
) STRICT;
