"""Test subprocess guard; deliberately contains no application imports."""

import ipaddress
import os
import socket


def permitted(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_resolve = socket.getaddrinfo


def connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not permitted(address[0]):
        raise PermissionError("Offline tests permit loopback connections only")
    return _connect(self, address)


def connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not permitted(address[0]):
        raise PermissionError("Offline tests permit loopback connections only")
    return _connect_ex(self, address)


def resolve(host, *args, **kwargs):
    if host is not None and not permitted(host):
        raise PermissionError("Offline tests prohibit external DNS")
    return _resolve(host, *args, **kwargs)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = resolve

# Explicit test-only bootstrap; no application environment escape hatch.
if os.environ.get("REPO_CATALOG_TEST_BOOTSTRAP") == "1":
    import runpy
    from pathlib import Path

    runpy.run_path(str(Path(__file__).parents[1] / "parser_bootstrap.py"))["install"]()
