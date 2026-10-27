"""Exercise the generation commands emitted by both schema entry points."""

import hashlib
import html
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from tools.schema_viz import generate_html, generate_readme

ROOT = Path(__file__).resolve().parents[2]


def test_emitted_commands_generate_and_check_pinned_inventory():
    ir = json.loads((ROOT / "documentation/.build/inputs/inventory.json").read_text())
    viewer = generate_html(ir)["index.html"]
    readme = generate_readme(ir)["README.md"]
    html_commands = html.unescape(
        re.search(
            r'Unified Generation Commands</span></div>\s*<pre class="sql-code">(.*?)</pre>',
            viewer,
            re.S,
        ).group(1)
    )
    readme_commands = re.search(
        r"## 3\. Unified Generation.*?```bash\n(.*?)\n```", readme, re.S
    ).group(1)
    assert html_commands == readme_commands
    commands = [
        line
        for line in html_commands.splitlines()
        if line
        and not line.startswith("#")
        and not line.startswith("FULL_PRODUCT_SHA=")
    ]
    assert len(commands) == 3
    guide = (ROOT / "documentation/content/development/index.md").read_text()
    guide_blocks = re.findall(r"```bash\n(.*?)\n```", guide, re.S)
    guide_lines = {line for block in guide_blocks for line in block.splitlines()}
    assert set(commands) <= guide_lines
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    inputs_root = ROOT / "documentation/.build/inputs"
    output_root = ROOT / "documentation/.build/output"
    inputs_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(prefix="commands-", dir=inputs_root) as inp,
        tempfile.TemporaryDirectory(prefix="commands-", dir=output_root) as out,
    ):
        input_dir = Path(inp)
        output_dir = Path(out)
        for line in commands:
            args = [
                part.replace("$FULL_PRODUCT_SHA", sha) for part in shlex.split(line)
            ]
            # Hosted Pages selects the product runtime and syncs the root uv
            # environment; unlike local bootstrap, it has no local-run receipt.
            if (
                args[0] == "scripts/local-run.sh"
                and os.environ.get("GITHUB_ACTIONS") == "true"
            ):
                args = ["uv", "run", "--no-sync", "python", *args[2:]]
            args = [
                str(input_dir)
                if part == "documentation/.build/inputs"
                else str(input_dir / "inventory.json")
                if part == "documentation/.build/inputs/inventory.json"
                else part
                for part in args
            ]
            if "documentation/tools/schema_viz.py" in args:
                args.extend(["--output-dir", str(output_dir)])
            subprocess.run(
                args,
                cwd=ROOT,
                env=os.environ.copy(),
                check=True,
                capture_output=True,
                text=True,
            )
        receipt = json.loads((input_dir / "producer.json").read_text())
        assert receipt["product_source"]["commit"] == sha
        assert (
            hashlib.sha256((input_dir / "inventory.json").read_bytes()).hexdigest()
            == receipt["ir_sha256"]
        )
        assert (output_dir / "index.html").is_file()
        assert (output_dir / "dbml/core.dbml").is_file()
        assert (output_dir / "mermaid/overview.md").is_file()
        (output_dir / "README.md").write_text("stale")
        check = subprocess.run(
            args, cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True
        )
        assert check.returncode != 0 and "README.md" in check.stdout
