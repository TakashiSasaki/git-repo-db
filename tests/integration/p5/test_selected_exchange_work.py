"""Selected metadata SQL/work follows actual closure, not unrelated history."""

from contextlib import closing
from dataclasses import replace

from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.exchange import ExchangeSelectionScope
from repo_catalog.domain.p1_context import (
    CoverageScope,
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.p1_repository import (
    OID,
    Provenance,
    RelationGroup,
    RepositoryCoverageScope,
    ScalarClaim,
)
from repo_catalog.domain.production_context import CollectionObservation
from repo_catalog.domain.provider_acquisition import make_provenance
from tests.integration.p5.test_pr_assessment import Fixture
from tests.support.context_admission import fixture_transaction


def measured_export(path, selection):
    """Record the real SQLite VM progress callback independently of row work."""
    service = ExchangeService(path)
    progress = []
    original = service._export_steps

    def measured(amount):
        progress.append(amount)
        return original(amount)  # Preserve the real shared ceiling/interruption.

    service._export_steps = measured
    package = service.export_package(selection=selection)
    assert progress and all(amount == 100 for amount in progress)
    sql_steps = sum(progress)
    assert 0 < sql_steps <= package.selection_report["work"]
    return package, sql_steps


def context_history(fixture, count):
    keys = tuple(
        ResourceKey.from_native(fixture.service, "issue", f"unrelated-{index}")
        for index in range(count)
    )
    grants = replace(fixture.grants, resources=fixture.grants.resources | set(keys))
    with fixture_transaction(fixture.path, grants) as context:
        for index, key in enumerate(keys):
            context.resource(key)
            original = make_provenance(
                "selected-work-fixture", {"read": f"unrelated-{index}"}
            )
            observation = CollectionObservation(
                key, "children", original, "{}", 100, "complete", ()
            )
            context.collection(observation)
            context.prove_collection(
                CoverageClaim(
                    CoverageScope.collection(key, "children", original, "children"),
                    100,
                    "complete",
                ),
                observation,
                required_scope_json="{}",
            )


def test_selected_context_sql_and_work_ignore_unrelated_same_service_capture_history(
    tmp_path,
):
    fixture = Fixture(tmp_path, repository_store=False)
    fixture.code()
    selection = ExchangeSelectionScope(
        include_repository=False,
        object_oids=(),
        resource_keys=(fixture.parent,),
        source_uuidv4s=(),
        repository_uuidv4s=(fixture.repository,),
    )
    before, before_sql = measured_export(tmp_path, selection)
    assert before.context["collections"] and before.context["coverage_proofs"]
    context_history(fixture, 1500)
    after, after_sql = measured_export(tmp_path, selection)
    assert after.context == before.context
    assert after_sql <= before_sql * 1.2 + 4000
    assert (
        after.selection_report["work"] <= before.selection_report["work"] * 1.2 + 4000
    )
    bounded = ExchangeService(tmp_path).export_package(
        selection=replace(
            selection, max_work=before.selection_report["work"] * 2 + 6000
        )
    )
    assert bounded.context == before.context
    assert not any(
        row["reason"] in {"work_limit", "resource_limit"}
        for row in bounded.selection_report["omissions"]
    )
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_selected_repository_sql_and_work_ignore_unrelated_object_claim_group_and_scope_history(
    tmp_path,
):
    fixture = Fixture(tmp_path)
    selected_scope = RepositoryCoverageScope(
        "object", (*fixture.head.key, "reported-inventory")
    )
    with closing(
        GitRepositoryStore(tmp_path / "repository.sqlite3")
    ) as repository_store:
        repository_store.admit_coverage_scope(selected_scope)
        repository_store.admit_coverage(CoverageClaim(selected_scope, 100, "partial"))
    selection = ExchangeSelectionScope(
        include_context=False,
        resource_keys=(),
        source_uuidv4s=(),
        object_oids=(fixture.head,),
        repository_uuidv4s=(fixture.repository,),
    )
    before, before_sql = measured_export(tmp_path, selection)
    assert (
        before.repository_store["retained_metadata"]
        and before.repository_store["coverage_claims"]
    )
    with closing(
        GitRepositoryStore(tmp_path / "repository.sqlite3")
    ) as repository_store:
        for index in range(1500):
            oid = OID("sha1", f"{index + 10000:040x}")
            original = Provenance(
                "selected-work-fixture",
                f"unrelated-{index}",
                "actual-reported-metadata",
                "fixture",
                "1",
            )
            repository_store.admit_claim(ScalarClaim(oid, "type", "commit", original))
            repository_store.admit_group(
                RelationGroup(oid, "commit_parents", "all", "known_empty", (), original)
            )
            scope = RepositoryCoverageScope("object", (*oid.key, "reported-inventory"))
            repository_store.admit_coverage_scope(scope)
            repository_store.admit_coverage(
                CoverageClaim(
                    scope,
                    100,
                    "partial",
                )
            )
    after, after_sql = measured_export(tmp_path, selection)
    assert after.repository_store == before.repository_store
    assert after_sql <= before_sql * 1.2 + 4000
    assert (
        after.selection_report["work"] <= before.selection_report["work"] * 1.2 + 4000
    )
    bounded = ExchangeService(tmp_path).export_package(
        selection=replace(
            selection, max_work=before.selection_report["work"] * 2 + 6000
        )
    )
    assert bounded.repository_store == before.repository_store
    assert not any(
        row["reason"] in {"work_limit", "resource_limit"}
        for row in bounded.selection_report["omissions"]
    )
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def selected_members(path, count):
    fixture = Fixture(path, repository_store=False)
    children = tuple(
        ResourceKey.from_native(fixture.service, "issue", f"selected-{index:05}")
        for index in range(count)
    )
    grants = DependencySet(
        resources={fixture.parent, *children}, provider_registrations={fixture.service}
    )
    original = make_provenance("selected-work-fixture", {"read": "actual-enumeration"})
    with fixture_transaction(path, grants) as context:
        for child in children:
            context.resource(child)
            context.admit_field(
                FieldCandidate(
                    child,
                    "title",
                    canonical("actual selected title"),
                    FieldClock("fixture", 100),
                    original,
                    100,
                )
            )
        observation = CollectionObservation(
            fixture.parent, "children", original, "{}", 100, "complete", children
        )
        context.collection(observation)
        context.prove_collection(
            CoverageClaim(
                CoverageScope.collection(
                    fixture.parent, "children", original, "children"
                ),
                100,
                "complete",
            ),
            observation,
            required_scope_json="{}",
        )
    selection = ExchangeSelectionScope(
        include_repository=False,
        object_oids=(),
        resource_keys=(fixture.parent,),
        source_uuidv4s=(),
        repository_uuidv4s=(fixture.repository,),
    )
    return measured_export(path, selection)


def test_actual_selected_member_volume_has_linear_cumulative_sql_and_proof_work(
    tmp_path,
):
    (small, small_sql), (large, large_sql) = (
        selected_members(tmp_path / str(count), count) for count in (50, 200)
    )
    assert large_sql <= small_sql * 4.5 + 4000
    assert len(small.context["resources"]) == 51
    assert len(large.context["resources"]) == 201
    assert (
        len(large.context["field_candidates"]) - len(small.context["field_candidates"])
        == 150
    )
    assert large.selection_report["work"] <= small.selection_report["work"] * 4.5 + 4000
    assert (
        len(large.context["collections"]) == len(large.context["coverage_proofs"]) == 1
    )


def test_selected_metadata_cursor_cannot_accept_sql_or_project_retained_bodies(
    tmp_path,
):
    import pytest

    from repo_catalog.domain.p1_repository import RepositoryFailure
    from repo_catalog.domain.query_work import UnlimitedWorkBudget

    fixture = Fixture(tmp_path)
    with closing(
        GitRepositoryStore(tmp_path / "repository.sqlite3")
    ) as repository_store:
        with pytest.raises(TypeError):
            repository_store._open_export_metadata_cursor(
                "repositories",
                (),
                lengths=False,
                selected_query="SELECT body FROM retained_metadata",
            )
        with pytest.raises(RepositoryFailure) as refused:
            repository_store._open_export_metadata_cursor(
                "repositories",
                (),
                lengths=False,
                selection_mode="SELECT body FROM retained_metadata",
            )
        assert refused.value.code == "QUERY_BUDGET"
        rows = repository_store.exchange_metadata_rows(
            "retained_metadata", (), UnlimitedWorkBudget(), keys=(fixture.head.key,)
        )
        assert rows and all(
            row["object_oid"] == fixture.head.object_oid for row in rows
        )
        assert all("body" not in row.keys() for row in rows)
    assert not (tmp_path / "p1-recovery-stop.json").exists()
