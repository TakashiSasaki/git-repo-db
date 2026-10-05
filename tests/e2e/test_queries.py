from tests.support.cli import pages, run


def test_commit_literal_checks_original_bytes(catalog):
    import base64

    from tests.support.git_fixture import git

    state, fixture, repos = catalog
    message = b"\xff" + "日本語".encode("utf8") + b"\n"
    headers = (
        f"tree {fixture.alpha.trees['M']}\nparent {fixture.alpha.commits['N']}\n"
        "author Fixture <fixture@example.invalid> 1700000000 +0000\n"
        "committer Fixture <fixture@example.invalid> 1700000000 +0000\n\n"
    ).encode()
    oid = (
        git(
            fixture.alpha.path,
            "hash-object",
            "-t",
            "commit",
            "-w",
            "--stdin",
            input=headers + message,
        )
        .strip()
        .decode()
    )
    git(fixture.alpha.path, "update-ref", "refs/heads/legacy", oid)
    run(state, "sync", "git")
    for indexed in (False, True):
        if indexed:
            run(state, "index", "rebuild", "--kind", "commits")
        assert not pages(
            state, "search", "commits", "--repo", repos["alpha"], "--literal", "�日本"
        )
        hits = pages(
            state, "search", "commits", "--repo", repos["alpha"], "--literal", "日本語"
        )
        assert len(hits) == 1 and hits[0]["oid"] == "sha1:" + oid
        assert hits[0]["byte_start"] == 1 and hits[0]["byte_end"] == 10
        assert base64.b64decode(hits[0]["message_b64"]) == message


def test_root_scopes(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    fixture.advance()
    run(state, "sync", "git")
    assert (
        pages(
            state,
            "search",
            "path",
            "--repo",
            repos["alpha"],
            "--path",
            "old-only.txt",
            "--scope",
            "current",
        )
        == []
    )
    assert (
        pages(
            state,
            "search",
            "path",
            "--repo",
            repos["alpha"],
            "--path",
            "old-only.txt",
            "--scope",
            "history",
        )
        == []
    )
    assert pages(
        state,
        "search",
        "path",
        "--repo",
        repos["alpha"],
        "--path",
        "old-only.txt",
        "--scope",
        "recorded",
    )
    assert pages(state, "search", "code", "--literal", "認証")
    assert pages(state, "search", "code", "--literal", "X")
    run(state, "search", "code", "--literal", "x", "--ref-kind", "tag", expected=2)


def test_raw_paths(catalog):
    import base64

    state, fixture, repos = catalog
    run(state, "sync", "git")
    raw = b"odd/\xff\tline\n.txt"
    rows = pages(state, "search", "path", "--path-b64", base64.b64encode(raw).decode())
    assert rows and all(
        base64.b64decode(r["path_b64"]) == raw and r["path_utf8"] is None for r in rows
    )


def test_pr_root_scopes(catalog):
    from tests.e2e.test_github_sync import configure
    from tests.support.github_fixture import GitHubFixture

    state, fixture, repos = catalog
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        run(state, "sync", "all", "--repo", repo, env=env)
    assert pages(state, "search", "path", "--repo", repo, "--path", "pr-only.txt") == []
    assert (
        pages(
            state,
            "search",
            "path",
            "--repo",
            repo,
            "--path",
            "pr-only.txt",
            "--scope",
            "history",
        )
        == []
    )
    assert pages(
        state,
        "search",
        "path",
        "--repo",
        repo,
        "--path",
        "pr-only.txt",
        "--scope",
        "history",
        "--pr",
        41,
    )
    assert pages(
        state,
        "search",
        "path",
        "--repo",
        repo,
        "--path",
        "pr-only.txt",
        "--scope",
        "recorded",
    )
    assert pages(
        state,
        "search",
        "path",
        "--repo",
        repo,
        "--path",
        "old-only.txt",
        "--scope",
        "history",
        "--ref-kind",
        "head",
        "--ref-kind",
        "pr-head",
    )
    snapshot = pages(state, "snapshots", "list", "--repo", repo)[0]["id"]
    run(
        state,
        "search",
        "path",
        "--repo",
        repo,
        "--path",
        "pr-only.txt",
        "--scope",
        "history",
        "--pr",
        41,
        "--snapshot",
        snapshot,
        expected=2,
    )
