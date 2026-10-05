"""Run independent target/core/contract tests with pinned SQLite 3.46.1.

Run scripts/prepare_sqlite_minimum.py before this offline lane.
The application dependency/runner is not changed.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sqlite_minimum import activate  # noqa: E402

activate()
import sqlite3  # noqa: E402

assert sqlite3.sqlite_version == "3.46.1", sqlite3.sqlite_version
os.environ["TEST_SQLITE_MINIMUM"] = sqlite3.sqlite_version
import pytest  # noqa: E402

print("Constraint lane SQLite:", sqlite3.sqlite_version)
raise SystemExit(
    pytest.main(
        [
            "tests/integration/test_target_schema.py",
            "tests/integration/test_p1_storage_lifecycle.py",
            "tests/integration/test_schema_proposal_core.py",
            "tests/integration/test_conversion_contract.py",
            "tests/integration/test_conversion_foundation.py",
            "tests/unit/test_conversion_protocol.py",
            "-q",
            *sys.argv[1:],
        ]
    )
)
