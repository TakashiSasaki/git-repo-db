"""Actual Git proof that a BOM can hide active include/includeIf configuration."""

import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from repo_catalog.adapters.git.access_native import AccessGitSource
from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget


def run_case(bom, kind, outside_valid):
    with tempfile.TemporaryDirectory(prefix="r2-extended-config-") as directory:
        root = Path(directory)
        repo = root / "repo.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(repo)], check=True, env={"PATH": os.defpath, "LC_ALL": "C"})
        external = root / "outside.cfg"
        external.write_bytes(b"[r2]\nvalue=outside\n" if outside_valid else b"THIS IS INVALID GIT CONFIG\n")
        baseline = (repo / "config").read_bytes()
        section = b"[include]" if kind == "include" else b'[includeIf "gitdir:/**"]'
        (repo / "config").write_bytes((b"\xef\xbb\xbf" if bom else b"") + section + b"\npath=" + os.fsencode(external) + b"\n" + baseline)
        descriptor = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
        commands, identities = [], []
        real_popen = subprocess.Popen

        def popen(*args, **kwargs):
            commands.append(args[0])
            return real_popen(*args, **kwargs)

        subprocess.Popen = popen
        record = {"bom": bom, "kind": kind, "outside_valid": outside_valid}
        source = None
        try:
            try:
                source = AccessGitSource(descriptor, str(repo), object_format="sha1", work=UnlimitedWorkBudget(), guard=lambda: None, bind_identity=identities.append)
            except Exception as error:
                record.update(accepted=False, error_code=getattr(error, "code", None))
            else:
                record.update(accepted=True, error_code=None)
                # The top-level config's bound token is unchanged; only an outside
                # file changes before a subsequent command on the same source.
                before = source._config_token()
                external.write_bytes(b"THIS IS INVALID GIT CONFIG\n")
                try:
                    source._run("rev-parse", "--show-object-format=storage")
                except Exception as error:
                    record["external_change_error"] = getattr(error, "code", None)
                else:
                    record["external_change_error"] = None
                record["bound_config_token_unchanged"] = before == source._config_token()
        finally:
            if source is not None:
                source.close()
            subprocess.Popen = real_popen
            os.close(descriptor)
        record["git_commands_started"] = len(commands)
        direct = subprocess.run(["git", "--git-dir=" + str(repo), "rev-parse", "--show-object-format=storage"], capture_output=True, env={"PATH": os.defpath, "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        record["direct_git_read_external_file"] = os.fsencode(external) in direct.stderr
        record["source_identity_recorded_before_git"] = len(identities) == 1
        return record


if __name__ == "__main__":
    print(json.dumps({"sqlite": sqlite3.sqlite_version, "results": [run_case(bom, kind, valid) for bom in (False, True) for kind in ("include", "includeIf") for valid in (False, True)]}, indent=2))
