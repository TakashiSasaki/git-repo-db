"""Execute the documented product-to-documentation flow in a disposable checkout."""

import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_guide_separates_product_and_docs_environments():
    guide = (ROOT / "documentation/content/development/index.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)\n```", guide, re.S)
    lines = [line for block in blocks for line in block.splitlines()]
    setup = next(
        line for line in lines if "uv sync --locked --project documentation" in line
    )
    producer = next(
        line for line in lines if "scripts/schema_inventory.py --source" in line
    )
    freshness = next(
        line for line in lines if "tools/schema_viz.py" in line and "--check" in line
    )
    site = next(
        line
        for line in lines
        if "tools/build_docs_site.py" in line and "--check" in line
    )
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    env = os.environ.copy()
    env.update(UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never")
    with tempfile.TemporaryDirectory(prefix="schema-guide-") as tmp:
        checkout = Path(tmp) / "checkout"
        subprocess.run(
            ["git", "clone", "--quiet", "--shared", str(ROOT), str(checkout)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "--quiet", "--detach", sha],
            cwd=checkout,
            check=True,
            capture_output=True,
        )
        product_python = ROOT / ".venv/bin/python"
        subprocess.run(
            ["uv", "venv", "--python", str(product_python), str(checkout / ".venv")],
            cwd=checkout,
            env=env,
            check=True,
            capture_output=True,
        )
        env["UV_PROJECT_ENVIRONMENT"] = str(checkout / ".venv")
        env["VIRTUAL_ENV"] = str(checkout / ".venv")
        product_probe = [str(checkout / ".venv/bin/python"), "-c", "import yaml"]
        assert (
            subprocess.run(product_probe, cwd=checkout, capture_output=True).returncode
            != 0
        )
        subprocess.run(
            shlex.split(setup), cwd=checkout, env=env, check=True, capture_output=True
        )
        assert (
            subprocess.run(product_probe, cwd=checkout, capture_output=True).returncode
            != 0
        )
        verify_docs = [
            "env",
            "-u",
            "UV_PROJECT_ENVIRONMENT",
            "uv",
            "run",
            "--project",
            "documentation",
            "--no-sync",
            "python",
            "-c",
            "import sys,yaml; print(sys.prefix); print(yaml.__file__)",
        ]
        result = subprocess.run(
            verify_docs,
            cwd=checkout,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert str(checkout / "documentation/.venv") in result.stdout
        args = [
            part.replace("$FULL_PRODUCT_SHA", sha) for part in shlex.split(producer)
        ]
        args[2] = str(checkout / "scripts/schema_inventory.py")
        args[-1] = str(checkout / "documentation/.build/inputs")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            args = [str(product_python), *args[2:]]
        else:
            args[0] = str(ROOT / "scripts/local-run.sh")
        subprocess.run(args, cwd=checkout, env=env, check=True, capture_output=True)
        subprocess.run(
            shlex.split(freshness),
            cwd=checkout,
            env=env,
            check=True,
            capture_output=True,
        )
        site_args = [
            part.replace("$FULL_PRODUCT_SHA", sha).replace("$FULL_DOC_SHA", sha)
            for part in shlex.split(site)
        ]
        site_args.append("--no-mermaid")
        result = subprocess.run(
            site_args, cwd=checkout, env=env, check=True, capture_output=True, text=True
        )
        assert "BUILD & VALIDATION SUCCESSFUL" in result.stdout
        assert (
            subprocess.run(product_probe, cwd=checkout, capture_output=True).returncode
            != 0
        )
