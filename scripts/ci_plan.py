"""Conservative, stdlib-only CI planning and effective Git-tree fingerprints."""

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
import sqlite3
import subprocess
import sysconfig
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANES = (
    "static",
    "legacy",
    "schema",
    "p2",
    "ci",
    "packaging",
    "minimum-schema",
    "minimum-p2",
    "smoke",
    "build",
    "demo",
)
TEST_LANES = (
    "legacy",
    "schema",
    "p2",
    "ci",
    "packaging",
    "minimum-schema",
    "minimum-p2",
)
NORMAL = ("legacy", "schema", "p2", "ci")
REQUIRED_DIRS = ("tests/unit", "tests/integration", "tests/e2e", "tests/packaging")
MINIMUM_SCHEMA = {
    "tests/integration/test_target_schema.py",
    "tests/integration/test_p1_storage_lifecycle.py",
    "tests/integration/test_schema_proposal_core.py",
    "tests/integration/test_conversion_contract.py",
}
SHA = re.compile(r"[0-9a-f]{40}\Z")


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def load_evidence(path):
    try:
        value = json.loads(path.read_bytes())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None  # Missing/corrupt evidence requires execution, not reuse.


def check_baseline(required, minimum, root=ROOT):
    baseline = json.loads((root / "scripts/ci_required_baseline.json").read_bytes())
    if (
        baseline["version"] != 1
        or not baseline["required_ids"]
        or not baseline["minimum_ids"]
    ):
        raise ValueError("Invalid required-test baseline")
    for key, actual in (("required_ids", required), ("minimum_ids", minimum)):
        nodes = baseline[key]
        if len(nodes) != len(set(nodes)) or not set(nodes) <= set(actual):
            raise ValueError("Previously required tests disappeared: " + key)


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.PIPE
    )


def policy(root=ROOT):
    value = json.loads((root / "scripts/ci_dependencies.json").read_bytes())
    if value["version"] != 1 or set(value["groups"]) != {"schema", "p2", "ci"}:
        raise ValueError("Unsupported dependency policy")
    grouped = sum(value["groups"].values(), [])
    if len(grouped) != len(set(grouped)) or not all(
        p.startswith("tests/") and p.endswith(".py") for p in grouped
    ):
        raise ValueError("Duplicate/invalid test group membership")
    if not set(value["minimum_schema"]) <= set(value["groups"]["schema"]):
        raise ValueError("Minimum lane is not a schema subset")
    if set(value["minimum_schema"]) != MINIMUM_SCHEMA or set(value["groups"]["p2"]) != {
        "tests/integration/test_conversion_foundation.py",
        "tests/unit/test_conversion_protocol.py",
    }:
        raise ValueError("Required minimum/P2 test files may not disappear")
    return value


def tree(root, revision):
    if not SHA.fullmatch(revision or ""):
        raise ValueError("Expected a full Git SHA")
    entries = {}
    for item in git(root, "ls-tree", "-rz", "--full-tree", revision).split(b"\0"):
        if not item:
            continue
        meta, raw_path = item.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        path = raw_path.decode("utf-8", "surrogateescape")
        entries[path] = [mode, kind, oid]
    return entries


def parse_diff(raw):
    """Parse --name-status -z, including both rename/copy sides; never shell paths."""
    parts = raw.split(b"\0")
    if parts.pop() != b"":
        raise ValueError("Truncated Git diff")
    changed = []
    i = 0
    while i < len(parts):
        status = parts[i].decode("ascii")
        i += 1
        if not re.fullmatch(r"[ACDMRTUXB](?:[0-9]{1,3})?", status):
            raise ValueError("Unknown Git status")
        count = 2 if status[0] in "RC" else 1
        paths = parts[i : i + count]
        if len(paths) != count or not all(paths):
            raise ValueError("Truncated Git diff paths")
        i += count
        changed.append(
            {
                "status": status,
                "paths": [p.decode("utf-8", "surrogateescape") for p in paths],
            }
        )
    return changed


def changes(root, context):
    if context.get("diff_complete") is False:
        raise ValueError("Diff is absent or truncated")
    event = context["event"]
    if event == "pull_request":
        bases = (
            git(
                root, "merge-base", "--all", context["base_sha"], context["feature_sha"]
            )
            .decode()
            .splitlines()
        )
        if len(bases) != 1:
            raise ValueError("Missing/ambiguous merge base")
        start = bases[0]
    elif (
        event == "push"
        and SHA.fullmatch(context.get("before_sha", ""))
        and set(context["before_sha"]) != {"0"}
    ):
        start = context["before_sha"]
        git(root, "cat-file", "-e", start + "^{commit}")
    else:
        raise ValueError("Missing comparison history")
    return start, parse_diff(
        git(
            root,
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            start,
            context["feature_sha"],
        )
    )


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def test_files(entries):
    return sorted(
        p
        for p in entries
        if p.rsplit("/", 1)[-1].startswith("test_")
        and p.endswith(".py")
        and any(p.startswith(d + "/") for d in REQUIRED_DIRS)
    )


def groups(entries, rules):
    files = test_files(entries)
    if not set(sum(rules["groups"].values(), [])) <= set(files):
        raise ValueError("Declared required test files are missing")
    named = {k: sorted(set(v) & set(files)) for k, v in rules["groups"].items()}
    assigned = set(sum(named.values(), []))
    named["packaging"] = [p for p in files if p.startswith("tests/packaging/")]
    named["legacy"] = [
        p for p in files if p not in assigned and p not in named["packaging"]
    ]
    named["minimum-schema"] = sorted(set(rules["minimum_schema"]) & set(files))
    named["minimum-p2"] = named["p2"]
    # Every current required file belongs to exactly one normal/packaging group.
    partition = sum((named[k] for k in (*NORMAL, "packaging")), [])
    if len(partition) != len(set(partition)) or set(partition) != set(files):
        raise ValueError("Required test partition is not exhaustive")
    return named


def runtime():
    os_release = platform.freedesktop_os_release()
    return {
        "python": platform.python_version(),
        "abi": sysconfig.get_config_var("SOABI"),
        "sqlite": sqlite3.sqlite_version,
        "os": [os_release.get("ID"), os_release.get("VERSION_ID")],
        "arch": platform.machine(),
        "git": subprocess.check_output(["git", "--version"], text=True).strip(),
        "uv": "0.12.19",
        "minimum_sqlite": "3.46.1",
        "runner_image": [os.environ.get("ImageOS"), os.environ.get("ImageVersion")],
        "compiler": subprocess.check_output(
            ["cc", "--version"], text=True
        ).splitlines()[0],
    }


def lane_inputs(entries, rules, named):
    common = rules["common_inputs"]
    schema_tests = (
        named["schema"]
        + named["p2"]
        + ["tests/integration/test_v2_hardening_reproductions.py"]
    )
    patterns = {
        "static": ["src/**", "tests/**", "scripts/**", "pyproject.toml", "uv.lock"],
        "legacy": common + named["legacy"],
        "schema": common + rules["schema_inputs"] + schema_tests,
        "p2": common + rules["schema_inputs"] + schema_tests,
        "ci": common
        + named["ci"]
        + rules["policy_inputs"]
        + ["docs/ci-performance-baseline.json"],
        "packaging": common + named["packaging"] + ["scripts/prepare_wheelhouse.py"],
        "minimum-schema": common + rules["schema_inputs"] + schema_tests,
        "minimum-p2": common + rules["schema_inputs"] + schema_tests,
        "smoke": common,
        "build": common + ["scripts/prepare_wheelhouse.py"],
        "demo": common + named["legacy"] + ["scripts/demo.py"],
    }
    return {
        k: {p: v for p, v in entries.items() if matches(p, patterns[k])} for k in LANES
    }


def context_from_environment():
    path = os.environ.get("GITHUB_EVENT_PATH")
    event = json.loads(Path(path).read_bytes()) if path else {}
    pr = event.get("pull_request", {})
    return {
        "repository": os.environ.get("GITHUB_REPOSITORY", "TakashiSasaki/git-repo-db"),
        "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "pr": event.get("number"),
        "feature_sha": pr.get("head", {}).get("sha")
        or git(ROOT, "rev-parse", "HEAD").decode().strip(),
        "base_sha": pr.get("base", {}).get("sha"),
        "tested_sha": git(ROOT, "rev-parse", "HEAD").decode().strip(),
        "head_repository": pr.get("head", {}).get("repo", {}).get("full_name"),
        "before_sha": event.get("before"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "full": event.get("inputs", {}).get("full", False) in (True, "true"),
    }


def check_context(root, context):
    for field in ("feature_sha", "tested_sha"):
        if not SHA.fullmatch(context.get(field) or ""):
            raise ValueError("Invalid revision: " + field)
    if context["event"] != "pull_request":
        return
    if not SHA.fullmatch(context.get("base_sha") or ""):
        raise ValueError("Invalid base revision")
    parents = (
        git(root, "show", "-s", "--format=%P", context["tested_sha"]).decode().split()
    )
    if parents != [context["base_sha"], context["feature_sha"]]:
        # Local use may use the feature tree if the base is already its ancestor.
        if (
            context.get("run_id")
            or context["tested_sha"] != context["feature_sha"]
            or git(root, "merge-base", context["base_sha"], context["feature_sha"])
            .decode()
            .strip()
            != context["base_sha"]
        ):
            raise ValueError("Effective merge parents do not match event revisions")


def validate_evidence(evidence, context, policy_hash, runtime_meta, root):
    """Only verified full acceptance artifacts can back reuse; no result-cache chain."""
    from scripts.ci_evidence import verify_envelope

    verify_envelope(evidence, context)
    manifest = evidence["manifest"]
    if (
        manifest["version"] != 1
        or not manifest["full_acceptance"]
        or manifest["outcome"] != "passed"
    ):
        raise ValueError("Prior evidence is not a full acceptance")
    prior = manifest["context"]
    if (
        prior["base_sha"] != context["base_sha"]
        or prior["repository"] != context["repository"]
        or prior["pr"] != context["pr"]
    ):
        raise ValueError("Prior base/repository/PR context differs")
    if manifest["policy_hash"] != policy_hash or manifest["runtime"] != runtime_meta:
        raise ValueError("Prior policy/dependency/runtime differs")
    if subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "merge-base",
            "--is-ancestor",
            prior["feature_sha"],
            context["feature_sha"],
        ],
        capture_output=True,
    ).returncode:
        raise ValueError(
            "Prior feature is not an ancestor (force push/unknown history)"
        )
    check_context(root, prior)
    rules = policy(root)
    old = tree(root, prior["tested_sha"])
    old_policy = digest({p: old.get(p) for p in rules["policy_inputs"]})
    if old_policy != policy_hash:
        raise ValueError("Tested workflow/planner policy differs")
    named = groups(old, rules)
    inputs = lane_inputs(old, rules, named)
    if set(manifest["lanes"]) != set(LANES):
        raise ValueError("Incomplete evidence lanes")
    all_ids = []
    for lane in LANES:
        item = manifest["lanes"][lane]
        if (
            item["state"] != "passed"
            or item["provenance"] != "fresh"
            or item["input_fingerprint"] != digest(inputs[lane])
        ):
            raise ValueError("Prior lane failed/skipped/incomplete or inputs differ")
        nodes = item["test_ids"]
        if item["selection_digest"] != digest(nodes) or len(nodes) != len(set(nodes)):
            raise ValueError("Prior selection digest/duplicates invalid")
        if lane in TEST_LANES:
            if not nodes or {n.split("::")[0] for n in nodes} != set(named[lane]):
                raise ValueError("Prior test-file coverage differs")
        elif nodes:
            raise ValueError("Non-test lane claimed tests")
        if lane in (*NORMAL, "packaging"):
            all_ids += nodes
    if sorted(all_ids) != manifest["required_ids"] or len(all_ids) != len(set(all_ids)):
        raise ValueError("Prior required collection mismatch")
    check_baseline(
        all_ids,
        manifest["lanes"]["minimum-schema"]["test_ids"]
        + manifest["lanes"]["minimum-p2"]["test_ids"],
        root,
    )
    return manifest


def make_plan(context, evidence=None, root=ROOT, runtime_meta=None):
    started = time.perf_counter()
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError(
            "Commit tracked/untracked changes before recording tree-based CI evidence"
        )
    if git(root, "rev-parse", "HEAD^{tree}") != git(
        root, "rev-parse", context["tested_sha"] + "^{tree}"
    ):
        raise ValueError("Working checkout does not match the effective tested tree")
    rules = policy(root)
    entries = tree(root, context["tested_sha"])
    named = groups(entries, rules)
    inputs = lane_inputs(entries, rules, named)
    meta = runtime_meta or runtime()
    policy_hash = digest({p: entries.get(p) for p in rules["policy_inputs"]})
    reasons = []
    try:
        check_context(root, context)
        comparison, changed = changes(root, context)
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        comparison, changed = None, []
        reasons.append(str(error))
    paths = sorted({p for row in changed for p in row["paths"]})
    known = (
        rules["prose"]
        + rules["policy_inputs"]
        + rules["common_inputs"]
        + rules["schema_inputs"]
        + [
            *test_files(entries),
            "scripts/prepare_wheelhouse.py",
            "scripts/demo.py",
            "docs/ci-performance-baseline.json",
            ".gitignore",
        ]
    )
    unknown = [p for p in paths if not matches(p, known)]
    if unknown:
        reasons.append("Unknown dependency paths: " + repr(unknown))
    if matches_any := [p for p in paths if p in rules["policy_inputs"]]:
        # An ancestor full acceptance for exactly this new policy may be reused.
        policy_changed = matches_any
    else:
        policy_changed = []
    if context["event"] != "pull_request" or context.get("full"):
        reasons.append("Main/push/manual/local or explicit full acceptance")
    if context.get("head_repository") != context["repository"]:
        reasons.append("Fork/unknown head context: full, no evidence reuse")
    prior = None
    if not reasons and evidence:
        try:
            prior = validate_evidence(evidence, context, policy_hash, meta, root)
        except (
            ValueError,
            KeyError,
            TypeError,
            subprocess.CalledProcessError,
        ) as error:
            reasons.append("Evidence rejected: " + str(error))
    if prior is None and not reasons:
        reasons.append("No verified unchanged-input full acceptance evidence")
    if policy_changed and prior is None:
        reasons.append("Workflow/planner policy changes require full acceptance")
    lanes = {}
    for lane in LANES:
        fingerprint = digest(inputs[lane])
        reused = (
            prior is not None
            and fingerprint == prior["lanes"][lane]["input_fingerprint"]
        )
        lanes[lane] = {
            "disposition": "reused" if reused else "selected",
            "input_fingerprint": fingerprint,
            "input_paths": sorted(inputs[lane]),
            "triggering_paths": [
                p
                for p in paths
                if p in inputs[lane] or p not in entries and p not in rules["prose"]
            ],
            "dependencies": [
                "effective merge tree",
                "policy",
                "runtime",
                "locked dependencies",
            ],
            "test_files": named.get(lane, []),
            "test_ids": prior["lanes"][lane]["test_ids"] if reused else [],
            "selection_digest": prior["lanes"][lane]["selection_digest"]
            if reused
            else digest(named.get(lane, [])),
            "selection_kind": "nodeids"
            if reused or lane not in TEST_LANES
            else "files-until-collection",
            "prior_run": prior["context"]["run_id"] if reused else None,
        }
    normal = any(lanes[k]["disposition"] == "selected" for k in NORMAL)
    minimum = any(
        lanes[k]["disposition"] == "selected" for k in ("minimum-schema", "minimum-p2")
    )
    packaging = lanes["packaging"]["disposition"] == "selected"
    preparation = {
        "dependencies": normal
        or minimum
        or packaging
        or any(
            lanes[k]["disposition"] == "selected"
            for k in ("static", "smoke", "build", "demo")
        ),
        "wheelhouse": packaging or lanes["build"]["disposition"] == "selected",
        "sqlite-binding": minimum or lanes["p2"]["disposition"] == "selected",
    }
    result = {
        "version": 1,
        "context": context,
        "runtime": meta,
        "policy_hash": policy_hash,
        "comparison_sha": comparison,
        "changed": changed,
        "fallback_reasons": reasons,
        "full": all(v["disposition"] == "selected" for v in lanes.values()),
        "lanes": lanes,
        "preparation": {
            k: {
                "disposition": "selected" if v else "not_applicable",
                "cache": "not-enabled",
                "test_ids": [],
                "selection_digest": digest([]),
                "input_fingerprint": digest(
                    {"runtime": meta, "policy": policy_hash, "kind": k}
                ),
                "prior_run": None,
                "reason": "Required by selected execution lanes"
                if v
                else "No selected lane requires preparation",
            }
            for k, v in preparation.items()
        },
        "prior_manifest": prior,
        "always_checks": {
            "reports": {
                "disposition": "selected",
                "input_fingerprint": digest(
                    {p: entries.get(p) for p in rules["prose"]}
                ),
                "selection_digest": digest([]),
            },
            "final-gate": {
                "disposition": "selected",
                "input_fingerprint": policy_hash,
                "selection_digest": digest([]),
            },
        },
        "selection_wall_seconds": time.perf_counter() - started,
    }
    return result


def explain(plan):
    lines = [
        "## Validation plan",
        "",
        f"Effective SHA `{plan['context']['tested_sha']}`; base `{plan['context'].get('base_sha')}`.",
        "",
        "| Lane | Disposition | Expected tests | Prior successful run |",
        "|---|---|---:|---|",
    ]
    for name, item in plan["lanes"].items():
        lines.append(
            f"| {name} | {item['disposition']} | {len(item['test_ids']) if item['selection_kind'] == 'nodeids' else 'collect ' + str(len(item['test_files'])) + ' files'} | {item['prior_run'] or '—'} |"
        )
    lines += [
        "",
        "Selected = fresh execution required; reused = verified earlier acceptance, no fresh test claim.",
    ]
    lines += (
        ["", "Fallback: " + reason]
        if (reason := "; ".join(plan["fallback_reasons"]))
        else []
    )
    lines += [
        "",
        f"Planner: {plan['selection_wall_seconds']:.3f}s. Preparation: "
        + ", ".join(f"{k}={v['disposition']}" for k, v in plan["preparation"].items()),
    ]
    return "\n".join(lines) + "\n"


def write_plan(plan, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=True) + "\n"
    )
    report = explain(plan)
    (output / "plan.md").write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(report)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            for name, item in plan["preparation"].items():
                handle.write(
                    f"{name}={str(item['disposition'] == 'selected').lower()}\n"
                )
            for name, item in plan["lanes"].items():
                handle.write(
                    f"{name}={str(item['disposition'] == 'selected').lower()}\n"
                )
            handle.write(
                f"normal={str(any(plan['lanes'][k]['disposition'] == 'selected' for k in NORMAL)).lower()}\n"
            )
            handle.write(
                f"minimum={str(any(plan['lanes'][k]['disposition'] == 'selected' for k in ('minimum-schema', 'minimum-p2'))).lower()}\n"
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ci-profile"))
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    context = (
        json.loads(args.context.read_bytes())
        if args.context
        else context_from_environment()
    )
    if args.full:
        context["full"] = True
    evidence = load_evidence(args.evidence) if args.evidence else None
    write_plan(make_plan(context, evidence), args.output)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT))
    main()
