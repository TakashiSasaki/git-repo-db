"""Documented cross-branch setup keeps product and web environments independent."""

import os
import subprocess
import tempfile
from pathlib import Path

from tools.product_context import PRODUCT_ROOT

ROOT = Path(__file__).resolve().parents[2]


def test_guide_separates_product_and_docs_environments():
    guide = (ROOT / "website/content/development/index.md").read_text()
    assert "python scripts/prepare_product.py" in guide
    assert "scripts/local-run.sh" in guide
    env = dict(os.environ, UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never")
    with tempfile.TemporaryDirectory(prefix="web-guide-") as temp:
        clone = Path(temp) / "web"
        subprocess.run(
            ["git", "clone", "--quiet", "--shared", str(ROOT), str(clone)],
            check=True,
            capture_output=True,
        )
        # A hostile product-launcher selection must not redirect the docs project.
        wrong = Path(temp) / "unrelated-env"
        subprocess.run(
            [
                "uv",
                "venv",
                "--python",
                str(PRODUCT_ROOT / ".venv/bin/python"),
                str(wrong),
            ],
            check=True,
            capture_output=True,
        )
        env["UV_PROJECT_ENVIRONMENT"] = str(wrong)
        subprocess.run(
            [
                str(PRODUCT_ROOT / ".venv/bin/python"),
                "scripts/prepare_product.py",
                "--product-root",
                str(PRODUCT_ROOT),
            ],
            cwd=clone,
            env=env,
            check=True,
            capture_output=True,
        )
        assert (clone / "website/.venv/bin/python").is_file()
        probe = subprocess.run(
            [str(wrong / "bin/python"), "-c", "import yaml"], capture_output=True
        )
        assert probe.returncode != 0
        result = subprocess.run(
            [
                str(clone / "website/.venv/bin/python"),
                "-c",
                "import sys,yaml; print(sys.prefix)",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert str(clone / "website/.venv") in result.stdout
        assert not (clone / "src").exists() and not (clone / "docs").exists()
