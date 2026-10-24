from pathlib import Path

import pytest

from scripts import ci_journal
from tests.support.cli import add_local, run
from tests.support.git_fixture import GitFixture


def pytest_addoption(parser):
    ci_journal.pytest_addoption(parser)


def pytest_configure(config):
    ci_journal.pytest_configure(config)


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
    monkeypatch.setenv("GIT_AUTHOR_NAME", "git-repo-db")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@git-repo-db.local")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "git-repo-db")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@git-repo-db.local")
    monkeypatch.setenv("GIT_EDITOR", "true")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    import os
    import runpy
    import socket
    import sys

    venv_bin = str(Path(sys.executable).parent)
    current_path = os.environ.get("PATH", "")
    if venv_bin not in current_path.split(os.pathsep):
        monkeypatch.setenv("PATH", venv_bin + os.pathsep + current_path)

    old_umask = os.umask(0o022)

    original = (socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo)
    runpy.run_path(str(guard / "sitecustomize.py"))
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = original
        os.umask(old_umask)


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
