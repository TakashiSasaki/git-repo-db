"""Bounded disposable-instance projection, not a general retained-DB validator."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef

M = Namespace("urn:git-repo-db:instance-pilot:v1:")
HERE = Path(__file__).resolve().parent


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def value(cell):
    kind = cell["type"]
    if kind == "blob":
        data = base64.b64decode(cell["base64"], validate=True)
        if (
            len(data) != cell["length"]
            or base64.b64encode(data).decode() != cell["base64"]
        ):
            raise ValueError("invalid BLOB encoding")
        return data
    result = cell["value"]
    if not (
        (kind == "null" and result is None)
        or (kind == "integer" and type(result) is int)
        or (kind == "text" and type(result) is str)
    ):
        raise ValueError("invalid SQLite value representation")
    return result


def project(data):
    if data["version"] != 1:
        raise ValueError("unsupported fixture version")
    actual = {s: {t: len(r) for t, r in ts.items()} for s, ts in data["tables"].items()}
    if actual != data["expected_counts"]:
        raise ValueError("source occurrence coverage mismatch")
    # This pilot has a fixed fixture contract, independently of graph targets.
    required = {
        "filesystem": {"catalog_metadata", "scans", "entries", "scan_outcomes"},
        "worktrees": {
            "catalog_identity",
            "observations",
            "worktrees",
            "scan_references",
            "repository_links",
        },
    }
    if {s: set(ts) for s, ts in data["tables"].items()} != required:
        raise ValueError("required table coverage missing")
    if not all(
        actual[s][t] > 0
        for s, t in (
            ("filesystem", "scans"),
            ("filesystem", "entries"),
            ("worktrees", "worktrees"),
            ("worktrees", "scan_references"),
        )
    ):
        raise ValueError("required fixture targets empty")
    g = Graph()
    source = digest(canonical(data).encode())
    nodes = {}
    decoded = {}
    for store, tables in data["tables"].items():
        for table, rows in tables.items():
            for index, row in enumerate(rows):
                node = URIRef(f"{M}{source}/{store}/{table}/{index}")
                nodes[store, table, index] = node
                decoded[store, table, index] = {k: value(v) for k, v in row.items()}
                g.add((node, RDF.type, M.RowOccurrence))
                g.add((node, M.record, Literal(canonical(row))))
                g.add((node, M.table, Literal(store + "." + table)))
    scan_nodes = {}
    worktrees = {}
    for (store, table, index), row in decoded.items():
        node = nodes[store, table, index]
        if store == "filesystem" and table == "scans":
            key = (row["namespace_uuid"], row["scan_uuid"])
            if key in scan_nodes:
                raise ValueError("duplicate scan key in input")
            scan_nodes[key] = node
            g.add((node, RDF.type, M.Scan))
        if store == "worktrees" and table == "worktrees":
            key = (row["observation_uuid"], row["root_path"])
            if key in worktrees:
                raise ValueError("duplicate worktree key in input")
            worktrees[key] = node
            g.add((node, RDF.type, M.Worktree))
    for (store, table, index), row in decoded.items():
        node = nodes[store, table, index]
        if store == "filesystem" and table in ("entries", "scan_outcomes"):
            parent = scan_nodes.get((row["namespace_uuid"], row["scan_uuid"]))
            cls = M.Entry if table == "entries" else M.Outcome
            g.add((node, RDF.type, cls))
            if parent is not None:
                g.add((node, M.parent, parent))
            if table == "scan_outcomes" and parent is not None:
                g.add((parent, M.outcome, node))
            if table == "entries":
                path = row["relative_path"]
                if not isinstance(path, bytes):
                    raise ValueError("path must remain BLOB")
                g.add(
                    (
                        node,
                        M.pathBytes,
                        Literal(
                            base64.b64encode(path).decode(), datatype=XSD.base64Binary
                        ),
                    )
                )
                g.add(
                    (
                        node,
                        M.semanticKey,
                        Literal(
                            canonical(
                                [row["namespace_uuid"], row["scan_uuid"], path.hex()]
                            )
                        ),
                    )
                )
                for field in ("mtime_ns", "birthtime_ns", "ctime_ns"):
                    raw = row[field]
                    if raw is not None:
                        if type(raw) is not str or str(int(raw)) != raw:
                            raise ValueError("invalid native timestamp lexeme")
                        g.add(
                            (node, M[field], Literal(raw))
                        )  # exact decimal TEXT, not long/float
                    else:
                        g.add((node, M[field], M.SqlNull))
        if store == "worktrees" and table == "scan_references":
            for field, version in (
                ("filesystem_namespace_uuid", 4),
                ("filesystem_scan_uuid", 7),
            ):
                raw = row[field]
                if str(UUID(raw)) != raw or UUID(raw).version != version:
                    raise ValueError("invalid qualified reference UUID")
            g.add((node, RDF.type, M.ExternalReference))
            g.add((node, M.resolution, Literal("unresolved")))
            parent = worktrees.get((row["observation_uuid"], row["root_path"]))
            if parent is not None:
                g.add((node, M.worktree, parent))
    if len(set(g.subjects(RDF.type, M.RowOccurrence))) != sum(
        sum(ts.values()) for ts in actual.values()
    ):
        raise ValueError("projected occurrence coverage mismatch")
    return g


def validate(data, output, timeout=30):
    output.mkdir(parents=True, exist_ok=True)
    families = {
        name: {"status": "not_run"}
        for name in (
            "data_conformance",
            "spec_satisfiability",
            "operation_invariants",
            "implementation_conformance",
        )
    }
    result = {
        "scope": "fixed disposable FS/WT pilot; no external target resolution",
        "families": families,
        "input_sha256": digest(canonical(data).encode()),
        "source_commit": data.get("source_commit"),
        "source_tree": data.get("source_tree"),
        "engine_evaluation_count": None,
        "expected_counts": data.get("expected_counts"),
        "tool_sha256": digest(Path(__file__).read_bytes()),
        "shapes_sha256": digest((HERE / "instance_shapes.ttl").read_bytes()),
        "lock_sha256": digest((HERE / "uv.lock").read_bytes()),
    }
    try:
        shape_bytes = (HERE / "instance_shapes.ttl").read_bytes()
        manifest = json.loads((HERE / "instance_constraints.json").read_text())
        if digest(shape_bytes) != manifest["shapes_sha256"]:
            raise ValueError("pinned pilot shape closure mismatch")
        g = project(data)
        result["constraint_targets"] = {
            shape: {
                "selected": len(set(g.subjects(RDF.type, cls))),
                "coverage": "not_applicable"
                if not set(g.subjects(RDF.type, cls))
                else "selected",
                "engine_evaluation_count": None,
            }
            for shape, cls in (
                ("EntryShape", M.Entry),
                ("ScanShape", M.Scan),
                ("OutcomeShape", M.Outcome),
                ("ReferenceShape", M.ExternalReference),
            )
        }
        result["checker_invocations_completed"] = 0
        nt = "\n".join(sorted(g.serialize(format="nt").splitlines())) + "\n"
        (output / "data.nt").write_text(nt)
        result["graph_sha256"] = digest(nt.encode())
        checked = subprocess.run(
            [
                sys.executable,
                str(HERE / "worker.py"),
                str(output / "data.nt"),
                str(HERE / "instance_shapes.ttl"),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        report = json.loads(checked.stdout)
        result["checker_invocations_completed"] = 1
        result["engine"] = report["engine"]
        families["data_conformance"] = {
            "status": report["status"],
            "scope": "Entry/Scan/Outcome/ExternalReference pilot shapes",
        }
        (output / "engine.json").write_text(json.dumps(report, indent=2))
    except (
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        OSError,
    ) as exc:
        families["data_conformance"] = {"status": "undetermined", "reason": str(exc)}
    (output / "result.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    receipt = validate(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2]))
    print(json.dumps(receipt, indent=2))
    sys.exit(
        {"pass": 0, "fail": 1, "undetermined": 2}[
            receipt["families"]["data_conformance"]["status"]
        ]
    )
