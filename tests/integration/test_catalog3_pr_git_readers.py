"""Exact PR-only Git acquisitions remain readable independently of refs."""

from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.git.parsing import reparse_git
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.target_queries import TargetQueryService
from repo_catalog.domain.models import CancellationToken


def test_pr_only_acquisition_reads_direct_objects_without_ref_selection(catalog):
    state, fixture, repositories = catalog
    repository = repositories["alpha"]
    commit = "sha1:" + fixture.alpha.commits["N"]
    with Store(state) as store:
        repo = store.one(
            "SELECT * FROM repositories WHERE repository_uuidv4=?", (repository,)
        )

        def acquire(number):
            return GitImporter(store, CancellationToken()).sync(
                repo,
                JobService(store).create("sync", {}),
                pr_roots=[
                    {
                        "ref": "refs/heads/main",
                        "expected": fixture.alpha.commits["N"],
                        "role": "head",
                        "number": number,
                    }
                ],
            )["git_acquisition_id"]

        acquisition = acquire(41)
        assert not store.one("SELECT 1 FROM current_snapshots")
        before = store.one("SELECT count(*) FROM git_objects")[0]
        reparse_git(store, acquisition)
        assert store.one("SELECT count(*) FROM git_objects")[0] == before
        other = acquire(42)
        assert other != acquisition
        assert store.one("SELECT count(*) FROM git_objects")[0] == before
        assert not store.one("SELECT 1 FROM snapshots")
    options = {"repo": repository, "commit": commit, "git_acquisition_id": acquisition}
    diagnostic = TargetQueryService(state / "catalog.sqlite3")
    assert diagnostic.query("commit", options).data["items"][0]["oid"] == commit
    assert any(
        row["path_utf8"] == "README.md"
        for row in diagnostic.query("tree", options).data["items"]
    )
    assert (
        diagnostic.query("file", {**options, "path": "README.md"})
        .data["items"][0]["text"]
        .startswith("認証")
    )
    ordinary = QueryService(state)
    assert ordinary.query("commits show", options).data["items"][0]["oid"] == commit
    assert (
        ordinary.query("file show", {**options, "path": "README.md"})
        .data["items"][0]["text"]
        .startswith("認証")
    )
    # Identical verified objects from another acquisition remain one domain
    # object, so acquisition UUID differences cannot manufacture decoder conflict.
    assert (
        ordinary.query("commits show", {"repo": repository, "commit": commit}).data[
            "items"
        ][0]["message"]
        is not None
    )
