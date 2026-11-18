"""Actual separated reads cover residual metadata and gitlink obligations."""

from uuid import uuid4

import pytest

from repo_catalog.application.git_history_query import GitHistoryQuery
from repo_catalog.application.metadata_reparse import reparse
from repo_catalog.domain.git_native import DECODER, DECODER_VERSION
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.p1_repository import Provenance, ScalarClaim, encode
from tests.integration.p1.test_repository import Budget, native, oid
from tests.integration.p2.conftest import repository_store as repository_store
from tests.integration.p2.test_native import commit_body, entry
from tests.integration.p2.test_retired_git_obligations import reparse_fixture


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_actual_commit_message_decoders_keep_both_original_settings_and_values(
    repository_store, fmt
):
    # This case compares valid message decoders, independently of the separate
    # invalid author-byte controls supplied by commit_body's default fixture.
    body = commit_body(oid("a", fmt), message=b"caf\xc3\xa9\n").replace(b"A\xff", b"A")
    incoming = native("commit", body, fmt)
    store, path, unit = reparse_fixture(repository_store, incoming)
    original_native = store.scalar(incoming.object_oid, "message").canonical
    for encoding in ("utf-8", "latin-1"):
        reparse(
            path.parent,
            unit,
            (incoming.object_oid,),
            request=RequestIdentity(str(uuid4()), str(uuid4())),
            new_request=True,
            text_encoding=encoding,
            metadata_encoding=encoding,
            metadata_errors="strict",
        )
    result = store.scalar(incoming.object_oid, "message")
    reports = [
        item
        for item in result.alternatives
        if item["provenance"][2:4] == ["reparse-message", DECODER]
    ]
    assert len(reports) == 2
    assert {item["value"][1] for item in reports} == {"café\n", "cafÃ©\n"}
    assert all(item["checked"] is False for item in reports)
    assert result.canonical == original_native
    for encoding in ("utf-8", "latin-1"):
        settings = {
            "text_encoding": encoding,
            "errors": "surrogateescape",
            "metadata_encoding": encoding,
            "metadata_errors": "strict",
        }
        version = DECODER_VERSION + ":" + encode(settings)
        assert any(item["provenance"][4] == version for item in reports)
    assert store.read_metadata(incoming.object_oid) == incoming.body


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_real_gitlink_query_is_a_boundary_without_child_or_file_body_gaps(
    repository_store, fmt
):
    store, path, _ = repository_store
    missing = oid("a", fmt)
    incoming = native("tree", entry(b"160000", b"submodule", missing), fmt)
    store.admit_metadata(incoming, str(uuid4()), Budget())
    result = GitHistoryQuery(path.parent).tree(incoming.object_oid, recursive=True)
    assert result["status"] == "complete"
    assert result["missing"] == []
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["path"] == b"submodule" and item["mode"] == "160000"
    assert item["object_oid"] == missing.object_oid
    assert item["qualification"] == "receiver_intrinsic"
    assert store.scalar(missing, "type").canonical is None
    assert store.sql("SELECT count(*) FROM retained_metadata")[0][0] == 1
    assert store.sql("SELECT count(*) FROM ref_retained_notes")[0][0] == 0


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_malformed_reported_decoder_settings_do_not_hide_valid_actual_tree_decode(
    repository_store, fmt
):
    raw = b"caf\xc3\xa9.txt"
    incoming = native("tree", entry(b"100644", raw, oid("a", fmt)), fmt)
    store, path, unit = reparse_fixture(repository_store, incoming)
    original = Provenance(
        "independent", "original", "tree-entry", "third_party.decoder", "999"
    )
    for field, value in (
        ("raw_name_hex", raw.hex()),
        ("decoded_name", "fabricated"),
        ("decoder_settings", "NOT_VALID_JSON{"),
    ):
        store.admit_claim(ScalarClaim(incoming.object_oid, field, value, original))
    reparse(
        path.parent,
        unit,
        (incoming.object_oid,),
        request=RequestIdentity(str(uuid4()), str(uuid4())),
        new_request=True,
        metadata_encoding="utf-8",
        metadata_errors="strict",
    )
    result = GitHistoryQuery(path.parent).tree(incoming.object_oid)
    item = result["items"][0]
    assert item["decoded_name"] == "café.txt" and not item["decoder_conflict"]
    assert len(item["decoded_name_candidates"]) == 1
    assert store.scalar(incoming.object_oid, "decoded_name").reported_conflict
    assert store.read_metadata(incoming.object_oid) == incoming.body
