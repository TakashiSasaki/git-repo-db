-- Discardable work state. UUIDs identify explicit request/attempt occurrences,
-- never authoritative facts. Losing this database makes old continuation fail.
CREATE TABLE acquisition_requests (
 request_origin_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(request_origin_uuidv4)),
 request_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(request_uuidv4)),
 request_scope_json TEXT NOT NULL CHECK(p1_json(request_scope_json)),
 state TEXT NOT NULL CHECK(state IN ('open','stopped','complete')),
 PRIMARY KEY(request_origin_uuidv4,request_uuidv4)
) STRICT, WITHOUT ROWID;
CREATE TABLE request_budgets (
 request_origin_uuidv4 TEXT NOT NULL,
 request_uuidv4 TEXT NOT NULL,
 work_kind TEXT NOT NULL CHECK(work_kind IN ('input_bytes','verification_bytes','metadata_units','proof_steps')),
 finite_limit INTEGER NOT NULL CHECK(finite_limit >= 0),
 PRIMARY KEY(request_origin_uuidv4,request_uuidv4,work_kind),
 FOREIGN KEY(request_origin_uuidv4,request_uuidv4) REFERENCES acquisition_requests
) STRICT, WITHOUT ROWID;
CREATE TABLE acquisition_attempts (
 request_origin_uuidv4 TEXT NOT NULL,
 request_uuidv4 TEXT NOT NULL,
 attempt_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(attempt_uuidv4)),
 continuation_json TEXT NOT NULL CHECK(p1_json(continuation_json)),
 PRIMARY KEY(request_origin_uuidv4,request_uuidv4,attempt_uuidv4),
 FOREIGN KEY(request_origin_uuidv4,request_uuidv4) REFERENCES acquisition_requests
) STRICT, WITHOUT ROWID;
CREATE TABLE work_accounting (
 request_origin_uuidv4 TEXT NOT NULL,
 request_uuidv4 TEXT NOT NULL,
 attempt_uuidv4 TEXT NOT NULL,
 work_kind TEXT NOT NULL,
 work_coordinate TEXT NOT NULL CHECK(length(work_coordinate)>0),
 reserved INTEGER NOT NULL CHECK(reserved >= 0),
 actual INTEGER CHECK(actual >= 0 AND actual <= reserved),
 PRIMARY KEY(request_origin_uuidv4,request_uuidv4,attempt_uuidv4,work_kind,work_coordinate),
 FOREIGN KEY(request_origin_uuidv4,request_uuidv4,attempt_uuidv4) REFERENCES acquisition_attempts,
 FOREIGN KEY(request_origin_uuidv4,request_uuidv4,work_kind) REFERENCES request_budgets
) STRICT, WITHOUT ROWID;
CREATE TRIGGER finite_work BEFORE INSERT ON work_accounting BEGIN
 SELECT CASE WHEN NEW.reserved + coalesce((SELECT sum(coalesce(actual,reserved)) FROM work_accounting
 WHERE request_origin_uuidv4=NEW.request_origin_uuidv4 AND request_uuidv4=NEW.request_uuidv4 AND work_kind=NEW.work_kind),0)
 > (SELECT finite_limit FROM request_budgets WHERE request_origin_uuidv4=NEW.request_origin_uuidv4 AND request_uuidv4=NEW.request_uuidv4 AND work_kind=NEW.work_kind)
 THEN RAISE(ABORT,'finite cumulative request budget') END;
END;
CREATE TABLE request_continuations (
 request_origin_uuidv4 TEXT NOT NULL,
 request_uuidv4 TEXT NOT NULL,
 continuation_scope_json TEXT NOT NULL CHECK(p1_json(continuation_scope_json)),
 cursor_json TEXT NOT NULL CHECK(p1_json(cursor_json)),
 PRIMARY KEY(request_origin_uuidv4,request_uuidv4,continuation_scope_json),
 FOREIGN KEY(request_origin_uuidv4,request_uuidv4) REFERENCES acquisition_requests
) STRICT, WITHOUT ROWID;
CREATE TABLE retry_state (
 request_origin_uuidv4 TEXT NOT NULL,
 request_uuidv4 TEXT NOT NULL,
 retry_scope_json TEXT NOT NULL CHECK(p1_json(retry_scope_json)),
 not_before_us INTEGER NOT NULL,
 reason TEXT NOT NULL,
 PRIMARY KEY(request_origin_uuidv4,request_uuidv4,retry_scope_json),
 FOREIGN KEY(request_origin_uuidv4,request_uuidv4) REFERENCES acquisition_requests
) STRICT, WITHOUT ROWID;
CREATE TABLE cache_locators (
 repository_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(repository_uuidv4)),
 cache_purpose TEXT NOT NULL CHECK(cache_purpose IN ('metadata','verified_notes')),
 semantic_coordinate_json TEXT NOT NULL CHECK(p1_json(semantic_coordinate_json)),
 locator TEXT NOT NULL,
 PRIMARY KEY(repository_uuidv4,cache_purpose,semantic_coordinate_json)
) STRICT, WITHOUT ROWID;
