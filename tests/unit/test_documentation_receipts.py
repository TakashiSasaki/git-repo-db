"""Synthetic release-conjunction controls; never claim actual release evidence."""

import json
import subprocess

import pytest

from scripts.documentation_receipts import DocumentationGap, complete_documentation, sha


@pytest.fixture
def evidence(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()

    git("init", "-q")
    git("config", "user.name", "Synthetic release fixture")
    git("config", "user.email", "fixture@example.invalid")
    source = root / "source.sql"
    source.write_text("synthetic SQL")
    mapping = root / "docs/implementation/documentation-separation-node-map.json"
    mapping.parent.mkdir(parents=True)
    node = "documentation/tests/test_example.py::test_example"
    mapping.write_text(json.dumps({"mapping": [{"current_nodes": [node]}]}))
    lock = root / "documentation/uv.lock"
    lock.parent.mkdir()
    lock.write_text("synthetic documentation lock")
    git("add", ".")
    git("commit", "-qm", "synthetic selected product")
    product = {
        "commit": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
    }
    (root / "documentation/page.md").write_text("synthetic documentation")
    git("add", ".")
    git("commit", "-qm", "synthetic documentation source")
    doc = {"commit": git("rev-parse", "HEAD"), "tree": git("rev-parse", "HEAD^{tree}")}
    ir = b'{"synthetic":"complete neutral IR fixture"}'
    producer = json.dumps(
        {
            "schema_version": 1,
            "product_source": product,
            "ir_sha256": sha(ir),
            "input_sha256": {"source.sql": sha(source.read_bytes())},
        }
    ).encode()
    receipts = []
    for context in ("local", "hosted"):
        directory = tmp_path / context
        directory.mkdir()
        (directory / "inventory.json").write_bytes(ir)
        (directory / "producer.json").write_bytes(producer)
        (directory / "tests.xml").write_text(
            '<testsuite><testcase classname="documentation.tests.test_example" name="test_example"/></testsuite>'
        )
        for i in range(5):
            (directory / f"command-{i}.log").write_text(
                node + "\n" if i == 1 else "synthetic success\n"
            )
        commands = [
            [
                "python",
                "documentation/tools/build_docs_site.py",
                "--product-source",
                product["commit"],
                "--documentation-source",
                doc["commit"],
            ],
            ["python", "-m", "pytest", "-q", "documentation/tests", "--collect-only"],
            [
                "python",
                "-m",
                "pytest",
                "-q",
                "documentation/tests",
                "--junitxml=tests.xml",
            ],
            [
                "python",
                "-m",
                "ruff",
                "check",
                "documentation/tools",
                "documentation/tests",
            ],
            [
                "python",
                "-m",
                "ruff",
                "format",
                "--check",
                "documentation/tools",
                "documentation/tests",
            ],
        ]
        value = {
            "schema_version": 1,
            "scope": "documentation",
            "full_acceptance": False,
            "status": "passed",
            "build_mode": "complete",
            "execution_context": context,
            "inputs": {
                "selected_product_source": product,
                "documentation_source": doc,
                "neutral_ir_sha256": sha(ir),
                "producer_manifest_sha256": sha(producer),
                "producer_input_sha256": {"source.sql": sha(source.read_bytes())},
            },
            "documentation_lock_sha256": sha(lock.read_bytes()),
            "test_ids": [node],
            "commands": commands,
            "command_exit_codes": [0] * 5,
            "artifact_sha256": {
                p.name: sha(p.read_bytes()) for p in directory.iterdir()
            },
        }
        path = directory / "documentation-receipt.json"
        path.write_text(json.dumps(value))
        receipts.append(path)
    return root, receipts, product, sha(ir)


def verify(evidence, provider=lambda *args: None):
    root, paths, product, ir = evidence
    return complete_documentation(
        *paths, product, ir, root, "fixture/repository", provider_check=provider
    )


def test_independent_matching_documentation_obligations_can_complete_conjunction(
    evidence,
):
    assert verify(evidence)["status"] == "verified"


@pytest.mark.parametrize(
    "change",
    [
        "missing-local",
        "missing-hosted",
        "preview",
        "failed",
        "wrong-ir",
        "wrong-tree",
        "wrong-doc-source",
        "node-loss",
        "changed-artifact",
        "changed-command",
        "failed-command",
    ],
)
def test_missing_failed_changed_or_preview_evidence_cannot_complete_release(
    evidence, change
):
    root, paths, product, ir = evidence
    if change.startswith("missing-"):
        paths[0 if change == "missing-local" else 1].unlink()
    else:
        path = paths[1]
        value = json.loads(path.read_text())
        if change == "preview":
            value["build_mode"] = "preview"
        elif change == "failed":
            value["status"] = "failed"
        elif change == "wrong-ir":
            value["inputs"]["neutral_ir_sha256"] = "0" * 64
        elif change == "wrong-tree":
            value["inputs"]["selected_product_source"]["tree"] = "0" * 40
        elif change == "wrong-doc-source":
            value["inputs"]["documentation_source"] = product
        elif change == "node-loss":
            value["test_ids"] = []
        elif change == "changed-artifact":
            (path.parent / "tests.xml").write_text("altered evidence")
        elif change == "changed-command":
            value["commands"][2][4] = "documentation/tests/one.py"
        else:
            value["command_exit_codes"][0] = 1
        path.write_text(json.dumps(value))
    assert verify(evidence)["status"] == "not_verified"


def test_unavailable_or_rejected_hosted_provider_is_a_gap(evidence):
    def denied(*args):
        raise DocumentationGap("provider access denied")

    assert verify(evidence, denied)["status"] == "not_verified"
