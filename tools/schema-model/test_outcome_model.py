"""F1-A controls: real producer evidence and separate synthetic counterexamples."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from instance_model import M, project, validate, value
from outcome_profile import EXPECTED_STATUSES, PROFILE
from rdflib import RDF
from test_instance_model import assert_contract


class OutcomePilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "OUTCOME_FIXTURE" not in os.environ:
            raise unittest.SkipTest(
                "run verified --profile filesystem-outcomes-v1 producer"
            )
        cls.fixture = json.loads(Path(os.environ["OUTCOME_FIXTURE"]).read_text())
        if cls.fixture.get("profile") != PROFILE:
            raise ValueError("wrong outcome fixture profile")

    def result(self, data):
        with tempfile.TemporaryDirectory() as temp:
            result = validate(data, Path(temp))
            assert_contract(self, result)
            self.assertEqual(
                result, json.loads((Path(temp) / "result.json").read_text())
            )
            return result

    def outcome(self, data, name):
        key = data["outcome_cases"][name]
        return next(
            r
            for r in data["tables"]["filesystem"]["scan_outcomes"]
            if [value(r["namespace_uuid"]), value(r["scan_uuid"])] == key
        )

    def entry(self, data, name):
        key = data["outcome_cases"][name]
        return next(
            r
            for r in data["tables"]["filesystem"]["entries"]
            if [value(r["namespace_uuid"]), value(r["scan_uuid"])] == key
        )

    def test_real_api_witnesses(self):
        api = self.fixture["api"]
        self.assertEqual(api["outcome_verify"], "ok")
        self.assertEqual(
            api["outcome_statuses"],
            {
                k: v if v is not None else "incomplete"
                for k, v in EXPECTED_STATUSES.items()
            },
        )
        self.assertEqual(api["outcome_completeness"]["complete"], [True, True])
        for name in ("partial", "interrupted", "incomplete"):
            self.assertEqual(api["outcome_completeness"][name], [False, False])
        controls = api["outcome_controls"]
        self.assertEqual(controls["invalid_status"]["stage"], "sqlite")
        for name in ("entry_count", "error_count", "complete_with_error"):
            self.assertEqual(controls[name]["stage"], "api")
        self.assertEqual(controls["empty_error_is_present"]["stage"], "accepted")

    def test_positive_nonvacuous_outcomes(self):
        result = self.result(self.fixture)
        self.assertEqual(result["families"]["data_conformance"]["status"], "pass")
        coverage = result["coverage"]["OutcomeShape"]
        self.assertEqual((coverage["expected"], coverage["selected"]), (4, 4))
        self.assertEqual(coverage["coverage"], "selected")
        self.assertEqual(result["checker_invocations_completed"], 1)
        self.assertIsNone(coverage["engine_evaluation_count"])
        self.assertEqual(result["source"]["profile"], PROFILE)
        self.assertIn("outcome_profile.py", result["digests"])
        self.assertFalse(
            any(
                "terminal scan behavior is not exercised" in s
                for s in result["unformalized"]
            )
        )

    def test_incomplete_and_zero_entry_partial_remain_legitimate(self):
        graph = project(self.fixture)
        self.assertEqual(len(set(graph.subjects(RDF.type, M.Scan))), 6)
        self.assertEqual(len(set(graph.subjects(RDF.type, M.Outcome))), 4)
        self.assertEqual(
            value(self.outcome(self.fixture, "empty_partial")["entry_count"]), 0
        )
        self.assertEqual(
            self.result(self.fixture)["families"]["data_conformance"]["status"], "pass"
        )

    def test_synthetic_count_mismatches(self):
        for name, field in (
            ("complete", "entry_count"),
            ("partial", "error_count"),
            ("empty_partial", "entry_count"),
        ):
            with self.subTest(case=name, field=field):
                data = copy.deepcopy(self.fixture)
                self.outcome(data, name)[field]["value"] += 1
                self.assertEqual(
                    self.result(data)["families"]["data_conformance"]["status"], "fail"
                )

    def test_synthetic_complete_with_error(self):
        data = copy.deepcopy(self.fixture)
        self.entry(data, "complete")["error"] = {"type": "text", "value": ""}
        self.outcome(data, "complete")["error_count"]["value"] = 1
        self.assertEqual(
            self.result(data)["families"]["data_conformance"]["status"], "fail"
        )

    def test_empty_error_is_not_null(self):
        data = copy.deepcopy(self.fixture)
        self.entry(data, "partial")["error"] = {"type": "text", "value": ""}
        self.assertEqual(
            self.result(data)["families"]["data_conformance"]["status"], "pass"
        )
        self.entry(data, "partial")["error"] = {"type": "null", "value": None}
        self.assertEqual(
            self.result(data)["families"]["data_conformance"]["status"], "fail"
        )

    def test_synthetic_invalid_status_and_count_time_ranges(self):
        for field, invalid in (
            ("status", "incomplete"),
            ("entry_count", -1),
            ("error_count", -1),
            ("finished_us", 0),
        ):
            with self.subTest(field=field):
                data = copy.deepcopy(self.fixture)
                self.outcome(data, "complete")[field]["value"] = invalid
                self.assertEqual(
                    self.result(data)["families"]["data_conformance"]["status"], "fail"
                )

    def test_missing_fields_are_not_null(self):
        for table, field in (
            ("scan_outcomes", "entry_count"),
            ("scan_outcomes", "finished_us"),
            ("entries", "error"),
        ):
            with self.subTest(table=table, field=field):
                data = copy.deepcopy(self.fixture)
                del data["tables"]["filesystem"][table][0][field]
                result = self.result(data)
                self.assertEqual(
                    result["families"]["data_conformance"]["status"], "undetermined"
                )
                self.assertEqual(result["checker_invocations_completed"], 0)

    def test_missing_outcomes_cannot_be_declared_empty(self):
        data = copy.deepcopy(self.fixture)
        data["tables"]["filesystem"]["scan_outcomes"] = []
        data["expected_counts"]["filesystem"]["scan_outcomes"] = 0
        result = self.result(data)
        self.assertEqual(
            result["families"]["data_conformance"]["status"], "undetermined"
        )
        self.assertEqual(result["checker_invocations_completed"], 0)

    def test_missing_or_rebound_scenario_is_not_success(self):
        for mode in ("missing", "rebound", "valid_wrong_status"):
            with self.subTest(mode=mode):
                data = copy.deepcopy(self.fixture)
                if mode == "missing":
                    del data["outcome_cases"]["interrupted"]
                elif mode == "rebound":
                    data["outcome_cases"]["partial"] = data["outcome_cases"]["complete"]
                else:
                    self.outcome(data, "interrupted")["status"]["value"] = "complete"
                self.assertEqual(
                    self.result(data)["families"]["data_conformance"]["status"],
                    "undetermined",
                )

    def test_no_invented_clock_ordering(self):
        data = copy.deepcopy(self.fixture)
        self.outcome(data, "complete")["finished_us"]["value"] = 1
        self.assertEqual(
            self.result(data)["families"]["data_conformance"]["status"], "pass"
        )

    def test_unknown_profile_and_invalid_sql_cell_type(self):
        data = copy.deepcopy(self.fixture)
        data["profile"] = "unsupported"
        self.assertEqual(
            self.result(data)["families"]["data_conformance"]["status"], "undetermined"
        )
        data = copy.deepcopy(self.fixture)
        self.outcome(data, "complete")["entry_count"] = {"type": "text", "value": "2"}
        self.assertEqual(
            self.result(data)["families"]["data_conformance"]["status"], "undetermined"
        )


if __name__ == "__main__":
    unittest.main()
