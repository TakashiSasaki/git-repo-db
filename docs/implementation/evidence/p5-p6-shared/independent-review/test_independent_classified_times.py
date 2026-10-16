"""Read-only review tests; independent SQL/typed counterexamples for ADR0028."""
import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_schema import compose, register_functions
from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_context import FieldCandidate, FieldClock, ResourceKey, canonical, CoverageScope
from repo_catalog.domain.p1_core import GitObservation, RepositoryClaim, Provenance
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.time import validate_epoch_us

REPO = '9ebbe38a-f937-40e6-a99c-701835ebcf10'
SERVICE = 'aad25448-03eb-4f83-a578-ceec84375b5a'
ORIGIN = '80f5c4f9-6d6b-4691-af3c-00ab02ad9f53'
CAPTURE = 'a1a5dfd6-69a3-4274-bbc7-2e7f6bcd39a4'
KEY = ResourceKey(SERVICE, 'issue', '7')
PROV = canonical({'source': 'provider.example', 'evidence': 'event-7'})
CPROV = Provenance('source', 'observation', 'coordinate', 'decoder', '1')
INVALID = [-1, 0, -(1 << 63), (1 << 63), -(1 << 63)-1, True, False, 1.0, 1.5, '1']

@pytest.fixture
def db():
    conn = sqlite3.connect(':memory:', isolation_level=None)
    register_functions(conn)
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(compose('context'))
    conn.execute('INSERT INTO providers VALUES(?,?,?)', (SERVICE, 'github', '{}'))
    conn.execute('INSERT INTO repository_context VALUES(?,?)', (REPO, '{}'))
    ContextStore(conn).resource(KEY, REPO)
    yield conn
    conn.close()

@pytest.mark.parametrize('stamp', [None, 1, (1 << 63)-1])
def test_unknown_or_positive_field_roundtrip(db, stamp):
    candidate = FieldCandidate(KEY, 'title', 'null', FieldClock('provider.updated', stamp), PROV, stamp)
    store = ContextStore(db)
    assert store.admit_field(candidate) == 'insert'
    assert store.admit_field(candidate) == 'duplicate'
    assert store.candidates(KEY, 'title') == (candidate,)

@pytest.mark.parametrize('stamp', INVALID)
def test_observed_and_provider_reject_same_invalid_types(stamp):
    with pytest.raises((TypeError, ValueError)):
        FieldClock('provider.updated', stamp)
    with pytest.raises((TypeError, ValueError)):
        FieldCandidate(KEY, 'title', 'null', FieldClock('provider.updated', None), PROV, stamp)
    with pytest.raises((TypeError, ValueError)):
        CoverageClaim(CoverageScope.repository(REPO, 'metadata'), stamp, 'unknown')


def test_null_coverage_is_not_a_proof():
    with pytest.raises((TypeError, ValueError)):
        CoverageClaim(CoverageScope.repository(REPO, 'metadata'), None, 'unknown')

@pytest.mark.parametrize('stamp', INVALID)
def test_json_clock_rejects_before_sql_generated_affinity(db, stamp):
    clock = canonical({'domain': 'provider.updated', 'at_us': stamp})
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)', (*KEY.coordinates(), 'title', 'null', clock, PROV, 1))

@pytest.mark.parametrize('stamp', [-1, 0, -(1 << 63)])
def test_sql_stored_observation_rejects_nonpositive(db, stamp):
    clock = canonical({'domain': 'provider.updated', 'at_us': None})
    with pytest.raises(sqlite3.IntegrityError):
        db.execute('INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)', (*KEY.coordinates(), 'title', 'null', clock, PROV, stamp))


def test_clockless_does_not_resolve_by_arrival_or_known_observation(db):
    store = ContextStore(db)
    for value, observed in [('unknown', None), ('early', 1), ('later', 2)]:
        item = FieldCandidate(KEY, 'title', canonical(value), FieldClock('provider.updated', None), canonical({'source':'provider.example','evidence':value}), observed)
        store.admit_field(item)
    assert {item.value_json for item in store.candidates(KEY, 'title')} == {'"unknown"', '"early"', '"later"'}

@pytest.mark.parametrize('stamp', [None, 1, (1 << 63)-1])
def test_core_observation_is_not_git_native_by_location(stamp):
    RepositoryClaim(REPO, 'observation_us', stamp, CPROV)
    GitObservation(ORIGIN, CAPTURE, REPO, 'acquisition', ('scope',), {'source':'source', 'observed_at_us':stamp, 'endpoint':None}, CPROV)

@pytest.mark.parametrize('stamp', INVALID)
def test_core_observation_rejects_nonpositive_noninteger(stamp):
    with pytest.raises((TypeError, ValueError)):
        RepositoryClaim(REPO, 'observation_us', stamp, CPROV)
    with pytest.raises((TypeError, ValueError)):
        GitObservation(ORIGIN, CAPTURE, REPO, 'acquisition', ('scope',), {'source':'source', 'observed_at_us':stamp, 'endpoint':None}, CPROV)


def test_terminal_requires_observation_coordinate():
    with pytest.raises((TypeError, ValueError)):
        GitObservation(ORIGIN, CAPTURE, REPO, 'acquisition', ('scope',), {'source':'source', 'observed_at_us':None, 'endpoint':None, 'enumeration_state':'complete', 'terminal_observation':True}, CPROV)

@pytest.mark.parametrize('fmt,width', [('sha1',40),('sha256',64)])
@pytest.mark.parametrize('seconds', [-1,0,1])
def test_git_native_signed_time_and_exact_original_body(fmt, width, seconds):
    body = f'tree {"a"*width}\nauthor A <a@b> {seconds} +0000\ncommitter A <a@b> {seconds} +0000\n\nmessage'.encode()
    original = bytes(body)
    metadata = parse_metadata(fmt, 'commit', body)
    assert metadata.scalars['author_time_us'] == seconds * 1_000_000
    assert metadata.scalars['committer_time_us'] == seconds * 1_000_000
    assert body == original
    validate_epoch_us(seconds * 1_000_000)
    if seconds <= 0:
        with pytest.raises((TypeError, ValueError)):
            FieldClock('provider.updated', seconds * 1_000_000)

@pytest.mark.parametrize('stamp', [-(1<<63),-1,0,1,(1<<63)-1])
def test_generic_signed_int64_is_unchanged(stamp):
    assert validate_epoch_us(stamp) == stamp

@pytest.mark.parametrize('stamp', INVALID)
def test_json_core_timestamp_guards_reject_types_before_sql_affinity(db, stamp):
    assert db.execute('SELECT p1_repository_claim(?,?,?,?)', (REPO, 'observation_us', canonical(stamp), CPROV.encoded)).fetchone()[0] == 0
    value = canonical({'source':'source', 'observed_at_us':stamp, 'endpoint':None})
    assert db.execute('SELECT p1_git_observation(?,?,?,?,?,?,?)', (ORIGIN, CAPTURE, REPO, 'acquisition', canonical(['scope']), value, CPROV.encoded)).fetchone()[0] == 0


def test_api_does_not_infer_seconds_from_small_magnitude(db):
    candidate = FieldCandidate(KEY, 'title', 'null', FieldClock('provider.updated', 1), PROV, 1)
    ContextStore(db).admit_field(candidate)
    assert db.execute('SELECT observed_at_us,source_clock_us FROM field_candidates').fetchone() == (1,1)

@pytest.mark.parametrize('fmt,width', [('sha1',40),('sha256',64)])
@pytest.mark.parametrize('seconds', [-1,0])
def test_signed_git_native_storage_and_reopen_preserve_bytes(tmp_path, fmt, width, seconds):
    import hashlib
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.adapters.sqlite.p1_schema import initialize
    from repo_catalog.domain.p1_core import OID, NativeObject, native_oid
    from uuid import uuid4
    class Budget:
        def require(self, unit, amount=1):
            assert type(amount) is int and amount >= 0
        def charge(self, unit, amount):
            assert type(amount) is int and amount >= 0
    body = f'tree {"a"*width}\nauthor A <a@b> {seconds} +0000\ncommitter A <a@b> {seconds} +0000\n\nmessage'.encode()
    native = NativeObject(OID(fmt,native_oid(fmt,'commit',body)), 'commit',body,len(body),hashlib.sha256(body).hexdigest())
    path = tmp_path / 'core.sqlite3'
    initialize(path, 'core', REPO, str(uuid4()))
    core = GitCore(path)
    core.admit_metadata(native, str(uuid4()), Budget())
    core.close()
    core = GitCore(path)
    try:
        assert core.read_metadata(native.oid) == body
        assert core.scalar(native.oid, 'author_time_us').canonical == ['known', seconds * 1_000_000]
        assert core.scalar(native.oid, 'committer_time_us').canonical == ['known', seconds * 1_000_000]
    finally:
        core.close()
