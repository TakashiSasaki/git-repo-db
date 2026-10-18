"""Check Access requirement/test links; receipts do not establish independent review.

Optional JUnit and collection files are paired to reject failed, skipped, missing,
substituted or duplicate test nodes. This checks evidence consistency, not its origin
or semantic completeness. Partial/deferred requirements stay explicitly incomplete.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = "docs/implementation/access-a6-acceptance.json"


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def path_in(root, relative):
    require(isinstance(relative, str), "path must be text")
    value = Path(relative)
    require(not value.is_absolute() and ".." not in value.parts, "unsafe path")
    target = (root / value).resolve()
    require(
        target.is_relative_to(root.resolve()) and target.is_file(), "missing source"
    )
    return target


def statements(text):
    try:
        section = text.split(
            "## 9. Required counterexamples (not executed tests)\n", 1
        )[1]
        section = section.split("\n## 10.", 1)[0]
    except IndexError:
        raise AuditError("requirement section absent") from None
    pairs = re.findall(r"(?ms)^(\d+)\. (.*?)(?=^\d+\. |\Z)", section)
    require(len(pairs) == 26, "expected exactly 26 requirements")
    result = {int(number): " ".join(value.split()) for number, value in pairs}
    require(set(result) == set(range(1, 27)), "requirement IDs differ")
    return result


def test_reference(root, value):
    require(isinstance(value, str) and value.count("::") == 1, "invalid test reference")
    path, function = value.split("::")
    require(path.startswith("tests/") and path.endswith(".py"), "not a test source")
    tree = ast.parse(path_in(root, path).read_text())
    names = {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    require(
        function.startswith("test_") and function in names,
        "test function absent: " + value,
    )


def junit_nodes(root, filename):
    document = ET.parse(filename)
    nodes = []
    for case in document.findall(".//testcase"):
        require(
            not any(
                case.find(tag) is not None for tag in ("failure", "error", "skipped")
            ),
            "receipt contains failed/error/skipped node",
        )
        classname, name = case.get("classname", ""), case.get("name", "")
        parts = classname.split(".")
        for length in range(len(parts), 0, -1):
            candidate = "/".join(parts[:length]) + ".py"
            if (root / candidate).is_file():
                node = candidate + "::" + "::".join([*parts[length:], name])
                nodes.append(node)
                break
        else:
            raise AuditError("receipt module does not exist: " + classname)
    require(nodes, "receipt has no tests")
    require(len(nodes) == len(set(nodes)), "receipt contains duplicate nodes")
    return nodes


def audit(root, ledger, junit=None, collection=None):
    require(
        ledger.get("format") == "git-repo-db/access-acceptance-v1", "unknown ledger"
    )
    expected = statements(path_in(root, ledger["requirements_file"]).read_text())
    rows = ledger.get("requirements", [])
    require(
        len(rows) == 26 and {r.get("id") for r in rows} == set(expected),
        "ledger IDs differ",
    )
    references = set()
    counts = Counter()
    for row in rows:
        require(row["requirement"] == expected[row["id"]], "requirement text drift")
        require(
            row.get("status") in {"covered", "partial", "deferred"}, "unknown status"
        )
        require(bool(row.get("verified_scope")), "missing scope statement")
        require(isinstance(row.get("gaps"), list), "missing gap list")
        if row["status"] != "covered":
            require(bool(row["gaps"]), "incomplete item lacks a gap")
        else:
            require(not row["gaps"], "covered item has unresolved gap")
        require(isinstance(row.get("tests"), list), "missing test references")
        require(len(row["tests"]) == len(set(row["tests"])), "duplicate test reference")
        require(
            row["status"] == "deferred" or row["tests"],
            "covered/partial item lacks tests",
        )
        for reference in row["tests"]:
            test_reference(root, reference)
            references.add(reference)
        counts[row["status"]] += 1
    # This ledger cannot certify reviewer independence or grant merge authority.
    require(
        ledger.get("gates")
        == {
            "independent_review": "pending",
            "adr_whole_replacement": "pending",
            "merge_authorization": "not_requested",
            "p8_activation": "not_requested",
        },
        "gate change requires separately reviewed evidence",
    )
    require(
        (junit is None) == (collection is None),
        "JUnit and collection must be supplied together",
    )
    executed = None
    if junit is not None:
        nodes = junit_nodes(root, junit)
        collected = [
            line.strip()
            for line in Path(collection).read_text().splitlines()
            if line.startswith("tests/") and "::" in line
        ]
        require(
            collected and len(collected) == len(set(collected)),
            "invalid/duplicate collected nodes",
        )
        require(Counter(collected) == Counter(nodes), "collection and execution differ")
        observed = {node.split("[", 1)[0] for node in nodes}
        require(references <= observed, "referenced tests were not executed")
        executed = len(nodes)
    return {
        "format": ledger["format"],
        "requirement_counts": dict(sorted(counts.items())),
        "unique_test_references": len(references),
        "executed_nodes": executed,
        "node_set_matched": executed is not None,
        "incomplete_requirements": [r["id"] for r in rows if r["status"] != "covered"],
        "gates": ledger["gates"],
        "meaning": "reference/evidence consistency only; not independent or release acceptance",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--collection", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit(
            ROOT, json.loads((ROOT / LEDGER).read_text()), args.junit, args.collection
        )
    except (
        AuditError,
        KeyError,
        TypeError,
        OSError,
        ET.ParseError,
        json.JSONDecodeError,
    ) as error:
        raise SystemExit("Access acceptance audit failed: " + str(error)) from None
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")


if __name__ == "__main__":
    main()
