"""Independent read-only audit of actual plan/profile/XML and Git input binding.

This does not execute the project's gate or accept incomplete/failed receipts.
"""
import argparse
from collections import Counter
import fnmatch
import hashlib
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def xml_nodes(path, repo):
    output = []
    for case in ET.parse(path).getroot().iter("testcase"):
        parts = case.attrib.get("classname", "unknown").split(".")
        file_name = case.attrib.get("file")
        classes = []
        if not file_name:
            for count in range(len(parts), 0, -1):
                candidate = "/".join(parts[:count]) + ".py"
                if (repo / candidate).is_file():
                    file_name, classes = candidate, parts[count:]
                    break
        file_name = file_name or "/".join(parts) + ".py"
        status = next((name for name in ("failure", "error", "skipped") if case.find(name) is not None), "passed")
        output.append({"nodeid": "::".join([file_name, *classes, case.attrib["name"]]), "status": status})
    return output


def audit(repo, artifacts, expected_sha):
    plan = json.loads((artifacts / "plan.json").read_text())
    context = plan["context"]
    tested = context["tested_sha"]
    tree = git(repo, "rev-parse", tested + "^{tree}").decode().strip()
    entries = {}
    for row in git(repo, "ls-tree", "-rz", "--full-tree", tested).split(b"\0"):
        if row:
            metadata, path = row.split(b"\t", 1)
            entries[path.decode("utf-8", "surrogateescape")] = metadata.decode().split()
    rules = json.loads(git(repo, "show", tested + ":scripts/ci_dependencies.json"))
    acceptance_files = sorted(path for path in entries if any(path.startswith(directory + "/") for directory in rules["acceptance_directories"]) and (Path(path).name.startswith("test_") or Path(path).name.endswith("_test.py")) and path.endswith(".py"))
    calculated = {
        "policy_hash": digest({path: entries.get(path) for path in rules["policy_inputs"]}),
        "tree_hash": digest(entries),
        "acceptance_input_hash": digest({path: entry for path, entry in entries.items() if path in acceptance_files or matches(path, rules["shared_inputs"] + rules["executable_inputs"]) or not matches(path, rules["prose"] + rules.get("report_inputs", []))}),
    }
    selected = plan.get("selected_ids", [])
    selected_text = sorted(line.strip() for line in (artifacts / "selected-tests.txt").read_text().splitlines() if "::" in line and line.strip().startswith("tests/"))
    issues = []
    if tested != expected_sha:
        issues.append("tested SHA differs from expected frozen SHA")
    for key, value in calculated.items():
        if plan.get(key) != value:
            issues.append("independently calculated " + key + " differs")
    if acceptance_files != plan["acceptance_files"]:
        issues.append("acceptance file inventory differs")
    if selected != selected_text or len(selected) != len(set(selected)):
        issues.append("selected node inventory mismatched or duplicate")
    profiles, executed = {}, []
    for lane in ("tests", "packaging"):
        profile_path, xml_path = artifacts / (lane + ".json"), artifacts / (lane + ".xml")
        expected = plan["lanes"][lane].get("test_ids", [])
        if not profile_path.exists() or not xml_path.exists():
            profiles[lane] = {"complete": False, "records_available": False, "expected_count": len(expected), "unexecuted_nodeids": sorted(expected)}
            issues.append(lane + " complete profile/XML unavailable")
            continue
        profile = json.loads(profile_path.read_text())
        actual = xml_nodes(xml_path, repo)
        normalized = [{"nodeid": row["nodeid"], "status": row["status"]} for row in profile["junit"]["tests"]]
        node_ids = [row["nodeid"] for row in actual]
        if actual != normalized:
            issues.append(lane + " XML/profile node/status differs")
        if sorted(node_ids) != sorted(expected) or len(node_ids) != len(set(node_ids)):
            issues.append(lane + " expected/actual node IDs differ")
        statuses = Counter(row["status"] for row in actual)
        if profile["exit_code"] or set(statuses) != {"passed"}:
            issues.append(lane + " failed/skipped/error exit or node status")
        meta = profile["runtime"]
        if meta["commit_sha"] != tested or meta.get("tracked_changes") or any(meta[key] != plan["runtime"][key] for key in ("python", "sqlite")):
            issues.append(lane + " actual run revision/runtime differs")
        if context.get("run_id") and any(str(meta.get(key)) != str(context.get(key)) for key in ("run_id", "run_attempt", "feature_sha")):
            issues.append(lane + " actual run/attempt/feature differs")
        executed.extend(node_ids)
        profiles[lane] = {"complete": sorted(node_ids) == sorted(expected) and len(node_ids) == len(set(node_ids)), "records_available": True, "count": len(actual), "expected_count": len(expected), "status_counts": dict(statuses), "exit_code": profile["exit_code"], "runtime": meta, "xml_sha256": sha(xml_path), "profile_sha256": sha(profile_path), "nonpassing_nodeids": [row["nodeid"] for row in actual if row["status"] != "passed"], "unexecuted_nodeids": sorted(set(expected) - set(node_ids)), "unexpected_nodeids": sorted(set(node_ids) - set(expected))}
    if sorted(executed) != selected or len(executed) != len(set(executed)):
        issues.append("complete executed set differs from selected set")
    command_names = {"static": ["lint", "format"], "smoke": ["fts", "doctor"], "dependencies": ["dependency-setup"], "wheelhouse": ["wheelhouse"]}
    command_profiles = {}
    expected_commands = ["planning", "report-validation"]
    for lane, names in command_names.items():
        item = plan["lanes"].get(lane) or plan["preparation"][lane]
        if item["disposition"] == "selected":
            expected_commands.extend(names)
        elif any((artifacts / (name + ".json")).exists() for name in names):
            issues.append(lane + " contains unexpected unselected result")
    for name in expected_commands:
        path = artifacts / (name + ".json")
        if not path.exists():
            issues.append(name + " complete profile unavailable")
            command_profiles[name] = {"complete": False}
            continue
        profile = json.loads(path.read_text())
        meta = profile["runtime"]
        correct_runtime = meta["commit_sha"] == tested and not meta.get("tracked_changes") and all(meta[key] == plan["runtime"][key] for key in ("python", "sqlite"))
        correct_run = not context.get("run_id") or all(str(meta.get(key)) == str(context.get(key)) for key in ("run_id", "run_attempt", "feature_sha"))
        if profile["exit_code"] or profile.get("measurement_error") or not correct_runtime or not correct_run or not math.isfinite(profile["wall_seconds"]) or profile["wall_seconds"] < 0:
            issues.append(name + " command failed or revision/runtime/run differs")
        command_profiles[name] = {"complete": True, "exit_code": profile["exit_code"], "runtime": meta, "sha256": sha(path)}
    mapping = json.loads(git(repo, "show", tested + ":tests/support/publication_free_node_dispositions.json"))
    old_node_bytes = git(repo, "show", tested + ":tests/support/publication_free_baseline_nodes.txt")
    old_nodes = old_node_bytes.decode().splitlines()
    mapped = [entry["baseline_node"] for entry in mapping["entries"]]
    same = mapping["still_collected_same_nodes"]
    accounted = mapped + same
    replacement_nodes = sorted({node for entry in mapping["entries"] for node in entry["replacement_nodes"]})
    ordinary = [node for node in selected if not node.startswith("tests/packaging/")]
    missing_replacements = sorted(set(replacement_nodes) - set(ordinary))
    if set(accounted) != set(old_nodes) or len(accounted) != len(set(accounted)):
        issues.append("baseline node disposition incomplete/duplicate")
    baseline_list_hash = hashlib.sha256(old_node_bytes).hexdigest()
    if mapping["node_list_sha256"]["baseline"] != baseline_list_hash:
        issues.append("baseline node list SHA256 differs from mapped receipt")
    baseline_functions = {node.split("[", 1)[0] for node in old_nodes}
    current_functions = {node.split("[", 1)[0] for node in ordinary}
    actual_removed_functions = sorted(baseline_functions - current_functions)
    if actual_removed_functions != mapping["removed_or_renamed_baseline_functions"] or len(actual_removed_functions) != mapping["removed_or_renamed_baseline_function_count"]:
        issues.append("removed/renamed function roster differs from selected current nodes")
    if missing_replacements:
        issues.append("mapped replacement nodes not selected")
    if len(ordinary) != mapping["current_collected_count"]:
        issues.append("disposition current collected count differs from actual selected ordinary")
    manifest = artifacts / "validation-manifest.json"
    manifest_record = json.loads(manifest.read_text()) if manifest.exists() else None
    if not manifest_record or manifest_record.get("outcome") != "passed" or not manifest_record.get("full_acceptance") or manifest_record.get("test_ids") != selected or manifest_record.get("acceptance_input_hash") != calculated["acceptance_input_hash"]:
        issues.append("matching full acceptance validation manifest unavailable")
    return {
        "status": "complete_passed" if not issues else "not_accepted",
        "expected_sha": expected_sha, "tested_sha": tested, "git_tree": tree,
        "feature_sha": context.get("feature_sha"), "context": context,
        "calculated_hashes": calculated, "runtime": plan["runtime"],
        "full": plan["full"], "acceptance_files": len(acceptance_files),
        "excluded_files": plan["excluded_files"], "unexecuted_files": plan["unexecuted_files"],
        "selected_count": len(selected), "selected_ordinary": len(ordinary),
        "profiles": profiles,
        "command_profiles": command_profiles,
        "dispositions": {"baseline_count": len(old_nodes), "baseline_list_sha256": baseline_list_hash, "explicit_count": len(mapped), "same_ids_count": len(same), "recorded_current_count": mapping["current_collected_count"], "recorded_current_node_list_sha256": mapping["node_list_sha256"]["current"], "actual_sorted_selected_ordinary_list_sha256": hashlib.sha256(("\n".join(ordinary) + "\n").encode()).hexdigest(), "removed_or_renamed_function_count": len(actual_removed_functions), "missing_replacements": missing_replacements, "ordinary_extra_over_mapped_plus_same": sorted(set(ordinary) - set(replacement_nodes) - set(same))},
        "manifest_sha256": sha(manifest) if manifest.exists() else None,
        "artifact_sha256": {path.name: sha(path) for path in sorted(artifacts.iterdir()) if path.is_file() and path.suffix in (".json", ".xml", ".txt")},
        "issues": issues,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.repo, args.artifacts, args.expected_sha)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "selected_count": report["selected_count"], "profiles": {name: {key: value for key, value in profile.items() if key in ("complete", "count", "status_counts", "exit_code")} for name, profile in report["profiles"].items()}, "issues": report["issues"]}, indent=2))
