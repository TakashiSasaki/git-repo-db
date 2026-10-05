import sqlite3

from tests.support.cli import add_local, pages, run
from tests.support.git_fixture import FixtureRepo


def test_initial_and_repeat(catalog):
    state, fixture, repos = catalog
    data = run(state, "sync", "git")
    assert len(data["data"]["results"]) == 3
    refs = pages(state, "refs", "list", "--repo", repos["alpha"])
    assert {r["ref"] for r in refs} == {
        "refs/heads/main",
        "refs/heads/alias",
        "refs/heads/feature",
        "refs/heads/rewrite",
    }
    count = 0
    for name, repo in repos.items():
        for ref in pages(state, "refs", "list", "--repo", repo):
            tree = pages(state, "tree", "list", "--repo", repo, "--ref", ref["ref"])
            count += sum(
                entry["path_utf8"] in ("shared/a.txt", "shared/b.txt", "copy.txt")
                for entry in tree
            )
    assert count == 9
    with sqlite3.connect(state / "catalog.sqlite3") as c:
        counts = [
            c.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("git_objects", "contents", "content_digests")
        ]
    run(state, "sync", "git")
    with sqlite3.connect(state / "catalog.sqlite3") as c:
        assert counts == [
            c.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("git_objects", "contents", "content_digests")
        ]


def test_rewrite_delete(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    snapshots = pages(state, "snapshots", "list", "--repo", repos["alpha"])
    s1 = snapshots[0]["id"]
    content = run(
        state,
        "search",
        "hash",
        "--algorithm",
        "raw-sha256",
        "--digest",
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    )["data"]["items"][0]["content_id"]
    assert len(pages(state, "search", "path", "--content-id", content)) == 9
    fixture.advance()
    run(state, "sync", "git")
    assert len(pages(state, "search", "path", "--content-id", content)) == 7
    assert (
        pages(
            state, "search", "path", "--repo", repos["alpha"], "--path", "old-only.txt"
        )
        == []
    )
    assert pages(
        state,
        "search",
        "path",
        "--repo",
        repos["alpha"],
        "--snapshot",
        s1,
        "--path",
        "old-only.txt",
    )
    messages = pages(
        state,
        "commits",
        "list",
        "--repo",
        repos["alpha"],
        "--ref",
        "refs/heads/rewrite",
    )
    assert any("commit E" in r["message"] for r in messages)


def test_parent_trees_and_empty(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    m = run(
        state,
        "commits",
        "show",
        "--repo",
        repos["alpha"],
        "--commit",
        "sha1:" + fixture.alpha.commits["M"],
    )["data"]["items"][0]
    assert m["parents"] == ["sha1:" + fixture.alpha.commits[x] for x in ("B", "C")]
    n = run(
        state,
        "commits",
        "show",
        "--repo",
        repos["alpha"],
        "--commit",
        "sha1:" + fixture.alpha.commits["N"],
    )["data"]["items"][0]
    assert n["tree"] == m["tree"]
    assert pages(state, "refs", "list", "--repo", repos["empty"]) == []
    comparison = pages(
        state,
        "commits",
        "compare",
        "--repo",
        repos["alpha"],
        "--left",
        "refs/heads/main",
        "--right",
        "refs/heads/feature",
        "--set",
        "left-only",
    )
    assert {r["oid"] for r in comparison} == {
        "sha1:" + fixture.alpha.commits[x] for x in ("B", "M", "N")
    }


def test_sha256_and_dedup(catalog, tmp_path):
    state, fixture, repos = catalog
    extra = FixtureRepo(tmp_path / "sha256.git", "sha256")
    extra.commit("root", {b"copy.txt": b"abc"})
    extra.ref("refs/heads/main", "root")
    rid = add_local(state, "sha256", extra.url)
    run(state, "sync", "git")
    entries = pages(state, "tree", "list", "--repo", rid, "--ref", "refs/heads/main")
    beta = pages(
        state, "tree", "list", "--repo", repos["beta"], "--ref", "refs/heads/main"
    )
    assert entries[0]["oid"].startswith("sha256:")
    assert entries[0]["content_id"] == beta[0]["content_id"]
