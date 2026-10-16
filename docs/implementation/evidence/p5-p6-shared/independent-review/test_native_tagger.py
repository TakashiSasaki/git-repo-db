"""Independent native tagger signed time storage control for both Git formats."""
import hashlib
from uuid import uuid4
import pytest
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.p1_core import OID, NativeObject, native_oid

class Budget:
    def require(self, unit, amount=1):
        assert type(amount) is int and amount >= 0
    def charge(self, unit, amount):
        assert type(amount) is int and amount >= 0

@pytest.mark.parametrize('fmt,width', [('sha1',40),('sha256',64)])
@pytest.mark.parametrize('seconds', [-1,0])
def test_native_tagger_signed_time_retains_exact_representation(tmp_path, fmt, width, seconds):
    identity = f'A <a@b> {seconds} +0000'
    body = f'object {"a"*width}\ntype commit\ntag v1\ntagger {identity}\n\nmessage'.encode()
    native = NativeObject(OID(fmt,native_oid(fmt,'tag',body)), 'tag',body,len(body),hashlib.sha256(body).hexdigest())
    path = tmp_path / 'core.sqlite3'
    initialize(path, 'core', str(uuid4()), str(uuid4()))
    core = GitCore(path)
    core.admit_metadata(native, str(uuid4()), Budget())
    core.close()
    core = GitCore(path)
    try:
        assert core.read_metadata(native.oid) == body
        assert core.scalar(native.oid, 'tagger').canonical == ['known', identity]
    finally:
        core.close()
