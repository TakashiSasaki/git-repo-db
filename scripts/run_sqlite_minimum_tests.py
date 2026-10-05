"""Run independent target/core/contract tests with pinned SQLite 3.46.1.

Prepare pysqlite3-binary==0.5.4 in artifacts/sqlite-min before this offline lane.
The application dependency/runner is not changed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "artifacts/sqlite-min"))
import pysqlite3  # noqa: E402

assert pysqlite3.sqlite_version == "3.46.1", pysqlite3.sqlite_version
sys.modules["sqlite3"] = pysqlite3
import pytest  # noqa: E402

print("Constraint lane SQLite:", pysqlite3.sqlite_version)
raise SystemExit(
    pytest.main(
        [
            "tests/integration/test_target_schema.py",
            "tests/integration/test_schema_proposal_core.py",
            "tests/integration/test_conversion_contract.py",
            "-q",
        ]
    )
)
