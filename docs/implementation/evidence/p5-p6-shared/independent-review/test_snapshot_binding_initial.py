"""Independent counterexample for shared typed snapshot origin binding."""
from uuid import uuid4
import pytest
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.p1_core import CoreFailure


def test_typed_core_reader_refuses_foreign_catalog_directory(tmp_path):
    source = tmp_path / 'source'
    other = tmp_path / 'other'
    source.mkdir()
    other.mkdir()
    initialize(source / 'core.sqlite3', 'core', str(uuid4()), str(uuid4()))
    initialize(other / 'core.sqlite3', 'core', str(uuid4()), str(uuid4()))
    with PairCoordinator(source).core_snapshot() as read:
        with pytest.raises((CoreFailure, ValueError)):
            with GitCore.for_snapshot(read, other):
                pass


def test_foreign_directory_cannot_redirect_detected_source_corruption_stop(tmp_path):
    import hashlib
    import sqlite3
    from repo_catalog.domain.p1_core import OID, NativeObject, native_oid
    from repo_catalog.adapters.sqlite.p1_schema import register_functions
    class Budget:
        def require(self, unit, amount=1):
            pass
        def charge(self, unit, amount):
            pass
    source = tmp_path / 'source'
    other = tmp_path / 'other'
    source.mkdir()
    other.mkdir()
    initialize(source / 'core.sqlite3', 'core', str(uuid4()), str(uuid4()))
    initialize(other / 'core.sqlite3', 'core', str(uuid4()), str(uuid4()))
    tree = NativeObject(OID('sha1',native_oid('sha1','tree',b'')), 'tree', b'',0,hashlib.sha256(b'').hexdigest())
    core = GitCore(source / 'core.sqlite3')
    core.admit_metadata(tree, str(uuid4()), Budget())
    core.close()
    db = sqlite3.connect(source / 'core.sqlite3', isolation_level=None)
    register_functions(db)
    db.execute('DROP TRIGGER p1_immutable_retained_metadata_update')
    db.execute('PRAGMA ignore_check_constraints=ON')
    db.execute("UPDATE retained_metadata SET body=x'01'")
    # Restore the packaged guard so source validation still checks the exact schema.
    from repo_catalog.adapters.sqlite.p1_schema import compose
    ddl = compose('core')
    trigger = ddl[ddl.index('CREATE TRIGGER p1_immutable_retained_metadata_update'):]
    db.executescript(trigger.split(';\n', 1)[0] + ';\n')
    db.close()
    with PairCoordinator(source).core_snapshot() as read:
        with pytest.raises(CoreFailure):
            with GitCore.for_snapshot(read, other) as typed:
                typed.read_metadata(tree.oid)
    assert (source / 'p1-recovery-stop.json').exists(), 'detected authoritative source was left unstopped'
    assert not (other / 'p1-recovery-stop.json').exists(), 'unrelated catalog was stopped'
