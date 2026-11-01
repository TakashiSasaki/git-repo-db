"""Local bootstrap orchestration and verified-launcher behavior with fake tools.

No test downloads anything, contacts a package index or touches the user's real
installation or ``.venv``; every command runner, provisioner and interpreter is
replaced by a temporary-directory fixture.
"""

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import ci_python_runtime as runtime
from scripts import local_env
from scripts import setup_local_python as setup

PYTHON = "3.12.15"


class Project:
    """A fake checkout, installed distribution and command runner."""

    def __init__(self, directory):
        base = Path(directory)
        self.root = base / "checkout"
        self.root.mkdir()
        (self.root / "uv.lock").write_text("lock\n")
        (self.root / "pyproject.toml").write_text("[project]\n")
        self.directory = base / "home" / ("a" * 64)
        binaries = self.directory / "python/bin"
        binaries.mkdir(parents=True)
        (binaries / "python3.12").write_bytes(b"interpreter")
        (binaries / "python3.12").chmod(0o755)
        (binaries / "python3").symlink_to("python3.12")
        self.selected = binaries / "python3"
        self.base = (binaries / "python3.12").resolve()
        self.tree = runtime.tree_digest(self.directory / "python")["sha256"]
        (self.directory / "ready.json").write_text(
            json.dumps({"tree_sha256": self.tree})
        )
        self.calls = []
        self.fail = set()
        self.mutate_lock = False
        self.probe_changes = {}
        self.venv_base = self.selected

    def provision(self, home=None, *, offline=False):
        self.calls.append(["provision", offline])
        if "provision" in self.fail:
            raise RuntimeError("Refusing the unverified Python installation")
        return {
            "selection": {"python": PYTHON, "sha256": "a" * 64, "platform": "x"},
            "directory": str(self.directory),
            "executable": str(self.selected),
            "archive_sha256": "a" * 64,
            "tree_sha256": self.tree,
            "ready": {"tree_sha256": self.tree},
            "reused": False,
        }

    def runtime(self, **changes):
        value = {
            "python": PYTHON,
            "executable": str(self.selected),
            "base_executable": str(self.base),
            "base_executable_sha256": runtime.sha256_file(self.base),
            "sqlite_version": "3.53.1",
            "sqlite_source_id": "source",
            "product_safety_and_capabilities": "passed",
            "child_runtime_identity": "passed",
            "capabilities": {"wal": "passed"},
            "repository": {"commit": "c" * 40, "tree": "t" * 40, "dirty": False},
        }
        value.update(changes)
        return value

    def venv_view(self, venv):
        resolved = Path(os.path.realpath(venv / "bin/python"))
        return {"base": str(resolved), "executable": str(venv / "bin/python")}

    def create_venv(self, base=None):
        venv = self.root / ".venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = x\n")
        (venv / "bin/python").symlink_to(base or self.selected)

    def __call__(self, argv, *, environment, cwd, timeout=3600):
        argv = [str(part) for part in argv]
        self.calls.append(argv)
        done = lambda code=0, out="", err="": SimpleNamespace(  # noqa: E731
            returncode=code, stdout=out, stderr=err
        )
        name = Path(argv[0]).name
        if argv[1:] == ["--version"]:
            return done(out=f"{name} 1.0\n")
        if name == "git":
            return done(out="" if argv[1] == "status" else "d" * 40 + "\n")
        if "probe" in argv:
            output = Path(argv[argv.index("probe") + 1])
            label = output.stem
            if label in self.fail:
                return done(1, err=f"{label} refused")
            output.parent.mkdir(parents=True, exist_ok=True)
            changes = self.probe_changes.get(label, {})
            output.write_text(json.dumps(self.runtime(**changes)))
            return done()
        if argv[1] == "sync":
            assert environment["UV_PYTHON"] == str(self.selected)
            assert environment["UV_PYTHON_DOWNLOADS"] == "never"
            if "sync" in self.fail:
                return done(2, err="resolution failed")
            if not (self.root / ".venv").exists():
                self.create_venv()
            if self.mutate_lock:
                (self.root / "uv.lock").write_text("rewritten\n")
            return done(err=" + httpx==0.28.1\n")
        if argv[1].endswith("preflight_access.py"):
            if "preflight" in self.fail:
                return done(1, err="preflight refused")
            output = Path(argv[argv.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "executable": str(self.root / ".venv/bin/python"),
                        "locked_dependencies": {"httpx": "0.28.1"},
                        "sqlite": {"sqlite_version": "3.53.1"},
                    }
                )
            )
            return done()
        raise AssertionError(f"unexpected command {argv}")


class BootstrapCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Project(temporary.name)
        self.root = self.project.root
        environment = {
            k: v for k, v in os.environ.items() if k not in local_env.FORBIDDEN
        }
        for item in (
            patch.dict(os.environ, environment, clear=True),
            patch.object(setup, "run_command", self.project),
            patch.object(runtime, "provision", self.project.provision),
            patch.object(local_env, "venv_view", self.project.venv_view),
            patch.object(setup, "find_tool", lambda name: f"/fake/{name}"),
        ):
            item.start()
            self.addCleanup(item.stop)

    def bootstrap(self, *arguments):
        with (
            patch("sys.stdout", new_callable=io.StringIO),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            return setup.main(["--root", str(self.root), *arguments])

    def receipt(self):
        return json.loads((self.root / local_env.RECEIPT).read_text())

    def statuses(self):
        return {name: step["status"] for name, step in self.receipt()["steps"].items()}

    def assert_failed_at(self, step):
        receipt = self.receipt()
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failure"]["step"], step)
        states = self.statuses()
        index = list(setup.STEPS).index(step)
        for position, name in enumerate(setup.STEPS):
            expected = (
                "passed"
                if position < index
                else "failed"
                if position == index
                else "not_run"
            )
            self.assertEqual(states[name], expected, name)


class SuccessfulBootstrapTests(BootstrapCase):
    def test_workspace_metadata_is_bound_and_drift_requires_resynchronization(self):
        metadata = self.root / "packages/core/pyproject.toml"
        metadata.parent.mkdir(parents=True)
        metadata.write_text('[project]\nname = "repo-catalog-core"\n')
        self.assertEqual(self.bootstrap(), 0)
        self.assertIn("packages/core/pyproject.toml", self.receipt()["inputs"])
        metadata.write_text('[project]\nname = "modified-core"\n')
        with self.assertRaisesRegex(
            local_env.EnvironmentRefused, "core/pyproject.toml changed"
        ):
            local_env.verify_environment(self.root)

    def test_success_creates_verified_environment_and_passed_receipt(self):
        self.assertEqual(self.bootstrap(), 0)
        receipt = self.receipt()
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(set(self.statuses().values()), {"passed"})
        self.assertEqual(receipt["selected_python"], str(self.project.selected))
        self.assertEqual(receipt["runtime"]["sqlite_version"], "3.53.1")
        self.assertEqual(receipt["runtime_after_dependencies"]["python"], PYTHON)
        self.assertTrue(receipt["dependency_sync"]["inputs_unchanged"])
        self.assertEqual(receipt["virtual_environment"]["action"], "create")
        sync = next(c for c in self.project.calls if c[1:2] == ["sync"])
        self.assertEqual(
            sync[1:],
            [
                "sync",
                "--locked",
                "--group",
                "dev",
                "--python",
                str(self.project.selected),
            ],
        )
        self.assertEqual(
            local_env.verify_environment(self.root, deep=True)["status"], "passed"
        )

    def test_identity_is_verified_before_dependencies_are_installed(self):
        self.bootstrap()
        calls = [c for c in self.project.calls if c[0] != "provision"]
        order = [
            "selected.json" if any(a.endswith("selected.json") for a in c) else c[1]
            for c in calls
            if "probe" in c or c[1:2] == ["sync"]
        ]
        self.assertEqual(order[:2], ["selected.json", "sync"])

    def test_repeated_bootstrap_reuses_the_environment(self):
        self.assertEqual(self.bootstrap(), 0)
        link = os.readlink(self.root / ".venv/bin/python")
        config = (self.root / ".venv/pyvenv.cfg").read_bytes()
        self.assertEqual(self.bootstrap(), 0)
        self.assertEqual(self.receipt()["virtual_environment"]["action"], "reuse")
        self.assertEqual(os.readlink(self.root / ".venv/bin/python"), link)
        self.assertEqual((self.root / ".venv/pyvenv.cfg").read_bytes(), config)
        self.assertEqual((self.root / "uv.lock").read_text(), "lock\n")

    def test_offline_option_is_propagated_to_provisioning_and_sync(self):
        self.assertEqual(self.bootstrap("--offline"), 0)
        self.assertIn(["provision", True], self.project.calls)
        sync = next(c for c in self.project.calls if c[1:2] == ["sync"])
        self.assertIn("--offline", sync)


class FailClosedBootstrapTests(BootstrapCase):
    def test_unsupported_platform_fails_at_host_without_installing(self):
        with patch.object(runtime.platform, "machine", return_value="riscv64"):
            self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("host")
        self.assertIn("not supported", self.receipt()["failure"]["message"])
        self.assertEqual(self.project.calls, [])

    def test_missing_uv_fails_with_install_pointer_before_any_work(self):
        real = lambda name: None if name == "uv" else f"/fake/{name}"  # noqa: E731
        with patch.object(setup, "find_tool", real):
            self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("tools")
        self.assertIn("uv", self.receipt()["failure"]["message"])
        self.assertIn("docs.astral.sh", self.receipt()["failure"]["message"])
        self.assertFalse((self.root / ".venv").exists())

    def test_missing_git_fails(self):
        real = lambda name: None if name == "git" else f"/fake/{name}"  # noqa: E731
        with patch.object(setup, "find_tool", real):
            self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("tools")

    def test_dynamic_loader_override_is_refused(self):
        with patch.dict(os.environ, {"LD_PRELOAD": "/unexpected/library"}):
            self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("host")

    def test_refused_distribution_stops_before_environment_work(self):
        self.project.fail.add("provision")
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("provision")
        self.assertFalse((self.root / ".venv").exists())

    def test_failed_pre_dependency_probe_prevents_dependency_installation(self):
        self.project.fail.add("selected")
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("identity_before_dependencies")
        self.assertFalse(any(c[1:2] == ["sync"] for c in self.project.calls))

    def test_missing_safety_capability_in_probe_is_refused(self):
        self.project.probe_changes["selected"] = {
            "product_safety_and_capabilities": "failed"
        }
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("identity_before_dependencies")

    def test_child_identity_failure_is_refused(self):
        self.project.probe_changes["selected"] = {"child_runtime_identity": "failed"}
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("identity_before_dependencies")

    def test_interpreter_drift_between_selection_and_probe_is_refused(self):
        other = self.root / "other-python"
        other.write_bytes(b"other")
        self.project.probe_changes["selected"] = {
            "base_executable": str(other),
            "base_executable_sha256": runtime.sha256_file(other),
        }
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("identity_before_dependencies")
        self.assertIn("not the provisioned", self.receipt()["failure"]["message"])

    def test_wrong_python_version_is_refused(self):
        self.project.probe_changes["selected"] = {"python": "3.11.9"}
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("identity_before_dependencies")

    def test_runtime_drift_after_dependencies_is_refused_with_accurate_receipt(self):
        self.project.fail.add("dependencies")
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("identity_after_dependencies")
        self.assertEqual(self.receipt()["steps"]["dependency_sync"]["status"], "passed")

    def test_sync_failure_is_reported_and_later_steps_are_not_run(self):
        self.project.fail.add("sync")
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("dependency_sync")
        self.assertIn("resolution failed", self.receipt()["failure"]["message"])

    def test_lockfile_modification_is_refused(self):
        self.project.mutate_lock = True
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("dependency_sync")
        self.assertIn("uv.lock", self.receipt()["failure"]["message"])

    def test_preflight_failure_yields_failed_receipt_and_nonzero_status(self):
        self.project.fail.add("preflight")
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("product_preflight")
        with self.assertRaises(local_env.EnvironmentRefused):
            local_env.verify_environment(self.root)

    def test_venv_on_a_different_interpreter_is_preserved_and_refused(self):
        foreign = self.root / "system-python"
        foreign.write_bytes(b"system")
        self.project.create_venv(foreign)
        before = os.readlink(self.root / ".venv/bin/python")
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("virtual_environment")
        message = self.receipt()["failure"]["message"]
        self.assertIn("--migrate-venv", message)
        self.assertIn("was not modified", message)
        self.assertEqual(os.readlink(self.root / ".venv/bin/python"), before)
        self.assertFalse(any(c[1:2] == ["sync"] for c in self.project.calls))

    def test_unverifiable_venv_is_refused(self):
        (self.root / ".venv").mkdir()
        (self.root / ".venv/leftover").write_text("keep")
        self.assertEqual(self.bootstrap(), 1)
        self.assert_failed_at("virtual_environment")
        self.assertEqual((self.root / ".venv/leftover").read_text(), "keep")

    def test_explicit_migration_preserves_the_old_environment(self):
        foreign = self.root / "system-python"
        foreign.write_bytes(b"system")
        self.project.create_venv(foreign)
        self.assertEqual(self.bootstrap("--migrate-venv"), 0)
        kept = [p for p in self.root.iterdir() if p.name.startswith(".venv.migrated-")]
        self.assertEqual(len(kept), 1)
        self.assertEqual(os.readlink(kept[0] / "bin/python"), str(foreign))
        self.assertEqual(self.receipt()["virtual_environment"]["action"], "migrated")
        self.assertEqual(
            os.path.realpath(self.root / ".venv/bin/python"), str(self.project.base)
        )


class LauncherCase(BootstrapCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.bootstrap(), 0)
        self.receipt_data = self.receipt()

    def refused(self, pattern):
        with self.assertRaisesRegex(local_env.EnvironmentRefused, pattern):
            local_env.verify_environment(self.root)


class LauncherVerificationTests(LauncherCase):
    def test_verified_environment_passes_deeply(self):
        self.assertEqual(
            local_env.verify_environment(self.root, deep=True)["status"], "passed"
        )

    def test_failed_or_foreign_receipts_are_refused(self):
        path = self.root / local_env.RECEIPT
        for change, pattern in (
            ({"status": "failed"}, "failed"),
            ({"repository_root": "/other/checkout"}, "another checkout"),
        ):
            with self.subTest(change=change):
                path.write_text(json.dumps({**self.receipt_data, **change}))
                self.refused(pattern)
        path.unlink()
        self.refused("No readable")

    def test_modified_selected_interpreter_is_refused(self):
        self.project.base.write_bytes(b"swapped interpreter")
        self.refused("missing or was modified")

    def test_venv_repointed_to_another_python_is_refused(self):
        other = self.root / "system-python"
        other.write_bytes(b"system")
        link = self.root / ".venv/bin/python"
        link.unlink()
        link.symlink_to(other)
        self.refused("not the selected")

    def test_venv_reporting_another_base_is_refused(self):
        view = {"base": "/usr/bin/python3.12", "executable": "x"}
        with patch.object(local_env, "venv_view", return_value=view):
            self.refused("reports base")

    def test_changed_lock_inputs_require_resynchronization(self):
        (self.root / "uv.lock").write_text("changed\n")
        self.refused("uv.lock changed")

    def test_new_workspace_project_requires_resynchronization(self):
        metadata = self.root / "packages/contracts/pyproject.toml"
        metadata.parent.mkdir(parents=True)
        metadata.write_text('[project]\nname = "repo-catalog-contracts"\n')
        self.refused("Workspace metadata inventory changed")

    def test_tampered_installation_is_refused_by_the_deep_check(self):
        (self.project.directory / "python/bin").chmod(0o755)
        (self.project.directory / "python/bin/extra").write_text("x")
        local_env.verify_environment(self.root)
        with self.assertRaisesRegex(local_env.EnvironmentRefused, "differ"):
            local_env.verify_environment(self.root, deep=True)

    def test_lost_ready_record_is_refused(self):
        (self.project.directory / "ready.json").unlink()
        self.refused("ready record")


class LauncherExecutionTests(LauncherCase):
    def test_environment_selects_the_project_python_for_children_and_uv(self):
        env = local_env.build_environment(
            self.root, self.receipt_data, {"PATH": "/usr/bin:/bin", "HOME": "/h"}
        )
        self.assertEqual(env["PATH"].split(os.pathsep)[0], str(self.root / ".venv/bin"))
        self.assertEqual(env["UV_PYTHON"], str(self.project.selected))
        self.assertEqual(env["UV_PYTHON_DOWNLOADS"], "never")
        self.assertEqual(env["CI_PRODUCT_PYTHON"], str(self.project.selected))
        self.assertEqual(env["VIRTUAL_ENV"], str(self.root / ".venv"))
        self.assertEqual(env["UV_PROJECT_ENVIRONMENT"], str(self.root / ".venv"))
        self.assertTrue(
            env["CI_RUNTIME_REFERENCE"].endswith("artifacts/runtime/selected.json")
        )

    def test_loader_and_python_overrides_are_refused(self):
        for name in local_env.FORBIDDEN:
            with self.subTest(name=name):
                with self.assertRaises(local_env.LoaderOverride):
                    local_env.build_environment(
                        self.root, self.receipt_data, {"PATH": "/bin", name: "x"}
                    )

    def test_python_names_must_resolve_to_the_project_environment(self):
        system = self.root / "system-bin"
        system.mkdir()
        for name in ("python", "python3", "python3.12"):
            (system / name).write_text("#!/bin/sh\n")
            (system / name).chmod(0o755)
        (self.root / ".venv/bin/python").unlink()  # no project python in front
        env = local_env.build_environment(
            self.root, self.receipt_data, {"PATH": str(system)}
        )
        for name in ("python", "python3", "python3.12"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    local_env.EnvironmentRefused, "not the project Python"
                ):
                    local_env.resolve_command([name, "-V"], env, self.root)

    def test_python_resolves_to_the_virtual_environment_when_verified(self):
        for name in ("python3", "python3.12"):
            (self.root / ".venv/bin" / name).symlink_to("python")
        env = local_env.build_environment(
            self.root, self.receipt_data, {"PATH": "/usr/bin:/bin"}
        )
        resolved = local_env.resolve_command(["python3", "-V"], env, self.root)
        self.assertEqual(resolved, [str(self.root / ".venv/bin/python3"), "-V"])
        self.assertEqual(
            local_env.resolve_command(["python3.12"], env, self.root)[0],
            str(self.root / ".venv/bin/python3.12"),
        )

    def test_unknown_command_is_refused(self):
        env = local_env.build_environment(
            self.root, self.receipt_data, {"PATH": "/bin"}
        )
        with self.assertRaisesRegex(local_env.EnvironmentRefused, "not found"):
            local_env.resolve_command(["definitely-not-installed-tool"], env, self.root)

    def test_run_propagates_the_child_status_and_environment(self):
        captured = {}

        def fake_call(argv, env, cwd):
            captured.update(argv=argv, env=env, cwd=cwd)
            return 7

        with patch.object(local_env.subprocess, "call", fake_call):
            status = local_env.run(["sh", "-c", "exit 7"], root=self.root)
        self.assertEqual(status, 7)
        self.assertEqual(captured["cwd"], self.root)
        self.assertEqual(captured["env"]["UV_PYTHON"], str(self.project.selected))

    def test_run_refuses_a_drifted_environment_without_starting_the_command(self):
        (self.root / "uv.lock").write_text("changed\n")
        with patch.object(local_env.subprocess, "call") as call:
            with self.assertRaises(local_env.EnvironmentRefused):
                local_env.run(["sh", "-c", "true"], root=self.root)
        call.assert_not_called()

    def test_cli_returns_distinct_failure_status_for_refusal(self):
        (self.root / "uv.lock").write_text("changed\n")
        with (
            patch.object(local_env, "ROOT", self.root),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            self.assertEqual(local_env.main(["verify"]), 3)


class RealProcessTests(unittest.TestCase):
    """Run the actual launcher program against a refused environment."""

    def test_wrapper_refuses_without_an_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            scripts = Path(directory) / "scripts"
            scripts.mkdir()
            wrapper = Path(local_env.__file__).with_name("local-run.sh")
            (scripts / "local-run.sh").write_bytes(wrapper.read_bytes())
            (scripts / "local-run.sh").chmod(0o755)
            result = subprocess.run(
                [str(scripts / "local-run.sh"), "python", "-V"],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 3)
        self.assertIn("setup-local-python.sh", result.stderr)


class GitIgnoreMigratedVenvTests(unittest.TestCase):
    """Verify that migrated virtual environments do not pollute git status or effective tree."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # Initialize a real disposable git repository
        self.git("init")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.com")
        # Copy the actual repository .gitignore into the disposable repo
        repo_gitignore = (setup.ROOT / ".gitignore").read_text()
        (self.root / ".gitignore").write_text(repo_gitignore)
        (self.root / "README.md").write_text("# Test\n")
        (self.root / "src/repo_catalog").mkdir(parents=True)
        (self.root / "src/repo_catalog/file.py").write_text("print('hello')\n")
        self.git("add", "-A")
        self.git("commit", "-m", "Initial commit")

    def git(self, *args, env=None):
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

    def test_migrated_venv_is_excluded_from_git_status(self):
        (self.root / ".venv").mkdir()
        (self.root / ".venv/bin").mkdir()
        (self.root / ".venv/bin/python").write_text("dummy")
        migrated = self.root / ".venv.migrated-20261025T120000Z"
        migrated.mkdir()
        (migrated / "bin").mkdir()
        (migrated / "bin/python").write_text("foreign")
        (migrated / "large_file.bin").write_bytes(b"0" * 10000)

        status = self.git("status", "--porcelain")
        self.assertEqual(status, "")

    def test_effective_tree_calculation_excludes_migrated_environments(self):
        migrated = self.root / ".venv.migrated-20261025T120000Z"
        migrated.mkdir()
        (migrated / "polluting.bin").write_bytes(b"pollution")

        # Make an ordinary source change
        (self.root / "src/repo_catalog/file.py").write_text("print('modified')\n")
        status = self.git("status", "--porcelain")
        self.assertEqual(status, "M src/repo_catalog/file.py")

        # Run effective-tree calculation logic using private temporary index
        with tempfile.TemporaryDirectory() as temp_index:
            environment = {**os.environ, "GIT_INDEX_FILE": f"{temp_index}/index"}
            self.git("read-tree", "HEAD", env=environment)
            self.git("add", "-A", env=environment)
            tree = self.git("write-tree", env=environment)

        staged_files = self.git("ls-tree", "-r", "--name-only", tree).splitlines()
        self.assertIn("src/repo_catalog/file.py", staged_files)
        self.assertIn(".gitignore", staged_files)
        self.assertFalse(any("migrated" in f for f in staged_files))
        self.assertFalse(any(".venv" in f for f in staged_files))

    def test_ordinary_source_changes_remain_discoverable(self):
        migrated = self.root / ".venv.migrated-20261025T120000Z"
        migrated.mkdir()
        (migrated / "bin").mkdir()
        (migrated / "bin/python").write_text("foreign")

        # Add a new untracked source file
        (self.root / "src/repo_catalog/new_feature.py").write_text("x = 1\n")
        status = self.git("status", "--porcelain")
        self.assertIn("?? src/repo_catalog/new_feature.py", status)
        self.assertNotIn(".venv", status)

    def test_git_check_ignore_root_level_scoping(self):
        # Root-level migrated dir must match
        res = self.git("check-ignore", "-v", ".venv.migrated-20261025T120000Z/")
        self.assertIn("/.venv.migrated-*/", res)

        # Nested directory should NOT match the root-level rule
        nested = self.root / "subdir/.venv.migrated-20261025T120000Z"
        nested.mkdir(parents=True)
        res_nested = subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "check-ignore",
                "-v",
                "subdir/.venv.migrated-20261025T120000Z/",
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res_nested.returncode, 0)


class CheckoutConcurrencyTests(BootstrapCase):
    """Verify that concurrent bootstrap processes in the same checkout serialize cleanly."""

    def test_held_checkout_lock_blocks_and_times_out(self):
        lock_path = self.root / setup.RECEIPT_DIRECTORY / ".bootstrap.lock"
        with setup.CheckoutLock(lock_path, timeout=5):
            # Attempt to bootstrap with small lock timeout
            result = self.bootstrap("--lock-timeout", "0.2")
            self.assertEqual(result, 1)
        # Verify receipt was not published by the timed out call
        self.assertFalse((self.root / local_env.RECEIPT).exists())

    def test_competing_receipt_writes_prevented(self):
        # Establish successful receipt first
        self.assertEqual(self.bootstrap(), 0)
        self.assertEqual(self.receipt()["status"], "passed")

        lock_path = self.root / setup.RECEIPT_DIRECTORY / ".bootstrap.lock"
        with setup.CheckoutLock(lock_path, timeout=5):
            result = self.bootstrap("--lock-timeout", "0.2")
            self.assertEqual(result, 1)

        # The existing passed receipt must not be modified or overwritten
        self.assertEqual(self.receipt()["status"], "passed")

    def test_sequential_bootstrap_under_lock_is_idempotent(self):
        self.assertEqual(self.bootstrap(), 0)
        self.assertEqual(self.receipt()["virtual_environment"]["action"], "create")
        self.assertEqual(self.bootstrap(), 0)
        self.assertEqual(self.receipt()["virtual_environment"]["action"], "reuse")

    def test_independent_checkouts_do_not_block_each_other(self):
        other_temp = tempfile.TemporaryDirectory()
        self.addCleanup(other_temp.cleanup)
        other_project = Project(other_temp.name)

        lock_path_a = self.root / setup.RECEIPT_DIRECTORY / ".bootstrap.lock"
        with setup.CheckoutLock(lock_path_a, timeout=5):
            # Bootstrapping another checkout while root_a is locked must succeed
            with (
                patch("sys.stdout", new_callable=io.StringIO),
                patch("sys.stderr", new_callable=io.StringIO),
                patch.object(setup, "run_command", other_project),
                patch.object(runtime, "provision", other_project.provision),
                patch.object(local_env, "venv_view", other_project.venv_view),
            ):
                result = setup.main(["--root", str(other_project.root)])
                self.assertEqual(result, 0)
            receipt_b = json.loads((other_project.root / local_env.RECEIPT).read_text())
            self.assertEqual(receipt_b["status"], "passed")

    def test_failed_bootstrap_under_lock_records_failure_and_releases_lock(self):
        self.project.fail.add("sync")
        self.assertEqual(self.bootstrap(), 1)
        self.assertEqual(self.receipt()["status"], "failed")
        self.assertEqual(self.receipt()["failure"]["step"], "dependency_sync")

        # The lock must have been released, allowing immediate acquisition
        lock_path = self.root / setup.RECEIPT_DIRECTORY / ".bootstrap.lock"
        with setup.CheckoutLock(lock_path, timeout=0.1):
            pass


if __name__ == "__main__":
    unittest.main()


class TimingAttemptTests(BootstrapCase):
    def attempts(self):
        return sorted(
            (self.root / setup.RECEIPT_DIRECTORY / "invocations").glob("*.json")
        )

    def test_failure_survives_successful_retry_with_parent_and_step_timing(self):
        with patch.dict(
            os.environ,
            {
                "CI_TASK_ID": "timing",
                "CI_SESSION_ID": "author",
                "CI_PARENT_INVOCATION_ID": "outer",
            },
        ):
            self.project.fail.add("sync")
            self.assertEqual(self.bootstrap(), 1)
            first = self.attempts()[0]
            original = first.read_bytes()
            self.project.fail.clear()
            self.assertEqual(self.bootstrap(), 0)
        self.assertEqual(len(self.attempts()), 2)
        self.assertEqual(first.read_bytes(), original)
        failed = json.loads(original)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["timing"]["parent_invocation_id"], "outer")
        step = failed["steps"]["dependency_sync"]
        self.assertIn("started_at", step)
        self.assertIn("completed_at", step)
        self.assertGreaterEqual(step["seconds"], 0)
        self.assertEqual(self.receipt()["timing"]["status"], "completed")

    def test_lock_timeout_preserves_prior_valid_pointer_and_retains_attempt(self):
        self.assertEqual(self.bootstrap(), 0)
        pointer = self.root / local_env.RECEIPT
        before = pointer.read_bytes()
        with setup.CheckoutLock(
            self.root / setup.RECEIPT_DIRECTORY / ".bootstrap.lock"
        ):
            self.assertEqual(self.bootstrap("--lock-timeout", "0"), 1)
        self.assertEqual(pointer.read_bytes(), before)
        self.assertEqual(len(self.attempts()), 2)
        failed = [
            json.loads(p.read_text())
            for p in self.attempts()
            if json.loads(p.read_text())["status"] == "failed"
        ]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["timing"]["exception_type"], "TimeoutError")

    def test_final_verification_interrupt_invalidates_provisional_success(self):
        with patch.object(
            local_env, "verify_environment", side_effect=KeyboardInterrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.bootstrap()
        receipt = self.receipt()
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["exit_code"], 130)
        self.assertEqual(receipt["timing"]["status"], "interrupted")
        self.assertEqual(receipt["steps"]["final_verification"]["status"], "failed")
        with self.assertRaises(local_env.EnvironmentRefused):
            local_env.read_receipt(self.root)
