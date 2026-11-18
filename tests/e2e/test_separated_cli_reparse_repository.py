"""Selected Git Repository identity is independent of the physical catalog seed."""

from dataclasses import replace
from uuid import uuid4

from tests.e2e.test_separated_cli import document, init, run, seed_metadata


def test_reparse_selected_repository_preserves_the_physical_catalog_identity(
    tmp_path, capsys
):
    catalog, identity, tree, _, original = seed_metadata(tmp_path, capsys)
    selected = str(uuid4())
    capture = replace(
        original,
        repository_uuidv4=selected,
        capture_origin_uuidv4=str(uuid4()),
        capture_uuidv4=str(uuid4()),
        native_objects=(),
        nominal_objects=(tree,),
    )
    declared = document(tmp_path, "selected-repository.json", capture)
    assert (
        run(
            capsys,
            "acquire",
            "git-metadata",
            "--catalog",
            catalog,
            "--input",
            declared,
            "--new-request",
        )["repository_uuidv4"]
        == selected
    )
    payload = document(
        tmp_path, "reparse-selected.json", {"unit": capture, "objects": [tree]}
    )
    reparsed = run(
        capsys,
        "reparse",
        "--catalog",
        catalog,
        "--input",
        payload,
        "--request-origin",
        str(uuid4()),
        "--request",
        str(uuid4()),
        "--new-request",
    )
    assert reparsed["repository_uuidv4"] == selected
    assert (
        init(capsys, catalog, "repository")["repository_uuidv4"]
        == identity["repository_uuidv4"]
    )
    tree_view = run(
        capsys, "query", "tree", "--catalog", catalog, "--object-oid", tree.object_oid
    )
    assert tree_view["items"][0]["decoded_name"] == "file"
    assert not (catalog / "context.sqlite3").exists()
