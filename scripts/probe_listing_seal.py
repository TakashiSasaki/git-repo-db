"""Exercise the reviewed DELETE/recreate/append path in a full synthetic DB.

No source database/cache or network is used. Requires the dev test dependencies.
Use --schema with an archived review DDL to reproduce an immutable input.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def probe(sql, kind, referenced):
    import sqlite3

    from tests.integration.test_target_schema import B, H, build_target, put

    db = build_target(sql)
    try:
        tables = db.execute(
            "SELECT count(*) FROM sqlite_schema WHERE type='table'"
        ).fetchone()[0]
        if tables != 74:
            raise ValueError("Probe requires the complete 74-table target DDL")
        db.execute(
            "UPDATE code_listing_progress SET state='complete', terminal=1, "
            "context_proven=1,page_count=1 WHERE listing_id LIKE 'listing-a-%'"
        )
        if referenced:
            put(
                db,
                "code_observations",
                id=1,
                change_request_id="cr-a",
                observation_id=1,
                commit_listing_id="listing-a-commits",
                file_listing_id="listing-a-files",
                state="complete",
                object_format="sha1",
                head_oid=H,
                base_oid=B,
                details="{}",
            )
        listing = "listing-a-" + kind
        error = None
        db.execute("BEGIN")
        try:
            db.execute(
                "DELETE FROM code_listing_progress WHERE listing_id=?", (listing,)
            )
            db.execute(
                "INSERT INTO code_listing_progress VALUES(?,'partial',0,0,0)",
                (listing,),
            )
            values = dict(listing_id=listing, position=99, payload="{}")
            if kind == "commits":
                put(
                    db,
                    "code_commits",
                    **values,
                    occurrence_id=1,
                    object_format="sha1",
                    oid=H,
                )
            else:
                put(
                    db,
                    "code_file_changes",
                    **values,
                    occurrence_id=2,
                    raw_path=b"new.txt",
                )
            db.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            error = str(exc)
            db.execute("ROLLBACK")
        return dict(
            kind=kind,
            referenced=referenced,
            tables=tables,
            attack_committed=error is None,
            error=error,
            progress_state=db.execute(
                "SELECT state FROM code_listing_progress WHERE listing_id=?", (listing,)
            ).fetchone()[0],
            code_states=db.execute("SELECT state FROM code_observations").fetchall(),
            foreign_key_violations=len(
                db.execute("PRAGMA foreign_key_check").fetchall()
            ),
            integrity_check=db.execute("PRAGMA integrity_check").fetchone()[0],
        )
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema",
        type=Path,
        default=ROOT / "docs/schema-hardening/target-schema.sql",
    )
    parser.add_argument("--sqlite-minimum", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    if args.sqlite_minimum:
        sys.path.insert(0, str(ROOT / "artifacts/sqlite-min"))
        import pysqlite3

        assert pysqlite3.sqlite_version == "3.46.1", pysqlite3.sqlite_version
        sys.modules["sqlite3"] = pysqlite3
    import sqlite3

    raw = args.schema.read_bytes()
    if not raw.strip():
        parser.error("Empty DDL cannot identify a complete target schema")
    print(
        json.dumps(
            dict(
                ddl_sha256=hashlib.sha256(raw).hexdigest(),
                sqlite=sqlite3.sqlite_version,
                synthetic_only=True,
                results=[
                    probe(raw.decode("utf-8"), kind, referenced)
                    for kind in ("commits", "files")
                    for referenced in (False, True)
                ],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
