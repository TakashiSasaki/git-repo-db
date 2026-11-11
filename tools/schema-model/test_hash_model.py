"""F1-B producer evidence, input coverage and synthetic hash counterexamples."""

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import hash_profile
from instance_model import validate, value
from test_instance_model import assert_contract


class HashPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "HASH_FIXTURE" not in os.environ:
            raise unittest.SkipTest(
                "run verified --profile filesystem-hash-v1 producer"
            )
        cls.fixture = json.loads(Path(os.environ["HASH_FIXTURE"]).read_text())
        if cls.fixture.get("profile") != hash_profile.PROFILE:
            raise ValueError("wrong hash fixture profile")

    def result(self, data):
        with tempfile.TemporaryDirectory() as temp:
            result = validate(data, Path(temp))
            assert_contract(self, result)
            self.assertEqual(
                result, json.loads((Path(temp) / "result.json").read_text())
            )
            return result

    def row(self, data, name):
        key = data["hash_cases"][name]
        return next(
            r
            for r in data["tables"]["filesystem"]["entries"]
            if [
                value(r["namespace_uuid"]),
                value(r["scan_uuid"]),
                value(r["relative_path"]).hex(),
            ]
            == key
        )

    def synthetic(self):
        data = copy.deepcopy(self.fixture)
        # This input intentionally does not claim all positive-profile scenarios.
        # Keep every extracted occurrence/count; evaluate invalid data with the
        # same shapes through the existing unrestricted values projection profile.
        data["profile"] = "values"
        data["scope"] = (
            "synthetic extracted-JSON counterexample, not product admission or a positive hash fixture"
        )
        return data

    def assert_status(self, data, status):
        result = self.result(data)
        self.assertEqual(result["families"]["data_conformance"]["status"], status)
        if status in ("pass", "fail"):
            self.assertEqual(result["checker_invocations_completed"], 1)
        else:
            self.assertEqual(result["checker_invocations_completed"], 0)

    def test_real_scanner_and_sqlite_controls(self):
        api = self.fixture["api"]
        self.assertEqual(api["hash_profile_verify"], "ok")
        self.assertEqual(api["empty_file_sha256"], hashlib.sha256(b"").hexdigest())
        for state in ("changed", "error"):
            control = api["hash_scanner_controls"][state]
            self.assertEqual(control["status"], state)
            self.assertIsNone(control["digest"])
            self.assertIsNotNone(control["error"])
            self.assertEqual(control["scan_status"], "partial")
            self.assertTrue(control["enumeration_complete"])
            self.assertFalse(control["hashing_complete"])
        self.assertEqual(len(api["hash_sqlite_rejections"]), 14)
        self.assertTrue(
            all("CHECK" in s for s in api["hash_sqlite_rejections"].values())
        )

    def test_positive_profile_and_source_bound_coverage(self):
        result = self.result(self.fixture)
        self.assertEqual(result["families"]["data_conformance"]["status"], "pass")
        for shape, count in (("EntryShape", 15), ("ScanShape", 9), ("OutcomeShape", 7)):
            self.assertEqual(result["coverage"][shape]["expected"], count)
            self.assertEqual(result["coverage"][shape]["selected"], count)
        self.assertIn("hash_profile.py", result["digests"])
        self.assertEqual(result["source"]["hash_cases"], self.fixture["hash_cases"])
        self.assertIn(
            "tools/schema-model/hash_profile.py", result["source"]["producer_inputs"]
        )

    def test_digest_null_and_lexical_negatives(self):
        for digest in (None, "", "a" * 63, "g" * 64, "A" * 64, "a" * 64 + "\n"):
            with self.subTest(digest=digest):
                data = self.synthetic()
                self.row(data, "complete")["sha256"] = {
                    "type": "null" if digest is None else "text",
                    "value": digest,
                }
                self.assert_status(data, "fail")

    def test_failure_never_retains_success_digest(self):
        for state in ("changed", "error"):
            with self.subTest(state=state):
                data = self.synthetic()
                self.row(data, state)["sha256"] = {"type": "text", "value": "a" * 64}
                self.assert_status(data, "fail")

    def test_failed_hash_requires_reason_but_empty_is_present(self):
        for state in ("changed", "error"):
            with self.subTest(state=state):
                data = self.synthetic()
                self.row(data, state)["error"] = {"type": "text", "value": ""}
                self.assert_status(data, "pass")
                self.row(data, state)["error"] = {"type": "null", "value": None}
                key = data["hash_cases"][state][:2]
                outcome = next(
                    r
                    for r in data["tables"]["filesystem"]["scan_outcomes"]
                    if [value(r["namespace_uuid"]), value(r["scan_uuid"])] == key
                )
                outcome["error_count"]["value"] = 0
                self.assert_status(data, "fail")

    def test_nonfiles_cannot_have_digest_or_hash_state(self):
        for name in ("directory", "symlink", "special", "unknown"):
            with self.subTest(kind=name):
                data = self.synthetic()
                self.row(data, name)["sha256"] = {"type": "text", "value": "a" * 64}
                self.row(data, name)["hash_status"]["value"] = "complete"
                self.assert_status(data, "fail")

    def test_regular_file_size_and_status(self):
        for field, kind, invalid in (
            ("size", "null", None),
            ("size", "integer", -1),
            ("hash_status", "text", "not-applicable"),
            ("hash_status", "text", "pending"),
            ("hash_status", "text", "unknown"),
        ):
            with self.subTest(field=field, invalid=invalid):
                data = self.synthetic()
                self.row(data, "complete")[field] = {"type": kind, "value": invalid}
                if field == "hash_status":
                    self.row(data, "complete")["sha256"] = {
                        "type": "null",
                        "value": None,
                    }
                self.assert_status(data, "fail")

    def test_no_invented_nonfile_size_or_success_error_rule(self):
        self.assertEqual(value(self.row(self.fixture, "special")["size"]), 0)
        self.assertEqual(
            value(self.row(self.fixture, "complete_with_error")["error"]), ""
        )
        self.assert_status(self.fixture, "pass")

    def test_absent_hash_state_coverage_never_passes(self):
        data = copy.deepcopy(self.fixture)
        self.row(data, "changed")["hash_status"]["value"] = "error"
        self.assert_status(data, "undetermined")

    def test_missing_case_or_occurrence_never_passes(self):
        for mode in ("case", "row", "kind"):
            with self.subTest(mode=mode):
                data = copy.deepcopy(self.fixture)
                if mode == "case":
                    del data["hash_cases"]["error"]
                elif mode == "row":
                    data["tables"]["filesystem"]["entries"].remove(
                        self.row(data, "error")
                    )
                    data["expected_counts"]["filesystem"]["entries"] -= 1
                else:
                    self.row(data, "special")["kind"]["value"] = "symlink"
                self.assert_status(data, "undetermined")

    def test_missing_columns_and_wrong_sql_types_are_undetermined(self):
        for field in ("kind", "hash_status", "size", "sha256"):
            with self.subTest(field=field):
                data = self.synthetic()
                del self.row(data, "complete")[field]
                self.assert_status(data, "undetermined")
        for field, kind, raw in (("size", "text", "0"), ("sha256", "integer", 3)):
            with self.subTest(field=field):
                data = self.synthetic()
                self.row(data, "complete")[field] = {"type": kind, "value": raw}
                self.assert_status(data, "undetermined")

    def test_unknown_kind_is_not_unknown_hash_status(self):
        row = self.row(self.fixture, "unknown")
        self.assertEqual(value(row["kind"]), "unknown")
        self.assertEqual(value(row["hash_status"]), "not-applicable")
        self.assertIsNone(value(row["sha256"]))

    def test_shape_digest_is_not_byte_equality_proof(self):
        data = self.synthetic()
        self.row(data, "complete")["sha256"] = {"type": "text", "value": "f" * 64}
        self.assert_status(data, "pass")
        self.assertNotEqual("f" * 64, self.fixture["api"]["empty_file_sha256"])


if __name__ == "__main__":
    unittest.main()
