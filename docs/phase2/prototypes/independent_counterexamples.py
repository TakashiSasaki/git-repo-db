"""Independent attacks on the deliberately narrow collection prototype.

This reader builds only in-memory synthetic catalogs. It does not claim the
prototype is an implemented core or that omitted domain policies are decided.
Run with --prototype-dir pointing at the directory containing completeness.sql
and completeness_probe.py. Success means a documented limit was reproduced.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def load_probe(directory):
    path = directory / "completeness_probe.py"
    spec = importlib.util.spec_from_file_location("collection_proposal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same_identity_field_state(probe):
    digests = []
    for status in ("missing", "null", "value"):
        with probe.proposal_db() as db:
            probe.observation(
                db,
                "same-observation",
                title="" if status == "value" else None,
                status=status,
            )
            digests.append(probe.observation_digest(db, "same-observation").hex())
    assert len(set(digests)) == 3
    # Disprove the weaker comparison that differed in identity as well as state.
    # With an intentionally collapsed status it still claims distinct values.
    with probe.proposal_db() as db:
        probe.observation(db, "missing", title=None, status="null")
        probe.observation(db, "null", title=None, status="null")
        weak_pass = probe.observation_digest(db, "missing") != probe.observation_digest(
            db, "null"
        )
    assert weak_pass
    return {
        "same_identity_missing_null_empty_digests_distinct": True,
        "weak_different_identity_test_passes_with_collapsed_status": weak_pass,
    }


def wrong_member_family(probe):
    with probe.proposal_db() as db:
        probe.collection(db, "root")  # Its collection scope family is pr.
        probe.observation(db, "thread-in-pr-list", family="thread")
        probe.fragment(db, "root", 0, ["thread-in-pr-list"], terminal=True)
        probe.seal(db, "root")
        accepted = probe.valid_collection(db, "root")
    assert accepted
    return {
        "scope_family": "pr",
        "member_family": "thread",
        "narrow_prototype_accepts": accepted,
        "limit": "Generic keys do not prove typed collection-family compatibility.",
    }


def unbound_child_parent(probe):
    with probe.proposal_db() as db:
        probe.collection(db, "root")
        probe.observation(db, "thread-T1", family="thread", child=True)
        probe.fragment(db, "root", 0, ["thread-T1"], terminal=True)
        probe.seal(db, "root")
        # Child has the generic PR-list scope, not a typed T1-comment scope.
        probe.collection(db, "unrelated-pr-list")
        probe.fragment(db, "unrelated-pr-list", 0, [], terminal=True)
        probe.seal(db, "unrelated-pr-list")
        db.execute(
            "INSERT INTO p2_child_obligations VALUES('root',0,0,'unrelated-pr-list')"
        )
        accepted = probe.valid_collection(db, "root")
    assert accepted
    return {
        "parent_resource_key": "thread-T1",
        "child_scope_family": "pr",
        "narrow_prototype_accepts": accepted,
        "limit": "Owner equality does not prove the child's natural domain parent.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prototype-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    directory = args.prototype_dir.resolve()
    probe = load_probe(directory)
    report = {
        "kind": "independent-narrow-prototype-falsifiers-v1",
        "prototype_files_sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("completeness.sql", "completeness_probe.py")
        },
        "missing_null_empty": same_identity_field_state(probe),
        "wrong_member_family": wrong_member_family(probe),
        "unbound_child_parent": unbound_child_parent(probe),
        "limits": [
            "These findings concern the generic disposable fixture only.",
            "Integrated DDL must use typed collection and child keys or equivalent admission checks.",
            "No production defect or permanent policy is inferred from a deliberately omitted prototype contract.",
        ],
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
