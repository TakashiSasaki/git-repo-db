"""Execute current selections and report exactly what ran, failed or remained untested."""

import argparse
import base64
import glob
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ci_journal, ci_plan, ci_profile, resource_scheduler  # noqa: E402

MARKER = "not live and not benchmark"


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def collection_ids(text):
    nodes = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    if not nodes or len(nodes) != len(set(nodes)):
        raise ValueError("Missing/duplicate collection IDs")
    return sorted(nodes)


def collect(path):
    plan = read(path)
    files = sorted(
        p for name in ci_plan.TEST_LANES for p in plan["lanes"][name]["test_files"]
    )
    if not files:
        raise ValueError("No tests were selected")
    command = [
        "uv",
        "run",
        "--no-sync",
        "pytest",
        *files,
        "--strict-markers",
        "-m",
        MARKER,
        "--collect-only",
        "-q",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    nodes = collection_ids(result.stdout)
    (path.parent / "selected-tests.txt").write_text("\n".join(nodes) + "\n")
    for name in ci_plan.TEST_LANES:
        item = plan["lanes"][name]
        expected = sorted(n for n in nodes if n.split("::")[0] in item["test_files"])
        if {n.split("::")[0] for n in expected} != set(item["test_files"]):
            raise ValueError("Collection is missing an expected test file")
        item.update(
            test_ids=expected,
            selection_digest=ci_plan.digest(expected),
            selection_kind="nodeids",
        )
    plan["selected_ids"] = nodes
    save(path, plan)


def pytest_command(files, xml, workers, journal=None):
    command = [
        "uv",
        "run",
        "--no-sync",
        "pytest",
        *files,
        "--strict-markers",
        "-m",
        MARKER,
        "--junitxml",
        str(xml),
        "--durations=20",
    ]
    if journal:
        command += ["--journal", str(journal)]
    if workers > 1:
        command += ["-n", str(workers), "--dist", "worksteal"]
    return command


def positive_workers(value):
    workers = int(value)
    if workers < 1:
        raise argparse.ArgumentTypeError("Workers must be at least one")
    return workers


def selected_workers(name, count, requested=None):
    return resource_scheduler.calculate_worker_budget(
        workload_count=count, lane_name=name, user_override=requested
    )


def run_selection(path, name, workers=None, quiet=True):
    plan, output = read(path), path.parent
    item = plan["lanes"][name]
    if (
        item["disposition"] != "selected"
        or item["selection_kind"] != "nodeids"
        or not item["test_ids"]
    ):
        raise ValueError("Lane was not selected/collected before execution")
    workers = selected_workers(name, len(item["test_ids"]), workers)
    xml = output / (name + ".xml")
    journal = output / (name + "-journal.jsonl")
    command = pytest_command(item["test_files"], xml, workers, journal=journal)
    return ci_profile.run(
        Namespace(
            command=command,
            output=output,
            name=name,
            junit=xml,
            journal=journal,
            mode="xdist" if workers > 1 else "sequential",
            workers=workers,
            quiet=quiet,
            selection={
                "kind": item.get("selection_kind"),
                "digest": item.get("selection_digest"),
                "test_ids": item.get("test_ids"),
                "test_files": item.get("test_files"),
            },
            acceptance_input_hash=plan.get("acceptance_input_hash"),
        )
    )


def run_current(output, name, workers=None, quiet=True):
    """Run the current manifest during edits; raw profiles retain dirty-tree status."""
    files = [
        path
        for path in ci_plan.current_acceptance_files()
        if path.startswith("tests/packaging/") == (name == "packaging")
    ]
    workers = resource_scheduler.calculate_worker_budget(
        workload_count=len(files), lane_name=name, user_override=workers
    )
    xml = output / (name + ".xml")
    journal = output / (name + "-journal.jsonl")
    command = pytest_command(files, xml, workers, journal=journal)
    return ci_profile.run(
        Namespace(
            command=command,
            output=output,
            name=name,
            junit=xml,
            journal=journal,
            mode="xdist" if workers > 1 else "sequential",
            workers=workers,
            quiet=quiet,
        )
    )


def reports(root=ROOT):
    """Check readable, nonempty reports and JSON objects without application imports."""
    checked = set()
    rules = ci_plan.policy(root)
    for pattern in rules["prose"] + rules.get("report_inputs", []):
        # Use the planner's matcher, where '*' can span directories, to avoid
        # classifying nested evidence as report-only without validating it.
        search = root
        for part in Path(pattern).parts:
            if glob.has_magic(part):
                break
            search /= part
        candidates = search.rglob("*") if search.is_dir() else [search]
        for path in sorted(candidates):
            if not path.is_file():
                continue
            relative = str(path.relative_to(root))
            if relative in checked or not ci_plan.matches(relative, [pattern]):
                continue
            if path.is_symlink() or root.resolve() not in path.resolve().parents:
                raise ValueError("Report/prose must be a regular repository file")
            raw = path.read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("Empty report/prose file")
            if path.suffix == ".json":
                value = json.loads(
                    raw,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("Nonfinite report JSON")
                    ),
                )
                if not isinstance(value, dict) or not value:
                    raise ValueError("Report must be a nonempty JSON object")
            checked.add(relative)
    return {"checked": sorted(checked), "outcome": "passed"}


def successful_profile(path, context, expected_runtime):
    record = read(path)
    if (
        record["exit_code"] != 0
        or record.get("measurement_error")
        or record.get("interrupted")
        or record.get("measurement_recovered_from_journal")
    ):
        raise ValueError("Selected command failed, interrupted, or output is invalid")
    meta = record["runtime"]
    if (
        meta["commit_sha"] != context["tested_sha"]
        or meta["tracked_changes"]
        or meta["python"] != expected_runtime["python"]
        or meta["sqlite"] != expected_runtime["sqlite"]
    ):
        raise ValueError("Selected command revision/runtime differs")
    if context.get("run_id") and (
        str(meta.get("run_id")) != str(context["run_id"])
        or str(meta.get("run_attempt")) != str(context["run_attempt"])
        or meta.get("feature_sha") != context["feature_sha"]
    ):
        raise ValueError("Selected command belongs to another run/attempt/feature")
    if not math.isfinite(record["wall_seconds"]) or record["wall_seconds"] < 0:
        raise ValueError("Invalid command wall time")
    return record


def find_artifact(lane_data, key_file, key_path, default_filename, receipt_path, root):
    target = lane_data.get(key_file) or lane_data.get(key_path) or default_filename
    target_path = Path(target)
    if target_path.is_absolute():
        return None
    if receipt_path is not None:
        rec_dir = Path(receipt_path).resolve().parent
        cand = (rec_dir / target_path).resolve()
        if rec_dir in cand.parents and cand.is_file():
            return cand
        cand_inv = (rec_dir / "invocations" / target_path.name).resolve()
        if rec_dir in cand_inv.parents and cand_inv.is_file():
            return cand_inv
        cand_parent_inv = (rec_dir.parent / "invocations" / target_path.name).resolve()
        if cand_parent_inv.is_file():
            return cand_parent_inv
    cand_root = (Path(root).resolve() / target_path).resolve()
    if cand_root.is_file() and not str(cand_root).startswith(
        str(Path(root).resolve() / "artifacts")
    ):
        return cand_root
    return None


def verify_local_receipt(rec, plan, required_nodes=None, root=ROOT, receipt_path=None):
    """Strictly verify a local release execution receipt against the required acceptance contract."""
    if not isinstance(rec, dict):
        return False, "Malformed receipt: not a JSON object"
    if rec.get("schema_version") not in (1, "1"):
        return False, "Unsupported schema version"
    # 1. Explicit clean-tree execution identity
    if rec.get("dirty") is not False or rec.get("tracked_changes") is not False:
        return False, "Receipt is marked dirty or has uncommitted changes"
    # 2. Explicit successful exit code and status
    if "exit_code" not in rec or rec.get("exit_code") != 0:
        return False, "Missing or non-zero exit_code in receipt"
    if rec.get("status") != "passed":
        return False, "Receipt status is not 'passed'"
    # 3. Exact candidate source/test-input binding
    if rec.get("acceptance_input_hash") != plan["acceptance_input_hash"]:
        return False, "Acceptance input hash mismatch"
    commit_sha = rec.get("commit_sha")
    expected_sha = plan.get("context", {}).get("tested_sha")
    if not commit_sha:
        return False, "Missing commit_sha in receipt"
    if expected_sha and commit_sha != expected_sha:
        return False, "Commit SHA mismatch"
    tree_sha = rec.get("tree_sha")
    if not tree_sha or not ci_plan.SHA.fullmatch(tree_sha):
        return False, "Missing or invalid tree_sha in receipt"
    expected_tree = plan.get("tree_sha") or plan.get("context", {}).get("tree_sha")
    if not expected_tree and commit_sha:
        try:
            expected_tree = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", f"{commit_sha}^{{tree}}"],
                text=True,
            ).strip()
        except Exception:
            expected_tree = None
    if expected_tree and tree_sha != expected_tree:
        return (
            False,
            f"Receipt tree SHA mismatch: expected {expected_tree}, got {tree_sha}",
        )

    # 4. Zero failures, errors, skips, or interruptions
    if rec.get("interrupted") or rec.get("measurement_error"):
        return False, "Receipt records an interrupted execution or measurement error"
    failed_nodes = rec.get("failed_nodes", [])
    if (
        not isinstance(failed_nodes, list)
        or failed_nodes
        or rec.get("failed_count", 0) != 0
    ):
        return False, "Receipt records test failures"
    skipped_nodes = rec.get("skipped_nodes", [])
    if (
        not isinstance(skipped_nodes, list)
        or skipped_nodes
        or rec.get("skipped_count", 0) != 0
    ):
        return False, "Receipt records test skips"
    error_nodes = rec.get("error_nodes", [])
    if (
        not isinstance(error_nodes, list)
        or error_nodes
        or rec.get("error_count", 0) != 0
    ):
        return False, "Receipt records test errors"
    # 5. Nodes list integrity and duplicate rejection
    passed = rec.get("passed_nodes")
    if not isinstance(passed, list) or not passed:
        return False, "Receipt contains empty or missing passed_nodes"
    if len(passed) != len(set(passed)):
        return False, "Receipt contains duplicate node IDs"
    if rec.get("passed_count") is not None and rec.get("passed_count") != len(passed):
        return False, "Contradictory passed_count and passed_nodes length"

    # 6. Structural test-node identity validation
    acceptance_files = set(plan.get("acceptance_files", []))
    has_packaging = False
    has_ordinary = False
    for node in passed:
        if not isinstance(node, str) or "::" not in node:
            return False, f"Malformed node identifier: {node}"
        file_part = node.split("::")[0]
        if not any(file_part.startswith(d + "/") for d in ci_plan.REQUIRED_DIRS):
            return False, f"Node ID is outside required acceptance directories: {node}"
        if acceptance_files and file_part not in acceptance_files:
            return (
                False,
                f"Node ID file is not in current acceptance files: {file_part}",
            )
        if file_part.startswith("tests/packaging/"):
            has_packaging = True
        else:
            has_ordinary = True

    # 7. Independent representation of ordinary and packaging validation
    if not has_packaging:
        return False, "Packaging validation is missing from receipt"
    if not has_ordinary:
        return False, "Ordinary test validation is missing from receipt"

    lanes = rec.get("lanes")
    if not isinstance(lanes, dict) or "tests" not in lanes or "packaging" not in lanes:
        return (
            False,
            "Lanes mapping is missing or must contain both 'tests' and 'packaging'",
        )

    all_lane_passed = set()
    for lane_name in ("tests", "packaging"):
        lane_data = lanes[lane_name]
        if not isinstance(lane_data, dict):
            return False, f"Lane {lane_name} is not an object"
        if lane_data.get("exit_code") != 0 or lane_data.get("status") != "passed":
            return False, f"Lane {lane_name} did not pass with exit code 0"
        if lane_data.get("interrupted") or lane_data.get("measurement_error"):
            return False, f"Lane {lane_name} records interruption or measurement error"
        for field in ("failed_nodes", "skipped_nodes", "error_nodes"):
            val = lane_data.get(field, [])
            if not isinstance(val, list) or val:
                return False, f"Lane {lane_name} records non-empty {field}"
        for count_field in ("failed_count", "skipped_count", "error_count"):
            if lane_data.get(count_field, 0) != 0:
                return False, f"Lane {lane_name} records non-zero {count_field}"
        lane_passed = lane_data.get("passed_nodes", [])
        if (
            not isinstance(lane_passed, list)
            or not lane_passed
            or len(lane_passed) != len(set(lane_passed))
        ):
            return False, f"Lane {lane_name} has empty or duplicate passed nodes"
        if lane_data.get("passed_count") is not None and lane_data.get(
            "passed_count"
        ) != len(lane_passed):
            return (
                False,
                f"Lane {lane_name} passed_count does not match passed_nodes",
            )
        for n in lane_passed:
            file_p = n.split("::")[0]
            if lane_name == "packaging" and not file_p.startswith("tests/packaging/"):
                return False, f"Packaging lane contains non-packaging node: {n}"
            elif lane_name == "tests" and file_p.startswith("tests/packaging/"):
                return False, f"Tests lane contains packaging node: {n}"
        if all_lane_passed & set(lane_passed):
            return (
                False,
                f"Overlap between test lanes: {all_lane_passed & set(lane_passed)}",
            )
        all_lane_passed.update(lane_passed)

    if all_lane_passed != set(passed):
        return (
            False,
            "Mismatch between top-level passed_nodes and lane passed_nodes",
        )

    # 8. Exact reconciliation against collected required node manifest in Release mode (Finding B)
    if required_nodes is not None:
        if not required_nodes:
            return False, "Required acceptance node set cannot be empty in Release mode"
        if set(passed) != set(required_nodes):
            missing = set(required_nodes) - set(passed)
            extra = set(passed) - set(required_nodes)
            return (
                False,
                f"Node reconciliation mismatch: missing={len(missing)}, extra={len(extra)}",
            )

    # 9. Artifact hash and supporting file validation (Finding A)
    for lane_name in ("tests", "packaging"):
        lane_data = lanes[lane_name]
        lane_passed = lane_data.get("passed_nodes", [])

        junit_sha = lane_data.get("junit_sha256")
        if (
            not junit_sha
            or not isinstance(junit_sha, str)
            or not ci_plan.SHA256.fullmatch(junit_sha)
        ):
            return False, f"Lane {lane_name} has invalid junit_sha256"

        journal_sha = lane_data.get("journal_sha256")
        if (
            not journal_sha
            or not isinstance(journal_sha, str)
            or not ci_plan.SHA256.fullmatch(journal_sha)
        ):
            return False, f"Lane {lane_name} has invalid journal_sha256"

        found_xml = find_artifact(
            lane_data,
            "junit_file",
            "junit_path",
            f"{lane_name}.xml",
            receipt_path,
            root,
        )
        if not found_xml:
            return (
                False,
                f"Supporting JUnit artifact for lane {lane_name} does not exist or is unreadable",
            )

        xml_bytes = found_xml.read_bytes()
        actual_xml_sha = hashlib.sha256(xml_bytes).hexdigest()
        if actual_xml_sha != junit_sha:
            return (
                False,
                f"Lane {lane_name} junit_sha256 digest mismatch: expected {junit_sha}, got {actual_xml_sha}",
            )

        try:
            parsed_xml = ci_profile.junit(found_xml)
        except Exception as err:
            return (
                False,
                f"Supporting JUnit artifact for lane {lane_name} is malformed: {err}",
            )

        if any(t["status"] != "passed" for t in parsed_xml["tests"]):
            return (
                False,
                f"Supporting JUnit artifact for lane {lane_name} contains failed/error/skipped tests",
            )

        xml_nodeids = [t["nodeid"] for t in parsed_xml["tests"]]
        if len(xml_nodeids) != len(set(xml_nodeids)):
            return (
                False,
                f"Supporting JUnit artifact for lane {lane_name} contains duplicate node IDs",
            )
        if set(xml_nodeids) != set(lane_passed):
            return (
                False,
                f"Supporting JUnit artifact for lane {lane_name} node set does not match claimed passed_nodes",
            )

        found_journal = find_artifact(
            lane_data,
            "journal_file",
            "journal_path",
            f"{lane_name}-journal.jsonl",
            receipt_path,
            root,
        )
        if not found_journal:
            return (
                False,
                f"Supporting journal artifact for lane {lane_name} does not exist or is unreadable",
            )

        journal_bytes = found_journal.read_bytes()
        actual_journal_sha = hashlib.sha256(journal_bytes).hexdigest()
        if actual_journal_sha != journal_sha:
            return (
                False,
                f"Lane {lane_name} journal_sha256 digest mismatch: expected {journal_sha}, got {actual_journal_sha}",
            )

        try:
            events = ci_journal.parse_journal(found_journal)
            journal_summary = ci_journal.aggregate_journal(events)
        except Exception as err:
            return (
                False,
                f"Supporting journal artifact for lane {lane_name} is corrupted: {err}",
            )

        if journal_summary.get("interrupted") or journal_summary.get("partial", 0) > 0:
            return (
                False,
                f"Journal for lane {lane_name} records interrupted or partial execution",
            )
        if journal_summary.get("completed_failing", 0) > 0:
            return False, f"Journal for lane {lane_name} records failing tests"
        if journal_summary.get("skipped", 0) > 0:
            return False, f"Journal for lane {lane_name} records skipped tests"

        finish_event = next((e for e in events if e.get("event") == "finish"), None)
        if not finish_event or finish_event.get("exitstatus") != 0:
            return (
                False,
                f"Journal for lane {lane_name} is incomplete: missing successful finish event",
            )

        journal_nodeids = {
            t["nodeid"]
            for t in journal_summary["tests"]
            if t["completed"] and t["status"] == "passed"
        }
        if journal_nodeids != set(lane_passed):
            return (
                False,
                f"Journal for lane {lane_name} completed passed nodes do not match claimed passed_nodes",
            )

    return True, "Verified"


def create_receipt(output_dir, dest_path=None, root=ROOT):
    """Generate a valid local release receipt from actual completed test and packaging profiles."""
    output_dir = Path(output_dir)
    dest_path = Path(dest_path or (output_dir / "local-receipt.json"))
    plan_path = output_dir / "plan.json"
    if not plan_path.is_file():
        raise ValueError(f"Missing plan.json in {output_dir}")
    plan = read(plan_path)

    if plan.get("mode") != "release" or not plan.get("full"):
        raise ValueError(
            "create_receipt requires a completed Release mode plan with full acceptance"
        )
    if plan.get("unexecuted_files"):
        raise ValueError(
            "Cannot generate release receipt with unexecuted acceptance files"
        )

    tracked = bool(
        subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--untracked-files=normal",
            ]
        ).strip()
    )
    if tracked:
        raise ValueError(
            "Cannot generate clean release receipt from dirty working tree"
        )

    tested_sha = plan.get("context", {}).get("tested_sha")
    if not tested_sha:
        raise ValueError("Plan is missing context.tested_sha")

    current_tree = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    tested_tree = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", f"{tested_sha}^{{tree}}"],
        text=True,
    ).strip()
    if current_tree != tested_tree:
        raise ValueError("Working tree does not match plan tested tree")

    lanes_data = {}
    all_passed = []
    for lane in ci_plan.TEST_LANES:
        lane_plan = plan["lanes"][lane]
        if lane_plan.get("disposition") != "selected" or not lane_plan.get("test_ids"):
            raise ValueError(f"Plan is missing collected test_ids for lane {lane}")

        lane_json = output_dir / f"{lane}.json"
        lane_xml = output_dir / f"{lane}.xml"
        lane_journal = output_dir / f"{lane}-journal.jsonl"
        if not lane_json.is_file():
            raise ValueError(f"Missing profile for required lane: {lane}")
        if not lane_xml.is_file():
            raise ValueError(f"Missing JUnit XML for required lane: {lane}")
        if not lane_journal.is_file():
            raise ValueError(f"Missing journal for required lane: {lane}")

        profile = read(lane_json)
        if (
            profile.get("exit_code") != 0
            or profile.get("interrupted")
            or profile.get("measurement_error")
            or profile.get("measurement_recovered_from_journal")
        ):
            raise ValueError(f"Lane {lane} did not complete successfully")

        meta = profile.get("runtime", {})
        if meta.get("commit_sha") != tested_sha:
            raise ValueError(
                f"Lane {lane} profile commit_sha does not match current candidate HEAD"
            )
        if meta.get("tree_sha") != tested_tree:
            raise ValueError(
                f"Lane {lane} profile tree_sha does not match current candidate tree"
            )
        if meta.get("dirty") or meta.get("tracked_changes"):
            raise ValueError(f"Lane {lane} profile was recorded on a dirty tree")

        # Validate JUnit XML
        xml_parsed = ci_profile.junit(lane_xml)
        if any(t["status"] != "passed" for t in xml_parsed["tests"]):
            raise ValueError(
                f"JUnit XML for lane {lane} contains failed/error/skipped tests"
            )
        xml_nodes = sorted(t["nodeid"] for t in xml_parsed["tests"])
        expected_nodes = sorted(lane_plan["test_ids"])
        if xml_nodes != expected_nodes:
            raise ValueError(
                f"JUnit XML for lane {lane} nodes do not match plan test_ids"
            )
        profile_nodes = sorted(
            t["nodeid"] for t in profile.get("junit", {}).get("tests", [])
        )
        if profile_nodes != xml_nodes:
            raise ValueError(
                f"Profile JUnit tests do not match raw JUnit XML for lane {lane}"
            )

        # Validate Journal
        journal_events = ci_journal.parse_journal(lane_journal)
        journal_summary = ci_journal.aggregate_journal(journal_events)
        if (
            journal_summary.get("interrupted")
            or journal_summary.get("partial", 0) > 0
            or journal_summary.get("completed_failing", 0) > 0
            or journal_summary.get("skipped", 0) > 0
        ):
            raise ValueError(
                f"Journal for lane {lane} records incomplete or failed tests"
            )
        finish = next((e for e in journal_events if e.get("event") == "finish"), None)
        if not finish or finish.get("exitstatus") != 0:
            raise ValueError(f"Journal for lane {lane} missing successful finish event")

        xml_hash = hashlib.sha256(lane_xml.read_bytes()).hexdigest()
        journal_hash = hashlib.sha256(lane_journal.read_bytes()).hexdigest()

        lanes_data[lane] = {
            "exit_code": 0,
            "status": "passed",
            "passed_nodes": expected_nodes,
            "passed_count": len(expected_nodes),
            "failed_nodes": [],
            "skipped_nodes": [],
            "junit_file": lane_xml.name,
            "junit_sha256": xml_hash,
            "journal_file": lane_journal.name,
            "journal_sha256": journal_hash,
        }
        all_passed.extend(expected_nodes)

    if len(all_passed) != len(set(all_passed)):
        raise ValueError("Duplicate node IDs across test lanes")

    receipt = {
        "schema_version": 1,
        "kind": "local_release_receipt",
        "created_at": datetime.now(UTC).isoformat(),
        "commit_sha": tested_sha,
        "tree_sha": tested_tree,
        "acceptance_input_hash": plan["acceptance_input_hash"],
        "exit_code": 0,
        "status": "passed",
        "dirty": False,
        "tracked_changes": False,
        "lanes": lanes_data,
        "passed_nodes": sorted(all_passed),
        "passed_count": len(all_passed),
        "failed_nodes": [],
        "failed_count": 0,
        "skipped_nodes": [],
        "skipped_count": 0,
    }
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    save(dest_path, receipt)
    valid, reason = verify_local_receipt(
        receipt, plan, required_nodes=set(all_passed), root=root, receipt_path=dest_path
    )
    if not valid:
        dest_path.unlink(missing_ok=True)
        raise ValueError(f"Generated receipt failed verification: {reason}")
    return receipt


def parse_log_receipt_bundle(log_text):
    """Extract and verify bounded receipt zip archive from GitHub Actions job log."""
    in_bundle = False
    digest = None
    expected_len = None
    lines = []
    for line in log_text.splitlines():
        if not in_bundle:
            m = re.search(
                r"(?:^|[\t ])CI_RECEIPTS_BEGIN_V1\s+([0-9a-f]{64})\s+(\d+)", line
            )
            if m and "print(" not in line:
                in_bundle = True
                digest = m.group(1)
                expected_len = int(m.group(2))
                lines = []
        else:
            m_end = re.search(r"(?:^|[\t ])CI_RECEIPTS_END_V1\s+([0-9a-f]{64})", line)
            if m_end and "print(" not in line:
                if m_end.group(1) != digest:
                    raise ValueError("CI_RECEIPTS_END_V1 digest mismatch with BEGIN")
                in_bundle = False
                break
            m_data = re.search(r"CI_RECEIPTS_DATA_V1\s+([A-Za-z0-9+/=]+)", line)
            if m_data:
                lines.append(m_data.group(1).strip())
    if not digest or not lines:
        return None
    raw = base64.b64decode("".join(lines))
    if len(raw) != expected_len:
        raise ValueError(
            f"Receipt bundle length mismatch: expected {expected_len}, got {len(raw)}"
        )
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Receipt bundle sha256 digest mismatch")
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for name in zf.namelist():
            files[name] = zf.read(name)
    return files


def compare_provider_artifact(bundle_dir, provider_source):
    """Compare local bundle files against provider-retrieved artifact contents."""
    if isinstance(provider_source, (str, Path)):
        prov_path = Path(provider_source)
        if not (prov_path / "validation-manifest.json").is_file():
            return False, "Provider artifact missing validation-manifest.json"
        try:
            prov_manifest = read(prov_path / "validation-manifest.json")
            local_manifest = read(bundle_dir / "validation-manifest.json")
        except Exception as err:
            return False, f"Failed to read manifest for comparison: {err}"
        if prov_manifest != local_manifest:
            return (
                False,
                "Supplied hosted manifest does not match provider-retrieved artifact",
            )
        for name in ("receipt-binding.json", "receipt-index.json"):
            if (prov_path / name).is_file() and (bundle_dir / name).is_file():
                if read(bundle_dir / name) != read(prov_path / name):
                    return (
                        False,
                        f"Supplied {name} does not match provider-retrieved artifact",
                    )
        return True, None
    elif isinstance(provider_source, dict):
        if "validation-manifest.json" not in provider_source:
            return False, "Provider artifact missing validation-manifest.json"
        try:
            prov_raw = provider_source["validation-manifest.json"]
            prov_manifest = (
                json.loads(prov_raw) if isinstance(prov_raw, (bytes, str)) else prov_raw
            )
            local_manifest = read(bundle_dir / "validation-manifest.json")
        except Exception as err:
            return False, f"Failed to read manifest for comparison: {err}"
        if prov_manifest != local_manifest:
            return (
                False,
                "Supplied hosted manifest does not match provider-retrieved artifact",
            )
        for name in ("receipt-binding.json", "receipt-index.json"):
            if name in provider_source and (bundle_dir / name).is_file():
                raw = provider_source[name]
                prov_val = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                if read(bundle_dir / name) != prov_val:
                    return (
                        False,
                        f"Supplied {name} does not match provider-retrieved artifact",
                    )
        return True, None
    return False, "Unsupported provider source format"


def verify_hosted_provider(
    run_id, binding, hosted, bundle_dir=None, root=ROOT, gh_runner=None
):
    """Retrieve and verify GitHub Actions hosted run metadata and artifact boundary."""
    runner = gh_runner or subprocess.run
    try:
        gh_res = runner(
            [
                "gh",
                "run",
                "view",
                str(run_id),
                "--json",
                "status,conclusion,headSha,event,workflowName,jobs,name",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as err:
        return "gap", f"Authoritative hosted run verification unavailable: {err}", None

    if gh_res.returncode != 0:
        return (
            "gap",
            f"Authoritative hosted run verification unavailable for run ID {run_id}: {gh_res.stderr.strip()}",
            None,
        )

    try:
        gh_info = json.loads(gh_res.stdout)
    except Exception as err:
        return False, f"Malformed GitHub Actions run view output: {err}", None

    if gh_info.get("status") != "completed" or gh_info.get("conclusion") != "success":
        return (
            False,
            f"GitHub Actions run not successful: status={gh_info.get('status')}, conclusion={gh_info.get('conclusion')}",
            None,
        )

    wf = gh_info.get("workflowName") or gh_info.get("name")
    if wf not in ("tests", "tests.yml"):
        return False, f"GitHub Actions run belongs to unexpected workflow: {wf}", None

    expected_head = binding.get("head") or hosted.get("context", {}).get("tested_sha")
    if expected_head and gh_info.get("headSha") != expected_head:
        return (
            False,
            f"GitHub Actions run commit SHA mismatch: expected {expected_head}, got {gh_info.get('headSha')}",
            None,
        )

    event = gh_info.get("event")
    if event in ("pull_request", "push"):
        return (
            False,
            f"GitHub Actions run was triggered by {event}, which does not execute full release qualification",
            None,
        )

    if event == "workflow_dispatch":
        jobs = gh_info.get("jobs", [])
        offline_job = next((j for j in jobs if j.get("name") == "offline"), None)
        if offline_job:
            steps = {
                s.get("name"): s.get("conclusion") for s in offline_job.get("steps", [])
            }
            t_conc = steps.get("Current catalog3 checks (offline)")
            p_conc = steps.get(
                "Installed wheel and sdist checks (offline, isolated parallel workers)"
            )
            if t_conc != "success" or p_conc != "success":
                return (
                    False,
                    "GitHub Actions run was triggered by workflow_dispatch in development mode (release test lanes were not executed)",
                    None,
                )
        else:
            return (
                False,
                "GitHub Actions run missing offline job details to confirm release qualification",
                None,
            )
    elif event not in ("schedule", "release"):
        return (
            False,
            f"GitHub Actions run event {event} does not qualify for release validation",
            None,
        )

    attempt = (
        binding.get("run_attempt") or hosted.get("context", {}).get("run_attempt") or 1
    )
    artifact_name = f"ci-profile-{run_id}-{attempt}"

    with tempfile.TemporaryDirectory(prefix="hosted-artifact-") as tmpdir:
        tmp_path = Path(tmpdir)
        downloaded = False
        try:
            dl_res = runner(
                [
                    "gh",
                    "run",
                    "download",
                    str(run_id),
                    "-n",
                    artifact_name,
                    "-D",
                    str(tmp_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            downloaded = dl_res.returncode == 0 and any(tmp_path.iterdir())
        except Exception:
            downloaded = False

        if not downloaded:
            # Fallback: authenticated job log bundle
            try:
                log_res = runner(
                    ["gh", "run", "view", str(run_id), "--log"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if log_res.returncode == 0 and "CI_RECEIPTS_BEGIN_V1" in log_res.stdout:
                    files = parse_log_receipt_bundle(log_res.stdout)
                    if files:
                        for fname, fdata in files.items():
                            (tmp_path / fname).write_bytes(fdata)
                        downloaded = True
            except Exception:
                downloaded = False

        if not downloaded:
            return (
                False,
                f"Missing or unretrievable provider validation artifact for run ID {run_id}",
                None,
            )

        if not (tmp_path / "validation-manifest.json").is_file():
            return (
                False,
                "Downloaded artifact is missing validation-manifest.json",
                None,
            )

        prov_manifest = read(tmp_path / "validation-manifest.json")
        if prov_manifest.get("validation_mode") != "release" or not prov_manifest.get(
            "full_acceptance"
        ):
            return (
                False,
                "Provider artifact manifest does not record completed release acceptance",
                None,
            )

        if (tmp_path / "receipt-index.json").is_file():
            prov_idx = read(tmp_path / "receipt-index.json")
            for fname, fmeta in prov_idx.items():
                fpath = tmp_path / fname
                if (
                    not fpath.is_file()
                    or hashlib.sha256(fpath.read_bytes()).hexdigest() != fmeta["sha256"]
                ):
                    return (
                        False,
                        f"Provider artifact internal digest mismatch: {fname}",
                        None,
                    )

        if (tmp_path / "receipt-binding.json").is_file():
            prov_binding = read(tmp_path / "receipt-binding.json")
            if prov_binding.get("run_attempt") and binding.get("run_attempt"):
                if str(prov_binding["run_attempt"]) != str(binding["run_attempt"]):
                    return (
                        False,
                        f"GitHub Actions run attempt mismatch: expected {binding['run_attempt']}, got {prov_binding['run_attempt']}",
                        None,
                    )

        if bundle_dir is not None:
            match_ok, match_err = compare_provider_artifact(bundle_dir, tmp_path)
            if not match_ok:
                return False, match_err, None

        return (
            True,
            None,
            dict((p.name, p.read_bytes()) for p in tmp_path.iterdir() if p.is_file()),
        )


def reconcile_release(
    local_receipt_path,
    hosted_manifest_path,
    root=ROOT,
    run_verifier=None,
    gh_runner=None,
):
    """Reconcile independent local release receipt and hosted validation manifest."""
    local_receipt_path = Path(local_receipt_path)
    hosted_manifest_path = Path(hosted_manifest_path)
    if not local_receipt_path.is_file():
        return {
            "verdict": "release_rejected",
            "reason": f"Local receipt file does not exist: {local_receipt_path}",
            "acceptance_status": "release_rejected",
        }
    if not hosted_manifest_path.is_file():
        return {
            "verdict": "release_rejected",
            "reason": f"Hosted manifest file does not exist: {hosted_manifest_path}",
            "acceptance_status": "release_rejected",
        }

    try:
        local_rec = read(local_receipt_path)
    except Exception as err:
        return {
            "verdict": "release_rejected",
            "reason": f"Malformed local receipt JSON: {err}",
            "acceptance_status": "release_rejected",
        }
    try:
        hosted = read(hosted_manifest_path)
    except Exception as err:
        return {
            "verdict": "release_rejected",
            "reason": f"Malformed hosted manifest JSON: {err}",
            "acceptance_status": "release_rejected",
        }

    if not isinstance(hosted, dict):
        return {
            "verdict": "release_rejected",
            "reason": "Hosted manifest is not a JSON object",
            "acceptance_status": "release_rejected",
        }

    if hosted.get("validation_mode") != "release" or not hosted.get("full_acceptance"):
        return {
            "verdict": "release_rejected",
            "reason": "Hosted manifest is not a completed release validation",
            "acceptance_status": "release_rejected",
        }
    if hosted.get("outcome") != "passed":
        return {
            "verdict": "release_rejected",
            "reason": "Hosted release validation outcome is not passed",
            "acceptance_status": "release_rejected",
        }

    test_ids = hosted.get("test_ids")
    if not isinstance(test_ids, list) or not test_ids:
        return {
            "verdict": "release_rejected",
            "reason": "Hosted manifest test_ids is empty or missing",
            "acceptance_status": "release_rejected",
        }
    if len(test_ids) != len(set(test_ids)):
        return {
            "verdict": "release_rejected",
            "reason": "Hosted manifest contains duplicate node IDs",
            "acceptance_status": "release_rejected",
        }

    has_pkg = any(t.startswith("tests/packaging/") for t in test_ids)
    has_ord = any(not t.startswith("tests/packaging/") for t in test_ids)
    if not has_pkg or not has_ord:
        return {
            "verdict": "release_rejected",
            "reason": "Hosted manifest claims full acceptance without packaging completion",
            "acceptance_status": "release_rejected",
        }

    coverage = hosted.get("coverage", {})
    if coverage.get("unexecuted_files"):
        return {
            "verdict": "release_rejected",
            "reason": f"Hosted manifest contains unexecuted acceptance files: {coverage.get('unexecuted_files')}",
            "acceptance_status": "release_rejected",
        }
    if coverage.get("excluded_files"):
        return {
            "verdict": "release_rejected",
            "reason": f"Hosted manifest contains excluded acceptance files: {coverage.get('excluded_files')}",
            "acceptance_status": "release_rejected",
        }

    required_acceptance_files = set(ci_plan.current_acceptance_files(root))
    hosted_files = {t.split("::")[0] for t in test_ids}
    missing_files = required_acceptance_files - hosted_files
    if missing_files:
        return {
            "verdict": "release_rejected",
            "reason": f"Hosted manifest is missing coverage for required acceptance files: {sorted(missing_files)}",
            "acceptance_status": "release_rejected",
        }

    # Verify hosted run provenance (Finding C)
    bundle_dir = hosted_manifest_path.parent
    binding_file = bundle_dir / "receipt-binding.json"
    if not binding_file.is_file() and "receipt_binding" not in hosted:
        return {
            "verdict": "release_rejected",
            "reason": "Arbitrary JSON claims successful hosted execution without verifiable run provenance",
            "acceptance_status": "release_rejected",
        }

    binding = (
        read(binding_file)
        if binding_file.is_file()
        else hosted.get("receipt_binding", {})
    )
    run_id = binding.get("run_id") or hosted.get("context", {}).get("run_id")
    if not run_id:
        return {
            "verdict": "release_rejected",
            "reason": "Missing run_id in hosted run provenance",
            "acceptance_status": "release_rejected",
        }
    if binding.get("head") and binding["head"] != hosted.get("context", {}).get(
        "tested_sha"
    ):
        return {
            "verdict": "release_rejected",
            "reason": "Receipt binding head SHA mismatch",
            "acceptance_status": "release_rejected",
        }

    # Verify active repository tree binding and effective merge tree equivalence
    try:
        active_commit = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        active_tree = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True
        ).strip()
    except Exception as err:
        return {
            "verdict": "release_rejected",
            "reason": f"Unable to determine active repository HEAD: {err}",
            "acceptance_status": "release_rejected",
        }

    tested_sha = hosted.get("context", {}).get("tested_sha")
    feature_sha = hosted.get("context", {}).get("feature_sha")
    if tested_sha != active_commit and feature_sha != active_commit:
        return {
            "verdict": "release_rejected",
            "reason": f"Hosted manifest tested_sha ({tested_sha}) / feature_sha ({feature_sha}) does not match active repository HEAD ({active_commit})",
            "acceptance_status": "release_rejected",
        }

    try:
        tested_tree = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", f"{tested_sha}^{{tree}}"],
            text=True,
        ).strip()
    except Exception:
        tested_tree = hosted.get("tree_sha")
    if tested_tree != active_tree:
        return {
            "verdict": "release_rejected",
            "reason": f"Hosted manifest tree ({tested_tree}) does not match active repository tree ({active_tree})",
            "acceptance_status": "release_rejected",
        }

    expected_tree = hosted.get("tree_sha") or active_tree
    if binding.get("tree") and expected_tree and binding["tree"] != expected_tree:
        return {
            "verdict": "release_rejected",
            "reason": "Receipt binding tree SHA mismatch",
            "acceptance_status": "release_rejected",
        }

    active_plan = ci_plan.make_plan(hosted["context"], root=root)
    if hosted.get("acceptance_input_hash") != active_plan["acceptance_input_hash"]:
        return {
            "verdict": "release_rejected",
            "reason": "Hosted manifest acceptance_input_hash does not match active repository candidate tree",
            "acceptance_status": "release_rejected",
        }

    index_file = bundle_dir / "receipt-index.json"
    if index_file.is_file():
        index_data = read(index_file)
        for fname, fmeta in index_data.items():
            fpath = bundle_dir / fname
            if not fpath.is_file():
                return {
                    "verdict": "release_rejected",
                    "reason": f"Downloaded receipt bundle missing indexed file: {fname}",
                    "acceptance_status": "release_rejected",
                }
            if hashlib.sha256(fpath.read_bytes()).hexdigest() != fmeta["sha256"]:
                return {
                    "verdict": "release_rejected",
                    "reason": f"Downloaded receipt bundle file digest mismatch: {fname}",
                    "acceptance_status": "release_rejected",
                }

    # Authoritative run verification check (Tier 3)
    run_verified = False
    if run_verifier is not None:
        ver_res = run_verifier(run_id, binding, hosted)
        if isinstance(ver_res, tuple):
            if ver_res[0] is False:
                return {
                    "verdict": "release_rejected",
                    "reason": ver_res[1],
                    "acceptance_status": "release_rejected",
                }
            elif ver_res[0] == "gap" or ver_res[0] is None:
                return {
                    "verdict": "validation_gap_reported",
                    "reason": ver_res[1]
                    or "Authoritative hosted run verification unavailable for run ID",
                    "acceptance_status": "validation_gap_reported",
                }
            elif ver_res[0] is True:
                if len(ver_res) > 2 and ver_res[2] is not None:
                    match_ok, match_err = compare_provider_artifact(
                        bundle_dir, ver_res[2]
                    )
                    if not match_ok:
                        return {
                            "verdict": "release_rejected",
                            "reason": match_err,
                            "acceptance_status": "release_rejected",
                        }
                run_verified = True
        elif ver_res is True:
            run_verified = True
    else:
        ver_ok, ver_err, _ = verify_hosted_provider(
            run_id, binding, hosted, bundle_dir, root=root, gh_runner=gh_runner
        )
        if ver_ok == "gap":
            return {
                "verdict": "validation_gap_reported",
                "reason": ver_err,
                "acceptance_status": "validation_gap_reported",
            }
        elif not ver_ok:
            return {
                "verdict": "release_rejected",
                "reason": ver_err,
                "acceptance_status": "release_rejected",
            }
        run_verified = True

    if not run_verified:
        return {
            "verdict": "validation_gap_reported",
            "reason": "Authoritative hosted run verification unavailable for run ID",
            "acceptance_status": "validation_gap_reported",
        }

    plan_context = hosted["context"]
    acceptance_input_hash = hosted["acceptance_input_hash"]
    dummy_plan = {
        "context": plan_context,
        "acceptance_input_hash": acceptance_input_hash,
        "acceptance_files": hosted["coverage"].get("required_files", []),
        "tree_sha": expected_tree,
    }
    valid, reason = verify_local_receipt(
        local_rec,
        dummy_plan,
        required_nodes=set(test_ids),
        root=root,
        receipt_path=local_receipt_path,
    )
    if not valid:
        return {
            "verdict": "release_rejected",
            "reason": reason,
            "acceptance_status": "release_rejected",
        }
    return {
        "verdict": "complete_release_passed",
        "reason": "Both independent local and hosted release validation obligations satisfied",
        "acceptance_status": "complete_release_passed",
        "acceptance_input_hash": acceptance_input_hash,
        "tested_sha": plan_context.get("tested_sha"),
    }


def gate(path, root=ROOT):
    manifest_path = path.parent / "validation-manifest.json"
    manifest_path.unlink(missing_ok=True)
    plan, output = read(path), path.parent
    rebuilt = ci_plan.make_plan(plan["context"], root=root)
    for key in (
        "version",
        "mode",
        "policy_hash",
        "tree_hash",
        "acceptance_input_hash",
        "runtime",
        "full",
        "acceptance_files",
        "required_files",
        "selected_files",
        "excluded_files",
        "unexecuted_files",
        "preparation",
        "fallback_reasons",
        "changed",
        "comparison_sha",
    ):
        if rebuilt.get(key) != plan.get(key):
            raise ValueError("Plan changed after selection: " + key)
    for name in ci_plan.LANES:
        for key in ("disposition", "test_files"):
            if rebuilt["lanes"][name][key] != plan["lanes"][name][key]:
                raise ValueError("Lane selection was modified")
    if rebuilt["preparation"] != plan["preparation"]:
        raise ValueError("Preparation selection was modified")
    if read(output / "reports.json") != reports(root):
        raise ValueError("Missing/changed report validation")
    profiles, selected = {}, []
    for name in ci_plan.TEST_LANES:
        item = plan["lanes"][name]
        result_path = output / (name + ".json")
        if item["disposition"] != "selected":
            if result_path.exists():
                raise ValueError("Unexpected result for an unselected lane")
            continue
        nodes = item["test_ids"]
        if (
            not nodes
            or len(nodes) != len(set(nodes))
            or {n.split("::")[0] for n in nodes} != set(item["test_files"])
            or item["selection_kind"] != "nodeids"
            or item["selection_digest"] != ci_plan.digest(nodes)
        ):
            raise ValueError("Expected selection does not match selected files")
        record = successful_profile(result_path, plan["context"], plan["runtime"])
        actual = record["junit"]["tests"]
        if any(n["status"] != "passed" for n in actual) or sorted(
            n["nodeid"] for n in actual
        ) != sorted(nodes):
            raise ValueError("Selected tests failed/skipped/missing/duplicated/extra")
        selected.extend(nodes)
        profiles[name] = record
    if selected:
        collected = collection_ids((output / "selected-tests.txt").read_text())
        if (
            len(selected) != len(set(selected))
            or sorted(selected) != collected
            or plan.get("selected_ids") != collected
        ):
            raise ValueError("Selected collection differs from recorded execution")
        ci_profile.coverage(
            output / "selected-tests.txt",
            [
                output / (name + ".json")
                for name in ci_plan.TEST_LANES
                if name in profiles
            ],
        )
    command_names = {
        "static": ["lint", "format"],
        "smoke": ["fts", "doctor"],
        "dependencies": ["dependency-setup"],
        "wheelhouse": ["wheelhouse"],
        "sdist_contract": ["sdist_contract"],
    }
    for name, commands in command_names.items():
        item = plan["lanes"].get(name) or plan["preparation"][name]
        for command in commands:
            result_path = output / (command + ".json")
            if item["disposition"] == "selected":
                profiles[command] = successful_profile(
                    result_path, plan["context"], plan["runtime"]
                )
            elif result_path.exists():
                raise ValueError("Unexpected unselected command output")
    for name in ("planning", "report-validation"):
        profiles[name] = successful_profile(
            output / (name + ".json"), plan["context"], plan["runtime"]
        )

    mode = plan.get("mode", "release" if plan.get("full") else "development")
    evidence_status = "local_evidence_unavailable"
    local_receipts = []
    candidate_paths = [
        output / "local-receipt.json",
        *(output / "receipts").glob("*.json"),
        *root.glob("docs/validation/receipts/*.json"),
        *root.glob("docs/validation/evidence/*.json"),
    ]
    corrupted_receipt = False
    for cand in candidate_paths:
        if cand.is_file():
            try:
                rec = read(cand)
                if cand == (output / "local-receipt.json") or (
                    isinstance(rec, dict)
                    and rec.get("acceptance_input_hash")
                    == plan["acceptance_input_hash"]
                ):
                    local_receipts.append((cand, rec))
            except Exception:
                if cand == (output / "local-receipt.json"):
                    corrupted_receipt = True

    failed_receipts = []
    if corrupted_receipt:
        failed_receipts.append(
            (
                output / "local-receipt.json",
                "Malformed or unparseable local receipt JSON",
            )
        )
        evidence_status = "local_evidence_failed"
    elif local_receipts:
        release_required_nodes = None
        if mode == "release":
            release_required_nodes = set(
                plan["lanes"]["tests"].get("test_ids", [])
            ) | set(plan["lanes"]["packaging"].get("test_ids", []))
            if not release_required_nodes:
                raise ValueError(
                    "Release mode requires non-empty test selection across tests and packaging lanes"
                )

        receipt_verified = False
        failed_receipts = []
        for cand_path, rec in local_receipts:
            valid, reason = verify_local_receipt(
                rec,
                plan,
                required_nodes=release_required_nodes,
                root=root,
                receipt_path=cand_path,
            )
            if valid:
                receipt_verified = True
            else:
                failed_receipts.append((cand_path, reason))

        if failed_receipts:
            evidence_status = "local_evidence_failed"
        elif receipt_verified:
            evidence_status = "local_evidence_verified"
        else:
            evidence_status = "validation_gap_reported"

    if mode == "development":
        acceptance_status = "development_checks_passed"
        status_label = (
            "Development infrastructure checks passed."
            if not plan["unexecuted_files"]
            else "Development infrastructure checks passed (unexecuted tests require local validation)."
        )
        summary_text = (
            f"## Validation outcome\n\n"
            f"**{status_label}**\n\n"
            f"Validation mode: `development`. Hosted CI validated repository configuration, static analysis, and smoke checks. Full runtime acceptance is not established by this run.\n\n"
            f"Executed tests in CI: {len(selected)}. Unexecuted acceptance files requiring local validation: {len(plan['unexecuted_files'])}.\n\n"
            f"Local evidence status: `{evidence_status}`. Acceptance input hash: `{plan['acceptance_input_hash']}`.\n"
        )
    else:  # mode == "release"
        if not plan["full"]:
            raise ValueError(
                "Release mode requires full acceptance plan with all lanes selected"
            )
        if evidence_status == "local_evidence_verified":
            acceptance_status = "complete_release_passed"
        elif evidence_status == "local_evidence_failed":
            acceptance_status = "release_rejected"
        else:
            acceptance_status = "hosted_release_passed"
        status_label = (
            "Complete release acceptance passed (local and hosted validated)."
            if acceptance_status == "complete_release_passed"
            else (
                f"Release validation rejected: local evidence failed verification ({failed_receipts[0][1] if failed_receipts else 'unknown'})."
                if acceptance_status == "release_rejected"
                else "Hosted release test suite passed for the tested inputs (awaiting local reconciliation for complete release)."
            )
        )
        summary_text = (
            f"## Validation outcome\n\n**{status_label}**\n\n"
            f"Validation mode: `release`. Executed tests: {len(selected)}. Unexecuted acceptance files: {len(plan['unexecuted_files'])}.\n\n"
            f"Acceptance input hash: `{plan['acceptance_input_hash']}`.\n"
        )

    tree_sha = None
    tested_sha = plan["context"].get("tested_sha")
    if tested_sha:
        try:
            tree_sha = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", f"{tested_sha}^{{tree}}"],
                text=True,
            ).strip()
        except Exception:
            tree_sha = None

    result = {
        "version": 3,
        "outcome": "failed" if acceptance_status == "release_rejected" else "passed",
        "context": plan["context"],
        "runtime": plan["runtime"],
        "tree_sha": tree_sha,
        "validation_mode": mode,
        "full_acceptance": plan["full"],
        "acceptance_status": acceptance_status,
        "evidence_status": evidence_status,
        "acceptance_input_hash": plan["acceptance_input_hash"],
        "coverage": {
            "executed": len(selected),
            "selected_files": sum(
                len(plan["lanes"][k]["test_files"]) for k in ci_plan.TEST_LANES
            ),
            "required_files": plan.get("required_files", []),
            "acceptance_files": plan.get("acceptance_files", []),
            "unexecuted_files": plan["unexecuted_files"],
            "excluded_files": plan["excluded_files"],
        },
        "test_ids": sorted(selected),
        "selection_wall_seconds": plan["selection_wall_seconds"],
        "command_wall_seconds": {
            name: record["wall_seconds"] for name, record in profiles.items()
        },
    }
    save(manifest_path, result)
    (output / "validation-summary.md").write_text(summary_text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(summary_text)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "collect",
            "run",
            "current",
            "reports",
            "gate",
            "receipt",
            "reconcile-release",
        ),
    )
    parser.add_argument(
        "--plan", type=Path, default=Path("artifacts/ci-profile/plan.json")
    )
    parser.add_argument("--lane", choices=ci_plan.TEST_LANES, default="tests")
    parser.add_argument(
        "--workers",
        type=positive_workers,
        help="Override worker count (one disables xdist)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/ci-profile"),
        help="Output directory containing test profiles for receipt creation",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        help="Destination path for generated local receipt",
    )
    parser.add_argument(
        "--local-receipt",
        type=Path,
        help="Path to local receipt for reconciliation",
    )
    parser.add_argument(
        "--hosted-manifest",
        type=Path,
        help="Path to hosted validation-manifest.json for reconciliation",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="GitHub Actions run ID for hosted evidence reconciliation",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root directory",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Stream full pytest output to terminal instead of quiet summary",
    )
    args = parser.parse_args()
    if args.action == "reports":
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        save(args.plan.parent / "reports.json", reports(args.root))
    elif args.action == "collect":
        collect(args.plan)
    elif args.action == "run":
        return run_selection(args.plan, args.lane, args.workers, quiet=not args.verbose)
    elif args.action == "current":
        return run_current(
            args.plan.parent, args.lane, args.workers, quiet=not args.verbose
        )
    elif args.action == "receipt":
        rec = create_receipt(args.output_dir, dest_path=args.dest, root=args.root)
        print(
            json.dumps(
                {
                    "status": "created",
                    "path": str(args.dest or (args.output_dir / "local-receipt.json")),
                    "passed_count": rec["passed_count"],
                }
            )
        )
        return 0
    elif args.action == "reconcile-release":
        if not args.local_receipt or not args.hosted_manifest:
            parser.error(
                "reconcile-release requires --local-receipt and --hosted-manifest"
            )
        res = reconcile_release(
            args.local_receipt, args.hosted_manifest, root=args.root
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("verdict") == "complete_release_passed" else 1
    else:
        res = gate(args.plan, root=args.root)
        cov = res["coverage"]
        compact_cov = {
            "status": res.get("acceptance_status"),
            "executed": cov.get("executed", 0),
            "selected_files": cov.get("selected_files", 0),
            "required_files_count": len(cov.get("required_files", [])),
            "acceptance_files_count": len(cov.get("acceptance_files", [])),
            "unexecuted_files_count": len(cov.get("unexecuted_files", [])),
            "excluded_files_count": len(cov.get("excluded_files", [])),
        }
        if args.verbose or os.environ.get("CI_VERBOSE") == "1":
            print(json.dumps(res["coverage"]))
        else:
            print(json.dumps(compact_cov))
        if (
            res.get("outcome") != "passed"
            or res.get("acceptance_status") == "release_rejected"
        ):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
