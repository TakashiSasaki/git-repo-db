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
 spent_or_reserved INTEGER NOT NULL DEFAULT 0 CHECK(spent_or_reserved >= 0 AND spent_or_reserved <= finite_limit),
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
-- Operational cached expenditure; the application independently checks these
-- counters against actual accounting rows and its mandatory durable checkpoint
-- on resume or unknown writes. No Core authority or success ledger is implied.
CREATE TRIGGER finite_work BEFORE INSERT ON work_accounting BEGIN
 SELECT CASE WHEN NEW.reserved >
 (SELECT finite_limit-spent_or_reserved FROM request_budgets WHERE request_origin_uuidv4=NEW.request_origin_uuidv4 AND request_uuidv4=NEW.request_uuidv4 AND work_kind=NEW.work_kind)
 THEN RAISE(ABORT,'finite cumulative request budget') END;
END;
CREATE TRIGGER work_reserved AFTER INSERT ON work_accounting BEGIN
 UPDATE request_budgets SET spent_or_reserved=spent_or_reserved+coalesce(NEW.actual,NEW.reserved)
 WHERE request_origin_uuidv4=NEW.request_origin_uuidv4 AND request_uuidv4=NEW.request_uuidv4 AND work_kind=NEW.work_kind;
END;
CREATE TRIGGER work_reservation_immutable BEFORE UPDATE OF
 request_origin_uuidv4,request_uuidv4,attempt_uuidv4,work_kind,work_coordinate,reserved
 ON work_accounting BEGIN
 SELECT RAISE(ABORT,'immutable work reservation');
END;
CREATE TRIGGER finite_settlement BEFORE UPDATE OF actual ON work_accounting BEGIN
 SELECT CASE WHEN coalesce(NEW.actual,NEW.reserved)-coalesce(OLD.actual,OLD.reserved) >
 (SELECT finite_limit-spent_or_reserved FROM request_budgets WHERE request_origin_uuidv4=NEW.request_origin_uuidv4 AND request_uuidv4=NEW.request_uuidv4 AND work_kind=NEW.work_kind)
 THEN RAISE(ABORT,'finite cumulative request budget') END;
END;
CREATE TRIGGER work_settled AFTER UPDATE OF actual ON work_accounting BEGIN
 UPDATE request_budgets SET spent_or_reserved=spent_or_reserved-coalesce(OLD.actual,OLD.reserved)+coalesce(NEW.actual,NEW.reserved)
 WHERE request_origin_uuidv4=NEW.request_origin_uuidv4 AND request_uuidv4=NEW.request_uuidv4 AND work_kind=NEW.work_kind;
END;
CREATE TRIGGER work_deleted AFTER DELETE ON work_accounting BEGIN
 UPDATE request_budgets SET spent_or_reserved=spent_or_reserved-coalesce(OLD.actual,OLD.reserved)
 WHERE request_origin_uuidv4=OLD.request_origin_uuidv4 AND request_uuidv4=OLD.request_uuidv4 AND work_kind=OLD.work_kind;
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

-- ADR 0030: direct PackageKey in an existing semantic progress slot. No payload
-- staging or Mapping witness. Request ownership does not enlarge the key.
CREATE UNIQUE INDEX exchange_package_key ON request_continuations(continuation_scope_json)
 WHERE json_extract(continuation_scope_json,'$[0]')='adr0030-package-binding';
CREATE TRIGGER exchange_binding_no_rebind BEFORE UPDATE ON request_continuations
 WHEN json_extract(OLD.continuation_scope_json,'$[0]')='adr0030-package-binding'
  AND (NEW.continuation_scope_json!=OLD.continuation_scope_json
    OR NEW.cursor_json!=OLD.cursor_json
    OR NEW.request_origin_uuidv4!=OLD.request_origin_uuidv4
    OR NEW.request_uuidv4!=OLD.request_uuidv4)
 BEGIN SELECT RAISE(ABORT,'immutable Exchange PackageKey digest binding'); END;
CREATE TRIGGER exchange_binding_no_delete BEFORE DELETE ON request_continuations
 WHEN json_extract(OLD.continuation_scope_json,'$[0]')='adr0030-package-binding'
 BEGIN SELECT RAISE(ABORT,'immutable Exchange PackageKey digest binding'); END;
