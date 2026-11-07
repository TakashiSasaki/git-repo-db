"""The small CI artifact must actually reproduce the selected Ruff checks."""

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = "scripts/access_ci_format_targets.sh"


@pytest.mark.parametrize(
    ("status", "mode", "static", "tests", "packaging", "scoped"),
    [
        ("success", "development", "true", "false", "false", True),
        ("failure", "development", "true", "false", "false", False),
        ("success", "release", "true", "false", "false", False),
        ("success", "development", "false", "false", "false", False),
        ("success", "development", "true", "true", "false", False),
        ("success", "development", "true", "false", "true", False),
        ("success", "development", "true", "", "", False),
    ],
)
def test_formatter_scope_never_replaces_release_or_failure_evidence(
    status, mode, static, tests, packaging, scoped
):
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source {HELPER}; access_ci_formatter_only "$@"',
            "scope-test",
            status,
            mode,
            static,
            tests,
            packaging,
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert (result.returncode == 0) is scoped


def test_committed_formatter_archive_runs_both_checks_offline(tmp_path):
    ruff = shutil.which("ruff")
    assert ruff, "run this test in the verified product environment"
    archive = tmp_path / "source.tar.gz"
    subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            f'source {HELPER}; archive_access_formatter_source "$1"',
            "archive-test",
            str(archive),
        ],
        cwd=ROOT,
        check=True,
    )
    assert archive.stat().st_size <= 2 * 1024 * 1024
    extracted = tmp_path / "source"
    extracted.mkdir()
    with tarfile.open(archive, "r:gz") as source:
        names = source.getnames()
        assert HELPER in names
        assert not any(
            name.startswith("docs/implementation/evidence/") for name in names
        )
        source.extractall(extracted, filter="data")
    subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            f'source {HELPER}; "$1" check "${{targets[@]}}"; '
            '"$1" format --check "${targets[@]}"',
            "ruff-test",
            ruff,
        ],
        cwd=extracted,
        check=True,
        capture_output=True,
        text=True,
    )
