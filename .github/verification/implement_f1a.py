"""Apply the bounded F1-A increment to the pinned, clean pilot source."""
from pathlib import Path
import hashlib
import json

ROOT = Path.cwd()
HERE = ROOT / 'tools/schema-model'

def replace_once(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one patch anchor in {path}: {old[:80]!r}')
    path.write_text(text.replace(old, new, 1))

PROFILE = r'''"""Fixed F1-A witnesses, not a general catalog loader or SQL proof."""

from __future__ import annotations

from contextlib import closing
import os
import sqlite3
from unittest.mock import patch

PROFILE = "filesystem-outcomes-v1"
EXPECTED_FS_COUNTS = {
    "catalog_metadata": 5,
    "scans": 6,
    "entries": 8,
    "scan_outcomes": 4,
}
EXPECTED_STATUSES = {
    "complete": "complete",
    "partial": "partial",
    "interrupted": "interrupted",
    "empty_partial": "partial",
    "incomplete": None,
}


def populate(catalog, root, api, unfinished_scan):
    """Use real scan(), with a bounded interruption and explicit SQL witnesses."""
    from repo_catalog.filesystem import FilesystemCatalog, FilesystemError
    from repo_catalog.filesystem.models import occurrence_uuid
    from repo_catalog.filesystem import store

    complete_root = root / "complete-root"
    complete_root.mkdir()
    (complete_root / "empty").write_bytes(b"")
    complete = catalog.scan(complete_root)
    partial = catalog.scan(root / "missing-root")
    interrupted_root = root / "interrupted-root"
    interrupted_root.mkdir()
    (interrupted_root / "file").write_bytes(b"bounded witness")
    original = store.walk

    def interrupted_walk(*args):
        with closing(original(*args)) as iterator:
            yield next(iterator)
            raise KeyboardInterrupt("controlled F1-A interruption")

    old_scans = {s.scan_uuid for s in catalog.list_scans()}
    with patch.object(store, "walk", interrupted_walk):
        try:
            catalog.scan(interrupted_root)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("scan swallowed the controlled interruption")
    new_scans = [s for s in catalog.list_scans() if s.scan_uuid not in old_scans]
    if len(new_scans) != 1:
        raise AssertionError("interruption did not preserve exactly one scan")
    interrupted = new_scans[0]
    assert complete.status == "complete" and complete.entries == 2
    assert partial.status == "partial" and partial.errors == 1
    assert interrupted.status == "interrupted" and interrupted.entries == 1
    assert complete.enumeration_complete and complete.hashing_complete
    assert not partial.enumeration_complete and not partial.hashing_complete
    assert not interrupted.enumeration_complete and not interrupted.hashing_complete

    # SQL/API permits an empty partial observation. This is NOT a scanner trace.
    empty_scan = occurrence_uuid()
    with catalog._db:
        catalog._db.execute(
            "INSERT INTO scans VALUES (?,?,?,?,?)",
            (catalog.namespace_uuid, empty_scan, os.fsencode(root), 1, "[]"),
        )
        catalog._db.execute(
            "INSERT INTO scan_outcomes VALUES (?,?,?,?,?,?)",
            (catalog.namespace_uuid, empty_scan, 1, "partial", 0, 0),
        )
    catalog.verify()
    cases = {
        "complete": complete.scan_uuid,
        "partial": partial.scan_uuid,
        "interrupted": interrupted.scan_uuid,
        "empty_partial": empty_scan,
        "incomplete": unfinished_scan,
    }
    api["outcome_statuses"] = {
        name: catalog.get_scan(scan).status for name, scan in cases.items()
    }
    api["outcome_completeness"] = {
        name: [catalog.get_scan(scan).enumeration_complete,
               catalog.get_scan(scan).hashing_complete]
        for name, scan in cases.items()
    }
    api["outcome_verify"] = catalog.verify()["integrity"]

    # Guards remain enabled. DDL rejects status; API adds cross-row checks.
    controls = {}
    for label, status, count, errors, rejected_by in (
        ("invalid_status", "incomplete", 1, 1, "sqlite"),
        ("entry_count", "partial", 2, 1, "api"),
        ("error_count", "partial", 1, 0, "api"),
        ("complete_with_error", "complete", 1, 1, "api"),
        ("empty_error_is_present", "partial", 1, 1, None),
    ):
        with FilesystemCatalog.initialize(root / (label + ".db")) as bad:
            scan = occurrence_uuid()
            with bad._db:
                bad._db.execute(
                    "INSERT INTO scans VALUES (?,?,?,?,?)",
                    (bad.namespace_uuid, scan, os.fsencode(root), 1, "[]"),
                )
                bad._db.execute(
                    "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (bad.namespace_uuid, scan, b"", "directory", None,
                     None, None, None, None, None, None, "not-applicable",
                     "", None, None),
                )
            try:
                with bad._db:
                    bad._db.execute(
                        "INSERT INTO scan_outcomes VALUES (?,?,?,?,?,?)",
                        (bad.namespace_uuid, scan, 1, status, count, errors),
                    )
            except sqlite3.IntegrityError as exc:
                if rejected_by != "sqlite":
                    raise
                controls[label] = {"stage": "sqlite", "reason": str(exc)}
                continue
            if rejected_by == "sqlite":
                raise AssertionError("DDL accepted an invalid terminal status")
            try:
                bad.verify()
            except FilesystemError as exc:
                if rejected_by != "api":
                    raise
                controls[label] = {"stage": "api", "reason": str(exc)}
            else:
                if rejected_by is not None:
                    raise AssertionError("API accepted inconsistent outcome: " + label)
                controls[label] = {"stage": "accepted", "reason": "empty text is non-NULL"}
    api["outcome_controls"] = controls
    return {name: [catalog.namespace_uuid, scan] for name, scan in cases.items()}


def check_coverage(data, decoded):
    """Admit declared construction coverage independently of generated RDF."""
    profile = data.get("profile", "values")
    if profile == "values":
        return
    if profile != PROFILE:
        raise ValueError("unsupported instance fixture profile")
    if data["expected_counts"]["filesystem"] != EXPECTED_FS_COUNTS:
        raise ValueError("F1-A fixed construction counts missing")
    cases = data["outcome_cases"]
    if not isinstance(cases, dict) or set(cases) != set(EXPECTED_STATUSES):
        raise ValueError("F1-A required scenario declarations missing")
    scans = {
        (r["namespace_uuid"], r["scan_uuid"])
        for (store, table, _), r in decoded.items()
        if store == "filesystem" and table == "scans"
    }
    outcomes = [
        r for (store, table, _), r in decoded.items()
        if store == "filesystem" and table == "scan_outcomes"
    ]
    seen = set()
    for name, expected in EXPECTED_STATUSES.items():
        key = cases[name]
        if (not isinstance(key, list) or len(key) != 2
                or any(type(v) is not str for v in key)):
            raise ValueError("malformed F1-A qualified scenario key")
        key = tuple(key)
        if key in seen or key not in scans:
            raise ValueError("F1-A scenario scan missing or repeated")
        seen.add(key)
        rows = [r for r in outcomes if (r["namespace_uuid"], r["scan_uuid"]) == key]
        if len(rows) != (0 if expected is None else 1):
            raise ValueError("F1-A required outcome occurrence missing or repeated")
        # A valid but different state no longer covers this positive scenario.
        # An invalid enum remains admitted to the SHACL negative control.
        if rows and rows[0]["status"] in ("complete", "partial", "interrupted"):
            if rows[0]["status"] != expected:
                raise ValueError("F1-A declared terminal scenario not covered")
'''
(HERE / 'outcome_profile.py').write_text(PROFILE)

p = HERE / 'instance_fixture.py'
replace_once(p, 'import base64\n', 'import argparse\nimport base64\n')
replace_once(p, 'from uuid import uuid4\n', 'from uuid import uuid4\n\nimport outcome_profile\n')
replace_once(p, 'def produce():\n', 'def produce(profile="values"):\n    if profile not in ("values", outcome_profile.PROFILE):\n        raise ValueError("unsupported fixture profile")\n    outcome_cases = None\n')
replace_once(p, '        with FilesystemCatalog.initialize(root / "invalid-ns.db") as bad:\n', '            if profile == outcome_profile.PROFILE:\n                outcome_cases = outcome_profile.populate(fs, root, api, scans[0])\n        with FilesystemCatalog.initialize(root / "invalid-ns.db") as bad:\n')
replace_once(p, '        expected = {\n', '''        helper = Path(outcome_profile.__file__).resolve()
        helper_relative = helper.relative_to(repo).as_posix()
        if helper.read_bytes() != subprocess.check_output(
            ["git", "-C", str(repo), "show", "HEAD:" + helper_relative]
        ):
            raise ValueError("producer helper differs from HEAD")
        producer_inputs = {helper_relative: hashlib.sha256(helper.read_bytes()).hexdigest()}
        expected = {
''')
replace_once(p, '        if {\n            s: {t: len(r) for t, r in ts.items()} for s, ts in tables.items()\n        } != expected:\n', '        if profile == outcome_profile.PROFILE:\n            expected["filesystem"] = dict(outcome_profile.EXPECTED_FS_COUNTS)\n        if {\n            s: {t: len(r) for t, r in ts.items()} for s, ts in tables.items()\n        } != expected:\n')
replace_once(p, '            "version": 1,\n', '            "version": 1,\n            "profile": profile,\n            "outcome_cases": outcome_cases,\n            "producer_inputs": producer_inputs,\n')
replace_once(p, '            "scope": "disposable synthetic fixture, not scanner execution or retained data",\n', '''            "scope": (
                "disposable real complete/partial/interrupted scanner witnesses plus explicit SQL-only value and empty-partial witnesses"
                if profile == outcome_profile.PROFILE
                else "disposable synthetic fixture, not scanner execution or retained data"
            ),
''')
replace_once(p, '    print(json.dumps(produce(), sort_keys=True, indent=2))', '''    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("values", outcome_profile.PROFILE), default="values")
    print(json.dumps(produce(parser.parse_args().profile), sort_keys=True, indent=2))''')

p = HERE / 'instance_model.py'
replace_once(p, 'import jsonschema\n', 'import jsonschema\nimport outcome_profile\n')
replace_once(p, 'SCOPE = "fixed disposable FS/WT Entry/Scan/Outcome/ExternalReference shapes; no external target resolution"', 'SCOPE = "disposable FS/WT representation and selected Filesystem outcome constraints; no external target resolution"')
replace_once(p, '    scan_nodes = {}\n', '    outcome_profile.check_coverage(data, decoded)\n    scan_nodes = {}\n')
replace_once(p, '            if table == "scan_outcomes" and parent is not None:\n                g.add((parent, M.outcome, node))\n', '''            if table == "scan_outcomes":
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
''')
replace_once(p, '            if table == "entries":\n                path = row["relative_path"]\n', '''            if table == "entries":
                error = row["error"]
                if error is not None and type(error) is not str:
                    raise ValueError("entry error must be SQLite TEXT or NULL")
                g.add((node, M.hasError, Literal(error is not None, datatype=XSD.boolean)))
                g.add((node, M.error, M.SqlNull if error is None else Literal(error)))
                path = row["relative_path"]
''')
replace_once(p, '                "expected_counts",\n', '                "expected_counts",\n                "profile",\n                "outcome_cases",\n                "producer_inputs",\n')
replace_once(p, '            "instance_fixture.py",\n', '            "instance_fixture.py",\n            "outcome_profile.py",\n')
replace_once(p, '            "Zero OutcomeShape targets are explicitly not_applicable; terminal scan behavior is not exercised.",\n', '''            "Terminal records describe retained observations, not atomic filesystem snapshots or every interruption path.",
''')
replace_once(p, '        result["fixture_expectation"] = None\n', '''        if not data["expected_counts"]["filesystem"]["scan_outcomes"]:
            result["unformalized"].append(
                "Zero OutcomeShape targets are explicitly not_applicable; terminal scan behavior is not exercised."
            )
        result["fixture_expectation"] = None
''')

SHAPES = '''@prefix m: <urn:git-repo-db:instance-pilot:v1:> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

m:EntryShape a sh:NodeShape; sh:targetClass m:Entry;
 sh:property [sh:path m:pathBytes; sh:minCount 1; sh:maxCount 1; sh:datatype xsd:base64Binary];
 sh:property [sh:path m:parent; sh:minCount 1; sh:maxCount 1; sh:class m:Scan];
 sh:property [sh:path m:hasError; sh:minCount 1; sh:maxCount 1; sh:datatype xsd:boolean];
 sh:sparql [sh:message "Duplicate complete entry semantic key"; sh:select """
 PREFIX m: <urn:git-repo-db:instance-pilot:v1:>
 SELECT $this WHERE { $this m:semanticKey ?key . ?other a m:Entry; m:semanticKey ?key . FILTER ($this != ?other) }
 """] .
m:OutcomeShape a sh:NodeShape; sh:targetClass m:Outcome;
 sh:property [sh:path m:parent; sh:minCount 1; sh:maxCount 1; sh:class m:Scan];
 sh:property [sh:path m:status; sh:minCount 1; sh:maxCount 1; sh:in ("complete" "partial" "interrupted")];
 sh:property [sh:path m:entryCount; sh:minCount 1; sh:maxCount 1; sh:datatype xsd:integer; sh:minInclusive 0];
 sh:property [sh:path m:errorCount; sh:minCount 1; sh:maxCount 1; sh:datatype xsd:integer; sh:minInclusive 0];
 sh:property [sh:path m:finishedUs; sh:minCount 1; sh:maxCount 1; sh:datatype xsd:integer; sh:minExclusive 0];
 sh:sparql [sh:message "Outcome entry count differs from its own scan observations"; sh:select """
 PREFIX m: <urn:git-repo-db:instance-pilot:v1:>
 SELECT $this WHERE {
   $this m:parent ?scan; m:entryCount ?declared .
   OPTIONAL { ?entry a m:Entry; m:parent ?scan . }
 } GROUP BY $this ?declared HAVING (COUNT(?entry) != ?declared)
 """];
 sh:sparql [sh:message "Outcome error count differs from SQL non-NULL errors"; sh:select """
 PREFIX m: <urn:git-repo-db:instance-pilot:v1:>
 SELECT $this WHERE {
   $this m:parent ?scan; m:errorCount ?declared .
   OPTIONAL { ?entry a m:Entry; m:parent ?scan; m:hasError true . }
 } GROUP BY $this ?declared HAVING (COUNT(?entry) != ?declared)
 """];
 sh:sparql [sh:message "Complete outcome has observed errors"; sh:select """
 PREFIX m: <urn:git-repo-db:instance-pilot:v1:>
 SELECT $this WHERE {
   $this m:parent ?scan; m:status "complete" .
   ?entry a m:Entry; m:parent ?scan; m:hasError true .
 }
 """] .
m:ScanShape a sh:NodeShape; sh:targetClass m:Scan;
 sh:property [sh:path m:outcome; sh:maxCount 1; sh:class m:Outcome] .
m:ReferenceShape a sh:NodeShape; sh:targetClass m:ExternalReference;
 sh:property [sh:path m:resolution; sh:hasValue "unresolved"; sh:minCount 1; sh:maxCount 1];
 sh:property [sh:path m:worktree; sh:minCount 1; sh:maxCount 1; sh:class m:Worktree] .
'''
(HERE / 'instance_shapes.ttl').write_text(SHAPES)
p = HERE / 'instance_constraints.json'
manifest = json.loads(p.read_text())
manifest['shapes_sha256'] = hashlib.sha256(SHAPES.encode()).hexdigest()
manifest['authority'].append('packages/filesystem/src/repo_catalog/filesystem/store.py')
manifest['constraints']['EntryShape'] += '; exact SQL non-NULL error presence'
manifest['constraints']['OutcomeShape'] = 'same-snapshot scan FK, terminal enum, nonnegative per-scan entry/error counts, positive finish time and no complete-with-errors; SQLite DDL plus FilesystemCatalog.verify'
p.write_text(json.dumps(manifest, indent=2) + '\n')

TESTS = r'''"""F1-A controls: real producer evidence and separate synthetic counterexamples."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

import instance_model
from instance_model import M, project, validate, value
from outcome_profile import EXPECTED_STATUSES, PROFILE
from rdflib import RDF
from test_instance_model import assert_contract


class OutcomePilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "OUTCOME_FIXTURE" not in os.environ:
            raise unittest.SkipTest("run verified --profile filesystem-outcomes-v1 producer")
        cls.fixture = json.loads(Path(os.environ["OUTCOME_FIXTURE"]).read_text())
        if cls.fixture.get("profile") != PROFILE:
            raise ValueError("wrong outcome fixture profile")

    def result(self, data):
        with tempfile.TemporaryDirectory() as temp:
            result = validate(data, Path(temp))
            assert_contract(self, result)
            self.assertEqual(result, json.loads((Path(temp) / "result.json").read_text()))
            return result

    def outcome(self, data, name):
        key = data["outcome_cases"][name]
        return next(r for r in data["tables"]["filesystem"]["scan_outcomes"]
                    if [value(r["namespace_uuid"]), value(r["scan_uuid"])] == key)

    def entry(self, data, name):
        key = data["outcome_cases"][name]
        return next(r for r in data["tables"]["filesystem"]["entries"]
                    if [value(r["namespace_uuid"]), value(r["scan_uuid"])] == key)

    def test_real_api_witnesses(self):
        api = self.fixture["api"]
        self.assertEqual(api["outcome_verify"], "ok")
        self.assertEqual(api["outcome_statuses"], {
            k: v if v is not None else "incomplete" for k, v in EXPECTED_STATUSES.items()
        })
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
        self.assertFalse(any("terminal scan behavior is not exercised" in s
                             for s in result["unformalized"]))

    def test_incomplete_and_zero_entry_partial_remain_legitimate(self):
        graph = project(self.fixture)
        self.assertEqual(len(set(graph.subjects(RDF.type, M.Scan))), 6)
        self.assertEqual(len(set(graph.subjects(RDF.type, M.Outcome))), 4)
        self.assertEqual(value(self.outcome(self.fixture, "empty_partial")["entry_count"]), 0)
        self.assertEqual(self.result(self.fixture)["families"]["data_conformance"]["status"], "pass")

    def test_synthetic_count_mismatches(self):
        for name, field in (("complete", "entry_count"), ("partial", "error_count"),
                            ("empty_partial", "entry_count")):
            with self.subTest(case=name, field=field):
                data = copy.deepcopy(self.fixture)
                self.outcome(data, name)[field]["value"] += 1
                self.assertEqual(self.result(data)["families"]["data_conformance"]["status"], "fail")

    def test_synthetic_complete_with_error(self):
        data = copy.deepcopy(self.fixture)
        self.entry(data, "complete")["error"] = {"type": "text", "value": ""}
        self.outcome(data, "complete")["error_count"]["value"] = 1
        self.assertEqual(self.result(data)["families"]["data_conformance"]["status"], "fail")

    def test_empty_error_is_not_null(self):
        data = copy.deepcopy(self.fixture)
        self.entry(data, "partial")["error"] = {"type": "text", "value": ""}
        self.assertEqual(self.result(data)["families"]["data_conformance"]["status"], "pass")
        self.entry(data, "partial")["error"] = {"type": "null", "value": None}
        self.assertEqual(self.result(data)["families"]["data_conformance"]["status"], "fail")

    def test_synthetic_invalid_status_and_count_time_ranges(self):
        for field, invalid in (("status", "incomplete"), ("entry_count", -1),
                               ("error_count", -1), ("finished_us", 0)):
            with self.subTest(field=field):
                data = copy.deepcopy(self.fixture)
                self.outcome(data, "complete")[field]["value"] = invalid
                self.assertEqual(self.result(data)["families"]["data_conformance"]["status"], "fail")

    def test_missing_fields_are_not_null(self):
        for table, field in (("scan_outcomes", "entry_count"),
                             ("scan_outcomes", "finished_us"), ("entries", "error")):
            with self.subTest(table=table, field=field):
                data = copy.deepcopy(self.fixture)
                del data["tables"]["filesystem"][table][0][field]
                result = self.result(data)
                self.assertEqual(result["families"]["data_conformance"]["status"], "undetermined")
                self.assertEqual(result["checker_invocations_completed"], 0)

    def test_missing_outcomes_cannot_be_declared_empty(self):
        data = copy.deepcopy(self.fixture)
        data["tables"]["filesystem"]["scan_outcomes"] = []
        data["expected_counts"]["filesystem"]["scan_outcomes"] = 0
        result = self.result(data)
        self.assertEqual(result["families"]["data_conformance"]["status"], "undetermined")
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
                self.assertEqual(self.result(data)["families"]["data_conformance"]["status"], "undetermined")

    def test_no_invented_clock_ordering(self):
        data = copy.deepcopy(self.fixture)
        self.outcome(data, "complete")["finished_us"]["value"] = 1
        self.assertEqual(self.result(data)["families"]["data_conformance"]["status"], "pass")

    def test_unknown_profile_and_invalid_sql_cell_type(self):
        data = copy.deepcopy(self.fixture)
        data["profile"] = "unsupported"
        self.assertEqual(self.result(data)["families"]["data_conformance"]["status"], "undetermined")
        data = copy.deepcopy(self.fixture)
        self.outcome(data, "complete")["entry_count"] = {"type": "text", "value": "2"}
        self.assertEqual(self.result(data)["families"]["data_conformance"]["status"], "undetermined")


if __name__ == "__main__":
    unittest.main()
'''
(HERE / 'test_outcome_model.py').write_text(TESTS)

p = HERE / 'INSTANCE-PILOT.md'
with p.open('a') as f:
    f.write('''
## F1-A: terminal outcome profile

The default `values` profile above remains the original representation pilot.
The additive `filesystem-outcomes-v1` profile retains its two unfinished scans
and adds real `scan()` complete, missing-root partial and controlled-interruption
witnesses. It also adds a SQL-only zero-entry partial witness; that case is not
scanner execution. The profile has six FS scans, eight entries and four outcomes.

```sh
scripts/local-run.sh python tools/schema-model/instance_fixture.py \\
  --profile filesystem-outcomes-v1 > /tmp/outcomes.json
uv run --project tools/schema-model --locked --offline python \\
  tools/schema-model/instance_model.py /tmp/outcomes.json /tmp/outcomes-result
OUTCOME_FIXTURE=/tmp/outcomes.json uv run --project tools/schema-model --locked --offline \\
  python -m unittest discover -s tools/schema-model -p test_outcome_model.py -q
```

Construction counts and qualified scenario identities are checked before RDF
coverage. Missing required outcome occurrences are not legitimate zero-target
coverage for this profile. The original unfinished scans remain legitimate.
Selected shapes check terminal enum, positive finish time, same-scan counts,
SQL non-NULL error presence (including empty error strings), and complete-with-error
contradictions. `partial` does not imply a positive error count. Clock ordering
and atomic filesystem snapshots are not asserted. Original bytes, native times,
NULL and row occurrences retain the existing encoding.

The producer separately demonstrates SQLite rejection of invalid status and API
rejection of inconsistent counts/complete-with-errors, with guards enabled.
Counterexamples in `test_outcome_model.py` are mutations of extracted JSON, not
claims that public scan() admitted invalid observations. Existing result families
and raw diagnostics are unchanged; these tests do not evaluate a state model,
external-reference resolution, hash-state semantics or full implementation proof.
The producer helper is checked against HEAD and hashed separately; source hashes
are consistency bindings, not authentication. Use fresh output directories.
''')

changed = ['instance_fixture.py','instance_model.py','instance_shapes.ttl',
           'instance_constraints.json','outcome_profile.py','test_outcome_model.py','INSTANCE-PILOT.md']
print(json.dumps({'changed_files':['tools/schema-model/'+p for p in changed],
                  'shapes_sha256':manifest['shapes_sha256']}))
