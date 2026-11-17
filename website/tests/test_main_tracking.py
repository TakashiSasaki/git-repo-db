"""Main advances between attempts without a manually updated source file."""

import importlib.util
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "web_prepare_product", ROOT / "scripts/prepare_product.py"
)
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def commit(root, text):
    (root / "input.txt").write_text(text)
    git(root, "add", ".")
    git(root, "commit", "-qm", text)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def remote(tmp_path):
    root = tmp_path / "remote"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Web tests")
    git(root, "config", "user.email", "web-tests@example.invalid")
    commit(root, "first")
    return root


def test_next_attempt_tracks_new_main_with_unchanged_selection(remote, tmp_path):
    selection = {"repository": str(remote), "ref": "main"}
    original = dict(selection)
    first = prepare.prepare_checkout(selection, cache=tmp_path / "cache")
    new_commit = commit(remote, "second")
    second = prepare.prepare_checkout(selection, cache=tmp_path / "cache")
    assert selection == original and "commit" not in selection
    assert first["commit"] != second["commit"] == new_commit
    assert first["selection_mode"] == second["selection_mode"] == "remote-ref"
    assert second["requested_ref"] == "main"
    assert git(Path(first["path"]), "rev-parse", "HEAD") == first["commit"]


def test_main_advance_after_resolution_does_not_restart_attempt(
    remote, tmp_path, monkeypatch
):
    resolved = git(remote, "rev-parse", "HEAD")
    original_run = prepare.run
    resolutions = []
    original_output = prepare.subprocess.check_output

    def output(command, **kwargs):
        if "ls-remote" in command:
            resolutions.append(command[-1])
        return original_output(command, **kwargs)

    def run(command, cwd, *, env=None):
        if command[:2] == ["git", "clone"]:
            commit(remote, "advanced during preparation")
        return original_run(command, cwd, env=env)

    monkeypatch.setattr(prepare.subprocess, "check_output", output)
    monkeypatch.setattr(prepare, "run", run)
    snapshot = prepare.prepare_checkout(
        {"repository": str(remote), "ref": "main"}, cache=tmp_path / "cache"
    )
    assert resolutions == ["refs/heads/main"]
    assert snapshot["commit"] == resolved != git(remote, "rev-parse", "HEAD")
    assert git(Path(snapshot["path"]), "rev-parse", "HEAD") == resolved


def test_local_override_records_head_without_remote_resolution(remote, monkeypatch):
    original_output = prepare.subprocess.check_output

    def output(command, **kwargs):
        assert "ls-remote" not in command
        return original_output(command, **kwargs)

    monkeypatch.setattr(prepare.subprocess, "check_output", output)
    snapshot = prepare.prepare_checkout(
        {"repository": str(remote), "ref": "main"}, remote
    )
    assert snapshot["commit"] == git(remote, "rev-parse", "HEAD")
    assert snapshot["selection_mode"] == "local-override"
    assert snapshot["requested_ref"] == "main"


def test_git_sends_one_authorization_header_inside_checkout(remote, monkeypatch):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(self.headers.get_all("Authorization"))
            self.send_response(500)  # Only headers are under test, not a Git server.
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 5
        scope = f"http://127.0.0.1:{server.server_port}/"
        git(remote, "config", f"http.{scope}.extraheader", "AUTHORIZATION: inherited")
        monkeypatch.setattr(prepare, "GITHUB_HTTP_SCOPE", scope)
        monkeypatch.setenv("GH_TOKEN", "test-only-not-a-real-token")
        worker = threading.Thread(target=server.handle_request, daemon=True)
        worker.start()
        try:
            subprocess.run(
                ["git", "ls-remote", scope, "refs/heads/main"],
                cwd=remote,
                env=prepare.git_environment(),
                capture_output=True,
                timeout=10,
            )
        finally:
            worker.join(timeout=6)
    assert len(received) == 1 and len(received[0]) == 1
    assert received[0][0].startswith("basic ")
