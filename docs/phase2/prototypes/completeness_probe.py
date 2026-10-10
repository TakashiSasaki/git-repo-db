#!/usr/bin/env python3
"""Disprove incomplete collection proposals with fresh, synthetic SQLite rows.

Run from the checkout: uv run --no-sync python docs/phase2/prototypes/completeness_probe.py
No retained catalog, provider, transport archive or network is accessed. Proposal
rows deliberately use short synthetic keys; portable identity validation is
tested independently in the production suites. This is not a replacement writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import tempfile
from pathlib import Path
from time import perf_counter

from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, SCHEMA_VERSION, schema_sql
from repo_catalog.domain.coverage import derive_coverage_state, latest_claims

REPO = "00000000-0000-4000-8000-000000000301"
SERVICE = "00000000-0000-4000-8000-000000000101"
SOURCE = "00000000-0000-4000-8000-000000000201"
FETCH = "00000000-0000-4000-8000-000000000401"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode("utf8")).digest()


def production_db():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(schema_sql())
    db.execute("INSERT INTO repositories VALUES(?, 'synthetic', NULL, '{}')", (REPO,))
    db.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) "
        "VALUES(?,'github','synthetic','{}')",
        (SERVICE,),
    )
    db.execute(
        "INSERT INTO sources VALUES('source',?,?,'github_inventory','synthetic','{}')",
        (SOURCE, SERVICE),
    )
    db.execute("INSERT INTO source_repositories VALUES('source',?,NULL,NULL)", (REPO,))
    db.execute(
        "INSERT INTO repository_bindings VALUES('binding',?,?,'1','{}',0)",
        (REPO, SERVICE),
    )
    db.execute(
        "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,repository_binding_id,source_id,"
        "request_context,parser_version,profile_version,confidence) "
        "VALUES('scope',?,'binding','source','{}','synthetic','synthetic','proven')",
        (REPO,),
    )
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,source_id,kind,resume_scope_id) "
        "VALUES('collection',?,'source','comments','scope')",
        (REPO,),
    )
    return db


def baseline_checks():
    results = {}
    for label, ordinals, cursors in (
        ("empty_terminal", [0], [None]),
        ("missing_terminal", [0], ["continuation"]),
        ("skipped_ordinal", [0, 2], ["continuation", None]),
        ("terminal_before_final", [0, 1], [None, None]),
    ):
        db = production_db()
        proof = CurrentCollectionProof(db)
        for ordinal, cursor in zip(ordinals, cursors, strict=True):
            proof.page(
                "collection",
                ordinal,
                100 + ordinal,
                cursor,
                [],
                parser_module="synthetic.current",
                parser_version="1",
            )
        actual = proof.evidence("collection") is not None
        assert actual == (label == "empty_terminal"), label
        results[f"current_{label}"] = actual
        if label == "empty_terminal":
            db.execute(
                "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) "
                "VALUES('scope','collection','complete',?,100)",
                (canonical(proof.evidence("collection")),),
            )
            graph = Graph(db)
            marker = graph.rows("completion_markers")[0]
            assert graph.proof_requirements("completion_markers", marker)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        db.close()
    db = production_db()
    proof = CurrentCollectionProof(db)
    proof.page(
        "collection", 0, 100, None, [], parser_module="synthetic", parser_version="1"
    )
    try:
        proof.page(
            "collection",
            0,
            100,
            None,
            [],
            parser_module="synthetic",
            parser_version="1",
        )
    except sqlite3.IntegrityError:
        results["current_duplicate_ordinal_rejected"] = True
    else:
        raise AssertionError("Duplicate ordinal admitted")
    db.close()
    # Report these independently from expected proposal outcomes. On baseline 18
    # they expose an integrity gap; the separate authorized fix must make false.
    for ordinal, cursor, label in (
        (2, None, "historical_skipped_ordinal_proof_accepted"),
        (0, "continuation", "historical_nonterminal_proof_accepted"),
    ):
        db = production_db()
        raw = b"[]"
        digest = hashlib.sha256(raw).digest()
        db.execute("INSERT INTO stored_bytes VALUES(?,?,?)", (digest, raw, len(raw)))
        db.execute("INSERT INTO payloads VALUES('decoded_api',?)", (digest,))
        db.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,"
            "payload_representation,payload_sha256,request,next_cursor,observed_at_us,parsed_at_us) "
            "VALUES(?,?,'collection',?,'decoded_api',?,'{}',?,100,100)",
            (FETCH, REPO, ordinal, digest, cursor),
        )
        db.execute(
            "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) "
            "VALUES('scope','collection','complete',?,100)",
            (canonical({"terminal": True, "fetch_occurrence_uuidv4s": [FETCH]}),),
        )
        graph = Graph(db)
        results[label] = (
            graph.proof_requirements(
                "completion_markers", graph.rows("completion_markers")[0]
            )
            is not None
        )
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        db.close()
    return results


def proposal_db(path=":memory:"):
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript(Path(__file__).with_name("completeness.sql").read_text())
    db.execute("INSERT INTO p2_repositories VALUES('repo')")
    db.execute("INSERT INTO p2_sources VALUES('source')")
    db.execute("INSERT INTO p2_collection_scopes VALUES('scope','repo',NULL,'pr')")
    return db


def collection(db, ident, scope="scope"):
    db.execute(
        "INSERT INTO p2_collection_observations VALUES(?,?,'source')", (ident, scope)
    )


def observation(db, ident, family="pr", *, title="value", status="value", child=False):
    db.execute(
        "INSERT INTO p2_member_observations VALUES(?,'repo',?,?,?, ?,?)",
        (ident, family, ident, status, title, int(child)),
    )


def observation_digest(db, ident):
    row = db.execute(
        "SELECT * FROM p2_member_observations WHERE observation_uuidv4=?", (ident,)
    ).fetchone()
    return sha(dict(row))


def member_records(db, ident, ordinal=None):
    return [
        {**dict(row), "state_sha256": row["state_sha256"].hex()}
        for row in db.execute(
            "SELECT * FROM p2_collection_members WHERE collection_uuidv4=? "
            "AND (? IS NULL OR fragment_ordinal=?) ORDER BY fragment_ordinal,member_ordinal",
            (ident, ordinal, ordinal),
        )
    ]


def fragment(
    db, ident, ordinal, members, *, terminal, observed=100, wrong_digest=False
):
    records = []
    for position, member in enumerate(members):
        resource = db.execute(
            "SELECT * FROM p2_member_observations WHERE observation_uuidv4=?", (member,)
        ).fetchone()
        records.append(
            {
                "collection_uuidv4": ident,
                "fragment_ordinal": ordinal,
                "member_ordinal": position,
                "observation_uuidv4": member,
                "repository_uuidv4": resource["repository_uuidv4"],
                "family": resource["family"],
                "resource_key": resource["resource_key"],
                "state_sha256": observation_digest(db, member).hex(),
            }
        )
    db.execute(
        "INSERT INTO p2_collection_fragments VALUES(?,?,?,?,?,'synthetic.domain','1')",
        (
            ident,
            ordinal,
            observed,
            int(terminal),
            bytes(32) if wrong_digest else sha(records),
        ),
    )
    for record in records:
        db.execute(
            "INSERT INTO p2_collection_members VALUES(?,?,?,?,?,?,?,?)",
            (*list(record.values())[:-1], bytes.fromhex(record["state_sha256"])),
        )


def seal(db, ident):
    final, observed = db.execute(
        "SELECT max(ordinal),max(observed_at_us) FROM p2_collection_fragments WHERE collection_uuidv4=?",
        (ident,),
    ).fetchone()
    db.execute(
        "INSERT INTO p2_collection_terminals VALUES(?,?,?,?,?)",
        (ident + "-terminal", ident, final, observed, sha(member_records(db, ident))),
    )


def valid_collection(db, root):
    """One indexed enumeration per reached collection; no repository-wide scan.

    Hashes cover modeled members and observations, never an HTTP message. This
    tests structural/verifiable closure; it cannot authenticate provider truth.
    """
    pending, visited = [root], set()
    while pending:
        ident = pending.pop()
        if ident in visited:
            return False
        visited.add(ident)
        terminal = db.execute(
            "SELECT * FROM p2_collection_terminals WHERE collection_uuidv4=?", (ident,)
        ).fetchone()
        pages = db.execute(
            "SELECT * FROM p2_collection_fragments WHERE collection_uuidv4=? ORDER BY ordinal",
            (ident,),
        ).fetchall()
        if not terminal or not pages:
            return False
        if [row["ordinal"] for row in pages] != list(range(len(pages))):
            return False
        if [row["is_terminal"] for row in pages] != [0] * (len(pages) - 1) + [1]:
            return False
        if terminal["final_ordinal"] != pages[-1]["ordinal"] or terminal[
            "observed_at_us"
        ] != max(row["observed_at_us"] for row in pages):
            return False
        records = member_records(db, ident)
        if terminal["members_sha256"] != sha(records):
            return False
        by_page = {}
        for record in records:
            by_page.setdefault(record["fragment_ordinal"], []).append(record)
            if (
                record["state_sha256"]
                != observation_digest(db, record["observation_uuidv4"]).hex()
            ):
                return False
        for page in pages:
            members = by_page.get(page["ordinal"], [])
            if [member["member_ordinal"] for member in members] != list(
                range(len(members))
            ):
                return False
            if page["members_sha256"] != sha(members):
                return False
        expected = {
            (row["fragment_ordinal"], row["member_ordinal"])
            for row in db.execute(
                "SELECT m.fragment_ordinal,m.member_ordinal FROM p2_collection_members m "
                "JOIN p2_member_observations o USING(observation_uuidv4) "
                "WHERE m.collection_uuidv4=? AND o.requires_child=1",
                (ident,),
            )
        }
        children = db.execute(
            "SELECT * FROM p2_child_obligations WHERE parent_collection_uuidv4=?",
            (ident,),
        ).fetchall()
        actual = {
            (row["parent_fragment_ordinal"], row["parent_member_ordinal"])
            for row in children
        }
        if actual != expected:
            return False
        pending.extend(row["child_collection_uuidv4"] for row in children)
    return True


def proposal_checks():
    results = {}
    for label, ordinals, terminals, good_digest, expected in (
        ("empty", [0], [True], True, True),
        ("missing_terminal", [0], [False], True, False),
        ("skipped_ordinal", [0, 2], [False, True], True, False),
        ("terminal_before_final", [0, 1], [True, True], True, False),
        ("inconsistent_member_digest", [0], [True], False, False),
    ):
        db = proposal_db()
        collection(db, "list")
        observation(db, "pr")
        for ordinal, terminal in zip(ordinals, terminals, strict=True):
            fragment(
                db,
                "list",
                ordinal,
                [] if label == "empty" else ["pr"],
                terminal=terminal,
                wrong_digest=not good_digest,
            )
        seal(db, "list")
        actual = valid_collection(db, "list")
        assert actual == expected, label
        results[label] = actual
        db.close()
    db = proposal_db()
    collection(db, "root")
    observation(db, "thread", family="thread", child=True)
    fragment(db, "root", 0, ["thread"], terminal=True)
    seal(db, "root")
    results["partial_nested_missing_child"] = valid_collection(db, "root")
    assert not results["partial_nested_missing_child"]
    collection(db, "child")
    db.execute("INSERT INTO p2_child_obligations VALUES('root',0,0,'child')")
    fragment(db, "child", 0, [], terminal=True)
    seal(db, "child")
    assert valid_collection(db, "root")
    results["nested_empty_child_complete"] = True
    # Selective receipt: copying only one of two members cannot satisfy digest.
    collection(db, "partial")
    observation(db, "a")
    observation(db, "b")
    fragment(db, "partial", 0, ["a", "b"], terminal=True)
    seal(db, "partial")
    db.execute(
        "DELETE FROM p2_collection_members WHERE collection_uuidv4='partial' AND member_ordinal=1"
    )
    assert not valid_collection(db, "partial")
    results["selective_member_subset_complete"] = False
    # Late arrival restores the exact required tuple; no new terminal is invented.
    db.execute(
        "INSERT INTO p2_collection_members VALUES('partial',0,1,'b','repo','pr','b',?)",
        (observation_digest(db, "b"),),
    )
    assert valid_collection(db, "partial")
    results["late_exact_member_completes"] = True
    # Close and reopen an actual disposable database after a committed prefix.
    with tempfile.TemporaryDirectory(prefix="phase2-completeness-") as directory:
        path = Path(directory) / "synthetic.db"
        restarted = proposal_db(path)
        collection(restarted, "restart")
        observation(restarted, "a")
        observation(restarted, "b")
        fragment(restarted, "restart", 0, ["a"], terminal=False)
        restarted.close()
        restarted = sqlite3.connect(path, isolation_level=None)
        restarted.row_factory = sqlite3.Row
        restarted.execute("PRAGMA foreign_keys=ON")
        restarted.execute("PRAGMA recursive_triggers=ON")
        assert not valid_collection(restarted, "restart")
        fragment(restarted, "restart", 1, ["b"], terminal=True, observed=175)
        seal(restarted, "restart")
        assert valid_collection(restarted, "restart")
        restarted.close()
    results["committed_prefix_restart"] = True
    # Only status differs: neither surrogate nor resource identity explains hash.
    observation(db, "same-identity", title=None, status="missing")
    missing_digest = observation_digest(db, "same-identity")
    db.execute(
        "UPDATE p2_member_observations SET title_status='null' WHERE observation_uuidv4='same-identity'"
    )
    assert missing_digest != observation_digest(db, "same-identity")
    results["missing_null_distinct"] = True
    db.execute("INSERT INTO p2_repositories VALUES('foreign')")
    db.execute("INSERT INTO p2_collection_scopes VALUES('foreign','foreign',NULL,'pr')")
    collection(db, "foreign", "foreign")
    db.execute(
        "INSERT INTO p2_collection_fragments VALUES('foreign',0,100,1,?,'synthetic','1')",
        (sha([]),),
    )
    try:
        db.execute(
            "INSERT INTO p2_collection_members VALUES('foreign',0,0,'a','repo','pr','a',?)",
            (observation_digest(db, "a"),),
        )
    except sqlite3.IntegrityError:
        results["repository_mismatch_rejected"] = True
    else:
        raise AssertionError("Wrong repository member admitted")
    try:
        db.execute(
            "INSERT INTO p2_collection_observations VALUES('bad','scope','absent-source')"
        )
    except sqlite3.IntegrityError:
        results["missing_source_rejected"] = True
    else:
        raise AssertionError("Missing captured Source admitted")
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()
    return results


def coverage_checks():
    results = {}
    for label, states, expected in (
        (
            "newer_partial_older_complete",
            [(100, "complete"), (200, "partial")],
            "partial",
        ),
        ("equal_time_contradiction", [(100, "complete"), (100, "partial")], "conflict"),
        (
            "stale_terminal_retry",
            [(100, "complete"), (200, "partial"), (175, "complete")],
            "partial",
        ),
    ):
        selected = latest_claims(
            {
                "coverage_scope_id": "scope",
                "observed_at_us": stamp,
                "coverage_state": state,
            }
            for stamp, state in states
        )
        result = derive_coverage_state(row["coverage_state"] for row in selected)
        assert result == expected
        results[label] = result
    return results


def scale_check(count):
    db = proposal_db()
    collection(db, "root")
    threads = []
    db.execute("BEGIN")
    for ordinal in range(count):
        ident = f"thread-{ordinal}"
        threads.append(ident)
        observation(db, ident, family="thread", child=True)
        collection(db, ident)
        fragment(db, ident, 0, [], terminal=True)
        seal(db, ident)
    fragment(db, "root", 0, threads, terminal=True)
    seal(db, "root")
    for ordinal, ident in enumerate(threads):
        db.execute(
            "INSERT INTO p2_child_obligations VALUES('root',0,?,?)", (ordinal, ident)
        )
    db.commit()
    statements = []
    db.set_trace_callback(statements.append)
    started = perf_counter()
    assert valid_collection(db, "root")
    elapsed = perf_counter() - started
    db.set_trace_callback(None)
    plan = [
        tuple(row)
        for row in db.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM p2_collection_members WHERE collection_uuidv4=? ORDER BY fragment_ordinal,member_ordinal",
            ("root",),
        )
    ]
    rows = {
        row[0]: db.execute(f'SELECT count(*) FROM "{row[0]}"').fetchone()[0]
        for row in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        ).fetchall()
    }
    report = {
        "threads": count,
        "verification_seconds": round(elapsed, 6),
        "verification_sql_statements": len(statements),
        "rows": rows,
        "member_query_plan": plan,
        "sqlite_pages": db.execute("PRAGMA page_count").fetchone()[0],
        "sqlite_page_size": db.execute("PRAGMA page_size").fetchone()[0],
        "measurement_kind": "single-process characterization; not a clean comparative benchmark",
    }
    db.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=10_000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expect-hardened", action="store_true")
    arguments = parser.parse_args()
    if arguments.threads < 1:
        parser.error("--threads must be positive")
    baseline = baseline_checks()
    if arguments.expect_hardened:
        assert not baseline["historical_skipped_ordinal_proof_accepted"]
        assert not baseline["historical_nonterminal_proof_accepted"]
    report = {
        "status": "proposal characterization; no production redesign implemented",
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "production_schema": SCHEMA_VERSION,
        "production_ddl_sha256": DDL_SHA256.hex(),
        "baseline": baseline,
        "proposal": proposal_checks(),
        "accepted_coverage": coverage_checks(),
        "scale": scale_check(arguments.threads),
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
