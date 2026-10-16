"""Read exact Git objects; never execute reviewed code or change remote state."""

import collections
import gzip
import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parent
MAIN = "b86c46761ec0c3f3843a19edd4f3e106ef5ef58c"
P87 = "c058af3a1be9ba3e9a1b0ba649c789f5bdcd1d75"
P88 = "e956cd50b1f25bd95427301cced4741bb68e24f8"
P89 = "660178ff1a881e4482b7a3cde02b51dc50cf2603"
TESTED = "178ddbaa8fa06f52aff4993730205c5a38da91f4"
EVIDENCE = "docs/implementation/evidence/p7-hardening-20261016/final/"


def git(*args, input=None):
    return subprocess.check_output(["git", *args], input=input)


def blob(ref, path):
    return git("show", f"{ref}:{path}")


def j(ref, path):
    return json.loads(blob(ref, path))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2) + "\n")


def junit_key(node):
    parts = node.split("::")
    classname = parts[0][:-3].replace("/", ".")
    if len(parts) > 2:
        classname += "." + ".".join(parts[1:-1])
    return classname, parts[-1]


def run():
    inputs = j(P88, EVIDENCE + "independent/d/executable-inputs.json")
    for item in inputs:
        assert sha(blob(P88, item["path"])) == item["sha256"]
        assert blob(P88, item["path"]) == blob(TESTED, item["path"])
    changed = git("diff", "--name-only", TESTED, P88).decode().splitlines()
    assert all(
        p.startswith(("docs/implementation/evidence/", ".agents/skills/"))
        for p in changed
    )
    artifacts = j(P88, EVIDENCE + "artifact-index.json")
    for item in artifacts:
        data = blob(P88, EVIDENCE + item["stored_path"])
        assert sha(data) == item["stored_sha256"], item
        original = gzip.decompress(data) if item["gzip"] else data
        assert len(original) == item["original_bytes"], item
        assert sha(original) == item["original_sha256"], item
    pubpath = "docs/implementation/evidence/pages-ci/2026-10-16-independent-review/"
    pub = j(P89, pubpath + "publication-inputs.json")
    for item in pub["files"]:
        data = blob(P89, item["path"])
        assert len(data) == item["bytes"] and sha(data) == item["sha256"], item
    pubchanged = (
        git("diff", "--name-only", pub["tested_commit"], P89).decode().splitlines()
    )
    assert all(p.startswith(pubpath) for p in pubchanged)
    pages = blob(P89, ".github/workflows/pages.yml").decode()
    # Compare both trigger lists with all recorded publication inputs. Workflow
    # includes further validators/tests not all present in the content manifest.
    triggers = re.findall(r"      - '([^']+)'", pages)
    middle = len(triggers) // 2
    assert triggers[:middle] == triggers[middle:]
    import fnmatch

    uncovered = [
        i["path"]
        for i in pub["files"]
        if not any(fnmatch.fnmatchcase(i["path"], p) for p in triggers[:middle])
    ]
    assert not uncovered, uncovered
    assert git("merge-base", MAIN, P87).decode().strip() == MAIN
    assert git("merge-base", P87, P88).decode().strip() == P87
    assert git("merge-base", MAIN, P89).decode().strip() == MAIN
    production = (
        git("diff", "--name-only", MAIN, P88, "--", "src").decode().splitlines()
    )
    allowed = {
        "src/repo_catalog/adapters/sqlite/recovery.py",
        "src/repo_catalog/adapters/sqlite/recovery_budget.py",
        "src/repo_catalog/adapters/sqlite/recovery_validation.py",
        "src/repo_catalog/application/recovery.py",
        "src/repo_catalog/domain/git_native.py",
        "src/repo_catalog/domain/ports/recovery.py",
        "src/repo_catalog/domain/recovery.py",
    }
    assert set(production) == allowed
    # Physical baseline DDL, core/operational/search stores and default entry
    # points are byte-identical. All changed existing runtime code is isolated
    # git_native.py; its import callers belong to opt-in P1-P7.
    baseline = [
        "src/repo_catalog/adapters/sqlite/store.py",
        "src/repo_catalog/adapters/sqlite/schema.py",
    ]
    baseline += (
        git(
            "ls-tree",
            "-r",
            "--name-only",
            MAIN,
            "src/repo_catalog/resources",
            "src/repo_catalog/cli",
        )
        .decode()
        .splitlines()
    )
    for path in baseline:
        assert blob(MAIN, path) == blob(P88, path), path
    # Sequential local synthetic merge commits preserve real two-parent ancestry.
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Readiness simulation",
        GIT_AUTHOR_EMAIL="simulation@example.invalid",
        GIT_COMMITTER_NAME="Readiness simulation",
        GIT_COMMITTER_EMAIL="simulation@example.invalid",
        GIT_AUTHOR_DATE="2026-10-16T18:00:00Z",
        GIT_COMMITTER_DATE="2026-10-16T18:00:00Z",
    )
    merges = []
    parent = MAIN
    for number, head in ((89, P89), (87, P87), (88, P88)):
        tree = git("merge-tree", "--write-tree", parent, head).decode().strip()
        commit = (
            subprocess.check_output(
                ["git", "commit-tree", tree, "-p", parent, "-p", head],
                input=f"Local nonremote simulation #{number}\n".encode(),
                env=env,
            )
            .decode()
            .strip()
        )
        merges.append(
            {
                "pr": number,
                "first_parent": parent,
                "second_parent": head,
                "merge_base": git("merge-base", parent, head).decode().strip(),
                "tree": tree,
                "synthetic_commit": commit,
                "conflicts": False,
            }
        )
        parent = commit
    # Actual merge SHA depends on metadata, but tree and parent order are fixed.
    changed_to_final = git("diff", "--name-only", P88, parent).decode().splitlines()
    p89changes = git("diff", "--name-only", MAIN, P89).decode().splitlines()
    assert set(changed_to_final) == set(p89changes)
    # JUnit/journal identities for both installed distributions are rechecked.
    installed = {}
    for variant in ("wheel", "sdist-wheel"):
        prefix = EVIDENCE + "independent/d/" + variant
        xml = ET.fromstring(gzip.decompress(blob(P88, prefix + "-junit.xml.gz")))
        cases = list(xml.iter("testcase"))
        assert len(cases) == 255
        assert not any(
            c.find(t) is not None
            for c in cases
            for t in ("failure", "error", "skipped")
        )
        records = [
            json.loads(line)
            for line in gzip.decompress(
                blob(P88, prefix + "-journal.jsonl.gz")
            ).splitlines()
        ]
        starts = [r["nodeid"] for r in records if r["event"] == "start"]
        collected = [
            line.strip()
            for line in gzip.decompress(blob(P88, prefix + "-collect.log.gz"))
            .decode()
            .splitlines()
            if line.startswith("tests/") and "::" in line
        ]
        assert len(collected) == len(set(collected)) == 255
        assert set(starts) == set(collected)
        xml_keys = [(c.attrib["classname"], c.attrib["name"]) for c in cases]
        assert len(xml_keys) == len(set(xml_keys)) == 255
        assert set(xml_keys) == {junit_key(node) for node in collected}
        phases = [r for r in records if r["event"] == "phase"]
        assert len(starts) == len(set(starts)) == 255
        assert len(phases) == 765 and all(r["outcome"] == "passed" for r in phases)
        assert collections.Counter((r["nodeid"], r["phase"]) for r in phases) == {
            (node, phase): 1
            for node in collected
            for phase in ("setup", "call", "teardown")
        }
        finish = [r for r in records if r["event"] == "finish"]
        assert len(finish) == 1 and finish[0]["exitstatus"] == 0
        installed[variant] = {
            "junit_cases": len(cases),
            "journal_unique_starts": len(set(starts)),
            "passed_phases": len(phases),
            "exitstatus": 0,
            "identities_match_collection": True,
        }
    root_prefix = EVIDENCE + "executions/final-overlay-178ddba/"
    root_xml = ET.fromstring(gzip.decompress(blob(P88, root_prefix + "junit.xml.gz")))
    root_cases = list(root_xml.iter("testcase"))
    root_records = [
        json.loads(line)
        for line in gzip.decompress(
            blob(P88, root_prefix + "journal.jsonl.gz")
        ).splitlines()
    ]
    root_starts = [r["nodeid"] for r in root_records if r["event"] == "start"]
    collection = [
        line.strip()
        for line in gzip.decompress(blob(P88, root_prefix + "collect.log.gz"))
        .decode()
        .splitlines()
        if line.startswith("tests/") and "::" in line
    ]
    assert (
        len(root_cases)
        == len(root_starts)
        == len(set(root_starts))
        == len(collection)
        == 3748
    )
    assert set(collection) == set(root_starts)

    assert {(c.attrib["classname"], c.attrib["name"]) for c in root_cases} == {
        junit_key(node) for node in collection
    }
    root_counts = collections.Counter(
        next(
            (
                tag
                for tag in ("failure", "error", "skipped")
                if case.find(tag) is not None
            ),
            "passed",
        )
        for case in root_cases
    )
    assert root_counts == {"passed": 3517, "failure": 229, "error": 2}
    root_phases = [r for r in root_records if r["event"] == "phase"]
    assert len(root_phases) == 11242
    root_finish = [r for r in root_records if r["event"] == "finish"]
    assert len(root_finish) == 1 and root_finish[0]["exitstatus"] == 1
    # Broad evidence disclosure scan prints paths/pattern names only. A match
    # requires human review; ordinary paths/UUIDs and fixture secrets are not
    # authentic credentials. No private payload value is emitted.
    evidence_paths = [
        p
        for p in git("diff", "--name-only", P87, P88).decode().splitlines()
        if p.startswith("docs/implementation/evidence/")
    ]
    patterns = {
        "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "github_token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b",
        "aws_access_key": rb"\bAKIA[A-Z0-9]{16}\b",
    }
    hits = []
    extensions = collections.Counter()
    for p in evidence_paths:
        data = blob(P88, p)
        extensions[Path(p).suffix] += 1
        if p.endswith(".gz"):
            data = gzip.decompress(data)
        for label, pattern in patterns.items():
            if re.search(pattern, data):
                hits.append({"path": p, "pattern": label})
    assert not hits, hits
    write(
        "verification.json",
        {
            "main": MAIN,
            "pr87": P87,
            "pr88": P88,
            "pr89": P89,
            "tested_source": TESTED,
            "executable_inputs_verified": len(inputs),
            "transport_artifacts_verified": len(artifacts),
            "publication_inputs_verified": len(pub["files"]),
            "publication_uncovered": uncovered,
            "followup_paths": changed,
            "baseline_files_byte_identical": baseline,
            "production_changes": production,
            "installed": installed,
            "root_full_run": {
                "junit_cases": len(root_cases),
                "journal_unique_starts": len(set(root_starts)),
                "phase_records": len(root_phases),
                "counts": dict(root_counts),
                "exitstatus": 1,
                "identities_match_collection": True,
            },
            "evidence_scan": {
                "paths": len(evidence_paths),
                "suffix_counts": dict(extensions),
                "credential_pattern_hits": hits,
                "limits": "Pattern scan plus scope review; no guarantee of every possible secret pattern. Synthetic evidence contains UUIDs, temp paths, process/environment logs; no catalog/archive binary is committed.",
            },
        },
    )
    write(
        "merge-simulation.json",
        {
            "base": MAIN,
            "strategy": "merge commits; preserve first parent main and feature second parent",
            "steps": merges,
            "final_vs_pr88_paths": changed_to_final,
            "limits": "Local objects only; no refs, branches or remote merges changed. Synthetic commit IDs are not predicted GitHub merge IDs.",
        },
    )
    print(
        json.dumps(
            {
                "inputs": len(inputs),
                "artifacts": len(artifacts),
                "publication_inputs": len(pub["files"]),
                "merge_trees": [s["tree"] for s in merges],
                "installed": installed,
            }
        )
    )


if __name__ == "__main__":
    run()
