"""Independent interaction probes added while b86 findings were corrected."""
from test_final_integrated import (
    FixtureRepo, Store, check_catalog, decoded_fact, export, git_catalog, init,
    receive, fresh_domain_db, candidate, insert, OWNER, sqlite3,
)
import hashlib
import json
import uuid
import pytest


@pytest.mark.parametrize('attack', ['minimal', 'foreign-capture-parent'])
def test_native_pending_current_candidate_is_closed_before_catalog_export(attack):
    db = fresh_domain_db()
    db.row_factory = sqlite3.Row
    value = {'kind': 'change-request', 'acquisition_scope': {}} if attack == 'minimal' else candidate(state='open')
    if attack != 'minimal':
        value['acquisition_scope']['change_request_id'] = 'pr2'
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'))
    with pytest.raises(sqlite3.IntegrityError):
        insert(db, 'exchange_staging',
               record_key='current-state:' + hashlib.sha256(encoded.encode()).hexdigest(),
               content_sha256=hashlib.sha256(encoded.encode()).digest(),
               table_name='change_request_state', repository_uuidv4=OWNER,
               origin_catalog_uuidv4=str(uuid.uuid4()), record_json=encoded,
               reason='current_state:missing_dependency')
    assert db.execute('SELECT count(*) FROM exchange_staging').fetchone()[0] == 0


@pytest.mark.parametrize('alias', ['metadata', 'acquisition_scope'])
def test_decoded_current_candidate_key_cannot_hide_opaque_nested_extension(alias):
    db = fresh_domain_db()
    db.row_factory = sqlite3.Row
    value = candidate(state='open')
    if alias == 'metadata':
        value['metadata'] = {'targets': {'head': {'original_response': {'raw_body': 'opaque provider envelope'}}}}
        escaped_name = 'metad\\u0061ta'
    else:
        value['acquisition_scope']['request_context'] = {'original_response': {'raw_body': 'opaque provider envelope'}}
        escaped_name = 'acquisition\\u005fscope'
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'))
    encoded = encoded.replace('"' + alias + '":', '"' + escaped_name + '":')
    assert json.loads(encoded) == value
    with pytest.raises(sqlite3.IntegrityError):
        insert(db, 'exchange_staging',
               record_key='current-state:' + hashlib.sha256(encoded.encode()).hexdigest(),
               content_sha256=hashlib.sha256(encoded.encode()).digest(),
               table_name='change_request_state', repository_uuidv4=OWNER,
               origin_catalog_uuidv4=str(uuid.uuid4()), record_json=encoded,
               reason='current_state:missing_dependency')
    assert db.execute('SELECT count(*) FROM exchange_staging').fetchone()[0] == 0


def test_pending_ref_capture_onward_two_receivers_then_exact_late_ref(tmp_path):
    remote = FixtureRepo(tmp_path / 'remote.git')
    remote.commit('A', {b'pending.txt': b'independently available canonical blob'})
    remote.ref('refs/heads/main', 'A')
    sender, _ = git_catalog(tmp_path / 'sender', remote)
    with sender:
        original = export(sender)
        expected_origins = sender.one('SELECT count(*) FROM root_origins')[0]
    refs = [row for row in original['records'] if row['table'] == 'ref_observations']
    assert refs
    prefix = {**original, 'records': [row for row in original['records'] if row['table'] != 'ref_observations']}
    first_path, second_path = init(tmp_path / 'first'), init(tmp_path / 'second')
    with Store(first_path) as first:
        assert receive(first, {**prefix, 'records': list(reversed(prefix['records']))})['staged_records']
        assert not first.one('SELECT 1 FROM current_snapshots')
        first_blob = first.one("SELECT git_object_id FROM git_objects WHERE type='blob'")[0]
        assert decoded_fact(first, first_blob, 'blob')['fact'] is not None
        pending_onward = export(first)
    with Store(second_path) as second:
        outcome = receive(second, {**pending_onward, 'records': list(reversed(pending_onward['records']))})
        assert outcome['staged_records']
        assert not second.one('SELECT 1 FROM current_snapshots')
        reasons = [row['reason'] for row in second.all('SELECT reason FROM exchange_staging')]
        assert not any(reason.startswith('invalid:') for reason in reasons), reasons
        second_blob = second.one("SELECT git_object_id FROM git_objects WHERE type='blob'")[0]
        assert decoded_fact(second, second_blob, 'blob')['fact'] is not None
    for path in (first_path, second_path):
        with Store(path) as receiver:
            assert receive(receiver, {**original, 'records': refs})['staged_records'] == 0
            assert receiver.one('SELECT count(*) FROM current_snapshots')[0] == 1
            assert receiver.one('SELECT count(*) FROM root_origins')[0] == expected_origins
            assert not check_catalog(receiver, full=True)
    with Store(second_path) as second:
        complete_onward = export(second)
    with Store(init(tmp_path / 'third')) as third:
        assert receive(third, {**complete_onward, 'records': list(reversed(complete_onward['records']))})['staged_records'] == 0
        assert third.one('SELECT count(*) FROM root_origins')[0] == expected_origins
        assert not check_catalog(third, full=True)
