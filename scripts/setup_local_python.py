"""One-command, fail-closed local Python environment bootstrap.

Runs with any stdlib Python 3.9+ that is used only to orchestrate. It provisions
the manifest-pinned complete Python distribution, verifies its Python/SQLite
identity before dependencies, creates or verifies ``.venv`` on exactly that
interpreter, installs locked dependencies, re-verifies after synchronization, runs
the real product preflight and writes a machine-readable receipt. Any failed
mandatory verification yields a nonzero exit and a ``failed`` receipt.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ci_python_runtime, local_env  # noqa: E402
from scripts.ci_timing import InvocationTiming, new_record  # noqa: E402

RECEIPT_SCHEMA = "git-repo-db-local-python-receipt/1"
RECEIPT_DIRECTORY = Path("artifacts/local-python")
STEPS = (
    "host",
    "tools",
    "repository",
    "provision",
    "identity_before_dependencies",
    "virtual_environment",
    "dependency_sync",
    "identity_after_dependencies",
    "product_preflight",
    "final_verification",
)
UV_INSTALL = "https://docs.astral.sh/uv/getting-started/installation/"


class SetupFailure(RuntimeError):
    pass


class CheckoutLock:
    """Exclusive advisory lock so concurrent bootstraps in the same checkout serialize."""

    def __init__(self, path: Path, timeout: float = 600.0):
        self.path = Path(path)
        self.timeout = timeout
        self.descriptor: int | None = None

    def __enter__(self):
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() > deadline:
                    os.close(self.descriptor)
                    self.descriptor = None
                    raise TimeoutError(
                        f"Another bootstrap holds {self.path}; retry when it finishes"
                    ) from None
                time.sleep(0.2)

    def __exit__(self, *exc):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None


def run_command(argv, *, environment, cwd, timeout=3600):
    """Run one bootstrap command, capturing output for the receipt."""
    return subprocess.run(
        [str(part) for part in argv],
        env=environment,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def find_tool(name):
    return shutil.which(name)


def tail(text, lines=40):
    return "\n".join((text or "").splitlines()[-lines:])


class Recorder:
    def __init__(self):
        self.steps = {name: {"status": "not_run"} for name in STEPS}
        self.current = None
        self.started = None
        self.checkpoint = lambda: None

    def begin(self, name):
        self.current = name
        self.started = time.perf_counter()
        self.steps[name] = {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self.checkpoint()

    def finish(self, **details):
        step = self.steps[self.current]
        step.update(
            details,
            status="passed",
            seconds=round(time.perf_counter() - self.started, 3),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.checkpoint()

    def fail(self, message):
        step = self.steps[self.current]
        step.update(
            status="failed",
            message=message,
            seconds=round(time.perf_counter() - self.started, 3),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.checkpoint()


def json_file(path):
    return json.loads(Path(path).read_text())


def execute(arguments, environment, root, what):
    result = run_command(arguments, environment=environment, cwd=root)
    if result.returncode != 0:
        raise SetupFailure(
            f"{what} failed with exit status {result.returncode}:\n"
            f"{tail(result.stdout)}\n{tail(result.stderr)}"
        )
    return result


def probe(python, root, environment, name, reference=None):
    output = root / "artifacts/runtime" / name
    command = [
        python,
        "-I",
        "-B",
        root / "scripts/ci_python_runtime.py",
        "probe",
        output,
    ]
    if reference:
        command += ["--reference", reference]
    result = run_command(command, environment=environment, cwd=root)
    runtime = json_file(output) if output.is_file() else None
    if result.returncode != 0 or not runtime:
        raise SetupFailure(
            f"Runtime probe {name} failed with exit status {result.returncode}:\n"
            f"{tail(result.stderr)}"
        )
    if runtime.get("product_safety_and_capabilities") != "passed":
        raise SetupFailure(f"Product capability checks did not pass in {name}")
    if runtime.get("child_runtime_identity") != "passed":
        raise SetupFailure(f"Child process runtime identity did not pass in {name}")
    return runtime


def runtime_summary(runtime):
    keys = (
        "python",
        "executable",
        "base_executable",
        "base_executable_sha256",
        "sqlite_version",
        "sqlite_source_id",
        "sqlite_threadsafety",
        "sqlite_module",
        "sqlite_module_origin",
        "sqlite_module_sha256",
        "sqlite_mappings",
        "compile_options",
        "pragmas",
        "capabilities",
        "repository",
    )
    return {key: runtime.get(key) for key in keys}


def inspect_existing_venv(root, base, migrate):
    venv = root / ".venv"
    if not (venv.exists() or venv.is_symlink()):
        return {"action": "create"}
    try:
        if venv.is_symlink():
            raise local_env.EnvironmentRefused(f"{venv} is a symbolic link")
        view = local_env.check_venv(venv, base)
        return {"action": "reuse", "view": view}
    except local_env.EnvironmentRefused as error:
        moved = venv.with_name(
            ".venv.migrated-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        if migrate and venv.is_dir() and not venv.is_symlink():
            venv.rename(moved)
            return {
                "action": "migrated",
                "preserved_as": str(moved),
                "reason": str(error),
            }
        raise SetupFailure(
            f"Existing {venv} does not use the selected Python: {error}.\n"
            "It was not modified. Either inspect/remove it yourself and rerun, or rerun "
            f"with --migrate-venv to keep it as {venv.name}.migrated-<UTC timestamp> "
            "and create a fresh environment."
        ) from None


def bootstrap(root, args, recorder, receipt):
    """Execute all mandatory steps; every failure raises SetupFailure."""
    recorder.begin("host")
    try:
        triple = ci_python_runtime.host_triple()
    except ci_python_runtime.UnsupportedPlatform as error:
        raise SetupFailure(str(error)) from None
    try:
        local_env.reject_loader_overrides(os.environ)
    except local_env.EnvironmentRefused as error:
        raise SetupFailure(str(error)) from None
    receipt["host"] = {
        "system": platform.system(),
        "machine": platform.machine(),
        "platform": triple,
        "orchestrator_python": sys.version.split()[0],
        "orchestrator_executable": sys.executable,
    }
    recorder.finish(platform=triple)

    recorder.begin("tools")
    tools = {}
    for name in ("uv", "git"):
        path = find_tool(name)
        if not path:
            hint = f" Install it first: {UV_INSTALL}" if name == "uv" else ""
            raise SetupFailure(f"Required tool {name!r} was not found on PATH.{hint}")
        version = run_command([path, "--version"], environment=os.environ, cwd=root)
        if version.returncode != 0:
            raise SetupFailure(f"{path} --version failed: {tail(version.stderr)}")
        tools[name] = {"path": path, "version": version.stdout.strip()}
    receipt["tools"] = tools
    recorder.finish(tools=tools)

    recorder.begin("repository")
    environment = ci_python_runtime.clean_environment()
    identity = {}
    for key, expression in (("commit", "HEAD"), ("tree", "HEAD^{tree}")):
        result = run_command(
            ["git", "rev-parse", expression], environment=environment, cwd=root
        )
        if result.returncode != 0:
            raise SetupFailure("The project root is not a Git checkout with a commit")
        identity[key] = result.stdout.strip()
    status = run_command(
        ["git", "status", "--porcelain"], environment=environment, cwd=root
    )
    identity["dirty"] = bool(status.stdout.strip())
    receipt["repository"] = identity
    recorder.finish(**identity)

    recorder.begin("provision")
    installed = ci_python_runtime.provision(args.home, offline=args.offline)
    selected = Path(installed["executable"])
    receipt["selected_python"] = str(selected)
    receipt["distribution"] = {
        "manifest": installed["selection"],
        "directory": installed["directory"],
        "archive_sha256": installed["archive_sha256"],
        "tree_sha256": installed["tree_sha256"],
        "reused": installed["reused"],
    }
    recorder.finish(reused=installed["reused"], directory=installed["directory"])

    environment.update(
        PATH=os.pathsep.join([str(selected.parent), environment.get("PATH", "")]),
        UV_PYTHON=str(selected),
        UV_PYTHON_DOWNLOADS="never",
        UV_PROJECT_ENVIRONMENT=str(root / ".venv"),
        CI_PRODUCT_PYTHON=str(selected),
        CI_RUNTIME_REFERENCE=str(root / local_env.REFERENCE),
    )
    inputs_before = {
        name: local_env.digest(root / name)
        for name in local_env.locked_input_names(root)
    }

    recorder.begin("identity_before_dependencies")
    before = probe(selected, root, environment, "selected.json")
    expected = installed["selection"]["python"]
    if before["python"] != expected:
        raise SetupFailure(f"Selected Python {before['python']} is not {expected}")
    if Path(before["base_executable"]) != Path(os.path.realpath(selected)):
        raise SetupFailure("The probed interpreter is not the provisioned distribution")
    if before["base_executable_sha256"] != ci_python_runtime.sha256_file(selected):
        raise SetupFailure("The probed interpreter digest differs from the file")
    receipt["runtime"] = runtime_summary(before)
    recorder.finish(sqlite_version=before["sqlite_version"])

    recorder.begin("virtual_environment")
    venv = inspect_existing_venv(
        root, Path(before["base_executable"]), args.migrate_venv
    )
    receipt["virtual_environment"] = {k: v for k, v in venv.items() if k != "view"}
    recorder.finish(**receipt["virtual_environment"])

    recorder.begin("dependency_sync")
    command = [
        "uv",
        "sync",
        "--locked",
        "--group",
        "dev",
        "--python",
        selected,
    ]
    if args.offline:
        command.append("--offline")
    synchronized = execute(
        [tools["uv"]["path"], *command[1:]], environment, root, "uv sync"
    )
    inputs_after = {
        name: local_env.digest(root / name)
        for name in local_env.locked_input_names(root)
    }
    if inputs_after != inputs_before:
        raise SetupFailure("uv.lock or pyproject.toml changed during synchronization")
    view = local_env.check_venv(root / ".venv", Path(before["base_executable"]))
    receipt["dependency_sync"] = {
        "command": [str(part) for part in command],
        "exit_status": 0,
        "inputs_unchanged": True,
        "output_tail": tail(synchronized.stderr, 10),
    }
    receipt["inputs"] = inputs_after
    receipt["virtual_environment"].update(
        path=str(root / ".venv"), python=view["executable"], base=view["base"]
    )
    recorder.finish(inputs_unchanged=True)

    venv_python = root / ".venv/bin/python"
    environment["PATH"] = os.pathsep.join(
        [str(root / ".venv/bin"), environment["PATH"]]
    )
    environment["VIRTUAL_ENV"] = str(root / ".venv")

    recorder.begin("identity_after_dependencies")
    after = probe(
        venv_python, root, environment, "dependencies.json", root / local_env.REFERENCE
    )
    receipt["runtime_after_dependencies"] = runtime_summary(after)
    recorder.finish(sqlite_version=after["sqlite_version"])

    recorder.begin("product_preflight")
    preflight = root / RECEIPT_DIRECTORY / "preflight.json"
    execute(
        [venv_python, root / "scripts/preflight_access.py", "--output", preflight],
        environment,
        root,
        "Product preflight",
    )
    outcome = json_file(preflight)
    if outcome.get("status") != "PASS" or Path(outcome["executable"]) != venv_python:
        raise SetupFailure("Product preflight did not pass on the project interpreter")
    receipt["preflight"] = {
        "status": outcome["status"],
        "locked_dependencies": outcome["locked_dependencies"],
        "sqlite": outcome["sqlite"]["sqlite_version"],
    }
    recorder.finish(status="PASS")


def write_receipt(root, receipt, recorder):
    receipt["steps"] = recorder.steps
    target = root / local_env.RECEIPT
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, indent=2) + "\n")
    os.replace(temporary, target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, help="Python installation root")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="never download; use verified local installs and uv cache",
    )
    parser.add_argument(
        "--migrate-venv",
        action="store_true",
        help="preserve an incompatible .venv under a timestamped name",
    )
    parser.add_argument(
        "--lock-timeout",
        type=float,
        default=600.0,
        help="maximum seconds to wait for checkout lock before failing",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    recorder = Recorder()
    receipt = new_record("setup", "setup")
    receipt.update(
        {
            "schema": RECEIPT_SCHEMA,
            "status": "failed",
            "created": datetime.now(timezone.utc).isoformat(),
            "repository_root": str(root),
            "steps": recorder.steps,
        }
    )
    attempt = (
        root / RECEIPT_DIRECTORY / "invocations" / (receipt["invocation_id"] + ".json")
    )
    timing = InvocationTiming(receipt, attempt)
    receipt["timing"]["kind"] = "preparation"
    recorder.checkpoint = timing.save
    timing.end("preparation")
    lock = root / RECEIPT_DIRECTORY / ".bootstrap.lock"
    acquired = False

    def failed(error, publish):
        receipt["status"] = "failed"
        receipt["exit_code"] = 130 if isinstance(error, KeyboardInterrupt) else 1
        if recorder.current:
            recorder.fail(str(error))
        receipt["failure"] = {"step": recorder.current, "message": str(error)}
        timing.finish(
            "interrupted" if isinstance(error, KeyboardInterrupt) else "error", error
        )
        if publish:
            write_receipt(root, receipt, recorder)

    try:
        with ExitStack() as locks:
            with timing.phase("resource_wait"):
                locks.enter_context(CheckoutLock(lock, timeout=args.lock_timeout))
                acquired = True
            try:
                with timing.phase("command"):
                    bootstrap(root, args, recorder, receipt)
                    receipt["status"] = "passed"
                    recorder.begin("final_verification")
                    write_receipt(root, receipt, recorder)
                    local_env.verify_environment(root, deep=True)
                    recorder.finish()
                receipt["exit_code"] = 0
                timing.finish("completed")
                write_receipt(root, receipt, recorder)
            except BaseException as error:
                failed(error, publish=True)
                if not isinstance(
                    error,
                    (
                        SetupFailure,
                        local_env.EnvironmentRefused,
                        ci_python_runtime.UnsupportedPlatform,
                        RuntimeError,
                        ValueError,
                        OSError,
                        subprocess.SubprocessError,
                        KeyError,
                    ),
                ):
                    raise
                print(
                    f"Local Python bootstrap FAILED at {recorder.current}: {error}",
                    file=sys.stderr,
                )
                return 1
    except BaseException as error:
        if not acquired:
            failed(error, publish=False)
        if not isinstance(error, TimeoutError):
            raise
        print(
            f"Local Python bootstrap FAILED: {error}",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "passed",
                "python": receipt["selected_python"],
                "sqlite": receipt["runtime"]["sqlite_version"],
                "receipt": str(root / local_env.RECEIPT),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
