CREATE TABLE service_instances(
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('github','gitlab','gitea','forgejo','gitolite','git','other')),
    name TEXT NOT NULL UNIQUE,
    web_base_url TEXT,
    api_base_url TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
) STRICT;
ALTER TABLE sources ADD COLUMN instance_id TEXT REFERENCES service_instances(id);

-- The migration runner disables FK enforcement for this transactional rebuild
-- and checks all FK relationships before committing. Repository UUIDs stay intact.
CREATE TABLE repositories_v2(
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    provider_host TEXT NOT NULL,
    provider_repo_id TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    current_snapshot TEXT
) STRICT;
INSERT INTO repositories_v2 SELECT * FROM repositories;
DROP TABLE repositories;
ALTER TABLE repositories_v2 RENAME TO repositories;

CREATE TABLE repository_bindings(
    repo_id TEXT NOT NULL REFERENCES repositories(id),
    instance_id TEXT NOT NULL REFERENCES service_instances(id),
    provider_repo_id TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    PRIMARY KEY(repo_id,instance_id),
    UNIQUE(instance_id,provider_repo_id),
    CHECK(provider_repo_id IS NULL OR length(provider_repo_id)>0)
) STRICT;
CREATE TABLE repository_endpoints(
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL REFERENCES repositories(id),
    url TEXT NOT NULL CHECK(length(url)>0),
    transport TEXT NOT NULL CHECK(transport IN ('file','https','ssh','other')),
    label TEXT,
    is_preferred INTEGER NOT NULL DEFAULT 0 CHECK(is_preferred IN (0,1)),
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(repo_id,url)
) STRICT;
CREATE UNIQUE INDEX endpoint_preferred ON repository_endpoints(repo_id) WHERE is_preferred=1;
CREATE TABLE source_repositories(
    source_id TEXT NOT NULL REFERENCES sources(id),
    repo_id TEXT NOT NULL REFERENCES repositories(id),
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY(source_id,repo_id)
) STRICT;
CREATE INDEX repository_sources ON source_repositories(repo_id,source_id);

ALTER TABLE collection_runs ADD COLUMN endpoint_id TEXT REFERENCES repository_endpoints(id);
ALTER TABLE collection_runs ADD COLUMN endpoint_url TEXT;
CREATE TRIGGER run_endpoint_repo_insert BEFORE INSERT ON collection_runs
WHEN NEW.endpoint_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM repository_endpoints WHERE id=NEW.endpoint_id AND repo_id=NEW.repo_id
) BEGIN
    SELECT RAISE(ABORT,'Endpoint belongs to another repository');
END;
CREATE TRIGGER run_endpoint_repo_update BEFORE UPDATE OF endpoint_id,repo_id ON collection_runs
WHEN NEW.endpoint_id IS NOT NULL AND NOT EXISTS(
    SELECT 1 FROM repository_endpoints WHERE id=NEW.endpoint_id AND repo_id=NEW.repo_id
) BEGIN
    SELECT RAISE(ABORT,'Endpoint belongs to another repository');
END;
