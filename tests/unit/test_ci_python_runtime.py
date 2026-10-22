"""Fail-closed distribution integrity and same-invocation runtime binding."""

import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ci_python_runtime as runtime


class ProductPythonTests(unittest.TestCase):
    def test_install_checks_whole_distribution_before_extracting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {"url": "https://example.invalid/python", "sha256": "0" * 64}
                )
            )

            def download(url, path):
                path.write_bytes(b"tampered distribution")

            with (
                patch.object(runtime, "MANIFEST", manifest),
                patch.object(runtime.urllib.request, "urlretrieve", download),
                patch.object(runtime.platform, "system", return_value="Linux"),
                patch.object(runtime.platform, "machine", return_value="x86_64"),
            ):
                with self.assertRaisesRegex(ValueError, "digest mismatch"):
                    runtime.install(root / "selected")
            self.assertEqual(list((root / "selected").iterdir()), [])

    def test_install_exports_exact_python_and_disables_implicit_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "python.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                member = tarfile.TarInfo("python/bin/python3")
                member.size = 6
                tar.addfile(member, io.BytesIO(b"python"))
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "url": "https://example.invalid/python",
                        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    }
                )
            )

            def download(url, path):
                path.write_bytes(archive.read_bytes())

            with (
                patch.object(runtime, "MANIFEST", manifest),
                patch.object(runtime.urllib.request, "urlretrieve", download),
                patch.dict(
                    os.environ,
                    {
                        "GITHUB_PATH": str(root / "path"),
                        "GITHUB_ENV": str(root / "env"),
                    },
                ),
                patch.object(runtime.platform, "system", return_value="Linux"),
                patch.object(runtime.platform, "machine", return_value="x86_64"),
            ):
                runtime.install(root / "selected")
            self.assertEqual(
                (root / "selected/python/bin/python3").read_bytes(), b"python"
            )
            self.assertIn(
                f"UV_PYTHON={root}/selected/python/bin/python3\n",
                (root / "env").read_text(),
            )
            self.assertIn("UV_PYTHON_DOWNLOADS=never\n", (root / "env").read_text())
            self.assertEqual(
                (root / "path").read_text(), f"{root}/selected/python/bin\n"
            )

    def test_changed_runtime_is_rejected_before_product_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            measured = runtime.identity()
            original = dict(measured, sqlite_source_id="different invocation")
            (root / "reference.json").write_text(json.dumps(original))
            with patch.object(runtime, "identity", return_value=measured):
                with self.assertRaisesRegex(RuntimeError, "sqlite_source_id"):
                    runtime.probe(root / "actual.json", root / "reference.json")
            self.assertEqual(json.loads((root / "actual.json").read_text()), measured)

    def test_loader_override_is_rejected_and_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "runtime.json"
            measured = runtime.identity()
            measured["loader_environment"]["LD_PRELOAD"] = "/unexpected/library"
            with patch.object(runtime, "identity", return_value=measured):
                with self.assertRaisesRegex(RuntimeError, "loader override"):
                    runtime.probe(target)
            self.assertEqual(json.loads(target.read_text()), measured)


if __name__ == "__main__":
    unittest.main()
