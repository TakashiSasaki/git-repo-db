#!/usr/bin/env python3
"""Characterize existing publication obligations in a fresh disposable catalog.

This is a Schema 18 probe, not a candidate replacement subsystem. It uses no
network, credentials, provider recordings, built-in verification bootstrap or
retained user state. Every invocation requires a new explicit state directory.
"""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
from pathlib import Path

from repo_catalog.adapters.sqlite.json_contracts import JsonContractError
from repo_catalog.adapters.sqlite.parser_model import ParserModel, canonical
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, SCHEMA_VERSION, schema_sql
from repo_catalog.domain.models import CatalogError


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012x}"


def reject(operation, *, contains: str | None = None) -> str:
    try:
        operation()
    except (sqlite3.IntegrityError, CatalogError, JsonContractError) as error:
        if contains is not None:
            assert contains in str(error), (contains, str(error))
        return type(error).__name__
    raise AssertionError("An invalid publication dependency was admitted")


def characterize(state_dir: Path) -> dict:
    # Refuse to open any pre-existing catalog or silently reuse earlier evidence.
    state_dir.mkdir(parents=True, exist_ok=False)
    db = sqlite3.connect(state_dir / "publication.sqlite3", isolation_level=None)
    try:
        db.executescript(schema_sql())
        db.execute(
            "INSERT INTO database_identity VALUES(1,'repo-catalog/catalog3',?,?,?,?,?)",
            (SCHEMA_VERSION, uid(1), 0, DDL_SHA256, "validated"),
        )
        for repo, name in ((uid(2), "one"), (uid(3), "two")):
            db.execute("INSERT INTO repositories VALUES(?,?,NULL,'{}')", (repo, name))
        db.execute(
            "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,request) VALUES(?,?,'git','{}')",
            (uid(4), uid(2)),
        )
        db.execute(
            "INSERT INTO git_acquisition_publications VALUES(?,?,'[]','[]')",
            (uid(4), uid(2)),
        )
        model = ParserModel(db)
        definition = {
            "implementation": {"fixture": "publication-characterization"},
            "settings": {},
            "output_schema": {},
            "capabilities": [
                {"owner_kind": "repository", "fact_kind": "git"},
                {"owner_kind": "repository", "fact_kind": "change-request"},
                {"owner_kind": "source", "fact_kind": "inventory"},
            ],
        }
        profile = model.register_profile(definition, profile_uuid=uid(5))
        verification = model.verify_profile(
            profile,
            verification_uuid=uid(6),
            criteria={"fixture": "synthetic structural probe"},
            evidence={
                "definition": definition,
                "capabilities": [
                    {**capability, "outcome": "passed", "checks": ["synthetic"]}
                    for capability in definition["capabilities"]
                ],
            },
        )
        model.trust_verification(verification)
        model.ensure_scope_profile(profile, repository_uuidv4=uid(2), fact_kind="git")

        def result(number: int) -> str:
            return model.create_result(
                profile,
                repository_uuidv4=uid(2),
                inputs=[{"git_acquisition_id": uid(4)}],
                result_uuid=uid(number),
                parsed_at_us=-1,
            )

        def snapshot(result_id: str, number: int) -> None:
            db.execute(
                "INSERT INTO snapshots(parsed_result_uuidv4,snapshot_id,git_acquisition_id,repository_uuidv4,published,generation,created_at_us) VALUES(?,?,?,?,1,0,0)",
                (result_id, uid(number), uid(4), uid(2)),
            )

        checks = []
        first = result(10)
        missing_manifest = canonical([{"table": "snapshots", "key": [uid(11)]}])
        rejected = reject(
            lambda: db.execute(
                "INSERT INTO parsed_result_publications VALUES(?,1,?,0)",
                (first, missing_manifest),
            ),
            contains="fact manifest",
        )
        checks.append({"check": "missing output cannot seal", "rejection": rejected})
        snapshot(first, 11)
        model.publish_result(first)
        rejected = reject(lambda: snapshot(first, 12), contains="sealed")
        checks.append(
            {"check": "sealed output membership cannot grow", "rejection": rejected}
        )
        assert db.execute("SELECT count(*) FROM current_snapshots").fetchone()[0] == 0
        model.select_fact(
            first, fact_kind="git", decision_uuid=uid(13), decided_at_us=999
        )
        second = result(20)
        snapshot(second, 21)
        model.publish_result(second)
        model.select_fact(
            second,
            fact_kind="git",
            decision_uuid=uid(22),
            predecessors=[],
            decided_at_us=-999,
        )
        assert db.execute("SELECT count(*) FROM current_snapshots").fetchone()[0] == 0
        assert (
            db.execute("SELECT count(*) FROM eligible_git_commits").fetchone()[0] == 0
        )
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 2
        checks.append(
            {
                "check": "two independent selection heads have no current winner",
                "retained_snapshots": 2,
                "current_snapshots": 0,
                "decided_at_us": [999, -999],
            }
        )
        model.select_fact(
            first,
            fact_kind="git",
            predecessors=[uid(13), uid(22)],
            decision_uuid=uid(23),
            decided_at_us=0,
        )
        assert db.execute("SELECT snapshot_id FROM current_snapshots").fetchall() == [
            (uid(11),)
        ]
        checks.append(
            {
                "check": "explicit multi-head resolution changes winner",
                "winner": uid(11),
            }
        )
        scope = db.execute(
            "SELECT fact_selection_scope_uuidv4 FROM fact_selection_decisions WHERE fact_selection_decision_uuidv4=?",
            (uid(23),),
        ).fetchone()[0]

        def decision(number: int, selected: str, predecessor: int, clock: int) -> dict:
            return {
                "fact_selection_decision_uuidv4": uid(number),
                "fact_selection_scope_uuidv4": scope,
                "parsed_result_uuidv4": selected,
                "repository_uuidv4": uid(2),
                "source_registration_uuidv4": None,
                "predecessor_manifest_json": canonical([uid(predecessor)]),
                "issuer": "synthetic-peer",
                "decided_at_us": clock,
            }

        assert model.receive_fact_decision(decision(25, second, 24, -1)) == "staged"
        assert db.execute("SELECT count(*) FROM current_snapshots").fetchone()[0] == 0
        assert model.receive_fact_decision(decision(24, first, 23, 1000)) == "admitted"
        assert (
            db.execute("SELECT count(*) FROM fact_selection_staging").fetchone()[0] == 0
        )
        assert db.execute("SELECT snapshot_id FROM current_snapshots").fetchall() == [
            (uid(21),)
        ]
        checks.append(
            {
                "check": "late predecessor promotes child without receipt-time ordering",
                "winner": uid(21),
            }
        )
        empty = result(30)
        model.publish_result(empty)
        assert (
            db.execute(
                "SELECT fact_manifest_json FROM parsed_result_publications WHERE parsed_result_uuidv4=?",
                (empty,),
            ).fetchone()[0]
            == "[]"
        )
        assert db.execute("SELECT count(*) FROM coverage_claims").fetchone()[0] == 0
        checks.append(
            {
                "check": "empty publication is not complete coverage",
                "coverage_claims": 0,
            }
        )
        rejected = reject(
            lambda: model.create_result(
                profile,
                repository_uuidv4=uid(3),
                inputs=[{"git_acquisition_id": uid(4)}],
                result_uuid=uid(31),
            )
        )
        checks.append(
            {"check": "repository input owner mismatch rejected", "rejection": rejected}
        )
        rejected = reject(
            lambda: model.create_result(
                profile,
                repository_uuidv4=uid(2),
                inputs=[{"fetch_occurrence_uuidv4": uid(32)}],
                result_uuid=uid(33),
            )
        )
        checks.append(
            {
                "check": "historical API result requires actual saved input",
                "rejection": rejected,
            }
        )

        source_id, source_registration = "synthetic-source", uid(40)
        db.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,discovery_kind,name) VALUES(?,?,'manual_git','synthetic')",
            (source_id, source_registration),
        )
        payload = intern_payload(
            db, b'{"synthetic":"source input"}', representation="decoded_api"
        )
        db.execute(
            "INSERT INTO source_input_observations VALUES(?,?,?,?,?,100)",
            (uid(41), source_registration, *payload.parameters(), "{}"),
        )
        source_result = model.create_result(
            profile,
            source_registration_uuidv4=source_registration,
            inputs=[{"source_input_uuidv4": uid(41)}],
            result_uuid=uid(42),
        )

        def source_member() -> None:
            db.execute(
                "INSERT INTO repository_inventory_observations VALUES(?,?,?,?,?,'{}')",
                (
                    uid(43),
                    uid(2),
                    source_result,
                    source_registration,
                    "synthetic-repository",
                ),
            )

        rejected = reject(source_member, contains="membership mismatch")
        checks.append(
            {
                "check": "Source output requires Source/repository membership",
                "rejection": rejected,
            }
        )
        db.execute(
            "INSERT INTO source_repositories VALUES(?,?,100,100)", (source_id, uid(2))
        )
        source_member()
        db.execute(
            "INSERT INTO inventory_observations(inventory_observation_id,source_id,asserted_state,scope,observed_at_us,reason,parsed_result_uuidv4,source_registration_uuidv4) VALUES(?,?,'partial','{}',100,'synthetic partial',?,?)",
            (uid(44), source_id, source_result, source_registration),
        )
        model.publish_result(source_result)
        model.ensure_scope_profile(
            profile,
            source_registration_uuidv4=source_registration,
            fact_kind="inventory",
        )
        model.select_fact(source_result, fact_kind="inventory", decision_uuid=uid(45))
        assert db.execute(
            "SELECT asserted_state FROM current_inventory_observations"
        ).fetchall() == [("partial",)]
        assert (
            db.execute(
                "SELECT count(*) FROM current_repository_inventory_observations"
            ).fetchone()[0]
            == 1
        )
        checks.append(
            {
                "check": "sealed admitted Source publication may remain partial",
                "asserted_state": "partial",
            }
        )

        direct = {}
        for (table,) in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ):
            foreign = [
                list(row)
                for row in db.execute(f'PRAGMA foreign_key_list("{table}")')
                if row[2] == "parsed_results"
            ]
            if foreign:
                direct[table] = foreign
        view = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='parsed_fact_members'"
        ).fetchone()[0]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return {
            "kind": "existing-schema-publication-characterization-v1",
            "schema": SCHEMA_VERSION,
            "ddl_sha256": DDL_SHA256.hex(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "checks": checks,
            "direct_parsed_result_foreign_keys": direct,
            "parsed_fact_members_sql": view,
            "foreign_key_check": [],
            "integrity_check": "ok",
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        required=True,
        help="new disposable directory; existing paths are refused",
    )
    args = parser.parse_args()
    receipt = characterize(args.state_dir)
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    (args.state_dir / "receipt.json").write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
