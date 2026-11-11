"""Apply the bounded F1-B child increment to the pinned F1-A source."""
from pathlib import Path
import hashlib
import json

HERE = Path.cwd() / "tools/schema-model"


def replace_once(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"Expected one patch anchor in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1))


HASH_PROFILE = r'''"""Bounded hash witnesses; graph conformance does not establish byte equality."""

from __future__ import annotations

from collections import Counter
import hashlib
import os
import sqlite3
from unittest.mock import patch

PROFILE = "filesystem-hash-v1"
EXPECTED_FS_COUNTS = {
    "catalog_metadata": 5,
    "scans": 9,
    "entries": 15,
    "scan_outcomes": 7,
}
EXPECTED_HASH_COUNTS = {"complete": 3, "changed": 1, "error": 1, "not-applicable": 10}
EXPECTED_KIND_COUNTS = {"file": 5, "directory": 7, "unknown": 1, "symlink": 1, "special": 1}
CASE_NAMES = {"complete", "changed", "error", "symlink", "special",
              "complete_with_error", "unknown", "directory"}


def populate(catalog, root, api, outcome_cases):
    """Exercise scan() plus precisely labeled SQL-only DDL boundary witnesses."""
    from repo_catalog.filesystem import FilesystemCatalog, scanner
    from repo_catalog.filesystem.models import occurrence_uuid

    results = {}
    cases = {}
    for state in ("changed", "error"):
        folder = root / (state + "-root")
        folder.mkdir()
        target = folder / "file"
        target.write_bytes(b"a" * 1024)
        original = scanner.os.read
        mutated = False

        def controlled_read(fd, count):
            nonlocal mutated
            if state == "error":
                raise PermissionError(13, "controlled read failure")
            block = original(fd, count)
            if block and not mutated:
                mutated = True
                target.write_bytes(b"different")
            return block

        with patch.object(scanner.os, "read", controlled_read):
            scan = catalog.scan(folder)
        row = next(e for e in catalog.iter_entries(scan.scan_uuid)
                   if e.relative_path == b"file")
        assert scan.status == "partial" and scan.errors == 1
        assert scan.enumeration_complete and not scan.hashing_complete
        assert row.hash_status == state and row.sha256 is None and row.error is not None
        if state == "changed":
            assert mutated
        results[state] = {"status": row.hash_status, "digest": row.sha256,
                          "error": row.error, "scan_status": scan.status,
                          "enumeration_complete": scan.enumeration_complete,
                          "hashing_complete": scan.hashing_complete}
        cases[state] = [catalog.namespace_uuid, scan.scan_uuid, b"file".hex()]

    # No symlink/device is opened: these are explicitly SQL-only boundary rows.
    # DDL permits non-file size, and complete entry with an error. Do not invent
    # stronger universal rules; the scan itself must not claim complete on errors.
    boundary_scan = occurrence_uuid()
    empty_digest = hashlib.sha256(b"").hexdigest()
    with catalog._db:
        catalog._db.execute("INSERT INTO scans VALUES (?,?,?,?,?)",
                            (catalog.namespace_uuid, boundary_scan, os.fsencode(root), 1, "[]"))
        for name, kind, size, digest, status, error in (
            ("symlink", "symlink", None, None, "not-applicable", None),
            ("special", "special", 0, None, "not-applicable", None),
            ("complete_with_error", "file", 0, empty_digest, "complete", ""),
        ):
            path = name.encode("ascii")
            catalog._db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (catalog.namespace_uuid, boundary_scan, path, kind, size,
                                 None, None, None, None, None, digest, status, error, None, None))
            cases[name] = [catalog.namespace_uuid, boundary_scan, path.hex()]
        catalog._db.execute("INSERT INTO scan_outcomes VALUES (?,?,?,?,?,?)",
                            (catalog.namespace_uuid, boundary_scan, 1, "partial", 3, 1))
    cases["complete"] = [*outcome_cases["complete"], b"empty".hex()]
    cases["directory"] = [*outcome_cases["complete"], ""]
    cases["unknown"] = [*outcome_cases["partial"], ""]
    complete = next(e for e in catalog.iter_entries(outcome_cases["complete"][1])
                    if e.relative_path == b"empty")
    assert complete.sha256 == empty_digest and complete.hash_status == "complete"
    api["hash_scanner_controls"] = results
    api["empty_file_sha256"] = complete.sha256
    api["hash_profile_verify"] = catalog.verify()["integrity"]

    bad_variants = {
        "missing_digest": {"sha256": None},
        "malformed_digest": {"sha256": "g" * 64},
        "uppercase_digest": {"sha256": "A" * 64},
        "short_digest": {"sha256": "a" * 63},
        "digest_on_error": {"hash_status": "error", "error": "read"},
        "changed_without_reason": {"hash_status": "changed", "sha256": None},
        "error_without_reason": {"hash_status": "error", "sha256": None},
        "directory_digest": {"kind": "directory"},
        "missing_file_size": {"size": None},
        "negative_size": {"size": -1},
        "nonfile_error_state": {"kind": "special", "hash_status": "error", "sha256": None, "error": "read"},
        "pending_persisted": {"hash_status": "pending", "sha256": None},
        "unknown_hash_state": {"hash_status": "unknown", "sha256": None},
    }
    controls = {}
    with FilesystemCatalog.initialize(root / "hash-rejections.db") as bad:
        scan = occurrence_uuid()
        with bad._db:
            bad._db.execute("INSERT INTO scans VALUES (?,?,?,?,?)",
                            (bad.namespace_uuid, scan, os.fsencode(root), 1, "[]"))
        for label, delta in bad_variants.items():
            row = dict(namespace_uuid=bad.namespace_uuid, scan_uuid=scan,
                       relative_path=label.encode("ascii"), kind="file", size=0,
                       mtime_ns=None, birthtime_ns=None, ctime_ns=None,
                       attributes=None, mode=None, sha256=empty_digest,
                       hash_status="complete", error=None, link_target=None, observed_us=None)
            row.update(delta)
            try:
                with bad._db:
                    bad._db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tuple(row.values()))
            except sqlite3.IntegrityError as exc:
                controls[label] = str(exc)
            else:
                raise AssertionError("SQLite accepted invalid hash tuple: " + label)
        assert bad._db.execute("SELECT count(*) FROM entries").fetchone()[0] == 0
        bad.verify()
    api["hash_sqlite_rejections"] = controls
    return cases


def check_coverage(data, decoded):
    """Positive profile coverage is independent of RDF; negatives use values."""
    cases = data["hash_cases"]
    if not isinstance(cases, dict) or set(cases) != CASE_NAMES:
        raise ValueError("F1-B required case declarations missing")
    entries = [r for (store, table, _), r in decoded.items()
               if store == "filesystem" and table == "entries"]
    if Counter(r["hash_status"] for r in entries) != EXPECTED_HASH_COUNTS:
        raise ValueError("F1-B declared hash-state coverage missing")
    if Counter(r["kind"] for r in entries) != EXPECTED_KIND_COUNTS:
        raise ValueError("F1-B declared file-kind coverage missing")
    seen = set()
    for key in cases.values():
        if (not isinstance(key, list) or len(key) != 3
                or any(type(v) is not str for v in key)):
            raise ValueError("malformed F1-B qualified entry key")
        path = bytes.fromhex(key[2])
        if path.hex() != key[2]:
            raise ValueError("noncanonical F1-B path encoding")
        key = (key[0], key[1], path)
        if key in seen:
            raise ValueError("repeated F1-B case identity")
        seen.add(key)
        if sum((r["namespace_uuid"], r["scan_uuid"], r["relative_path"]) == key for r in entries) != 1:
            raise ValueError("F1-B case occurrence missing or repeated")
'''
(HERE / "hash_profile.py").write_text(HASH_PROFILE)

p = HERE / "outcome_profile.py"
replace_once(p, "def check_coverage(data, decoded):", "def check_coverage(data, decoded, *, profile=PROFILE, expected_counts=EXPECTED_FS_COUNTS):")
replace_once(p, '    profile = data.get("profile", "values")\n    if profile == "values":\n        return\n    if profile != PROFILE:', '    supplied_profile = data.get("profile", "values")\n    if supplied_profile == "values":\n        return\n    if supplied_profile != profile:')
replace_once(p, '    if data["expected_counts"]["filesystem"] != EXPECTED_FS_COUNTS:', '    if data["expected_counts"]["filesystem"] != expected_counts:')

p = HERE / "instance_fixture.py"
replace_once(p, "import outcome_profile\n", "import outcome_profile\nimport hash_profile\n")
replace_once(p, '    if profile not in ("values", outcome_profile.PROFILE):', '    if profile not in ("values", outcome_profile.PROFILE, hash_profile.PROFILE):')
replace_once(p, '    outcome_cases = None\n', '    outcome_cases = None\n    hash_cases = None\n')
replace_once(p, '            if profile == outcome_profile.PROFILE:\n                outcome_cases = outcome_profile.populate(fs, root, api, scans[0])\n', '            if profile in (outcome_profile.PROFILE, hash_profile.PROFILE):\n                outcome_cases = outcome_profile.populate(fs, root, api, scans[0])\n            if profile == hash_profile.PROFILE:\n                hash_cases = hash_profile.populate(fs, root, api, outcome_cases)\n')
replace_once(p, '''        helper = Path(outcome_profile.__file__).resolve()
        helper_relative = helper.relative_to(repo).as_posix()
        if helper.read_bytes() != subprocess.check_output(
            ["git", "-C", str(repo), "show", "HEAD:" + helper_relative]
        ):
            raise ValueError("producer helper differs from HEAD")
        producer_inputs = {
            helper_relative: hashlib.sha256(helper.read_bytes()).hexdigest()
        }
''', '''        producer_inputs = {}
        for module in (outcome_profile, hash_profile):
            helper = Path(module.__file__).resolve()
            helper_relative = helper.relative_to(repo).as_posix()
            if helper.read_bytes() != subprocess.check_output(
                ["git", "-C", str(repo), "show", "HEAD:" + helper_relative]
            ):
                raise ValueError("producer helper differs from HEAD")
            producer_inputs[helper_relative] = hashlib.sha256(helper.read_bytes()).hexdigest()
''')
replace_once(p, '        if profile == outcome_profile.PROFILE:\n            expected["filesystem"] = dict(outcome_profile.EXPECTED_FS_COUNTS)\n', '        if profile == outcome_profile.PROFILE:\n            expected["filesystem"] = dict(outcome_profile.EXPECTED_FS_COUNTS)\n        elif profile == hash_profile.PROFILE:\n            expected["filesystem"] = dict(hash_profile.EXPECTED_FS_COUNTS)\n')
replace_once(p, '            "outcome_cases": outcome_cases,\n', '            "outcome_cases": outcome_cases,\n            "hash_cases": hash_cases,\n')
replace_once(p, '''            "scope": (
                "disposable real complete/partial/interrupted scanner witnesses plus explicit SQL-only value and empty-partial witnesses"
                if profile == outcome_profile.PROFILE
                else "disposable synthetic fixture, not scanner execution or retained data"
            ),
''', '''            "scope": (
                "real terminal and changed/read-error scanner witnesses plus explicitly SQL-only value, empty-partial and hash-boundary rows"
                if profile == hash_profile.PROFILE
                else "disposable real complete/partial/interrupted scanner witnesses plus explicit SQL-only value and empty-partial witnesses"
                if profile == outcome_profile.PROFILE
                else "disposable synthetic fixture, not scanner execution or retained data"
            ),
''')
replace_once(p, '        "--profile", choices=("values", outcome_profile.PROFILE), default="values"', '        "--profile", choices=("values", outcome_profile.PROFILE, hash_profile.PROFILE), default="values"')

p = HERE / "instance_model.py"
replace_once(p, "import outcome_profile\n", "import outcome_profile\nimport hash_profile\n")
replace_once(p, 'SCOPE = "disposable FS/WT representation and selected Filesystem outcome constraints; no external target resolution"', 'SCOPE = "disposable FS/WT representation and selected Filesystem outcome/hash constraints; no external target resolution or real-byte proof"')
replace_once(p, '    outcome_profile.check_coverage(data, decoded)\n', '''    if data.get("profile") == hash_profile.PROFILE:
        outcome_profile.check_coverage(
            data, decoded, profile=hash_profile.PROFILE,
            expected_counts=hash_profile.EXPECTED_FS_COUNTS,
        )
        hash_profile.check_coverage(data, decoded)
    else:
        outcome_profile.check_coverage(data, decoded)
''')
replace_once(p, '            if table == "entries":\n                error = row["error"]\n', '''            if table == "entries":
                for field, predicate in (("kind", M.kind), ("hash_status", M.hashStatus)):
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
                    g.add((node, predicate, M.SqlNull if raw is None else Literal(raw, datatype=datatype)))
                error = row["error"]
''')
replace_once(p, '                "outcome_cases",\n', '                "outcome_cases",\n                "hash_cases",\n')
replace_once(p, '            "outcome_profile.py",\n', '            "outcome_profile.py",\n            "hash_profile.py",\n')
replace_once(p, '            "No general SQL/trigger/UDF semantics, all WT physical FKs, hash-state rules, scanner races or concurrent transitions.",', '            "No general SQL/trigger/UDF semantics, all WT physical FKs, exhaustive scanner races or concurrent transitions; digest syntax does not prove real-byte equality.",')

p = HERE / "instance_shapes.ttl"
text = p.read_text()
anchor = ' sh:property [sh:path m:hasError; sh:minCount 1; sh:maxCount 1; sh:datatype xsd:boolean];\n'
if text.count(anchor) != 1:
    raise RuntimeError("EntryShape anchor missing")
new_properties = ''' sh:property [sh:path m:kind; sh:minCount 1; sh:maxCount 1; sh:in ("file" "directory" "symlink" "special" "unknown")];
 sh:property [sh:path m:hashStatus; sh:minCount 1; sh:maxCount 1; sh:in ("complete" "changed" "error" "not-applicable")];
 sh:property [sh:path m:size; sh:minCount 1; sh:maxCount 1;
   sh:or ( [sh:in (m:SqlNull)] [sh:datatype xsd:integer; sh:minInclusive 0] )];
 sh:property [sh:path m:sha256; sh:minCount 1; sh:maxCount 1;
   sh:or ( [sh:in (m:SqlNull)] [sh:datatype xsd:string; sh:pattern "^[0-9a-f]{64}$"] )];
 sh:sparql [sh:message "Digest presence must agree with successful regular-file hashing"; sh:select """
 PREFIX m: <urn:git-repo-db:instance-pilot:v1:>
 SELECT $this WHERE {
   $this m:kind ?kind; m:hashStatus ?status; m:sha256 ?digest .
   FILTER ((?status = "complete" && (?kind != "file" || ?digest = m:SqlNull)) ||
           (?status != "complete" && ?digest != m:SqlNull))
 }
 """];
 sh:sparql [sh:message "Entry kind, size and hash state disagree with the SQLite contract"; sh:select """
 PREFIX m: <urn:git-repo-db:instance-pilot:v1:>
 SELECT $this WHERE {
   $this m:kind ?kind; m:hashStatus ?status; m:size ?size .
   FILTER ((?kind = "file" && (?size = m:SqlNull || ?status NOT IN ("complete", "changed", "error"))) ||
           (?kind != "file" && ?status != "not-applicable"))
 }
 """];
 sh:sparql [sh:message "Changed or failed hashing requires a non-NULL reason"; sh:select """
 PREFIX m: <urn:git-repo-db:instance-pilot:v1:>
 SELECT $this WHERE {
   $this m:hashStatus ?status; m:hasError false .
   FILTER (?status IN ("changed", "error"))
 }
 """];
'''
text = text.replace(anchor, anchor + new_properties, 1)
p.write_text(text)
p = HERE / "instance_constraints.json"
manifest = json.loads(p.read_text())
manifest["shapes_sha256"] = hashlib.sha256(text.encode()).hexdigest()
manifest["constraints"]["EntryShape"] += "; selected SQLite kind/size/hash/digest/reason tuple constraints (not byte verification)"
p.write_text(json.dumps(manifest, indent=2) + "\n")

TESTS = r'''"""F1-B producer evidence, input coverage and synthetic hash counterexamples."""

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import hash_profile
from instance_model import validate, value
from test_instance_model import assert_contract


class HashPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "HASH_FIXTURE" not in os.environ:
            raise unittest.SkipTest("run verified --profile filesystem-hash-v1 producer")
        cls.fixture = json.loads(Path(os.environ["HASH_FIXTURE"]).read_text())
        if cls.fixture.get("profile") != hash_profile.PROFILE:
            raise ValueError("wrong hash fixture profile")

    def result(self, data):
        with tempfile.TemporaryDirectory() as temp:
            result = validate(data, Path(temp))
            assert_contract(self, result)
            self.assertEqual(result, json.loads((Path(temp) / "result.json").read_text()))
            return result

    def row(self, data, name):
        key = data["hash_cases"][name]
        return next(r for r in data["tables"]["filesystem"]["entries"]
                    if [value(r["namespace_uuid"]), value(r["scan_uuid"]),
                        value(r["relative_path"]).hex()] == key)

    def synthetic(self):
        data = copy.deepcopy(self.fixture)
        # This input intentionally does not claim all positive-profile scenarios.
        # Keep every extracted occurrence/count; evaluate invalid data with the
        # same shapes through the existing unrestricted values projection profile.
        data["profile"] = "values"
        data["scope"] = "synthetic extracted-JSON counterexample, not product admission or a positive hash fixture"
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
        self.assertEqual(len(api["hash_sqlite_rejections"]), 13)
        self.assertTrue(all("CHECK" in s for s in api["hash_sqlite_rejections"].values()))

    def test_positive_profile_and_source_bound_coverage(self):
        result = self.result(self.fixture)
        self.assertEqual(result["families"]["data_conformance"]["status"], "pass")
        for shape, count in (("EntryShape", 15), ("ScanShape", 9), ("OutcomeShape", 7)):
            self.assertEqual(result["coverage"][shape]["expected"], count)
            self.assertEqual(result["coverage"][shape]["selected"], count)
        self.assertIn("hash_profile.py", result["digests"])
        self.assertEqual(result["source"]["hash_cases"], self.fixture["hash_cases"])
        self.assertIn("tools/schema-model/hash_profile.py", result["source"]["producer_inputs"])

    def test_digest_null_and_lexical_negatives(self):
        for digest in (None, "", "a" * 63, "g" * 64, "A" * 64):
            with self.subTest(digest=digest):
                data = self.synthetic()
                self.row(data, "complete")["sha256"] = {
                    "type": "null" if digest is None else "text", "value": digest}
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
                outcome = next(r for r in data["tables"]["filesystem"]["scan_outcomes"]
                               if [value(r["namespace_uuid"]), value(r["scan_uuid"])] == key)
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
        for field, kind, invalid in (("size", "null", None), ("size", "integer", -1),
                                     ("hash_status", "text", "not-applicable"),
                                     ("hash_status", "text", "pending"),
                                     ("hash_status", "text", "unknown")):
            with self.subTest(field=field, invalid=invalid):
                data = self.synthetic()
                self.row(data, "complete")[field] = {"type": kind, "value": invalid}
                if field == "hash_status":
                    self.row(data, "complete")["sha256"] = {"type": "null", "value": None}
                self.assert_status(data, "fail")

    def test_no_invented_nonfile_size_or_success_error_rule(self):
        self.assertEqual(value(self.row(self.fixture, "special")["size"]), 0)
        self.assertEqual(value(self.row(self.fixture, "complete_with_error")["error"]), "")
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
                    data["tables"]["filesystem"]["entries"].remove(self.row(data, "error"))
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
'''
(HERE / "test_hash_model.py").write_text(TESTS)

with (HERE / "INSTANCE-PILOT.md").open("a") as f:
    f.write('''
## F1-B: hash-state profile

`--profile filesystem-hash-v1` extends F1-A with real changed-during-read and
controlled read-error scans. Both retain no successful digest; enumeration and
hashing completion remain distinct. Three additional SQL-only rows cover a link,
a special entry and a complete file entry with a non-NULL error. These last rows
are DDL/API boundary witnesses, not claims of scanner execution. The fixed
profile contains nine FS scans, fifteen entries and seven outcomes, with all
five file kinds and all four persisted hash states selected.

```sh
scripts/local-run.sh python tools/schema-model/instance_fixture.py \\
  --profile filesystem-hash-v1 > /tmp/hashes.json
uv run --project tools/schema-model --locked --offline python \\
  tools/schema-model/instance_model.py /tmp/hashes.json /tmp/hashes-result
HASH_FIXTURE=/tmp/hashes.json uv run --project tools/schema-model --locked --offline \\
  python -m unittest discover -s tools/schema-model -p test_hash_model.py -q
```

All profiles now project required kind, hash status, size and digest cells.
Selected SHACL rules mirror the current SQLite tuples: only complete regular
files have digests; digests use 64 lowercase hex characters; files have a known
nonnegative size; failed/changed hashing has a non-NULL reason. Empty error text
is not NULL. Unknown is a file kind, not a hash state. Pending is not persisted.
Non-file size is not universally forbidden, and a complete entry may carry an
error, but the enclosing scan cannot claim complete while errors exist.

The positive hash profile checks fixed construction counts, state/kind coverage
and qualified case occurrences before graph generation. Synthetic negative tests
use the existing `values` projection profile with explicit synthetic scope, so
they do not simultaneously claim to be a complete set of positive hash witnesses.
The same shapes apply to every profile. Missing required extraction is still
undetermined; a correctly rejected counterexample has data_conformance=fail.

Thirteen SQLite invalid-tuple controls run with guards enabled. The actual empty
file digest is separately checked against known bytes. A syntactically valid but
incorrect digest deliberately passes the shape-only control: graph conformance
is not a real-byte equality proof. No general SQL/trigger proof, external target
resolution, atomic snapshot, exhaustive race verification, operation-state model,
retained-catalog checking or mandatory CI gate is introduced. Both helper sources
are checked against committed HEAD and retained in producer digest bindings.
''')

print(json.dumps({"changed_files": ["tools/schema-model/" + p for p in (
    "instance_fixture.py", "instance_model.py", "outcome_profile.py", "hash_profile.py",
    "test_hash_model.py", "instance_shapes.ttl", "instance_constraints.json", "INSTANCE-PILOT.md")],
    "shapes_sha256": manifest["shapes_sha256"]}))
