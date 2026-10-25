"""Stage only test dependencies and reconcile isolated installed I4/I5 execution.

These files belong to the external test harness, never to the product wheel.
The caller supplies a fresh outside directory and separately installs its wheel.
"""

import hashlib
import json
import shutil
from pathlib import Path

from scripts import verify_i5_offline as evidence

SUPPORT_FILES = (
    "tests/__init__.py",
    "tests/support/__init__.py",
    "tests/support/context_admission.py",
    "tests/support/i6a.py",
)

IMPORT_CONTRACT = '''"""Installed artifact binding for the external pytest process itself."""
import hashlib
import json
import os
import sys
from pathlib import Path

import repo_catalog


def verify_imports(phase, session):
    harness_root = Path(__file__).parent
    assert session.config.inipath == harness_root / "pytest.ini"
    assert session.config.rootpath == harness_root
    root = Path(repo_catalog.__file__).resolve().parent
    assert root.is_relative_to(Path(sys.prefix).resolve()), root
    expected = json.loads((Path(__file__).parent / "artifact-files.json").read_text())
    actual = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in root.rglob("*") if p.is_file() and p.suffix in (".py", ".sql", ".json")}
    assert actual == expected, "installed product files differ from the wheel"
    modules = {name: str(Path(module.__file__).resolve())
               for name, module in sys.modules.items()
               if (name == "repo_catalog" or name.startswith("repo_catalog."))
               and getattr(module, "__file__", None)}
    assert all(Path(path).is_relative_to(root) for path in modules.values()), modules
    support = {name: str(Path(module.__file__).resolve())
               for name, module in sys.modules.items()
               if (name == "tests" or name.startswith("tests.support"))
               and getattr(module, "__file__", None)}
    assert all(Path(path).is_relative_to(harness_root / "tests")
               for path in support.values()), support
    receipt = Path(os.environ["REPO_CATALOG_IMPORT_RECEIPT"])
    records = json.loads(receipt.read_text()) if receipt.exists() else []
    records.append({"phase": phase, "prefix": sys.prefix, "origin": str(root),
                    "product_modules": modules, "installed_files": actual,
                    "test_support_modules": support,
                    "pytest_config": str(session.config.inipath),
                    "pytest_root": str(session.config.rootpath)})
    receipt.write_text(json.dumps(records, indent=2) + "\\n")


def pytest_sessionstart(session):
    verify_imports("sessionstart", session)


def pytest_sessionfinish(session, exitstatus):
    verify_imports("sessionfinish", session)
'''


def stage_support(source, outside):
    """Preserve the package root used by copied tests' absolute support imports."""
    source, outside = Path(source).resolve(), Path(outside).resolve()
    if outside.is_relative_to(source):
        raise ValueError("installed test harness must be outside the source checkout")
    files = {}
    for name in SUPPORT_FILES:
        target = outside / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        files[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    shutil.copyfile(source / "scripts/ci_journal.py", outside / "installed_journal.py")
    files["installed_journal.py"] = hashlib.sha256(
        (outside / "installed_journal.py").read_bytes()
    ).hexdigest()
    (outside / "test-support-binding.json").write_text(
        json.dumps(files, indent=2) + "\n"
    )
    # Never inherit the checkout's pythonpath=['src'] when logs live in artifacts/.
    (outside / "pytest.ini").write_text(
        "[pytest]\naddopts = --strict-markers\npythonpath =\n"
    )
    return files


def bind_artifact(outside, expected):
    """Check actual imports and wheel file bytes inside every pytest invocation."""
    (outside / "artifact-files.json").write_text(json.dumps(expected, indent=2) + "\n")
    (outside / "conftest.py").write_text(IMPORT_CONTRACT)


def execute_tests(run, label, stage, python, outside, output, env):
    """Require the actual isolated collection to execute exactly once, without skips."""
    name = f"{label}-i{stage}"
    test_file = f"test_installed_i{stage}.py"
    arguments = [
        python,
        "-m",
        "pytest",
        test_file,
        "-q",
        "--tb=short",
        "--confcutdir=" + str(outside),
        "--rootdir=" + str(outside),
        "-c",
        outside / "pytest.ini",
    ]
    env = dict(env, REPO_CATALOG_IMPORT_RECEIPT=str(output / (name + "-imports.json")))
    collection_status = run(
        name + "-collect", arguments + ["--collect-only"], outside, env
    )
    selected = [
        line.strip()
        for line in (output / (name + "-collect.log")).read_text().splitlines()
        if line.startswith(test_file + "::")
    ]
    (output / (name + "-selected.txt")).write_text(
        "".join(node + "\n" for node in selected)
    )
    journal, junit = output / (name + ".jsonl"), output / (name + ".xml")
    status = run(
        name,
        arguments
        + [
            "-p",
            "installed_journal",
            "-o",
            "junit_family=xunit1",
            "--journal=" + str(journal),
            "--junitxml=" + str(junit),
        ],
        outside,
        env,
    )
    result = {
        "exit_code": status,
        "collection_exit_code": collection_status,
        "collected": len(selected),
        "required_count": {4: 217, 5: 29}[stage],
    }
    if junit.exists() and journal.exists():
        result.update(evidence.outcomes(junit))
        result["reconciliation"] = evidence.reconciliation(selected, junit, journal)
    result["required_tests_executed"] = (
        collection_status == 0
        and len(selected) == result["required_count"]
        and evidence.cohort_succeeded(result)
    )
    (output / (name + "-execution.json")).write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result["required_tests_executed"]
