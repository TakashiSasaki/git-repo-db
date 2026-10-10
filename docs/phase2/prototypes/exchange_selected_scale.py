"""Measure large selected production Exchange closures, without elapsed-time claims.

Every catalog is synthetic and lives under a required new --state-dir. This
exercises the existing Schema 19 Graph/publication/completeness contracts; it
does not propose or implement a new wire format, trust, lifecycle or GC policy.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from repo_catalog.adapters.sqlite import exchange as exchange_module  # noqa: E402
from repo_catalog.adapters.sqlite.cas_integrity import (  # noqa: E402
    register_git_object_sql_function,
    verify_all,
)
from repo_catalog.adapters.sqlite.coverage import freeze_complete_proof  # noqa: E402
from repo_catalog.adapters.sqlite.exchange import Graph  # noqa: E402
from repo_catalog.adapters.sqlite.parser_model import ParserModel  # noqa: E402
from repo_catalog.adapters.sqlite.payloads import intern_payload  # noqa: E402
from repo_catalog.adapters.sqlite.schema import (  # noqa: E402
    DDL_SHA256,
    SCHEMA_VERSION,
    schema_sql,
)
from tests.integration.test_catalog3_exchange import (  # noqa: E402
    complete_collection,
    fixture,
    receive,
    uid,
)


def catalog(path, *, fresh=True):
    if fresh and path.exists():
        raise ValueError("Synthetic catalog must be new")
    db = sqlite3.connect(path, isolation_level=None)
    register_git_object_sql_function(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    if fresh:
        db.executescript(schema_sql())
    return db


def measure(db, call):
    """Count SQL statements and approximate VM work; no wall/CPU timer is used."""
    statements = callbacks = 0

    def trace(_):
        nonlocal statements
        statements += 1

    def progress():
        nonlocal callbacks
        callbacks += 1
        return 0

    db.set_trace_callback(trace)
    db.set_progress_handler(progress, 100)
    try:
        result = call()
    finally:
        db.set_trace_callback(None)
        db.set_progress_handler(None, 0)
    return {"sql_statements": statements, "vm_steps_estimate": callbacks * 100}, result


def unit_counts(unit):
    return dict(sorted(Counter(r["table"] for r in unit["records"]).items()))


def same_records(a, b):
    # Catalog origin is not a domain identity. All record keys/values/proofs are.
    return (
        a["repository_uuidv4"] == b["repository_uuidv4"]
        and a["records"] == b["records"]
    )


def reverse(unit):
    value = copy.deepcopy(unit)
    value["records"].reverse()
    return value


def checks(db):
    foreign = db.execute("PRAGMA foreign_key_check").fetchall()
    integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    assert foreign == [] and integrity == "ok"
    return {"foreign_keys": foreign, "integrity": integrity}


def count(db, table):
    # All callers use fixed schema table names from this script.
    return db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]


def build_history(db, size):
    """One exact domain comment/output per page; N distinct natural members."""
    db.execute("BEGIN")
    try:
        expected = fixture(db, next_cursor="page:1")
        # Registration ownership is portable; local acquisition settings are
        # deliberately not imported as authority. Keep this synthetic Source
        # unconfigured so whole-record convergence compares only portable facts.
        db.execute("UPDATE sources SET settings=NULL")
        collection = db.execute(
            "SELECT fetch_collection_id FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
            (expected["fetch"],),
        ).fetchone()[0]
        fetches, observations = [expected["fetch"]], [expected["observation"]]
        model = ParserModel(db)
        db.execute(
            "INSERT INTO collection_memberships VALUES(?,?,'comment','1',0)",
            (collection, expected["cr"]),
        )
        for ordinal in range(1, size):
            document = str(ordinal + 1)
            body = f"synthetic selected comment {document}"
            raw = json.dumps({"id": document, "body": body}).encode()
            ref = intern_payload(db, raw, representation="decoded_api")
            fetch = uid()
            local = db.execute(
                "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,next_cursor,observed_at_us,parsed_at_us) "
                "VALUES(?,?,?,?,?,?,'{}',?,?,0)",
                (
                    fetch,
                    expected["repository"],
                    collection,
                    ordinal,
                    *ref.parameters(),
                    f"page:{ordinal + 1}" if ordinal + 1 < size else None,
                    ordinal,
                ),
            ).lastrowid
            result = model.create_result(
                expected["profile"],
                repository_uuidv4=expected["repository"],
                inputs=[{"fetch_occurrence_uuidv4": fetch}],
            )
            digest = hashlib.sha256(body.encode()).digest()
            db.execute(
                "INSERT INTO text_bodies(body,byte_length,sha256) VALUES(?,?,?)",
                (body, len(body.encode()), digest),
            )
            db.execute(
                "INSERT INTO documents VALUES(?,'comment',?)",
                (expected["cr"], document),
            )
            observation = uid()
            db.execute(
                "INSERT INTO document_observations(document_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at_us,parsed_at_us,fetch_occurrence_id,metadata) "
                "VALUES(?,?,?,?,'comment',?,?,?,0,?,'{}')",
                (
                    observation,
                    result,
                    expected["repository"],
                    expected["cr"],
                    document,
                    digest,
                    ordinal,
                    local,
                ),
            )
            model.publish_result(result)
            db.execute(
                "INSERT INTO collection_memberships VALUES(?,?,'comment',?,?)",
                (collection, expected["cr"], document, ordinal),
            )
            fetches.append(fetch)
            observations.append(observation)
        complete_collection(db, fetches[-1])
        scope = uid()
        db.execute(
            "INSERT INTO coverage_scopes VALUES(?,?,?,'comment')",
            (scope, expected["repository"], expected["cr"]),
        )
        details = freeze_complete_proof(
            db, size - 1, json.dumps({"fetch_collection_ids": [collection]})
        )
        db.execute(
            "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES(?,'complete',?,?)",
            (scope, size - 1, details),
        )
        db.commit()
    except BaseException:
        db.rollback()
        raise
    for table in (
        "documents",
        "document_observations",
        "collection_memberships",
        "parsed_results",
        "parsed_result_publications",
        "fetch_occurrences",
    ):
        assert count(db, table) == size
    return expected, collection, fetches, observations


def historical_case(directory, size):
    directory.mkdir()
    source = catalog(directory / "source.sqlite3")
    direct = catalog(directory / "reversed.sqlite3")
    late_path = directory / "late.sqlite3"
    late = catalog(late_path)
    try:
        expected, collection, fetches, observations = build_history(source, size)
        owner = expected["repository"]
        full_work, full = measure(source, lambda: Graph(source).export(owner))
        assert unit_counts(full)["collection_memberships"] == size
        assert unit_counts(full)["document_observations"] == size
        assert unit_counts(full)["parsed_result_publications"] == size
        assert unit_counts(full)["fetch_occurrences"] == size
        assert unit_counts(full)["completion_markers"] == 1
        assert unit_counts(full)["coverage_claims"] == 1
        single_work, single = measure(
            source,
            lambda: Graph(source).export(owner, fetch_occurrence_uuidv4s=[fetches[-1]]),
        )
        assert unit_counts(single)["document_observations"] == 1
        assert unit_counts(single)["parsed_result_publications"] == 1
        assert unit_counts(single)["fetch_occurrences"] == 1
        assert (
            not {"completion_markers", "coverage_claims"} & unit_counts(single).keys()
        )
        half_work, half = measure(
            source,
            lambda: Graph(source).export(
                owner, fetch_occurrence_uuidv4s=fetches[: size // 2]
            ),
        )
        assert unit_counts(half)["document_observations"] == size // 2
        assert not {"completion_markers", "coverage_claims"} & unit_counts(half).keys()
        collection_work, collection_unit = measure(
            source, lambda: Graph(source).export(owner, fetch_collection_id=collection)
        )
        assert unit_counts(collection_unit)["document_observations"] == size
        assert unit_counts(collection_unit)["coverage_claims"] == 1
        reversed_work, reversed_outcome = measure(
            direct, lambda: receive(direct, reverse(full))
        )
        assert reversed_outcome["staged_records"] == 0
        repeat_work, repeat_outcome = measure(direct, lambda: receive(direct, full))
        assert repeat_outcome["received_records"] == 0
        assert same_records(full, Graph(direct).export(owner))
        half_receive_work, half_outcome = measure(
            late, lambda: receive(late, reverse(half))
        )
        assert half_outcome["staged_records"] == 0
        assert count(late, "document_observations") == size // 2
        assert count(late, "coverage_claims") == 0
        # Retain an accepted prefix on disk and restart before the missing set.
        late.close()
        late = catalog(late_path, fresh=False)
        missing = copy.deepcopy(full)
        missing["records"] = [
            r
            for r in full["records"]
            if not (
                r["table"] == "fetch_occurrences"
                and r["values"]["fetch_occurrence_uuidv4"] == fetches[-1]
                or r["table"] == "document_observations"
                and r["values"]["document_observation_uuidv4"] == observations[-1]
            )
        ]
        missing_work, missing_outcome = measure(
            late, lambda: receive(late, reverse(missing))
        )
        assert missing_outcome["staged_records"] > 0
        assert count(late, "document_observations") == size - 1
        assert count(late, "coverage_claims") == 0
        late_work, late_outcome = measure(late, lambda: receive(late, full))
        assert late_outcome["staged_records"] == 0
        assert late.execute(
            "SELECT coverage_state,observed_at_us FROM current_coverage"
        ).fetchall() == [("complete", size - 1)]
        assert same_records(full, Graph(late).export(owner))
        assert receive(late, full)["received_records"] == 0
        assert count(late, "local_parser_profile_verification_trust") == 0
        return {
            "selected_pages_and_natural_members": size,
            "full_record_count": len(full["records"]),
            "full_records_by_table": unit_counts(full),
            "single_fetch_records_by_table": unit_counts(single),
            "half_fetch_records_by_table": unit_counts(half),
            "collection_records_by_table": unit_counts(collection_unit),
            "work": {
                "full_export": full_work,
                "single_fetch_export": single_work,
                "half_fetch_export": half_work,
                "collection_export": collection_work,
                "reversed_full_receive": reversed_work,
                "repeated_full_receive": repeat_work,
                "selective_half_receive": half_receive_work,
                "incomplete_full_receive_after_restart": missing_work,
                "late_dependency_promotion": late_work,
            },
            "outcomes": {
                "reversed_full_receive": reversed_outcome,
                "repeated_full_receive": repeat_outcome,
                "selective_half_receive": half_outcome,
                "incomplete_full_receive_after_restart": missing_outcome,
                "late_dependency_promotion": late_outcome,
            },
            "complete_only_after_exact_closure": True,
            "portable_graph_converged": True,
            "accepted_prefix_reopened": True,
            "receiver_local_trust_imported": False,
            "checks": {
                "source": checks(source),
                "full": checks(direct),
                "late": checks(late),
            },
        }
    finally:
        source.close()
        direct.close()
        late.close()


def git_case(directory, size):
    directory.mkdir()
    source = catalog(directory / "source.sqlite3")
    direct = catalog(directory / "reversed.sqlite3")
    late_path = directory / "late.sqlite3"
    late = catalog(late_path)
    try:
        owner = uid()
        source.execute("BEGIN")
        source.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic-selected-git','{}')",
            (owner,),
        )
        for fmt in ("sha1", "sha256"):
            acquisition = uid()
            source.execute(
                "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request) VALUES(?,?,?,'git','{}')",
                (acquisition, owner, fmt),
            )
            for index in range(size // 2):
                body = f"synthetic-selected-git-pair-{index:08d}".encode()
                oid = hashlib.new(fmt, f"blob {len(body)}\0".encode() + body).digest()
                ref = intern_payload(source, body, representation="git-object-raw-v1")
                object_id = source.execute(
                    "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,'blob',?,1) RETURNING git_object_id",
                    (fmt, oid, len(body)),
                ).fetchone()[0]
                source.execute(
                    "INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",
                    (object_id, ref.sha256),
                )
                source.execute(
                    "INSERT INTO repository_object_sources VALUES(?,?,?)",
                    (owner, object_id, acquisition),
                )
        source.commit()
        export_work, full = measure(source, lambda: Graph(source).export(owner))
        assert len(full["records"]) == size * 4 + 3
        reverse_work, reversed_outcome = measure(
            direct, lambda: receive(direct, reverse(full))
        )
        assert reversed_outcome["staged_records"] == 0
        repeat_work, repeated = measure(direct, lambda: receive(direct, full))
        assert repeated["received_records"] == 0
        assert same_records(full, Graph(direct).export(owner))
        body_records = [r for r in full["records"] if r["table"] == "stored_bytes"]
        missing_keys = {r["key"] for r in body_records[::2]}
        partial = dict(
            full, records=[r for r in full["records"] if r["key"] not in missing_keys]
        )
        missing_work, missing_outcome = measure(
            late, lambda: receive(late, reverse(partial))
        )
        assert missing_outcome["staged_records"] > 0
        # Declared Git identity/ownership can exist before its required bytes.
        # The typed raw-object mapping stays staged until the physical body and
        # logical payload are present and actual format/OID/type/size verify.
        assert count(late, "git_objects") == size
        assert count(late, "git_object_payloads") == size - 2 * len(missing_keys)
        late.close()
        late = catalog(late_path, fresh=False)
        bodies = dict(
            full, records=[r for r in body_records if r["key"] in missing_keys]
        )
        late_work, late_outcome = measure(late, lambda: receive(late, reverse(bodies)))
        assert late_outcome["staged_records"] == 0
        assert count(late, "git_objects") == size
        assert count(late, "stored_bytes") == size // 2
        assert count(late, "payloads") == size // 2
        assert late.execute(
            "SELECT object_format,count(*) FROM git_objects GROUP BY object_format ORDER BY object_format"
        ).fetchall() == [("sha1", size // 2), ("sha256", size // 2)]
        raw_objects = late.execute(
            "SELECT o.object_format,o.oid,o.type,o.size,b.body FROM git_objects o "
            "JOIN git_object_payloads p USING(git_object_id) "
            "JOIN stored_bytes b ON b.sha256=p.payload_sha256"
        ).fetchall()
        assert len(raw_objects) == size
        for fmt, oid, kind, declared_size, body in raw_objects:
            assert declared_size == len(body)
            assert (
                hashlib.new(fmt, f"{kind} {len(body)}\0".encode() + body).digest()
                == oid
            )
        assert verify_all(late)["corrupt"] == []
        assert same_records(full, Graph(late).export(owner))
        assert receive(late, full)["received_records"] == 0
        return {
            "selected_verified_git_objects": size,
            "object_formats": {"sha1": size // 2, "sha256": size // 2},
            "shared_physical_bodies": size // 2,
            "full_record_count": len(full["records"]),
            "full_records_by_table": unit_counts(full),
            "missing_body_records": len(missing_keys),
            "independently_recomputed_git_object_identities": len(raw_objects),
            "work": {
                "full_export": export_work,
                "reversed_full_receive": reverse_work,
                "repeated_full_receive": repeat_work,
                "missing_body_receive": missing_work,
                "late_body_promotion_after_restart": late_work,
            },
            "outcomes": {
                "reversed_full_receive": reversed_outcome,
                "repeated_full_receive": repeated,
                "missing_body_receive": missing_outcome,
                "late_body_promotion_after_restart": late_outcome,
            },
            "portable_graph_converged": True,
            "accepted_prefix_reopened": True,
            "checks": {
                "source": checks(source),
                "full": checks(direct),
                "late": checks(late),
            },
        }
    finally:
        source.close()
        direct.close()
        late.close()


def revision():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD", "HEAD^{tree}"], cwd=ROOT, text=True
    ).splitlines()


def binding():
    paths = sorted(
        subprocess.check_output(
            ["git", "ls-files", "src"], cwd=ROOT, text=True
        ).splitlines()
    )
    paths += [
        "tests/integration/test_catalog3_exchange.py",
        "docs/phase2/prototypes/exchange_selected_scale.py",
    ]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--sizes", nargs="+", type=int, default=[64, 256, 1024])
    args = parser.parse_args()
    if args.sizes != sorted(set(args.sizes)) or any(n < 2 or n % 2 for n in args.sizes):
        parser.error("sizes must be unique increasing even counts >= 2")
    if (
        Path(exchange_module.__file__).resolve()
        != ROOT / "src/repo_catalog/adapters/sqlite/exchange.py"
    ):
        raise RuntimeError("Wrong production source checkout")
    if hashlib.sha256(schema_sql().encode()).digest() != DDL_SHA256:
        raise RuntimeError("Composed production schema fingerprint differs")
    args.state_dir.mkdir(parents=True, exist_ok=False)
    before_revision, before_binding = revision(), binding()
    workloads = []
    for size in args.sizes:
        print(f"selected workload size {size}", flush=True)
        workloads.append(
            {
                "size": size,
                "historical": historical_case(
                    args.state_dir / f"historical-{size}", size
                ),
                "git": git_case(args.state_dir / f"git-{size}", size),
            }
        )
    assert revision() == before_revision and binding() == before_binding
    report = {
        "kind": "large-selected-production-exchange-characterization-v1",
        "source_head": before_revision[0],
        "source_tree": before_revision[1],
        "source_sha256": before_binding,
        "schema_version": SCHEMA_VERSION,
        "ddl_sha256": DDL_SHA256.hex(),
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "bootstrap_override": False,
        "workloads": workloads,
        "limits": [
            "Counts characterize the existing Schema 19 implementation, not a proposed normalized wire/trust policy.",
            "Historical fixture publications have distinct natural comment members; synthetic profile verification is receiver-local and is not imported.",
            "Git workload is verified raw blobs, not commits/trees or historical Git interpretation selection.",
            "VM progress callbacks every 100 opcodes are estimates; SQL includes production triggers and savepoints.",
            "Other focused work may execute concurrently; no wall-time, CPU-time or clean timing-comparison claim is made.",
            "CAS corruption/quarantine/repair and CAS-41 backup/restore remain separately verified production tests; this large-closure probe does not repeat them.",
            "No authenticated traffic, retained catalogs, production code edits, owner policy, merge, release or deployment.",
        ],
    }
    path = args.state_dir / "exchange-selected-scale.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(path, flush=True)


if __name__ == "__main__":
    main()
