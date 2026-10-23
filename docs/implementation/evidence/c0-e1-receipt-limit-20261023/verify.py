"""Replay the focused regressions against the current or a historical emitter."""

import argparse
import hashlib
import importlib.util
import io
import json
import platform
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref")
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    test_path = ROOT / "tests/unit/test_emit_ci_evidence.py"
    source = (
        subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:scripts/emit_ci_evidence.py"],
            cwd=ROOT,
        )
        if args.baseline_ref
        else (ROOT / "scripts/emit_ci_evidence.py").read_bytes()
    )
    tests = load("receipt_tests", test_path)
    samples = []
    original = tests.ReceiptTests.emit

    def measured(test, payload, target_size=None):
        outcome, output, body = original(test, payload, target_size)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            expanded = sum(info.file_size for info in archive.infolist())
        samples.append(
            {
                "test": test.id(),
                "requested_zip_bytes": target_size,
                "measured_zip_bytes": len(body),
                "zip_sha256": hashlib.sha256(body).hexdigest(),
                "expanded_member_bytes": expanded,
                "exit_code": 0 if outcome == 0 else 1,
                "diagnostic": None if outcome == 0 else str(outcome),
                "stdout_bytes": len(output.encode()),
                "stdout_sha256": hashlib.sha256(output.encode()).hexdigest(),
                "has_begin": "CI_RECEIPTS_BEGIN_V1" in output,
                "has_end": "CI_RECEIPTS_END_V1" in output,
            }
        )
        return outcome, output, body

    tests.ReceiptTests.emit = measured
    log = io.StringIO()
    with tempfile.TemporaryDirectory() as directory:
        emitter_path = Path(directory) / "emit_ci_evidence.py"
        emitter_path.write_bytes(source)
        tests.emitter = load("measured_emitter", emitter_path)
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(tests)
        )
    record = {
        "command": [sys.executable, *sys.argv],
        "cwd": str(Path.cwd()),
        "baseline_ref": args.baseline_ref,
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "tree": subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
        ).strip(),
        "working_tree_overlay": True,
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_source_id": sqlite3.connect(":memory:")
        .execute("select sqlite_source_id()")
        .fetchone()[0],
        "emitter_sha256": hashlib.sha256(source).hexdigest(),
        "test_sha256": hashlib.sha256(test_path.read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skips": len(result.skipped),
        "exit_code": 0 if result.wasSuccessful() else 1,
        "samples": samples,
    }
    args.output_prefix.with_suffix(".log").write_text(log.getvalue())
    args.output_prefix.with_suffix(".json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
    print(log.getvalue(), end="")
    return record["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
