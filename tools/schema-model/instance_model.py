"""Bounded disposable-instance projection, not a general retained-DB validator."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import hash_profile
import jsonschema
import outcome_profile
from model import FAMILIES, git
from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef

M = Namespace("urn:git-repo-db:instance-pilot:v1:")
HERE = Path(__file__).resolve().parent
RESULT_SCHEMA = HERE / "result.schema.json"
SCOPE = "disposable FS/WT representation and selected Filesystem outcome/hash constraints; no external target resolution or real-byte proof"
TARGETS = (
    ("EntryShape", M.Entry, "filesystem", "entries"),
    ("ScanShape", M.Scan, "filesystem", "scans"),
    ("OutcomeShape", M.Outcome, "filesystem", "scan_outcomes"),
    ("ReferenceShape", M.ExternalReference, "worktrees", "scan_references"),
)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


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
    if data.get("profile") == hash_profile.PROFILE:
        outcome_profile.check_coverage(
            data,
            decoded,
            profile=hash_profile.PROFILE,
            expected_counts=hash_profile.EXPECTED_FS_COUNTS,
        )
        hash_profile.check_coverage(data, decoded)
    else:
        outcome_profile.check_coverage(data, decoded)
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
            if table == "scan_outcomes":
                if parent is not None:
                    g.add((parent, M.outcome, node))
                if type(row["status"]) is not str:
                    raise ValueError("outcome status must be SQLite TEXT")
                g.add((node, M.status, Literal(row["status"])))
                for field, predicate in (
                    ("entry_count", M.entryCount),
                    ("error_count", M.errorCount),
                    ("finished_us", M.finishedUs),
                ):
                    if type(row[field]) is not int:
                        raise ValueError("outcome count/time must be SQLite INTEGER")
                    g.add((node, predicate, Literal(row[field], datatype=XSD.integer)))
            if table == "entries":
                for field, predicate in (
                    ("kind", M.kind),
                    ("hash_status", M.hashStatus),
                ):
                    if type(row[field]) is not str:
                        raise ValueError("entry kind/status must be SQLite TEXT")
                    g.add((node, predicate, Literal(row[field])))
                for field, predicate, expected, datatype in (
                    ("size", M.size, int, XSD.integer),
                    ("sha256", M.sha256, str, XSD.string),
                ):
                    raw = row[field]
                    if raw is not None and type(raw) is not expected:
                        raise ValueError("invalid SQLite size/digest type")
                    g.add(
                        (
                            node,
                            predicate,
                            M.SqlNull
                            if raw is None
                            else Literal(raw, datatype=datatype),
                        )
                    )
                error = row["error"]
                if error is not None and type(error) is not str:
                    raise ValueError("entry error must be SQLite TEXT or NULL")
                g.add(
                    (node, M.hasError, Literal(error is not None, datatype=XSD.boolean))
                )
                g.add((node, M.error, M.SqlNull if error is None else Literal(error)))
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


def new_result():
    """The common contract also permits honest, incomplete admission failures."""
    return {
        "schema_version": 1,
        "families": {
            name: {
                "status": "undetermined" if name == "data_conformance" else "not_run",
                "scope": SCOPE
                if name == "data_conformance"
                else "outside instance-pilot execution",
                "reason": "validation did not complete"
                if name == "data_conformance"
                else "not evaluated by the instance pilot",
            }
            for name in FAMILIES
        },
    }


def write_result(result, output):
    serialized = json.dumps(result, indent=2, allow_nan=False) + "\n"
    jsonschema.validate(result, json.loads(RESULT_SCHEMA.read_text()))
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(serialized)
    return result


def save_diagnostics(output, stdout, stderr):
    # TimeoutExpired may expose bytes even for subprocesses run with text=True.
    for name, raw in (("engine.stdout", stdout), ("engine.stderr", stderr)):
        if raw is not None:
            (output / name).write_bytes(raw.encode() if isinstance(raw, str) else raw)


def run_checker(output, timeout):
    """Preserve child bytes before interpreting a normalized conformance result."""
    try:
        checked = subprocess.run(
            [
                sys.executable,
                str(HERE / "worker.py"),
                str(output / "data.nt"),
                str(HERE / "instance_shapes.ttl"),
            ],
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        save_diagnostics(output, exc.stdout, exc.stderr)
        raise
    save_diagnostics(output, checked.stdout, checked.stderr)
    return checked


def validate(data, output, timeout=30):
    output.mkdir(parents=True, exist_ok=True)
    result = new_result()
    result["checker_invocations_completed"] = 0
    result["engine_evaluation_count"] = None
    stage = "input admission"
    try:
        timeout = float(timeout)
        if not math.isfinite(timeout) or not 0 < timeout <= 600:
            raise ValueError("timeout must be in (0,600] seconds")
        if not isinstance(data, dict):
            raise ValueError("instance input must be a JSON object")
        # Reject non-JSON programmatic values before echoing any producer claims.
        raw_input = (canonical(data) + "\n").encode()
        # Preserve available producer claims without inventing missing identities.
        result["source"] = {
            key: data[key]
            for key in (
                "source_commit",
                "source_tree",
                "producer_sha256",
                "runtime",
                "imported_product_sources",
                "scope",
                "expected_counts",
                "profile",
                "outcome_cases",
                "hash_cases",
                "producer_inputs",
            )
            if key in data
        }
        for key, size in (
            ("source_commit", 40),
            ("source_tree", 40),
            ("producer_sha256", 64),
        ):
            if not isinstance(data.get(key), str) or not re.fullmatch(
                f"[0-9a-f]{{{size}}}", data[key]
            ):
                raise ValueError(f"missing or malformed {key}")
        if not isinstance(data.get("runtime"), dict) or any(
            not isinstance(data["runtime"].get(key), str)
            for key in ("python", "sqlite")
        ):
            raise ValueError("missing producer runtime identity")
        if (
            not isinstance(data.get("imported_product_sources"), dict)
            or not data["imported_product_sources"]
        ):
            raise ValueError("missing imported product source bindings")
        result["tool"] = {
            "commit": git("rev-parse", "HEAD"),
            "tree": git("rev-parse", "HEAD^{tree}"),
            "working_tree_dirty": bool(git("status", "--porcelain")),
        }
        (output / "source-input.json").write_bytes(raw_input)
        result["digests"] = {"input": digest(raw_input)}
        for name in (
            "instance_model.py",
            "instance_fixture.py",
            "outcome_profile.py",
            "hash_profile.py",
            "model.py",
            "worker.py",
            "instance_shapes.ttl",
            "instance_constraints.json",
            "result.schema.json",
            "uv.lock",
            "pyproject.toml",
        ):
            result["digests"][name] = digest((HERE / name).read_bytes())
        shape_bytes = (HERE / "instance_shapes.ttl").read_bytes()
        manifest = json.loads((HERE / "instance_constraints.json").read_text())
        if digest(shape_bytes) != manifest["shapes_sha256"]:
            raise ValueError("pinned pilot shape closure mismatch")
        if set(manifest["constraints"]) != {shape for shape, *_ in TARGETS}:
            raise ValueError("required constraint coverage missing")
        g = project(data)
        result["coverage"] = {
            shape: {
                "expected": data["expected_counts"][store][table],
                "selected": len(set(g.subjects(RDF.type, cls))),
                "coverage": "not_applicable"
                if not set(g.subjects(RDF.type, cls))
                else "selected",
                "engine_evaluation_count": None,
            }
            for shape, cls, store, table in TARGETS
        }
        if any(c["expected"] != c["selected"] for c in result["coverage"].values()):
            raise ValueError("projected target coverage mismatch")
        result["constraints"] = [
            {
                "id": shape,
                "authority": manifest["authority"],
                "implementation": manifest["constraints"][shape],
                "expected_targets": result["coverage"][shape]["expected"],
                "selected_targets": result["coverage"][shape]["selected"],
                "coverage": result["coverage"][shape]["coverage"],
                "engine_evaluation_count": None,
                "result_scope": "combined checker verdict; no per-constraint verdict attributed",
            }
            for shape, *_ in TARGETS
        ]
        result["unformalized"] = [
            "External-target resolution is not implemented; references remain unresolved.",
            "Terminal records describe retained observations, not atomic filesystem snapshots or every interruption path.",
            "No general SQL/trigger/UDF semantics, all WT physical FKs, exhaustive scanner races or concurrent transitions; digest syntax does not prove real-byte equality.",
            "No specification satisfiability, operation-model or whole-implementation proof.",
        ]
        if not data["expected_counts"]["filesystem"]["scan_outcomes"]:
            result["unformalized"].append(
                "Zero OutcomeShape targets are explicitly not_applicable; terminal scan behavior is not exercised."
            )
        result["fixture_expectation"] = None
        nt = "\n".join(sorted(g.serialize(format="nt").splitlines())) + "\n"
        (output / "data.nt").write_text(nt)
        result["digests"]["graph"] = digest(nt.encode())
        stage = "checker execution"
        checked = run_checker(output, timeout)
        result["checker_returncode"] = checked.returncode
        if checked.returncode:
            raise ValueError(f"checker exited {checked.returncode}; see engine.stderr")
        report = json.loads(checked.stdout, parse_constant=reject_nonfinite_constant)
        (output / "engine.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n"
        )
        if (
            not isinstance(report, dict)
            or report.get("status") not in ("pass", "fail")
            or not isinstance(report.get("engine"), dict)
            or not isinstance(report.get("raw_report"), str)
            or not isinstance(report.get("reason"), str)
        ):
            raise ValueError("checker returned no supported definitive report")
        result["checker_invocations_completed"] = 1
        result["engine"] = report["engine"]
        result["families"]["data_conformance"] = {
            "status": report["status"],
            "scope": SCOPE,
            "reason": "selected pilot shapes conform"
            if report["status"] == "pass"
            else "selected pilot shapes detected nonconformance; see engine.json",
        }
    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        subprocess.SubprocessError,
        OSError,
    ) as exc:
        result["families"]["data_conformance"]["reason"] = (
            f"{stage}: {type(exc).__name__}: {exc}"
        )
    return write_result(result, output)


def reject_nonfinite_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--timeout", default=30)
    args = parser.parse_args(argv)
    try:
        data = json.loads(
            args.input.read_bytes(), parse_constant=reject_nonfinite_constant
        )
    except (ValueError, OSError) as exc:
        result = new_result()
        result["families"]["data_conformance"]["reason"] = (
            f"input admission: {type(exc).__name__}: {exc}"
        )
        result = write_result(result, args.output)
    else:
        result = validate(data, args.output, args.timeout)
    print(json.dumps(result, indent=2, allow_nan=False))
    return {"pass": 0, "fail": 1, "undetermined": 2}[
        result["families"]["data_conformance"]["status"]
    ]


if __name__ == "__main__":
    sys.exit(main())
