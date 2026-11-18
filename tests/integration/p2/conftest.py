"""Production Repository fixtures are independently initialized disposable stores."""

from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_schema import initialize


@pytest.fixture
def repository_store(tmp_path):
    repository = str(uuid4())
    path = tmp_path / "repository.sqlite3"
    initialize(path, "repository", repository, str(uuid4()))
    result = GitRepositoryStore(path)
    yield result, path, repository
    result.close()
