"""Real subprocess counterexamples; fixture checkouts contain no user state."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "producer"
    root.mkdir()
    for directory in ["src", "packages", "scripts"]:
        shutil.copytree(
            ROOT / directory,
            root / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for name in ["pyproject.toml", "uv.lock", ".gitignore"]:
        shutil.copyfile(ROOT / name, root / name)

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()

    git("init", "-q")
    git("config", "user.name", "Synthetic producer fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("add", ".")
    git("commit", "-qm", "pinned producer")
    return root, git


def run_export(root, source):
    import sys

    output = root / "documentation/.build/inputs"
    output.mkdir(parents=True, exist_ok=True)
    (output / "inventory.json").write_text("retain previous inventory")
    (output / "producer.json").write_text("retain previous producer")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/schema_inventory.py",
            "--source",
            source,
            "--output",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, output


def test_uncommitted_audit_control_cannot_change_ir_under_old_pin(checkout):
    root, git = checkout
    source = git("rev-parse", "HEAD")
    audit = root / "scripts/audit_publication_free.py"
    audit.write_text(
        audit.read_text()
        + "\nimport sys\nsys.modules['__main__'].GROUP_METADATA['portable_identity_and_registration']['title']='uncommitted probe'\n"
    )
    result, output = run_export(root, source)
    assert result.returncode != 0 and "Producer input differs" in result.stderr
    assert (output / "inventory.json").read_text() == "retain previous inventory"
    assert (output / "producer.json").read_text() == "retain previous producer"


def test_control_side_effect_after_preflight_is_rechecked_before_publication(checkout):
    root, git = checkout
    audit = root / "scripts/audit_publication_free.py"
    audit.write_text(
        audit.read_text()
        + "\n(ROOT/'packages/contracts/src/repo_catalog/_version.py').write_text('# mutated during control import\\n')\n"
    )
    git("add", ".")
    git("commit", "-qm", "synthetic mutating control")
    result, output = run_export(root, git("rev-parse", "HEAD"))
    assert result.returncode != 0 and "Producer input differs" in result.stderr
    assert (output / "inventory.json").read_text() == "retain previous inventory"


def test_executed_unbound_repository_helper_is_refused(checkout):
    root, git = checkout
    audit = root / "scripts/audit_publication_free.py"
    audit.write_text(audit.read_text() + "\nimport unbound_control\n")
    git("add", ".")
    git("commit", "-qm", "synthetic external control import")
    (root / "unbound_control.py").write_text("marker=True\n")
    result, output = run_export(root, git("rev-parse", "HEAD"))
    assert result.returncode != 0 and "outside bound inventory" in result.stderr
    assert (output / "producer.json").read_text() == "retain previous producer"
