import json
import sys
from argparse import Namespace

import jsonschema
import pytest

from scripts import ci_profile
from tests.support.cli import response_validator


def test_cached_cli_validator_still_rejects_invalid_envelope():
    with pytest.raises(jsonschema.ValidationError):
        response_validator().validate({"status": "ok"})


def test_junit_aggregation_preserves_failures(tmp_path):
    xml = tmp_path / "tests.xml"
    xml.write_text(
        '<testsuites><testsuite><testcase classname="tests.unit.synthetic" name="a" time="1.25"/><testcase classname="tests.unit.synthetic" name="b" time="2"><failure/></testcase><testcase classname="tests.unit.other" name="c" time="0.1"><skipped/></testcase></testsuite></testsuites>'
    )
    result = ci_profile.junit(xml)
    assert result["count"] == 3
    assert result["files"][0] == {
        "file": "tests/unit/synthetic.py",
        "seconds": 3.25,
        "tests": 2,
        "failures": 1,
        "skipped": 0,
    }


@pytest.mark.parametrize("exit_code", [0, 7])
def test_command_status_metadata_and_stale_junit(tmp_path, monkeypatch, exit_code):
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    xml = tmp_path / "stale.xml"
    xml.write_text(
        '<testsuites><testsuite><testcase name="stale"/></testsuite></testsuites>'
    )
    args = Namespace(
        command=[sys.executable, "-c", f"raise SystemExit({exit_code})"],
        output=tmp_path,
        name="command",
        junit=xml,
        mode="sequential",
        workers=1,
        sqlite=None,
    )
    assert ci_profile.run(args) == (exit_code or 2)
    saved = json.loads((tmp_path / "command.json").read_text())
    assert saved["measurement_error"]
    assert saved["wall_seconds"] > 0
    assert saved["runtime"]["cpu_count"] > 0
    assert "junit" not in saved


def test_coverage_rejects_omitted_duplicate_skipped_and_failed_tests(tmp_path):
    expected = tmp_path / "required.txt"
    expected.write_text(
        "tests/unit/synthetic.py::a\ntests/unit/synthetic.py::b\n2 tests collected\n"
    )
    profile = tmp_path / "result.json"
    record = {
        "exit_code": 0,
        "junit": {
            "tests": [
                {"nodeid": f"tests/unit/synthetic.py::{name}", "status": "passed"}
                for name in ("a", "b")
            ]
        },
    }
    profile.write_text(json.dumps(record))
    assert ci_profile.coverage(expected, [profile])["executed_once"] == 2
    for bad in (
        record["junit"]["tests"][:1],
        record["junit"]["tests"] * 2,
        [{"nodeid": "tests/unit/synthetic.py::a", "status": "skipped"}],
    ):
        profile.write_text(json.dumps({"exit_code": 0, "junit": {"tests": bad}}))
        with pytest.raises(ValueError):
            ci_profile.coverage(expected, [profile])


def test_compare_reports_median_range_not_single_sample(tmp_path):
    paths = []
    for i, seconds in enumerate((3.0, 1.0, 2.0)):
        path = tmp_path / f"{i}.json"
        path.write_text(
            json.dumps(
                {"mode": "xdist", "workers": 2, "wall_seconds": seconds, "exit_code": 0}
            )
        )
        paths.append(path)
    assert ci_profile.compare(paths)[0] == {
        "mode": "xdist",
        "series": "pytest",
        "workers": 2,
        "samples": 3,
        "median": 2.0,
        "minimum": 1.0,
        "maximum": 3.0,
        "failures": 0,
    }
