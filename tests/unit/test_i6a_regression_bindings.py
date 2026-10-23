"""Source provenance must survive the classifier's plain/gzip transport."""

import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts.classify_i6a_regressions import run_index

BINDING = {
    "head": "1" * 40,
    "tree": "2" * 40,
    "inputs": {"src/repo_catalog/example.py": "3" * 64},
    "status": "",
}


def write_binding(directory, name, value, compressed):
    raw = json.dumps(value).encode()
    path = directory / f"binding-{name}.json"
    if compressed:
        path = path.with_suffix(".json.gz")
        raw = gzip.compress(raw, mtime=0)
    path.write_bytes(raw)


@pytest.fixture
def run_directory(tmp_path):
    """One real-shaped completed protocol isolates binding validation."""
    node = "tests/unit/test_example.py::test_example"
    (tmp_path / "ordinary.selected.txt").write_text(node + "\n")
    (tmp_path / "ordinary.xml").write_text(
        '<testsuites><testsuite><testcase classname="tests.unit.test_example" '
        'name="test_example"/></testsuite></testsuites>'
    )
    phases = [
        {"nodeid": node, "phase": phase, "outcome": "passed", "duration": 0.1}
        for phase in ("setup", "call", "teardown")
    ]
    events = [
        {"event": "start", "nodeid": node},
        *[{"event": "phase", **phase} for phase in phases],
        {"event": "finish", "status": "completed", "exitstatus": 0},
    ]
    (tmp_path / "ordinary.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    (tmp_path / "ordinary.report-types.jsonl").write_text(
        "".join(
            json.dumps({**phase, "subtest_context": None}) + "\n" for phase in phases
        )
    )
    (tmp_path / "ordinary.execution.json").write_text('{"exit_code": 0}')
    return tmp_path


@pytest.mark.parametrize(
    "before_compressed,after_compressed",
    [(False, False), (True, True), (False, True), (True, False)],
)
def test_binding_transports_are_actually_compared(
    run_directory, before_compressed, after_compressed
):
    write_binding(run_directory, "before", BINDING, before_compressed)
    write_binding(run_directory, "after", BINDING, after_compressed)
    index, receipt = run_index(run_directory)
    assert len(index) == 1
    assert receipt["consistent"] is True
    assert receipt["checks"]["source_bindings_complete_and_unchanged"] is True
    assert receipt["source_binding_before"] == BINDING
    assert receipt["source_binding_after"] == BINDING


@pytest.mark.parametrize("missing", ["before", "after", "both"])
@pytest.mark.parametrize("compressed", [False, True])
def test_absent_binding_is_explicitly_inconsistent(run_directory, missing, compressed):
    for name in ("before", "after"):
        if missing not in (name, "both"):
            write_binding(run_directory, name, BINDING, compressed)
    with pytest.raises(
        ValueError, match='"source_bindings_complete_and_unchanged": false'
    ):
        run_index(run_directory)


@pytest.mark.parametrize("field", ["head", "tree", "inputs", "status"])
@pytest.mark.parametrize("compressed", [False, True])
def test_changed_binding_is_not_consistent(run_directory, field, compressed):
    after = copy.deepcopy(BINDING)
    after[field] = {
        "head": "4" * 40,
        "tree": "5" * 40,
        "inputs": {"src/repo_catalog/example.py": "6" * 64},
        "status": " M source.py\n",
    }[field]
    write_binding(run_directory, "before", BINDING, compressed)
    write_binding(run_directory, "after", after, compressed)
    with pytest.raises(
        ValueError, match='"source_bindings_complete_and_unchanged": false'
    ):
        run_index(run_directory)


@pytest.mark.parametrize("field", ["head", "tree", "inputs", "status"])
def test_matching_incomplete_bindings_are_rejected(run_directory, field):
    binding = copy.deepcopy(BINDING)
    del binding[field]
    for name in ("before", "after"):
        write_binding(run_directory, name, binding, True)
    with pytest.raises(
        ValueError, match='"source_bindings_complete_and_unchanged": false'
    ):
        run_index(run_directory)


@pytest.mark.parametrize("digest", [None, "not-a-digest", "0" * 63])
def test_matching_invalid_input_hashes_do_not_prove_binding(run_directory, digest):
    binding = copy.deepcopy(BINDING)
    binding["inputs"]["src/repo_catalog/example.py"] = digest
    for name in ("before", "after"):
        write_binding(run_directory, name, binding, True)
    with pytest.raises(
        ValueError, match='"source_bindings_complete_and_unchanged": false'
    ):
        run_index(run_directory)


@pytest.mark.parametrize("name,selected", [("before", 5941), ("after-final", 5974)])
def test_frozen_compressed_evidence_is_reloaded_without_rewriting(name, selected):
    root = Path(__file__).resolve().parents[2]
    directory = (
        root / "docs/implementation/evidence/adr0031-i6a/remediation-20261023" / name
    )
    _, receipt = run_index(directory)
    assert receipt["consistent"] is True
    assert receipt["selected"] == selected
    assert receipt["checks"]["source_bindings_complete_and_unchanged"] is True
    assert receipt["source_binding_before"] == receipt["source_binding_after"]
    assert len(receipt["source_binding_before"]["inputs"]) > 0
