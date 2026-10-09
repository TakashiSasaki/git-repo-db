import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite.schema import SCHEMA_VERSION
from tests.support.git_fixture import FixtureRepo
from tests.support.legacy_v2 import initialize

ROOT = Path(__file__).resolve().parents[2]


def checked(args, *, cwd, env=None):
    p = subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if p.returncode:
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
                "import repo_catalog.adapters.import_v2.engine; "
                "print(json.dumps({'schema': root.joinpath('catalog3.sql').is_file(), "
                "'import_contract': root.joinpath('import_v2/conversion-contract.json').is_file()}))",
            ],
            cwd=outside,
            env=env,
        )
    )
    assert resources == {"schema": True, "import_contract": True}
    repo = FixtureRepo(tmp_path / "remote.git")
    repo.commit("A", {b"hello.txt": "認証 wheel".encode()})
    repo.ref("refs/heads/main", "A")
    state = tmp_path / "state"

    def cli(*args):
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
                env=env,
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
        "sources", "add", "local-git", "--name", "packaged", "--url", repo.url
    )["data"]["source_id"]
    cli("discover", "--source", source)
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

    # Exercise packaged salvage resources in these already isolated installs;
    # a separate --target wheel build cannot add another distribution variant.
    legacy, cache = initialize(tmp_path / "legacy")
    preserved_cache = cache / "synthetic-evidence"
    preserved_cache.write_bytes(b"packaged salvage original cache\x00\xff")
    repository_id = "00000000-0000-4000-8000-000000000123"
    display_name = "synthetic/packaged salvage 日本語"
    with sqlite3.connect(legacy) as db:
        db.execute(
            "INSERT INTO sources VALUES('packaged-source','local-git',?, ?,NULL)",
            ("packaged salvage", '{"url":"file:///synthetic/packaged.git"}'),
        )
        db.execute(
            "INSERT INTO repositories VALUES(?,'packaged-source','local','synthetic-repo',?,?,?,NULL)",
            (repository_id, display_name, "file:///synthetic/packaged.git", "{}"),
        )
        db.execute(
            "INSERT INTO source_repositories VALUES('packaged-source',?,?,?)",
            (repository_id, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
    preserved = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (legacy, preserved_cache)
    }
    state = tmp_path / "salvaged-state"
    imported = cli("import-v2", "--source", legacy, "--source-cache", cache)["data"]
    assert imported["complete"] and imported["lifecycle"] == "building"
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute(
            "SELECT format_id,lifecycle FROM database_identity"
        ).fetchone() == ("repo-catalog/catalog3", "building")
    with sqlite3.connect(state / "import-v2/workspace.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == 1
    assert cli("db", "finalize")["data"]["lifecycle"] == "validated"
    repositories = cli("repos", "list", "--repo", repository_id)["data"]["items"]
    assert len(repositories) == 1
    assert repositories[0]["repository_uuidv4"] == repository_id
    assert repositories[0]["name"] == display_name
    assert cli("db", "check", "--full")["data"]["checks"]["sqlite"] == ["ok"]
    assert preserved == {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in preserved
    }
