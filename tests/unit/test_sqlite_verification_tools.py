"""Behavioral regressions for environment SQLite evidence and offline tooling."""

import ast
import hashlib
import importlib
import json
import sqlite3
import sys
import types
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from scripts import verify_i5_offline as evidence

ROOT = Path(__file__).resolve().parents[2]


def xml_case(name, message="I2_TRANSFER_UNSUPPORTED: staged", phase="call", line=15):
    suite = ET.Element("testsuite")
    case = ET.SubElement(suite, "testcase", classname="tests.test_example", name=name)
    tag = "failure" if phase == "call" else "error"
    if phase == "teardown":
        message = 'failed on teardown with "' + message + '"'
    event = ET.SubElement(case, tag, message=message)
    event.text = f"tests/test_example.py:{line}: in test_example\n{message}"
    return ET.tostring(suite)


@pytest.mark.parametrize("stage", [2, 3, 4, 5])
def test_author_records_environment_before_preserving_capability_refusal(
    monkeypatch, tmp_path, stage
):
    module = importlib.import_module(f"scripts.verify_i{stage}")
    from repo_catalog.adapters.sqlite import p1_schema

    def refuse(_):
        raise RuntimeError("required capability absent")

    monkeypatch.setattr(p1_schema, "configure", refuse)
    output = tmp_path / "evidence"
    monkeypatch.setattr(sys, "argv", [module.__name__, "--output", str(output)])
    with pytest.raises(RuntimeError, match="required capability absent"):
        module.main()
    runtime = json.loads((output / "runtime-before-checks.json").read_text())
    assert runtime["sqlite_version"] == sqlite3.sqlite_version
    assert runtime["executable"] == sys.executable
    assert runtime["sqlite_source_id"]
    assert not (output / "summary.json").exists()


def test_runtime_metadata_records_unfamiliar_environment_without_release_gate():
    class ObservedDatabase:
        def execute(self, sql):
            class Rows:
                def fetchone(self):
                    return "9.27.42", "future environment source"

                def fetchall(self):
                    return []

            return Rows()

    measured = evidence.runtime_metadata(ObservedDatabase())
    assert measured["sqlite_version"] == "9.27.42"
    assert measured["sqlite_source_id"] == "future environment source"


@pytest.mark.parametrize(
    "problem", ["failed", "error", "skipped", "xfail", "xpass", "reconciliation"]
)
def test_zero_process_exit_does_not_hide_incomplete_or_skipped_execution(problem):
    result = {"exit_code": 0, "reconciliation": {"consistent_node_execution": True}}
    assert evidence.cohort_succeeded(result)
    if problem == "reconciliation":
        result["reconciliation"]["consistent_node_execution"] = False
    else:
        result[problem] = 1
    assert not evidence.cohort_succeeded(result)


@pytest.mark.parametrize("stage", [4, 5])
def test_failure_comparison_retains_unexpected_failure_and_teardown(stage):
    module = importlib.import_module(f"scripts.compare_i{stage}_failures")
    baseline = module.index(xml_case("test_old"))
    current = module.index(xml_case("test_old", "unexpected failure", "teardown"))
    result = module.compare(baseline, current)
    assert result["same_nodes"]
    assert not result["comparison"][0]["same_phase"]
    assert not result["comparison"][0]["same_stage_refusal"]
    assert result["comparison"][0]["current"]["stage_refusal"] is None
    extra = module.index(xml_case("test_new", "arbitrary assertion"))
    current.update(extra)
    result = module.compare(baseline, current)
    assert not result["same_nodes"]
    assert result["additional"] == 1
    assert result["additional_nodes"][0]["name"] == "test_new"


@pytest.mark.parametrize("stage", [4, 5])
def test_failure_comparison_trace_location_checks_keep_paths_and_functions(stage):
    module = importlib.import_module(f"scripts.compare_i{stage}_failures")
    baseline = module.index(xml_case("test_old", line=10))
    current = module.index(xml_case("test_old", line=100))
    assert module.compare(baseline, current)["comparison"][0][
        "same_trace_paths_functions"
    ]
    current[("tests.test_example", "test_old")]["frames"][0]["function"] = "different"
    assert not module.compare(baseline, current)["comparison"][0][
        "same_trace_paths_functions"
    ]


@pytest.mark.parametrize("stage", [4, 5])
def test_comparison_cli_requires_explicit_historical_entry_and_keeps_79_contract(
    monkeypatch, tmp_path, stage
):
    module = importlib.import_module(f"scripts.compare_i{stage}_failures")
    baseline = ET.Element("testsuite")
    for number in range(79):
        baseline.append(ET.fromstring(xml_case(f"test_{number}"))[0])
    xml = ET.tostring(baseline)
    archive = tmp_path / "old.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("author-old/regressions.xml", xml_case("stale"))
        bundle.writestr("final-record/regressions.xml", xml)
    current = tmp_path / "current.xml"
    current.write_bytes(xml)
    output = tmp_path / "comparison.json"
    argv = [
        module.__name__,
        "--current",
        str(current),
        "--output",
        str(output),
        "--baseline-archive",
        str(archive),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as missing:
        module.main()
    assert missing.value.code == 2
    argv += ["--baseline-entry", "final-record/regressions.xml"]
    module.main()
    result = json.loads(output.read_text())
    assert result["baseline_non_successes"] == 79
    assert result["same_nodes"]
    assert result["baseline_entry"] == "final-record/regressions.xml"
    current.write_bytes(xml_case("different", "unexpected failure"))
    with pytest.raises(SystemExit, match="comparison differs"):
        module.main()
    assert json.loads(output.read_text())["additional"] == 1


def wheelhouse_fixture(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheel = wheelhouse / "pytest-1-py3-none-any.whl"
    wheel.write_bytes(b"locked wheel")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    lock = f"""[[package]]
name = "pytest"
wheels = [{{url = "https://example.invalid/{wheel.name}", hash = "sha256:{digest}"}}]
""".encode()
    (root / "uv.lock").write_bytes(lock)
    manifest = {
        "lock_sha256": hashlib.sha256(lock).hexdigest(),
        "wheels": [{"name": "pytest", "file": wheel.name, "sha256": digest}],
    }
    (wheelhouse / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(evidence, "ROOT", root)
    return wheelhouse, wheel, manifest


def test_offline_wheelhouse_is_bound_to_lock_and_actual_bytes(tmp_path, monkeypatch):
    directory, wheel, _ = wheelhouse_fixture(tmp_path, monkeypatch)
    assert evidence.verified_wheelhouse(directory)[0] == directory
    wheel.write_bytes(b"corrupted wheel")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        evidence.verified_wheelhouse(directory)


def test_manifest_cannot_authorize_an_unlocked_wheel(tmp_path, monkeypatch):
    directory, wheel, manifest = wheelhouse_fixture(tmp_path, monkeypatch)
    wheel.write_bytes(b"replacement")
    manifest["wheels"][0]["sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="unlocked"):
        evidence.verified_wheelhouse(directory)


@pytest.mark.parametrize("stage", [4, 5])
@pytest.mark.parametrize("refuse", [False, True])
def test_generated_installed_probe_records_runtime_and_real_json_before_guard(
    tmp_path, monkeypatch, stage, refuse
):
    program = next(
        node.value
        for node in ast.walk(
            ast.parse((ROOT / f"scripts/verify_i{stage}_distribution.py").read_text())
        )
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("import hashlib,json,sqlite3")
    )
    package = types.ModuleType("repo_catalog")
    package_dir = tmp_path / "site-packages/repo_catalog"
    package_dir.mkdir(parents=True)
    package.__file__ = str(package_dir / "__init__.py")
    Path(package.__file__).write_text("# installed fixture\n")
    schema = types.ModuleType("repo_catalog.adapters.sqlite.p1_schema")
    schema.verify_declared = lambda: None
    schema.register_functions = lambda db: None

    def configure(db):
        if refuse:
            raise RuntimeError("missing required capability")

    schema.configure = configure
    schema.compose = lambda role: "CREATE TABLE probe(value TEXT)"
    schema.fingerprint = lambda role: "fixture-fingerprint"
    schema.schema_rows = lambda db: []
    schema.REQUIRED_PRAGMAS = {"foreign_keys": "ON"}
    adapter = types.ModuleType("repo_catalog.adapters.sqlite")
    adapter.p1_schema = schema
    monkeypatch.setitem(sys.modules, "repo_catalog", package)
    monkeypatch.setitem(sys.modules, "repo_catalog.adapters.sqlite", adapter)
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    output = tmp_path / "runtime.json"
    monkeypatch.setattr(sys, "argv", ["measure.py", str(output)])
    if refuse:
        with pytest.raises(RuntimeError, match="missing required capability"):
            exec(compile(program, "measure.py", "exec"), {})
    else:
        exec(compile(program, "measure.py", "exec"), {})
    measured = json.loads(output.read_text())
    assert measured["sqlite"][0] == sqlite3.sqlite_version
    assert measured["executable"] == sys.executable
    assert measured["origin"] == package.__file__
    if not refuse:
        assert measured["installed_files"] == {
            "__init__.py": hashlib.sha256(
                Path(package.__file__).read_bytes()
            ).hexdigest()
        }


@pytest.mark.parametrize("stage", [2, 3, 4, 5])
def test_author_exit_keeps_focused_and_regression_failures(
    monkeypatch, tmp_path, stage
):
    module = importlib.import_module(f"scripts.verify_i{stage}")
    selected = ["tests/integration/p3/test_parent_reports.py::test_parent"]
    selected += [
        f"tests/integration/p3/test_transfer_sql.py::test_{n}" for n in range(217)
    ]
    selected += [
        f"tests/integration/p3/test_transfer_admission.py::test_{n}" for n in range(29)
    ]
    monkeypatch.setattr(evidence, "ci_targets", lambda: [])
    monkeypatch.setattr(evidence, "git", lambda *args: "fixture-head")
    monkeypatch.setattr(evidence, "input_hashes", lambda: {"input": "frozen"})
    monkeypatch.setattr(evidence, "collect", lambda *args: (selected, {"exit_code": 0}))
    names = []

    def run_cohort(out, name, selected, workers):
        names.append(name)
        return {
            "exit_code": 0,
            "reconciliation": {"consistent_node_execution": True},
            "skipped": int(name == "regressions"),
        }

    monkeypatch.setattr(evidence, "run_cohort", run_cohort)
    output = tmp_path / "evidence"
    monkeypatch.setattr(sys, "argv", [module.__name__, "--output", str(output)])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 1
    assert "regressions" in names
    if stage >= 4:
        assert "transfer-sql" in names
    if stage == 5:
        assert "transfer-admission" in names
    assert json.loads((output / "summary.json").read_text())["run"]["skipped"] == 1
