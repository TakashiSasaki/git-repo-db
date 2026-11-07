"""Resolved C+G+O and A+C+G+O consumers without concrete Context/Search."""

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from tests.integration.p5.conftest import build_sample_git_repo, git
from tests.support.distributions import (
    build_once,
    dependency_wheels,
    make_package_distributions,
    package_build_environment,
    package_build_inputs,
    package_build_runner,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def git_acquisition_distributions(tmp_path_factory):
    env = package_build_environment()
    products = {}
    for name in ("git-acquisition", "access"):
        project = ROOT / "packages" / name
        products[name] = build_once(
            tmp_path_factory.getbasetemp() / (name + "-distributions"),
            lambda work, project=project: make_package_distributions(
                work, project, env
            ),
            inputs=lambda project=project: package_build_inputs(project, env),
        )
    return env, products


@pytest.mark.parametrize("access", [False, True], ids=["local", "access"])
@pytest.mark.parametrize("variant", ["wheel", "sdist_wheel"])
def test_git_acquisition_minimum(
    git_acquisition_distributions, tmp_path, access, variant
):
    env, products = git_acquisition_distributions
    artifacts = (
        products["git-acquisition"][variant],
        *dependency_wheels(products["git-acquisition"], variant=variant),
        *((products["access"][variant],) if access else ()),
    )
    assert len(artifacts) == (6 if access else 5)
    owners = {}
    for artifact in artifacts:
        with zipfile.ZipFile(artifact) as archive:
            for name in archive.namelist():
                if name.startswith("repo_catalog/") and not name.endswith("/"):
                    assert name not in owners, name
                    owners[name] = artifact.name
    assert owners["repo_catalog/application/git_acquisition.py"].startswith(
        "repo_catalog_git_acquisition-"
    )
    for relative in (
        "application/acquisition.py",
        "domain/acquisition.py",
        "application/exchange.py",
        "application/recovery.py",
        "application/paired_query.py",
        "application/production_query.py",
        "domain/p1_context.py",
        "domain/search_query.py",
        "adapters/sqlite/p1_coordination.py",
        "adapters/sqlite/p1_ddl/context.sql",
        "adapters/sqlite/p1_ddl/search.sql",
    ):
        assert "repo_catalog/" + relative not in owners, relative
    outside = tmp_path / "consumer"
    source = outside / "executor/source.git"
    objects = build_sample_git_repo(source, "sha1")
    (outside / "fixture.json").write_text(
        json.dumps(
            {
                "access": access,
                "objects": {name: list(oid.key) for name, oid in objects.items()},
                "commit_hex": git(
                    source, "cat-file", "commit", objects["commit2"].object_oid
                ).hex(),
                "note_hex": git(
                    source, "cat-file", "blob", objects["note_blob"].object_oid
                ).hex(),
            }
        )
    )
    links = outside / "allowed-artifacts"
    links.mkdir()
    for artifact in artifacts:
        shutil.copy2(artifact, links / artifact.name)
    run = package_build_runner
    venv = tmp_path / "venv"
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    before = sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*"))
    names = ["repo-catalog-git-acquisition==0.2.0"] + (
        ["repo-catalog-access==0.2.0"] if access else []
    )
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--no-index",
            "--find-links",
            links,
            *names,
        ],
        outside,
        env,
    )
    assert (
        sorted(p.relative_to(outside).as_posix() for p in outside.rglob("*")) == before
    )
    driver = outside / "git_acquisition_probe.py"
    shutil.copy2(ROOT / "tests/support/git_acquisition_probe.py", driver)
    shutil.copy2(
        ROOT / "tests/support/network_guard/sitecustomize.py",
        outside / "sitecustomize.py",
    )
    receipt = outside / "result.json"
    run([python, "-I", driver, receipt], outside, env)
    result = json.loads(receipt.read_text())
    assert result["result"] == "passed"
    result["artifacts"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n")

    # Independent resolver-created basic installations retain the optional boundary.
    basic = tmp_path / "basic"
    run(["uv", "venv", basic, "--python", sys.executable, "--offline"], outside, env)
    basic_python = basic / "bin/python"
    target = "access" if access else "core"
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            basic_python,
            "--offline",
            "--no-index",
            "--find-links",
            links,
            "repo-catalog-" + target + "==0.2.0",
        ],
        outside,
        env,
    )
    program = """
import importlib.metadata,importlib.util,json
names={d.metadata['Name'] for d in importlib.metadata.distributions() if d.metadata['Name'].startswith('repo-catalog')}
expected={'repo-catalog-access'} if ACCESS else {'repo-catalog-core','repo-catalog-runtime','repo-catalog-contracts'}
assert names==expected,names
for module in ('application.git_acquisition','domain.git_acquisition','adapters.git.native'):
 try: found=importlib.util.find_spec('repo_catalog.'+module)
 except ModuleNotFoundError: found=None
 assert found is None,module
print(json.dumps({'result':'passed','installed_distributions':sorted(names)}))
""".replace("ACCESS", repr(access))
    basic_result = json.loads(run([basic_python, "-I", "-c", program], outside, env))
    (outside / "basic-result.json").write_text(
        json.dumps(basic_result, indent=2) + "\n"
    )
