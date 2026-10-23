"""Independently reproduce missing required-sdist-input binding (stdlib only)."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts import ci_plan
from tests.support.ci_fixture import commit, context, repository, write


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


with tempfile.TemporaryDirectory(prefix="adr0033-readme-binding-") as temporary:
    root = Path(temporary) / "synthetic"
    base, head = repository(root)
    before = ci_plan.make_plan(context(root, base, head, event="push"), root=root)
    before_blob = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD:README.md"], text=True).strip()
    write(root, "README.md", "# Changed required sdist source input\n")
    changed = commit(root, "Change required sdist README input only")
    after = ci_plan.make_plan(context(root, head, changed, event="push"), root=root)
    after_blob = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD:README.md"], text=True).strip()
    result = {
        "probe_kind": "counterexample_expected_to_expose_defect",
        "source_head": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "reviewed_file_hashes": {str(p.relative_to(ROOT)): sha(p) for p in [ROOT / "scripts/ci_plan.py", ROOT / "scripts/ci_dependencies.json"]},
        "changed_paths": after["changed"],
        "before_readme_blob": before_blob,
        "after_readme_blob": after_blob,
        "before_acceptance_input_hash": before["acceptance_input_hash"],
        "after_acceptance_input_hash": after["acceptance_input_hash"],
        "before_tree_hash": before["tree_hash"],
        "after_tree_hash": after["tree_hash"],
        "after_preparation": after["preparation"],
        "after_selected_files": after["selected_files"],
    }
    assert before_blob != after_blob
    assert before["tree_hash"] != after["tree_hash"]
    assert before["acceptance_input_hash"] == after["acceptance_input_hash"]
    assert after["preparation"]["sdist_contract"]["disposition"] == "selected"
    print(json.dumps(result, indent=2))
