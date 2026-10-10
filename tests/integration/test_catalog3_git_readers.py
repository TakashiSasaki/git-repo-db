"""Git readers expose direct decoder conflicts and exact raw captures."""

import base64

from repo_catalog.adapters.git.parsing import reparse_git
from repo_catalog.adapters.sqlite.index import rebuild
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.target_queries import TargetQueryService
from tests.support.cli import run


def test_git_readers_require_explicit_decoder_when_real_outputs_differ(catalog):
    state, fixture, repositories = catalog
    run(state, "sync", "git")
    repository = repositories["alpha"]
    options = {"repo": repository, "ref": "refs/heads/main", "path": "README.md"}
    query = QueryService(state)
    original = query.query("file show", options).data["items"][0]
    assert original["text"].startswith("認証")
    with Store(state) as store:
        acquisition = store.one(
            "SELECT git_acquisition_id FROM current_snapshots WHERE repository_uuidv4=?",
            (repository,),
        )[0]
        snapshot = store.one(
            "SELECT snapshot_id FROM current_snapshots WHERE repository_uuidv4=?",
            (repository,),
        )[0]
        alternate = reparse_git(
            store, acquisition, text_encoding="latin-1", metadata_encoding="latin-1"
        )
        unresolved = query.query("file show", options)
        assert unresolved.data["items"][0]["text"] is None
        assert unresolved.status == "partial"
        assert any(
            row["reason"] == "decoder_conflict" for row in unresolved.coverage.missing
        )
        selected_options = {**options, "decoder_key": alternate["decoder_key"]}
        selected = query.query("file show", selected_options).data["items"][0]
        expected = original["text"].encode().decode("latin-1")
        assert selected["text"] == expected
        assert selected["content_id"] == original["content_id"]
        assert "parsed_result_uuidv4" not in selected
        commit = query.query("commits show", selected_options).data["items"][0]
        assert "認証".encode().decode("latin-1") in commit["message"]
        raw = query.query("content show", {"content_id": selected["content_id"]})
        assert (
            base64.b64decode(raw.data["items"][0]["data_b64"])
            == original["text"].encode()
        )
        rebuild(store, "code")
        assert (
            query.query("search code", {"repo": repository, "literal": "認証"}).data[
                "items"
            ]
            == []
        )
        assert query.query(
            "search code",
            {
                "repo": repository,
                "literal": expected[:3],
                "decoder_key": alternate["decoder_key"],
            },
        ).data["items"]
        # Repeating the same concrete decoder does not create a new candidate,
        # acquisition, capture, selection or current-ref winner.
        before = store.one("SELECT count(*) FROM git_text_facts")[0]
        again = reparse_git(
            store, acquisition, text_encoding="latin-1", metadata_encoding="latin-1"
        )
        assert again["decoder_key"] == alternate["decoder_key"]
        assert store.one("SELECT count(*) FROM git_text_facts")[0] == before
        assert (
            store.one(
                "SELECT snapshot_id FROM current_snapshots WHERE repository_uuidv4=?",
                (repository,),
            )[0]
            == snapshot
        )
    historical = query.query("file show", {**selected_options, "snapshot": snapshot})
    assert historical.data["items"][0]["text"] == expected
    diagnostic = TargetQueryService(state / "catalog.sqlite3").query(
        "file",
        {
            "repo": repository,
            "commit": "sha1:" + fixture.alpha.commits["N"],
            "path": "README.md",
            "snapshot": snapshot,
            "decoder_key": alternate["decoder_key"],
        },
    )
    assert diagnostic.data["items"][0]["text"] == expected
