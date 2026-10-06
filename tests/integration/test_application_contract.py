from repo_catalog.application.query_service import QueryService
from tests.support.cli import run


def test_operational_failure_retains_resumable_job(catalog, monkeypatch):
    import pytest

    from repo_catalog.adapters.git.importer import GitImporter
    from repo_catalog.adapters.sqlite.store import Store
    from repo_catalog.application.collection_service import CollectionService
    from repo_catalog.application.contracts import CollectionRequest
    from repo_catalog.domain.models import CatalogError

    state, fixture, repos = catalog
    original = GitImporter.sync

    def fail(*args, **kwargs):
        raise OSError("injected operational failure")

    monkeypatch.setattr(GitImporter, "sync", fail)
    with pytest.raises(CatalogError) as raised:
        CollectionService(state).sync(CollectionRequest("git"))
    assert raised.value.code == "IO_ERROR"
    job = raised.value.details["job_id"]
    with Store(state, readonly=True) as store:
        assert store.one(
            "SELECT a.state,a.reason FROM jobs j JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt WHERE j.job_id=?",
            (job,),
        )[:] == (
            "failed",
            "IO_ERROR",
        )
    monkeypatch.setattr(GitImporter, "sync", original)
    assert CollectionService(state).resume(job).status == "complete"


def test_service_cli_equivalence(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    service = QueryService(state).query(
        "search code", {"literal": "認証", "scope": "current"}
    )
    cli = run(state, "search", "code", "--literal", "認証")
    assert service.data == cli["data"]
    assert (
        service.coverage.complete_for_requested_scope
        == cli["coverage"]["complete_for_requested_scope"]
    )
