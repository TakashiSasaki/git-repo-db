"""Original native ref occurrences remain dependencies of selected PR checks."""

from uuid import uuid4

import pytest

from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    create_local_admission_service,
)
from repo_catalog.domain.exchange import ExchangeSelectionScope
from tests.integration.p5.conftest import init_catalog_stores, write_git_object
from tests.integration.p5.test_pr_assessment import Fixture
from tests.integration.p5.test_pr_native_ref_checks import observe, read_ref


@pytest.mark.parametrize("selective", [False, True])
@pytest.mark.parametrize("changed", [False, True])
def test_full_and_selected_pr_checks_preserve_actual_ref_results_through_onward_exchange(
    tmp_path, selective, changed
):
    fixture = Fixture(tmp_path / "sender")
    fixture.code()
    target = fixture.head
    if changed:
        target = write_git_object(
            fixture.path / "input.git",
            "sha1",
            "commit",
            (
                f"tree {fixture.objects['tree'].object_oid}\n"
                f"parent {fixture.head.object_oid}\n"
                "author New <new@example.com> 1700000400 +0000\n"
                "committer New <new@example.com> 1700000400 +0000\n\n"
                "Actual new remote head\n"
            ).encode(),
        )
    check = read_ref(fixture, target=target)
    observe(fixture, check, state="partial" if changed else "complete")
    before = fixture.query()
    assert before.state == ("partial" if changed else "complete")
    assert before.git_metadata["state"] == "complete"
    selection = (
        ExchangeSelectionScope(
            resource_keys=(fixture.parent,),
            source_uuidv4s=(),
            object_oids=(fixture.head,),
            repository_uuidv4s=(fixture.repository,),
        )
        if selective
        else ExchangeSelectionScope(all_selected=True)
    )
    package = ExchangeService(fixture.path).export_package(selection=selection)
    original_key = tuple(check["ref_observation_key"])
    assert original_key in {
        (row["observation_origin_uuidv4"], row["ref_observation_uuidv7"])
        for row in package.repository_store["ref_observations"]
    }
    assert package.repository_store["ref_enumeration_observations"]
    assert package.repository_store["ref_enumeration_links"]
    assert (target.object_format, target.object_oid) in {
        (row["object_format"], row["object_oid"])
        for row in package.repository_store["git_objects"]
    }
    for name in ("receiver", "onward"):
        directory = tmp_path / name
        init_catalog_stores(directory, repository_uuidv4=fixture.repository)
        auth, admission, _ = create_local_admission_service(
            "exchange_import",
            grants=fixture.grants,
            selection=AdmissionSelection(all_selected=True),
        )
        exchange = ExchangeService(directory, authorization=auth, admission=admission)
        exchange.import_package(
            package,
            new_request=True,
            permitted_repository_uuidv4s=(fixture.repository,),
        )
        assert exchange.import_package(
            package, permitted_repository_uuidv4s=(fixture.repository,)
        ).idempotent_replay
        after = PRQueryService(directory).get_pr_code(fixture.parent)
        assert after.state == before.state
        assert (
            after.anchors == before.anchors and after.collections == before.collections
        )
        assert after.git_metadata["ref_checks"] == before.git_metadata["ref_checks"]
        package = exchange.export_package(selection=selection)


def test_selected_pr_dependencies_cannot_bypass_repository_permission(tmp_path):
    fixture = Fixture(tmp_path / "sender")
    fixture.code()
    check = read_ref(fixture)
    observe(fixture, check)
    selection = ExchangeSelectionScope(
        resource_keys=(fixture.parent,),
        source_uuidv4s=(),
        object_oids=(fixture.head,),
        repository_uuidv4s=(str(uuid4()),),
    )
    package = ExchangeService(fixture.path).export_package(selection=selection)
    assert package.repository_store["ref_observations"] == []
    assert package.repository_store["ref_observation_claims"] == []
    assert package.repository_store["ref_enumeration_observations"] == []
    assert package.context["collections"]
