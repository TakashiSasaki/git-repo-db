"""Reproduce accepted-contract attacks against illustrative candidate DDL.

All catalogs are synthetic and in memory. Results record actual SQL behavior;
they are not a claim that SQL alone implements the candidate's admission rules.
This reviewer probe deliberately operates below an application validator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def catalog(ddl):
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.create_function("sha256", 1, lambda body: hashlib.sha256(body).digest())
    db.create_function(
        "valid_utf8", 1, lambda body: int(body.decode("utf-8") is not None)
    )
    db.create_function("valid_git", 5, valid_git)
    db.executescript(ddl)
    return db


def valid_git(algorithm, oid, kind, size, raw):
    if algorithm not in ("sha1", "sha256") or not isinstance(raw, bytes):
        return 0
    header = f"{kind} {len(raw)}\0".encode("ascii")
    return int(
        size == len(raw) and hashlib.new(algorithm, header + raw).digest() == oid
    )


def owners(db):
    db.execute("INSERT INTO service_instances VALUES('service','github')")
    db.execute("INSERT INTO repositories VALUES('repo')")
    db.execute("INSERT INTO repositories VALUES('other-repo')")
    db.execute("INSERT INTO sources VALUES('source','service')")
    db.execute("INSERT INTO source_repositories VALUES('source','repo')")
    db.execute("INSERT INTO repository_bindings VALUES('binding','repo','service','1')")


def rejected(operation):
    try:
        operation()
    except sqlite3.IntegrityError:
        return True
    return False


def probe(ddl):
    result = {}
    with catalog(ddl) as db:
        owners(db)
        result["coverage_claim_columns"] = [
            row[1] for row in db.execute("PRAGMA table_info(coverage_claims)")
        ]
        result["coverage_contract_preserved"] = set(
            result["coverage_claim_columns"]
        ) == {
            "coverage_claim_id",
            "coverage_scope_id",
            "coverage_state",
            "observed_at_us",
            "details_json",
        }
        db.execute(
            "INSERT INTO coverage_scopes VALUES('scope','repo',NULL,'git','synthetic')"
        )
        empty = db.execute(
            "SELECT observed_at_us,coverage_state FROM current_coverage WHERE coverage_scope_id='scope'"
        ).fetchall()
        result["empty_scope_state"] = empty
        db.execute(
            "INSERT INTO coverage_claims(coverage_scope_id,observed_at_us,coverage_state) VALUES('scope',0,'unknown')"
        )
        db.execute(
            "INSERT INTO coverage_claims(coverage_scope_id,observed_at_us,coverage_state) VALUES('scope',0,'complete')"
        )
        result["unknown_plus_complete_state"] = db.execute(
            "SELECT coverage_state FROM current_coverage WHERE coverage_scope_id='scope'"
        ).fetchone()[0]
        result["duplicate_provider_binding_rejected"] = rejected(
            lambda: db.execute(
                "INSERT INTO repository_bindings VALUES('other-binding','other-repo','service','1')"
            )
        )
        db.execute(
            "INSERT INTO change_requests VALUES('pr','repo','binding','service',1,'pull_request')"
        )
        result["duplicate_pr_natural_identity_rejected"] = rejected(
            lambda: db.execute(
                "INSERT INTO change_requests VALUES('other-pr','repo','binding','service',1,'pull_request')"
            )
        )
        db.execute(
            "INSERT INTO issue_resources(service_uuid,provider_issue_id,kind,repository_uuid,"
            "field_evidence_json,captured_source_uuid,captured_repository_uuid) "
            "VALUES('service','1','issue','repo','{}','source','repo')"
        )
        result["same_numeric_issue_comment_identity_admitted"] = not rejected(
            lambda: db.execute(
                "INSERT INTO issue_resources(service_uuid,provider_issue_id,kind,repository_uuid,"
                "provider_parent_issue_id,field_evidence_json,captured_source_uuid,captured_repository_uuid) "
                "VALUES('service','1','issue-comment','repo','1','{}','source','repo')"
            )
        )
        result["null_repository_identity_rejected"] = rejected(
            lambda: db.execute("INSERT INTO repositories VALUES(NULL)")
        )
        result["nonnumeric_epoch_rejected"] = rejected(
            lambda: db.execute(
                "INSERT INTO identity_relations VALUES('r','repo','other-repo','synthetic','unknown-clock')"
            )
        )
        result["sourceless_publication_unknown_repository_rejected"] = rejected(
            lambda: db.execute(
                "INSERT INTO repository_publications VALUES('missing-owner','absent-repo',NULL,0,'synthetic','1')"
            )
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

    with catalog(ddl) as db:
        owners(db)
        db.execute(
            "INSERT INTO repository_publications VALUES('pub','repo','source',0,'synthetic','1')"
        )
        db.execute(
            "INSERT INTO git_acquisitions(acquisition_uuid,repository_uuid,source_uuid,observed_at_us) "
            "VALUES('acq','repo','source',0)"
        )
        db.execute(
            "INSERT INTO git_interpretations VALUES('interpretation','acq','repo','pub','synthetic','1')"
        )
        raw = b"160000 submodule\0" + bytes([1]) * 20
        digest = hashlib.sha256(raw).digest()
        oid = hashlib.sha1(f"tree {len(raw)}\0".encode() + raw).digest()
        db.execute("INSERT INTO domain_bytes VALUES(?,?,?)", (digest, raw, len(raw)))
        db.execute(
            "INSERT INTO git_objects VALUES('sha1',?,'tree',?,?)",
            (oid, len(raw), digest),
        )
        result["gitlink_missing_target_admitted"] = not rejected(
            lambda: db.execute(
                "INSERT INTO tree_entries(interpretation_uuid,object_format,tree_oid,raw_name,mode,child_oid) "
                "VALUES('interpretation','sha1',?,?,57344,?)",
                (oid, b"submodule", bytes([1]) * 20),
            )
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ddl", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    ddl = args.ddl.read_text()
    report = {
        "kind": "independent-candidate-sql-contract-attacks-v1",
        "ddl_sha256": hashlib.sha256(ddl.encode()).hexdigest(),
        "sqlite": sqlite3.sqlite_version,
        "actual_sql_results": probe(ddl),
        "limits": [
            "SQL-only attacks; application validator may reject additional rows.",
            "Candidate DDL remains illustrative and unapproved.",
        ],
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
