"""Actual HTTP intake preserves identity-qualified nested milestone producers."""

import json
from uuid import uuid4

import httpx

from repo_catalog.adapters.github.production_intake import milestone_field_name
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.application.provider_fetch import acquire_github
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import ResourceKey
from tests.integration.p5.conftest import init_catalog_stores


class HTTPFixture:
    def __init__(self, path):
        self.path = path
        init_catalog_stores(path, stores=("context", "operational"))
        self.service, self.source = str(uuid4()), str(uuid4())
        self.issue = ResourceKey.from_native(self.service, "issue", "20")
        self.repository = ResourceKey.from_native(self.service, "repository", "10")
        self.auth, self.admission, _ = create_local_admission_service(
            "provider_intake",
            grants=DependencySet(
                resources={self.issue, self.repository},
                sources={self.source},
                provider_registrations={self.service},
            ),
            selection=AdmissionSelection(all_selected=True),
        )

    def collect(self, payload):
        def handler(request):
            value = (
                {"id": 10, "full_name": "owner/repo"}
                if request.url.path == "/repos/owner/repo"
                else [payload]
            )
            return httpx.Response(200, json=value)

        class Anonymous:
            def get(self):
                return None

        document = {
            "operation": "sync",
            "service_instance_uuidv4": self.service,
            "source_registration_uuidv4": self.source,
            "owner": "owner",
            "repository": "repo",
            "request_identity": [str(uuid4()), str(uuid4())],
            "new_request": True,
            "sections": ["issues"],
            "rest_base_url": "https://fixture.invalid",
            "graphql_url": "https://fixture.invalid/graphql",
            "response_bytes": 8192,
        }
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            report = acquire_github(
                self.path,
                document,
                authorization=self.auth,
                admission=self.admission,
                client=client,
                credentials=Anonymous(),
            )
        assert report.status == "complete", report.failure_code
        return ProductionQueryService(self.path).get_context_resource(self.issue)


def payload(month, milestone, **fields):
    return {
        "id": 20,
        "number": 1,
        "updated_at": f"2026-{month:02d}-01T00:00:00Z",
        "milestone": milestone,
        **fields,
    }


def test_same_identified_milestone_sparse_fields_keep_exact_independent_producers(
    tmp_path,
):
    api = HTTPFixture(tmp_path)
    first = api.collect(
        payload(
            1,
            {
                "id": 50,
                "title": "known milestone",
                "state": "closed",
                "closed_issues": 1,
            },
            title="known issue",
            body="exact body\n\x00tail",
            labels=[{"id": 1, "name": "retained"}],
        )
    )
    title = first.fields[milestone_field_name(50, "title")][0]
    body = first.fields["text_body_sha256"]
    newer = api.collect(payload(2, {"id": 50, "state": "open", "closed_issues": 2}))
    assert newer.fields[milestone_field_name(50, "title")] == (title,)
    state = newer.fields[milestone_field_name(50, "state")][0]
    count = newer.fields[milestone_field_name(50, "closed_issues")][0]
    assert json.loads(state.value_json) == "open"
    assert json.loads(count.value_json) == 2
    assert state.provenance_json == count.provenance_json != title.provenance_json
    assert state.clock.at_us > title.clock.at_us
    assert newer.fields["text_body_sha256"] == body
    assert newer.fields["labels"] == first.fields["labels"]
    assert list(newer.resolved_texts.values()) == ["exact body\n\x00tail"]
    assert json.loads(newer.fields["title"][0].value_json) == "known issue"
    # The sparse raw projection is kept honestly; no merged object is assigned
    # the new observation's clock or producer.
    assert json.loads(newer.fields["milestone"][0].value_json) == {
        "id": 50,
        "state": "open",
        "closed_issues": 2,
    }


def test_different_null_and_unidentified_milestones_never_borrow_another_subject_title(
    tmp_path,
):
    api = HTTPFixture(tmp_path)
    first = api.collect(
        payload(1, {"id": 50, "title": "subject fifty", "state": "closed"})
    )
    original = first.fields[milestone_field_name(50, "title")]
    changed = api.collect(payload(2, {"id": 51, "state": "open"}))
    assert changed.fields[milestone_field_name(50, "title")] == original
    assert milestone_field_name(51, "title") not in changed.fields
    assert json.loads(changed.fields["milestone"][0].value_json) == {
        "id": 51,
        "state": "open",
    }
    null = api.collect(payload(3, None, body=None))
    assert null.fields["milestone"][0].value_json == "null"
    assert null.fields[milestone_field_name(50, "title")] == original
    assert null.fields["text_body_sha256"][0].value_json == "null"
    before = {
        key: value
        for key, value in null.fields.items()
        if key.startswith('["milestone",')
    }
    unidentified = api.collect(payload(4, {"state": "closed", "closed_issues": 7}))
    assert json.loads(unidentified.fields["milestone"][0].value_json) == {
        "state": "closed",
        "closed_issues": 7,
    }
    assert {
        key: value
        for key, value in unidentified.fields.items()
        if key.startswith('["milestone",')
    } == before
    explicit_null = api.collect(payload(5, {"id": 50, "title": None}, body=""))
    assert (
        explicit_null.fields[milestone_field_name(50, "title")][0].value_json == "null"
    )
    assert list(explicit_null.resolved_texts.values()) == [""]
    empty = api.collect(payload(6, {"id": 50, "title": ""}))
    assert empty.fields[milestone_field_name(50, "title")][0].value_json == '""'
    assert not (tmp_path / "core.sqlite3").exists()
