"""Finite remote Git input, metered before native metadata/Notes acquisition.

HTTPS uses a loopback smart-HTTP relay; SSH uses an argv-only plaintext protocol
meter with strict host-key checking. Counts are application transfer body bytes,
not TLS/SSH framing or pack-file-size estimates. The independent temporary Git
cache is destroyed on exit and is never an authoritative file-content archive.
"""

from __future__ import annotations

import base64
import http.client
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.domain.p1_repository import RepositoryFailure, encode

_BLOCK = 65536
_OVERHEAD = 2 * _BLOCK


def _finite(value, scope):
    if type(value) is not int or not 0 < value < 2**63 - _OVERHEAD:
        raise RepositoryFailure("BUDGET", scope, "positive finite limit required")
    return value


def _location(locator):
    if (
        type(locator) is not str
        or len(locator) > 8192
        or any(ord(c) < 33 for c in locator)
    ):
        raise RepositoryFailure("REMOTE_URL", "git", "explicit remote URL required")
    try:
        value = urlsplit(locator)
        if value.scheme not in {"https", "http", "ssh"} or not value.hostname:
            raise ValueError
        if value.username or value.password or value.query or value.fragment:
            raise ValueError
        if (
            not value.path.startswith("/")
            or value.path == "/"
            or ".." in value.path.split("/")
        ):
            raise ValueError
        if value.scheme == "http" and value.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError
        if value.scheme == "ssh" and any(
            c
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._~+-"
            for c in value.path
        ):
            raise ValueError
        _ = value.port
        return value
    except (ValueError, TypeError):
        raise RepositoryFailure("REMOTE_URL", "git", "unsafe remote URL") from None


def _environment():
    env = dict(os.environ)
    for key in tuple(env):
        if key.startswith("GIT_"):
            env.pop(key)
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_OPTIONAL_LOCKS="0",
        GIT_NO_LAZY_FETCH="1",
        LC_ALL="C",
    )
    return env


def _command(path, *args):
    return [
        "git",
        "--no-replace-objects",
        "-C",
        str(path),
        "-c",
        "core.hooksPath=" + os.devnull,
        "-c",
        "credential.helper=",
        "-c",
        "http.proxy=",
        "-c",
        "http.followRedirects=false",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.http.allow=always",
        "-c",
        "protocol.ssh.allow=always",
        *args,
    ]


class RemoteGitSource(GitNativeSource):
    """Native parser source whose original locator scope survives cache renewal."""

    def __init__(
        self,
        path,
        *,
        object_format,
        acquisition_scope,
        transfer_body_bytes,
        metadata_bytes,
    ):
        self._acquisition_scope = acquisition_scope
        self.transfer_body_bytes = transfer_body_bytes
        super().__init__(path, metadata_bytes=metadata_bytes)
        if self.object_format != object_format:
            raise RepositoryFailure(
                "NATIVE_FORMAT", "remote-git", "remote object format mismatch"
            )

    @property
    def acquisition_scope(self):
        return self._acquisition_scope

    def _environment(self):
        return _environment()

    def _command(self, *args):
        return _command(self.path, *args)


class _Transfer:
    def __init__(self, limit, guard):
        self.limit, self.guard = limit, guard
        self.count, self.error = 0, None

    def count_bytes(self, amount):
        self.count += amount
        self.guard()
        if self.count > self.limit:
            raise RepositoryFailure(
                "BUDGET", "remote-transfer", "finite transfer body limit"
            )


def _handler(location, transfer, credentials, username, timeout):
    class Relay(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(timeout)

        def log_message(self, *args):
            pass

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            connection = None
            try:
                if self.path not in {
                    "/repo/info/refs?service=git-upload-pack",
                    "/repo/git-upload-pack",
                }:
                    raise RepositoryFailure(
                        "REMOTE_PROTOCOL", "git", "unexpected Git HTTP operation"
                    )
                suffix = self.path.removeprefix("/repo")
                if (self.command == "GET") != suffix.startswith("/info/refs?"):
                    raise RepositoryFailure(
                        "REMOTE_PROTOCOL", "git", "unexpected Git HTTP method"
                    )
                if self.headers.get("Transfer-Encoding"):
                    raise RepositoryFailure(
                        "REMOTE_PROTOCOL", "git", "unbounded request framing"
                    )
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= transfer.limit - transfer.count:
                    raise RepositoryFailure(
                        "BUDGET", "remote-transfer", "finite upload body limit"
                    )
                cls = (
                    http.client.HTTPSConnection
                    if location.scheme == "https"
                    else http.client.HTTPConnection
                )
                connection = cls(location.hostname, location.port, timeout=timeout)
                headers = {
                    "User-Agent": "repo-catalog-git",
                    "Accept-Encoding": "identity",
                }
                for name in (
                    "Content-Type",
                    "Content-Encoding",
                    "Accept",
                    "Git-Protocol",
                ):
                    if self.headers.get(name):
                        headers[name] = self.headers[name]
                if credentials is not None:
                    secret = credentials.get()
                    if secret:
                        raw = (username + ":" + secret).encode("utf-8")
                        headers["Authorization"] = "Basic " + base64.b64encode(
                            raw
                        ).decode("ascii")
                headers["Content-Length"] = str(length)
                connection.putrequest(
                    self.command,
                    location.path.rstrip("/") + suffix,
                    skip_accept_encoding=True,
                )
                for name, value in headers.items():
                    connection.putheader(name, value)
                connection.endheaders()
                while length:
                    transfer.guard()
                    chunk = self.rfile.read(min(_BLOCK, length))
                    if not chunk:
                        raise RepositoryFailure(
                            "REMOTE_PROTOCOL", "git", "truncated upload"
                        )
                    transfer.count_bytes(len(chunk))
                    connection.send(chunk)
                    length -= len(chunk)
                upstream = connection.getresponse()
                # Never follow redirects, forward cookies, or copy an upstream
                # credential challenge into Git's local client/helper channel.
                if upstream.status != 200:
                    raise RepositoryFailure(
                        "REMOTE_HTTP", "git", "remote Git request refused"
                    )
                self.send_response(200)
                for name in ("Content-Type", "Content-Length"):
                    if upstream.getheader(name) is not None:
                        self.send_header(name, upstream.getheader(name))
                self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    transfer.guard()
                    remaining = max(1, min(_BLOCK, transfer.limit - transfer.count + 1))
                    chunk = upstream.read(remaining)
                    if not chunk:
                        break
                    transfer.count_bytes(len(chunk))
                    self.wfile.write(chunk)
            except BaseException as error:
                transfer.error = (
                    error
                    if isinstance(error, RepositoryFailure)
                    else RepositoryFailure(
                        "REMOTE_NETWORK", "git", "remote Git transport failed"
                    )
                )
                self.close_connection = True
            finally:
                if connection is not None:
                    connection.close()

    return Relay


def _disk_guard(path, limit, work):
    total = 0
    for root, directories, files in os.walk(path):
        work.require("metadata_units", len(files) + len(directories) + 1)
        work.charge("metadata_units", len(files) + len(directories) + 1)
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except FileNotFoundError:
                continue  # Git atomically renames temporary object files.
            if total > limit:
                raise RepositoryFailure(
                    "BUDGET", "remote-cache", "finite temporary disk limit"
                )


def _stop(process):
    # Git can exit while a helper still owns inherited pipes. The dedicated
    # process group belongs entirely to this invocation, including SSH children.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # Waiting for the leader is insufficient: SSH/credential helpers can still
    # own the invocation's group and inherited descriptors after it has exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        # Preserve the original transfer error and keep cleanup itself finite
        # if the operating system cannot yet reap a killed I/O-bound process.
        pass


def validate_remote_transport(
    locator,
    *,
    object_format,
    transfer_bytes=64 * 1024 * 1024,
    disk_bytes=512 * 1024 * 1024,
    timeout_seconds=300,
    metadata_bytes=64 * 1024 * 1024,
    credentials=None,
    username="git",
    ssh_username=None,
    ssh_identity_file=None,
    ssh_known_hosts_file=None,
    refspecs=None,
):
    """Pure shared shape/origin/finite-options policy; no files or network read."""
    location = _location(locator)
    _finite(transfer_bytes, "remote-transfer")
    _finite(disk_bytes, "remote-cache")
    _finite(metadata_bytes, "remote-metadata")
    if (
        type(timeout_seconds) not in {int, float}
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise RepositoryFailure(
            "BUDGET", "remote-timeout", "positive finite timeout required"
        )
    if object_format not in {"sha1", "sha256"}:
        raise RepositoryFailure(
            "NATIVE_FORMAT", "remote-git", "explicit sha1/sha256 required"
        )
    if type(username) is not str or any(c in username for c in "\r\n:"):
        raise RepositoryFailure("REMOTE_CREDENTIAL", "git", "invalid HTTP username")
    if location.scheme == "ssh" and credentials is not None:
        raise RepositoryFailure(
            "REMOTE_CREDENTIAL", "git", "HTTP credentials cannot authorize SSH"
        )
    if refspecs is not None and type(refspecs) not in {tuple, list}:
        raise RepositoryFailure(
            "REF", "remote-git", "explicit finite refspec sequence required"
        )
    specs = (
        tuple(refspecs)
        if refspecs is not None
        else (
            "+refs/heads/*:refs/heads/*",
            "+refs/tags/*:refs/tags/*",
            "+refs/notes/*:refs/notes/*",
        )
    )
    if (
        not specs
        or len(specs) > 10_000
        or any(
            type(s) is not str
            or not s.startswith("+refs/")
            or len(s) > 8192
            or any(ord(c) < 33 for c in s)
            or ":refs/" not in s
            for s in specs
        )
    ):
        raise RepositoryFailure(
            "REF", "remote-git", "bounded explicit refspecs required"
        )
    if ssh_username is not None and (
        type(ssh_username) is not str
        or not ssh_username
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
            for c in ssh_username
        )
    ):
        raise RepositoryFailure("REMOTE_CREDENTIAL", "ssh", "invalid SSH username")
    for reference in (ssh_identity_file, ssh_known_hosts_file):
        if reference is not None and (
            type(reference) is not str
            or not reference
            or len(reference) > 16384
            or "\0" in reference
        ):
            raise RepositoryFailure(
                "REMOTE_CREDENTIAL", "ssh", "bounded local path reference required"
            )
    return location, specs


@contextmanager
def fetch_remote(
    locator,
    *,
    object_format,
    work,
    guard=lambda: None,
    transfer_bytes=64 * 1024 * 1024,
    disk_bytes=512 * 1024 * 1024,
    timeout_seconds=300,
    metadata_bytes=64 * 1024 * 1024,
    credentials=None,
    username="git",
    ssh_username=None,
    ssh_identity_file=None,
    ssh_known_hosts_file=None,
    refspecs=None,
):
    """Fetch an isolated native source, then discard the entire incidental cache.

    Caller supplies the original durable WorkBudget before opening a connection.
    ``credentials`` is an ephemeral get() provider for HTTP Basic authentication.
    SSH uses explicit key/agent authentication and known-hosts verification.
    """
    location, specs = validate_remote_transport(
        locator,
        object_format=object_format,
        transfer_bytes=transfer_bytes,
        disk_bytes=disk_bytes,
        timeout_seconds=timeout_seconds,
        metadata_bytes=metadata_bytes,
        credentials=credentials,
        username=username,
        ssh_username=ssh_username,
        ssh_identity_file=ssh_identity_file,
        ssh_known_hosts_file=ssh_known_hosts_file,
        refspecs=refspecs,
    )
    scope = encode(
        [
            "remote-git",
            location.scheme,
            location.hostname,
            location.port,
            location.path,
            object_format,
        ]
    )
    with tempfile.TemporaryDirectory(prefix="repo-catalog-remote-") as temporary:
        root = Path(temporary)
        cache = root / "objects.git"
        cache.mkdir()
        subprocess.run(
            _command(cache, "init", "--bare", "--object-format=" + object_format),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_environment(),
            timeout=min(timeout_seconds, 30),
        )
        deadline = time.monotonic() + timeout_seconds

        def check():
            guard()
            if time.monotonic() >= deadline:
                raise RepositoryFailure(
                    "REMOTE_TIMEOUT", "git", "finite remote transfer timeout"
                )
            _disk_guard(cache, disk_bytes, work)

        transfer = _Transfer(transfer_bytes, check)
        server, meter_file = None, None
        env = _environment()
        if location.scheme in {"https", "http"}:
            server = HTTPServer(
                ("127.0.0.1", 0),
                _handler(
                    location, transfer, credentials, username, min(timeout_seconds, 30)
                ),
            )
            server.timeout = 0.05
            remote = f"http://127.0.0.1:{server.server_port}/repo"
        else:
            remote = locator
            meter_file = root / "ssh-meter.json"
            config_file = root / "ssh.json"
            wrapper = root / "ssh-meter"
            binary = shutil.which("ssh")
            if binary is None:
                raise RepositoryFailure(
                    "REMOTE_EXECUTOR", "ssh", "SSH executable unavailable"
                )
            config_file.write_text(
                json.dumps(
                    {
                        "binary": binary,
                        "host": location.hostname,
                        "port": location.port or 22,
                        "path": location.path,
                        "username": ssh_username,
                        "identity_file": ssh_identity_file,
                        "known_hosts_file": ssh_known_hosts_file,
                        "limit": transfer_bytes,
                        "meter_file": str(meter_file),
                    }
                ),
                encoding="utf-8",
            )
            wrapper.write_text(
                "#!"
                + sys.executable
                + "\nfrom repo_catalog.adapters.git.remote import ssh_meter\n"
                + "ssh_meter("
                + repr(str(config_file))
                + ")\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o700)
            env.update(GIT_SSH=str(wrapper), GIT_SSH_VARIANT="ssh")
        work.require("metadata_units", 1)
        work.charge("metadata_units", 1)
        # At most two concurrent SSH readers may each observe a bounded block
        # before the shared limit stops them. Reserve that finite read overhead.
        work.require("input_bytes", transfer_bytes + _OVERHEAD)
        process = None
        measured = None
        try:
            process = subprocess.Popen(
                _command(
                    cache,
                    "fetch",
                    "--atomic",
                    "--no-tags",
                    "--no-write-fetch-head",
                    "--refmap=",
                    "--",
                    remote,
                    *specs,
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            while process.poll() is None:
                check()
                if server is not None:
                    server.handle_request()
                    if transfer.error is not None:
                        raise transfer.error
                else:
                    time.sleep(0.025)
                _disk_guard(cache, disk_bytes, work)
            if server is not None and transfer.error is not None:
                raise transfer.error
            if meter_file is not None:
                value = json.loads(meter_file.read_text(encoding="ascii"))
                transfer.count = value["bytes"]
                if value["limited"]:
                    raise RepositoryFailure(
                        "BUDGET", "remote-transfer", "finite SSH body limit"
                    )
            if process.returncode:
                raise RepositoryFailure("REMOTE_GIT", "git", "remote Git fetch failed")
            measured = transfer.count
        finally:
            if process is not None:
                _stop(process)
            if server is not None:
                server.server_close()
                measured = transfer.count
            elif meter_file is not None and meter_file.exists():
                try:
                    measured = json.loads(meter_file.read_text(encoding="ascii"))[
                        "bytes"
                    ]
                except (ValueError, OSError, KeyError):
                    pass
            if type(measured) is int and 0 <= measured <= transfer_bytes + _OVERHEAD:
                work.charge("input_bytes", measured)
            else:
                work.abandon("input_bytes")
        check()
        _disk_guard(cache, disk_bytes, work)
        yield RemoteGitSource(
            cache,
            object_format=object_format,
            acquisition_scope=scope,
            transfer_body_bytes=transfer.count,
            metadata_bytes=metadata_bytes,
        )


def ssh_meter(config_path):
    """Private executable bridge; no local shell or caller-supplied SSH flags."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    args = [
        config["binary"],
        "-F",
        os.devnull,
        "-p",
        str(config["port"]),
        "-oBatchMode=yes",
        "-oStrictHostKeyChecking=yes",
        "-oPermitLocalCommand=no",
        "-oClearAllForwardings=yes",
        "-oForwardAgent=no",
        "-oConnectTimeout=30",
    ]
    if config["username"] is not None:
        args.extend(["-l", config["username"]])
    if config["identity_file"] is not None:
        args.extend(["-i", config["identity_file"]])
    if config["known_hosts_file"] is not None:
        args.extend(["-oUserKnownHostsFile=" + config["known_hosts_file"]])
    args.extend(["--", config["host"], "git-upload-pack '" + config["path"] + "'"])
    process = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    lock = threading.Lock()
    state = {"bytes": 0, "limited": False}
    destination = Path(config["meter_file"])

    def record():
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(state), encoding="ascii")
        temporary.replace(destination)

    def forward(source, target):
        try:
            while True:
                chunk = os.read(source.fileno(), _BLOCK)
                if not chunk:
                    break
                with lock:
                    state["bytes"] += len(chunk)
                    state["limited"] = (
                        state["limited"] or state["bytes"] > config["limit"]
                    )
                    record()
                    if state["limited"]:
                        process.terminate()
                        break
                target.write(chunk)
                target.flush()
        except (OSError, ValueError):
            pass
        finally:
            if target is process.stdin:
                target.close()

    with lock:
        record()
    outgoing = threading.Thread(
        target=forward, args=(sys.stdin.buffer, process.stdin), daemon=True
    )
    outgoing.start()
    forward(process.stdout, sys.stdout.buffer)
    code = process.wait()
    with lock:
        record()
    raise SystemExit(1 if state["limited"] else code)
