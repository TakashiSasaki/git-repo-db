"""Actual Provider repository normalization preserves per-field original evidence."""

import json

import pytest

from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.provider_acquisition import (
    ProviderIntakeBatch,
    ProviderRepositoryIntake,
)
from tests.integration.p3.test_production_context import SERVICE, SOURCE, directory
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]


def test_repository_null_omission_empty_object_and_new_name_retain_each_exact_producer(
    directory,
):
    key = ResourceKey.from_native(SERVICE, "repository", "10")
    grants = DependencySet(
        resources={key}, provider_registrations={SERVICE}, sources={SOURCE}
    )
    with fixture_transaction(directory, grants) as context:
        context.provider(SERVICE, "github")
        context.source(SOURCE, SERVICE)
    auth, admission, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    acquisition = ProviderAcquisition(
        directory, authorization=auth, admission=admission
    )

    def admit(payload, stamp):
        producer = canonical(
            {
                "source": "actual-repository-normalizer",
                "evidence": {"source_registration_uuidv4": SOURCE, "step": stamp},
            }
        )
        acquisition.admit_batch(
            ProviderIntakeBatch(
                SERVICE,
                provider_repositories=(
                    ProviderRepositoryIntake(payload, stamp, producer),
                ),
            )
        )
        return producer

    first = admit(
        {
            "id": 10,
            "name": None,
            "private": False,
            "owner": {"login": "original-owner"},
            "updated_at": 10,
        },
        11,
    )
    before = ContextQueryService(directory, mode="context_only").get_context_resource(
        key
    )
    assert before.fields["name"][0].value_json == "null"
    second = admit({"id": 10, "owner": {}, "updated_at": 20}, 21)
    sparse = ContextQueryService(directory, mode="context_only").get_context_resource(
        key
    )
    assert sparse.fields["name"] == before.fields["name"]
    assert sparse.fields["private"] == before.fields["private"]
    assert sparse.fields["owner"][0].value_json == "{}"
    assert sparse.fields["owner"][0].provenance_json == second
    third = admit({"id": 10, "name": "genuine newer name", "updated_at": 30}, 31)
    current = ContextQueryService(directory, mode="context_only").get_context_resource(
        key
    )
    assert json.loads(current.fields["name"][0].value_json) == "genuine newer name"
    assert current.fields["name"][0].provenance_json == third
    assert current.fields["private"][0].provenance_json == first
    assert current.fields["private"][0].observed_at_us == 11
    assert current.fields["owner"] == sparse.fields["owner"]
    with pytest.raises(ValueError):
        acquisition.admit_batch(
            ProviderIntakeBatch(
                SERVICE,
                provider_repositories=(
                    ProviderRepositoryIntake(
                        {"id": 10, "name": "must not write"},
                        40,
                        canonical({"source": "missing-evidence"}),
                    ),
                ),
            )
        )
    assert (
        ContextQueryService(directory, mode="context_only").get_context_resource(key)
        == current
    )
    assert not (directory / "repository.sqlite3").exists()
    assert not (directory / "p1-recovery-stop.json").exists()
