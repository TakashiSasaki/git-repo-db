"""Versioned, optional source-bound structural projection. No product imports."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import quote

from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.compare import to_isomorphic

M = Namespace("urn:git-repo-db:model:v1:")
SH = Namespace("http://www.w3.org/ns/shacl#")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FAMILIES = (
    "data_conformance",
    "spec_satisfiability",
    "operation_invariants",
    "implementation_conformance",
)
CLASSES = (
    "SchemaDefinition",
    "Table",
    "Column",
    "PrimaryKeyPart",
    "ForeignKey",
    "ColumnBinding",
    "SourceUnit",
    "Distribution",
    "ResponsibilityDomain",
    "Configuration",
    "ExternalReference",
    "View",
    "Index",
    "Trigger",
    "ReferenceBinding",
    "LogicalAnnotation",
)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def iri(*parts):
    return URIRef(str(M) + "/".join(quote(str(p), safe="") for p in parts))


def git(*args):
    return (
        subprocess.check_output(["git", "-C", str(ROOT), *args], timeout=30)
        .decode()
        .strip()
    )


def load_input(directory):
    raw = (directory / "inventory.json").read_bytes()
    data = json.loads(raw)
    producer = json.loads((directory / "producer.json").read_bytes())
    if data.get("profile") != "all" or data.get("inventory_schema_version") != 1:
        raise ValueError("unsupported IR profile/version")
    if (
        producer.get("schema_version") != 1
        or producer.get("inventory_profile") != "all"
    ):
        raise ValueError("unsupported producer profile/version")
    if producer.get("ir_sha256") != digest(raw):
        raise ValueError("IR digest mismatch")
    source = producer["product_source"]
    if not re.fullmatch("[0-9a-f]{40}", source["commit"]):
        raise ValueError("invalid source commit")
    if git("rev-parse", source["commit"] + "^{tree}") != source["tree"]:
        raise ValueError("source tree mismatch")
    inputs = producer["input_sha256"]
    if (
        not inputs
        or not producer["executed_python_inputs"]
        or not set(producer["executed_python_inputs"]) <= set(inputs)
    ):
        raise ValueError("producer input coverage missing")
    # Validate against the existing producer control input closure, without importing
    # product code or trusting a caller-supplied shortened manifest.
    names = git("ls-tree", "-r", "--name-only", source["commit"]).splitlines()
    required = {
        p
        for p in names
        if p.startswith(("src/", "packages/"))
        or (p.startswith("scripts/") and p.endswith(".py"))
        or p
        in {
            "scripts/schema_inventory.py",
            "scripts/audit_publication_free.py",
            "scripts/verification_outputs.py",
            "pyproject.toml",
            "uv.lock",
        }
    }
    if required != set(inputs):
        raise ValueError("producer input closure incomplete")
    for path in inputs:
        if path not in names:
            raise ValueError("unknown producer input: " + path)
    requests = "".join(source["commit"] + ":" + path + "\n" for path in inputs)
    batch = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "--batch"],
        input=requests.encode(),
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout
    cursor = 0
    bound_blobs = {}
    for path, expected in inputs.items():
        end = batch.index(b"\n", cursor)
        _, kind, length = batch[cursor:end].split()
        size = int(length)
        blob = batch[end + 1 : end + 1 + size]
        if kind != b"blob" or digest(blob) != expected:
            raise ValueError("source input digest mismatch: " + path)
        bound_blobs[path] = blob
        cursor = end + size + 2
    registry = ast.parse(bound_blobs["scripts/schema_catalog.py"])
    assignment = next(
        n.value
        for n in registry.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "STORE_LAYOUT" for t in n.targets)
    )
    if not isinstance(assignment, ast.Dict) or set(data["stores"]) != {
        ast.literal_eval(k) for k in assignment.keys
    }:
        raise ValueError("schema registry coverage mismatch")
    config = tomllib.loads(bound_blobs["pyproject.toml"].decode())
    distributions = {}
    owners = {}
    for directory in [".", *config["tool"]["uv"]["workspace"]["members"]]:
        prefix = "" if directory == "." else directory + "/"
        path = prefix + "pyproject.toml"
        package = tomllib.loads(bound_blobs[path].decode())["project"]
        name = package["name"]
        distributions[name] = {
            "pyproject": path,
            "version": package["version"],
            "dependency_requirements": package.get("dependencies", []),
            "optional_dependency_requirements": package.get(
                "optional-dependencies", {}
            ),
        }
        for source_path in bound_blobs:
            if source_path.startswith(prefix + "src/repo_catalog/"):
                owners[source_path] = name
    if data["distributions"] != distributions or data["source_ownership"] != owners:
        raise ValueError("source ownership/distribution coverage mismatch")
    return data, producer


def expected_targets(data, revision):
    """Independent enumeration: SQLite extracted_objects, not projected RDF."""
    expected = {c: set() for c in CLASSES}
    for kind, field in [
        ("Distribution", "distributions"),
        ("ResponsibilityDomain", "authority_domains"),
        ("Configuration", "configurations"),
        ("SourceUnit", "source_ownership"),
    ]:
        expected[kind] = {iri(revision, kind, n) for n in data[field]}
    for name, store in data["stores"].items():
        expected["SchemaDefinition"].add(iri(revision, "schema", name))
        if store["foreign_key_count"] != sum(
            len(t["foreign_keys"]) for t in store["tables"].values()
        ):
            raise ValueError("FK coverage differs from independent extraction count")
        records = store["extracted_objects"]
        if len({(r["type"], r["name"]) for r in records}) != len(records):
            raise ValueError("duplicate extracted object")
        for r in records:
            cls = {
                "table": "Table",
                "index": "Index",
                "trigger": "Trigger",
                "view": "View",
            }[r["type"]]
            expected[cls].add(iri(revision, name, cls, r["name"]))
        for name_t, table in store["tables"].items():
            if table["column_count"] != len(table["columns"]):
                raise ValueError("column coverage mismatch")
            expected["Column"].update(
                iri(revision, name, name_t, "column", c["name"])
                for c in table["columns"]
            )
            expected["PrimaryKeyPart"].update(
                iri(revision, name, name_t, "pk", n)
                for n in range(len(table["primary_key"]))
            )
            for f in table["foreign_keys"]:
                expected["ForeignKey"].add(iri(revision, name, name_t, "fk", f["id"]))
                expected["ColumnBinding"].update(
                    iri(revision, name, name_t, "fk", f["id"], n)
                    for n in range(len(f["from_columns"]))
                )
    expected["ExternalReference"] = {
        iri(revision, "reference", x["id"]) for x in data["optional_references"]
    }
    expected["ReferenceBinding"] = {
        iri(revision, "reference", ref["id"], pos)
        for ref in data["optional_references"]
        for pos in range(len(ref["source_columns"]))
    }
    expected["LogicalAnnotation"] = {
        iri(revision, "logical-annotation", ref["id"])
        for ref in data["normal_logical_dependencies"]
    }
    if (
        not expected["SchemaDefinition"]
        or not expected["Table"]
        or not expected["Column"]
    ):
        raise ValueError("empty required schema targets")
    return expected


def project(data, producer):
    revision = producer["product_source"]["commit"]
    graph = Graph()

    def record(node, cls, raw):
        graph.add((node, RDF.type, M[cls]))
        graph.add(
            (node, M.sourceRecordSHA256, Literal(digest(canonical(raw).encode())))
        )
        # Raw SQL and full records remain in source-ir.json; avoid repeated large
        # SQL literals in the executable graph. The receipt binds both artifacts.
        for key, value in raw.items():
            if (
                key not in ("sql", "raw_sql")
                and (value is None or isinstance(value, (str, int, bool)))
                and len(str(value)) < 2048
            ):
                graph.add((node, M["ir." + key], Literal(canonical(value))))

    def link(a, prop, b):
        graph.add((a, M[prop], b))

    # Lossless source evidence preserves fields not yet given semantics.
    record(
        iri(revision, "inventory"),
        "Inventory",
        {
            "source_ir_sha256": producer["ir_sha256"],
            "unformalized": data["scope"]["unformalized"],
        },
    )
    for cls, field in [
        ("Distribution", "distributions"),
        ("ResponsibilityDomain", "authority_domains"),
        ("Configuration", "configurations"),
    ]:
        for name, raw in data[field].items():
            node = iri(revision, cls, name)
            record(node, cls, raw)
            if cls == "Distribution":
                for requirement in raw["dependency_requirements"]:
                    link(node, "mandatoryInstallRequirement", Literal(requirement))
                for group, requirements in raw[
                    "optional_dependency_requirements"
                ].items():
                    for requirement in requirements:
                        link(
                            node,
                            "optionalInstallRequirement",
                            Literal(
                                canonical({"group": group, "requirement": requirement})
                            ),
                        )
            if cls == "Configuration":
                for store in raw["stores"]:
                    link(node, "configuredSchema", iri(revision, "schema", store))
            if cls == "ResponsibilityDomain":
                link(
                    node,
                    "implementedBy",
                    iri(revision, "Distribution", raw["independent_distribution"]),
                )
    for path, owner in data["source_ownership"].items():
        node = iri(revision, "SourceUnit", path)
        record(node, "SourceUnit", {"path": path})
        link(node, "ownedByDistribution", iri(revision, "Distribution", owner))
    for name, store in data["stores"].items():
        sn = iri(revision, "schema", name)
        record(
            sn, "SchemaDefinition", {k: v for k, v in store.items() if k != "tables"}
        )
        link(
            sn,
            "assembledBy",
            iri(revision, "SourceUnit", store["composition_entrypoint"]),
        )
        for d in store["definition_sources"]:
            link(sn, "contributedBy", iri(revision, "Distribution", d["distribution"]))
        for kind, field in [
            ("View", "views"),
            ("Index", "explicit_indexes"),
            ("Trigger", "triggers"),
        ]:
            for n, raw in store[field].items():
                node = iri(revision, name, kind, n)
                record(node, kind, raw)
                link(node, "schema", sn)
        for tn, table in store["tables"].items():
            node = iri(revision, name, "Table", tn)
            record(
                node,
                "Table",
                {
                    k: v
                    for k, v in table.items()
                    if k not in ("columns", "foreign_keys", "incoming_foreign_keys")
                },
            )
            link(node, "schema", sn)
            for col in table["columns"]:
                cn = iri(revision, name, tn, "column", col["name"])
                record(cn, "Column", col)
                link(cn, "table", node)
            for pos, col in enumerate(table["primary_key"]):
                pn = iri(revision, name, tn, "pk", pos)
                record(pn, "PrimaryKeyPart", {"position": pos, "column": col})
                link(pn, "table", node)
                link(pn, "column", iri(revision, name, tn, "column", col))
                link(pn, "position", Literal(pos))
            for fk in table["foreign_keys"]:
                fn = iri(revision, name, tn, "fk", fk["id"])
                target = fk["target_table"]
                record(fn, "ForeignKey", fk)
                link(node, "physicalForeignKey", fn)
                link(fn, "sourceTable", node)
                link(fn, "targetTable", iri(revision, name, "Table", target))
                effective = fk["to_columns"]
                if all(c is None for c in effective):
                    effective = store["tables"][target]["primary_key"]
                if len(effective) != len(fk["from_columns"]):
                    raise ValueError("foreign key arity mismatch")
                for pos, (src, dst) in enumerate(zip(fk["from_columns"], effective)):
                    bn = iri(revision, name, tn, "fk", fk["id"], pos)
                    record(
                        bn,
                        "ColumnBinding",
                        {
                            "declared_target": fk["to_columns"][pos],
                            "effective_target": dst,
                        },
                    )
                    link(bn, "foreignKey", fn)
                    link(bn, "position", Literal(pos))
                    link(bn, "sourceColumn", iri(revision, name, tn, "column", src))
                    link(bn, "targetColumn", iri(revision, name, target, "column", dst))
    for ref in data["optional_references"]:
        node = iri(revision, "reference", ref["id"])
        record(node, "ExternalReference", ref)
        link(node, "resolution", Literal("not_applicable_schema_only"))
        link(
            iri(revision, ref["source_store"], "Table", ref["source_table"]),
            "qualifiedExternalReference",
            node,
        )
        for pos, column in enumerate(ref["source_columns"]):
            binding = iri(revision, "reference", ref["id"], pos)
            record(binding, "ReferenceBinding", {"position": pos})
            link(binding, "reference", node)
            link(binding, "position", Literal(pos))
            link(
                binding,
                "sourceColumn",
                iri(
                    revision, ref["source_store"], ref["source_table"], "column", column
                ),
            )
            if "target_columns" in ref:
                link(
                    binding,
                    "targetColumn",
                    iri(
                        revision,
                        ref["target_store"],
                        ref["target_table"],
                        "column",
                        ref["target_columns"][pos],
                    ),
                )
            else:
                link(
                    binding,
                    "targetDomain",
                    iri(revision, "ResponsibilityDomain", ref["target_domain"]),
                )
    for annotation in data["normal_logical_dependencies"]:
        node = iri(revision, "logical-annotation", annotation["id"])
        record(node, "LogicalAnnotation", annotation)
        link(
            node,
            "sourceTable",
            iri(
                revision,
                annotation["source_store"],
                "Table",
                annotation["source_table"],
            ),
        )
        link(
            node,
            "targetTable",
            iri(
                revision,
                annotation["target_store"],
                "Table",
                annotation["target_table"],
            ),
        )
        link(
            node,
            "interpretation",
            Literal(
                "historical annotation; not current authority or operation requirement"
            ),
        )
        link(
            node,
            "declaredColumnPairs",
            Literal(
                canonical(
                    list(
                        zip(annotation["source_columns"], annotation["target_columns"])
                    )
                )
            ),
        )
    return graph


def graph_bytes(graph):
    # Every generated subject is an IRI. Sorted N-Triples has no blank-node labels.
    if any(not isinstance(s, URIRef) for s in graph.subjects()):
        raise ValueError("blank subjects not supported for deterministic projection")
    return (
        "\n".join(sorted(graph.serialize(format="nt").splitlines())) + "\n"
    ).encode()


def coverage(graph, data, producer):
    expected = expected_targets(data, producer["product_source"]["commit"])
    results = {}
    for cls, nodes in expected.items():
        actual = set(graph.subjects(RDF.type, M[cls]))
        results[cls] = {
            "expected": len(nodes),
            "selected": len(actual),
            "missing": sorted(map(str, nodes - actual)),
            "unexpected": sorted(map(str, actual - nodes)),
        }
    return results


def mapping_errors(graph, data, producer):
    """Compare ordered bindings to source IR, independently of SHACL verdict."""
    rev = producer["product_source"]["commit"]
    errors = []

    def exact(node, predicate, expected):
        if set(graph.objects(node, M[predicate])) != set(expected):
            errors.append(str(node) + ":" + predicate)

    for path, owner in data["source_ownership"].items():
        exact(
            iri(rev, "SourceUnit", path),
            "ownedByDistribution",
            [iri(rev, "Distribution", owner)],
        )
    for name, store in data["stores"].items():
        exact(
            iri(rev, "schema", name),
            "contributedBy",
            [
                iri(rev, "Distribution", d["distribution"])
                for d in store["definition_sources"]
            ],
        )
        exact(
            iri(rev, "schema", name),
            "assembledBy",
            [iri(rev, "SourceUnit", store["composition_entrypoint"])],
        )
        for tn, table in store["tables"].items():
            table_node = iri(rev, name, "Table", tn)
            exact(table_node, "schema", [iri(rev, "schema", name)])
            exact(
                table_node,
                "physicalForeignKey",
                [iri(rev, name, tn, "fk", fk["id"]) for fk in table["foreign_keys"]],
            )
            for column in table["columns"]:
                exact(
                    iri(rev, name, tn, "column", column["name"]), "table", [table_node]
                )
            for pos, col in enumerate(table["primary_key"]):
                node = iri(rev, name, tn, "pk", pos)
                exact(node, "position", [Literal(pos)])
                exact(node, "table", [table_node])
                exact(node, "column", [iri(rev, name, tn, "column", col)])
            for fk in table["foreign_keys"]:
                fk_node = iri(rev, name, tn, "fk", fk["id"])
                exact(fk_node, "sourceTable", [table_node])
                exact(
                    fk_node,
                    "targetTable",
                    [iri(rev, name, "Table", fk["target_table"])],
                )
                effective = fk["to_columns"]
                if all(x is None for x in effective):
                    effective = store["tables"][fk["target_table"]]["primary_key"]
                if len(effective) != len(fk["from_columns"]):
                    errors.append("FK arity")
                    continue
                for pos, (src, dst) in enumerate(zip(fk["from_columns"], effective)):
                    node = iri(rev, name, tn, "fk", fk["id"], pos)
                    exact(node, "position", [Literal(pos)])
                    exact(node, "foreignKey", [fk_node])
                    exact(node, "sourceColumn", [iri(rev, name, tn, "column", src)])
                    exact(
                        node,
                        "targetColumn",
                        [iri(rev, name, fk["target_table"], "column", dst)],
                    )
    for ref in data["optional_references"]:
        node = iri(rev, "reference", ref["id"])
        table = iri(rev, ref["source_store"], "Table", ref["source_table"])
        if (table, M.qualifiedExternalReference, node) not in graph or (
            table,
            M.physicalForeignKey,
            node,
        ) in graph:
            errors.append("reference classification: " + ref["id"])
        for pos, column in enumerate(ref["source_columns"]):
            binding = iri(rev, "reference", ref["id"], pos)
            exact(binding, "reference", [node])
            exact(binding, "position", [Literal(pos)])
            exact(
                binding,
                "sourceColumn",
                [iri(rev, ref["source_store"], ref["source_table"], "column", column)],
            )
            if "target_columns" in ref:
                exact(
                    binding,
                    "targetColumn",
                    [
                        iri(
                            rev,
                            ref["target_store"],
                            ref["target_table"],
                            "column",
                            ref["target_columns"][pos],
                        )
                    ],
                )
            else:
                exact(
                    binding,
                    "targetDomain",
                    [iri(rev, "ResponsibilityDomain", ref["target_domain"])],
                )
    for ref in data["normal_logical_dependencies"]:
        node = iri(rev, "logical-annotation", ref["id"])
        exact(
            node,
            "sourceTable",
            [iri(rev, ref["source_store"], "Table", ref["source_table"])],
        )
        exact(
            node,
            "targetTable",
            [iri(rev, ref["target_store"], "Table", ref["target_table"])],
        )
        exact(
            node,
            "declaredColumnPairs",
            [
                Literal(
                    canonical(list(zip(ref["source_columns"], ref["target_columns"])))
                )
            ],
        )
    return errors


def check_shapes(shapes, catalog):
    if str(to_isomorphic(shapes).graph_digest()) != catalog["shape_graph_digest"]:
        raise ValueError("shape closure differs from constraint catalog")
    allowed = {
        "NodeShape",
        "PropertyShape",
        "targetClass",
        "property",
        "path",
        "minCount",
        "maxCount",
        "class",
        "datatype",
        "nodeKind",
        "IRI",
        "message",
        "severity",
        "Violation",
        "Warning",
        "Info",
        "sparql",
        "select",
    }
    for s, p, o in shapes:
        for term in (p, o):
            if (
                isinstance(term, URIRef)
                and str(term).startswith(str(SH))
                and str(term)[len(str(SH)) :] not in allowed
            ):
                raise ValueError("unsupported SHACL construct: " + str(term))
        if p == SH.select:
            # Only repository-pinned SELECT templates are executable; no arbitrary query.
            if str(o) not in {x.get("select") for x in catalog["constraints"]}:
                raise ValueError("unsupported SELECT template")
        if str(p).endswith("#imports"):
            raise ValueError("imports forbidden")
    required = {URIRef(x["shape"]) for x in catalog["constraints"]}
    if set(shapes.subjects(RDF.type, SH.NodeShape)) != required:
        raise ValueError("required shape set mismatch")
    if any(
        re.search(r"\b(SERVICE|LOAD|FROM)\b", str(o), re.I)
        for o in shapes.objects(None, SH.select)
    ):
        raise ValueError("external SPARQL access forbidden")


def run_worker(graph_path, shapes_path, timeout):
    try:
        p = subprocess.run(
            [
                sys.executable,
                str(HERE / "worker.py"),
                str(graph_path),
                str(shapes_path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONHASHSEED": "0"},
        )
    except subprocess.TimeoutExpired:
        return {"status": "undetermined", "reason": "timeout"}
    if p.returncode:
        return {
            "status": "undetermined",
            "reason": "checker_failure",
            "diagnostic": p.stderr[-2000:],
        }
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"status": "undetermined", "reason": "invalid_checker_report"}


def validate(data, producer, output, timeout=60, graph=None):
    output.mkdir(parents=True, exist_ok=True)
    graph = project(data, producer) if graph is None else graph
    (output / "source-ir.json").write_text(canonical(data) + "\n")
    raw = graph_bytes(graph)
    (output / "model.nt").write_bytes(raw)
    cov = coverage(graph, data, producer)
    catalog = json.loads((HERE / "constraints.json").read_text())
    shapes = Graph().parse(HERE / "shapes.ttl", format="turtle")
    check_shapes(shapes, catalog)
    checks = []
    mapping = mapping_errors(graph, data, producer)
    required_nonempty = all(
        cov[c["target_class"]]["expected"] > 0 for c in catalog["constraints"]
    )
    coverage_ok = (
        required_nonempty
        and not mapping
        and all(not v["missing"] and not v["unexpected"] for v in cov.values())
    )
    for c in catalog["constraints"]:
        cls = c["target_class"]
        if not coverage_ok:
            checks.append(
                {
                    "id": c["id"],
                    "status": "undetermined",
                    "reason": "coverage_mismatch",
                    "completed_invocations": 0,
                }
            )
            continue
        # Shape closure is isolated per constraint, making completion observable.
        selected = Graph()
        node = URIRef(c["shape"])
        pending = [node]
        seen = set()
        while pending:
            s = pending.pop()
            if s in seen:
                continue
            seen.add(s)
            for triple in shapes.triples((s, None, None)):
                selected.add(triple)
                if triple[1] in (SH.property, SH.sparql):
                    pending.append(triple[2])
        sp = output / (c["id"] + ".ttl")
        selected.serialize(sp, format="turtle")
        result = run_worker(output / "model.nt", sp, timeout)
        checks.append(
            {
                "id": c["id"],
                "authority": c["authority"],
                "implementation": c["implementation"],
                "expected_targets": cov[cls]["expected"],
                "selected_targets": cov[cls]["selected"],
                "engine_evaluation_count": None,
                "coverage_basis": "independent_IR_targets_and_isolated_constraint_completion",
                "completed_invocations": int(result["status"] in ("pass", "fail")),
                **result,
            }
        )
    status = (
        "fail"
        if any(x["status"] == "fail" for x in checks)
        else (
            "pass"
            if coverage_ok and checks and all(x["status"] == "pass" for x in checks)
            else "undetermined"
        )
    )
    result = {
        "schema_version": 1,
        "source": producer,
        "tool": {
            "commit": git("rev-parse", "HEAD"),
            "tree": git("rev-parse", "HEAD^{tree}"),
            "working_tree_dirty": bool(git("status", "--porcelain")),
        },
        "digests": {
            "graph": digest(raw),
            "source_ir": digest((output / "source-ir.json").read_bytes()),
            **{
                p.name: digest(p.read_bytes())
                for p in HERE.iterdir()
                if p.suffix in (".py", ".json", ".ttl", ".toml") or p.name == "uv.lock"
            },
        },
        "coverage": cov,
        "mapping_errors": mapping,
        "constraints": checks,
        "families": {
            f: {
                "status": status if f == "data_conformance" else "not_run",
                "scope": "selected structural schema projection"
                if f == "data_conformance"
                else "outside PR-A execution",
                "reason": "see constraint receipts"
                if f == "data_conformance"
                else "not implemented by structural runner",
            }
            for f in FAMILIES
        },
        "unformalized": data["scope"]["unformalized"]
        + [
            "Operation requiresCapability and derivedFrom are not instantiated: IR supplies no authoritative operation/derivation registry; logical dependencies remain historical annotations, not current requirements."
        ],
        "fixture_expectation": None,
    }
    import jsonschema

    jsonschema.validate(result, json.loads((HERE / "result.schema.json").read_text()))
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if args.timeout <= 0 or args.timeout > 600:
        parser.error("timeout must be in (0,600] seconds per constraint")
    try:
        data, producer = load_input(args.input)
        result = validate(data, producer, args.output, args.timeout)
        status = result["families"]["data_conformance"]["status"]
        print(
            json.dumps(
                {
                    "status": status,
                    "constraints": len(result["constraints"]),
                    "result": str(args.output / "result.json"),
                }
            )
        )
        return 0 if status == "pass" else 1
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        result = {
            "schema_version": 1,
            "families": {
                f: {
                    "status": "undetermined" if f == "data_conformance" else "not_run",
                    "reason": str(exc),
                    "scope": "input/runner admission",
                }
                for f in FAMILIES
            },
        }
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": "undetermined", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
