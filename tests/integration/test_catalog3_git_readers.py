"""Git readers follow exact immutable interpretations over shared raw objects."""

import base64

from repo_catalog.adapters.git.parsing import reparse_git
from repo_catalog.adapters.sqlite.index import rebuild
from repo_catalog.adapters.sqlite.parser_model import ParserModel, builtin_definition
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.target_queries import TargetQueryService
from tests.support.cli import run


def latin_profile(model):
    definition = builtin_definition()
    definition["settings"] = {
        **definition["settings"],
        "git_text_encoding": "latin-1",
        "git_metadata_encoding": "latin-1",
    }
    profile = model.register_profile(definition)
    verification = model.verify_profile(
        profile,
        criteria={"test": "Git decoding reader contract"},
        evidence={
            "definition": definition,
            "capabilities": [
                {**capability, "outcome": "passed", "checks": ["synthetic fixture"]}
                for capability in definition["capabilities"]
            ],
        },
    )
    model.trust_verification(verification)
    return profile, verification


def test_git_reader_profile_and_result_selection(catalog):
    state, fixture, repositories = catalog
    run(state, "sync", "git")
    repository = repositories["alpha"]
    options = {
        "repo": repository,
        "ref": "refs/heads/main",
        "path": "README.md",
    }
    query = QueryService(state)
    original = query.query("file show", options).data["items"][0]
    assert original["text"].startswith("認証")
    with Store(state) as store:
        model = ParserModel(store.connection)
        acquisition = store.one(
            "SELECT git_acquisition_id FROM current_snapshots WHERE repository_uuidv4=?",
            (repository,),
        )[0]
        with store.transaction():
            profile, verification = latin_profile(model)
        alternate = reparse_git(store, acquisition, profile_uuid=profile)
        assert query.query("file show", options).data["items"][0] == original
        rebuild(store, "code")
        assert not store.one(
            "SELECT 1 FROM search_documents d JOIN git_text_facts f ON f.git_fact_uuidv4=d.source_key WHERE f.parsed_result_uuidv4=?",
            (alternate["parsed_result_uuidv4"],),
        )
        with store.transaction():
            model.select_profile(
                profile,
                verification,
                repository_uuidv4=repository,
                fact_kind="git",
            )
        unresolved = query.query("file show", options)
        assert unresolved.data["items"] == []
        assert unresolved.status == "partial"
        with store.transaction():
            model.select_fact(alternate["parsed_result_uuidv4"], fact_kind="git")
            model.select_fact(
                alternate["parsed_result_uuidv4"],
                fact_kind="git",
                git_acquisition_id=acquisition,
            )
        selected = query.query("file show", options).data["items"][0]
        expected = original["text"].encode().decode("latin-1")
        assert selected["text"] == expected
        assert selected["content_id"] == original["content_id"]
        assert selected["parsed_result_uuidv4"] == alternate["parsed_result_uuidv4"]
        commit = query.query("commits show", options).data["items"][0]
        assert "認証" not in commit["message"]
        assert "認証".encode().decode("latin-1") in commit["message"]
        odd = query.query(
            "file show", {**options, "path": None, "path_b64": "b2RkL/8JbGluZQoudHh0"}
        ).data["items"][0]
        assert "ÿ" in odd["path_display"]
        raw = query.query("content show", {"content_id": selected["content_id"]})
        assert (
            base64.b64decode(raw.data["items"][0]["data_b64"])
            == original["text"].encode()
        )
        rebuild(store, "code")
        ready = store.one(
            "SELECT index_generation_id FROM index_generations WHERE kind='code' AND state='ready'"
        )[0]
        assert not store.one(
            "SELECT 1 FROM index_membership m JOIN search_documents d USING(search_document_id) JOIN git_text_facts f ON f.git_fact_uuidv4=d.source_key WHERE m.index_generation_id=? AND f.repository_uuidv4=? AND f.parsed_result_uuidv4<>?",
            (ready, repository, alternate["parsed_result_uuidv4"]),
        )
        assert (
            query.query("search code", {"repo": repository, "literal": "認証"}).data[
                "items"
            ]
            == []
        )
        assert query.query(
            "search code", {"repo": repository, "literal": expected[:3]}
        ).data["items"]
        other = reparse_git(store, acquisition, profile_uuid=profile)
        with store.transaction():
            model.select_fact(
                other["parsed_result_uuidv4"], fact_kind="git", predecessors=[]
            )
        conflicted = query.query(
            "search code", {"repo": repository, "literal": expected}
        )
        assert conflicted.data["items"] == []
        assert conflicted.status == "partial"
        historical = query.query(
            "file show", {**options, "snapshot": alternate["snapshot_id"]}
        )
        assert historical.data["items"][0]["text"] == expected
        diagnostic = TargetQueryService(state / "catalog.sqlite3").query(
            "file",
            {
                "repo": repository,
                "commit": "sha1:" + fixture.alpha.commits["N"],
                "path": "README.md",
                "snapshot": alternate["snapshot_id"],
            },
        )
        assert diagnostic.data["items"][0]["text"] == expected
