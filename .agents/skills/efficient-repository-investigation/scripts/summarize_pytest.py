"""Bounded consistency summary of actual git-repo-db pytest evidence."""

import argparse
import collections
import gzip
import itertools
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def open_text(path):
    return (
        gzip.open(path, "rt", encoding="utf-8")
        if path.suffix == ".gz"
        else path.open(encoding="utf-8")
    )


def junit_key(node):
    prefix, bracket, parameter = node.partition("[")
    parts = prefix.split("::")
    return (
        ".".join([parts[0][:-3].replace("/", "."), *parts[1:-1]]),
        parts[-1] + bracket + parameter,
    )


def summarize(args):
    with open_text(args.nodes) as stream:
        nodes = [
            line.strip()
            for line in stream
            if line.startswith("tests/") and "::" in line
        ]
    expected = collections.Counter(nodes)
    starts = collections.Counter()
    phases = collections.Counter()
    outcomes = collections.Counter()
    finishes = []
    with open_text(args.journal) as stream:
        for line in stream:
            if not line.strip():
                continue
            event = json.loads(line)
            kind = event["event"]
            if kind == "start":
                starts[event["nodeid"]] += 1
            elif kind == "phase":
                phases[(event["nodeid"], event["phase"])] += 1
                outcomes[event["outcome"]] += 1
            elif kind == "finish":
                finishes.append((event.get("status"), event.get("exitstatus")))
            else:
                raise ValueError("Unknown journal event: " + str(kind))
    junit = collections.Counter()
    results = collections.Counter()
    with open_text(args.junit) as stream:
        for _, element in ET.iterparse(stream, events=("end",)):
            if element.tag != "testcase":
                continue
            junit[(element.attrib["classname"], element.attrib["name"])] += 1
            result = next(
                (
                    tag
                    for tag in ("failure", "error", "skipped")
                    if element.find(tag) is not None
                ),
                "passed",
            )
            results[result] += 1
            element.clear()
    with open_text(args.execution) as stream:
        execution = json.load(stream)
    expected_phases = collections.Counter(
        {
            (node, phase): 1
            for node in expected
            for phase in ("setup", "call", "teardown")
        }
    )
    checks = {
        "nonempty_unique_selected": bool(expected)
        and all(n == 1 for n in expected.values()),
        "selected_equals_starts": expected == starts,
        "selected_equals_junit": collections.Counter(junit_key(n) for n in nodes)
        == junit,
        "each_phase_exactly_once": expected_phases == phases,
        "all_phases_passed": outcomes
        == collections.Counter({"passed": len(expected) * 3}),
        "junit_all_passed": results == collections.Counter({"passed": len(expected)}),
        "successful_finish": finishes == [("completed", 0)],
        "process_exit_zero": type(execution.get("exit_code")) is int
        and execution["exit_code"] == 0,
    }
    return {
        "consistent_success": all(checks.values()),
        "selected": len(nodes),
        "starts": sum(starts.values()),
        "junit": sum(junit.values()),
        "phases": sum(phases.values()),
        "junit_results": dict(results),
        "checks": checks,
        "missing_start_examples": [
            node[:200] for node in itertools.islice((expected - starts).elements(), 8)
        ],
        "extra_start_examples": [
            node[:200] for node in itertools.islice((starts - expected).elements(), 8)
        ],
        "execution_source": {key: execution.get(key) for key in ("head", "tree")},
        "scope": "Evidence consistency only; not source binding, authenticity or Release Acceptance.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("nodes", "junit", "journal", "execution"):
        parser.add_argument("--" + name, type=Path, required=True)
    try:
        result = summarize(parser.parse_args())
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        print(json.dumps({"consistent_success": False, "error": str(error)[:400]}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["consistent_success"] else 1


if __name__ == "__main__":
    sys.exit(main())
