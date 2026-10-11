import base64

from repo_catalog.adapters.sqlite.store import Store
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
        entries["over-limit.txt"]["raw_available"]
        and entries["over-limit.txt"]["text_state"] == "oversize"
        and entries["over-limit.txt"]["byte_length"] == 8388609
    )
    assert (
        entries["nul.txt"]["text_state"] == "nul"
        and entries["invalid.txt"]["text_state"] == "non_utf8"
    )
    assert entries["nul.txt"]["raw_available"]
    with Store(state, readonly=True) as store:
        canonical = store.one(
            "SELECT b.body FROM blob_content_map c JOIN available_git_objects g USING(git_object_id) JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 WHERE c.content_id=?",
            (entries["nul.txt"]["content_id"],),
        )
        assert canonical[0] == b"a\0b"
    nul = run(
        state,
        "content",
        "show",
        "--content-id",
        entries["nul.txt"]["content_id"],
        expected=4,
    )
    assert nul["error"]["details"]["reason"] == "nul"
    excluded = run(
        state,
        "content",
        "show",
        "--content-id",
        entries["over-limit.txt"]["content_id"],
        "--offset",
        8388607,
        "--length",
        2,
        expected=4,
    )
    assert excluded["error"]["details"]["reason"] == "oversize"
    bounded = run(
        state,
        "content",
        "show",
        "--content-id",
        entries["at-limit.txt"]["content_id"],
        "--offset",
        8388606,
        "--length",
        2,
    )["data"]["items"][0]
    assert base64.b64decode(bounded["data_b64"]) == b"zz"
    assert bounded["byte_length"] == 8388608 and not bounded["has_more"]
    # Canonical raw Git bytes remain available independently of text eligibility.
    # History follows ancestors of the selected capture, including old.txt.
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
