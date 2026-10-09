from tests.support.cli import add_local, pages, run
from tests.support.git_fixture import FixtureRepo, git


def test_repeat_reuses_durable_objects(catalog, monkeypatch):
    import subprocess

    from repo_catalog.application.collection_service import CollectionService
    from repo_catalog.application.contracts import CollectionRequest

    state, fixture, repos = catalog
    run(state, "sync", "git")
    popen = subprocess.Popen
    requested = []

    def inspect_batch(args, *positional, **kwargs):
        if "cat-file" in args and "--batch" in args:
            stream = kwargs["stdin"]
            requested.append(stream.read().splitlines())
            stream.seek(0)
        return popen(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", inspect_batch)
    result = CollectionService(state).sync(CollectionRequest("git"))
    assert result.status == "complete"
    assert requested and all(not batch for batch in requested)
    fixture.advance()
    requested.clear()
    assert CollectionService(state).sync(CollectionRequest("git")).status == "complete"
    assert any(requested)
    assert all(fixture.alpha.commits["N"].encode() not in batch for batch in requested)


def test_related_oid_reuses_published_local_closure(catalog, monkeypatch):
    from repo_catalog.adapters.git.importer import GitImporter
    from repo_catalog.adapters.git.runner import GitRunner
    from repo_catalog.adapters.sqlite.store import Store
    from repo_catalog.application.job_service import JobService
    from repo_catalog.domain.models import CancellationToken

    state, fixture, repos = catalog
    run(state, "sync", "git")

    def no_transfer(*args, **kwargs):
        raise AssertionError("Already published direct OID must not fetch again")

    monkeypatch.setattr(GitRunner, "transfer", no_transfer)
    import subprocess

    popen = subprocess.Popen
    requested = []

    def inspect_batch(args, *positional, **kwargs):
        if "cat-file" in args and "--batch" in args:
            stream = kwargs["stdin"]
            requested.append(stream.read().splitlines())
            stream.seek(0)
        return popen(args, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", inspect_batch)
    with Store(state) as store:
        repo = store.one(
            "SELECT * FROM repositories WHERE repository_uuidv4=?", (repos["alpha"],)
        )
        job = JobService(store).create("sync", {})
        root = {
            "ref": fixture.alpha.commits["N"],
            "expected": fixture.alpha.commits["N"],
            "role": "base",
            "number": 41,
        }
        result = GitImporter(store, CancellationToken()).sync(
            repo, job, pr_roots=[root]
        )
        assert result["state"] == "complete"
        acquired = store.one(
            "SELECT role,oid,published FROM acquisition_roots WHERE git_acquisition_id=?",
            (result["git_acquisition_id"],),
        )
        assert acquired["role"] == "traversal" and acquired["published"] == 1
        assert acquired["oid"].hex() == fixture.alpha.commits["N"]
        assert requested and all(not batch for batch in requested)
        assert (
            store.one(
                "SELECT count(*) FROM repository_object_sources WHERE git_acquisition_id=?",
                (result["git_acquisition_id"],),
            )[0]
            > 0
        )
        assert store.one(
            "SELECT 1 FROM git_acquisition_publications WHERE git_acquisition_id=?",
            (result["git_acquisition_id"],),
        )


def test_manifest_generation_publishes_bounded_rows_in_new_result(catalog):
    import math

    from repo_catalog.adapters.git.parsing import GitParsing
    from repo_catalog.adapters.sqlite.parser_model import ParserModel
    from repo_catalog.adapters.sqlite.store import Store

    state, fixture, repos = catalog
    run(state, "sync", "git")
    oid = fixture.alpha.trees["A"]
    expected = len(git(fixture.alpha.path, "ls-tree", "-r", "-z", oid).split(b"\0")) - 1
    statements = []
    with Store(state) as store:
        tree = store.git_object_id("sha1", bytes.fromhex(oid))
        original = store.one(
            "SELECT parsed_result_uuidv4,git_acquisition_id FROM current_snapshots WHERE repository_uuidv4=?",
            (repos["alpha"],),
        )
        assert not store.one(
            "SELECT complete FROM root_manifests WHERE parsed_result_uuidv4=? AND tree_git_object_id=?",
            (original[0], tree),
        )[0]
        store.config["collection"]["write_batch_rows"] = 2
        model = ParserModel(store.connection)
        with store.transaction():
            result = model.create_result(
                model.ensure_builtin_profile(),
                repository_uuidv4=repos["alpha"],
                inputs=[{"git_acquisition_id": original[1]}],
            )
        parser = GitParsing(store, result)
        parser.parse_acquisition(original[1], [])
        store.connection.set_trace_callback(statements.append)
        parser.manifest(tree)
        store.connection.set_trace_callback(None)
        with store.transaction():
            model.publish_result(result)
        assert (
            store.one(
                "SELECT count(*) FROM root_manifest_entries WHERE parsed_result_uuidv4=? AND tree_git_object_id=?",
                (result, tree),
            )[0]
            == expected
        )
        assert (
            store.one(
                "SELECT complete FROM root_manifests WHERE parsed_result_uuidv4=? AND tree_git_object_id=?",
                (original[0], tree),
            )[0]
            == 0
        )
        assert (
            store.one(
                "SELECT parsed_result_uuidv4 FROM current_snapshots WHERE repository_uuidv4=?",
                (repos["alpha"],),
            )[0]
            == original[0]
        )
    # Manifest entries are staged in bounded transactions, then completed in
    # one final boundary. Exact output publication belongs to the new result.
    inserts = [
        sql
        for sql in statements
        if sql.startswith("INSERT INTO root_manifest_entries(")
    ]
    # SQLite repeats the originating SQL in its trace for every trigger call.
    assert len(set(inserts)) == expected
    assert all(" VALUES(" in sql and "),(" not in sql for sql in inserts)
    assert statements.count("COMMIT") == math.ceil(expected / 2) + 1


def test_tags_paths_links(catalog, tmp_path):
    state, fixture, repos = catalog
    extra = FixtureRepo(tmp_path / "tags.git")
    files = {
        b"link": ("120000", b"not-existing"),
        b"exec": ("100755", b"run"),
        b"submodule": ("160000", "ab" * 20),
        b"lfs": b"version https://git-lfs.github.com/spec/v1\noid sha256:"
        + b"ab" * 32
        + b"\nsize 999\n",
    }
    extra.commit("root", files)
    extra.ref("refs/heads/main", "root")
    git(extra.path, "tag", "-a", "v1", extra.commits["root"], "-m", "tag")
    blob = extra.blob(b"tag-only")
    git(extra.path, "update-ref", "refs/tags/blob", blob)
    git(extra.path, "update-ref", "refs/tags/tree", extra.trees["root"])
    ident = add_local(state, "tags", extra.url)
    run(state, "sync", "git", "--repo", ident)
    refs = pages(state, "refs", "list", "--repo", ident)
    assert (
        len(refs) == 4
        and next(r for r in refs if r["ref"] == "refs/tags/v1")["peeled_oid"]
        == "sha1:" + extra.commits["root"]
    )
    entries = {
        r["path_utf8"]: r
        for r in pages(
            state, "tree", "list", "--repo", ident, "--ref", "refs/heads/main"
        )
    }
    assert (
        entries["link"]["mode"] == "120000"
        and entries["submodule"]["content_id"] is None
    )
    assert entries["exec"]["mode"] == "100755" and entries["lfs"]["content_id"]


def test_incomplete_closure(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    before = run(state, "repos", "show", "--repo", repos["alpha"])["data"]["items"][0][
        "current_snapshot_id"
    ]
    import sqlite3

    with sqlite3.connect(state / "catalog.sqlite3") as db:
        path = db.execute(
            "SELECT l.path FROM active_cache_entries c JOIN cache_locators l ON l.cache_locator_id=c.cache_locator_id WHERE l.repository_uuidv4=? AND l.access='target_active' AND c.state='active'",
            (repos["alpha"],),
        ).fetchone()[0]
    (state / path / "objects/pack/missing.promisor").touch()
    run(state, "sync", "git", "--repo", repos["alpha"], expected=3)
    assert (
        run(state, "repos", "show", "--repo", repos["alpha"])["data"]["items"][0][
            "current_snapshot_id"
        ]
        == before
    )
