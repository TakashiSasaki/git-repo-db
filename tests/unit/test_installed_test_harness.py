"""Copied I4/I5 tests retain test-only imports outside the source checkout."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import installed_test_harness as harness

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("stage", "source_name", "required_count"),
    [(4, "test_transfer_sql.py", 217), (5, "test_transfer_admission.py", 29)],
)
def test_copied_contracts_collect_with_external_test_support(
    tmp_path, stage, source_name, required_count
):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / f"test_installed_i{stage}.py"
    shutil.copyfile(ROOT / "tests/integration/p3" / source_name, target)
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    argv = [sys.executable, "-m", "pytest", target.name, "-q", "--collect-only"]
    # This reproduces the hosted omission before testing the corrected staging.
    missing = subprocess.run(argv, cwd=outside, env=env, capture_output=True, text=True)
    assert missing.returncode == 2, missing.stdout + missing.stderr
    assert "No module named 'tests'" in missing.stdout
    staged = harness.stage_support(ROOT, outside)
    collected = subprocess.run(
        argv, cwd=outside, env=env, capture_output=True, text=True
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr
    nodes = [line for line in collected.stdout.splitlines() if "::" in line]
    assert len(nodes) == required_count
    assert set(staged) == {*harness.SUPPORT_FILES, "installed_journal.py"}
    assert not (outside / "repo_catalog").exists()
    assert not (outside / "src").exists()
    assert not (outside / "tests/conftest.py").exists()


def test_installed_test_support_refuses_a_source_child(tmp_path):
    with pytest.raises(ValueError, match="outside the source checkout"):
        harness.stage_support(tmp_path, tmp_path / "outside")


def test_installed_pytest_process_refuses_a_shadow_product(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    harness.stage_support(ROOT, outside)
    harness.bind_artifact(outside, {})
    shadow = outside / "repo_catalog"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("# a source product must never be accepted\n")
    (outside / "test_probe.py").write_text("def test_probe():\n    assert True\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "test_probe.py",
            "--collect-only",
            "-c",
            outside / "pytest.ini",
            "--rootdir=" + str(outside),
        ],
        cwd=outside,
        env=dict(
            os.environ,
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            REPO_CATALOG_IMPORT_RECEIPT=str(tmp_path / "imports.json"),
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "AssertionError" in result.stdout + result.stderr
    assert str(shadow) in result.stdout + result.stderr
    assert not (tmp_path / "imports.json").exists()
