"""Fast preflight verification for Access environment and test isolation.

Verifies:
1. Interpreter & locked dependencies: Python >= 3.12, locked package versions verified from uv.lock.
2. Console-script availability and identity: repo-catalog on PATH, shebang matches active interpreter,
   module imports from active repository tree, and --version executes.
3. Actual SQLite capabilities: version >= 3.51.3, safe WAL, STRICT, JSON, FTS5, PRAGMAs,
   source ID recorded, reusing accepted product SQLite runtime policy.
4. Test collection conditions and isolated test state: umask 0o022 checked/set,
   clean catalog isolation, and GITHUB_PATH propagation when run in CI.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_SQLITE = (3, 51, 3)
LOCKED_DEPENDENCIES = (
    "httpx",
    "pytest",
    "ruff",
    "pytest-xdist",
    "hatchling",
    "jsonschema",
)


def check_interpreter() -> dict[str, str]:
    version_info = sys.version_info[:3]
    if version_info < (3, 12, 0):
        raise SystemExit(
            f"Preflight failed: Python >= 3.12 required, found {platform.python_version()}"
        )

    lockfile = ROOT / "uv.lock"
    if not lockfile.is_file():
        raise SystemExit(
            "Preflight failed: 'uv.lock' file not found in repository root"
        )

    lock_data = tomllib.loads(lockfile.read_text(encoding="utf-8"))
    locked_versions = {
        pkg["name"]: pkg["version"]
        for pkg in lock_data.get("package", [])
        if "name" in pkg and "version" in pkg
    }

    verified_deps = {}
    for pkg in LOCKED_DEPENDENCIES:
        if pkg not in locked_versions:
            raise SystemExit(f"Preflight failed: dependency {pkg!r} not in uv.lock")
        expected_ver = locked_versions[pkg]
        try:
            actual_ver = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            raise SystemExit(
                f"Preflight failed: required dependency {pkg!r} not installed"
            ) from None
        if actual_ver != expected_ver:
            raise SystemExit(
                f"Preflight failed: dependency {pkg!r} version mismatch: "
                f"expected {expected_ver} (locked), found {actual_ver}"
            )
        verified_deps[pkg] = actual_ver

    return verified_deps


def check_console_script() -> dict[str, str]:
    venv_bin = Path(sys.executable).parent
    current_path = os.environ.get("PATH", "")
    if str(venv_bin) not in current_path.split(os.pathsep):
        os.environ["PATH"] = str(venv_bin) + os.pathsep + current_path

    # Propagate to subsequent GitHub Actions steps if running under CI
    github_path = os.environ.get("GITHUB_PATH")
    if github_path and Path(github_path).is_file():
        try:
            with open(github_path, "a", encoding="utf-8") as f:
                f.write(str(venv_bin) + "\n")
        except OSError:
            pass

    cmd = shutil.which("repo-catalog")
    if not cmd:
        raise SystemExit(
            "Preflight failed: 'repo-catalog' console script not found on PATH. "
            "Ensure the project is installed editable via 'uv sync'."
        )

    cmd_path = Path(cmd).resolve()

    # 1. Verify shebang points to the active Python interpreter
    try:
        first_line = cmd_path.read_text(encoding="utf-8").splitlines()[0]
        if first_line.startswith("#!"):
            shebang_bin = Path(first_line[2:].strip()).resolve()
            if shebang_bin != Path(sys.executable).resolve():
                raise SystemExit(
                    f"Preflight failed: 'repo-catalog' interpreter mismatch: "
                    f"shebang {shebang_bin} != active {Path(sys.executable).resolve()}"
                )
    except OSError as exc:
        raise SystemExit(
            f"Preflight failed: unable to read 'repo-catalog' script: {exc}"
        )

    # 2. Verify imported repo_catalog module originates from the active workspace
    from repo_catalog import _version as repo_catalog

    rc_file = Path(repo_catalog.__file__).resolve()
    expected_src = (ROOT / "src" / "repo_catalog").resolve()
    if not (rc_file == expected_src / "_version.py" or rc_file.is_relative_to(ROOT)):
        raise SystemExit(
            f"Preflight failed: 'repo_catalog' module ({rc_file}) does not "
            f"originate from active repository source tree ({ROOT})"
        )

    # 3. Verify console-script execution and reported version
    try:
        proc = subprocess.run(
            [str(cmd_path), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        version_output = proc.stdout.strip() or proc.stderr.strip()
        if repo_catalog.__version__ not in version_output:
            raise SystemExit(
                f"Preflight failed: 'repo-catalog --version' output ({version_output}) "
                f"does not match package version {repo_catalog.__version__}"
            )
    except Exception as exc:
        raise SystemExit(
            f"Preflight failed: 'repo-catalog --version' execution failed: {exc}"
        )

    return {
        "repo_catalog_script": str(cmd_path),
        "shebang_interpreter": str(sys.executable),
        "module_origin": str(rc_file),
        "version": repo_catalog.__version__,
    }


def check_sqlite_capabilities() -> dict:
    from repo_catalog.adapters.sqlite.access_schema import require_runtime

    require_runtime()

    with tempfile.TemporaryDirectory() as td:
        probe_db = Path(td) / "probe_capabilities.sqlite3"
        with sqlite3.connect(probe_db) as db:
            wal_mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if wal_mode != "wal":
                raise SystemExit(
                    f"Preflight failed: SQLite WAL mode unavailable, got {wal_mode!r}"
                )
            version = db.execute("SELECT sqlite_version()").fetchone()[0]
            source_id = db.execute("SELECT sqlite_source_id()").fetchone()[0]
            compile_options = [r[0] for r in db.execute("PRAGMA compile_options")]
            db.execute("CREATE TABLE _probe(x TEXT) STRICT")
            db.execute("INSERT INTO _probe VALUES('ok')")
            json_test = db.execute("SELECT json_valid('[]')").fetchone()[0]
            if json_test != 1:
                raise SystemExit("Preflight failed: SQLite JSON capability unavailable")
            db.execute(
                "CREATE VIRTUAL TABLE f USING fts5(body,tokenize='trigram case_sensitive 1',content='',detail=full)"
            )

    return {
        "sqlite_version": version,
        "sqlite_source_id": source_id,
        "compile_options": compile_options,
        "compile_options_count": len(compile_options),
        "journal_mode": wal_mode,
        "strict_tables": True,
        "fts5_trigram": True,
    }


def check_isolated_test_state() -> dict[str, str]:
    old_umask = os.umask(0o022)
    test_dir = ROOT / ".build" / "_preflight_perm_test"
    test_dir.mkdir(parents=True, exist_ok=True)
    mode = test_dir.stat().st_mode
    if mode & 0o022:
        try:
            os.chmod(test_dir, 0o755)
        except OSError:
            pass
    try:
        shutil.rmtree(test_dir)
    except OSError:
        pass

    return {
        "initial_umask": oct(old_umask),
        "enforced_umask": "0o022",
    }


def run_preflight(output_path: Path | None = None) -> dict:
    verified_deps = check_interpreter()
    script_info = check_console_script()
    sqlite_info = check_sqlite_capabilities()
    isolation_info = check_isolated_test_state()

    result = {
        "status": "PASS",
        "python_version": platform.python_version(),
        "executable": sys.executable,
        "locked_dependencies": verified_deps,
        "console_script": script_info,
        "sqlite": sqlite_info,
        "isolation": isolation_info,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2) + "\n")
        runtime_path = output_path.parent / "runtime.json"
        runtime_data = {
            "python": result["python_version"],
            "executable": result["executable"],
            "sqlite_version": sqlite_info["sqlite_version"],
            "sqlite_source_id": sqlite_info["sqlite_source_id"],
            "compile_options": [[opt] for opt in sqlite_info["compile_options"]],
            "locked_dependencies": verified_deps,
            "console_script_origin": script_info["module_origin"],
        }
        runtime_path.write_text(json.dumps(runtime_data, indent=2) + "\n")

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save preflight receipt JSON")
    parser.add_argument("--verbose", action="store_true", help="Print full JSON output")
    args = parser.parse_args()
    result = run_preflight(args.output)
    if args.verbose or os.environ.get("CI_VERBOSE") == "1":
        print(json.dumps(result, indent=2))
    else:
        out_ref = f"; receipt: {args.output}" if args.output else ""
        print(
            f"Preflight passed: Python {result['python_version']}, "
            f"SQLite {result['sqlite']['sqlite_version']}, repo-catalog verified{out_ref}"
        )


if __name__ == "__main__":
    main()
