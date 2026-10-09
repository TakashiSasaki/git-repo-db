"""Explicit Git targets remain readable without a regular ref snapshot."""

from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.git.parsing import reparse_git
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.target_queries import TargetQueryService
from repo_catalog.domain.models import CancellationToken


def test_pr_only_acquisition_has_explicit_selected_git_reads(catalog):
    state, fixture, repositories = catalog
    repository = repositories["alpha"]
    commit = "sha1:" + fixture.alpha.commits["N"]
    with Store(state) as store:
        repo = store.one(
            "SELECT * FROM repositories WHERE repository_uuidv4=?", (repository,)
        )
        acquisition = GitImporter(store, CancellationToken()).sync(
            repo,
            JobService(store).create("sync", {}),
            pr_roots=[
                {
                    "ref": "refs/heads/main",
                    "expected": fixture.alpha.commits["N"],
                    "role": "head",
                    "number": 41,
                }
            ],
        )["git_acquisition_id"]
        assert not store.one("SELECT 1 FROM current_snapshots")
        selected = store.one(
            "SELECT parsed_result_uuidv4 FROM selected_git_acquisition_results WHERE git_acquisition_id=?",
            (acquisition,),
        )[0]
        reparse_git(store, acquisition)
        assert (
            store.one(
                "SELECT count(*) FROM parsed_result_inputs WHERE git_acquisition_id=?",
                (acquisition,),
            )[0]
            == 2
        )
    options = {"repo": repository, "commit": commit}
    diagnostic = TargetQueryService(state / "catalog.sqlite3")
    assert (
        diagnostic.query("commit", options).data["items"][0]["parsed_result_uuidv4"]
        == selected
    )
    tree = diagnostic.query("tree", options).data["items"]
    assert any(row["path_utf8"] == "README.md" for row in tree)
    file = diagnostic.query("file", {**options, "path": "README.md"})
    assert file.data["items"][0]["text"].startswith("認証")
    for kind, literal in (("code", "observed_in"), ("commits", "commit N")):
        hits = diagnostic.query(
            "search", {"repo": repository, "kind": kind, "literal": literal}
        ).data["items"]
        assert hits and {row["parsed_result_uuidv4"] for row in hits} == {selected}
    ordinary = QueryService(state)
    assert (
        ordinary.query("commits show", options).data["items"][0]["parsed_result_uuidv4"]
        == selected
    )
    assert (
        ordinary.query("file show", {**options, "path": "README.md"})
        .data["items"][0]["text"]
        .startswith("認証")
    )
    with Store(state) as store:
        repo = store.one(
            "SELECT * FROM repositories WHERE repository_uuidv4=?", (repository,)
        )
        GitImporter(store, CancellationToken()).sync(
            repo,
            JobService(store).create("sync", {}),
            pr_roots=[
                {
                    "ref": "refs/heads/main",
                    "expected": fixture.alpha.commits["N"],
                    "role": "head",
                    "number": 42,
                }
            ],
        )
    ambiguous = ordinary.query("commits show", options)
    assert ambiguous.data["items"] == []
    assert any(
        row["reason"] == "git_interpretation_selection_unresolved"
        for row in ambiguous.coverage.missing
    )
    for kind, literal in (("code", "observed_in"), ("commits", "commit N")):
        ambiguous = diagnostic.query(
            "search", {"repo": repository, "kind": kind, "literal": literal}
        )
        assert ambiguous.data["items"] == []
        assert any(
            row["reason"] == "git_interpretation_selection_unresolved"
            for row in ambiguous.coverage.missing
        )
