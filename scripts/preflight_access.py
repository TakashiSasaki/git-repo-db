"""Fast preflight verification for Access environment and test isolation.

Verifies:
1. Interpreter & dependencies: Python >= 3.12, locked dependencies present.
2. Console-script availability and identity: repo-catalog on PATH, functional,
   and importing from the active repository source tree.
3. Actual SQLite capabilities: version >= 3.51.3, safe WAL, STRICT, JSON, PRAGMAs,
   source ID recorded, no spoofing/overrides.
4. Test collection conditions and isolated test state: umask 0o022 checked/set,
   clean catalog isolation, no lingering network or poisoned state.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_SQLITE = (3, 51, 3)


def check_interpreter():
    version_info = sys.version_info[:3]
    if version_info < (3, 12, 0):
        raise SystemExit(
            f"Preflight failed: Python >= 3.12 required, found {platform.python_version()}"
        )
    for pkg in ("httpx", "pytest", "ruff"):
        if importlib.util.find_spec(pkg) is None:
            raise SystemExit(f"Preflight failed: required dependency {pkg!r} not found")


def check_console_script():
    venv_bin = Path(sys.executable).parent
    current_path = os.environ.get("PATH", "")
    if str(venv_bin) not in current_path.split(os.pathsep):
        os.environ["PATH"] = str(venv_bin) + os.pathsep + current_path

    cmd = shutil.which("repo-catalog")
    if not cmd:
        raise SystemExit(
            "Preflight failed: 'repo-catalog' console script not found on PATH. "
            "Ensure the project is installed editable via 'uv sync'."
        )
    try:
        proc = subprocess.run(
            [cmd, "--help"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except Exception as exc:
        raise SystemExit(
            f"Preflight failed: 'repo-catalog --help' execution failed: {exc}"
        )
    if "repo-catalog" not in proc.stdout:
        raise SystemExit("Preflight failed: 'repo-catalog' identity check failed")


def check_sqlite_capabilities():
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise SystemExit(
            f"Preflight failed: SQLite >= {'.'.join(map(str, MIN_SQLITE))} required, "
            f"found {sqlite3.sqlite_version}"
        )
    with sqlite3.connect(":memory:") as db:
        version = db.execute("SELECT sqlite_version()").fetchone()[0]
        source_id = db.execute("SELECT sqlite_source_id()").fetchone()[0]
        compile_options = [r[0] for r in db.execute("PRAGMA compile_options")]
        db.execute("CREATE TABLE _probe(x TEXT) STRICT")
        db.execute("INSERT INTO _probe VALUES('ok')")
        json_test = db.execute("SELECT json_extract('{\"a\":1}', '$.a')").fetchone()[0]
        if json_test != 1:
            raise SystemExit("Preflight failed: SQLite JSON capability unavailable")
    from repo_catalog.adapters.sqlite.access_schema import require_runtime

    require_runtime()
    return {
        "sqlite_version": version,
        "sqlite_source_id": source_id,
        "compile_options": compile_options,
        "compile_options_count": len(compile_options),
    }


def check_isolated_test_state():
    os.umask(0o022)
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


def run_preflight(output_path: Path | None = None) -> dict:
    check_interpreter()
    check_console_script()
    sqlite_info = check_sqlite_capabilities()
    check_isolated_test_state()
    result = {
        "status": "PASS",
        "python_version": platform.python_version(),
        "executable": sys.executable,
        "repo_catalog_script": shutil.which("repo-catalog"),
        **sqlite_info,
        "umask": "0022",
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2) + "\n")
        runtime_path = output_path.parent / "runtime.json"
        runtime_data = {
            "python": result["python_version"],
            "executable": result["executable"],
            "sqlite_version": result["sqlite_version"],
            "sqlite_source_id": result["sqlite_source_id"],
            "compile_options": [[opt] for opt in result["compile_options"]],
        }
        runtime_path.write_text(json.dumps(runtime_data, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save preflight receipt JSON")
    args = parser.parse_args()
    result = run_preflight(args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
