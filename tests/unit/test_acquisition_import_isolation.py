"""Selected Git acquisition does not require Provider or paired capabilities."""

import subprocess
import sys


def _run_without_imports(code, forbidden, tmp_path):
    guard = """
import importlib.abc
import sys

class AbsentModules(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in forbidden):
            raise AssertionError("Unselected capability imported: " + fullname)

sys.meta_path.insert(0, AbsentModules())
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "forbidden = " + repr(forbidden) + "\n" + guard + code,
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_git_api_admits_without_provider_or_pair_imports(tmp_path):
    _run_without_imports(
        """
from pathlib import Path
from uuid import uuid4

from repo_catalog.application.acquisition import GitAcquisition
from repo_catalog.application.git_acquisition import GitAcquisition as CanonicalAcquisition
from repo_catalog.domain.acquisition import AcquisitionError, GitMetadataInput
from repo_catalog.domain.git_acquisition import GitMetadataInput as CanonicalInput
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.core_query import CoreQueryService
from repo_catalog.domain.p1_core import OID

assert GitAcquisition is CanonicalAcquisition
assert GitMetadataInput is CanonicalInput
directory = Path(sys.argv[1])
assert not list(directory.iterdir())
repository, instance = str(uuid4()), str(uuid4())
for role in ("core", "operational"):
    initialize(directory / (role + ".sqlite3"), role, repository, instance)
object_oid = OID("sha1", "1" * 40)
unit = GitMetadataInput(
    repository, str(uuid4()), str(uuid4()), "synthetic-input", 1700000000000000,
    nominal_objects=(object_oid,),
)
service = GitAcquisition(directory, operational=directory)
report = service.acquire_metadata_only(unit, new_request=True)
assert report.status == "complete"
assert report.admitted_objects == (object_oid,)
assert not report.retained_objects
assert CoreQueryService(directory, mode="core_only").get_git_object(object_oid)
assert not any((directory / (role + ".sqlite3")).exists() for role in (
    "context", "search", "access"
))
""",
        (
            "repo_catalog.adapters.github",
            "repo_catalog.adapters.sqlite.p1_context",
            "repo_catalog.adapters.sqlite.production_context",
            "repo_catalog.adapters.sqlite.context_transaction",
            "repo_catalog.adapters.sqlite.p1_coordination",
            "repo_catalog.application.provider_acquisition",
            "repo_catalog.application.paired_acquisition",
            "repo_catalog.domain.p1_context",
            "repo_catalog.domain.production_context",
            "repo_catalog.domain.provider_acquisition",
            "repo_catalog.domain.paired_acquisition",
            "repo_catalog.adapters.sqlite.production_search",
        ),
        tmp_path,
    )


def test_operational_ledger_opens_without_concrete_authorities(tmp_path):
    _run_without_imports(
        """
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from repo_catalog.adapters.sqlite.operational_coordination import WorkLedger
from repo_catalog.adapters.sqlite.p1_schema import initialize, connect

directory = Path(sys.argv[1])
repository, instance = str(uuid4()), str(uuid4())
path = directory / "operational.sqlite3"
initialize(path, "operational", repository, instance)
with closing(connect(path, "operational")) as db:
    ledger = WorkLedger(db)
    assert ledger.store_identity() == (repository, instance)
assert not any((directory / (role + ".sqlite3")).exists() for role in (
    "core", "context", "search", "access"
))
""",
        (
            "repo_catalog.adapters.sqlite.git_core",
            "repo_catalog.adapters.sqlite.p1_core",
            "repo_catalog.adapters.sqlite.core_coordination",
            "repo_catalog.adapters.sqlite.p1_context",
            "repo_catalog.adapters.sqlite.production_context",
            "repo_catalog.adapters.sqlite.p1_coordination",
            "repo_catalog.domain.p1_core",
            "repo_catalog.domain.p1_context",
        ),
        tmp_path,
    )
