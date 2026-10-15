"""Production Core fixtures are independently initialized disposable stores."""

from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import initialize


@pytest.fixture
def core(tmp_path):
    repository = str(uuid4())
    path = tmp_path / "core.sqlite3"
    initialize(path, "core", repository, str(uuid4()))
    result = GitCore(path)
    yield result, path, repository
    result.close()
