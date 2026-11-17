"""Execute fresh independent-role DDL checks without user data or conversion.

This replaces the retired Catalog3 acceptance probe. It establishes only fresh
DDL construction, declared fingerprints, integrity and physical FK consistency;
behavioral and installed-runtime validation are reported by their actual tests.
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.export_sqlite_databases import definitions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = {}
    for role, (ddl, prepare) in definitions().items():
        db = sqlite3.connect(":memory:")
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA recursive_triggers=ON")
            prepare(db)
            db.executescript(ddl)
            integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
            foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
            result[role] = {
                "status": "passed"
                if integrity == ["ok"] and not foreign_keys
                else "failed",
                "ddl_sha256": hashlib.sha256(ddl.encode()).hexdigest(),
                "integrity_check": integrity,
                "foreign_key_check": foreign_keys,
            }
        finally:
            db.close()
    report = {"scope": "fresh independent-role DDL only", "roles": result}
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 0 if all(item["status"] == "passed" for item in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
