"""An actual failed remote fetch leaves no managed cache or admitted capture."""

from contextlib import closing
from pathlib import Path

import pytest

from repo_catalog.adapters.git import remote
from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.application.remote_git_acquisition import acquire_remote_git
from repo_catalog.domain.p1_repository import RepositoryFailure
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores
from tests.integration.p5.test_separated_remote_git import git_http, request


def test_actual_failed_http_fetch_removes_temporary_cache_without_original_capture(
    tmp_path, monkeypatch
):
    objects = build_sample_git_repo(tmp_path / "repository.git")
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("repository", "operational"))
    directories = []
    temporary_directory = remote.tempfile.TemporaryDirectory

    def tracked(*args, **kwargs):
        directory = temporary_directory(*args, **kwargs)
        directories.append(Path(directory.name))
        return directory

    monkeypatch.setattr(remote.tempfile, "TemporaryDirectory", tracked)
    with git_http(tmp_path) as (base, _):
        with pytest.raises(RepositoryFailure) as error:
            acquire_remote_git(
                catalog,
                {
                    "locator": base + "/missing.git",
                    "object_format": "sha1",
                    "request": request(repository, objects),
                    "new_request": True,
                    "transfer_bytes": 1024 * 1024,
                },
            )
        assert error.value.code == "REMOTE_HTTP"
    assert directories and all(not path.exists() for path in directories)
    assert not (catalog / "cache").exists()
    assert not (catalog / "p1-recovery-stop.json").exists()
    with closing(
        GitRepositoryStore(catalog / "repository.sqlite3")
    ) as repository_store:
        for table in (
            "retained_metadata",
            "repository_claims",
            "git_observations",
            "ref_observations",
        ):
            assert repository_store.sql(f"SELECT count(*) FROM {table}")[0][0] == 0
