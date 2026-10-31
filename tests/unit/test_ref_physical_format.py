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


@pytest.mark.parametrize("old_version", [1, 2])
def test_old_backup_manifest_rejected_after_checksum_recomputation(
    tmp_path, old_version
):
    repository, instance = str(uuid4()), str(uuid4())
    source, backup, fresh = (tmp_path / name for name in ("source", "backup", "fresh"))
    source.mkdir()
    initialize(source / "core.sqlite3", "core", repository, instance)
    adapter = SQLiteRecoveryAdapter()
    adapter.create_consistent_backup(source, backup, BackupScope.GIT_ONLY)
    manifest = backup / "manifest.json"
    wire = json.loads(manifest.read_text())
    wire["manifest_version"] = old_version
    manifest.write_text(json.dumps(wire) + "\n")
    (backup / "manifest.json.sha256").write_text(
        hashlib.sha256(manifest.read_bytes()).hexdigest() + "  manifest.json\n"
    )
    with pytest.raises(RestoreValidationError, match="Unsupported manifest version"):
        adapter.restore_backup(backup, fresh, repository)
    assert not fresh.exists()


def _checksummed_wire(wire):
    content = json.dumps(
        {k: v for k, v in wire.items() if k != "digest_sha256"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    wire["digest_sha256"] = hashlib.sha256(content).hexdigest()
    return json.dumps(wire)


def _nominal_package(object_format):
    core = empty_core_section()
    core["git_objects"] = [
        {
            "object_format": object_format,
            "object_oid": "a" * (40 if object_format == "sha1" else 64),
        }
    ]
    return ExchangePackage(
        package_id=str(uuid4()),
        exported_at_us=1,
        sender_catalog_instance_uuidv4=str(uuid4()),
        repository_uuidv4=str(uuid4()),
        selection_scope=ExchangeSelectionScope(
            all_selected=True, include_context=False
        ),
        core=core,
    )


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_nominal_wire_preserves_typed_identity_and_refuses_old_component(object_format):
    package = _nominal_package(object_format)
    wire = json.loads(encode_package(package))
    assert decode_package(json.dumps(wire)).core == package.core
    row = wire["core"]["git_objects"][0]
    row["full_oid"] = row.pop("object_oid")
    with pytest.raises(ExchangeError) as failure:
        decode_package(_checksummed_wire(wire))
    assert failure.value.code == "MALFORMED_ROW"


@pytest.mark.parametrize("old_version", [6, 7])
def test_old_exchange_format_refused_even_with_a_current_checksum(old_version):
    wire = json.loads(encode_package(_nominal_package("sha1")))
    wire["format"] = f"git-repo-db/adr0036-exchange-v{old_version}"
    with pytest.raises(ExchangeError) as failure:
        decode_package(_checksummed_wire(wire))
    assert failure.value.code == "UNSUPPORTED_WIRE_VERSION"


@pytest.mark.parametrize(
    "role", ["direct_target", "resolved_target", "peeled_target", "root"]
)
def test_ref_wire_refuses_old_role_fields_even_when_target_is_unknown(role):
    from repo_catalog.domain.p1_core import Provenance
    from repo_catalog.domain.ref_exchange import claim_from_wire, claim_to_wire
    from repo_catalog.domain.ref_observation import (
        RefObservationClaim,
        RefObservationKey,
    )

    claim = RefObservationClaim(
        RefObservationKey(str(uuid4()), "01890f47-0000-7000-8000-000000000001"),
        Provenance("source", "read", "coordinate", "decoder", "1"),
        "present",
    )
    wire = claim_to_wire(claim)
    assert claim_from_wire(wire) == claim
    wire[f"{role}_oid"] = wire.pop(f"{role}_object_oid")
    with pytest.raises(ValueError, match="exact typed ref wire fields required"):
        claim_from_wire(wire)
