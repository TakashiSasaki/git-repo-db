"""Execute the unchanged related cohort with command/exit and source receipts."""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent / "raw"
TARGETS = [
    "tests/unit/test_emit_ci_evidence.py",
    "tests/unit/test_ci_plan.py",
    "tests/unit/test_ci_profile.py",
    "tests/unit/test_ci_journal.py",
    "tests/unit/test_ci_python_runtime.py",
    "tests/unit/test_sqlite_validation_policy.py",
    "tests/integration/test_ci_execution.py",
]


def inputs():
    names = subprocess.check_output(
        [
            "git",
            "ls-files",
            "src",
            "tests",
            "scripts",
            ".github",
            "pyproject.toml",
            "uv.lock",
        ],
        text=True,
    ).splitlines()
    return {n: hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in names}


def main():
    before = inputs()
    (OUT / "input-hashes.json").write_text(json.dumps(before, indent=2) + "\n")
    commands = [
        (
            "collection",
            [".venv/bin/python", "-m", "pytest", *TARGETS, "-q", "--collect-only"],
        ),
        (
            "pytest",
            [
                ".venv/bin/python",
                "-m",
                "pytest",
                *TARGETS,
                "-q",
                "-o",
                "junit_family=xunit1",
                "--junitxml",
                str(OUT / "tests.xml"),
                "--journal",
                str(OUT / "journal.jsonl"),
            ],
        ),
        ("ruff-lint", [".venv/bin/ruff", "check", "src", "tests", "scripts"]),
        (
            "ruff-format",
            [".venv/bin/ruff", "format", "--check", "src", "tests", "scripts"],
        ),
        (
            "sqlite-policy",
            [".venv/bin/python", "scripts/check_sqlite_validation_policy.py"],
        ),
        ("review-lint", [".venv/bin/ruff", "check", str(Path(__file__).parent)]),
        (
            "review-format",
            [".venv/bin/ruff", "format", "--check", str(Path(__file__).parent)],
        ),
    ]
    records = []
    for name, command in commands:
        started = time.monotonic()
        with (OUT / f"{name}.log").open("wb") as log:
            proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        records.append(
            {
                "name": name,
                "command": command,
                "cwd": str(ROOT),
                "exit_code": proc.returncode,
                "wall_seconds": time.monotonic() - started,
                "log": f"{name}.log",
            }
        )
        (OUT / "checks.json").write_text(json.dumps(records, indent=2) + "\n")
        print(name, proc.returncode, flush=True)
    assert before == inputs()
    assert all(x["exit_code"] == 0 for x in records)
    (OUT / "execution.json").write_text(
        json.dumps(
            {
                "head": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip(),
                "inputs_unchanged": True,
                "PYTHONPATH": os.environ.get("PYTHONPATH"),
                "exit_code": 0,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
