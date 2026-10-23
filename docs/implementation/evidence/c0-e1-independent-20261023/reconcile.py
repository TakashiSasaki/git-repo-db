"""Reconcile ordinary test identities and retain additional unittest subreports."""

import collections
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    raw = Path(__file__).resolve().parent / "raw"
    nodes = [
        s.strip()
        for s in (raw / "collection.log").read_text().splitlines()
        if s.startswith("tests/") and "::" in s
    ]
    expected = collections.Counter(nodes)
    events = [json.loads(s) for s in (raw / "journal.jsonl").read_text().splitlines()]
    starts = collections.Counter(e["nodeid"] for e in events if e["event"] == "start")
    phases = collections.Counter(
        (e["nodeid"], e["phase"]) for e in events if e["event"] == "phase"
    )
    outcomes = collections.Counter(
        e["outcome"] for e in events if e["event"] == "phase"
    )
    finishes = [e for e in events if e["event"] == "finish"]
    xml = ET.parse(raw / "tests.xml")
    cases = list(xml.iter("testcase"))

    def key(node):
        prefix, bracket, parameter = node.partition("[")
        parts = prefix.split("::")
        return (
            ".".join([parts[0][:-3].replace("/", "."), *parts[1:-1]]),
            parts[-1] + bracket + parameter,
        )

    junit = collections.Counter(
        (c.attrib["classname"], c.attrib["name"]) for c in cases
    )
    checks = {
        "unique_collection": len(expected) == len(nodes) == 280,
        "collection_equals_starts": expected == starts,
        "collection_equals_junit": collections.Counter(key(n) for n in nodes) == junit,
        "only_selected_phase_nodes": {n for n, _ in phases} == set(nodes),
        "one_setup_and_teardown": all(
            phases[n, p] == 1 for n in nodes for p in ("setup", "teardown")
        ),
        "every_node_called": all(phases[n, "call"] >= 1 for n in nodes),
        "all_phase_reports_passed": set(outcomes) == {"passed"},
        "junit_no_non_success": all(
            c.find(t) is None for c in cases for t in ("failure", "error", "skipped")
        ),
        "session_completed_zero": len(finishes) == 1
        and finishes[0]["status"] == "completed"
        and finishes[0]["exitstatus"] == 0,
        "process_exit_zero": next(
            c
            for c in json.loads((raw / "checks.json").read_text())
            if c["name"] == "pytest"
        )["exit_code"]
        == 0,
        "same_source_inputs": json.loads((raw / "execution.json").read_text())[
            "inputs_unchanged"
        ],
    }
    extra = sum(phases[n, "call"] - 1 for n in nodes)
    checks["separate_57_extra_subtest_reports"] = extra == 57
    result = {
        "consistent": all(checks.values()),
        "checks": checks,
        "ordinary_nodes": len(nodes),
        "junit_testcase_elements": len(cases),
        "junit_suite_counters": [s.attrib for s in xml.iter("testsuite")],
        "extra_passing_call_reports": extra,
        "phase_outcomes": dict(outcomes),
        "finishes": finishes,
        "exit_code": 0 if all(checks.values()) else 1,
    }
    (raw / "reconciliation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(result["exit_code"])


if __name__ == "__main__":
    main()
