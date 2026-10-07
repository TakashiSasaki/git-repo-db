import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.git_fixture import FixtureRepo

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
        ).fetchone() == ("repo-catalog/catalog3", 6, "validated")
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
