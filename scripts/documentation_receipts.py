"""Fail-closed conjunction of independent documentation release evidence.

No renderer/MkDocs imports. Product-only gates remain independent of this check.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


class DocumentationGap(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.PIPE
    )


def web_branch_map(root, commit):
    name = "docs/web-branch-test-map.json"
    present = subprocess.run(
        ["git", "cat-file", "-e", commit + ":" + name],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return (
        json.loads(git(root, "show", commit + ":" + name))
        if present.returncode == 0
        else None
    )


def verify_web_tracking_config(config):
    """Validate tracking policy, without requiring a maintained product SHA."""
    if (
        config.get("schema_version") != 2
        or config.get("repository")
        != "https://github.com/TakashiSasaki/resource-atlas.git"
        or config.get("ref") != "main"
        or "commit" in config
    ):
        raise DocumentationGap("Web source must follow canonical main")


def verify_moved_product_obligations(mapping, product_nodes):
    if mapping is None:
        return
    required = mapping.get("main_nodes")
    if not required or not set(required).issubset(set(product_nodes or [])):
        raise DocumentationGap(
            "Moved ownership/runtime-reference product obligations missing"
        )


def checked_receipt(path, context, product, ir_hash, root):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise DocumentationGap("Linked documentation receipt refused")
    raw = path.read_bytes()
    value = json.loads(raw)
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or value.get("pytest_root") != "website"
        or value.get("full_acceptance") is not False
        or value.get("scope") != "documentation"
        or value.get("status") != "passed"
        or value.get("build_mode") != "complete"
        or value.get("execution_context") != context
    ):
        raise DocumentationGap("Missing complete independent documentation execution")
    inputs = value.get("inputs", {})
    if (
        inputs.get("selected_product_source") != product
        or inputs.get("neutral_ir_sha256") != ir_hash
    ):
        raise DocumentationGap("Documentation selected product/IR mismatch")
    doc = inputs.get("documentation_source", {})
    commit = doc.get("commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or git(
        root, "rev-parse", commit + "^{tree}"
    ).decode().strip() != doc.get("tree"):
        raise DocumentationGap("Missing documentation source identity")
    lock = git(root, "show", commit + ":website/uv.lock")
    if sha(lock) != value.get("documentation_lock_sha256"):
        raise DocumentationGap("Documentation dependency lock mismatch")
    branch_map = web_branch_map(root, product["commit"])
    artifacts = value.get("artifact_sha256", {})
    required = {
        "tests.xml",
        "inventory.json",
        "producer.json",
        *{f"command-{i}.log" for i in range(6)},
    }
    if branch_map is not None:
        required.add("source-manifest.json")
    if set(artifacts) != required:
        raise DocumentationGap("Documentation execution artifact set mismatch")
    for name, digest in artifacts.items():
        item = path.parent / name
        if (
            item.is_symlink()
            or not item.is_file()
            or item.stat().st_size > 32 * 1024 * 1024
            or sha(item.read_bytes()) != digest
        ):
            raise DocumentationGap("Documentation execution artifact hash mismatch")
    if artifacts["inventory.json"] != ir_hash or artifacts[
        "producer.json"
    ] != inputs.get("producer_manifest_sha256"):
        raise DocumentationGap("Documentation producer evidence mismatch")
    producer = json.loads((path.parent / "producer.json").read_bytes())
    if (
        producer.get("product_source") != product
        or producer.get("ir_sha256") != ir_hash
        or producer.get("input_sha256") != inputs.get("producer_input_sha256")
        or not producer.get("input_sha256")
    ):
        raise DocumentationGap("Missing matching producer input evidence")
    from scripts.schema_inventory import producer_input_names

    expected_inputs = set(producer_input_names(root, product["commit"]))
    if set(producer["input_sha256"]) != expected_inputs:
        raise DocumentationGap("Complete producer input inventory missing or changed")
    executed = producer.get("executed_python_inputs")
    if (
        not isinstance(executed, list)
        or not executed
        or len(executed) != len(set(executed))
        or not set(executed).issubset(expected_inputs)
        or "scripts/schema_catalog.py" not in executed
    ):
        raise DocumentationGap("Executed producer closure missing or changed")
    for name, digest in producer["input_sha256"].items():
        if (
            not isinstance(name, str)
            or name.startswith("/")
            or any(x in {"", ".", ".."} for x in name.split("/"))
            or "\\" in name
        ):
            raise DocumentationGap("Unsafe producer input")
        if sha(git(root, "show", product["commit"] + ":" + name)) != digest:
            raise DocumentationGap("Producer committed input mismatch")
    if branch_map is not None:
        canonical_raw = (path.parent / "source-manifest.json").read_bytes()
        canonical = json.loads(canonical_raw)
        config = json.loads(git(root, "show", commit + ":product-source.json"))
        verify_web_tracking_config(config)
        if (
            canonical.get("product_source") != product
            or canonical.get("ir_sha256") != ir_hash
            or sha(canonical_raw) != inputs.get("canonical_source_manifest_sha256")
        ):
            raise DocumentationGap("Canonical-source handoff identity mismatch")
        policy_path = "docs/web-source-policy.json"
        policy = json.loads(git(root, "show", product["commit"] + ":" + policy_path))
        expected = {
            policy_path,
            policy["canonical_index"],
            *policy["public_adrs"],
            *policy["support"],
        }
        if set(canonical.get("canonical_sources", {})) != expected:
            raise DocumentationGap("Canonical publication selection mismatch")
        for name, digest in canonical["canonical_sources"].items():
            if sha(git(root, "show", product["commit"] + ":" + name)) != digest:
                raise DocumentationGap("Canonical source digest mismatch")
    nodes = value.get("test_ids", [])
    cases = ET.parse(path.parent / "tests.xml").findall(".//testcase")

    def canonical(node):
        return "website/" + node if node.startswith("tests/") else node

    actual = [
        canonical(c.attrib["classname"].replace(".", "/") + ".py::" + c.attrib["name"])
        for c in cases
    ]
    collected = [
        canonical(x.strip())
        for x in (path.parent / "command-1.log").read_text().splitlines()
        if x.startswith(("website/tests/", "tests/")) and "::" in x
    ]
    if (
        not nodes
        or len(nodes) != len(set(nodes))
        or Counter(nodes) != Counter(actual)
        or Counter(nodes) != Counter(collected)
        or any(
            c.find(x) is not None
            for c in cases
            for x in ("failure", "error", "skipped")
        )
    ):
        raise DocumentationGap("Documentation exact-node/outcome reconciliation failed")
    mapping = json.loads(
        git(
            root,
            "show",
            product["commit"]
            + ":docs/implementation/documentation-separation-node-map.json",
        )
    )
    obligations = {
        # A selected product revision may predate the workspace rename. Keep
        # its pinned mapping intact while locating the same obligation now.
        n.replace("documentation/", "website/", 1)
        if n.startswith("documentation/")
        else n
        for row in mapping["mapping"]
        for n in row["current_nodes"]
        if n.startswith(("website/", "documentation/"))
    }
    if branch_map is not None:
        moved = {m["old_path"] for m in branch_map["moves"]}
        obligations = {n for n in obligations if n.split("::", 1)[0] not in moved}
    if not obligations or not obligations.issubset(nodes):
        raise DocumentationGap("Historical documentation obligations missing")
    commands = value.get("commands", [])
    if (
        len(commands) != 6
        or any(not isinstance(c, list) or not c for c in commands)
        or value.get("command_exit_codes") != [0] * 6
    ):
        raise DocumentationGap("Incomplete documentation execution commands")
    expected = [
        [
            "website/tools/build_docs_site.py",
            "--product-source",
            product["commit"],
            "--documentation-source",
            commit,
        ],
        ["-m", "pytest", "-q", "website/tests", "--collect-only"],
        None,
        [
            "-m",
            "ruff",
            "check",
            "website/tools",
            "website/tests",
            *(["scripts"] if branch_map is not None else []),
        ],
        [
            "-m",
            "ruff",
            "format",
            "--check",
            "website/tools",
            "website/tests",
            *(["scripts"] if branch_map is not None else []),
        ],
        (
            [
                "@product/scripts/check_sqlite_validation_policy.py",
                "--root",
                "@web",
                "--scope",
                "documentation",
            ]
            if branch_map is not None
            else [
                "scripts/check_sqlite_validation_policy.py",
                "--scope",
                "documentation",
            ]
        ),
    ]
    for i in (0, 1, 3, 4, 5):
        if commands[i][1:] != expected[i]:
            raise DocumentationGap("Documentation execution scope changed")
    if (
        commands[2][1:5] != ["-m", "pytest", "-q", "website/tests"]
        or commands[2][5:-1] not in ([], ["-n", "2", "--dist", "worksteal"])
        or not commands[2][-1].startswith("--junitxml=")
        or Path(commands[2][-1].split("=", 1)[1]).name != "tests.xml"
    ):
        raise DocumentationGap("Documentation pytest obligation changed")
    return value, raw


def verify_provider(value, raw, directory, repository, root):
    """Bind hosted bytes to the successful Pages run and its private artifact."""
    if value.get("repository") != repository or not re.fullmatch(
        r"[^/]+/[^/]+", repository or ""
    ):
        raise DocumentationGap("Hosted repository identity mismatch")
    run, attempt = str(value.get("run_id", "")), str(value.get("run_attempt", ""))
    if not run.isdigit() or not attempt.isdigit():
        raise DocumentationGap("Hosted run/attempt identity missing")
    metadata = json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{repository}/actions/runs/{run}/attempts/{attempt}"],
            stderr=subprocess.PIPE,
        )
    )
    if (
        metadata.get("status") != "completed"
        or metadata.get("conclusion") != "success"
        or metadata.get("path") != ".github/workflows/pages.yml"
        or metadata.get("head_sha") != value.get("feature_sha")
    ):
        raise DocumentationGap(
            "Hosted documentation provider did not succeed at selected source"
        )
    doc_commit = value["inputs"]["documentation_source"]["commit"]
    if doc_commit != value["feature_sha"]:
        parents = git(root, "show", "-s", "--format=%P", doc_commit).decode().split()
        if len(parents) != 2 or parents[1] != value["feature_sha"]:
            raise DocumentationGap("Hosted effective documentation source mismatch")
    with tempfile.TemporaryDirectory(prefix="documentation-provider-") as temp:
        subprocess.run(
            [
                "gh",
                "run",
                "download",
                run,
                "--repo",
                repository,
                "--name",
                f"documentation-verification-{run}-{attempt}",
                "--dir",
                temp,
            ],
            check=True,
            capture_output=True,
        )
        found = [
            p
            for p in Path(temp).rglob("documentation-receipt.json")
            if not p.is_symlink() and p.read_bytes() == raw
        ]
        if len(found) != 1:
            raise DocumentationGap("Hosted receipt bytes absent from provider artifact")
        for name, digest in value["artifact_sha256"].items():
            item = found[0].parent / name
            if (
                item.is_symlink()
                or not item.is_file()
                or sha(item.read_bytes()) != digest
            ):
                raise DocumentationGap("Hosted provider artifact content mismatch")


def complete_documentation(
    local,
    hosted,
    product,
    ir_hash,
    root,
    repository,
    provider_check=None,
    product_nodes=None,
):
    """Return a verified conjunction; any missing or denied evidence stays a gap."""
    try:
        if not local or not hosted:
            raise DocumentationGap(
                "Independent local and hosted documentation evidence required"
            )
        verify_moved_product_obligations(
            web_branch_map(root, product["commit"]), product_nodes
        )
        a, _ = checked_receipt(local, "local", product, ir_hash, root)
        b, raw = checked_receipt(hosted, "hosted", product, ir_hash, root)
        if (
            a["inputs"]["documentation_source"] != b["inputs"]["documentation_source"]
            or a["test_ids"] != b["test_ids"]
        ):
            raise DocumentationGap(
                "Independent documentation source/node obligations differ"
            )
        (provider_check or verify_provider)(
            b, raw, Path(hosted).parent, repository, root
        )
        return {
            "status": "verified",
            "documentation_source": a["inputs"]["documentation_source"],
            "neutral_ir_sha256": ir_hash,
            "nodes": len(a["test_ids"]),
        }
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ET.ParseError,
        subprocess.SubprocessError,
    ) as exc:
        return {"status": "not_verified", "reason": str(exc)}
