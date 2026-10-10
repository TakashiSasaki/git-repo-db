import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite.schema import SCHEMA_VERSION
from tests.support.distributions import build_once
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
def distributions(tmp_path_factory, request):
    base = tmp_path_factory.getbasetemp()
    if hasattr(request.config, "workerinput"):
        base = base.parent
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
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    wheelhouse = Path(
        os.environ.get("REPO_CATALOG_WHEELHOUSE", ROOT / "artifacts/wheelhouse")
    ).resolve()
    assert (wheelhouse / "manifest.json").is_file(), (
        "Run scripts/prepare_wheelhouse.py before offline tests"
    )
    env["REPO_CATALOG_WHEELHOUSE"] = str(wheelhouse)
    offline_sources = ["--offline", "--no-index", "--find-links", str(wheelhouse)]

    def prepare(work):
        checked(
            ["uv", "build", *offline_sources, "--out-dir", work / "dist"],
            cwd=ROOT,
            env=env,
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
            [
                "uv",
                "build",
                *offline_sources,
                "--wheel",
                "--out-dir",
                work / "sdist-wheel",
            ],
            cwd=source,
            env=env,
        )
        return {
            "wheel": next((work / "dist").glob("*.whl")),
            "sdist_wheel": next((work / "sdist-wheel").glob("*.whl")),
            "requirements": work / "requirements.txt",
        }

    products = build_once(base / "package-distributions", prepare)
    return (
        products["requirements"].parent,
        env,
        [products["wheel"], products["sdist_wheel"]],
    )


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
def test_wheel_sdist_cli(distributions, tmp_path, variant):
    work, env, wheels = distributions
    home = tmp_path / "home"
    home.mkdir()
    env = {**env, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}
    venv, outside = tmp_path / "venv", tmp_path / "outside"
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
    installed = json.loads(
        checked(
            [
                venv / "bin/python",
                "-c",
                "import json,importlib.util; from importlib.resources import files; "
                "root=files('repo_catalog').joinpath('resources'); "
                "print(json.dumps({'resources': [name for name in "
                "['catalog3.sql','git_domain.sql','git_facts.sql','current_api.sql','current_resources.sql',"
                "'current_collections.sql','json_contracts.sql','cas_integrity.sql','exchange.sql'] "
                "if root.joinpath(name).is_file()], 'certificate': root.joinpath('builtin_parser_verification.json').is_file(), "
                "'parser_authority': importlib.util.find_spec('repo_catalog.adapters.sqlite.parser_model') is not None}))",
            ],
            cwd=outside,
            env=env,
        )
    )
    assert len(installed["resources"]) == 9
    assert not installed["certificate"] and not installed["parser_authority"]
    help_text = checked(
        [venv / "bin/repo-catalog", "parser", "--help"], cwd=outside, env=env
    )
    assert "reparse" in help_text and "inspect-message" in help_text
    assert "select-profile" not in help_text and "verify" not in help_text
    fixture = GitFixture(tmp_path / "remotes")
    state = tmp_path / "disposable-state"

    def cli(*args, credentials=None, state_dir=state, accepted_codes=(0,)):
        return json.loads(
            checked(
                [
                    venv / "bin/repo-catalog",
                    "--state-dir",
                    state_dir,
                    "--format",
                    "json",
                    *args,
                ],
                cwd=outside,
                env={**env, **(credentials or {})},
                accepted_codes=accepted_codes,
            )
        )

    cli(
        "init",
        "--profile",
        "catalog-text-v1",
        "--cache-max-bytes",
        "67108864",
        "--min-free-bytes",
        "0",
    )
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
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute(
            "SELECT schema_version,lifecycle FROM database_identity"
        ).fetchone() == (SCHEMA_VERSION, "validated")
        acquisition = db.execute(
            "SELECT git_acquisition_id FROM git_acquisitions"
        ).fetchone()[0]
        captures = db.execute("SELECT * FROM git_acquisitions").fetchall()
        structure_counts = {
            table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("commits", "commit_parents", "tree_entries", "snapshots")
        }
    reanalysis = cli("parser", "reparse", acquisition)["data"]["result"]
    assert "parsed_result_uuidv4" not in reanalysis
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute("SELECT * FROM git_acquisitions").fetchall() == captures
        assert {
            table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in structure_counts
        } == structure_counts
    cli("index", "rebuild")
    assert cli("search", "code", "--literal", "認証")["data"]["items"]

    def current_reads(stage):
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
        assert (
            len(comments) == 1
            and comments[0]["body"] == f"ordinary-issue-comment {stage} 1"
        )
        reviews = cli(
            "pr",
            "documents",
            "--repo",
            repository,
            "--provider-change-request-number",
            "41",
            "--document-kind",
            "review-comment",
        )["data"]["items"]
        assert any(row["body"] == f"review-comment-marker {stage}" for row in reviews)
        issue_matches = cli(
            "search",
            "issue",
            "--repo",
            repository,
            "--literal",
            f"ordinary-issue-comment {stage}",
        )["data"]["items"]
        assert issue_matches
        review_matches = cli(
            "search",
            "pr",
            "--repo",
            repository,
            "--document-kind",
            "review-comment",
            "--literal",
            f"review-comment-marker {stage}",
        )["data"]["items"]
        assert review_matches
        if stage == "B":
            assert not cli(
                "search",
                "issue",
                "--repo",
                repository,
                "--literal",
                "ordinary-issue-comment A",
            )["data"]["items"]
            assert not cli(
                "search",
                "pr",
                "--repo",
                repository,
                "--document-kind",
                "review-comment",
                "--literal",
                "review-comment-marker A",
            )["data"]["items"]
        return shown, comments, reviews, issue_matches, review_matches

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
        api.stage = "B"
        cli("sync", "all", "--repo", repository, credentials=credentials)
        expected = current_reads("B")
        cli("index", "rebuild", "--kind", "issue")
        cli("index", "rebuild", "--kind", "pr")
        assert current_reads("B") == expected
        assert not api.errors

    checked(
        [
            venv / "bin/python",
            "-c",
            "import sqlite3,sys; from importlib.resources import files; "
            "from repo_catalog.adapters.sqlite.json_contracts import inventory,guard_sql,validate_catalog; "
            "assert files('repo_catalog').joinpath('resources/json_contracts.sql').read_text()==guard_sql(); "
            "db=sqlite3.connect(sys.argv[1]); validate_catalog(db); inventory(db)",
            state / "catalog.sqlite3",
        ],
        cwd=outside,
        env=env,
    )
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        names = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        assert not names & {
            "parsed_results",
            "parsed_result_inputs",
            "parsed_result_publications",
            "parser_profiles",
            "fetch_occurrences",
            "source_input_observations",
            "change_request_observations",
            "document_observations",
            "review_thread_observations",
        }
        assert db.execute(
            "SELECT DISTINCT representation FROM payloads"
        ).fetchall() == [("git-object-raw-v1",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert {r[1] for r in db.execute("PRAGMA table_info(coverage_claims)")} == {
            "coverage_claim_id",
            "coverage_scope_id",
            "coverage_state",
            "observed_at_us",
            "details_json",
        }
        assert "record_json" not in {
            r[1] for r in db.execute("PRAGMA table_info(exchange_admissions)")
        }
    cli("db", "check", "--full")
    unit = tmp_path / "repository.json"
    cli("exchange", "export", "--repo", repository, "--output", unit)
    receiver = tmp_path / "disposable-receiver"
    cli(
        "init",
        "--profile",
        "catalog-text-v1",
        "--cache-max-bytes",
        "67108864",
        "--min-free-bytes",
        "0",
        state_dir=receiver,
    )
    cli("exchange", "import", "--input", unit, state_dir=receiver)
    cli("exchange", "import", "--input", unit, state_dir=receiver)
    assert (
        cli(
            "issue",
            "show",
            "--repo",
            repository,
            "--provider-issue-number",
            "1",
            state_dir=receiver,
        )["data"]["items"][0]["body"]
        == "ordinary-issue-body B"
    )
    assert cli("search", "code", "--literal", "認証", state_dir=receiver)["data"][
        "items"
    ]
    cli("db", "check", "--full", state_dir=receiver)
    backup = tmp_path / "backup.sqlite3"
    cli("db", "backup", "--output", backup)
    restored = tmp_path / "disposable-restored"
    cli("db", "restore", "--input", backup, state_dir=restored)
    assert cli("search", "code", "--literal", "認証", state_dir=restored)["data"][
        "items"
    ]
    cli("db", "check", "--full", state_dir=restored)
    failed = cli(
        "db", "restore", "--input", backup, state_dir=restored, accepted_codes=(2,)
    )
    assert failed["error"]["code"] == "INVALID_ARGUMENT"
