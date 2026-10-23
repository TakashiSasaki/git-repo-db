"""Audit I6-A failure identities, signatures and first reached boundaries.

This is a reporting tool, not an acceptance gate or a failure suppression list.
Each input run remains independent; focused/installed/hosted repetitions must
never be passed as additional cohorts of an ordinary invocation.
"""

import argparse
import ast
import gzip
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from functools import lru_cache
from pathlib import Path


def read(path):
    path = Path(path)
    if not path.exists():
        path = Path(str(path) + ".gz")
    raw = path.read_bytes()
    return gzip.decompress(raw) if path.suffix == ".gz" else raw


def json_read(path):
    return json.loads(read(path))


@lru_cache(maxsize=None)
def source_tree(path):
    source = path.read_text()
    return ast.parse(source), source.splitlines()


def rows(path):
    return [json.loads(line) for line in read(path).splitlines() if line]


def junit_key(node):
    head, bracket, parameter = node.partition("[")
    parts = head.split("::")
    parts[-1] += bracket + parameter
    return (
        parts[0].removesuffix(".py").replace("/", ".")
        + "".join("." + part for part in parts[1:-1]),
        parts[-1],
    )


def normalize_path(path):
    for prefix in ("tests/", "src/repo_catalog/"):
        if prefix in path:
            return prefix + path.split(prefix, 1)[1]
    if "/repo_catalog/" in path:
        return "src/repo_catalog/" + path.split("/repo_catalog/", 1)[1]
    return path


def trace_frames(trace):
    frames = []
    for path, line, function in re.findall(
        r"^([^\n:]+\.py):(\d+):(?: in (\w+))?", trace, re.M
    ):
        path = normalize_path(path)
        if path.startswith(("tests/", "src/")):
            frames.append({"path": path, "line": int(line), "function": function})
    for path, line, function in re.findall(
        r'File "([^\n"]+\.py)", line (\d+), in (\w+)', trace
    ):
        path = normalize_path(path)
        if path.startswith(("tests/", "src/")):
            frame = {"path": path, "line": int(line), "function": function}
            if frame not in frames:
                frames.append(frame)
    return frames


def exception(message):
    match = re.search(
        r"(?:^|[\"\n])([A-Za-z_][\w.]*(?:Error|Refused|Stage|Failure)):", message
    )
    return match.group(1) if match else None


def signature(result):
    return (
        result["phase"],
        result["message"],
        tuple((frame["path"], frame["function"]) for frame in result["frames"]),
    )


def stage_refusal(message):
    match = re.search(
        r"I2_(?:TRANSFER|IDENTIFICATION_WIRE)_UNSUPPORTED(?:: [^\n\\]*)?",
        message,
    )
    return match.group() if match else None


def run_index(directory, prefix="ordinary"):
    selected = read(directory / (prefix + ".selected.txt")).decode().splitlines()
    events = rows(directory / (prefix + ".jsonl"))
    reports = rows(directory / (prefix + ".report-types.jsonl"))
    execution = json_read(directory / (prefix + ".execution.json"))
    binding_before_path = directory / "binding-before.json"
    binding_after_path = directory / "binding-after.json"
    binding_before = (
        json_read(binding_before_path) if binding_before_path.exists() else None
    )
    binding_after = (
        json_read(binding_after_path) if binding_after_path.exists() else None
    )
    keys = {junit_key(node): node for node in selected}
    if len(keys) != len(selected):
        raise ValueError("duplicate or ambiguous selected identity")
    index = {}
    for case in ET.fromstring(read(directory / (prefix + ".xml"))).findall(
        ".//testcase"
    ):
        key = (case.get("classname"), case.get("name"))
        if key not in keys:
            raise ValueError(f"JUnit case not selected: {key}")
        node = keys[key]
        if node in index:
            raise ValueError(f"duplicate JUnit node: {node}")
        result = {"outcome": "passed", "phase": None, "message": "", "frames": []}
        for tag, phase in (("failure", "call"), ("error", "setup"), ("skipped", None)):
            event = case.find(tag)
            if event is None:
                continue
            message, trace = event.get("message", ""), event.text or ""
            result = {
                "outcome": {
                    "failure": "failed",
                    "error": "error",
                    "skipped": "skipped",
                }[tag],
                "phase": "teardown" if "failed on teardown" in message else phase,
                "message": message,
                "exception": exception(message),
                "frames": trace_frames(trace),
                "trace_sha256": hashlib.sha256(trace.encode()).hexdigest(),
            }
            break
        index[node] = result

    def phase_key(event):
        return (
            event["nodeid"],
            event["phase"],
            event["outcome"],
            round(event["duration"], 6),
        )

    main = [r for r in reports if r["subtest_context"] is None]
    subtests = [r for r in reports if r["subtest_context"] is not None]
    phases = Counter((r["nodeid"], r["phase"]) for r in main)
    setup = {r["nodeid"]: r["outcome"] for r in main if r["phase"] == "setup"}
    finishes = [event for event in events if event["event"] == "finish"]
    checks = {
        "selected_unique": len(selected) == len(set(selected)),
        "selected_equals_junit": set(index) == set(selected),
        "selected_equals_starts": Counter(selected)
        == Counter(e["nodeid"] for e in events if e["event"] == "start"),
        "raw_phase_sidecar_multisets_equal": Counter(
            phase_key(e) for e in events if e["event"] == "phase"
        )
        == Counter(phase_key(r) for r in reports),
        "main_phase_nodes_equal_selected": {r["nodeid"] for r in main} == set(selected),
        "main_setup_teardown_once": all(
            phases[node, phase] == 1
            for node in selected
            for phase in ("setup", "teardown")
        ),
        "main_call_once_after_successful_setup": all(
            phases[node, "call"] == int(setup.get(node) == "passed")
            for node in selected
        ),
        "no_duplicate_main_phases": all(count == 1 for count in phases.values()),
        "subtest_types_explicit": all(
            r["report_type"] == "_pytest.subtests.SubtestReport"
            and r["phase"] == "call"
            for r in subtests
        ),
        "subtests_have_selected_parent": all(r["nodeid"] in index for r in subtests),
        "subtest_failure_reflected_in_junit_parent": all(
            r["outcome"] != "failed" or index[r["nodeid"]]["outcome"] != "passed"
            for r in subtests
            if r["nodeid"] in index
        ),
        "one_completed_finish": len(finishes) == 1
        and finishes[0]["status"] in ("completed", "failed")
        and execution["exit_code"] in (0, 1)
        and finishes[0]["exitstatus"] == execution["exit_code"],
    }
    if binding_before is not None or binding_after is not None:
        checks["source_bindings_complete_and_unchanged"] = (
            binding_before is not None
            and binding_after is not None
            and all(
                binding_before.get(key) == binding_after.get(key)
                for key in ("head", "tree", "inputs", "status")
            )
        )
    receipt = {
        "checks": checks,
        "consistent": all(checks.values()),
        "counts": dict(Counter(r["outcome"] for r in index.values())),
        "selected": len(selected),
        "exit_code": execution["exit_code"],
        "subtest_count": len(subtests),
        "subtest_outcomes": dict(Counter(r["outcome"] for r in subtests)),
        "finishes": finishes,
        "source_binding_before": binding_before,
        "source_binding_after": binding_after,
        "inputs": {
            name: hashlib.sha256(read(directory / (prefix + suffix))).hexdigest()
            for name, suffix in (
                ("junit", ".xml"),
                ("journal", ".jsonl"),
                ("sidecar", ".report-types.jsonl"),
                ("selected", ".selected.txt"),
                ("execution", ".execution.json"),
            )
        },
    }
    if not receipt["consistent"]:
        raise ValueError(f"inconsistent run: {json.dumps(receipt)}")
    return index, receipt


def classify(result, root, supplemental=None):
    frames = result["frames"]
    for frame in frames:
        path, line = frame["path"], frame["line"]
        if path == "src/repo_catalog/adapters/sqlite/context_admission.py":
            source = (root / path).read_text().splitlines()
            if (
                0 < line <= len(source)
                and 'raise AdmissionRefused("PERMISSION_DENIED")' in source[line - 1]
            ):
                # This exact branch is verified against the frozen source, not
                # every permission failure or a test's future stage name.
                before = "\n".join(source[max(0, line - 4) : line])
                if "not isinstance(service, ContextAdmissionService)" in before:
                    if any(
                        f["path"] == "src/repo_catalog/adapters/sqlite/recovery.py"
                        for f in frames
                    ):
                        return (
                            "recovery_context_composition_unconnected",
                            "I7",
                            "production_callsite",
                            False,
                        )
                    coordinator = any(
                        f["path"].endswith("/p1_coordination.py") for f in frames
                    )
                    return (
                        "coordinator_missing_explicit_authority"
                        if coordinator
                        else "direct_missing_explicit_authority",
                        "I6-A",
                        "fixture",
                        False,
                    )
        if path in (
            "src/repo_catalog/application/acquisition.py",
            "src/repo_catalog/application/exchange.py",
        ):
            source = (root / path).read_text().splitlines()
            if (
                0 < line <= len(source)
                and 'raise AdmissionRefused("PERMISSION_DENIED")' in source[line - 1]
            ):
                return (
                    "unconnected_provider_exchange_guard",
                    "I6-C",
                    "unsupported_route",
                    True,
                )
    if supplemental and any(
        f["function"] == "_open_context"
        and f["path"].endswith("/application/acquisition.py")
        for f in supplemental
    ):
        return (
            "unconnected_provider_exchange_guard",
            "I6-C",
            "unsupported_route",
            True,
        )
    if "I2_IDENTIFICATION_WIRE_UNSUPPORTED" in result["message"]:
        return ("unimplemented_identification_wire", "I6-B", "unsupported_route", True)
    if "I2_TRANSFER_UNSUPPORTED" in result["message"]:
        return ("retained_transfer_stage_refusal", "I6-C", "unsupported_route", True)
    return ("requires_trace_review", "other/unresolved", "unresolved", False)


def production_callers(root, result):
    callers = []
    for frame in result["frames"]:
        if not frame["path"].startswith("src/"):
            continue
        path = root / frame["path"]
        if not path.exists():
            callers.append(frame)
            continue
        tree, lines = source_tree(path)
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.lineno <= frame["line"] <= node.end_lineno
        ]
        function = (
            min(functions, key=lambda node: node.end_lineno - node.lineno)
            if functions
            else None
        )
        callers.append(
            {
                **frame,
                "enclosing_function_from_source": function.name if function else None,
                "source_line": lines[frame["line"] - 1]
                if 0 < frame["line"] <= len(lines)
                else None,
            }
        )
    return callers


def function_assertions(root, node):
    path, *parts = node.split("::")
    source = root / path
    if not source.exists():
        return None
    name = parts[-1].split("[", 1)[0]
    functions = [
        item
        for item in ast.walk(source_tree(source)[0])
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    ]
    if len(functions) != 1:
        return None
    return [
        {"line": item.lineno, "ast": ast.dump(item, include_attributes=False)}
        for item in ast.walk(functions[0])
        if isinstance(item, ast.Assert)
    ]


def reachability(root, node, result, observations=None):
    assertions = function_assertions(root, node)
    if result["phase"] == "setup":
        status = "test_body_not_entered"
    elif result["outcome"] == "passed":
        status = (
            "test_body_completed; conditional assertion branch coverage is not inferred"
        )
    else:
        status = (
            "failed_call; assertions beyond the reached exception remain unverified"
        )
    test_frames = [f for f in result["frames"] if f["path"].startswith("tests/")]
    result = {
        "status": status,
        "test_trace_frames": test_frames,
        "local_test_function_identified": assertions is not None,
        "assertion_lines_in_test_function": [a["line"] for a in assertions or []],
        "per_assertion_execution": "not instrumented; traceback and test phase establish only the stated bound",
    }
    if observations is not None and node in observations:
        observed = observations[node]
        result["actual_assertion_line_observations_by_phase"] = observed
        result["per_assertion_execution"] = (
            "Actual traced entry to listed assertion statement source lines; subexpression coverage and spawned threads are not inferred"
        )
        body = observed.get("call", {}).get(node.split("::")[0], [])
        result["actual_test_function_assertion_lines_entered"] = sorted(
            set(body) & {a["line"] for a in assertions or []}
        )
    return result


def assertion_observations(directory):
    if directory is None:
        return None, None
    observations, starts, finishes, sessions = {}, Counter(), Counter(), []
    files = sorted(directory.glob("*.jsonl"))
    if not files:
        raise ValueError("assertion trace files absent")
    for path in files:
        entries = rows(path)
        configured = [entry for entry in entries if entry["event"] == "configure"]
        ended = [entry for entry in entries if entry["event"] == "session_finish"]
        if (
            len(configured) != 1
            or configured[0]["optimization"] != 0
            or len(ended) != 1
            or ended[0]["exitstatus"] not in (0, 1)
        ):
            raise ValueError("assertion trace worker lifecycle incomplete")
        sessions.append(
            {
                "file": path.name,
                "source": configured[0]["source"],
                "exitstatus": ended[0]["exitstatus"],
                "sha256": hashlib.sha256(read(path)).hexdigest(),
            }
        )
        for entry in entries:
            event = entry["event"]
            node = entry.get("nodeid")
            if event == "node_start":
                starts[node] += 1
                observations.setdefault(node, {})
            elif event == "node_finish":
                finishes[node] += 1
            elif event == "assertion_line":
                if (
                    entry["phase"] not in ("setup", "call", "teardown")
                    or not entry["path"].startswith("tests/")
                    or node not in observations
                ):
                    raise ValueError("invalid assertion-line observation")
                observations[node].setdefault(entry["phase"], {}).setdefault(
                    entry["path"], []
                ).append(entry["line"])
    if starts != finishes or any(count != 1 for count in starts.values()):
        raise ValueError("assertion trace node starts/finishes differ or repeat")
    for observed in observations.values():
        for paths in observed.values():
            for path, lines in paths.items():
                paths[path] = sorted(set(lines))
    return observations, {
        "sessions": sessions,
        "node_count": len(observations),
        "start_finish_multisets_equal_unique": True,
    }


def supplemental_frames(path):
    supplements = {}
    if path:
        trace = json_read(path)
        if trace["exitstatus"] != 1:
            raise ValueError("supplemental diagnostic must retain its measured failure")
        for record in trace["records"]:
            frame = record["raise_frame"]
            supplements.setdefault(record["nodeid"], []).append(
                {
                    "path": normalize_path(frame["file"]),
                    "line": frame["line"],
                    "function": frame["function"],
                }
            )
    return supplements


def build(args):
    root = args.source_root.resolve()
    evidence = root / "docs/implementation/evidence/adr0031-i6a/author"
    historical_rows = json_read(
        evidence / "final-v3/inherited-79-node-phase-exception-assertion-map.json"
    )["rows"]
    historical = {(r["class"], r["name"]): r for r in historical_rows}
    frozen_additional = json_read(
        evidence / "final-v3/additional-failure-classification.json"
    )["rows"]
    additional = {(r["classname"], r["name"]): r for r in frozen_additional}
    before, before_receipt = run_index(args.before)
    after, after_receipt = run_index(args.after) if args.after else ({}, None)
    supplements = supplemental_frames(args.supplemental)
    after_supplements = supplemental_frames(args.after_supplemental)
    before_assertion_observations, before_assertion_receipt = assertion_observations(
        args.before_assertions
    )
    after_assertion_observations, after_assertion_receipt = assertion_observations(
        args.after_assertions
    )
    if before_assertion_receipt:
        before_assertion_receipt["matches_before_failure_nodes"] = set(
            before_assertion_observations
        ) == {node for node, result in before.items() if result["outcome"] != "passed"}
    if after_assertion_receipt:
        after_assertion_receipt["matches_full_after_nodes"] = set(
            after_assertion_observations
        ) == set(after)
    ledger, inherited = [], []
    for node, old in sorted(before.items()):
        if old["outcome"] == "passed":
            continue
        key = junit_key(node)
        historic = historical.get(key)
        new = after.get(node)
        cat, owner, carrier, refusal = classify(
            old, args.before_source, supplements.get(node)
        )
        old141 = (
            historic["baseline"]
            if historic
            else {"phase": None, "message": "", "frames": [], "outcome": "passed"}
        )
        if historic:
            comparison = {
                "nodeid": node,
                "baseline141": old141,
                "before143": old,
                "after": new,
                "same_phase": old["phase"] == old141["phase"],
                "same_message": old["message"] == old141["message"],
                "same_stage_refusal": bool(
                    old141.get("stage_refusal")
                    and stage_refusal(old["message"]) == old141["stage_refusal"]
                ),
                "same_exception": old.get("exception")
                == historic["baseline_exception"],
                "same_paths_functions": [
                    (f["path"], f["function"]) for f in old["frames"]
                ]
                == [(f["path"], f["function"]) for f in old141["frames"]],
                "same_full_signature": signature(old) == signature(old141),
                "before_reachability": reachability(
                    args.before_source, node, old, before_assertion_observations
                ),
                "after_reachability": reachability(
                    root, node, new, after_assertion_observations
                )
                if new
                else None,
            }
            inherited.append(comparison)
        test_frames = [f for f in old["frames"] if f["path"].startswith("tests/")]
        semantic = [f for f in old["frames"] if f["path"].startswith("src/")]
        repair = sorted({f["path"] for f in test_frames}) or [node.split("::")[0]]
        after_category = (
            classify(new, root, after_supplements.get(node))
            if new and new["outcome"] != "passed"
            else None
        )
        before_assertions = function_assertions(args.before_source, node)
        after_assertions = function_assertions(root, node)
        ledger.append(
            {
                "nodeid": node,
                "historical79": bool(historic),
                "additional664": key in additional,
                "phase_before": old["phase"],
                "exception_141": historic["baseline_exception"] if historic else None,
                "exception_before": old.get("exception"),
                "first_semantic_failure_location": semantic[-1] if semantic else None,
                "production_call_chain_before": production_callers(
                    args.before_source, old
                ),
                "production_call_chain_after": production_callers(root, new)
                if new
                else None,
                "category_before": cat,
                "responsible_stage_before": owner,
                "caller_carrier": carrier,
                "expected_stage_refusal": refusal,
                "new_implementation_defect": "fixture migration required"
                if owner == "I6-A"
                else "not inferred from first refusal",
                "candidate_repair_files": repair if owner == "I6-A" else [],
                "before": old,
                "after": new,
                "after_category": after_category[0] if after_category else None,
                "after_responsible_stage": after_category[1]
                if after_category
                else None,
                "before_reachability": reachability(
                    args.before_source, node, old, before_assertion_observations
                ),
                "after_reachability": reachability(
                    root, node, new, after_assertion_observations
                )
                if new
                else None,
                "test_function_assertion_asts_preserved": [
                    a["ast"] for a in before_assertions or []
                ]
                == [a["ast"] for a in after_assertions or []]
                if before_assertions is not None and after_assertions is not None
                else None,
                "handoff_condition": "Explicit finite trusted fixture/composition authority; rerun original behavior assertions"
                if owner == "I6-A"
                else "Separately authorized I6-B/C wiring and exact originals; preserve current refusal until integrated acceptance"
                if owner.startswith("I6-")
                else "Inspect exact traceback before assigning ownership",
            }
        )
    additional_nodes = [r for r in ledger if r["additional664"]]
    result = {
        "scope": "Fresh ordinary before/after results only; historical source is separately labeled. No focused/installed/hosted counts are added.",
        "before_receipt": before_receipt,
        "after_receipt": after_receipt,
        "before_assertion_trace_receipt": before_assertion_receipt,
        "after_assertion_trace_receipt": after_assertion_receipt,
        "baseline141_historical79_count": len(historical),
        "fresh_historical79_retained_failure_nodes": len(inherited),
        "fresh_additional664_matched_nodes": len(additional_nodes),
        "fresh_extra_failure_nodes": [
            r["nodeid"]
            for r in ledger
            if not r["historical79"] and not r["additional664"]
        ],
        "historical_signature_counts": {
            key: sum(r[key] for r in inherited)
            for key in (
                "same_phase",
                "same_message",
                "same_stage_refusal",
                "same_exception",
                "same_paths_functions",
                "same_full_signature",
            )
        },
        "changed_full_signature_nodes": [
            r["nodeid"] for r in inherited if not r["same_full_signature"]
        ],
        "additional_before_categories": dict(
            Counter(r["category_before"] for r in additional_nodes)
        ),
        "additional_after_outcomes": dict(
            Counter(
                r["after"]["outcome"] if r["after"] else "not_run"
                for r in additional_nodes
            )
        ),
        "additional_after_categories": dict(
            Counter(
                r["after_category"] for r in additional_nodes if r["after_category"]
            )
        ),
        "new_after_failures": [
            {"nodeid": node, **result}
            for node, result in after.items()
            if result["outcome"] != "passed"
            and before.get(node, {}).get("outcome") == "passed"
        ],
        "after_nodes_missing": sorted(set(before) - set(after)) if args.after else [],
        "after_nodes_added": sorted(set(after) - set(before)) if args.after else [],
        "rows": ledger,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "failure-ledger.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    (args.output / "historical79-signature-audit.json").write_text(
        json.dumps(inherited, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key
                not in ("rows", "changed_full_signature_nodes", "new_after_failures")
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--before-source", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--supplemental", type=Path)
    parser.add_argument("--after-supplemental", type=Path)
    parser.add_argument("--before-assertions", type=Path)
    parser.add_argument("--after-assertions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
