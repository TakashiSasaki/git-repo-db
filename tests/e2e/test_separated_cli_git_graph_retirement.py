"""Ordinary separated CLI preserves ordered merge topology and set queries."""

import hashlib
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.git_acquisition import GitMetadataInput
from repo_catalog.domain.p1_repository import OID, NativeObject, native_object_oid
from tests.e2e.test_separated_cli import document, init, run


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_normal_cli_ordered_merge_graph_compare_empty_tree_and_exact_repeat(
    tmp_path, capsys, fmt
):
    catalog = tmp_path / "catalog"
    identity = init(capsys, catalog)
    init(capsys, catalog, "operational")
    objects = []

    def native(kind, body):
        oid = OID(fmt, native_object_oid(fmt, kind, body))
        objects.append(
            NativeObject(oid, kind, body, len(body), hashlib.sha256(body).hexdigest())
        )
        return oid

    tree = native("tree", b"")
    commits = {}
    for name, parents in (
        ("A", ()),
        ("B", ("A",)),
        ("C", ("A",)),
        ("M", ("B", "C")),
        ("N", ("M",)),
    ):
        body = (
            f"tree {tree.object_oid}\n"
            + "".join(f"parent {commits[parent].object_oid}\n" for parent in parents)
            + "author Test <test@example.test> 0 +0000\n"
            + "committer Test <test@example.test> 0 +0000\n\n"
            + name
            + "\n"
        ).encode()
        commits[name] = native("commit", body)
    unit = GitMetadataInput(
        identity["repository_uuidv4"],
        str(uuid4()),
        str(uuid4()),
        "ordered-native-topology",
        1,
        native_objects=tuple(objects),
    )
    path = document(tmp_path, "native-graph.json", unit)
    args = (
        "acquire",
        "git-metadata",
        "--catalog",
        catalog,
        "--input",
        path,
        "--new-request",
    )
    assert run(capsys, *args)["retained_objects"]

    def query(command, *options):
        return run(
            capsys, "query", command, "--catalog", catalog, "--format", fmt, *options
        )

    history = query("log", "--object-oid", commits["N"].object_oid)
    assert history["status"] == "complete" and not history["missing"]
    assert [row["object_oid"] for row in history["items"]] == [
        list(commits[name].key) for name in ("N", "M", "B", "A", "C")
    ]
    first = query("log", "--object-oid", commits["N"].object_oid, "--first-parent")
    assert first["status"] == "complete"
    assert [row["object_oid"] for row in first["items"]] == [
        list(commits[name].key) for name in ("N", "M", "B", "A")
    ]
    for selection, names in (
        ("left-only", ("N", "M", "B")),
        ("right-only", ()),
        ("common", ("A", "C")),
        ("symmetric", ("N", "M", "B")),
    ):
        compared = query(
            "compare",
            "--left",
            commits["N"].object_oid,
            "--right",
            commits["C"].object_oid,
            "--set",
            selection,
        )
        assert compared["status"] == "complete"
        assert {tuple(key) for key in compared["items"]} == {
            commits[name].key for name in names
        }
    for name in ("M", "N"):
        empty = query("tree", "--object-oid", commits[name].object_oid)
        assert empty["status"] == "complete" and empty["items"] == []
    with closing(connect(catalog / "repository.sqlite3", "repository")) as db:
        tables = ("git_objects", "retained_metadata")
        before = [
            db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in tables
        ]
    run(capsys, *args)
    with closing(connect(catalog / "repository.sqlite3", "repository")) as db:
        assert before == [
            db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in tables
        ]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not (catalog / "context.sqlite3").exists()
    assert not (catalog / "search.sqlite3").exists()


def test_history_distinguishes_known_parent_from_unknown_oid(tmp_path, capsys):
    catalog = tmp_path / "catalog"
    identity = init(capsys, catalog)
    init(capsys, catalog, "operational")
    parent = OID("sha1", "a" * 40)
    body = (
        f"tree {native_object_oid('sha1', 'tree', b'')}\n"
        f"parent {parent.object_oid}\n"
        "author Test <test@example.test> 0 +0000\n"
        "committer Test <test@example.test> 0 +0000\n\n"
        "selected commit\n"
    ).encode()
    head = OID("sha1", native_object_oid("sha1", "commit", body))
    unit = GitMetadataInput(
        identity["repository_uuidv4"],
        str(uuid4()),
        str(uuid4()),
        "selected-commit-history",
        1,
        native_objects=(
            NativeObject(
                head, "commit", body, len(body), hashlib.sha256(body).hexdigest()
            ),
        ),
    )
    run(
        capsys,
        "acquire",
        "git-metadata",
        "--catalog",
        catalog,
        "--input",
        document(tmp_path, "single-commit.json", unit),
        "--new-request",
    )
    unknown = OID("sha1", "b" * 40)
    for start, missing, known in ((head, parent, True), (unknown, unknown, False)):
        history = run(
            capsys,
            "query",
            "log",
            "--catalog",
            catalog,
            "--object-oid",
            start.object_oid,
        )
        assert history["status"] == "partial"
        assert history["missing"] == [list(missing.key)]
        assert history["missing_details"] == [
            {
                "object_oid": list(missing.key),
                "oid_known": known,
                "relations": {
                    "commit_tree": "unobserved",
                    "commit_parents": "unobserved",
                },
            }
        ]
