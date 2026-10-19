"""Read-only final-source binding of previously executed independent R2 review."""

import ast
import datetime
import hashlib
import json
import subprocess
from zoneinfo import ZoneInfo


PREVIOUS = "f81a3992ac85542e015cb8f37a5ae9fc31f265b5"
FINAL = "8dcb5150ac6c987a93b96e56a9f935184affab94"
PATHS = [
    "src/repo_catalog/adapters/git/access_native.py",
    "src/repo_catalog/application/access_workflow.py",
    "src/repo_catalog/adapters/filesystem/access_executor.py",
    "src/repo_catalog/adapters/git/native.py",
    "src/repo_catalog/adapters/git/notes.py",
    "src/repo_catalog/adapters/sqlite/acquisition.py",
    "src/repo_catalog/adapters/sqlite/access_connections.py",
    "src/repo_catalog/adapters/sqlite/access_registry.py",
    "src/repo_catalog/adapters/sqlite/access_schema.py",
    "src/repo_catalog/domain/native_acquisition.py",
    "src/repo_catalog/domain/access_workflow.py",
    "src/repo_catalog/domain/access_connections.py",
    "src/repo_catalog/domain/access_registry.py",
    "tests/integration/access/test_handoff_boundary.py",
    "scripts/verify_access_distribution.py",
    ".agents/skills/three-store-invariants/references/final-executor-handoff.md",
]


def git(*args):
    return subprocess.check_output(["git", *args])


def main():
    assert git("rev-parse", "HEAD").decode().strip() == FINAL
    assert not git("status", "--porcelain=v1").strip()
    equal = []
    for path in PATHS:
        before, after = git("show", PREVIOUS + ":" + path), git("show", FINAL + ":" + path)
        assert before == after, path
        equal.append({"path": path, "git_blob": git("rev-parse", FINAL + ":" + path).decode().strip(), "sha256": hashlib.sha256(after).hexdigest(), "unchanged": True})
    source_changes = git("diff", "--name-only", PREVIOUS, FINAL, "--", "src/repo_catalog").decode().splitlines()
    assert source_changes == ["src/repo_catalog/application/acquisition.py"], source_changes
    regressions = "tests/integration/access/test_review_corrections.py"
    old_tests, new_tests = git("show", PREVIOUS + ":" + regressions), git("show", FINAL + ":" + regressions)
    before_functions = {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(old_tests).body if isinstance(node, ast.FunctionDef)}
    after_functions = {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(new_tests).body if isinstance(node, ast.FunctionDef)}
    assert all(after_functions.get(name) == value for name, value in before_functions.items()), "Existing regression assertions changed"
    print(json.dumps({"finish_jst": str(datetime.datetime.now(ZoneInfo("Asia/Tokyo"))), "previous_head": PREVIOUS, "previous_tree": git("rev-parse", PREVIOUS + "^{tree}").decode().strip(), "final_head": FINAL, "final_tree": git("rev-parse", FINAL + "^{tree}").decode().strip(), "dirty": git("status", "--porcelain=v1").decode(), "unchanged_inputs": equal, "source_changes": source_changes, "prior_review_regression_functions_unchanged_ast": len(before_functions), "conclusion": "R2 defect closures retain unchanged executable inputs; no runtime rerun claimed."}, indent=2))


if __name__ == "__main__":
    main()
