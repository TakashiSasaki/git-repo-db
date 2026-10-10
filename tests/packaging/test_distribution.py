import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite.schema import SCHEMA_VERSION
from tests.support.git_fixture import GitFixture
from tests.support.github_fixture import GitHubFixture

ROOT = Path(__file__).resolve().parents[2]


def checked(args, *, cwd, env=None, accepted_codes=(0,)):
    p = subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if p.returncode not in accepted_codes:
        pytest.fail(
            f"Command failed: {args}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}",
            pytrace=False,
        )
    return p.stdout


@pytest.fixture(scope="module")
def distributions(tmp_path_factory):
    work = tmp_path_factory.mktemp("distributions")
    env = {
        **os.environ,
        "UV_PYTHON": sys.executable,
        "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", "/workspace/.cache/uv"),
    }
    # The installed CLI and its guarded worker must resolve the distribution,
    # even when the outer test runner uses a checkout PYTHONPATH.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("REPO_CATALOG_TEST_BOOTSTRAP", None)
    wheelhouse = Path(
        os.environ.get("REPO_CATALOG_WHEELHOUSE", ROOT / "artifacts/wheelhouse")
    ).resolve()
    assert (wheelhouse / "manifest.json").is_file(), (
        "Run scripts/prepare_wheelhouse.py before offline tests"
    )
    env["REPO_CATALOG_WHEELHOUSE"] = str(wheelhouse)
    offline_sources = ["--offline", "--no-index", "--find-links", str(wheelhouse)]
    checked(
        ["uv", "build", *offline_sources, "--out-dir", work / "dist"], cwd=ROOT, env=env
    )
    checked(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            work / "requirements.txt",
        ],
        cwd=ROOT,
        env=env,
    )
    sdist = next((work / "dist").glob("*.tar.gz"))
    import tarfile

    with tarfile.open(sdist) as archive:
        archive.extractall(work / "sdist", filter="data")
    source = next((work / "sdist").iterdir())
    checked(
        ["uv", "build", *offline_sources, "--wheel", "--out-dir", work / "sdist-wheel"],
        cwd=source,
        env=env,
    )
    return (
        work,
        env,
        [
            next((work / "dist").glob("*.whl")),
            next((work / "sdist-wheel").glob("*.whl")),
        ],
    )


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
def test_wheel_sdist_cli(distributions, tmp_path, variant):
    work, env, wheels = distributions
    venv = tmp_path / "venv"
    outside = tmp_path / "outside"
    outside.mkdir()
    checked(
        ["uv", "venv", venv, "--python", sys.executable, "--offline"],
        cwd=outside,
        env=env,
    )
    checked(
        [
            "uv",
            "pip",
            "install",
            "--offline",
            "--no-index",
            "--find-links",
            env["REPO_CATALOG_WHEELHOUSE"],
            "--python",
            venv / "bin/python",
            "--constraint",
            work / "requirements.txt",
            wheels[variant],
        ],
        cwd=outside,
        env=env,
    )
    origin = checked(
        [
            venv / "bin/python",
            "-c",
            "import repo_catalog; print(repo_catalog.__file__)",
        ],
        cwd=outside,
        env=env,
    ).strip()
    assert origin.startswith(str(venv)) and not origin.startswith(str(ROOT))
    resources = json.loads(
        checked(
            [
                venv / "bin/python",
                "-c",
                "import json; from importlib.resources import files; "
                "root=files('repo_catalog').joinpath('resources'); "
                "import repo_catalog.adapters.sqlite.parser_model; "
                "print(json.dumps({'schema': root.joinpath('catalog3.sql').is_file(), "
                "'git_facts': root.joinpath('git_facts.sql').is_file(), "
                "'current_resources': root.joinpath('current_resources.sql').is_file(), "
                "'current_collections': root.joinpath('current_collections.sql').is_file(), "
                "'json_contracts': root.joinpath('json_contracts.sql').is_file(), "
                "'cas': root.joinpath('cas_integrity.sql').is_file(), 'exchange': root.joinpath('exchange.sql').is_file(), 'verification': root.joinpath('builtin_parser_verification.json').is_file()}))",
            ],
            cwd=outside,
            env=env,
        )
    )
    assert resources == {
        "schema": True,
        "git_facts": True,
        "current_resources": True,
        "current_collections": True,
        "json_contracts": True,
        "cas": True,
        "exchange": True,
        "verification": True,
    }
    fixture = GitFixture(tmp_path / "remotes")
    state = tmp_path / "state"

    def cli(*args, credentials=None, allow_partial=False):
        return json.loads(
            checked(
                [
                    venv / "bin/repo-catalog",
                    "--state-dir",
                    state,
                    "--format",
                    "json",
                    *args,
                ],
                cwd=outside,
                env={**env, **(credentials or {})},
                accepted_codes=(0, 3) if allow_partial else (0,),
            )
        )

    def current_reads(stage):
        """Installed ordinary reads require only guaranteed catalog data."""
        assert not (state / "transport-archive").exists()
        issues = cli("issue", "list", "--repo", repository)["data"]["items"]
        assert {(row["provider_issue_number"], row["state"]) for row in issues} == {
            (1, "open"),
            (2, "closed"),
        }
        shown = cli(
            "issue", "show", "--repo", repository, "--provider-issue-number", "1"
        )["data"]["items"]
        assert len(shown) == 1 and shown[0]["body"] == f"ordinary-issue-body {stage}"
        comments = cli(
            "issue", "comments", "--repo", repository, "--provider-issue-number", "1"
        )["data"]["items"]
        assert len(comments) == 1
        assert comments[0]["body"] == f"ordinary-issue-comment {stage} 1"
        issue_matches = cli(
            "search",
            "issue",
            "--repo",
            repository,
            "--literal",
            f"ordinary-issue-comment {stage}",
        )["data"]["items"]
        assert len(issue_matches) == 2
        assert {row["resource_kind"] for row in issue_matches} == {"issue-comment"}
        reviews = cli(
            "pr",
            "documents",
            "--repo",
            repository,
            "--provider-change-request-number",
            "41",
            "--document-observations",
            "all",
            "--document-kind",
            "review-comment",
        )["data"]["items"]
        assert len(reviews) == 1
        assert reviews[0]["body"] == f"review-comment-marker {stage}"
        assert reviews[0]["resource_lifecycle"] == "current"
        assert reviews[0]["document_observation_id"] is None
        review_matches = cli(
            "search",
            "pr",
            "--repo",
            repository,
            "--document-observations",
            "all",
            "--document-kind",
            "review-comment",
            "--literal",
            f"review-comment-marker {stage}",
        )["data"]["items"]
        assert len(review_matches) == 3
        assert all(row["resource_lifecycle"] == "current" for row in review_matches)
        if stage == "B":
            assert (
                cli(
                    "search",
                    "issue",
                    "--repo",
                    repository,
                    "--literal",
                    "ordinary-issue-comment A",
                )["data"]["items"]
                == []
            )
            assert (
                cli(
                    "search",
                    "pr",
                    "--repo",
                    repository,
                    "--document-observations",
                    "all",
                    "--document-kind",
                    "review-comment",
                    "--literal",
                    "review-comment-marker A",
                )["data"]["items"]
                == []
            )
        return issues, shown, comments, issue_matches, reviews, review_matches

    cli(
        "init",
        "--profile",
        "catalog-text-v1",
        "--cache-max-bytes",
        "33554432",
        "--min-free-bytes",
        "0",
    )
    with sqlite3.connect(state / "catalog.sqlite3") as connection:
        assert connection.execute(
            "SELECT format_id,schema_version,lifecycle FROM database_identity"
        ).fetchone() == ("repo-catalog/catalog3", SCHEMA_VERSION, "validated")
        assert not connection.execute(
            "SELECT name FROM sqlite_schema WHERE name='schema_migrations'"
        ).fetchall()
    source = cli(
        "sources",
        "add",
        "local-git",
        "--name",
        "fixture/alpha",
        "--url",
        fixture.alpha.url,
    )["data"]["source_id"]
    repository = cli("discover", "--source", source)["data"]["repositories"][0][
        "repository_uuidv4"
    ]
    cli("sync", "git")
    assert cli("search", "code", "--literal", "認証")["data"]["items"]
    assert cli("index", "rebuild")["data"]["generations"]
    assert cli("db", "check")["data"]["checks"]["sqlite"] == ["ok"]
    data = json.loads(
        checked(
            [
                venv / "bin/python",
                "-m",
                "repo_catalog",
                "--state-dir",
                state,
                "--format",
                "json",
                "repos",
                "list",
            ],
            cwd=outside,
            env=env,
        )
    )
    assert len(data["data"]["items"]) == 1

    # Reparse the installed Git reader from retained bytes, preserving the
    # acquisition identity and the explicitly selected interpretation.
    git_tables = (
        "commits",
        "commit_parents",
        "tree_entries",
        "root_manifests",
        "root_manifest_entries",
        "git_text_facts",
    )
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        acquisition = db.execute(
            "SELECT git_acquisition_id FROM git_acquisitions"
        ).fetchone()[0]
        before_acquisitions = db.execute("SELECT * FROM git_acquisitions").fetchall()
        selected_commits = db.execute(
            "SELECT git_fact_uuidv4 FROM current_git_commits ORDER BY git_fact_uuidv4"
        ).fetchall()
        for table in git_tables:
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > 0
            assert (
                db.execute(
                    f"SELECT count(*) FROM {table} f JOIN parsed_results r "
                    "USING(parsed_result_uuidv4,repository_uuidv4)"
                ).fetchone()[0]
                == db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            )
        assert db.execute("SELECT count(*) FROM git_object_payloads").fetchone()[0] > 0
        assert {r[1] for r in db.execute("PRAGMA table_info(contents)")} == {
            "content_id",
            "byte_length",
            "created_at_us",
        }
    reparsed = cli("parser", "reparse", acquisition)["data"]["result"][
        "parsed_result_uuidv4"
    ]
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert (
            db.execute("SELECT * FROM git_acquisitions").fetchall()
            == before_acquisitions
        )
        assert (
            db.execute(
                "SELECT git_fact_uuidv4 FROM current_git_commits ORDER BY git_fact_uuidv4"
            ).fetchall()
            == selected_commits
        )
        assert (
            db.execute(
                "SELECT count(*) FROM commits WHERE parsed_result_uuidv4=?", (reparsed,)
            ).fetchone()[0]
            > 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM parsed_result_publications WHERE parsed_result_uuidv4=?",
                (reparsed,),
            ).fetchone()[0]
            == 1
        )
    assert cli("index", "rebuild")["data"]["generations"]
    assert cli("search", "code", "--literal", "認証")["data"]["items"]

    # Real localhost HTTP provides fetch/collection selectors without any live
    # credentials or acquisition. The existing repository is attached explicitly.
    with GitHubFixture(fixture) as api:
        instance = cli(
            "instances",
            "add",
            "github",
            "--name",
            "packaged-http",
            "--web-base-url",
            api.url,
            "--api-base-url",
            api.url,
        )["data"]["service_instance_uuidv4"]
        cli(
            "repos",
            "bind",
            "--repo",
            repository,
            "--instance",
            instance,
            "--provider-repo-id",
            "101",
        )
        github_source = cli(
            "sources",
            "add",
            "github",
            "--owner",
            "fixture",
            "--instance",
            instance,
            "--clone-url-override",
            "101=" + fixture.alpha.url,
            "--include-repo",
            "alpha",
        )["data"]["source_id"]
        credentials = {"GH_TOKEN": "fixture-dummy"}
        cli("discover", "--source", github_source, credentials=credentials)
        cli("sync", "all", "--repo", repository, credentials=credentials)
        current_reads("A")
        cli("index", "rebuild", "--kind", "issue")
        cli("index", "rebuild", "--kind", "pr")
        api.stage = "B"
        cli("sync", "all", "--repo", repository, credentials=credentials)
        expected_current_reads = current_reads("B")
        # The edited body must remain current before and after rebuilding FTS.
        cli("index", "rebuild", "--kind", "issue")
        cli("index", "rebuild", "--kind", "pr")
        assert current_reads("B") == expected_current_reads
        assert not api.errors

    # Installed core reparse rejects HTTP input without reading the original or
    # changing any domain row. This holds for wheel and sdist installations.
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        fetch = db.execute(
            "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences LIMIT 1"
        ).fetchone()[0]
        before_replay = list(db.iterdump())
    rejected = json.loads(
        checked(
            [
                venv / "bin/repo-catalog",
                "--state-dir",
                state,
                "--format",
                "json",
                "parser",
                "reparse",
                fetch,
                "--select",
            ],
            cwd=outside,
            env=env,
            accepted_codes=(5,),
        )
    )
    assert rejected["error"]["code"] == "PARSER_UNSUPPORTED_INPUT"
    assert "API response replay is retired" in rejected["error"]["message"]
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert list(db.iterdump()) == before_replay

    # The registry and its schema-discovered completeness gate must resolve
    # from each installed distribution, outside the source checkout.
    inventory = json.loads(
        checked(
            [
                venv / "bin/python",
                "-c",
                "import json,sqlite3,sys; from importlib.resources import files; "
                "from repo_catalog.adapters.sqlite.json_contracts import inventory,guard_sql,validate_catalog; "
                "assert files('repo_catalog').joinpath('resources/json_contracts.sql').read_text()==guard_sql(); "
                "db=sqlite3.connect(sys.argv[1]); validate_catalog(db); print(json.dumps(inventory(db)))",
                state / "catalog.sqlite3",
            ],
            cwd=outside,
            env=env,
        )
    )
    assert {r["category"] for r in inventory} >= {"authored", "provider", "operational"}
    assert any(
        r["table"] == "parsed_results" and r["column"] == "derivation_json"
        for r in inventory
    )

    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert not db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name IN ('reviews','review_comments')"
        ).fetchall()
        assert db.execute(
            "SELECT count(*) FROM documents WHERE kind IN ('review','review-comment')"
        ).fetchone() == (0,)
        assert db.execute(
            "SELECT count(*) FROM document_observations WHERE kind IN ('review','review-comment')"
        ).fetchone() == (0,)
        assert db.execute(
            "SELECT kind,count(*) FROM issue_resources GROUP BY kind ORDER BY kind"
        ).fetchall() == [("issue", 2), ("issue-comment", 2)]
        assert db.execute(
            "SELECT kind,count(*) FROM review_resources GROUP BY kind ORDER BY kind"
        ).fetchall() == [("review", 3), ("review-comment", 3)]
        assert db.execute(
            "SELECT count(*) FROM fetch_occurrences o JOIN fetch_collections c "
            "USING(fetch_collection_id) WHERE c.kind IN "
            "('issue','ordinary-issue-comment','review','review-comment')"
        ).fetchone() == (0,)
        for table in (
            "issue_resources",
            "review_resources",
            "current_collection_pages",
        ):
            assert "parser_profile_uuidv4" not in {
                row[1] for row in db.execute(f"PRAGMA table_info({table})")
            }
            assert db.execute(
                f"SELECT DISTINCT parser_module,parser_version FROM {table}"
            ).fetchall() == [("repo_catalog.adapters.github.current_parser", "1")]
        for (encoded,) in db.execute("SELECT field_evidence_json FROM issue_resources"):
            assert all(
                evidence["parser_module"]
                == "repo_catalog.adapters.github.current_parser"
                and evidence["parser_version"] == "1"
                and "parser_profile_uuidv4" not in evidence
                for evidence in json.loads(encoded).values()
            )
        current_collection = db.execute(
            "SELECT c.fetch_collection_id FROM fetch_collections c "
            "JOIN current_collection_pages p USING(fetch_collection_id) "
            "WHERE c.kind='ordinary-issue-comment' "
            "ORDER BY p.observed_at_us DESC LIMIT 1"
        ).fetchone()[0]
        selected_fetch, collection = db.execute(
            "SELECT o.fetch_occurrence_uuidv4,o.fetch_collection_id "
            "FROM fetch_occurrences o JOIN fetch_collections c USING(fetch_collection_id) "
            "WHERE c.kind='issue-comment' ORDER BY o.ordinal LIMIT 1"
        ).fetchone()
        expected_collection = {
            r[0]
            for r in db.execute(
                "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences WHERE fetch_collection_id=?",
                (collection,),
            )
        }

        # Acquired pages belong to sealed multi-input PR-code results. The
        # second sync can reuse unchanged first-sync inputs after a 304, so
        # shared inputs require both whole results. Derive the transitive
        # membership closure while excluding unrelated change requests.
        def required_fetches(fetches):
            required = set(fetches)
            while True:
                placeholders = ",".join("?" for _ in required)
                expanded = required | {
                    row[0]
                    for row in db.execute(
                        "SELECT DISTINCT sibling.fetch_occurrence_uuidv4 "
                        "FROM parsed_result_inputs selected JOIN parsed_result_inputs sibling "
                        "USING(parsed_result_uuidv4) "
                        f"WHERE selected.fetch_occurrence_uuidv4 IN ({placeholders}) "
                        "AND sibling.fetch_occurrence_uuidv4 IS NOT NULL",
                        tuple(required),
                    )
                }
                if expanded == required:
                    return required
                required = expanded

        required_fetch = required_fetches({selected_fetch})
        required_collection = required_fetches(expected_collection)
        unrelated_fetches = {
            row[0]
            for row in db.execute(
                "SELECT o.fetch_occurrence_uuidv4 FROM fetch_occurrences o "
                "JOIN fetch_collections c USING(fetch_collection_id) "
                "WHERE c.change_request_id IS NOT NULL AND c.change_request_id!=?",
                (f"{repository}:41",),
            )
        }
        assert unrelated_fetches
        assert not required_fetch & unrelated_fetches
        assert not required_collection & unrelated_fetches
    fetch_unit = tmp_path / "selected-fetch.json"
    collection_unit = tmp_path / "selected-collection.json"
    full_unit = tmp_path / "repository.json"
    current_unit = tmp_path / "selected-current-collection.json"
    cli(
        "exchange",
        "export",
        "--repo",
        repository,
        "--fetch",
        selected_fetch,
        "--output",
        fetch_unit,
    )
    cli(
        "exchange",
        "export",
        "--repo",
        repository,
        "--collection",
        collection,
        "--output",
        collection_unit,
    )
    cli("exchange", "export", "--repo", repository, "--output", full_unit)
    cli(
        "exchange",
        "export",
        "--repo",
        repository,
        "--collection",
        current_collection,
        "--output",
        current_unit,
    )

    def exported_fetches(path):
        return {
            r["values"]["fetch_occurrence_uuidv4"]
            for r in json.loads(path.read_text())["records"]
            if r["table"] == "fetch_occurrences"
        }

    assert exported_fetches(fetch_unit) == required_fetch
    assert exported_fetches(collection_unit) == required_collection
    assert required_collection < exported_fetches(full_unit)
    current_records = json.loads(current_unit.read_text())["records"]
    current_tables = {record["table"] for record in current_records}
    assert {
        "issue_resources",
        "current_collection_pages",
        "text_bodies",
    } <= current_tables
    assert (
        not {"fetch_occurrences", "parsed_results", "stored_bytes", "payloads"}
        & current_tables
    )
    selected_pages = [
        record
        for record in current_records
        if record["table"] == "current_collection_pages"
    ]
    assert selected_pages
    selected_members = [
        member
        for page in selected_pages
        for member in json.loads(page["values"]["members"])
    ]
    assert selected_members
    assert {member["kind"] for member in selected_members} == {"issue-comment"}
    assert all(member["family"] == "issue" for member in selected_members)
    assert {
        record["values"]["kind"]
        for record in current_records
        if record["table"] == "issue_resources"
    } == {"issue", "issue-comment"}
    full_records = json.loads(full_unit.read_text())["records"]
    assert {record["table"] for record in full_records} >= {
        "issue_resources",
        "review_resources",
        "current_collection_pages",
    }
    sender_state = state
    state = tmp_path / "receiver-state"
    cli(
        "init",
        "--profile",
        "catalog-text-v1",
        "--cache-max-bytes",
        "33554432",
        "--min-free-bytes",
        "0",
    )
    for unit in (
        fetch_unit,
        fetch_unit,
        collection_unit,
        current_unit,
        current_unit,
        full_unit,
    ):
        assert (
            cli("exchange", "import", "--input", unit, allow_partial=True)["data"][
                "rejected_records"
            ]
            == 0
        )
    with (
        sqlite3.connect(state / "catalog.sqlite3") as receiver,
        sqlite3.connect(sender_state / "catalog.sqlite3") as sender,
    ):
        assert (
            receiver.execute(
                "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences ORDER BY 1"
            ).fetchall()
            == sender.execute(
                "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences ORDER BY 1"
            ).fetchall()
        )
        for table in git_tables:
            assert (
                receiver.execute(
                    f"SELECT git_fact_uuidv4 FROM {table} ORDER BY 1"
                ).fetchall()
                == sender.execute(
                    f"SELECT git_fact_uuidv4 FROM {table} ORDER BY 1"
                ).fetchall()
            )
        for table, keys in (
            ("issue_resources", "service_instance_uuidv4,kind,provider_resource_id"),
            (
                "review_resources",
                "change_request_id,kind,provider_change_request_document_id",
            ),
            ("current_collection_pages", "fetch_collection_id,ordinal"),
        ):
            assert (
                receiver.execute(
                    f"SELECT {keys} FROM {table} ORDER BY {keys}"
                ).fetchall()
                == sender.execute(
                    f"SELECT {keys} FROM {table} ORDER BY {keys}"
                ).fetchall()
            )
        assert receiver.execute(
            "SELECT DISTINCT parser_module,parser_version FROM review_resources"
        ).fetchall() == [("repo_catalog.adapters.github.current_parser", "1")]
        assert (
            receiver.execute(
                "SELECT count(*) FROM eligible_review_resources"
            ).fetchone()[0]
            > 0
        )
        assert (
            receiver.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0
        )
        assert receiver.execute("PRAGMA foreign_key_check").fetchall() == []
        assert receiver.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    # Exchange preserves provider observations, but the sender's live checks
    # cannot claim a receiver-local check. Compare every other returned field
    # exactly; backup/restore below retains the original catalog's check times.
    assert all(
        type(row["last_checked_at_us"]) is int
        for group in expected_current_reads
        for row in group
    )
    expected_imported_reads = tuple(
        [{**row, "last_checked_at_us": None} for row in group]
        for group in expected_current_reads
    )
    assert current_reads("B") == expected_imported_reads
    state = sender_state

    # Validate the installed fresh model and preservation path in both builds.
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM parsed_results").fetchone()[0] >= 2
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    backup = tmp_path / "packaged-backup.sqlite3"
    manifest = cli("db", "backup", "--output", backup)["data"]["manifest"]
    assert type(manifest["quarantined_payload_count"]) is int
    assert manifest["quarantined_payload_count"] == 0
    assert (
        json.loads(backup.with_name(backup.name + ".manifest.json").read_text())
        == manifest
    )
    state = tmp_path / "restored-state"
    cli("db", "restore", "--input", backup)
    assert current_reads("B") == expected_current_reads
    assert cli("search", "code", "--literal", "認証")["data"]["items"]
    assert cli("db", "check", "--full")["data"]["checks"]["sqlite"] == ["ok"]
    assert cli("db", "verify-payloads")["status"] == "complete"
