from scripts.schema_audit import BOOLEAN_COLUMNS, JSON_COLUMNS, STATE_VALUES

from .common import canonical, now, strict_json


def classify(record, encoding="UTF-8"):
    issues = []
    for name, kind, raw in record.values:
        if kind == "text":
            try:
                raw.decode(encoding)
            except UnicodeError:
                issues.append(("MALFORMED_TEXT", "blocking", name))
        if name in JSON_COLUMNS.get(record.table, ()) and kind != "null":
            try:
                if kind != "text":
                    raise ValueError()
                strict_json(raw.decode(encoding))
            except (ValueError, UnicodeError):
                issues.append(("INVALID_LEGACY_JSON", "blocking", name))
        if name in BOOLEAN_COLUMNS.get(record.table, ()) and (
            kind != "integer" or raw not in (b"0", b"1")
        ):
            issues.append(("INVALID_LEGACY_BOOLEAN", "blocking", name))
        if name == "state" and record.table in STATE_VALUES:
            if kind != "text" or raw not in [
                s.encode(encoding) for s in STATE_VALUES[record.table]
            ]:
                issues.append(("INVALID_LEGACY_STATE", "blocking", name))
            elif raw == "partial".encode(encoding):
                issues.append(("PARTIAL_ACQUISITION_PRESERVED", "partial", name))
        if record.table == "api_responses" and name == "body":
            # Linking/replaying opaque payloads is P3/P4, not inferred in P2.
            issues.append(("PAYLOAD_REPLAY_PENDING", "partial", name))
    return issues


def store(db, run_id, code, severity, details):
    db.execute(
        "INSERT INTO validation_results(run_id,invariant_id,code,severity,observed_at,details) VALUES(?,?,?,?,?,?)",
        (run_id, "I31", code, severity, now(), canonical(details)),
    )


def source_issues(db):
    # Counts/locations only, no payload/URL/credential in diagnostic messages.
    return [
        {"table": r[0], "rowid": r[1], "parent": r[2], "fk": r[3]}
        for r in db.execute("PRAGMA foreign_key_check")
    ]


def counts(db, run_id):
    return dict(
        db.execute(
            "SELECT severity,count(*) FROM validation_results WHERE run_id=? GROUP BY severity",
            (run_id,),
        )
    )
