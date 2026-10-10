"""Independent reader counterexamples after the complete fafc hosted failure."""
import base64

import pytest

from test_final_integrated import (
    OWNER, CatalogError, CancellationToken, FixtureRepo, GitImporter,
    JobService, QueryService, Store, git_catalog, rebuild,
)
from tests.support.git_fixture import git


def acquire_again(store):
    job = JobService(store).create('sync', {'kind': 'git'})
    result = GitImporter(store, CancellationToken()).sync(
        {'repository_uuidv4': OWNER, 'name': 'synthetic'}, job
    )
    JobService(store).update(job, 'complete')
    return result


def rows(state, command, **options):
    return QueryService(state).query(command, {'repo': OWNER, **options}).data['items']


@pytest.fixture
def two_acquisitions(tmp_path):
    remote = FixtureRepo(tmp_path / 'reader.git')
    remote.commit('retired', {b'retired-only.txt': b'retired orphan'})
    remote.commit('ancestor', {b'ancestor-only.txt': b'reachable ancestor'})
    remote.ref('refs/heads/retired', 'retired')
    remote.ref('refs/heads/main', 'ancestor')
    state = tmp_path / 'catalog'
    store, _ = git_catalog(state, remote)
    remote.commit('current', {b'current-only.txt': b'current main'}, ('ancestor',))
    remote.ref('refs/heads/main', 'current')
    git(remote.path, 'update-ref', '-d', 'refs/heads/retired')
    acquire_again(store)
    snapshots = [dict(row) for row in store.all('SELECT * FROM snapshots ORDER BY generation')]
    assert len(snapshots) == 2
    store.close()
    return state, remote, snapshots


def test_history_does_not_promote_retired_captured_head(two_acquisitions):
    state, _, _ = two_acquisitions
    assert rows(state, 'search path', path='retired-only.txt', scope='recorded')
    assert not rows(state, 'search path', path='retired-only.txt', scope='current')
    assert not rows(state, 'search path', path='retired-only.txt', scope='history')


def test_history_uses_reachable_ancestor_tree_of_latest_head(two_acquisitions):
    state, _, _ = two_acquisitions
    assert not rows(state, 'search path', path='ancestor-only.txt', scope='current')
    assert rows(state, 'search path', path='ancestor-only.txt', scope='history')
    assert rows(state, 'search code', literal='reachable ancestor', scope='history')


def test_pr_and_snapshot_are_exclusive_before_subject_lookup(two_acquisitions):
    state, _, snapshots = two_acquisitions
    with pytest.raises(CatalogError) as error:
        rows(state, 'search path', scope='history', path='absent',
             pr=41, snapshot=snapshots[-1]['snapshot_id'])
    assert error.value.code == 'INVALID_ARGUMENT'


@pytest.fixture
def invalid_utf8_commit(tmp_path):
    remote = FixtureRepo(tmp_path / 'message.git')
    remote.commit('parent', {b'plain.txt': b'physical raw bytes'})
    message = b'\xff' + '\u65e5\u672c\u8a9e'.encode('utf8') + b'\n'
    headers = (
        f"tree {remote.trees['parent']}\nparent {remote.commits['parent']}\n"
        'author Independent <independent@example.invalid> 1700000000 +0000\n'
        'committer Independent <independent@example.invalid> 1700000000 +0000\n\n'
    ).encode()
    commit = git(remote.path, 'hash-object', '-t', 'commit', '-w', '--stdin',
                 input=headers + message).strip().decode()
    remote.ref('refs/heads/main', commit)
    state = tmp_path / 'catalog'
    store, _ = git_catalog(state, remote)
    store.close()
    return state, message, commit


def test_commit_literal_cannot_match_replacement_character(invalid_utf8_commit):
    state, _, _ = invalid_utf8_commit
    for indexed in (False, True):
        if indexed:
            with Store(state) as store:
                rebuild(store, 'commits')
        assert not rows(state, 'search commits', literal='\ufffd\u65e5\u672c')
        assert not rows(state, 'search commits', literal='independent absent literal')


def test_commit_literal_offsets_are_physical_message_offsets(invalid_utf8_commit):
    state, message, commit = invalid_utf8_commit
    for indexed in (False, True):
        if indexed:
            with Store(state) as store:
                rebuild(store, 'commits')
        hits = rows(state, 'search commits', literal='\u65e5\u672c\u8a9e')
        assert len(hits) == 1 and hits[0]['oid'] == 'sha1:' + commit
        assert base64.b64decode(hits[0]['message_b64']) == message
        assert (hits[0]['byte_start'], hits[0]['byte_end']) == (1, 10)


def test_tree_entry_reports_actual_saved_eligible_raw(invalid_utf8_commit):
    state, _, _ = invalid_utf8_commit
    entry = rows(state, 'search path', path='plain.txt')[0]
    assert entry['raw_available'] is True
    body = rows(state, 'content show', content_id=entry['content_id'])[0]
    assert base64.b64decode(body['data_b64']) == b'physical raw bytes'


def test_saved_raw_ranges_remain_bounded(invalid_utf8_commit):
    state, _, _ = invalid_utf8_commit
    entry = rows(state, 'search path', path='plain.txt')[0]
    body = rows(state, 'content show', content_id=entry['content_id'])[0]
    assert body['requested_length'] == 65536
    body = rows(state, 'content show', content_id=entry['content_id'], offset=1, length=2)[0]
    assert base64.b64decode(body['data_b64']) == b'hy' and body['has_more']
    with pytest.raises(CatalogError) as error:
        rows(state, 'content show', content_id=entry['content_id'], length=1048577)
    assert error.value.code == 'INVALID_ARGUMENT'


def test_physical_git_bytes_do_not_override_content_profile(tmp_path):
    remote = FixtureRepo(tmp_path / 'binary.git')
    raw = b'\x00\xffindependent canonical bytes'
    remote.commit('binary', {b'binary.bin': raw})
    remote.ref('refs/heads/main', 'binary')
    state = tmp_path / 'catalog'
    store, _ = git_catalog(state, remote)
    canonical = store.one(
        "SELECT b.body FROM available_git_objects g JOIN git_object_payloads p USING(git_object_id) "
        "JOIN stored_bytes b ON b.sha256=p.payload_sha256 WHERE g.type='blob'"
    )
    assert canonical[0] == raw
    store.close()
    entry = rows(state, 'search path', path='binary.bin')[0]
    assert entry['text_state'] == 'nul'
    with pytest.raises(CatalogError) as error:
        rows(state, 'content show', content_id=entry['content_id'])
    assert error.value.code == 'RAW_CONTENT_UNAVAILABLE'
