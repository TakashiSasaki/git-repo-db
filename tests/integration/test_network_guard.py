import socket
import subprocess
import sys

import pytest


def test_parent_and_subprocess_external_network_blocked():
    with pytest.raises(PermissionError):
        socket.getaddrinfo("api.github.com", 443)
    p = subprocess.run(
        [
            sys.executable,
            "-c",
            "import socket; socket.create_connection(('1.1.1.1',443))",
        ],
        capture_output=True,
        text=True,
    )
    assert p.returncode != 0 and "PermissionError" in p.stderr
