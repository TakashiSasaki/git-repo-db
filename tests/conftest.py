import os
import sys
from pathlib import Path

import pytest

# xdist starts a fresh interpreter. Activate the explicitly prepared minimum
# binding before test modules can import SQLite; never quietly fall back to the
# runner's native version. Normal pytest/application processes are unchanged.
if os.environ.get("TEST_SQLITE_MINIMUM"):
    if "sqlite3" not in sys.modules:
        from scripts.sqlite_minimum import activate

        activate()
    import sqlite3

    assert sqlite3.sqlite_version == os.environ["TEST_SQLITE_MINIMUM"]

from tests.support.cli import add_local, run
from tests.support.git_fixture import GitFixture


@pytest.fixture(autouse=True)
def offline_test_environment(monkeypatch, request):
    if request.node.get_closest_marker("live"):
        yield
        return
    guard = Path(__file__).parent / "support/network_guard"
    if hasattr(request.config, "workerinput"):
        home = request.getfixturevalue("tmp_path_factory").getbasetemp() / "home"
        home.mkdir(exist_ok=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("PYTHONPATH", str(guard))
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    import runpy
    import socket

    original = (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo)
    runpy.run_path(str(guard / "sitecustomize.py"))
    yield
    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = original


@pytest.fixture
def catalog(tmp_path):
    fixture = GitFixture(tmp_path / "remotes")
    state = tmp_path / "state"
    run(
        state,
        "init",
        "--profile",
        "catalog-text-v1",
        "--cache-max-bytes",
        67108864,
        "--min-free-bytes",
        0,
    )
    repos = {
        name: add_local(state, name, getattr(fixture, name).url)
        for name in ("alpha", "beta", "empty")
    }
    return state, fixture, repos
