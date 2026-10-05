from __future__ import annotations

import math
import os
import signal
import subprocess
import tempfile
import time

from repo_catalog.domain.models import CatalogError


def git_env():
    return {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_ALLOW_PROTOCOL": os.environ.get("GIT_ALLOW_PROTOCOL", "file:https:ssh"),
    }


class GitRunner:
    def __init__(self, token, lock=None, monitor=None):
        self.token, self.lock, self.monitor = token, lock, monitor

    def run(self, args, *, cwd=None, input=None, timeout=300):
        self.token.check()
        try:
            p = subprocess.run(
                ["git", "--no-replace-objects", *args],
                cwd=cwd,
                input=input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=git_env(),
                timeout=timeout,
                pass_fds=(self.lock.fd,) if self.lock else (),
            )
        except subprocess.TimeoutExpired:
            raise CatalogError(
                "GIT_TIMEOUT", "Git command exceeded timeout", retryable=True
            )
        if p.returncode:
            # Never echo Git stderr: remote URLs/helper output can contain secrets.
            raise CatalogError(
                "GIT_ERROR",
                "Git command failed",
                {"operation": args[0] if args else "", "returncode": p.returncode},
                True,
            )
        return p.stdout

    def transfer(self, args, *, cwd=None, timeout=300):
        if not math.isfinite(timeout) or timeout <= 0:
            raise CatalogError(
                "CONFIG_ERROR", "Git transfer timeout must be finite and positive"
            )
        deadline = time.monotonic() + timeout
        with tempfile.TemporaryFile() as stderr:
            p = subprocess.Popen(
                ["git", "--no-replace-objects", *args],
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=stderr,
                env=git_env(),
                start_new_session=True,
                pass_fds=(self.lock.fd,) if self.lock else (),
            )
            try:
                while p.poll() is None:
                    self.token.check()
                    if time.monotonic() >= deadline:
                        raise CatalogError(
                            "GIT_TIMEOUT",
                            "Git transfer exceeded timeout",
                            retryable=True,
                        )
                    if self.monitor:
                        self.monitor()
                    time.sleep(0.05)
                if p.returncode:
                    raise CatalogError(
                        "GIT_ERROR",
                        "Git transfer failed",
                        {"returncode": p.returncode},
                        True,
                    )
                if self.monitor:
                    self.monitor()
            except BaseException:
                if p.poll() is None:
                    os.killpg(p.pid, signal.SIGTERM)
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid, signal.SIGKILL)
                        p.wait()
                raise


def hook(name):
    """Explicitly enabled test handshake; no hooks active in normal operation."""
    directory = os.environ.get("REPO_CATALOG_TEST_HOOK_DIR")
    if os.environ.get("REPO_CATALOG_ENABLE_TEST_HOOKS") == "1" and directory:
        from pathlib import Path

        p = Path(directory)
        if (p / (name + ".enabled")).exists():
            (p / (name + ".reached")).touch()
            while not (p / (name + ".release")).exists():
                time.sleep(0.01)
