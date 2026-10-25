"""Fail-closed distribution integrity and same-invocation runtime binding."""

import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import threading
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
            # Model only source-ID drift; bootstrap setup-python may configure a
            # loader path. Loader rejection has its own independent test below.
            measured["loader_environment"] = {
                name: None for name in measured["loader_environment"]
            }
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


def build_archive(path, members):
    """Write a gzip tar from (name, kind, payload) tuples without trusting its names."""
    with tarfile.open(path, "w:gz") as tar:
        for name, kind, payload in members:
            member = tarfile.TarInfo(name)
            if kind == "file":
                member.size = len(payload)
                member.mode = 0o755
                tar.addfile(member, io.BytesIO(payload))
                continue
            member.type = {
                "dir": tarfile.DIRTYPE,
                "symlink": tarfile.SYMTYPE,
                "hardlink": tarfile.LNKTYPE,
                "fifo": tarfile.FIFOTYPE,
                "device": tarfile.CHRTYPE,
            }[kind]
            member.linkname = payload or ""
            tar.addfile(member)
    return Path(path)


GOOD_MEMBERS = [
    ("python/bin/python3.12", "file", b"interpreter"),
    ("python/bin/python3", "symlink", "python3.12"),
    ("python/lib/data.txt", "file", b"data"),
]


class LocalInstallCase(unittest.TestCase):
    """Isolated manifest, home, mocked download and smoke for destructive tests."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(self.force_cleanup, Path(temporary.name))
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.downloads = 0
        self.archive = build_archive(self.root / "source.tar.gz", GOOD_MEMBERS)
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.write_manifest(self.digest)
        patches = [
            patch.object(runtime, "MANIFEST", self.root / "manifest.json"),
            patch.object(runtime.urllib.request, "urlretrieve", self.download),
            patch.object(runtime.platform, "system", return_value="Linux"),
            patch.object(runtime.platform, "machine", return_value="x86_64"),
            patch.object(runtime, "smoke", return_value=self.identity()),
            patch.dict(os.environ, {}, clear=False),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        for name in ("GITHUB_PATH", "GITHUB_ENV"):
            os.environ.pop(name, None)

    @staticmethod
    def force_cleanup(root):
        for current, directories, _files in os.walk(root):
            Path(current).chmod(0o700)

    @staticmethod
    def identity(python="3.12.15"):
        return {"python": python, "base": "/unused", "sqlite_version": "3.53.1"}

    def write_manifest(self, digest, **extra):
        manifest = {
            "python": "3.12.15",
            "release": "test",
            "platform": "x86_64-unknown-linux-gnu",
            "url": "https://example.invalid/python.tar.gz",
            "sha256": digest,
            **extra,
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest))

    def download(self, url, path):
        self.downloads += 1
        shutil.copyfile(self.archive, path)

    def provision(self, **options):
        return runtime.provision(self.home, **options)

    def staging(self):
        return sorted(self.home.glob(".staging-*"))


class SafeExtractionTests(LocalInstallCase):
    def extract(self, members):
        archive = build_archive(self.root / "case.tar.gz", members)
        target = self.root / "target"
        target.mkdir(exist_ok=True)
        runtime.safe_extract(archive, target)
        return target

    def assert_refused(self, members, message=None):
        with self.assertRaisesRegex(ValueError, message or ".") as caught:
            self.extract(members)
        self.assertIn(type(caught.exception), (ValueError,))
        self.assertFalse((self.root / "evil").exists())

    def test_regular_tree_with_links_is_extracted(self):
        target = self.extract(GOOD_MEMBERS)
        self.assertEqual((target / "python/lib/data.txt").read_bytes(), b"data")
        self.assertEqual(os.readlink(target / "python/bin/python3"), "python3.12")
        self.assertTrue(os.access(target / "python/bin/python3.12", os.X_OK))

    def test_path_traversal_absolute_and_foreign_roots_are_refused(self):
        for name in (
            "python/../../evil",
            "../evil",
            "/tmp/evil",
            "other/file",
            "python/..\\evil",
        ):
            with self.subTest(name=name):
                self.assert_refused([(name, "file", b"x")])

    def test_escaping_or_absolute_links_are_refused(self):
        for link in ("../../../evil", "/etc/passwd", "../../evil", ""):
            with self.subTest(link=link):
                self.assert_refused([("python/bin/link", "symlink", link)])

    def test_hardlink_to_outside_member_is_refused(self):
        self.assert_refused([("python/bin/link", "hardlink", "../../evil")])

    def test_member_below_archive_link_is_refused(self):
        self.assert_refused(
            [
                ("python/bin", "symlink", "../.."),
                ("python/bin/evil", "file", b"x"),
            ]
        )

    def test_special_files_and_duplicates_are_refused(self):
        self.assert_refused([("python/dev", "device", None)], "member type")
        self.assert_refused([("python/pipe", "fifo", None)], "member type")
        self.assert_refused(
            [("python/a", "file", b"1"), ("python/a", "file", b"2")], "Duplicate"
        )

    def test_unsafe_archive_leaves_no_partial_extraction_or_exports(self):
        members = [("python/ok", "file", b"x"), ("python/../../evil", "file", b"x")]
        self.archive = build_archive(self.root / "source.tar.gz", members)
        self.write_manifest(hashlib.sha256(self.archive.read_bytes()).hexdigest())
        os.environ["GITHUB_PATH"] = str(self.root / "path")
        with self.assertRaises(ValueError):
            runtime.install(self.root / "hosted")
        self.assertEqual(list((self.root / "hosted").iterdir()), [])
        self.assertFalse((self.root / "path").exists())


class PlatformSelectionTests(LocalInstallCase):
    def test_committed_manifest_keeps_hosted_x86_64_and_pins_aarch64(self):
        manifest = json.loads((Path(runtime.__file__).with_suffix(".json")).read_text())
        self.assertEqual(manifest["platform"], "x86_64-unknown-linux-gnu")
        self.assertEqual(
            manifest["sha256"],
            "6d7521138fd33afddc1ccd08abb007d9a2829e38117c2576f9efdc0ec73ce772",
        )
        arm = manifest["additional_platforms"]["aarch64-unknown-linux-gnu"]
        self.assertRegex(arm["sha256"], r"^[0-9a-f]{64}$")
        self.assertIn(manifest["release"], arm["url"])
        self.assertTrue(arm["url"].startswith("https://github.com/astral-sh/"))

    def test_additional_platform_is_selected_only_for_its_host(self):
        self.write_manifest(
            self.digest,
            additional_platforms={
                "aarch64-unknown-linux-gnu": {
                    "url": "https://example.invalid/arm.tar.gz",
                    "sha256": "1" * 64,
                }
            },
        )
        manifest = json.loads((self.root / "manifest.json").read_text())
        self.assertEqual(runtime.select_distribution(manifest)["sha256"], self.digest)
        with patch.object(runtime.platform, "machine", return_value="aarch64"):
            chosen = runtime.select_distribution(manifest)
        self.assertEqual(chosen["sha256"], "1" * 64)
        self.assertEqual(chosen["platform"], "aarch64-unknown-linux-gnu")

    def test_unsupported_hosts_are_reported_without_substitution(self):
        for system, machine in (
            ("Linux", "riscv64"),
            ("Darwin", "arm64"),
            ("Windows", "AMD64"),
        ):
            with self.subTest(system=system, machine=machine):
                with (
                    patch.object(runtime.platform, "system", return_value=system),
                    patch.object(runtime.platform, "machine", return_value=machine),
                ):
                    with self.assertRaisesRegex(
                        runtime.UnsupportedPlatform, "not supported"
                    ):
                        self.provision()
                    with self.assertRaises(runtime.UnsupportedPlatform):
                        runtime.install(self.root / "hosted")
        self.assertFalse(self.home.exists())
        self.assertEqual(self.downloads, 0)

    def test_host_missing_from_manifest_is_refused(self):
        with patch.object(runtime.platform, "machine", return_value="aarch64"):
            with self.assertRaisesRegex(runtime.UnsupportedPlatform, "no aarch64"):
                self.provision()
        self.assertEqual(self.downloads, 0)

    def test_manifest_with_invalid_digest_or_insecure_url_is_refused(self):
        for change in ({"sha256": "XYZ"}, {"url": "http://example.invalid/p.tgz"}):
            with self.subTest(change=change):
                self.write_manifest(self.digest, **change)
                with self.assertRaises(ValueError):
                    self.provision()
        self.assertEqual(self.downloads, 0)


class ProvisionTests(LocalInstallCase):
    def test_install_is_content_addressed_read_only_and_ready(self):
        result = self.provision()
        final = self.home / self.digest
        self.assertEqual(result["directory"], str(final))
        self.assertEqual(result["executable"], str(final / "python/bin/python3"))
        self.assertFalse(result["reused"])
        ready = json.loads((final / "ready.json").read_text())
        self.assertEqual(ready["archive_sha256"], self.digest)
        self.assertEqual(
            ready["tree_sha256"], runtime.tree_digest(final / "python")["sha256"]
        )
        self.assertFalse(os.access(final / "python/lib/data.txt", os.W_OK))
        self.assertEqual(self.staging(), [])

    def test_repeated_invocation_reuses_without_download_or_replacement(self):
        first = self.provision()
        inode = (self.home / self.digest).stat().st_ino
        again = self.provision()
        self.assertTrue(again["reused"])
        self.assertEqual(self.downloads, 1)
        self.assertEqual((self.home / self.digest).stat().st_ino, inode)
        self.assertEqual(first["tree_sha256"], again["tree_sha256"])

    def test_offline_never_downloads_but_reuses_a_verified_install(self):
        with self.assertRaisesRegex(RuntimeError, "offline"):
            self.provision(offline=True)
        self.assertEqual(self.downloads, 0)
        self.provision()
        self.assertTrue(self.provision(offline=True)["reused"])
        self.assertEqual(self.downloads, 1)

    def test_invalid_archive_digest_is_refused_and_leaves_nothing(self):
        self.write_manifest("0" * 64)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.provision()
        self.assertFalse((self.home / ("0" * 64)).exists())
        self.assertEqual(self.staging(), [])

    def test_truncated_archive_with_matching_digest_is_refused(self):
        data = self.archive.read_bytes()[:-40]
        self.archive.write_bytes(data)
        self.write_manifest(hashlib.sha256(data).hexdigest())
        with self.assertRaises((tarfile.TarError, EOFError, OSError, ValueError)):
            self.provision()
        self.assertFalse((self.home / hashlib.sha256(data).hexdigest()).exists())
        self.assertEqual(self.staging(), [])

    def test_corrupted_archive_bytes_fail_the_digest_check(self):
        def corrupt(url, path):
            data = bytearray(self.archive.read_bytes())
            data[len(data) // 2] ^= 0xFF
            Path(path).write_bytes(bytes(data))

        with patch.object(runtime.urllib.request, "urlretrieve", corrupt):
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                self.provision()
        self.assertEqual(self.staging(), [])

    def test_unsafe_archive_is_refused_before_publication(self):
        self.archive = build_archive(
            self.root / "source.tar.gz", [("python/x", "symlink", "../../..")]
        )
        self.write_manifest(hashlib.sha256(self.archive.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.provision()
        self.assertEqual([p.name for p in self.home.iterdir() if p.name[0] != "."], [])
        self.assertEqual(self.staging(), [])

    def test_wrong_reported_python_is_not_published(self):
        with patch.object(runtime, "smoke", return_value=self.identity("3.11.0")):
            with self.assertRaisesRegex(ValueError, "expected 3.12.15"):
                self.provision()
        self.assertFalse((self.home / self.digest).exists())
        self.assertEqual(self.staging(), [])

    def test_interrupted_download_publishes_nothing_and_next_run_recovers(self):
        def interrupted(url, path):
            Path(path).write_bytes(b"partial")
            raise KeyboardInterrupt

        with patch.object(runtime.urllib.request, "urlretrieve", interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.provision()
        self.assertFalse((self.home / self.digest).exists())
        self.assertEqual(self.staging(), [])
        self.assertFalse(self.provision()["reused"])

    def test_stale_staging_from_a_killed_process_is_removed_under_the_lock(self):
        stale = self.home / f".staging-{self.digest}-99999-dead"
        (stale / "python").mkdir(parents=True)
        (stale / "python/partial").write_text("half")
        stale.chmod(0o500)
        self.provision()
        self.assertFalse(stale.exists())

    def test_partial_or_tampered_installation_is_refused_not_replaced(self):
        final = self.home / self.digest
        final.mkdir(parents=True)
        (final / "python").mkdir()
        with self.assertRaisesRegex(RuntimeError, "Refusing the unverified"):
            self.provision()
        self.assertEqual(self.downloads, 0)
        self.assertEqual(sorted(p.name for p in final.iterdir()), ["python"])
        shutil.rmtree(final)

        self.provision()
        victim = final / "python/lib/data.txt"
        (final / "python/lib").chmod(0o755)
        victim.chmod(0o644)
        victim.write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "differ from the verified tree"):
            self.provision()
        self.assertEqual(victim.read_bytes(), b"tampered")
        self.assertEqual(self.downloads, 1)

    def test_shared_or_foreign_writable_locations_are_not_trusted(self):
        self.provision()
        self.home.chmod(0o777)
        with self.assertRaisesRegex(RuntimeError, "writable by other users"):
            self.provision()
        self.home.chmod(0o700)
        final = self.home / self.digest
        final.chmod(0o757)
        with self.assertRaisesRegex(RuntimeError, "writable by other users"):
            self.provision()
        final.chmod(0o500)
        with patch.object(runtime.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaisesRegex(RuntimeError, "owned by this user"):
                self.provision()
        self.assertEqual(self.downloads, 1)

    def test_ready_record_for_another_distribution_is_refused(self):
        self.provision()
        final = self.home / self.digest
        final.chmod(0o700)
        (final / "ready.json").chmod(0o600)
        ready = json.loads((final / "ready.json").read_text())
        ready["archive_sha256"] = "2" * 64
        (final / "ready.json").write_text(json.dumps(ready))
        with self.assertRaisesRegex(RuntimeError, "does not match the manifest"):
            self.provision()

    def test_installed_python_that_reports_another_version_is_refused(self):
        self.provision()
        with patch.object(runtime, "smoke", return_value=self.identity("3.13.0")):
            with self.assertRaisesRegex(RuntimeError, "not the manifest"):
                self.provision()

    def test_concurrent_bootstraps_install_once(self):
        gate = threading.Event()

        def slow(url, path):
            gate.wait(0.5)
            self.download(url, path)

        results, errors = [], []

        def worker():
            try:
                results.append(self.provision())
            except Exception as error:  # Reported by the assertion below.
                errors.append(error)

        with patch.object(runtime.urllib.request, "urlretrieve", slow):
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(self.downloads, 1)
        self.assertEqual(
            sorted(r["reused"] for r in results), [False, True, True, True]
        )
        self.assertEqual(self.staging(), [])

    def test_held_lock_blocks_then_times_out_without_modifying_anything(self):
        self.home.mkdir()
        with runtime.InstallLock(self.home / f".lock-{self.digest}", 5):
            with self.assertRaises(TimeoutError):
                self.provision(lock_timeout=0.3)
        self.assertFalse((self.home / self.digest).exists())


class HostedInstallationTests(LocalInstallCase):
    def test_hosted_install_exports_only_when_github_files_exist(self):
        output = io.StringIO()
        with patch("sys.stdout", output):
            runtime.install(self.root / "local-style")
        self.assertEqual(
            (self.root / "local-style/python/lib/data.txt").read_bytes(), b"data"
        )
        self.assertFalse((self.root / "env").exists())

    def test_hosted_install_exports_python_path_and_environment(self):
        os.environ["GITHUB_PATH"] = str(self.root / "path")
        os.environ["GITHUB_ENV"] = str(self.root / "env")
        with patch("sys.stdout", io.StringIO()):
            runtime.install(self.root / "selected")
        python = self.root / "selected/python/bin/python3"
        exported = (self.root / "env").read_text()
        self.assertIn(f"UV_PYTHON={python}\n", exported)
        self.assertIn(f"CI_PRODUCT_PYTHON={python}\n", exported)
        self.assertIn("UV_PYTHON_DOWNLOADS=never\n", exported)
        self.assertEqual((self.root / "path").read_text(), f"{python.parent}\n")


class ProbeBindingTests(unittest.TestCase):
    def measured(self, **changes):
        measured = runtime.identity()
        measured["loader_environment"] = {
            name: None for name in measured["loader_environment"]
        }
        measured.update(changes)
        return measured

    def run_probe(self, directory, measured, **options):
        capabilities = options.pop(
            "capabilities", ({"wal": "passed"}, "/product/access_schema.py")
        )
        with (
            patch.object(runtime, "identity", return_value=measured),
            patch.object(runtime, "capability_checks", return_value=capabilities),
            patch.object(runtime, "repository_identity", return_value=None),
        ):
            runtime.probe(Path(directory) / "actual.json", **options)
        return json.loads((Path(directory) / "actual.json").read_text())

    def test_successful_probe_records_distribution_capabilities_and_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_probe(directory, self.measured())
        self.assertEqual(result["product_safety_and_capabilities"], "passed")
        self.assertEqual(result["capabilities"], {"wal": "passed"})
        self.assertIn("distribution", result)
        self.assertIn("repository", result)

    def test_missing_safety_capability_is_recorded_then_refused(self):
        failing = ({"wal": "failed: no WAL", "strict": "passed"}, "/product.py")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "no WAL"):
                self.run_probe(directory, self.measured(), capabilities=failing)
            recorded = json.loads((Path(directory) / "actual.json").read_text())
        self.assertEqual(recorded["product_safety_and_capabilities"], "failed")
        self.assertEqual(recorded["capabilities"]["wal"], "failed: no WAL")

    def test_interpreter_drift_after_explicit_selection_is_refused(self):
        measured = self.measured(base_executable="/usr/bin/python3.12")
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"CI_PRODUCT_PYTHON": f"{directory}/python"}):
                with self.assertRaisesRegex(RuntimeError, "changed after explicit"):
                    self.run_probe(directory, measured)

    def test_sqlite_binding_drift_against_the_reference_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            measured = self.measured()
            for field, other in (
                ("sqlite_module", "/elsewhere/_sqlite3.so"),
                ("sqlite_module_sha256", "9" * 64),
                ("sqlite_mappings", ["/usr/lib/libsqlite3.so.0"]),
            ):
                with self.subTest(field=field):
                    reference = Path(directory) / "reference.json"
                    reference.write_text(json.dumps({**measured, field: other}))
                    with self.assertRaisesRegex(RuntimeError, field):
                        self.run_probe(directory, measured, reference=reference)

    def test_system_sqlite_outside_the_selected_distribution_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "dist/python"
            (root / "bin").mkdir(parents=True)
            selected = root / "bin/python3"
            selected.write_bytes(b"x")
            for field, value, message in (
                (
                    "sqlite_mappings",
                    ["/usr/lib/libsqlite3.so.0"],
                    "system SQLite library",
                ),
                (
                    "sqlite_module",
                    "/usr/lib/python3/_sqlite3.so",
                    "outside the selected",
                ),
            ):
                measured = self.measured(base_executable=str(selected))
                measured["sqlite_module"] = str(selected)
                measured[field] = value
                with self.subTest(field=field):
                    with patch.dict(os.environ, {"CI_PRODUCT_PYTHON": str(selected)}):
                        with self.assertRaisesRegex(RuntimeError, message):
                            self.run_probe(directory, measured)

    def test_built_in_sqlite_without_module_file_is_accepted_in_the_distribution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "dist/python"
            (root / "bin").mkdir(parents=True)
            selected = root / "bin/python3"
            selected.write_bytes(b"x")
            measured = self.measured(
                base_executable=str(selected),
                sqlite_module=str(selected),
                sqlite_module_origin="built-in",
                sqlite_mappings=[],
            )
            with patch.dict(os.environ, {"CI_PRODUCT_PYTHON": str(selected)}):
                result = self.run_probe(directory, measured)
        self.assertEqual(result["sqlite_module_origin"], "built-in")

    @unittest.skipUnless(
        sqlite3.sqlite_version_info >= (3, 51, 3),
        "needs the product-capable SQLite this test is meant to protect",
    )
    def test_real_capabilities_pass_on_a_product_capable_runtime(self):
        import sys

        if importlib.util.find_spec("repo_catalog") is None:
            sys.path.insert(0, str(runtime.ROOT / "src"))
        with tempfile.TemporaryDirectory() as directory:
            results, _module = runtime.capability_checks(Path(directory))
        self.assertEqual(set(results.values()), {"passed"}, results)
        self.assertEqual(
            set(results),
            {
                "access_runtime_factory",
                "p1_runtime_factory",
                "access_initialize",
                "thread_safety",
                "wal",
                "strict",
                "json",
                "fts5_trigram",
                "integrity_and_transaction",
            },
        )


if __name__ == "__main__":
    unittest.main()
