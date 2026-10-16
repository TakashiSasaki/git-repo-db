-- Exactly FIVE physical authoritative claim columns, no rowid or hidden alias.
CREATE TABLE coverage_claims(
 owner_kind TEXT NOT NULL,
 owner_coordinates_json TEXT NOT NULL,
 observed_at_us INTEGER NOT NULL CHECK(typeof(observed_at_us)='integer' AND observed_at_us>0),
 coverage_state TEXT NOT NULL CHECK(coverage_state IN('complete','partial','unknown','not_applicable')),
 details_json TEXT CHECK(details_json IS NULL OR p1_json(details_json)),
 PRIMARY KEY(owner_kind,owner_coordinates_json,observed_at_us,coverage_state),
 FOREIGN KEY(owner_kind,owner_coordinates_json) REFERENCES coverage_scopes
) STRICT, WITHOUT ROWID;
CREATE TRIGGER coverage_claim_no_update BEFORE UPDATE ON coverage_claims BEGIN SELECT RAISE(ABORT,'immutable Coverage claim'); END;
CREATE TRIGGER coverage_claim_no_delete BEFORE DELETE ON coverage_claims BEGIN SELECT RAISE(ABORT,'immutable Coverage claim'); END;
CREATE TRIGGER coverage_claim_no_replace BEFORE INSERT ON coverage_claims WHEN EXISTS(
 SELECT 1 FROM coverage_claims WHERE owner_kind=NEW.owner_kind AND owner_coordinates_json=NEW.owner_coordinates_json AND observed_at_us=NEW.observed_at_us AND coverage_state=NEW.coverage_state)
 BEGIN SELECT RAISE(ABORT,'Coverage exact replay must be compared before insert'); END;
