from tests.support.cli import add_local, pages, run
from tests.support.git_fixture import FixtureRepo


def test_text_bounds(catalog, tmp_path):
    state, fixture, repos = catalog
    repo = FixtureRepo(tmp_path / "bounds.git")
    repo.commit("past", {b"old.txt": "過去専用".encode()})
    repo.commit(
        "tip",
        {
            b"at-limit.txt": b"z" * 8388608,
            b"over-limit.txt": b"z" * 8388609,
            b"nul.txt": b"a\0b",
            b"invalid.txt": b"\xff",
            b"bom-crlf.txt": b"\xef\xbb\xbfA\r\n",
        },
        ("past",),
    )
    repo.ref("refs/heads/main", "tip")
    ident = add_local(state, "bounds", repo.url)
    run(state, "sync", "git", "--repo", ident)
    entries = {
        r["path_utf8"]: r
        for r in pages(
            state, "tree", "list", "--repo", ident, "--ref", "refs/heads/main"
        )
    }
    assert entries["at-limit.txt"]["raw_available"]
    assert (
        not entries["over-limit.txt"]["raw_available"]
        and entries["over-limit.txt"]["text_state"] == "oversize"
    )
    assert (
        entries["nul.txt"]["text_state"] == "nul"
        and entries["invalid.txt"]["text_state"] == "non_utf8"
    )
    assert run(
        state,
        "search",
        "code",
        "--repo",
        ident,
        "--literal",
        "過去専用",
        "--scope",
        "history",
        expected=3,
    )["coverage"]["missing"]
    past = run(
        state,
        "tree",
        "list",
        "--repo",
        ident,
        "--commit",
        "sha1:" + repo.commits["past"],
    )["data"]["items"][0]
    assert past["content_id"]
    run(
        state, "content", "hydrate", "--content-id", past["content_id"], "--repo", ident
    )
    assert pages(
        state,
        "search",
        "code",
        "--repo",
        ident,
        "--literal",
        "過去専用",
        "--scope",
        "history",
    )
