"""Core Exchange remains usable without Context implementation or stores."""

import subprocess
import sys
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.p1_core import Provenance, RepositoryClaim

BLOCK = """
import importlib.abc
import sys
class NoContext(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("repo_catalog.") and (
            "context" in fullname or "resource_identification" in fullname
        ):
            raise AssertionError("unexpected Context import: " + fullname)
        return None
sys.meta_path.insert(0, NoContext())
"""


def guarded(script, *args):
    result = subprocess.run(
        [sys.executable, "-c", BLOCK + script, *map(str, args)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result


def catalog(path, repo, instance, *, operational=False, context=False):
    path.mkdir()
    for role in (
        "core",
        *(["operational"] if operational else []),
        *(["context"] if context else []),
    ):
        initialize(path / f"{role}.sqlite3", role, repo, instance)


def test_core_export_import_and_cumulative_work_without_context(tmp_path):
    repo, source_id, target_id = (str(uuid4()) for _ in range(3))
    source, target, no_ledger = (
        tmp_path / name for name in ("source", "target", "no-ledger")
    )
    catalog(source, repo, source_id)
    catalog(target, repo, target_id, operational=True)
    catalog(no_ledger, repo, str(uuid4()))
    claim = RepositoryClaim(
        repo,
        "name",
        "history-長い",
        Provenance("source", "observation", "coordinate", "decoder", "1"),
    )
    with closing(GitCore(source / "core.sqlite3")) as core:
        core.admit_repository_claim(claim)
    guarded(
        """
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.domain.exchange import ExchangeSelectionScope, ExchangeError, encode_package, decode_package
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
source, target, no_ledger, repo, target_id = sys.argv[1:]
scope = ExchangeSelectionScope(all_selected=True, include_context=False, resource_keys=())
package = ExchangeService(source).export_package(selection=scope)
assert package.context is None and package.core["repository_claims"]
wire = encode_package(package)
assert decode_package(wire).digest_sha256 == package.digest_sha256
try:
    ExchangeService(no_ledger).import_package(package, new_request=True, permitted_repository_uuidv4s=(repo,))
except CoordinationError as error:
    assert error.code == "CONTINUATION_UNAVAILABLE"
else:
    raise AssertionError("Operational ledger was not required")
request = RequestIdentity(package.sender_catalog_instance_uuidv4, package.package_id)
service = ExchangeService(target)
first = service.import_package(package, request=request, new_request=True, permitted_repository_uuidv4s=(repo,))
with OperationalAcquisitionLedger(target, repository_uuidv4=repo, catalog_instance_uuidv4=target_id) as ledger:
    before = ledger.work_ledger.usage(request)
second = service.import_package(package, request=request, permitted_repository_uuidv4s=(repo,))
with OperationalAcquisitionLedger(target, repository_uuidv4=repo, catalog_instance_uuidv4=target_id) as ledger:
    after = ledger.work_ledger.usage(request)
assert first.core_imported and second.core_imported
assert after["metadata_units"] > before["metadata_units"] > 0
reverse = service.export_package(selection=scope)
assert reverse.core["repository_claims"] == package.core["repository_claims"]
bad = package.to_dict()
bad["digest_sha256"] = "0" * 64
try:
    decode_package(bad)
except ExchangeError:
    pass
else:
    raise AssertionError("invalid digest accepted")
""",
        source,
        target,
        no_ledger,
        repo,
        target_id,
    )


def test_coexisting_context_pair_identity_and_persistent_stop(tmp_path):
    repo, instance = str(uuid4()), str(uuid4())
    healthy, mismatch = tmp_path / "healthy", tmp_path / "mismatch"
    catalog(healthy, repo, instance, context=True)
    catalog(mismatch, repo, instance)
    initialize(mismatch / "context.sqlite3", "context", repo, str(uuid4()))
    scope = ExchangeSelectionScope(all_selected=True, include_context=False)
    assert ExchangeService(healthy).export_package(selection=scope).context is None
    with pytest.raises(Exception, match="PAIR_IDENTITY"):
        ExchangeService(mismatch).export_package(selection=scope)
    persist_catalog_stop(healthy, "detected Context corruption")
    with pytest.raises(Exception, match="RECOVERY_REQUIRED"):
        ExchangeService(healthy).export_package(selection=scope)


def test_core_receive_stop_before_commit_rolls_back_without_context(tmp_path):
    repo, source_id, target_id = (str(uuid4()) for _ in range(3))
    source, target = tmp_path / "source", tmp_path / "target"
    catalog(source, repo, source_id)
    catalog(target, repo, target_id, operational=True)
    with closing(GitCore(source / "core.sqlite3")) as core:
        core.admit_repository_claim(
            RepositoryClaim(
                repo,
                "name",
                "important",
                Provenance("source", "observation", "coordinate", "decoder", "1"),
            )
        )
    guarded(
        """
from pathlib import Path
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.adapters.sqlite.p1_schema import connect
source, target, repo = sys.argv[1:]
package = ExchangeService(source).export_package(selection=ExchangeSelectionScope(all_selected=True, include_context=False))
def cut(point):
    if point == "before_core_commit":
        persist_catalog_stop(Path(target), "detected authoritative corruption")
try:
    ExchangeService(target).import_package(package, new_request=True, permitted_repository_uuidv4s=(repo,), cut=cut)
except CoordinationError as error:
    assert error.code == "RECOVERY_REQUIRED"
else:
    raise AssertionError("commit was not stopped")
db = connect(Path(target) / "core.sqlite3", "core")
assert db.execute("SELECT COUNT(*) FROM repository_claims").fetchone()[0] == 0
db.close()
""",
        source,
        target,
        repo,
    )
