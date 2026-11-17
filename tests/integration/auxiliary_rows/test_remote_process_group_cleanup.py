"""Real expired-transfer cleanup owns helpers after the Git leader exits."""

import json
import os
import signal
import subprocess
import sys
import time

import pytest

from repo_catalog.adapters.git.remote import _disk_guard, _stop
from repo_catalog.domain.p1_core import CoreFailure

CHILD = """
import json, os, signal, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path(sys.argv[1]).write_text(json.dumps({'pid': os.getpid(), 'pgid': os.getpgrp()}))
time.sleep(30)
"""
PARENT = """
import subprocess, sys, time
from pathlib import Path
subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])
end = time.monotonic() + 5
while not Path(sys.argv[2]).exists():
    if time.monotonic() > end:
        raise RuntimeError('helper readiness deadline')
    time.sleep(0.01)
if sys.argv[3] == 'exited':
    raise SystemExit(0)
time.sleep(30)
"""


def running(pid):
    # A terminated helper can briefly remain a zombie owned by the host reaper.
    # It no longer runs or holds inherited pipes/cache descriptors.
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as status:
            return status.read().rpartition(")")[2].split()[0] != "Z"
    except FileNotFoundError:
        return False


def test_remote_capacity_scan_tolerates_actual_temporary_pack_removal(
    tmp_path, monkeypatch
):
    keep, temporary = tmp_path / "keep.pack", tmp_path / "temporary.pack"
    keep.write_bytes(b"k" * 8192)
    temporary.write_bytes(b"temporary Git pack")
    walk = os.walk

    def changing_walk(*args, **kwargs):
        for root, directories, files in walk(*args, **kwargs):
            temporary.unlink(missing_ok=True)
            yield root, directories, files

    class Work:
        def __init__(self):
            self.charges = []

        def require(self, unit, count):
            assert unit == "metadata_units" and type(count) is int and count > 0

        def charge(self, unit, count):
            self.charges.append((unit, count))

    work = Work()
    monkeypatch.setattr(os, "walk", changing_walk)
    _disk_guard(tmp_path, keep.stat().st_size, work)
    assert work.charges and not temporary.exists()
    assert keep.read_bytes() == b"k" * 8192
    with pytest.raises(CoreFailure) as error:
        _disk_guard(tmp_path, keep.stat().st_size - 1, work)
    assert error.value.code == "BUDGET"


@pytest.mark.parametrize("leader_state", ["alive", "exited"])
def test_expired_remote_transfer_stops_term_ignoring_helper_after_leader_exit(
    tmp_path, leader_state
):
    marker = tmp_path / "owned-helper.json"
    process = subprocess.Popen(
        [sys.executable, "-c", PARENT, CHILD, str(marker), leader_state],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    helper = None
    try:
        end = time.monotonic() + 5
        while not marker.exists():
            assert time.monotonic() < end, "actual helper did not become ready"
            time.sleep(0.01)
        helper = json.loads(marker.read_text())
        assert helper["pgid"] == process.pid
        assert running(helper["pid"])
        if leader_state == "exited":
            assert process.wait(timeout=5) == 0
        # This is the trusted cleanup used when the finite transfer check fails.
        _stop(process)
        end = time.monotonic() + 1
        while running(helper["pid"]) and time.monotonic() < end:
            time.sleep(0.01)
        assert not running(helper["pid"]), (
            "expired transfer left its owned helper alive"
        )
    finally:
        # Always clean up only the process group created by this test invocation.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
