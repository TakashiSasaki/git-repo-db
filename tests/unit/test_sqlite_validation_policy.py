"""Policy-checker counterexamples; executable with stdlib unittest, no deps."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import check_sqlite_validation_policy as policy  # noqa: E402


class PolicyDetectionTests(unittest.TestCase):
    def rules(self, source, path="scripts/verify_future.py"):
        return {finding.rule for finding in policy.inspect(path, source)}

    def test_download_in_workflow(self):
        source = "run: curl https://www.sqlite.org/2026/sqlite-amalgamation-3510300.zip"
        self.assertIn(
            "sqlite-download", self.rules(source, ".github/workflows/new.yml")
        )

    def test_compile_continued_shell_command(self):
        self.assertIn(
            "sqlite-compile",
            self.rules('cc -shared \\\n "$SQLITE_C" -o libsqlite3.so.0'),
        )

    def test_test_only_installation_shell_and_python_argv(self):
        for source in (
            "uv pip install pysqlite3-binary",
            "apt-get install libsqlite3-dev",
            "brew install sqlite",
            "subprocess.run(['pip', 'install', 'pysqlite3-binary'])",
        ):
            with self.subTest(source=source):
                self.assertIn("sqlite-install", self.rules(source))

    def test_library_environment_writes(self):
        for source in (
            "export LD_LIBRARY_PATH=/tmp/sqlite",
            "env['LD_PRELOAD'] = '/tmp/libsqlite3.so'",
            "dict(os.environ, LD_LIBRARY_PATH=str(library))",
            "env.update({'LD_LIBRARY_PATH': str(library)})",
        ):
            with self.subTest(source=source):
                self.assertIn("sqlite-library-swap", self.rules(source))

    def test_version_matrix_forms(self):
        for source in (
            "sqlite: ['3.51.3', '3.53.1']",
            "sqlite-version:\n  - '3.51.3'\n  - '3.53.1'\n",
            "run: python verify.py ${{ matrix.sqlite }}",
            "import sqlite3\nfor version in ('3.51.3', '3.53.1'):\n    run(version)",
        ):
            with self.subTest(source=source):
                self.assertIn("sqlite-matrix", self.rules(source))

    def test_version_and_library_selection_options(self):
        for name in (
            "sqlite",
            "sqlite-version",
            "sqlite-source-id",
            "minimum-library",
            "newer-library",
        ):
            source = f"parser.add_argument('--{name}', required=True)"
            with self.subTest(name=name):
                self.assertIn("sqlite-version-option", self.rules(source))

    def test_literal_version_gates(self):
        for source in (
            "import sqlite3\nassert sqlite3.sqlite_version_info == (3, 51, 3)",
            "import sqlite3 as sql\nif sql.sqlite_version != '3.51.3':\n    raise RuntimeError()",
            "import sqlite3\nEXPECTED = (3, 51, 3)\nactual = sqlite3.sqlite_version_info\nassert actual == EXPECTED",
        ):
            with self.subTest(source=source):
                self.assertIn("sqlite-exact-gate", self.rules(source))

    def test_source_id_gate_through_aliases(self):
        source = """SOURCE_ID = '2026-03-13 10:38:09 abcdef'
actual = db.execute('SELECT sqlite_source_id()').fetchone()[0]
if actual != SOURCE_ID:
    raise RuntimeError('wrong source')
"""
        self.assertIn("sqlite-exact-gate", self.rules(source))

    def test_command_line_expected_version_is_an_exact_gate(self):
        source = """import sys, sqlite3
EXPECTED = sys.argv[2]
actual = db.execute('SELECT sqlite_version()').fetchone()[0]
assert actual == EXPECTED
"""
        self.assertIn("sqlite-exact-gate", self.rules(source))

    def test_from_import_and_workflow_heredoc_source_gate(self):
        self.assertIn(
            "sqlite-exact-gate",
            self.rules("from sqlite3 import sqlite_version as v\nassert v == '3.51.3'"),
        )
        source = """run: |
  python - <<'PY'
  import sqlite3
  source = db.execute('SELECT sqlite_source_id()').fetchone()[0]
  assert source == '2026-03-13 10:38:09 abcdef'
  PY
"""
        found = policy.inspect(".github/workflows/future.yml", source)
        self.assertIn(
            policy.Finding(".github/workflows/future.yml", 5, "sqlite-exact-gate"),
            found,
        )

    def test_generated_python_gate(self):
        source = '''probe.write_text("""import sqlite3
actual = sqlite3.sqlite_version
assert actual == '3.51.3'
""")'''
        self.assertIn("sqlite-exact-gate", self.rules(source))

    def test_generated_probe_with_comma_imports_and_cli_selector(self):
        for imports in ("import hashlib,json,sqlite3,sys", "import json,sqlite3"):
            source = f'''probe.write_text("""{imports}
actual = db.execute('SELECT sqlite_version()').fetchone()[0]
assert actual == sys.argv[2]
""")'''
            with self.subTest(imports=imports):
                self.assertIn("sqlite-exact-gate", self.rules(source))

    def test_fenced_command_in_agent_instructions(self):
        source = "```sh\nuv pip install pysqlite3-binary\n```\n"
        self.assertIn("sqlite-install", self.rules(source, "nested/AGENTS.md"))

    def test_affirmative_wrapped_instructions(self):
        for source in (
            "Run both the minimum and newer SQLite\nruntimes before acceptance.",
            "Build SQLite from source before running tests.",
            "Use the actual SQLite 3.51.3 interpreter.",
            "Require a SQLite version matrix.",
            "Run SQLite 3.51.3 and 3.53.1.",
            "Verify two versions of SQLite.",
            "Require an exact SQLite source ID.",
        ):
            with self.subTest(source=source):
                self.assertIn("sqlite-procedure", self.rules(source, "docs/testing.md"))

    def test_prohibition_does_not_hide_subsequent_instruction(self):
        source = "Do not alter product safety checks. Run both SQLite versions."
        self.assertIn("sqlite-procedure", self.rules(source, "AGENTS.md"))

    def test_unrelated_negative_clause_does_not_hide_positive_requirement(self):
        for source in (
            "Run SQLite 3.51.3 and 3.53.1 without disabling product safety checks.",
            "Run both SQLite versions and never spoof version strings.",
            "Never spoof version strings and run both SQLite versions.",
            "Run both SQLite versions and preserve historical evidence.",
            "Run without bypassing safety checks on SQLite 3.51.3 and 3.53.1.",
        ):
            with self.subTest(source=source):
                self.assertIn("sqlite-procedure", self.rules(source, "AGENTS.md"))

    def test_japanese_source_build_instruction_and_prohibition(self):
        self.assertIn(
            "sqlite-procedure", self.rules("SQLiteをソースビルドする。", "AGENTS.md")
        )
        self.assertFalse(self.rules("SQLiteをソースビルドしない。", "AGENTS.md"))
        self.assertFalse(self.rules("SQLiteのソースビルドは禁止する。", "AGENTS.md"))
        self.assertIn(
            "sqlite-procedure",
            self.rules(
                "SQLiteをソースビルドしない。SQLiteをソースビルドする。", "AGENTS.md"
            ),
        )

    def test_negative_policy_and_historical_observations(self):
        for source in (
            "Do not build SQLite from source for tests.",
            "Never require both SQLite versions.",
            "Run without a SQLite version matrix.",
            "Historical runs used both SQLite releases.",
            "The completed experiment supplies SQLite 3.51.3/3.53.1 evidence.",
            "SQLite のソースビルドは廃止する。",
        ):
            with self.subTest(source=source):
                self.assertFalse(self.rules(source, ".agents/skills/example/SKILL.md"))

    def test_runtime_measurement_and_library_environment_recording(self):
        source = """import sqlite3, os
runtime = {'sqlite': sqlite3.sqlite_version,
           'source': db.execute('SELECT sqlite_source_id()').fetchone()[0],
           'LD_LIBRARY_PATH': os.environ.get('LD_LIBRARY_PATH')}
print(runtime)
"""
        self.assertFalse(self.rules(source))

    def test_report_status_is_not_a_sqlite_gate(self):
        source = """import sqlite3
report = {'environment': {'sqlite': sqlite3.sqlite_version}}
report['status'] = 'passed'
assert report['status'] == 'passed'
"""
        self.assertFalse(self.rules(source))

    def test_distribution_artifacts_and_doc_builds_are_not_version_matrices(self):
        for source in (
            "Build and publish developer documentation for SQLite architectures.",
            "Use SQLite for both artifacts and record exact collected test cases.",
            "SQLite のソースビルドや複数版での検証は要求しません。",
        ):
            with self.subTest(source=source):
                self.assertFalse(self.rules(source, "docs/testing.md"))

    def test_same_invocation_runtime_binding_is_retained(self):
        source = """if meta['sqlite'] != expected_runtime['sqlite']:
    raise ValueError('runtime differs within invocation')
"""
        self.assertFalse(self.rules(source))

    def test_capability_and_minimum_safety_requirements_are_retained(self):
        source = """import sqlite3
MIN_SQLITE = (3, 51, 3)
if sqlite3.sqlite_version_info < MIN_SQLITE:
    raise ValueError('safe WAL, STRICT and JSON required')
assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
"""
        self.assertFalse(self.rules(source))
        self.assertFalse(
            self.rules(
                "Preserve SQLite >= 3.51.3 for WAL safety and STRICT.",
                "docs/testing.md",
            )
        )

    def test_non_sqlite_hash_binding_and_release_download_links(self):
        source = "expected = 'abcdef'\nassert actual_sha256 == expected\n# https://sqlite.org/releaselog/3_51_3.html"
        self.assertFalse(self.rules(source))

    def test_historical_baseline_selection_is_not_runtime_selection(self):
        source = "python scripts/compare_i5_failures.py --baseline-entry final-3.53.1/regressions.xml"
        self.assertFalse(self.rules(source))
        self.assertFalse(self.rules("parser.add_argument('--sqlite-info-output')"))

    def test_line_location_for_python_gate(self):
        found = policy.inspect(
            "scripts/check.py",
            "import sqlite3\n\nassert sqlite3.sqlite_version == '3.51.3'\n",
        )
        self.assertEqual({finding.line for finding in found}, {3})


class PolicyScopeAndCliTests(unittest.TestCase):
    def test_active_scopes_include_future_agent_helpers_and_nested_agents(self):
        for path in (
            ".agents/skills/new/scripts/prepare.sh",
            ".agents/skills/new/references/run.md",
            "docs/phase2/AGENTS.md",
            ".github/copilot-instructions.md",
            "scripts/new-verification.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(policy.in_scope(path))

    def test_evidence_product_and_negative_fixtures_are_outside_scope(self):
        for path in (
            "docs/implementation/evidence/adr0031-i5/independent/REPORT.md",
            "docs/validation/synthetic/old.md",
            "docs/implementation/adr0031-i5-typed-admission.md",
            "tests/fixtures/bad-workflow.yml",
            "tests/unit/test_sqlite_validation_policy.py",
            "src/repo_catalog/adapters/sqlite/p1_schema.py",
            policy.SELF,
        ):
            with self.subTest(path=path):
                self.assertFalse(policy.in_scope(path))

    def test_cli_passes_then_fails_for_tracked_active_violation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "scripts").mkdir()
            target = root / "scripts/future.sh"
            target.write_text(
                "python -c 'import sqlite3; print(sqlite3.sqlite_version)'\n"
            )
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            command = [
                sys.executable,
                str(policy.ROOT / policy.SELF),
                "--root",
                str(root),
            ]
            passed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            target.write_text("uv pip install pysqlite3-binary\n")
            failed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
            self.assertIn("scripts/future.sh:1: sqlite-install", failed.stdout)

    def test_untracked_artifacts_and_history_do_not_affect_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "scripts").mkdir()
            (root / "scripts/temporary.sh").write_text(
                "uv pip install pysqlite3-binary"
            )
            self.assertFalse(policy.scan(root, ["docs/implementation/evidence/old.sh"]))
            result = subprocess.run(
                [sys.executable, str(policy.ROOT / policy.SELF), "--root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
