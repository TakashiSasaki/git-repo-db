"""Focused isolated tests; product extraction is performed by the existing producer."""

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import model
from rdflib import RDF, Graph, Literal


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.producer = model.load_input(
            model.ROOT / "documentation/.build/inputs/all-formats"
        )
        cls.graph = model.project(cls.data, cls.producer)
        cls.catalog = json.loads((model.HERE / "constraints.json").read_text())

    def test_complete_coverage_and_mapping(self):
        cov = model.coverage(self.graph, self.data, self.producer)
        self.assertTrue(
            all(not x["missing"] and not x["unexpected"] for x in cov.values())
        )
        self.assertEqual(model.mapping_errors(self.graph, self.data, self.producer), [])

    def test_determinism(self):
        self.assertEqual(
            model.graph_bytes(self.graph),
            model.graph_bytes(model.project(self.data, self.producer)),
        )

    def test_missing_table(self):
        graph = self.graph - Graph()
        node = next(graph.subjects(RDF.type, model.M.Table))
        graph.remove((node, None, None))
        self.assertTrue(
            model.coverage(graph, self.data, self.producer)["Table"]["missing"]
        )

    def test_missing_trigger_in_ir(self):
        data = copy.deepcopy(self.data)
        store = next(s for s in data["stores"].values() if s["triggers"])
        store["triggers"].pop(next(iter(store["triggers"])))
        graph = model.project(data, self.producer)
        self.assertTrue(
            model.coverage(graph, data, self.producer)["Trigger"]["missing"]
        )

    def test_key_position_mutation(self):
        graph = self.graph - Graph()
        node = next(graph.subjects(RDF.type, model.M.PrimaryKeyPart))
        graph.set((node, model.M.position, Literal(999)))
        self.assertTrue(model.mapping_errors(graph, self.data, self.producer))

    def test_owner_mutation(self):
        graph = self.graph - Graph()
        node = next(graph.subjects(RDF.type, model.M.SourceUnit))
        graph.remove((node, model.M.ownedByDistribution, None))
        self.assertTrue(model.mapping_errors(graph, self.data, self.producer))

    def test_missing_shapes(self):
        shapes = Graph().parse(model.HERE / "shapes.ttl")
        shapes.remove((model.M["OWNER-01"], None, None))
        with self.assertRaises(ValueError):
            model.check_shapes(shapes, self.catalog)

    def test_deactivated_unsupported(self):
        shapes = Graph().parse(model.HERE / "shapes.ttl")
        shapes.add((model.M["OWNER-01"], model.SH.deactivated, Literal(True)))
        with self.assertRaises(ValueError):
            model.check_shapes(shapes, self.catalog)

    def test_service_rejected(self):
        shapes = Graph().parse(model.HERE / "shapes.ttl")
        shapes.add(
            (
                model.M.x,
                model.SH.select,
                Literal("SELECT $this WHERE { SERVICE <https://example.org> {} }"),
            )
        )
        with self.assertRaises(ValueError):
            model.check_shapes(shapes, self.catalog)

    def test_timeout_and_unavailable(self):
        with patch(
            "model.subprocess.run", side_effect=subprocess.TimeoutExpired("x", 1)
        ):
            self.assertEqual(
                model.run_worker(Path("a"), Path("b"), 1)["reason"], "timeout"
            )
        with patch(
            "model.subprocess.run",
            return_value=subprocess.CompletedProcess("x", 1, "", "unavailable"),
        ):
            self.assertEqual(
                model.run_worker(Path("a"), Path("b"), 1)["status"], "undetermined"
            )

    def test_zero_required_targets(self):
        data = copy.deepcopy(self.data)
        data["stores"] = {}
        with self.assertRaises(ValueError):
            model.expected_targets(data, "x")

    def test_input_bindings(self):
        original = model.ROOT / "documentation/.build/inputs/all-formats"
        for field, value in [("ir_sha256", "0" * 64), ("inventory_profile", "normal")]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as d:
                p = Path(d)
                (p / "inventory.json").write_bytes(
                    (original / "inventory.json").read_bytes()
                )
                manifest = copy.deepcopy(self.producer)
                manifest[field] = value
                (p / "producer.json").write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    model.load_input(p)

    def test_missing_property_in_required_shape(self):
        shapes = Graph().parse(model.HERE / "shapes.ttl")
        shapes.remove((model.M["OWNER-01"], model.SH.property, None))
        with self.assertRaises(ValueError):
            model.check_shapes(shapes, self.catalog)

    def test_binding_order_mutation(self):
        graph = self.graph - Graph()
        node = next(graph.subjects(RDF.type, model.M.ColumnBinding))
        graph.set((node, model.M.position, Literal(999)))
        self.assertTrue(model.mapping_errors(graph, self.data, self.producer))

    def test_external_reference_misclassified(self):
        graph = self.graph - Graph()
        source, _, target = next(
            graph.triples((None, model.M.qualifiedExternalReference, None))
        )
        graph.add((source, model.M.physicalForeignKey, target))
        self.assertTrue(model.mapping_errors(graph, self.data, self.producer))

    def test_immutable_negative_source_binding(self):
        original = model.ROOT / "documentation/.build/inputs/all-formats"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "inventory.json").write_bytes(
                (original / "inventory.json").read_bytes()
            )
            manifest = copy.deepcopy(self.producer)
            manifest["product_source"]["tree"] = "0" * 40
            (p / "producer.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                model.load_input(p)

    def test_fk_parent_and_endpoint_mutations(self):
        revision = self.producer["product_source"]["commit"]
        table = self.data["stores"]["normal.core"]["tables"]["acquisition_roots"]
        fk = next(
            f for f in table["foreign_keys"] if f["target_table"] == "git_acquisitions"
        )
        fk_node = model.iri(
            revision, "normal.core", "acquisition_roots", "fk", fk["id"]
        )
        wrong_table = model.iri(revision, "normal.core", "Table", "acquisition_roots")
        for predicate in ("targetTable", "sourceTable"):
            with self.subTest(predicate=predicate):
                graph = self.graph - Graph()
                target = (
                    wrong_table
                    if predicate == "targetTable"
                    else model.iri(revision, "normal.core", "Table", "git_acquisitions")
                )
                graph.set((fk_node, model.M[predicate], target))
                self.assertTrue(model.mapping_errors(graph, self.data, self.producer))
                with tempfile.TemporaryDirectory() as d:
                    result = model.validate(
                        self.data, self.producer, Path(d), graph=graph
                    )
                    self.assertNotEqual(
                        result["families"]["data_conformance"]["status"], "pass"
                    )
        graph = self.graph - Graph()
        binding = model.iri(
            revision, "normal.core", "acquisition_roots", "fk", fk["id"], 0
        )
        other_fk = next(
            n for n in graph.subjects(RDF.type, model.M.ForeignKey) if n != fk_node
        )
        graph.set((binding, model.M.foreignKey, other_fk))
        self.assertTrue(model.mapping_errors(graph, self.data, self.producer))

    def test_removed_foreign_keys_are_not_vacuous_success(self):
        data = copy.deepcopy(self.data)
        for store in data["stores"].values():
            for table in store["tables"].values():
                table["foreign_keys"] = []
        with self.assertRaisesRegex(ValueError, "FK coverage"):
            model.expected_targets(data, self.producer["product_source"]["commit"])
        # Even with the count forged to zero, required FK shapes must not pass.
        for store in data["stores"].values():
            store["foreign_key_count"] = 0
        with tempfile.TemporaryDirectory() as d:
            result = model.validate(data, self.producer, Path(d))
            self.assertEqual(
                result["families"]["data_conformance"]["status"], "undetermined"
            )

    def test_external_column_binding_order(self):
        graph = self.graph - Graph()
        node = next(graph.subjects(RDF.type, model.M.ReferenceBinding))
        graph.set((node, model.M.position, Literal(99)))
        self.assertTrue(model.mapping_errors(graph, self.data, self.producer))

    def test_actual_negative_shape(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            graph = self.graph - Graph()
            node = next(graph.subjects(RDF.type, model.M.SourceUnit))
            graph.remove((node, model.M.ownedByDistribution, None))
            (p / "data.nt").write_bytes(model.graph_bytes(graph))
            result = model.run_worker(p / "data.nt", model.HERE / "shapes.ttl", 60)
            self.assertEqual(result["status"], "fail")


if __name__ == "__main__":
    unittest.main()
