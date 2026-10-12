"""Small changed-file CI planner for the current catalog3 acceptance suite."""

import argparse
import ast
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
LANES = ("static", "tests", "packaging", "smoke")
TEST_LANES = ("tests", "packaging")
REQUIRED_DIRS = ("tests/unit", "tests/integration", "tests/e2e", "tests/packaging")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.PIPE
    )


def policy(root=ROOT):
    value = json.loads((root / "scripts/ci_dependencies.json").read_bytes())
    if value["version"] != 3 or value.get("acceptance_directories") != list(
        REQUIRED_DIRS
    ):
        raise ValueError("Unsupported acceptance policy or ordinary test directories")
    return value


def tree(root, revision):
    if not SHA.fullmatch(revision or ""):
        raise ValueError("Expected a full Git SHA")
    entries = {}
    for item in git(root, "ls-tree", "-rz", "--full-tree", revision).split(b"\0"):
        if item:
            meta, raw_path = item.split(b"\t", 1)
            entries[raw_path.decode("utf-8", "surrogateescape")] = meta.decode().split()
    return entries


def parse_diff(raw):
    parts = raw.split(b"\0")
    if parts.pop() != b"":
        raise ValueError("Truncated Git diff")
    changed, i = [], 0
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
    if context["event"] == "pull_request" and context.get("action") == "synchronize":
        before = context.get("before_sha")
        if (
            not isinstance(before, str)
            or not SHA.fullmatch(before)
            or set(before) == {"0"}
        ):
            raise ValueError("Missing/invalid PR synchronization history")
        git(root, "cat-file", "-e", before + "^{commit}")
        if subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "merge-base",
                "--is-ancestor",
                before,
                context["feature_sha"],
            ],
            capture_output=True,
        ).returncode:
            raise ValueError(
                "PR before revision is not an ancestor (force push/unknown history)"
            )
        # Select fresh affected checks. This is not acceptance-result reuse:
        # unexecuted runtime coverage stays explicitly unexecuted. Comparing
        # against the actual merge tree also includes current base deltas.
        start = before
    elif context["event"] == "pull_request":
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
        context["event"] == "push"
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
            context["tested_sha"],
        )
    )


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def is_test_file(path):
    # Pytest's default python_files patterns, including sibling-style names.
    return matches(path.rsplit("/", 1)[-1], ("test_*.py", "*_test.py"))


def acceptance_files(entries, rules):
    files = sorted(
        path
        for path in entries
        if is_test_file(path)
        and any(
            path.startswith(directory + "/")
            for directory in rules["acceptance_directories"]
        )
    )
    if not files:
        raise ValueError("No ordinary acceptance test files found")
    return files


def imported_test_files(root, entries, files):
    """Find test modules used as helpers; uncertain imports require full selection."""
    modules = {path[:-3].replace("/", "."): path for path in files}
    basenames = {}
    for module, path in modules.items():
        basenames.setdefault(module.rsplit(".", 1)[-1], set()).add(path)
    imported = set()
    for path in entries:
        if not path.startswith("tests/") or not path.endswith(".py"):
            continue
        try:
            syntax = ast.parse((root / path).read_bytes(), filename=path)
        except (SyntaxError, UnicodeError, OSError) as error:
            raise ValueError("Cannot inspect test dependencies: " + path) from error
        package = path.split("/")[:-1]
        for node in ast.walk(syntax):
            names = []
            if (
                isinstance(node, ast.Name)
                and node.id in ("pytest_plugins", "__import__", "import_module")
                or isinstance(node, ast.Attribute)
                and node.attr in ("import_module", "__import__")
            ):
                # Pytest plugins and aliased/computed imports can make a test
                # module a shared input without an ordinary import statement.
                raise ValueError(
                    "Dynamic test dependency requires full selection: " + path
                )
            if isinstance(node, ast.Import):
                if any(alias.name == "importlib" for alias in node.names):
                    raise ValueError(
                        "Dynamic test dependency requires full selection: " + path
                    )
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module in ("importlib", "builtins") and any(
                    alias.name in ("import_module", "__import__", "*")
                    for alias in node.names
                ):
                    raise ValueError(
                        "Dynamic test dependency requires full selection: " + path
                    )
                if node.level > len(package):
                    raise ValueError("Unresolved relative test import: " + path)
                prefix = package[: len(package) - node.level + 1] if node.level else []
                module = ".".join(prefix + ([node.module] if node.module else []))
                names = [module] + [module + "." + alias.name for alias in node.names]
                if any(alias.name == "*" for alias in node.names):
                    imported.update(
                        file
                        for name, file in modules.items()
                        if name.startswith(module + ".")
                    )
            imported.update(modules[name] for name in names if name in modules)
            # Pytest's prepend import mode can also make sibling test modules
            # available by basename; ambiguous names conservatively include both.
            for name in names:
                imported.update(basenames.get(name, ()))
    return imported


def current_acceptance_files(root=ROOT):
    entries = [
        str(path.relative_to(root))
        for directory in REQUIRED_DIRS
        for path in (root / directory).glob("**/*.py")
    ]
    return acceptance_files(entries, policy(root))


def runtime():
    try:
        uv = subprocess.check_output(["uv", "--version"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        uv = None
    return {
        "python": platform.python_version(),
        "abi": sysconfig.get_config_var("SOABI"),
        "sqlite": sqlite3.sqlite_version,
        "os": platform.system(),
        "arch": platform.machine(),
        "git": subprocess.check_output(["git", "--version"], text=True).strip(),
        "uv": uv,
        "runner_image": [os.environ.get("ImageOS"), os.environ.get("ImageVersion")],
    }


def context_from_environment():
    path = os.environ.get("GITHUB_EVENT_PATH")
    event = json.loads(Path(path).read_bytes()) if path else {}
    pr = event.get("pull_request", {})
    head = git(ROOT, "rev-parse", "HEAD").decode().strip()
    inputs = event.get("inputs", {})
    mode = os.environ.get("CI_VALIDATION_MODE") or inputs.get("mode")
    if not mode:
        full_in = inputs.get("full", False) in (True, "true")
        mode = "release" if full_in else "development"
    if mode not in ("development", "release"):
        raise ValueError(f"Unsupported validation mode: {mode}")
    return {
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "action": event.get("action"),
        "feature_sha": pr.get("head", {}).get("sha") or head,
        "base_sha": pr.get("base", {}).get("sha"),
        "tested_sha": head,
        "before_sha": event.get("before"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "mode": mode,
        "full": mode == "release",
    }


def check_context(root, context):
    for field in ("feature_sha", "tested_sha"):
        if not SHA.fullmatch(context.get(field) or ""):
            raise ValueError("Invalid revision: " + field)
    if context["event"] == "pull_request":
        parents = (
            git(root, "show", "-s", "--format=%P", context["tested_sha"])
            .decode()
            .split()
        )
        if parents != [context["base_sha"], context["feature_sha"]]:
            if (
                context.get("run_id")
                or context["tested_sha"] != context["feature_sha"]
                or git(root, "merge-base", context["base_sha"], context["feature_sha"])
                .decode()
                .strip()
                != context["base_sha"]
            ):
                raise ValueError("Effective merge parents do not match event revisions")


def make_plan(context, root=ROOT, runtime_meta=None):
    started = time.perf_counter()
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError(
            "Commit tracked/untracked changes before recording tree-based CI evidence"
        )
    if git(root, "rev-parse", "HEAD^{tree}") != git(
        root, "rev-parse", context["tested_sha"] + "^{tree}"
    ):
        raise ValueError("Working checkout does not match the effective tested tree")
    rules, entries = policy(root), tree(root, context["tested_sha"])
    files = acceptance_files(entries, rules)
    excluded = sorted(
        path
        for path in entries
        if is_test_file(path)
        and any(path.startswith(directory + "/") for directory in REQUIRED_DIRS)
        and path not in files
    )
    reasons = []
    try:
        check_context(root, context)
        comparison, changed = changes(root, context)
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        comparison, changed = None, []
        reasons.append(str(error))
    paths = sorted({p for row in changed for p in row["paths"]})
    imported = set()
    if set(paths) & set(files):
        try:
            imported = imported_test_files(root, entries, files)
        except ValueError as error:
            reasons.append(str(error))

    context = dict(context)
    mode = context.get("mode")
    if context.get("full") and mode != "release":
        mode = "release"
    elif not mode:
        mode = "release" if context.get("full") else "development"
    if mode not in ("development", "release"):
        raise ValueError(f"Unsupported validation mode: {mode}")
    is_release = mode == "release"
    context["mode"] = mode
    context["full"] = is_release

    scope_reasons = []
    leaf_tests = set()
    code_or_config_changed = False
    schema_or_contract_changed = False

    for path in paths:
        if matches(path, rules["shared_inputs"] + rules["executable_inputs"]):
            scope_reasons.append("Shared/executable input: " + path)
            code_or_config_changed = True
            if (
                path.startswith("src/")
                or "schema" in path
                or path == "scripts/ci_dependencies.json"
            ):
                schema_or_contract_changed = True
        elif path in imported:
            scope_reasons.append("Imported test helper: " + path)
            code_or_config_changed = True
        elif path in files:
            leaf_tests.add(path)
            code_or_config_changed = True
        elif matches(path, rules.get("report_inputs", [])):
            pass
        elif matches(path, rules["prose"]):
            pass
        else:
            scope_reasons.append("Unknown dependency path: " + path)
            code_or_config_changed = True

    if reasons:
        scope_reasons.extend(reasons)
        code_or_config_changed = True

    if scope_reasons or is_release:
        required_files = set(files)
    elif leaf_tests:
        required_files = set(leaf_tests)
    else:
        required_files = set()

    if is_release:
        selected = set(files)
        static = smoke = True
    else:
        static = code_or_config_changed
        smoke = schema_or_contract_changed or bool(scope_reasons)
        if leaf_tests and not scope_reasons:
            selected = set(leaf_tests)
        else:
            selected = set()

    if context.get("selected_test_files"):
        selected.update(context["selected_test_files"])

    lanes = {}
    for name in LANES:
        lane_files = (
            sorted(
                p
                for p in selected
                if p.startswith("tests/packaging/") == (name == "packaging")
            )
            if name in TEST_LANES
            else []
        )
        active = (
            bool(lane_files)
            if name in TEST_LANES
            else static
            if name == "static"
            else smoke
        )
        lanes[name] = {
            "disposition": "selected" if active else "not_applicable",
            "test_files": lane_files,
            "test_ids": [],
            "selection_kind": "files-until-collection" if lane_files else "nodeids",
            "selection_digest": digest(lane_files),
        }
    packaging = lanes["packaging"]["disposition"] == "selected"
    return {
        "version": 3,
        "mode": mode,
        "context": context,
        "runtime": runtime_meta or runtime(),
        "policy_hash": digest({p: entries.get(p) for p in rules["policy_inputs"]}),
        "tree_hash": digest(entries),
        "acceptance_input_hash": digest(
            {
                path: entry
                for path, entry in entries.items()
                if path in files
                or matches(path, rules["shared_inputs"] + rules["executable_inputs"])
                or not matches(path, rules["prose"] + rules.get("report_inputs", []))
            }
        ),
        "comparison_sha": comparison,
        "changed": changed,
        "fallback_reasons": scope_reasons,
        "full": is_release and set(files) == selected and static and smoke,
        "acceptance_files": files,
        "required_files": sorted(required_files),
        "selected_files": sorted(selected),
        "excluded_files": excluded,
        "unexecuted_files": sorted(set(files) - selected),
        "lanes": lanes,
        "preparation": {
            "dependencies": {
                "disposition": "selected"
                if selected or static or smoke
                else "not_applicable"
            },
            "wheelhouse": {
                "disposition": "selected" if packaging else "not_applicable"
            },
        },
        "selection_wall_seconds": time.perf_counter() - started,
    }


def explain(plan):
    lines = [
        "## Validation plan",
        "",
        f"Mode: `{plan.get('mode', 'development')}`; Effective SHA `{plan['context']['tested_sha']}`; full acceptance selected: {plan['full']}.",
        f"Acceptance input hash: `{plan['acceptance_input_hash']}`.",
        "",
        "| Lane | Disposition | Test files |",
        "|---|---|---:|",
    ]
    lines += [
        f"| {name} | {item['disposition']} | {len(item['test_files'])} |"
        for name, item in plan["lanes"].items()
    ]
    lines += [
        "",
        f"Required test files: {len(plan.get('required_files', []))}.",
        f"Selected test files: {len(plan.get('selected_files', []))}.",
        f"Unexecuted acceptance files: {len(plan['unexecuted_files'])}. Earlier test results are never claimed as fresh execution.",
        f"Files outside current acceptance: {len(plan['excluded_files'])}; listed in plan.json.",
        "",
        f"Planner: {plan['selection_wall_seconds']:.3f}s.",
    ]
    if plan["fallback_reasons"]:
        lines += ["", "### Scope reasons", *plan["fallback_reasons"]]
    return "\n".join(lines) + "\n"


def write_plan(plan, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    report = explain(plan)
    (output / "plan.md").write_text(report)
    for env, value in (
        ("GITHUB_STEP_SUMMARY", report),
        (
            "GITHUB_OUTPUT",
            "".join(
                f"{name}={str(item['disposition'] == 'selected').lower()}\n"
                for name, item in {**plan["lanes"], **plan["preparation"]}.items()
            ),
        ),
    ):
        if os.environ.get(env):
            with open(os.environ[env], "a") as handle:
                handle.write(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ci-profile"))
    parser.add_argument(
        "--mode",
        choices=("development", "release"),
        help="Validation mode (development or release)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="(Deprecated) Alias for --mode release",
    )
    args = parser.parse_args()
    context = (
        json.loads(args.context.read_bytes())
        if args.context
        else context_from_environment()
    )
    if args.mode:
        context["mode"] = args.mode
        context["full"] = args.mode == "release"
    elif args.full:
        context["mode"] = "release"
        context["full"] = True
    write_plan(make_plan(context), args.output)


if __name__ == "__main__":
    main()
