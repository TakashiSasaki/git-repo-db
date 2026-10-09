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
        cli("sync", "pr", "--repo", repository, credentials=credentials)
        assert not api.errors

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

        # Each acquired page also belongs to the sealed multi-input PR-code
        # result. Required whole-result membership is portable; other CRs are
        # unrelated. Derive the fixture's exact closure from persisted inputs.
        def required_fetches(fetches):
            placeholders = ",".join("?" for _ in fetches)
            return set(fetches) | {
                row[0]
                for row in db.execute(
                    "SELECT DISTINCT sibling.fetch_occurrence_uuidv4 "
                    "FROM parsed_result_inputs selected JOIN parsed_result_inputs sibling "
                    "USING(parsed_result_uuidv4) "
                    f"WHERE selected.fetch_occurrence_uuidv4 IN ({placeholders}) "
                    "AND sibling.fetch_occurrence_uuidv4 IS NOT NULL",
                    tuple(fetches),
                )
            }

        required_fetch = required_fetches({selected_fetch})
        required_collection = required_fetches(expected_collection)
    fetch_unit = tmp_path / "selected-fetch.json"
    collection_unit = tmp_path / "selected-collection.json"
    full_unit = tmp_path / "repository.json"
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

    def exported_fetches(path):
        return {
            r["values"]["fetch_occurrence_uuidv4"]
            for r in json.loads(path.read_text())["records"]
            if r["table"] == "fetch_occurrences"
        }

    assert exported_fetches(fetch_unit) == required_fetch
    assert exported_fetches(collection_unit) == required_collection
    assert required_collection < exported_fetches(full_unit)
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
    for unit in (fetch_unit, fetch_unit, collection_unit, full_unit):
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
        assert (
            receiver.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0
        )
        assert receiver.execute("PRAGMA foreign_key_check").fetchall() == []
        assert receiver.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    state = sender_state

    # Validate the installed fresh model and preservation path in both builds.
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM parsed_results").fetchone()[0] >= 2
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    backup = tmp_path / "packaged-backup.sqlite3"
    cli("db", "backup", "--output", backup)
    state = tmp_path / "restored-state"
    cli("db", "restore", "--input", backup)
    assert cli("search", "code", "--literal", "認証")["data"]["items"]
    assert cli("db", "check", "--full")["data"]["checks"]["sqlite"] == ["ok"]
    assert cli("db", "verify-payloads")["status"] == "complete"
