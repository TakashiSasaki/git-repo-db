"""Installed opt-in P7 recovery capabilities from wheel and wheel built from sdist."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.packaging.test_p1_distribution import p1_distributions, run  # noqa: F401


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
def test_p7_installed_recovery_distribution(
    p1_distributions,  # noqa: F811
    tmp_path: Path,
    variant: int,
) -> None:
    env, wheels = p1_distributions
    outside = tmp_path / "outside"
    outside.mkdir()
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
    script = r"""
import sys
from pathlib import Path

from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import BackupScope

assert "site-packages" in str(Path(__import__("repo_catalog.application.recovery", fromlist=["x"]).__file__))
service = RecoveryService()
assert service is not None
print("P7 recovery installed and importable from wheel/sdist successfully")
"""
    run([python, "-c", script], outside, env)
