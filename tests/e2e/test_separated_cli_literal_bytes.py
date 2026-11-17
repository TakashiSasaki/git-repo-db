"""Permitted metadata literal search verifies original bytes before returning hits."""

import base64
import hashlib
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.domain.git_acquisition import GitMetadataInput
from repo_catalog.domain.p1_core import OID, NativeObject, native_object_oid
from tests.e2e.test_separated_cli import document, init, run


def setup(tmp_path, capsys, fmt):
    catalog = tmp_path / "catalog"
    identity = init(capsys, catalog, "core")
    init(capsys, catalog, "operational")
    blob = "1" * (40 if fmt == "sha1" else 64)
    tree_body = b"".join(
        b"100644 " + name + b"\0" + bytes.fromhex(blob)
        for name in (rb"\xff-literal.txt", b"\xff\tline\n.txt")
    )
    tree = OID(fmt, native_object_oid(fmt, "tree", tree_body))
    messages = (
        b"\xff" + "日本語".encode() + b"\n",
        b"\xff gap \\xff literal\n" + "� actual\n".encode(),
    )
    bodies = [
        (
            f"tree {tree.object_oid}\nauthor Test <test@example.test> 1700000000 +0000\n"
            "committer Test <test@example.test> 1700000000 +0000\n\n"
        ).encode()
        + message
        for message in messages
    ]
    commits = tuple(OID(fmt, native_object_oid(fmt, "commit", body)) for body in bodies)
    native = tuple(
        NativeObject(oid, kind, body, len(body), hashlib.sha256(body).hexdigest())
        for oid, kind, body in (
            (tree, "tree", tree_body),
            *((oid, "commit", body) for oid, body in zip(commits, bodies)),
        )
    )
    unit = GitMetadataInput(
        identity["repository_uuidv4"],
        str(uuid4()),
        str(uuid4()),
        "explicit-native-metadata",
        100,
        object_format=fmt,
        native_objects=native,
    )
    run(
        capsys,
        "acquire",
        "git-metadata",
        "--catalog",
        catalog,
        "--input",
        document(tmp_path, "native-literals.json", unit),
        "--new-request",
    )
    return catalog, unit, tree, commits, messages


def search(capsys, catalog, text, *options, expected=0):
    return run(
        capsys,
        "query",
        "search",
        "--catalog",
        catalog,
        "--kinds",
        "git_metadata",
        "--query",
        text,
        *options,
        expected=expected,
    )


def messages(result):
    return [
        hit
        for hit in result["hits"]
        if hit["authoritative_summary"].get("field") == "message"
    ]


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_normal_cli_literal_bytes_survive_reparse_and_index_without_escape_matches(
    tmp_path, capsys, fmt
):
    catalog, unit, tree, commits, originals = setup(tmp_path, capsys, fmt)

    def check():
        assert search(capsys, catalog, "�日本")["hits"] == []
        japanese = messages(search(capsys, catalog, "日本語"))
        assert japanese and {
            hit["authoritative_summary"]["object_oid"] for hit in japanese
        } == {commits[0].object_oid}
        for hit in japanese:
            match = hit["authoritative_summary"]["literal_match"]
            assert (match["byte_start"], match["byte_end"], match["line"]) == (1, 10, 1)
            assert base64.b64decode(match["source_bytes"]["$bytes"]) == originals[0]
        escaped = search(capsys, catalog, r"\xff")
        assert {
            hit["authoritative_summary"]["object_oid"] for hit in messages(escaped)
        } == {commits[1].object_oid}
        for hit in escaped["hits"]:
            assert b"\\xff" in base64.b64decode(
                hit["authoritative_summary"]["literal_match"]["source_bytes"]["$bytes"]
            )
            assert "_literal_source_bytes" not in hit["authoritative_summary"]
        replacement = messages(search(capsys, catalog, "�"))
        assert replacement and {
            hit["authoritative_summary"]["object_oid"] for hit in replacement
        } == {commits[1].object_oid}
        for hit in replacement:
            match = hit["authoritative_summary"]["literal_match"]
            start = originals[1].index("�".encode())
            assert (match["byte_start"], match["byte_end"], match["line"]) == (
                start,
                start + 3,
                2,
            )
            assert "� actual" in hit["matched_text"]

    check()
    init(capsys, catalog, "search")
    run(
        capsys,
        "query",
        "search-rebuild",
        "--catalog",
        catalog,
        "--kinds",
        "git_metadata",
    )
    check()
    request = [str(uuid4()), str(uuid4())]
    reparse_unit = replace(
        unit,
        native_objects=(),
        capture_uuidv4=str(uuid4()),
        observed_at_us=200,
        source_attribution="explicit-reparse",
    )
    run(
        capsys,
        "reparse",
        "--catalog",
        catalog,
        "--input",
        document(
            tmp_path,
            "reparse-literals.json",
            {"unit": reparse_unit, "objects": (tree, *commits)},
        ),
        "--request-origin",
        request[0],
        "--request",
        request[1],
        "--new-request",
        "--errors",
        "replace",
        "--metadata-errors",
        "replace",
    )
    check()
    run(
        capsys,
        "query",
        "search-rebuild",
        "--catalog",
        catalog,
        "--kinds",
        "git_metadata",
    )
    check()
    assert not (catalog / "context.sqlite3").exists()
    assert not (catalog / "p1-recovery-stop.json").exists()


def test_normal_cli_note_search_uses_checked_note_bytes_instead_of_display_escapes(
    tmp_path, capsys
):
    from repo_catalog.adapters.git.native import GitNativeSource
    from repo_catalog.application.git_acquisition import GitAcquisition
    from repo_catalog.domain.git_acquisition import (
        GitNativeAcquisitionRequest,
        NotesAcquisitionSpec,
    )
    from tests.integration.p5.conftest import (
        build_sample_git_repo,
        git,
        tree_entry,
        write_git_object,
    )

    catalog, native = tmp_path / "catalog", tmp_path / "native"
    identity = init(capsys, catalog, "core")
    init(capsys, catalog, "operational")
    objects = build_sample_git_repo(native, "sha1")
    raw = b"\xff" + "日本語".encode() + b"\n\\xff actual\n"
    note = write_git_object(native, "sha1", "blob", raw)
    tree = write_git_object(
        native,
        "sha1",
        "tree",
        tree_entry(b"100644", objects["commit2"].object_oid.encode(), note),
    )
    commit = write_git_object(
        native,
        "sha1",
        "commit",
        (
            f"tree {tree.object_oid}\nauthor Note <note@example.test> 1700000000 +0000\ncommitter Note <note@example.test> 1700000000 +0000\n\nactual notes root\n"
        ).encode(),
    )
    git(native, "update-ref", "refs/notes/commits", commit.object_oid)
    report = GitAcquisition(catalog, operational=catalog).acquire_from_native(
        GitNativeSource(native),
        GitNativeAcquisitionRequest(
            identity["repository_uuidv4"],
            str(uuid4()),
            str(uuid4()),
            "explicit-note-source",
            100,
            select_object_oids=(objects["commit2"],),
            notes=NotesAcquisitionSpec(
                discover_notes=True,
                acquire_inventories=True,
                target_object_oids=(objects["commit2"],),
                retain_note_bodies=True,
            ),
        ),
        new_request=True,
    )
    assert report.status == "complete" and any(
        item.role_verified and item.body_retained
        for item in report.ref_note_acquisitions
    )

    def note_search(query):
        return run(
            capsys,
            "query",
            "search",
            "--catalog",
            catalog,
            "--kinds",
            "notes",
            "--query",
            query,
        )

    def check():
        assert note_search("�日本")["hits"] == []
        for query in ("日本語", r"\xff"):
            result = note_search(query)
            assert result["hits"]
            for hit in result["hits"]:
                summary = hit["authoritative_summary"]
                assert summary["role_verified"] and summary["note_retained"]
                match = summary["literal_match"]
                assert base64.b64decode(match["source_bytes"]["$bytes"]) == raw
                assert match["byte_start"] == raw.index(query.encode())

    check()
    init(capsys, catalog, "search")
    run(capsys, "query", "search-rebuild", "--catalog", catalog, "--kinds", "notes")
    check()
