import os
import shutil
import subprocess
import time


def start_hooked(state, hook, work, *args):
    directory = work / "hooks"
    directory.mkdir(exist_ok=True)
    (directory / (hook + ".enabled")).touch()
    env = {
        **os.environ,
        "REPO_CATALOG_ENABLE_TEST_HOOKS": "1",
        "REPO_CATALOG_TEST_HOOK_DIR": str(directory),
        "GH_TOKEN": "fixture-dummy",
        "GITHUB_TOKEN": "",
    }
    p = subprocess.Popen(
        [
            shutil.which("repo-catalog"),
            "--state-dir",
            str(state),
            "--format",
            "json",
            *map(str, args),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    end = time.monotonic() + 20
    while not (directory / (hook + ".reached")).exists():
        if p.poll() is not None:
            out, err = p.communicate()
            raise AssertionError((p.returncode, out, err))
        if time.monotonic() > end:
            p.kill()
            p.communicate()
            raise AssertionError("Hook not reached: " + hook)
        time.sleep(0.01)
    return p, directory


def wait_unlocked(path):
    from repo_catalog.adapters.filesystem.locks import FileLock
    from repo_catalog.domain.models import Waiting

    end = time.monotonic() + 10
    while True:
        try:
            with FileLock(path):
                return
        except Waiting:
            if time.monotonic() > end:
                raise
            time.sleep(0.01)
