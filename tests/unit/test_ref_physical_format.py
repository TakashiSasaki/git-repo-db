"""Retired physical/wire scope cannot be restored by recomputing checksums."""

import hashlib
import json
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangePackage,
    ExchangeSelectionScope,
    decode_package,
    empty_core_section,
    encode_package,
)
from repo_catalog.domain.p1_core import CoreCoverageScope, CoreFailure
from repo_catalog.domain.recovery import BackupScope, RestoreValidationError


@pytest.mark.parametrize(
    "section",
    [
        "captures",
        "notes_claims",
        "notes_groups",
        "notes_inventories",
        "note_roles",
        "retained_notes",
    ],
)
def test_retired_sections_rejected_with_recomputed_digest(section):
    package = ExchangePackage(
        package_id=str(uuid4()),
        exported_at_us=1,
        sender_catalog_instance_uuidv4=str(uuid4()),
        repository_uuidv4=str(uuid4()),
        selection_scope=ExchangeSelectionScope(
            all_selected=True, include_context=False
        ),
        core=empty_core_section(),
    )
    wire = json.loads(encode_package(package))
    wire["core"][section] = []
    content = json.dumps(
        {k: v for k, v in wire.items() if k != "digest_sha256"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    wire["digest_sha256"] = hashlib.sha256(content).hexdigest()
    with pytest.raises(ExchangeError) as failure:
        decode_package(json.dumps(wire))
    assert failure.value.code == "MALFORMED_CORE_SECTION"


def test_capture_coverage_owner_is_no_longer_an_admissible_input():
    with pytest.raises(CoreFailure) as failure:
        CoreCoverageScope("capture", (str(uuid4()), str(uuid4()), "inventory"))
    assert failure.value.code == "COVERAGE_SCOPE"


def test_old_backup_manifest_rejected_after_checksum_recomputation(tmp_path):
    repository, instance = str(uuid4()), str(uuid4())
    source, backup, fresh = (tmp_path / name for name in ("source", "backup", "fresh"))
    source.mkdir()
    initialize(source / "core.sqlite3", "core", repository, instance)
    adapter = SQLiteRecoveryAdapter()
    adapter.create_consistent_backup(source, backup, BackupScope.GIT_ONLY)
    manifest = backup / "manifest.json"
    wire = json.loads(manifest.read_text())
    wire["manifest_version"] = 1
    manifest.write_text(json.dumps(wire) + "\n")
    (backup / "manifest.json.sha256").write_text(
        hashlib.sha256(manifest.read_bytes()).hexdigest() + "  manifest.json\n"
    )
    with pytest.raises(RestoreValidationError, match="Unsupported manifest version"):
        adapter.restore_backup(backup, fresh, repository)
    assert not fresh.exists()
