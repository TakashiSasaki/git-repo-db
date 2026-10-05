import base64

from tests.support.cli import pages, run


def test_bounded_raw(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    entry = pages(state, "search", "path", "--path", "shared/a.txt")[0]
    content = entry["content_id"]
    default = run(state, "content", "show", "--content-id", content)["data"]["items"][0]
    assert (
        default["requested_length"] == 65536
        and base64.b64decode(default["data_b64"]) == b"abc"
    )
    piece = run(
        state, "content", "show", "--content-id", content, "--offset", 1, "--length", 1
    )["data"]["items"][0]
    assert base64.b64decode(piece["data_b64"]) == b"b" and piece["has_more"]
    run(
        state,
        "content",
        "show",
        "--content-id",
        content,
        "--length",
        1048577,
        expected=2,
    )
    binary = pages(state, "search", "path", "--path", "binary.bin")[0]["content_id"]
    run(state, "content", "show", "--content-id", binary, expected=4)
    run(state, "content", "hydrate", "--content-id", binary, expected=2)
