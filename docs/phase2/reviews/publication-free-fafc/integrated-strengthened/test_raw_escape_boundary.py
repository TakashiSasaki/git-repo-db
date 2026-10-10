"""A displayed decoder escape is not a literal present in canonical bytes."""
from test_reader_boundaries import invalid_utf8_commit, rows
import base64
from test_final_integrated import FixtureRepo, Store, git_catalog, rebuild


def test_generated_decoder_escape_is_not_raw_commit_literal(invalid_utf8_commit):
    state, message, _ = invalid_utf8_commit
    assert b'\\xff' not in message
    for indexed in (False, True):
        if indexed:
            with Store(state) as store:
                rebuild(store, 'commits')
        assert not rows(state, 'search commits', literal=r'\xff')


def test_real_backslash_bytes_remain_searchable(tmp_path):
    remote = FixtureRepo(tmp_path / 'literal-backslash.git')
    label = r'literal-\xff'
    commit = remote.commit(label, {b'plain.txt': b'positive control'})
    remote.ref('refs/heads/main', label)
    message = f'commit {label} \u8a8d\u8a3c\n'.encode()
    expected = message.index(b'\\xff')
    state = tmp_path / 'catalog'
    store, _ = git_catalog(state, remote)
    store.close()
    for indexed in (False, True):
        if indexed:
            with Store(state) as store:
                rebuild(store, 'commits')
        hits = rows(state, 'search commits', literal=r'\xff')
        assert len(hits) == 1 and hits[0]['oid'] == 'sha1:' + commit
        assert base64.b64decode(hits[0]['message_b64']) == message
        assert (hits[0]['byte_start'], hits[0]['byte_end']) == (expected, expected + 4)
