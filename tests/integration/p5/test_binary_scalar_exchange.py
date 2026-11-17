"""Git surrogateescape scalar facts retain exact bytes across bounded Exchange."""

from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangePackage,
    ExchangeSelectionScope,
    decode_package,
    empty_context_section,
    empty_core_section,
    encode_package,
)
from repo_catalog.domain.git_acquisition import GitNativeAcquisitionRequest
from repo_catalog.domain.p1_core import Provenance, encode
from repo_catalog.domain.scalar_wire import SCALAR_ENCODING, scalar_value_json
from tests.integration.p5.conftest import git, init_catalog_stores, write_git_object


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_actual_non_utf8_commit_tag_scalars_and_bodies_survive_onward_exchange(
    tmp_path, fmt
):
    source, middle, target = (
        tmp_path / name for name in ("source", "middle", "target")
    )
    repository, _ = init_catalog_stores(source, stores=("core", "operational"))
    native = tmp_path / "native.git"
    native.mkdir()
    git(native, "init", "--bare", "--object-format=" + fmt)
    tree = write_git_object(native, fmt, "tree", b"")
    commit_body = (
        b"tree " + tree.object_oid.encode() + b"\nauthor A\xff <a@invalid> 1 +0930\n"
        b"committer C\xfe <c@invalid> 1 +0000\n\ncommit message\xfftail\n"
    )
    commit = write_git_object(native, fmt, "commit", commit_body)
    tag_body = (
        b"object " + commit.object_oid.encode() + b"\ntype commit\ntag raw-\xff\n"
        b"tagger T\xfe <t@invalid> 1 +0000\n\ntag message\xfftail\n"
    )
    tag = write_git_object(native, fmt, "tag", tag_body)
    GitAcquisition(source, operational=source).acquire_from_native(
        GitNativeSource(native),
        GitNativeAcquisitionRequest(
            repository,
            str(uuid4()),
            str(uuid4()),
            "actual-git-input",
            100,
            select_object_oids=(tag, commit, tree),
            include_refs=False,
        ),
        new_request=True,
    )
    expected = {}
    with closing(GitCore(source / "core.sqlite3")) as core:
        for oid, field in (
            (commit, "author"),
            (commit, "message"),
            (tag, "tag_name"),
            (tag, "tagger"),
            (tag, "message"),
        ):
            expected[(oid, field)] = core.scalar(oid, field).canonical
            assert any(0xDC80 <= ord(c) <= 0xDCFF for c in expected[(oid, field)][1])
    service = ExchangeService(source)
    partial = service.export_package(
        selection=ExchangeSelectionScope(
            all_selected=True, include_context=False, include_retained_bytes=False
        )
    )
    assert any(
        row.get("value_encoding") == SCALAR_ENCODING
        for row in partial.core["scalar_claims"]
    )
    assert partial.core["retained_metadata"] == []
    wire = encode_package(partial)
    assert wire.encode("utf-8")
    assert decode_package(wire).digest_sha256 == partial.digest_sha256
    for directory in (middle, target):
        init_catalog_stores(
            directory, repository_uuidv4=repository, stores=("core", "operational")
        )
    ExchangeService(middle).import_package(
        decode_package(wire),
        new_request=True,
        permitted_repository_uuidv4s=(repository,),
    )
    onward = ExchangeService(middle).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_context=False)
    )
    ExchangeService(target).import_package(
        decode_package(encode_package(onward)),
        new_request=True,
        permitted_repository_uuidv4s=(repository,),
    )
    with closing(GitCore(target / "core.sqlite3")) as core:
        for (oid, field), original in expected.items():
            assert any(
                candidate["value"] == original
                for candidate in core.scalar(oid, field).alternatives
            )
    complete = service.export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_context=False)
    )
    ExchangeService(middle).import_package(
        decode_package(encode_package(complete)),
        new_request=True,
        permitted_repository_uuidv4s=(repository,),
    )
    onward = ExchangeService(middle).export_package(
        selection=ExchangeSelectionScope(all_selected=True, include_context=False)
    )
    destination = ExchangeService(target)
    destination.import_package(
        decode_package(encode_package(onward)),
        new_request=True,
        permitted_repository_uuidv4s=(repository,),
    )
    assert destination.import_package(
        onward, permitted_repository_uuidv4s=(repository,)
    ).idempotent_replay
    with closing(GitCore(target / "core.sqlite3")) as core:
        assert core.read_metadata(commit) == commit_body
        assert core.read_metadata(tag) == tag_body
        for (oid, field), original in expected.items():
            assert core.scalar(oid, field).canonical == original
            assert core.scalar(oid, field).canonical[1].encode(
                "utf-8", "surrogateescape"
            ) == original[1].encode("utf-8", "surrogateescape")


@pytest.mark.parametrize(
    "encoding,value",
    [
        ("unrecognized", encode(["known", "x\udcff"])),
        (SCALAR_ENCODING, encode(["known", "ordinary UTF-8"])),
        (SCALAR_ENCODING, encode(["known", "x\ud800"])),
        (SCALAR_ENCODING, encode(["known", "x\udc7f"])),
        (SCALAR_ENCODING, '["known", "x\\udcff"]'),
        (SCALAR_ENCODING, encode(["known", ["x\udcff"]])),
    ],
)
def test_malformed_or_unnecessary_ascii_scalar_variant_is_refused(encoding, value):
    core = empty_core_section()
    core["scalar_claims"] = [
        {
            "object_format": "sha1",
            "object_oid": "1" * 40,
            "field": "message",
            "provenance_json": Provenance(
                "source", "read", "message", "git", "1"
            ).encoded,
            "authority": "reported",
            "value_encoding": encoding,
            "value_ascii": value,
        }
    ]
    with pytest.raises(ExchangeError) as refusal:
        ExchangePackage(
            str(uuid4()),
            100,
            str(uuid4()),
            str(uuid4()),
            selection_scope=ExchangeSelectionScope(
                all_selected=True, include_context=False
            ),
            core=core,
        )
    assert refusal.value.code == "INVALID_SCALAR_ENCODING"


def test_ascii_variant_decodes_only_exact_canonical_git_surrogateescape_string():
    raw = encode(["known", "A\udcff\x00suffix"])
    assert (
        scalar_value_json({"value_encoding": SCALAR_ENCODING, "value_ascii": raw})
        == raw
    )
    with pytest.raises(ExchangeError):
        scalar_value_json(
            {"value_encoding": SCALAR_ENCODING, "value_ascii": raw, "value_json": raw}
        )


def test_context_text_keeps_strict_utf8_boundary():
    context = empty_context_section()
    context["text_bodies"] = [{"sha256": "1" * 64, "utf8": "not Context UTF-8\udcff"}]
    with pytest.raises(ExchangeError) as refusal:
        ExchangePackage(
            str(uuid4()),
            100,
            str(uuid4()),
            str(uuid4()),
            selection_scope=ExchangeSelectionScope(all_selected=True),
            context=context,
        )
    assert refusal.value.code == "MALFORMED_JSON"
