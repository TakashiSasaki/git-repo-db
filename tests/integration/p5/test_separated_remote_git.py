"""Remote protocol input into native Git/Notes acquisition using local fixtures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.adapters.git.remote import fetch_remote
from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.application.remote_git_acquisition import acquire_remote_git
from repo_catalog.domain.git_acquisition import (
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
)
from repo_catalog.domain.p1_repository import RepositoryFailure
from tests.integration.p5.conftest import build_sample_git_repo, init_catalog_stores


@contextmanager
def git_http(root):
    events = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            location = urlsplit(self.path)
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            env = {
                **os.environ,
                "GIT_PROJECT_ROOT": str(root),
                "GIT_HTTP_EXPORT_ALL": "1",
                "PATH_INFO": location.path,
                "QUERY_STRING": location.query,
                "REQUEST_METHOD": self.command,
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": str(len(body)),
            }
            result = subprocess.run(
                ["git", "http-backend"],
                input=body,
                capture_output=True,
                env=env,
                check=True,
            )
            head, output = result.stdout.split(b"\r\n\r\n", 1)
            events.append(
                {
                    "bytes": len(body) + len(output),
                    "authorization": self.headers.get("Authorization"),
                }
            )
            headers = dict(line.decode().split(": ", 1) for line in head.split(b"\r\n"))
            self.send_response(int(headers.pop("Status", "200 OK").split()[0]))
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", events
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(repository, objects, *, notes=True):
    return GitNativeAcquisitionRequest(
        repository,
        str(uuid4()),
        str(uuid4()),
        "original-remote-fixture",
        1_700_000_600_000_000,
        select_object_oids=(objects["commit2"], objects["tag"]),
        notes=NotesAcquisitionSpec(
            discover_notes=True,
            acquire_inventories=True,
            target_object_oids=(objects["commit2"],),
            retain_note_bodies=True,
        )
        if notes
        else None,
    )


def test_smart_http_actual_bytes_and_original_capture_retry(tmp_path):
    objects = build_sample_git_repo(tmp_path / "repository.git")
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("repository", "operational"))
    native = request(repository, objects)
    with git_http(tmp_path) as (base, events):
        document = {
            "locator": base + "/repository.git",
            "object_format": "sha1",
            "request": native,
            "new_request": True,
            "transfer_bytes": 1024 * 1024,
        }
        first = acquire_remote_git(catalog, document)
        first_bytes = sum(event["bytes"] for event in events)
        assert first.transfer_body_bytes == first_bytes > 0
        document["new_request"] = False
        second = acquire_remote_git(catalog, document)
        assert (
            second.transfer_body_bytes
            == sum(event["bytes"] for event in events) - first_bytes
        )
    assert (
        first.git_report.capture_uuidv4
        == second.git_report.capture_uuidv4
        == native.capture_uuidv4
    )
    assert first.git_report.failure_code is None
    assert second.git_report.failure_code is None
    assert first.git_report.retained_objects
    assert objects["blob"] not in first.git_report.retained_objects
    assert any(item.body_retained for item in first.git_report.ref_note_acquisitions)
    repository_store = GitRepositoryStore(catalog / "repository.sqlite3")
    try:
        assert (
            repository_store.sql(
                "SELECT count(*) FROM retained_metadata WHERE object_oid=?",
                (objects["blob"].object_oid,),
            )[0][0]
            == 0
        )
    finally:
        repository_store.close()
    assert not (catalog / "context.sqlite3").exists()


def test_remote_transport_username_and_refspec_change_rejected_before_network(tmp_path):
    objects = build_sample_git_repo(tmp_path / "repository.git")
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("repository", "operational"))
    with git_http(tmp_path) as (base, events):
        document = {
            "locator": base + "/repository.git",
            "object_format": "sha1",
            "request": request(repository, objects, notes=False),
            "new_request": True,
            "transfer_bytes": 1024 * 1024,
        }
        acquire_remote_git(catalog, document)
        count = len(events)
        for change in (
            {"username": "another-principal"},
            {"refspecs": ["+refs/heads/*:refs/heads/*"]},
            {"locator": base + "/different.git"},
        ):
            with pytest.raises(RepositoryFailure) as refusal:
                acquire_remote_git(
                    catalog, {**document, "new_request": False, **change}
                )
            assert refusal.value.code == "INCOMPATIBLE_REPLAY"
        assert len(events) == count


def test_http_budget_refusal_does_not_enter_catalog_recovery(tmp_path):
    objects = build_sample_git_repo(tmp_path / "repository.git")
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("repository", "operational"))
    with git_http(tmp_path) as (base, _):
        with pytest.raises(RepositoryFailure) as refusal:
            acquire_remote_git(
                catalog,
                {
                    "locator": base + "/repository.git",
                    "object_format": "sha1",
                    "request": request(repository, objects),
                    "new_request": True,
                    "transfer_bytes": 1,
                },
            )
        assert refusal.value.code == "BUDGET"
    assert not (catalog / "p1-recovery-stop.json").exists()


def test_ssh_argv_protocol_meter_and_strict_host_verification(tmp_path, monkeypatch):
    objects = build_sample_git_repo(tmp_path / "repository.git")
    catalog = tmp_path / "catalog"
    repository, _ = init_catalog_stores(catalog, stores=("repository", "operational"))
    executable = tmp_path / "ssh-fixture"
    log = tmp_path / "argv.json"
    executable.write_text(
        "#!"
        + sys.executable
        + "\nimport json, os, shlex, sys\n"
        + "open("
        + repr(str(log))
        + ", 'w').write(json.dumps(sys.argv[1:]))\n"
        + "command = shlex.split(sys.argv[-1])\n"
        + "os.execvp('git', ['git', 'upload-pack', command[1]])\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setattr(
        "repo_catalog.adapters.git.remote.shutil.which", lambda _: str(executable)
    )
    report = acquire_remote_git(
        catalog,
        {
            "locator": "ssh://example.test" + str(tmp_path / "repository.git"),
            "object_format": "sha1",
            "request": request(repository, objects, notes=False),
            "new_request": True,
            "transfer_bytes": 1024 * 1024,
            "ssh_username": "reader",
            "ssh_known_hosts_file": str(tmp_path / "known_hosts"),
        },
    )
    assert report.git_report.failure_code is None
    assert report.transfer_body_bytes > 0
    argv = json.loads(log.read_text())
    assert "-oStrictHostKeyChecking=yes" in argv
    assert "-oBatchMode=yes" in argv
    assert "-oForwardAgent=no" in argv
    assert argv[argv.index("-l") + 1] == "reader"
    assert argv[-2] == "example.test"


def test_declared_remote_scope_is_canonical_and_temporary_cache_is_removed(tmp_path):
    build_sample_git_repo(tmp_path / "repository.git")

    class Work:
        def require(self, *_):
            pass

        def charge(self, *_):
            pass

        def abandon(self, *_):
            pass

    with git_http(tmp_path) as (base, _):
        scopes, paths = [], []
        for _ in range(2):
            with fetch_remote(
                base + "/repository.git",
                object_format="sha1",
                work=Work(),
                transfer_bytes=1024 * 1024,
            ) as source:
                scopes.append(GitNotesSource(source).scope)
                paths.append(source.path)
    assert scopes[0] == scopes[1]
    assert paths[0] != paths[1]
    assert all(not path.exists() for path in paths)


@pytest.mark.parametrize(
    "locator",
    [
        "https://token@remote.test/repository.git",
        "https://remote.test/repository.git?token=secret",
        "http://remote.test/repository.git",
        "ssh://user:secret@remote.test/repository.git",
    ],
)
def test_embedded_secrets_and_cleartext_remote_urls_are_refused(locator):
    with pytest.raises(RepositoryFailure) as refusal:
        with fetch_remote(locator, object_format="sha1", work=None):
            pytest.fail("unsafe remote opened")
    assert refusal.value.code == "REMOTE_URL"
