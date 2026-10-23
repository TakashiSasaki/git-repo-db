"""Repeat immutable production operations across source154/155 and both wheels."""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ARTIFACTS = Path("/workspace/pr155-review-artifacts")
RUNTIME = Path("/workspace/pr155-review-runtime/bin/python")


def main():
    results = []
    for label, interpreter, source in (
        ("source155", RUNTIME, ROOT / "src"),
        ("source154", RUNTIME, ARTIFACTS / "source154/src"),
        ("direct", ARTIFACTS / "distribution/direct-venv/bin/python", None),
        ("derived", ARTIFACTS / "distribution/derived-venv/bin/python", None),
    ):
        for script, prefix in (("study.py", ""), ("store_case.py", "store-")):
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            if source is not None:
                env["PYTHONPATH"] = str(source)
            output = HERE / (prefix + label + ".json")
            command = [str(interpreter), str(HERE / script), "--output", str(output)]
            start = time.time()
            completed = subprocess.run(
                command, cwd="/tmp", env=env, capture_output=True, text=True
            )
            results.append(
                dict(
                    label=label,
                    command=command,
                    pythonpath=env.get("PYTHONPATH"),
                    script_sha256=hashlib.sha256(
                        (HERE / script).read_bytes()
                    ).hexdigest(),
                    observer_sha256=hashlib.sha256(
                        (HERE / "study.py").read_bytes()
                    ).hexdigest(),
                    started_unix=start,
                    ended_unix=time.time(),
                    exit=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    output_sha256=hashlib.sha256(output.read_bytes()).hexdigest()
                    if output.exists()
                    else None,
                )
            )
            (HERE / "executions.json").write_text(json.dumps(results, indent=2) + "\n")
            print(label, script, completed.returncode, flush=True)
            if completed.returncode:
                raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
