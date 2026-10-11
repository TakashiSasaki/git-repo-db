"""A displayed decoder escape is not a literal present in canonical bytes."""
from test_reader_boundaries import invalid_utf8_commit, rows
from test_final_integrated import Store, rebuild


def test_generated_decoder_escape_is_not_raw_commit_literal(invalid_utf8_commit):
    state, message, _ = invalid_utf8_commit
    assert b'\\xff' not in message
    for indexed in (False, True):
        if indexed:
            with Store(state) as store:
                rebuild(store, 'commits')
        assert not rows(state, 'search commits', literal=r'\xff')
