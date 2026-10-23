"""Exercise the complete compressed-bundle limit and existing receipt contract."""

import base64
import contextlib
import hashlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import emit_ci_evidence as emitter

ROOT = Path(__file__).resolve().parents[2]
LIMIT = 2_097_152
REAL_ZIP_FILE = zipfile.ZipFile


class ReceiptTests(unittest.TestCase):
    def emit(self, payload, target_size=None):
        """Pad a real, complete DEFLATED ZIP, never its input or a mocked len."""
        bundles = []

        class SizedZip(REAL_ZIP_FILE):
            def __exit__(archive, *exception):
                buffer = archive.fp
                result = super().__exit__(*exception)
                if exception[0] is None:
                    if target_size is not None:
                        padding = target_size - len(buffer.getvalue())
                        self.assertTrue(0 <= padding <= 65_535, padding)
                        with REAL_ZIP_FILE(buffer, "a") as finalized:
                            finalized.comment = b"p" * padding
                    bundles.append(buffer.getvalue())
                return result

        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            evidence = Path("artifacts/access-registry/result.log")
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(payload)
            runtime = Path("artifacts/runtime/selected.json")
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b'{"synthetic": true}\n')
            for excluded in ("source", "from-sdist", "outside", "test-venv"):
                path = evidence.parent / excluded / "excluded.log"
                path.parent.mkdir()
                path.write_text("not a log receipt")
            before = {
                p: p.read_bytes() for p in Path("artifacts").rglob("*") if p.is_file()
            }
            stdout = io.StringIO()
            with (
                patch.object(emitter.zipfile, "ZipFile", SizedZip),
                patch.object(emitter.subprocess, "check_output", return_value="a" * 40),
                patch.dict(os.environ, GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="1"),
                contextlib.redirect_stdout(stdout),
            ):
                try:
                    emitter.main()
                except SystemExit as error:
                    outcome = error.code
                else:
                    outcome = 0
            self.assertEqual(
                before,
                {
                    p: p.read_bytes()
                    for p in Path("artifacts").rglob("*")
                    if p.is_file()
                },
            )
        self.assertEqual(len(bundles), 1)
        body = bundles[0]
        if target_size is not None:
            self.assertEqual(len(body), target_size)
        with REAL_ZIP_FILE(io.BytesIO(body)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertTrue(
                all(i.compress_type == zipfile.ZIP_DEFLATED for i in archive.infolist())
            )
        return outcome, stdout.getvalue(), body

    def verify_receipt(self, output, body):
        digest = hashlib.sha256(body).hexdigest()
        lines = output.splitlines()
        self.assertEqual(lines[0], f"CI_RECEIPTS_BEGIN_V1 {digest} {len(body)}")
        self.assertEqual(lines[-1], f"CI_RECEIPTS_END_V1 {digest}")
        chunks = []
        for line in lines[1:-1]:
            marker, chunk = line.split(" ")
            self.assertEqual(marker, "CI_RECEIPTS_DATA_V1")
            self.assertLessEqual(len(chunk), 120)
            chunks.append(chunk)
        self.assertEqual(base64.b64decode("".join(chunks), validate=True), body)
        with REAL_ZIP_FILE(io.BytesIO(body)) as archive:
            index = json.loads(archive.read("receipt-index.json"))
            self.assertEqual(
                set(index), set(archive.namelist()) - {"receipt-index.json"}
            )
            for name, entry in index.items():
                data = archive.read(name)
                self.assertEqual(entry["bytes"], len(data))
                self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(
                json.loads(archive.read("receipt-binding.json")),
                {
                    "head": "a" * 40,
                    "tree": "a" * 40,
                    "run_id": "123",
                    "run_attempt": "1",
                },
            )

    def boundary(self, size, allowed):
        payload = random.Random(0).randbytes(size - 8192)
        outcome, output, body = self.emit(payload, size)
        if allowed:
            self.assertEqual(outcome, 0)
            self.verify_receipt(output, body)
        else:
            self.assertNotEqual(outcome, 0)
            self.assertIn("2 MiB", str(outcome))
            self.assertIn("uploaded GitHub Actions artifact", str(outcome))
            self.assertEqual(output, "")

    def test_below_limit(self):
        self.boundary(LIMIT - 1, allowed=True)

    def test_exact_limit(self):
        self.boundary(LIMIT, allowed=True)

    def test_one_byte_over_limit(self):
        self.boundary(LIMIT + 1, allowed=False)

    def test_audit_counterexample(self):
        self.boundary(2_323_560, allowed=False)

    def test_complete_receipt_and_compressed_not_expanded_limit(self):
        # Expanded evidence exceeds the cap, but the complete ZIP is small.
        outcome, output, body = self.emit(b"compressible\n" * LIMIT)
        self.assertEqual(outcome, 0)
        self.assertLess(len(body), LIMIT)
        self.verify_receipt(output, body)

    def test_cli_rejection_has_no_stdout_and_retains_artifact_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", directory], check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Synthetic",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-q",
                    "--allow-empty",
                    "-m",
                    "synthetic receipt test",
                ],
                cwd=root,
                check=True,
            )
            path = root / "artifacts/access-registry/result.log"
            path.parent.mkdir(parents=True)
            payload = random.Random(0).randbytes(2_323_560)
            path.write_bytes(payload)
            result = subprocess.run(
                [sys.executable, str(Path(emitter.__file__).resolve())],
                cwd=root,
                env=dict(os.environ, GITHUB_RUN_ID="123", GITHUB_RUN_ATTEMPT="1"),
                capture_output=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b"")
            self.assertIn(b"uploaded GitHub Actions artifact", result.stderr)
            self.assertEqual(path.read_bytes(), payload)

    def test_artifact_upload_runs_even_when_emitter_fails(self):
        workflow = (ROOT / ".github/workflows/access-registry.yml").read_text()
        emit_step = workflow.split(
            "- name: Emit indexed verification receipts to job log\n"
        )[1]
        emit_step, upload_step = emit_step.split(
            "- name: Save focused verification evidence\n"
        )
        self.assertIn("if: always()", emit_step)
        self.assertIn("run: python scripts/emit_ci_evidence.py", emit_step)
        self.assertIn("if: always()", upload_step)
        self.assertIn("uses: actions/upload-artifact@", upload_step)
        self.assertIn("name: access-registry-verification", upload_step)
        self.assertIn("artifacts/access-registry/", upload_step)
        self.assertIn("artifacts/runtime/", upload_step)


if __name__ == "__main__":
    unittest.main()
