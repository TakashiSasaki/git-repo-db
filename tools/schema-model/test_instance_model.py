"""Cross-representation controls; product fixtures run under local-run separately."""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import instance_model
import jsonschema
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

    def receipt(self, data, timeout=30):
        with tempfile.TemporaryDirectory() as temp:
            result = validate(data, Path(temp), timeout)
            saved = json.loads((Path(temp) / "result.json").read_text())
            self.assertEqual(result, saved)
            assert_contract(self, saved)
            return saved

    def run_case(self, data):
        return self.receipt(data)["families"]["data_conformance"]["status"]

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
            with self.subTest(error=type(error).__name__):
                with patch("instance_model.run_checker", side_effect=error):
                    result = self.receipt(self.fixture)
                self.assertEqual(
                    result["families"]["data_conformance"]["status"], "undetermined"
                )
                self.assertEqual(result["checker_invocations_completed"], 0)
                self.assertIsNone(result["engine_evaluation_count"])
                self.assertNotIn("engine", result)

    def test_missing_shape_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for source in instance_model.HERE.iterdir():
                if source.is_file():
                    shutil.copyfile(source, folder / source.name)
            (folder / "instance_shapes.ttl").write_text("")
            with patch("instance_model.HERE", folder):
                self.assertEqual(self.run_case(self.fixture), "undetermined")

    def test_reproducible_graph(self):
        self.assertEqual(set(project(self.fixture)), set(project(self.fixture)))

    def test_common_receipt_metadata_and_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            result = validate(self.fixture, output)
            assert_contract(self, result)
            self.assertEqual(
                result["source"]["source_commit"], self.fixture["source_commit"]
            )
            self.assertEqual(result["source"]["runtime"], self.fixture["runtime"])
            self.assertEqual(
                result["source"]["imported_product_sources"],
                self.fixture["imported_product_sources"],
            )
            self.assertEqual(result["checker_invocations_completed"], 1)
            self.assertIsNone(result["engine_evaluation_count"])
            for shape, count in (
                ("EntryShape", 4),
                ("ScanShape", 2),
                ("OutcomeShape", 0),
                ("ReferenceShape", 1),
            ):
                coverage = result["coverage"][shape]
                self.assertEqual(coverage["expected"], count)
                self.assertEqual(coverage["selected"], count)
                self.assertIsNone(coverage["engine_evaluation_count"])
            self.assertEqual(
                result["coverage"]["OutcomeShape"]["coverage"], "not_applicable"
            )
            self.assertEqual(
                {c["id"] for c in result["constraints"]},
                {s for s, *_ in instance_model.TARGETS},
            )
            self.assertTrue(all(c["authority"] for c in result["constraints"]))
            self.assertIsNone(result["fixture_expectation"])
            self.assertEqual(
                result["digests"]["graph"],
                instance_model.digest((output / "data.nt").read_bytes()),
            )
            raw = json.loads((output / "engine.stdout").read_bytes())
            self.assertEqual(raw, json.loads((output / "engine.json").read_text()))
            self.assertEqual(result["engine"], raw["engine"])
            self.assertIn("raw_report", raw)

    def test_missing_required_extraction(self):
        for store, table in (
            ("filesystem", "entries"),
            ("worktrees", "scan_references"),
        ):
            with self.subTest(table=table):
                data = copy.deepcopy(self.fixture)
                del data["tables"][store][table]
                del data["expected_counts"][store][table]
                result = self.receipt(data)
                self.assertEqual(
                    result["families"]["data_conformance"]["status"], "undetermined"
                )
                self.assertEqual(result["checker_invocations_completed"], 0)

    def test_missing_source_identity_is_not_fabricated(self):
        data = copy.deepcopy(self.fixture)
        del data["source_commit"]
        result = self.receipt(data)
        self.assertEqual(
            result["families"]["data_conformance"]["status"], "undetermined"
        )
        self.assertNotIn("source_commit", result["source"])
        self.assertNotIn("engine", result)

    def test_invalid_timeout_produces_failure_receipt(self):
        for timeout in (0, -1, 601, float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                result = self.receipt(self.fixture, timeout)
                self.assertEqual(
                    result["families"]["data_conformance"]["status"], "undetermined"
                )
                self.assertEqual(result["checker_invocations_completed"], 0)

    def test_checker_failure_and_malformed_report(self):
        for code, raw in (
            (2, b""),
            (0, b"not-json"),
            (0, b"[]"),
            (0, b'{"status":"pass"}'),
            (0, b'{"status":"unknown"}'),
        ):
            with self.subTest(returncode=code, report=raw):
                process = subprocess.CompletedProcess(
                    ["checker"], code, raw, b"raw diagnostic"
                )
                with patch("instance_model.run_checker", return_value=process):
                    result = self.receipt(self.fixture)
                self.assertEqual(
                    result["families"]["data_conformance"]["status"], "undetermined"
                )
                self.assertEqual(result["checker_invocations_completed"], 0)
                self.assertEqual(result["checker_returncode"], code)
                self.assertIsNone(result["engine_evaluation_count"])
                self.assertNotIn("engine", result)


def assert_contract(test, result):
    jsonschema.validate(result, json.loads(instance_model.RESULT_SCHEMA.read_text()))
    test.assertEqual(result["schema_version"], 1)
    test.assertNotIn("verified", result)
    for name, family in result["families"].items():
        test.assertTrue(family["scope"])
        test.assertTrue(family["reason"])
        if name != "data_conformance":
            test.assertEqual(family["status"], "not_run")


class AdmissionReceiptTests(unittest.TestCase):
    """Input failures need no product fixture and must not skip with that cohort."""

    def test_nonobject_input_produces_common_receipt(self):
        for data in ([], None, "invalid", 1):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as temp:
                result = validate(data, Path(temp))
                assert_contract(self, result)
                self.assertEqual(
                    result["families"]["data_conformance"]["status"], "undetermined"
                )
                self.assertNotIn("source", result)

    def test_cli_input_failures_write_receipts(self):
        for raw in (None, b"{", b"\xff", b"[]", b"null"):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temp:
                input_path, output = Path(temp) / "input.json", Path(temp) / "out"
                if raw is not None:
                    input_path.write_bytes(raw)
                run = subprocess.run(
                    [
                        sys.executable,
                        str(instance_model.HERE / "instance_model.py"),
                        str(input_path),
                        str(output),
                    ],
                    capture_output=True,
                )
                self.assertEqual(run.returncode, 2, run.stderr)
                result = json.loads((output / "result.json").read_text())
                assert_contract(self, result)
                self.assertEqual(json.loads(run.stdout), result)
                self.assertNotIn("source", result)
                self.assertNotIn("engine", result)

    def test_timeout_preserves_partial_engine_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            error = subprocess.TimeoutExpired(
                "checker", 1, output=b"partial stdout", stderr=b"partial stderr"
            )
            with patch("instance_model.subprocess.run", side_effect=error):
                with self.assertRaises(subprocess.TimeoutExpired):
                    instance_model.run_checker(output, 1)
            self.assertEqual((output / "engine.stdout").read_bytes(), b"partial stdout")
            self.assertEqual((output / "engine.stderr").read_bytes(), b"partial stderr")

    def test_checker_stderr_preserved_on_failed_process(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            process = subprocess.CompletedProcess(
                ["checker"], 7, b"bad output", b"raw failure"
            )
            with patch("instance_model.subprocess.run", return_value=process):
                returned = instance_model.run_checker(output, 1)
            self.assertEqual(returned.returncode, 7)
            self.assertEqual((output / "engine.stdout").read_bytes(), b"bad output")
            self.assertEqual((output / "engine.stderr").read_bytes(), b"raw failure")


if __name__ == "__main__":
    unittest.main()
