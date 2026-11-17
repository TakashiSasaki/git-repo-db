from pathlib import Path

import pytest

from scripts import ci_journal


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
        try:
            from tests.support.context_admission import _cleanup_isolated_fixtures

            _cleanup_isolated_fixtures()
        except Exception:
            pass
