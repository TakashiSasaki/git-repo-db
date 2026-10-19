"""Independent synthetic test of AccessGitSource's indirect-config boundary."""

import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from repo_catalog.adapters.git.access_native import AccessGitSource
from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget


def main():
    records = []
    with tempfile.TemporaryDirectory(prefix="r2-config-bom-") as directory:
        base = Path(directory)
        repo = base / "repo.git"
        subprocess.run(
            ["git", "init", "--bare", "--quiet", str(repo)],
            check=True,
            env={"PATH": os.defpath, "LC_ALL": "C"},
        )
        original = (repo / "config").read_bytes()
        outside = base / "outside.cfg"
        outside.write_bytes(b"THIS IS INVALID GIT CONFIG\n")
        for bom in (False, True):
            config = b"[include]\npath = " + os.fsencode(outside) + b"\n" + original
            if bom:
                config = b"\xef\xbb\xbf" + config
            (repo / "config").write_bytes(config)
            invoked = []
            real_popen = subprocess.Popen

            def record_popen(*args, **kwargs):
                invoked.append(args[0])
                return real_popen(*args, **kwargs)

            subprocess.Popen = record_popen
            descriptor = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
            try:
                try:
                    source = AccessGitSource(
                        descriptor,
                        str(repo),
                        object_format="sha1",
                        work=UnlimitedWorkBudget(),
                        guard=lambda: None,
                        bind_identity=lambda _identity: None,
                    )
                except Exception as error:
                    record = {
                        "bom": bom,
                        "error_type": type(error).__name__,
                        "code": getattr(error, "code", None),
                        "detail": str(error),
                        "git_commands_started": len(invoked),
                    }
                else:
                    source.close()
                    record = {"bom": bom, "accepted": True, "git_commands_started": len(invoked)}
            finally:
                os.close(descriptor)
                subprocess.Popen = real_popen
            # Independently prove Git itself interpreted the external file.
            git = subprocess.run(
                ["git", "--git-dir=" + str(repo), "rev-parse", "--show-object-format=storage"],
                capture_output=True,
                env={"PATH": os.defpath, "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
            )
            record["direct_git_status"] = git.returncode
            record["direct_git_read_external_file"] = os.fsencode(outside) in git.stderr
            record["direct_git_stderr"] = git.stderr.decode()
            records.append(record)
    print(json.dumps({"sqlite": sqlite3.sqlite_version, "results": records}, indent=2))


if __name__ == "__main__":
    main()
