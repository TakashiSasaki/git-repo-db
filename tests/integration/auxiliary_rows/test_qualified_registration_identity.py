"""Names remain descriptions; current selection uses permanent typed identities."""

from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_repository import Provenance, RepositoryClaim
from repo_catalog.domain.shared_values import encode


def test_same_names_and_uuid_looking_descriptions_never_select_or_merge_registrations(
    tmp_path,
):
    repository, instance, left, right, source_a, source_b = (
        str(uuid4()) for _ in range(6)
    )
    initialize(tmp_path / "context.sqlite3", "context", repository, instance)
    authorization, admission, _ = create_local_admission_service(
        grants=DependencySet(
            provider_registrations={left, right}, sources={source_a, source_b}
        ),
        selection=AdmissionSelection(all_selected=True),
    )
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        for service in (left, right):
            context.provider(service, "github", encode({"name": "same name"}))
        context.source(source_a, left, encode({"name": "same name"}))
        context.source(source_b, right, encode({"name": "same name"}))
        context.provider(right, "github", encode({"name": left}))
        context.source(source_b, right, encode({"name": source_a}))
        assert [
            tuple(row)
            for row in context.db.execute(
                "SELECT service_instance_uuidv4 FROM providers ORDER BY service_instance_uuidv4"
            )
        ] == [(value,) for value in sorted((left, right))]
        assert {
            tuple(row)
            for row in context.db.execute(
                "SELECT source_registration_uuidv4,service_instance_uuidv4 FROM sources"
            )
        } == {(source_a, left), (source_b, right)}
        with pytest.raises(ValueError):
            context.source("same name", left)
        assert context.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 2
    assert not (tmp_path / "repository.sqlite3").exists()


@pytest.mark.parametrize(
    "invalid", ["not-a-uuid", "9ed40fb6-0254-5e7a-82da-8009f471fd45", None]
)
def test_source_registration_rejects_non_uuid4_without_writing(tmp_path, invalid):
    repository, instance, service = (str(uuid4()) for _ in range(3))
    initialize(tmp_path / "context.sqlite3", "context", repository, instance)
    authorization, admission, _ = create_local_admission_service(
        grants=DependencySet(provider_registrations={service}),
        selection=AdmissionSelection(all_selected=True),
    )
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        context.provider(service, "synthetic")
        with pytest.raises((ValueError, TypeError)):
            context.source(invalid, service)
        assert context.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0


def test_repository_name_claim_replay_and_equal_names_keep_independent_originals(
    tmp_path,
):
    repository, instance, other = (str(uuid4()) for _ in range(3))
    initialize(tmp_path / "repository.sqlite3", "repository", repository, instance)
    original = Provenance("synthetic", "original", "capture", "parser", "1", "reported")
    with closing(
        GitRepositoryStore(tmp_path / "repository.sqlite3")
    ) as repository_store:
        repository_store.admit_repository(other)
        for owner in (repository, other):
            claim = RepositoryClaim(owner, "name", "historical same name", original)
            repository_store.admit_repository_claim(claim)
            repository_store.admit_repository_claim(claim)
        rows = repository_store.sql(
            "SELECT repository_uuidv4,field,value,provenance FROM repository_claims ORDER BY repository_uuidv4"
        )
        assert len(rows) == 2 and {row[0] for row in rows} == {repository, other}
        assert rows[0][1:] == rows[1][1:]
        assert (
            len(repository_store.sql("SELECT repository_uuidv4 FROM repositories")) == 2
        )
    assert not (tmp_path / "context.sqlite3").exists()
