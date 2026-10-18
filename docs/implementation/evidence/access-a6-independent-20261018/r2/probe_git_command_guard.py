"""Locate the consent/cancellation checkpoint relative to final Git preparation."""

import inspect
import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from repo_catalog.adapters.git.access_native import AccessGitSource
from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.domain.p1_core import CoreFailure


def main():
    with tempfile.TemporaryDirectory(prefix="r2-command-guard-") as directory:
        repo = Path(directory) / "repo.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(repo)], check=True, env={"PATH": os.defpath, "LC_ALL": "C"})
        stopped = [False]
        triggered = [False]
        commands = []
        real_stat, real_popen = os.stat, subprocess.Popen

        def guard():
            if stopped[0]:
                raise CoreFailure("CANCELLED", "independent-command-probe", "synthetic cancellation")

        def stat_at_final_preparation(path, *args, **kwargs):
            if path == "http-alternates" and any(frame.function == "_process_options" and frame.filename.endswith("/access_native.py") for frame in inspect.stack()):
                try:
                    return real_stat(path, *args, **kwargs)
                finally:
                    stopped[0] = triggered[0] = True
            return real_stat(path, *args, **kwargs)

        def popen(*args, **kwargs):
            commands.append({"started_after_cancellation": stopped[0], "argv": args[0]})
            return real_popen(*args, **kwargs)

        descriptor = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
        before = set(os.listdir("/proc/self/fd"))
        try:
            with patch.object(os, "stat", stat_at_final_preparation), patch.object(subprocess, "Popen", popen):
                try:
                    source = AccessGitSource(descriptor, str(repo), object_format="sha1", work=UnlimitedWorkBudget(), guard=guard, bind_identity=lambda _identity: None)
                except Exception as error:
                    code = getattr(error, "code", None)
                else:
                    source.close()
                    code = None
        finally:
            after = set(os.listdir("/proc/self/fd"))
            os.close(descriptor)
        print(json.dumps({"sqlite": sqlite3.sqlite_version, "late_change_injected": triggered[0], "rejection": code, "git_commands": commands, "fd_set_unchanged": before == after}, indent=2))


if __name__ == "__main__":
    main()
