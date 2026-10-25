"""Focused installed target-resource checks, not full released-runtime acceptance."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.installed_test_harness import stage_support
from tests.support.distributions import build_once, make_package_distributions

ROOT = Path(__file__).resolve().parents[2]


def run(args, cwd, env):
    result = subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture(scope="module")
def p1_distributions(tmp_path_factory):
    base = tmp_path_factory.getbasetemp()
    while base.name.startswith("popen-gw"):
        base = base.parent
    env = dict(os.environ)
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "REPO_CATALOG_TEST_BOOTSTRAP",
        "GH_TOKEN",
        "GITHUB_TOKEN",
    ):
        env.pop(name, None)
    products = build_once(
        base / "package-distributions",
        lambda w: make_package_distributions(w, ROOT, env),
    )
    return env, [products["wheel"], products["sdist_wheel"]]


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
def test_p1_packaged_ddl_outside_checkout(p1_distributions, tmp_path, variant):
    env, wheels = p1_distributions
    outside = tmp_path / "outside"
    outside.mkdir()
    stage_support(ROOT, outside)
    venv = tmp_path / "venv"
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--no-deps",
            wheels[variant],
        ],
        outside,
        env,
    )
    script = """
import json
from pathlib import Path
from uuid import uuid4
from repo_catalog.adapters.sqlite import p1_schema as s
assert "site-packages" in str(Path(s.__file__))
s.verify_declared()
repo, instance = str(uuid4()), str(uuid4())
for store in s.STORES:
    path = Path(store + ".sqlite3")
    s.initialize(path, store, repo, instance)
    db = s.connect(path, store)
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()
print(json.dumps(s.expected_ddl_manifest(), sort_keys=True))
"""
    actual = json.loads(run([python, "-c", script], outside, env))
    from repo_catalog.adapters.sqlite.p1_schema import expected_ddl_manifest

    assert actual == expected_ddl_manifest()
    driver = outside / "verify_i2_distribution.py"
    driver.write_bytes((ROOT / "scripts/verify_i2_distribution.py").read_bytes())
    run([python, driver, "--output", outside / "i2-installed.json"], outside, env)
    receipt = json.loads((outside / "i2-installed.json").read_text())
    assert all(str(venv) in item["path"] for item in receipt["origins"].values())

    parent_driver = outside / "verify_i3_distribution.py"
    parent_driver.write_bytes((ROOT / "scripts/verify_i3_distribution.py").read_bytes())
    run(
        [python, parent_driver, "--output", outside / "i3-installed.json"], outside, env
    )
    parent_receipt = json.loads((outside / "i3-installed.json").read_text())
    assert all(str(venv) in item["path"] for item in parent_receipt["origins"].values())
