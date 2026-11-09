"""Cross-representation controls; product fixtures run under local-run separately."""

import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import instance_model
from instance_model import M, project, validate, value
from rdflib import RDF


class InstancePilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "INSTANCE_FIXTURE" not in os.environ:
            raise unittest.SkipTest(
                "run the verified product fixture producer; set INSTANCE_FIXTURE"
            )
        cls.fixture = json.loads(Path(os.environ["INSTANCE_FIXTURE"]).read_text())

    def run_case(self, data):
        with tempfile.TemporaryDirectory() as temp:
            return validate(data, Path(temp))["families"]["data_conformance"]["status"]

    def test_positive_api_and_shacl(self):
        api = self.fixture["api"]
        self.assertEqual(api["filesystem_verify"], "ok")
        self.assertTrue(api["incomplete_scan"])
        self.assertTrue(api["blob_and_huge_ns_roundtrip"])
        self.assertIn("FOREIGN KEY", api["sqlite_orphan_rejection"])
        self.assertEqual(self.run_case(self.fixture), "pass")

    def test_lossless_exact_cells(self):
        rows = self.fixture["tables"]["filesystem"]["entries"]
        self.assertEqual({value(r["relative_path"]) for r in rows}, {b"", b"bad-\xff"})
        self.assertTrue(
            all(value(r["mtime_ns"]) == "9223372036854775808" for r in rows)
        )
        self.assertTrue(all(value(r["birthtime_ns"]) is None for r in rows))
        graph = project(self.fixture)
        self.assertEqual(len(set(graph.subjects(RDF.type, M.Entry))), 4)
        self.assertEqual(
            {str(v) for v in graph.objects(None, M.mtime_ns)}, {"9223372036854775808"}
        )
        self.assertEqual(set(graph.objects(None, M.birthtime_ns)), {M.SqlNull})

    def test_orphan_graph_rejected(self):
        data = copy.deepcopy(self.fixture)
        data["tables"]["filesystem"]["entries"][0]["scan_uuid"]["value"] = (
            "01800000-0000-7000-8000-000000000000"
        )
        self.assertEqual(self.run_case(data), "fail")

    def test_duplicate_occurrences_do_not_collapse(self):
        data = copy.deepcopy(self.fixture)
        rows = data["tables"]["filesystem"]["entries"]
        rows.append(copy.deepcopy(rows[0]))
        data["expected_counts"]["filesystem"]["entries"] += 1
        self.assertEqual(len(set(project(data).subjects(RDF.type, M.Entry))), 5)
        self.assertEqual(self.run_case(data), "fail")

    def test_duplicate_parent_keys(self):
        for store, table in (("filesystem", "scans"), ("worktrees", "worktrees")):
            data = copy.deepcopy(self.fixture)
            data["tables"][store][table].append(
                copy.deepcopy(data["tables"][store][table][0])
            )
            data["expected_counts"][store][table] += 1
            self.assertEqual(self.run_case(data), "undetermined")

    def test_missing_row_is_not_success(self):
        data = copy.deepcopy(self.fixture)
        data["tables"]["filesystem"]["entries"].pop()
        self.assertEqual(self.run_case(data), "undetermined")

    def test_missing_column_not_null(self):
        data = copy.deepcopy(self.fixture)
        del data["tables"]["filesystem"]["entries"][0]["birthtime_ns"]
        self.assertEqual(self.run_case(data), "undetermined")

    def test_corrupt_blob_not_silently_decoded(self):
        data = copy.deepcopy(self.fixture)
        data["tables"]["filesystem"]["entries"][0]["relative_path"]["length"] += 1
        self.assertEqual(self.run_case(data), "undetermined")

    def test_malformed_unresolved_reference(self):
        data = copy.deepcopy(self.fixture)
        data["tables"]["worktrees"]["scan_references"][0]["filesystem_scan_uuid"][
            "value"
        ] = "not-a-uuid"
        self.assertEqual(self.run_case(data), "undetermined")

    def test_noncanonical_ns(self):
        self.assertEqual(self.fixture["api"]["sqlite_noncanonical_ns"], "accepted")
        self.assertIn(
            "invalid native timestamp", self.fixture["api"]["api_noncanonical_ns"]
        )
        data = copy.deepcopy(self.fixture)
        data["tables"]["filesystem"]["entries"][0]["mtime_ns"]["value"] = "+01"
        self.assertEqual(self.run_case(data), "undetermined")

    def test_checker_timeout_and_unavailable(self):
        for error in (
            FileNotFoundError("checker unavailable"),
            subprocess.TimeoutExpired("checker", 1),
        ):
            with patch("instance_model.subprocess.run", side_effect=error):
                self.assertEqual(self.run_case(self.fixture), "undetermined")

    def test_missing_shape_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for name in ("instance_shapes.ttl", "instance_constraints.json", "uv.lock"):
                shutil.copyfile(instance_model.HERE / name, folder / name)
            (folder / "instance_shapes.ttl").write_text("")
            with patch("instance_model.HERE", folder):
                self.assertEqual(self.run_case(self.fixture), "undetermined")

    def test_reproducible_graph(self):
        self.assertEqual(set(project(self.fixture)), set(project(self.fixture)))


if __name__ == "__main__":
    unittest.main()
