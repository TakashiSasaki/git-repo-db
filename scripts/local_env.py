"""Verify the local project environment and run commands inside it.

``run`` never falls back to another Python: it re-verifies the recorded bootstrap
receipt, the selected interpreter's digest, ``.venv`` and the locked inputs, then
starts the command with the verified virtual environment first on ``PATH`` and the
selected interpreter exported for ``uv`` and child processes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ci_python_runtime  # noqa: E402

RECEIPT = Path("artifacts/local-python/receipt.json")
REFERENCE = Path("artifacts/runtime/selected.json")
FORBIDDEN = (
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "LD_AUDIT",
    "DYLD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "PYTHONHOME",
    "PYTHONSTARTUP",
)
SETUP_COMMAND = "./scripts/setup-local-python.sh"
PYTHON_NAME = re.compile(r"python[0-9.]*")


class EnvironmentRefused(RuntimeError):
    """The project environment is absent, unverified, or has drifted."""


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class LoaderOverride(EnvironmentRefused):
    """An interpreter or dynamic-loader environment override is present."""


def reject_loader_overrides(environment):
    present = sorted(name for name in FORBIDDEN if environment.get(name))
    if present:
        raise LoaderOverride(
            "Unset these interpreter or dynamic-loader overrides first: "
            + ", ".join(present)
        )


def venv_view(venv):
    """Report what the virtual environment's own interpreter says it is based on."""
    environment = ci_python_runtime.clean_environment()
    output = subprocess.check_output(
        [
            str(venv / "bin/python"),
            "-I",
            "-B",
            "-c",
            "import json, sys; print(json.dumps("
            "{'base': sys._base_executable, 'executable': sys.executable,"
            " 'prefix': sys.prefix, 'version': sys.version.split()[0]}))",
        ],
        env=environment,
        text=True,
        timeout=120,
    )
    return json.loads(output)


def check_venv(venv, expected_base):
    """Raise unless ``venv`` is based on exactly ``expected_base`` (both resolved)."""
    expected_base = Path(expected_base).resolve()
    interpreter = venv / "bin/python"
    if not (venv / "pyvenv.cfg").is_file() or not interpreter.exists():
        raise EnvironmentRefused(f"{venv} is not a usable virtual environment")
    if Path(os.path.realpath(interpreter)) != expected_base:
        raise EnvironmentRefused(
            f"{interpreter} resolves to {os.path.realpath(interpreter)}, "
            f"not the selected {expected_base}"
        )
    try:
        view = venv_view(venv)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise EnvironmentRefused(
            f"{interpreter} could not be verified: {error}"
        ) from None
    if Path(view["base"]).resolve() != expected_base:
        raise EnvironmentRefused(
            f"{interpreter} reports base {view['base']}, not the selected {expected_base}"
        )
    return view


def read_receipt(root):
    path = root / RECEIPT
    try:
        receipt = json.loads(path.read_text())
    except (OSError, ValueError):
        raise EnvironmentRefused(f"No readable bootstrap receipt at {path}") from None
    if receipt.get("status") != "passed":
        raise EnvironmentRefused(
            f"The last bootstrap receipt reports {receipt.get('status')!r}"
        )
    if receipt.get("repository_root") != str(root):
        raise EnvironmentRefused("The receipt was recorded for another checkout")
    return receipt


def verify_environment(root=ROOT, *, deep=False):
    """Return the verified receipt or raise EnvironmentRefused with remediation."""
    root = Path(root).resolve()
    receipt = read_receipt(root)
    selected = Path(receipt["selected_python"])
    base = Path(receipt["runtime"]["base_executable"])
    if (
        not selected.exists()
        or ci_python_runtime.sha256_file(base)
        != receipt["runtime"]["base_executable_sha256"]
    ):
        raise EnvironmentRefused("The selected Python is missing or was modified")
    if Path(os.path.realpath(selected)) != base:
        raise EnvironmentRefused("The selected Python no longer resolves to its base")
    installation = Path(receipt["distribution"]["directory"])
    try:
        ready = json.loads((installation / "ready.json").read_text())
    except (OSError, ValueError):
        raise EnvironmentRefused(f"{installation} lost its ready record") from None
    if ready.get("tree_sha256") != receipt["distribution"]["tree_sha256"]:
        raise EnvironmentRefused("The installation's ready record changed")
    if deep and (
        ci_python_runtime.tree_digest(installation / "python")["sha256"]
        != ready["tree_sha256"]
    ):
        raise EnvironmentRefused("The installed Python files differ from the receipt")
    check_venv(root / ".venv", base)
    for name, recorded in receipt["inputs"].items():
        if digest(root / name) != recorded:
            raise EnvironmentRefused(
                f"{name} changed after the environment was synchronized"
            )
    return receipt


def build_environment(root, receipt, base=None):
    """Environment that makes the verified project Python the only default Python."""
    environment = dict(os.environ if base is None else base)
    reject_loader_overrides(environment)
    selected = receipt["selected_python"]
    venv = root / ".venv"
    entries = [str(venv / "bin")] + [
        entry
        for entry in environment.get("PATH", "").split(os.pathsep)
        if entry and entry != str(venv / "bin")
    ]
    environment.update(
        PATH=os.pathsep.join(entries),
        VIRTUAL_ENV=str(venv),
        UV_PROJECT_ENVIRONMENT=str(venv),
        UV_PYTHON=selected,
        UV_PYTHON_DOWNLOADS="never",
        CI_PRODUCT_PYTHON=selected,
        CI_RUNTIME_REFERENCE=str(root / REFERENCE),
    )
    environment.pop("PYTHONPATH", None)
    return environment


def resolve_command(argv, environment, root):
    """Resolve argv[0]; a Python name must resolve to the project's virtual environment."""
    import shutil

    resolved = shutil.which(argv[0], path=environment["PATH"])
    if resolved is None:
        raise EnvironmentRefused(f"Command not found: {argv[0]}")
    if PYTHON_NAME.fullmatch(Path(argv[0]).name) and Path(resolved).parent != (
        root / ".venv/bin"
    ):
        raise EnvironmentRefused(
            f"{argv[0]} resolves to {resolved}, not the project Python"
        )
    return [resolved, *argv[1:]]


def run(argv, root=ROOT):
    root = Path(root).resolve()
    receipt = verify_environment(root)
    environment = build_environment(root, receipt)
    return subprocess.call(
        resolve_command(argv, environment, root), env=environment, cwd=root
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "verify", help="verify the environment; exit nonzero if unsafe"
    )
    check.add_argument(
        "--deep", action="store_true", help="re-hash the installed Python tree"
    )
    commands.add_parser("env", help="print shell exports for the verified environment")
    runner = commands.add_parser(
        "run", help="run a command in the verified environment"
    )
    runner.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            if not command:
                parser.error("run requires a command after --")
            return run(command)
        receipt = verify_environment(ROOT, deep=getattr(args, "deep", False))
        if args.command == "env":
            for name, value in sorted(build_environment(ROOT, receipt).items()):
                if name in (
                    "PATH",
                    "VIRTUAL_ENV",
                    "UV_PROJECT_ENVIRONMENT",
                    "UV_PYTHON",
                    "UV_PYTHON_DOWNLOADS",
                    "CI_PRODUCT_PYTHON",
                    "CI_RUNTIME_REFERENCE",
                ):
                    print(f"export {name}={shlex.quote(value)}")
        else:
            print(f"verified: {receipt['selected_python']}")
        return 0
    except EnvironmentRefused as error:
        hint = (
            ""
            if isinstance(error, LoaderOverride)
            else f"\nRepair with: {SETUP_COMMAND}"
        )
        print(f"Refusing to use this environment: {error}{hint}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
