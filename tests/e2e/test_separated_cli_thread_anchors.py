"""Thread capture inputs remain original after later detail reads and failures."""

import json

import httpx

from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.p1_repository import OID
from tests.e2e.test_separated_cli import document
from tests.e2e.test_separated_cli_pr_assessment import query
from tests.e2e.test_separated_cli_provider_regressions import (
    GraphQLFixture,
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def test_live_thread_root_and_child_keep_actual_captured_head_when_later_detail_changes(
    provider_case, tmp_path, capsys, monkeypatch
):
    case, phase, api = provider_case, ["original"], GraphQLFixture()
    old_head, new_head, base = "1" * 40, "3" * 40, "2" * 40
    case.authority = document(
        tmp_path,
        "anchor-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()),
                sources=frozenset({case.source}),
                provider_registrations=frozenset({case.service}),
                object_oids=frozenset(
                    OID("sha1", value) for value in (old_head, new_head, base)
                ),
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )

    def handle(http):
        if http.url.path.endswith("/pulls/1"):
            payload = {"id": 20, "updated_at": 10 if phase[0] == "original" else 20}
            if phase[0] != "unanchored":
                payload.update(
                    head={"sha": old_head if phase[0] == "original" else new_head},
                    base={"sha": base},
                )
            return _http_response(http, payload)
        if http.method == "POST" and phase[0] == "unobserved":
            return httpx.Response(401, json={"message": "no thread root was observed"})
        return api.response(http)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first, request = _network_cli(case, tmp_path, capsys, monkeypatch, client)
        assert first["status"] == "complete"
        before = case.view(capsys, case.keys["pull"])
        root = [
            item
            for item in before["collections"]
            if item["collection_kind"] == "review_threads"
        ]
        children = case.view(capsys, case.keys["thread"])["collections"]
        for captured in (*root, *children):
            assert captured["scope"]["head_object_oid"] == ["sha1", old_head]
            assert captured["scope"]["base_object_oid"] == ["sha1", base]
            anchor = json.loads(captured["scope"]["anchor_provenance_json"])
            assert anchor in [
                candidate["provenance"]
                for candidate in before["fields"]["head_object_oid"]
            ]
            assert captured["scope"]["member_provenance_jsons"]
        phase[0] = "unobserved"
        request["new_request"] = False
        failed, request = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
        assert (
            failed["status"] == "partial"
            and failed["failure_code"] == "CREDENTIALS_MISSING"
        )
        after = case.view(capsys, case.keys["pull"])
        assert {item["value"] for item in after["fields"]["head_object_oid"]} == {
            new_head
        }
        assert [
            item
            for item in after["collections"]
            if item["collection_kind"] == "review_threads"
        ] == root
        assert case.view(capsys, case.keys["thread"])["collections"] == children
        selected = query(capsys, case, "pr-documents", "--thread-id", "thread-one")
        assert selected["state"] == "complete" and selected["total_count"] == 2
        phase[0] = "unanchored"
        unanchored, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
    assert unanchored["status"] == "complete"
    actual_scopes = [
        json.loads(observation["scope_json"])
        for batch in unanchored["batches"]
        for _, observation, _ in batch["collection_proofs"]
        if observation["collection_kind"]
        in {"review_threads", "review_thread_comments"}
    ]
    assert actual_scopes and all(
        "head_object_oid" not in scope and "anchor_provenance_json" not in scope
        for scope in actual_scopes
    )
    assert {
        item["value"]
        for item in case.view(capsys, case.keys["pull"])["fields"]["head_object_oid"]
    } == {new_head}
    assert not (case.directory / "repository.sqlite3").exists()
