-- Every document is a derivative projection of an exact authority snapshot.
-- No ordinary repository-file text/body projection is admitted.
CREATE TABLE search_projections (
 projection_kind TEXT NOT NULL CHECK(projection_kind IN ('git_metadata','notes','context_text')),
 snapshot_token_json TEXT NOT NULL CHECK(p1_json(snapshot_token_json)),
 PRIMARY KEY(projection_kind,snapshot_token_json)
) STRICT, WITHOUT ROWID;
CREATE TABLE search_documents (
 projection_kind TEXT NOT NULL,
 snapshot_token_json TEXT NOT NULL,
 document_key_json TEXT NOT NULL CHECK(p1_json(document_key_json)),
 searchable_text TEXT NOT NULL,
 PRIMARY KEY(projection_kind,snapshot_token_json,document_key_json),
 FOREIGN KEY(projection_kind,snapshot_token_json) REFERENCES search_projections
) STRICT, WITHOUT ROWID;
