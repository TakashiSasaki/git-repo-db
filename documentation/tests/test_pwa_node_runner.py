"""Include the Node icon safety suite in the documentation receipt."""

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pwa_node_suite():
    node = shutil.which("node")
    assert node is not None, "Node.js is required for documentation verification"
    result = subprocess.run(
        [
            node,
            "--test",
            "--test-reporter=tap",
            "documentation/tests/test_generate_pwa_icons.mjs",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    evidence = result.stdout + "\n" + result.stderr
    assert result.returncode == 0, evidence
    for field, count in (("tests", 6), ("pass", 6), ("fail", 0), ("skipped", 0)):
        assert re.search(rf"(?m)^# {field} {count}\s*$", result.stdout), evidence
