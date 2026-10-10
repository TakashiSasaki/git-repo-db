"""Resolve exact baseline ordinary test nodes to active collected counterparts.

Both node lists must come from real pytest collection. This validates node
existence and disposition completeness; it does not claim tests were executed
or independently prove that every surviving assertion is sufficient.
"""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def function_node(node):
    return node.split("[", 1)[0]


def read_nodes(path):
    nodes = path.read_text().splitlines()
    if not nodes or any(
        not node.startswith("tests/") or "::" not in node for node in nodes
    ):
        raise ValueError(f"Expected pytest node IDs only: {path}")
    if len(nodes) != len(set(nodes)):
        raise ValueError(f"Duplicate pytest node IDs: {path}")
    return nodes


def resolve(baseline_path, current_path, disposition_path, schema_path):
    baseline, current = read_nodes(baseline_path), read_nodes(current_path)
    current_set = set(current)
    current_functions = {}
    for node in current:
        current_functions.setdefault(function_node(node), []).append(node)
    disposition = json.loads(disposition_path.read_text())
    schema = json.loads(schema_path.read_text())
    explicit, functions = {}, {}
    for item in schema["node_replacements"]:
        group = schema["replacement_groups"][item["replacement_group"]]
        explicit[item["old_node"]] = {
            **group,
            "source": "schema_contract_rewrites",
        }
    for item in disposition["exchange_contract_rewrites"]["entries"]:
        explicit[item["baseline_node"]] = {
            **item,
            "source": "exchange_contract_rewrites",
        }
    for item in disposition["mechanism_only_retirements"]:
        functions[item["retired_node"]] = {
            **item,
            "source": "mechanism_only_retirements",
        }
    for section in (
        "acquisition_contract_rewrites",
        "other_contract_rewrites",
    ):
        for item in disposition.get(section, {}).get("mappings", []):
            functions[item["retired_node"]] = {**item, "source": section}

    git_path = disposition.get("git_contract_rewrites", {}).get("artifact")
    if git_path:
        git = json.loads((ROOT / git_path).read_text())
        for item in git["mappings"]:
            explicit[item["old_node"]] = {
                "replacement_nodes": item["replacement_nodes"],
                "surviving_assertion": " ".join(item["retained_assertions"]),
                "reason": " ".join(item["retired_assertions"]) or None,
                "source": "git_contract_rewrites",
            }

    entries, retained, missing, invalid = [], [], [], []
    for old in baseline:
        item = explicit.get(old) or functions.get(function_node(old))
        if item is None:
            if old in current_set:
                retained.append(old)
                continue
            missing.append(old)
            continue
        if old in explicit:
            targets = item["replacement_nodes"]
        else:
            targets = []
            for target in item["replacement_nodes"]:
                if "[" in target:
                    choices = [target] if target in current_set else []
                else:
                    choices = current_functions.get(target, [])
                    suffix = old[len(function_node(old)) :]
                    # Retain the exact existing parameter where it survives.
                    corresponding = target + suffix
                    if suffix and corresponding in choices:
                        choices = [corresponding]
                    else:
                        renamed_suffix = suffix.replace(
                            "unpublished", "incomplete"
                        ).replace("published", "complete")
                        corresponding = target + renamed_suffix
                        if renamed_suffix and corresponding in choices:
                            choices = [corresponding]
                targets.extend(choices)
            targets = list(dict.fromkeys(targets))
        if not targets:
            missing.append(old)
            continue
        invalid.extend(target for target in targets if target not in current_set)
        reason = item.get("surviving_assertion") or item.get("reason")
        if not reason:
            raise ValueError(f"No concrete disposition rationale: {old}")
        entries.append(
            {
                "baseline_node": old,
                "replacement_nodes": targets,
                "disposition_source": item["source"],
                "surviving_assertion": reason,
                "retired_mechanism_reason": item.get("reason"),
            }
        )
    if missing or invalid:
        raise ValueError(
            json.dumps(
                {
                    "unmapped_baseline_nodes": missing,
                    "uncollected_replacement_nodes": sorted(set(invalid)),
                },
                indent=2,
            )
        )
    removed_functions = {
        function_node(old)
        for old in baseline
        if function_node(old) not in current_functions
    }
    mapped_functions = {function_node(item["baseline_node"]) for item in entries}
    if not removed_functions <= mapped_functions:
        raise ValueError("Removed baseline function has no exact node disposition")
    return {
        "status": "all baseline nodes accounted for; collection proof only",
        "baseline_sha": disposition["baseline"]["sha"],
        "selection": disposition["baseline"]["selection"],
        "baseline_collected_count": len(baseline),
        "current_collected_count": len(current),
        "mapped_baseline_node_count": len(entries),
        "still_collected_same_node_count": len(retained),
        "removed_or_renamed_baseline_function_count": len(removed_functions),
        "removed_or_renamed_baseline_functions": sorted(removed_functions),
        "node_list_sha256": {
            "baseline": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
            "current": hashlib.sha256(current_path.read_bytes()).hexdigest(),
        },
        "limitations": "Exact counterpart existence and explicit rationales are checked. Still-collected names do not imply unchanged implementation. Full execution, assertion sufficiency and fresh independent review remain separate acceptance requirements.",
        "entries": entries,
        "still_collected_same_nodes": retained,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=ROOT
        / "artifacts/publication-free/baseline-ordinary-collected-nodes.txt",
    )
    parser.add_argument(
        "--current",
        type=Path,
        default=ROOT / "artifacts/publication-free/ordinary-collected-latest.txt",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tests/support/publication_free_node_dispositions.json",
    )
    args = parser.parse_args()
    report = resolve(
        args.baseline,
        args.current,
        ROOT / "docs/phase2/publication-free-test-disposition.json",
        ROOT / "tests/support/schema20_contract_replacements.json",
    )
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        f"{report['baseline_collected_count']} baseline nodes accounted for; "
        f"{report['mapped_baseline_node_count']} explicit mappings; "
        f"{report['current_collected_count']} current nodes collected; no execution claim"
    )


if __name__ == "__main__":
    main()
