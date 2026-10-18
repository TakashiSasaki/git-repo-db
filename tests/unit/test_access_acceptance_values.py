"""Consistency checks for the A6 ledger, not proof of independent acceptance."""

import copy
import json
import xml.etree.ElementTree as ET

import pytest

from scripts.audit_access_acceptance import LEDGER, ROOT, AuditError, audit


@pytest.fixture
def ledger():
    return json.loads((ROOT / LEDGER).read_text())


def receipts(ledger, tmp_path):
    refs = sorted({ref for r in ledger["requirements"] for ref in r["tests"]})
    suite = ET.Element("testsuite")
    for ref in refs:
        path, name = ref.split("::")
        ET.SubElement(
            suite, "testcase", classname=path[:-3].replace("/", "."), name=name
        )
    junit = tmp_path / "tests.xml"
    ET.ElementTree(suite).write(junit)
    collection = tmp_path / "collection.txt"
    collection.write_text("\n".join(refs) + "\n\n42 tests collected\n")
    return junit, collection


def test_ledger_has_scoped_coverage_and_explicit_remaining_gates(ledger):
    result = audit(ROOT, ledger)
    assert result["requirement_counts"] == {"covered": 24, "partial": 1, "deferred": 1}
    assert result["incomplete_requirements"] == [11, 15]
    assert result["executed_nodes"] is None and not result["node_set_matched"]


@pytest.mark.parametrize(
    "damage", ["missing", "duplicate", "text", "test", "gap", "path", "gate"]
)
def test_inconsistent_ledger_is_rejected(ledger, damage):
    value = copy.deepcopy(ledger)
    if damage == "missing":
        value["requirements"].pop()
    elif damage == "duplicate":
        value["requirements"][-1] = value["requirements"][0]
    elif damage == "text":
        value["requirements"][0]["requirement"] += " altered"
    elif damage == "test":
        value["requirements"][0]["tests"] = [
            "tests/integration/access/test_registry.py::test_invented"
        ]
    elif damage == "gap":
        value["requirements"][10]["gaps"] = []
    elif damage == "path":
        value["requirements_file"] = "../outside.md"
    else:
        value["gates"]["independent_review"] = "passed"
    with pytest.raises(AuditError):
        audit(ROOT, value)


def test_receipt_and_collection_consistency(ledger, tmp_path):
    junit, collection = receipts(ledger, tmp_path)
    result = audit(ROOT, ledger, junit, collection)
    assert result["node_set_matched"]
    assert result["executed_nodes"] == result["unique_test_references"]


@pytest.mark.parametrize(
    "damage",
    ["failure", "error", "skipped", "missing", "duplicate", "substituted", "module"],
)
def test_receipt_cannot_hide_execution_gaps(ledger, tmp_path, damage):
    junit, collection = receipts(ledger, tmp_path)
    tree = ET.parse(junit)
    root = tree.getroot()
    if damage in ("failure", "error", "skipped"):
        ET.SubElement(root[0], damage)
    elif damage == "missing":
        root.remove(root[0])
    elif damage == "duplicate":
        root.append(copy.deepcopy(root[0]))
    elif damage == "substituted":
        root[0].set("name", "test_another_case")
    else:
        root[0].set("classname", "tests.invented")
    tree.write(junit)
    with pytest.raises(AuditError):
        audit(ROOT, ledger, junit, collection)


def test_partial_evidence_arguments_are_rejected(ledger, tmp_path):
    junit, _ = receipts(ledger, tmp_path)
    with pytest.raises(AuditError):
        audit(ROOT, ledger, junit=junit)
