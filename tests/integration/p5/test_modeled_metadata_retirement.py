"""Decoded API keys retain their modeled types before current Context admission."""

import json
from contextlib import closing

import pytest

from repo_catalog.adapters.github import production_intake as intake
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.acquisition_errors import AcquisitionError
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.provider_acquisition import (
    ProviderIntakeBatch,
    ProviderIssueIntake,
    ProviderPullRequestIntake,
)
from tests.integration.p3.test_production_context import SERVICE, SOURCE, directory
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]
ORIGIN = canonical(
    {"source": "real metadata parser", "evidence": "captured API fields"}
)
CASES = [
    ("escaped-object", r'{"\u006dilestone":{"title":false}}'),
    ("escaped-leaf", r'{"milestone":{"\u0074itle":false}}'),
    ("escaped-label-name", r'{"labels":[{"\u006eame":false}]}'),
    ("escaped-label-container", r'{"\u006cabels":[false]}'),
    ("escaped-reaction", r'{"reactions":{"\u002b1":"wrong"}}'),
    ("escaped-node-id", r'{"\u006eode_id":false}'),
]
TARGETS = [
    pytest.param(family, raw, id=f"{family}-{label}")
    for family in ("issue", "pull_request")
    for label, raw in CASES
    if family == "pull_request" or label != "escaped-node-id"
]


def payload(extra=None, *, month=1):
    return {
        "id": 51,
        "number": 2,
        "title": "healthy original title",
        "body": "healthy original body",
        "state": "open",
        "updated_at": f"2026-{month:02d}-01T00:00:00Z",
        **(extra or {}),
    }


def normalized(family, value):
    fn = intake.normalize_issue if family == "issue" else intake.normalize_pull_request
    return fn(SERVICE, value, 100, ORIGIN)


def batch(family, value):
    constructor = (
        ProviderIssueIntake if family == "issue" else ProviderPullRequestIntake
    )
    return ProviderIntakeBatch(
        SERVICE,
        **{
            "issues" if family == "issue" else "pull_requests": (
                constructor(value, 100, ORIGIN),
            )
        },
    )


def service(directory, family):
    key = ResourceKey.from_native(SERVICE, family, "51")
    unit = normalized(family, payload())
    resources = {key, *(observation.resource for observation in unit.observations)}
    resources.update(item[0] for item in unit.text_admissions)
    grants = DependencySet(
        resources=resources, sources={SOURCE}, provider_registrations={SERVICE}
    )
    with fixture_transaction(directory, grants) as context:
        context.provider(SERVICE, "github")
        context.source(SOURCE, SERVICE)
    authorization, admission, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    return ProviderAcquisition(
        directory, authorization=authorization, admission=admission
    ), key


@pytest.mark.parametrize("family,raw", TARGETS)
def test_decoded_known_metadata_keys_reject_malformed_native_types(family, raw):
    with pytest.raises(AcquisitionError):
        normalized(family, payload(json.loads(raw)))


@pytest.mark.parametrize("family,raw", TARGETS)
def test_malformed_modeled_metadata_cannot_replace_healthy_current_fields(
    directory, family, raw
):
    acquisition, key = service(directory, family)
    acquisition.admit_batch(batch(family, payload()))
    query = ContextQueryService(directory, mode="context_only")
    before = query.get_context_resource(key, include_text=True)
    with closing(connect(directory / "context.sqlite3", "context")) as db:
        original_counts = tuple(
            db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for table in ("resources", "field_candidates", "text_bodies")
        )
    with pytest.raises(AcquisitionError):
        acquisition.admit_batch(batch(family, payload(json.loads(raw), month=2)))
    after = query.get_context_resource(key, include_text=True)
    assert after.fields == before.fields
    assert after.resolved_texts == before.resolved_texts
    with closing(connect(directory / "context.sqlite3", "context")) as db:
        assert (
            tuple(
                db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                for table in ("resources", "field_candidates", "text_bodies")
            )
            == original_counts
        )
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert not (directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("family", ["issue", "pull_request"])
def test_valid_nested_metadata_is_retained_with_its_actual_original(directory, family):
    extra = json.loads(
        r'{"\u006dilestone":{"id":50,"\u0074itle":"known","creator":{"login":"synthetic"}},'
        r'"\u006cabels":[{"\u006eame":"ready","default":false}],"reactions":{"\u002b1":0}}'
    )
    if family == "pull_request":
        extra["node_id"] = "descriptive-node"
    acquisition, key = service(directory, family)
    acquisition.admit_batch(batch(family, payload(extra)))
    query = ContextQueryService(directory, mode="context_only")
    before = query.get_context_resource(key)
    for name, value in extra.items():
        assert {item.value_json for item in before.fields[name]} == {canonical(value)}
        assert all(item.provenance_json == ORIGIN for item in before.fields[name])
    acquisition.admit_batch(batch(family, payload(month=2)))
    after = query.get_context_resource(key)
    for name in extra:
        assert after.fields[name] == before.fields[name]
    assert after.resource == key
